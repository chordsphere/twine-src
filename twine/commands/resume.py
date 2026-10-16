"""`twine resume` — continue a kept session cold, from its transcript, with
the planner's answer — or, when it was only stopped, twine's own words — as
the next user turn (Arc 2 R5; D23; twine-run-recovery; cli-contract.md §19,
runtime-contract.md §7.9).

    twine resume SID --cap USD|+USD [--answer FILE|-] [--script FILE]
                 [--model M] [--max-tokens N] [--thinking adaptive|off]
                 [--prices PATH] [--max-turns N] [--window N]
                 [--state-dir DIR] [--bale-root DIR] [--cwd DIR] [--json]
    twine resume SID --plan [--state-dir DIR] [--prices PATH] [--json]

**The rule** (twine-run-recovery): a run `twine run` or `twine resume` left
`stopped`, `cap-reached`, `cap-unchecked`, `ended` or `suspended` resumes
with `twine resume`, in its kept home, from its transcript;
`respawn-from-request` is the last resort — for a home that is gone, or a
session bale has closed. A `killed` session is one bale closed (`twine kill`
unlocks it `aborted`): `twine resume` refuses it, naming the respawn path.

What it resumes: any run whose in-flight record (with its `runtime` fields)
and transcript are kept. Under the same sid, cold (D23): nothing was held
hot, so the conversation is rebuilt from the transcript's `request` lines
(twine.runtime.resume) and the first call re-warms the cache — its usage is
the twin's `rewarm`, D23's named telemetry field.

  0. refused before anything starts, every reason at once: the sid, the
     state directory; no in-flight record, or one without `runtime` fields
     (never hosted, or delivered); its transcript missing or unreadable as a
     conversation; its last run `killed` (or an abort request standing: a
     kill closed the session); its sandbox home missing, or not this state
     directory's; `--answer` missing on a `suspended` session (an answer is
     what a suspended worker waits for; on any other outcome it is optional
     and `RESUME_TEXT` is sent), unreadable or empty (`-` reads stdin);
     `--cap` absent or not dollars or `+dollars` (D15; `+USD` is the
     session's spend so far plus that amount, and refuses when that spend
     cannot be priced); the recorded adapter's arguments — `fake` needs
     `--script`, `anthropic` refuses one and needs ANTHROPIC_API_KEY;
     `--model`, `--max-tokens` or `--thinking` given and differing from the
     transcript's last `run-start` (D12: spawn-time constants — a different
     one is a new session, not a resume); the limits; the tool registry and
     the transition table, as `twine run` refuses them. **No `bale open`**:
     the session is open in bale already (bale suspended it on the
     clarification, or left it open on the light block).
  1. as `twine run` from its step 3: the running record (lead_own_group,
     register_running) before anything is spawned; the sandbox reused
     (Sandbox.create on the existing home — the request is already unpacked
     there, and is not unpacked again); the adapter spawned with the
     transcript's constants and the key as before, and the window
     (`--window`, or the adapter's statement); the transcript appended to —
     a `run-start` carrying `resumed_from`, the `seq` of the line before it,
     and `cap_given`, the `--cap` as typed; the in-flight record's `runtime`
     fields replaced; the loop, its messages the rebuilt conversation plus
     one user message, the answer.
  2. the end as `twine run`'s: the running record cleared; on `delivered`
     the in-flight record removed and the home kept; otherwise both kept —
     a resumed run can suspend again, and a transcript carries any number of
     runs. The twin's `next` and the human `next:` lines name the command the
     ending names (recovery.next_commands).

**`--plan`** reads and writes nothing: the session's transcript, its spend
stream, its in-flight record and its sandbox home, no bale started and no
model called. It says whether the session resumes (the rule above and the
`killed` refusal) and with what line, and suggests a cap (twine.recovery:
the rule is stated there and in cli-contract.md §19.1). Its twin is
`command` `"resume"` with `plan` true.

Like `twine run` it appends one `runs.jsonl` line on every outcome (`command`
`"resume"`, `desk` null; cli-contract.md §20.1) and prints its apply lines with
the session's cost file (§18.7a) — the file sums every record of the sid, the
earlier runs' included.

The twin is `twine run`'s (cli-contract.md §18.5), `command` `"resume"`,
`open` null, `resumed_from` set and `rewarm` the first call's usage. ok
exactly on `delivered`. Like `run`, it never applies anything (T12) and
imports no process-spawning module: bale runs through ctx.run, the tools
through the sandbox.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from twine import cost, inflight, kill, process, recovery, spend
from twine.cli import Context
from twine.commands import run as run_verb
from twine.commands.carry_bale import BALE_ROOT_ARGUMENT
from twine.commands.kill import state_dir_fault
from twine.registry import Argument, Command, Result
from twine.runtime import loop as runloop
from twine.runtime.adapters.anthropic import KEY_VARIABLE
from twine.runtime.boundary import Boundary, BoundaryError
from twine.runtime.resume import (RESUME_SOURCE, RESUME_TEXT, Conversation, ResumeError,
                                  read_conversation)
from twine.runtime.sandbox import HOME_NAME, SANDBOX_SUBDIR, Sandbox, SandboxError
from twine.transcript import Transcript, TranscriptError, transcript_path

log = logging.getLogger("twine.resume")

NAME = "resume"
STDIN = "-"


@dataclasses.dataclass
class Prepared:
    """What the refusals found, for the sequence: the in-flight record, the
    rebuilt conversation, the answer, the adapter class and its script and
    key, the registry and the table, and the repo bale and the tools run in."""

    record: dict[str, Any]
    conversation: Conversation
    answer: str
    answer_source: str
    adapter_cls: type
    script: Any
    key: str | None
    tools: Any
    moves: runloop.MoveBook
    cwd: str
    home: Path


# ---------------------------------------------------------------------------
# The verb
# ---------------------------------------------------------------------------


def cmd_resume(ctx: Context, args: argparse.Namespace) -> Result:
    if args.plan:
        return cmd_plan(ctx, args)
    sid = args.sid if kill.is_sid(args.sid) else None
    report = run_verb.RunReport(bundle=args.sid, adapter=None, command=NAME, resume_sid=sid)
    try:
        resume(ctx, args, report)
    except Exception:
        log.exception("twine resume: internal error")
        if report.transcript is not None:
            run_verb._log_end(report, internal_error=True)
        raise
    finally:
        run_verb.finish_running(ctx, report)
    if report.result is None and report.running_registered:
        report.refusals.append(
            f"nothing ran in {report.sid}; it is as it was — still open in bale, its "
            f"transcript and in-flight record kept: fix the fault and resume again, or "
            f"close it with `twine kill {report.sid}`")
    run_verb.name_next(report, args, ctx)
    payload = report.payload()
    if report.transcript is not None:
        run_verb._log_end(report)
    run_verb.write_run_line(ctx, report, payload)
    ctx.info(f"{NAME}: {run_verb.summary_line(report)}")
    run_verb.say_next(ctx, report)
    return Result(report.ok, payload, run_verb.lines(report))


def resume(ctx: Context, args: argparse.Namespace, report: run_verb.RunReport) -> None:
    """The sequence (module docstring), filling `report`."""
    prepared = pre_start(ctx, args, report)
    if report.refusals:
        ctx.info(f"resume {args.sid}: refused — {report.reason}")
        return
    assert prepared is not None and report.sid is not None and report.state_dir is not None
    sid, state_dir = report.sid, report.state_dir
    start = prepared.conversation.run_start
    courier = dataclasses.replace(ctx, env={k: v for k, v in ctx.env.items()
                                            if k != KEY_VARIABLE})
    # 3. The running record, before anything is spawned.
    try:
        report.group = lead_own_group()
    except OSError as exc:
        report.refusals.append(f"the runtime could not lead a process group of its own "
                               f"(setsid: {exc.strerror or exc}), so the kill-switch could "
                               "not find it; nothing was started")
        return
    if report.group.setsid:
        ctx.info(f"resume: the runtime was not its group's leader; it called setsid and "
                 f"leads group {report.group.pgid}")
    try:
        kill.register_running(state_dir, sid, report.group.pgid, report.group.pid)
    except (kill.RunningRecordError, kill.KillError) as exc:
        report.refusals.append(f"the running record could not be written ({exc}); nothing "
                               "is started that the kill-switch could not reach")
        return
    report.running_registered = True
    ctx.info(f"resume: running record for {sid}: group {report.group.pgid}")
    # 4. The sandbox, reused: the request is unpacked there already.
    try:
        report.sandbox = Sandbox.create(state_dir, sid, repo=Path(prepared.cwd), run=ctx.run)
    except SandboxError as exc:
        report.refusals.append(str(exc))
        return
    report.unpacked = runloop.Unpacked(report.sandbox.home / runloop.REQUEST_DIR,
                                       members=None, stripped=None)  # type: ignore[arg-type]
    ctx.info(f"resume: sandbox {report.sandbox.home} reused (network "
             f"{report.sandbox.network}, filesystem {report.sandbox.filesystem}); the "
             "request at request/ is not unpacked again")
    # 5. The adapter with the transcript's constants, and the window.
    spawn = argparse.Namespace(adapter=start.adapter, max_tokens=start.max_tokens,
                               thinking=start.thinking)
    prompt = runloop.system_prompt(prepared.tools)
    try:
        boundary = Boundary(run_verb.build_adapter(spawn, report, prepared.adapter_cls,
                                                   prepared.script, prepared.key, prompt))
    except (BoundaryError, ValueError, TypeError) as exc:
        report.refusals.append(f"the {start.adapter} adapter could not be spawned: {exc}")
        return
    report.window = run_verb.spawn_window(ctx, args, boundary, label=NAME)
    # 6. The transcript, appended to: the run-start names the line before it.
    try:
        report.transcript = Transcript.open(state_dir, sid)
    except (TranscriptError, ValueError) as exc:
        report.refusals.append(f"the transcript cannot be opened: {exc}")
        return
    report.resumed_from = report.transcript.next_seq - 1
    report.transcript.append(
        "run-start", adapter=start.adapter, model=start.model, max_tokens=start.max_tokens,
        thinking=start.thinking, sandbox=report.sandbox.as_json(),
        request=report.unpacked.as_json(), open=None, group=report.group.as_json(),
        cap_usd=spend.usd(report.cap_usd), cap_given=run_verb.cap_given(report),
        max_turns=report.max_turns, system=prompt.as_json(), window=report.window.start_json(),
        resumed_from=report.resumed_from,
        answer={"source": prepared.answer_source,
                "sha256": hashlib.sha256(prepared.answer.encode("utf-8")).hexdigest(),
                "chars": len(prepared.answer)},
        rebuilt={"messages": prepared.conversation.messages_total,
                 "request_lines": prepared.conversation.request_lines,
                 "runs": prepared.conversation.runs})
    # 7. The in-flight record's runtime fields, replaced.
    try:
        inflight.record_runtime(state_dir, sid, inflight.runtime_fields(
            adapter=start.adapter, model=start.model, sandbox_home=str(report.sandbox.home),
            transcript=str(report.transcript.path), pgid=report.group.pgid))
    except (inflight.InflightError, ValueError) as exc:
        report.inflight_error = str(exc)
        ctx.info(f"warning: the in-flight record's runtime fields were not written: {exc}")
    report.inflight_state = run_verb.INFLIGHT_KEPT
    # 8. The loop: the conversation as it was, then the answer.
    rebuilt = [dict(m) for m in prepared.conversation.messages]
    ctx.info(f"resume: {sid}: the loop starts cold — {len(rebuilt)} message(s) rebuilt from "
             f"the transcript, the answer appended ({start.adapter}, model {start.model}, cap "
             f"{spend.dollars(report.cap_usd)})")
    bale_args = argparse.Namespace(cwd=prepared.cwd, bale_root=args.bale_root)
    the_loop = runloop.Loop(
        boundary=boundary, sandbox=report.sandbox, transcript=report.transcript,
        settings=runloop.LoopSettings(sid=sid, state_dir=state_dir,
                                      cap_usd=report.cap_usd or Decimal(0),
                                      model=start.model, max_tokens=start.max_tokens,
                                      max_turns=report.max_turns or runloop.DEFAULT_MAX_TURNS,
                                      prices_path=report.prices_path),
        prompt=prompt, moves=prepared.moves, tools=prepared.tools,
        deliver=lambda path: run_verb.deliver(courier, bale_args, path, report),
        messages=[*rebuilt, runloop.user_message(prepared.answer)], logged=len(rebuilt),
        window=report.window, progress=lambda line: ctx.info(f"resume: {line}"))
    report.result = the_loop.run()
    report.wall_seconds = the_loop.elapsed()
    if report.result.outcome == runloop.DELIVERED:
        try:
            removed = inflight.remove_inflight(state_dir, sid)
            report.inflight_state = (run_verb.INFLIGHT_REMOVED if removed
                                     else report.inflight_state)
        except inflight.InflightError as exc:
            report.inflight_error = str(exc)
            ctx.info(f"warning: the in-flight record could not be removed: {exc}")
    ctx.info(f"resume: {sid}: {report.outcome}"
             + (f" — {report.reason}" if report.reason else "")
             + f"; sandbox home kept at {report.sandbox.home}")


def lead_own_group() -> process.OwnGroup:
    """The runtime's own group. A name of this module's, so a test that runs
    the verb in its own process can stand a child in for it."""
    return process.lead_own_group()


# ---------------------------------------------------------------------------
# Refused before anything starts
# ---------------------------------------------------------------------------


def pre_start(ctx: Context, args: argparse.Namespace,
              report: run_verb.RunReport) -> Prepared | None:
    """Every refusal before the runtime registers, named at once. Returns
    what the sequence needs, or None when anything refused."""
    refusals = report.refusals
    sid = report.sid
    if sid is None:
        refusals.append(f"{args.sid!r} is not a session id twine accepts")
    # The cap (D15: an absent cap refuses — named here, with the rest). `+USD`
    # waits for the state directory: it is the spend so far plus the amount.
    if args.cap is None:
        refusals.append("--cap USD is required (or +USD, the session's spend so far plus "
                        "that amount): the session's hard cap is checked before every call "
                        "(D15), and an absent cap refuses; `twine resume SID --plan` "
                        "suggests one")
    else:
        run_verb.parse_cap(report, args.cap, refusals)
    answer = answer_source = None
    if args.answer is not None:
        answer, answer_source = read_answer(ctx, args.answer, refusals)
    for flag, value, what in (("--max-tokens", args.max_tokens, "tokens"),
                              ("--max-turns", args.max_turns, "calls")):
        if value is not None and value <= 0:
            refusals.append(f"{flag} {value} is not a positive number of {what}")
    report.max_turns = args.max_turns
    window_fault = run_verb.window_refusal(args.window)
    if window_fault is not None:
        refusals.append(window_fault)
    if args.prices is not None:
        if not args.prices:
            refusals.append("--prices is empty; it names no price file")
        else:
            report.prices_path = Path(args.prices).expanduser().resolve()
    # The state directory, the in-flight record, the transcript, the home.
    record = conversation = None
    home: Path | None = None
    try:
        where = spend.resolve_state_dir(args.state_dir, ctx.env)
    except spend.SpendError as exc:
        refusals.append(f"{exc.message} — twine resume reads the session's in-flight "
                        "record, transcript and sandbox there")
    else:
        report.state_dir, report.state_dir_source = where.path, where.source
        fault = state_dir_fault(where.path)
        if fault is not None:
            refusals.append(f"the state directory {where.path} (from {where.source}) {fault}")
        elif sid is not None:
            record, conversation, home = kept_session(where.path, sid, refusals)
            run_verb.resolve_cap(report, sid, label=NAME)
    if conversation is not None and report.state_dir is not None and sid is not None:
        answer, answer_source = last_run_rules(args, report.state_dir, sid, answer,
                                               answer_source, refusals)
    if record is not None:
        report.inflight_state = run_verb.INFLIGHT_KEPT
    # The adapter the record names, and its arguments.
    adapter_cls = script = key = None
    if record is not None:
        report.adapter = record["runtime"]["adapter"]
        report.model = record["runtime"]["model"]
        adapter_cls, script, key = adapter_arguments(ctx, args, report.adapter, refusals)
    if conversation is not None:
        constants_refusals(args, conversation, refusals)
        report.model = conversation.run_start.model
    tools = run_verb.tool_registry(refusals)
    moves = run_verb.move_book(refusals)
    if refusals:
        return None
    assert record is not None and conversation is not None and home is not None
    return Prepared(record=record, conversation=conversation, answer=answer or "",
                    answer_source=answer_source or "", adapter_cls=adapter_cls,
                    script=script, key=key, tools=tools, moves=moves,
                    cwd=args.cwd or record["cwd"], home=home)


def last_run_rules(args: argparse.Namespace, state_dir: Path, sid: str, answer: str | None,
                   source: str | None, refusals: list[str]) -> tuple[str | None, str | None]:
    """What the transcript's last run's end decides: a `killed` session is
    refused (a kill is a close: the respawn path is named), and `--answer` is
    required only on a `suspended` one — on any other outcome (or a run that
    never ended) an absent answer is `RESUME_TEXT`, from source `twine`."""
    story = recovery.read_story(transcript_path(state_dir, sid))
    if story.outcome == recovery.KILLED or kill.abort_requested(state_dir, sid):
        refusals.append(recovery.killed_refusal(sid))
    if args.answer is None:
        if story.outcome in recovery.ANSWER_REQUIRED_ON:
            refusals.append("--answer FILE|- is required on a suspended session: the "
                            "planner's answer is what the suspended worker waits for, the "
                            "next user turn of the resumed conversation")
        else:
            return RESUME_TEXT, RESUME_SOURCE
    return answer, source


def read_answer(ctx: Context, name: str, refusals: list[str]
                ) -> tuple[str | None, str | None]:
    """The planner's answer — the packer's words for a light block, or the
    worker-facing block `bale relay` printed for a clarification — from a
    file, or from stdin for `-`; refused when unreadable, not UTF-8 or empty.
    Returned as given: the loop sends it unchanged. (Absent is
    `last_run_rules`'s: required only on a suspended session.)"""
    if name == STDIN:
        source = "stdin"
        try:
            data = ctx.stdin.read()
        except (OSError, ValueError) as exc:
            refusals.append(f"--answer -: stdin cannot be read: {exc}")
            return None, None
    else:
        source = str(Path(name).expanduser())
        try:
            data = Path(name).expanduser().read_bytes()
        except FileNotFoundError:
            refusals.append(f"--answer {name}: no such file")
            return None, None
        except OSError as exc:
            refusals.append(f"--answer {name} cannot be read: {exc.strerror or exc}")
            return None, None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        refusals.append(f"--answer {name}: not UTF-8 text ({exc})")
        return None, None
    if not text.strip():
        refusals.append(f"--answer {name} is empty: there is no answer to resume on")
        return None, None
    return text, source


def kept_session(state_dir: Path, sid: str, refusals: list[str]
                 ) -> tuple[dict[str, Any] | None, Conversation | None, Path | None]:
    """The session `twine run` kept: its in-flight record with `runtime`
    fields, the conversation its transcript holds, and its sandbox home —
    each refused, named, when it is not there or not this state
    directory's."""
    try:
        record = inflight.read_inflight(state_dir, sid)
    except inflight.InflightRecordError as exc:
        refusals.append(f"the in-flight record of {sid} cannot be read: {exc}")
        return None, None, None
    if record is None:
        refusals.append(f"no in-flight record of {sid} under {state_dir}: twine never opened "
                        "it here, or it was delivered (the record is removed then) — there "
                        "is no kept session to resume" + delivered_hint(state_dir, sid))
        return None, None, None
    runtime = record.get(inflight.RUNTIME_KEY)
    if runtime is None:
        refusals.append(f"the in-flight record of {sid} has no runtime fields: twine never "
                        "hosted the session (carry bundle opened it, nothing ran), so "
                        "there is no transcript to resume from")
        return None, None, None
    expected = transcript_path(state_dir, sid)
    named = Path(runtime["transcript"])
    conversation = None
    if named != expected:
        refusals.append(f"the in-flight record names the transcript {named}, and this state "
                        f"directory's is {expected}: resume with the state directory the "
                        "run used")
    else:
        try:
            conversation = read_conversation(named)
        except ResumeError as exc:
            refusals.append(str(exc))
    home = Path(runtime["sandbox_home"])
    own_home = (state_dir / SANDBOX_SUBDIR / sid / HOME_NAME)
    if not home.is_dir():
        refusals.append(f"the sandbox home the record names, {home}, does not exist: the "
                        "session's files and its unpacked request are gone")
        home = None
    elif home.resolve() != own_home.resolve():
        refusals.append(f"the sandbox home the record names, {home}, is not this state "
                        f"directory's ({own_home})")
        home = None
    elif not (home / runloop.REQUEST_DIR).is_dir():
        refusals.append(f"the sandbox home {home} holds no request/: the request is not "
                        "unpacked there, and a resume does not unpack it again")
        home = None
    if conversation is None or home is None:
        return record, None, None
    return record, conversation, home


def delivered_hint(state_dir: Path, sid: str) -> str:
    """When the transcript says the session was delivered, the response it
    delivered and its apply line — what to do with a session there is
    nothing to resume in; empty otherwise."""
    story = recovery.read_story(transcript_path(state_dir, sid))
    if story.outcome != recovery.DELIVERED:
        return ""
    line, tarball = story.field("apply_line"), story.field("tarball")
    if not line:
        return f"; its transcript says it was delivered ({tarball or 'no tarball named'})"
    return f"; its transcript says it was delivered, and the response applies with `{line}`"


def adapter_arguments(ctx: Context, args: argparse.Namespace, adapter: str,
                      refusals: list[str]) -> tuple[type | None, Any, str | None]:
    """The class of the adapter the record names, the fake's parsed script
    and the Anthropic adapter's key — each refused as `twine run` refuses
    them."""
    script = key = None
    if adapter == run_verb.FAKE:
        if args.script is None:
            refusals.append("the session ran on the fake adapter, which needs --script FILE "
                            "to play")
        else:
            script = run_verb.read_script(args.script, refusals)
    else:
        if args.script is not None:
            refusals.append(f"--script is the fake adapter's; the session ran on {adapter}, "
                            "which reads no script")
        key = ctx.env.get(KEY_VARIABLE)
        if not isinstance(key, str) or not key.strip():
            refusals.append(f"{KEY_VARIABLE} is not set (or is empty) in the environment "
                            f"twine was started with; the {adapter} adapter does not start "
                            "without its key")
            key = None
    try:
        cls = runloop.adapter_class(adapter)
    except runloop.LoopError as exc:
        refusals.append(f"the session's adapter: {exc}")
        cls = None
    return cls, script, key


def constants_refusals(args: argparse.Namespace, conversation: Conversation,
                       refusals: list[str]) -> None:
    """D12: the model, max_tokens and thinking are spawn-time constants. A
    resume spawns with the transcript's; one given and different is a new
    session, not a resume."""
    start = conversation.run_start
    for flag, given, recorded in (("--model", args.model, start.model),
                                  ("--max-tokens", args.max_tokens, start.max_tokens),
                                  ("--thinking", args.thinking, start.thinking)):
        if given is not None and given != recorded:
            refusals.append(f"{flag} {given} differs from the transcript's {recorded!r} (its "
                            f"run-start at seq {start.seq}): it is a spawn-time constant "
                            "(D12), and a different one is a new session, not a resume")
    if start.thinking not in run_verb.THINKING_CHOICES:
        refusals.append(f"the transcript's run-start says thinking {start.thinking!r}, not one "
                        f"of {', '.join(run_verb.THINKING_CHOICES)}")


# ---------------------------------------------------------------------------
# --plan: the recovery reading
# ---------------------------------------------------------------------------

# The keys of the plan's twin after `command` and `ok`, in this order.
PLAN_KEYS = ("plan", "sid", "outcome", "stop", "move", "actor", "resumable", "why", "window",
             "calls", "spend_usd", "per_call_usd", "next_call_worst_usd", "suggested_cap_usd",
             "last_tools", "home", "next", "reason")
# The flags a plan has no use for: accepted, said to be ignored.
PLAN_IGNORES = (("--cap", "cap"), ("--answer", "answer"), ("--script", "script"),
                ("--model", "model"), ("--max-tokens", "max_tokens"),
                ("--thinking", "thinking"), ("--window", "window"))


@dataclasses.dataclass
class Plan:
    """`twine resume SID --plan`: what the session says about going on.
    `ok` is true exactly when it could be read; `resumable` is the rule's
    verdict on it, `why` the refusal's reason when it is not."""

    sid: str | None
    ok: bool = False
    outcome: str | None = None
    stop: str | None = None
    move: str | None = None
    actor: str | None = None
    resumable: bool = False
    why: str | None = None
    window: dict[str, Any] | None = None
    advice: recovery.Advice = dataclasses.field(default_factory=recovery.Advice)
    suggested: Decimal | None = None
    last_tools: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    home: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"path": None, "exists": False, "entries": []})
    next: list[str] = dataclasses.field(default_factory=list)
    reason: str | None = None
    state_dir: Path | None = None

    def payload(self) -> dict[str, Any]:
        a = self.advice
        return {
            "plan": True, "sid": self.sid, "outcome": self.outcome, "stop": self.stop,
            "move": self.move, "actor": self.actor, "resumable": self.resumable,
            "why": self.why, "window": self.window, "calls": a.calls,
            "spend_usd": spend.usd(a.spent), "per_call_usd": spend.usd(a.per_call),
            "next_call_worst_usd": spend.usd(a.worst),
            "suggested_cap_usd": spend.usd(self.suggested),
            "last_tools": list(self.last_tools), "home": dict(self.home),
            "next": list(self.next), "reason": self.reason}

    def lines(self) -> list[str]:
        """Human mode: the facts, one per line, then the `next` lines last."""
        if not self.ok:
            return [f"resume {self.sid or 'SID'} --plan: cannot be read — {self.reason}"]
        a = self.advice
        out = [f"resume plan for {self.sid} (state directory {self.state_dir})"]
        if self.outcome is None:
            out.append("outcome: unknown — the transcript's last run did not end")
        else:
            out.append(f"outcome: {self.outcome}"
                       + (f", stop {self.stop}" if self.stop else "")
                       + (f", move {self.move} ({self.actor}'s)" if self.move else ""))
        if self.reason:
            out.append(f"reason: {self.reason}")
        out.append("resumable: yes" if self.resumable else f"resumable: no — {self.why}")
        if self.window is None:
            out.append("window: no call counted one")
        else:
            size, used = self.window.get("size"), self.window.get("used")
            fraction = self.window.get("fraction")
            out.append(f"window: {used} of {size} input tokens in use ({fraction * 100:.0f}%)"
                       if size and fraction is not None
                       else f"window: {used} input tokens in use (its size is unknown)")
        out.append(f"calls: {'unknown' if a.calls is None else a.calls}")
        out.append(f"spend so far: {spend.dollars(a.spent)}")
        out.append("per call, the mean of the last ten: "
                   + ("none yet" if a.calls == 0 else spend.dollars(a.per_call)))
        out.append(f"next call's worst case: {spend.dollars(a.worst)}")
        if self.suggested is not None:
            out.append(f"suggested cap: ${self.suggested:.2f} = {a.arithmetic()}")
        else:
            out.append("suggested cap: none"
                       + (f" — {a.problem}" if a.problem else
                          " — the session is not resumable" if not self.resumable else ""))
        for tool in self.last_tools:
            out.append(f"last tool: call {tool['call']} {tool['name']}"
                       + (f" — {tool['what']}" if tool["what"] else ""))
        home = self.home
        out.append(f"home: {home['path']} ("
                   + (f"{len(home['entries'])} entries: {', '.join(home['entries'])}"
                      if home["exists"] else "gone") + ")")
        out += [f"next: {line}" for line in self.next]
        return out


def cmd_plan(ctx: Context, args: argparse.Namespace) -> Result:
    """`twine resume SID --plan`: read, write nothing, start nothing."""
    ignored = [flag for flag, name in PLAN_IGNORES
               if getattr(args, name, None) is not None]
    if ignored:
        ctx.info(f"resume --plan reads the session and starts nothing: {', '.join(ignored)} "
                 "ignored")
    plan = make_plan(ctx, args)
    return Result(plan.ok, plan.payload(), plan.lines())


def unreadable(plan: Plan, why: str) -> Plan:
    plan.ok, plan.resumable, plan.why, plan.reason = False, False, why, why
    return plan


def make_plan(ctx: Context, args: argparse.Namespace) -> Plan:
    plan = Plan(sid=args.sid if kill.is_sid(args.sid) else None)
    if plan.sid is None:
        return unreadable(plan, f"{args.sid!r} is not a session id twine accepts")
    sid = plan.sid
    try:
        where = spend.resolve_state_dir(args.state_dir, ctx.env)
    except spend.SpendError as exc:
        return unreadable(plan, f"{exc.message} — twine resume --plan reads the session's "
                                "transcript, spend, in-flight record and sandbox there")
    fault = state_dir_fault(where.path)
    if fault is not None:
        return unreadable(plan, f"the state directory {where.path} (from {where.source}) "
                                f"{fault}")
    state_dir = plan.state_dir = where.path
    transcript = transcript_path(state_dir, sid)
    try:
        conversation = read_conversation(transcript)
    except ResumeError as exc:
        return unreadable(plan, str(exc))
    story = recovery.read_story(transcript)
    plan.ok = True
    plan.outcome, plan.stop, plan.move = story.outcome, story.field("stop"), story.field("move")
    plan.actor, plan.reason = story.field("actor"), story.field("reason")
    plan.window, plan.last_tools = (None if story.window is None else dict(story.window),
                                    list(story.tools))
    # The refusals: the rule's (a kept record, transcript and home), and `killed`.
    refusals: list[str] = []
    record, _, home = kept_session(state_dir, sid, refusals)
    if story.outcome == recovery.KILLED or kill.abort_requested(state_dir, sid):
        refusals.append(recovery.killed_refusal(sid))
    elif story.outcome == recovery.DELIVERED and record is not None:
        refusals.append(f"{sid} was delivered: there is nothing to resume, its response "
                        "applies with `" + str(story.field("apply_line")) + "`")
    plan.resumable = not refusals
    plan.why = "; ".join(refusals) if refusals else None
    prices = Path(args.prices).expanduser().resolve() if args.prices else None
    plan.advice = recovery.advise(state_dir, sid, conversation, story.window, prices)
    plan.suggested = plan.advice.suggested if plan.resumable else None
    plan.home = home_facts(state_dir, sid, record)
    if plan.resumable or story.outcome == recovery.DELIVERED:
        plan.next = recovery.next_commands(
            sid, outcome=story.outcome, stop=plan.stop, move=plan.move,
            apply_line=story.field("apply_line"), light_block=bool(story.field("block")),
            tarball=story.field("tarball"), dry_run=story.field("dry_run"),
            suggested=plan.suggested, carried=recovery.Carried.of(args), plannable=False,
            cost_file=kept_cost_file(state_dir, sid))
    return plan


def kept_cost_file(state_dir: Path, sid: str) -> str | None:
    """The session's cost file when one is kept (the run that printed an apply
    line wrote it; the plan writes nothing, so it names the file only when it
    is there — a `bale apply --cost-file` on an absent file is refused)."""
    path = cost.cost_path(state_dir, sid)
    return str(path) if path.is_file() else None


def home_facts(state_dir: Path, sid: str, record: dict[str, Any] | None) -> dict[str, Any]:
    """The sandbox home as the plan shows it: the path the record names (or
    the state directory's own), whether it exists, and its top-level names,
    sorted."""
    runtime = None if record is None else record.get(inflight.RUNTIME_KEY)
    named = runtime.get("sandbox_home") if isinstance(runtime, dict) else None
    path = Path(named) if named else state_dir / SANDBOX_SUBDIR / sid / HOME_NAME
    entries: list[str] = []
    exists = path.is_dir()
    if exists:
        try:
            entries = sorted(os.listdir(path))
        except OSError as exc:
            log.warning("cannot list the sandbox home %s: %s", path, exc)
    return {"path": str(path), "exists": exists, "entries": entries}


COMMANDS = (
    Command(
        name=NAME,
        summary="resume a kept session cold from its transcript, the planner's answer as "
                "the next user turn",
        handler=cmd_resume,
        arguments=(
            Argument(("sid",), {
                "metavar": "SID",
                "help": "the session `twine run` left suspended (or ended, stopped, killed, "
                        "cap-*), its in-flight record and transcript kept"}),
            Argument(("--cap",), {
                "metavar": "USD|+USD", "default": None,
                "help": "the session's hard cap in US dollars (D15), checked before every "
                        "call; required — an absent cap refuses. The cap is cumulative per "
                        "session: `+USD` is the spend so far plus that amount, and "
                        "`--plan` suggests one"}),
            Argument(("--answer",), {
                "metavar": "FILE|-", "default": None,
                "help": "the planner's answer — the packer's words for a light block, or "
                        "the worker-facing block `bale relay` printed for a clarification; "
                        "`-` reads stdin; required on a suspended session, optional "
                        "otherwise (absent, twine sends its own one-line RESUME_TEXT)"}),
            Argument(("--plan",), {
                "action": "store_true", "default": False,
                "help": "read the session — transcript, spend, in-flight record, sandbox "
                        "home — and say whether it resumes, with what line and what cap; "
                        "writes nothing, starts no bale, calls no model"}),
            Argument(("--script",), {
                "metavar": "FILE", "default": None,
                "help": "the fake adapter's script, when the session ran on the fake"}),
            Argument(("--model",), {
                "metavar": "M", "default": None,
                "help": "must equal the transcript's: a spawn-time constant (D12)"}),
            Argument(("--max-tokens",), {
                "metavar": "N", "type": int, "default": None,
                "help": "must equal the transcript's when given (D12)"}),
            Argument(("--thinking",), {
                "choices": run_verb.THINKING_CHOICES, "default": None,
                "help": "must equal the transcript's when given (D12)"}),
            Argument(("--prices",), {
                "metavar": "PATH", "default": None,
                "help": "the price file (default <state-dir>/prices.toml)"}),
            Argument(("--max-turns",), {
                "metavar": "N", "type": int, "default": runloop.DEFAULT_MAX_TURNS,
                "help": "twine's own limit on this run's model calls (default "
                        f"{runloop.DEFAULT_MAX_TURNS})"}),
            run_verb.WINDOW_ARGUMENT,
            Argument(("--state-dir",), {
                "metavar": "DIR", "default": None,
                "help": "twine's state directory: the one the run used"}),
            BALE_ROOT_ARGUMENT,
            Argument(("--cwd",), {
                "metavar": "DIR", "default": None,
                "help": "the repo bale and probe run in (default: the in-flight record's "
                        "cwd, where the session was opened)"}),
        ),
        description="Resume SID cold (D23): rebuild its conversation from the transcript "
                    "`twine run` kept (the request lines' appended messages, joined), "
                    "append the planner's answer — or, when no answer is given on a "
                    "stopped run, twine's one-line RESUME_TEXT — as one user message, and "
                    "run the loop "
                    "again under the same sid — in the same sandbox home, with the "
                    "adapter, model, max_tokens and thinking the transcript recorded. No "
                    "`bale open`: the session is open in bale already. The first call's "
                    "usage is the re-warm cost (the twin's rewarm). A killed session is refused: "
                    "a kill closes it in bale. Ends as `twine run` does, naming its next "
                    "command; ok exactly when the outcome is delivered. With --plan: read "
                    "and say, start nothing."),
)

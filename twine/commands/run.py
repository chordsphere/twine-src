"""`twine run` — host a worker session from `bale open` to the apply line
(Arc 2 R4; twine-seed.md §4, §5.2; cli-contract.md §18).

    twine run BUNDLE --cap USD [--adapter anthropic|fake] [--script FILE]
              [--model M] [--max-tokens N] [--thinking adaptive|off]
              [--prices PATH] [--max-turns N] [--window N] [--state-dir DIR]
              [--bale-root DIR] [--cwd DIR] [--json]

What made the architect the courier on the worker side — open the bundle,
paste the opener into a chat, attach the tarball, carry the response back
to `bale apply` — is this verb's, in this order, each step refusing loudly
before the next:

  0. the verb's own refusals (nothing started): the adapter and its
     arguments (`--model` with `anthropic`; `--script` with `fake` only, and
     parsed; ANTHROPIC_API_KEY in the environment twine was started with),
     the cap (D15: none refuses — argparse's, since `--cap` is required — and
     one that is not a number of dollars is named), the limits, the state
     directory, the tool registry and the transition table the loop stands on
  1. `carry bundle` — the function (twine.commands.carry_bundle.open_bundle),
     not a subprocess: `bale open BUNDLE --json`, the in-flight record written
  2. the key, handed to the adapter and to nothing else: the courier's bale
     calls get twine's environment without it; the cage never has it (R3)
  3. the running record (twine.kill.register_running) before anything is
     spawned — the runtime made its group's leader first when it is not
     (twine.process.lead_own_group: os.setsid, guarded)
  4. the sandbox (R3), and the request unpacked at <home>/request/ with
     tarfile's `data` filter (twine.runtime.loop.unpack_request)
  5. the adapter: `anthropic` (R2) with the model, max_tokens and thinking
     as spawn-time constants and the surface note as its system text, or
     `fake` with the script — behind the boundary (R1); then the window
     (R5): `--window N`, or the adapter's statement at spawn (the Anthropic
     adapter's one `GET /v1/models`; the fake states unknown)
  6. the transcript, <state-dir>/transcripts/<sid>.jsonl, append-only
  7. the in-flight record's `runtime` fields (twine.inflight.record_runtime)
  8. the loop (twine.runtime.loop.Loop)

A refusal before the first model call is outcome `refused`, exit 1. At the
end, whatever the outcome, the running record is cleared (unless a tool's
group outlived its run: then it stays for `twine kill`); on `delivered` the
in-flight record is removed and the sandbox home kept (the response tarball
lives there until the operator applies it); otherwise both are kept, for R5
and the planner — `twine resume` (twine/commands/resume.py, R5) continues
a kept session cold from its transcript. ok exactly when the outcome is
`delivered`.

**twine run never applies anything** (T12): the only apply argv is `bale
apply --dry-run --json` (carry response's); the operator runs the apply line.

The verb never imports a process-spawning module: bale runs through ctx.run
(the seam), the tools through the sandbox.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

from twine import CONSUMPTION_MANIFEST, TRANSITIONS_TABLE, inflight, kill, process, spend
from twine.bale import ManifestError, load_manifest
from twine.cli import Context
from twine.commands import carry_bale, carry_bundle
from twine.commands.carry_bale import BALE_ROOT_ARGUMENT, CWD_ARGUMENT
from twine.commands.kill import state_dir_fault
from twine.registry import Argument, Command, Result
from twine.runtime import loop as runloop
from twine.runtime.adapters.anthropic import KEY_VARIABLE
# The script's parser only: the adapter itself is reached through the
# registry by name (runtime.loop.adapter_class), as every adapter is.
from twine.runtime.adapters.fake import FakeScript, FakeScriptError
from twine.runtime.boundary import Boundary, BoundaryError, SpawnSettings
from twine.runtime.registry import DeclarationError
from twine.runtime.sandbox import Sandbox, SandboxError
from twine.runtime.terms import ThinkingSettings
from twine.runtime.tooling import ToolRegistry, load_tool_registry
from twine.runtime.window import Window
from twine.transcript import Transcript, TranscriptError
from twine.transitions import load_table

log = logging.getLogger("twine.run")

NAME = "run"
ADAPTERS = ("anthropic", "fake")
DEFAULT_ADAPTER = "anthropic"
FAKE = "fake"
# The model the fake's spend records carry when none is named: the prices
# file must price it, as it prices any model (§13.4).
FAKE_DEFAULT_MODEL = "fake"
# 16000 starved file writes: a stream that ends at the ceiling inside a
# tool call loses the call (twine-run-ergonomics, finding 2).
DEFAULT_MAX_TOKENS = 32000
THINKING_CHOICES = ("adaptive", "off")
# The thinking parameter each choice sends the Anthropic adapter. `off` is
# `disabled`, said explicitly: sending none leaves the model's default,
# which may think — and a thinking turn on a session spawned with thinking
# off is refused at the boundary. Sonnet 5.5, Opus 5.5 and the Fable models
# refuse `disabled` (the 2026-10-13 /v1/models recording): request-refused,
# whose move tells the operator.
ANTHROPIC_THINKING = {"adaptive": {"type": "adaptive"}, "off": {"type": "disabled"}}
INFLIGHT_REMOVED = "removed"
INFLIGHT_KEPT = "kept"


@dataclasses.dataclass
class RunReport:
    """Everything `twine run` learned; rendered once as the JSON twin and
    once as human lines."""

    bundle: str
    adapter: str | None
    model: str | None = None
    # The verb the twin speaks for: `run`, or `resume` (R5), which shares
    # the report.
    command: str = NAME
    refusals: list[str] = dataclasses.field(default_factory=list)
    open: carry_bundle.BundleOutcome | None = None
    result: runloop.LoopResult | None = None
    state_dir: Path | None = None
    state_dir_source: str | None = None
    prices_path: Path | None = None
    cap_usd: Decimal | None = None
    max_turns: int | None = None
    transcript: Transcript | None = None
    sandbox: Sandbox | None = None
    unpacked: runloop.Unpacked | None = None
    group: process.OwnGroup | None = None
    running_registered: bool = False
    running_cleared: bool | None = None
    running_note: str | None = None
    inflight_state: str | None = None
    inflight_error: str | None = None
    # R5: the run's window (None until the adapter was spawned), and on a
    # resume the `seq` of the transcript's last line before it, and the sid
    # it was asked for (a resume has no open line to take it from).
    window: Window | None = None
    resumed_from: int | None = None
    resume_sid: str | None = None
    # The loop's wall time (seconds since it started), for the summary line.
    wall_seconds: float = 0.0

    @property
    def sid(self) -> str | None:
        if self.resume_sid is not None:
            return self.resume_sid
        sid = None if self.open is None else self.open.sid
        return sid if isinstance(sid, str) else None

    @property
    def rewarm(self) -> dict[str, Any] | None:
        """D23's named telemetry field: a resumed run's first call's
        Tokens, the five classes — null until that call is made, and null on
        `twine run`."""
        if self.command == NAME or self.result is None:
            return None
        return self.result.first_usage

    @property
    def outcome(self) -> str:
        return runloop.REFUSED if self.result is None else self.result.outcome

    @property
    def ok(self) -> bool:
        return self.outcome == runloop.DELIVERED

    @property
    def reason(self) -> str | None:
        if self.result is None:
            return "; ".join(self.refusals) if self.refusals else None
        return None if self.ok else self.result.reason

    def cost_usd(self) -> float | None:
        records = [] if self.result is None else self.result.records
        if self.state_dir is None:
            return 0.0 if not records else None
        path = self.prices_path or (self.state_dir / spend.PRICES_NAME)
        return spend.usd(runloop.run_cost(records, path))

    def payload(self) -> dict[str, Any]:
        """The JSON twin beside `command` and `ok` (cli-contract.md §18.5):
        the fixed names first, then the ones beside them. Every path carries
        the same key set, the values it did not reach null."""
        r = self.result
        records = [] if r is None else r.records
        return {
            "sid": self.sid,
            "outcome": self.outcome,
            "stop": None if r is None else r.stop,
            "move": None if r is None else r.move,
            "shape": None if r is None else r.shape,
            "reason": self.reason,
            "turns": 0 if r is None else r.turns,
            "tool_calls": 0 if r is None else r.tool_calls,
            "retries": 0 if r is None else r.retries,
            "block": None if r is None else r.block,
            "tarball": None if r is None else r.tarball,
            "apply_line": None if r is None else r.apply_line,
            "dry_run": None if r is None else r.dry_run,
            "usage": runloop.usage_sum(records),
            "cost_usd": self.cost_usd(),
            "transcript": None if self.transcript is None else str(self.transcript.path),
            "sandbox": None if self.sandbox is None else str(self.sandbox.home),
            "inflight": self.inflight_state,
            "open": None if self.open is None else self.open.payload(),
            # R5's, after R4's names so their order holds.
            "window": None if self.window is None else self.window.as_json(),
            "resumed_from": self.resumed_from,
            "rewarm": self.rewarm,
            # beside them
            "actor": None if r is None else r.actor,
            "refusals": list(self.refusals),
            "adapter": self.adapter,
            "model": self.model,
            "cap_usd": spend.usd(self.cap_usd),
            "max_turns": self.max_turns,
            "window_reason": None if self.window is None else self.window.reason,
            "check": None if r is None else r.check,
            "running": None if self.group is None else {
                **self.group.as_json(), "registered": self.running_registered,
                "cleared": self.running_cleared, "note": self.running_note},
            "request": None if self.unpacked is None else self.unpacked.as_json(),
            "network": None if self.sandbox is None else self.sandbox.network,
            "transcript_faults": ([] if self.transcript is None
                                  else list(self.transcript.faults)),
            "inflight_error": self.inflight_error,
            "state_dir": None if self.state_dir is None else str(self.state_dir),
            "state_dir_source": self.state_dir_source,
        }


# ---------------------------------------------------------------------------
# The verb
# ---------------------------------------------------------------------------


def cmd_run(ctx: Context, args: argparse.Namespace) -> Result:
    report = RunReport(bundle=args.bundle, adapter=args.adapter)
    try:
        run(ctx, args, report)
    except Exception:
        # A defect of twine's: the dispatcher reports it (exit 2). The story
        # gets its last line and the running record is not left behind.
        log.exception("twine run: internal error")
        if report.transcript is not None:
            _log_end(report, internal_error=True)
        raise
    finally:
        finish_running(ctx, report)
    if report.result is None and report.open is not None and report.open.ok:
        report.refusals.append(
            f"session {report.sid} is open in bale and nothing ran in it: fix the fault "
            f"and run again (bale opens a second desk), or close it with `twine kill "
            f"{report.sid}`")
    payload = report.payload()
    if report.transcript is not None:
        _log_end(report)
    ctx.info(f"{NAME}: {summary_line(report)}")
    return Result(report.ok, payload, lines(report))


def summary_line(report: RunReport) -> str:
    """The run's last progress line (cli-contract.md §18.7), the same words
    the loop's `summary()` speaks — and the same line when the loop never ran
    (`refused`: no calls, nothing spent, no time)."""
    r = report.result
    return runloop.summary_text(
        report.outcome, stop=None if r is None else r.stop, move=None if r is None else r.move,
        calls=0 if r is None else r.turns, tool_calls=0 if r is None else r.tool_calls,
        retries=0 if r is None else r.retries, cost=report.cost_usd(),
        seconds=report.wall_seconds)


def _log_end(report: RunReport, *, internal_error: bool = False) -> None:
    assert report.transcript is not None
    try:
        if internal_error:
            report.transcript.append("run-end", internal_error=True)
        else:
            report.transcript.append("run-end", twin={"command": report.command,
                                                      "ok": report.ok, **report.payload()})
    except TranscriptError:
        pass


def run(ctx: Context, args: argparse.Namespace, report: RunReport) -> None:
    """The sequence (module docstring), filling `report`."""
    # 0. Refused before anything is started.
    settings = pre_open(ctx, args, report)
    if report.refusals:
        ctx.info(f"run {args.bundle}: refused — {report.reason}")
        return
    assert settings is not None
    tools, moves, adapter_cls, script, key = settings
    # The courier's context: twine's environment without the key (step 2 —
    # the key reaches the adapter and nothing else, bale included).
    courier = dataclasses.replace(ctx, env={k: v for k, v in ctx.env.items()
                                            if k != KEY_VARIABLE})
    # 1. carry bundle.
    ctx.info(f"run: opening {args.bundle} with bale (carry bundle)")
    report.open = carry_bundle.open_bundle(courier, argparse.Namespace(
        bundle=args.bundle, check=False, cwd=args.cwd, bale_root=args.bale_root,
        state_dir=str(report.state_dir)))
    if not report.open.ok:
        report.refusals.append(f"carry bundle did not open the session: "
                               f"{report.open.reason}")
        return
    sid = report.sid
    assert sid is not None
    report.inflight_state = (INFLIGHT_KEPT if report.open.record is not None else None)
    if report.open.tarball is None:
        report.refusals.append(f"bale opened {sid} but no request tarball is known for it "
                               "(its line names none and no in-flight record holds one); "
                               "the session is open — `twine kill` or `bale unlock` closes "
                               "it")
        return
    state_dir = report.state_dir
    assert state_dir is not None
    # 3. The running record, before anything is spawned.
    try:
        report.group = lead_own_group()
    except OSError as exc:
        report.refusals.append(f"the runtime could not lead a process group of its own "
                               f"(setsid: {exc.strerror or exc}), so the kill-switch could "
                               "not find it; nothing was started")
        return
    if report.group.setsid:
        ctx.info(f"run: the runtime was not its group's leader; it called setsid and leads "
                 f"group {report.group.pgid}")
    try:
        kill.register_running(state_dir, sid, report.group.pgid, report.group.pid)
    except (kill.RunningRecordError, kill.KillError) as exc:
        report.refusals.append(f"the running record could not be written ({exc}); nothing "
                               "is started that the kill-switch could not reach")
        return
    report.running_registered = True
    ctx.info(f"run: running record for {sid}: group {report.group.pgid}")
    # 4. The sandbox, and the request unpacked in it.
    try:
        report.sandbox = Sandbox.create(state_dir, sid, repo=Path(report.open.cwd or "."),
                                        run=ctx.run)
        ctx.info(f"run: sandbox {report.sandbox.home} (network {report.sandbox.network})")
        report.unpacked = runloop.unpack_request(Path(report.open.tarball),
                                                 report.sandbox.home)
    except (SandboxError, runloop.LoopError) as exc:
        report.refusals.append(str(exc))
        return
    ctx.info(f"run: request unpacked at {report.unpacked.directory} "
             f"({report.unpacked.members} members)")
    # 5. The adapter, behind the boundary, and the window it states.
    prompt = runloop.system_prompt(tools)
    try:
        boundary = Boundary(build_adapter(args, report, adapter_cls, script, key, prompt))
    except (BoundaryError, ValueError, TypeError) as exc:
        report.refusals.append(f"the {args.adapter} adapter could not be spawned: {exc}")
        return
    report.window = spawn_window(ctx, args, boundary)
    # 6. The transcript.
    try:
        report.transcript = Transcript.open(state_dir, sid)
    except (TranscriptError, ValueError) as exc:
        report.refusals.append(f"the transcript cannot be opened: {exc}")
        return
    report.transcript.append(
        "run-start", adapter=args.adapter, model=report.model,
        max_tokens=args.max_tokens, thinking=args.thinking,
        sandbox=report.sandbox.as_json(), request=report.unpacked.as_json(),
        open={"sid": sid, "tarball": report.open.tarball}, group=report.group.as_json(),
        cap_usd=spend.usd(report.cap_usd), max_turns=report.max_turns,
        system=prompt.as_json(), window=report.window.start_json(), resumed_from=None)
    # 7. The in-flight record's runtime fields.
    try:
        inflight.record_runtime(state_dir, sid, inflight.runtime_fields(
            adapter=args.adapter, model=report.model or "",
            sandbox_home=str(report.sandbox.home), transcript=str(report.transcript.path),
            pgid=report.group.pgid))
    except (inflight.InflightError, ValueError) as exc:
        report.inflight_error = str(exc)
        ctx.info(f"warning: the in-flight record's runtime fields were not written: {exc}")
    # 8. The loop.
    ctx.info(f"run: {sid}: the loop starts ({args.adapter}, model {report.model}, cap "
             f"{spend.dollars(report.cap_usd)})")
    the_loop = runloop.Loop(
        boundary=boundary, sandbox=report.sandbox, transcript=report.transcript,
        settings=runloop.LoopSettings(sid=sid, state_dir=state_dir,
                                      cap_usd=report.cap_usd or Decimal(0),
                                      model=report.model or "",
                                      max_tokens=args.max_tokens,
                                      max_turns=report.max_turns or runloop.DEFAULT_MAX_TURNS,
                                      prices_path=report.prices_path),
        prompt=prompt, moves=moves, tools=tools,
        deliver=lambda path: deliver(courier, args, path),
        messages=[runloop.user_message(report.open.opener)], window=report.window,
        progress=lambda line: ctx.info(f"run: {line}"))
    report.result = the_loop.run()
    report.wall_seconds = the_loop.elapsed()
    # The end: what is kept and what is removed.
    if report.result.outcome == runloop.DELIVERED:
        try:
            removed = inflight.remove_inflight(state_dir, sid)
            report.inflight_state = INFLIGHT_REMOVED if removed else report.inflight_state
        except inflight.InflightError as exc:
            report.inflight_error = str(exc)
            ctx.info(f"warning: the in-flight record could not be removed: {exc}")
    ctx.info(f"run: {sid}: {report.outcome}"
             + (f" — {report.reason}" if report.reason else "")
             + f"; sandbox home kept at {report.sandbox.home}")


def spawn_window(ctx: Context, args: argparse.Namespace, boundary: Boundary, *,
                 label: str = NAME) -> Window:
    """The run's window (R5): `--window N` fixes it and the adapter is not
    asked; otherwise the adapter states it at spawn — the Anthropic
    adapter's one `GET /v1/models`, the fake's unknown. Unknown is not a
    refusal: the run counts the window and cannot warn or stop on it."""
    if args.window is not None:
        window = Window.from_flag(args.window)
    else:
        window = Window.stated(boundary.context_window())
    ctx.info(f"{label}: window: {window.describe()}")
    return window


def window_refusal(value: int | None) -> str | None:
    """Why `--window` refuses: a size that is not a positive number of
    tokens; None when absent or fine."""
    if value is not None and value <= 0:
        return f"--window {value} is not a positive number of tokens"
    return None


def lead_own_group() -> process.OwnGroup:
    """The runtime's own group (step 3). A name of this module's, so a test
    that runs the verb in its own process can stand a child in for it."""
    return process.lead_own_group()


def pre_open(ctx: Context, args: argparse.Namespace, report: RunReport):
    """Every refusal before bale is started, named at once. Returns the
    tool registry, the move book, the adapter class, the parsed script and
    the key — or None when anything refused."""
    refusals = report.refusals
    adapter = args.adapter
    key: str | None = None
    script = None
    if adapter == FAKE:
        report.model = args.model or FAKE_DEFAULT_MODEL
        if args.script is None:
            refusals.append("--adapter fake needs --script FILE: the fake plays a script "
                            "(runtime-contract.md §3) and has no model to ask")
    else:
        report.model = args.model
        if not args.model:
            refusals.append("--adapter anthropic needs --model: the office holds the "
                            "policy (N4), and twine does not pick a model")
        if args.script is not None:
            refusals.append(f"--script is the fake adapter's; --adapter {adapter} reads "
                            "no script")
        key = ctx.env.get(KEY_VARIABLE)
        if not isinstance(key, str) or not key.strip():
            refusals.append(f"{KEY_VARIABLE} is not set (or is empty) in the environment "
                            f"twine was started with; --adapter {adapter} does not start "
                            "without its key, and nothing was opened")
            key = None
    if adapter == FAKE and args.script is not None:
        script = read_script(args.script, refusals)
    try:
        report.cap_usd = spend.parse_usd(args.cap)
    except ValueError as exc:
        refusals.append(f"--cap: {exc}")
    if args.max_tokens <= 0:
        refusals.append(f"--max-tokens {args.max_tokens} is not a positive number of tokens")
    if args.max_turns <= 0:
        refusals.append(f"--max-turns {args.max_turns} is not a positive number of calls")
    report.max_turns = args.max_turns
    window_fault = window_refusal(args.window)
    if window_fault is not None:
        refusals.append(window_fault)
    if args.prices is not None:
        if not args.prices:
            refusals.append("--prices is empty; it names no price file")
        else:
            report.prices_path = Path(args.prices).expanduser().resolve()
    try:
        where = spend.resolve_state_dir(args.state_dir, ctx.env)
    except spend.SpendError as exc:
        refusals.append(f"{exc.message} — twine run keeps its state there (the in-flight "
                        "record, the running record, the sandbox, the transcript, spend)")
    else:
        report.state_dir, report.state_dir_source = where.path, where.source
        fault = state_dir_fault(where.path)
        if fault is not None and fault != carry_bundle.STATE_DIR_ABSENT:
            refusals.append(f"the state directory {where.path} (from {where.source}) "
                            f"{fault}")
    tools = tool_registry(refusals)
    moves = move_book(refusals)
    adapter_cls = None
    try:
        adapter_cls = runloop.adapter_class(adapter)
    except runloop.LoopError as exc:
        refusals.append(str(exc))
    if refusals:
        return None
    return tools, moves, adapter_cls, script, key


def read_script(name: str, refusals: list[str]) -> list[Any] | None:
    """The fake's script file: JSON, a list of turns runtime-contract.md §3
    describes. Parsed here, and played by the fake, which refuses it whole
    when a turn is malformed — so a bad script refuses before bale opens."""
    path = Path(name).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        refusals.append(f"--script {name}: no such file")
        return None
    except (OSError, ValueError) as exc:
        refusals.append(f"--script {name} is not a JSON script: {exc}")
        return None
    try:
        return FakeScript.from_data(data)
    except FakeScriptError as exc:
        refusals.append(f"--script {name}: {exc}")
        return None


def tool_registry(refusals: list[str]) -> ToolRegistry | None:
    try:
        tools = load_tool_registry()
    except DeclarationError as exc:
        refusals.append(f"the tool declaration is malformed: {exc}")
        return None
    if not tools.ok:
        refusals.append("the tool registry is not ok (`twine runtime tools` names it): "
                        + "; ".join(p.message for p in tools.problems))
    return tools


def move_book(refusals: list[str]) -> runloop.MoveBook | None:
    try:
        manifest, manifest_error = load_manifest(CONSUMPTION_MANIFEST), None
    except ManifestError as exc:
        manifest, manifest_error = None, str(exc)
    book = runloop.MoveBook(load_table(TRANSITIONS_TABLE, manifest, manifest_error))
    faults = book.faults()
    if faults:
        refusals.append("the transition table does not stand behind the loop (`twine "
                        "transitions` names it): " + "; ".join(faults))
    return book


def build_adapter(args: argparse.Namespace, report: RunReport, cls: type, script: Any,
                  key: str | None, prompt: runloop.SystemPrompt):
    """The adapter, its spawn-time constants fixed (D12). The key goes into
    the Anthropic adapter's environment mapping and nowhere else."""
    if args.adapter == FAKE:
        thinking = (ThinkingSettings(enabled=True, adaptive=True)
                    if args.thinking == "adaptive" else ThinkingSettings(enabled=False))
        return cls(SpawnSettings(model=report.model, max_tokens=args.max_tokens,
                                 thinking=thinking), script)
    assert key is not None
    return cls(env={KEY_VARIABLE: key}, model=report.model, max_tokens=args.max_tokens,
               thinking=ANTHROPIC_THINKING[args.thinking], system=prompt.note)


def deliver(courier: Context, args: argparse.Namespace, path: Path) -> runloop.Delivery:
    """`carry response` on the delivered tarball — the function, not a
    subprocess: `bale apply --dry-run --json <path>`, in --cwd."""
    outcome = carry_bale.check_response(courier, argparse.Namespace(
        tarball=str(path), cwd=args.cwd, bale_root=args.bale_root))
    return runloop.Delivery(ok=outcome.ok, tarball=outcome.tarball or str(path),
                            apply_line=outcome.apply_line, dry_run=outcome.dry_run,
                            outcome=outcome.outcome, reason=outcome.reason,
                            twin=outcome.payload())


def finish_running(ctx: Context, report: RunReport) -> None:
    """The end, on every path once the record was written: the runtime's
    entry cleared (twine.kill.clear_running) — unless the record still names
    a tool's group, which `twine kill` must still reach."""
    if not report.running_registered or report.state_dir is None or report.sid is None:
        return
    try:
        record = kill.read_running(report.state_dir, report.sid)
    except kill.RunningRecordError as exc:
        record = None
        report.running_note = f"the running record cannot be read ({exc}); it is cleared"
    if record is not None and record.groups:
        report.running_cleared = False
        report.running_note = (f"the running record still names group(s) "
                               f"{', '.join(str(g.pgid) for g in record.groups)} whose "
                               f"run returned with live members; it is kept for "
                               f"`twine kill {report.sid}`")
        ctx.info(f"warning: {report.running_note}")
        return
    try:
        report.running_cleared = kill.clear_running(report.state_dir, report.sid)
    except kill.KillError as exc:
        report.running_cleared = False
        report.running_note = f"the running record could not be cleared: {exc}"
        ctx.info(f"warning: {report.running_note}")


def lines(report: RunReport) -> list[str]:
    """stdout without --json: the apply line alone on `delivered`; the light
    block alone on `suspended`; one line naming the outcome, stop and reason
    otherwise."""
    r = report.result
    if r is not None and r.outcome == runloop.DELIVERED and r.apply_line:
        return [r.apply_line]
    if r is not None and r.outcome == runloop.SUSPENDED and r.apply_line:
        # escalate's clarification form (R5): the operator applies it. Its
        # twin's `block` is the paste block, for the other courier; human
        # mode on stdout stays the apply line alone.
        return [r.apply_line]
    if r is not None and r.outcome == runloop.SUSPENDED and r.block:
        return carry_bale.passthrough_lines(r.block)
    who = report.sid or report.bundle
    if r is None:
        return [f"{report.command} {who}: refused — {report.reason}"]
    parts = [f"{report.command} {who}: {r.outcome}"]
    if r.stop is not None:
        parts.append(f"stop {r.stop}")
    if r.move is not None:
        parts.append(f"move {r.move} ({r.actor}'s)")
    if r.shape is not None:
        parts.append(f"shape {r.shape}")
    return [", ".join(parts) + (f" — {r.reason}" if r.reason else "")]


WINDOW_ARGUMENT = Argument(("--window",), {
    "metavar": "N", "type": int, "default": None,
    "help": "the context window in input tokens (R5): fixes it; absent, the adapter states "
            "it at spawn (the fake states unknown, and an unknown window is counted but "
            "never warned or stopped on)"})


COMMANDS = (
    Command(
        name=NAME,
        summary="host a worker session: open the bundle with bale, run the model's "
                "turns and tools in a sandbox, and hand back the apply line",
        handler=cmd_run,
        arguments=(
            Argument(("bundle",), {
                "metavar": "BUNDLE",
                "help": "the planner's bundle, as `carry bundle` takes it"}),
            Argument(("--cap",), {
                "metavar": "USD", "required": True,
                "help": "the session's hard cap in US dollars (D15): checked before every "
                        "model call; required — an absent cap refuses"}),
            Argument(("--adapter",), {
                "choices": ADAPTERS, "default": DEFAULT_ADAPTER,
                "help": "the model adapter (default anthropic; fake plays --script, for "
                        "tests and dry runs of the loop)"}),
            Argument(("--script",), {
                "metavar": "FILE", "default": None,
                "help": "the fake adapter's script: a JSON list of turns "
                        "(runtime-contract.md §3); refused with any other adapter"}),
            Argument(("--model",), {
                "metavar": "M", "default": None,
                "help": "the model id: required with anthropic (twine picks none); "
                        "`fake` by default with the fake adapter — the id its spend "
                        "records carry, which the price file must price"}),
            Argument(("--max-tokens",), {
                "metavar": "N", "type": int, "default": DEFAULT_MAX_TOKENS,
                "help": f"the output ceiling per call (default {DEFAULT_MAX_TOKENS}; a "
                        "turn cut at it is continued, and a tool call it cut off is "
                        "asked for again in parts)"}),
            Argument(("--thinking",), {
                "choices": THINKING_CHOICES, "default": "adaptive",
                "help": "thinking, a spawn-time constant (default adaptive)"}),
            Argument(("--prices",), {
                "metavar": "PATH", "default": None,
                "help": "the price file (default <state-dir>/prices.toml)"}),
            Argument(("--max-turns",), {
                "metavar": "N", "type": int, "default": runloop.DEFAULT_MAX_TURNS,
                "help": "twine's own limit on model calls (default "
                        f"{runloop.DEFAULT_MAX_TURNS}): reaching it ends the run "
                        "`ended`, shape max-turns"}),
            WINDOW_ARGUMENT,
            Argument(("--state-dir",), {
                "metavar": "DIR", "default": None,
                "help": "twine's state directory (as carry bundle takes it): the "
                        "in-flight and running records, the sandbox, the transcript, "
                        "spend"}),
            BALE_ROOT_ARGUMENT,
            CWD_ARGUMENT,
        ),
        description="Open BUNDLE with `bale open --json` (carry bundle), register the "
                    "runtime with the kill-switch, make the session's sandbox and unpack "
                    "the request at request/ in it, and run the worker: the opener as the "
                    "first turn, the canonical tools, the abort file and the cap checked "
                    "before every call, usage appended to spend.jsonl after each, every "
                    "step in <state-dir>/transcripts/<sid>.jsonl. The context window is "
                    "counted from each call's usage: the worker is warned in its tool "
                    "results at 80% and the run stops window-exhausted before a call past "
                    "it. A delivered response tarball is checked with `bale apply "
                    "--dry-run --json` (carry response) and its apply line printed — "
                    "twine never applies. escalate suspends (the light block printed, or "
                    "the clarification response's apply line); every other ending is "
                    "named with its stop and the transition table's move. ok exactly when "
                    "the outcome is delivered."),
)

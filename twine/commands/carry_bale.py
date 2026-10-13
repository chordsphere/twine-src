"""`twine carry exchange` and `twine carry response` — the courier hands
bale what it carried (Arc 1 session 2b-ii).

`twine carry exchange FILE [--block N] [--cwd DIR] [--bale-root DIR]
[--json]` reads FILE exactly as `twine take` does, chooses one exchange
block (twine/commands/carry.py's `choose_block`: never a guess), refuses
a block whose integrity does not hold — twine never relays a block it
cannot vouch for, and never repairs one — and hands the block's own
lines (`shapes.block_text`: BEGIN through END, LF, one trailing newline;
nothing else from the input) to `bale relay <sid> - --json` on stdin, in
the repo the block's session lives in, and reads the one JSON line bale
answers with (since session 2026-10-08-twine-carry-exchange-json-001,
which retired the flagless `bale relay <sid> -` and its pass-through). ok
exactly when bale exits 0 and the line's `outcome` is "relayed", its
`sid` the block's and its `block` exactly one intact exchange block of
the same session (since session 2026-10-08-twine-exchange-vouch-005:
twine vouches for the block it hands on as for the block it carried in);
on ok, human stdout is exactly that `block` — the block the courier
carries next, byte for byte what the flagless relay printed. On a refusal
the reason quotes bale's `cause` whole: twine names it and never
dispatches on its wording.

`twine carry response TARBALL [--cwd DIR] [--bale-root DIR] [--json]`
runs `bale apply --dry-run --json` on the tarball, named by its absolute
path, and on a clean dry run hands back the one line that applies it:
`bale apply <path>`. It never applies anything (T12): the only `apply`
argv twine can build is twine.bale.dry_run_argv's, and no admission or
override flag exists anywhere in twine. ok exactly when bale exits 0 and
its stdout is one JSON object whose `outcome` is `"dry-run"`.

`call_bale`, `resolve_cwd`, `locate` and `passthrough_lines` are shared
with `twine carry bundle` (twine/commands/carry_bundle.py, Arc 1 session
3), which passes `call_bale` its own, longer timeout.

Both run bale through `ctx.run`, the seam (twine/process.py), never a
subprocess of their own, and find bale exactly as `bale check` does
(twine.bale.locate_executable): the tests pin TWINE_BALE_ROOT, so a bale
on the operator's PATH is never what a test reaches. Since Arc 1 session
4 both refuse, before starting it, a bale the gate does not admit (D2;
twine.bale.Executable.drive_refusal) — since session
2026-10-12-twine-pin-floor-002 one below the floor, or whose installed
schemas do not hash as the manifest pins them, where it was an exact pin
before. Since that session both also check, on the line they read, every
key the consumption manifest lists for its surface
(twine.bale.missing_keys_failure). The contract is
claude/context/cli-contract.md §11.

Sections:
  1. Limits and the bale call        (~line 60)
  2. carry exchange                  (~line 155)
  3. carry response                  (~line 420)
  4. Shared helpers                  (~line 545)
  5. The registry entries            (~line 590)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from twine import bale, shapes
from twine.cli import Context
from twine.commands.carry import choose_block, label_of, read_turn
from twine.process import RunError
from twine.registry import Argument, Command, Result

# ---------------------------------------------------------------------------
# 1. Limits and the bale call
# ---------------------------------------------------------------------------

# The two verbs' registered names, which are also how the consumption
# manifest's `read_by` names them: bale.missing_keys_failure finds the surface
# whose keys a line owes by the reader (since session
# 2026-10-12-twine-pin-floor-002).
READER_EXCHANGE = "carry exchange"
READER_RESPONSE = "carry response"

# How long a bale verb may take. Neither verb is long-running — relay
# records a round and prints one line; a dry run stages nothing — so a
# call past this is stuck (waiting on something), and is killed and
# reported, never waited on forever.
BALE_TIMEOUT_SECONDS = 300.0
# bale's stdout is one JSON line (relay's carries a paste block):
# kilobytes. Past this the call is stopped and is not ok.
BALE_STDOUT_CAP_BYTES = 4 * 1024 * 1024


@dataclass
class BaleCall:
    """One run of bale through the seam, as both verbs report it."""

    argv: list[str] | None = None
    ran: bool = False
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    stderr_truncated: bool = False
    timed_out: bool = False
    capped: bool = False
    duration_seconds: float | None = None

    def report(self) -> dict[str, Any]:
        return {"argv": self.argv, "ran": self.ran, "exit_code": self.exit_code,
                "stdout": self.stdout, "stderr": self.stderr,
                "stderr_truncated": self.stderr_truncated,
                "timed_out": self.timed_out, "capped": self.capped,
                "duration_seconds": self.duration_seconds}


def call_bale(ctx: Context, argv: list[str], cwd: str, stdin: bytes | None,
              refusals: list[str], failures: list[str], *,
              timeout: float = BALE_TIMEOUT_SECONDS) -> BaleCall:
    """Run `argv` through ctx.run and record what came back. A bale that
    cannot be started is a refusal (nothing ran); a run that was killed
    or exited non-zero is a failure naming why. bale's stderr is always
    surfaced on twine's stderr, whatever the outcome. `timeout` is
    BALE_TIMEOUT_SECONDS unless a verb's bale call is long by design
    (`carry bundle`'s open runs a checkpoint dry-run: session 3)."""
    call = BaleCall(argv=list(argv))
    ctx.info(f"running bale {' '.join(argv[1:])} in {cwd} (executable {argv[0]})")
    try:
        result = ctx.run(argv, cwd=cwd, stdin=stdin, timeout=timeout,
                         env=dict(ctx.env), stdout_cap=BALE_STDOUT_CAP_BYTES)
    except RunError as exc:
        refusals.append(f"bale could not be started ({argv[0]}): "
                        f"{exc.strerror or exc}")
        return call
    call.ran = True
    call.exit_code = result.exit_code
    call.stdout = decode(ctx, result.stdout, "stdout")
    call.stderr = decode(ctx, result.stderr, "stderr")
    call.stderr_truncated = result.stderr_truncated
    call.timed_out = result.timed_out
    call.capped = result.stdout_capped
    call.duration_seconds = result.duration_seconds
    if result.timed_out:
        failures.append(f"bale did not finish within {timeout:g}s "
                        "and was killed")
    if result.stdout_capped:
        failures.append(f"bale's stdout passed {BALE_STDOUT_CAP_BYTES} bytes and "
                        "it was stopped")
    if not result.killed and result.exit_code != 0:
        failures.append(f"bale exited {result.exit_code}")
    if call.stderr:
        ctx.info("bale's stderr follows")
        ctx.stderr.write(call.stderr if call.stderr.endswith("\n")
                         else call.stderr + "\n")
    return call


def decode(ctx: Context, data: bytes, stream: str) -> str:
    """bale's bytes as text. bale writes UTF-8 (its paste blocks are
    ASCII-escaped); anything else is replaced and logged, never fatal."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        ctx.info(f"bale's {stream} is not UTF-8 (byte {exc.start}); "
                 "undecodable bytes replaced")
        return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 2. carry exchange
# ---------------------------------------------------------------------------


# The `outcome` values of `bale relay --json`'s line (format_relay_json,
# bale 0.4.48; all three recorded at 0.4.49). Only RELAYED is ok. A
# re-emission is what bale prints when given no input — it recorded
# nothing — and twine always passes the block, so seeing one is named,
# never accepted. Any other value is named as one twine does not know.
RELAYED_OUTCOME = "relayed"
RE_EMITTED_OUTCOME = "re-emitted"
RELAY_REFUSED_OUTCOME = "relay-refused"


@dataclass
class ExchangeOutcome:
    """Everything `carry exchange` learned; rendered once as the JSON twin
    and once as human lines. `relay` is bale's `relay --json` line parsed,
    when its stdout was one JSON object."""

    source: str
    input: dict[str, Any] = field(default_factory=dict)
    block_number: int | None = None
    block: shapes.Block | None = None
    refusals: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    call: BaleCall = field(default_factory=BaleCall)
    relay: dict[str, Any] | None = None
    cwd: str | None = None
    bale: dict[str, Any] | None = None

    @property
    def sid(self) -> str | None:
        return None if self.block is None else self.block.fields.get("sid")

    @property
    def outcome(self) -> Any:
        """The line's `outcome`, as bale spelled it; None without a line."""
        return None if self.relay is None else self.relay.get("outcome")

    @property
    def relayed_block(self) -> str | None:
        """The block bale handed back — on ok only, so a caller can never
        print a block from a line twine did not accept."""
        if not self.ok or self.relay is None:
            return None
        return self.relay["block"]

    @property
    def ok(self) -> bool:
        return not self.refusals and self.call.ran and not self.failures

    @property
    def reason(self) -> str | None:
        problems = self.refusals + self.failures
        return "; ".join(problems) if problems else None

    def payload(self) -> dict[str, Any]:
        """The JSON twin beside `command` and `ok` (cli-contract.md §11.2).
        `sid`, `block`, `ran`, `exit_code`, `stdout`, `stderr`, `reason`,
        `refusals`, `relay` and `outcome` are fixed names the shell and the
        oracle read; `relay` and `outcome` (since session
        2026-10-08-twine-carry-exchange-json-001) are present on every
        path, null when there is no line."""
        call = self.call.report()
        return {
            "sid": self.sid,
            "block": self.block_number,
            "ran": call.pop("ran"),
            "exit_code": call.pop("exit_code"),
            "stdout": call.pop("stdout"),
            "stderr": call.pop("stderr"),
            "reason": self.reason,
            "refusals": self.refusals,
            "relay": self.relay,
            "outcome": self.outcome,
            "integrity": None if self.block is None else self.block.integrity,
            **call,
            "cwd": self.cwd,
            "bale": self.bale,
            "input": self.input,
        }


def cmd_carry_exchange(ctx: Context, args: argparse.Namespace) -> Result:
    """Read, choose, vouch, relay, then read bale's line. Every refusal is
    collected before bale is called, and nothing reaches bale unless there
    is none."""
    outcome = ExchangeOutcome(source=args.file)
    outcome.cwd = resolve_cwd(args.cwd, outcome.refusals)
    read = read_turn(ctx, outcome)
    text = None
    if read is not None:
        report, text = read
        choose_block(report, args.block, outcome, kind=shapes.EXCHANGE)
    if outcome.block is not None:
        check_vouchable(outcome)
    executable = locate(ctx, args, outcome.refusals)
    outcome.bale = executable.as_json()
    if not outcome.refusals:
        assert outcome.block is not None and text is not None and outcome.sid
        assert executable.path is not None
        carried = shapes.block_text(text, outcome.block).encode("utf-8")
        ctx.info(f"relaying exchange block {outcome.sid} "
                 f"(block [{outcome.block_number}], {len(carried)} bytes)")
        outcome.call = call_bale(ctx, bale.relay_argv(executable.path, outcome.sid),
                                 outcome.cwd or ".", carried,
                                 outcome.refusals, outcome.failures)
        if outcome.call.ran:
            read_relay_line(outcome, executable.manifest)
    for problem in outcome.refusals + outcome.failures:
        ctx.info(problem)
    if outcome.ok:
        # Only the keys the consumption manifest lists are read here
        # (outcome, sid, block, cause); the rest of the line is carried
        # whole in the twin's `relay`, never interpreted.
        ctx.info(f"bale relayed the exchange block of {outcome.sid} "
                 f"(outcome {RELAYED_OUTCOME!r}) and handed back an intact one; "
                 "stdout is the block to carry next")
    return Result(outcome.ok, outcome.payload(), exchange_lines(outcome))


def check_vouchable(outcome: ExchangeOutcome) -> None:
    """The block must be intact, and its sid safe to pass as an argument.
    A failed integrity is never repaired: the fault is named and the
    block is re-requested by whoever carries it."""
    block = outcome.block
    assert block is not None
    if not block.ok:
        fault = block.integrity.get("fault", "malformed")
        outcome.refusals.append(
            f"exchange block {outcome.sid} fails integrity ({fault}): {block.error}"
            " — twine never relays a block it cannot vouch for, and never "
            "repairs one")
        return
    sid = outcome.sid or ""
    if not bale.SID_ARGUMENT.fullmatch(sid):
        outcome.refusals.append(
            f"exchange block's session id {sid!r} is not safe to pass to bale "
            "as an argument")


def read_relay_line(outcome: ExchangeOutcome,
                    manifest: bale.Manifest | None) -> None:
    """bale's stdout must be one JSON object (`relay --json` prints exactly
    one line on every path, refusals included) carrying every key the
    manifest lists for the relay surface (bale.missing_keys_failure, since
    session 2026-10-12-twine-pin-floor-002), whose `outcome` is "relayed",
    whose `sid` is the block's and whose `block` is a non-empty string that
    twine can vouch for (vouch_for_relayed_block: exactly one intact
    exchange block of the carried block's session). Each thing that differs
    is named in its own failure, so the reason says all of it at once. A
    refusal's `cause` is quoted whole — it is bale's only account of why —
    and never dispatched on: bale documents its wording as the stderr text,
    free to change."""
    stdout = outcome.call.stdout
    try:
        obj = json.loads(stdout)
    except ValueError:
        obj = None
    if not isinstance(obj, dict):
        shown = stdout.strip()
        outcome.failures.append(
            "bale's stdout was not one JSON object"
            + (f" (it began {shown[:60]!r})" if shown else " (it was empty)"))
        return
    outcome.relay = obj
    lacking = bale.missing_keys_failure(manifest, READER_EXCHANGE, obj)
    if lacking is not None:
        outcome.failures.append(lacking)
    got = obj.get("outcome")
    if got == RELAY_REFUSED_OUTCOME:
        cause = obj.get("cause")
        outcome.failures.append(
            f"bale refused the relay (outcome {RELAY_REFUSED_OUTCOME!r}): "
            + (f'"{cause}"' if isinstance(cause, str) and cause
               else "its line names no cause"))
    elif got == RE_EMITTED_OUTCOME:
        outcome.failures.append(
            f"bale reported outcome {RE_EMITTED_OUTCOME!r}: it recorded nothing "
            "(a re-emission answers a relay given no input; twine always passes "
            "the block)")
    elif got != RELAYED_OUTCOME:
        outcome.failures.append(f"bale reported outcome {got!r}, which twine "
                                f"does not know (not {RELAYED_OUTCOME!r})")
    if obj.get("sid") != outcome.sid:
        outcome.failures.append(f"bale's line names sid {obj.get('sid')!r}, not "
                                f"the block's {outcome.sid!r}")
    block = obj.get("block")
    if not isinstance(block, str):
        outcome.failures.append(f"bale's line carries no block (block is "
                                f"{'null' if block is None else type(block).__name__})")
    elif not block:
        outcome.failures.append("bale's line carries an empty block")
    else:
        vouch_for_relayed_block(outcome, block)


# The words every vouch failure opens with, so a reader of the reason sees
# at once that bale's line was read and understood and the block it handed
# back is what twine refused to hand on.
VOUCH_FAILURE = "twine cannot vouch for the block bale handed back"


def vouch_for_relayed_block(outcome: ExchangeOutcome, text: str) -> None:
    """The block bale hands back is the one the courier carries next, so it
    is held to what `take` asks of any exchange block (cli-contract.md §9.2,
    §9.3) and to what `carry exchange` asked of the block it carried in:
    `text`, CRLF turned to LF as `take` normalizes (§9.1), must be exactly
    one block — its own lines and nothing around them, though a missing
    final newline is supplied (§11.2's human mode always did) — of kind
    `exchange`, whose integrity holds and whose sentinel sid is the carried
    block's. Each thing that differs is its own failure, beside the line's;
    nothing is ever repaired, and `relayed_block` (ok-only) means a block
    that failed here is never printed. Since session
    2026-10-08-twine-exchange-vouch-005."""
    normalized = text.replace("\r\n", "\n")
    blocks = shapes.find_blocks(normalized).blocks
    if not blocks:
        outcome.failures.append(
            f"{VOUCH_FAILURE}: it holds no block at all (`take` finds none in it)")
        return
    if len(blocks) > 1:
        listed = ", ".join(f"[{n}] {describe_block(b)}" for n, b in enumerate(blocks, 1))
        outcome.failures.append(
            f"{VOUCH_FAILURE}: it holds {len(blocks)} blocks, not exactly one ({listed})")
        return
    found = blocks[0]
    whole = normalized if normalized.endswith("\n") else normalized + "\n"
    if shapes.block_text(normalized, found) != whole:
        outcome.failures.append(
            f"{VOUCH_FAILURE}: it carries text around its one block (the block is "
            f"lines {found.start_line}–{found.end_line} of "
            f"{len(shapes.split_lines(normalized))}); twine hands on exactly a "
            "block's own lines")
    if found.kind != shapes.EXCHANGE:
        outcome.failures.append(
            f"{VOUCH_FAILURE}: it is a {found.kind} block "
            f"({describe_block(found)}), not an exchange block")
        return
    if not found.ok:
        fault = found.integrity.get("fault", "malformed")
        outcome.failures.append(
            f"{VOUCH_FAILURE}: it fails integrity ({fault}): {found.error} — twine "
            "never prints a block it cannot vouch for, and never repairs one")
    sid = found.fields.get("sid")
    if sid is not None and sid != outcome.sid:
        outcome.failures.append(
            f"{VOUCH_FAILURE}: it is an exchange block of session {sid!r}, not of the "
            f"carried block's {outcome.sid!r}")


def describe_block(block: shapes.Block) -> str:
    """A block's kind and identity, as a reason names it: `exchange
    2026-10-07-sc-002`, `light <sid>`, `probe <slug>`."""
    identity = block.fields.get("sid") or block.fields.get("slug")
    return f"{block.kind} {identity}" if identity else block.kind


def exchange_lines(outcome: ExchangeOutcome) -> list[str]:
    """stdout without --json: on ok exactly the line's `block` (the block
    the courier carries next, byte for byte what the flagless relay
    printed); otherwise one line naming why, never the block."""
    if not outcome.ok:
        state = "NOT OK" if outcome.call.ran else "refused"
        return [f"carry exchange {label_of(outcome.source)}: {state} — "
                f"{outcome.reason}"]
    return passthrough_lines(outcome.relayed_block or "")


# ---------------------------------------------------------------------------
# 3. carry response
# ---------------------------------------------------------------------------

DRY_RUN_OUTCOME = "dry-run"


@dataclass
class ResponseOutcome:
    """Everything `carry response` learned."""

    name: str
    tarball: str | None = None
    refusals: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    call: BaleCall = field(default_factory=BaleCall)
    dry_run: dict[str, Any] | None = None
    cwd: str | None = None
    bale: dict[str, Any] | None = None

    @property
    def outcome(self) -> Any:
        return None if self.dry_run is None else self.dry_run.get("outcome")

    @property
    def ok(self) -> bool:
        return not self.refusals and self.call.ran and not self.failures

    @property
    def apply_line(self) -> str | None:
        if not self.ok or self.tarball is None:
            return None
        return bale.apply_line(self.tarball)

    @property
    def reason(self) -> str | None:
        problems = self.refusals + self.failures
        return "; ".join(problems) if problems else None

    def payload(self) -> dict[str, Any]:
        """The JSON twin beside `command` and `ok` (cli-contract.md §11.3).
        `tarball`, `ran`, `exit_code`, `dry_run`, `outcome`, `apply_line`,
        `stderr`, `reason` and `refusals` are fixed names."""
        call = self.call.report()
        return {
            "tarball": self.tarball,
            "ran": call.pop("ran"),
            "exit_code": call.pop("exit_code"),
            "dry_run": self.dry_run,
            "outcome": self.outcome,
            "apply_line": self.apply_line,
            "stderr": call.pop("stderr"),
            "reason": self.reason,
            "refusals": self.refusals,
            **call,
            "cwd": self.cwd,
            "bale": self.bale,
        }


def cmd_carry_response(ctx: Context, args: argparse.Namespace) -> Result:
    """The verb: `check_response`, rendered."""
    outcome = check_response(ctx, args)
    return Result(outcome.ok, outcome.payload(), response_lines(outcome))


def check_response(ctx: Context, args: argparse.Namespace) -> ResponseOutcome:
    """Check the file exists, dry-run it, read the verdict, hand back the
    apply line. Never `bale apply` without `--dry-run` (T12). The verb
    renders what this returns; since Arc 2 R4 `twine run` calls it when the
    worker delivers (cli-contract.md §18: the function, not a subprocess),
    with `args` carrying `tarball`, `cwd` and `bale_root`."""
    outcome = ResponseOutcome(name=args.tarball)
    outcome.cwd = resolve_cwd(args.cwd, outcome.refusals)
    resolve_tarball(outcome)
    executable = locate(ctx, args, outcome.refusals)
    outcome.bale = executable.as_json()
    if not outcome.refusals:
        assert outcome.tarball is not None and executable.path is not None
        outcome.call = call_bale(ctx, bale.dry_run_argv(executable.path,
                                                        outcome.tarball),
                                 outcome.cwd or ".", None,
                                 outcome.refusals, outcome.failures)
        if outcome.call.ran:
            read_verdict(outcome, executable.manifest)
    for problem in outcome.refusals + outcome.failures:
        ctx.info(problem)
    if outcome.ok:
        ctx.info(f"dry run clean (outcome {DRY_RUN_OUTCOME!r}); nothing was "
                 "applied — run the line on stdout to apply")
    return outcome


def resolve_tarball(outcome: ResponseOutcome) -> None:
    """The operator names the file; twine makes the name absolute and
    checks it is an existing file — no search path. `tarball` stays None
    unless it is."""
    path = bale.absolute_path(outcome.name)
    if not Path(path).exists():
        outcome.refusals.append(f"{outcome.name}: no such file ({path}); name the "
                                "response tarball's path — twine does not search "
                                "for it")
    elif not Path(path).is_file():
        outcome.refusals.append(f"{outcome.name}: not a file ({path})")
    else:
        outcome.tarball = path


def read_verdict(outcome: ResponseOutcome, manifest: bale.Manifest | None) -> None:
    """bale's stdout must be one JSON object carrying every key the
    manifest lists for the apply surface (bale.missing_keys_failure, since
    session 2026-10-12-twine-pin-floor-002) and whose `outcome` is
    "dry-run". Whatever it said instead is named in the reason, each fault
    beside the others."""
    try:
        obj = json.loads(outcome.call.stdout)
    except ValueError:
        obj = None
    if not isinstance(obj, dict):
        shown = outcome.call.stdout.strip()
        outcome.failures.append(
            "bale's stdout was not one JSON object"
            + (f" (it began {shown[:60]!r})" if shown else " (it was empty)"))
        return
    outcome.dry_run = obj
    lacking = bale.missing_keys_failure(manifest, READER_RESPONSE, obj)
    if lacking is not None:
        outcome.failures.append(lacking)
    if obj.get("outcome") != DRY_RUN_OUTCOME:
        outcome.failures.append(f"bale reported outcome {obj.get('outcome')!r}, "
                                f"not {DRY_RUN_OUTCOME!r}")


def response_lines(outcome: ResponseOutcome) -> list[str]:
    """stdout without --json: on ok exactly the apply line; otherwise one
    line naming why."""
    if outcome.ok:
        return [outcome.apply_line or ""]
    state = "NOT OK" if outcome.call.ran else "refused"
    return [f"carry response {outcome.name}: {state} — {outcome.reason}"]


# ---------------------------------------------------------------------------
# 4. Shared helpers
# ---------------------------------------------------------------------------


def resolve_cwd(name: str | None, refusals: list[str]) -> str:
    """Where bale runs: `--cwd`, else the current directory — the repo
    whose session the block or tarball belongs to. A current directory
    that no longer exists is a refusal, never a traceback (session 5b)."""
    if name is None:
        try:
            return str(Path.cwd())
        except OSError as exc:
            refusals.append(f"the current directory cannot be resolved "
                            f"({exc.strerror or exc}); name the repo with --cwd")
            return "."
    path = Path(name).expanduser()
    if not path.is_dir():
        refusals.append(f"--cwd {name} is not a directory")
        return str(path)
    return str(path.resolve())


def locate(ctx: Context, args: argparse.Namespace,
           refusals: list[str]) -> bale.Executable:
    """The bale to run, found as `bale check` finds it. None found is a
    refusal; so, since Arc 1 session 4, is a bale the gate does not admit
    (D2: `bale.Executable.drive_refusal` — since session
    2026-10-12-twine-pin-floor-002 exactly the install `twine bale check`
    reports not ok: below the floor, a VERSION that cannot be read or
    parsed, or schemas that do not hash as the manifest pins them)."""
    executable = bale.locate_executable(args.bale_root, ctx.env, ctx.which)
    refusal = executable.drive_refusal
    if refusal is not None:
        refusals.append(refusal)
    return executable


def passthrough_lines(stdout: str) -> list[str]:
    """Lines the dispatcher prints back as exactly `stdout` (it writes
    each with a newline). A stdout without a final newline gains one."""
    if not stdout:
        return []
    return stdout[:-1].split("\n") if stdout.endswith("\n") else stdout.split("\n")


# ---------------------------------------------------------------------------
# 5. The registry entries
# ---------------------------------------------------------------------------

CWD_ARGUMENT = Argument(("--cwd",), {
    "metavar": "DIR", "default": None,
    "help": "the repo bale runs in (default: the current directory)"})
BALE_ROOT_ARGUMENT = Argument(("--bale-root",), {
    "metavar": "DIR", "default": None,
    "help": "the bale install root (default: $TWINE_BALE_ROOT, else `bale` "
            "on PATH — as `twine bale check` finds it)"})

COMMANDS = (
    Command(
        name=READER_EXCHANGE,
        summary="hand an exchange block from a pasted turn to `bale relay "
                "<sid> - --json`; print the block bale hands back",
        handler=cmd_carry_exchange,
        arguments=(
            Argument(("file",), {
                "metavar": "FILE",
                "help": "the pasted turn carrying the exchange block; `-` reads "
                        "stdin"}),
            Argument(("--block",), {
                "metavar": "N", "type": int, "default": None,
                "help": "the block to relay, by the number `twine take` prints "
                        "(its position among all blocks); required when the "
                        "input carries more than one exchange block"}),
            CWD_ARGUMENT,
            BALE_ROOT_ARGUMENT,
        ),
        description="Find the exchange block in FILE (read as `twine take` "
                    "reads it), refuse it unless its sha256 trailer holds, and "
                    "hand exactly its own lines — BEGIN through END — to "
                    "`bale relay <sid> - --json` on stdin, in --cwd, and read "
                    "the one JSON line bale prints. ok when bale exits 0 and "
                    "the line says \"relayed\" for the block's sid and carries "
                    "exactly one intact exchange block of that session; stdout "
                    "is then exactly that block, the one to carry next — a "
                    "block twine cannot vouch for is never printed. On a refusal the reason quotes bale's cause. "
                    "bale's stderr goes to stderr."),
    Command(
        name=READER_RESPONSE,
        summary="dry-run a response tarball with `bale apply --dry-run --json` "
                "and print the `bale apply` line that applies it — never applies",
        handler=cmd_carry_response,
        arguments=(
            Argument(("tarball",), {
                "metavar": "TARBALL",
                "help": "the response tarball (an existing file; no search)"}),
            CWD_ARGUMENT,
            BALE_ROOT_ARGUMENT,
        ),
        description="Run `bale apply --dry-run --json` on TARBALL, named by its "
                    "absolute path, in --cwd. ok when bale exits 0 and prints "
                    "one JSON object whose outcome is \"dry-run\"; stdout is "
                    "then exactly the line that applies it, `bale apply "
                    "<path>`, for you to run. twine never runs `bale apply` "
                    "without --dry-run and never passes an admission or "
                    "override flag: the merge stays yours."),
)

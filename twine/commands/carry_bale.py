"""`twine carry exchange` and `twine carry response` — the courier hands
bale what it carried (Arc 1 session 2b-ii).

`twine carry exchange FILE [--block N] [--cwd DIR] [--bale-root DIR]
[--json]` reads FILE exactly as `twine take` does, chooses one exchange
block (twine/commands/carry.py's `choose_block`: never a guess), refuses
a block whose integrity does not hold — twine never relays a block it
cannot vouch for, and never repairs one — and hands the block's own
lines (`shapes.block_text`: BEGIN through END, LF, one trailing newline;
nothing else from the input) to `bale relay <sid> -` on stdin, in the
repo the block's session lives in. ok exactly when bale exits 0; on ok,
human stdout is exactly bale's stdout — the block the courier carries
next.

`twine carry response TARBALL [--cwd DIR] [--bale-root DIR] [--json]`
runs `bale apply --dry-run --json` on the tarball, named by its absolute
path, and on a clean dry run hands back the one line that applies it:
`bale apply <path>`. It never applies anything (T12): the only `apply`
argv twine can build is twine.bale.dry_run_argv's, and no admission or
override flag exists anywhere in twine. ok exactly when bale exits 0 and
its stdout is one JSON object whose `outcome` is `"dry-run"`.

Both run bale through `ctx.run`, the seam (twine/process.py), never a
subprocess of their own, and find bale exactly as `bale check` does
(twine.bale.locate_executable): the tests pin TWINE_BALE_ROOT, so a bale
on the operator's PATH is never what a test reaches. Since Arc 1 session
4 both refuse, before starting it, a bale whose `bin/VERSION` is not the
pin (D2; twine.bale.Executable.drive_refusal). The contract is
claude/context/cli-contract.md §11.

Sections:
  1. Limits and the bale call        (~line 50)
  2. carry exchange                  (~line 135)
  3. carry response                  (~line 250)
  4. Shared helpers                  (~line 375)
  5. The registry entries            (~line 415)
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

# How long a bale verb may take. Neither verb is long-running — relay
# records a round and prints a block; a dry run stages nothing — so a
# call past this is stuck (waiting on something), and is killed and
# reported, never waited on forever.
BALE_TIMEOUT_SECONDS = 300.0
# bale's stdout is a paste block or one JSON line: kilobytes. Past this
# the call is stopped and is not ok.
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
              refusals: list[str], failures: list[str]) -> BaleCall:
    """Run `argv` through ctx.run and record what came back. A bale that
    cannot be started is a refusal (nothing ran); a run that was killed
    or exited non-zero is a failure naming why. bale's stderr is always
    surfaced on twine's stderr, whatever the outcome."""
    call = BaleCall(argv=list(argv))
    ctx.info(f"running bale {' '.join(argv[1:])} in {cwd} (executable {argv[0]})")
    try:
        result = ctx.run(argv, cwd=cwd, stdin=stdin, timeout=BALE_TIMEOUT_SECONDS,
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
        failures.append(f"bale did not finish within {BALE_TIMEOUT_SECONDS:g}s "
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


@dataclass
class ExchangeOutcome:
    """Everything `carry exchange` learned; rendered once as the JSON twin
    and once as human lines."""

    source: str
    input: dict[str, Any] = field(default_factory=dict)
    block_number: int | None = None
    block: shapes.Block | None = None
    refusals: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    call: BaleCall = field(default_factory=BaleCall)
    cwd: str | None = None
    bale: dict[str, Any] | None = None

    @property
    def sid(self) -> str | None:
        return None if self.block is None else self.block.fields.get("sid")

    @property
    def ok(self) -> bool:
        return not self.refusals and self.call.ran and not self.failures

    @property
    def reason(self) -> str | None:
        problems = self.refusals + self.failures
        return "; ".join(problems) if problems else None

    def payload(self) -> dict[str, Any]:
        """The JSON twin beside `command` and `ok` (cli-contract.md §11.2).
        `sid`, `block`, `ran`, `exit_code`, `stdout`, `stderr`, `reason`
        and `refusals` are fixed names the shell and the oracle read."""
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
            "integrity": None if self.block is None else self.block.integrity,
            **call,
            "cwd": self.cwd,
            "bale": self.bale,
            "input": self.input,
        }


def cmd_carry_exchange(ctx: Context, args: argparse.Namespace) -> Result:
    """Read, choose, vouch, then relay. Every refusal is collected before
    bale is called, and nothing reaches bale unless there is none."""
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
    for problem in outcome.refusals + outcome.failures:
        ctx.info(problem)
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


def exchange_lines(outcome: ExchangeOutcome) -> list[str]:
    """stdout without --json: on ok exactly bale's stdout (the block the
    courier carries next); otherwise one line naming why."""
    if not outcome.ok:
        state = "NOT OK" if outcome.call.ran else "refused"
        return [f"carry exchange {label_of(outcome.source)}: {state} — "
                f"{outcome.reason}"]
    return passthrough_lines(outcome.call.stdout)


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
    """Check the file exists, dry-run it, read the verdict, hand back the
    apply line. Never `bale apply` without `--dry-run` (T12)."""
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
            read_verdict(outcome)
    for problem in outcome.refusals + outcome.failures:
        ctx.info(problem)
    if outcome.ok:
        ctx.info(f"dry run clean (outcome {DRY_RUN_OUTCOME!r}); nothing was "
                 "applied — run the line on stdout to apply")
    return Result(outcome.ok, outcome.payload(), response_lines(outcome))


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


def read_verdict(outcome: ResponseOutcome) -> None:
    """bale's stdout must be one JSON object whose `outcome` is
    "dry-run". Whatever it said instead is named in the reason."""
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
    whose session the block or tarball belongs to."""
    if name is None:
        return str(Path.cwd())
    path = Path(name).expanduser()
    if not path.is_dir():
        refusals.append(f"--cwd {name} is not a directory")
        return str(path)
    return str(path.resolve())


def locate(ctx: Context, args: argparse.Namespace,
           refusals: list[str]) -> bale.Executable:
    """The bale to run, found as `bale check` finds it. None found is a
    refusal; so, since Arc 1 session 4, is a bale whose `bin/VERSION` is
    not the pin or cannot be read (D2: `bale.Executable.drive_refusal` —
    the transition table keys on the pinned version's vocabularies)."""
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
        name="carry exchange",
        summary="hand an exchange block from a pasted turn to `bale relay "
                "<sid> -`; print the block bale hands back",
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
                    "`bale relay <sid> -` on stdin, in --cwd. ok when bale "
                    "exits 0; stdout is then exactly bale's stdout, the block "
                    "to carry next. bale's stderr goes to stderr."),
    Command(
        name="carry response",
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

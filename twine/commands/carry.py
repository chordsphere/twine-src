"""`twine carry …` — the courier acts on what it read (Arc 1 session 2b).

This module is the `carry` verb family. Session 2b-i lands `carry probe`;
session 2b-ii adds `carry exchange` (a block to `bale relay`) and
`carry response` (a tarball to `bale apply --dry-run --json`) beside it.

`twine carry probe FILE [--block N] [--run] [--cwd DIR] [--timeout S]
[--out PATH] [--json]` reads FILE exactly as `twine take` does (one
parser, twine.shapes), picks one probe block, and shows it. Only an
explicit `--run` hands the script to bash — through `ctx.run`, the run
seam (twine/process.py), never a subprocess of its own — with a timeout
and a stdout cap, and only when the block is ready: intact, no unfilled
`TODO(worker)` placeholder, a `# Read-only:` header line, and no
existing `--out` file to clobber. The script's stdout is read back with
twine.shapes; the run is ok exactly when it exited 0, in time, under the
cap, with exactly one intact `probe-output` block of the probe's slug.
That block — BEGIN through END, LF, one trailing newline — is the
paste-back the operator carries.

The script runs unconfined (`confined: false`, always, in Arc 1): the
operator's privileges, environment and network. Arc 2's sandbox is what
makes it true. The contract is claude/context/cli-contract.md §10.

Sections:
  1. Limits and the outcome         (~line 45)
  2. Reading and choosing a block   (~line 135)
  3. Readiness: refused before running (~line 200)
  4. Running and verifying          (~line 235)
  5. The verb                       (~line 335)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from twine import shapes
from twine.cli import Context
from twine.commands.take import STDIN, read_input
from twine.process import RunError
from twine.registry import Argument, Command, Result

# ---------------------------------------------------------------------------
# 1. Limits and the outcome
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_SECONDS = 300.0
# The captured-stdout cap. A probe's output is a chat paste (TARBALL.md
# §4.2: "bounded output"); the largest one recorded so far is 37,521
# bytes (fixtures/…/probe-output_twine-take-specimens.txt). 256 KiB is
# seven times that and still a paste a person can carry. Past it the
# run is stopped and is not ok.
STDOUT_CAP_BYTES = 256 * 1024
BASH = "bash"


@dataclass
class Outcome:
    """Everything `carry probe` learned, rendered once as the JSON twin
    and once as human lines — the two never disagree."""

    source: str
    input: dict[str, Any] = field(default_factory=dict)
    run_requested: bool = False
    block_number: int | None = None
    block: shapes.Block | None = None
    header: list[str] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    run_failures: list[str] = field(default_factory=list)
    ran: bool = False
    exit_code: int | None = None
    timed_out: bool = False
    capped: bool = False
    stderr: str = ""
    stderr_truncated: bool = False
    duration_seconds: float | None = None
    integrity: dict[str, Any] = field(default_factory=lambda: {
        "ok": False, "basis": "line-count", "expected_lines": None,
        "found_lines": None, "error": "no paste-back: the probe did not run"})
    output: str = ""
    out_written: str | None = None
    cwd: str | None = None
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    @property
    def slug(self) -> str | None:
        return None if self.block is None else self.block.fields.get("slug")

    @property
    def script(self) -> str | None:
        return None if self.block is None else self.block.fields.get("script")

    @property
    def ok(self) -> bool:
        if self.refusals:
            return False
        return not self.run_requested or (self.ran and not self.run_failures)

    @property
    def reason(self) -> str | None:
        problems = self.refusals + self.run_failures
        return "; ".join(problems) if problems else None

    def payload(self) -> dict[str, Any]:
        """The JSON twin's keys beside `command` and `ok` (cli-contract.md
        §10.4). `slug`, `ran`, `confined`, `exit_code`, `timed_out`,
        `integrity` and `output` are fixed names 2b-ii and the shell read."""
        return {
            "slug": self.slug,
            "block": self.block_number,
            "ran": self.ran,
            "confined": False,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "capped": self.capped,
            "stdout_cap_bytes": STDOUT_CAP_BYTES,
            "integrity": self.integrity,
            "output": self.output,
            "reason": self.reason,
            "refusals": self.refusals,
            "header": self.header,
            "script": self.script,
            "run_requested": self.run_requested,
            "cwd": self.cwd,
            "timeout_seconds": self.timeout,
            "duration_seconds": self.duration_seconds,
            "stderr": self.stderr,
            "stderr_truncated": self.stderr_truncated,
            "out": self.out_written,
            "input": self.input,
        }


# ---------------------------------------------------------------------------
# 2. Reading and choosing a block
# ---------------------------------------------------------------------------


def read_turn(ctx: Context, outcome: Outcome) -> shapes.Report | None:
    """Read and normalize FILE exactly as `twine take` does; a failure is
    a refusal on the outcome, and None."""
    try:
        data = read_input(ctx, outcome.source)
    except OSError as exc:
        outcome.refusals.append(f"cannot read {label_of(outcome.source)}: "
                                f"{exc.strerror or exc}")
        return None
    try:
        norm = shapes.normalize(data)
    except ValueError as exc:
        outcome.input = {"source": label_of(outcome.source), "bytes": len(data)}
        outcome.refusals.append(f"{label_of(outcome.source)}: {exc}")
        return None
    outcome.input = {"source": label_of(outcome.source), "bytes": norm.bytes_read,
                     "lines": len(shapes.split_lines(norm.text)),
                     "crlf_normalized": norm.crlf_replaced,
                     "bom_stripped": norm.bom_stripped}
    return shapes.find_blocks(norm.text)


def label_of(source: str) -> str:
    return "<stdin>" if source == STDIN else source


def choose_block(report: shapes.Report, number: int | None,
                 outcome: Outcome) -> None:
    """Pick the probe block, or refuse — never guess. `number` is the
    1-based position `twine take` prints, among *all* blocks; without it,
    exactly one probe block must be present."""
    blocks = report.blocks
    if number is not None:
        if not 1 <= number <= len(blocks):
            outcome.refusals.append(
                f"--block {number} names no block: the input has "
                f"{len(blocks)} block{'' if len(blocks) == 1 else 's'}")
            return
        block = blocks[number - 1]
        if block.kind != shapes.PROBE:
            outcome.refusals.append(
                f"--block {number} names a {block.kind} block, not a probe "
                f"(lines {block.start_line}-{block.end_line})")
            return
        outcome.block_number, outcome.block = number, block
        return
    probes = [(n, b) for n, b in enumerate(blocks, 1) if b.kind == shapes.PROBE]
    if not probes:
        kinds = ", ".join(b.kind for b in blocks) or "none"
        outcome.refusals.append(f"no probe block in the input (blocks found: {kinds})")
        return
    if len(probes) > 1:
        listed = ", ".join(f"[{n}] {b.fields.get('slug')}" for n, b in probes)
        outcome.refusals.append(
            f"{len(probes)} probe blocks ({listed}); name one with --block N")
        return
    outcome.block_number, outcome.block = probes[0]


# ---------------------------------------------------------------------------
# 3. Readiness: refused before running
# ---------------------------------------------------------------------------


def check_ready(outcome: Outcome, args: argparse.Namespace) -> None:
    """Every reason the chosen block may not run, collected (not just the
    first), so one invocation names them all. These hold with or
    without --run: a block that would be refused is never reported ok."""
    block = outcome.block
    assert block is not None
    script = outcome.script
    if not block.ok:
        outcome.refusals.append(f"probe {outcome.slug} is malformed: {block.error}")
    if script is not None:
        outcome.header = shapes.probe_header(script)
        if shapes.UNFILLED_SENTINEL in script:
            outcome.refusals.append(
                f"probe {outcome.slug} still carries the crafter's "
                f"{shapes.UNFILLED_SENTINEL} placeholder — an unfilled scaffold, "
                "not ready to paste")
        if shapes.probe_read_only_line(outcome.header) is None:
            outcome.refusals.append(
                f"probe {outcome.slug}'s header declares no `# Read-only:` line "
                "(TARBALL.md §4.2's purpose header confirms the script is read-only)")
    if args.out is not None and Path(args.out).expanduser().exists():
        outcome.refusals.append(f"--out {args.out} already exists; carry probe "
                                "never overwrites")
    if args.timeout <= 0:
        outcome.refusals.append(f"--timeout must be positive (got {args.timeout:g})")
    if args.cwd is not None and not Path(args.cwd).expanduser().is_dir():
        outcome.refusals.append(f"--cwd {args.cwd} is not a directory")


# ---------------------------------------------------------------------------
# 4. Running and verifying
# ---------------------------------------------------------------------------


def run_probe(ctx: Context, outcome: Outcome) -> None:
    """Hand the script to bash through the seam, then verify its stdout.
    bash gets the script as `-c` text (no file is written) and /dev/null
    as stdin (a probe is not interactive, and `-` may have consumed ours)."""
    bash = ctx.which(BASH)
    if bash is None:
        outcome.refusals.append("bash not found on PATH; nothing ran")
        return
    ctx.info(f"running probe {outcome.slug} with {bash} in {outcome.cwd} — "
             f"timeout {outcome.timeout:g}s, stdout cap {STDOUT_CAP_BYTES} bytes, "
             "unconfined (your privileges, environment and network)")
    try:
        result = ctx.run([bash, "-c", outcome.script, f"twine-probe-{outcome.slug}"],
                         cwd=outcome.cwd, stdin=None, timeout=outcome.timeout,
                         env=dict(ctx.env), stdout_cap=STDOUT_CAP_BYTES)
    except RunError as exc:
        outcome.refusals.append(f"bash could not be started: {exc.strerror or exc}")
        return
    outcome.ran = True
    outcome.exit_code = result.exit_code
    outcome.timed_out = result.timed_out
    outcome.capped = result.stdout_capped
    outcome.duration_seconds = result.duration_seconds
    outcome.stderr = result.stderr.decode("utf-8", errors="replace")
    outcome.stderr_truncated = result.stderr_truncated
    if result.timed_out:
        outcome.run_failures.append(
            f"timed out after {outcome.timeout:g}s; the script and its children "
            "were killed")
    if result.stdout_capped:
        outcome.run_failures.append(
            f"stdout passed the cap of {STDOUT_CAP_BYTES} bytes; the script was "
            "stopped and its output is incomplete")
    if not result.killed and result.exit_code != 0:
        outcome.run_failures.append(f"the script exited {result.exit_code}")
    verify_output(result.stdout, outcome)


def verify_output(stdout: bytes, outcome: Outcome) -> None:
    """Read stdout with twine.shapes: exactly one probe-output block, of
    the probe's slug, whose line-count trailer holds. `output` is that
    block's own lines, or the best candidate found when not ok."""
    try:
        text = shapes.normalize(stdout).text
    except ValueError as exc:
        outcome.integrity = {"ok": False, "basis": "line-count",
                             "expected_lines": None, "found_lines": None,
                             "error": f"stdout: {exc}"}
        outcome.run_failures.append(f"stdout: {exc}")
        return
    found = [b for b in shapes.find_blocks(text).blocks
             if b.kind == shapes.PROBE_OUTPUT]
    same = [b for b in found if b.fields.get("slug") == outcome.slug]
    pick = (same or found or [None])[0]
    if pick is None:
        outcome.integrity = {"ok": False, "basis": "line-count",
                             "expected_lines": None, "found_lines": None,
                             "error": "stdout carries no probe-output block"}
        outcome.run_failures.append(
            f"stdout carries no `=== PROBE BEGIN {outcome.slug} ===` block")
        return
    outcome.output = shapes.block_text(text, pick)
    outcome.integrity = dict(pick.integrity)
    if pick.error is not None:
        outcome.integrity["error"] = pick.error
    if len(found) != 1:
        outcome.run_failures.append(
            f"stdout carries {len(found)} probe-output blocks; exactly one is "
            "the paste-back")
    if pick.fields.get("slug") != outcome.slug:
        outcome.run_failures.append(
            f"the probe-output block's slug is {pick.fields.get('slug')}, the "
            f"probe's is {outcome.slug}")
    if not pick.ok:
        outcome.run_failures.append(f"the paste-back fails integrity: {pick.error}")


def write_out(path: str, outcome: Outcome) -> None:
    """Write the verified paste-back to PATH, exclusively: a file that
    appeared since the readiness check is refused, not overwritten."""
    target = Path(path).expanduser()
    try:
        with target.open("xb") as fh:
            fh.write(outcome.output.encode("utf-8"))
    except FileExistsError:
        outcome.run_failures.append(f"--out {path} appeared during the run; "
                                    "not overwritten")
        return
    except OSError as exc:
        outcome.run_failures.append(f"--out {path}: {exc.strerror or exc}")
        return
    outcome.out_written = str(target)


# ---------------------------------------------------------------------------
# 5. The verb
# ---------------------------------------------------------------------------


def cmd_carry_probe(ctx: Context, args: argparse.Namespace) -> Result:
    """Read, choose, check, and — only on --run — run and verify. Every
    failure is a not-ok Result (exit 1) with the reason named."""
    outcome = Outcome(source=args.file, run_requested=bool(args.run),
                      timeout=float(args.timeout))
    outcome.cwd = str(Path(args.cwd).expanduser().resolve()) if args.cwd \
        else str(Path.cwd())
    report = read_turn(ctx, outcome)
    if report is not None:
        choose_block(report, args.block, outcome)
    if outcome.block is not None:
        check_ready(outcome, args)
    if not outcome.refusals and args.run:
        run_probe(ctx, outcome)
        if outcome.ok and args.out is not None:
            write_out(args.out, outcome)
    for problem in outcome.refusals + outcome.run_failures:
        ctx.info(problem)
    return Result(outcome.ok, outcome.payload(), human_lines(ctx, outcome))


def human_lines(ctx: Context, outcome: Outcome) -> list[str]:
    """stdout without --json. A verified run prints exactly the paste-back
    block (so `> paste.txt` captures what is carried); a block shown
    without --run prints exactly its script (so it is read before it
    runs); anything not ok prints one line naming why. The summary and
    diagnostics go to stderr."""
    label = label_of(outcome.source)
    where = ""
    if outcome.block is not None:
        b = outcome.block
        where = (f"probe {outcome.slug} (block [{outcome.block_number}], "
                 f"lines {b.start_line}-{b.end_line})")
    if not outcome.ok:
        if outcome.ran:
            ctx.info(f"{where}: ran — exit {outcome.exit_code}, timed out "
                     f"{outcome.timed_out}, capped {outcome.capped}")
            if outcome.stderr:
                ctx.info("the script's stderr follows")
                ctx.stderr.write(outcome.stderr if outcome.stderr.endswith("\n")
                                 else outcome.stderr + "\n")
        state = "NOT OK" if outcome.ran else "refused"
        return [f"carry probe {label}: {state} — {outcome.reason}"]
    if not outcome.ran:
        ctx.info(f"{where}: shown, not run — pass --run to execute it with bash "
                 "(unconfined: your privileges, environment and network)")
        return (outcome.script or "").rstrip("\n").split("\n")
    ctx.info(f"{where}: ran — exit 0, paste-back verified "
             f"({outcome.integrity.get('found_lines')} lines)"
             + (f", written to {outcome.out_written}" if outcome.out_written else ""))
    return outcome.output.rstrip("\n").split("\n")


COMMANDS = (
    Command(
        name="carry probe",
        summary="show a probe block from a pasted turn; run it with bash only "
                "on --run (timeout, output cap) and return the verified paste-back",
        handler=cmd_carry_probe,
        arguments=(
            Argument(("file",), {
                "metavar": "FILE",
                "help": "the pasted turn carrying the probe block; `-` reads stdin"}),
            Argument(("--block",), {
                "metavar": "N", "type": int, "default": None,
                "help": "the block to use, by the number `twine take` prints "
                        "(its position among all blocks); required when the "
                        "input carries more than one probe"}),
            Argument(("--run",), {
                "action": "store_true",
                "help": "run the script with bash (unconfined: your privileges, "
                        "environment and network); without it nothing executes"}),
            Argument(("--cwd",), {
                "metavar": "DIR", "default": None,
                "help": "the directory bash runs in (default: the current one)"}),
            Argument(("--timeout",), {
                "metavar": "SECONDS", "type": float,
                "default": DEFAULT_TIMEOUT_SECONDS,
                "help": "stop the script and its children after this long "
                        f"(default {DEFAULT_TIMEOUT_SECONDS:g})"}),
            Argument(("--out",), {
                "metavar": "PATH", "default": None,
                "help": "also write the verified paste-back here; refused if "
                        "PATH exists (never overwrites)"}),
        ),
        description="Find the probe block in FILE (read as `twine take` reads "
                    "it), check it is ready — intact, no TODO(worker) "
                    "placeholder, a `# Read-only:` header line — and show it. "
                    "Only --run executes it: bash in --cwd, inheriting your "
                    f"environment, killed with its children after --timeout, "
                    f"stdout capped at {STDOUT_CAP_BYTES} bytes. The run is ok "
                    "when the script exits 0 and its stdout carries exactly one "
                    "intact probe-output block of the probe's slug; that block "
                    "is printed (and written to --out). Not a sandbox."),
)

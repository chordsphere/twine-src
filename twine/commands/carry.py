"""`twine carry …` — the courier acts on what it read (Arc 1 session 2b).

This module is the `carry` verb family's first member, `carry probe`
(session 2b-i), and the reading every carry verb shares: FILE read as
`take` reads it, and one block chosen by kind — never a guess. Session
2b-ii's `carry exchange` (a block to `bale relay`) and `carry response`
(a tarball to `bale apply --dry-run --json`) live beside it in
twine/commands/carry_bale.py and choose their block through the same
`choose_block` — which, with the rest of the probe machinery, lives in
twine/probing.py since session 2026-10-13-twine-housekeeping-probe-008.

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
makes it true, and the flag is read from the runner in one place
(twine.process.runner_confines), never set here. The contract is claude/context/cli-contract.md §10.

Sections:
  1. Reading a turn                 (read_turn, label_of)
  2. The verb's own readiness       (check_ready: --out, --timeout, --cwd)
  3. Writing the paste-back         (write_out)
  4. The verb                       (cmd_carry_probe, human_lines, COMMANDS)
The limits, the outcome and choosing, readiness, running and verifying a
block are twine/probing.py's (sections 1-4 there).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from twine import shapes
from twine.cli import Context
from twine.commands.take import STDIN, read_input
from twine.probing import (BASH, CARRIED_KINDS, DEFAULT_TIMEOUT_SECONDS,  # noqa: F401
                           STDOUT_CAP_BYTES, CarryOutcome, Outcome, check_block_ready,
                           choose_block, run_probe, verify_output)
from twine.process import runner_confines
from twine.registry import Argument, Command, Result

# The probe machinery — the limits, `Outcome`, `choose_block`,
# `check_block_ready`, `run_probe`, `verify_output` — lives in
# twine/probing.py (session 2026-10-13-twine-housekeeping-probe-008) so the
# runtime's `probe` tool can use it without importing a command module. The
# names above are imported back: this module calls them, and carry_bale.py
# and the tests still read them here. The names marked noqa are re-exports
# nothing in this file calls.

# ---------------------------------------------------------------------------
# 1. Reading a turn
# ---------------------------------------------------------------------------


def read_turn(ctx: Context, outcome: CarryOutcome
              ) -> tuple[shapes.Report, str] | None:
    """Read and normalize FILE exactly as `twine take` does: the report,
    and the normalized text its line numbers count in (block_text slices
    it). A failure is a refusal on the outcome, and None."""
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
    return shapes.find_blocks(norm.text), norm.text


def label_of(source: str) -> str:
    return "<stdin>" if source == STDIN else source


# ---------------------------------------------------------------------------
# 2. The verb's own readiness
# ---------------------------------------------------------------------------


def check_ready(outcome: Outcome, args: argparse.Namespace) -> None:
    """Every reason the chosen block may not run, collected (not just the
    first), so one invocation names them all. These hold with or
    without --run: a block that would be refused is never reported ok."""
    check_block_ready(outcome)
    if args.out is not None and Path(args.out).expanduser().exists():
        outcome.refusals.append(f"--out {args.out} already exists; carry probe "
                                "never overwrites")
    if args.timeout <= 0:
        outcome.refusals.append(f"--timeout must be positive (got {args.timeout:g})")
    if args.cwd is not None and not Path(args.cwd).expanduser().is_dir():
        outcome.refusals.append(f"--cwd {args.cwd} is not a directory")


# ---------------------------------------------------------------------------
# 3. Writing the paste-back
# ---------------------------------------------------------------------------


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
# 4. The verb
# ---------------------------------------------------------------------------


def cmd_carry_probe(ctx: Context, args: argparse.Namespace) -> Result:
    """Read, choose, check, and — only on --run — run and verify. Every
    failure is a not-ok Result (exit 1) with the reason named."""
    outcome = Outcome(source=args.file, run_requested=bool(args.run),
                      timeout=float(args.timeout), confined=runner_confines(ctx.run))
    outcome.cwd = str(Path(args.cwd).expanduser().resolve()) if args.cwd \
        else str(Path.cwd())
    read = read_turn(ctx, outcome)
    if read is not None:
        choose_block(read[0], args.block, outcome)
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

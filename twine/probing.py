"""The probe machinery, shared by `twine carry probe` and the runtime's
`probe` tool — a home that is neither a command module nor the CLI.

Until session 2026-10-13-twine-housekeeping-probe-008 these functions
lived in twine/commands/carry.py, and the runtime's `probe` tool
(twine/runtime/tools/probe.py, Arc 2 R3) imported that command module — the
first runtime→commands edge. They moved here so that nothing under
twine/runtime/ imports a command module or twine.cli (tests/test_probing.py
walks the imports and holds it). twine/commands/carry.py imports them back
and keeps re-exporting the names, so `carry probe` calls the same functions
from their new home and every older import of them still resolves.

What is here: the limits and the `Outcome` a probe's reading, readiness and
run write to (section 1); choosing exactly one block of a kind from a
`twine.shapes` report (section 2: `choose_block`, never a guess); the
block's own readiness rules (section 3: `check_block_ready`); and running
the script with bash through a run seam and verifying its stdout (section 4:
`run_probe`, `verify_output`). The verb's own concerns — reading FILE,
`--out`, `--timeout`, `--cwd`, the JSON twin and the human lines — stay in
carry.py.

What the helpers take instead of a `cli.Context`: `run_probe` takes a
`ProbeSeam`, the four things it uses — the run seam (`run`), `which`, `env`
and `info` — and nothing else of the CLI's (no streams, no stdin).
`cli.Context` satisfies the protocol as it is, so `carry probe` passes its
own; the runtime's tool passes a `Seam` (below), a small concrete one that
collects the informational lines for its log instead of writing them to a
stream. `choose_block`, `check_block_ready` and `verify_output` take only an
outcome (and a report or bytes).

Pure of the CLI: imports twine.shapes and twine.process only, and no
subprocess of its own — the script runs through the seam it is handed
(twine/process.py; cli-contract.md §10.6).

Sections:
  1. Limits, the outcome and the seam
  2. Choosing a block
  3. Readiness: refused before running
  4. Running and verifying
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from twine import shapes
from twine.process import RunError, Runner

# ---------------------------------------------------------------------------
# 1. Limits, the outcome and the seam
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
    # Read from the runner (twine.process.runner_confines), never set
    # anywhere else: false for the default runner, all of Arc 1.
    confined: bool = False

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
            "confined": self.confined,
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


class ProbeSeam(Protocol):
    """What `run_probe` touches: the run seam, `which`, the environment
    mapping handed to the script, and a line for a human. `twine.cli.Context`
    has exactly these members (its `info` writes `[twine] <line>` to stderr),
    so it is a ProbeSeam without importing this module."""

    run: Runner
    which: Callable[[str], str | None]
    env: Mapping[str, str]

    def info(self, message: str) -> None: ...


@dataclass
class Seam:
    """A concrete ProbeSeam for a caller that is not the CLI (the runtime's
    `probe` tool): the same four members, `info` collecting each line into
    `lines` — the caller logs them — rather than writing to a stream."""

    run: Runner
    which: Callable[[str], str | None]
    env: Mapping[str, str]
    lines: list[str] = field(default_factory=list)

    def info(self, message: str) -> None:
        self.lines.append(message)


# ---------------------------------------------------------------------------
# 2. Choosing a block
# ---------------------------------------------------------------------------


class CarryOutcome(Protocol):
    """What reading and choosing write to — every carry verb's outcome
    (`Outcome` here; carry_bale.py's two) carries these fields."""

    source: str
    input: dict[str, Any]
    refusals: list[str]
    block_number: int | None
    block: shapes.Block | None


# The kinds a carry verb acts on, as a refusal names them.
CARRIED_KINDS = {shapes.PROBE: ("a probe", "slug"),
                 shapes.EXCHANGE: ("an exchange", "sid")}


def choose_block(report: shapes.Report, number: int | None,
                 outcome: CarryOutcome, kind: str = shapes.PROBE) -> None:
    """Pick the block of `kind`, or refuse — never guess. `number` is the
    1-based position `twine take` prints, among *all* blocks; without it,
    exactly one block of `kind` must be present. A `--block` naming a
    block of another kind is refused, which is also why no carry verb can
    be pointed at a relay block (cli-contract.md §9.4)."""
    noun, ident = CARRIED_KINDS[kind]
    blocks = report.blocks
    if number is not None:
        if not 1 <= number <= len(blocks):
            outcome.refusals.append(
                f"--block {number} names no block: the input has "
                f"{len(blocks)} block{'' if len(blocks) == 1 else 's'}")
            return
        block = blocks[number - 1]
        if block.kind != kind:
            article = "an" if block.kind[0] in "aeiou" else "a"
            outcome.refusals.append(
                f"--block {number} names {article} {block.kind} block, not {noun} "
                f"(lines {block.start_line}-{block.end_line})")
            return
        outcome.block_number, outcome.block = number, block
        return
    found = [(n, b) for n, b in enumerate(blocks, 1) if b.kind == kind]
    if not found:
        kinds = ", ".join(b.kind for b in blocks) or "none"
        outcome.refusals.append(f"no {kind} block in the input (blocks found: {kinds})")
        return
    if len(found) > 1:
        listed = ", ".join(f"[{n}] {b.fields.get(ident)}" for n, b in found)
        outcome.refusals.append(
            f"{len(found)} {kind} blocks ({listed}); name one with --block N")
        return
    outcome.block_number, outcome.block = found[0]


# ---------------------------------------------------------------------------
# 3. Readiness: refused before running
# ---------------------------------------------------------------------------


def check_block_ready(outcome: Outcome) -> None:
    """The block's own readiness — intact, no unfilled TODO(worker)
    placeholder, a `# Read-only:` header line — each fault a refusal on the
    outcome, and the header recorded. Split out of check_ready at Arc 2 R3
    so the runtime's `probe` tool (twine/runtime/tools/probe.py) holds a
    block to exactly the rules `carry probe` does; the verb's own flags
    (--out, --timeout, --cwd) stay check_ready's (twine/commands/carry.py)."""
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


# ---------------------------------------------------------------------------
# 4. Running and verifying
# ---------------------------------------------------------------------------


def run_probe(seam: ProbeSeam, outcome: Outcome) -> None:
    """Hand the script to bash through the seam, then verify its stdout.
    bash gets the script as `-c` text (no file is written) and /dev/null
    as stdin (a probe is not interactive, and `-` may have consumed ours)."""
    bash = seam.which(BASH)
    if bash is None:
        outcome.refusals.append("bash not found on PATH; nothing ran")
        return
    seam.info(f"running probe {outcome.slug} with {bash} in {outcome.cwd} — "
             f"timeout {outcome.timeout:g}s, stdout cap {STDOUT_CAP_BYTES} bytes, "
             "unconfined (your privileges, environment and network)")
    try:
        result = seam.run([bash, "-c", outcome.script, f"twine-probe-{outcome.slug}"],
                         cwd=outcome.cwd, stdin=None, timeout=outcome.timeout,
                         env=dict(seam.env), stdout_cap=STDOUT_CAP_BYTES)
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

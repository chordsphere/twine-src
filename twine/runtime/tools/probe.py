"""`probe` — a read-only probe block run against the real repository, its
verified paste-back returned (T6, D13; Arc 2 R3, runtime-contract.md §6.2,
§6.5). **The one tool that leaves the cage.**

D13: "a `probe` tool closes the paste-back hop". It reuses `twine carry
probe`'s machinery (twine/probing.py — a module that is neither a command
nor the CLI, so nothing under twine/runtime/ imports either) rather than a
second copy of it: the block found in the text by twine.shapes (exactly one probe block —
`choose_block`), held to the same readiness rules (`check_block_ready`:
intact, no unfilled `TODO(worker)`, a `# Read-only:` header line), run with
bash through the run seam (`run_probe`), and its stdout verified
(`verify_output`: exactly one intact `probe-output` block of the probe's
slug). Its `content` is that block — the paste that closes the hop.

Where it runs, and what confines it: `cwd` is the sandbox's `repo`, the real
repository, by D13; the run is **not** the sandbox's runner (no `unshare`),
so the network and the filesystem are the operator's, as cli-contract.md
§10.5 says of `carry probe`. Confinement is the read-only declaration's and
the operator's; this tool does not pretend otherwise, and says so with
`leaves_cage: true`. Two things it does that `carry probe` does not: the
environment is the cage's minimal one, so the script never sees
ANTHROPIC_API_KEY or anything else of the operator's; and its process group
is registered with the kill-switch (Sandbox.spawn), like every spawn of the
runtime's.
"""

from __future__ import annotations

import logging
import shutil
from typing import Any, Mapping

from twine import probing, shapes
from twine.process import RunResult
from twine.runtime.sandbox import Sandbox, SpawnRefused
from twine.runtime.terms import ToolSpec
from twine.runtime.tooling import Tool, ToolResult

log = logging.getLogger("twine.runtime.tools.probe")

SOURCE_LABEL = "<probe tool>"
# How much of a failed probe's stderr the model reads back.
STDERR_SHOWN_CHARS = 4096


def probe_seam(sandbox: Sandbox) -> probing.Seam:
    """The seam probing's run_probe runs against: the cage's environment,
    `bash` looked up on the cage's PATH, and the run seam composed with the
    kill-switch hook (Sandbox.spawn) around the sandbox's unwrapped runner.
    Its `info` lines are collected on the seam (`lines`), for the log."""
    def seam(argv, *, cwd=None, stdin=None, timeout=None, env=None, stdout_cap=None,
             on_spawn=None) -> RunResult:
        return sandbox.spawn(argv, runner=sandbox.run, cwd=cwd, timeout=timeout,
                             stdout_cap=stdout_cap, env=env, stdin=stdin)

    return probing.Seam(run=seam, env=dict(sandbox.env),
                        which=lambda name: shutil.which(name, path=sandbox.env.get("PATH")))


def execute(sandbox: Sandbox, arguments: Mapping[str, Any]) -> ToolResult:
    text = arguments["block"]
    timeout = sandbox.tool_timeout(probing.DEFAULT_TIMEOUT_SECONDS)
    outcome = probing.Outcome(source=SOURCE_LABEL, run_requested=True, timeout=timeout)
    outcome.cwd = str(sandbox.repo)
    try:
        norm = shapes.normalize(text.encode("utf-8"))
    except (UnicodeEncodeError, ValueError) as exc:
        return TOOL.error(f"probe: the block cannot be read: {exc}")
    probing.choose_block(shapes.find_blocks(norm.text), None, outcome)
    if outcome.block is not None:
        probing.check_block_ready(outcome)
    if outcome.refusals:
        return TOOL.error("probe: refused before running — " + "; ".join(outcome.refusals)
                          + " (a probe block is a fenced script whose header carries "
                            "`# PROBE <slug>: …` and `# Read-only: …`, TARBALL.md §4.2)",
                          slug=outcome.slug)
    seam = probe_seam(sandbox)
    try:
        probing.run_probe(seam, outcome)
    except SpawnRefused as exc:
        return TOOL.error(f"probe {outcome.slug}: nothing ran: {exc}", slug=outcome.slug)
    finally:
        for line in seam.lines:
            log.info("probe %s: %s", outcome.slug, line)
    lines = outcome.integrity.get("expected_lines")
    if outcome.ok:
        return TOOL.ok(outcome.output, slug=outcome.slug, leaves_cage=True,
                       exit_code=outcome.exit_code, lines=lines)
    parts = [f"probe {outcome.slug}: NOT OK — {outcome.reason}"]
    if outcome.output:
        parts.append("[the best candidate block in its stdout]\n" + outcome.output.rstrip("\n"))
    if outcome.stderr:
        shown = outcome.stderr[-STDERR_SHOWN_CHARS:]
        parts.append("[stderr" + (", its end" if len(shown) < len(outcome.stderr) else "")
                     + "]\n" + shown.rstrip("\n"))
    return TOOL.error("\n".join(parts) + "\n", slug=outcome.slug,
                      exit_code=outcome.exit_code, lines=lines)


TOOL = Tool(
    spec=ToolSpec(
        name="probe",
        description=("Ask the operator's machine a question: run a read-only probe "
                     "block (bale's shape — a fenced bash script whose header carries "
                     "`# PROBE <slug>: …` and `# Read-only: …`, printing one "
                     "`=== PROBE BEGIN <slug> ===` block with its integrity trailer) "
                     "against the real repository, outside your sandbox. Returns the "
                     "verified probe-output block."),
        input_schema={
            "type": "object",
            "properties": {
                "block": {"type": "string", "minLength": 1,
                          "description": "the probe block, fence included, as text"},
            },
            "required": ["block"],
            "additionalProperties": False,
        }),
    leaves_cage=True,
    result_keys=("slug", "leaves_cage", "exit_code", "lines"),
    error_defaults={"slug": None, "leaves_cage": True, "exit_code": None, "lines": None},
    execute=execute,
)

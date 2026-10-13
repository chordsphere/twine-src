"""`escalate` — the worker asks the packer, and asks the loop to suspend
(T6, D13 and its annotations; Arc 2 R3 and R5, runtime-contract.md §6.2,
§6.6).

D13 as annotated: `escalate` emits bale's shapes, never a fork — a light
question block or a clarification response. Both forms take the same rows:
each question a clarification question row's four fields under the names
the model is offered — `question`, `while_doing` (the row's `context`),
`would_assume` (`default_assumption`), `why_blocked`.

**The light form** (R3; `blocking` absent or false; TARBALL.md §5.10): one
to three questions — admission is a count, never a judgment — each field one
line, rendered under the four fixed labels between `=== LIGHT BEGIN <sid>
===` and `=== LIGHT END <sid> ===`, ending with the packer's three replies.
The block is read back with twine.shapes before it is returned: exactly one
`light` block, intact, for the sandbox's sid, carrying the rows as given —
or the call is an error naming why. The result is the block as `content`,
`kind: "light"`, `suspend: true`; the loop stops the worker's turn and
carries the block.

**The clarification form** (R5; `blocking: true`; TARBALL.md §5.9): one or
more questions — the light tier's count of three does not bind; the
clarification response's schema does (`questions[]` non-empty, each row the
four fields, none empty). The tool writes the clarification response
tarball in the home and names it, wrapping bale's shape and never forking
it:

  1. the request-carried crafter scaffolds the response directory, in the
     cage through the sandbox's runner — `request/tools/craft_response.py
     <dir> --sid <sid> --kind clarification --questions N --write`: the
     manifest skeleton, its no-op `apply.sh` and `validation.sh`;
  2. the manifest's judgment fields are filled from the arguments — the
     rows, and a `summary` saying what the session was asked to do (the
     request manifest's goal) and that it is blocked on the questions;
  3. the request-carried lint (`request/tools/response_lint.py <dir>
     --json`) judges it in the cage, when the request carries it: a finding
     is an error result naming it;
  4. the tarball is built as a response tarball is (TARBALL.md §5.1, one
     top directory `response-NNN/`, NNN the sid's counter), named
     `response-<sid>.tar.gz` (§10.1 step 11).

The work lands under `escalations/<k>/` in the home, `k` the first number
not yet taken, so a session that escalates in several rounds keeps every
round. The result: `kind: "clarification"`, `suspend: true`, `questions`
(the count), `path` (the tarball, relative to the home) and `sha256`; the
loop treats it as `deliver` and suspend — `carry response` on the tarball,
then `suspended` with the apply line (runtime-contract.md §7.4). `path`
and `sha256` are null on the light form.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import sys
import tarfile
from pathlib import Path
from typing import Any, Mapping

from twine import process, shapes
from twine.runtime.sandbox import Sandbox, SpawnRefused
from twine.runtime.terms import ToolSpec
from twine.runtime.tooling import Tool, ToolResult

log = logging.getLogger("twine.runtime.tools.escalate")

KIND_LIGHT = "light"
KIND_CLARIFICATION = "clarification"
MAX_QUESTIONS = 3
# The call's field names, in the order the block renders them, onto
# TARBALL.md §5.10's labels and the clarification row fields twine.shapes
# reads them back as (and the response manifest's `questions[]` carries).
FIELDS = (("question", "question", "question"),
          ("while_doing", "while doing", "context"),
          ("would_assume", "would assume", "default_assumption"),
          ("why_blocked", "why blocked", "why_blocked"))
LABEL_WIDTH = max(len(label) for _, label, _ in FIELDS) + 2   # "would assume: "
REPLY_LINE = 'Reply: answer inline, "as assumed", or "formal".'

# The clarification form's paths, inside the home.
REQUEST_TOOLS = "request/tools"
CRAFTER = f"{REQUEST_TOOLS}/craft_response.py"
LINT = f"{REQUEST_TOOLS}/response_lint.py"
REQUEST_MANIFEST = "request/manifest.json"
ESCALATIONS = "escalations"
# How long the crafter and the lint may each run, at most (both are
# stdlib-only formatters that finish in well under a second).
TOOL_TIMEOUT_SECONDS = 60.0
TOOL_STDOUT_CAP = 256 * 1024


# ---------------------------------------------------------------------------
# The light form (R3)
# ---------------------------------------------------------------------------


def light_block(sid: str, questions: list[dict[str, str]]) -> str:
    """The light question block, as TARBALL.md §5.10 lays it out."""
    lines = [f"=== LIGHT BEGIN {sid} ==="]
    for n, row in enumerate(questions, 1):
        for i, (key, label, _) in enumerate(FIELDS):
            lead = f"[{n}] " if i == 0 else " " * len(f"[{n}] ")
            lines.append(f"{lead}{(label + ':').ljust(LABEL_WIDTH)}{row[key]}")
    lines.append(REPLY_LINE)
    lines.append(f"=== LIGHT END {sid} ===")
    return "\n".join(lines) + "\n"


def row_faults(n: int, row: Mapping[str, str], *, one_line: bool = True) -> list[str]:
    found = []
    for key, _, _ in FIELDS:
        value = row[key]
        if not value.strip():
            found.append(f"question {n}'s {key} is empty")
        elif one_line and ("\n" in value or "\r" in value):
            found.append(f"question {n}'s {key} is more than one line (a light question "
                         "fits on one line; a longer one is the clarification form, "
                         "blocking: true)")
    return found


def read_back(sid: str, text: str, rows: list[dict[str, str]]) -> str | None:
    """Why the block does not read back as one intact light block for `sid`
    carrying `rows`; None when it does."""
    blocks = shapes.find_blocks(text).blocks
    if len(blocks) != 1 or blocks[0].kind != shapes.LIGHT:
        return f"it reads as {[b.kind for b in blocks]}, not one light block"
    block = blocks[0]
    if not block.ok:
        return f"twine.shapes refuses it: {block.error}"
    if block.fields.get("sid") != sid:
        return f"it names session {block.fields.get('sid')!r}, not {sid!r}"
    parsed = block.fields.get("questions", [])
    wanted = [{field: row[key] for key, _, field in FIELDS} for row in rows]
    if parsed != wanted:
        return "its rows do not read back as given"
    return None


def light(sandbox: Sandbox, given: list[Mapping[str, str]]) -> ToolResult:
    if not 1 <= len(given) <= MAX_QUESTIONS:
        return TOOL.error(f"escalate: {len(given)} questions; a light block holds one to "
                          f"{MAX_QUESTIONS} (more is the clarification form: call escalate "
                          "with blocking: true)", questions=len(given))
    rows = [{key: q[key].strip() for key, _, _ in FIELDS} for q in given]
    faults = [f for n, row in enumerate(given, 1) for f in row_faults(n, row)]
    if faults:
        return TOOL.error("escalate: " + "; ".join(faults), questions=len(given))
    text = light_block(sandbox.sid, rows)
    problem = read_back(sandbox.sid, text, rows)
    if problem is not None:
        return TOOL.error(f"escalate: the light block would not reach the packer intact: "
                          f"{problem}", questions=len(given))
    return TOOL.ok(text, kind=KIND_LIGHT, suspend=True, questions=len(rows), path=None,
                   sha256=None)


# ---------------------------------------------------------------------------
# The clarification form (R5)
# ---------------------------------------------------------------------------


class ClarificationFault(Exception):
    """A clarification response that could not be written; the message is
    the error result's content."""


def response_dir_name(sid: str) -> str:
    """`response-NNN`: the sid's per-day counter, zero-padded to three
    digits (TARBALL.md §1)."""
    counter = sid.rsplit("-", 1)[-1]
    return f"response-{int(counter):03d}" if counter.isdigit() else "response-001"


def tarball_name(sid: str) -> str:
    """`response-<sid>.tar.gz`: the filename carries the full session id
    (TARBALL.md §10.1 step 11)."""
    return f"response-{sid}.tar.gz"


def next_round_dir(home: Path) -> Path:
    """`escalations/<k>/` under the home, `k` the first positive number not
    taken — every round of a session's escalations is kept."""
    base = home / ESCALATIONS
    k = 1
    while (base / str(k)).exists():
        k += 1
    return base / str(k)


def run_in_cage(sandbox: Sandbox, argv: list[str], what: str) -> process.RunResult:
    """A request-carried tool, run in the cage through the sandbox's runner
    (network off where it can be, the cage's environment, registered with the
    kill-switch), with the home as its working directory. The interpreter is
    the one twine runs on, so the tool gets a Python twine knows is 3.11 or
    newer whatever the cage's PATH holds."""
    try:
        result = sandbox.spawn([sys.executable, "-I", "-B", *argv], cwd=sandbox.home,
                               timeout=min(TOOL_TIMEOUT_SECONDS, sandbox.max_timeout),
                               stdout_cap=TOOL_STDOUT_CAP)
    except SpawnRefused as exc:
        raise ClarificationFault(f"escalate: {what} was not started: {exc}") from exc
    except process.RunError as exc:
        raise ClarificationFault(f"escalate: {what} could not start: "
                                 f"{exc.strerror or exc}") from exc
    if result.timed_out:
        raise ClarificationFault(f"escalate: {what} did not finish within "
                                 f"{TOOL_TIMEOUT_SECONDS:g}s")
    return result


def said(result: process.RunResult) -> str:
    text = (result.stderr or b"").decode("utf-8", errors="replace").strip()
    return text[-2000:] if text else "nothing on stderr"


def request_goal(home: Path) -> str | None:
    """The request manifest's goal, when it can be read — the summary says
    what the session was asked to do."""
    try:
        goal = json.loads((home / REQUEST_MANIFEST).read_text(encoding="utf-8")).get("goal")
    except (OSError, ValueError, AttributeError):
        return None
    return goal.strip() if isinstance(goal, str) and goal.strip() else None


def summary(sid: str, goal: str | None, count: int) -> str:
    asked = (f"Session {sid} was asked to: {goal}" if goal is not None
             else f"Session {sid} was asked to do the work its request names")
    return (f"{asked.rstrip('.')}. The worker, hosted by twine, cannot produce trustworthy "
            f"work without the planner's answer to the {count} question(s) below; it is "
            "blocked on them and continues under the same session id when the answer "
            "comes back (twine resume).")


def write_clarification(sandbox: Sandbox, rows: list[dict[str, str]]) -> tuple[str, str, str]:
    """Steps 1–4 of the module docstring. Returns the tarball's path
    relative to the home, its sha256 and what the lint said; raises
    ClarificationFault naming what went wrong."""
    home = sandbox.home
    sid = sandbox.sid
    if not (home / CRAFTER).is_file():
        raise ClarificationFault(f"escalate: the request carries no crafter at {CRAFTER}; "
                                 "the clarification response is bale's shape, written by "
                                 "bale's tool, and twine does not fork it")
    round_dir = next_round_dir(home)
    response = round_dir / response_dir_name(sid)
    try:
        response.mkdir(mode=0o700, parents=True)
    except OSError as exc:
        raise ClarificationFault(f"escalate: cannot make {sandbox.relative(response)}: "
                                 f"{exc.strerror or exc}") from exc
    rel = sandbox.relative(response)
    # 1. The crafter's skeleton.
    crafted = run_in_cage(sandbox, [CRAFTER, rel, "--sid", sid, "--kind", KIND_CLARIFICATION,
                                    "--questions", str(len(rows)), "--write"],
                          "the crafter")
    if crafted.exit_code != 0:
        raise ClarificationFault(f"escalate: the crafter exited {crafted.exit_code}: "
                                 f"{said(crafted)}")
    manifest_path = response / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ClarificationFault(f"escalate: the crafter's manifest cannot be read: {exc}") \
            from exc
    stubs = manifest.get("questions") if isinstance(manifest, dict) else None
    if (not isinstance(manifest, dict) or manifest.get("response_kind") != KIND_CLARIFICATION
            or not isinstance(stubs, list) or len(stubs) != len(rows)):
        raise ClarificationFault("escalate: the crafter's manifest is not a clarification "
                                 f"skeleton with {len(rows)} question row(s)")
    # 2. The judgment fields, from the arguments.
    manifest["summary"] = summary(sid, request_goal(home), len(rows))
    manifest["questions"] = [{**stub, **{field: row[key] for key, _, field in FIELDS}}
                             for stub, row in zip(stubs, rows)]
    try:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ClarificationFault(f"escalate: cannot write the manifest: "
                                 f"{exc.strerror or exc}") from exc
    # 3. The lint, when the request carries it.
    if (home / LINT).is_file():
        linted = run_in_cage(sandbox, [LINT, rel, "--json"], "the lint")
        if linted.exit_code != 0:
            raise ClarificationFault("escalate: the clarification response does not pass "
                                     f"the request's lint (exit {linted.exit_code}): "
                                     + lint_findings(linted))
        lint = "the request's lint passed it"
    else:
        log.warning("escalate: the request carries no %s; the clarification response was "
                    "not linted before the dry run", LINT)
        lint = f"the request carries no {LINT}, so it was not linted (the dry run judges it)"
    # 4. The tarball: one top directory, response-NNN/.
    tarball = round_dir / tarball_name(sid)
    try:
        with tarfile.open(tarball, "w:gz") as tf:
            tf.add(response, arcname=response.name)
    except (OSError, tarfile.TarError) as exc:
        raise ClarificationFault(f"escalate: cannot build {sandbox.relative(tarball)}: "
                                 f"{exc}") from exc
    digest = hashlib.sha256(tarball.read_bytes()).hexdigest()
    return sandbox.relative(tarball), digest, lint


def lint_findings(result: process.RunResult) -> str:
    try:
        report = json.loads(result.stdout.decode("utf-8"))
        findings = report.get("findings") or []
        named = [f"{f.get('id') or f.get('code')}: {f.get('detail') or f.get('message')}"
                 if isinstance(f, dict) else str(f) for f in findings]
        if named:
            return "; ".join(named)
    except (ValueError, AttributeError, UnicodeDecodeError):
        pass
    return said(result)


def clarification(sandbox: Sandbox, given: list[Mapping[str, str]]) -> ToolResult:
    if not given:
        return TOOL.error("escalate: no questions; a clarification response carries at least "
                          "one", kind=KIND_CLARIFICATION, questions=0)
    rows = [{key: q[key].strip() for key, _, _ in FIELDS} for q in given]
    faults = [f for n, row in enumerate(rows, 1) for f in row_faults(n, row, one_line=False)]
    if faults:
        return TOOL.error("escalate: " + "; ".join(faults), kind=KIND_CLARIFICATION,
                          questions=len(given))
    try:
        path, sha, lint = write_clarification(sandbox, rows)
    except ClarificationFault as exc:
        log.error("%s", exc)
        return TOOL.error(str(exc), kind=KIND_CLARIFICATION, questions=len(rows))
    return TOOL.ok(f"escalate: wrote the clarification response {path} ({len(rows)} "
                   f"question(s); sha256 {sha}; {lint}). The courier checks it with bale and "
                   "the session suspends; the planner's answer comes back as your next turn. "
                   "Do no more work in this turn.",
                   kind=KIND_CLARIFICATION, suspend=True, questions=len(rows), path=path,
                   sha256=sha)


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------


def execute(sandbox: Sandbox, arguments: Mapping[str, Any]) -> ToolResult:
    given = arguments["questions"]
    if arguments.get("blocking") is True:
        return clarification(sandbox, given)
    return light(sandbox, given)


QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "minLength": 1,
                     "description": "the question, one line"},
        "while_doing": {"type": "string", "minLength": 1,
                        "description": "what you were doing when it arose"},
        "would_assume": {"type": "string", "minLength": 1,
                         "description": "the default you would take — one the packer "
                                        "can ratify with a word"},
        "why_blocked": {"type": "string", "minLength": 1,
                        "description": "why you cannot simply proceed on that default"},
    },
    "required": ["question", "while_doing", "would_assume", "why_blocked"],
    "additionalProperties": False,
}

TOOL = Tool(
    spec=ToolSpec(
        name="escalate",
        description=("Ask the packer questions you cannot settle yourself, each with the "
                     "default you would take, and suspend until the answer comes back; do "
                     "no more work in this turn. By default a light question block "
                     "(TARBALL.md §5.10): one to three short, non-blocking questions, each "
                     "field one line. With blocking: true, a clarification response "
                     "(TARBALL.md §5.9) for a gap that blocks trustworthy work: one or more "
                     "questions, written as the response tarball bale carries to the "
                     "planner."),
        input_schema={
            "type": "object",
            "properties": {
                "questions": {"type": "array", "minItems": 1,
                              "items": QUESTION_SCHEMA,
                              "description": "the questions: one to three for a light "
                                             "block; one or more with blocking: true"},
                "blocking": {"type": "boolean",
                             "description": "true for the clarification response (a "
                                            "blocking intent gap); false or absent for "
                                            "the light question block"},
            },
            "required": ["questions"],
            "additionalProperties": False,
        }),
    leaves_cage=False,
    result_keys=("kind", "suspend", "questions", "path", "sha256"),
    error_defaults={"kind": KIND_LIGHT, "suspend": False, "questions": None, "path": None,
                    "sha256": None},
    execute=execute,
)

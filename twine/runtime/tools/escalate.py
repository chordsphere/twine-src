"""`escalate` — the worker asks the packer, and asks the loop to suspend
(T6, D13 and its annotations; Arc 2 R3, runtime-contract.md §6.2, §6.6).

D13 as annotated: `escalate` emits bale's shapes, never a fork — a
clarification response or a light question block. R3 builds the light form
(TARBALL.md §5.10): one to three questions, each a clarification question
row's four fields — `question`, `while_doing`, `would_assume`, `why_blocked`
— rendered under the four fixed labels between `=== LIGHT BEGIN <sid> ===`
and `=== LIGHT END <sid> ===`, ending with the packer's three replies. The
block is read back with twine.shapes before it is returned: exactly one
`light` block, intact, for the sandbox's sid, carrying the rows as given —
or the call is an error naming why. More than three questions is an error
(admission is a count, never a judgment), as is a field that is empty or not
one line.

The result carries `kind: "light"` and `suspend: true`: the loop (R4) stops
the worker's turn and carries the block. The blocking form — the
clarification response, with cold resume — is R5's; `kind` is declared now so
R5 adds a value, not a shape.
"""

from __future__ import annotations

from typing import Any, Mapping

from twine import shapes
from twine.runtime.sandbox import Sandbox
from twine.runtime.terms import ToolSpec
from twine.runtime.tooling import Tool, ToolResult

KIND_LIGHT = "light"
MAX_QUESTIONS = 3
# The call's field names, in the order the block renders them, onto
# TARBALL.md §5.10's labels and the clarification row fields twine.shapes
# reads them back as.
FIELDS = (("question", "question", "question"),
          ("while_doing", "while doing", "context"),
          ("would_assume", "would assume", "default_assumption"),
          ("why_blocked", "why blocked", "why_blocked"))
LABEL_WIDTH = max(len(label) for _, label, _ in FIELDS) + 2   # "would assume: "
REPLY_LINE = 'Reply: answer inline, "as assumed", or "formal".'


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


def row_faults(n: int, row: Mapping[str, str]) -> list[str]:
    found = []
    for key, _, _ in FIELDS:
        value = row[key]
        if not value.strip():
            found.append(f"question {n}'s {key} is empty")
        elif "\n" in value or "\r" in value:
            found.append(f"question {n}'s {key} is more than one line (a light question "
                         "fits on one line; a longer one is a clarification response)")
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


def execute(sandbox: Sandbox, arguments: Mapping[str, Any]) -> ToolResult:
    given = arguments["questions"]
    if not 1 <= len(given) <= MAX_QUESTIONS:
        return TOOL.error(f"escalate: {len(given)} questions; a light block holds one to "
                          f"{MAX_QUESTIONS} (more is a clarification response, R5's)",
                          questions=len(given))
    rows = [{key: q[key].strip() for key, _, _ in FIELDS} for q in given]
    faults = [f for n, row in enumerate(given, 1) for f in row_faults(n, row)]
    if faults:
        return TOOL.error("escalate: " + "; ".join(faults), questions=len(given))
    text = light_block(sandbox.sid, rows)
    problem = read_back(sandbox.sid, text, rows)
    if problem is not None:
        return TOOL.error(f"escalate: the light block would not reach the packer intact: "
                          f"{problem}", questions=len(given))
    return TOOL.ok(text, kind=KIND_LIGHT, suspend=True, questions=len(rows))


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
        description=("Ask the packer one to three short questions you cannot settle "
                     "yourself, each with the default you would take. Emits a light "
                     "question block (TARBALL.md §5.10) and suspends you until the "
                     "answer comes back; do no more work in this turn."),
        input_schema={
            "type": "object",
            "properties": {
                "questions": {"type": "array", "minItems": 1, "maxItems": MAX_QUESTIONS,
                              "items": QUESTION_SCHEMA,
                              "description": "one to three questions"},
            },
            "required": ["questions"],
            "additionalProperties": False,
        }),
    leaves_cage=False,
    result_keys=("kind", "suspend", "questions"),
    error_defaults={"kind": KIND_LIGHT, "suspend": False, "questions": None},
    execute=execute,
)

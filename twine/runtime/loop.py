"""The loop (Arc 2 R4; twine-seed.md §4, §4.3; claude/context/
runtime-contract.md §7): the functions that host a worker session's turns
once `twine run` (twine/commands/run.py, cli-contract.md §18) has opened the
session, registered the runtime, made the sandbox, unpacked the request,
built the adapter and opened the transcript.

The loop composes what R1–R3 built and Arc 1's spine:

  messages     start with one user turn, the opener — the text the operator
               used to paste into a worker chat, verbatim from bale's open
               line — and grow append-only (D12): an assistant turn, the
               tool results, the next user turn; nothing earlier is edited
  the prompt   SystemPrompt: the tool definitions and the surface note, and
               nothing else — nothing about the model, the provider or the
               task (D11, §4.3); a spawn-time constant, so prompt-cache
               stable (D12)
  each call    the abort file first (twine.kill.abort_requested, §14.3),
               then twine's --max-turns, then the window (R5: used up after
               the last call → `window-exhausted`, the call not made), then
               the pre-call cap check (twine.spend.check_call, §13.8) with
               the input estimate below — once a call has counted the
               window, its `used` plus the estimate of what was appended
               since — then one call through the boundary, its usage
               appended to the spend stream (spend.append_record, the sid's
               own, served_sid null) before anything else is done with the
               turn, then counted against the window (a `window` line)
  the window   twine.runtime.window (R5): warned at 80%, every tool result
               the model reads ends with the warning line from then on —
               never the transcript's tool-result line, never an earlier
               turn
  the move     the transition table's `stop` row for the turn's stop key,
               read through MoveBook — never a second dispatch table: the
               loop performs `classify-final-text`, `continue-turn` and
               `retry-with-backoff` itself (and `return-tool-error` for a
               failed tool), and every other move ends the run `stopped`,
               the move named for whoever performs it
  the tools    run in order through twine.runtime.tooling.run_tool (never
               raises); `escalate` suspends — on its clarification form (R5)
               after carrying the tarball it wrote to `carry response`, as
               `deliver` does — `deliver` hands the tarball to the courier's
               `carry response` (the `deliver` callable the verb passes), a
               failed tool goes back to the model as its result
  the view     the operator's only live view, `progress` lines on stderr
               (cli-contract.md §18.7): a returned turn's line carries the
               run's cost, the wall time and the window; a tool's line what
               it ran; a heartbeat every HEARTBEAT_SECONDS while one runs;
               and the verb's last line, the summary
  the story    every step is a transcript line (twine.transcript) before
               the next begins; when the run ends, what was never sent goes
               in one last `request` line, `sent: false`, so the lines'
               `appended`, joined, are the conversation `twine resume`
               rebuilds (R5, twine.runtime.resume)

Nothing here spells a stop key (the one spelling is the table's; tests walk
twine/runtime/ for it): the loop's own four keys come from twine.spend,
twine.kill and twine.transitions. Nothing here imports a process or
network module or reads the process environment; tools spawn through the
sandbox, the model is reached through the boundary.

Sections:
  1. Names, outcomes and limits     (~line 90)
  2. The system prompt and the estimate (~line 160)
  3. The conversation's shape       (~line 250)
  4. The request on disk            (~line 345)
  5. Moves, from the table          (~line 460)
  6. The loop                       (~line 525)
"""

from __future__ import annotations

import copy
import importlib
import json
import logging
import math
import pkgutil
import re
import tarfile
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

from twine import kill, shapes, spend
from twine.runtime import ADAPTERS_PACKAGE
from twine.runtime.boundary import Adapter, Boundary, BoundaryError, Request, Turn
from twine.runtime.sandbox import Sandbox
from twine.runtime.terms import ToolSpec
from twine.runtime.tooling import ToolRegistry, ToolResult, plain, run_tool
from twine.runtime.window import Window
from twine.transcript import Transcript, TranscriptError, write_raw
from twine.transitions import (STOP_ADAPTER_DEFECT, STOP_AXIS, STOP_WINDOW_EXHAUSTED, Move,
                               Table)

log = logging.getLogger("twine.runtime.loop")

# ---------------------------------------------------------------------------
# 1. Names, outcomes and limits
# ---------------------------------------------------------------------------

# How a run ends (cli-contract.md §18's `outcome`). Three are the loop's own
# stop keys and are taken from the modules that define them, never spelled
# here: the kill-switch's and the cost spine's two. A fourth loop key,
# `adapter-defect`, ends the run `stopped` (it has no outcome of its own) and
# comes from twine.transitions.
DELIVERED = "delivered"
SUSPENDED = "suspended"
ENDED = "ended"
STOPPED = "stopped"
KILLED = kill.STOP_KILLED
CAP_REACHED = spend.STOP_CAP_REACHED
CAP_UNCHECKED = spend.STOP_CAP_UNCHECKED
ADAPTER_DEFECT = STOP_ADAPTER_DEFECT
# The window's edge (Arc 2 R5): a provider's key the loop also reports
# itself, before a call, when the counted window is used up — `stopped`,
# the table's move for it (`split-goal`, the planner's) named.
WINDOW_EXHAUSTED = STOP_WINDOW_EXHAUSTED
REFUSED = "refused"
OUTCOMES = (DELIVERED, SUSPENDED, ENDED, STOPPED, KILLED, CAP_REACHED, CAP_UNCHECKED,
            REFUSED)
# The `shape` an `ended` run reports when twine's own turn limit stopped it
# (§18 (g): a limit twine imposes on itself is not a stop key).
SHAPE_MAX_TURNS = "max-turns"

# The moves the loop performs itself, by the table's names (each must be a
# declared move, or `twine run` refuses before it opens anything: MoveBook).
MOVE_CLASSIFY = "classify-final-text"
MOVE_CONTINUE = "continue-turn"
MOVE_RETRY = "retry-with-backoff"
MOVE_TOOL_ERROR = "return-tool-error"
PERFORMED_MOVES = (MOVE_CLASSIFY, MOVE_CONTINUE, MOVE_RETRY, MOVE_TOOL_ERROR)
# The stop keys the loop reports itself (the table's `loop_keys`): the table
# must declare each, with a row whose move is declared.
LOOP_STOP_KEYS = (CAP_REACHED, CAP_UNCHECKED, KILLED, ADAPTER_DEFECT)
# The stop keys the loop reports itself that a provider may report too, so
# the table declares them among its keys but not its loop_keys (Arc 2 R5):
# the table must still give each a row whose move is declared.
SHARED_STOP_KEYS = (WINDOW_EXHAUSTED,)
# The table's axis whose row names the move after a dry run (§11.3).
APPLY_AXIS = "apply-outcome"

# Bounds (PLANNER.md §16: bounded retries).
DEFAULT_MAX_TURNS = 200
MAX_RETRIES = 5
BACKOFF_SECONDS = (2, 4, 8, 16, 32)
MAX_CONTINUATIONS = 3
# The sleep between abort checks while waiting out a backoff (§14.3).
ABORT_POLL_SECONDS = 1.0
# How much of a tool result's text a transcript line keeps (the model got
# all of it; the request line carries what was sent).
TRANSCRIPT_TEXT_CAP = 64 * 1024

# The operator's live view (cli-contract.md §18.7): a heartbeat line every
# this many seconds while a tool runs, and a tool's argument cut at this many
# characters in a progress line.
HEARTBEAT_SECONDS = 30
PROGRESS_ARGUMENT_CHARS = 80

# Where the request is unpacked in the sandbox home (D11).
REQUEST_DIR = "request"
# The tool the loop runs a probe block in the final text through (D13).
PROBE_TOOL = "probe"


class LoopError(Exception):
    """A run that cannot start as asked: a request tarball that cannot be
    unpacked, an adapter not registered, a table whose moves the loop needs
    are not declared. The message names every fault; `twine run` refuses."""


# ---------------------------------------------------------------------------
# 2. The system prompt and the estimate
# ---------------------------------------------------------------------------

# The surface note (decision 1 of the R4 brief): what a worker needs to know
# about where it is and how its session ends — and nothing about the model,
# the provider or the task. Pinned in what it must say (runtime-contract §7.2):
# the request at request/, read with read_file/list_dir; the session ends with
# deliver, the response tarball built in the cage (the crafter is in the
# request); a question is escalate; a probe is probe.
SURFACE_NOTE = """\
You are a worker in a bale session hosted by twine. No one reads this \
conversation as it happens: what you need from anyone, and what you hand \
back, goes through your tools.

Your working directory is your sandbox home. Every file tool takes a path \
relative to it. The request you were handed is unpacked at request/ — \
request/manifest.json, request/AGENT.md, request/README.md (the brief) and \
request/context/, with bale's other docs and tools beside them. It is not in \
this conversation: read it with read_file and list_dir, as much as the \
docs tell you to. The shell tool runs bash in your home, with no network \
where the sandbox can turn it off.

You end the session by building the response tarball in your home — \
request/tools/craft_response.py and request/tools/response_lint.py are in \
the request — and calling deliver with its path. The courier checks it with \
bale; nothing is applied by you or by twine.

A question for the planner is the escalate tool: it suspends you until the \
answer comes back; with blocking: true it writes a clarification response \
for a gap that blocks trustworthy work, where the default is a light block \
of one to three short questions. A fact from the operator's machine is the \
probe tool: it runs a read-only probe block against the real repository and \
returns its paste-back. A turn that ends with neither a tool call nor a \
deliver ends the session without a response.

How to work here. List your home first: a previous desk's work may already \
be in it. Read ranges of a file, never the whole of a large one: every byte \
you print is read again on every later call. Write a large file in parts, a \
piece per call, rather than in one call. Never put a command in the \
background and poll it; run it to its end, and give it a timeout if it can \
be slow. The request carries no schemas: the lint judges your manifest, so \
run it on the response before you deliver. The context window does not \
compact; when it runs thin, the last line of a tool result says so."""


@dataclass(frozen=True)
class SystemPrompt:
    """What the model is given before the first turn: the surface note and
    the tool definitions, nothing else. A native-tool adapter carries the
    tools in its own field and the note as its system text; the text
    protocol (R6) will render both into one."""

    note: str
    tools: tuple[ToolSpec, ...]

    def tool_json(self) -> list[dict[str, Any]]:
        return [{"name": t.name, "description": t.description,
                 "input_schema": plain(t.input_schema)} for t in self.tools]

    def as_json(self) -> dict[str, Any]:
        return {"note": self.note, "tools": self.tool_json()}


def system_prompt(registry: ToolRegistry) -> SystemPrompt:
    """The run's system prompt: the surface note and the canonical tools'
    specs, in the declaration's order (the order the model is offered them)."""
    return SystemPrompt(SURFACE_NOTE, registry.specs())


# The input estimate for the pre-call check (decision 2): the request as
# twine would send it — the note, the tool definitions and the messages,
# JSON-encoded — counted in UTF-8 bytes and divided by this, rounded up.
# Deliberately high: a token is three to four bytes of English or code, and
# only the densest text (hex, base64) comes near two, so the worst case the
# check prices is above the real one. R5's window accounting replaces it
# with counted usage.
BYTES_PER_TOKEN_ESTIMATE = 2


def estimate_input_tokens(prompt: SystemPrompt, messages: Sequence[Mapping[str, Any]]) -> int:
    """An upper estimate of the call's input tokens, by characters (R4)."""
    body = json.dumps({"system": prompt.note, "tools": prompt.tool_json(),
                       "messages": list(messages)}, ensure_ascii=False, default=str)
    return math.ceil(len(body.encode("utf-8")) / BYTES_PER_TOKEN_ESTIMATE)


def estimate_appended_tokens(messages: Sequence[Mapping[str, Any]]) -> int:
    """R4's estimate (UTF-8 bytes / 2, rounded up) of the messages
    appended since the last call alone — what the pre-call check adds to the
    window's counted `used` once one exists (R5). 0 when nothing was
    appended (a retry of the same call)."""
    if not messages:
        return 0
    body = json.dumps(list(messages), ensure_ascii=False, default=str)
    return math.ceil(len(body.encode("utf-8")) / BYTES_PER_TOKEN_ESTIMATE)


# ---------------------------------------------------------------------------
# 3. The conversation's shape
# ---------------------------------------------------------------------------
#
# R1 left the message objects' shape to R4. It is the Messages API's own
# (runtime-contract §5.6): `{"role": "user" | "assistant", "content": …}`,
# content a string or a list of blocks — `text`, `tool_use`, `tool_result`,
# `thinking`, `redacted_thinking` — because the first adapter speaks it and
# keeps a turn's blocks byte for byte. An adapter for another wire (R6)
# translates from it. The helpers below build exactly what
# twine.runtime.adapters.anthropic's do for the same input (a test holds
# them to it), without the loop importing a provider's module.

CONTINUE_TEXT = ("Your last turn stopped at the output limit before it was finished. "
                 "Continue exactly where it stopped; do not repeat what you already "
                 "wrote.")
CUT_CALL_TEXT = ("The {name} call you were writing was cut off before its input was "
                 "complete, so it was not run. Make it again in smaller pieces: write a "
                 "large file in parts, never all in one call.")
NOT_RUN_CUT = ("not run: the turn was cut off at the output limit before this call was "
               "complete; call it again if you still need it")
NOT_RUN_ENDED = "not run: the session ended at an earlier call in the same turn ({why})"


def user_message(text: str) -> dict[str, Any]:
    return {"role": "user", "content": text}


def assistant_blocks(turn: Turn) -> list[dict[str, Any]]:
    """The assistant turn's content blocks: the turn's own `content`, exactly
    as the adapter received it (D12: a thinking block goes back byte for
    byte), when it has any; otherwise built from its text and tool calls —
    an adapter with no blocks of its own (the fake) has nothing a provider
    would reject. Thinking without blocks is not rebuilt: a provider's
    thinking block carries a signature only the provider can write."""
    if turn.content:
        return copy.deepcopy([dict(block) for block in turn.content])
    blocks: list[dict[str, Any]] = []
    if turn.text:
        blocks.append({"type": "text", "text": turn.text})
    for call in turn.tool_calls:
        blocks.append({"type": "tool_use", "id": call.id, "name": call.name,
                       "input": copy.deepcopy(dict(call.arguments))})
    return blocks


def assistant_message(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"role": "assistant", "content": blocks}


def tool_result_message(results: Sequence[tuple[str, str, bool]]) -> dict[str, Any]:
    """One user message carrying a `tool_result` block per (id, content,
    failed), `is_error: true` when the tool failed."""
    blocks = []
    for tool_use_id, content, failed in results:
        block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tool_use_id,
                                 "content": content}
        if failed:
            block["is_error"] = True
        blocks.append(block)
    return {"role": "user", "content": blocks}


def continue_message(blocks: list[dict[str, Any]],
                     noted: Callable[[str], str] = lambda text: text,
                     cut_tool_call: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The user turn that continues a cut-off turn (decision 3): a
    `tool_result` for every `tool_use` block the partial turn holds — the
    API refuses a tool_use left unanswered — saying it was not run, then the
    request to continue. The partial content itself is kept as the assistant
    turn before it, unedited; ending on a user turn needs no prefill, which
    not every model allows. `noted` is the window's (R5): on a warned run
    each text the model reads here ends with the warning line.
    `cut_tool_call` is the turn's, when the output ceiling cut a tool call
    off before its input was complete (that call is not among `blocks`, so
    no "not run" result answers it): the text then says so beside the
    request to continue, so the model writes a large file in parts."""
    content: list[dict[str, Any]] = [
        {"type": "tool_result", "tool_use_id": b.get("id"), "content": noted(NOT_RUN_CUT),
         "is_error": True}
        for b in blocks if b.get("type") == "tool_use"]
    text = CONTINUE_TEXT
    if cut_tool_call is not None:
        text += " " + CUT_CALL_TEXT.format(name=cut_tool_call.get("name") or "tool")
    content.append({"type": "text", "text": noted(text)})
    return {"role": "user", "content": content}


def clip(text: str, limit: int = TRANSCRIPT_TEXT_CAP) -> str:
    """`text` cut to at most `limit` UTF-8 bytes (on a character boundary),
    the cut marked; unchanged when it fits."""
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    kept = data[:limit].decode("utf-8", errors="ignore")
    return kept + f"\n[twine: cut at {limit} bytes of {len(data)}]"


def result_for_transcript(result: ToolResult) -> dict[str, Any]:
    """A tool result's as_json(), every string in it over 64 KiB cut with
    the cut marked (`content`, and `shell`'s `stdout` and `stderr`, which
    repeat it)."""
    out = result.as_json()
    for key, value in out.items():
        if isinstance(value, str):
            out[key] = clip(value)
    return out


# ---------------------------------------------------------------------------
# 3b. The operator's live view (cli-contract.md §18.7)
# ---------------------------------------------------------------------------


def format_cost(cost: Decimal | float | None) -> str:
    """A run's cost as the progress lines print it: `$<n>` with at least two
    decimals (four under a cent, so a first cheap call is not `$0.00`), and
    `$?` when the run cannot be priced (a model the price file lacks, no
    price file)."""
    if cost is None:
        return "$?"
    value = Decimal(str(cost)) if isinstance(cost, float) else cost
    return f"${value:.4f}" if 0 < value < Decimal("0.01") else f"${value:.2f}"


def format_seconds(seconds: float) -> str:
    """Wall time as the progress lines print it: whole seconds, `<n>s`."""
    return f"{max(0, round(seconds))}s"


def summary_text(outcome: str, *, stop: str | None, move: str | None, calls: int,
                 tool_calls: int, retries: int, cost: Decimal | float | None,
                 seconds: float) -> str:
    """The run's last progress line (cli-contract.md §18.7): `summary:`, then
    in this order the outcome, the stop and the move when there are any, the
    calls, the tool calls, the retries, the cost as `$<n>` and the wall time
    as `<n>s`."""
    parts = [outcome]
    if stop is not None:
        parts.append(f"stop {stop}")
    if move is not None:
        parts.append(f"move {move}")
    parts += [f"{calls} calls", f"{tool_calls} tool calls", f"{retries} retries",
              format_cost(cost), format_seconds(seconds)]
    return "summary: " + ", ".join(parts)


def one_line(text: str, limit: int = PROGRESS_ARGUMENT_CHARS) -> str:
    """`text` as one progress-line fragment: whitespace runs (a command's
    newlines among them) folded to one space, cut after `limit` characters
    with `...` where it was cut. No colour, no cursor movement: a line is
    plain text (N6)."""
    folded = re.sub(r"\s+", " ", text).strip()
    return folded if len(folded) <= limit else folded[:limit] + "..."


def tool_argument(name: str, arguments: Mapping[str, Any],
                  limit: int = PROGRESS_ARGUMENT_CHARS) -> str:
    """What a tool call runs, for its progress line, cut at 80 characters (or
    `limit`: a recovery plan shows 110):
    `shell`'s command, a file tool's path, `probe`'s slug, `escalate`'s
    question count and form, `deliver`'s path; empty for a tool this does
    not know, or arguments that do not have the key (the call is refused
    and the result says why)."""
    def text(key: str, default: str = "") -> str:
        value = arguments.get(key, default)
        return value if isinstance(value, str) else ""

    if name == "shell":
        shown = text("command")
    elif name in ("read_file", "write_file"):
        shown = text("path")
    elif name == "list_dir":
        shown = text("path", ".")
    elif name == "probe":
        report = shapes.find_blocks(text("block"))
        probes = [b for b in report.blocks if b.kind == shapes.PROBE]
        shown = str(probes[0].fields.get("slug")) if probes and probes[0].fields.get(
            "slug") else "(no readable slug)"
    elif name == "escalate":
        asked = arguments.get("questions")
        count = len(asked) if isinstance(asked, (list, tuple)) else 0
        form = "blocking" if arguments.get("blocking") is True else "light"
        shown = f"{count} question{'' if count == 1 else 's'}, {form}"
    elif name == "deliver":
        shown = text("tarball")
    else:
        shown = ""
    return one_line(shown, limit)


# ---------------------------------------------------------------------------
# 4. The request on disk (D11)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Unpacked:
    """What unpack_request put in the home: the directory, how many members,
    and the top-level directory it stripped (bale's `request-NNN/`), if any."""

    directory: Path
    members: int
    stripped: str | None

    def as_json(self) -> dict[str, Any]:
        return {"directory": str(self.directory), "members": self.members,
                "stripped": self.stripped}


def unpack_request(tarball: Path, home: Path) -> Unpacked:
    """Unpack the request tarball into `<home>/request/` with tarfile's
    `data` filter — every member as it is in the tarball, under the one
    top-level directory bale's request tarballs carry (`request-NNN/`),
    which is stripped so `request/manifest.json` is the manifest. Every
    member is put through the filter before anything is written, so a
    member that would escape (an absolute path, `..`, a link pointing out,
    a device) refuses the whole unpack — LoopError naming it — and nothing
    is extracted. A tarball whose members share no one top directory is
    unpacked as it is. Over an existing `request/` (a later run of the same
    session) each member is written again."""
    data_filter = getattr(tarfile, "data_filter", None)
    if data_filter is None:
        raise LoopError("this Python's tarfile has no `data` filter (3.11.4 and later "
                        "have it); twine will not unpack a request without one")
    dest = Path(home) / REQUEST_DIR
    try:
        archive = tarfile.open(tarball, "r:*")
    except (OSError, tarfile.TarError) as exc:
        raise LoopError(f"the request tarball {tarball} cannot be opened: {exc}") from exc
    with archive:
        try:
            members = archive.getmembers()
        except tarfile.TarError as exc:
            raise LoopError(f"the request tarball {tarball} cannot be read: {exc}") from exc
        strip = _top_directory(members)
        chosen: list[tarfile.TarInfo] = []
        faults: list[str] = []
        for member in members:
            renamed = member
            if strip is not None:
                parts = PurePosixPath(member.name).parts
                if len(parts) <= 1:          # the top directory itself
                    continue
                renamed = member.replace(name="/".join(parts[1:]), deep=False)
                if member.islnk():           # a hard link names a path in the archive
                    link = PurePosixPath(member.linkname).parts
                    if len(link) > 1 and link[0] == strip:
                        renamed = renamed.replace(linkname="/".join(link[1:]), deep=False)
            try:
                filtered = data_filter(renamed, str(dest))
            except tarfile.FilterError as exc:
                faults.append(f"{member.name!r}: {exc}")
                continue
            if filtered is not None:
                chosen.append(filtered)
        if faults:
            raise LoopError(f"the request tarball {tarball} has member(s) the `data` "
                            f"filter refuses, so nothing was unpacked: " + "; ".join(faults))
        try:
            dest.mkdir(mode=0o700, parents=True, exist_ok=True)
            archive.extractall(dest, members=chosen, filter="data")
        except (OSError, tarfile.TarError) as exc:
            raise LoopError(f"the request tarball {tarball} could not be unpacked into "
                            f"{dest}: {exc}") from exc
    log.info("request unpacked: %d member(s) into %s%s", len(chosen), dest,
             f" (top directory {strip}/ stripped)" if strip else "")
    return Unpacked(dest, len(chosen), strip)


def _top_directory(members: Sequence[tarfile.TarInfo]) -> str | None:
    """The one top-level directory every member lies under (bale's
    `request-NNN/`), or None when there is not exactly one: a member at the
    top that is not that directory, two top-level names, or nothing under
    it. Names are read as paths, so `./request-004/x` lies under
    `request-004`."""
    tops: set[str] = set()
    under = False
    for member in members:
        parts = PurePosixPath(member.name).parts
        if not parts:
            return None
        tops.add(parts[0])
        if len(parts) == 1 and not member.isdir():
            return None
        under = under or len(parts) > 1
    return next(iter(tops)) if len(tops) == 1 and under else None


def adapter_class(name: str) -> type[Adapter]:
    """The registered adapter class named `name`, found by listing the
    adapters package as the registry does (twine.runtime.registry) — so no
    module but an adapter's own names its class. LoopError when none is."""
    package = importlib.import_module(ADAPTERS_PACKAGE)
    for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda m: m.name):
        try:
            module = importlib.import_module(f"{ADAPTERS_PACKAGE}.{info.name}")
        except Exception as exc:   # named by `twine runtime list`; skipped here
            log.warning("adapters module %s does not import: %s", info.name, exc)
            continue
        for cls in getattr(module, "ADAPTERS", ()):
            if getattr(cls, "name", None) == name:
                return cls
    raise LoopError(f"no registered adapter is named {name!r}")


# ---------------------------------------------------------------------------
# 5. Moves, from the table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MoveBook:
    """The transition table as the loop reads it: the move of a stop key's
    row, and of an apply outcome's. The one dispatch is the table's; the
    loop branches on the move a row names."""

    table: Table

    def faults(self) -> list[str]:
        """Why the loop cannot stand on this table: the table's own problems
        (it must be total — D17), and any move the loop performs that it
        does not declare."""
        found = [p.message for p in self.table.problems]
        for name in PERFORMED_MOVES:
            if name not in self.table.moves:
                found.append(f"the loop performs the move {name!r}, which the table "
                             "does not declare")
        axis = self.table.axis(STOP_AXIS)
        if axis is None:
            found.append(f"the table has no {STOP_AXIS!r} axis")
        else:
            # The loop reports each of its own keys itself and names the move
            # of its row; a table without the key, or without its row, would
            # leave a stop with no move (D17).
            for key in LOOP_STOP_KEYS:
                if key not in (axis.loop_keys or ()):
                    found.append(f"the loop reports the stop {key!r}, which the {STOP_AXIS} "
                                 "axis does not declare among its loop_keys")
                elif self.stop_move(key) is None:
                    found.append(f"the loop reports the stop {key!r}, which has no row "
                                 "with a declared move")
            # A key a provider shares with the loop (R5: window-exhausted)
            # is one of the axis's keys, never a loop key, and has a row.
            for key in SHARED_STOP_KEYS:
                if key not in axis.keys:
                    found.append(f"the loop reports the stop {key!r}, which is not a key "
                                 f"of the {STOP_AXIS} axis")
                elif self.stop_move(key) is None:
                    found.append(f"the loop reports the stop {key!r}, which has no row "
                                 "with a declared move")
        return found

    def _row(self, axis: str, key: str | None) -> Move | None:
        if key is None:
            return None
        row = next((r for r in self.table.rows if r.axis == axis and r.key == key), None)
        return None if row is None else self.table.moves.get(row.move)

    def stop_move(self, stop: str | None) -> Move | None:
        """The move of the stop axis's row for `stop`; None for None (a turn
        that asks for tools) or a key with no row (the boundary passes none)."""
        return self._row(STOP_AXIS, stop)

    def apply_move(self, outcome: Any) -> Move | None:
        """The move of the apply-outcome row for a dry run's outcome; None
        when the outcome is no key of the axis."""
        return self._row(APPLY_AXIS, outcome) if isinstance(outcome, str) else None


# ---------------------------------------------------------------------------
# 6. The loop
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Delivery:
    """What the courier's `carry response` said of a delivered tarball (the
    verb's `deliver` callable builds it): whether the dry run was clean, the
    apply line, bale's parsed line and its outcome, why not, and the verb's
    twin for the transcript."""

    ok: bool
    tarball: str
    apply_line: str | None
    dry_run: dict[str, Any] | None
    outcome: Any
    reason: str | None
    twin: dict[str, Any] = field(default_factory=dict)


Deliver = Callable[[Path], Delivery]


@dataclass(frozen=True)
class LoopSettings:
    """The run's constants: the session, where twine's state is, the cap
    and the prices it is checked against, the model the spend records carry
    and the output ceiling the worst case prices, and twine's own limit on
    calls."""

    sid: str
    state_dir: Path
    cap_usd: Decimal
    model: str
    max_tokens: int
    max_turns: int = DEFAULT_MAX_TURNS
    prices_path: Path | None = None


@dataclass
class LoopResult:
    """How the loop ended — the fields cli-contract.md §18's twin carries
    that the loop knows."""

    outcome: str
    stop: str | None = None
    move: str | None = None
    actor: str | None = None
    shape: str | None = None
    reason: str | None = None
    turns: int = 0
    tool_calls: int = 0
    retries: int = 0
    block: str | None = None
    tarball: str | None = None
    apply_line: str | None = None
    dry_run: dict[str, Any] | None = None
    check: dict[str, Any] | None = None
    records: list[spend.UsageRecord] = field(default_factory=list)
    # The run's first call's usage, the five classes (R5: on a resumed run
    # this is D23's re-warm cost, the twin's `rewarm`); None until made.
    first_usage: dict[str, Any] | None = None
    # twine-run-telemetry: what `runs.jsonl` records beside the counts above —
    # the continuations asked for (`continue-turn`), the heartbeat lines
    # printed, and per tool that ran its calls, its errors and the wall
    # seconds spent around `run_tool` (the tool's own time, not the model's).
    continuations: int = 0
    heartbeats: int = 0
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)


class Loop:
    """One run of the loop. Build it with what the verb assembled and call
    `run()`; the conversation is `messages` (append-only), the outcome what
    `run()` returns. Every collaborator is an argument so the tests drive
    it with the fake adapter, a real sandbox, a fake clock and sleep."""

    def __init__(self, *, boundary: Boundary, sandbox: Sandbox, transcript: Transcript,
                 settings: LoopSettings, prompt: SystemPrompt, moves: MoveBook,
                 tools: ToolRegistry, deliver: Deliver,
                 messages: Sequence[Mapping[str, Any]],
                 window: Window | None = None, logged: int = 0,
                 sleep: Callable[[float], None] = time.sleep,
                 abort: Callable[[Path, str], bool] = kill.abort_requested,
                 progress: Callable[[str], None] = lambda line: None,
                 clock: Callable[[], float] = time.monotonic,
                 heartbeat_seconds: float = HEARTBEAT_SECONDS) -> None:
        """`window` is the run's (R5; unknown when not given); `logged` how
        many of `messages` are in the transcript's `request` lines already —
        a resumed run's rebuilt conversation (R5), so its first `request`
        line carries only what this run appended. `clock` (monotonic
        seconds) times the run for the progress lines and `heartbeat_seconds`
        is the heartbeat's interval while a tool runs (HEARTBEAT_SECONDS;
        a test shortens it)."""
        if not 0 <= logged <= len(messages):
            raise ValueError(f"logged={logged} is not between 0 and the {len(messages)} "
                             "message(s) given")
        self.boundary = boundary
        self.sandbox = sandbox
        self.transcript = transcript
        self.settings = settings
        self.prompt = prompt
        self.moves = moves
        self.tools = tools
        self.deliver = deliver
        self.messages: list[dict[str, Any]] = [copy.deepcopy(dict(m)) for m in messages]
        self.sleep = sleep
        self.abort = abort
        self.progress = progress
        self.clock = clock
        self.heartbeat_seconds = heartbeat_seconds
        self._started: float | None = None   # the clock when run() began
        self.window = window if window is not None else Window.unknown(
            "the loop was given no window")
        self.result = LoopResult(outcome=STOPPED)
        self._logged_upto = logged     # messages already in a `request` line
        self._retries_this_call = 0
        self._continuations = 0

    # --- the story ---------------------------------------------------------

    def log_line(self, kind: str, **event: Any) -> None:
        """One transcript line. A line that cannot be written is logged and
        kept in the transcript's `faults`; the run goes on (the spend stream
        and the running record are what the cap and the kill stand on)."""
        try:
            self.transcript.append(kind, **event)
        except TranscriptError:
            pass

    # --- the operator's live view -----------------------------------------

    def elapsed(self) -> float:
        """Wall seconds since `run()` began (0 before it)."""
        return 0.0 if self._started is None else self.clock() - self._started

    def cost(self) -> Decimal | None:
        """What the run has cost so far, exactly: its records priced from the
        price file; None when it cannot be priced."""
        s = self.settings
        return run_cost(self.result.records, s.prices_path or s.state_dir / spend.PRICES_NAME)

    def standing(self) -> str:
        """`$<cost>, <n>s` — what a progress line about a returned turn
        carries beside its words — and `window <used> of <size>` when the
        window's size is known."""
        text = f"{format_cost(self.cost())}, {format_seconds(self.elapsed())}"
        if self.window.known:
            text += f", window {self.window.used} of {self.window.size}"
        return text

    def summary(self) -> str:
        """The run's last progress line (cli-contract.md §18.7): `summary:`,
        then the outcome, the stop and move when there are any, the calls,
        the tool calls, the retries, the cost and the wall time."""
        r = self.result
        return summary_text(r.outcome, stop=r.stop, move=r.move, calls=r.turns,
                            tool_calls=r.tool_calls, retries=r.retries, cost=self.cost(),
                            seconds=self.elapsed())

    def run_tool_beating(self, n: int, name: str,
                         arguments: Mapping[str, Any]) -> ToolResult:
        """`run_tool`, with the operator's heartbeat: while the tool runs, a
        line every `heartbeat_seconds` naming it and the seconds elapsed,
        from a thread that writes nothing else and is stopped and joined
        before this returns (so no heartbeat lands after the tool's own
        line). The tool itself is run on the calling thread, as ever."""
        shown = tool_argument(name, arguments)
        tail = f" — {shown}" if shown else ""
        began = self.clock()
        done = threading.Event()

        def beat() -> None:
            while not done.wait(self.heartbeat_seconds):
                try:
                    self.progress(f"call {n}: tool {name}: still running, "
                                  f"{format_seconds(self.clock() - began)}{tail}")
                    self.result.heartbeats += 1
                except Exception as exc:   # a view that cannot be written is not the tool's
                    log.warning("the heartbeat line could not be written: %s", exc)
                    return

        thread = threading.Thread(target=beat, name=f"twine-heartbeat-{n}", daemon=True)
        self.progress(f"call {n}: tool {name}: running{tail}")
        thread.start()
        result: ToolResult | None = None
        try:
            result = run_tool(self.sandbox, name, arguments, registry=self.tools)
            return result
        finally:
            done.set()
            thread.join()
            self.note_tool(name, result, self.clock() - began)

    def note_tool(self, name: str, result: ToolResult | None, seconds: float) -> None:
        """One tool call into the run's `tools` tally (what `runs.jsonl`
        keeps): calls, errors and wall seconds, measured around `run_tool`.
        A call that raised (no result) counts as an error."""
        entry = self.result.tools.setdefault(name, {"calls": 0, "errors": 0, "seconds": 0.0})
        entry["calls"] += 1
        if result is None or result.is_error:
            entry["errors"] += 1
        entry["seconds"] = round(entry["seconds"] + max(0.0, seconds), 3)

    # --- ending ------------------------------------------------------------

    def end(self, outcome: str, *, stop: str | None = None, move: Move | None = None,
            reason: str | None = None, **fields: Any) -> LoopResult:
        r = self.result
        r.outcome, r.stop, r.reason = outcome, stop, reason
        r.move = None if move is None else move.name
        r.actor = None if move is None else move.actor
        for key, value in fields.items():
            setattr(r, key, value)
        log.info("run %s ends %s (stop %s, move %s): %s", self.settings.sid, outcome, stop,
                 r.move, reason)
        return r

    def stop_on(self, turn: Turn, move: Move | None, why: str) -> LoopResult:
        """End `stopped` on a turn's stop: the stop key, its move named for
        whoever performs it, and the turn's own reason beside ours."""
        reason = why + (f": {turn.reason}" if turn.reason else "")
        self.log_line("move", call=self.result.turns, stop=turn.stop,
                      move=None if move is None else move.name,
                      actor=None if move is None else move.actor, did="stopped the run")
        return self.end(STOPPED, stop=turn.stop, move=move, reason=reason)

    # --- the run -------------------------------------------------------------

    def run(self) -> LoopResult:
        """The loop until an outcome; then the conversation's tail that was
        never sent — tool results of a turn that ended the run, the final
        assistant turn of an end-turn — goes into one last `request` line
        with `sent: false`, so the lines' `appended`, joined, are the whole
        conversation a resume rebuilds (R5)."""
        self._started = self.clock()
        try:
            return self._run()
        finally:
            self.log_unsent()

    def log_unsent(self) -> None:
        if len(self.messages) > self._logged_upto:
            self.log_line("request", call=self.result.turns,
                          messages_total=len(self.messages),
                          appended=self.messages[self._logged_upto:], sent=False)
            self._logged_upto = len(self.messages)

    def _run(self) -> LoopResult:
        s = self.settings
        while True:
            # 1. The abort file, before every call (§14.3).
            if self.abort(s.state_dir, s.sid):
                return self.killed(f"before call {self.result.turns + 1}")
            # twine's own limit: stop before call max_turns + 1 (decision 4).
            if self.result.turns >= s.max_turns:
                self.log_line("move", call=self.result.turns, stop=None, move=None,
                              actor=None, did=f"stopped at --max-turns {s.max_turns}")
                return self.end(ENDED, shape=SHAPE_MAX_TURNS,
                                reason=f"twine's limit of {s.max_turns} model call(s) "
                                       f"(--max-turns) was reached; it stopped before call "
                                       f"{s.max_turns + 1} — a limit twine imposes on "
                                       "itself, not a stop key")
            n = self.result.turns + 1
            # The window (R5): used up after the last call → this one is not
            # made. Before the cap: a call the window refuses is never priced.
            if self.window.exhausted:
                return self.window_exhausted(n)
            # 2. The pre-call check (§13.8). Once a call has counted the
            # window, the input it prices is that count plus R4's estimate
            # of what was appended since (R5) — tighter than the estimate of
            # the whole request, still above the real number.
            if self.window.counted:
                appended = estimate_appended_tokens(self.messages[self._logged_upto:])
                estimate, basis = self.window.used + appended, "counted"
            else:
                estimate, basis = estimate_input_tokens(self.prompt, self.messages), "estimated"
            check = spend.check_call(s.state_dir, sid=s.sid, cap_usd=s.cap_usd,
                                     model=s.model, input_tokens=estimate,
                                     max_output_tokens=s.max_tokens,
                                     prices_path=s.prices_path)
            self.result.check = check.as_json()
            self.log_line("check", call=n, input_estimate=estimate, input_basis=basis,
                          check=check.as_json())
            if not check.admitted:
                move = self.moves.stop_move(check.stop)
                self.progress(f"call {n}: not made — {check.stop} ({check.refusal}): "
                              f"{check.reason}")
                self.log_line("move", call=n, stop=check.stop,
                              move=None if move is None else move.name,
                              actor=None if move is None else move.actor,
                              did="the call was not made")
                return self.end(check.stop or CAP_UNCHECKED, stop=check.stop, move=move,
                                reason=self.refused_reason(check))
            # 3. The call, and its usage appended before anything else.
            turn = self.call(n)
            if isinstance(turn, LoopResult):
                return turn
            # 4. The move.
            ended = self.move(turn)
            if ended is not None:
                return ended

    def refused_reason(self, check: spend.CallCheck) -> str:
        """Why the pre-call check refused: its refusal and reason — and, when
        the cap itself is already spent (the session's spend so far is at or
        past it), the sentence a resume under the same cap needs: the cap is
        cumulative per session, so the same cap refuses every call and a
        higher one is the way on."""
        reason = f"{check.refusal}: {check.reason}"
        spent, cap = check.spend_so_far_usd, check.cap_usd
        if check.stop == CAP_REACHED and spent is not None and cap is not None and spent >= cap:
            reason = (f"{check.refusal}: the cap {spend.dollars(cap)} is already spent — the "
                      f"session's spend so far is {spend.dollars(spent)}, and the cap is "
                      "cumulative per session, so the same cap refuses every call; "
                      f"raise it: {check.reason}")
        return reason

    def window_exhausted(self, n: int) -> LoopResult:
        """The counted window is used up: call `n` is not made. `stopped`,
        stop `window-exhausted`, the table's move for it (`split-goal`, the
        planner's) — the same stop the provider's own refusal maps to (R2)."""
        move = self.moves.stop_move(WINDOW_EXHAUSTED)
        reason = self.window.exhausted_reason(n)
        self.progress(f"call {n}: not made — {WINDOW_EXHAUSTED}: {self.window.used} of "
                      f"{self.window.size} input tokens in use")
        self.log_line("move", call=n, stop=WINDOW_EXHAUSTED,
                      move=None if move is None else move.name,
                      actor=None if move is None else move.actor,
                      did=f"the call was not made: the window is exhausted "
                          f"({self.window.used} of {self.window.size} input tokens in use)")
        return self.end(STOPPED, stop=WINDOW_EXHAUSTED, move=move, reason=reason)

    def killed(self, when: str) -> LoopResult:
        s = self.settings
        path = kill.abort_path(s.state_dir, s.sid)
        move = self.moves.stop_move(KILLED)
        self.progress(f"abort requested ({path}) — stopping {when}")
        self.log_line("abort", when=when, path=str(path),
                      move=None if move is None else move.name)
        return self.end(KILLED, stop=KILLED, move=move,
                        reason=f"the abort request {path} stands (observed {when}); the "
                               "loop stops and leaves the closure to `twine kill`")

    def adapter_defect(self, n: int, reason: str) -> LoopResult:
        """End `stopped` on an adapter defect: the loop's own stop key, the
        move of its row (`fix-adapter`, the operator's) and a `move` line
        after the `adapter-error` line, as every other stop gets one."""
        move = self.moves.stop_move(ADAPTER_DEFECT)
        self.log_line("move", call=n, stop=ADAPTER_DEFECT,
                      move=None if move is None else move.name,
                      actor=None if move is None else move.actor,
                      did="stopped the run")
        return self.end(STOPPED, stop=ADAPTER_DEFECT, move=move, reason=reason)

    def call(self, n: int) -> Turn | LoopResult:
        """One call through the boundary, its request and turn logged and
        its usage appended to the spend stream. A boundary refusal or an
        adapter's own failure ends the run `stopped` — an adapter defect: stop
        `adapter-defect`, the table's move `fix-adapter` (the operator's), the
        spend stream untouched (no turn, no record)."""
        s = self.settings
        appended = self.messages[self._logged_upto:]
        self.log_line("request", call=n, messages_total=len(self.messages),
                      appended=appended)
        self._logged_upto = len(self.messages)
        request = Request(tuple(copy.deepcopy(self.messages)), self.prompt.tools)
        self.progress(f"call {n}: {len(self.messages)} message(s)")
        try:
            turn = self.boundary.call(request)
        except BoundaryError as exc:
            self.result.turns = n
            self.log_line("adapter-error", call=n, error=type(exc).__name__,
                          faults=exc.faults, message=str(exc))
            return self.adapter_defect(n, f"the adapter broke the boundary's contract "
                                          f"(an adapter defect, not a model outcome): {exc}")
        except Exception as exc:   # the adapter's own fault: named, never a crash
            self.result.turns = n
            # A handled failure prints no traceback (cli-contract.md §3); it is
            # kept at DEBUG for --verbose.
            log.error("call %d: the adapter raised %s: %s", n, type(exc).__name__, exc)
            log.debug("call %d: the adapter's traceback", n, exc_info=True)
            self.log_line("adapter-error", call=n, error=type(exc).__name__,
                          message=str(exc))
            return self.adapter_defect(n, f"the adapter failed on call {n} "
                                          f"({type(exc).__name__}: {exc}); whatever the "
                                          "provider billed for it is not in the spend "
                                          "stream")
        self.result.turns = n
        try:
            extra: dict[str, Any] = {"call": n, "stop": turn.stop,
                                     "adapter": self.boundary.name}
            if turn.request_id is not None:
                extra["request_id"] = turn.request_id
            record = spend.append_record(s.state_dir, sid=s.sid, model=s.model,
                                         tokens=turn.usage.as_json(), served_sid=None,
                                         extra=extra)
        except (spend.SpendError, spend.RecordError, OSError) as exc:
            message = getattr(exc, "message", None) or str(exc)
            self.log_line("turn", call=n, turn=turn.as_json(), spend_error=message,
                          **self.kept(n, turn))
            return self.end(STOPPED, reason=f"call {n}'s usage could not be appended to "
                                            f"the spend stream ({message}); the run stops "
                                            "rather than spend what it cannot count")
        self.result.records.append(record)
        if self.result.first_usage is None:
            self.result.first_usage = turn.usage.as_json()
        self.log_line("turn", call=n, turn=turn.as_json(), **self.kept(n, turn))
        was_warned = self.window.warned
        self.log_line("window", **self.window.count(n, turn.usage))
        if self.window.warned and not was_warned:
            self.progress(f"call {n}: the window runs thin — {self.window.used} of "
                          f"{self.window.size} input tokens in use "
                          f"({self.window.percent()}%); the worker is warned from here on "
                          f"[{self.standing()}]")
        self.progress(f"call {n}: " + ("asks for " + ", ".join(c.name for c in turn.tool_calls)
                                       if turn.continues else f"stop {turn.stop}")
                      + f" — {self.standing()}")
        return turn

    def kept(self, n: int, turn: Turn) -> dict[str, Any]:
        """What the transcript's `turn` line carries beside `turn` for what the
        adapter kept (runtime-contract.md §7.6): `raw`, the path of the
        response body written to `<sid>.call-<N>.raw` — handed over only by a
        call that ended malformed-shape, so nothing is written for any other
        — and `cut_tool_input`, the tool call the output ceiling cut off
        before its input was complete. A body that cannot be written is
        named (`raw: null`, `raw_error`), never silent."""
        extra: dict[str, Any] = {}
        if turn.raw is not None:
            s = self.settings
            try:
                extra["raw"] = str(write_raw(s.state_dir, s.sid, n, turn.raw))
            except (TranscriptError, ValueError) as exc:
                log.error("call %d: %s", n, exc)
                extra["raw"] = None
                extra["raw_error"] = str(exc)
        if turn.cut_tool_call is not None:
            extra["cut_tool_input"] = dict(turn.cut_tool_call)
        return extra

    # --- the moves -----------------------------------------------------------

    def move(self, turn: Turn) -> LoopResult | None:
        """Perform the table's move for the turn: None to call again, or the
        result that ends the run."""
        if turn.continues:
            self._retries_this_call = 0
            self._continuations = 0
            return self.run_tools(turn)
        move = self.moves.stop_move(turn.stop)
        if move is None:   # the boundary passes only keys with rows: a defect
            return self.stop_on(turn, None, f"stop {turn.stop!r} has no row in the table")
        if move.name == MOVE_RETRY:
            return self.retry(turn, move)
        self._retries_this_call = 0
        if move.name == MOVE_CONTINUE:
            return self.continue_turn(turn, move)
        self._continuations = 0
        if move.name == MOVE_CLASSIFY:
            return self.classify(turn, move)
        return self.stop_on(turn, move, f"the turn stopped {turn.stop}; its move, "
                                        f"{move.name}, is the {move.actor}'s")

    def retry(self, turn: Turn, move: Move) -> LoopResult | None:
        """retry-with-backoff: the same call again after Turn.retry_after
        seconds when the provider named them, else 2, 4, 8, 16, 32; at most
        MAX_RETRIES retries of one call, then `stopped`. The wait is
        interruptible by the abort file, checked each second."""
        if self._retries_this_call >= MAX_RETRIES:
            return self.stop_on(turn, move,
                                f"the call stopped {turn.stop} on {MAX_RETRIES + 1} attempts "
                                f"({MAX_RETRIES} retries with backoff); twine retries no more")
        self._retries_this_call += 1
        self.result.retries += 1
        attempt = self._retries_this_call
        wait = (turn.retry_after if turn.retry_after is not None
                else BACKOFF_SECONDS[attempt - 1])
        self.log_line("retry", call=self.result.turns, stop=turn.stop, move=move.name,
                      attempt=attempt, wait_seconds=wait, retry_after=turn.retry_after)
        self.progress(f"call {self.result.turns}: {turn.stop} — retry {attempt} of "
                      f"{MAX_RETRIES} in {wait:g}s [{self.standing()}]")
        if self.wait(wait):
            return self.killed(f"while waiting to retry call {self.result.turns}")
        return None

    def wait(self, seconds: float) -> bool:
        """Sleep `seconds`, checking the abort file each second; True when an
        abort was requested meanwhile."""
        s = self.settings
        remaining = float(seconds)
        while remaining > 0:
            if self.abort(s.state_dir, s.sid):
                return True
            step = min(ABORT_POLL_SECONDS, remaining)
            self.sleep(step)
            remaining -= step
        return False

    def continue_turn(self, turn: Turn, move: Move) -> LoopResult | None:
        """continue-turn: the partial assistant content kept as an assistant
        turn, then a user turn asking to continue — at most
        MAX_CONTINUATIONS times in a row, then `stopped`."""
        if self._continuations >= MAX_CONTINUATIONS:
            return self.stop_on(turn, move,
                                f"the turn hit the output limit {MAX_CONTINUATIONS + 1} times "
                                f"({MAX_CONTINUATIONS} continuations); twine continues no "
                                "more")
        self._continuations += 1
        self.result.continuations += 1
        blocks = assistant_blocks(turn)
        if blocks:
            self.messages.append(assistant_message(blocks))
        self.messages.append(continue_message(blocks, self.window.noted, turn.cut_tool_call))
        self.log_line("move", call=self.result.turns, stop=turn.stop, move=move.name,
                      actor=move.actor,
                      did=f"asked the model to continue ({self._continuations} of "
                          f"{MAX_CONTINUATIONS})")
        return None

    def classify(self, turn: Turn, move: Move) -> LoopResult | None:
        """classify-final-text: the turn's text read as `twine take` reads a
        paste. A light block → `suspended`; a probe block → run through the
        probe tool, its output the next user turn (D13: the hop closed);
        anything else → `ended`, the shape reported."""
        blocks = assistant_blocks(turn)
        if blocks:
            self.messages.append(assistant_message(blocks))
        report = shapes.find_blocks(turn.text)
        shape = report.shape
        if shape == shapes.LIGHT:
            block = report.blocks[-1]
            if block.ok and block.fields.get("sid") == self.settings.sid:
                text = shapes.block_text(turn.text, block)
                self.log_line("move", call=self.result.turns, stop=turn.stop,
                              move=move.name, actor=move.actor, shape=shape,
                              did="suspended on the light block in the final text")
                return self.end(SUSPENDED, reason=None, block=text)
            why = (block.error if not block.ok
                   else f"it names session {block.fields.get('sid')!r}, not "
                        f"{self.settings.sid!r}")
            self.log_line("move", call=self.result.turns, stop=turn.stop, move=move.name,
                          actor=move.actor, shape=shape,
                          did="ended: a light block twine cannot carry")
            return self.end(ENDED, stop=turn.stop, move=move, shape=shape,
                            reason=f"the final text ends in a light block twine cannot "
                                   f"carry ({why}); the worker did not deliver")
        if shape == shapes.PROBE:
            return self.probe_hop(turn, move, shapes.block_text(turn.text, report.blocks[-1]))
        self.log_line("move", call=self.result.turns, stop=turn.stop, move=move.name,
                      actor=move.actor, shape=shape, did=f"ended on {shape}")
        if shape == shapes.PROSE:
            return self.end(ENDED, shape=shape,
                            reason="the worker ended its turn in prose without delivering "
                                   "a response; the planner reads the transcript")
        return self.end(ENDED, stop=turn.stop, move=move, shape=shape,
                        reason=f"the worker ended its turn on a {shape} block without "
                               "delivering a response; the planner reads it")

    def probe_hop(self, turn: Turn, move: Move, block: str) -> LoopResult | None:
        """The probe block in the final text run through the probe tool;
        what it returns — the paste-back, or why it did not run — becomes
        the next user turn."""
        n = self.result.turns
        call_id = f"final-text-probe-{n}"
        self.log_line("tool-call", call=n, id=call_id, name=PROBE_TOOL,
                      arguments={"block": block}, source="final-text")
        result = self.run_tool_beating(n, PROBE_TOOL, {"block": block})
        self.result.tool_calls += 1
        self.log_line("tool-result", call=n, id=call_id, result=result_for_transcript(result))
        self.progress(f"call {n}: ran the probe block in the final text "
                      f"({'error' if result.is_error else 'ok'}) — "
                      f"{tool_argument(PROBE_TOOL, {'block': block})}")
        self.messages.append(user_message(self.window.noted(result.content)))
        self.log_line("move", call=n, stop=turn.stop, move=move.name, actor=move.actor,
                      shape=shapes.PROBE, did="ran the probe and fed its output back")
        return None

    def run_tools(self, turn: Turn) -> LoopResult | None:
        """A turn that asks for tools: each call run in order through
        run_tool; its result becomes a tool_result block, `is_error` carried
        (return-tool-error: a failed tool goes back as a result). `escalate`
        suspends and `deliver` hands the tarball to the courier — nothing
        after either runs this turn."""
        n = self.result.turns
        self.messages.append(assistant_message(assistant_blocks(turn)))
        results: list[tuple[str, str, bool]] = []
        ending: LoopResult | None = None
        noted = self.window.noted     # a warned run's results end with the warning
        for call in turn.tool_calls:
            if ending is not None:
                results.append((call.id, noted(NOT_RUN_ENDED.format(why=ending.outcome)),
                                True))
                continue
            arguments = dict(call.arguments)
            self.log_line("tool-call", call=n, id=call.id, name=call.name,
                          arguments=arguments)
            result = self.run_tool_beating(n, call.name, arguments)
            self.result.tool_calls += 1
            self.log_line("tool-result", call=n, id=call.id,
                          result=result_for_transcript(result))
            shown = tool_argument(call.name, arguments)
            self.progress(f"call {n}: tool {call.name}: "
                          f"{'error' if result.is_error else 'ok'}"
                          + (f" — {shown}" if shown else ""))
            results.append((call.id, noted(result.content), result.is_error))
            if result.is_error:
                tool_move = self.moves.table.moves.get(MOVE_TOOL_ERROR)
                self.log_line("move", call=n, stop=None, move=MOVE_TOOL_ERROR,
                              actor=None if tool_move is None else tool_move.actor,
                              did=f"returned {call.name}'s error to the model as its "
                                  "result")
                continue
            if result.fields.get("suspend") is True and result.fields.get("path"):
                # escalate's clarification form (R5): a response tarball to
                # carry, then suspend — `deliver` and suspend in one.
                ending = self.clarified(n, result)
            elif result.fields.get("suspend") is True:
                self.log_line("move", call=n, stop=None, move=None, actor=None,
                              did=f"suspended on {call.name}")
                ending = self.end(SUSPENDED, block=result.content)
            elif result.fields.get("delivered") is True:
                ending = self.delivered(n, result)
        self.messages.append(tool_result_message(results))
        if ending is None:
            self.log_line("move", call=n, stop=None, move=None, actor=None,
                          did=f"ran {len(results)} tool call(s); the results go back to "
                              "the model")
        # On an ending the results are logged by run() (`sent: false`), so
        # the transcript holds the whole conversation for a resume (R5).
        return ending

    def clarified(self, n: int, result: ToolResult) -> LoopResult:
        """escalate wrote a clarification response tarball (R5): hand it to
        the courier's `carry response` as a delivery is handed (the dry run),
        then end `suspended` with the tarball, the apply line and the dry run
        — the operator applies it, bale suspends the session and prints the
        planner's paste block, and `twine resume` continues on the answer. The
        twin's `block` is the exchange paste block the tool rendered
        (runtime-contract.md §6.6). A dry run that is not clean ends the run
        `stopped`, as a bad delivery does."""
        path = (self.sandbox.home / str(result.fields.get("path"))).resolve()
        self.progress(f"call {n}: escalate wrote the clarification response {path}; "
                      "checking it with bale (dry run)")
        delivery = self.deliver(path)
        move = self.moves.apply_move(delivery.outcome)
        self.log_line("move", call=n, stop=None, move=None if move is None else move.name,
                      actor=None if move is None else move.actor,
                      did="carried the clarification response to `carry response`"
                          + ("; suspended on it" if delivery.ok else ""),
                      carry_response=delivery.twin)
        if delivery.ok:
            return self.end(SUSPENDED, move=move, tarball=delivery.tarball,
                            apply_line=delivery.apply_line, dry_run=delivery.dry_run,
                            block=result.fields.get("block"))
        return self.end(STOPPED, move=move, tarball=delivery.tarball,
                        dry_run=delivery.dry_run,
                        reason=f"the clarification response did not pass the dry run "
                               f"(outcome {delivery.outcome!r}): {delivery.reason}")

    def delivered(self, n: int, result: ToolResult) -> LoopResult:
        """`deliver` named a tarball: hand it to the courier's `carry
        response` (`bale apply --dry-run --json`); `delivered` with the apply
        line when the dry run is clean, else `stopped` with its outcome. The
        apply-outcome row names the move — the operator's or the planner's;
        the loop reports it."""
        path = (self.sandbox.home / str(result.fields.get("path"))).resolve()
        self.progress(f"call {n}: delivered {path}; checking it with bale (dry run)")
        delivery = self.deliver(path)
        move = self.moves.apply_move(delivery.outcome)
        self.log_line("move", call=n, stop=None, move=None if move is None else move.name,
                      actor=None if move is None else move.actor,
                      did="carried the delivered tarball to `carry response`",
                      carry_response=delivery.twin)
        if delivery.ok:
            return self.end(DELIVERED, move=move, tarball=delivery.tarball,
                            apply_line=delivery.apply_line, dry_run=delivery.dry_run)
        return self.end(STOPPED, move=move, tarball=delivery.tarball,
                        dry_run=delivery.dry_run,
                        reason=f"the delivered tarball did not pass the dry run "
                               f"(outcome {delivery.outcome!r}): {delivery.reason}")


def usage_sum(records: Sequence[spend.UsageRecord]) -> dict[str, int | None]:
    """The five classes summed over the run's records — `thinking` the sum
    of the non-null values, null only when every record had null (0 with no
    records), as `twine spend totals` sums a session (§13.6)."""
    total = {name: 0 for name in spend.TOKEN_CLASSES}
    thinking_seen = False
    for record in records:
        for name in spend.TOKEN_CLASSES:
            value = getattr(record.tokens, name)
            if value is None:
                continue
            if name == "thinking":
                thinking_seen = True
            total[name] += value
    if records and not thinking_seen:
        total["thinking"] = None
    return total


def run_cost(records: Sequence[spend.UsageRecord], prices_path: Path) -> Decimal | None:
    """The run's own cost, exactly: its records priced from the price file;
    None when the file cannot be read or a record's model has no row. Zero
    with no records."""
    if not records:
        return Decimal(0)
    try:
        prices = spend.load_prices(prices_path)
    except spend.SpendError as exc:
        log.info("run cost not priced: %s", exc.message)
        return None
    total = Decimal(0)
    for record in records:
        price = prices.models.get(record.model)
        if price is None:
            return None
        total += spend.record_cost(record, price)
    return total


__all__ = ["ADAPTER_DEFECT", "CAP_REACHED", "CAP_UNCHECKED", "DELIVERED", "Delivery", "ENDED",
           "KILLED", "Loop", "LoopError", "LoopResult", "LoopSettings", "MoveBook", "OUTCOMES",
           "REFUSED", "STOPPED", "SUSPENDED", "SystemPrompt", "WINDOW_EXHAUSTED",
           "adapter_class", "estimate_appended_tokens", "estimate_input_tokens", "format_cost",
           "format_seconds", "run_cost", "summary_text", "system_prompt", "tool_argument",
           "unpack_request", "usage_sum"]

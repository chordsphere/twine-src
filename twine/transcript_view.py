"""Reading a transcript as a story (twine-run-telemetry; cli-contract.md §21):
what `twine transcript SID` renders — one line per transcript line, `<seq>
<kind> [call <n>] <summary>`, the summary per kind — so a run's story is read
without a hand-written probe.

    read_transcript(path) -> TranscriptFile
        every physical line, numbered: the lines that are JSON objects, and a
        fault (named by its number) for every one that is not — blank, torn
        (no LF), not UTF-8, not JSON, not an object. A transcript is a log,
        read for its story: a bad line is reported, never fatal, and never
        skipped silently (`twine.transcript.read_lines`, which the resume reads
        by, skips and logs).

    story_entry(number, obj) -> {"seq", "kind", "call", "summary"}
    story_line(entry) -> the human line

Read-only: nothing here writes, creates or spawns anything. The summaries
use the loop's own spellings (`twine.runtime.loop.tool_argument`, the same
cut at 80 characters the progress lines use).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from twine.runtime import loop as runloop

# Where an argument summary is cut (the progress lines' own limit).
ARGUMENT_CHARS = runloop.PROGRESS_ARGUMENT_CHARS


@dataclass
class TranscriptFile:
    """A transcript as read. `present` is False for an absent file;
    `unreadable` says why an existing one could not be read. `entries` are
    (line number, object) for the lines that are objects."""

    path: Path
    present: bool = False
    lines: int = 0
    entries: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    faults: list[str] = field(default_factory=list)
    unreadable: str | None = None


def read_transcript(path: Path) -> TranscriptFile:
    result = TranscriptFile(Path(path))
    try:
        data = result.path.read_bytes()
    except FileNotFoundError:
        return result
    except OSError as exc:
        result.present = True
        result.unreadable = f"{result.path} cannot be read: {exc.strerror or exc}"
        return result
    result.present = True
    pieces = data.split(b"\n")
    torn = pieces[-1] != b""
    numbered = list(enumerate(pieces[:-1], 1))
    if torn:
        numbered.append((len(numbered) + 1, pieces[-1]))
    result.lines = len(numbered)
    for number, raw in numbered:
        if torn and number == len(numbered):
            result.faults.append(f"line {number}: not newline-terminated (a torn write?)")
            continue
        if not raw.strip():
            result.faults.append(f"line {number}: blank")
            continue
        try:
            obj = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            result.faults.append(f"line {number}: not UTF-8 ({exc.reason} at byte {exc.start})")
            continue
        except (ValueError, RecursionError) as exc:
            result.faults.append(f"line {number}: not JSON ({exc})")
            continue
        if not isinstance(obj, dict):
            result.faults.append(f"line {number}: not a JSON object")
            continue
        result.entries.append((number, obj))
    return result


# ---------------------------------------------------------------------------
# The summaries
# ---------------------------------------------------------------------------


def _text(value: Any) -> str:
    return "null" if value is None else str(value)


def _map(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def summary_of(kind: str, obj: Mapping[str, Any]) -> str:
    """The one-line summary of a transcript line of `kind`; empty for a kind
    twine does not know (the story still lists it)."""
    if kind == "run-start":
        size = _map(obj.get("window")).get("size")
        resumed = obj.get("resumed_from")
        return (f"{_text(obj.get('adapter'))}, model {_text(obj.get('model'))}, window "
                f"{'unknown' if size is None else size}, "
                + ("not resumed" if resumed is None else f"resumed from line {resumed}"))
    if kind == "check":
        check = _map(obj.get("check"))
        verdict = "admitted" if check.get("admitted") is True else (
            f"refused ({_text(check.get('stop'))})")
        return (f"estimate {_text(obj.get('input_estimate'))} "
                f"({_text(obj.get('input_basis'))}), {verdict}")
    if kind == "request":
        appended = obj.get("appended")
        count = len(appended) if isinstance(appended, list) else 0
        return (f"{_text(obj.get('messages_total'))} messages, {count} appended"
                + (", sent: false" if obj.get("sent") is False else ""))
    if kind == "turn":
        turn = _map(obj.get("turn"))
        calls = turn.get("tool_calls")
        names = [_text(_map(c).get("name")) for c in calls] if isinstance(calls, list) else []
        return "asks for " + ", ".join(names) if names else f"stop {_text(turn.get('stop'))}"
    if kind == "window":
        text = (f"{_text(obj.get('used'))} of "
                f"{'unknown' if obj.get('size') is None else obj.get('size')}")
        return text + (" (warned)" if obj.get("warned") is True else "")
    if kind == "tool-call":
        name = _text(obj.get("name"))
        shown = runloop.tool_argument(name, _map(obj.get("arguments")), ARGUMENT_CHARS)
        return f"{name} {shown}".rstrip()
    if kind == "tool-result":
        result = _map(obj.get("result"))
        content = result.get("content")
        return (("error" if result.get("is_error") is True else "ok")
                + f", {len(content) if isinstance(content, str) else 0} characters")
    if kind == "move":
        move = obj.get("move")
        return (f"{move}: " if move else "") + _text(obj.get("did"))
    if kind == "retry":
        return (f"{_text(obj.get('stop'))}, attempt {_text(obj.get('attempt'))}, "
                f"wait {_text(obj.get('wait_seconds'))}s")
    if kind == "abort":
        return _text(obj.get("path"))
    if kind == "adapter-error":
        message = obj.get("message")
        return _text(obj.get("error")) + (f": {message}" if message else "")
    if kind == "run-end":
        if obj.get("internal_error") is True:
            return "internal error"
        twin = _map(obj.get("twin"))
        parts = [_text(twin.get("outcome"))]
        if twin.get("stop") is not None:
            parts.append(f"stop {twin['stop']}")
        if twin.get("move") is not None:
            parts.append(f"move {twin['move']}")
        return ", ".join(parts)
    return ""


def story_entry(number: int, obj: Mapping[str, Any]) -> dict[str, Any]:
    """`{"seq", "kind", "call", "summary"}` for one transcript line. `seq` is
    the line's own, or its line number when it carries none; `call` null where
    the line has none."""
    seq = obj.get("seq")
    call = obj.get("call")
    kind = obj.get("kind")
    kind = kind if isinstance(kind, str) else "?"
    return {"seq": seq if type(seq) is int else number, "kind": kind,
            "call": call if type(call) is int else None,
            "summary": summary_of(kind, obj)}


def story_line(entry: Mapping[str, Any]) -> str:
    """The human line: `<seq> <kind> [call <n>] <summary>` — the bracketed
    part only on a line that has a call — a single line whatever the summary
    held."""
    parts = [str(entry["seq"]), entry["kind"]]
    if entry["call"] is not None:
        parts.append(f"[call {entry['call']}]")
    if entry["summary"]:
        parts.append(entry["summary"])
    return " ".join(" ".join(parts).split())


__all__ = ["ARGUMENT_CHARS", "TranscriptFile", "read_transcript", "story_entry",
           "story_line", "summary_of"]

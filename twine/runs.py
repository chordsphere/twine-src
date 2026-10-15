"""`runs.jsonl` — one line per run (twine-run-telemetry; cli-contract.md §20):
the run twin's essentials plus what the twin does not carry — durations by
tool, the events the stderr warnings name, the desk, wall time — so a run's
cost, outcome and shape can be read without opening its transcript, and
`twine stats` can aggregate them.

    <state-dir>/runs.jsonl

Written like the spend stream (twine/spend.py `append_record`): one
`os.write` of one LF-terminated line to a file opened O_APPEND, created
0600, then fsync; never rewritten, never read by the loop. **One line per
run that has a sid**, on every outcome — the rule PLANNER.md §17 states for
cost records (a record set that covers only some exits is a numerator-only
dataset). A stream whose last line is torn (no LF) is appended to all the
same, an LF first ending the torn line, which `read_runs` then reports as a
fault, as `twine.transcript` does.

The record is pinned whole — `KEYS`, in this order, `record_version` 1 — and
`record_faults` judges a line against it. A line that is not a record is a
fault, named by its number, never skipped silently and never fatal: the
reader goes on.

This module writes the one line and reads and aggregates them; the verb
that builds a line from a finished run is `twine.commands.run`'s
(`RunReport.run_record`). Nothing here reads a key, the process environment
or the spend stream, and nothing spawns anything.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from twine.kill import FILE_MODE

log = logging.getLogger("twine.runs")

RUNS_NAME = "runs.jsonl"
RECORD_VERSION = 1
COMMANDS = ("run", "resume")
# The eight outcomes (twine.runtime.loop.OUTCOMES, spelled again so this
# module imports nothing of the loop; a test holds the two together).
OUTCOMES = ("delivered", "suspended", "ended", "stopped", "killed", "cap-reached",
            "cap-unchecked", "refused")
USAGE_KEYS = ("input", "output", "thinking", "cache_read", "cache_write")
WINDOW_KEYS = ("size", "used", "warned", "source")
TOOL_KEYS = ("calls", "errors", "seconds")
EVENT_KEYS = ("window_warned", "continuations", "retries", "heartbeats",
              "transcript_faults", "inflight_error", "group_survivors")
INFLIGHT_STATES = ("removed", "kept")
# The record's keys, in the order a line carries them.
KEYS = tuple("""record_version sid command desk started_at ended_at wall_seconds outcome stop
move actor shape reason turns tool_calls retries continuations usage cost_usd cap_usd adapter
model window resumed_from rewarm tools events transcript sandbox inflight cost_file
apply""".split())
# The reserved last key (null until the T12 session fills it with the apply
# outcome). Taken from KEYS rather than spelled: the one place twine's code
# may hold the bare word as an argv token is `twine.bale.dry_run_argv`
# (tests/test_carry_bale.py guards it), and this is a record key, not one.
APPLY = KEYS[-1]
MAX_REPORTED_FAULTS = 50


class RunsError(OSError):
    """A line that could not be written; the message names the path."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


def runs_path(state_dir: Path) -> Path:
    return Path(state_dir) / RUNS_NAME


def utc_stamp(moment: datetime | None = None) -> str:
    """UTC ISO 8601 with the offset, seconds: `2026-10-15T22:19:22+00:00`."""
    moment = moment or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def _is_int(value: Any) -> bool:
    return type(value) is int


def _is_number(value: Any) -> bool:
    return type(value) in (int, float) and value == value and abs(value) != float("inf")


def _is_str_or_null(value: Any) -> bool:
    return value is None or isinstance(value, str)


def _stamp_fault(name: str, value: Any) -> str | None:
    if not isinstance(value, str):
        return f"{name} is not a string"
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return f"{name} {value!r} is not an ISO 8601 time"
    if moment.tzinfo is None:
        return f"{name} {value!r} has no UTC offset"
    return None


def record_faults(obj: Any) -> list[str]:
    """Why `obj` is not a run record: every fault, in one pass; empty when it
    is one. Judges the keys, their order and the types the pinned format
    names — not whether the numbers are plausible."""
    if not isinstance(obj, dict):
        return ["not a JSON object"]
    faults: list[str] = []
    if tuple(obj) != KEYS:
        missing = [k for k in KEYS if k not in obj]
        extra = [k for k in obj if k not in KEYS]
        if missing:
            faults.append("missing key(s) " + ", ".join(missing))
        if extra:
            faults.append("unknown key(s) " + ", ".join(extra))
        if not missing and not extra:
            faults.append("the keys are not in the record's order")
        if missing:
            return faults
    if obj.get("record_version") != RECORD_VERSION or not _is_int(obj.get("record_version")):
        faults.append(f"record_version {obj.get('record_version')!r} is not {RECORD_VERSION}")
    if not isinstance(obj.get("sid"), str) or not obj.get("sid"):
        faults.append("sid is not a non-empty string")
    if obj.get("command") not in COMMANDS:
        faults.append(f"command {obj.get('command')!r} is not one of {', '.join(COMMANDS)}")
    if obj.get("desk") is not None and not _is_int(obj.get("desk")):
        faults.append("desk is not an integer or null")
    for name in ("started_at", "ended_at"):
        fault = _stamp_fault(name, obj.get(name))
        if fault:
            faults.append(fault)
    if not _is_number(obj.get("wall_seconds")):
        faults.append("wall_seconds is not a number")
    if obj.get("outcome") not in OUTCOMES:
        faults.append(f"outcome {obj.get('outcome')!r} is not one of the eight")
    for name in ("stop", "move", "actor", "shape", "reason", "adapter", "model",
                 "transcript", "sandbox", "cost_file"):
        if not _is_str_or_null(obj.get(name)):
            faults.append(f"{name} is not a string or null")
    for name in ("turns", "tool_calls", "retries", "continuations"):
        if not _is_int(obj.get(name)):
            faults.append(f"{name} is not an integer")
    usage = obj.get("usage")
    if not isinstance(usage, dict) or tuple(usage) != USAGE_KEYS:
        faults.append("usage is not the five token classes")
    for name in ("cost_usd", "cap_usd"):
        if obj.get(name) is not None and not _is_number(obj.get(name)):
            faults.append(f"{name} is not a number or null")
    window = obj.get("window")
    if window is not None and (not isinstance(window, dict) or tuple(window) != WINDOW_KEYS):
        faults.append("window is not null or {size, used, warned, source}")
    if obj.get("resumed_from") is not None and not _is_int(obj.get("resumed_from")):
        faults.append("resumed_from is not an integer or null")
    if obj.get("rewarm") is not None and not isinstance(obj.get("rewarm"), dict):
        faults.append("rewarm is not an object or null")
    faults += _tools_faults(obj.get("tools"))
    events = obj.get("events")
    if not isinstance(events, dict) or tuple(events) != EVENT_KEYS:
        faults.append("events is not the seven counts")
    if obj.get("inflight") is not None and obj.get("inflight") not in INFLIGHT_STATES:
        faults.append("inflight is not removed, kept or null")
    if obj.get(APPLY) is not None:
        faults.append(f"{APPLY} is reserved and must be null")
    return faults


def _tools_faults(tools: Any) -> list[str]:
    if not isinstance(tools, dict):
        return ["tools is not an object"]
    faults = []
    for name, entry in tools.items():
        if (not isinstance(entry, dict) or tuple(entry) != TOOL_KEYS
                or not _is_int(entry["calls"]) or not _is_int(entry["errors"])
                or not _is_number(entry["seconds"])):
            faults.append(f"tools[{name!r}] is not {{calls, errors, seconds}}")
    return faults


def append_run(state_dir: Path, record: Mapping[str, Any]) -> Path:
    """Append one record to `<state_dir>/runs.jsonl` — validated first by
    `record_faults`, so a malformed record raises ValueError and the file is
    untouched — and return the path. The directory is made 0700 when absent
    (the caller has a sid, so a state directory is in use); the file is
    created 0600. Raises RunsError naming the path when the write fails."""
    faults = record_faults(dict(record))
    if faults:
        raise ValueError("not a run record: " + "; ".join(faults))
    line = json.dumps(dict(record), ensure_ascii=False) + "\n"
    if "\n" in line[:-1]:
        raise ValueError("the record rendered as more than one line")
    data = line.encode("utf-8")
    path = runs_path(state_dir)
    try:
        Path(state_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
        data = (b"\n" if _ends_torn(path) else b"") + data
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, FILE_MODE)
        try:
            written = 0
            while written < len(data):
                written += os.write(fd, data[written:])
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise RunsError(f"cannot append to {path}: {exc.strerror or exc}") from exc
    log.info("runs: appended a line for %s (%s, %s) to %s", record["sid"], record["command"],
             record["outcome"], path)
    return path


def _ends_torn(path: Path) -> bool:
    """Whether `path`'s last byte exists and is not LF (a torn write)."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            if fh.tell() == 0:
                return False
            fh.seek(-1, os.SEEK_END)
            return fh.read(1) != b"\n"
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


@dataclass
class RunsFile:
    """`runs.jsonl` as read: the records (with their line numbers), the lines
    that are not records, and why the file could not be read. `present` is
    False for an absent file (an absent file is an empty one)."""

    path: Path
    present: bool = False
    lines: int = 0
    records: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    faults: list[str] = field(default_factory=list)
    unreadable: str | None = None


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate key {key!r}")
        obj[key] = value
    return obj


def read_runs(path: Path) -> RunsFile:
    """Read `runs.jsonl`. Never raises for what is in the file: a line that
    is blank, torn, not UTF-8, not JSON or not a record is a fault naming
    its line number, and the reading goes on. Writes nothing."""
    result = RunsFile(Path(path))
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
    complete = pieces[:-1]      # the last piece is empty, or the torn line
    numbered = list(enumerate(complete, 1))
    if torn:
        numbered.append((len(complete) + 1, pieces[-1]))
    result.lines = len(numbered)
    for number, raw in numbered:
        why = None
        obj: Any = None
        if torn and number == len(numbered):
            why = "not newline-terminated (a torn write?)"
        elif not raw.strip():
            why = "blank"
        else:
            try:
                obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
            except UnicodeDecodeError as exc:
                why = f"not UTF-8 ({exc.reason} at byte {exc.start})"
            except (ValueError, RecursionError) as exc:
                why = f"not JSON ({exc})"
            else:
                faults = record_faults(obj)
                if faults:
                    why = "not a run record: " + "; ".join(faults)
        if why is None:
            result.records.append((number, obj))
        else:
            result.faults.append(f"line {number}: {why}")
    return result


# ---------------------------------------------------------------------------
# Aggregation (`twine stats`)
# ---------------------------------------------------------------------------


def parse_since(text: str) -> date:
    """`--since`'s date: ISO `YYYY-MM-DD`. Raises ValueError saying so."""
    try:
        if len(text) != 10:
            raise ValueError
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"--since {text!r} is not a date (ISO YYYY-MM-DD)") from None


def started_on(record: Mapping[str, Any]) -> date:
    """The UTC date the record's `started_at` names."""
    return datetime.fromisoformat(record["started_at"]).astimezone(timezone.utc).date()


def _round(value: Decimal | float, places: int = 6) -> float:
    return round(float(value), places)


def aggregate(file: RunsFile, *, since: date | None = None,
              sid: str | None = None) -> dict[str, Any]:
    """The `twine stats` keys after `command` and `ok`, from the records that
    are members (`started_at` on or after `since`, and `sid`, when given —
    both together intersect). `runs` counts the members; `faults` names every
    line of the file that is not a record, members or not (a bad line has no
    sid to filter by)."""
    members = [r for _, r in file.records
               if (since is None or started_on(r) >= since)
               and (sid is None or r["sid"] == sid)]
    by_outcome = {name: 0 for name in OUTCOMES}
    by_command = {name: 0 for name in COMMANDS}
    by_tool: dict[str, dict[str, Any]] = {}
    cost = Decimal(0)
    unpriced = 0
    wall = Decimal(0)
    delivered: list[dict[str, Any]] = []
    for r in members:
        by_outcome[r["outcome"]] += 1
        by_command[r["command"]] += 1
        wall += Decimal(str(r["wall_seconds"]))
        if r["cost_usd"] is None:
            unpriced += 1
        else:
            cost += Decimal(str(r["cost_usd"]))
        for name, entry in r["tools"].items():
            row = by_tool.setdefault(name, {"calls": 0, "errors": 0, "seconds": Decimal(0)})
            row["calls"] += entry["calls"]
            row["errors"] += entry["errors"]
            row["seconds"] += Decimal(str(entry["seconds"]))
        if r["outcome"] == "delivered":
            delivered.append(r)
    priced = [Decimal(str(r["cost_usd"])) for r in delivered if r["cost_usd"] is not None]
    return {
        "runs": len(members),
        "faults": list(file.faults),
        "sessions": len({r["sid"] for r in members}),
        "by_outcome": by_outcome,
        "by_command": by_command,
        "turns": sum(r["turns"] for r in members),
        "tool_calls": sum(r["tool_calls"] for r in members),
        "retries": sum(r["retries"] for r in members),
        "cost_usd": _round(cost),
        "unpriced_runs": unpriced,
        "wall_seconds": _round(wall, 3),
        "by_tool": {name: {"calls": row["calls"], "errors": row["errors"],
                           "seconds": _round(row["seconds"], 3)}
                    for name, row in sorted(by_tool.items())},
        "delivered": {
            "runs": len(delivered),
            "mean_cost_usd": _round(sum(priced) / len(priced)) if priced else None,
            "mean_turns": (_round(Decimal(sum(r["turns"] for r in delivered)) / len(delivered))
                           if delivered else None),
            "mean_wall_seconds": (_round(sum(Decimal(str(r["wall_seconds"]))
                                             for r in delivered) / len(delivered), 3)
                                  if delivered else None),
        },
    }


__all__ = ["COMMANDS", "EVENT_KEYS", "KEYS", "OUTCOMES", "RECORD_VERSION", "RUNS_NAME",
           "RunsError", "RunsFile", "aggregate", "append_run", "parse_since", "read_runs",
           "record_faults", "runs_path", "started_on", "utc_stamp"]

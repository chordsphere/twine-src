"""The two verbs that read what a run left (twine-run-telemetry;
cli-contract.md §20, §21):

    twine stats [--since DATE] [--sid SID] [--state-dir DIR] [--json]
    twine transcript SID [--from SEQ] [--state-dir DIR] [--json]

`twine stats` aggregates `<state-dir>/runs.jsonl` (twine/runs.py) — the shape
of `bale stats`: read-only, and an absent or empty file is an honest empty
report, not an error. `twine transcript` renders `<state-dir>/transcripts/
<sid>.jsonl` as a story (twine/transcript_view.py). **Neither writes
anything**, not even a directory: both resolve the state directory as every
verb does and only read from it. No network, no subprocess, no key.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from twine import runs, spend, transcript, transcript_view
from twine.cli import Context
from twine.kill import is_sid
from twine.registry import Argument, Command, Result

log = logging.getLogger("twine.telemetry")


def _state_dir_argument() -> Argument:
    return Argument(("--state-dir",), {
        "metavar": "DIR", "default": None,
        "help": "twine's state directory; else $TWINE_STATE_DIR, else "
                "${XDG_STATE_HOME:-$HOME/.local/state}/twine"})


# ---------------------------------------------------------------------------
# twine stats
# ---------------------------------------------------------------------------

STATS_AFTER_RUNS = ("runs", "faults", "sessions", "by_outcome", "by_command", "turns",
                    "tool_calls", "retries", "cost_usd", "unpriced_runs", "wall_seconds",
                    "by_tool", "delivered")


def stats_payload(path: str | None, report: dict[str, Any], *, since: str | None,
                  sid: str | None, reason: str | None) -> dict[str, Any]:
    """The twin after `command` and `ok`, in the contract's order (§20.2)."""
    return {"path": path, **{key: report[key] for key in STATS_AFTER_RUNS},
            "since": since, "sid": sid, "reason": reason}


def cmd_stats(ctx: Context, args: argparse.Namespace) -> Result:
    empty = runs.aggregate(runs.RunsFile(Path()))
    problem: str | None = None
    since = None
    if args.since is not None:
        try:
            since = runs.parse_since(args.since)
        except ValueError as exc:
            problem = str(exc)
    path: Path | None = None
    report = empty
    if problem is None:
        try:
            where = spend.resolve_state_dir(args.state_dir, ctx.env)
        except spend.SpendError as exc:
            problem = exc.message
        else:
            path = runs.runs_path(where.path)
            file = runs.read_runs(path)
            if file.unreadable is not None:
                problem = file.unreadable
            else:
                report = runs.aggregate(file, since=since, sid=args.sid)
    if problem is not None:
        ctx.info(f"stats: {problem}")
        payload = stats_payload(None if path is None else str(path), empty,
                                since=args.since, sid=args.sid, reason=problem)
        return Result(False, payload, [f"stats: not ok — {problem}"])
    for fault in report["faults"][:runs.MAX_REPORTED_FAULTS]:
        ctx.info(f"{path}: {fault}")
    payload = stats_payload(str(path), report, since=args.since, sid=args.sid, reason=None)
    return Result(True, payload, stats_lines(payload))


def _number(value: Any) -> str:
    return "null" if value is None else str(value)


def stats_lines(payload: dict[str, Any]) -> list[str]:
    """Human mode: one line per key, in the twin's order; `faults`, `by_*` and
    `delivered` as indented lines under their key."""
    lines = [f"path: {_number(payload['path'])}", f"runs: {payload['runs']}",
             f"faults: {len(payload['faults'])}"]
    lines += [f"  {fault}" for fault in payload["faults"]]
    lines.append(f"sessions: {payload['sessions']}")
    lines.append("by_outcome:")
    lines += [f"  {name}: {count}" for name, count in payload["by_outcome"].items()]
    lines.append("by_command:")
    lines += [f"  {name}: {count}" for name, count in payload["by_command"].items()]
    for key in ("turns", "tool_calls", "retries", "cost_usd", "unpriced_runs",
                "wall_seconds"):
        lines.append(f"{key}: {_number(payload[key])}")
    lines.append("by_tool:")
    lines += [f"  {name}: {row['calls']} calls, {row['errors']} errors, {row['seconds']}s"
              for name, row in payload["by_tool"].items()]
    delivered = payload["delivered"]
    lines.append("delivered:")
    lines += [f"  {key}: {_number(value)}" for key, value in delivered.items()]
    lines.append(f"since: {_number(payload['since'])}")
    lines.append(f"sid: {_number(payload['sid'])}")
    lines.append(f"reason: {_number(payload['reason'])}")
    return lines


# ---------------------------------------------------------------------------
# twine transcript
# ---------------------------------------------------------------------------


def transcript_payload(sid: str, path: str | None, *, lines: int = 0, run_starts: int = 0,
                       faults: list[str] | None = None,
                       story: list[dict[str, Any]] | None = None,
                       reason: str | None = None) -> dict[str, Any]:
    return {"sid": sid, "path": path, "lines": lines, "runs": run_starts,
            "faults": faults or [], "story": story or [], "reason": reason}


def cmd_transcript(ctx: Context, args: argparse.Namespace) -> Result:
    sid = args.sid
    if not is_sid(sid):
        reason = f"{sid!r} is not a session id twine names a transcript by"
        ctx.info(f"transcript: {reason}")
        return Result(False, transcript_payload(sid, None, reason=reason),
                      [f"transcript {sid}: not ok — {reason}"])
    try:
        where = spend.resolve_state_dir(args.state_dir, ctx.env)
    except spend.SpendError as exc:
        ctx.info(f"transcript: {exc.message}")
        return Result(False, transcript_payload(sid, None, reason=exc.message),
                      [f"transcript {sid}: not ok — {exc.message}"])
    path = transcript.transcript_path(where.path, sid)
    file = transcript_view.read_transcript(path)
    problem = file.unreadable
    if problem is None and not file.present:
        problem = f"{path} does not exist: twine kept no transcript for {sid} in this state directory"
    if problem is not None:
        ctx.info(f"transcript: {problem}")
        return Result(False, transcript_payload(sid, str(path), reason=problem),
                      [f"transcript {sid}: not ok — {problem}"])
    for fault in file.faults:
        ctx.info(f"{path}: {fault}")
    story = [transcript_view.story_entry(number, obj) for number, obj in file.entries]
    if args.from_seq is not None:
        story = [entry for entry in story if entry["seq"] >= args.from_seq]
    run_starts = sum(1 for _, obj in file.entries if obj.get("kind") == "run-start")
    payload = transcript_payload(sid, str(path), lines=file.lines, run_starts=run_starts,
                                 faults=file.faults, story=story)
    human = [transcript_view.story_line(entry) for entry in story]
    return Result(True, payload, human)


COMMANDS = (
    Command(
        name="stats",
        summary="aggregate runs.jsonl: runs, outcomes, tools, cost — read-only",
        handler=cmd_stats,
        arguments=(
            Argument(("--since",), {
                "metavar": "DATE", "default": None,
                "help": "only runs that started on or after DATE (ISO YYYY-MM-DD, UTC, "
                        "inclusive)"}),
            Argument(("--sid",), {
                "metavar": "SID", "default": None,
                "help": "only this session's runs; with --since, both must hold"}),
            _state_dir_argument()),
        description="Aggregate <state-dir>/runs.jsonl — the one line `twine run` and "
                    "`twine resume` write per run, on every outcome. Reads only: it "
                    "writes and creates nothing, and an absent or empty file is an "
                    "honest empty report (exit 0). A line that is not a run record is "
                    "named in `faults`, by line number, and the reading goes on."),
    Command(
        name="transcript",
        summary="read a run's story from its transcript — read-only",
        handler=cmd_transcript,
        arguments=(
            Argument(("sid",), {"metavar": "SID", "help": "the session whose transcript to read"}),
            Argument(("--from",), {
                "metavar": "SEQ", "type": int, "default": None, "dest": "from_seq",
                "help": "start at the line whose seq is SEQ"}),
            _state_dir_argument()),
        description="Render <state-dir>/transcripts/<sid>.jsonl, one line per transcript "
                    "line: `<seq> <kind> [call <n>] <summary>`. Reads only. A torn last "
                    "line is reported (in `faults`), not refused; a missing transcript is "
                    "not ok."),
)

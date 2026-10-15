"""The transcript (Arc 2 R4; TQ-1, answered 2026-10-01): the story of a
worker session `twine run` hosted, one JSON object per line, append-only.

    <state-dir>/transcripts/<sid>.jsonl

TQ-1 as answered: transcripts are kept **durably, append-only**, as logs and
not as records of intent; deleting one loses an effort option (T11's "ask an
old worker", R8) and nothing of record (N4). The sid's `spend.jsonl` lines
are the money; the transcript is the story.

Each line is one object, its first three keys `at` (UTC, RFC 3339, seconds),
`seq` (1-based, continuing across runs: a transcript that exists when a run
starts is appended to, its next `seq` one past the last line's) and `kind`,
then the event's own keys. The kinds are the loop's (twine/runtime/loop.py,
runtime-contract.md §7.5); this module only writes and reads lines.

Written like the spend stream (twine/spend.py append_record): the directory
0700 and the file 0600 when created, each line one `os.write` of one
LF-terminated line to a file opened O_APPEND, then fsync. Never rewritten. A
transcript whose last line was torn (no LF — a run killed mid-write) is
appended to all the same: an LF is written first to end the torn line, which
is an append, and the next line says so (`torn_before`). A log that cannot be
written does not stop the run that writes it (TranscriptError, which the
loop logs and carries in its twin); the spend stream and the running record
are what the cap and the kill stand on.

Beside it, since twine-run-ergonomics, a call that ends `malformed-shape`
keeps the response body the transport drew:

    <state-dir>/transcripts/<sid>.call-<N>.raw      (0600, N the call number)

written by `write_raw` and named in the `turn` line's `raw` key — nothing is
kept for any other outcome. It is a response body, so the key is never in it.

Nothing here reads a key or the process environment, or spawns anything.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from twine.kill import DIR_MODE, FILE_MODE, is_sid, utc_now

log = logging.getLogger("twine.transcript")

TRANSCRIPTS_SUBDIR = "transcripts"
SUFFIX = ".jsonl"
# The raw response body kept for a call that ended malformed-shape:
# `<sid>.call-<N>.raw`, beside the transcript.
RAW_INFIX = ".call-"
RAW_SUFFIX = ".raw"
RAW_NAME = re.compile(r"^(?P<sid>.+)\.call-(?P<call>[1-9][0-9]*)\.raw$")
# The three keys every line opens with, in this order.
LINE_KEYS = ("at", "seq", "kind")


class TranscriptError(OSError):
    """A transcript line that could not be written (or a transcript that
    could not be opened). The message names the path."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


def transcripts_dir(state_dir: Path) -> Path:
    return Path(state_dir) / TRANSCRIPTS_SUBDIR


def transcript_path(state_dir: Path, sid: str) -> Path:
    """`<state-dir>/transcripts/<sid>.jsonl`. Raises ValueError for a sid
    twine would not name a file by (twine.kill.is_sid)."""
    if not is_sid(sid):
        raise ValueError(f"session id {sid!r} is not one twine names a transcript by")
    return transcripts_dir(state_dir) / f"{sid}{SUFFIX}"


def raw_path(state_dir: Path, sid: str, call: int) -> Path:
    """`<state-dir>/transcripts/<sid>.call-<N>.raw`, the response body kept
    for call N when it ended `malformed-shape`. Raises ValueError for a sid
    twine would not name a file by, or a call that is not a positive int."""
    if not is_sid(sid):
        raise ValueError(f"session id {sid!r} is not one twine names a transcript by")
    if type(call) is not int or call < 1:
        raise ValueError(f"call {call!r} is not a positive call number")
    return transcripts_dir(state_dir) / f"{sid}{RAW_INFIX}{call}{RAW_SUFFIX}"


def write_raw(state_dir: Path, sid: str, call: int, data: bytes) -> Path:
    """Keep `data` — the response body of call `call`, as drawn — at
    `raw_path`, mode 0600 (the directory 0700 when it has to be made). A
    file of the same name (a resumed run's numbering restarts) is replaced.
    Returns the path; raises TranscriptError naming it when it cannot be
    written."""
    path = raw_path(state_dir, sid, call)
    try:
        path.parent.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
        try:
            os.fchmod(fd, FILE_MODE)
            written = 0
            while written < len(data):
                written += os.write(fd, data[written:])
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise TranscriptError(f"cannot keep the raw response of call {call} at {path}: "
                              f"{exc.strerror or exc}") from exc
    log.info("%s: kept the raw response of call %d (%d bytes)", path, call, len(data))
    return path


def read_lines(path: Path) -> Iterator[dict[str, Any]]:
    """Every complete line of a transcript that parses as a JSON object, in
    order — what a reader (R5's resume, a test) walks. A torn last line and a
    line that is not an object are skipped and logged: a transcript is a
    log, read for its story, never trusted as a record."""
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError:
        return
    lines = data.split(b"\n")
    if lines and lines[-1]:
        log.warning("%s: the last line is torn (no LF); it is not read", path)
    for n, raw in enumerate(lines[:-1], 1):
        if not raw:
            continue
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError) as exc:
            log.warning("%s: line %d is not JSON (%s); skipped", path, n, exc)
            continue
        if isinstance(obj, dict):
            yield obj
        else:
            log.warning("%s: line %d is not a JSON object; skipped", path, n)


def _last_seq(path: Path) -> tuple[int, bool]:
    """The `seq` the transcript's last complete line carries (0 when it has
    none, or there is no file), and whether its last line is torn."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return 0, False
    except OSError as exc:
        raise TranscriptError(f"cannot read the transcript {path}: "
                              f"{exc.strerror or exc}") from exc
    torn = bool(data) and not data.endswith(b"\n")
    last = 0
    complete = data.split(b"\n")[:-1]
    for raw in reversed(complete):
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError):
            continue
        if isinstance(obj, dict) and type(obj.get("seq")) is int and obj["seq"] > 0:
            last = obj["seq"]
            break
    else:
        # No line carries a seq twine wrote: continue past the line count,
        # so seq still grows.
        last = len([r for r in complete if r])
    return last, torn


@dataclass
class Transcript:
    """An open transcript: where it is, the `seq` its next line takes, and
    the faults met writing it (each also logged). Open one with
    `Transcript.open(state_dir, sid)`; write with `append(kind, **event)`."""

    path: Path
    next_seq: int = 1
    torn_before: bool = False
    faults: list[str] = field(default_factory=list)
    clock: Callable[[], str] = utc_now

    @classmethod
    def open(cls, state_dir: Path, sid: str, *,
             clock: Callable[[], str] = utc_now) -> "Transcript":
        """The sid's transcript, created (and its directory) when absent;
        its next `seq` follows the last line's. Raises TranscriptError when
        the directory cannot be made or the file cannot be read."""
        path = transcript_path(state_dir, sid)
        try:
            path.parent.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        except OSError as exc:
            raise TranscriptError(f"cannot make {path.parent}: "
                                  f"{exc.strerror or exc}") from exc
        last, torn = _last_seq(path)
        if last:
            log.info("transcript %s exists (last seq %d); appending", path, last)
        return cls(path=path, next_seq=last + 1, torn_before=torn, clock=clock)

    def append(self, kind: str, **event: Any) -> dict[str, Any]:
        """Write one line — `at`, `seq`, `kind`, then the event's keys — and
        return it. The seq is taken whether or not the write succeeds, so a
        gap says a line was lost. Raises TranscriptError when the line cannot
        be written (also kept in `faults`)."""
        clash = [k for k in LINE_KEYS if k in event]
        if clash:
            raise ValueError(f"a transcript event may not set {', '.join(clash)}")
        obj: dict[str, Any] = {"at": self.clock(), "seq": self.next_seq, "kind": kind}
        self.next_seq += 1
        if self.torn_before:
            obj["torn_before"] = True
        obj.update(event)
        line = json.dumps(obj, ensure_ascii=False, default=str) + "\n"
        if "\n" in line[:-1]:
            raise ValueError("a transcript line rendered as more than one line")
        data = line.encode("utf-8")
        if self.torn_before:
            data = b"\n" + data
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, FILE_MODE)
            try:
                written = 0
                while written < len(data):
                    written += os.write(fd, data[written:])
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            fault = (f"cannot append to the transcript {self.path} (line {obj['seq']}, "
                     f"{kind}): {exc.strerror or exc}")
            self.faults.append(fault)
            log.error("%s", fault)
            raise TranscriptError(fault) from exc
        if self.torn_before:
            log.warning("%s: the torn last line was ended with an LF before line %d",
                        self.path, obj["seq"])
            self.torn_before = False
        return obj


def list_transcripts(state_dir: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(sids, faults) for `<state-dir>/transcripts/`: the sids of the
    `<sid>.jsonl` files there, sorted, and one sentence per other entry —
    what `twine status` lists. Reads names only; writes nothing."""
    directory = transcripts_dir(state_dir)
    if not os.path.isdir(directory):
        return (), ()
    try:
        names = sorted(os.listdir(directory))
    except OSError as exc:
        return (), (f"{TRANSCRIPTS_SUBDIR}/ cannot be listed: {exc.strerror or exc}",)
    sids, faults = [], []
    for name in names:
        shown = name if name.isprintable() else repr(name)
        stem = name[:-len(SUFFIX)] if name.endswith(SUFFIX) else None
        kept = RAW_NAME.match(name)
        if kept is not None and is_sid(kept.group("sid")) and os.path.isfile(directory / name):
            continue    # a kept raw response (`<sid>.call-<N>.raw`): not a transcript, no fault
        if stem is not None and is_sid(stem) and os.path.isfile(directory / name):
            sids.append(stem)
        else:
            faults.append(f"{shown} is not a transcript: its name is not <sid>{SUFFIX} "
                          "for a sid twine accepts, or it is not a file")
    return tuple(sorted(sids)), tuple(faults)

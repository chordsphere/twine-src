"""The kill-switch (twine-seed.md D15; Arc 1 session 5b): the between-calls
abort, the process-level kill, and the `aborted` closure.

D15, the architect's words: "every session spawn should come with a
foolproof kill-switch and running total of the money used through the api,
including a hard cap for budget reasons" — and the kill "must work when the
harness itself is wedged". The running total and the cap are session 5a's
(twine/spend.py). This module is the kill-switch, in three layers:

  1. **The between-calls abort.** `request_abort` writes a durable abort
     request into twine's state directory, `<state-dir>/abort/<sid>.json`;
     `abort_requested` is what the Arc 2 loop checks before every model
     call, beside `spend.check_call`. Observed, the loop stops with the
     `stop` key `killed` (STOP_KILLED; its move is `close-aborted`) and runs
     layer 3. The request is a file: it survives the runtime's death and
     needs no runtime to exist. Its presence is the signal — the content is
     a note for a reader — and a request that cannot be looked for reads as
     requested, so a broken state directory stops the loop rather than
     letting it run on (fail closed).
  2. **The process-level kill.** Before it starts a model call or a tool,
     the runtime records the process group it runs in (`register_running`,
     `<state-dir>/running/<sid>.json`; a cache, re-derivable), and every
     further group it starts — a tool run through the seam leads a group of
     its own — the moment the child exists (`register_group`, from the
     seam's `on_spawn` hook; session 5c), and forgets each such group once
     its run has returned with no survivor (`clear_group`, beside it, which
     the loop calls itself; session 2026-10-06-twine-clear-group-003), so
     the record holds what is alive. `kill_group` needs nothing else
     from the runtime: the runtime's group first, so it can start nothing
     more, then each recorded group in record order — SIGTERM, SIGCONT, a
     grace, SIGKILL, then a bounded wait until no member is alive — or the
     survivors, named. It is finished only when every one of them is gone.
  3. **The `aborted` closure.** `close_aborted` runs, through the run seam
     and only with the pinned bale, exactly `bale unlock <sid> --reason
     aborted --json` (twine.bale.unlock_argv), once, never retried, and
     reads bale's one JSON line: ok exactly when bale exits 0 and says
     `unlocked` for this sid with closure reason `aborted`. The verb and
     the loop share it; it takes the seam's runner, so tests inject a
     double.

`kill_session` is the operator's kill, `twine kill <sid>`: the three layers
in order, each reported, stopping short of the closure while any member of
any killed group lives (brief ruling 3: a record that says `aborted` while
the worker's shell still runs is the mystery D15 forbids). Once the
recorded groups are gone it re-reads the record once, so a group a hook
registered while the kill ran is killed too, and only then removes the
record and attempts the closure. When it cannot finish, its report names
where it stopped and the one line that finishes by hand (`operator_line`).

The pin gates the closure alone (session 5c, the sitting's correction to
5b): the abort request and the process kill run with any bale or none —
D15's kill "must work when the harness itself is wedged", and a bale
drifted off the pin is one way it can be — while the closure, whose
vocabulary the pin exists for (D17), is only ever attempted with the pinned
bale (`close_aborted` checks `Executable.drive_refusal` itself).

What it never does: merge, apply or revert anything (T12 — `bale unlock`
performs no git operation); run any `unlock` argv but the one; retry a
closure; guess a process group from anything but the running record; or
signal twine kill's own group. It spawns nothing itself: signals and
/proc reads go through twine.process's group helpers, and bale through the
runner it is handed. It never reads the seam's hook: the record is all it
relies on.

Sections:
  1. Names and errors                 (~line 98)
  2. The abort request                (~line 247)
  3. The running record               (~line 328)
  4. The process-level kill           (~line 719)
  5. The aborted closure              (~line 951)
  6. The kill, end to end             (~line 1101)
"""

from __future__ import annotations

import errno
import json
import logging
import os
import signal
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

try:
    import fcntl
except ImportError:  # not a POSIX platform; the record's writers then run unlocked
    fcntl = None  # type: ignore[assignment]

from twine import bale, process

log = logging.getLogger("twine.kill")

# ---------------------------------------------------------------------------
# 1. Names and errors
# ---------------------------------------------------------------------------

ABORT_SUBDIR = "abort"
RUNNING_SUBDIR = "running"
RECORD_SUFFIX = ".json"
# The running record's six keys and a group entry's three (brief 5c §2.1):
# what register_running and register_group write, what read_running requires.
RECORD_KEYS = ("sid", "pgid", "pid", "started_at", "leader_start_ticks", "groups")
GROUP_KEYS = ("pgid", "leader_start_ticks", "registered_at")

# The transition table's `stop` key for a session the loop finds killed
# (share/transitions.toml: killed -> close-aborted, actor twine).
STOP_KILLED = "killed"

# How long `twine kill` waits after SIGTERM before SIGKILL (--grace), and
# after SIGKILL for the last member to go — "bounded, a few seconds".
DEFAULT_GRACE_SECONDS = 5.0
KILL_WAIT_SECONDS = 5.0
POLL_SECONDS = 0.05
# How long clear_running waits for the lock on `running/` before it gives up
# and leaves the record in place (KillError). register_group and clear_group
# hold that lock for one read and one replace; the bound exists because the
# lock is the directory's, shared by every session's record, and `twine kill`
# must not hang behind a writer that is wedged (a runtime stopped mid-write).
CLEAR_LOCK_SECONDS = 5.0

# `bale unlock` closes a session's records and wipes its directory: seconds.
# Past these it is stuck, is killed by the seam, and is not ok (and never
# retried: it may or may not have closed the session).
UNLOCK_TIMEOUT_SECONDS = 120.0
UNLOCK_STDOUT_CAP_BYTES = 1024 * 1024
# What a close looks like (format_unlock_json's key contract, bale 0.4.49;
# recorded: fixtures/bale-0.4.49/scratch/unlock_sid_--reason-aborted_--json.json).
UNLOCKED_OUTCOME = "unlocked"

# A sid names a file (`<sid>.json`): bounded well under a file name's 255
# bytes. bale's own ids are a few dozen characters.
MAX_SID_LENGTH = 200
# How long --grace may be: a kill is not a scheduler.
MAX_GRACE_SECONDS = 600.0

# Where `twine kill` stopped when it could not finish; null when it did.
STEPS = ("refused", "abort", "process", "closure")

DIR_MODE = 0o700
FILE_MODE = 0o600


class KillError(OSError):
    """A kill-switch file could not be written or removed."""


class RunningRecordError(ValueError):
    """A running record that is not one; the message names every fault."""


def utc_now() -> str:
    """UTC, RFC 3339, seconds — the clock every twine record uses."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_sid(sid: str) -> None:
    """A sid names a file under the state directory and is passed to bale
    as an argument: the same rule as relay_argv (it cannot read as a flag
    and carries no `/`, whitespace or shell-significant byte)."""
    if not is_sid(sid):
        raise ValueError(f"session id {sid!r} is not a session id twine passes "
                         "to bale (a letter or digit, then letters, digits, "
                         f"`.`, `_`, `-`; at most {MAX_SID_LENGTH} characters)")


def is_sid(sid: Any) -> bool:
    """The rule `twine kill` and the loop's functions hold a sid to:
    relay_argv's, bounded so `<sid>.json` is a file name any filesystem
    takes."""
    return (isinstance(sid, str) and len(sid) <= MAX_SID_LENGTH
            and bale.SID_ARGUMENT.fullmatch(sid) is not None)


def _write_exclusive(path: Path, data: bytes) -> bool:
    """Write `data` to `path` durably, only if `path` does not exist: a
    temp file in the same directory, fsynced, then hard-linked into place
    (link fails if the name is taken) and the directory fsynced. True when
    written, False when `path` already existed. Raises OSError."""
    path.parent.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    tmp = _temp_name(path)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
    try:
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(tmp, path)
        except FileExistsError:
            return False
        _fsync_dir(path.parent)
        return True
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _write_replacing(path: Path, data: bytes) -> None:
    """Write `data` to `path` durably, replacing what is there: a temp file,
    fsynced, renamed over `path`, the directory fsynced. Raises OSError."""
    path.parent.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    tmp = _temp_name(path)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
    try:
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def _temp_name(path: Path) -> Path:
    """A temp file beside `path`, short whatever `path`'s name: a long sid
    must not fail on the temp file alone."""
    return path.with_name(f".twine-{os.getpid()}-{time.monotonic_ns()}.tmp")


def _fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError as exc:
        log.debug("cannot open %s to fsync it: %s", directory, exc)
        return
    try:
        os.fsync(fd)
    except OSError as exc:
        log.debug("cannot fsync %s: %s", directory, exc)
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# 2. The abort request
# ---------------------------------------------------------------------------


def abort_path(state_dir: Path, sid: str) -> Path:
    _check_sid(sid)
    return Path(state_dir) / ABORT_SUBDIR / f"{sid}{RECORD_SUFFIX}"


@dataclass(frozen=True)
class AbortRequest:
    """A durable abort request: where it is, when it was first made, and
    whether this call found it already made (requesting twice is
    idempotent: the first request's time stands)."""

    sid: str
    path: Path
    requested_at: str | None
    already: bool


def request_abort(state_dir: Path, sid: str, *,
                  clock: Callable[[], str] = utc_now) -> AbortRequest:
    """Request the between-calls abort for `sid`, durably: write
    `<state-dir>/abort/<sid>.json` (`sid`, `requested_at`) unless it is
    already there. Idempotent. Raises KillError when it cannot be written
    and ValueError for a sid that is not one."""
    path = abort_path(state_dir, sid)
    requested_at = clock()
    body = json.dumps({"sid": sid, "requested_at": requested_at},
                      ensure_ascii=True) + "\n"
    try:
        written = _write_exclusive(path, body.encode("ascii"))
    except OSError as exc:
        raise KillError(exc.errno, f"cannot write the abort request {path}: "
                                   f"{exc.strerror or exc}") from exc
    if written:
        log.info("abort requested for %s (%s)", sid, path)
        return AbortRequest(sid, path, requested_at, already=False)
    first = _requested_at(path)
    log.info("abort already requested for %s at %s (%s)", sid, first, path)
    return AbortRequest(sid, path, first, already=True)


def _requested_at(path: Path) -> str | None:
    """The first request's time, when its file says; None when it cannot be
    read as one. The request stands either way: its presence is the signal."""
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        log.warning("abort request %s exists but is not readable as one (%s); "
                    "it still stands", path, exc)
        return None
    value = obj.get("requested_at") if isinstance(obj, dict) else None
    return value if isinstance(value, str) else None


def abort_requested(state_dir: Path, sid: str) -> bool:
    """What the Arc 2 loop checks before every model call, beside
    spend.check_call: True when an abort has been requested for `sid`.

    Presence is the signal — a request file of any content stands. Only a
    path that does not exist reads as False. A request that cannot be
    looked for — the state directory unreadable, or a file where a
    directory should be — reads as True and is logged: a kill-switch that
    cannot be read stops the loop rather than letting it spend (fail
    closed). Observed, the loop stops with STOP_KILLED and runs
    close_aborted."""
    path = abort_path(state_dir, sid)
    try:
        os.stat(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        log.error("cannot look for the abort request %s (%s); treating it as "
                  "requested — the loop stops", path, exc.strerror or exc)
        return True
    return True


# ---------------------------------------------------------------------------
# 3. The running record
# ---------------------------------------------------------------------------


def running_path(state_dir: Path, sid: str) -> Path:
    _check_sid(sid)
    return Path(state_dir) / RUNNING_SUBDIR / f"{sid}{RECORD_SUFFIX}"


@dataclass(frozen=True)
class GroupEntry:
    """One additional process group the runtime started and registered
    (`register_group`, from the seam's spawn hook): its id, its leader's
    start time at registration (as the record's own `leader_start_ticks`,
    or None), and when it was registered (UTC, RFC 3339)."""

    pgid: int
    leader_start_ticks: int | None
    registered_at: str

    def as_json(self) -> dict[str, Any]:
        return {"pgid": self.pgid, "leader_start_ticks": self.leader_start_ticks,
                "registered_at": self.registered_at}


@dataclass(frozen=True)
class RunningRecord:
    """The process groups a session's runtime runs in, as the runtime wrote
    them: its own (`pgid`, `pid`, `started_at`, `leader_start_ticks`,
    written before it started working — brief item 3) and, in `groups`,
    every additional group it started and registered since, in
    registration order (session 5c; the runtime's own is never repeated
    there). `leader_start_ticks` is a group leader's start time
    (/proc/<pgid>/stat field 22) when the leader was alive and readable at
    registration, else None: with it, a kill can tell the recorded group
    from a later one that reuses the number (kill_group).

    The file is one JSON object with exactly six keys — `sid`, `pgid`,
    `pid`, `started_at`, `leader_start_ticks`, `groups` — and a reader
    requires every one of them (read_running)."""

    sid: str
    pgid: int
    pid: int
    started_at: str
    leader_start_ticks: int | None
    path: Path
    groups: tuple[GroupEntry, ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {"sid": self.sid, "pgid": self.pgid, "pid": self.pid,
                "started_at": self.started_at,
                "leader_start_ticks": self.leader_start_ticks,
                "groups": [g.as_json() for g in self.groups]}

    @property
    def pgids(self) -> list[int]:
        """Every group the record names, the runtime's first."""
        return [self.pgid, *(g.pgid for g in self.groups)]


def _write_record(record: RunningRecord) -> None:
    body = json.dumps(record.as_json(), ensure_ascii=True) + "\n"
    try:
        _write_replacing(record.path, body.encode("ascii"))
    except OSError as exc:
        raise KillError(exc.errno, f"cannot write the running record {record.path}: "
                                   f"{exc.strerror or exc}") from exc


def register_running(state_dir: Path, sid: str, pgid: int, pid: int, *,
                     clock: Callable[[], str] = utc_now,
                     proc_root: Path = process.PROC_ROOT) -> RunningRecord:
    """Record the process group `sid`'s runtime runs in — the runtime's,
    before it starts a model call or a tool (Arc 2). Writes
    `<state-dir>/running/<sid>.json` (`sid`, `pgid`, `pid`, `started_at`,
    `leader_start_ticks`, `groups: []`), replacing an older one — and so
    forgetting an older one's groups: the runtime registers itself once,
    before it starts anything. A cache in N4's sense: deleting it loses
    nothing of record. Raises RunningRecordError for a pgid or pid that
    could not be a group to kill, KillError when it cannot be written."""
    faults = _id_faults(pgid, pid)
    if faults:
        raise RunningRecordError("; ".join(faults))
    path = running_path(state_dir, sid)
    record = RunningRecord(sid, pgid, pid, clock(),
                           process.start_ticks(pgid, proc_root), path, ())
    _write_record(record)
    log.info("running record for %s: group %d, pid %d (%s)", sid, pgid, pid, path)
    return record


def register_group(state_dir: Path, sid: str, pgid: int, *,
                   clock: Callable[[], str] = utc_now,
                   proc_root: Path = process.PROC_ROOT) -> RunningRecord:
    """Add one more process group to `sid`'s running record — a group the
    runtime started, registered the moment the child exists (the seam's
    `on_spawn` hook hands over the child's pid, which is its pgid: the Arc
    2 loop composes `run(argv, …, on_spawn=lambda pid: register_group(
    state_dir, sid, pid))`). Reads the leader's start ticks as
    register_running does, appends `{pgid, leader_start_ticks,
    registered_at}` to `groups`, rewrites the record durably, and returns
    the grown record.

    Refuses (RunningRecordError) when there is no record to grow — the
    runtime registers itself before it starts anything — when the record
    is malformed (read_running's faults), when `pgid` could not be a group
    to kill, and when it is the runtime's own group, which the record
    already names. Raises KillError when the record cannot be rewritten.

    Two registrations at once cannot lose each other's entry: the
    read-append-replace runs under an exclusive lock on the `running/`
    directory (flock; no lock file is added beside the record), so hooks
    from concurrent runs serialize. Where flock is unavailable the lock is
    skipped and logged."""
    fault = _id_fault("pgid", pgid)
    if fault:
        raise RunningRecordError(fault)
    path = running_path(state_dir, sid)
    with _locked(path.parent):
        record = read_running(state_dir, sid)
        if record is None:
            raise RunningRecordError(
                f"no running record for {sid} at {path} to add group {pgid} to: the "
                "runtime registers itself (register_running) before it starts anything")
        if pgid == record.pgid:
            raise RunningRecordError(f"process group {pgid} is the runtime's own, which "
                                     f"the running record {path} already names")
        entry = GroupEntry(pgid, process.start_ticks(pgid, proc_root), clock())
        grown = RunningRecord(record.sid, record.pgid, record.pid, record.started_at,
                              record.leader_start_ticks, path, (*record.groups, entry))
        _write_record(grown)
    log.info("running record for %s: group %d registered (%d groups beside the "
             "runtime's; %s)", sid, pgid, len(grown.groups), path)
    return grown


def clear_group(state_dir: Path, sid: str, pgid: int) -> bool:
    """Forget one process group in `sid`'s running record — the tidy that
    keeps a long session's record to what is alive. The Arc 2 loop calls it
    itself, after a `run` returns with `RunResult.group_survivors` empty
    (the seam's promise that the group is gone, contract §10.6); a run that
    returned survivors leaves its entry for `twine kill` to reach. The loop
    never forgets a group that may be alive.

    Removes every entry of `groups` whose pgid is `pgid` — one, normally;
    each of them when the record names it twice — and rewrites the record
    durably, as register_group does: the same six keys, the runtime's four
    values and every other entry untouched and in their order. True.

    False, nothing written and nothing created (no `running/` appears where
    there was none), when the record names no such group or there is no
    record — a `twine kill` may have removed it, or the session is between
    runs. Both are logged; neither is a fault: the record is a cache (N4),
    and a group already forgotten is what the caller wanted.

    Refuses (RunningRecordError), the record untouched, for a `pgid` that
    could not be a group to kill (an integer above 1, never a bool), for
    the runtime's own group — the record's `pgid`, forgotten only with the
    whole record by clear_running — and for a malformed record
    (read_running's faults, each named). Raises KillError when the record
    cannot be rewritten, ValueError for a sid that is not one.

    The read-filter-replace runs under the exclusive lock register_group
    takes on `running/`, so a registration and a clear at once lose nothing
    of each other: afterwards the record names exactly the groups registered
    and not cleared, in registration order. clear_running takes the same
    lock, so a record `twine kill` has removed does not come back: either
    this clear finishes before the removal, or it reads no record and
    writes nothing. Where flock is unavailable it runs unlocked and logs
    it, as register_group does."""
    fault = _id_fault("pgid", pgid)
    if fault:
        raise RunningRecordError(fault)
    path = running_path(state_dir, sid)
    with _locked(path.parent):
        record = read_running(state_dir, sid)
        if record is None:
            log.info("running record for %s: none at %s, so group %d is not in it; "
                     "nothing to clear", sid, path, pgid)
            return False
        if pgid == record.pgid:
            raise RunningRecordError(
                f"process group {pgid} is the runtime's own, which the running record "
                f"{path} names as its pgid, not in groups: it is forgotten with the whole "
                "record (clear_running), never one entry at a time")
        kept = tuple(g for g in record.groups if g.pgid != pgid)
        removed = len(record.groups) - len(kept)
        if not removed:
            log.info("running record for %s: group %d is not in it (already "
                     "cleared, or never registered); nothing to clear (%s)",
                     sid, pgid, path)
            return False
        shrunk = RunningRecord(record.sid, record.pgid, record.pid, record.started_at,
                               record.leader_start_ticks, path, kept)
        _write_record(shrunk)
    log.info("running record for %s: group %d cleared (%d entr%s removed; %d groups "
             "beside the runtime's; %s)", sid, pgid, removed,
             "y" if removed == 1 else "ies", len(kept), path)
    return True


@contextmanager
def _locked(directory: Path, *, timeout: float | None = None) -> Iterator[None]:
    """An exclusive advisory lock on `directory` for the body's duration —
    what serializes register_group, clear_group and clear_running. A
    directory that does not exist is not locked (there is no record in it
    to change, and the body says so); where flock is unavailable — no
    fcntl on the platform, or a filesystem that refuses the lock (ENOLCK on
    some network mounts) — the body runs unlocked and that is logged, as it
    was before any lock existed. With `timeout`, the lock is waited for that
    many seconds at most and KillError (EWOULDBLOCK) is raised when another
    holder keeps it, the body not run; without one it is waited for."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError as exc:
        log.debug("cannot open %s to lock it: %s", directory, exc)
        yield
        return
    try:
        if fcntl is None:
            log.warning("fcntl is unavailable; %s is not locked while the running "
                        "record is changed", directory)
        else:
            _flock(fd, directory, timeout)
        yield
    finally:
        os.close(fd)


def _flock(fd: int, directory: Path, timeout: float | None) -> None:
    """Take an exclusive flock on `fd` — waiting, or polling for at most
    `timeout` seconds and then raising KillError (EWOULDBLOCK) naming
    `directory`. A flock the filesystem refuses outright (any error but
    another holder's) is logged and the caller goes on unlocked: the lock
    serializes twine's own writers, and `twine kill` must not fail on a
    state directory that cannot lock."""
    deadline = None if timeout is None else time.monotonic() + max(timeout, 0.0)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX if deadline is None
                        else fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if deadline is None or time.monotonic() >= deadline:
                raise KillError(errno.EWOULDBLOCK,
                                f"{directory} stayed locked by a running-record writer "
                                f"for {timeout or 0:g}s, so no record in it was "
                                "changed") from None
            time.sleep(POLL_SECONDS)
        except OSError as exc:
            log.warning("cannot lock %s (%s); the running record is changed unlocked",
                        directory, exc.strerror or exc)
            return


def clear_running(state_dir: Path, sid: str) -> bool:
    """Remove `sid`'s running record — the runtime's, on a clean end, and
    `twine kill`'s once the group is confirmed gone. True when one was
    removed, False when there was none. Raises KillError otherwise.

    The removal runs under the lock register_group and clear_group take on
    `running/`, so neither can be between its read and its replace when the
    record goes — a replace there would bring the removed record back.
    Unlike theirs, this wait is bounded (CLEAR_LOCK_SECONDS): past it the
    record is left in place and KillError says so, since `twine kill` must
    not hang behind a wedged writer, and a record left behind is a cache."""
    path = running_path(state_dir, sid)
    with _locked(path.parent, timeout=CLEAR_LOCK_SECONDS):
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise KillError(exc.errno, f"cannot remove the running record {path}: "
                                       f"{exc.strerror or exc}") from exc
        _fsync_dir(path.parent)
    log.info("running record for %s removed (%s)", sid, path)
    return True


def read_running(state_dir: Path, sid: str) -> RunningRecord | None:
    """`sid`'s running record, or None when there is none (a session between
    runs, or one whose runtime never started). Raises RunningRecordError,
    naming every fault, for one that cannot be read as a record — never a
    guess at a pgid. Every one of the six keys is required: a record
    without `groups`, or whose `groups` is not an array of group entries
    (`pgid` an integer above 1, `leader_start_ticks` a non-negative integer
    or null, `registered_at` a non-empty string), is malformed, fault by
    fault, as a record whose `sid` is not the file's is."""
    path = running_path(state_dir, sid)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RunningRecordError(f"{path} cannot be read: {exc.strerror or exc}") from exc
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError) as exc:
        # UnicodeDecodeError is a ValueError; RecursionError is how json
        # refuses a deeply nested document.
        raise RunningRecordError(f"{path} is not a JSON object: "
                                 f"{type(exc).__name__}: {str(exc)[:200]}") from exc
    if not isinstance(obj, dict):
        raise RunningRecordError(f"{path} is not a JSON object")
    faults = _id_faults(obj.get("pgid"), obj.get("pid"))
    if obj.get("sid") != sid:
        faults.append(f"its sid is {obj.get('sid')!r}, not {sid!r}")
    started_at = obj.get("started_at")
    if not isinstance(started_at, str) or not started_at:
        faults.append(f"started_at {started_at!r} is not a timestamp")
    ticks = obj.get("leader_start_ticks")
    fault = _ticks_fault("leader_start_ticks", ticks)
    if fault:
        faults.append(fault)
    groups, group_faults = _read_groups(obj)
    faults.extend(group_faults)
    if faults:
        raise RunningRecordError(f"{path} is not a running record: "
                                 + "; ".join(faults))
    return RunningRecord(sid, obj["pgid"], obj["pid"], started_at, ticks, path,
                         tuple(groups))


def _read_groups(obj: dict[str, Any]) -> tuple[list[GroupEntry], list[str]]:
    """The record's `groups`, read entry by entry, and every fault found —
    a missing key, a value that is not an array, an entry that is not an
    object or lacks a well-formed `pgid`, `leader_start_ticks` or
    `registered_at`."""
    if "groups" not in obj:
        return [], ["it has no groups key (a record written against the five-key "
                    "format of session 5b; the runtime that wrote it is not this "
                    "twine's)"]
    raw = obj["groups"]
    if not isinstance(raw, list):
        return [], [f"groups {_short(raw)} is not an array"]
    groups: list[GroupEntry] = []
    faults: list[str] = []
    for index, entry in enumerate(raw):
        where = f"groups[{index}]"
        if not isinstance(entry, dict):
            faults.append(f"{where} {_short(entry)} is not a group entry")
            continue
        entry_faults = [f"{where} has no {key}" for key in GROUP_KEYS if key not in entry]
        if "pgid" in entry:
            fault = _id_fault(f"{where} pgid", entry["pgid"])
            if fault:
                entry_faults.append(fault)
        if "leader_start_ticks" in entry:
            fault = _ticks_fault(f"{where} leader_start_ticks", entry["leader_start_ticks"])
            if fault:
                entry_faults.append(fault)
        registered_at = entry.get("registered_at")
        if "registered_at" in entry and (not isinstance(registered_at, str)
                                         or not registered_at):
            entry_faults.append(f"{where} registered_at {registered_at!r} is not a "
                                "timestamp")
        if entry_faults:
            faults.extend(entry_faults)
        else:
            groups.append(GroupEntry(entry["pgid"], entry.get("leader_start_ticks"),
                                     registered_at))
    return groups, faults


def _short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def _id_fault(name: str, value: Any) -> str | None:
    """A group to kill is a positive id above 1: 0 would signal the
    signaller's own group, 1 is init's, and a bool is not an id."""
    if type(value) is not int or value <= 1:
        return f"{name} {value!r} is not a process id above 1"
    return None


def _id_faults(pgid: Any, pid: Any) -> list[str]:
    faults = [_id_fault("pgid", pgid), _id_fault("pid", pid)]
    return [f for f in faults if f]


def _ticks_fault(name: str, value: Any) -> str | None:
    if value is not None and (type(value) is not int or value < 0):
        return f"{name} {value!r} is not a tick count or null"
    return None


# ---------------------------------------------------------------------------
# 4. The process-level kill
# ---------------------------------------------------------------------------


@dataclass
class GroupStep:
    """What the kill did to one process group, and what is left of it.

    `dead` is True only when no member was found alive at the end (or the
    record was stale: the number now leads another process, so the recorded
    group is gone). `survivors` names every member still alive — [] when
    dead. `error` names why this group is not known to be gone (members
    that cannot be enumerated, the kill's own group, survivors)."""

    pgid: int
    leader_start_ticks: int | None = None
    signals: list[str] = field(default_factory=list)
    dead: bool = False
    survivors: list[int] = field(default_factory=list)
    stale: bool = False
    error: str | None = None
    # True when the group was not signalled at all because it is twine
    # kill's own: the kill stops there (the operator runs it from another
    # shell), and the groups after it are left for that run.
    refused: bool = False

    @property
    def signalled(self) -> bool:
        return bool(self.signals)

    def as_json(self) -> dict[str, Any]:
        """The twin's entry for an additional group (cli-contract.md §14.6)."""
        return {"pgid": self.pgid, "signalled": self.signalled,
                "signals": list(self.signals), "dead": self.dead,
                "survivors": list(self.survivors), "stale": self.stale}


@dataclass
class ProcessStep:
    """What the kill did to every recorded group, and what is left of them.

    `runtime` is the runtime's own group (None when the record was
    malformed and named no group); `groups` the additional groups, in
    signalling order — the record's, then any the one re-read found. The
    whole is `dead` only when every group is gone (or stale); `survivors`
    is every surviving pid across all of them, sorted; `error` names why
    the step could not finish — a malformed record, or each group that is
    not known to be gone. `signals`, `signalled` and `stale` are the
    runtime's group's, as session 5b defined them."""

    record: RunningRecord | None = None
    record_path: Path | None = None
    runtime: GroupStep | None = None
    groups: list[GroupStep] = field(default_factory=list)
    record_cleared: bool = False
    record_error: str | None = None

    @property
    def steps(self) -> list[GroupStep]:
        return ([] if self.runtime is None else [self.runtime]) + list(self.groups)

    @property
    def signals(self) -> list[str]:
        return [] if self.runtime is None else list(self.runtime.signals)

    @property
    def signalled(self) -> bool:
        return bool(self.signals)

    @property
    def stale(self) -> bool:
        return self.runtime is not None and self.runtime.stale

    @property
    def dead(self) -> bool:
        """Every group the record names is gone. False while the record's
        whole is not known — malformed, or malformed on the re-read, so a
        group registered meanwhile may be unknown."""
        return (self.runtime is not None and self.record_error is None
                and all(s.dead for s in self.steps))

    @property
    def survivors(self) -> list[int]:
        return sorted({pid for s in self.steps for pid in s.survivors})

    @property
    def alive_groups(self) -> list[int]:
        """The pgids not known to be gone, the runtime's first, then in
        signalling order: what the hand line names."""
        return [s.pgid for s in self.steps if not s.dead]

    @property
    def error(self) -> str | None:
        problems = [self.record_error] if self.record_error else []
        problems.extend(s.error for s in self.steps if s.error)
        return "; ".join(problems) if problems else None

    def as_json(self) -> dict[str, Any]:
        r = self.record
        return {"pgid": None if r is None else r.pgid,
                "pid": None if r is None else r.pid,
                "started_at": None if r is None else r.started_at,
                "signalled": self.signalled, "signals": self.signals,
                "dead": self.dead, "survivors": self.survivors,
                "stale": self.stale,
                "groups": [g.as_json() for g in self.groups],
                "record_cleared": self.record_cleared,
                "record": None if self.record_path is None else str(self.record_path),
                "error": self.error}


def kill_one_group(pgid: int, leader_start_ticks: int | None, *,
                   grace: float = DEFAULT_GRACE_SECONDS, wait: float = KILL_WAIT_SECONDS,
                   proc_root: Path = process.PROC_ROOT, sid: str = "") -> GroupStep:
    """Kill one process group and wait until no member is alive.

    In order: refuse to signal twine kill's own group; if the record carries
    the leader's start time and a live process now holds that number with
    another start time, the recorded group is gone (Linux never hands out a
    pid still in use as a group id) — stale, nothing is signalled; if no
    member is alive, nothing is signalled; else SIGTERM to the group, then
    SIGCONT (a stopped member never sees SIGTERM until it is continued), up
    to `grace` seconds for the members to go, SIGKILL to the group if any
    remain, and up to `wait` more seconds. `dead` only when none is left;
    otherwise `survivors` names them. Members are enumerated from /proc:
    where there is none the group is still signalled, but it is never
    reported dead."""
    step = GroupStep(pgid=pgid, leader_start_ticks=leader_start_ticks)
    own = os.getpgrp()
    if pgid == own:
        step.refused = True
        step.error = (f"the recorded process group {pgid} is twine kill's own; it "
                      "is not signalled — run twine kill from another shell")
        return step
    if leader_start_ticks is not None:
        now = process.read_stat(pgid, proc_root)
        if now is not None and now.start_ticks != leader_start_ticks:
            step.stale, step.dead = True, True
            log.warning("running record for %s is stale: pid %d started at tick %d, "
                        "the record says %d; the recorded group is gone and nothing "
                        "is signalled", sid, pgid, now.start_ticks, leader_start_ticks)
            return step
    members = process.group_members(pgid, proc_root)
    if members == []:
        step.dead = True
        log.info("process group %d: no member alive; nothing to signal", pgid)
        return step
    for signums, bound in (((signal.SIGTERM, signal.SIGCONT), grace),
                           ((signal.SIGKILL,), wait)):
        for signum in signums:
            why = process.signal_group(pgid, signum)
            if why is None:
                step.signals.append(signal.Signals(signum).name)
            elif why != "gone":
                log.warning("process group %d: %s not delivered: %s", pgid,
                            signal.Signals(signum).name, why)
        members = _await_members_gone(pgid, bound, proc_root)
        if members == []:
            step.dead = True
            return step
    if members is None:
        step.error = (f"process group {pgid} was signalled, but its members cannot "
                      "be enumerated here (no /proc), so it is not known to be gone")
        return step
    step.survivors = members
    step.error = (f"process group {pgid} still has live members after SIGKILL and "
                  f"{wait:g}s: {', '.join(str(p) for p in members)}")
    return step


def kill_group(record: RunningRecord, *, grace: float = DEFAULT_GRACE_SECONDS,
               wait: float = KILL_WAIT_SECONDS,
               proc_root: Path = process.PROC_ROOT) -> ProcessStep:
    """Kill every process group the record names and wait until no member
    of any of them is alive: the runtime's own group first, so it can start
    nothing more, then each group in `record.groups` in record order, each
    as kill_one_group does it (the same signals, grace and wait; the stale
    check on its own `leader_start_ticks`). The step is done only when
    every group is gone; otherwise the survivors of all of them are named.
    A runtime group that is twine kill's own is not signalled and the step
    stops there — the groups after it are not signalled either, since the
    runtime that could start more is not stopped; the run from another
    shell takes them all. The caller (kill_session) re-reads the record
    once afterwards for a group registered while this ran: `kill_more`
    takes those."""
    step = ProcessStep(record=record, record_path=record.path)
    step.runtime = kill_one_group(record.pgid, record.leader_start_ticks, grace=grace,
                                  wait=wait, proc_root=proc_root, sid=record.sid)
    if step.runtime.refused:
        log.error("kill %s: the runtime's group is twine kill's own; %d further "
                  "recorded group(s) left for a run from another shell", record.sid,
                  len(record.groups))
        return step
    kill_more(step, record.groups, grace=grace, wait=wait, proc_root=proc_root)
    return step


def kill_more(step: ProcessStep, groups: Sequence[GroupEntry], *,
              grace: float = DEFAULT_GRACE_SECONDS, wait: float = KILL_WAIT_SECONDS,
              proc_root: Path = process.PROC_ROOT) -> None:
    """Kill each of `groups`, in order, the same way, and append each to
    `step.groups`. A pgid the step already handled is not signalled twice:
    its number could by now lead a stranger's group."""
    done = {s.pgid for s in step.steps}
    sid = "" if step.record is None else step.record.sid
    for entry in groups:
        if entry.pgid in done:
            log.info("process group %d is already handled; not signalled again",
                     entry.pgid)
            continue
        done.add(entry.pgid)
        one = kill_one_group(entry.pgid, entry.leader_start_ticks, grace=grace,
                             wait=wait, proc_root=proc_root, sid=sid)
        step.groups.append(one)
        if one.refused:
            log.error("kill %s: recorded group %d is twine kill's own; the groups "
                      "after it are left for a run from another shell", sid, one.pgid)
            return


def _await_members_gone(pgid: int, timeout: float, proc_root: Path) -> list[int] | None:
    """Poll until no member of `pgid` is alive (returns []) or `timeout`
    passes (returns the members). None when they cannot be enumerated."""
    deadline = time.monotonic() + max(timeout, 0.0)
    while True:
        members = process.group_members(pgid, proc_root)
        if members is None or not members or time.monotonic() >= deadline:
            return members
        time.sleep(POLL_SECONDS)


# ---------------------------------------------------------------------------
# 5. The aborted closure
# ---------------------------------------------------------------------------

# bale 0.4.49's refusal when the session reached HOLD, as recorded
# (fixtures/bale-0.4.49/scratch/unlock_sid_--json+unlock-refused+hold-branch.json,
# its `message`, also printed as `[bale] error: <message>` on stderr):
# `branch bale/<sid> exists — this session reached HOLD. Use `bale revert
# <sid>` …`. Twine reads only this prefix of bale's stderr, to hand the
# operator bale's own remedy; every other refusal is surfaced verbatim. The
# recorded line also carries the reason code `hold-branch` (bale 0.4.47);
# keying on it instead of the text is the next session's.
HOLD_BRANCH_REFUSAL = "branch bale/{sid} exists"


@dataclass
class Closure:
    """One run of `bale unlock <sid> --reason aborted --json` and what it
    said. `ok` exactly when bale exited 0 and its stdout is one JSON object
    with `outcome` "unlocked", `sid` the session and `closure_reason`
    "aborted". Never retried."""

    sid: str
    argv: list[str] | None = None
    ran: bool = False
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    stderr_truncated: bool = False
    timed_out: bool = False
    capped: bool = False
    duration_seconds: float | None = None
    unlock: dict[str, Any] | None = None
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.ran and not self.failures

    @property
    def telemetry(self) -> Any:
        return None if self.unlock is None else self.unlock.get("telemetry")

    @property
    def hold_branch(self) -> bool:
        return HOLD_BRANCH_REFUSAL.format(sid=self.sid) in self.stderr

    @property
    def operator_line(self) -> str | None:
        """The hand line when the closure did not land: bale's own remedy,
        `bale revert <sid>`, when bale refused because the session reached
        HOLD (revert touches git, so it is the operator's, never twine's);
        otherwise the one unlock line. None when it landed."""
        if self.ok:
            return None
        return bale.revert_line(self.sid) if self.hold_branch else bale.unlock_line(self.sid)

    def report(self) -> dict[str, Any]:
        return {"argv": self.argv, "ran": self.ran, "exit_code": self.exit_code,
                "stdout": self.stdout, "stderr": self.stderr,
                "stderr_truncated": self.stderr_truncated,
                "timed_out": self.timed_out, "capped": self.capped,
                "duration_seconds": self.duration_seconds}


def close_aborted(run: process.Runner, executable: bale.Executable, sid: str, *,
                  cwd: str | Path, env: Mapping[str, str]) -> Closure:
    """Close `sid` in bale with the closure reason `aborted`: run exactly
    `bale unlock <sid> --reason aborted --json` (bale.unlock_argv) through
    `run`, the seam's runner, in `cwd` — the repo whose session it is —
    once, and only with the pinned bale: an `executable` whose
    `drive_refusal` is set is a failure here, bale not started (D2), so a
    caller cannot reach an unpinned bale by forgetting the gate. The caller
    has checked that no member of the session's process group is alive.

    Shared by `twine kill` and, when it observes an abort request, the Arc
    2 loop. Never raises for anything bale does: a refusal (exit 1, nothing
    on stdout, the reason on stderr), a timeout, or a line that is not the
    close it asked for is a Closure whose failures name it. A bale that
    cannot be started at all is a failure too (`ran` false)."""
    closure = Closure(sid=sid)
    refusal = executable.drive_refusal
    if refusal is not None or executable.path is None:
        closure.failures.append(refusal or "no bale executable")
        return closure
    argv = bale.unlock_argv(executable.path, sid)
    closure.argv = list(argv)
    log.info("closing %s aborted: %s (in %s)", sid, " ".join(argv[1:]), cwd)
    try:
        result = run(argv, cwd=cwd, stdin=None, timeout=UNLOCK_TIMEOUT_SECONDS,
                     env=dict(env), stdout_cap=UNLOCK_STDOUT_CAP_BYTES)
    except process.RunError as exc:
        closure.failures.append(f"bale could not be started ({argv[0]}): "
                                f"{exc.strerror or exc}")
        return closure
    closure.ran = True
    closure.exit_code = result.exit_code
    closure.stdout = _text(result.stdout)
    closure.stderr = _text(result.stderr)
    closure.stderr_truncated = result.stderr_truncated
    closure.timed_out = result.timed_out
    closure.capped = result.stdout_capped
    closure.duration_seconds = result.duration_seconds
    if result.timed_out:
        closure.failures.append(
            f"bale unlock did not finish within {UNLOCK_TIMEOUT_SECONDS:g}s and was "
            "killed; it may or may not have closed the session (`bale status` "
            "says), and twine does not retry")
    if result.stdout_capped:
        closure.failures.append(f"bale's stdout passed {UNLOCK_STDOUT_CAP_BYTES} "
                                "bytes and it was stopped")
    if not result.killed and result.exit_code != 0:
        refusal = closure.stderr.strip().splitlines()
        closure.failures.append(
            f"bale exited {result.exit_code}"
            + (f": {refusal[-1]}" if refusal else " with nothing on stderr"))
    if not result.killed:
        _read_unlock_line(closure)
    return closure


def _read_unlock_line(closure: Closure) -> None:
    """bale's stdout must be one JSON object saying this sid was unlocked
    with closure reason `aborted`; whatever it said instead is named. On a
    refusal stdout is empty (bale's fail()), which is said only when bale
    exited 0 — a refusal's reason is already its exit and stderr."""
    try:
        obj = json.loads(closure.stdout)
    except (ValueError, RecursionError):
        obj = None
    if not isinstance(obj, dict):
        if closure.exit_code == 0 or closure.stdout.strip():
            shown = closure.stdout.strip()
            closure.failures.append(
                "bale's stdout was not one JSON object"
                + (f" (it began {shown[:80]!r})" if shown else " (it was empty)"))
        return
    closure.unlock = obj
    expected = (("outcome", UNLOCKED_OUTCOME), ("sid", closure.sid),
                ("closure_reason", bale.UNLOCK_REASON))
    for key, want in expected:
        if obj.get(key) != want:
            closure.failures.append(f"bale reported {key} {obj.get(key)!r}, not {want!r}")


def _text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        log.info("bale's output is not UTF-8 (byte %d); replaced", exc.start)
        return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 6. The kill, end to end
# ---------------------------------------------------------------------------


@dataclass
class KillReport:
    """Everything `twine kill <sid>` did, in order, and where it stopped.

    ok exactly when the abort request stands, no process of any recorded
    group is alive (or none was recorded), and bale closed the session
    `aborted`. `as_json()` is the verb's payload (cli-contract.md §14)."""

    sid: str
    state_dir: Path | None = None
    state_dir_source: str | None = None
    cwd: str | None = None
    grace_seconds: float | None = None
    bale: dict[str, Any] | None = None
    refusals: list[str] = field(default_factory=list)
    abort: AbortRequest | None = None
    abort_error: str | None = None
    process: ProcessStep | None = None
    closure: Closure | None = None
    closure_skipped: str | None = None

    @property
    def abort_requested(self) -> bool:
        return self.abort is not None

    @property
    def process_done(self) -> bool:
        return self.process is None or (self.process.dead and self.process.error is None)

    @property
    def closed(self) -> bool:
        return self.closure is not None and self.closure.ok

    @property
    def ok(self) -> bool:
        return (not self.refusals and self.abort_requested and self.process_done
                and self.closed)

    @property
    def stopped_at(self) -> str | None:
        """The first step that did not complete: `refused` (nothing was
        done), `abort`, `process` or `closure`; None when the kill finished."""
        if self.refusals:
            return "refused"
        if not self.abort_requested:
            return "abort"
        if not self.process_done:
            return "process"
        if not self.closed:
            return "closure"
        return None

    @property
    def operator_line(self) -> str | None:
        """The one line that finishes the kill by hand, or None when nothing
        is left to do. Members alive: the signal to every group not known
        to be gone, the runtime's first then record order — `kill -KILL --
        -<pgid> -<pgid> …`. The closure refused or not reached: bale's own
        remedy for a HOLD branch, else the unlock line. None when no one
        line finishes it safely — a malformed running record names no
        group, and a close must wait until the runtime is found and stopped
        (the reason says so) — and when the kill was refused before anything
        was done: fix the named fault and run twine kill again."""
        stop = self.stopped_at
        if stop is None or stop == "refused":
            return None
        p = self.process
        if p is not None and not self.process_done:
            # Whatever else stopped, a group that may be alive comes first:
            # never hand out a close while a member of it may live.
            alive = p.alive_groups
            return None if not alive else "kill -KILL -- " + " ".join(f"-{g}" for g in alive)
        if self.closure is not None:
            return self.closure.operator_line
        return bale.unlock_line(self.sid)

    @property
    def problems(self) -> list[str]:
        out = list(self.refusals)
        if self.abort_error:
            out.append(self.abort_error)
        if self.process is not None and self.process.error:
            out.append(self.process.error)
        if self.closure_skipped:
            out.append(self.closure_skipped)
        if self.closure is not None:
            out.extend(self.closure.failures)
            if self.closure.hold_branch:
                out.append(f"bale refused because the session reached HOLD; its "
                           f"remedy, `{bale.revert_line(self.sid)}`, touches git and "
                           "is the operator's — twine never runs it")
        return out

    @property
    def reason(self) -> str | None:
        problems = self.problems
        return "; ".join(problems) if problems else None

    def as_json(self) -> dict[str, Any]:
        closure = self.closure.report() if self.closure is not None else Closure(self.sid).report()
        return {
            "sid": self.sid,
            "abort_requested": self.abort_requested,
            "process": None if self.process is None else self.process.as_json(),
            "closed": self.closed,
            "closure": None if self.closure is None else self.closure.unlock,
            "telemetry": None if self.closure is None else self.closure.telemetry,
            "operator_line": self.operator_line,
            "stopped_at": self.stopped_at,
            "reason": self.reason,
            "refusals": list(self.refusals),
            "abort": {
                "path": None if self.state_dir is None
                else str(abort_path(self.state_dir, self.sid)) if is_sid(self.sid) else None,
                "already_requested": None if self.abort is None else self.abort.already,
                "requested_at": None if self.abort is None else self.abort.requested_at,
            },
            **closure,
            "state_dir": None if self.state_dir is None else str(self.state_dir),
            "state_dir_source": self.state_dir_source,
            "cwd": self.cwd,
            "grace_seconds": self.grace_seconds,
            "bale": self.bale,
        }

    def lines(self) -> list[str]:
        """The human rendering: a verdict line, one line per step, and the
        line to finish by hand when there is one."""
        if self.ok:
            head = (f"kill {self.sid}: done — abort requested, no process left, "
                    "closed in bale as aborted")
        elif self.stopped_at == "refused":
            head = f"kill {self.sid}: refused — nothing was done: {self.reason}"
        else:
            head = f"kill {self.sid}: NOT FINISHED (stopped at {self.stopped_at}) — {self.reason}"
        lines = [head]
        if self.stopped_at == "refused":
            return lines
        if self.abort is not None:
            when = f" (first at {self.abort.requested_at})" if self.abort.already else ""
            lines.append(f"  abort:   requested{' already' if self.abort.already else ''}"
                         f"{when} — {self.abort.path}")
        else:
            lines.append(f"  abort:   NOT requested — {self.abort_error}")
        p = self.process
        if p is None:
            lines.append("  process: no running record — no process to kill")
        elif p.record is None or p.runtime is None:
            lines.append(f"  process: NOT KILLED — {p.error}")
        else:
            label = "  process: "
            for step in p.steps:
                lines.append(f"{label}group {step.pgid}: {_group_state(step)}")
                label = "           "
            if p.groups:
                lines.append(f"           {len(p.steps)} groups in all: "
                             + ("none alive" if p.dead
                                else "survivors " + ", ".join(str(s) for s in p.survivors)
                                if p.survivors else "not all known to be gone"))
            if p.record_error:
                lines.append(f"           record: {p.record_error}")
        c = self.closure
        if c is None:
            lines.append(f"  closure: not attempted — {self.closure_skipped}")
        elif c.ok:
            lines.append(f"  closure: bale unlocked {self.sid} (closure reason aborted); "
                         f"telemetry {c.telemetry}")
        else:
            lines.append(f"  closure: NOT CLOSED — {'; '.join(c.failures)}")
        if self.operator_line:
            lines.append(f"  finish by hand: {self.operator_line}")
        return lines


def _group_state(step: GroupStep) -> str:
    """One group's line in the human rendering: what was sent, what is left."""
    did = ", ".join(step.signals) if step.signals else "nothing signalled"
    if step.stale:
        state = "stale record (the number now leads another process); the group is gone"
    elif step.dead:
        state = "no member alive"
    elif step.survivors:
        state = "survivors " + ", ".join(str(s) for s in step.survivors)
    else:
        state = step.error or "not known to be gone"
    return f"{did}; {state}"


def kill_session(state_dir: Path, sid: str, *, run: process.Runner,
                 executable: bale.Executable,
                 cwd: str | Path, env: Mapping[str, str],
                 grace: float = DEFAULT_GRACE_SECONDS, wait: float = KILL_WAIT_SECONDS,
                 report: KillReport | None = None,
                 proc_root: Path = process.PROC_ROOT) -> KillReport:
    """`twine kill <sid>`'s three steps, in order, each reported (brief item 1):

    1. request the between-calls abort (durable, idempotent);
    2. kill every recorded process group, if a running record exists — the
       runtime's first, then each registered group in record order — and
       wait until no member of any of them is alive; a malformed record is
       a named refusal of this step, never a guess. Once they are gone the
       record is re-read once, and a group registered since (a hook racing
       the kill) is killed the same way; only then is the record (a cache)
       removed, so a later kill cannot signal a reused number;
    3. close the session in bale `aborted` (close_aborted) — only when the
       abort request stands and no process is alive or none was recorded,
       and only with the pinned bale: the pin gates this step alone, and
       close_aborted checks it.

    The caller has validated the sid, the state directory, `cwd` and the
    grace. A report the caller started (the verb's, with its locations)
    may be passed in."""
    report = report if report is not None else KillReport(sid=sid)
    report.state_dir = Path(state_dir)
    try:
        report.abort = request_abort(state_dir, sid)
    except KillError as exc:
        report.abort_error = str(exc.strerror or exc)
        log.error("kill %s: %s", sid, report.abort_error)
    try:
        record = read_running(state_dir, sid)
    except RunningRecordError as exc:
        report.process = ProcessStep(
            record_path=running_path(state_dir, sid),
            record_error=f"the running record is malformed, so no process group "
                         f"is known to kill — find and stop the session's runtime "
                         f"yourself before closing it: {exc}")
        log.error("kill %s: %s", sid, report.process.error)
        record = None
    if record is not None:
        step = kill_group(record, grace=grace, wait=wait, proc_root=proc_root)
        report.process = step
        if step.dead and step.error is None:
            _kill_registered_since(step, state_dir, sid, grace=grace, wait=wait,
                                   proc_root=proc_root)
        if step.dead and step.error is None:
            try:
                step.record_cleared = clear_running(state_dir, sid)
            except KillError as exc:
                log.warning("kill %s: the groups are gone but %s (a cache; "
                            "nothing of record is lost)", sid, exc.strerror or exc)
    if not report.abort_requested:
        report.closure_skipped = ("the abort request could not be written, so the "
                                  "session is not closed; fix the state directory "
                                  "and run twine kill again, or close it by hand")
    elif not report.process_done:
        report.closure_skipped = ("a process of the session may still be alive, so "
                                  "it is not closed `aborted` (brief ruling 3)")
    else:
        report.closure = close_aborted(run, executable, sid, cwd=cwd, env=env)
    log.info("kill %s: ok=%s stopped_at=%s", sid, report.ok, report.stopped_at)
    return report


def _kill_registered_since(step: ProcessStep, state_dir: Path, sid: str, *,
                           grace: float, wait: float, proc_root: Path) -> None:
    """The one re-read (brief §2.3): a hook that raced the kill may have
    registered a group after the record was first read. Any group the
    re-read names that the step has not handled — in `groups`, or a
    runtime that re-registered under a new number — is killed the same
    way. A record that has become malformed is an error of the step (the
    record is left for the operator); one that is gone is nothing more to
    do. What this cannot close is the window between a child's Popen and
    its hook's write in a runtime that is itself SIGKILLed (§14.4)."""
    try:
        again = read_running(state_dir, sid)
    except RunningRecordError as exc:
        step.record_error = (f"the running record changed under the kill and is "
                             f"malformed now, so a group registered meanwhile may be "
                             f"unknown — find and stop the session's runtime yourself "
                             f"before closing it: {exc}")
        log.error("kill %s: %s", sid, step.record_error)
        return
    if again is None:
        log.info("kill %s: the running record is gone already; nothing registered "
                 "since", sid)
        return
    handled = {s.pgid for s in step.steps}
    named = [GroupEntry(again.pgid, again.leader_start_ticks, again.started_at),
             *again.groups]
    new = [g for g in named if g.pgid not in handled]
    if new:
        log.warning("kill %s: %d group(s) registered while the kill ran: %s", sid,
                    len(new), ", ".join(str(g.pgid) for g in new))
    kill_more(step, new, grace=grace, wait=wait, proc_root=proc_root)

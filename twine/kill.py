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
     `<state-dir>/running/<sid>.json`; a cache, re-derivable). `kill_group`
     needs nothing else from the runtime: SIGTERM to the group, a grace,
     SIGKILL, then a bounded wait until no member is alive — or the
     survivors, named. It is finished only when the group is gone.
  3. **The `aborted` closure.** `close_aborted` runs, through the run seam
     and only with the pinned bale, exactly `bale unlock <sid> --reason
     aborted --json` (twine.bale.unlock_argv), once, never retried, and
     reads bale's one JSON line: ok exactly when bale exits 0 and says
     `unlocked` for this sid with closure reason `aborted`. The verb and
     the loop share it; it takes the seam's runner, so tests inject a
     double.

`kill_session` is the operator's kill, `twine kill <sid>`: the three layers
in order, each reported, stopping short of the closure while any member of
the killed group lives (brief ruling 3: a record that says `aborted` while
the worker's shell still runs is the mystery D15 forbids). When it cannot
finish, its report names where it stopped and the one line that finishes
by hand (`operator_line`).

One group, not every group: the running record holds the one process group
the runtime runs in. A child the runtime starts through the seam
(twine.process.run_process) leads a group of its own and is outside it; the
Arc 2 runtime must record those too or start them inside its own group
(cli-contract.md §14.4).

What it never does: merge, apply or revert anything (T12 — `bale unlock`
performs no git operation); run any `unlock` argv but the one; retry a
closure; guess a process group from anything but the running record; or
signal twine kill's own group. It spawns nothing itself: signals and
/proc reads go through twine.process's group helpers, and bale through the
runner it is handed.

Sections:
  1. Names and errors                 (~line 75)
  2. The abort request                (~line 215)
  3. The running record               (~line 295)
  4. The process-level kill           (~line 415)
  5. The aborted closure              (~line 525)
  6. The kill, end to end             (~line 675)
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from twine import bale, process

log = logging.getLogger("twine.kill")

# ---------------------------------------------------------------------------
# 1. Names and errors
# ---------------------------------------------------------------------------

ABORT_SUBDIR = "abort"
RUNNING_SUBDIR = "running"
RECORD_SUFFIX = ".json"

# The transition table's `stop` key for a session the loop finds killed
# (share/transitions.toml: killed -> close-aborted, actor twine).
STOP_KILLED = "killed"

# How long `twine kill` waits after SIGTERM before SIGKILL (--grace), and
# after SIGKILL for the last member to go — "bounded, a few seconds".
DEFAULT_GRACE_SECONDS = 5.0
KILL_WAIT_SECONDS = 5.0
POLL_SECONDS = 0.05

# `bale unlock` closes a session's records and wipes its directory: seconds.
# Past these it is stuck, is killed by the seam, and is not ok (and never
# retried: it may or may not have closed the session).
UNLOCK_TIMEOUT_SECONDS = 120.0
UNLOCK_STDOUT_CAP_BYTES = 1024 * 1024
# What a close looks like (format_unlock_json's key contract, bale 0.4.45).
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
class RunningRecord:
    """The process group a session's runtime runs in, as the runtime wrote
    it before it started working (brief item 3). `leader_start_ticks` is
    the group leader's start time (/proc/<pgid>/stat field 22) when the
    leader was alive and readable at registration, else None: with it, a
    kill can tell the recorded group from a later one that reuses the
    number (twine/kill.py kill_group)."""

    sid: str
    pgid: int
    pid: int
    started_at: str
    leader_start_ticks: int | None
    path: Path

    def as_json(self) -> dict[str, Any]:
        return {"sid": self.sid, "pgid": self.pgid, "pid": self.pid,
                "started_at": self.started_at,
                "leader_start_ticks": self.leader_start_ticks}


def register_running(state_dir: Path, sid: str, pgid: int, pid: int, *,
                     clock: Callable[[], str] = utc_now,
                     proc_root: Path = process.PROC_ROOT) -> RunningRecord:
    """Record the process group `sid`'s runtime runs in — the runtime's,
    before it starts a model call or a tool (Arc 2). Writes
    `<state-dir>/running/<sid>.json` (`sid`, `pgid`, `pid`, `started_at`,
    `leader_start_ticks`), replacing an older one. A cache in N4's sense:
    deleting it loses nothing of record. Raises RunningRecordError for a
    pgid or pid that could not be a group to kill, KillError when it
    cannot be written."""
    faults = _id_faults(pgid, pid)
    if faults:
        raise RunningRecordError("; ".join(faults))
    path = running_path(state_dir, sid)
    record = RunningRecord(sid, pgid, pid, clock(),
                           process.start_ticks(pgid, proc_root), path)
    body = json.dumps(record.as_json(), ensure_ascii=True) + "\n"
    try:
        _write_replacing(path, body.encode("ascii"))
    except OSError as exc:
        raise KillError(exc.errno, f"cannot write the running record {path}: "
                                   f"{exc.strerror or exc}") from exc
    log.info("running record for %s: group %d, pid %d (%s)", sid, pgid, pid, path)
    return record


def clear_running(state_dir: Path, sid: str) -> bool:
    """Remove `sid`'s running record — the runtime's, on a clean end, and
    `twine kill`'s once the group is confirmed gone. True when one was
    removed, False when there was none. Raises KillError otherwise."""
    path = running_path(state_dir, sid)
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
    guess at a pgid."""
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
    if ticks is not None and (type(ticks) is not int or ticks < 0):
        faults.append(f"leader_start_ticks {ticks!r} is not a tick count or null")
    if faults:
        raise RunningRecordError(f"{path} is not a running record: "
                                 + "; ".join(faults))
    return RunningRecord(sid, obj["pgid"], obj["pid"], started_at, ticks, path)


def _id_faults(pgid: Any, pid: Any) -> list[str]:
    """A group to kill is a positive id above 1: 0 would signal the
    signaller's own group, 1 is init's, and a bool is not an id."""
    faults = []
    for name, value in (("pgid", pgid), ("pid", pid)):
        if type(value) is not int or value <= 1:
            faults.append(f"{name} {value!r} is not a process id above 1")
    return faults


# ---------------------------------------------------------------------------
# 4. The process-level kill
# ---------------------------------------------------------------------------


@dataclass
class ProcessStep:
    """What the kill did to the recorded group, and what is left of it.

    `dead` is True only when no member was found alive at the end (or the
    record was stale: the number now leads another process, so the recorded
    group is gone). `survivors` names every member still alive — [] when
    dead. `error` names why the step could not finish (a malformed record,
    members that cannot be enumerated, the kill's own group)."""

    record: RunningRecord | None = None
    record_path: Path | None = None
    signals: list[str] = field(default_factory=list)
    dead: bool = False
    survivors: list[int] = field(default_factory=list)
    stale: bool = False
    record_cleared: bool = False
    error: str | None = None

    @property
    def signalled(self) -> bool:
        return bool(self.signals)

    def as_json(self) -> dict[str, Any]:
        r = self.record
        return {"pgid": None if r is None else r.pgid,
                "pid": None if r is None else r.pid,
                "started_at": None if r is None else r.started_at,
                "signalled": self.signalled, "signals": list(self.signals),
                "dead": self.dead, "survivors": list(self.survivors),
                "stale": self.stale, "record_cleared": self.record_cleared,
                "record": None if self.record_path is None else str(self.record_path),
                "error": self.error}


def kill_group(record: RunningRecord, *, grace: float = DEFAULT_GRACE_SECONDS,
               wait: float = KILL_WAIT_SECONDS,
               proc_root: Path = process.PROC_ROOT) -> ProcessStep:
    """Kill the recorded process group and wait until no member is alive.

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
    step = ProcessStep(record=record, record_path=record.path)
    pgid = record.pgid
    own = os.getpgrp()
    if pgid == own:
        step.error = (f"the recorded process group {pgid} is twine kill's own; it "
                      "is not signalled — run twine kill from another shell")
        return step
    if record.leader_start_ticks is not None:
        now = process.read_stat(pgid, proc_root)
        if now is not None and now.start_ticks != record.leader_start_ticks:
            step.stale, step.dead = True, True
            log.warning("running record for %s is stale: pid %d started at tick %d, "
                        "the record says %d; the recorded group is gone and nothing "
                        "is signalled", record.sid, pgid, now.start_ticks,
                        record.leader_start_ticks)
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

# bale 0.4.45's refusal when the session reached HOLD (cmd_unlock, bin/bale
# lines 3234-3479, read by probe twine-unlock-code): `branch bale/<sid>
# exists — this session reached HOLD. Use `bale revert <sid>` …`. Twine
# reads only this prefix of bale's stderr, to hand the operator bale's own
# remedy; every other refusal is surfaced verbatim.
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

    ok exactly when the abort request stands, no process of the recorded
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
        is left to do. Members alive: the signal to their group. The closure
        refused or not reached: bale's own remedy for a HOLD branch, else the
        unlock line. None when no one line finishes it safely — a malformed
        running record names no group, and a close must wait until the
        runtime is found and stopped (the reason says so) — and when the kill
        was refused before anything was done: fix the named fault and run
        twine kill again."""
        stop = self.stopped_at
        if stop is None or stop == "refused":
            return None
        p = self.process
        if p is not None and not self.process_done:
            # Whatever else stopped, a group that may be alive comes first:
            # never hand out a close while a member of it may live.
            return None if p.record is None else f"kill -KILL -- -{p.record.pgid}"
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
        elif p.record is None:
            lines.append(f"  process: NOT KILLED — {p.error}")
        else:
            did = ", ".join(p.signals) if p.signals else "nothing signalled"
            if p.stale:
                state = "stale record (the number now leads another process); the group is gone"
            elif p.dead:
                state = "no member alive"
            elif p.survivors:
                state = "survivors " + ", ".join(str(s) for s in p.survivors)
            else:
                state = p.error or "not known to be gone"
            lines.append(f"  process: group {p.record.pgid}: {did}; {state}")
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


def kill_session(state_dir: Path, sid: str, *, run: process.Runner,
                 executable: bale.Executable,
                 cwd: str | Path, env: Mapping[str, str],
                 grace: float = DEFAULT_GRACE_SECONDS, wait: float = KILL_WAIT_SECONDS,
                 report: KillReport | None = None,
                 proc_root: Path = process.PROC_ROOT) -> KillReport:
    """`twine kill <sid>`'s three steps, in order, each reported (brief item 1):

    1. request the between-calls abort (durable, idempotent);
    2. kill the recorded process group, if a running record exists, and wait
       until no member is alive — a malformed record is a named refusal of
       this step, never a guess; once the group is confirmed gone the record
       (a cache) is removed so a later kill cannot signal a reused number;
    3. close the session in bale `aborted` (close_aborted) — only when the
       abort request stands and no process is alive or none was recorded.

    The caller has validated the sid, the state directory, `cwd` and the
    grace, and checked the pin before anything was done (close_aborted
    checks it again). A report the caller started (the verb's, with its
    locations) may be passed in."""
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
        report.process = ProcessStep(record_path=running_path(state_dir, sid),
                                     error=f"the running record is malformed, so no "
                                           f"process group is known to kill — find and "
                                           f"stop the session's runtime yourself before "
                                           f"closing it: {exc}")
        log.error("kill %s: %s", sid, report.process.error)
        record = None
    if record is not None:
        report.process = kill_group(record, grace=grace, wait=wait, proc_root=proc_root)
        if report.process.dead and report.process.error is None:
            try:
                report.process.record_cleared = clear_running(state_dir, sid)
            except KillError as exc:
                log.warning("kill %s: the group is gone but %s (a cache; "
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

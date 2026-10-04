"""The run seam: the one way a twine handler runs a subprocess (Arc 1
session 2b-i).

A handler never imports subprocess. It calls `ctx.run(argv, …)` — the
`run` field of twine.cli.Context — whose default is `run_process` below,
and tests inject a double with the same signature. `twine carry probe`
uses it for bash; session 2b-ii uses it for `bale relay` and
`bale apply --dry-run --json`, and its fixture player answers through
the same signature. The contract page (claude/context/cli-contract.md
§10.6) states the signature as the seam later sessions build on.

What the default runner guarantees:

  - the child starts in a new session, so it leads its own process
    group; on a timeout, on the stdout cap, and when the child itself
    exits, the whole group is sent SIGKILL — a `sleep` or a pipeline
    the child started cannot outlive the run or hold its pipes open
    (a grandchild that calls setsid itself leaves the group; the
    runner then waits a short grace for the pipes, gives up, and logs
    it — this is not a sandbox);
  - stdout is captured up to `stdout_cap` bytes; past the cap the group
    is killed and `stdout_capped` is set (memory stays bounded, and a
    probe that floods is stopped rather than drained until the timeout);
  - stderr is captured up to `stderr_cap` bytes and drained, never
    blocking the child; what was dropped is flagged;
  - stdin is the bytes given, or /dev/null — never the caller's own
    stdin, which `twine carry probe -` may already have consumed;
  - a failure to start (no such executable, an argv too long) raises
    RunError; everything after the start is a RunResult, never an
    exception;
  - since Arc 1 session 5b, the group is SIGKILLed however the run
    ended, and the run returns only once no member of it is alive, or
    after GROUP_GRACE_SECONDS more with the survivors named in
    `group_survivors` and logged — so a caller that reads a RunResult can
    rely on the group being gone (members are enumerated from /proc;
    where there is none, the wait is skipped and logged, and
    `group_survivors` is empty). Both happen before the child is reaped,
    while its zombie still holds the group id.

Section 3's process-group helpers are also what `twine kill` (twine/kill.py,
session 5b) signals and waits with: they read /proc and send signals, and
spawn nothing.

Sections:
  1. The result and the signature   (~line 65)
  2. The default runner             (~line 145)
  3. Process-group helpers          (~line 310)
"""

from __future__ import annotations

import logging
import os
import selectors
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, Sequence

log = logging.getLogger("twine.process")

# ---------------------------------------------------------------------------
# 1. The result and the signature
# ---------------------------------------------------------------------------

# Defaults a caller may override per call. The stdout cap a verb enforces
# is the verb's own number (carry probe states its own); this default
# only keeps an uncapped call from holding unbounded memory.
DEFAULT_STDOUT_CAP = 16 * 1024 * 1024
DEFAULT_STDERR_CAP = 64 * 1024
READ_CHUNK = 65536
# After the group is killed (or the child exited), how long to wait for
# the pipes to reach EOF before giving up on an escaped grandchild.
PIPE_GRACE_SECONDS = 2.0
# After the pipes close and the child is reaped, how long the runner waits
# for every other member of the group to be gone (session 5b). A SIGKILLed
# process closes its descriptors before the kernel marks it a zombie, so
# without this a caller could see the pipes close while a member still runs.
GROUP_GRACE_SECONDS = 2.0
POLL_SECONDS = 0.05
# Where live processes are enumerated (Linux procfs).
PROC_ROOT = Path("/proc")


@dataclass(frozen=True)
class RunResult:
    """What one run produced.

    exit_code       the child's exit status; None when the runner killed
                    it (timeout or stdout cap). A child killed by a
                    signal the runner did not send reports the negative
                    signal number, as subprocess does.
    stdout, stderr  the captured bytes (stdout at most the cap; stderr
                    at most its cap)
    timed_out       the timeout expired and the group was killed
    stdout_capped   stdout passed the cap and the group was killed
    stderr_truncated  stderr passed its cap; the rest was drained and
                    dropped
    duration_seconds  wall time from spawn to the run returning
    group_survivors   pids of the child's process group still alive when
                    the run returned (after GROUP_GRACE_SECONDS); () when
                    the whole group is gone — or could not be enumerated
                    (no /proc), which is logged (session 5b)
    """

    argv: tuple[str, ...]
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    stdout_capped: bool = False
    stderr_truncated: bool = False
    duration_seconds: float = 0.0
    group_survivors: tuple[int, ...] = ()

    @property
    def killed(self) -> bool:
        return self.timed_out or self.stdout_capped


class RunError(OSError):
    """The process could not be started at all (nothing ran)."""


def runner_confines(runner: object) -> bool:
    """Whether `runner` confines what it runs — the one switch point a
    verb's `confined` flag reads (accepted from session 2b-i's Proposals,
    prepared in 2b-ii). A runner declares it with a `confines` attribute;
    one that does not say does not confine. Arc 2's sandbox runner — a
    wrapper around run_process — is what will declare True; nothing else
    may infer the flag."""
    return getattr(runner, "confines", False) is True


class Runner(Protocol):
    """The seam's signature — every runner, real or double, takes this."""

    def __call__(self, argv: Sequence[str], *, cwd: str | Path | None = None,
                 stdin: bytes | None = None, timeout: float | None = None,
                 env: Mapping[str, str] | None = None,
                 stdout_cap: int | None = None) -> RunResult: ...


# ---------------------------------------------------------------------------
# 2. The default runner
# ---------------------------------------------------------------------------


def run_process(argv: Sequence[str], *, cwd: str | Path | None = None,
                stdin: bytes | None = None, timeout: float | None = None,
                env: Mapping[str, str] | None = None,
                stdout_cap: int | None = None) -> RunResult:
    """Spawn `argv` for real and collect it under the guarantees above.

    `cwd` None inherits the caller's directory; `env` None inherits the
    caller's environment (a handler passes ctx.env); `timeout` None
    waits forever; `stdout_cap` None is DEFAULT_STDOUT_CAP.
    """
    argv = tuple(str(a) for a in argv)
    if not argv:
        raise RunError("run: empty argv")
    cap = DEFAULT_STDOUT_CAP if stdout_cap is None else int(stdout_cap)
    log.info("run: %s (cwd=%s, timeout=%s, stdout cap=%d bytes)",
             argv[0], cwd or ".", timeout, cap)
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv, cwd=None if cwd is None else str(cwd),
            env=None if env is None else dict(env),
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True)
    except OSError as exc:
        log.error("run: cannot start %s: %s", argv[0], exc)
        raise RunError(exc.errno, f"cannot start {argv[0]}: "
                                  f"{exc.strerror or exc}") from exc
    feeder = _feed_stdin(proc, stdin) if stdin is not None else None
    collected = _collect(proc, cap, DEFAULT_STDERR_CAP,
                         None if timeout is None else started + timeout)
    if feeder is not None:
        feeder.join(timeout=PIPE_GRACE_SECONDS)
    code = proc.returncode
    # _collect SIGKILLed the group and waited for it before reaping the
    # child; any member still alive is named, never hidden.
    survivors = collected.group_survivors
    if survivors:
        log.error("run: process group %d still has live members %s %.1fs after "
                  "SIGKILL", proc.pid, survivors, GROUP_GRACE_SECONDS)
    result = RunResult(
        argv=argv,
        exit_code=None if collected.killed else code,
        stdout=bytes(collected.stdout), stderr=bytes(collected.stderr),
        timed_out=collected.timed_out, stdout_capped=collected.capped,
        stderr_truncated=collected.stderr_truncated,
        duration_seconds=round(time.monotonic() - started, 3),
        group_survivors=tuple(survivors))
    log.info("run: %s finished: exit=%s timed_out=%s capped=%s %.3fs "
             "(%d stdout bytes, %d stderr bytes)", argv[0], result.exit_code,
             result.timed_out, result.stdout_capped, result.duration_seconds,
             len(result.stdout), len(result.stderr))
    return result


# The default runner confines nothing: the child gets the caller's
# privileges, environment, files and network (cli-contract.md §10.5).
run_process.confines = False  # type: ignore[attr-defined]


@dataclass
class _Collected:
    stdout: bytearray
    stderr: bytearray
    timed_out: bool = False
    capped: bool = False
    stderr_truncated: bool = False
    group_survivors: list[int] = field(default_factory=list)

    @property
    def killed(self) -> bool:
        return self.timed_out or self.capped


def _feed_stdin(proc: subprocess.Popen, data: bytes) -> threading.Thread:
    """Write stdin from a thread so a child that writes before it reads
    can never deadlock against us; a child that exits early (EPIPE) is
    not an error of ours."""
    def feed() -> None:
        try:
            proc.stdin.write(data)
        except (BrokenPipeError, ValueError, OSError) as exc:
            log.debug("run: stdin not fully written: %s", exc)
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass
    thread = threading.Thread(target=feed, name="twine-run-stdin", daemon=True)
    thread.start()
    return thread


def _collect(proc: subprocess.Popen, stdout_cap: int, stderr_cap: int,
             deadline: float | None) -> _Collected:
    """Read both pipes until EOF, the deadline, or the stdout cap — then
    make sure nothing of the child's group is left running."""
    got = _Collected(bytearray(), bytearray())
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ, "stdout")
    sel.register(proc.stderr, selectors.EVENT_READ, "stderr")
    group_killed = False
    grace_until: float | None = None
    try:
        while sel.get_map():
            now = time.monotonic()
            if not group_killed and deadline is not None and now >= deadline:
                got.timed_out = True
                log.warning("run: timeout expired; killing process group %d", proc.pid)
                _kill_group(proc)
                group_killed = True
            if not group_killed and _exited(proc):
                # The child is done; anything it left behind in its group
                # (a backgrounded sleep holding our pipe) goes with it.
                _kill_group(proc)
                group_killed = True
            if group_killed and grace_until is None:
                grace_until = now + PIPE_GRACE_SECONDS
            if grace_until is not None and now >= grace_until:
                log.warning("run: pipes still open %.1fs after the group was "
                            "killed — a process left the group (setsid?); "
                            "closing our ends", PIPE_GRACE_SECONDS)
                break
            for key, _ in sel.select(timeout=POLL_SECONDS):
                chunk = os.read(key.fileobj.fileno(), READ_CHUNK)
                if not chunk:
                    sel.unregister(key.fileobj)
                    continue
                if key.data == "stdout":
                    room = stdout_cap - len(got.stdout)
                    got.stdout += chunk[:max(room, 0)]
                    if len(chunk) > room and not got.capped:
                        got.capped = True
                        log.warning("run: stdout passed the cap of %d bytes; "
                                    "killing process group %d", stdout_cap, proc.pid)
                        if not group_killed:
                            _kill_group(proc)
                            group_killed = True
                else:
                    room = stderr_cap - len(got.stderr)
                    if room > 0:
                        got.stderr += chunk[:room]
                    if len(chunk) > room:
                        got.stderr_truncated = True
    finally:
        sel.close()
        for pipe in (proc.stdout, proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass
        # Always, whatever ended the loop: the pipes can reach EOF in the
        # same instant the child exits, before the loop saw the exit, and a
        # member that closed its descriptors (`sleep … >/dev/null &`) would
        # then outlive the run (found by session 5b's review). The child is
        # not reaped yet — _exited never reaps — so its zombie still holds
        # the group id: the SIGKILL and the wait below cannot reach a group
        # that reused the number. A child that closes its pipes just before
        # it exits (coreutils `cat` does, in its exit handler) is given up to
        # PIPE_GRACE_SECONDS to exit on its own first, so a clean exit is
        # never reported as the runner's SIGKILL; only a timeout or the cap
        # skips the wait.
        if not got.killed:
            _await_exit(proc, PIPE_GRACE_SECONDS)
        _kill_group(proc)
        got.group_survivors = wait_group_gone(proc.pid, GROUP_GRACE_SECONDS)
        _reap(proc)
    return got


# ---------------------------------------------------------------------------
# 3. Process-group helpers
# ---------------------------------------------------------------------------


def _kill_group(proc: subprocess.Popen) -> None:
    """SIGKILL the child's process group (it leads one: start_new_session).
    A group already gone is fine; where killpg does not exist, the child
    alone is killed and that limit is logged."""
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        log.warning("run: os.killpg unavailable; killing the child only")
        try:
            proc.kill()
        except OSError:
            pass
        return
    try:
        killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        log.debug("run: process group %d already gone", proc.pid)
    except PermissionError as exc:
        log.warning("run: cannot signal process group %d: %s", proc.pid, exc)


def _exited(proc: subprocess.Popen) -> bool:
    """Whether the child has exited, without reaping it: its zombie keeps
    holding the process-group id until _reap, so the group can still be
    signalled by that id with no risk of reaching a group that reused it.
    Where waitid is unavailable, falls back to Popen.poll (which reaps)."""
    if proc.returncode is not None:
        return True
    waitid = getattr(os, "waitid", None)
    if waitid is None:
        return proc.poll() is not None
    try:
        info = waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:
        return proc.poll() is not None
    return info is not None


def _await_exit(proc: subprocess.Popen, timeout: float) -> bool:
    """Poll, without reaping, until the child has exited or `timeout`
    seconds pass. True when it exited."""
    deadline = time.monotonic() + timeout
    while not _exited(proc):
        if time.monotonic() >= deadline:
            log.warning("run: child %d closed its pipes but is still running "
                        "%.1fs later; killing its group", proc.pid, timeout)
            return False
        time.sleep(0.005)
    return True


def _reap(proc: subprocess.Popen) -> None:
    """Collect the child's exit status so no zombie is left behind."""
    try:
        proc.wait(timeout=PIPE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        log.error("run: child %d did not exit after SIGKILL", proc.pid)


# --- Live members of a process group (session 5b) -------------------------
#
# `twine kill` and the runner's own wait both ask one question: which
# processes of group G are still alive? A zombie (exited, not yet reaped —
# a container's PID 1 may never reap an orphan) has run its last
# instruction and holds nothing open, so it counts as dead; an `X` (dead)
# entry likewise. Members are read from /proc/<pid>/stat, Linux's procfs:
# field 3 is the state, field 5 the process group, field 22 the start time
# in clock ticks since boot.

_STAT_STATE, _STAT_PGRP, _STAT_STARTTIME = 0, 2, 19   # indexes after "(comm)"
DEAD_STATES = frozenset({"Z", "X", "x"})


@dataclass(frozen=True)
class ProcStat:
    """What /proc/<pid>/stat says about one process."""

    pid: int
    state: str
    pgid: int
    start_ticks: int

    @property
    def alive(self) -> bool:
        return self.state not in DEAD_STATES


def read_stat(pid: int, proc_root: Path = PROC_ROOT) -> ProcStat | None:
    """/proc/<pid>/stat parsed, or None when there is no such process (or
    its entry vanished while being read). The command name may hold spaces
    and parentheses, so the fields are read after its last `)`."""
    try:
        text = (proc_root / str(pid) / "stat").read_text(encoding="ascii",
                                                         errors="replace")
        fields = text.rsplit(")", 1)[1].split()
        return ProcStat(pid, fields[_STAT_STATE], int(fields[_STAT_PGRP]),
                        int(fields[_STAT_STARTTIME]))
    except (OSError, IndexError, ValueError):
        return None


def procfs_available(proc_root: Path = PROC_ROOT) -> bool:
    """Whether live processes can be enumerated here (a Linux procfs)."""
    return (proc_root / "self" / "stat").is_file()


def group_members(pgid: int, proc_root: Path = PROC_ROOT) -> list[int] | None:
    """The live (non-zombie) pids whose process group is `pgid`, sorted;
    [] when there are none. None when members cannot be enumerated (no
    procfs) — the caller must then not claim the group is gone."""
    if not procfs_available(proc_root):
        log.warning("no procfs at %s: process group %d's members cannot be "
                    "enumerated", proc_root, pgid)
        return None
    members = []
    try:
        entries = list(proc_root.iterdir())
    except OSError as exc:
        log.warning("cannot list %s: %s", proc_root, exc)
        return None
    for entry in entries:
        if not entry.name.isdigit():
            continue
        st = read_stat(int(entry.name), proc_root)
        if st is not None and st.pgid == pgid and st.alive:
            members.append(st.pid)
    return sorted(members)


def start_ticks(pid: int, proc_root: Path = PROC_ROOT) -> int | None:
    """The process's start time in clock ticks since boot, or None when it
    does not exist or there is no procfs. With the pid, it identifies one
    process across pid reuse."""
    st = read_stat(pid, proc_root)
    return None if st is None else st.start_ticks


def signal_group(pgid: int, signum: int) -> str | None:
    """Send `signum` to process group `pgid`. None when it was delivered;
    otherwise why not ("gone" when no process is in the group, or the
    error). Never signals group 0 or 1, or a negative id — killpg(0) is the
    caller's own group."""
    if pgid <= 1:
        raise ValueError(f"refusing to signal process group {pgid}")
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        return "os.killpg is unavailable on this platform"
    try:
        killpg(pgid, signum)
    except ProcessLookupError:
        return "gone"
    except PermissionError as exc:
        log.warning("cannot signal process group %d: %s", pgid, exc)
        return f"not permitted: {exc.strerror or exc}"
    except OSError as exc:
        log.warning("cannot signal process group %d: %s", pgid, exc)
        return f"{exc.strerror or exc}"
    log.info("sent %s to process group %d", signal.Signals(signum).name, pgid)
    return None


def wait_group_gone(pgid: int, timeout: float, *, poll: float = POLL_SECONDS,
                    proc_root: Path = PROC_ROOT) -> list[int]:
    """Poll until no member of `pgid` is alive or `timeout` seconds pass.
    Returns the survivors — [] when the group is gone. When members cannot
    be enumerated (no procfs) it returns [] at once, having logged that
    it could not look; a caller that must be sure (twine kill) checks
    group_members for None itself."""
    deadline = time.monotonic() + max(timeout, 0.0)
    while True:
        members = group_members(pgid, proc_root)
        if not members:
            return []
        if time.monotonic() >= deadline:
            return members
        time.sleep(poll)


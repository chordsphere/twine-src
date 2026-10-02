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
    exception.

Sections:
  1. The result and the signature   (~line 50)
  2. The default runner             (~line 115)
  3. Process-group helpers          (~line 265)
"""

from __future__ import annotations

import logging
import os
import selectors
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
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
POLL_SECONDS = 0.05


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
    duration_seconds  wall time from spawn to the last pipe closing
    """

    argv: tuple[str, ...]
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False
    stdout_capped: bool = False
    stderr_truncated: bool = False
    duration_seconds: float = 0.0

    @property
    def killed(self) -> bool:
        return self.timed_out or self.stdout_capped


class RunError(OSError):
    """The process could not be started at all (nothing ran)."""


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
    result = RunResult(
        argv=argv,
        exit_code=None if collected.killed else code,
        stdout=bytes(collected.stdout), stderr=bytes(collected.stderr),
        timed_out=collected.timed_out, stdout_capped=collected.capped,
        stderr_truncated=collected.stderr_truncated,
        duration_seconds=round(time.monotonic() - started, 3))
    log.info("run: %s finished: exit=%s timed_out=%s capped=%s %.3fs "
             "(%d stdout bytes, %d stderr bytes)", argv[0], result.exit_code,
             result.timed_out, result.stdout_capped, result.duration_seconds,
             len(result.stdout), len(result.stderr))
    return result


@dataclass
class _Collected:
    stdout: bytearray
    stderr: bytearray
    timed_out: bool = False
    capped: bool = False
    stderr_truncated: bool = False

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
            if not group_killed and proc.poll() is not None:
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
        if proc.poll() is None:
            _kill_group(proc)
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


def _reap(proc: subprocess.Popen) -> None:
    """Collect the child's exit status so no zombie is left behind."""
    try:
        proc.wait(timeout=PIPE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        log.error("run: child %d did not exit after SIGKILL", proc.pid)

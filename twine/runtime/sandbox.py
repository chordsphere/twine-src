"""The sandbox: the per-sid cage a worker's tools run in (twine-seed.md
§4.3 "Sandbox", D10, D15; Arc 2 R3 — claude/context/runtime-contract.md §6).

One sandbox per session id, created by `Sandbox.create(state_dir, sid,
repo=…)`:

  - **a home**, `<state-dir>/sandbox/<sid>/home/` (created, with `tmp/`
    inside it): every file tool resolves its path against it and is refused,
    as a tool error naming the cage, when the path is absolute, carries a
    `..` component, or — symlinks resolved — lands outside it (`resolve`);
  - **a minimal environment**: PATH, HOME (the home), TMPDIR (its `tmp/`)
    and LANG, and nothing else the sandbox was not told to pass. PATH and
    LANG come from the process environment by name only
    (twine.process.inherited_environment); `env=` replaces those two with
    what the caller passes. **ANTHROPIC_API_KEY never reaches the cage** —
    dropped, and logged, even when a caller passes it;
  - **network off through `unshare` where available**: at creation the
    sandbox runs `unshare -rn true` through the run seam; when it exits 0,
    every argv its runner runs is wrapped `unshare -rn -- …` and the
    sandbox reports `network: "off"`; otherwise `network: "unconfined"` and
    the reason. `-rn` alone at R3: a user namespace (so no privilege is
    needed) and an empty network namespace. No mount or pid namespace — the
    shell is cwd'd in the home, not confined to it; the file tools are what
    is path-confined (runtime-contract.md §6.3 says so);
  - **`confines`**, cli-contract.md §10.5's switch: the sandbox's runner
    (`SandboxRunner`, a wrapper around the runner it is given) declares
    `confines` exactly when the network is off, and the sandbox reads it
    back through twine.process.runner_confines — set nowhere else;
  - **the kill-switch hook** (D15, cli-contract.md §14.4): everything the
    sandbox spawns goes through `spawn`, which hands the seam
    `on_spawn=lambda pid: register_group(state_dir, sid, pid)` when a
    running record for the sid exists, and `clear_group`s the group after a
    run that returned with `group_survivors` empty. Without a record (a
    test, the architect at a terminal) the run proceeds unregistered and
    that is logged; a record that cannot be read refuses the spawn (fail
    closed: a group the kill could not find must not start).

Nothing here imports a process-spawning module, `os`, or reads the process
environment (a test walks twine/runtime/ for all three): processes go through
the run seam it is handed, the environment through the seam's module.

Sections:
  1. Names and errors              (~line 70)
  2. The environment               (~line 110)
  3. The runner                    (~line 150)
  4. The sandbox                   (~line 200)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from twine import kill, process

log = logging.getLogger("twine.runtime.sandbox")

# The runtime implements this capability itself, not through an adapter:
# twine/runtime/capabilities.toml's `implemented_by` names this module, and
# the registry holds the declaration to this tuple (runtime-contract.md §2.3).
IMPLEMENTS = ("sandboxing",)

# ---------------------------------------------------------------------------
# 1. Names and errors
# ---------------------------------------------------------------------------

SANDBOX_SUBDIR = "sandbox"
HOME_NAME = "home"
TMP_NAME = "tmp"
DIR_MODE = 0o700

# How long a tool may run, at most, unless the sandbox is created with
# another maximum; a tool's own timeout is capped by it.
DEFAULT_MAX_TIMEOUT_SECONDS = 600.0

# The network rule. `unshare -rn`: a new user namespace mapping the caller
# to root inside it (no privilege needed where unprivileged user namespaces
# are allowed) and a new, empty network namespace (loopback only, down).
UNSHARE = "unshare"
UNSHARE_FLAGS = ("-rn",)
NETWORK_OFF = "off"
NETWORK_UNCONFINED = "unconfined"
# The detection run at creation: a few seconds at most, a few bytes of output.
DETECT_TIMEOUT_SECONDS = 10.0
DETECT_STDOUT_CAP = 4096


class SandboxError(ValueError):
    """A sandbox that cannot be created as asked (the caller's fault: a bad
    sid, a repo that is not a directory, a maximum timeout that is not a
    positive number, a home that cannot be made, a running record that
    cannot be read)."""


class CageError(ValueError):
    """A path a file tool may not touch; the message names the cage. The
    tools return it as an error result, never raise it."""


class SpawnRefused(RuntimeError):
    """The kill-switch could not stand behind a spawn: the running record
    could not be read, or the spawn hook could not register the group (the
    seam then killed the child before it ran). The tools return it as an
    error result."""


# ---------------------------------------------------------------------------
# 2. The environment
# ---------------------------------------------------------------------------

# What the cage inherits from the process environment, by name, when the
# sandbox is told nothing else — and the fallbacks when even those are unset.
INHERITED = ("PATH", "LANG")
FALLBACK_PATH = "/usr/local/bin:/usr/bin:/bin"
FALLBACK_LANG = "C.UTF-8"
# Never in the cage, whoever passes it.
NEVER_PASSED = frozenset({"ANTHROPIC_API_KEY"})


def cage_environment(home: Path, env: Mapping[str, str] | None = None) -> dict[str, str]:
    """The cage's environment: what the sandbox was told to pass (`env`, or
    PATH and LANG inherited by name), with HOME and TMPDIR set to the home
    and its `tmp/` over anything given, PATH and LANG filled from the
    fallbacks when absent, and every NEVER_PASSED name dropped (logged).
    Raises SandboxError for a variable that is not a string pair."""
    given = dict(process.inherited_environment(INHERITED) if env is None else env)
    faults = [f"{name!r}={value!r}" for name, value in given.items()
              if not isinstance(name, str) or not isinstance(value, str)
              or not name or "=" in name or "\0" in name or "\0" in value]
    if faults:
        raise SandboxError("the sandbox's environment must map names to strings; "
                           "refused: " + ", ".join(faults))
    for name in sorted(NEVER_PASSED & set(given)):
        log.warning("sandbox: %s was offered to the cage's environment and is "
                    "dropped: it never reaches the cage", name)
        del given[name]
    cage = dict(given)
    cage.setdefault("PATH", FALLBACK_PATH)
    cage.setdefault("LANG", FALLBACK_LANG)
    cage["HOME"] = str(home)
    cage["TMPDIR"] = str(home / TMP_NAME)
    return cage


# ---------------------------------------------------------------------------
# 3. The runner
# ---------------------------------------------------------------------------


class SandboxRunner:
    """The sandbox's runner — a wrapper around the runner it is given
    (twine.process.run_process by default) with the seam's whole signature.
    When the network is off it wraps every argv `unshare -rn -- <argv>` and
    declares `confines` true: the one runner that does (cli-contract.md
    §10.5's switch). Otherwise it passes argv through and declares false."""

    def __init__(self, inner: process.Runner, *, network_off: bool) -> None:
        self.inner = inner
        self.confines = network_off is True

    def wrap(self, argv: Sequence[str]) -> tuple[str, ...]:
        """The argv the inner runner is handed."""
        argv = tuple(str(a) for a in argv)
        return (UNSHARE, *UNSHARE_FLAGS, "--", *argv) if self.confines else argv

    def __call__(self, argv: Sequence[str], *, cwd: str | Path | None = None,
                 stdin: bytes | None = None, timeout: float | None = None,
                 env: Mapping[str, str] | None = None,
                 stdout_cap: int | None = None,
                 on_spawn: process.SpawnHook | None = None) -> process.RunResult:
        return self.inner(self.wrap(argv), cwd=cwd, stdin=stdin, timeout=timeout,
                          env=env, stdout_cap=stdout_cap, on_spawn=on_spawn)


# ---------------------------------------------------------------------------
# 4. The sandbox
# ---------------------------------------------------------------------------


@dataclass
class Sandbox:
    """One session's cage. Build it with `Sandbox.create`; the fields are
    what creation found.

    sid, state_dir  the session, and the state directory its home and its
                    running record live under
    home            <state-dir>/sandbox/<sid>/home, resolved — the cage
    repo            the real repository, resolved: where `probe` runs (D13)
    run             the run seam it was handed — unwrapped; `probe` runs
                    through it, since a probe leaves the cage by design
    runner          the SandboxRunner around `run`: what `shell` runs through
    env             the cage's environment (read-only)
    max_timeout     the longest any tool may run, in seconds
    network         "off" or "unconfined"
    network_reason  why it is unconfined; None when off
    """

    sid: str
    state_dir: Path
    home: Path
    repo: Path
    run: process.Runner
    runner: SandboxRunner
    env: Mapping[str, str]
    max_timeout: float
    network: str
    network_reason: str | None = None
    # What the last spawn did with the kill-switch: its argv, the groups it
    # registered and whether they were cleared (None when none registered).
    last_spawn: dict[str, Any] | None = field(default=None, repr=False)

    # --- creation ---------------------------------------------------------

    @classmethod
    def create(cls, state_dir: Path, sid: str, *, repo: Path,
               run: process.Runner = process.run_process,
               env: Mapping[str, str] | None = None,
               max_timeout: float = DEFAULT_MAX_TIMEOUT_SECONDS) -> "Sandbox":
        """Make (or reuse) the session's home under `state_dir`, build the
        cage's environment, and detect whether the network can be turned off
        here. Raises SandboxError for a bad sid, a repo that is not a
        directory, a maximum that is not a positive finite number, a home
        that cannot be made, or a running record that cannot be read."""
        if not kill.is_sid(sid):
            raise SandboxError(f"session id {sid!r} is not one twine names a sandbox by")
        if isinstance(max_timeout, bool) or not isinstance(max_timeout, (int, float)) \
                or not math.isfinite(max_timeout) or max_timeout <= 0:
            raise SandboxError(f"max_timeout must be a positive number of seconds, "
                               f"not {max_timeout!r}")
        repo_path = Path(repo).expanduser()
        if not repo_path.is_dir():
            raise SandboxError(f"repo {repo} is not a directory")
        home = Path(state_dir) / SANDBOX_SUBDIR / sid / HOME_NAME
        try:
            # The mode applies to the directory named, never to the parents
            # mkdir creates: the home and its tmp/ are each made 0700.
            home.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
            (home / TMP_NAME).mkdir(mode=DIR_MODE, exist_ok=True)
        except OSError as exc:
            raise SandboxError(f"cannot make the sandbox home {home}: "
                               f"{exc.strerror or exc}") from exc
        home = home.resolve()
        cage_env = MappingProxyType(cage_environment(home, env))
        sandbox = cls(sid=sid, state_dir=Path(state_dir), home=home,
                      repo=repo_path.resolve(), run=run,
                      runner=SandboxRunner(run, network_off=False), env=cage_env,
                      max_timeout=float(max_timeout), network=NETWORK_UNCONFINED,
                      network_reason="not yet detected")
        sandbox._detect_network()
        log.info("sandbox for %s: home %s, network %s%s, max timeout %gs", sid, home,
                 sandbox.network,
                 f" ({sandbox.network_reason})" if sandbox.network_reason else "",
                 sandbox.max_timeout)
        return sandbox

    def _detect_network(self) -> None:
        """Try `unshare -rn true` through the seam (registered like any spawn).
        Exit 0: the runner wraps from now on and the network is off. Anything
        else — no `unshare`, a refusal (no unprivileged user namespaces), a
        timeout — leaves it unconfined, the reason named."""
        argv = (UNSHARE, *UNSHARE_FLAGS, "true")
        try:
            result = self.spawn(argv, runner=self.run, cwd=self.home,
                                timeout=DETECT_TIMEOUT_SECONDS,
                                stdout_cap=DETECT_STDOUT_CAP)
        except process.RunError as exc:
            self._unconfined(f"`{' '.join(argv)}` could not start on the cage's PATH: "
                             f"{exc.strerror or exc}")
            return
        except SpawnRefused as exc:
            raise SandboxError(f"cannot detect the network rule: {exc}") from exc
        if result.timed_out:
            self._unconfined(f"`{' '.join(argv)}` did not finish within "
                             f"{DETECT_TIMEOUT_SECONDS:g}s")
            return
        if result.exit_code != 0:
            said = result.stderr.decode("utf-8", errors="replace").strip()
            said = said.splitlines()[0][:200] if said else "no message"
            self._unconfined(f"`{' '.join(argv)}` exited {result.exit_code} "
                             f"({said}) — unprivileged user or network namespaces are "
                             "not available here")
            return
        self.runner = SandboxRunner(self.run, network_off=True)
        self.network, self.network_reason = NETWORK_OFF, None

    def _unconfined(self, reason: str) -> None:
        log.warning("sandbox for %s: network unconfined: %s", self.sid, reason)
        self.runner = SandboxRunner(self.run, network_off=False)
        self.network, self.network_reason = NETWORK_UNCONFINED, reason

    # --- what it reports --------------------------------------------------

    @property
    def confines(self) -> bool:
        """Read from the runner — cli-contract.md §10.5's one switch point."""
        return process.runner_confines(self.runner)

    @property
    def tmp(self) -> Path:
        return self.home / TMP_NAME

    def as_json(self) -> dict[str, Any]:
        """`sid`, `home`, `repo`, `network`, `confines`, `max_timeout`, and
        `reason` when the network is unconfined (runtime-contract.md §6.4)."""
        out: dict[str, Any] = {"sid": self.sid, "home": str(self.home),
                               "repo": str(self.repo), "network": self.network,
                               "confines": self.confines, "max_timeout": self.max_timeout}
        if self.network != NETWORK_OFF:
            out["reason"] = self.network_reason
        return out

    def tool_timeout(self, asked: float | None) -> float:
        """A tool's timeout: what it asked for, at most the maximum; the
        maximum when it asked for none."""
        if asked is None:
            return self.max_timeout
        if asked > self.max_timeout:
            log.info("sandbox for %s: a timeout of %gs is capped at the maximum, %gs",
                     self.sid, asked, self.max_timeout)
        return min(float(asked), self.max_timeout)

    # --- the cage's paths -------------------------------------------------

    def resolve(self, path: Any) -> Path:
        """`path` (a string, relative to the home) as an absolute path inside
        the home, symlinks resolved — or CageError naming the cage: an empty
        or non-string path, a NUL byte, an absolute path, a `..` component,
        or a path whose resolution (a symlink anywhere along it) leaves the
        home. The target need not exist."""
        if not isinstance(path, str) or not path:
            raise CageError(f"the path must be a non-empty string relative to the "
                            f"sandbox home {self.home}, not {path!r}")
        if "\0" in path:
            raise CageError("the path carries a NUL byte")
        pure = PurePosixPath(path)
        if pure.is_absolute():
            raise CageError(f"{path!r} is an absolute path; the tools reach only the "
                            f"sandbox home {self.home}, by paths relative to it")
        if ".." in pure.parts:
            raise CageError(f"{path!r} climbs with `..`; the tools reach only the "
                            f"sandbox home {self.home}")
        try:
            target = (self.home / pure).resolve(strict=False)
        except (OSError, RuntimeError) as exc:   # a symlink loop, an unreadable link
            raise CageError(f"{path!r} cannot be resolved inside the sandbox home "
                            f"{self.home}: {exc}") from exc
        if target != self.home and self.home not in target.parents:
            raise CageError(f"{path!r} resolves to {target}, outside the sandbox home "
                            f"{self.home} (a symlink pointing out of the cage)")
        return target

    def relative(self, target: Path) -> str:
        """A resolved path inside the home, as the tools report it."""
        rel = target.relative_to(self.home).as_posix()
        return rel if rel else "."

    # --- spawning, with the kill-switch hook --------------------------------

    def spawn(self, argv: Sequence[str], *, runner: process.Runner | None = None,
              cwd: str | Path | None = None, timeout: float | None = None,
              stdout_cap: int | None = None, env: Mapping[str, str] | None = None,
              stdin: bytes | None = None) -> process.RunResult:
        """Run `argv` through `runner` (the sandbox's runner by default) in the
        cage's environment (or `env`), with the kill-switch hook: when the
        session has a running record, the seam's `on_spawn` registers the
        child's group (twine.kill.register_group) before it does anything,
        and once the run returns with `group_survivors` empty the group is
        cleared again (clear_group) — a group with survivors stays recorded
        for `twine kill`. Without a record the run proceeds unregistered,
        logged. Raises SpawnRefused when the record cannot be read or the
        hook cannot register (the seam has killed the child), and the seam's
        RunError when nothing could start."""
        runner = self.runner if runner is None else runner
        try:
            record = kill.read_running(self.state_dir, self.sid)
        except kill.RunningRecordError as exc:
            raise SpawnRefused(f"the running record for {self.sid} cannot be read, so "
                               f"the kill-switch could not reach this process; nothing "
                               f"was started: {exc}") from exc
        registered: list[int] = []
        hook: Callable[[int], None] | None = None
        if record is None:
            log.info("sandbox for %s: no running record under %s; %s runs unregistered "
                     "with the kill-switch", self.sid, self.state_dir, argv[0])
        else:
            def hook(pid: int) -> None:
                kill.register_group(self.state_dir, self.sid, pid)
                registered.append(pid)
        try:
            result = runner(tuple(argv), cwd=cwd, stdin=stdin, timeout=timeout,
                            env=dict(self.env if env is None else env),
                            stdout_cap=stdout_cap, on_spawn=hook)
        except (kill.RunningRecordError, kill.KillError) as exc:
            raise SpawnRefused(f"the kill-switch could not register the process group "
                               f"for {self.sid}, so the process was killed before it "
                               f"ran: {exc}") from exc
        cleared: bool | None = None
        for pgid in registered:
            if result.group_survivors:
                log.warning("sandbox for %s: group %d returned with live members %s; "
                            "it stays in the running record for twine kill",
                            self.sid, pgid, list(result.group_survivors))
                cleared = False
                continue
            try:
                cleared = kill.clear_group(self.state_dir, self.sid, pgid)
            except (kill.RunningRecordError, kill.KillError) as exc:
                log.error("sandbox for %s: group %d is gone but could not be cleared "
                          "from the running record (a cache; twine kill will find it "
                          "dead): %s", self.sid, pgid, exc)
                cleared = False
        self.last_spawn = {"argv": list(argv), "registered": list(registered),
                           "cleared": cleared}
        return result

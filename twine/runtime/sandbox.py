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
  - **the cage, where the namespaces can be made** (twine-sandbox-confine):
    `unshare -rnmpf --kill-child` — a user namespace (so no privilege is
    needed), an empty network namespace, a mount namespace and a PID
    namespace — around a short `sh` script (CAGE_SCRIPT) that builds a
    private root in tmpfs and pivots into it: the system directories
    (`/usr`, `/bin`, `/sbin`, `/lib*`) read-only, a few `/etc` files copied,
    its own `/proc`, `/dev` (the ordinary devices), `/dev/shm` and an empty
    `/tmp`, and **the home bind-mounted at its own absolute path, the only
    writable tree**. Nothing else of the host is there: not the operator's
    home outside the sandbox home, not `/mnt`, not the host's `/tmp`, not the
    repository the session was opened in, not the state directory beyond the
    home. `CAP_SYS_ADMIN` and `CAP_SYS_CHROOT` are dropped from the command's
    bounding set, and when the command returns the PID namespace's init —
    the command itself — has exited, so no process it started is alive;
  - **detected at creation**: the sandbox runs the whole cage on `true`
    through the run seam. It works: `network: "off"`, `filesystem:
    "confined"`. It does not: each half is tried alone (`unshare -rn true`;
    the cage without `-n`), the sandbox keeps what works and reports the rest
    as `"unconfined"` with a reason (`reason` for the network,
    `filesystem_reason` for the filesystem), never silently;
  - **`confines`**, cli-contract.md §10.5's switch: the sandbox's runner
    (`SandboxRunner`, a wrapper around the runner it is given) declares
    `confines` exactly when the network is off **and** the filesystem is
    confined, and the sandbox reads it back through
    twine.process.runner_confines — set nowhere else;
  - **the kill-switch hook** (D15, cli-contract.md §14.4): everything the
    sandbox spawns goes through `spawn`, which hands the seam
    `on_spawn=lambda pid: register_group(state_dir, sid, pid)` when a
    running record for the sid exists, and `clear_group`s the group after a
    run that returned with `group_survivors` empty. Without a record (a
    test, the architect at a terminal) the run proceeds unregistered and
    that is logged; a record that cannot be read refuses the spawn (fail
    closed: a group the kill could not find must not start). **In the cage
    the pid the hook registers is the outer `unshare`'s**, not the
    command's (the command is the PID namespace's init, `$$` 1): `twine
    kill` signals that group — the outer `unshare`, and the init, which was
    forked into it, so SIGKILL reaches it directly; SIGTERM ends the outer
    `unshare` and `--kill-child` turns that into the init's death — and when
    the init dies the kernel kills every other process of the namespace,
    the ones that left the group with `setsid` included. A timeout is the
    same signal, from the seam.

Nothing here imports a process-spawning module, `os`, or reads the process
environment (a test walks twine/runtime/ for all three): processes go through
the run seam it is handed, the environment through the seam's module.

Sections:
  1. Names and errors
  2. The environment
  3. The cage script and the runner
  4. The sandbox
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
# The filesystem rule (twine-sandbox-confine). The cage adds a mount and a
# PID namespace (`-m`, `-p` with `--fork`, so the command is the namespace's
# init) to the user and network namespaces, and `--kill-child` so the init
# dies with the outer `unshare` — which is what the kill-switch signals.
CAGE_FLAGS_ALL = "-rnmpf"        # user, network, mount, PID (+ fork)
CAGE_FLAGS_FILESYSTEM = "-rmpf"  # the same, the network left as it is
KILL_CHILD = "--kill-child"
FILESYSTEM_CONFINED = "confined"
FILESYSTEM_UNCONFINED = "unconfined"
# Beside the home: the mount point the cage's tmpfs root is made on, an
# empty directory kept in the sid's directory (never visible in the cage).
ROOT_NAME = "root"
# The system directories the cage shows read-only, at their own paths — what
# bash, python3, tar, git and coreutils need. A symlink (a merged /usr's
# /bin -> usr/bin) is recreated as one. Anything else a call needs is named
# by that call (`Sandbox.spawn(readonly=…)`).
SYSTEM_DIRS = ("/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32")
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
# 3. The cage script and the runner
# ---------------------------------------------------------------------------

# What runs inside `unshare -rnmpf --kill-child`, as `sh -c SCRIPT twine-cage
# HOME CWD ROOT N RO1…RON COMMAND…` — every path an argument, never spliced
# into the text. It is the first process of the new PID namespace, so it
# turns into the command (`exec`), which is then the namespace's init: when
# it exits the kernel kills everything else the call started, however it
# was detached. Steps, in order — a private root in tmpfs; /tmp, /proc,
# /dev, /dev/shm; the system directories and any named read-only trees
# bound read-only at their own paths; a few /etc files copied; the home
# bound at its own path; the root and /dev made read-only; `pivot_root`
# into it and the old root detached (`chroot` where `pivot_root` is refused);
# the working directory; the capabilities that would let the command undo
# any of it dropped from its bounding set. A step that fails stops the
# script (`set -e`) with a line on stderr saying which — the creation-time
# detection reports it as the reason the filesystem is unconfined.
CAGE_SCRIPT = r"""set -e
step="starting"
trap 'status=$?; [ "$status" -eq 0 ] || echo "twine cage: stopped while $step" >&2' EXIT
home=$1 cwd=$2 root=$3 nro=$4
shift 4
extras=
while [ "$nro" -gt 0 ]; do
  extras="$extras$1
"
  shift
  nro=$((nro - 1))
done
nl='
'
origpath=$PATH
PATH=$PATH:/usr/sbin:/sbin
setpriv=$(command -v setpriv)

readonly_tree() {
  mount -o remount,bind,ro "$1"
  subs=
  while read -r _ _ _ _ mp _; do
    case $mp in "$1"/*) subs="$subs$mp$nl" ;; esac
  done < /proc/self/mountinfo
  while read -r mp; do
    [ -z "$mp" ] || mount -o remount,bind,ro "$mp"
  done <<EOF
$subs
EOF
}

step="making the private root"
mount -t tmpfs -o mode=0755,size=32m tmpfs "$root"
mkdir "$root/proc" "$root/dev" "$root/tmp" "$root/etc"
step="mounting /tmp"
mount -t tmpfs -o mode=1777,size=256m tmpfs "$root/tmp"
step="mounting /proc"
mount -t proc proc "$root/proc"
step="making /dev"
mount -t tmpfs -o mode=0755,size=1m tmpfs "$root/dev"
for n in null zero full random urandom tty; do
  if [ -e "/dev/$n" ]; then
    : > "$root/dev/$n"
    mount --bind "/dev/$n" "$root/dev/$n"
  fi
done
ln -s /proc/self/fd "$root/dev/fd"
ln -s /proc/self/fd/0 "$root/dev/stdin"
ln -s /proc/self/fd/1 "$root/dev/stdout"
ln -s /proc/self/fd/2 "$root/dev/stderr"
mkdir "$root/dev/shm"
mount -t tmpfs -o mode=1777,size=64m tmpfs "$root/dev/shm"
mount -o remount,bind,ro "$root/dev"
step="mounting the system directories"
for d in /usr /bin /sbin /lib /lib32 /lib64 /libx32; do
  if [ -L "$d" ]; then
    ln -s "$(readlink "$d")" "$root$d"
  elif [ -d "$d" ]; then
    mkdir "$root$d"
    mount --rbind "$d" "$root$d"
    readonly_tree "$root$d"
  fi
done
step="copying /etc"
for p in /etc/ld.so.cache /etc/ld.so.conf /etc/ld.so.conf.d /etc/passwd /etc/group \
    /etc/nsswitch.conf /etc/hosts /etc/localtime /etc/timezone /etc/alternatives \
    /etc/gitconfig /etc/os-release /etc/mime.types; do
  if [ -e "$p" ] || [ -L "$p" ]; then
    cp -RP "$p" "$root$p" || :
  fi
done
step="mounting the read-only trees the call named"
while read -r p; do
  if [ -n "$p" ]; then
    mkdir -p "$root$p"
    mount --rbind "$p" "$root$p"
    readonly_tree "$root$p"
  fi
done <<EOF
$extras
EOF
step="mounting the home"
# The directories on the way to the home get a tmpfs of their own, made at
# the shallowest of them the private root does not have yet and remounted
# read-only once the home is bound, so the way is read-only wherever it
# falls: on the read-only root, or inside the cage's writable /tmp when the
# state directory lives under the host's /tmp. When every directory on the
# way is already there (inside a named read-only tree), nothing is added.
top=
p=$home
while [ ! -e "$root$p" ]; do
  top=$p
  p=${p%/*}
  [ -n "$p" ] || p=/
done
if [ -n "$top" ]; then
  mkdir "$root$top"
  mount -t tmpfs -o mode=0755,size=1m tmpfs "$root$top"
  mkdir -p "$root$home"
fi
mount --rbind "$home" "$root$home"
if [ -n "$top" ]; then
  mount -o remount,bind,ro "$root$top"
fi
mount -o remount,bind,ro "$root"
step="entering the private root"
cd "$root"
if pivot_root . . 2>/dev/null; then
  umount -l .
  cd /
  step="starting the command"
  cd "$cwd"
  unset OLDPWD
  PATH=$origpath
  exec "$setpriv" --no-new-privs --bounding-set=-sys_admin,-sys_chroot -- "$@"
fi
chroot=$(command -v chroot)
unset OLDPWD
PATH=$origpath
exec "$chroot" "$root" "$setpriv" --no-new-privs --bounding-set=-sys_admin,-sys_chroot -- \
  sh -c 'cd "$1" && unset OLDPWD && shift && exec "$@"' twine-cage "$cwd" "$@"
"""


def readonly_trees(paths: Sequence[str | Path], *, home: Path | None = None
                   ) -> tuple[str, ...]:
    """The directories among `paths` the cage must be told to show
    read-only, resolved, sorted, without repeats: those that exist as
    directories, are not `/`, hold no newline, are not already visible (under
    one of SYSTEM_DIRS) or already the home's, and are not inside another
    one named. What a call needs beyond the system directories — the
    interpreter `escalate` runs the request's tools with, when it lives under
    the operator's home — is named this way."""
    found: set[Path] = set()
    for item in paths:
        try:
            path = Path(item).resolve()
        except (OSError, RuntimeError):
            continue
        text = str(path)
        if (not path.is_dir() or text == "/" or "\n" in text
                or any(path == Path(d) or Path(d) in path.parents for d in SYSTEM_DIRS)
                or (home is not None and (path == home or home in path.parents))):
            continue
        found.add(path)
    kept = [p for p in sorted(found) if not any(q in p.parents for q in found)]
    return tuple(str(p) for p in kept)


class SandboxRunner:
    """The sandbox's runner — a wrapper around the runner it is given
    (twine.process.run_process by default) with the seam's whole signature.

    It wraps every argv as far as the sandbox found it can: with the
    network off, `unshare -rn -- <argv>`; with the filesystem confined (the
    sandbox passes `home` and `root`), `unshare -rnmpf --kill-child --
    sh -c CAGE_SCRIPT … <argv>` (`-rmpf` when the network is not off).
    **`confines` is true exactly when both hold** — cli-contract.md §10.5's
    switch, the one runner that declares it. With neither it passes the argv
    through and declares false."""

    def __init__(self, inner: process.Runner, *, network_off: bool,
                 home: Path | None = None, root: Path | None = None,
                 readonly: Sequence[str] = ()) -> None:
        self.inner = inner
        self.network_off = network_off is True
        self.home = None if home is None else Path(home)
        self.root = None if root is None else Path(root)
        self.filesystem_confined = self.home is not None and self.root is not None
        self.readonly = tuple(readonly)
        self.confines = self.network_off and self.filesystem_confined

    def with_readonly(self, paths: Sequence[str | Path]) -> "SandboxRunner":
        """This runner, also showing `paths` read-only in the cage (see
        `readonly_trees`: the ones already visible are dropped). The same
        runner when nothing is left to add."""
        added = readonly_trees([*self.readonly, *paths], home=self.home)
        if added == self.readonly:
            return self
        return SandboxRunner(self.inner, network_off=self.network_off, home=self.home,
                             root=self.root, readonly=added)

    def wrap(self, argv: Sequence[str], cwd: str | Path | None = None) -> tuple[str, ...]:
        """The argv the inner runner is handed. `cwd` is where the command
        starts inside the cage (the home when none is named)."""
        argv = tuple(str(a) for a in argv)
        if not self.filesystem_confined:
            return (UNSHARE, *UNSHARE_FLAGS, "--", *argv) if self.network_off else argv
        flags = CAGE_FLAGS_ALL if self.network_off else CAGE_FLAGS_FILESYSTEM
        return (UNSHARE, flags, KILL_CHILD, "--", "sh", "-c", CAGE_SCRIPT, "twine-cage",
                str(self.home), str(self.home if cwd is None else cwd), str(self.root),
                str(len(self.readonly)), *self.readonly, *argv)

    def __call__(self, argv: Sequence[str], *, cwd: str | Path | None = None,
                 stdin: bytes | None = None, timeout: float | None = None,
                 env: Mapping[str, str] | None = None,
                 stdout_cap: int | None = None,
                 on_spawn: process.SpawnHook | None = None) -> process.RunResult:
        return self.inner(self.wrap(argv, cwd), cwd=cwd, stdin=stdin, timeout=timeout,
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
    root            <state-dir>/sandbox/<sid>/root, resolved: the empty mount
                    point the cage's private root is built on
    filesystem      "confined" or "unconfined" (twine-sandbox-confine)
    filesystem_reason  why it is unconfined; None when confined
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
    root: Path | None = None
    filesystem: str = FILESYSTEM_UNCONFINED
    filesystem_reason: str | None = None
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
            (home.parent / ROOT_NAME).mkdir(mode=DIR_MODE, exist_ok=True)
        except OSError as exc:
            raise SandboxError(f"cannot make the sandbox home {home}: "
                               f"{exc.strerror or exc}") from exc
        home = home.resolve()
        cage_env = MappingProxyType(cage_environment(home, env))
        sandbox = cls(sid=sid, state_dir=Path(state_dir), home=home,
                      repo=repo_path.resolve(), run=run,
                      runner=SandboxRunner(run, network_off=False), env=cage_env,
                      max_timeout=float(max_timeout), network=NETWORK_UNCONFINED,
                      network_reason="not yet detected",
                      root=(home.parent / ROOT_NAME).resolve(),
                      filesystem=FILESYSTEM_UNCONFINED,
                      filesystem_reason="not yet detected")
        sandbox._detect()
        log.info("sandbox for %s: home %s, network %s%s, filesystem %s%s, max timeout %gs",
                 sid, home, sandbox.network,
                 f" ({sandbox.network_reason})" if sandbox.network_reason else "",
                 sandbox.filesystem,
                 f" ({sandbox.filesystem_reason})" if sandbox.filesystem_reason else "",
                 sandbox.max_timeout)
        return sandbox

    def _detect(self) -> None:
        """Run the whole cage on `true` through the seam (registered like any
        spawn). It works: the network is off and the filesystem confined, the
        runner wraps from now on. It does not: each half is tried alone — `unshare
        -rn true`, then the cage without `-n` — and the sandbox keeps what
        works and names, for each half that does not, why: no `unshare`, a
        refusal (no unprivileged user, network, mount or PID namespaces), a
        timeout, or the step of the cage's setup that failed. If each half
        works alone but not together, the network is off and the filesystem
        unconfined, the whole cage's failure the reason."""
        both = self._probe(network=True, filesystem=True)
        if both is None:
            self._settle(None, None)
            return
        network = self._probe(network=True, filesystem=False)
        filesystem = self._probe(network=False, filesystem=True)
        if network is None and filesystem is None:
            filesystem = both
        self._settle(network, filesystem)

    def _probe(self, *, network: bool, filesystem: bool) -> str | None:
        """None when `true` runs under the cage made of the named halves;
        else why it did not."""
        probe = SandboxRunner(self.run, network_off=network,
                              home=self.home if filesystem else None,
                              root=self.root if filesystem else None)
        label = (f"`{UNSHARE} {CAGE_FLAGS_ALL if network else CAGE_FLAGS_FILESYSTEM} "
                 f"{KILL_CHILD}` and the cage's private root" if filesystem
                 else f"`{UNSHARE} {' '.join(UNSHARE_FLAGS)} true`")
        try:
            result = self.spawn(("true",), runner=probe, cwd=self.home,
                                timeout=DETECT_TIMEOUT_SECONDS,
                                stdout_cap=DETECT_STDOUT_CAP)
        except process.RunError as exc:
            return (f"{label} could not start on the cage's PATH: "
                    f"{exc.strerror or exc}")
        except SpawnRefused as exc:
            raise SandboxError(f"cannot detect the cage: {exc}") from exc
        if result.timed_out:
            return f"{label} did not finish within {DETECT_TIMEOUT_SECONDS:g}s"
        if result.exit_code != 0:
            lines = [ln.strip() for ln in
                     result.stderr.decode("utf-8", errors="replace").splitlines()
                     if ln.strip()]
            said = " / ".join(lines[-2:])[:300] if lines else "no message"
            return (f"{label} exited {result.exit_code} ({said}) — unprivileged user, "
                    "network, mount or PID namespaces are not available here, or the "
                    "cage could not be built")
        return None

    def _settle(self, network: str | None, filesystem: str | None) -> None:
        """Record what the probes found (None: it works) and build the runner
        that wraps accordingly."""
        self.network = NETWORK_OFF if network is None else NETWORK_UNCONFINED
        self.network_reason = network
        self.filesystem = FILESYSTEM_CONFINED if filesystem is None else FILESYSTEM_UNCONFINED
        self.filesystem_reason = filesystem
        for what, reason in (("network", network), ("filesystem", filesystem)):
            if reason is not None:
                log.warning("sandbox for %s: %s unconfined: %s", self.sid, what, reason)
        self.runner = SandboxRunner(
            self.run, network_off=network is None,
            home=self.home if filesystem is None else None,
            root=self.root if filesystem is None else None)

    # --- what it reports --------------------------------------------------

    @property
    def confines(self) -> bool:
        """Read from the runner — cli-contract.md §10.5's one switch point."""
        return process.runner_confines(self.runner)

    @property
    def tmp(self) -> Path:
        return self.home / TMP_NAME

    def as_json(self) -> dict[str, Any]:
        """`sid`, `home`, `repo`, `network`, `filesystem`, `confines`,
        `max_timeout`, then `reason` when the network is unconfined and
        `filesystem_reason` when the filesystem is (each absent when the
        half is confined; runtime-contract.md §6.4)."""
        out: dict[str, Any] = {"sid": self.sid, "home": str(self.home),
                               "repo": str(self.repo), "network": self.network,
                               "filesystem": self.filesystem,
                               "confines": self.confines, "max_timeout": self.max_timeout}
        if self.network != NETWORK_OFF:
            out["reason"] = self.network_reason
        if self.filesystem != FILESYSTEM_CONFINED:
            out["filesystem_reason"] = self.filesystem_reason
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
              stdin: bytes | None = None,
              readonly: Sequence[str | Path] = ()) -> process.RunResult:
        """Run `argv` through `runner` (the sandbox's runner by default) in the
        cage's environment (or `env`), with the kill-switch hook: when the
        session has a running record, the seam's `on_spawn` registers the
        child's group (twine.kill.register_group) before it does anything,
        and once the run returns with `group_survivors` empty the group is
        cleared again (clear_group) — a group with survivors stays recorded
        for `twine kill`. Without a record the run proceeds unregistered,
        logged. `readonly` names directories the cage must also show,
        read-only at their own paths (the interpreter a request's tool runs
        with, when it lives outside the system directories; see
        `readonly_trees`); a runner that is not the sandbox's ignores it.
        Raises SpawnRefused when the record cannot be read or the
        hook cannot register (the seam has killed the child), and the seam's
        RunError when nothing could start."""
        runner = self.runner if runner is None else runner
        if readonly and isinstance(runner, SandboxRunner):
            runner = runner.with_readonly(readonly)
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

"""The bale surface twine reads (twine-seed.md D2, D3, D4; T10).

Twine never imports bale. What it reads from an install is files bale
leaves on disk and the stdout of bale's non-interactive verbs: the file
`<root>/bin/VERSION`, compared to the pin in the consumption manifest
(`share/bale-consumption.toml`), and — since Arc 1 session 2b-ii — the
stdout of the two verbs the `carry` hand-offs run, `bale relay <sid> -`
and `bale apply --dry-run --json <tarball>`. Section 5 is the only place
a bale argv is built, so T12 ("twine never merges at rung 1") has one
home: `apply` is only ever built with `--dry-run --json`, and no other
flag reaches it.

Since Arc 1 session 4 the manifest also records the three closed
vocabularies bale declares — telemetry outcomes, closure reasons, and
the outcomes `bale apply --json` prints — as `[[vocabulary]]` data the
transition table keys on (twine/transitions.py), and the pin gates
(D2): a carry verb drives only a bale whose `bin/VERSION` is the pin,
because the table's bale axes are that version's spellings and no
other's (`Executable.drive_refusal`).

Since Arc 1 session 5b, `twine kill` closes a killed session with one more
argv built here, `unlock_argv`: `bale unlock <sid> --reason aborted
--json`, the sid always explicit and the reason always `aborted` — never
the no-sid form (bale would close whichever one session is open), never an
inferred reason, never the flag that clears the lock past a HOLD branch
(that state is `bale revert`'s, the operator's). No other `unlock` argv
exists in twine.

Sections:
  1. Install-root resolution     (~line 50)
  2. The installed version       (~line 105)
  3. The consumption manifest    (~line 125)
  4. The pin check               (~line 210)
  5. Running bale: the executable, the pin gate, the argvs  (~line 260)
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from twine import CONSUMPTION_MANIFEST

log = logging.getLogger("twine.bale")

ENV_ROOT = "TWINE_BALE_ROOT"
VERSION_RELPATH = Path("bin") / "VERSION"

# ---------------------------------------------------------------------------
# 1. Install-root resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Root:
    """Where the bale install root was found, or that it was not.

    `path` is None when nothing resolved; `source` names which rule
    produced it ("--bale-root", "TWINE_BALE_ROOT", "PATH") or is None.
    """

    path: Path | None
    source: str | None
    detail: str

    @property
    def found(self) -> bool:
        return self.path is not None


def resolve_root(explicit: str | None = None,
                 env: Mapping[str, str] | None = None,
                 which: Callable[[str], str | None] = shutil.which) -> Root:
    """Resolve the install root, first rule that answers wins (D2):

    1. `--bale-root DIR` (the explicit argument);
    2. the environment variable TWINE_BALE_ROOT;
    3. `command -v bale`, followed to its real path and up to the
       directory holding bin/ (`~/.local/bin/bale` -> `~/bale/bin/bale`
       -> `~/bale` on the architect's machine).

    `env` and `which` are injectable so tests never touch the real
    environment or a real install.
    """
    env = os.environ if env is None else env
    if explicit:
        path = Path(explicit).expanduser()
        log.info("bale root from --bale-root: %s", path)
        return Root(path, "--bale-root", f"--bale-root {explicit}")
    from_env = env.get(ENV_ROOT)
    if from_env:
        path = Path(from_env).expanduser()
        log.info("bale root from %s: %s", ENV_ROOT, path)
        return Root(path, ENV_ROOT, f"{ENV_ROOT}={from_env}")
    exe = which("bale")
    if not exe:
        log.info("no bale on PATH, no %s, no --bale-root", ENV_ROOT)
        return Root(None, None,
                    f"no --bale-root, no {ENV_ROOT}, and no bale on PATH")
    real = Path(os.path.realpath(exe))
    path = real.parent.parent
    log.info("bale root from PATH: %s -> %s -> %s", exe, real, path)
    return Root(path, "PATH", f"command -v bale -> {real}")


# ---------------------------------------------------------------------------
# 2. The installed version
# ---------------------------------------------------------------------------


def read_installed_version(root: Path) -> tuple[str | None, str]:
    """`<root>/bin/VERSION` stripped, or None with the reason it was not
    readable. Never raises: an unreadable install is a reported fact."""
    path = root / VERSION_RELPATH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        log.info("cannot read %s: %s", path, exc.strerror or exc)
        return None, f"{path} unreadable: {exc.strerror or exc}"
    version = text.strip()
    if not version:
        return None, f"{path} is empty"
    return version, f"{path} reads {version}"


# ---------------------------------------------------------------------------
# 3. The consumption manifest
# ---------------------------------------------------------------------------


class ManifestError(Exception):
    """share/bale-consumption.toml is missing, unparseable, or malformed."""


@dataclass(frozen=True)
class Manifest:
    """The parsed consumption manifest (D4): the pin, the installed
    schema hashes, the surfaces twine reads, and the vocabularies bale
    declares (keyed by the transition-table axis they are the keys of),
    as data a test can walk. `data` is the whole TOML document."""

    path: Path
    pin: str
    schemas: dict[str, str]
    surfaces: list[dict[str, Any]]
    data: dict[str, Any]
    vocabularies: dict[str, dict[str, Any]] = field(default_factory=dict)


def load_manifest(path: Path = CONSUMPTION_MANIFEST) -> Manifest:
    """Parse the manifest with tomllib and check the shape twine relies
    on. Raises ManifestError with the reason; callers report, never
    swallow."""
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        raise ManifestError(f"{path}: {exc.strerror or exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"{path}: not valid TOML: {exc}") from exc
    bale = data.get("bale")
    if not isinstance(bale, dict):
        raise ManifestError(f"{path}: no [bale] table")
    pin = bale.get("pin")
    if not isinstance(pin, str) or not pin.strip():
        raise ManifestError(f"{path}: [bale] pin must be a non-empty string")
    schemas = bale.get("schemas")
    if not isinstance(schemas, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in schemas.items()):
        raise ManifestError(f"{path}: [bale.schemas] must map file names to sha256 strings")
    surfaces = data.get("surface", [])
    if not isinstance(surfaces, list) or not all(isinstance(s, dict) for s in surfaces):
        raise ManifestError(f"{path}: [[surface]] must be an array of tables")
    vocabularies = load_vocabularies(path, data.get("vocabulary", []))
    log.debug("manifest %s: pin %s, %d schemas, %d surfaces, %d vocabularies",
              path, pin, len(schemas), len(surfaces), len(vocabularies))
    return Manifest(path, pin.strip(), dict(schemas), list(surfaces), data,
                    vocabularies)


def load_vocabularies(path: Path, entries: Any) -> dict[str, dict[str, Any]]:
    """`[[vocabulary]]` keyed by `axis`. Each entry's `values` must be a
    non-empty list of distinct non-empty strings — a closed set of bale's
    spellings, in bale's order — and its `axis` and `home` named. Two
    entries for one axis, or a malformed one, refuse: the transition
    table must never key on a vocabulary twine cannot state exactly."""
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise ManifestError(f"{path}: [[vocabulary]] must be an array of tables")
    found: dict[str, dict[str, Any]] = {}
    for entry in entries:
        axis = entry.get("axis")
        if not isinstance(axis, str) or not axis.strip():
            raise ManifestError(f"{path}: a [[vocabulary]] entry has no axis")
        if axis in found:
            raise ManifestError(f"{path}: two [[vocabulary]] entries for {axis!r}")
        values = entry.get("values")
        if (not isinstance(values, list) or not values
                or not all(isinstance(v, str) and v.strip() for v in values)):
            raise ManifestError(f"{path}: vocabulary {axis!r}: values must be a "
                                "non-empty list of non-empty strings")
        if len(set(values)) != len(values):
            dupes = sorted({v for v in values if values.count(v) > 1})
            raise ManifestError(f"{path}: vocabulary {axis!r} repeats {dupes}")
        if not isinstance(entry.get("home"), str) or not entry["home"].strip():
            raise ManifestError(f"{path}: vocabulary {axis!r} names no home")
        found[axis] = dict(entry)
    return found


# ---------------------------------------------------------------------------
# 4. The pin check
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckResult:
    """`twine bale check`'s facts: the pin, what is installed (None when
    unreadable), where, and whether they agree."""

    pin: str
    installed: str | None
    root: Path | None
    source: str | None
    ok: bool
    reason: str

    def as_json(self) -> dict[str, Any]:
        return {"pin": self.pin, "installed": self.installed,
                "root": None if self.root is None else str(self.root),
                "source": self.source, "ok": self.ok, "reason": self.reason}

    def as_lines(self) -> list[str]:
        where = "no install found" if self.root is None else str(self.root)
        return [f"pin:       {self.pin}",
                f"installed: {self.installed if self.installed else '(unreadable)'}",
                f"root:      {where}" + (f"  (from {self.source})" if self.source else ""),
                f"check:     {'ok' if self.ok else 'FAIL'} — {self.reason}"]


def check(manifest: Manifest, root: Root) -> CheckResult:
    """Compare the installed bin/VERSION to the manifest's pin (D2).

    ok only when an install was found, its VERSION read, and the two
    strings are equal. Every other outcome is reported, with the reason,
    and never raises — a wrong or absent install is a check result, not
    an internal error.
    """
    if root.path is None:
        return CheckResult(manifest.pin, None, None, None, False,
                           f"no bale install found ({root.detail})")
    installed, detail = read_installed_version(root.path)
    if installed is None:
        return CheckResult(manifest.pin, None, root.path, root.source, False,
                           detail)
    if installed != manifest.pin:
        return CheckResult(manifest.pin, installed, root.path, root.source, False,
                           f"installed {installed} differs from pin {manifest.pin}")
    return CheckResult(manifest.pin, installed, root.path, root.source, True,
                       f"installed {installed} matches the pin")


# ---------------------------------------------------------------------------
# 5. Running bale: the executable, the pin gate, the argvs
# ---------------------------------------------------------------------------

EXECUTABLE_RELPATH = Path("bin") / "bale"
# The only flags `bale apply` ever receives from twine (T12): a dry run,
# reported as one JSON line. No admission, override or interaction flag
# exists anywhere in twine; the merge stays the operator's.
DRY_RUN_FLAGS = ("--dry-run", "--json")
# The one closure reason twine ever passes to `bale unlock` (session 5b): a
# kill's. bale 0.4.35 added it to CLOSURE_REASONS; the closure-reason
# vocabulary in share/bale-consumption.toml records it.
UNLOCK_REASON = "aborted"
# A session id twine will pass to bale as an argument. Not bale's sid
# grammar (YYYY-MM-DD-<slug>-NNN, which twine does not re-declare) but a
# floor under it: it starts with a letter or digit, so it can never be
# read as a flag, and holds no whitespace or shell-significant byte.
SID_ARGUMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


@dataclass(frozen=True)
class Executable:
    """The bale executable a carry verb would run, and what is known of
    it: where its root came from (the same three rules as `bale check`),
    the installed `bin/VERSION`, and the pin. `path` is None when no
    root resolved. Since Arc 1 session 4 the version gates (D2): a carry
    verb refuses to start a bale whose `bin/VERSION` is not the pin, or
    cannot be read (`drive_refusal`)."""

    root: Root
    path: Path | None
    installed: str | None
    pin: str | None
    detail: str

    @property
    def pin_matches(self) -> bool | None:
        if self.installed is None or self.pin is None:
            return None
        return self.installed == self.pin

    @property
    def drive_refusal(self) -> str | None:
        """Why twine will not drive this bale, or None when it will (D2).

        Twine drives only the pinned bale. Since Arc 1 session 4 the
        transition table keys on the pinned version's whole outcome and
        closure vocabularies, so a bale of another version — or one whose
        version cannot be read — may answer in spellings the table has no
        move for: the surprise D17 rules out. A pin bump is the deliberate
        event that re-reads the vocabularies (D4), never an ambient one."""
        if self.path is None:
            return self.detail
        if self.pin is None:
            return ("the pin is unknown (share/bale-consumption.toml is "
                    "unusable), so no bale's vocabulary is known to the "
                    "transition table — twine drives only the pinned bale (D2)")
        if self.installed is None:
            return (f"bale at {self.root.path}: {self.detail}; twine drives only "
                    f"the pinned bale {self.pin} (D2) and cannot tell this one's "
                    "version")
        if self.installed != self.pin:
            return (f"bale at {self.root.path} is {self.installed}, not the pin "
                    f"{self.pin}; twine drives only the pinned bale (D2), whose "
                    "outcome vocabularies its transition table keys on — install "
                    f"{self.pin}, or bump the pin in a session that re-reads them")
        return None

    def as_json(self) -> dict[str, Any]:
        return {"executable": None if self.path is None else str(self.path),
                "root": None if self.root.path is None else str(self.root.path),
                "source": self.root.source, "installed": self.installed,
                "pin": self.pin, "pin_matches": self.pin_matches}


def locate_executable(explicit: str | None, env: Mapping[str, str],
                      which: Callable[[str], str | None]) -> Executable:
    """`<root>/bin/bale`, the root resolved exactly as `bale check` does
    (`--bale-root`, TWINE_BALE_ROOT, then PATH). The tests pin
    TWINE_BALE_ROOT, so a bale on the operator's PATH is never what a
    test runs (cli-contract.md §8). Whether the file exists is learned by
    starting it: a root with no `bin/bale` is a RunError at the seam."""
    root = resolve_root(explicit, env, which)
    pin: str | None = None
    try:
        pin = load_manifest().pin
    except ManifestError as exc:
        log.warning("pin unknown: %s", exc)
    if root.path is None:
        return Executable(root, None, None, pin,
                          f"no bale install found ({root.detail})")
    installed, detail = read_installed_version(root.path)
    path = root.path / EXECUTABLE_RELPATH
    log.info("bale executable: %s (%s; %s)", path, root.detail, detail)
    return Executable(root, path, installed, pin, detail)


def relay_argv(executable: Path, sid: str) -> list[str]:
    """`bale relay <sid> -`: the block arrives on stdin. Raises ValueError
    for a sid that could read as a flag or carries whitespace."""
    if not SID_ARGUMENT.fullmatch(sid):
        raise ValueError(f"session id {sid!r} is not safe to pass to bale")
    return [str(executable), "relay", sid, "-"]


def dry_run_argv(executable: Path, tarball: str) -> list[str]:
    """`bale apply --dry-run --json <tarball>` — the one `apply` argv
    twine builds (T12). The tarball is named by its absolute path, so it
    begins with `/` and can never be read as a flag."""
    if not os.path.isabs(tarball):
        raise ValueError(f"tarball {tarball!r} is not an absolute path")
    return [str(executable), "apply", *DRY_RUN_FLAGS, tarball]


def apply_line(tarball: str) -> str:
    """The line the operator runs to apply: `bale apply ` and the
    tarball's absolute path, quoted only when the shell needs it."""
    return "bale apply " + shlex.quote(tarball)


def absolute_path(name: str) -> str:
    """The operator's name for a file made absolute against the current
    directory (`~` expanded, `..` folded, symlinks left as named). No
    search path: the operator names the file."""
    return os.path.abspath(os.path.expanduser(name))


def unlock_argv(executable: Path, sid: str) -> list[str]:
    """`bale unlock <sid> --reason aborted --json` — the one `unlock` argv
    twine builds (session 5b; brief ruling 2). The sid is always explicit:
    without it bale closes whichever single session is open. The reason is
    always `aborted`: without it bale infers `closed-read-only` or
    `abandoned`. Nothing else is ever added. Raises ValueError for a sid
    that could read as a flag or carries whitespace."""
    if not SID_ARGUMENT.fullmatch(sid):
        raise ValueError(f"session id {sid!r} is not safe to pass to bale")
    return [str(executable), "unlock", sid, "--reason", UNLOCK_REASON, "--json"]


def unlock_line(sid: str) -> str:
    """The line an operator runs to close a killed session by hand, in the
    repo whose session it is — the same argv without `--json`."""
    return f"bale unlock {shlex.quote(sid)} --reason {UNLOCK_REASON}"


def revert_line(sid: str) -> str:
    """bale's own remedy when a session reached HOLD: revert discards the
    `bale/<sid>` branch and clears the lock together. It touches git, so it
    is always the operator's; twine never runs it."""
    return f"bale revert {shlex.quote(sid)}"

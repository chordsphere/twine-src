"""The bale surface twine reads (twine-seed.md D2, D3, D4; T10).

Twine never imports bale. What it reads from an install is files bale
leaves on disk and the stdout of bale's non-interactive verbs: the file
`<root>/bin/VERSION`, compared to the floor in the consumption manifest
(`share/bale-consumption.toml`), the files under `<root>/schemas/`, hashed
against the manifest's `[bale.schemas]` (since session
2026-10-12-twine-pin-floor-002), and — since Arc 1 session 2b-ii — the
stdout of the two verbs the `carry` hand-offs run, `bale relay <sid> -
--json` (since session 2026-10-08-twine-carry-exchange-json-001; the
flagless `bale relay <sid> -` before it) and `bale apply --dry-run --json
<tarball>`. Section 5 is the only place a bale argv is built, so T12
("twine never merges at rung 1") has one home: `apply` is only ever built
with `--dry-run --json`, and no other flag reaches it. Likewise `relay`
is only ever built as `relay <sid> - --json`: the block on stdin, one
JSON line back.

Since Arc 1 session 4 the manifest also records the three closed
vocabularies bale declares — telemetry outcomes, closure reasons, and
the outcomes `bale apply --json` prints — as `[[vocabulary]]` data the
transition table keys on (twine/transitions.py), and the gate (D2) keeps
them true: a carry verb drives only a bale the gate admits
(`Executable.drive_refusal`). Until session 2026-10-12-twine-pin-floor-002
the gate was an exact pin; since then it is a floor plus the manifest's
contract (D2 as amended on 2026-10-08): `bin/VERSION` at or above the
floor — the version the recordings were made at, raised only by a
recording session — and every schema `[bale.schemas]` names installed
with that sha256, which holds the two schema-homed vocabularies fixed.
The third half of the contract is on the line: every verb that reads a
bale `--json` line checks that each key the manifest lists for that
surface is present (`missing_keys_failure`, section 6); bale's own rule
is that existing keys are never renamed or removed, and an extra key is
free.

Since Arc 1 session 5b, `twine kill` closes a killed session with one more
argv built here, `unlock_argv`: `bale unlock <sid> --reason aborted
--json`, the sid always explicit and the reason always `aborted` — never
the no-sid form (bale would close whichever one session is open), never an
inferred reason, never the flag that clears the lock past a HOLD branch
(that state is `bale revert`'s, the operator's). No other `unlock` argv
exists in twine.

Since Arc 1 session 3 (`twine carry bundle`, 2026-10-07-twine-carry-bundle-003)
one more argv is built here, `open_argv`: exactly `bale open <bundle>
--json`, or with `--check` exactly `bale open --check <bundle> --json` — the
two argvs the consumption manifest's open surface records. Never
`--dry-run`, `--verbose`, `--no-sandbox` or another flag; no other `open`
argv exists in twine.

Sections:
  1. Install-root resolution     (~line 80)
  2. The installed version       (~line 135)
  3. The consumption manifest    (~line 175)
  4. The gate: the floor and the schemas  (~line 280)
  5. Running bale: the executable, the gate, the argvs  (~line 435)
  6. The contract on the line: the listed keys  (~line 635)
"""

from __future__ import annotations

import hashlib
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
SCHEMAS_RELPATH = Path("schemas")

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


# A bale version as twine compares it: three dotted non-negative integers,
# nothing before or after (bin/VERSION's shape at every version twine has
# read). Compared as a tuple, so 0.4.100 is above 0.4.51 — never as a string.
VERSION_SHAPE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def parse_version(text: str | None) -> tuple[int, int, int] | None:
    """`text` as a (major, minor, patch) tuple, or None when it is not
    exactly three dotted integers (a leading zero, a suffix such as
    `-rc1`, or whitespace inside all count as not)."""
    if text is None:
        return None
    match = VERSION_SHAPE.fullmatch(text)
    if match is None:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


# ---------------------------------------------------------------------------
# 3. The consumption manifest
# ---------------------------------------------------------------------------


class ManifestError(Exception):
    """share/bale-consumption.toml is missing, unparseable, or malformed."""


# A file name [bale.schemas] may name: one path component under schemas/,
# so the gate never hashes a file outside the install's schemas directory.
SCHEMA_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


@dataclass(frozen=True)
class Manifest:
    """The parsed consumption manifest (D4): the floor (D2 as amended:
    the lowest bale twine drives, the version the recordings were made
    at), the installed schema hashes the gate's second half holds an
    install to, the surfaces twine reads, and the vocabularies bale
    declares (keyed by the transition-table axis they are the keys of),
    as data a test can walk. `data` is the whole TOML document."""

    path: Path
    floor: str
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
    if "pin" in bale:
        # The exact pin retired at session 2026-10-12-twine-pin-floor-002; a
        # manifest still carrying it is one twine no longer reads, never one
        # it guesses about.
        raise ManifestError(f"{path}: [bale] carries `pin`, which retired when D2 "
                            "became a floor; the key is `floor`")
    floor = bale.get("floor")
    if not isinstance(floor, str) or parse_version(floor.strip()) is None:
        raise ManifestError(f"{path}: [bale] floor must be a version string of three "
                            f"dotted integers (got {floor!r})")
    schemas = bale.get("schemas")
    if not isinstance(schemas, dict) or not schemas or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in schemas.items()):
        raise ManifestError(f"{path}: [bale.schemas] must map file names to sha256 strings")
    unsafe = sorted(k for k in schemas if not SCHEMA_NAME.fullmatch(k))
    if unsafe:
        raise ManifestError(f"{path}: [bale.schemas] names {unsafe}, which are not plain "
                            "file names under schemas/")
    surfaces = data.get("surface", [])
    if not isinstance(surfaces, list) or not all(isinstance(s, dict) for s in surfaces):
        raise ManifestError(f"{path}: [[surface]] must be an array of tables")
    vocabularies = load_vocabularies(path, data.get("vocabulary", []))
    log.debug("manifest %s: floor %s, %d schemas, %d surfaces, %d vocabularies",
              path, floor, len(schemas), len(surfaces), len(vocabularies))
    return Manifest(path, floor.strip(), dict(schemas), list(surfaces), data,
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
# 4. The gate: the floor and the schemas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchemaVerdict:
    """The gate's second half: every file `[bale.schemas]` names, looked
    for under `<root>/schemas/` and hashed. `checked` names every file that
    was there and hashed (matching or not), `mismatched` those whose
    sha256 differs from the manifest's, `missing` those not there as a
    file — each list sorted. `present` is whether `schemas/` itself is a
    directory; when it is not, every pinned file is missing and the reason
    says so once. `dir` is the directory looked in."""

    dir: Path
    present: bool
    checked: tuple[str, ...]
    mismatched: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.present and not self.mismatched and not self.missing

    def problems(self) -> list[str]:
        """One sentence per failing fact, for the check's reason."""
        if not self.present:
            return [f"no schemas/ directory at {self.dir}"]
        found = []
        if self.missing:
            found.append("schemas missing from schemas/: " + ", ".join(self.missing))
        if self.mismatched:
            found.append("schemas that do not hash as the manifest pins them: "
                         + ", ".join(self.mismatched))
        return found

    def as_json(self) -> dict[str, Any]:
        return {"dir": str(self.dir), "present": self.present, "ok": self.ok,
                "checked": list(self.checked), "mismatched": list(self.mismatched),
                "missing": list(self.missing)}

    def summary(self, pinned: int) -> str:
        """The human line's verdict."""
        if self.ok:
            return f"all {pinned} hash as the manifest pins them"
        return "NOT OK — " + "; ".join(self.problems())


def check_schemas(manifest: Manifest, root: Path) -> SchemaVerdict:
    """Hash every file the manifest pins under `<root>/schemas/`. Never
    raises: a file that cannot be read is reported missing (with a log line
    saying why), never skipped."""
    where = root / SCHEMAS_RELPATH
    names = sorted(manifest.schemas)
    if not where.is_dir():
        log.info("no schemas directory at %s", where)
        return SchemaVerdict(where, False, (), (), tuple(names))
    checked: list[str] = []
    mismatched: list[str] = []
    missing: list[str] = []
    for name in names:
        path = where / name
        try:
            data = path.read_bytes()
        except OSError as exc:
            log.info("schema %s not readable as a file: %s", path, exc.strerror or exc)
            missing.append(name)
            continue
        checked.append(name)
        digest = hashlib.sha256(data).hexdigest()
        if digest != manifest.schemas[name]:
            log.info("schema %s hashes %s, the manifest pins %s", path, digest,
                     manifest.schemas[name])
            mismatched.append(name)
    return SchemaVerdict(where, True, tuple(checked), tuple(mismatched), tuple(missing))


@dataclass(frozen=True)
class CheckResult:
    """`twine bale check`'s facts: the floor, what is installed (None when
    unreadable), where, the schema verdict (None when no install was
    found), and whether the gate admits the install."""

    floor: str
    installed: str | None
    root: Path | None
    source: str | None
    schemas: SchemaVerdict | None
    ok: bool
    reason: str
    pinned: int = 0

    @property
    def floor_admits(self) -> bool | None:
        """Whether `installed` is at or above the floor, compared as a tuple;
        None when it cannot be read or parsed."""
        installed = parse_version(self.installed)
        floor = parse_version(self.floor)
        if installed is None or floor is None:
            return None
        return installed >= floor

    def as_json(self) -> dict[str, Any]:
        return {"floor": self.floor, "installed": self.installed,
                "root": None if self.root is None else str(self.root),
                "source": self.source,
                "schemas": None if self.schemas is None else self.schemas.as_json(),
                "ok": self.ok, "reason": self.reason}

    def as_lines(self) -> list[str]:
        where = "no install found" if self.root is None else str(self.root)
        schemas = ("(not checked: no install)" if self.schemas is None
                   else self.schemas.summary(self.pinned))
        return [f"floor:     {self.floor} (twine drives this bale or any above it)",
                f"installed: {self.installed if self.installed else '(unreadable)'}",
                f"root:      {where}" + (f"  (from {self.source})" if self.source else ""),
                f"schemas:   {schemas}",
                f"check:     {'ok' if self.ok else 'FAIL'} — {self.reason}"]


def check(manifest: Manifest, root: Root) -> CheckResult:
    """The gate (D2 as amended on 2026-10-08): ok exactly when an install
    was found, its `bin/VERSION` reads and parses as three dotted integers
    at or above the manifest's floor (compared as a tuple), and every file
    `[bale.schemas]` names exists under `<root>/schemas/` with that sha256.

    Every failing fact is named at once in the reason — a version below
    the floor and a mismatched schema are two sentences, not the first of
    them — and nothing raises: a wrong or absent install is a check result,
    not an internal error.
    """
    pinned = len(manifest.schemas)
    if root.path is None:
        return CheckResult(manifest.floor, None, None, None, None, False,
                           f"no bale install found ({root.detail})", pinned)
    problems: list[str] = []
    installed, detail = read_installed_version(root.path)
    if installed is None:
        problems.append(detail)
    else:
        parsed, floor = parse_version(installed), parse_version(manifest.floor)
        if parsed is None:
            problems.append(f"{root.path / VERSION_RELPATH} reads {installed!r}, which is "
                            "not a version of three dotted integers")
        elif floor is None:
            # load_manifest refuses such a floor; a Manifest built by hand
            # can still carry one, and it admits nothing.
            problems.append(f"the floor {manifest.floor!r} is not a version of three "
                            "dotted integers, so no install compares at or above it")
        elif parsed < floor:
            problems.append(f"installed {installed} is below the floor {manifest.floor}")
    schemas = check_schemas(manifest, root.path)
    problems.extend(schemas.problems())
    if problems:
        return CheckResult(manifest.floor, installed, root.path, root.source, schemas,
                           False, "; ".join(problems), pinned)
    return CheckResult(manifest.floor, installed, root.path, root.source, schemas, True,
                       f"installed {installed} is at or above the floor {manifest.floor}, "
                       f"and all {pinned} schemas hash as the manifest pins them", pinned)


# ---------------------------------------------------------------------------
# 5. Running bale: the executable, the gate, the argvs
# ---------------------------------------------------------------------------

EXECUTABLE_RELPATH = Path("bin") / "bale"
# The only flags `bale apply` ever receives from twine (T12): a dry run,
# reported as one JSON line. No admission, override or interaction flag
# exists anywhere in twine; the merge stays the operator's.
DRY_RUN_FLAGS = ("--dry-run", "--json")
# The input argument and the one flag `bale relay` receives from twine
# (session 2026-10-08-twine-carry-exchange-json-001): `-`, the block on
# stdin, and `--json`, so bale answers with exactly one line on every path,
# refusals included (format_relay_json, bale 0.4.48). Nothing else is added.
RELAY_INPUT = "-"
RELAY_FLAGS = ("--json",)
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
    the installed `bin/VERSION`, the floor, and the gate's verdict on the
    install (`verdict`, `bale check`'s own CheckResult; None when no root
    resolved or the manifest is unusable). `path` is None when no root
    resolved. A carry verb refuses to start a bale the gate does not admit
    (`drive_refusal`). `manifest` is kept so a verb that reads bale's line
    can check the keys its surface lists (section 6)."""

    root: Root
    path: Path | None
    installed: str | None
    floor: str | None
    detail: str
    verdict: CheckResult | None = None
    manifest: Manifest | None = None

    @property
    def floor_admits(self) -> bool | None:
        """Whether `installed` is at or above the floor (a tuple comparison);
        None when either is unknown or does not parse."""
        if self.verdict is None:
            return None
        return self.verdict.floor_admits

    @property
    def schemas_match(self) -> bool | None:
        """Whether every pinned schema is installed with its sha256; None
        when the gate never looked (no root, or no manifest)."""
        if self.verdict is None or self.verdict.schemas is None:
            return None
        return self.verdict.schemas.ok

    @property
    def drive_refusal(self) -> str | None:
        """Why twine will not drive this bale, or None when it will (D2).

        Twine drives a bale the gate admits — exactly one `twine bale check`
        reports ok — and refuses every other before starting it. The
        transition table keys on bale's outcome and closure vocabularies; the
        floor is the version they were read at, the schema hashes hold the
        two schema-homed ones fixed above it, and the key check on each line
        catches a listed key gone missing. A bale the gate does not admit may
        answer in spellings the table has no move for: the surprise D17 rules
        out. Raising the floor is the deliberate event — a recording session
        — never an ambient one."""
        if self.path is None:
            return self.detail
        if self.floor is None or self.verdict is None:
            return ("the floor is unknown (share/bale-consumption.toml is "
                    "unusable), so twine cannot tell whether any bale keeps the "
                    "vocabularies its transition table keys on — it drives only a "
                    "bale at or above the floor whose schemas hash as the manifest "
                    "pins them (D2)")
        if not self.verdict.ok:
            return (f"bale at {self.root.path} is not one twine drives: "
                    f"{self.verdict.reason}; twine drives only a bale at or above the "
                    f"floor {self.floor} whose schemas hash as the manifest pins them "
                    "(D2), since its transition table keys on the vocabularies that "
                    "keeps — install such a bale, or raise the floor in a recording "
                    "session")
        return None

    def as_json(self) -> dict[str, Any]:
        return {"executable": None if self.path is None else str(self.path),
                "root": None if self.root.path is None else str(self.root.path),
                "source": self.root.source, "installed": self.installed,
                "floor": self.floor, "floor_admits": self.floor_admits,
                "schemas_match": self.schemas_match}


def locate_executable(explicit: str | None, env: Mapping[str, str],
                      which: Callable[[str], str | None]) -> Executable:
    """`<root>/bin/bale`, the root resolved exactly as `bale check` does
    (`--bale-root`, TWINE_BALE_ROOT, then PATH), with the gate's verdict
    computed by `check` itself, so a carry verb and `bale check` can never
    disagree about an install. The tests pin TWINE_BALE_ROOT, so a bale on
    the operator's PATH is never what a test runs (cli-contract.md §8).
    Whether the file exists is learned by starting it: a root with no
    `bin/bale` is a RunError at the seam."""
    root = resolve_root(explicit, env, which)
    manifest: Manifest | None = None
    try:
        manifest = load_manifest()
    except ManifestError as exc:
        log.warning("floor unknown: %s", exc)
    floor = None if manifest is None else manifest.floor
    if root.path is None:
        return Executable(root, None, None, floor,
                          f"no bale install found ({root.detail})", None, manifest)
    installed, detail = read_installed_version(root.path)
    verdict = None if manifest is None else check(manifest, root)
    path = root.path / EXECUTABLE_RELPATH
    log.info("bale executable: %s (%s; %s; gate %s)", path, root.detail, detail,
             "unknown" if verdict is None else ("admits" if verdict.ok else "refuses"))
    return Executable(root, path, installed, floor, detail, verdict, manifest)


def relay_argv(executable: Path, sid: str) -> list[str]:
    """`bale relay <sid> - --json` — the one `relay` argv twine builds
    (session 2026-10-08-twine-carry-exchange-json-001, which retired the
    flagless `relay <sid> -`). The block arrives on stdin; bale answers with
    one JSON line whose `block` is what the flagless form printed. Raises
    ValueError for a sid that could read as a flag or carries whitespace."""
    if not SID_ARGUMENT.fullmatch(sid):
        raise ValueError(f"session id {sid!r} is not safe to pass to bale")
    return [str(executable), "relay", sid, RELAY_INPUT, *RELAY_FLAGS]


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


def open_argv(executable: Path, bundle: str, *, check: bool = False) -> list[str]:
    """`bale open <bundle> --json`, or with `check` `bale open --check
    <bundle> --json` — the one `open` argv twine builds (Arc 1 session 3),
    exactly as the consumption manifest's open surface records it. Nothing
    else is ever added: an open runs the bundle's checkpoint dry-run and
    packs a session, and twine asks for nothing beyond the JSON line.
    `bundle` is an existing file's absolute path or the operator's name for
    bale to resolve; it never begins with `-`, so bale cannot read it as a
    flag. Raises ValueError for an empty bundle or one that does."""
    if not bundle or bundle.startswith("-"):
        raise ValueError(f"bundle {bundle!r} is not safe to pass to bale "
                         "(empty, or it would read as a flag)")
    return [str(executable), "open", *(["--check"] if check else []), bundle, "--json"]


def revert_line(sid: str) -> str:
    """bale's own remedy when a session reached HOLD: revert discards the
    `bale/<sid>` branch and clears the lock together. It touches git, so it
    is always the operator's; twine never runs it."""
    return f"bale revert {shlex.quote(sid)}"


# ---------------------------------------------------------------------------
# 6. The contract on the line: the listed keys
# ---------------------------------------------------------------------------


def surface_keys(manifest: Manifest, reader: str) -> tuple[list[str], str, str]:
    """The keys the consumption manifest lists for the one bale verb surface
    the twine verb `reader` reads (`kind = "verb"`, `reader` in its
    `read_by`: `carry exchange` reads relay, `carry response` apply, `carry
    bundle` open, `kill` unlock), the bale verb itself, and the surface named
    as a reason names it: `the relay surface (bale relay <sid> - --json)`.
    Keyed on the reader rather than the bale verb, so no bale verb's name is
    spelled here beyond the argv builders above. Raises ManifestError when
    the manifest records no such surface, or more than one: which keys a
    line owes is never guessed."""
    found = [s for s in manifest.surfaces
             if s.get("kind") == "verb" and reader in (s.get("read_by") or [])]
    if len(found) != 1:
        raise ManifestError(f"{manifest.path}: {len(found)} bale verb surfaces read by "
                            f"`twine {reader}`, not one")
    entry = found[0]
    keys = entry.get("keys", [])
    if not isinstance(keys, list) or not all(isinstance(k, str) and k for k in keys):
        raise ManifestError(f"{manifest.path}: the keys of the surface `twine {reader}` "
                            "reads are not a list of key names")
    verb = str(entry.get("verb"))
    argv = entry.get("argv")
    shown = (" (bale " + " ".join(argv) + ")") if isinstance(argv, list) else ""
    return list(keys), verb, f"the {verb} surface{shown}"


def missing_keys_failure(manifest: Manifest | None, reader: str,
                         line: Mapping[str, Any]) -> str | None:
    """The contract check on the line (D2 as amended): None when `line`, the
    one JSON object bale printed for the twine verb `reader`, has every key
    the manifest lists for the surface `reader` reads; otherwise the
    failure, naming each absent key and the surface. Presence is all it
    asks — a key whose value is null is present (bale prints every key on
    every outcome, null where it does not apply), and a key the manifest
    does not list is free. The four readers (`carry exchange` on relay,
    `carry response` on apply, `carry bundle` on open, `kill` on unlock)
    call it on the line they read and append its failure beside whatever
    else the line fails. A manifest that cannot say which keys the line
    owes makes the line not ok too, named."""
    if manifest is None:
        return (f"the keys bale's line owes `twine {reader}` are unknown "
                "(share/bale-consumption.toml is unusable)")
    try:
        keys, verb, surface = surface_keys(manifest, reader)
    except ManifestError as exc:
        return f"the keys bale's line owes `twine {reader}` are unknown: {exc}"
    missing = [key for key in keys if key not in line]
    if not missing:
        return None
    named = ", ".join(repr(key) for key in missing)
    plural = "keys" if len(missing) > 1 else "key"
    return (f"bale's {verb} line lacks the {plural} {named}, which the consumption "
            f"manifest lists for {surface}; existing keys are never removed, so "
            "this bale is not the contract twine reads")

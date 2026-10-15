"""The bale surface twine reads (twine-seed.md D2, D3, D4; T10).

Twine never imports bale. What it reads from an install is files bale
leaves on disk and the stdout of bale's non-interactive verbs: the file
`<root>/bin/VERSION`, compared to the floor in the consumption manifest
(`share/bale-consumption.toml`); since session
2026-10-15-twine-gate-contract-001, the one line `<root>/bin/bale contract
--json` prints — bale's own statement of what a consumer reads — checked
against what twine reads; and — since Arc 1 session 2b-ii — the stdout of
the two verbs the `carry` hand-offs run, `bale relay <sid> - --json` (since
session 2026-10-08-twine-carry-exchange-json-001; the flagless `bale relay
<sid> -` before it) and `bale apply --dry-run --json <tarball>`. Section 5
is the only place a bale argv is built, so T12 ("twine never merges at
rung 1") has one home: `apply` is only ever built with `--dry-run --json`,
and no other flag reaches it. Likewise `relay` is only ever built as
`relay <sid> - --json`: the block on stdin, one JSON line back.

Since Arc 1 session 4 the manifest also records the three closed
vocabularies bale declares — telemetry outcomes, closure reasons, and
the outcomes `bale apply --json` prints — as `[[vocabulary]]` data the
transition table keys on (twine/transitions.py), and the gate (D2) keeps
them true: a carry verb drives only a bale the gate admits
(`Executable.drive_refusal`). Until session 2026-10-12-twine-pin-floor-002
the gate was an exact pin; that session made it a floor plus a sha256 of
each of bale's eight schema files whole. Since session
2026-10-15-twine-gate-contract-001 (ruled by the architect on 2026-10-15)
it is the floor plus bale's contract, and no file under `<root>/schemas/`
is read: `bin/VERSION` at or above the floor — 0.4.54, the first bale with
`contract --json` — and the contract line, run through the seam, stating
exactly the table's three vocabularies, every key each line twine reads
carries, and every outcome and the one unlock reason twine dispatches on
(section 4). A bale release then stops twine only when something twine
reads moved, and the refusal names it. The third half of the contract is
on the line itself: every verb that reads a bale `--json` line checks that
each key the manifest lists for that surface is present
(`missing_keys_failure`, section 6); bale's own rule is that existing keys
are never renamed or removed, and an extra key is free.

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
argv exists in twine. And since session 2026-10-15-twine-gate-contract-001
the gate's own, `contract_argv`: exactly `bale contract --json`.

Sections:
  1. Install-root resolution     (~line 85)
  2. The installed version       (~line 145)
  3. The consumption manifest    (~line 180)
  4. The gate: the floor and bale's contract  (~line 360)
  5. Running bale: the executable, the gate, the argvs  (~line 795)
  6. The contract on the line: the listed keys  (~line 1025)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shlex
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from twine import CONSUMPTION_MANIFEST, process

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


# The keys `[bale]` holds, exactly (session 2026-10-15-twine-gate-contract-001):
# the floor the gate compares bin/VERSION to, the version whose recordings
# the tests replay (fixtures/bale-<recordings>/), and the carried contract
# line the tests replay (a path under fixtures/).
BALE_TABLE_KEYS = ("floor", "recordings", "contract")
# Keys `[bale]` once held, refused by name so a stale manifest says what
# retired rather than reading as an unknown key: the exact pin (retired at
# session 2026-10-12-twine-pin-floor-002) and the schema hashes (retired at
# session 2026-10-15-twine-gate-contract-001, when the gate became the floor
# plus bale's contract).
RETIRED_BALE_KEYS = {
    "pin": "retired when D2 became a floor; the key is `floor`",
    "schemas": "retired when the gate became the floor plus bale's contract "
               "(`bale contract --json`); the gate reads no file under schemas/",
}
# A carried contract line's path: relative, under fixtures/, no `..`, so a
# manifest can never point a test at a file outside the tree's fixtures.
CONTRACT_PATH = re.compile(r"fixtures/(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*[A-Za-z0-9][A-Za-z0-9._-]*\.json")


@dataclass(frozen=True)
class Manifest:
    """The parsed consumption manifest (D4): the floor (D2 as amended: the
    lowest bale twine drives — since session
    2026-10-15-twine-gate-contract-001 the first bale with `bale contract
    --json`), the version whose recordings the tests replay (`recordings`,
    which names fixtures/bale-<recordings>/; the floor named it until that
    session), the carried contract line the tests replay (`contract`, a path
    under fixtures/), the surfaces twine reads, and the vocabularies bale
    declares (keyed by the transition-table axis they are the keys of), as
    data a test can walk. `data` is the whole TOML document."""

    path: Path
    floor: str
    recordings: str
    contract: str
    surfaces: list[dict[str, Any]]
    data: dict[str, Any]
    vocabularies: dict[str, dict[str, Any]] = field(default_factory=dict)


def _version_key(path: Path, bale: dict[str, Any], key: str) -> str:
    """`[bale] <key>` as a version string of three dotted integers, or a
    ManifestError naming it."""
    value = bale.get(key)
    if not isinstance(value, str) or parse_version(value.strip()) is None:
        raise ManifestError(f"{path}: [bale] {key} must be a version string of three "
                            f"dotted integers (got {value!r})")
    return value.strip()


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
    for key, why in RETIRED_BALE_KEYS.items():
        if key in bale:
            # A manifest still carrying a retired key is one twine no longer
            # reads, never one it guesses about.
            shown = "[bale.schemas]" if key == "schemas" else f"[bale] `{key}`"
            raise ManifestError(f"{path}: {shown} {why}")
    unknown = sorted(k for k in bale if k not in BALE_TABLE_KEYS)
    if unknown:
        raise ManifestError(f"{path}: [bale] holds {unknown}; its keys are exactly "
                            + ", ".join(BALE_TABLE_KEYS))
    floor = _version_key(path, bale, "floor")
    recordings = _version_key(path, bale, "recordings")
    contract = bale.get("contract")
    if not isinstance(contract, str) or not CONTRACT_PATH.fullmatch(contract):
        raise ManifestError(f"{path}: [bale] contract must be the carried contract line's "
                            f"path under fixtures/, a .json file (got {contract!r})")
    surfaces = data.get("surface", [])
    if not isinstance(surfaces, list) or not all(isinstance(s, dict) for s in surfaces):
        raise ManifestError(f"{path}: [[surface]] must be an array of tables")
    for surface in surfaces:
        check_surface_contract_fields(path, surface)
    vocabularies = load_vocabularies(path, data.get("vocabulary", []))
    log.debug("manifest %s: floor %s, recordings %s, contract %s, %d surfaces, "
              "%d vocabularies", path, floor, recordings, contract, len(surfaces),
              len(vocabularies))
    return Manifest(path, floor, recordings, contract, list(surfaces), data, vocabularies)


def _string_list(value: Any) -> bool:
    return (isinstance(value, list) and bool(value)
            and all(isinstance(v, str) and v.strip() for v in value)
            and len(set(value)) == len(value))


def check_surface_contract_fields(path: Path, surface: dict[str, Any]) -> None:
    """The fields the contract gate reads from a verb `[[surface]]` (session
    2026-10-15-twine-gate-contract-001), held to their shape:

      contract_lines      the lines of `bale contract --json`'s `json_keys`
                          the surface's reader reads; required on a verb
                          surface that lists keys and names a reader, so no
                          key twine reads goes unchecked against the contract
      outcome_vocabulary  the contract vocabulary of that line's `outcome`
                          (`open-outcome`, …), with `outcomes` — its values
                          as recorded — when one is named
      reasons             (already recorded) a refusal reason set, a list

    Raises ManifestError naming the surface and the field."""
    if surface.get("kind") != "verb":
        return
    name = f"the {surface.get('verb')!s} surface"
    reads = bool(surface.get("keys")) and bool(surface.get("read_by"))
    lines = surface.get("contract_lines")
    if lines is not None and not _string_list(lines):
        raise ManifestError(f"{path}: {name}: contract_lines must be a non-empty list of "
                            "distinct line names")
    if reads and lines is None:
        raise ManifestError(f"{path}: {name} lists keys twine reads but no contract_lines "
                            "(the contract lines whose keys the gate checks)")
    vocabulary = surface.get("outcome_vocabulary")
    outcomes = surface.get("outcomes")
    if (vocabulary is None) != (outcomes is None):
        raise ManifestError(f"{path}: {name}: outcome_vocabulary and outcomes come together")
    if vocabulary is not None and (not isinstance(vocabulary, str) or not vocabulary.strip()
                                   or not _string_list(outcomes)):
        raise ManifestError(f"{path}: {name}: outcome_vocabulary must name a contract "
                            "vocabulary and outcomes list its distinct values")
    reasons = surface.get("reasons")
    if reasons is not None and not _string_list(reasons):
        raise ManifestError(f"{path}: {name}: reasons must be a non-empty list of distinct "
                            "reason codes")


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
# 4. The gate: the floor and bale's contract
# ---------------------------------------------------------------------------

# Running `bale contract --json` (session 2026-10-15-twine-gate-contract-001):
# bale prints one line of about 8.5 KB from tables it holds in memory, so a
# run that takes longer than this is stuck and is killed by the seam; a
# stdout past the cap is not a contract line, whatever it is.
CONTRACT_TIMEOUT_SECONDS = 30.0
CONTRACT_STDOUT_CAP_BYTES = 1024 * 1024
# The `outcome` a contract line carries (bale's CONTRACT_OUTCOMES).
CONTRACT_OUTCOME = "contract"
# How much of bale's stderr a refusal quotes when the run itself failed.
CONTRACT_STDERR_QUOTED = 300

# What twine's code dispatches on, by the contract vocabulary that holds it —
# the spellings the readers compare a line's `outcome` with, so the gate can
# hold an install to them. Each reader keeps its own constant and a test holds
# every one of them to this table (tests/test_bale_check.py), so a reader
# cannot start dispatching on a spelling the gate does not check:
#   open-outcome    carry bundle and twine.inflight (opened, second-desk;
#                   rehearsed under --check; open-refused named and quoted)
#   relay-outcome   carry exchange (relayed; re-emitted and relay-refused
#                   each named as what it is)
#   unlock-outcome  kill (unlocked is the close; unlock-refused carries the
#                   reason the hand line keys on)
DISPATCHED_OUTCOMES: dict[str, tuple[str, ...]] = {
    "open-outcome": ("opened", "second-desk", "rehearsed", "open-refused"),
    "relay-outcome": ("relayed", "re-emitted", "relay-refused"),
    "unlock-outcome": ("unlocked", "unlock-refused"),
}
# The refusal reasons twine dispatches on, by the twine verb that reads them
# (a surface's `read_by`; the reader rather than the bale verb, as
# surface_keys keys, so no bale verb's name is spelled here beyond the argv
# builders): one — `twine kill`'s hand line is `bale revert <sid>` exactly
# when the unlock refusal's reason is hold-branch (session
# 2026-10-07-twine-kill-reason-002). The gate looks it up in the contract's
# refusal_reasons under the surface's own `verb`.
DISPATCHED_REASONS: dict[str, tuple[str, ...]] = {"kill": ("hold-branch",)}


@dataclass(frozen=True)
class ContractVerdict:
    """The gate's second half: what `<root>/bin/bale contract --json` printed,
    held to what twine reads.

    `asked` is whether the gate ran it (it does not below the floor: no bale
    below 0.4.54 has the verb); `argv` what it ran; `exit_code` bale's exit
    (None when it never exited on its own, or never ran). `bale_version` is
    the line's (None when no line could be read); `sha256` the sha256 of
    stdout as printed (None when nothing was printed). `problems` are the
    refusing facts, one sentence each; `moved` is the subset that says
    something twine reads moved in a contract that read cleanly — the
    vocabularies, a line's keys, an outcome or reason twine dispatches on —
    which is the one case a recording session is for. `notes` are reported
    additions: a value a contract vocabulary or refusal-reason set gained
    that twine records but does not dispatch on, never refused."""

    asked: bool
    argv: tuple[str, ...]
    exit_code: int | None
    bale_version: str | None
    sha256: str | None
    problems: tuple[str, ...]
    moved: tuple[str, ...]
    notes: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.asked and not self.problems

    def as_json(self) -> dict[str, Any]:
        """`twine bale check --json`'s `contract` object, exactly these keys."""
        return {"ok": self.ok, "bale_version": self.bale_version, "sha256": self.sha256,
                "problems": list(self.problems), "notes": list(self.notes)}

    def summary(self) -> str:
        """The human line's verdict."""
        if self.ok:
            return (f"ok — bale {self.bale_version}'s line (sha256 {self.sha256}) states "
                    "everything twine reads")
        return "NOT OK — " + "; ".join(self.problems)


def parse_contract_stdout(stdout: bytes) -> tuple[dict[str, Any] | None, str | None]:
    """The one JSON object line `bale contract --json` prints, or None and
    the problem: nothing printed, more than one line, not UTF-8, not JSON,
    or JSON that is not an object. One line is the bytes up to a single
    trailing newline (bale ends its line with one); a blank second line is
    a second line."""
    if not stdout:
        return None, "bale contract --json printed nothing"
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, f"bale contract --json printed bytes that are not UTF-8 ({exc.reason})"
    body = text[:-1] if text.endswith("\n") else text
    if "\n" in body:
        return None, (f"bale contract --json printed {body.count(chr(10)) + 1} lines, "
                      "not one")
    try:
        obj = json.loads(body)
    except json.JSONDecodeError as exc:
        return None, f"bale contract --json's line is not JSON: {exc}"
    if not isinstance(obj, dict):
        return None, (f"bale contract --json's line is JSON but not an object (a "
                      f"{type(obj).__name__})")
    return obj, None


def _values(table: Any, name: str) -> list[str] | None:
    """`table[name]["values"]` for a contract vocabulary, or `table[name]`
    for a refusal-reason set (a list), when it is a list of strings; None
    when it is absent or not that shape."""
    if not isinstance(table, dict) or name not in table:
        return None
    entry = table[name]
    values = entry.get("values") if isinstance(entry, dict) else entry
    if isinstance(values, list) and all(isinstance(v, str) for v in values):
        return values
    return None


def _quoted(values: list[str]) -> str:
    return ", ".join(repr(v) for v in values)


def _plural(values: list[str], one: str, many: str) -> str:
    return one if len(values) == 1 else many


def contract_findings(manifest: Manifest, line: Mapping[str, Any],
                      installed: str | None) -> tuple[list[str], list[str], list[str]]:
    """Hold one contract line (already parsed) to what twine reads. Returns
    (problems, moved, notes): every refusing fact, the subset that says
    something twine reads moved, and the reported additions. Pure: the
    manifest, the line and bin/VERSION's text in, sentences out.

    Refused, each named:
      - an `outcome` that is not "contract";
      - a `bale_version` that is not bin/VERSION's text (or cannot be held to
        it, bin/VERSION not having read);
      - a `[[vocabulary]]` axis the contract does not state, or states with
        another set of values — a value added or removed, named with the axis
        (the transition table must stay total, D17);
      - a key a verb `[[surface]]` lists in `keys` that the contract's
        `json_keys` does not give one of the lines its reader reads
        (`contract_lines`) — or such a line the contract does not state;
      - an outcome twine dispatches on (DISPATCHED_OUTCOMES) that the
        contract's vocabulary lacks, and a reason it dispatches on
        (DISPATCHED_REASONS: hold-branch, by its reader) that the contract's
        `refusal_reasons` for the surface's verb lacks.
    Reported, never refused: a value a surface's outcome vocabulary or
    refusal-reason set gained beyond what the manifest records, or lost when
    twine does not dispatch on it."""
    problems: list[str] = []
    moved: list[str] = []
    notes: list[str] = []

    def refuse(sentence: str, *, is_move: bool) -> None:
        problems.append(sentence)
        if is_move:
            moved.append(sentence)

    outcome = line.get("outcome")
    if outcome != CONTRACT_OUTCOME:
        refuse(f"bale contract --json's line has outcome {outcome!r}, not "
               f"{CONTRACT_OUTCOME!r}", is_move=False)
    version = line.get("bale_version")
    if not isinstance(version, str):
        refuse(f"bale contract --json's line carries no bale_version string (got "
               f"{version!r})", is_move=False)
    elif installed is None:
        refuse(f"the contract's bale_version {version} cannot be held to bin/VERSION, "
               "which did not read", is_move=False)
    elif version != installed:
        refuse(f"the contract's bale_version {version} disagrees with bin/VERSION, which "
               f"reads {installed} — the line is not this install's", is_move=False)

    # A section that is not an object is one shape problem, named once; a
    # section that is an object — even an empty one — is read, and every
    # thing twine reads that it does not state is named.
    vocabularies = line.get("vocabularies")
    has_vocabularies = isinstance(vocabularies, dict)
    if not has_vocabularies:
        refuse("bale contract --json's line has no `vocabularies` object", is_move=False)
        vocabularies = {}
    for axis, entry in manifest.vocabularies.items():
        if not has_vocabularies:
            break
        stated = _values(vocabularies, axis)
        if stated is None:
            refuse(f"the contract states no {axis} vocabulary, which the transition "
                   "table keys on", is_move=True)
            continue
        recorded = list(entry["values"])
        added = [v for v in stated if v not in recorded]
        removed = [v for v in recorded if v not in stated]
        if added:
            refuse(f"the contract's {axis} vocabulary adds {_quoted(added)}, which the "
                   "consumption manifest does not record — the transition table would "
                   f"have no row for {_plural(added, 'it', 'them')} (D17)", is_move=True)
        if removed:
            refuse(f"the contract's {axis} vocabulary no longer lists {_quoted(removed)}, "
                   "which the consumption manifest records and the transition table keys "
                   "on", is_move=True)

    json_keys = line.get("json_keys")
    has_json_keys = isinstance(json_keys, dict)
    if not has_json_keys:
        refuse("bale contract --json's line has no `json_keys` object", is_move=False)
        json_keys = {}
    refusal_reasons = line.get("refusal_reasons")
    has_reasons = isinstance(refusal_reasons, dict)
    if not has_reasons:
        refuse("bale contract --json's line has no `refusal_reasons` object", is_move=False)
        refusal_reasons = {}
    for surface in manifest.surfaces:
        if surface.get("kind") != "verb":
            continue
        verb = str(surface.get("verb"))
        keys = [k for k in surface.get("keys") or [] if isinstance(k, str)]
        for name in surface.get("contract_lines") or []:
            if not has_json_keys:
                break
            stated = json_keys.get(name)
            if not isinstance(stated, list):
                refuse(f"the contract states no keys for bale's {name} line, which twine "
                       f"reads (the {verb} surface)", is_move=True)
                continue
            lacking = [k for k in keys if k not in stated]
            if lacking:
                refuse(f"the contract's {name} line lacks the "
                       f"{_plural(lacking, 'key', 'keys')} {_quoted(lacking)}, which twine "
                       f"reads (the {verb} surface)", is_move=True)
        vocabulary = surface.get("outcome_vocabulary")
        if isinstance(vocabulary, str) and has_vocabularies:
            dispatched = list(DISPATCHED_OUTCOMES.get(vocabulary, ()))
            stated = _values(vocabularies, vocabulary)
            if stated is None:
                refuse(f"the contract states no {vocabulary} vocabulary, which twine "
                       f"dispatches on (the {verb} surface)", is_move=True)
            else:
                _held(f"the contract's {vocabulary} vocabulary", False, stated,
                      list(surface.get("outcomes") or []), dispatched,
                      "an outcome", refuse, notes)
        reasons = surface.get("reasons")
        if isinstance(reasons, list) and has_reasons:
            dispatched = [reason for reader in surface.get("read_by") or []
                          for reason in DISPATCHED_REASONS.get(reader, ())]
            stated = _values(refusal_reasons, verb)
            if stated is None:
                if dispatched:
                    refuse(f"the contract states no {verb} refusal reasons, and twine "
                           f"dispatches on {_quoted(dispatched)}", is_move=True)
                else:
                    notes.append(f"the contract states no {verb} refusal reasons, which "
                                 "the consumption manifest records (reported, not refused: "
                                 "twine dispatches on none)")
            else:
                _held(f"the contract's {verb} refusal reasons", True, stated, list(reasons),
                      dispatched, "a reason", refuse, notes)
    return problems, moved, notes


def _held(what: str, plural: bool, stated: list[str], recorded: list[str],
          dispatched: list[str], kind: str, refuse: Callable[..., None],
          notes: list[str]) -> None:
    """One outcome vocabulary (`plural` false) or refusal-reason set (`plural`
    true): a value twine dispatches on that the contract lacks refuses; a
    value the contract adds beyond what the manifest records, or drops that
    twine does not dispatch on, is a note."""
    lack, add, lists = ("lack", "add", "list") if plural else ("lacks", "adds", "lists")
    for value in dispatched:
        if value not in stated:
            refuse(f"{what} {lack} {value!r}, {kind} twine dispatches on", is_move=True)
    added = [v for v in stated if v not in recorded]
    if added:
        notes.append(f"{what} {add} {_quoted(added)}, which the consumption manifest "
                     "does not record (reported, not refused: twine does not dispatch on "
                     f"{_plural(added, 'it', 'them')})")
    dropped = [v for v in recorded if v not in stated and v not in dispatched]
    if dropped:
        notes.append(f"{what} no longer {lists} {_quoted(dropped)}, which the "
                     "consumption manifest records (reported, not refused: twine does "
                     f"not dispatch on {_plural(dropped, 'it', 'them')})")


def check_contract(manifest: Manifest, root: Path, installed: str | None,
                   run: Callable[..., Any], env: Mapping[str, str] | None = None
                   ) -> ContractVerdict:
    """Run `<root>/bin/bale contract --json` — the resolved root's own
    executable, through the run seam, stdin closed, with a timeout and a
    stdout cap — and hold its one line to what twine reads
    (contract_findings). Never raises for anything bale does: a bale that
    cannot be started, is killed, exits non-zero or prints anything but one
    JSON object line is a verdict whose problems name it."""
    argv = contract_argv(root / EXECUTABLE_RELPATH)
    log.info("asking bale for its contract: %s", " ".join(argv))
    try:
        result = run(argv, cwd=None, stdin=None, timeout=CONTRACT_TIMEOUT_SECONDS,
                     env=None if env is None else dict(env),
                     stdout_cap=CONTRACT_STDOUT_CAP_BYTES)
    except process.RunError as exc:
        problem = f"bale contract --json could not be started: {exc.strerror or exc}"
        log.info("%s", problem)
        return ContractVerdict(True, tuple(argv), None, None, None, (problem,), (), ())
    stdout = bytes(result.stdout or b"")
    digest = hashlib.sha256(stdout).hexdigest() if stdout else None
    problems: list[str] = []
    if result.timed_out:
        problems.append(f"bale contract --json was killed after "
                        f"{CONTRACT_TIMEOUT_SECONDS:g}s without exiting")
    elif result.stdout_capped:
        problems.append(f"bale contract --json printed more than "
                        f"{CONTRACT_STDOUT_CAP_BYTES} bytes and was killed")
    elif result.exit_code != 0:
        said = bytes(result.stderr or b"").decode("utf-8", "replace").strip()
        if len(said) > CONTRACT_STDERR_QUOTED:
            said = said[-CONTRACT_STDERR_QUOTED:]
        problems.append(f"bale contract --json exited {result.exit_code}"
                        + (f" (stderr: {said!r})" if said else " with nothing on stderr"))
    if problems:
        log.info("contract run failed: %s", "; ".join(problems))
        return ContractVerdict(True, tuple(argv), result.exit_code, None, digest,
                               tuple(problems), (), ())
    line, problem = parse_contract_stdout(stdout)
    if line is None:
        log.info("contract line unreadable: %s", problem)
        return ContractVerdict(True, tuple(argv), result.exit_code, None, digest,
                               (problem or "bale contract --json printed no line",), (), ())
    version = line.get("bale_version")
    found, moved, notes = contract_findings(manifest, line, installed)
    for sentence in found:
        log.info("contract: %s", sentence)
    for sentence in notes:
        log.info("contract note: %s", sentence)
    return ContractVerdict(True, tuple(argv), result.exit_code,
                           version if isinstance(version, str) else None, digest,
                           tuple(found), tuple(moved), tuple(notes))


def contract_not_asked(root: Path, installed: str, floor: str) -> ContractVerdict:
    """The verdict for an install below the floor: the floor is the first
    bale with `contract --json`, so the gate does not run a verb the install
    cannot have — said, never silently skipped."""
    return ContractVerdict(False, tuple(contract_argv(root / EXECUTABLE_RELPATH)), None,
                           None, None,
                           (f"bale contract --json was not run (no bale below the floor "
                            f"{floor} has it)",), (), ())


@dataclass(frozen=True)
class CheckResult:
    """`twine bale check`'s facts: the floor, what is installed (None when
    unreadable), where, the contract verdict (None when no install was
    found), and whether the gate admits the install."""

    floor: str
    installed: str | None
    root: Path | None
    source: str | None
    contract: ContractVerdict | None
    ok: bool
    reason: str

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
                "contract": None if self.contract is None else self.contract.as_json(),
                "ok": self.ok, "reason": self.reason}

    def as_lines(self) -> list[str]:
        where = "no install found" if self.root is None else str(self.root)
        contract = ("(not checked: no install)" if self.contract is None
                    else self.contract.summary())
        notes = [] if self.contract is None else list(self.contract.notes)
        return [f"floor:     {self.floor} (twine drives this bale or any above it)",
                f"installed: {self.installed if self.installed else '(unreadable)'}",
                f"root:      {where}" + (f"  (from {self.source})" if self.source else ""),
                f"contract:  {contract}",
                *(f"note:      {note}" for note in notes),
                f"check:     {'ok' if self.ok else 'FAIL'} — {self.reason}"]


def check(manifest: Manifest, root: Root, run: Callable[..., Any],
          env: Mapping[str, str] | None = None) -> CheckResult:
    """The gate (D2; since session 2026-10-15-twine-gate-contract-001 the
    floor plus bale's contract): ok exactly when an install was found, its
    `bin/VERSION` reads and parses as three dotted integers at or above the
    manifest's floor (compared as a tuple), and `<root>/bin/bale contract
    --json`, run through `run` (the seam), prints one contract line for that
    version stating everything twine reads (check_contract). No file under
    `<root>/schemas/` is read.

    Every failing fact is named at once in the reason — a version that does
    not parse and a contract that lacks a key are two sentences, not the
    first of them — and nothing raises: a wrong or absent install is a check
    result, not an internal error. Below the floor the contract is not asked
    (the floor is the first bale with the verb), and the reason says so."""
    if root.path is None:
        return CheckResult(manifest.floor, None, None, None, None, False,
                           f"no bale install found ({root.detail})")
    problems: list[str] = []
    installed, detail = read_installed_version(root.path)
    below = False
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
            below = True
    if below and installed is not None:
        contract = contract_not_asked(root.path, installed, manifest.floor)
    else:
        contract = check_contract(manifest, root.path, installed, run, env)
    problems.extend(contract.problems)
    if problems:
        return CheckResult(manifest.floor, installed, root.path, root.source, contract,
                           False, "; ".join(problems))
    added = (f"; {len(contract.notes)} addition{'s' if len(contract.notes) != 1 else ''} "
             "reported, none refused") if contract.notes else ""
    return CheckResult(manifest.floor, installed, root.path, root.source, contract, True,
                       f"installed {installed} is at or above the floor {manifest.floor}, "
                       "and its contract (bale contract --json) states everything twine "
                       f"reads{added}")


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
# The gate's argv after the executable (session 2026-10-15-twine-gate-contract-001):
# the verb bale 0.4.54 added and `--json`, its only form that prints a line.
CONTRACT_ARGS = ("contract", "--json")


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
    def contract_ok(self) -> bool | None:
        """Whether the install's contract (`bale contract --json`) states
        everything twine reads; None when the gate never asked (no root, no
        manifest, or an install below the floor). Since session 2026-10-15-twine-gate-contract-001, in
        the place of `schemas_match`."""
        if (self.verdict is None or self.verdict.contract is None
                or not self.verdict.contract.asked):
            return None
        return self.verdict.contract.ok

    @property
    def drive_refusal(self) -> str | None:
        """Why twine will not drive this bale, or None when it will (D2).

        Twine drives a bale the gate admits — exactly one `twine bale check`
        reports ok — and refuses every other before starting it. The
        transition table keys on bale's outcome and closure vocabularies, and
        the readers on the keys and outcomes of four lines; the floor is the
        first bale that states them (`bale contract --json`), and the gate
        holds the install's statement to twine's. A bale the gate does not
        admit may answer in spellings twine has no move for: the surprise D17
        rules out. When the contract read cleanly and something twine reads
        moved, the refusal says bale changed it and that a recording session
        lands the new spelling (the moved facts are in the reason); otherwise
        it says which bale twine drives."""
        if self.path is None:
            return self.detail
        if self.floor is None or self.verdict is None:
            return ("the floor is unknown (share/bale-consumption.toml is "
                    "unusable), so twine cannot tell whether any bale states the "
                    "spellings its transition table and readers key on — it drives "
                    "only a bale at or above the floor whose contract (bale contract "
                    "--json) states everything twine reads (D2)")
        if self.verdict.ok:
            return None
        refusal = f"bale at {self.root.path} is not one twine drives: {self.verdict.reason}"
        contract = self.verdict.contract
        if contract is not None and contract.moved:
            refusal += ("; bale changed something twine reads (named above), so twine "
                        "would meet spellings it has no move for (D17) — a recording "
                        "session lands the new spelling")
        # Anything else that failed — the version, or a contract that could not
        # be read or is not this install's — is about which bale is installed.
        other = (self.verdict.floor_admits is not True or contract is None
                 or len(contract.problems) > len(contract.moved))
        if other:
            refusal += (f"; twine drives only a bale at or above the floor {self.floor} "
                        "whose contract (bale contract --json) states everything twine "
                        "reads (D2)")
        return refusal

    def as_json(self) -> dict[str, Any]:
        return {"executable": None if self.path is None else str(self.path),
                "root": None if self.root.path is None else str(self.root.path),
                "source": self.root.source, "installed": self.installed,
                "floor": self.floor, "floor_admits": self.floor_admits,
                "contract_ok": self.contract_ok}


def locate_executable(explicit: str | None, env: Mapping[str, str],
                      which: Callable[[str], str | None],
                      run: Callable[..., Any]) -> Executable:
    """`<root>/bin/bale`, the root resolved exactly as `bale check` does
    (`--bale-root`, TWINE_BALE_ROOT, then PATH), with the gate's verdict
    computed by `check` itself — `run`, the caller's seam, runs the
    install's `contract --json` — so a carry verb and `bale check` can never
    disagree about an install. The tests pin TWINE_BALE_ROOT, so a bale on
    the operator's PATH is never what a test runs (cli-contract.md §8).
    Whether the file exists is learned by starting it: a root with no
    `bin/bale` is a RunError at the seam, which the gate reports."""
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
    verdict = None if manifest is None else check(manifest, root, run, env)
    path = root.path / EXECUTABLE_RELPATH
    log.info("bale executable: %s (%s; %s; gate %s)", path, root.detail, detail,
             "unknown" if verdict is None else ("admits" if verdict.ok else "refuses"))
    return Executable(root, path, installed, floor, detail, verdict, manifest)


def contract_argv(executable: Path) -> list[str]:
    """`bale contract --json` — the gate's one argv (session
    2026-10-15-twine-gate-contract-001): the install's own executable, the
    verb and `--json`, nothing else. bale prints one JSON line stating its
    vocabularies, refusal reasons and the keys of every `--json` line."""
    return [str(executable), *CONTRACT_ARGS]


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

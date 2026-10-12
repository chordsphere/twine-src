"""fixtures/README.md's rule, as code: the naming rule (the argv
normalized to roles, the groups, `<where>`, the outcome groups and their
collision rule, the `.stderr` sibling) and the README row shapes.

Shared by `tests/helpers.py` (which re-exports it, with the pin as the
default version) and `bin/twine-land-recordings` (which lands a version's
recordings from a recorder's paste-back) — one rule, never re-derived
(session 2026-10-12-twine-pin-051-001). It lives under tests/ rather than
twine/ on purpose: the naming rule spells bale verbs as string constants
(`"relay"`, `"apply"`, `"unlock"`, `"open"`), and the guards in
tests/test_carry_bale.py, tests/test_kill.py and tests/test_carry_bundle.py
hold that no module under twine/ but twine/bale.py carries those tokens —
the rule names recordings, it builds no argv, and it is not twine's code.

Pure and stdlib-only: no import of twine, no file read except where a
function says so, so the lander can import it under `python3 -I -S -B`
without loading the CLI. Every path function takes the version
explicitly; tests/helpers.py's wrappers pass FLOOR (PIN until session
2026-10-12-twine-pin-floor-002).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The outcome group's separator in a fixture name: between the normalized
# name and the extension, `+<outcome>` and, where that still collides,
# `+<reason>` (fixtures/README.md, "Outcome groups").
GROUP_SEP = "+"
# The directory a recording ran in, as a test (or the recorder's
# annotation) names it, and the `<where>` it lands under.
WHERE = {"repo": "twine-src", "scratch": "scratch"}
WHERE_ANYWHERE = "anywhere"
# Fixtures that are not the stdout of a `bale` argv: the crafter's
# emissions land under their own `<where>`.
EMISSION_TOOLS = {"crafter": "tools/craft_response.py"}
# A recording's stderr lands beside its stdout file: the same name with
# this extension in place of `.json`/`.txt` (since bale 0.4.51).
STDERR_EXT = ".stderr"
# The installed schemas the gate hashes (share/bale-consumption.toml
# [bale.schemas]) land byte-exact under the floor's directory, in this
# subdirectory, named as installed (since session
# 2026-10-12-twine-pin-floor-002). They are not recordings — no argv printed
# them, the recorder does not derive them, and they have no stderr sibling —
# so the lander leaves this subdirectory alone and fixtures/README.md lists
# them in a table of their own (SCHEMA_ROW).
SCHEMAS_WHERE = "schemas"


class Role(str):
    """A per-run argv value's role, standing in for the value in a fixture
    name (`sid`, `stdin`, `file`, `tarball`, `bundle`, `goal`). A Role is
    its own `_` group: it is never joined to the flag before it, because
    it is not that flag's value."""


def fixture_key(argv: list[str]) -> list[str]:
    """The argv after `bale`, normalized for naming a fixture: the values
    that differ per run are replaced by their roles (fixtures/README.md,
    "Per-run values"), one rule per verb. `relay <sid> …` keys as relay,
    sid, then `stdin` for `-` and `file` for any other positional; every
    positional after `apply` is the tarball; a positional right after
    `unlock` is the sid (session 5b); every positional after `open` is the
    bundle and the positional right after `pack` is the goal (session
    2026-10-07-twine-pin-049-001) — a flag's value (`--slug ro`, `--sid
    <sid>` on stats) stays. Any other argv is its own key. A token that is
    already a Role keeps its place, so normalizing is idempotent."""
    argv = [a if isinstance(a, Role) else str(a) for a in argv]
    if argv[:1] == ["relay"] and len(argv) >= 2:
        key: list[str] = ["relay", Role("sid")]
        for token in argv[2:]:
            if isinstance(token, Role):
                key.append(token)
            elif token == "-":
                key.append(Role("stdin"))
            elif token.startswith("-"):
                key.append(token)
            else:
                key.append(Role("file"))
        return key
    if argv[:1] == ["apply"]:
        return ["apply"] + [t if t.startswith("-") else Role("tarball")
                            for t in argv[1:]]
    if argv[:1] == ["unlock"] and len(argv) >= 2 and not argv[1].startswith("-"):
        # `unlock <sid> --reason aborted --json` (session 5b): the sid is per run.
        return ["unlock", Role("sid"), *argv[2:]]
    if argv[:1] == ["open"]:
        # `open [--check] <bundle> --json`: the bundle file is per run.
        return ["open"] + [t if t.startswith("-") else Role("bundle")
                           for t in argv[1:]]
    if argv[:1] == ["pack"] and len(argv) >= 2 and not argv[1].startswith("-"):
        # `pack <goal> --slug ro …`: the goal is per run; the flags' values stay.
        return ["pack", Role("goal"), *argv[2:]]
    return argv


def fixture_where(cwd: str) -> str:
    return WHERE.get(cwd, WHERE_ANYWHERE)


def fixture_stem(argv: list[str]) -> tuple[str, str]:
    """The normalized name and extension of the recording of `argv`: each
    flag joined to the values that follow it with `-`, a Role a group of
    its own, the groups joined with `_`; `.json` when --json is among the
    flags, else `.txt`."""
    argv = list(argv)
    key = argv if any(isinstance(t, Role) for t in argv) else fixture_key(argv)
    groups: list[str] = []
    for token in key:
        if token.startswith("-") or not groups or isinstance(token, Role):
            groups.append(str(token))
        else:
            groups[-1] += "-" + token
    return "_".join(groups), (".json" if "--json" in key else ".txt")


def fixture_relpath_at(version: str, argv: list[str], cwd: str,
                       group: str | None = None) -> str:
    """The fixtures/ path a recorded bale output of `version` lands at:

      fixtures/bale-<version>/<where>/<verb>_<flag[-value…]>[_…][+<group>].<ext>

    `cwd` is "repo" (twine-src/), "scratch" (scratch/) or anything else
    (anywhere/); `group` is the outcome group, `<outcome>` or
    `<outcome>+<reason>`, None for an argv recorded once."""
    stem, ext = fixture_stem(argv)
    tail = f"{GROUP_SEP}{group}" if group else ""
    return f"fixtures/bale-{version}/{fixture_where(cwd)}/{stem}{tail}{ext}"


def emission_relpath_at(version: str, tool: str, argv: list[str]) -> str:
    """fixtures/bale-<version>/<tool>/<flag[-value…]>[_…].txt for a bale
    tool run with `argv` — fixture_stem's grouping, with a `-` value
    (stdin) spelled `stdin` so no name carries a bare dash."""
    if tool not in EMISSION_TOOLS:
        raise ValueError(f"unknown emitting tool {tool!r}")
    spelled = ["stdin" if token == "-" else token for token in argv]
    groups: list[str] = []
    for token in spelled:
        if token.startswith("-") or not groups:
            groups.append(token)
        else:
            groups[-1] += "-" + token
    return f"fixtures/bale-{version}/{tool}/{'_'.join(groups)}.txt"


def carried_relpath_at(version: str, kind: str, identity: str,
                       to: str | None = None) -> str:
    """fixtures/bale-<version>/carried/<kind>_<identity>[_to-<addressee>].txt
    for a carried paste: the block kind, the slug or sid its sentinel
    names, and for a relay block its addressee."""
    tail = f"_to-{to}" if to else ""
    return f"fixtures/bale-{version}/carried/{kind}_{identity}{tail}.txt"


def split_group(name: str) -> tuple[str, str | None]:
    """A fixture file name without its extension, split into the
    normalized name and its outcome group (None when plain)."""
    stem, sep, group = name.partition(GROUP_SEP)
    return stem, (group if sep else None)


def stderr_relpath(relpath: str) -> str:
    """The `.stderr` sibling of a recording's stdout file: the same name,
    the extension `.stderr` in place of `.json` or `.txt`."""
    base, dot, ext = relpath.rpartition(".")
    if not dot or "/" in ext:
        raise ValueError(f"{relpath!r} has no extension to replace")
    return base + STDERR_EXT


def echoed_argv(command: str) -> list[str]:
    """The argv after `bale` from a command as the recorder echoed it
    (`argv: $*`, so the quoting is gone) or as a README row writes it,
    `bale` included. A token never carries a space except `pack`'s goal,
    the one positional that does: everything between `pack` and its first
    flag is the goal. Any other verb splits on single spaces."""
    tokens = command.split(" ")
    if tokens[:1] != ["bale"]:
        raise ValueError(f"not a bale command: {command!r}")
    argv = tokens[1:]
    if argv[:1] == ["pack"]:
        cut = next((i for i, t in enumerate(argv[1:], 1) if t.startswith("-")), len(argv))
        if cut > 1:
            argv = ["pack", " ".join(argv[1:cut]), *argv[cut:]]
    return argv


class CollisionError(ValueError):
    """The collision rule cannot name a recording: two share a normalized
    name and an outcome and the line carries no `reason` to tell them
    apart (a tag is the README's to assign, never invented here)."""


def assign_groups(recordings: list[tuple[str, str | None, str | None]]) -> list[str | None]:
    """The collision rule (fixtures/README.md, "Outcome groups"): given,
    per recording, its normalized name with extension (`stem + ext`), its
    line's `outcome` and its line's `reason` (None when it has none, or the
    output is not a JSON line), the outcome group each one carries — None
    for a name recorded once in the version, else `<outcome>`, and
    `<outcome>+<reason>` where two share the outcome. Raises
    CollisionError when a group cannot be formed from the lines alone."""
    by_name: dict[str, list[int]] = {}
    for i, (name, _, _) in enumerate(recordings):
        by_name.setdefault(name, []).append(i)
    groups: list[str | None] = [None] * len(recordings)
    for name, members in by_name.items():
        if len(members) == 1:
            continue
        by_outcome: dict[str | None, list[int]] = {}
        for i in members:
            outcome = recordings[i][1]
            if not isinstance(outcome, str) or not outcome:
                raise CollisionError(f"{name} is recorded {len(members)} times and "
                                     f"recording {i + 1}'s output names no outcome")
            by_outcome.setdefault(outcome, []).append(i)
        for outcome, same in by_outcome.items():
            if len(same) == 1:
                groups[same[0]] = outcome
                continue
            reasons = [recordings[i][2] for i in same]
            if any(not isinstance(r, str) or not r for r in reasons) \
                    or len(set(reasons)) != len(reasons):
                raise CollisionError(
                    f"{name}: {len(same)} recordings share outcome {outcome!r} and their "
                    f"lines' reasons {reasons!r} do not tell them apart; a tag is the "
                    "README's to assign, not the rule's")
            for i, reason in zip(same, reasons):
                groups[i] = f"{outcome}{GROUP_SEP}{reason}"
    return groups


# ---------------------------------------------------------------------------
# The README row shapes
# ---------------------------------------------------------------------------

# A recording's row: file (the path under fixtures/), command, ran in, exit
# (a number, or `unrecorded`), bytes, sha256 — and, since bale 0.4.51, the
# stderr sibling's bytes and sha256. The six-column rows of 0.4.45 and
# 0.4.49 stay as history and parse as rows without stderr.
RECORDING_ROW = re.compile(
    r"^\| `(?P<file>bale-[^`]+)` \| `(?P<cmd>[^`]+)` \| `(?P<ran>[^`]+)` "
    r"\| (?P<exit>\d+|unrecorded) \| (?P<bytes>\d+) \| `(?P<sha>[0-9a-f]{64})` "
    r"\|(?: (?P<sbytes>\d+) \| `(?P<ssha>[0-9a-f]{64})` \|)?$", re.M)
# A carried paste's row: file, emission (prose), received (line endings,
# bytes, sha256), bytes, sha256.
CARRIED_ROW = re.compile(
    r"^\| `(?P<file>bale-[^`]+/carried/[^`]+)` \| [^|]+ "
    r"\| (?P<ending>CRLF|LF) (?P<rbytes>\d+) `(?P<rsha>[0-9a-f]{64})` "
    r"\| (?P<bytes>\d+) \| `(?P<sha>[0-9a-f]{64})` \|$", re.M)
UNRECORDED = "unrecorded"
RECORDING_HEADER = ("| file | command | ran in | exit | bytes | sha256 "
                    "| stderr bytes | stderr sha256 |\n|---|---|---|---|---|---|---|---|")


@dataclass(frozen=True)
class Row:
    """One recording's README row. `exit` is an int or "unrecorded";
    `stderr_bytes` and `stderr_sha256` are None on a six-column row."""

    file: str
    command: str
    ran_in: str
    exit: int | str
    bytes: int
    sha256: str
    stderr_bytes: int | None
    stderr_sha256: str | None

    @property
    def has_stderr(self) -> bool:
        return self.stderr_sha256 is not None


def parse_rows(text: str) -> dict[str, Row]:
    """Every recording row of a fixtures/README.md text, keyed by its
    fixtures/ path (`fixtures/<file>`). A file listed twice is an error,
    never a silent pick."""
    rows: dict[str, Row] = {}
    for m in RECORDING_ROW.finditer(text):
        key = f"fixtures/{m['file']}"
        if key in rows:
            raise ValueError(f"fixtures/README.md lists {m['file']} twice")
        rows[key] = Row(m["file"], m["cmd"], m["ran"],
                        UNRECORDED if m["exit"] == UNRECORDED else int(m["exit"]),
                        int(m["bytes"]), m["sha"],
                        int(m["sbytes"]) if m["sbytes"] is not None else None,
                        m["ssha"])
    return rows


# A schema fixture's row (fixtures/README.md, the floor's schemas table):
# file, bytes, sha256 — three columns, which RECORDING_ROW (a backticked
# command in its second) and CARRIED_ROW never match.
SCHEMA_ROW = re.compile(
    r"^\| `(?P<file>bale-[^`/]+/schemas/[^`/]+)` \| (?P<bytes>\d+) "
    r"\| `(?P<sha>[0-9a-f]{64})` \|$", re.M)


def schemas_relpath_at(version: str) -> str:
    """fixtures/bale-<version>/schemas — where the schema files the gate
    hashes land for the version the floor names."""
    return f"fixtures/bale-{version}/{SCHEMAS_WHERE}"


def parse_schema_rows(text: str) -> dict[str, tuple[int, str]]:
    """Every schema row of fixtures/README.md, keyed by its fixtures/ path:
    (bytes, sha256). Raises ValueError for a file listed twice."""
    rows: dict[str, tuple[int, str]] = {}
    for m in SCHEMA_ROW.finditer(text):
        key = f"fixtures/{m['file']}"
        if key in rows:
            raise ValueError(f"{m['file']} has two schema rows")
        rows[key] = (int(m["bytes"]), m["sha"])
    return rows


def format_row(row: Row) -> str:
    """The README line for a row, eight columns when it carries stderr."""
    cells = [f"`{row.file}`", f"`{row.command}`", f"`{row.ran_in}`", str(row.exit),
             str(row.bytes), f"`{row.sha256}`"]
    if row.has_stderr:
        cells += [str(row.stderr_bytes), f"`{row.stderr_sha256}`"]
    return "| " + " | ".join(cells) + " |"

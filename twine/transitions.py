"""The transition table (twine-seed.md D17): every way a worker session or
turn can end, keyed on the closed vocabularies that name it, each with a
declared move — no default case.

The data is `share/transitions.toml`; this module loads it and checks
that it is total. Pure: it reads two of twine's own files and nothing
else — no bale install, no subprocess, no network — so `twine
transitions` answers the same whether or not bale is installed.

Four axes, each a closed set of keys:

  telemetry-outcome  bale's telemetry outcomes  } keys: the consumption
  closure-reason     bale's closure reasons     } manifest's [[vocabulary]]
  apply-outcome      `bale apply --json`'s      } (bale's spellings, read by
                     outcomes                   }  probe at the floor)
  stop               twine's API-side stop set — keys declared in the table,
                     with `loop_keys`, the ones the loop produces and no
                     model adapter may (Arc 2 R2)

and, beside the rows, the provider mappings (Arc 2 R2): `[[mapping]]`
entries, each a provider's word — a stop_reason, an error type, an HTTP
status, or a condition twine names itself — onto a key of the stop axis
(or `continues`, the turn goes on). They are the only place a provider's
word becomes twine's.

The table is ok exactly when every key of every axis has one row, every
row's move is declared, and every mapping lands on a key of the stop axis
that is not a loop key, once per word, every condition mapped. Every other
finding is a Problem naming the axis, the key, the move or the provider at
fault; nothing is ever defaulted, guessed or dropped.

`stop_keys()`, `loop_keys()` and `provider_mapping()` are the readers
outside this module's own rendering: the runtime's adapter boundary
(twine/runtime/boundary.py) takes its stop set and the loop's keys from the
first two, and a model adapter its provider's words from the third, so the
stop names are spelled once, in the table, and nowhere in code.

Sections:
  1. Shapes: axes, moves, rows, mappings, problems   (~line 59)
  2. Loading the table                               (~line 232)
  3. Checking it is total                            (~line 561)
  4. Rendering                                       (~line 638)
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from twine import TRANSITIONS_TABLE
from twine.bale import Manifest

log = logging.getLogger("twine.transitions")

# ---------------------------------------------------------------------------
# 1. Shapes: axes, moves, rows, mappings, problems
# ---------------------------------------------------------------------------

# Who performs a move — exactly one of these. Twine holds no intent (N4):
# a move that needs a decision names the planner or the operator.
ACTORS = ("twine", "operator", "planner")
# Where an axis's keys come from.
SOURCE_BALE = "bale"     # the consumption manifest's [[vocabulary]] entry
SOURCE_TWINE = "twine"   # the table's own `keys`
SOURCES = (SOURCE_BALE, SOURCE_TWINE)
# Spellings that would make a key a default case. D17 has none: a key so
# spelled is refused on any axis, whatever its source.
CATCH_ALL_KEYS = frozenset({"*", "_", "any", "default", "else", "fallback",
                            "other", "others", "rest", "unknown"})
# What a mapping's `word` is (Arc 2 R2): the provider's stop_reason, an error
# type (an error body's or an SSE error event's), an HTTP status, or a
# condition twine names itself because the provider has no word for it.
MAPPING_ON = ("stop_reason", "error_type", "status", "condition")
# The conditions every provider maps — what a model adapter meets that no
# provider word names. Each is a word of `on = "condition"` rows; a provider
# with any mapping must map them all (missing-mapping). None is a stop key:
# they name what happened, the mapping names what it means.
CONDITIONS = ("socket-timeout", "connection-error", "stream-cut",
              "unclassified-stream-error", "unlisted-stop-reason", "unlisted-status",
              "malformed-body")


@dataclass(frozen=True)
class Axis:
    """One axis: its name, rendering order, where its keys come from, the
    keys themselves (in their vocabulary's order), what a key names, and
    the home of the keys (the bale file and pointer, or the table)."""

    name: str
    order: int
    source: str
    keys: tuple[str, ...]
    means: str
    home: str
    # The keys the loop produces and no adapter may (the stop axis's
    # `loop_keys`, Arc 2 R2); None when the axis declares none.
    loop_keys: tuple[str, ...] | None = None

    def as_json(self) -> dict[str, Any]:
        return {"name": self.name, "source": self.source, "home": self.home,
                "means": self.means, "keys": list(self.keys),
                "loop_keys": None if self.loop_keys is None else list(self.loop_keys)}


@dataclass(frozen=True)
class Move:
    """A declared move: who performs it and what happens next."""

    name: str
    actor: str
    description: str
    grounds: str


@dataclass(frozen=True)
class Row:
    """One (axis, key) and its move, as written in the table."""

    axis: str
    key: str
    move: str
    means: str


@dataclass(frozen=True)
class WordMapping:
    """One [[mapping]]: a provider's word onto the stop axis.

    `stop` is the key the word means, or None when the turn goes on (the
    table's `continues = true`: the model asked for tools)."""

    provider: str
    on: str
    word: str
    stop: str | None
    means: str

    @property
    def continues(self) -> bool:
        return self.stop is None

    def as_json(self) -> dict[str, Any]:
        return {"provider": self.provider, "on": self.on, "word": self.word,
                "stop": self.stop, "continues": self.continues, "means": self.means}


@dataclass(frozen=True)
class ProviderMapping:
    """One provider's words, as provider_mapping() hands them to an adapter:
    looked up by (on, word); a word no row lists is None, and the adapter
    then takes the condition row that names that case — never a guess."""

    provider: str
    rows: tuple[WordMapping, ...]

    def get(self, on: str, word: str) -> WordMapping | None:
        return next((m for m in self.rows if m.on == on and m.word == word), None)

    def condition(self, word: str) -> WordMapping:
        """The row for one of CONDITIONS; provider_mapping() refused the
        table already if any is missing, so this never comes back empty."""
        found = self.get("condition", word)
        if found is None:
            raise KeyError(f"{self.provider}: no condition row {word!r}")
        return found

    def words(self, on: str) -> tuple[str, ...]:
        return tuple(m.word for m in self.rows if m.on == on)


@dataclass(frozen=True)
class Problem:
    """Why the table is not ok, naming what is at fault.

    kind is one of: unusable, malformed-axis, malformed-move,
    malformed-row, missing-vocabulary, missing-axis, catch-all-key,
    unknown-axis, unknown-key, duplicate-row, missing-row, undeclared-move,
    and for the provider mappings (Arc 2 R2) malformed-mapping,
    unknown-stop, loop-key-mapped, duplicate-mapping, missing-mapping.
    """

    kind: str
    message: str
    axis: str | None = None
    key: str | None = None
    move: str | None = None
    provider: str | None = None

    def as_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "axis": self.axis, "key": self.key,
                "move": self.move, "provider": self.provider, "message": self.message}


@dataclass
class Table:
    """The loaded table, with every problem found loading and checking it.

    `axes` are in rendering order; `moves` and `rows` in the file's order.
    A move that failed to load is not in `moves` (it is not declared) and
    is named by a malformed-move problem."""

    path: Path
    written_against: str | None = None
    floor: str | None = None
    axes: list[Axis] = field(default_factory=list)
    moves: dict[str, Move] = field(default_factory=dict)
    rows: list[Row] = field(default_factory=list)
    mappings: list[WordMapping] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    malformed_moves: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return not self.problems

    def axis(self, name: str) -> Axis | None:
        return next((a for a in self.axes if a.name == name), None)

    def problem(self, kind: str, message: str, **where: str | None) -> None:
        log.info("transition table: %s: %s", kind, message)
        self.problems.append(Problem(kind, message, **where))


class TableError(Exception):
    """The table file cannot be read or parsed at all."""


# ---------------------------------------------------------------------------
# 2. Loading the table
# ---------------------------------------------------------------------------


def read_toml(path: Path) -> dict[str, Any]:
    """The table file parsed, or TableError naming why it could not be."""
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except OSError as exc:
        raise TableError(f"{path}: {exc.strerror or exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise TableError(f"{path}: not valid TOML: {exc}") from exc


def load_table(path: Path = TRANSITIONS_TABLE, manifest: Manifest | None = None,
               manifest_error: str | None = None,
               data: dict[str, Any] | None = None) -> Table:
    """Load and check the table. Never raises for a bad table: every fault
    is a Problem on the result, so the verb reports it by name.

    `manifest` supplies the bale axes' keys (its vocabularies); when it is
    None, `manifest_error` says why, and each bale axis is reported as
    having no vocabulary. `data`, when given, is used instead of reading
    `path` — how the tests check a table they edited in memory."""
    table = Table(path=path, floor=None if manifest is None else manifest.floor)
    if data is None:
        try:
            data = read_toml(path)
        except TableError as exc:
            table.problem("unusable", str(exc))
            return table
    vocabularies = {} if manifest is None else manifest.vocabularies
    meta = data.get("table", {})
    table.written_against = meta.get("written_against") if isinstance(meta, dict) else None
    load_axes(table, data.get("axis"), vocabularies, manifest, manifest_error)
    load_moves(table, data.get("move"))
    load_rows(table, data.get("row"))
    load_mappings(table, data.get("mapping"))
    check_total(table)
    check_mappings(table)
    log.debug("transition table %s: %d axes, %d moves, %d rows, %d mappings, %d problems",
              path, len(table.axes), len(table.moves), len(table.rows),
              len(table.mappings), len(table.problems))
    return table


def load_axes(table: Table, raw: Any, vocabularies: dict[str, dict[str, Any]],
              manifest: Manifest | None, manifest_error: str | None) -> None:
    """[axis.<name>] tables, in `order`. A bale axis takes its keys from
    the vocabulary of the same name; a twine axis declares its own. A
    vocabulary the manifest records for an axis the table lacks is a
    missing axis: its keys would have no rows."""
    if not isinstance(raw, dict) or not raw:
        table.problem("malformed-axis", "the table declares no [axis.<name>] tables")
        raw = {}
    for name, spec in raw.items():
        if not isinstance(spec, dict):
            table.problem("malformed-axis", f"axis {name!r} is not a table", axis=name)
            continue
        source = spec.get("source")
        order = spec.get("order")
        if source not in SOURCES:
            table.problem("malformed-axis", f"axis {name!r}: source {source!r} is not "
                          f"one of {', '.join(SOURCES)}", axis=name)
            continue
        if not isinstance(order, int) or isinstance(order, bool):
            table.problem("malformed-axis", f"axis {name!r}: order must be an integer",
                          axis=name)
            continue
        means = spec.get("means") if isinstance(spec.get("means"), str) else ""
        if source == SOURCE_BALE:
            if "keys" in spec:
                table.problem("malformed-axis", f"axis {name!r}: a bale axis takes its "
                              "keys from the consumption manifest, never its own "
                              "`keys`", axis=name)
                continue
            vocab = vocabularies.get(name)
            if vocab is None:
                why = (manifest_error if manifest is None and manifest_error
                       else "share/bale-consumption.toml has no [[vocabulary]] "
                            f"entry with axis = {name!r}")
                table.problem("missing-vocabulary", f"axis {name!r} keys on bale's "
                              f"vocabulary, and none is recorded: {why}", axis=name)
                keys: tuple[str, ...] = ()
                home = "(no vocabulary)"
            else:
                keys = tuple(vocab["values"])
                home = f"{vocab['home']} {vocab.get('pointer', '')}".strip()
        else:
            raw_keys = spec.get("keys")
            if (not isinstance(raw_keys, list) or not raw_keys
                    or not all(isinstance(k, str) and k.strip() for k in raw_keys)):
                table.problem("malformed-axis", f"axis {name!r}: keys must be a "
                              "non-empty list of non-empty strings", axis=name)
                continue
            if len(set(raw_keys)) != len(raw_keys):
                dupes = sorted({k for k in raw_keys if raw_keys.count(k) > 1})
                table.problem("malformed-axis", f"axis {name!r} declares {dupes} "
                              "more than once", axis=name)
            keys = tuple(dict.fromkeys(raw_keys))
            home = f"{table.path.name} [axis.{name}] keys"
        loop = load_loop_keys(table, name, source, spec, keys)
        for key in keys:
            if key.strip().lower() in CATCH_ALL_KEYS:
                table.problem("catch-all-key", f"axis {name!r} has the catch-all key "
                              f"{key!r}; the table has no default case (D17)",
                              axis=name, key=key)
        table.axes.append(Axis(name, order, source, keys, means, home, loop))
    table.axes.sort(key=lambda a: (a.order, a.name))
    declared = {a.name for a in table.axes} | set(raw)
    for name in vocabularies:
        if name not in declared:
            table.problem("missing-axis", f"share/bale-consumption.toml records bale's "
                          f"{name!r} vocabulary and the table has no such axis: its "
                          "keys have no rows", axis=name)


def load_loop_keys(table: Table, name: str, source: str, spec: dict[str, Any],
                   keys: tuple[str, ...]) -> tuple[str, ...] | None:
    """An axis's `loop_keys` (Arc 2 R2): the keys the loop produces and no
    model adapter may — a non-empty list of the axis's own keys, each once,
    on a twine axis only. None when the axis declares none; a malformed
    list is a malformed-axis problem and reads as None."""
    if "loop_keys" not in spec:
        return None
    raw = spec["loop_keys"]
    if source != SOURCE_TWINE:
        table.problem("malformed-axis", f"axis {name!r}: a bale axis declares no "
                      "loop_keys (the loop's keys are twine's)", axis=name)
        return None
    if (not isinstance(raw, list) or not raw
            or not all(isinstance(k, str) and k.strip() for k in raw)):
        table.problem("malformed-axis", f"axis {name!r}: loop_keys must be a non-empty "
                      "list of non-empty strings", axis=name)
        return None
    faults = []
    if len(set(raw)) != len(raw):
        faults.append(f"declares {sorted({k for k in raw if raw.count(k) > 1})} more "
                      "than once")
    stray = [k for k in raw if k not in keys]
    if stray:
        faults.append(f"names {stray}, which are not keys of the axis")
    if faults:
        table.problem("malformed-axis", f"axis {name!r}: loop_keys " + "; ".join(faults),
                      axis=name)
        return None
    return tuple(raw)


def load_moves(table: Table, raw: Any) -> None:
    """[move.<name>] tables. A move is declared only when it names exactly
    one actor of ACTORS and has a description; a malformed one is named,
    and left undeclared."""
    if not isinstance(raw, dict) or not raw:
        table.problem("malformed-move", "the table declares no [move.<name>] tables")
        return
    for name, spec in raw.items():
        faults = []
        if not isinstance(spec, dict):
            faults.append("not a table")
            spec = {}
        actor = spec.get("actor")
        if actor not in ACTORS:
            faults.append(f"actor {actor!r} is not exactly one of "
                          f"{', '.join(ACTORS)}")
        description = spec.get("description")
        if not isinstance(description, str) or not description.strip():
            faults.append("no description")
        if faults:
            table.malformed_moves.add(name)
            table.problem("malformed-move", f"move {name!r}: {'; '.join(faults)} — "
                          "it is not declared until it is whole", move=name)
            continue
        grounds = spec.get("grounds") if isinstance(spec.get("grounds"), str) else ""
        table.moves[name] = Move(name, actor, description.strip(), grounds)


def load_rows(table: Table, raw: Any) -> None:
    """[[row]] entries: axis, key, move (strings), and `means`."""
    if not isinstance(raw, list) or not raw:
        table.problem("malformed-row", "the table has no [[row]] entries")
        return
    for n, spec in enumerate(raw, 1):
        fields = {f: spec.get(f) if isinstance(spec, dict) else None
                  for f in ("axis", "key", "move")}
        bad = [f for f, v in fields.items() if not isinstance(v, str) or not v.strip()]
        if bad:
            table.problem("malformed-row", f"row {n}: {', '.join(bad)} missing or not a "
                          "string", axis=fields["axis"] if isinstance(fields["axis"], str)
                          else None, key=fields["key"] if isinstance(fields["key"], str)
                          else None)
            continue
        means = spec.get("means") if isinstance(spec.get("means"), str) else ""
        table.rows.append(Row(fields["axis"], fields["key"], fields["move"], means))


MAPPING_KEYS = frozenset({"provider", "on", "word", "stop", "continues", "means"})


def load_mappings(table: Table, raw: Any) -> None:
    """[[mapping]] entries (Arc 2 R2): provider, on, word (strings), and
    exactly one of `stop` (a string) and `continues = true`; `means`
    optional. A malformed entry is named and not loaded. Whether each stop
    is a key of the axis is check_mappings', once the axes are known."""
    if raw is None:
        return
    if not isinstance(raw, list):
        table.problem("malformed-mapping", "`mapping` must be an array of tables "
                      "([[mapping]])")
        return
    for n, spec in enumerate(raw, 1):
        if not isinstance(spec, dict):
            table.problem("malformed-mapping", f"mapping {n} is not a table")
            continue
        provider = spec.get("provider") if isinstance(spec.get("provider"), str) else None
        faults = []
        for f in ("provider", "on", "word"):
            if not isinstance(spec.get(f), str) or not spec[f].strip():
                faults.append(f"{f} missing or not a string")
        unknown = sorted(set(spec) - MAPPING_KEYS)
        if unknown:
            faults.append(f"unknown key(s) {unknown}")
        on, word = spec.get("on"), spec.get("word")
        if isinstance(on, str) and on not in MAPPING_ON:
            faults.append(f"on {on!r} is not one of {', '.join(MAPPING_ON)}")
        if on == "status" and isinstance(word, str) and not (len(word) == 3
                                                             and word.isdigit()):
            faults.append(f"a status word is three digits, not {word!r}")
        if on == "condition" and isinstance(word, str) and word not in CONDITIONS:
            faults.append(f"condition {word!r} is not one of {', '.join(CONDITIONS)}")
        has_stop, continues = "stop" in spec, spec.get("continues")
        if has_stop and "continues" in spec:
            faults.append("names both a stop and continues; a word means one")
        elif has_stop:
            if not isinstance(spec["stop"], str) or not spec["stop"].strip():
                faults.append("stop must be a non-empty string")
        elif continues is not True:
            faults.append("names neither a stop nor `continues = true`")
        if faults:
            where = f"mapping {n}" + (f" ({provider} {on} {word!r})" if provider and
                                      isinstance(on, str) and isinstance(word, str) else "")
            table.problem("malformed-mapping", f"{where}: {'; '.join(faults)}",
                          provider=provider)
            continue
        means = spec.get("means") if isinstance(spec.get("means"), str) else ""
        table.mappings.append(WordMapping(provider, on, word,  # type: ignore[arg-type]
                                          spec["stop"] if has_stop else None, means))


# The axis whose keys are twine's API-side stop set.
STOP_AXIS = "stop"
# The loop's fourth own stop key (session 2026-10-13-twine-table-adapter-
# defect-007): a boundary refusal or an adapter that raised, ended `stopped`
# by twine.runtime.loop with the operator's move `fix-adapter`. Its one
# spelling in code, beside the others the loop reports: cap-reached and
# cap-unchecked are twine.spend's (STOP_CAP_*), killed is twine.kill's
# (STOP_KILLED). It lives here and not in twine/runtime/ because no module
# under twine/runtime/ may spell a stop key (tests/test_runtime.py); the
# boundary learns the key only through the table's `loop_keys`, and the
# table's row for it is checked by MoveBook.faults and by tests/test_run.py.
STOP_ADAPTER_DEFECT = "adapter-defect"
# The problems that make an axis's own keys untrustworthy. Other problems
# (a bale axis without its vocabulary, a missing row elsewhere) say
# nothing about the stop axis's keys and do not stop them being read.
_KEY_FAULTS = ("malformed-axis", "catch-all-key")


def stop_keys(path: Path = TRANSITIONS_TABLE) -> tuple[str, ...]:
    """The `stop` axis's keys, in the table's order — twine's stop set.

    Read from the table's `[axis.stop] keys` and nowhere else (the axis's
    source is `twine`, so no consumption manifest is consulted). Raises
    TableError when the table cannot be read, has no `stop` axis, the axis
    is not a twine axis, or its keys are malformed: a caller that needs the
    stop set never gets a guessed one."""
    _, axis = _usable_stop_axis(path)
    log.debug("stop set from %s: %s", path, ", ".join(axis.keys))
    return axis.keys


def _usable_stop_axis(path: Path) -> tuple[Table, Axis]:
    """The table loaded for a runtime reader, and its stop axis, or
    TableError for exactly the faults stop_keys refuses."""
    table = load_table(path, None, "not consulted: the stop axis is twine's own")
    for problem in table.problems:
        if problem.kind == "unusable":
            raise TableError(problem.message)
        if problem.axis == STOP_AXIS and problem.kind in _KEY_FAULTS:
            raise TableError(f"{path}: the {STOP_AXIS!r} axis is unusable: "
                             f"{problem.message}")
    axis = table.axis(STOP_AXIS)
    if axis is None:
        raise TableError(f"{path}: no [axis.{STOP_AXIS}] is declared")
    if axis.source != SOURCE_TWINE:
        raise TableError(f"{path}: [axis.{STOP_AXIS}] has source {axis.source!r}; "
                         f"the stop set is twine's own ({SOURCE_TWINE!r})")
    return table, axis


def loop_keys(path: Path = TRANSITIONS_TABLE) -> tuple[str, ...]:
    """The `stop` axis's `loop_keys`, in the table's order: the stops the
    loop produces (the cost spine's, the kill-switch's) and no model
    adapter may — the boundary refuses a turn an adapter stops with one.

    Read from `[axis.stop] loop_keys` and nowhere else. Raises TableError
    whenever stop_keys would, and when the axis declares no loop_keys (or a
    malformed list): the boundary never runs on a guessed subset."""
    _, axis = _usable_stop_axis(path)
    if axis.loop_keys is None:
        raise TableError(f"{path}: [axis.{STOP_AXIS}] declares no loop_keys — the keys "
                         "the loop produces and no adapter may")
    log.debug("loop keys from %s: %s", path, ", ".join(axis.loop_keys))
    return axis.loop_keys


def provider_mapping(provider: str, path: Path = TRANSITIONS_TABLE) -> ProviderMapping:
    """One provider's [[mapping]] rows, checked, for its model adapter.

    Raises TableError whenever stop_keys would, when any mapping problem
    names this provider (or a mapping too malformed to name one), and when
    the table maps nothing for it: an adapter never runs on a mapping the
    table does not stand behind."""
    table, _ = _usable_stop_axis(path)
    mapping_kinds = {"malformed-mapping", "unknown-stop", "loop-key-mapped",
                     "duplicate-mapping", "missing-mapping"}
    faults = [p.message for p in table.problems
              if p.kind in mapping_kinds and p.provider in (provider, None)]
    if faults:
        raise TableError(f"{path}: the {provider!r} mapping is unusable: "
                         + "; ".join(faults))
    rows = tuple(m for m in table.mappings if m.provider == provider)
    if not rows:
        raise TableError(f"{path}: no [[mapping]] row names the provider {provider!r}")
    log.debug("%s mapping from %s: %d rows", provider, path, len(rows))
    return ProviderMapping(provider, rows)


# ---------------------------------------------------------------------------
# 3. Checking it is total
# ---------------------------------------------------------------------------


def check_total(table: Table) -> None:
    """One row per (axis, key), no row outside an axis's keys, every
    row's move declared. Each failure names the axis and key, or the
    move; a bale-axis key that is not bale's spelling says so."""
    axes = {a.name: a for a in table.axes}
    seen: dict[tuple[str, str], int] = {}
    for row in table.rows:
        axis = axes.get(row.axis)
        if axis is None:
            table.problem("unknown-axis", f"row {row.axis!r} {row.key!r}: no axis "
                          f"{row.axis!r} is declared", axis=row.axis, key=row.key)
        elif row.key not in axis.keys:
            whose = (f"one of bale {table.floor or '(floor unknown)'}'s spellings on "
                     f"{row.axis!r}" if axis.source == SOURCE_BALE
                     else f"a key of twine's {row.axis!r} axis")
            table.problem("unknown-key", f"{row.axis} {row.key!r} is not {whose}",
                          axis=row.axis, key=row.key)
        seen[(row.axis, row.key)] = seen.get((row.axis, row.key), 0) + 1
        if row.move not in table.moves and row.move not in table.malformed_moves:
            table.problem("undeclared-move", f"{row.axis} {row.key!r} names the move "
                          f"{row.move!r}, which is not declared", axis=row.axis,
                          key=row.key, move=row.move)
    for (axis_name, key), count in seen.items():
        if count > 1:
            table.problem("duplicate-row", f"{axis_name} {key!r} has {count} rows; it "
                          "takes exactly one", axis=axis_name, key=key)
    for axis in table.axes:
        for key in axis.keys:
            if (axis.name, key) not in seen:
                table.problem("missing-row", f"{axis.name} {key!r} has no row: no move "
                              "is defined for it", axis=axis.name, key=key)


def check_mappings(table: Table) -> None:
    """Every mapping lands on a key of the stop axis that is not a loop
    key; each (provider, on, word) once; every provider maps every
    condition. Each failure names the provider and the word."""
    axis = table.axis(STOP_AXIS)
    keys = set(axis.keys) if axis is not None else set()
    loop = set(axis.loop_keys or ()) if axis is not None else set()
    seen: dict[tuple[str, str, str], int] = {}
    for m in table.mappings:
        label = f"{m.provider} {m.on} {m.word!r}"
        if m.stop is not None:
            if m.stop not in keys:
                table.problem("unknown-stop", f"{label} maps onto {m.stop!r}, which is not "
                              f"a key of the {STOP_AXIS} axis", axis=STOP_AXIS, key=m.stop,
                              provider=m.provider)
            elif m.stop in loop:
                table.problem("loop-key-mapped", f"{label} maps onto {m.stop!r}, a loop "
                              "key: the loop produces it, never a provider's word",
                              axis=STOP_AXIS, key=m.stop, provider=m.provider)
        seen[(m.provider, m.on, m.word)] = seen.get((m.provider, m.on, m.word), 0) + 1
    for (provider, on, word), count in seen.items():
        if count > 1:
            table.problem("duplicate-mapping", f"{provider} {on} {word!r} is mapped {count} "
                          "times; a word means one thing", provider=provider)
    for provider in dict.fromkeys(m.provider for m in table.mappings):
        for word in CONDITIONS:
            if (provider, "condition", word) not in seen:
                table.problem("missing-mapping", f"{provider} maps no condition {word!r}: "
                              "an adapter meeting it would have no defined stop",
                              provider=provider)


def unused_moves(table: Table) -> list[str]:
    """Declared moves no row names. Not a fault (ok is about rows having
    moves), but reported: a move nobody reaches is worth a look."""
    used = {row.move for row in table.rows}
    return [name for name in table.moves if name not in used]


# ---------------------------------------------------------------------------
# 4. Rendering
# ---------------------------------------------------------------------------


def ordered_rows(table: Table) -> list[Row]:
    """Rows in rendering order: by axis order, then by the key's place in
    its vocabulary; rows the check refused (unknown axis or key) follow,
    in the file's order."""
    rank: dict[tuple[str, str], tuple[int, int]] = {}
    for i, axis in enumerate(table.axes):
        for j, key in enumerate(axis.keys):
            rank[(axis.name, key)] = (i, j)
    known = [r for r in table.rows if (r.axis, r.key) in rank]
    known.sort(key=lambda r: rank[(r.axis, r.key)])
    return known + [r for r in table.rows if (r.axis, r.key) not in rank]


def row_json(table: Table, row: Row) -> dict[str, Any]:
    move = table.moves.get(row.move)
    return {"axis": row.axis, "key": row.key, "move": row.move,
            "actor": None if move is None else move.actor, "means": row.means}


def as_json(table: Table) -> dict[str, Any]:
    """The JSON twin's payload (cli-contract.md §12)."""
    rows = ordered_rows(table)
    counts: dict[str, int] = {}
    for row in table.rows:
        counts[row.move] = counts.get(row.move, 0) + 1
    stop_moves = {row.key: row.move for row in table.rows if row.axis == STOP_AXIS}
    return {
        "table": str(table.path),
        "written_against": table.written_against,
        "floor": table.floor,
        "axes": [a.as_json() for a in table.axes],
        "rows": [row_json(table, r) for r in rows],
        "moves": {m.name: {"actor": m.actor, "description": m.description,
                           "grounds": m.grounds, "rows": counts.get(m.name, 0)}
                  for m in table.moves.values()},
        "mappings": [dict(m.as_json(), move=None if m.stop is None
                          else stop_moves.get(m.stop)) for m in table.mappings],
        "counts": {"axes": len(table.axes), "keys": sum(len(a.keys) for a in table.axes),
                   "rows": len(table.rows), "moves": len(table.moves),
                   "mappings": len(table.mappings)},
        "unused_moves": unused_moves(table),
        "problems": [p.as_json() for p in table.problems],
        "reason": None if table.ok else "; ".join(p.message for p in table.problems),
    }


def as_lines(table: Table) -> list[str]:
    """The same facts as readable lines: a verdict, each axis with its
    rows, the moves, and every problem."""
    keys = sum(len(a.keys) for a in table.axes)
    lines = [f"transition table {table.path}: {'ok' if table.ok else 'NOT OK'}",
             f"  {len(table.axes)} axes, {keys} keys, {len(table.rows)} rows, "
             f"{len(table.moves)} moves, {len(table.mappings)} provider mappings; "
             "bale axes spelled for "
             f"{table.written_against or '(unstated)'}, floor {table.floor or '(unknown)'}"]
    rows = ordered_rows(table)
    width = max((len(r.key) for r in rows), default=0)
    mwidth = max((len(r.move) for r in rows), default=0)
    for axis in table.axes:
        lines.append("")
        lines.append(f"{axis.name}  ({axis.source}: {axis.home}; {len(axis.keys)} keys)")
        for row in (r for r in rows if r.axis == axis.name):
            move = table.moves.get(row.move)
            actor = move.actor if move else "UNDECLARED"
            lines.append(f"  {row.key:<{width}}  -> {row.move:<{mwidth}}  [{actor}]")
        if axis.loop_keys:
            lines.append(f"  loop keys (the loop's, never an adapter's): "
                         f"{', '.join(axis.loop_keys)}")
    if table.mappings:
        lines.append("")
        lines.append(f"provider mappings ({len(table.mappings)})")
        wwidth = max(len(f"{m.on} {m.word}") for m in table.mappings)
        for m in table.mappings:
            target = "(continues: the turn asked for tools)" if m.stop is None else m.stop
            lines.append(f"  {m.provider}  {m.on + ' ' + m.word:<{wwidth}}  -> {target}")
    stray = [r for r in rows if table.axis(r.axis) is None]
    if stray:
        lines.append("")
        lines.append("rows on no declared axis")
        lines.extend(f"  {r.axis} {r.key} -> {r.move}" for r in stray)
    if table.moves:
        lines.append("")
        lines.append("moves")
        nwidth = max(len(n) for n in table.moves)
        for move in table.moves.values():
            lines.append(f"  {move.name:<{nwidth}}  {move.actor:<8}  {move.description}")
    unused = unused_moves(table)
    if unused:
        lines.append("")
        lines.append(f"unused moves (no row names them): {', '.join(unused)}")
    if table.problems:
        lines.append("")
        lines.append(f"{len(table.problems)} problem(s):")
        lines.extend(f"  {p.kind}: {p.message}" for p in table.problems)
    return lines

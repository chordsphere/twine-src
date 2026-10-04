"""The cost spine (twine-seed.md D15; Arc 1 session 5a): twine's usage
record, the running totals over it, and the hard cap's pre-call check.

What this module is, and what it is not:

  - It owns twine's **spend stream**, `<state-dir>/spend.jsonl`: append-only,
    one JSON object per line, one line per model call (the usage record).
    N4's test — "if twine's local state were deleted, what is lost? Spend
    history and nothing else" — names this file.
  - It **never sees a provider's usage shape.** It consumes twine's own
    record, in twine's own five token classes. Mapping a provider's usage
    onto the record is the model adapter's job (Arc 2), verified against a
    recording when one exists; none exists yet (the gated probe
    `twine-usage-record` is what will record one).
  - It **ships no prices.** Prices are operator data, a TOML file the
    operator writes (`<state-dir>/prices.toml`, or `--prices PATH`). A model
    with no price row is a refusal naming it — never a zero, a guess or a
    skip.
  - It is **pure** apart from the stream and price files: no network, no
    subprocess, no provider SDK. A test asserts the imports.

One function, two faces (brief item 7): `spend_totals` and `check_call`
are what `twine spend totals` and `twine spend check` call, and what the
Arc 2 loop will call before every model call. Neither raises for any fault
it anticipates: each returns a report whose `ok` (for the check:
`admitted`) is False and whose `refusal` names the fault. A caller that
reads only `admitted` therefore fails closed — if the cap cannot be
checked, the call does not happen.

Money is exact: prices are parsed as `Decimal` (tomllib's parse_float), a
cost is `tokens * price / 1_000_000` in Decimal, and the cap comparison is
made in Decimal. Only the JSON twin rounds, to a double, at the edge.

Sections:
  1. Names and errors                       (~line 60)
  2. The state directory                    (~line 120)
  3. The usage record                       (~line 180)
  4. Appending to the stream                (~line 310)
  5. Reading the stream                     (~line 385)
  6. Prices                                 (~line 500)
  7. Cost                                   (~line 630)
  8. Running totals                         (~line 655)
  9. The pre-call check                     (~line 850)
 10. Rendering helpers                      (~line 1015)
"""

from __future__ import annotations

import json
import logging
import os
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

log = logging.getLogger("twine.spend")

# ---------------------------------------------------------------------------
# 1. Names and errors
# ---------------------------------------------------------------------------

STREAM_NAME = "spend.jsonl"
PRICES_NAME = "prices.toml"
STATE_SUBDIR = "twine"            # under $XDG_STATE_HOME, or $HOME/.local/state
ENV_STATE_DIR = "TWINE_STATE_DIR"

# The record's token classes, in the order every renderer lists them. They
# are disjoint: tokens counted in `thinking` are not also in `output`.
TOKEN_CLASSES = ("input", "output", "thinking", "cache_read", "cache_write")
# The classes a price row carries. Thinking has no price of its own: it is
# billed at the model's `output` price (D20).
PRICED_CLASSES = ("input", "output", "cache_read", "cache_write")
# The input-side classes the worst case chooses the dearest of.
INPUT_SIDE_CLASSES = ("input", "cache_read", "cache_write")
REQUIRED_KEYS = ("sid", "served_sid", "model", "tokens")
# The one key twine's writer adds beside the required ones.
RECORDED_AT = "recorded_at"

PER_MILLION = Decimal(1_000_000)

# The transition table's `stop` keys for a call the check did not admit
# (share/transitions.toml). Every refusal names one, so the Arc 2 loop
# always stops with a key the table has a move for (D17: no default case):
#   cap-reached    the cap refused the call       -> stop-at-cap
#   cap-unchecked  the check itself could not run -> fix-and-resume
#                  (every refusal that is not cap-reached; session 5b)
STOP_CAP_REACHED = "cap-reached"
STOP_CAP_UNCHECKED = "cap-unchecked"

# Why a totals report or a check is not ok. Closed; each names a fault.
REFUSALS = (
    "cap-reached",        # the check: spend so far + worst case > cap
    "bad-argument",       # a cap, a token count or a sid that is not one
    "no-state-dir",       # no --state-dir, $TWINE_STATE_DIR, $XDG_STATE_HOME or $HOME
    "unreadable-stream",  # spend.jsonl exists and cannot be read
    "malformed-stream",   # a line that is not a usage record, named by number
    "no-prices",          # the price file is absent (twine ships none)
    "malformed-prices",   # the price file is not a valid price table
    "unpriced-model",     # a model with no price row, named
)

# How many line problems a report lists before it says "and N more".
MAX_REPORTED_PROBLEMS = 50


class SpendError(Exception):
    """A spend fault with its refusal kind (one of REFUSALS)."""

    def __init__(self, kind: str, message: str) -> None:
        assert kind in REFUSALS, kind
        super().__init__(message)
        self.kind = kind
        self.message = message


class RecordError(ValueError):
    """A usage record that is not one; the message names every fault."""


# ---------------------------------------------------------------------------
# 2. The state directory
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StateDir:
    """Where twine's state lives, and which rule answered.

    source is "--state-dir", "TWINE_STATE_DIR", "XDG_STATE_HOME" or "HOME".
    """

    path: Path
    source: str

    @property
    def stream(self) -> Path:
        return self.path / STREAM_NAME

    @property
    def prices(self) -> Path:
        return self.path / PRICES_NAME


def resolve_state_dir(flag: str | None, env: Mapping[str, str]) -> StateDir:
    """`--state-dir DIR`, else `$TWINE_STATE_DIR`, else
    `${XDG_STATE_HOME:-$HOME/.local/state}/twine` (brief item 2).

    The default is outside any project's working tree on purpose: spend is
    twine's state, not the project's (N4), and a file in the tree would
    dirty what bale checks. Per the XDG base-directory spec a relative
    `$XDG_STATE_HOME` is ignored. With none of the four set, this refuses
    (SpendError "no-state-dir") rather than inventing a location — the
    working directory is never a fallback. An empty `--state-dir` was
    asked for and names nothing: it is refused ("bad-argument"), never
    read as "no flag" (an empty environment variable is unset, as usual).
    """
    if flag is not None:
        if not flag.strip():
            raise SpendError("bad-argument", "--state-dir is empty; it names no "
                             "directory")
        return StateDir(_absolute(flag), "--state-dir")
    value = env.get(ENV_STATE_DIR, "")
    if value:
        return StateDir(_absolute(value), ENV_STATE_DIR)
    xdg = env.get("XDG_STATE_HOME", "")
    if xdg and os.path.isabs(xdg):
        return StateDir(Path(xdg) / STATE_SUBDIR, "XDG_STATE_HOME")
    if xdg:
        log.info("XDG_STATE_HOME %r is relative; the XDG spec says to ignore it", xdg)
    home = env.get("HOME", "")
    if home and os.path.isabs(home):
        return StateDir(Path(home) / ".local" / "state" / STATE_SUBDIR, "HOME")
    raise SpendError(
        "no-state-dir",
        "cannot resolve twine's state directory: no --state-dir, and none of "
        f"${ENV_STATE_DIR}, an absolute $XDG_STATE_HOME or an absolute $HOME "
        "is set")


def _absolute(value: str) -> Path:
    return Path(os.path.abspath(os.path.expanduser(value)))


# ---------------------------------------------------------------------------
# 3. The usage record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tokens:
    """One call's tokens by class. Each a non-negative int; `thinking` is
    None when the provider does not report thinking separately (its
    thinking tokens are then inside `output`, never counted twice)."""

    input: int
    output: int
    thinking: int | None
    cache_read: int
    cache_write: int

    def as_json(self) -> dict[str, int | None]:
        return {name: getattr(self, name) for name in TOKEN_CLASSES}


@dataclass(frozen=True)
class UsageRecord:
    """One line of the spend stream.

    sid         the session the call ran in
    served_sid  the session the spend served (T11's envelope: a `delegate`
                child or a `compare` session bills to the session it
                served), or None when the call served its own session
    model       the model id the call ran on
    tokens      the five classes
    extra       every other key on the line, kept as read (a reader keeps
                unknown keys and never fails on them)
    line        the 1-based line number it was read from; None when built
    """

    sid: str
    served_sid: str | None
    model: str
    tokens: Tokens
    extra: Mapping[str, Any] = field(default_factory=dict)
    line: int | None = None

    def as_json(self) -> dict[str, Any]:
        """The line's object: the required keys first, then the rest."""
        obj: dict[str, Any] = {"sid": self.sid, "served_sid": self.served_sid,
                               "model": self.model, "tokens": self.tokens.as_json()}
        obj.update(self.extra)
        return obj


def record_faults(obj: Any) -> list[str]:
    """Every reason `obj` is not a usage record; [] when it is one.

    The one rule the writer and the reader share, so a line the writer
    accepts is a line the reader accepts.
    """
    if not isinstance(obj, dict):
        return [f"not a JSON object (a {type(obj).__name__})"]
    faults: list[str] = []
    missing = [key for key in REQUIRED_KEYS if key not in obj]
    if missing:
        faults.append("missing required key" + ("s " if len(missing) > 1 else " ")
                      + ", ".join(repr(k) for k in missing))
    sid = obj.get("sid")
    if "sid" in obj and not _is_name(sid):
        faults.append(f"'sid' must be a non-empty string without surrounding "
                      f"whitespace, not {sid!r}")
    served = obj.get("served_sid")
    if "served_sid" in obj and served is not None and not _is_name(served):
        faults.append(f"'served_sid' must be null or a non-empty string without "
                      f"surrounding whitespace, not {served!r}")
    elif _is_name(served) and served == sid:
        # A call that served its own session carries null. A record naming
        # itself would count twice in its session's spend so far (own +
        # served), so it is refused rather than guessed at.
        faults.append(f"'served_sid' equals 'sid' ({sid!r}); a call that served its "
                      "own session carries null")
    model = obj.get("model")
    if "model" in obj and not _is_name(model):
        faults.append(f"'model' must be a non-empty string without surrounding "
                      f"whitespace, not {model!r}")
    if "tokens" in obj:
        faults.extend(_token_faults(obj["tokens"]))
    return faults


def _is_name(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _token_faults(tokens: Any) -> list[str]:
    if not isinstance(tokens, dict):
        return [f"'tokens' must be an object, not {type(tokens).__name__}"]
    faults: list[str] = []
    keys = set(tokens)
    expected = set(TOKEN_CLASSES)
    if keys != expected:
        if expected - keys:
            faults.append("'tokens' lacks " + ", ".join(
                repr(k) for k in TOKEN_CLASSES if k not in keys))
        if keys - expected:
            faults.append("'tokens' has keys outside the five classes: " + ", ".join(
                repr(k) for k in sorted(keys - expected)))
    for name in TOKEN_CLASSES:
        if name not in tokens:
            continue
        value = tokens[name]
        if name == "thinking" and value is None:
            continue
        # bool is an int subclass; JSON true is not a count.
        if type(value) is not int:
            allowed = "a non-negative integer or null" if name == "thinking" \
                else "a non-negative integer"
            faults.append(f"tokens.{name} must be {allowed}, not {value!r}")
        elif value < 0:
            faults.append(f"tokens.{name} is negative ({value})")
    return faults


def parse_record(obj: Any, line: int | None = None) -> UsageRecord:
    """A usage record from a parsed JSON object, or RecordError naming every
    fault. Unknown keys are kept in `extra`."""
    faults = record_faults(obj)
    if faults:
        raise RecordError("; ".join(faults))
    t = obj["tokens"]
    tokens = Tokens(t["input"], t["output"], t["thinking"], t["cache_read"],
                    t["cache_write"])
    extra = {k: v for k, v in obj.items() if k not in REQUIRED_KEYS}
    return UsageRecord(obj["sid"], obj["served_sid"], obj["model"], tokens, extra, line)


# ---------------------------------------------------------------------------
# 4. Appending to the stream
# ---------------------------------------------------------------------------


def utc_now() -> str:
    """An RFC 3339 UTC timestamp, seconds precision: `recorded_at`'s form."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_record(state_dir: Path, *, sid: str, model: str,
                  tokens: Mapping[str, int | None], served_sid: str | None = None,
                  extra: Mapping[str, Any] | None = None,
                  clock: Callable[[], str] = utc_now) -> UsageRecord:
    """Append one usage record — one model call — to
    `<state_dir>/spend.jsonl`, and return it.

    This is the writer the Arc 2 loop calls after every call; nothing in
    Arc 1 calls it outside the tests. The record is validated by the same
    rule the reader applies (`record_faults`) before a byte is written, so
    a bad record raises RecordError and the stream is untouched.

    It adds `recorded_at` (UTC) unless `extra` names one. `extra` may carry
    any other keys (a call id, a stop reason) but never a required one.

    The write is one `os.write` of one LF-terminated line to a file opened
    O_APPEND, then fsync: spend history is the one thing N4 says deleting
    twine's state loses, so it is written durably. A stream whose last
    line is not newline-terminated (a torn write) is refused, loudly,
    rather than appended onto — gluing a record to a torn line would
    corrupt both.
    """
    extra = dict(extra or {})
    clash = [k for k in REQUIRED_KEYS if k in extra]
    if clash:
        raise RecordError("extra keys may not set a required key: "
                          + ", ".join(repr(k) for k in clash))
    obj: dict[str, Any] = {"sid": sid, "served_sid": served_sid, "model": model,
                           "tokens": dict(tokens)}
    if RECORDED_AT not in extra:
        obj[RECORDED_AT] = clock()
    obj.update(extra)
    record = parse_record(obj)
    line = json.dumps(record.as_json(), ensure_ascii=False) + "\n"
    if "\n" in line[:-1]:
        raise RecordError("the record rendered as more than one line")
    data = line.encode("utf-8")

    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    stream = state_dir / STREAM_NAME
    if _ends_torn(stream):
        raise SpendError("malformed-stream",
                         f"{stream}: the last line is not newline-terminated (a torn "
                         "write?); refusing to append onto it")
    fd = os.open(stream, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        written = 0
        while written < len(data):
            written += os.write(fd, data[written:])
        os.fsync(fd)
    finally:
        os.close(fd)
    log.info("spend: appended a record for sid %s (model %s) to %s", sid, model, stream)
    return record


def _ends_torn(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            if fh.tell() == 0:
                return False
            fh.seek(-1, os.SEEK_END)
            return fh.read(1) != b"\n"
    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# 5. Reading the stream
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LineProblem:
    """A stream line that is not a usage record. `line` is 1-based."""

    line: int
    message: str

    def as_json(self) -> dict[str, Any]:
        return {"line": self.line, "message": self.message}

    def __str__(self) -> str:
        return f"line {self.line}: {self.message}"


@dataclass
class Stream:
    """The spend stream as read: every record, and every line that is not
    one. `present` is False when the file does not exist (an absent stream
    is an empty one); `unreadable` says why an existing file could not be
    read."""

    path: Path
    present: bool = False
    lines: int = 0
    records: list[UsageRecord] = field(default_factory=list)
    problems: list[LineProblem] = field(default_factory=list)
    unreadable: str | None = None

    @property
    def ok(self) -> bool:
        return self.unreadable is None and not self.problems

    def refusal(self) -> SpendError | None:
        """Why the stream cannot be used, or None when it can."""
        if self.unreadable is not None:
            return SpendError("unreadable-stream", self.unreadable)
        if self.problems:
            shown = "; ".join(str(p) for p in self.problems[:3])
            more = len(self.problems) - 3
            return SpendError(
                "malformed-stream",
                f"{self.path}: {len(self.problems)} line(s) are not usage records — "
                + shown + (f"; and {more} more" if more > 0 else "")
                + " (a malformed line is never skipped)")
        return None


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate key {key!r}")
        obj[key] = value
    return obj


def read_stream(path: Path) -> Stream:
    """Read `spend.jsonl`. Never raises for what is in the file: every line
    that is not a usage record is a LineProblem naming its line number —
    not JSON, not UTF-8, blank, a duplicate key, a missing required key, a
    negative count, a torn (not newline-terminated) last line. Nothing is
    skipped silently."""
    stream = Stream(Path(path))
    try:
        fh = stream.path.open("rb")
    except FileNotFoundError:
        log.debug("spend: no stream at %s (an absent stream is empty)", stream.path)
        return stream
    except OSError as exc:
        stream.present = True
        stream.unreadable = f"{stream.path}: cannot be read: {exc.strerror or exc}"
        return stream
    stream.present = True
    try:
        with fh:
            for number, raw in enumerate(fh, 1):
                stream.lines = number
                problem, obj = _parse_line(raw)
                if problem is not None:
                    stream.problems.append(LineProblem(number, problem))
                    continue
                stream.records.append(parse_record(obj, number))
    except OSError as exc:
        stream.unreadable = f"{stream.path}: read failed: {exc.strerror or exc}"
    log.debug("spend: %s: %d lines, %d records, %d problems", stream.path,
              stream.lines, len(stream.records), len(stream.problems))
    return stream


def _parse_line(raw: bytes) -> tuple[str | None, Any]:
    """One raw line (with its LF, when it has one): (None, the object) when
    it is a usage record, else (why it is not, None)."""
    if not raw.endswith(b"\n"):
        return "not newline-terminated (a torn write?)", None
    body = raw[:-1]
    if not body.strip():
        return "blank", None
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        return f"not UTF-8 ({exc.reason} at byte {exc.start})", None
    try:
        obj = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except ValueError as exc:
        return f"not JSON ({exc})", None
    faults = record_faults(obj)
    return ("; ".join(faults), None) if faults else (None, obj)


# ---------------------------------------------------------------------------
# 6. Prices
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelPrice:
    """One model's price row, in US dollars per million tokens. `extra`
    keeps the row's other keys (a source, an as-of date)."""

    model: str
    input: Decimal
    output: Decimal
    cache_read: Decimal
    cache_write: Decimal
    extra: Mapping[str, Any] = field(default_factory=dict)

    def of(self, token_class: str) -> Decimal:
        """The price a token class bills at; thinking at output's (D20)."""
        return self.output if token_class == "thinking" else getattr(self, token_class)

    def dearest_input_side(self) -> tuple[str, Decimal]:
        """The largest of input, cache_read and cache_write, and its class.
        Ties go to the earlier class in INPUT_SIDE_CLASSES."""
        best = INPUT_SIDE_CLASSES[0]
        for name in INPUT_SIDE_CLASSES[1:]:
            if getattr(self, name) > getattr(self, best):
                best = name
        return best, getattr(self, best)


@dataclass
class PriceTable:
    """The operator's price file, loaded and validated whole."""

    path: Path
    models: dict[str, ModelPrice] = field(default_factory=dict)

    def unpriced(self, models: Iterable[str]) -> list[str]:
        """The given model ids with no price row, sorted, each once."""
        return sorted({m for m in models if m not in self.models})


def resolve_prices_path(flag: str | None, state_dir: Path) -> tuple[Path, str]:
    """`--prices PATH`, else `<state-dir>/prices.toml`; and which answered
    ("--prices" or "state-dir"). An empty `--prices` is refused
    ("bad-argument"), never read as "no flag"."""
    if flag is not None:
        if not flag.strip():
            raise SpendError("bad-argument", "--prices is empty; it names no file")
        return _absolute(flag), "--prices"
    return Path(state_dir) / PRICES_NAME, "state-dir"


def load_prices(path: Path) -> PriceTable:
    """The price table at `path`, validated whole, or SpendError.

    "no-prices" when the file does not exist — twine ships no price file
    and no price values, so the operator writes one. "malformed-prices"
    when it is not TOML, `model` is not a table of tables, or any row lacks
    one of the four classes or carries one that is not a finite,
    non-negative number. The whole file is checked, not just the rows a
    caller needs: a typo in a row you will use tomorrow is reported today.
    Other keys, in a row or at the top, are the operator's and are kept.
    """
    path = Path(path)
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh, parse_float=Decimal)
    except FileNotFoundError:
        raise SpendError("no-prices", f"no price file at {path}: twine ships no prices; "
                         "write one table per model, [model.\"<id>\"] with input, "
                         "output, cache_read and cache_write in US dollars per "
                         "million tokens") from None
    except OSError as exc:
        raise SpendError("malformed-prices",
                         f"{path}: cannot be read: {exc.strerror or exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise SpendError("malformed-prices", f"{path}: not valid TOML: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise SpendError("malformed-prices", f"{path}: not UTF-8: {exc}") from exc
    models = data.get("model", {})
    if not isinstance(models, dict):
        raise SpendError("malformed-prices", f"{path}: `model` must be a table of "
                         "[model.\"<id>\"] tables")
    table = PriceTable(path)
    faults: list[str] = []
    for model, row in models.items():
        if not model.strip():
            faults.append("a [model.\"\"] row has an empty model id")
            continue
        if not isinstance(row, dict):
            faults.append(f"model {model!r}: not a table")
            continue
        row_faults, prices = _price_row(row)
        if row_faults:
            faults.extend(f"model {model!r}: {f}" for f in row_faults)
            continue
        extra = {k: v for k, v in row.items() if k not in PRICED_CLASSES}
        table.models[model] = ModelPrice(model, prices["input"], prices["output"],
                                         prices["cache_read"], prices["cache_write"],
                                         extra)
    if faults:
        raise SpendError("malformed-prices", f"{path}: " + "; ".join(faults))
    log.debug("spend: %s: %d priced models", path, len(table.models))
    return table


def _price_row(row: Mapping[str, Any]) -> tuple[list[str], dict[str, Decimal]]:
    faults: list[str] = []
    prices: dict[str, Decimal] = {}
    for name in PRICED_CLASSES:
        if name not in row:
            faults.append(f"no {name!r} price")
            continue
        value = row[name]
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
            faults.append(f"{name!r} must be a number (US dollars per million "
                          f"tokens), not {value!r}")
            continue
        price = Decimal(value)
        if not price.is_finite():
            faults.append(f"{name!r} is not finite ({value})")
        elif price < 0:
            faults.append(f"{name!r} is negative ({value})")
        else:
            prices[name] = price
    return faults, prices


# ---------------------------------------------------------------------------
# 7. Cost
# ---------------------------------------------------------------------------


def record_cost(record: UsageRecord, price: ModelPrice) -> Decimal:
    """One call's cost in US dollars: the four priced classes at their
    prices, plus `thinking` at the output price when it is not null (D20).
    Exact (Decimal)."""
    t = record.tokens
    total = (t.input * price.input + t.output * price.output
             + t.cache_read * price.cache_read + t.cache_write * price.cache_write)
    if t.thinking is not None:
        total += t.thinking * price.output
    return total / PER_MILLION


def worst_case_cost(price: ModelPrice, input_tokens: int, max_output: int) -> Decimal:
    """The most a call can cost: every input token at the dearest
    input-side price the model has (the largest of input, cache_read and
    cache_write) and every possible output token at the output price.
    Thinking falls inside the output bound, at the output price."""
    _, dearest = price.dearest_input_side()
    return (input_tokens * dearest + max_output * price.output) / PER_MILLION


# ---------------------------------------------------------------------------
# 8. Running totals
# ---------------------------------------------------------------------------


@dataclass
class SessionTotals:
    """One session's totals over the stream.

    calls, tokens and cost_usd are over the session's own records (`sid`
    is this session); served_calls and served_cost_usd over the records
    whose `served_sid` is this session. A session the stream names only
    as a `served_sid` has a row with calls 0. Costs are None when the
    stream could not be priced."""

    sid: str
    calls: int = 0
    input: int = 0
    output: int = 0
    thinking: int | None = None
    cache_read: int = 0
    cache_write: int = 0
    cost_usd: Decimal | None = Decimal(0)
    served_calls: int = 0
    served_cost_usd: Decimal | None = Decimal(0)
    models: set[str] = field(default_factory=set)

    def add_own(self, record: UsageRecord, cost: Decimal | None) -> None:
        t = record.tokens
        self.calls += 1
        self.input += t.input
        self.output += t.output
        self.cache_read += t.cache_read
        self.cache_write += t.cache_write
        # A thinking total is the sum of the non-null values, and null only
        # when every record had null.
        if t.thinking is not None:
            self.thinking = (self.thinking or 0) + t.thinking
        self.models.add(record.model)
        self.cost_usd = None if cost is None or self.cost_usd is None \
            else self.cost_usd + cost

    def add_served(self, cost: Decimal | None) -> None:
        self.served_calls += 1
        self.served_cost_usd = None if cost is None or self.served_cost_usd is None \
            else self.served_cost_usd + cost

    @property
    def tokens(self) -> dict[str, int | None]:
        # A session with no records of its own reports 0, not null: null
        # says "the provider did not report thinking", and nothing was.
        thinking = self.thinking if self.calls else 0
        return {"input": self.input, "output": self.output, "thinking": thinking,
                "cache_read": self.cache_read, "cache_write": self.cache_write}

    @property
    def spend_so_far_usd(self) -> Decimal | None:
        """What counts against this session's cap: its own cost plus what
        effort mechanisms spent serving it (T11)."""
        if self.cost_usd is None or self.served_cost_usd is None:
            return None
        return self.cost_usd + self.served_cost_usd

    def as_json(self) -> dict[str, Any]:
        return {"sid": self.sid, "calls": self.calls, "tokens": self.tokens,
                "cost_usd": usd(self.cost_usd), "served_calls": self.served_calls,
                "served_cost_usd": usd(self.served_cost_usd),
                "models": sorted(self.models)}


def accumulate(records: Iterable[UsageRecord],
               prices: PriceTable | None) -> tuple[dict[str, SessionTotals],
                                                   Decimal | None]:
    """Every session's totals, in order of first appearance (as `sid` or
    `served_sid`), and the stream's whole cost with each record counted
    once. With `prices` None, or any record's model unpriced, every cost
    is None — a partial sum is never reported as a total."""
    records = list(records)
    priceable = prices is not None and not prices.unpriced(r.model for r in records)
    sessions: dict[str, SessionTotals] = {}
    total: Decimal | None = Decimal(0) if priceable else None
    for record in records:
        cost = record_cost(record, prices.models[record.model]) if priceable else None
        sessions.setdefault(record.sid, SessionTotals(record.sid)).add_own(record, cost)
        if record.served_sid is not None:
            sessions.setdefault(record.served_sid,
                                SessionTotals(record.served_sid)).add_served(cost)
        if total is not None and cost is not None:
            total += cost
    if not priceable:
        for s in sessions.values():
            s.cost_usd = s.served_cost_usd = None
    return sessions, total


@dataclass
class TotalsReport:
    """`twine spend totals`' result — and the loop's, when it renders
    spend. ok is False exactly when `refusal` is set."""

    state_dir: Path
    stream: Path
    stream_present: bool = False
    records: int = 0
    prices: Path | None = None
    prices_read: bool = False
    sid: str | None = None
    sessions: list[SessionTotals] = field(default_factory=list)
    total_cost_usd: Decimal | None = None
    unpriced_models: list[str] = field(default_factory=list)
    problems: list[LineProblem] = field(default_factory=list)
    refusal: str | None = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.refusal is None

    def refuse(self, error: SpendError) -> "TotalsReport":
        self.refusal, self.reason = error.kind, error.message
        log.info("spend totals: %s: %s", error.kind, error.message)
        return self

    def as_json(self) -> dict[str, Any]:
        return {
            "sessions": [s.as_json() for s in self.sessions],
            "total_cost_usd": usd(self.total_cost_usd),
            "sid": self.sid,
            "records": self.records,
            "unpriced_models": list(self.unpriced_models),
            "refusal": self.refusal,
            "reason": self.reason,
            "problems": [p.as_json() for p in self.problems[:MAX_REPORTED_PROBLEMS]],
            "problems_total": len(self.problems),
            "state_dir": str(self.state_dir),
            "stream": str(self.stream),
            "stream_present": self.stream_present,
            "prices": None if self.prices is None else str(self.prices),
            "prices_read": self.prices_read,
        }


def spend_totals(state_dir: Path, prices_path: Path | None = None,
                 sid: str | None = None) -> TotalsReport:
    """The running totals over `<state_dir>/spend.jsonl` (brief item 4).

    Per session (only `sid`'s, when given): calls, the five token classes
    summed, the cost, and the cost of records that served it.
    `total_cost_usd` is the whole stream's, whatever `sid` says.

    An empty or absent stream is ok with no sessions, and the price file is
    not read. Otherwise every record is priced: a malformed line, an
    unreadable stream, an absent or malformed price file, or any model with
    no price row is not ok, its refusal named — never skipped, never
    estimated. Never raises for those."""
    state_dir = Path(state_dir)
    prices_path = Path(prices_path) if prices_path else state_dir / PRICES_NAME
    report = TotalsReport(state_dir=state_dir, stream=state_dir / STREAM_NAME,
                          prices=prices_path, sid=sid)
    if sid is not None and not _is_name(sid):
        return report.refuse(SpendError("bad-argument",
                                        f"--sid {sid!r} is not a session id"))
    stream = read_stream(report.stream)
    report.stream_present, report.records = stream.present, len(stream.records)
    report.problems = list(stream.problems)
    error = stream.refusal()
    if error is not None:
        return report.refuse(error)
    if not stream.records:
        return _finish_totals(report, {}, Decimal(0))
    try:
        prices = load_prices(prices_path)
    except SpendError as exc:
        sessions, _ = accumulate(stream.records, None)
        _finish_totals(report, sessions, None)
        return report.refuse(exc)
    report.prices_read = True
    sessions, total = accumulate(stream.records, prices)
    _finish_totals(report, sessions, total)
    unpriced = prices.unpriced(r.model for r in stream.records)
    if unpriced:
        report.unpriced_models = unpriced
        return report.refuse(SpendError(
            "unpriced-model", f"no price row for {', '.join(repr(m) for m in unpriced)} "
            f"in {prices_path}; an unpriced model is never estimated"))
    return report


def _finish_totals(report: TotalsReport, sessions: dict[str, SessionTotals],
                   total: Decimal | None) -> TotalsReport:
    rows = list(sessions.values())
    if report.sid is not None:
        rows = [s for s in rows if s.sid == report.sid]
    report.sessions, report.total_cost_usd = rows, total
    return report


# ---------------------------------------------------------------------------
# 9. The pre-call check
# ---------------------------------------------------------------------------


@dataclass
class CallCheck:
    """The hard cap's verdict on one call, made before the call.

    `admitted` is True exactly when the session's spend so far plus the
    call's worst-case cost is at most the cap. When it is False the call is
    not made: `refusal` says why, and `stop` is "cap-reached" exactly when
    the cap refused it and "cap-unchecked" for every other refusal — the
    check could not run, so the cap was never compared. The call as asked is reported unchanged — a refused
    call is never shrunk to fit (D15: refuse loudly, never degrade
    silently)."""

    sid: str
    model: str
    cap_usd: Decimal | None
    input_tokens: int | None
    max_output_tokens: int | None
    state_dir: Path
    stream: Path
    prices: Path
    admitted: bool = False
    stop: str | None = None
    refusal: str | None = None
    reason: str | None = None
    calls_so_far: int | None = None
    own_cost_usd: Decimal | None = None
    served_cost_usd: Decimal | None = None
    spend_so_far_usd: Decimal | None = None
    worst_case_usd: Decimal | None = None
    projected_usd: Decimal | None = None
    input_price_class: str | None = None
    input_price: Decimal | None = None
    output_price: Decimal | None = None
    unpriced_models: list[str] = field(default_factory=list)
    problems: list[LineProblem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.admitted

    def refuse(self, error: SpendError) -> "CallCheck":
        self.admitted = False
        self.refusal, self.reason = error.kind, error.message
        self.stop = (STOP_CAP_REACHED if error.kind == "cap-reached"
                     else STOP_CAP_UNCHECKED)
        log.info("spend check %s: %s: %s", self.sid, error.kind, error.message)
        return self

    def as_json(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "stop": self.stop,
            "refusal": self.refusal,
            "reason": self.reason,
            "sid": self.sid,
            "model": self.model,
            "cap_usd": usd(self.cap_usd),
            "spend_so_far_usd": usd(self.spend_so_far_usd),
            "own_cost_usd": usd(self.own_cost_usd),
            "served_cost_usd": usd(self.served_cost_usd),
            "worst_case_usd": usd(self.worst_case_usd),
            "projected_usd": usd(self.projected_usd),
            "calls_so_far": self.calls_so_far,
            "input_tokens": self.input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "input_price_class": self.input_price_class,
            "input_price_usd_per_mtok": usd(self.input_price),
            "output_price_usd_per_mtok": usd(self.output_price),
            "unpriced_models": list(self.unpriced_models),
            "problems": [p.as_json() for p in self.problems[:MAX_REPORTED_PROBLEMS]],
            "problems_total": len(self.problems),
            "state_dir": str(self.state_dir),
            "stream": str(self.stream),
            "prices": str(self.prices),
        }


def check_call(state_dir: Path, *, sid: str, cap_usd: Decimal, model: str,
               input_tokens: int, max_output_tokens: int,
               prices_path: Path | None = None) -> CallCheck:
    """The hard cap's pre-call check (brief item 5): the function the Arc 2
    loop runs before every model call, and `twine spend check` runs by hand.

    Admits the call exactly when

        spend so far + worst case <= cap

    where spend so far is the session's own cost plus the cost of records
    that served it (T11: what an effort mechanism spent for this session
    counts against its envelope), and the worst case is
    `worst_case_cost(price, input_tokens, max_output_tokens)`.

    Not admitted, with `refusal` naming why: the cap (`cap-reached`, with
    `stop` "cap-reached"); and, each with `stop` "cap-unchecked" (the check
    could not run): an argument that is not a cap, a count or a sid; an
    unreadable or malformed stream; an absent or malformed price file; a
    model — the call's, or one in the session's history — with no price
    row. If the cap cannot be checked the call does not happen. Never
    raises for those.
    """
    state_dir = Path(state_dir)
    prices_path = Path(prices_path) if prices_path else state_dir / PRICES_NAME
    check = CallCheck(sid=sid, model=model, cap_usd=cap_usd, input_tokens=input_tokens,
                      max_output_tokens=max_output_tokens, state_dir=state_dir,
                      stream=state_dir / STREAM_NAME, prices=prices_path)
    bad = _argument_faults(sid, cap_usd, model, input_tokens, max_output_tokens)
    if bad:
        return check.refuse(SpendError("bad-argument", "; ".join(bad)))
    stream = read_stream(check.stream)
    check.problems = list(stream.problems)
    error = stream.refusal()
    if error is not None:
        return check.refuse(error)
    try:
        prices = load_prices(prices_path)
    except SpendError as exc:
        return check.refuse(exc)
    relevant = [r for r in stream.records if sid in (r.sid, r.served_sid)]
    unpriced = prices.unpriced([model] + [r.model for r in relevant])
    if unpriced:
        check.unpriced_models = unpriced
        return check.refuse(SpendError(
            "unpriced-model", f"no price row for {', '.join(repr(m) for m in unpriced)} "
            f"in {prices_path}; the cap cannot be checked"))
    sessions, _ = accumulate(relevant, prices)
    session = sessions.get(sid, SessionTotals(sid))
    price = prices.models[model]
    check.calls_so_far = session.calls
    check.own_cost_usd = session.cost_usd
    check.served_cost_usd = session.served_cost_usd
    check.spend_so_far_usd = session.spend_so_far_usd
    check.input_price_class, check.input_price = price.dearest_input_side()
    check.output_price = price.output
    check.worst_case_usd = worst_case_cost(price, input_tokens, max_output_tokens)
    check.projected_usd = check.spend_so_far_usd + check.worst_case_usd
    if check.projected_usd <= cap_usd:
        check.admitted = True
        log.info("spend check %s: admitted: %s + %s <= %s", sid, check.spend_so_far_usd,
                 check.worst_case_usd, cap_usd)
        return check
    return check.refuse(SpendError(
        "cap-reached",
        f"spend so far {dollars(check.spend_so_far_usd)} + worst case "
        f"{dollars(check.worst_case_usd)} = {dollars(check.projected_usd)}, over the "
        f"cap {dollars(cap_usd)}; the call is not made, and it is not shrunk to fit"))


def _argument_faults(sid: Any, cap: Any, model: Any, input_tokens: Any,
                     max_output: Any) -> list[str]:
    faults = []
    if not _is_name(sid):
        faults.append(f"sid {sid!r} is not a session id")
    if not _is_name(model):
        faults.append(f"model {model!r} is not a model id")
    if not isinstance(cap, Decimal) or not cap.is_finite() or cap < 0:
        faults.append(f"cap {cap!r} is not a finite, non-negative amount of US dollars")
    for name, value in (("input", input_tokens), ("max-output", max_output)):
        if type(value) is not int or value < 0:
            faults.append(f"{name} {value!r} is not a non-negative token count")
    return faults


# ---------------------------------------------------------------------------
# 10. Rendering helpers
# ---------------------------------------------------------------------------


def parse_usd(text: str) -> Decimal:
    """A cap from the command line, exactly: "5", "0.25", "1e2". Raises
    ValueError for anything that is not a finite, non-negative number."""
    try:
        value = Decimal(text.strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"{text!r} is not a number of US dollars") from None
    if not value.is_finite() or value < 0:
        raise ValueError(f"{text!r} is not a finite, non-negative number of US dollars")
    return value


def parse_count(text: str) -> int:
    """A token count from the command line: a non-negative integer."""
    try:
        value = int(text.strip(), 10)
    except (ValueError, AttributeError):
        raise ValueError(f"{text!r} is not a whole number of tokens") from None
    if value < 0:
        raise ValueError(f"{text!r} is negative")
    return value


def usd(value: Decimal | None) -> float | None:
    """The JSON twin's number: the exact Decimal rounded to a double. The
    decision a check made was made on the Decimal, not on this."""
    return None if value is None else float(value)


def dollars(value: Decimal | None) -> str:
    """A human-readable amount, exact: `$0.0123`, never rounded."""
    if value is None:
        return "(unpriced)"
    text = format(value.normalize(), "f") if value else "0"
    return "$" + text

"""The session's cost file (twine-run-telemetry; cli-contract.md §18.7a):
what `bale apply --cost-file PATH` is handed, so bale stamps the session's
cost into the attempt that apply writes.

    <state-dir>/cost/<sid>.json        (the directory 0700, the file 0600)

One JSON object with exactly six keys, in this order — bale's own, from its
`telemetry-record` schema, which refuses any other:

    tokens_in    every token the model read as prompt: `input` + `cache_read`
                 + `cache_write` (twine's token classes are disjoint, so this
                 is a plain sum)
    tokens_out   every token the model generated: `output` + `thinking`
                 (thinking 0 where the provider did not report it — it is
                 then inside `output`, counted once)
    usd          the cost in dollars, priced as `twine spend totals` prices
                 it; null when any record is unpriced (a partial sum is never
                 reported as a total)
    model_tier   always null: twine allocates no effort tier
    calls        the number of records
    models       the records' model strings, sorted and unique

Summed over **every** `spend.jsonl` record of the sid — the session's whole
spend, whatever run, resume or desk made the calls — and written as a
snapshot (a temporary file in the same directory, fsynced, then renamed over
the name), never a log: whoever prints an apply line writes it first, so the
file the line names is the spend up to that line.

A cost file that cannot be written (a stream that does not parse, a
directory that cannot be made) raises CostFileError naming why; the caller
prints the plain apply line and says so — an apply is never held up by
telemetry. Nothing here starts a process, reads a key or calls a model.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from twine import bale, spend
from twine.kill import DIR_MODE, FILE_MODE, is_sid

log = logging.getLogger("twine.cost")

COST_SUBDIR = "cost"
SUFFIX = ".json"
# bale's six keys, in the order the file carries them.
KEYS = ("tokens_in", "tokens_out", "usd", "model_tier", "calls", "models")


class CostFileError(Exception):
    """The cost file could not be worked out or written; the message says
    why, in a sentence the twin and the warning carry."""


def cost_dir(state_dir: Path) -> Path:
    return Path(state_dir) / COST_SUBDIR


def cost_path(state_dir: Path, sid: str) -> Path:
    """`<state-dir>/cost/<sid>.json`. Raises ValueError for a sid twine would
    not name a file by."""
    if not is_sid(sid):
        raise ValueError(f"session id {sid!r} is not one twine names a cost file by")
    return cost_dir(state_dir) / f"{sid}{SUFFIX}"


@dataclass(frozen=True)
class Cost:
    """The session's cost as bale's six keys carry it."""

    tokens_in: int
    tokens_out: int
    usd: float | None
    calls: int
    models: tuple[str, ...]

    def as_json(self) -> dict[str, Any]:
        return {"tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
                "usd": self.usd, "model_tier": None, "calls": self.calls,
                "models": list(self.models)}


def session_cost(state_dir: Path, sid: str, prices_path: Path | None = None) -> Cost:
    """The sums over every record of `sid` in the state directory's spend
    stream. Raises CostFileError when the stream cannot be read as one (a
    malformed line is never skipped: the sum would be a guess). An unreadable
    price file or a model it does not price is not an error: `usd` is null."""
    stream = read_records(state_dir)
    records = [r for r in stream if r.sid == sid]
    tokens_in = tokens_out = 0
    for record in records:
        t = record.tokens
        tokens_in += t.input + t.cache_read + t.cache_write
        tokens_out += t.output + (t.thinking or 0)
    return Cost(tokens_in=tokens_in, tokens_out=tokens_out,
                usd=priced(state_dir, records, prices_path), calls=len(records),
                models=tuple(sorted({r.model for r in records})))


def read_records(state_dir: Path) -> list[spend.UsageRecord]:
    stream = spend.read_stream(Path(state_dir) / spend.STREAM_NAME)
    error = stream.refusal()
    if error is not None:
        raise CostFileError(f"the spend stream cannot be summed: {error.message}")
    return stream.records


def priced(state_dir: Path, records: list[spend.UsageRecord],
           prices_path: Path | None) -> float | None:
    """The records' cost in dollars, or None when any is unpriced. No records
    cost nothing (the price file is not read)."""
    if not records:
        return 0.0
    path = Path(prices_path) if prices_path else Path(state_dir) / spend.PRICES_NAME
    try:
        table = spend.load_prices(path)
    except spend.SpendError as exc:
        log.info("cost: %s cannot be read as a price file (%s); usd is null", path,
                 exc.message)
        return None
    if table.unpriced(r.model for r in records):
        return None
    total = Decimal(0)
    for record in records:
        total += spend.record_cost(record, table.models[record.model])
    return spend.usd(total)


def write_cost_file(state_dir: Path, sid: str, prices_path: Path | None = None) -> Path:
    """Work the session's cost out and write `<state-dir>/cost/<sid>.json`,
    replacing any earlier snapshot atomically. Returns the path. Raises
    CostFileError, naming why, when it cannot."""
    try:
        path = cost_path(state_dir, sid)
    except ValueError as exc:
        raise CostFileError(str(exc)) from exc
    cost = session_cost(state_dir, sid, prices_path)
    data = (json.dumps(cost.as_json(), ensure_ascii=False) + "\n").encode("utf-8")
    temporary = path.parent / f".{path.name}.tmp-{os.getpid()}"
    try:
        path.parent.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
        try:
            os.fchmod(fd, FILE_MODE)
            written = 0
            while written < len(data):
                written += os.write(fd, data[written:])
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, path)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise CostFileError(f"{path} cannot be written: {exc.strerror or exc}") from exc
    log.info("cost: wrote %s (%d call(s), usd %s)", path, cost.calls, cost.usd)
    return path


@dataclass(frozen=True)
class CostedLine:
    """An apply line and what happened to its cost file: `path` the file it
    names (None when it was not written), `error` why not."""

    line: str
    path: Path | None = None
    error: str | None = None


def costed_apply_line(state_dir: Path, sid: str, tarball: str,
                      prices_path: Path | None = None,
                      extra_flags: str = "") -> CostedLine:
    """`bale apply <tarball> --cost-file <path>` after writing the file — or
    the plain `bale apply <tarball>` and the reason, when the file cannot be
    written. `extra_flags` (already quoted, e.g. the admit line's
    `--allow-out-of-scope PATH`) is appended last."""
    try:
        path = write_cost_file(state_dir, sid, prices_path)
    except CostFileError as exc:
        log.warning("cost: no cost file for %s: %s", sid, exc)
        line = bale.apply_line(tarball)
        return CostedLine(line + (f" {extra_flags}" if extra_flags else ""), None, str(exc))
    line = bale.apply_cost_line(tarball, str(path))
    return CostedLine(line + (f" {extra_flags}" if extra_flags else ""), path, None)


__all__ = ["COST_SUBDIR", "Cost", "CostFileError", "CostedLine", "KEYS", "cost_dir",
           "cost_path", "costed_apply_line", "session_cost", "write_cost_file"]

"""The in-flight record (Arc 1 session 3, "offline courier — emit";
twine-seed.md §5.1 row 3): twine's one piece of state besides spend.

When `twine carry bundle` opens a session with `bale open --json` and bale
answers `opened` or `second-desk`, the verb records the open here:

    <state-dir>/inflight/<sid>.json

one JSON object with exactly four keys —

    {"sid": <sid>, "cwd": <the absolute directory bale ran in>,
     "tarball": <bale's tarball from the opened line, or null>,
     "opens": [{"outcome": "opened" | "second-desk",
                "desk": <bale's desk: null | "desk-2" | …>,
                "bundle_sha256": <bale's bundle.sha256>,
                "opener_sha256": <sha256 of the opener's UTF-8 bytes>,
                "recorded_at": <UTC, ISO 8601, Z>}]}

— the directory 0700, the file 0600, written by atomic replace (a temp
file, fsynced, renamed over the record, the directory fsynced) under an
exclusive flock on `<state-dir>/inflight/` (twine/kill.py's
`_write_replacing` and `_locked`, imported, not moved).

`opened` writes a record holding that one open, replacing any record of the
same sid. `second-desk` appends its entry to the record of that sid,
keeping the record's `tarball` and `cwd`; with no record, or one that
cannot be read as this shape, it writes a fresh record — `tarball` null,
this invocation's `cwd`, only this entry — and says which (`Recorded.fresh`).

Why it exists in Arc 1 already: bale 0.4.49's `second-desk` line carries
`tarball` null, so the record of the first open is where twine finds the
request tarball a second desk needs (brief ruling 3).

It is a **cache** in N4's sense: every value in it is bale's (from the line
bale printed) or the invocation's (`cwd`, `recorded_at`). Deleting it loses
nothing bale does not know. Nothing in Arc 1 removes it (Arc 2's loop knows
when a session closes), and nothing in Arc 1 reads it but the verb that
writes it (`twine status` reading it is a later session's).

Sections:
  1. Names and errors       (~line 60)
  2. Reading a record       (~line 110)
  3. Recording an open      (~line 200)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from twine.kill import DIR_MODE, RECORD_SUFFIX, _locked, _write_replacing, is_sid, utc_now

log = logging.getLogger("twine.inflight")

# ---------------------------------------------------------------------------
# 1. Names and errors
# ---------------------------------------------------------------------------

INFLIGHT_SUBDIR = "inflight"
# The record's four keys and an open entry's five (brief §2.4): exactly what
# record_open writes and what read_inflight requires — no more, no fewer.
RECORD_KEYS = ("sid", "cwd", "tarball", "opens")
OPEN_KEYS = ("outcome", "desk", "bundle_sha256", "opener_sha256", "recorded_at")

# The two outcomes of `bale open --json` that open a session at a desk
# (format_open_json, bale 0.4.49). `rehearsed` (under --check) writes nothing.
OPENED = "opened"
SECOND_DESK = "second-desk"
RECORDED_OUTCOMES = (OPENED, SECOND_DESK)


class InflightError(OSError):
    """The in-flight record could not be written. `found` is the record that
    was read before the write failed — a well-formed one — or None, so a
    caller can still name the tarball it holds."""

    def __init__(self, errno_: int | None, message: str,
                 found: dict[str, Any] | None = None) -> None:
        super().__init__(errno_, message)
        self.message = message
        self.found = found

    def __str__(self) -> str:
        return self.message


class InflightRecordError(ValueError):
    """A file at a record's path that is not an in-flight record; the message
    names every fault."""


def inflight_dir(state_dir: Path) -> Path:
    return Path(state_dir) / INFLIGHT_SUBDIR


def inflight_path(state_dir: Path, sid: str) -> Path:
    """`<state-dir>/inflight/<sid>.json`. Raises ValueError for a sid twine
    would not accept (twine.kill.is_sid: it names a file)."""
    if not is_sid(sid):
        raise ValueError(f"session id {sid!r} is not one twine records")
    return inflight_dir(state_dir) / f"{sid}{RECORD_SUFFIX}"


def opener_sha256(opener: str) -> str:
    """The sha256 of the opener's UTF-8 bytes — what the record keeps of it
    (the opener itself is bale's to print again; the hash says which one a
    desk was handed)."""
    return hashlib.sha256(opener.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 2. Reading a record
# ---------------------------------------------------------------------------


def read_inflight(state_dir: Path, sid: str) -> dict[str, Any] | None:
    """`sid`'s in-flight record as a dict with exactly RECORD_KEYS, or None
    when there is none. Raises InflightRecordError, naming every fault, for
    a file there that cannot be read as one — unreadable, not a JSON object,
    a key missing or extra, its `sid` not the file's, `cwd` not an absolute
    path, `tarball` neither a string nor null, `opens` not a non-empty array
    of entries with exactly OPEN_KEYS (an `outcome` of the two, `desk` and
    `bundle_sha256` a string or null, `opener_sha256` and `recorded_at`
    non-empty strings)."""
    path = inflight_path(state_dir, sid)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise InflightRecordError(f"{path} cannot be read: {exc.strerror or exc}") from exc
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError) as exc:
        # UnicodeDecodeError is a ValueError; RecursionError is how json
        # refuses a deeply nested document.
        raise InflightRecordError(f"{path} is not a JSON object: "
                                  f"{type(exc).__name__}: {str(exc)[:200]}") from exc
    if not isinstance(obj, dict):
        raise InflightRecordError(f"{path} is not a JSON object")
    faults = _key_faults("the record", obj, RECORD_KEYS)
    if obj.get("sid") != sid:
        faults.append(f"its sid is {obj.get('sid')!r}, not {sid!r}")
    cwd = obj.get("cwd")
    if not isinstance(cwd, str) or not os.path.isabs(cwd):
        faults.append(f"cwd {_short(cwd)} is not an absolute path")
    if not _str_or_none(obj.get("tarball")):
        faults.append(f"tarball {_short(obj.get('tarball'))} is neither a string nor null")
    opens = obj.get("opens")
    if not isinstance(opens, list) or not opens:
        faults.append(f"opens {_short(opens)} is not a non-empty array")
    else:
        for n, entry in enumerate(opens):
            faults.extend(_entry_faults(n, entry))
    if faults:
        raise InflightRecordError(f"{path} is not an in-flight record: " + "; ".join(faults))
    return {key: obj[key] for key in RECORD_KEYS}


def _entry_faults(n: int, entry: Any) -> list[str]:
    where = f"opens[{n}]"
    if not isinstance(entry, dict):
        return [f"{where} is not an object"]
    faults = _key_faults(where, entry, OPEN_KEYS)
    if entry.get("outcome") not in RECORDED_OUTCOMES:
        faults.append(f"{where}.outcome {_short(entry.get('outcome'))} is not "
                      f"{OPENED!r} or {SECOND_DESK!r}")
    for key in ("desk", "bundle_sha256"):
        if not _str_or_none(entry.get(key)):
            faults.append(f"{where}.{key} {_short(entry.get(key))} is neither a string "
                          "nor null")
    for key in ("opener_sha256", "recorded_at"):
        value = entry.get(key)
        if not isinstance(value, str) or not value:
            faults.append(f"{where}.{key} {_short(value)} is not a non-empty string")
    return faults


def _key_faults(where: str, obj: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    missing = [k for k in keys if k not in obj]
    extra = sorted(k for k in obj if k not in keys)
    faults = []
    if missing:
        faults.append(f"{where} lacks {', '.join(missing)}")
    if extra:
        faults.append(f"{where} has keys the format does not name: "
                      f"{', '.join(map(repr, extra))}")
    return faults


def _str_or_none(value: Any) -> bool:
    return value is None or isinstance(value, str)


def _short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


# ---------------------------------------------------------------------------
# 3. Recording an open
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Recorded:
    """What record_open wrote: the record's path and content, the record
    found there before (a well-formed one, else None), and — when the write
    is not the plain case — what happened instead:

    replaced  an `opened` replaced an earlier record of the same sid (not
              an error: the open bale reported is the session's now)
    fresh     a `second-desk` found no record to append to, or one that
              could not be read as one, and wrote a fresh record holding
              only its own entry, `tarball` null — the sentence says which
    """

    path: Path
    record: dict[str, Any]
    found: dict[str, Any] | None
    replaced: bool = False
    fresh: str | None = None


def open_entry(outcome: str, *, desk: str | None, bundle_sha256: str | None,
               opener: str, clock: Callable[[], str] = utc_now) -> dict[str, Any]:
    """One `opens` entry, its keys in OPEN_KEYS order."""
    if outcome not in RECORDED_OUTCOMES:
        raise ValueError(f"outcome {outcome!r} opens nothing to record")
    return {"outcome": outcome, "desk": desk, "bundle_sha256": bundle_sha256,
            "opener_sha256": opener_sha256(opener), "recorded_at": clock()}


def record_open(state_dir: Path, sid: str, *, outcome: str, cwd: str,
                tarball: str | None, desk: str | None, bundle_sha256: str | None,
                opener: str, clock: Callable[[], str] = utc_now) -> Recorded:
    """Record one open bale reported (`opened` or `second-desk`) in `sid`'s
    in-flight record — the module docstring's rules. Creates the state
    directory and `inflight/` (0700) when absent, then reads, composes and
    replaces the record under an exclusive flock on `inflight/`, so two
    desks recording at once lose neither entry.

    `tarball` is bale's (the opened line's; a second desk's is not kept:
    the record's stands, or null on a fresh record). Raises ValueError for
    a sid or outcome that is not one, InflightError (carrying the record it
    found, if any) when the record cannot be written."""
    path = inflight_path(state_dir, sid)
    entry = open_entry(outcome, desk=desk, bundle_sha256=bundle_sha256, opener=opener,
                       clock=clock)
    directory = path.parent
    try:
        Path(state_dir).mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        directory.mkdir(mode=DIR_MODE, exist_ok=True)
    except OSError as exc:
        fault = ("exists and is not a directory" if isinstance(exc, FileExistsError)
                 else f"cannot be created: {exc.strerror or exc}")
        raise InflightError(exc.errno, f"{exc.filename or directory} {fault}") from exc
    found: dict[str, Any] | None = None
    try:
        with _locked(directory):
            found, fault = _read_for_update(state_dir, sid)
            record, replaced, fresh = _compose(sid, outcome, cwd, tarball, entry,
                                               found, fault, path)
            body = json.dumps(record, ensure_ascii=True) + "\n"
            _write_replacing(path, body.encode("ascii"))
    except InflightError:
        raise
    except OSError as exc:
        raise InflightError(exc.errno, f"cannot write the in-flight record {path}: "
                                       f"{exc.strerror or exc}", found) from exc
    log.info("in-flight record for %s: %s recorded (%d open%s; %s)", sid, outcome,
             len(record["opens"]), "" if len(record["opens"]) == 1 else "s", path)
    return Recorded(path, record, found, replaced, fresh)


def _read_for_update(state_dir: Path, sid: str) -> tuple[dict[str, Any] | None, str | None]:
    """The record there now and, when a file there is not one, why."""
    try:
        return read_inflight(state_dir, sid), None
    except InflightRecordError as exc:
        log.warning("%s", exc)
        return None, str(exc)


def _compose(sid: str, outcome: str, cwd: str, tarball: str | None,
             entry: dict[str, Any], found: dict[str, Any] | None, fault: str | None,
             path: Path) -> tuple[dict[str, Any], bool, str | None]:
    """The record to write, whether an `opened` replaced one, and the
    sentence a fresh `second-desk` record carries."""
    if outcome == OPENED:
        replaced = found is not None or fault is not None
        if replaced:
            log.info("in-flight record for %s: an earlier record at %s is replaced "
                     "by this open", sid, path)
        return ({"sid": sid, "cwd": cwd, "tarball": tarball, "opens": [entry]},
                replaced, None)
    if found is not None:
        if found["cwd"] != cwd:
            log.info("in-flight record for %s: this desk ran in %s; the record keeps "
                     "the first open's %s", sid, cwd, found["cwd"])
        return ({"sid": sid, "cwd": found["cwd"], "tarball": found["tarball"],
                 "opens": [*found["opens"], entry]}, False, None)
    if fault is not None:
        fresh = (f"{fault} — it was replaced by a fresh record holding only this "
                 "second-desk open, tarball null")
    else:
        fresh = (f"no in-flight record of {sid} to append this second-desk open to; "
                 f"a fresh one holding only it was written at {path}, tarball null")
    return ({"sid": sid, "cwd": cwd, "tarball": None, "opens": [entry]}, False, fresh)

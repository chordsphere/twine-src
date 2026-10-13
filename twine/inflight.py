"""The in-flight record (Arc 1 session 3, "offline courier — emit";
twine-seed.md §5.1 row 3): twine's one piece of state besides spend.

When `twine carry bundle` opens a session with `bale open --json` and bale
answers `opened` or `second-desk`, the verb records the open here:

    <state-dir>/inflight/<sid>.json

one JSON object with exactly four keys —

    {"sid": <sid>, "cwd": <the absolute directory bale ran in>,
     "tarball": <bale's request tarball, or null>,
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
same sid, its `tarball` the opened line's. `second-desk` appends its entry
to the record of that sid, keeping the record's `cwd` and its `tarball` when
that is set — adopting the second-desk line's when the record's is null and
the line names one; with no record, or one that cannot be read as this
shape, it writes a fresh record — the second-desk line's `tarball` (null
only when bale's is null), this invocation's `cwd`, only this entry — and
says which (`Recorded.fresh`). Session 2026-10-12-twine-bundle-051-004
made those two second-desk rules: before it, the second-desk line's tarball
was never kept.

Why it exists in Arc 1 already: bale 0.4.49's `second-desk` line carried
`tarball` null, so the record of the first open was where twine found the
request tarball a second desk needs (brief ruling 3). Since bale 0.4.50 the
`second-desk` line names the outbox tarball itself when the file exists;
the record still answers when a line names none.

It is a **cache** in N4's sense: every value in it is bale's (from the line
bale printed) or the invocation's (`cwd`, `recorded_at`). Deleting it loses
nothing bale does not know. Nothing in Arc 1 removes it (Arc 2's loop knows
when a session closes). Two things read it: the verb that writes it, and
`twine status` (session `2026-10-08-twine-status-inflight-004`), through
`list_inflight` — which lists `inflight/` and reads every record there
without writing, locking or creating anything, and names each entry there
that is not a record rather than dropping it.

Since Arc 2 R4 (`twine run`, cli-contract.md §15.4 and §18) a record may
carry a fifth key, after the four: **`runtime`** — the run that hosts the
session, written by `record_runtime` once its sandbox, adapter and
transcript exist:

    "runtime": {"adapter": <the adapter's name>, "model": <the model id>,
                "sandbox_home": <the sandbox home, absolute>,
                "transcript": <the transcript, absolute>,
                "started_at": <UTC, ISO 8601, Z>, "pgid": <the runtime's group>}

It is optional — a record `carry bundle` wrote has none — and when present
it has exactly those six keys. A later run replaces it; a `second-desk`
append keeps it; an `opened` replaces the whole record and so drops it.
`remove_inflight` is the one removal: the loop's, when a run ends
`delivered` (the response is the courier's now; the sandbox home stays
until the operator applies).

Sections:
  1. Names and errors       (~line 90)
  2. Reading a record       (~line 150)
  3. Listing the records    (~line 260)
  4. Recording an open      (~line 370)
  5. The runtime's fields, and the one removal (~line 510)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from twine.kill import (DIR_MODE, RECORD_SUFFIX, _locked, _write_replacing, is_sid,
                        is_temp_name, utc_now)

log = logging.getLogger("twine.inflight")

# ---------------------------------------------------------------------------
# 1. Names and errors
# ---------------------------------------------------------------------------

INFLIGHT_SUBDIR = "inflight"
# The record's four keys and an open entry's five (brief §2.4): exactly what
# record_open writes and what read_inflight requires — no more, no fewer.
RECORD_KEYS = ("sid", "cwd", "tarball", "opens")
OPEN_KEYS = ("outcome", "desk", "bundle_sha256", "opener_sha256", "recorded_at")
# Since Arc 2 R4: the optional fifth key, after the four, and its six keys —
# the run that hosts the session (record_runtime). Optional, so every record
# carry bundle writes still reads; exactly these six when present.
RUNTIME_KEY = "runtime"
RUNTIME_KEYS = ("adapter", "model", "sandbox_home", "transcript", "started_at", "pgid")

# The two outcomes of `bale open --json` that open a session at a desk
# (format_open_json; recorded at bale 0.4.51). `rehearsed` (under --check)
# and `open-refused` (bale 0.4.50 on) write nothing.
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
    """`sid`'s in-flight record as a dict with exactly RECORD_KEYS — and,
    since Arc 2 R4, `runtime` after them when the record carries one — or
    None when there is none. Raises InflightRecordError, naming every fault,
    for a file there that cannot be read as one — unreadable, not a JSON
    object, a key missing or extra, its `sid` not the file's, `cwd` not an
    absolute path, `tarball` neither a string nor null, `opens` not a
    non-empty array of entries with exactly OPEN_KEYS (an `outcome` of the
    two, `desk` and `bundle_sha256` a string or null, `opener_sha256` and
    `recorded_at` non-empty strings), a `runtime` that is not an object with
    exactly RUNTIME_KEYS (`adapter`, `model`, `sandbox_home`, `transcript`,
    `started_at` non-empty strings, the two paths absolute, `pgid` an
    integer above 1)."""
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
    faults = _key_faults("the record", obj, RECORD_KEYS, optional=(RUNTIME_KEY,))
    if RUNTIME_KEY in obj:
        faults.extend(_runtime_faults(obj[RUNTIME_KEY]))
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
    record = {key: obj[key] for key in RECORD_KEYS}
    if RUNTIME_KEY in obj:
        record[RUNTIME_KEY] = {key: obj[RUNTIME_KEY][key] for key in RUNTIME_KEYS}
    return record


def _runtime_faults(runtime: Any) -> list[str]:
    where = RUNTIME_KEY
    if not isinstance(runtime, dict):
        return [f"{where} {_short(runtime)} is not an object"]
    faults = _key_faults(where, runtime, RUNTIME_KEYS)
    for key in ("adapter", "model", "started_at", "sandbox_home", "transcript"):
        value = runtime.get(key)
        if not isinstance(value, str) or not value:
            faults.append(f"{where}.{key} {_short(value)} is not a non-empty string")
        elif key in ("sandbox_home", "transcript") and not os.path.isabs(value):
            faults.append(f"{where}.{key} {_short(value)} is not an absolute path")
    pgid = runtime.get("pgid")
    if type(pgid) is not int or pgid <= 1:
        faults.append(f"{where}.pgid {_short(pgid)} is not an integer above 1")
    return faults


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


def _key_faults(where: str, obj: dict[str, Any], keys: tuple[str, ...],
                optional: tuple[str, ...] = ()) -> list[str]:
    missing = [k for k in keys if k not in obj]
    extra = sorted(k for k in obj if k not in keys and k not in optional)
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
# 3. Listing the records
# ---------------------------------------------------------------------------

# The temp file twine/kill.py's _write_replacing writes beside a record before
# renaming it over the record (_temp_name: `.twine-<pid>-<monotonic ns>.tmp`).
# One seen in `inflight/` is a write in progress or one that did not finish;
# it is still not a record, so it is still named — this only says which.
# The shape is tested by twine.kill.is_temp_name, exported beside _temp_name
# so this module never restates it (session 2026-10-12-twine-pin-floor-002,
# status-inflight-004's proposal).


@dataclass(frozen=True)
class InflightListing:
    """What list_inflight found in `<state-dir>/inflight/`.

    sids    the sids whose `<sid>.json` read_inflight accepts, sorted
    faults  one sentence per entry there that is not a record, in name
            order, each naming the entry by its basename and saying why —
            read_inflight's own words for a `<sid>.json` it refuses
    """

    sids: tuple[str, ...] = ()
    faults: tuple[str, ...] = ()


def list_inflight(state_dir: Path) -> InflightListing:
    """Every in-flight record in `<state-dir>/inflight/`, read, and every
    entry there that is not one, named. Reading only: nothing is created,
    written or locked (a record is replaced atomically, so a reader sees the
    old record or the new one, never half of either), and nothing here
    raises for what the directory holds.

    - `inflight/` absent, or not a directory: no sids, no faults.
    - `inflight/` that cannot be listed (no read permission, say): no sids
      and one fault naming `inflight/` — never a traceback, and never an
      empty listing that would read as "no records".
    - an entry whose name is not `<sid>.json` for a sid twine accepts
      (twine.kill.is_sid): a fault saying so.
    - a `<sid>.json` read_inflight refuses: a fault in read_inflight's
      words, the full path cut to the basename.
    - a `<sid>.json` listed but gone when read (a dangling link, or removed
      in between): a fault saying so — a silent skip is a bug.
    """
    directory = inflight_dir(state_dir)
    # os.path.isdir never raises: a path that cannot be stat'd reads as
    # absent, as `twine status` reads the state directory itself.
    if not os.path.isdir(directory):
        return InflightListing()
    try:
        names = sorted(os.listdir(directory))
    except OSError as exc:
        fault = f"{INFLIGHT_SUBDIR}/ cannot be listed: {exc.strerror or exc}"
        log.warning("%s: %s", directory, fault)
        return InflightListing((), (fault,))
    sids: list[str] = []
    faults: list[str] = []
    for name in names:
        sid, fault = _read_entry(state_dir, name)
        if sid is not None:
            sids.append(sid)
        else:
            faults.append(fault)
            log.warning("%s: %s", directory, fault)
    log.debug("%s: %d record(s), %d fault(s)", directory, len(sids), len(faults))
    # Sorted by sid, not by file name: `a.json` sorts after `a-b.json`, `a`
    # before `a-b`.
    return InflightListing(tuple(sorted(sids)), tuple(faults))


def _read_entry(state_dir: Path, name: str) -> tuple[str | None, str]:
    """(sid, "") when `name` is a record that reads, else (None, the fault)."""
    shown = _shown(name)
    if not name.endswith(RECORD_SUFFIX):
        if is_temp_name(name):
            return None, (f"{shown} is not an in-flight record: it is the temp file of a "
                          "record write still in progress, or of one that did not finish")
        return None, (f"{shown} is not an in-flight record: its name is not "
                      f"<sid>{RECORD_SUFFIX}")
    sid = name[:-len(RECORD_SUFFIX)]
    if not is_sid(sid):
        return None, (f"{shown} is not an in-flight record: {_shown(sid, quote=True)} "
                      "is not a session id twine accepts")
    path = inflight_path(state_dir, sid)
    try:
        record = read_inflight(state_dir, sid)
    except InflightRecordError as exc:
        message = str(exc)
        # read_inflight's sentences open with the record's full path; the
        # listing names the file by its basename.
        if message.startswith(f"{path} "):
            return None, shown + message[len(str(path)):]
        return None, f"{shown}: {message}"
    if record is None:
        return None, (f"{shown} cannot be read: it was listed but no file is there now "
                      "(a dangling link, or removed while it was read)")
    return sid, ""


def _shown(name: str, *, quote: bool = False) -> str:
    """`name` fit to print on any line: as it is when it is printable text
    (and `quote` is not asked), else its repr — so a name holding a newline,
    or bytes that are not UTF-8 (os.listdir hands those back as lone
    surrogates), can break neither a human line nor the JSON twin's
    encoding."""
    if name.isprintable() and not quote:
        return name
    return repr(name)


# ---------------------------------------------------------------------------
# 4. Recording an open
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
              only its own entry and bale's `tarball` (null when the line
              names none) — the sentence says which
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

    `tarball` is bale's, from the line of this open: an `opened` record
    holds it; a fresh `second-desk` record holds it; an appended
    `second-desk` keeps the record's own when set and adopts it when the
    record's is null (_compose). Raises ValueError for
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
    sentence a fresh `second-desk` record carries.

    The tarball rules (contract §15.4; session 2026-10-12-twine-bundle-051-004,
    once bale 0.4.50's `second-desk` line began naming the outbox tarball):
    every value stays bale's, so

      opened                 bale's `tarball` (null when the line has none)
      second-desk, appended  the record's own when it is set; bale's when
                             the record's is null (adopted); null when both are
      second-desk, fresh     bale's (null only when bale's is null)
    """
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
        kept = found["tarball"]
        if kept is None and tarball is not None:
            log.info("in-flight record for %s: the record held no tarball; it adopts "
                     "the one bale's second-desk line names, %s", sid, tarball)
            kept = tarball
        elif kept is not None and tarball is not None and kept != tarball:
            log.info("in-flight record for %s: the record keeps its own tarball %s; "
                     "bale's second-desk line names %s", sid, kept, tarball)
        appended = {"sid": sid, "cwd": found["cwd"], "tarball": kept,
                    "opens": [*found["opens"], entry]}
        if RUNTIME_KEY in found:
            # The run hosting an earlier desk keeps its fields until a run of
            # this desk writes its own (record_runtime): a reader keeps them.
            appended[RUNTIME_KEY] = found[RUNTIME_KEY]
        return appended, False, None
    held = ("bale's tarball" if tarball is not None
            else "tarball null (bale's line names none)")
    if fault is not None:
        fresh = (f"{fault} — it was replaced by a fresh record holding only this "
                 f"second-desk open, {held}")
    else:
        fresh = (f"no in-flight record of {sid} to append this second-desk open to; "
                 f"a fresh one holding only it was written at {path}, {held}")
    return ({"sid": sid, "cwd": cwd, "tarball": tarball, "opens": [entry]}, False, fresh)


# ---------------------------------------------------------------------------
# 5. The runtime's fields, and the one removal (Arc 2 R4)
# ---------------------------------------------------------------------------


def runtime_fields(*, adapter: str, model: str, sandbox_home: str, transcript: str,
                   pgid: int, clock: Callable[[], str] = utc_now) -> dict[str, Any]:
    """The `runtime` object, its keys in RUNTIME_KEYS order."""
    return {"adapter": adapter, "model": model, "sandbox_home": sandbox_home,
            "transcript": transcript, "started_at": clock(), "pgid": pgid}


def record_runtime(state_dir: Path, sid: str, runtime: dict[str, Any]) -> dict[str, Any]:
    """Write `runtime` into `sid`'s in-flight record — replacing an earlier
    run's — under the record's flock, by atomic replace, and return the
    record written. Raises InflightError when there is no record to grow
    (carry bundle could not write one), when the record there cannot be
    read as one (its faults named), or when it cannot be written; ValueError
    for a `runtime` without exactly RUNTIME_KEYS."""
    faults = _runtime_faults(runtime)
    if faults:
        raise ValueError("runtime fields: " + "; ".join(faults))
    path = inflight_path(state_dir, sid)
    directory = path.parent
    if not directory.is_dir():
        raise InflightError(None, f"no in-flight record of {sid} to add the runtime's "
                                  f"fields to ({directory} does not exist)")
    try:
        with _locked(directory):
            try:
                found = read_inflight(state_dir, sid)
            except InflightRecordError as exc:
                raise InflightError(None, f"{exc}; the runtime's fields were not "
                                          "written") from exc
            if found is None:
                raise InflightError(None, f"no in-flight record of {sid} to add the "
                                          f"runtime's fields to ({path})")
            record = {key: found[key] for key in RECORD_KEYS}
            record[RUNTIME_KEY] = {key: runtime[key] for key in RUNTIME_KEYS}
            body = json.dumps(record, ensure_ascii=True) + "\n"
            _write_replacing(path, body.encode("ascii"))
    except InflightError:
        raise
    except OSError as exc:
        raise InflightError(exc.errno, f"cannot write the in-flight record {path}: "
                                       f"{exc.strerror or exc}") from exc
    log.info("in-flight record for %s: runtime fields written (%s, %s)", sid,
             runtime["adapter"], runtime["model"])
    return record


def remove_inflight(state_dir: Path, sid: str) -> bool:
    """Remove `sid`'s in-flight record, under its flock — the loop's, when a
    run ends `delivered`. True when one was removed, False when there was
    none (logged; the record is a cache). Raises InflightError when it
    cannot be removed."""
    path = inflight_path(state_dir, sid)
    if not path.parent.is_dir():
        log.info("in-flight record for %s: none to remove (%s absent)", sid, path.parent)
        return False
    try:
        with _locked(path.parent):
            try:
                path.unlink()
            except FileNotFoundError:
                log.info("in-flight record for %s: none to remove (%s)", sid, path)
                return False
    except OSError as exc:
        raise InflightError(exc.errno, f"cannot remove the in-flight record {path}: "
                                       f"{exc.strerror or exc}") from exc
    log.info("in-flight record for %s removed (%s)", sid, path)
    return True


"""The sandbox lifecycle: which kept homes may go, and removing them
(twine-sandbox-confine; claude/context/cli-contract.md §22, runtime-contract.md
§7.7). `twine sandbox prune` (twine/commands/sandbox.py) is the verb; this is
the library under it, so the rule has one home and the tests read it as
functions.

twine never sees an apply — `twine run` ends at `delivered` and keeps the
home, because the response tarball lives in it until the operator applies
it — so what removes a home is a verb that asks bale's own record whether the
session was applied. The record is bale's, written in the repository the
session was opened in: `<repo>/<agent_dir>/telemetry/<sid>.json`, `agent_dir`
from the repository's `bale.toml` `[layout]` (`claude` when unset). **twine
reads from it `attempts[].outcome` and nothing else.**

The rule (`applied_verdict`): of the attempts whose outcome is one of
`applied`, `re-applied`, `rolled-back` or `reverted` — the ones that say
where the merge stands — the last is `applied` or `re-applied`. A close bale
records after the apply (`unlocked`, `closed`, …) is none of the four and
does not hide it; a rollback or a revert after the apply keeps the home. Every
other home is kept, each with why.

Never removed, whatever the record says: a home whose session has an
in-flight record or a running record (the session is not over), and anything
outside `<state-dir>/sandbox/<sid>/` — a name that is not a sid, a `<sid>`
that is a symlink. Nothing here spawns a process or reaches a network; it
reads files and removes one directory tree per home.

Sections:
  1. The record and the rule
  2. The plan
  3. Removal
"""

from __future__ import annotations

import json
import logging
import os
import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from twine.inflight import inflight_path
from twine.kill import is_sid, running_path
from twine.runtime.sandbox import SANDBOX_SUBDIR

log = logging.getLogger("twine.prune")

DEFAULT_AGENT_DIR = "claude"
TELEMETRY_SUBDIR = "telemetry"
# The outcomes that say where the merge stands, and the two that say it stands.
MERGE_OUTCOMES = ("applied", "re-applied", "rolled-back", "reverted")
APPLIED_OUTCOMES = ("applied", "re-applied")

# ---------------------------------------------------------------------------
# 1. The record and the rule
# ---------------------------------------------------------------------------


class RecordError(ValueError):
    """bale's record (or the file that says where it is) cannot be read; the
    message is the reason a home is kept for it."""


def agent_dir(cwd: Path) -> str:
    """`[layout] agent_dir` of `<cwd>/bale.toml`; `claude` when the file is
    absent or does not set it. Raises RecordError for a file that cannot be
    read or parsed or a value that is not a non-empty string."""
    path = Path(cwd) / "bale.toml"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return DEFAULT_AGENT_DIR
    except (OSError, UnicodeDecodeError) as exc:
        raise RecordError(f"{path} cannot be read: {getattr(exc, 'strerror', None) or exc}") \
            from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise RecordError(f"{path} is not valid TOML: {exc}") from exc
    layout = data.get("layout")
    if layout is None:
        return DEFAULT_AGENT_DIR
    if not isinstance(layout, dict):
        raise RecordError(f"{path}: [layout] is not a table")
    value = layout.get("agent_dir", DEFAULT_AGENT_DIR)
    if not isinstance(value, str) or not value.strip():
        raise RecordError(f"{path}: [layout] agent_dir is not a non-empty string")
    return value


def record_path(cwd: Path, agent: str, sid: str) -> Path:
    """`<cwd>/<agent_dir>/telemetry/<sid>.json`."""
    return Path(cwd) / agent / TELEMETRY_SUBDIR / f"{sid}.json"


def attempt_outcomes(path: Path) -> list[str] | None:
    """`attempts[].outcome` of the record at `path`, in order — the only thing
    read from it. None when there is no such file. Raises RecordError for a
    file that cannot be read, is not JSON, is not an object, has no
    `attempts` list, or an attempt that is not an object with a string
    `outcome`."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise RecordError(f"{path} cannot be read: {getattr(exc, 'strerror', None) or exc}") \
            from exc
    try:
        obj = json.loads(text)
    except ValueError as exc:
        raise RecordError(f"{path} is not JSON: {exc}") from exc
    attempts = obj.get("attempts") if isinstance(obj, dict) else None
    if not isinstance(attempts, list):
        raise RecordError(f"{path} has no attempts[] list")
    outcomes = []
    for n, attempt in enumerate(attempts):
        outcome = attempt.get("outcome") if isinstance(attempt, dict) else None
        if not isinstance(outcome, str):
            raise RecordError(f"{path}: attempts[{n}] has no string outcome")
        outcomes.append(outcome)
    return outcomes


def applied_verdict(outcomes: list[str]) -> tuple[bool, str]:
    """(applied, last) for a session's attempt outcomes, oldest first. `last`
    is the last of the four merge outcomes, or — when the session has none —
    the last outcome of any kind (`none` for no attempts at all), the word
    the `not applied (last: …)` reason carries."""
    merges = [o for o in outcomes if o in MERGE_OUTCOMES]
    if merges:
        return merges[-1] in APPLIED_OUTCOMES, merges[-1]
    return False, outcomes[-1] if outcomes else "none"


# ---------------------------------------------------------------------------
# 2. The plan
# ---------------------------------------------------------------------------


@dataclass
class Plan:
    """What to do with each home: `prune` the sids (with their sizes) and
    `kept` each with why, both sorted by sid; `notes` the entries of
    `sandbox/` that are not homes, named (never touched)."""

    prune: list[tuple[str, int]] = field(default_factory=list)
    kept: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def homes(state_dir: Path) -> tuple[list[str], list[str]]:
    """(sids, notes) of `<state-dir>/sandbox/`: every directory (not a
    symlink) named like a sid, sorted — a kept home, whatever it still holds
    beside or instead of its `home/` — and one sentence per other entry. An
    absent `sandbox/` is no homes. Raises OSError when it exists and cannot be
    listed."""
    directory = Path(state_dir) / SANDBOX_SUBDIR
    try:
        names = sorted(os.listdir(directory))
    except FileNotFoundError:
        return [], []
    sids, notes = [], []
    for name in names:
        shown = name if name.isprintable() else repr(name)
        path = directory / name
        if not is_sid(name):
            notes.append(f"{SANDBOX_SUBDIR}/{shown} is not a session id twine names a home by")
        elif path.is_symlink() or not path.is_dir():
            notes.append(f"{SANDBOX_SUBDIR}/{shown} is not a directory twine made")
        else:
            sids.append(name)
    return sids, notes


def _present(path: Path) -> bool | str:
    """True when `path` exists (a symlink counts), False when it does not, and
    the reason as a string when it cannot be looked at."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        return f"{exc.strerror or exc}"
    return True


def why_kept(state_dir: Path, cwd: Path, sid: str, agent: str | RecordError) -> str | None:
    """Why the home of `sid` must stay, or None when it may go. The order:
    an in-flight record, a running record, then bale's record. `agent` is the
    repository's `agent_dir`, or the RecordError that reading it raised."""
    for what, path in (("in flight", inflight_path(state_dir, sid)),
                       ("running", running_path(state_dir, sid))):
        found = _present(path)
        if found is True:
            return what
        if found is not False:
            return f"{what}: its record cannot be looked at ({found})"
    if isinstance(agent, RecordError):
        return f"the record cannot be read: {agent}"
    try:
        outcomes = attempt_outcomes(record_path(cwd, agent, sid))
    except RecordError as exc:
        return f"the record cannot be read: {exc}"
    if outcomes is None:
        return "no bale record"
    applied, last = applied_verdict(outcomes)
    return None if applied else f"not applied (last: {last})"


def plan(state_dir: Path, cwd: Path, *, sid: str | None = None) -> Plan:
    """The decision for every home under `state_dir` (only `sid`'s when
    given). Reads; removes nothing. Raises OSError when `sandbox/` cannot be
    listed."""
    sids, notes = homes(state_dir)
    result = Plan(notes=notes)
    if sid is not None:
        if not is_sid(sid):
            result.kept.append((sid, "not a session id twine names a home by"))
            return result
        if sid not in sids:
            result.kept.append((sid, f"no sandbox home for it under {Path(state_dir) / SANDBOX_SUBDIR}"))
            return result
        sids = [sid]
    try:
        agent: str | RecordError = agent_dir(cwd)
    except RecordError as exc:
        agent = exc
    for name in sids:
        why = why_kept(state_dir, cwd, name, agent)
        if why is not None:
            result.kept.append((name, why))
            log.info("prune: keeping %s: %s", name, why)
        else:
            size = tree_bytes(Path(state_dir) / SANDBOX_SUBDIR / name)
            result.prune.append((name, size))
            log.info("prune: %s was applied; its home (%d bytes) may go", name, size)
    return result


# ---------------------------------------------------------------------------
# 3. Removal
# ---------------------------------------------------------------------------


def tree_bytes(path: Path) -> int:
    """The bytes under `path`: the sizes of its files and symlinks as they
    are (nothing followed, directories not counted). What cannot be listed is
    skipped and logged — the number is what could be seen."""
    total = 0
    stack = [path]
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        st = entry.stat(follow_symlinks=False)
                    except OSError as exc:
                        log.warning("prune: cannot size %s: %s", entry.path, exc)
                        continue
                    if stat.S_ISDIR(st.st_mode):
                        stack.append(Path(entry.path))
                    else:
                        total += st.st_size
        except OSError as exc:
            log.warning("prune: cannot list %s: %s", directory, exc)
    return total


def remove_tree(path: Path) -> None:
    """Remove the directory tree at `path`, never following a symlink. A
    directory the worker made unreadable or unwritable (a tool's read-only
    cache, say) is given back owner rwx before it is emptied. Raises OSError
    naming what could not go."""
    if path.is_symlink() or not path.is_dir():
        raise NotADirectoryError(f"{path} is not a directory")
    try:
        path.chmod(0o700)
    except OSError as exc:
        log.debug("prune: cannot chmod %s: %s", path, exc)
    with os.scandir(path) as entries:
        children = list(entries)
    for entry in children:
        if entry.is_dir(follow_symlinks=False):
            remove_tree(Path(entry.path))
        else:
            os.unlink(entry.path)
    os.rmdir(path)


def remove_home(state_dir: Path, sid: str) -> None:
    """Remove `<state-dir>/sandbox/<sid>/`, and only that: refused (ValueError)
    for a name that is not a sid or a path that is not directly under
    `sandbox/`."""
    if not is_sid(sid):
        raise ValueError(f"{sid!r} is not a session id twine names a home by")
    base = Path(state_dir) / SANDBOX_SUBDIR
    target = base / sid
    if target.is_symlink() or os.path.dirname(os.path.realpath(target)) \
            != os.path.realpath(base):
        raise ValueError(f"{target} is not a directory directly under {base}")
    remove_tree(target)
    log.info("prune: removed %s", target)

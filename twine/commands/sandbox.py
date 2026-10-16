"""`twine sandbox prune` — remove the homes of sessions bale records as applied
(twine-sandbox-confine; claude/context/cli-contract.md §22):

    twine sandbox prune [--sid SID] [--dry-run] [--state-dir DIR] [--cwd DIR] [--json]

`twine run` keeps a session's sandbox home when it delivers — the response
tarball lives there until the operator applies it — and twine never sees the
apply, so what removes a home is this verb, which asks bale's own record:
`<cwd>/<agent_dir>/telemetry/<sid>.json`, `attempts[].outcome` only
(twine/prune.py states the rule). Thin over twine.prune: it resolves the state
directory and `--cwd` as the kill verb does, takes the plan, removes what the
plan says (unless `--dry-run`) and reports every home either way — the
removed with their sizes, the kept each with why.

It runs nothing: no subprocess (`ctx.run` is never called), no bale (the record
is a file it reads), no network, no key; and it removes nothing outside
`<state-dir>/sandbox/<sid>/`.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from twine import prune, spend
from twine.cli import Context
from twine.commands.carry_bale import resolve_cwd
from twine.commands.kill import state_dir_fault
from twine.registry import Argument, Command, Result

log = logging.getLogger("twine.commands.sandbox")


def payload(*, dry_run: bool, state_dir: str | None, cwd: str | None, pruned: list[str],
            kept: list[dict[str, str]], freed_bytes: int, reason: str | None
            ) -> dict[str, Any]:
    """The twin after `command` and `ok`, in the contract's order (§22)."""
    return {"dry_run": dry_run, "state_dir": state_dir, "cwd": cwd, "pruned": pruned,
            "kept": kept, "freed_bytes": freed_bytes, "reason": reason}


def human_lines(twin: dict[str, Any], sizes: dict[str, int]) -> list[str]:
    """One line per pruned and per kept sid, then a total."""
    dry = twin["dry_run"]
    lines = []
    if twin["reason"] is not None:
        lines.append(f"sandbox prune: not ok — {twin['reason']}")
    for sid in twin["pruned"]:
        lines.append(f"{'would prune' if dry else 'pruned'} {sid}  ({sizes.get(sid, 0)} bytes)")
    for row in twin["kept"]:
        lines.append(f"kept {row['sid']}: {row['why']}")
    count = len(twin["pruned"])
    homes = f"{count} home{'' if count == 1 else 's'}"
    lines.append(f"{'dry run: would prune' if dry else 'pruned'} {homes}, "
                 f"{'freeing' if dry else 'freed'} {twin['freed_bytes']} bytes; "
                 f"{len(twin['kept'])} kept")
    return lines


def cmd_sandbox_prune(ctx: Context, args: argparse.Namespace) -> Result:
    refusals: list[str] = []
    state_dir: Path | None = None
    try:
        where = spend.resolve_state_dir(args.state_dir, ctx.env)
        fault = state_dir_fault(where.path)
        if fault is not None:
            refusals.append(f"the state directory {where.path} (from {where.source}) "
                            f"{fault}")
        else:
            state_dir = where.path
    except spend.SpendError as exc:
        refusals.append(exc.message)
    cwd = resolve_cwd(args.cwd, refusals)
    shown_state = None if state_dir is None else str(state_dir)
    if refusals or state_dir is None:
        reason = "; ".join(refusals)
        ctx.info(f"sandbox prune: {reason}; nothing was removed")
        twin = payload(dry_run=args.dry_run, state_dir=shown_state, cwd=cwd, pruned=[],
                       kept=[], freed_bytes=0, reason=reason)
        return Result(False, twin, human_lines(twin, {}))
    try:
        decided = prune.plan(state_dir, Path(cwd), sid=args.sid)
    except OSError as exc:
        reason = (f"the sandbox directory under {state_dir} cannot be listed: "
                  f"{exc.strerror or exc}")
        ctx.info(f"sandbox prune: {reason}")
        twin = payload(dry_run=args.dry_run, state_dir=shown_state, cwd=cwd, pruned=[],
                       kept=[], freed_bytes=0, reason=reason)
        return Result(False, twin, human_lines(twin, {}))
    for note in decided.notes:
        ctx.info(f"sandbox prune: ignoring {note}")
    pruned: list[tuple[str, int]] = []
    kept = list(decided.kept)
    failures: list[str] = []
    for sid, size in decided.prune:
        if args.dry_run:
            ctx.info(f"sandbox prune: would remove the home of {sid} ({size} bytes)")
            pruned.append((sid, size))
            continue
        try:
            prune.remove_home(state_dir, sid)
        except (OSError, ValueError) as exc:
            problem = f"could not remove {sid}: {getattr(exc, 'strerror', None) or exc}"
            ctx.info(f"sandbox prune: {problem}")
            failures.append(problem)
            kept.append((sid, f"removal failed: {getattr(exc, 'strerror', None) or exc}"))
            continue
        ctx.info(f"sandbox prune: removed the home of {sid} ({size} bytes)")
        pruned.append((sid, size))
    kept.sort()
    twin = payload(dry_run=args.dry_run, state_dir=shown_state, cwd=cwd,
                   pruned=sorted(sid for sid, _ in pruned),
                   kept=[{"sid": sid, "why": why} for sid, why in kept],
                   freed_bytes=sum(size for _, size in pruned),
                   reason="; ".join(failures) if failures else None)
    return Result(not failures, twin, human_lines(twin, dict(pruned)))


COMMANDS = (
    Command(
        name="sandbox prune",
        summary="remove the sandbox homes of sessions bale records as applied",
        handler=cmd_sandbox_prune,
        arguments=(
            Argument(("--sid",), {
                "metavar": "SID", "default": None,
                "help": "only this session's home"}),
            Argument(("--dry-run",), {
                "action": "store_true",
                "help": "remove nothing; say what would go"}),
            Argument(("--state-dir",), {
                "metavar": "DIR", "default": None,
                "help": "twine's state directory, holding sandbox/ (it must exist); "
                        "else $TWINE_STATE_DIR, else "
                        "${XDG_STATE_HOME:-$HOME/.local/state}/twine"}),
            Argument(("--cwd",), {
                "metavar": "DIR", "default": None,
                "help": "the repository the sessions were opened in, whose bale record "
                        "is read (default: the current directory)"}),
        ),
        description="Remove <state-dir>/sandbox/<sid>/ for each kept home whose session "
                    "bale records as applied: read from "
                    "<cwd>/<agent_dir>/telemetry/<sid>.json (agent_dir from the "
                    "repository's bale.toml [layout], `claude` when unset) only "
                    "attempts[].outcome — applied exactly when, of the attempts whose "
                    "outcome is applied, re-applied, rolled-back or reverted, the last is "
                    "applied or re-applied. Every other home is kept, each with why "
                    "(no bale record; not applied; the record cannot be read; in flight; "
                    "running). A home whose session has an in-flight record or a running "
                    "record is never removed, nor anything outside "
                    "<state-dir>/sandbox/. --dry-run removes nothing and says what would "
                    "go. ok unless the state directory or --cwd cannot be read or a "
                    "removal failed."),
)

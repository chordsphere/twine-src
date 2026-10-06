"""The core verbs: `commands`, `status`, and `bale check`.

These are twine's own facts — what verbs exist, whether twine itself is
intact, whether the bale install matches the pin, and (session 5c) where
twine's state directory resolves and what of it exists. No bale repo
state is read here (that is Arc 1 session 3's), and nothing here writes:
`status` never creates the state directory it reports.
"""

from __future__ import annotations

import argparse
import os
import platform
from typing import Any

from twine import CONSUMPTION_MANIFEST, FIXTURES_DIR, REPO_ROOT, __version__, spend
from twine.bale import ManifestError, check, load_manifest, resolve_root
from twine.cli import Context
from twine.kill import ABORT_SUBDIR, RUNNING_SUBDIR
from twine.registry import Argument, Command, Result, load_registry


def cmd_commands(ctx: Context, args: argparse.Namespace) -> Result:
    """List every registered verb — rendered from the registry, so the
    listing can never omit a verb the parser accepts."""
    rows = [cmd.listing() for cmd in load_registry().values()]
    width = max(len(r["name"]) for r in rows)
    lines = [f"{r['name']:<{width}}  {r['summary']}"
             + ("" if r["json"] else "  [cli-only]") for r in rows]
    return Result(True, {"commands": rows}, lines)


def _bale_root_argument() -> Argument:
    return Argument(("--bale-root",), {
        "metavar": "DIR", "default": None,
        "help": "the bale install root (the directory holding bin/); else "
                "$TWINE_BALE_ROOT, else `command -v bale` followed to its "
                "real path"})


def _state_dir_argument() -> Argument:
    """The same argument the spend verbs and `kill` take, so an operator can
    ask what a given flag resolves to."""
    return Argument(("--state-dir",), {
        "metavar": "DIR", "default": None,
        "help": "twine's state directory to report on (never created); else "
                "$TWINE_STATE_DIR, else ${XDG_STATE_HOME:-$HOME/.local/state}/twine"})


def cmd_bale_check(ctx: Context, args: argparse.Namespace) -> Result:
    """Compare the installed bin/VERSION to the consumption manifest's
    pin (D2). A missing install, an unreadable VERSION, or a different
    version is a not-ok result (exit 1), never a traceback."""
    manifest = load_manifest(CONSUMPTION_MANIFEST)
    root = resolve_root(args.bale_root, ctx.env, ctx.which)
    result = check(manifest, root)
    return Result(result.ok, result.as_json(), result.as_lines())


def state_dir_facts(flag: str | None, env: dict[str, str]) -> dict[str, Any]:
    """Where twine's state lives and what of it exists (session 5c; the
    keys of cli-contract.md §4): `state_dir` and `state_dir_source` as
    spend.resolve_state_dir resolves them (§13.2), `state_dir_reason` the
    refusal text when none resolves (a null `state_dir` is never silent),
    `state_dir_exists`, and `state_present` — whether `spend.jsonl` and
    `prices.toml` exist as files and `abort/` and `running/` as directories,
    all false when the directory itself does not. Nothing is created: an
    operator whose `twine kill` was refused for a missing directory learns
    here which one twine resolves, and makes it (or names the runtime's)
    themselves. A state directory that does not resolve or exist is a fact
    about the machine, not a fault in twine."""
    try:
        where = spend.resolve_state_dir(flag, env)
    except spend.SpendError as exc:
        return {"state_dir": None, "state_dir_source": None,
                "state_dir_reason": exc.message, "state_dir_exists": None,
                "state_present": None}
    # os.path's tests never raise: a path that cannot be stat'd (a parent
    # without search permission, say) reads as absent, which is a fact
    # about the machine too, not an internal error.
    exists = os.path.isdir(where.path)
    present = {"spend_jsonl": os.path.isfile(where.stream),
               "prices_toml": os.path.isfile(where.prices),
               "abort": os.path.isdir(where.path / ABORT_SUBDIR),
               "running": os.path.isdir(where.path / RUNNING_SUBDIR)}
    if not exists:
        present = {key: False for key in present}
    return {"state_dir": str(where.path), "state_dir_source": where.source,
            "state_dir_reason": None, "state_dir_exists": exists,
            "state_present": present}


def state_dir_lines(facts: dict[str, Any]) -> list[str]:
    """The human rendering of state_dir_facts: one line for the directory,
    one for what is in it."""
    if facts["state_dir"] is None:
        return [f"state dir:            none resolves — {facts['state_dir_reason']}"]
    head = f"state dir:            {facts['state_dir']}  (from {facts['state_dir_source']})"
    if not facts["state_dir_exists"]:
        return [head + "  (does not exist)"]
    names = {"spend_jsonl": "spend.jsonl", "prices_toml": "prices.toml",
             "abort": "abort/", "running": "running/"}
    there = [names[k] for k, yes in facts["state_present"].items() if yes]
    missing = [names[k] for k, yes in facts["state_present"].items() if not yes]
    return [head,
            "state present:        " + (", ".join(there) if there else "nothing of twine's")
            + (f"  (missing: {', '.join(missing)})" if missing and there else "")]


def cmd_status(ctx: Context, args: argparse.Namespace) -> Result:
    """Twine's own facts: version, python, the bale check, where the
    consumption manifest and fixtures live, and where its state directory
    resolves and what of it exists. ok is about twine itself — the
    manifest parses and its pin resolves — regardless of whether a bale
    install is present or a state directory resolves or exists; the bale
    result and the state facts ride inside."""
    payload: dict = {
        "version": __version__,
        "python": platform.python_version(),
        "repo_root": str(REPO_ROOT),
        "consumption_manifest": str(CONSUMPTION_MANIFEST),
        "fixtures": str(FIXTURES_DIR),
        "fixtures_present": FIXTURES_DIR.is_dir(),
    }
    state = state_dir_facts(getattr(args, "state_dir", None), ctx.env)
    payload.update(state)
    lines = [f"twine {__version__}",
             f"python {payload['python']}",
             f"repo root:            {REPO_ROOT}",
             f"consumption manifest: {CONSUMPTION_MANIFEST}",
             f"fixtures:             {FIXTURES_DIR}"
             + ("" if payload["fixtures_present"] else "  (missing)"),
             *state_dir_lines(state)]
    try:
        manifest = load_manifest(CONSUMPTION_MANIFEST)
    except ManifestError as exc:
        payload.update({"ok_reason": f"consumption manifest unusable: {exc}",
                        "pin": None, "bale": None})
        lines.append(f"manifest:             UNUSABLE — {exc}")
        return Result(False, payload, lines)
    payload["pin"] = manifest.pin
    root = resolve_root(getattr(args, "bale_root", None), ctx.env, ctx.which)
    result = check(manifest, root)
    payload["bale"] = result.as_json()
    payload["ok_reason"] = "manifest parses and the pin resolves"
    lines.append(f"pin:                  {manifest.pin}")
    lines.append("bale check:           " + ("ok" if result.ok else "not ok")
                 + f" — {result.reason}")
    return Result(True, payload, lines)


COMMANDS = (
    Command(
        name="commands",
        summary="list every registered verb (the registry, rendered)",
        handler=cmd_commands,
        description="List every verb the registry holds: name, summary, "
                    "whether it has a --json twin. A CLI-only verb is "
                    "listed with cli_only true, never omitted."),
    Command(
        name="status",
        summary="twine's own facts: version, python, the bale pin check, "
                "where its manifest, fixtures and state directory live",
        handler=cmd_status,
        arguments=(_bale_root_argument(), _state_dir_argument()),
        description="Report twine's own state. ok is true when twine "
                    "itself is intact (its consumption manifest parses "
                    "and its pin resolves), whether or not a bale "
                    "install is present; the bale check result rides "
                    "inside, and so do the state directory twine resolves "
                    "(--state-dir, else $TWINE_STATE_DIR, else XDG, else "
                    "$HOME; null, with the reason, when none does), whether "
                    "it exists, and whether spend.jsonl, prices.toml, abort/ "
                    "and running/ are in it. Nothing is created."),
    Command(
        name="bale check",
        summary="compare the installed bale's bin/VERSION to the pin in "
                "share/bale-consumption.toml",
        handler=cmd_bale_check,
        arguments=(_bale_root_argument(),),
        description="Resolve the bale install root (--bale-root, else "
                    "$TWINE_BALE_ROOT, else `command -v bale`), read "
                    "<root>/bin/VERSION, and compare it to the pin. "
                    "Exit 0 when they match; 1 when they differ, the "
                    "file is unreadable, or no install was found."),
)

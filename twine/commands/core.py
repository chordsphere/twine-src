"""The core verbs: `commands`, `status`, and `bale check`.

These are twine's own facts — what verbs exist, whether twine itself is
intact, and whether the bale install matches the pin. No bale repo
state is read here (that is Arc 1 session 3's).
"""

from __future__ import annotations

import argparse
import platform

from twine import CONSUMPTION_MANIFEST, FIXTURES_DIR, REPO_ROOT, __version__
from twine.bale import ManifestError, check, load_manifest, resolve_root
from twine.cli import Context
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


def cmd_bale_check(ctx: Context, args: argparse.Namespace) -> Result:
    """Compare the installed bin/VERSION to the consumption manifest's
    pin (D2). A missing install, an unreadable VERSION, or a different
    version is a not-ok result (exit 1), never a traceback."""
    manifest = load_manifest(CONSUMPTION_MANIFEST)
    root = resolve_root(args.bale_root, ctx.env, ctx.which)
    result = check(manifest, root)
    return Result(result.ok, result.as_json(), result.as_lines())


def cmd_status(ctx: Context, args: argparse.Namespace) -> Result:
    """Twine's own facts: version, python, the bale check, and where the
    consumption manifest and fixtures live. ok is about twine itself —
    the manifest parses and its pin resolves — regardless of whether a
    bale install is present; the bale result rides inside."""
    payload: dict = {
        "version": __version__,
        "python": platform.python_version(),
        "repo_root": str(REPO_ROOT),
        "consumption_manifest": str(CONSUMPTION_MANIFEST),
        "fixtures": str(FIXTURES_DIR),
        "fixtures_present": FIXTURES_DIR.is_dir(),
    }
    lines = [f"twine {__version__}",
             f"python {payload['python']}",
             f"repo root:            {REPO_ROOT}",
             f"consumption manifest: {CONSUMPTION_MANIFEST}",
             f"fixtures:             {FIXTURES_DIR}"
             + ("" if payload["fixtures_present"] else "  (missing)")]
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
                "where its manifest and fixtures live",
        handler=cmd_status,
        arguments=(_bale_root_argument(),),
        description="Report twine's own state. ok is true when twine "
                    "itself is intact (its consumption manifest parses "
                    "and its pin resolves), whether or not a bale "
                    "install is present; the bale check result rides "
                    "inside."),
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

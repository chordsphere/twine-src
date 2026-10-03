"""`twine transitions [--table PATH] [--json]` — render the transition
table (D17; Arc 1 session 4) and say whether it is total.

The table is `share/transitions.toml` (twine/transitions.py loads and
checks it). Its three bale axes take their keys from the consumption
manifest's `[[vocabulary]]` entries — twine's own record of bale's
spellings — so this verb reads two of twine's files and nothing else: no
bale install, no subprocess (it never touches `ctx.run`), no network. Its
`ok` is the table's alone: true exactly when every key of every axis has
one row and every row's move is declared; otherwise exit 1 with each
offending axis and key, or move, named.

`--table PATH` checks another table file against the same vocabularies —
a draft, or a table a test edited — and is the only input the verb takes.
The contract is claude/context/cli-contract.md §12.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from twine import TRANSITIONS_TABLE
from twine import transitions
from twine.bale import ManifestError, load_manifest
from twine.cli import Context
from twine.registry import Argument, Command, Result


def cmd_transitions(ctx: Context, args: argparse.Namespace) -> Result:
    """Load the vocabularies and the table, check the table is total,
    render it. A bad table or an unusable manifest is a not-ok result
    naming why, never a traceback."""
    path = Path(args.table).expanduser() if args.table else TRANSITIONS_TABLE
    manifest, manifest_error = None, None
    try:
        manifest = load_manifest()
    except ManifestError as exc:
        manifest_error = f"the consumption manifest is unusable: {exc}"
        ctx.info(manifest_error)
    table = transitions.load_table(path, manifest, manifest_error)
    payload = transitions.as_json(table)
    for problem in table.problems:
        ctx.info(f"{problem.kind}: {problem.message}")
    if payload["unused_moves"]:
        ctx.info("declared moves no row names: " + ", ".join(payload["unused_moves"]))
    if table.ok:
        ctx.info(f"transition table total: {payload['counts']['rows']} rows over "
                 f"{payload['counts']['axes']} axes, every move declared")
    return Result(table.ok, payload, transitions.as_lines(table))


COMMANDS = (
    Command(
        name="transitions",
        summary="render the transition table (D17): every bale outcome, closure "
                "reason and stop, each with its move; ok when it is total",
        handler=cmd_transitions,
        arguments=(
            Argument(("--table",), {
                "metavar": "PATH", "default": None,
                "help": "check this table file instead of share/transitions.toml "
                        "(against the same vocabularies)"}),
        ),
        description="Render share/transitions.toml: four axes — bale's telemetry "
                    "outcomes, closure reasons and `bale apply --json` outcomes "
                    "(the consumption manifest's [[vocabulary]] entries, bale's "
                    "spellings at the pin) and twine's own stop set — one row per "
                    "key, each naming a declared move and who performs it. ok when "
                    "every key of every axis has one row and every row's move is "
                    "declared; otherwise exit 1, naming each axis and key or move "
                    "at fault. Reads no bale install and runs nothing."),
)

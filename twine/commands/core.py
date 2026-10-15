"""The core verbs: `commands`, `status`, and `bale check`.

These are twine's own facts — what verbs exist, whether twine itself is
intact, whether the gate admits the bale install (since session
2026-10-15-twine-gate-contract-001 the floor plus bale's contract, `bale
contract --json` run through ctx.run; a floor plus schema hashes from
session 2026-10-12-twine-pin-floor-002, an exact pin before), and (session 5c) where
twine's state directory resolves and what of it exists — since session
`twine-status-inflight` (0.11.0) including the in-flight records `carry
bundle` keeps there, read through `twine.inflight.list_inflight` — and since
Arc 2 R4 the transcripts and sandbox homes `twine run` keeps there (counts and
sids, as the in-flight records are listed). No bale
repo state is read here (that is Arc 1 session 3's) — the one bale verb
run here is the install's `contract --json`, which reads none — and nothing
here writes: `status` never creates the state directory it reports, nor
anything in it.
"""

from __future__ import annotations

import argparse
import os
import platform
from typing import Any

from twine import CONSUMPTION_MANIFEST, FIXTURES_DIR, REPO_ROOT, __version__, spend
from twine.bale import ManifestError, check, load_manifest, resolve_root
from twine.cli import Context
from twine.inflight import INFLIGHT_SUBDIR, list_inflight
from twine.kill import ABORT_SUBDIR, RUNNING_SUBDIR, is_sid
from twine.runtime.sandbox import HOME_NAME, SANDBOX_SUBDIR
from twine.transcript import TRANSCRIPTS_SUBDIR, list_transcripts
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
    """The gate (D2; since session 2026-10-15-twine-gate-contract-001): the
    installed bin/VERSION at or above the consumption manifest's floor, and
    the install's `bale contract --json`, run through ctx.run, stating
    everything twine reads. A missing install, an unreadable or unparsable
    VERSION, a version below the floor, or a contract that cannot be read,
    is not this install's, or lacks something twine reads is a not-ok
    result (exit 1) naming every failing fact at once, never a traceback."""
    manifest = load_manifest(CONSUMPTION_MANIFEST)
    root = resolve_root(args.bale_root, ctx.env, ctx.which)
    result = check(manifest, root, ctx.run, ctx.env)
    return Result(result.ok, result.as_json(), result.as_lines())


def state_dir_facts(flag: str | None, env: dict[str, str]) -> dict[str, Any]:
    """Where twine's state lives and what of it exists (session 5c; the
    keys of cli-contract.md §4): `state_dir` and `state_dir_source` as
    spend.resolve_state_dir resolves them (§13.2), `state_dir_reason` the
    refusal text when none resolves (a null `state_dir` is never silent),
    `state_dir_exists`, and `state_present` — whether `spend.jsonl` and
    `prices.toml` exist as files and `abort/`, `running/` and `inflight/` as
    directories, all false when the directory itself does not. Then the
    in-flight records (session `twine-status-inflight`): `inflight_sids`,
    the sids whose records read, sorted, and `inflight_faults`, one sentence
    per entry in `inflight/` that is not a record, naming it — both `[]`
    when there is no `inflight/`, both null when no directory resolves.
    Nothing is created: an operator whose `twine kill` was refused for a
    missing directory learns here which one twine resolves, and makes it
    (or names the runtime's) themselves. A state directory that does not
    resolve or exist, or an `inflight/` holding junk, is a fact about the
    machine, not a fault in twine."""
    try:
        where = spend.resolve_state_dir(flag, env)
    except spend.SpendError as exc:
        return {"state_dir": None, "state_dir_source": None,
                "state_dir_reason": exc.message, "state_dir_exists": None,
                "state_present": None, "inflight_sids": None, "inflight_faults": None,
                "transcript_sids": None, "transcript_faults": None,
                "sandbox_sids": None, "sandbox_faults": None}
    # os.path's tests never raise: a path that cannot be stat'd (a parent
    # without search permission, say) reads as absent, which is a fact
    # about the machine too, not an internal error.
    exists = os.path.isdir(where.path)
    present = {"spend_jsonl": os.path.isfile(where.stream),
               "prices_toml": os.path.isfile(where.prices),
               "abort": os.path.isdir(where.path / ABORT_SUBDIR),
               "running": os.path.isdir(where.path / RUNNING_SUBDIR),
               "inflight": os.path.isdir(where.path / INFLIGHT_SUBDIR),
               "transcripts": os.path.isdir(where.path / TRANSCRIPTS_SUBDIR),
               "sandbox": os.path.isdir(where.path / SANDBOX_SUBDIR)}
    if not exists:
        present = {key: False for key in present}
    # Listed only when the directory is there to list; list_inflight reads
    # an absent `inflight/` as no records and no faults all the same.
    listing = list_inflight(where.path) if present["inflight"] else None
    transcripts = (list_transcripts(where.path) if present["transcripts"] else ((), ()))
    sandboxes = list_sandboxes(where.path) if present["sandbox"] else ((), ())
    return {"state_dir": str(where.path), "state_dir_source": where.source,
            "state_dir_reason": None, "state_dir_exists": exists,
            "state_present": present,
            "inflight_sids": list(listing.sids) if listing is not None else [],
            "inflight_faults": list(listing.faults) if listing is not None else [],
            "transcript_sids": list(transcripts[0]),
            "transcript_faults": list(transcripts[1]),
            "sandbox_sids": list(sandboxes[0]),
            "sandbox_faults": list(sandboxes[1])}


def list_sandboxes(state_dir) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(sids, faults) for `<state-dir>/sandbox/` (Arc 2 R4): the sids whose
    `<sid>/home/` is a directory — a sandbox home `twine run` made and keeps —
    sorted, and one sentence per other entry. Reads names only; writes
    nothing."""
    directory = os.path.join(state_dir, SANDBOX_SUBDIR)
    try:
        names = sorted(os.listdir(directory))
    except OSError as exc:
        return (), (f"{SANDBOX_SUBDIR}/ cannot be listed: {exc.strerror or exc}",)
    sids, faults = [], []
    for name in names:
        shown = name if name.isprintable() else repr(name)
        if is_sid(name) and os.path.isdir(os.path.join(directory, name, HOME_NAME)):
            sids.append(name)
        else:
            faults.append(f"{shown} is not a sandbox: its name is not a sid twine "
                          f"accepts, or it holds no {HOME_NAME}/")
    return tuple(sids), tuple(faults)


def state_dir_lines(facts: dict[str, Any]) -> list[str]:
    """The human rendering of state_dir_facts: one line for the directory,
    one for what is in it, then one per in-flight record (its sid) and one
    per entry in `inflight/` that is not a record (its fault)."""
    if facts["state_dir"] is None:
        return [f"state dir:            none resolves — {facts['state_dir_reason']}"]
    head = f"state dir:            {facts['state_dir']}  (from {facts['state_dir_source']})"
    if not facts["state_dir_exists"]:
        return [head + "  (does not exist)"]
    names = {"spend_jsonl": "spend.jsonl", "prices_toml": "prices.toml",
             "abort": "abort/", "running": "running/", "inflight": "inflight/",
             "transcripts": "transcripts/", "sandbox": "sandbox/"}
    there = [names[k] for k, yes in facts["state_present"].items() if yes]
    missing = [names[k] for k, yes in facts["state_present"].items() if not yes]
    return [head,
            "state present:        " + (", ".join(there) if there else "nothing of twine's")
            + (f"  (missing: {', '.join(missing)})" if missing and there else ""),
            *(f"in-flight record:     {sid}" for sid in facts["inflight_sids"]),
            *(f"in-flight fault:      {fault}" for fault in facts["inflight_faults"]),
            *_listed("transcripts:", "transcript fault:", facts["transcript_sids"],
                     facts["transcript_faults"]),
            *_listed("sandbox homes:", "sandbox fault:", facts["sandbox_sids"],
                     facts["sandbox_faults"])]


def _listed(label: str, fault_label: str, sids: list[str], faults: list[str]) -> list[str]:
    """One line with the count and the sids, then one per fault; nothing
    when there is neither (Arc 2 R4)."""
    out = []
    if sids:
        out.append(f"{label:<22}{len(sids)} — {', '.join(sids)}")
    out.extend(f"{fault_label:<22}{fault}" for fault in faults)
    return out


def cmd_status(ctx: Context, args: argparse.Namespace) -> Result:
    """Twine's own facts: version, python, the bale check, where the
    consumption manifest and fixtures live, and where its state directory
    resolves and what of it exists. ok is about twine itself — the
    manifest parses and its floor resolves — regardless of whether a bale
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
                        "floor": None, "bale": None})
        lines.append(f"manifest:             UNUSABLE — {exc}")
        return Result(False, payload, lines)
    payload["floor"] = manifest.floor
    root = resolve_root(getattr(args, "bale_root", None), ctx.env, ctx.which)
    result = check(manifest, root, ctx.run, ctx.env)
    payload["bale"] = result.as_json()
    payload["ok_reason"] = "manifest parses and the floor resolves"
    lines.append(f"floor:                {manifest.floor}")
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
        summary="twine's own facts: version, python, the bale check, "
                "where its manifest, fixtures and state directory live",
        handler=cmd_status,
        arguments=(_bale_root_argument(), _state_dir_argument()),
        description="Report twine's own state. ok is true when twine "
                    "itself is intact (its consumption manifest parses "
                    "and its floor resolves), whether or not a bale "
                    "install is present; the bale check result rides "
                    "inside, and so do the state directory twine resolves "
                    "(--state-dir, else $TWINE_STATE_DIR, else XDG, else "
                    "$HOME; null, with the reason, when none does), whether "
                    "it exists, whether spend.jsonl, prices.toml, abort/, "
                    "running/, inflight/, transcripts/ and sandbox/ are in "
                    "it, the sids whose in-flight records read, and every "
                    "file in inflight/ that is not a record, named, and the "
                    "sids of the transcripts and sandbox homes `twine run` "
                    "keeps. Nothing is created or written."),
    Command(
        name="bale check",
        summary="check the installed bale against the floor in "
                "share/bale-consumption.toml and its contract against what "
                "twine reads",
        handler=cmd_bale_check,
        arguments=(_bale_root_argument(),),
        description="Resolve the bale install root (--bale-root, else "
                    "$TWINE_BALE_ROOT, else `command -v bale`), read "
                    "<root>/bin/VERSION and compare it, as three dotted "
                    "integers, to the floor; run <root>/bin/bale contract "
                    "--json and hold its one line to what twine reads: the "
                    "transition table's three vocabularies (the same values), "
                    "the keys of each line twine reads, and every outcome and "
                    "the one unlock reason twine dispatches on. No file under "
                    "<root>/schemas/ is read. Exit 0 when the version is at or "
                    "above the floor and the contract states all of it (a value "
                    "bale added that twine does not dispatch on is reported, "
                    "not refused); 1 otherwise — below the floor, an "
                    "unreadable or unparsable VERSION, a contract that cannot "
                    "be read or names another version, something twine reads "
                    "moved, or no install found — each failing fact named."),
)

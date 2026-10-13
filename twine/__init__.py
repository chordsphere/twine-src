"""twine — the process layer of the Nisaba suite (twine-seed.md §1).

One core, one command registry, one CLI, a JSON twin for every command,
and the shell as the only renderer (T4). This package is the core; the
`twine` script under bin/ is its entrypoint.

Modules:
  registry  the command registry — the single source for the verbs
            (argparse wiring, --help, and `twine commands` all render
            from it); discovers each module under twine/commands/
  cli       the parser built from the registry, dispatch, and the
            --json discipline (one JSON line on stdout, exit 0/1/2)
  bale      the bale surface twine reads: install-root resolution,
            bin/VERSION, the consumption manifest, the gate (D2, D4: the
            floor and the schema hashes) and the key check on bale's lines
  shapes    the bale shapes in text: find, parse and verify every block a
            courier carries (probe, probe-output, light, exchange, relay);
            pure, executes nothing — `twine take` is the verb over it
  process   the run seam: the one way a handler runs a subprocess
            (Context.run) — a process group, a timeout that reaches its
            children, a stdout cap, a spawn hook that hands the child's
            group to the kill-switch's record; tests inject a double. Since
            Arc 2 R3 also the one place the runtime's sandbox reads PATH
            and LANG from the process environment, by name
            (inherited_environment)
  transitions  the transition table (D17): share/transitions.toml loaded
            and checked total — every key of every axis one row, every
            row's move declared — with the stop axis's loop keys and, since
            Arc 2 R2, each provider's words mapped onto the stop axis
            ([[mapping]], read by provider_mapping); pure, reads no bale
            install
  spend     the cost spine (D15, session 5a): the usage record and its
            append-only stream (<state-dir>/spend.jsonl), the operator's
            prices (twine ships none), the running totals and the hard
            cap's pre-call check — one function per face, called by the
            `spend` verbs and, later, the Arc 2 loop; pure, no network
  kill      the kill-switch (D15, sessions 5b and 5c): the between-calls
            abort (<state-dir>/abort/<sid>.json), the running record — the
            runtime's group and every group it registered — and the
            process-level kill of all of them, and the `aborted` closure
            (`bale unlock <sid> --reason aborted --json`, through the seam,
            the one step the pin gates) — called by `twine kill` and,
            later, the Arc 2 loop; spawns nothing itself
  inflight  the in-flight record (Arc 1 session 3): <state-dir>/inflight/
            <sid>.json, a cache of the opens `carry bundle` carried into
            bale — written by that verb (record_open), listed by `twine
            status` (list_inflight); nothing in Arc 1 removes one
  runtime   the runtime (T4, §4; Arc 2), a package: since R1 the
            capability registry — the declaration capabilities.toml, one
            module per capability under capabilities/ (each a CONTRACT),
            parity by name — the adapter boundary (boundary.py: the
            Adapter interface, the Turn, the stop set read from the
            transition table's `stop` axis, the loop's keys refused), the
            registered adapters under adapters/ — `fake`, the scripted
            transport the tests drive, and since R2 `anthropic`, the
            Messages API — and from_anthropic (usage.py), the first
            provider usage mapping; rendered by `twine runtime list` and
            `show`. One module reaches a network: runtime/transport.py, the
            real transport the Anthropic adapter is handed when the tests
            do not hand it theirs; the adapter reads its key from the
            environment mapping it is given. Since R3 the canonical tools —
            tools.toml declaring the seven, one module each under tools/,
            run by tooling.run_tool (a tool error is a result, never an
            exception), rendered by `twine runtime tools` — and the per-sid
            sandbox they run in (sandbox.py: a home under the state
            directory, paths confined, a minimal environment without the
            key, network off through `unshare` where available, `confines`
            declared by its runner, every spawn registered with the
            kill-switch's running record), which implements `sandboxing`
            itself (the declaration's `implemented_by`)
  commands  the verb modules, each exposing COMMANDS (a family may span
            modules: the `carry` verbs live in carry.py, carry_bale.py
            and carry_bundle.py)

Stdlib only (T9) — the `anthropic` SDK included: no module imports it.
Nothing here imports from bale's bin/, office's lib/
or tedder-src (T10); the `bale` executable is driven only through its
non-interactive paths, and this package reads files it leaves on disk.
"""

from __future__ import annotations

import logging
from pathlib import Path

# The repository root, located from this file — never from the working
# directory. bin/twine and the tests both rely on this being stable.
REPO_ROOT = Path(__file__).resolve().parent.parent

VERSION_FILE = REPO_ROOT / "VERSION"
CONSUMPTION_MANIFEST = REPO_ROOT / "share" / "bale-consumption.toml"
TRANSITIONS_TABLE = REPO_ROOT / "share" / "transitions.toml"
FIXTURES_DIR = REPO_ROOT / "fixtures"

log = logging.getLogger("twine")


def read_version(path: Path = VERSION_FILE) -> str:
    """The version string from the repo-root VERSION file, stripped.

    One line, no prefix; `twine --version` prints it as `twine <version>`.
    A missing or empty file is an error, never a silent default — a
    twine that cannot say its version is not intact.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot read {path}: {exc}") from exc
    version = text.strip()
    if not version or "\n" in version:
        raise RuntimeError(f"{path} must hold exactly one non-empty line")
    return version


__version__ = read_version()

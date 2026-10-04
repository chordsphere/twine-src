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
            bin/VERSION, the consumption manifest, the pin check (D2, D4)
  shapes    the bale shapes in text: find, parse and verify every block a
            courier carries (probe, probe-output, light, exchange, relay);
            pure, executes nothing — `twine take` is the verb over it
  process   the run seam: the one way a handler runs a subprocess
            (Context.run) — a process group, a timeout that reaches its
            children, a stdout cap; tests inject a double
  transitions  the transition table (D17): share/transitions.toml loaded
            and checked total — every key of every axis one row, every
            row's move declared; pure, reads no bale install
  spend     the cost spine (D15, session 5a): the usage record and its
            append-only stream (<state-dir>/spend.jsonl), the operator's
            prices (twine ships none), the running totals and the hard
            cap's pre-call check — one function per face, called by the
            `spend` verbs and, later, the Arc 2 loop; pure, no network
  kill      the kill-switch (D15, session 5b): the between-calls abort
            (<state-dir>/abort/<sid>.json), the running record and the
            process-level kill of a session's recorded group, and the
            `aborted` closure (`bale unlock <sid> --reason aborted --json`,
            through the seam) — called by `twine kill` and, later, the Arc
            2 loop; spawns nothing itself
  commands  the verb modules, each exposing COMMANDS (a family may span
            modules: the `carry` verbs live in carry.py and carry_bale.py)

Stdlib only (T9). Nothing here imports from bale's bin/, office's lib/
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

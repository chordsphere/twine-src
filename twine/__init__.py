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
  commands  one module per verb family, each exposing COMMANDS

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

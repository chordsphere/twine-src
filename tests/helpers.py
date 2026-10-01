"""Shared test helpers: run the real entrypoint as a subprocess the way
the brief specifies (`python3 -I -S bin/twine …`, plus -B so no
bytecode lands), build temp bale roots, and run the CLI in-process with
injected streams and environment."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from twine import REPO_ROOT
from twine.cli import Context, main

TWINE = REPO_ROOT / "bin" / "twine"
PIN = "0.4.45"


@dataclass
class Run:
    code: int
    stdout: str
    stderr: str


def run_cli(*argv: str, cwd: Path | None = None,
            bale_root: Path | str | None = None,
            extra_env: dict[str, str] | None = None) -> Run:
    """Run bin/twine as a subprocess under `python3 -I -S -B`.

    TWINE_BALE_ROOT is always set — to `bale_root`, or to a directory
    that does not exist — so the resolution never falls through to a
    bale on the developer's PATH (the suite's no-install rule).
    """
    env = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8",
           "TWINE_BALE_ROOT": str(bale_root) if bale_root is not None
           else os.path.join(tempfile.gettempdir(), "twine-tests-no-bale-here")}
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(TWINE), *argv],
        cwd=str(cwd or REPO_ROOT), env=env, capture_output=True, text=True)
    return Run(proc.returncode, proc.stdout, proc.stderr)


def run_inprocess(*argv: str, env: dict[str, str] | None = None,
                  which=lambda name: None) -> Run:
    """Run cli.main in-process with captured streams. `env` defaults to
    an empty mapping and `which` to "nothing on PATH", so no test reaches
    the real environment unless it says so."""
    out, err = io.StringIO(), io.StringIO()
    ctx = Context(env=env if env is not None else {}, stdout=out, stderr=err,
                  which=which)
    code = main(list(argv), ctx=ctx)
    return Run(code, out.getvalue(), err.getvalue())


class TempRoots:
    """Three bale install roots under one temp dir: `ok` (bin/VERSION at
    the pin), `other` (another version), `absent` (no bin/VERSION)."""

    def __init__(self, pin: str = PIN, other: str = "0.4.46") -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="twine-roots-")
        base = Path(self._dir.name)
        self.ok = base / "ok"
        self.other = base / "other"
        self.absent = base / "absent"
        (self.ok / "bin").mkdir(parents=True)
        (self.other / "bin").mkdir(parents=True)
        self.absent.mkdir()
        (self.ok / "bin" / "VERSION").write_text(pin + "\n", encoding="utf-8")
        (self.other / "bin" / "VERSION").write_text(other + "\n", encoding="utf-8")
        self.other_version = other

    def cleanup(self) -> None:
        self._dir.cleanup()


def fixture_relpath(argv: list[str], cwd: str) -> str:
    """The fixtures/ path a recorded bale output lands at, from the argv
    after `bale` and where it ran — fixtures/README.md's naming rule:

      fixtures/bale-<pin>/<where>/<verb>_<flag[-value…]>[_…].<ext>

    `where` is `twine-src` for cwd "repo" and `anywhere` otherwise; each
    flag is joined to the values that follow it with `-`, the groups are
    joined with `_`; `.json` when --json is among the flags, else `.txt`.
    """
    where = "twine-src" if cwd == "repo" else "anywhere"
    groups: list[str] = []
    for token in argv:
        if token.startswith("-") or not groups:
            groups.append(token)
        else:
            groups[-1] += "-" + token
    ext = ".json" if "--json" in argv else ".txt"
    return f"fixtures/bale-{PIN}/{where}/{'_'.join(groups)}{ext}"

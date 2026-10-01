"""bin/twine under `python3 -I -S`: --version, --help, path-located
package; and the stdlib-only (T9) and no-bale-import (T10) proofs."""

from __future__ import annotations

import ast
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from twine import REPO_ROOT, __version__

from tests.helpers import TWINE, run_cli

SOURCE_DIRS = [REPO_ROOT / "twine", REPO_ROOT / "tests"]
FORBIDDEN_ROOTS = {"bale", "office", "tedder", "office_bale", "bale_report"}


def python_sources() -> list[Path]:
    files = [TWINE]
    for d in SOURCE_DIRS:
        files += sorted(d.rglob("*.py"))
    return files


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


class Entrypoint(unittest.TestCase):

    def test_version_is_exactly_one_line(self):
        run = run_cli("--version")
        self.assertEqual((run.code, run.stdout), (0, f"twine {__version__}\n"))

    def test_version_file_is_the_source(self):
        self.assertEqual((REPO_ROOT / "VERSION").read_text(encoding="utf-8"),
                         f"{__version__}\n")

    def test_help_exits_zero(self):
        run = run_cli("--help")
        self.assertEqual(run.code, 0)
        self.assertIn("usage: twine", run.stdout)

    def test_runs_from_another_cwd(self):
        """The package is located from bin/twine's own path, not cwd."""
        with tempfile.TemporaryDirectory() as d:
            run = run_cli("--version", cwd=Path(d))
        self.assertEqual((run.code, run.stdout), (0, f"twine {__version__}\n"))

    def test_shebang_and_exec_bit(self):
        first = TWINE.read_text(encoding="utf-8").split("\n", 1)[0]
        self.assertEqual(first, "#!/usr/bin/env python3")
        self.assertTrue(TWINE.stat().st_mode & stat.S_IXUSR, "bin/twine not executable")

    def test_no_bytecode_left_behind(self):
        """-I ignores PYTHONDONTWRITEBYTECODE; bin/twine sets
        sys.dont_write_bytecode itself so an -I -S run (without -B, as
        the brief invokes it) leaves no __pycache__ under twine/."""
        import subprocess
        env = {"PATH": os.environ.get("PATH", ""),
               "TWINE_BALE_ROOT": os.path.join(tempfile.gettempdir(), "no-bale")}
        subprocess.run([sys.executable, "-I", "-S", str(TWINE), "commands"],
                       cwd=str(REPO_ROOT), env=env, capture_output=True, check=True)
        caches = [p for p in (REPO_ROOT / "twine").rglob("__pycache__")]
        self.assertEqual(caches, [])


class StdlibOnly(unittest.TestCase):

    def test_every_import_is_stdlib_or_twine(self):
        """T9, mechanically: every top-level module imported by the
        entrypoint, the package and the suite is in the standard library
        or is twine/tests itself."""
        allowed = set(sys.stdlib_module_names) | {"twine", "tests"}
        for path in python_sources():
            with self.subTest(file=path.relative_to(REPO_ROOT).as_posix()):
                self.assertLessEqual(imported_roots(path), allowed)

    def test_nothing_imports_bale_office_or_tedder(self):
        """T10: the executables are driven, never imported."""
        for path in python_sources():
            with self.subTest(file=path.relative_to(REPO_ROOT).as_posix()):
                self.assertFalse(imported_roots(path) & FORBIDDEN_ROOTS)


if __name__ == "__main__":
    unittest.main()

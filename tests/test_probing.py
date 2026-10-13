"""twine/probing.py — the probe machinery's home (session
2026-10-13-twine-housekeeping-probe-008).

The helpers `twine carry probe` and the runtime's `probe` tool share left
twine/commands/carry.py so that nothing under twine/runtime/ imports a
command module or the CLI. `carry probe`'s own behaviour is held by
tests/test_carry.py and the tool's by tests/test_runtime_tools.py; this file
holds the move: the import edge, the names still resolving where older
code reads them, and `run_probe` running against a seam that is not a
`cli.Context`.

Sections:
  1. The import walk
  2. The move
  3. A seam that is not a Context
"""

from __future__ import annotations

import ast
import dataclasses
import io
import unittest
from pathlib import Path

from twine import REPO_ROOT, probing, shapes
from twine.cli import Context
from twine.commands import carry
from twine.process import RunResult

from tests.helpers import PROBE_SLUG, RecordingRunner, filled_probe

# ---------------------------------------------------------------------------
# 1. The import walk
# ---------------------------------------------------------------------------

RUNTIME_DIR = REPO_ROOT / "twine" / "runtime"
# The modules nothing under twine/runtime/ may import: the CLI, and any
# command module (twine.commands and everything under it).
FORBIDDEN_FOR_RUNTIME = ("twine.cli", "twine.commands")


def module_name(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imported_modules(source: str, module: str, is_package: bool = False) -> set[str]:
    """Every module a source text imports, as dotted names: `import a.b`
    gives `a.b`; `from a import b` gives `a` and `a.b` (b may be a module);
    a relative import is resolved against `module`. Imports inside functions
    and under `if TYPE_CHECKING` count — the walk is over the whole tree."""
    found: set[str] = set()
    package = module.split(".") if is_package else module.split(".")[:-1]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[:len(package) - node.level + 1]
                name = ".".join(base + ([node.module] if node.module else []))
            else:
                name = node.module or ""
            found.add(name)
            found.update(f"{name}.{alias.name}" for alias in node.names)
    return found


def reaches(imports: set[str], forbidden: tuple[str, ...]) -> list[str]:
    return sorted(m for m in imports
                  if any(m == f or m.startswith(f + ".") for f in forbidden))


class TheImportWalk(unittest.TestCase):

    def test_the_walk_sees_every_way_to_import_a_command_module_or_the_cli(self):
        """The walker itself, on text: absolute, from-import of a submodule,
        from-import of the package, and relative forms all show."""
        for source, expect in (
                ("from twine.cli import Context", "twine.cli"),
                ("import twine.cli", "twine.cli"),
                ("from twine import cli", "twine.cli"),
                ("from twine.commands import carry", "twine.commands.carry"),
                ("from twine.commands.carry import choose_block", "twine.commands.carry"),
                ("from ... import cli", "twine.cli"),
                ("from ...commands import carry", "twine.commands.carry"),
                ("def f():\n    from twine.commands import run\n", "twine.commands.run")):
            with self.subTest(source=source):
                found = reaches(imported_modules(source, "twine.runtime.tools.probe"),
                                FORBIDDEN_FOR_RUNTIME)
                self.assertIn(expect, found)
        self.assertEqual(reaches(imported_modules("from twine import shapes, probing",
                                                  "twine.runtime.tools.probe"),
                                 FORBIDDEN_FOR_RUNTIME), [])

    def test_nothing_under_the_runtime_imports_a_command_module_or_the_cli(self):
        """The edge the brief closes: no module under twine/runtime/ —
        probe.py was the one — imports twine.cli or any twine.commands
        module."""
        checked = 0
        for path in sorted(RUNTIME_DIR.rglob("*.py")):
            checked += 1
            with self.subTest(module=module_name(path)):
                found = reaches(imported_modules(path.read_text(encoding="utf-8"),
                                                 module_name(path),
                                                 is_package=path.name == "__init__.py"),
                                FORBIDDEN_FOR_RUNTIME)
                self.assertEqual(found, [])
        self.assertGreater(checked, 20)

    def test_probing_itself_imports_neither_and_nothing_that_runs_by_itself(self):
        """probing.py is the shared home, so it is under the same rule, and
        it spawns nothing of its own — the script runs through the seam it
        is handed."""
        path = REPO_ROOT / "twine" / "probing.py"
        imports = imported_modules(path.read_text(encoding="utf-8"), "twine.probing")
        self.assertEqual(reaches(imports, FORBIDDEN_FOR_RUNTIME), [])
        roots = {m.split(".")[0] for m in imports}
        self.assertFalse(roots & {"subprocess", "os", "shutil", "socket", "urllib", "http",
                                  "multiprocessing", "pty", "asyncio", "ctypes"})


# ---------------------------------------------------------------------------
# 2. The move
# ---------------------------------------------------------------------------


class TheMove(unittest.TestCase):

    def test_the_names_carry_and_its_neighbours_read_are_probings_objects(self):
        """carry.py imports the machinery back: the same objects answer at
        both names, so carry_bale.py's `from twine.commands.carry import
        choose_block` and the older tests' imports resolve unchanged."""
        for name in ("choose_block", "check_block_ready", "run_probe", "verify_output",
                     "Outcome", "CarryOutcome", "CARRIED_KINDS", "DEFAULT_TIMEOUT_SECONDS",
                     "STDOUT_CAP_BYTES", "BASH"):
            with self.subTest(name=name):
                self.assertIs(getattr(carry, name), getattr(probing, name))

    def test_the_functions_and_the_outcome_are_defined_in_probing_alone(self):
        wanted = {"choose_block", "check_block_ready", "run_probe", "verify_output",
                  "Outcome", "CarryOutcome"}

        def defined(rel: str) -> set[str]:
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
            return {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}

        self.assertFalse(defined("twine/commands/carry.py") & wanted)
        self.assertGreaterEqual(defined("twine/probing.py"), wanted)

    def test_a_context_has_every_member_of_the_seam_run_probe_reads(self):
        """cli.Context is a ProbeSeam without importing probing: it carries
        the four members the protocol names."""
        fields = {f.name for f in dataclasses.fields(Context)}
        self.assertLessEqual({"run", "which", "env"}, fields)
        self.assertTrue(callable(Context().info))


# ---------------------------------------------------------------------------
# 3. A seam that is not a Context
# ---------------------------------------------------------------------------


def ready_outcome(script: str) -> probing.Outcome:
    outcome = probing.Outcome(source="<test>", run_requested=True)
    outcome.cwd = "/tmp"
    report = shapes.find_blocks(shapes.normalize(f"```bash\n{script}```\n".encode()).text)
    probing.choose_block(report, None, outcome)
    return outcome


class RunProbeAgainstASeam(unittest.TestCase):

    def paste_back(self) -> bytes:
        body = "--- section: seam ---\nseam ok"
        return (f"=== PROBE BEGIN {PROBE_SLUG} ===\n{body}\n"
                f"--- integrity: {len(body.splitlines())} lines ---\n"
                f"=== PROBE END {PROBE_SLUG} ===\n").encode()

    def test_run_probe_takes_a_seam_and_collects_its_info_lines(self):
        """A `probing.Seam` — no streams, no stdin, no CLI — is enough: the
        script goes to bash through the seam's runner with the seam's
        environment, the verified block is the outcome's output, and the
        one informational line is collected, not written anywhere."""
        runner = RecordingRunner(RunResult(argv=("bash",), exit_code=0,
                                           stdout=self.paste_back(), stderr=b""))
        seam = probing.Seam(run=runner, which=lambda name: f"/usr/bin/{name}",
                            env={"PATH": "/usr/bin"})
        outcome = ready_outcome(filled_probe())
        probing.check_block_ready(outcome)
        self.assertEqual(outcome.refusals, [])
        probing.run_probe(seam, outcome)
        self.assertTrue(outcome.ok, outcome.reason)
        self.assertTrue(outcome.output.startswith(f"=== PROBE BEGIN {PROBE_SLUG} ===\n"))
        (call,) = runner.calls
        self.assertEqual(call["argv"][:2], ["/usr/bin/bash", "-c"])
        self.assertEqual(call["env"], {"PATH": "/usr/bin"})
        self.assertEqual((call["cwd"], call["stdin"], call["timeout"], call["stdout_cap"]),
                         ("/tmp", None, probing.DEFAULT_TIMEOUT_SECONDS,
                          probing.STDOUT_CAP_BYTES))
        (line,) = seam.lines
        self.assertIn(f"running probe {PROBE_SLUG} with /usr/bin/bash in /tmp", line)

    def test_a_missing_bash_is_a_refusal_and_nothing_runs(self):
        runner = RecordingRunner()
        seam = probing.Seam(run=runner, which=lambda name: None, env={})
        outcome = ready_outcome(filled_probe())
        probing.run_probe(seam, outcome)
        self.assertEqual(outcome.refusals, ["bash not found on PATH; nothing ran"])
        self.assertEqual((runner.calls, seam.lines), ([], []))

    def test_a_context_is_taken_as_it_is(self):
        """`carry probe` hands run_probe its Context: the `[twine] ` line goes
        to the context's stderr as before."""
        runner = RecordingRunner(RunResult(argv=("bash",), exit_code=0,
                                           stdout=self.paste_back(), stderr=b""))
        stderr = io.StringIO()
        ctx = Context(env={"PATH": "/usr/bin"}, stdout=io.StringIO(), stderr=stderr,
                      which=lambda name: f"/usr/bin/{name}", stdin=io.BytesIO(b""), run=runner)
        outcome = ready_outcome(filled_probe())
        probing.run_probe(ctx, outcome)
        self.assertTrue(outcome.ok, outcome.reason)
        self.assertTrue(stderr.getvalue().startswith("[twine] running probe "))


if __name__ == "__main__":
    unittest.main()

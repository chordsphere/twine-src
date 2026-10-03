"""The run seam (twine/process.py, Context.run): a real process group,
the timeout that reaches children, the stdout cap, stderr capture, and
the rule that no verb module spawns a process of its own."""

from __future__ import annotations

import ast
import shutil
import time
import unittest

from twine import REPO_ROOT
from twine.cli import Context
from twine.process import (DEFAULT_STDERR_CAP, RunError, RunResult,
                           run_process, runner_confines)

from tests.helpers import FixturePlayer, dies_within

# Every command below is bash, the one interpreter the seam's first caller
# (carry probe) needs; none of them reaches outside its temp state. The
# absolute path, so a test that hands the child a narrow PATH still finds it.
BASH = shutil.which("bash") or "bash"


class RealRuns(unittest.TestCase):

    def test_exit_code_and_both_streams_as_bytes(self):
        r = run_process([BASH, "-c", "echo out; echo err >&2; exit 3"])
        self.assertIsInstance(r, RunResult)
        self.assertEqual((r.exit_code, r.stdout, r.stderr), (3, b"out\n", b"err\n"))
        self.assertFalse(r.timed_out or r.stdout_capped or r.stderr_truncated)

    def test_stdin_bytes_are_fed_and_none_is_dev_null(self):
        self.assertEqual(run_process([BASH, "-c", "cat"], stdin=b"a\r\nb").stdout,
                         b"a\r\nb")
        started = time.monotonic()
        r = run_process([BASH, "-c", "cat"], timeout=10)
        self.assertEqual((r.exit_code, r.stdout), (0, b""))
        self.assertLess(time.monotonic() - started, 5, "stdin must not be inherited")

    def test_cwd_and_env_are_the_callers(self):
        r = run_process([BASH, "-c", 'pwd; echo "$TWINE_SEAM"'], cwd="/",
                        env={"PATH": "/usr/bin:/bin", "TWINE_SEAM": "seen"})
        self.assertEqual(r.stdout, b"/\nseen\n")

    def test_timeout_kills_the_child_and_its_children_promptly(self):
        started = time.monotonic()
        r = run_process([BASH, "-c", "sleep 30 & echo $!; wait"], timeout=1)
        elapsed = time.monotonic() - started
        self.assertTrue(r.timed_out)
        self.assertIsNone(r.exit_code)
        self.assertLess(elapsed, 8, f"the run outlived its timeout: {elapsed:.1f}s")
        child = int(r.stdout.split()[0])
        self.assertTrue(dies_within(child), f"sleep {child} outlived the timeout")

    def test_a_backgrounded_child_cannot_hold_the_pipes_open(self):
        """bash exits at once; the sleep it left behind holds stdout. The
        run ends with bash, and the sleep goes with its group."""
        started = time.monotonic()
        r = run_process([BASH, "-c", "sleep 30 & echo $!"], timeout=20)
        self.assertLess(time.monotonic() - started, 8)
        self.assertEqual((r.exit_code, r.timed_out), (0, False))
        self.assertTrue(dies_within(int(r.stdout.split()[0])))

    def test_stdout_cap_stops_the_run_and_keeps_exactly_the_cap(self):
        started = time.monotonic()
        r = run_process([BASH, "-c", "yes"], stdout_cap=4096, timeout=30)
        self.assertLess(time.monotonic() - started, 8, "a flood is stopped, not drained")
        self.assertTrue(r.stdout_capped)
        self.assertFalse(r.timed_out)
        self.assertIsNone(r.exit_code)
        self.assertEqual(len(r.stdout), 4096)

    def test_stderr_is_drained_past_its_cap_and_flagged(self):
        n = DEFAULT_STDERR_CAP + 10000
        r = run_process([BASH, "-c", f"head -c {n} /dev/zero >&2; echo done"])
        self.assertEqual((r.exit_code, r.stdout), (0, b"done\n"))
        self.assertEqual(len(r.stderr), DEFAULT_STDERR_CAP)
        self.assertTrue(r.stderr_truncated)

    def test_a_process_that_cannot_start_raises_run_error(self):
        with self.assertRaises(RunError):
            run_process(["/nonexistent/twine-no-such-program"])
        with self.assertRaises(RunError):
            run_process([])


class TheSeam(unittest.TestCase):

    def test_context_run_defaults_to_the_real_runner(self):
        self.assertIs(Context().run, run_process)

    def test_the_default_runner_confines_nothing(self):
        """runner_confines is the `confined` switch point: the default
        runner declares false, and a runner that does not say is false."""
        self.assertIs(runner_confines(run_process), False)
        self.assertIs(runner_confines(FixturePlayer(REPO_ROOT)), False)
        self.assertIs(runner_confines(lambda *a, **k: None), False)

    def test_no_verb_module_spawns_a_process_of_its_own(self):
        """Handlers run subprocesses through ctx.run only: no module under
        twine/commands/ imports a process-spawning module."""
        forbidden = {"subprocess", "multiprocessing", "pty", "asyncio", "pexpect"}
        for path in sorted((REPO_ROOT / "twine" / "commands").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            roots = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    roots.add(node.module.split(".")[0])
            with self.subTest(module=path.name):
                self.assertFalse(roots & forbidden, roots & forbidden)

    def test_fixture_player_answers_a_recorded_bale_argv(self):
        """The double session 2b-ii builds on: `bale status --json` run in
        the repo answers with the recorded fixture's bytes."""
        player = FixturePlayer(REPO_ROOT)
        r = player(["bale", "status", "--json"], cwd=REPO_ROOT)
        recorded = (REPO_ROOT / "fixtures/bale-0.4.45/twine-src/status_--json.json")
        self.assertEqual((r.exit_code, r.stdout), (0, recorded.read_bytes()))
        r = player(["/somewhere/bin/bale", "--version"], cwd="/tmp")
        self.assertEqual(r.stdout, (REPO_ROOT / "fixtures/bale-0.4.45/anywhere/"
                                    "--version.txt").read_bytes())
        with self.assertRaises(AssertionError):
            player(["bale", "relay", "some-sid", "-"], cwd=REPO_ROOT)
        with self.assertRaises(AssertionError):
            player(["bash", "-c", "true"])


if __name__ == "__main__":
    unittest.main()

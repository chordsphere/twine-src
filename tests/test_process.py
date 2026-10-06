"""The run seam (twine/process.py, Context.run): a real process group,
the timeout that reaches children, the stdout cap, stderr capture, the
spawn hook (session 5c), and the rule that no verb module spawns a
process of its own."""

from __future__ import annotations

import ast
import json
import shutil
import signal
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from twine import REPO_ROOT, process
from twine.cli import Context
from twine.process import (DEFAULT_STDERR_CAP, RunError, RunResult,
                           run_process, runner_confines)

from tests.helpers import FixturePlayer, RealGroup, dies_within

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

    def test_the_run_returns_only_once_its_group_is_gone(self):
        """Session 5b: after a kill the runner waits for every member of the
        group, so one check right after the run is enough — no polling."""
        r = run_process([BASH, "-c", "sleep 30 & echo $!; sleep 30 & echo $!; wait"],
                        timeout=1)
        self.assertTrue(r.timed_out)
        self.assertEqual(r.group_survivors, ())
        for pid in map(int, r.stdout.split()):
            # Polled, not checked once (brief §7; cost-spine-005's race): the
            # guarantee is group_survivors == (), asserted above.
            self.assertTrue(dies_within(pid), f"{pid} outlived the run")

    def test_a_member_with_its_pipes_closed_dies_with_the_run(self):
        """Session 5b's review: the child exits as its pipes reach EOF, and a
        backgrounded member holds no pipe — the loop can end before it sees
        the exit. The group is SIGKILLed anyway, every time."""
        script = "sleep 30 >/dev/null 2>&1 </dev/null & echo $!; exit 0"
        for attempt in range(25):
            with self.subTest(attempt=attempt):
                r = run_process([BASH, "-c", script], timeout=20)
                self.assertEqual((r.exit_code, r.group_survivors), (0, ()))
                pid = int(r.stdout.split()[0])
                # Polled (brief §7): a SIGKILLed sleep can close its
                # descriptors before the kernel marks it a zombie; a sleep the
                # runner never killed is still alive after 3 s and fails here.
                self.assertTrue(dies_within(pid), f"sleep {pid} outlived the run")

    def test_a_clean_exit_is_never_reported_as_the_runners_kill(self):
        """Session 5b's review: `cat` closes its pipes in its exit handler,
        just before it exits; the runner waits for the exit before it kills
        the group, so the exit code is the child's own."""
        for attempt in range(200):
            with self.subTest(attempt=attempt):
                r = run_process([BASH, "-c", "cat"], timeout=10)
                self.assertEqual((r.exit_code, r.stdout), (0, b""))

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


class SpawnHook(unittest.TestCase):
    """Session 5c: `on_spawn(pid)` the moment Popen returns, before stdin is
    fed and before the collector starts; a hook that raises never leaves
    the child running."""

    def test_the_hook_sees_the_childs_pid_before_stdin_is_fed(self):
        """The child waits for stdin, then prints its pid and pgid; the
        hook recorded that pid before the child could read a byte — and,
        in the runner, before the stdin feeder and the collector started
        (both are spied on, so the order is asserted, not inferred)."""
        order: list[str] = []
        real_feed, real_collect = process._feed_stdin, process._collect

        def feed(proc, data):
            order.append("feed")
            return real_feed(proc, data)

        def collect(*args):
            order.append("collect")
            return real_collect(*args)

        def hook(pid: int) -> None:
            order.append(f"hook:{pid}")

        with mock.patch.object(process, "_feed_stdin", side_effect=feed), \
                mock.patch.object(process, "_collect", side_effect=collect):
            r = run_process([BASH, "-c", "read -r go; echo $$ $(ps -o pgid= -p $$)"],
                            stdin=b"go\n", timeout=10, on_spawn=hook)
        self.assertEqual(r.exit_code, 0, r.stderr)
        pid, pgid = (int(t) for t in r.stdout.split())
        self.assertEqual(order, [f"hook:{pid}", "feed", "collect"])
        self.assertEqual(pgid, pid, "the child leads its own group: pid is pgid")

    def test_no_hook_is_the_default_and_nothing_changes(self):
        r = run_process([BASH, "-c", "echo out"], on_spawn=None)
        self.assertEqual((r.exit_code, r.stdout), (0, b"out\n"))

    def test_a_hook_that_raises_kills_the_child_and_re_raises(self):
        """Nothing runs on unregistered: the group is killed and reaped,
        and the hook's own exception comes back unchanged."""
        seen: list[int] = []

        def refuse(pid: int) -> None:
            seen.append(pid)
            raise RuntimeError("the record could not be grown")

        with self.assertRaises(RuntimeError) as caught:
            run_process([BASH, "-c", "sleep 30 & echo $!; wait"], stdin=b"x",
                        timeout=30, on_spawn=refuse)
        self.assertEqual(str(caught.exception), "the record could not be grown")
        self.assertEqual(len(seen), 1)
        self.assertTrue(dies_within(seen[0]), f"child {seen[0]} outlived the failed hook")
        self.assertEqual(process.wait_group_gone(seen[0], 3.0), [],
                         "the child's whole group goes with it")

    def test_the_hook_registers_the_group_with_twine_kill_end_to_end(self):
        """Brief §2.2: a child started through run_process, with the hook
        registering into a temp state directory, appears in that directory's
        running record while it runs — the child itself reads the record
        back and prints it."""
        from twine import kill
        sid = "2026-10-05-hook-test-001"
        with tempfile.TemporaryDirectory(prefix="twine-hook-") as tmp:
            state = Path(tmp) / "state"
            state.mkdir()
            runtime = RealGroup()
            self.addCleanup(runtime.cleanup)
            kill.register_running(state, sid, runtime.pgid, runtime.pgid)
            record = kill.running_path(state, sid)
            r = run_process([BASH, "-c", f"read -r go; echo $$; cat {record}"],
                            stdin=b"go\n", timeout=10,
                            on_spawn=lambda pid: kill.register_group(state, sid, pid))
            self.assertEqual(r.exit_code, 0, r.stderr)
            first, rest = r.stdout.split(b"\n", 1)
            child = int(first)
            seen_by_child = json.loads(rest)
            self.assertEqual([g["pgid"] for g in seen_by_child["groups"]], [child],
                             "the child found itself registered")
            self.assertEqual(seen_by_child["pgid"], runtime.pgid)
            after = kill.read_running(state, sid)
            self.assertEqual([g.pgid for g in after.groups], [child])
            self.assertIsInstance(after.groups[0].leader_start_ticks, int,
                                  "the leader was alive when registered")
            self.assertTrue(dies_within(child))

    def test_every_run_seam_double_accepts_the_hook(self):
        """The Runner protocol grew the keyword; the doubles take it (and
        never call it — a double spawns nothing, so it has no pid)."""
        from tests.helpers import RecordingRunner, UnlockDouble

        def never(pid: int) -> None:
            raise AssertionError("a double called the hook")

        recorder = RecordingRunner()
        recorder(["x"], on_spawn=never)
        self.assertIs(recorder.calls[0]["on_spawn"], never)
        unlock = UnlockDouble()
        unlock(["/double/bin/bale", "unlock", "sid", "--reason", "aborted", "--json"],
               on_spawn=never)
        self.assertIs(unlock.calls[0]["on_spawn"], never)
        player = FixturePlayer(REPO_ROOT)
        r = player(["bale", "status", "--json"], cwd=REPO_ROOT, on_spawn=never)
        self.assertEqual(r.exit_code, 0)
        import inspect
        for runner in (run_process, recorder, unlock, player):
            with self.subTest(runner=type(runner).__name__):
                self.assertIn("on_spawn", inspect.signature(runner).parameters)


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

    def test_group_members_reads_a_real_group(self):
        group = RealGroup()
        self.addCleanup(group.cleanup)
        self.assertEqual(process.group_members(group.pgid), sorted(group.pids))
        self.assertEqual(process.start_ticks(group.pgid),
                         process.read_stat(group.pgid).start_ticks)
        self.assertIsNone(process.signal_group(group.pgid, signal.SIGKILL))
        self.assertEqual(process.wait_group_gone(group.pgid, 3.0), [])
        self.assertEqual(process.group_members(group.pgid), [])
        self.assertEqual(process.signal_group(2 ** 22 + 7, 0), "gone")

    def test_signal_group_never_signals_group_0_or_1(self):
        for pgid in (-5, 0, 1):
            with self.subTest(pgid=pgid), self.assertRaises(ValueError):
                process.signal_group(pgid, signal.SIGTERM)

    def test_read_stat_survives_a_command_name_with_parens_and_counts_zombies_dead(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "self").mkdir()
            (root / "self" / "stat").write_text("1 (x) S 0 1 1")
            rest = " ".join(["0"] * 16) + " 4242 0"
            for pid, comm, state, pgrp in ((10, "a) b (c", "S", 77), (11, "z", "Z", 77),
                                           (12, "y", "R", 78)):
                (root / str(pid)).mkdir()
                (root / str(pid) / "stat").write_text(
                    f"{pid} ({comm}) {state} 1 {pgrp} {rest}\n")
            st = process.read_stat(10, root)
            self.assertEqual((st.pid, st.state, st.pgid, st.start_ticks, st.alive),
                             (10, "S", 77, 4242, True))
            self.assertFalse(process.read_stat(11, root).alive)
            self.assertEqual(process.group_members(77, root), [10])
            self.assertIsNone(process.read_stat(99, root))
            self.assertIsNone(process.group_members(77, root / "absent"),
                              "no procfs: the members cannot be enumerated")

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

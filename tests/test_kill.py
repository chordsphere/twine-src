"""The kill-switch (D15; Arc 1 session 5b): twine/kill.py and `twine kill`.

No test here, and nothing in the suite, runs a real `bale unlock`: every
unlock answer is a double built from format_unlock_json's key contract
(tests/helpers.py unlock_json_double, UnlockDouble, StubBale's
unlock_stdout), named as one; no output of the verb has been recorded. The
processes the kill kills are real `setsid`-led groups the tests start
(tests/helpers.py RealGroup) — and a test that asserts one is dead polls
for it (`dies_within`, brief §7) rather than checking once — and every state
directory is a temporary one
— never the real default: the in-process runs carry an empty environment.

Sections:
  1. The between-calls abort
  2. The running record
  3. The process-level kill
  4. The aborted closure
  5. The kill, end to end (the function)
  6. `twine kill`, the verb
  7. Guards: one unlock argv, nothing spawned, the stop key
"""

from __future__ import annotations

import ast
import io
import json
import logging
import os
import signal
import stat
import tempfile
import time
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from twine import REPO_ROOT, TRANSITIONS_TABLE, bale, kill, process
from twine.cli import Context, main
from twine.commands import kill as kill_verb

from tests.helpers import (PIN, UNLOCK_KEYS, RealGroup, StubBale, TempRoots, UnlockDouble,
                           dies_within, process_alive, run_cli, unlock_json_double,
                           unlock_refusal_double)

SID = "2026-10-04-kill-test-001"
EXE = Path("/double/root/bin/bale")


def executable(path: Path = EXE, installed: str = PIN) -> bale.Executable:
    """A bale.Executable as locate_executable would build it for a root at
    `installed` — a value, not a bale: nothing is run but the double the
    test hands the closure."""
    root = bale.Root(path.parent.parent, "--bale-root", f"--bale-root {path.parent.parent}")
    return bale.Executable(root, path, installed, PIN, f"bin/VERSION reads {installed}")
# bale 0.4.45's HOLD-branch refusal (cmd_unlock, quoted in the session-5b
# brief §2.2), for this sid: what a double prints on stderr.
HOLD_REFUSAL = (f"branch bale/{SID} exists — this session reached HOLD. Use `bale "
                f"revert {SID}` to discard the branch and clear the lock together, or "
                "`bale unlock --force` to clear only the lock (the branch would be "
                "left in place for you to delete manually).")


_QUIET = logging.NullHandler()


def setUpModule():
    """The kill module logs the faults these tests make on purpose; keep
    them out of the test output (the reports carry them)."""
    logging.getLogger("twine.kill").addHandler(_QUIET)
    logging.getLogger("twine.process").addHandler(_QUIET)


def tearDownModule():
    logging.getLogger("twine.kill").removeHandler(_QUIET)
    logging.getLogger("twine.process").removeHandler(_QUIET)


class StateCase(unittest.TestCase):
    """A temp state directory per test, and cleanup of any group started."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="twine-kill-")
        self.base = Path(self._dir.name)
        self.state = self.base / "state"
        self.state.mkdir()
        self.repo = self.base / "repo"
        self.repo.mkdir()

    def state_is_empty(self) -> bool:
        return not any(self.state.iterdir())

    def tearDown(self):
        self._dir.cleanup()

    def group(self, **kwargs) -> RealGroup:
        group = RealGroup(**kwargs)
        self.addCleanup(group.cleanup)
        return group


# ---------------------------------------------------------------------------
# 1. The between-calls abort
# ---------------------------------------------------------------------------


class BetweenCallsAbort(StateCase):

    def test_request_is_durable_and_observed(self):
        self.assertFalse(kill.abort_requested(self.state, SID))
        req = kill.request_abort(self.state, SID, clock=lambda: "2026-10-04T00:00:00Z")
        self.assertEqual((req.already, req.requested_at), (False, "2026-10-04T00:00:00Z"))
        self.assertEqual(req.path, self.state / "abort" / f"{SID}.json")
        self.assertEqual(json.loads(req.path.read_text()),
                         {"sid": SID, "requested_at": "2026-10-04T00:00:00Z"})
        self.assertTrue(kill.abort_requested(self.state, SID))
        self.assertFalse(kill.abort_requested(self.state, "2026-10-04-other-001"))

    def test_requesting_twice_is_idempotent_and_the_first_time_stands(self):
        first = kill.request_abort(self.state, SID, clock=lambda: "2026-10-04T00:00:00Z")
        before = first.path.read_bytes()
        again = kill.request_abort(self.state, SID, clock=lambda: "2026-10-04T09:09:09Z")
        self.assertEqual((again.already, again.requested_at),
                         (True, "2026-10-04T00:00:00Z"))
        self.assertEqual(first.path.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in first.path.parent.iterdir()),
                         [f"{SID}.json"], "no temp file left behind")

    def test_owner_only_modes(self):
        req = kill.request_abort(self.state, SID)
        self.assertEqual(stat.S_IMODE(req.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(req.path.parent.stat().st_mode), 0o700)

    def test_any_file_at_the_path_is_a_request(self):
        """Presence is the signal: a torn or foreign file still stops the loop."""
        path = kill.abort_path(self.state, SID)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\x00not json")
        self.assertTrue(kill.abort_requested(self.state, SID))
        again = kill.request_abort(self.state, SID)
        self.assertEqual((again.already, again.requested_at), (True, None))

    def test_a_request_that_cannot_be_looked_for_reads_as_requested(self):
        """Fail closed: the loop stops rather than spending on. Only a path
        that does not exist reads as no request."""
        with mock.patch.object(kill.os, "stat", side_effect=PermissionError(13, "denied")):
            self.assertTrue(kill.abort_requested(self.state, SID))
        (self.state / "abort").write_text("a file where the directory should be")
        self.assertTrue(kill.abort_requested(self.state, SID))
        self.assertFalse(kill.abort_requested(self.base / "no-such-state", SID))

    def test_a_request_that_cannot_be_written_raises_kill_error(self):
        not_a_dir = self.base / "file"
        not_a_dir.write_text("a file where the state directory should be")
        with self.assertRaises(kill.KillError):
            kill.request_abort(not_a_dir, SID)

    def test_a_long_sid_fails_only_where_its_own_name_would(self):
        """The temp file's name is short whatever the sid's: a sid at the
        bound writes; one past it is refused before any path is built."""
        longest = "a" * kill.MAX_SID_LENGTH
        req = kill.request_abort(self.state, longest)
        self.assertTrue(req.path.is_file())
        with self.assertRaises(ValueError):
            kill.request_abort(self.state, longest + "a")

    def test_a_sid_that_is_not_one_is_refused_before_any_path_is_built(self):
        for sid in ("", "../escape", "-flag", "a b", "a/b", ".hidden"):
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                kill.request_abort(self.state, sid)
        self.assertTrue(self.state_is_empty())


# ---------------------------------------------------------------------------
# 2. The running record
# ---------------------------------------------------------------------------


class RunningRecord(StateCase):

    def test_register_read_clear(self):
        group = self.group()
        rec = kill.register_running(self.state, SID, group.pgid, group.pgid,
                                    clock=lambda: "2026-10-04T01:00:00Z")
        self.assertEqual(rec.path, self.state / "running" / f"{SID}.json")
        self.assertEqual(json.loads(rec.path.read_text()),
                         {"sid": SID, "pgid": group.pgid, "pid": group.pgid,
                          "started_at": "2026-10-04T01:00:00Z",
                          "leader_start_ticks": process.start_ticks(group.pgid)})
        self.assertIsInstance(rec.leader_start_ticks, int)
        self.assertEqual(kill.read_running(self.state, SID), rec)
        self.assertEqual(stat.S_IMODE(rec.path.stat().st_mode), 0o600)
        self.assertTrue(kill.clear_running(self.state, SID))
        self.assertIsNone(kill.read_running(self.state, SID))
        self.assertFalse(kill.clear_running(self.state, SID))

    def test_register_refuses_a_group_that_could_not_be_one(self):
        for pgid, pid in ((0, 5), (1, 5), (True, 5), (5, -1), ("5", 5)):
            with self.subTest(pgid=pgid, pid=pid):
                with self.assertRaises(kill.RunningRecordError):
                    kill.register_running(self.state, SID, pgid, pid)
        self.assertTrue(self.state_is_empty())

    def test_a_malformed_record_is_named_never_guessed(self):
        path = kill.running_path(self.state, SID)
        path.parent.mkdir(parents=True)
        good = {"sid": SID, "pgid": 4242, "pid": 4243, "started_at": "t",
                "leader_start_ticks": None}
        cases = {
            "not a JSON object": b"{nope",
            "is not a JSON object": b"[1, 2]",
            "pgid 1": json.dumps({**good, "pgid": 1}).encode(),
            "pgid True": json.dumps({**good, "pgid": True}).encode(),
            "pid None": json.dumps({k: v for k, v in good.items() if k != "pid"}).encode(),
            "not '" + SID: json.dumps({**good, "sid": "2026-10-04-other-001"}).encode(),
            "started_at None": json.dumps({**good, "started_at": None}).encode(),
            "leader_start_ticks -3": json.dumps({**good, "leader_start_ticks": -3}).encode(),
            "RecursionError": b"[" * 200_000,
        }
        for needle, raw in cases.items():
            with self.subTest(needle=needle):
                path.write_bytes(raw)
                with self.assertRaises(kill.RunningRecordError) as caught:
                    kill.read_running(self.state, SID)
                self.assertIn(needle, str(caught.exception))
                self.assertIn(str(path), str(caught.exception))


# ---------------------------------------------------------------------------
# 3. The process-level kill
# ---------------------------------------------------------------------------


class ProcessLevelKill(StateCase):

    def record(self, group: RealGroup, ticks="real") -> kill.RunningRecord:
        rec = kill.register_running(self.state, SID, group.pgid, group.pgid)
        if ticks != "real":
            rec = kill.RunningRecord(SID, rec.pgid, rec.pid, rec.started_at, ticks, rec.path)
        return rec

    def test_a_group_that_honours_sigterm_needs_no_sigkill(self):
        group = self.group()
        step = kill.kill_group(self.record(group), grace=5, wait=5)
        self.assertEqual((step.dead, step.signals, step.survivors, step.error),
                         (True, ["SIGTERM", "SIGCONT"], [], None))
        for pid in group.pids:
            self.assertTrue(dies_within(pid), f"{pid} outlived the kill")

    def test_a_group_that_ignores_sigterm_gets_sigkill_after_the_grace(self):
        group = self.group(body='trap "" TERM; sleep 60 & echo $!; sleep 60 & echo $!; wait')
        started = time.monotonic()
        step = kill.kill_group(self.record(group), grace=0.4, wait=5)
        elapsed = time.monotonic() - started
        self.assertEqual((step.dead, step.signals, step.survivors),
                         (True, ["SIGTERM", "SIGCONT", "SIGKILL"], []))
        self.assertGreaterEqual(elapsed, 0.4, "SIGKILL came before the grace ran out")
        self.assertLess(elapsed, 4)
        for pid in group.pids:
            self.assertTrue(dies_within(pid), f"{pid} outlived the kill")

    def test_a_group_already_gone_is_not_signalled(self):
        group = self.group()
        rec = self.record(group)
        os.killpg(group.pgid, signal.SIGKILL)
        self.assertEqual(process.wait_group_gone(group.pgid, 3), [])
        with mock.patch.object(process, "signal_group",
                               side_effect=AssertionError("signalled")):
            step = kill.kill_group(rec)
        self.assertEqual((step.dead, step.signals), (True, []))

    def test_a_stopped_member_is_continued_so_sigterm_reaches_it(self):
        """A stopped (T-state) member sees SIGTERM only once continued:
        SIGCONT follows SIGTERM, so the grace is not wasted on it."""
        group = self.group()
        os.kill(group.children[0], signal.SIGSTOP)
        step = kill.kill_group(self.record(group), grace=5, wait=5)
        self.assertEqual((step.dead, step.signals), (True, ["SIGTERM", "SIGCONT"]))

    def test_a_stale_record_signals_nothing(self):
        """The number now leads a process with another start time: the
        recorded group is gone, and the live one is not touched."""
        group = self.group()
        rec = self.record(group, ticks=process.start_ticks(group.pgid) + 1)
        step = kill.kill_group(rec, grace=0, wait=0)
        self.assertEqual((step.stale, step.dead, step.signals), (True, True, []))
        for pid in group.pids:
            self.assertTrue(process_alive(pid), f"{pid} was signalled on a stale record")

    def test_twine_kills_own_group_is_never_signalled(self):
        own = os.getpgrp()
        rec = kill.RunningRecord(SID, own, own, "t", None,
                                 kill.running_path(self.state, SID))
        with mock.patch.object(process, "signal_group",
                               side_effect=AssertionError("signalled own group")):
            step = kill.kill_group(rec)
        self.assertFalse(step.dead)
        self.assertIn("twine kill's own", step.error)

    def test_survivors_are_named_and_the_step_is_not_done(self):
        """A member that will not die (a double: the group always answers
        with it) is named, after SIGTERM and SIGKILL, and the step stops."""
        sent = []
        rec = kill.RunningRecord(SID, 4242, 4242, "t", None,
                                 kill.running_path(self.state, SID))
        with mock.patch.object(process, "group_members", return_value=[4242, 4250]), \
                mock.patch.object(process, "signal_group",
                                  side_effect=lambda g, s: sent.append((g, s))):
            step = kill.kill_group(rec, grace=0.1, wait=0.1)
        self.assertEqual(sent, [(4242, signal.SIGTERM), (4242, signal.SIGCONT),
                                (4242, signal.SIGKILL)])
        self.assertEqual((step.dead, step.survivors, step.signals),
                         (False, [4242, 4250], ["SIGTERM", "SIGCONT", "SIGKILL"]))
        self.assertIn("4242, 4250", step.error)

    def test_without_procfs_the_group_is_signalled_but_never_called_dead(self):
        sent = []
        rec = kill.RunningRecord(SID, 4242, 4242, "t", None,
                                 kill.running_path(self.state, SID))
        with mock.patch.object(process, "group_members", return_value=None), \
                mock.patch.object(process, "signal_group",
                                  side_effect=lambda g, s: sent.append(s)):
            step = kill.kill_group(rec, grace=0, wait=0)
        self.assertEqual(sent, [signal.SIGTERM, signal.SIGCONT, signal.SIGKILL])
        self.assertFalse(step.dead)
        self.assertIn("cannot be enumerated", step.error)


# ---------------------------------------------------------------------------
# 4. The aborted closure
# ---------------------------------------------------------------------------


class AbortedClosure(StateCase):

    def close(self, runner, exe=None):
        return kill.close_aborted(runner, exe or executable(), SID, cwd=self.repo,
                                  env={"X": "1"})

    def test_the_one_argv_once(self):
        runner = UnlockDouble()
        closure = self.close(runner)
        self.assertTrue(closure.ok, closure.failures)
        self.assertEqual(len(runner.calls), 1)
        call = runner.calls[0]
        self.assertEqual(call["argv"],
                         [str(EXE), "unlock", SID, "--reason", "aborted", "--json"])
        self.assertEqual((call["cwd"], call["stdin"], call["env"]), (self.repo, None, {"X": "1"}))
        self.assertEqual(closure.telemetry, f"claude/telemetry/{SID}.json")
        self.assertEqual(list(closure.unlock), list(UNLOCK_KEYS))
        self.assertIsNone(closure.operator_line)

    def test_a_refusal_is_not_ok_names_bales_reason_and_is_never_retried(self):
        runner = UnlockDouble(stdout=b"", exit_code=1, stderr=unlock_refusal_double(
            f"session {SID} is not open; nothing to unlock. No sessions are open."))
        closure = self.close(runner)
        self.assertFalse(closure.ok)
        self.assertEqual(len(runner.calls), 1, "a closure is never retried")
        self.assertEqual(closure.failures,
                         [f"bale exited 1: [bale] error: session {SID} is not open; "
                          "nothing to unlock. No sessions are open."])
        self.assertEqual(closure.operator_line, f"bale unlock {SID} --reason aborted")
        self.assertIsNone(closure.unlock)

    def test_the_hold_branch_refusal_hands_back_bales_own_remedy(self):
        runner = UnlockDouble(stdout=b"", exit_code=1,
                              stderr=unlock_refusal_double(HOLD_REFUSAL))
        closure = self.close(runner)
        self.assertFalse(closure.ok)
        self.assertTrue(closure.hold_branch)
        self.assertEqual(closure.operator_line, f"bale revert {SID}")
        self.assertEqual(len(runner.calls), 1)

    def test_a_line_that_is_not_this_close_is_not_ok(self):
        cases = {
            "outcome 'no-op'": unlock_json_double(SID, outcome="no-op", sid=None,
                                                  closure_reason=None),
            "sid '2026-10-04-other-001'": unlock_json_double(
                SID, sid="2026-10-04-other-001"),
            "closure_reason 'abandoned'": unlock_json_double(SID,
                                                             closure_reason="abandoned"),
            "not one JSON object (it began 'unlocked')": b"unlocked\n",
            "not one JSON object (it was empty)": b"",
        }
        for needle, stdout in cases.items():
            with self.subTest(needle=needle):
                closure = self.close(UnlockDouble(stdout=stdout))
                self.assertFalse(closure.ok)
                self.assertIn(needle, "; ".join(closure.failures))
                self.assertEqual(closure.operator_line,
                                 f"bale unlock {SID} --reason aborted")

    def test_a_timeout_is_not_ok_and_not_retried(self):
        runner = UnlockDouble(timed_out=True)
        closure = self.close(runner)
        self.assertFalse(closure.ok)
        self.assertEqual(len(runner.calls), 1)
        self.assertIn("may or may not have closed", closure.failures[0])

    def test_an_unpinned_bale_is_never_started(self):
        """The closure checks the pin itself, so the loop cannot reach an
        unpinned bale by forgetting the gate."""
        runner = UnlockDouble()
        closure = self.close(runner, exe=executable(installed="0.4.46"))
        self.assertEqual((closure.ok, closure.ran, runner.calls), (False, False, []))
        self.assertIn("not the pin", closure.failures[0])

    def test_a_bale_that_cannot_start_is_not_ok(self):
        def cannot_start(argv, **kwargs):
            raise process.RunError(2, "cannot start bale: No such file or directory")
        closure = self.close(cannot_start)
        self.assertEqual((closure.ok, closure.ran), (False, False))
        self.assertIn("could not be started", closure.failures[0])


# ---------------------------------------------------------------------------
# 5. The kill, end to end (the function)
# ---------------------------------------------------------------------------


class KillSession(StateCase):

    def kill(self, runner=None, **kwargs):
        runner = runner if runner is not None else UnlockDouble()
        report = kill.kill_session(self.state, SID, run=runner, executable=executable(),
                                   cwd=self.repo, env={}, **kwargs)
        return report, runner

    def test_no_running_record_is_not_a_fault(self):
        report, runner = self.kill()
        self.assertTrue(report.ok, report.reason)
        self.assertEqual((report.stopped_at, report.operator_line, report.process),
                         (None, None, None))
        self.assertTrue(kill.abort_requested(self.state, SID))
        self.assertEqual(len(runner.calls), 1)

    def test_a_live_group_is_killed_then_the_session_closed_and_the_cache_cleared(self):
        group = self.group()
        kill.register_running(self.state, SID, group.pgid, group.pgid)
        report, runner = self.kill(grace=2)
        self.assertTrue(report.ok, report.reason)
        self.assertEqual((report.process.dead, report.process.signals,
                          report.process.record_cleared),
                         (True, ["SIGTERM", "SIGCONT"], True))
        self.assertIsNone(kill.read_running(self.state, SID))
        self.assertEqual(len(runner.calls), 1)
        for pid in group.pids:
            self.assertTrue(dies_within(pid), f"{pid} outlived the kill")

    def test_no_closure_while_a_member_lives(self):
        """Ruling 3: survivors are named and the closure is not attempted."""
        rec = kill.RunningRecord(SID, 4242, 4242, "t", None,
                                 kill.running_path(self.state, SID))
        with mock.patch.object(kill, "read_running", return_value=rec), \
                mock.patch.object(process, "group_members", return_value=[4242]), \
                mock.patch.object(process, "signal_group", return_value=None):
            report, runner = self.kill(grace=0, wait=0)
        self.assertEqual(runner.calls, [], "no closure while a member lives")
        self.assertEqual((report.ok, report.stopped_at, report.closure),
                         (False, "process", None))
        self.assertEqual(report.operator_line, "kill -KILL -- -4242")
        self.assertEqual(report.as_json()["process"]["survivors"], [4242])
        self.assertTrue(report.abort_requested, "the abort still lands")

    def test_a_malformed_record_refuses_the_process_step_and_the_closure(self):
        path = kill.running_path(self.state, SID)
        path.parent.mkdir(parents=True)
        path.write_text('{"sid": "%s", "pgid": "not a number"}' % SID)
        report, runner = self.kill()
        self.assertEqual(runner.calls, [])
        self.assertEqual(report.stopped_at, "process")
        self.assertTrue(report.abort_requested, "the abort request still lands")
        self.assertIn("malformed", report.reason)
        self.assertIsNone(report.process.record)
        self.assertTrue(path.exists(), "a malformed record is left for the operator")
        self.assertIsNone(report.operator_line,
                          "no close is handed out while the group is unknown")
        self.assertIn("find and stop the session's runtime", report.reason)

    def test_an_abort_that_cannot_be_written_stops_short_of_the_closure(self):
        with mock.patch.object(kill, "request_abort",
                               side_effect=kill.KillError(28, "No space left on device")):
            report, runner = self.kill()
        self.assertEqual(runner.calls, [])
        self.assertEqual((report.abort_requested, report.stopped_at), (False, "abort"))
        self.assertIn("No space left", report.reason)

    def test_an_unwritten_abort_with_survivors_hands_out_the_kill_not_a_close(self):
        """Session 5b's review: whichever step stopped first, a group that may
        be alive is what the hand line addresses."""
        rec = kill.RunningRecord(SID, 4242, 4242, "t", None,
                                 kill.running_path(self.state, SID))
        with mock.patch.object(kill, "request_abort",
                               side_effect=kill.KillError(30, "Read-only file system")), \
                mock.patch.object(kill, "read_running", return_value=rec), \
                mock.patch.object(process, "group_members", return_value=[4242]), \
                mock.patch.object(process, "signal_group", return_value=None):
            report, runner = self.kill(grace=0, wait=0)
        self.assertEqual((report.stopped_at, report.operator_line, runner.calls),
                         ("abort", "kill -KILL -- -4242", []))

    def test_a_refused_closure_says_where_it_stopped(self):
        report, runner = self.kill(UnlockDouble(stdout=b"", exit_code=1,
                                                stderr=unlock_refusal_double(HOLD_REFUSAL)))
        self.assertEqual((report.ok, report.stopped_at, report.closed),
                         (False, "closure", False))
        self.assertEqual(report.operator_line, f"bale revert {SID}")
        self.assertIn("twine never runs it", report.reason)
        self.assertEqual(report.as_json()["stderr"],
                         unlock_refusal_double(HOLD_REFUSAL).decode())


# ---------------------------------------------------------------------------
# 6. `twine kill`, the verb
# ---------------------------------------------------------------------------


class KillVerb(StateCase):

    def setUp(self):
        super().setUp()
        self.roots = TempRoots()
        self.addCleanup(self.roots.cleanup)

    def run_verb(self, *extra, runner=None, env=None, sid=SID):
        out, err = io.StringIO(), io.StringIO()
        runner = runner if runner is not None else UnlockDouble()
        ctx = Context(env=env if env is not None else {}, stdout=out, stderr=err,
                      which=lambda name: None, stdin=io.BytesIO(b""), run=runner)
        argv = ["kill", sid, "--state-dir", str(self.state), "--cwd", str(self.repo),
                "--bale-root", str(self.roots.ok), *extra]
        code = main(argv, ctx=ctx)
        return code, out.getvalue(), err.getvalue(), runner

    def json_of(self, *extra, **kwargs):
        code, out, err, runner = self.run_verb(*extra, "--json", **kwargs)
        lines = out.split("\n")
        self.assertEqual((len(lines), lines[1]), (2, ""), out)
        return code, json.loads(lines[0]), err, runner

    def test_ok_is_exit_0_with_the_fixed_keys(self):
        code, obj, err, runner = self.json_of("--grace", "0")
        self.assertEqual((code, obj["ok"], obj["command"]), (0, True, "kill"))
        self.assertEqual((obj["sid"], obj["abort_requested"], obj["process"], obj["closed"],
                          obj["operator_line"], obj["reason"], obj["refusals"],
                          obj["stopped_at"]),
                         (SID, True, None, True, None, None, [], None))
        self.assertEqual(obj["closure"], json.loads(unlock_json_double(SID)))
        self.assertEqual(obj["telemetry"], f"claude/telemetry/{SID}.json")
        self.assertEqual(obj["argv"][1:], ["unlock", SID, "--reason", "aborted", "--json"])
        self.assertEqual(obj["argv"][0], str(self.roots.ok / "bin" / "bale"))
        self.assertEqual((obj["state_dir"], obj["state_dir_source"], obj["cwd"],
                          obj["grace_seconds"]),
                         (str(self.state), "--state-dir", str(self.repo), 0.0))
        self.assertEqual(obj["bale"]["pin_matches"], True)
        self.assertNotIn("Traceback", err)

    def test_the_verb_is_the_functions_report(self):
        """One function, two faces: the verb's payload equals what
        kill_session returns when called on its own — in a second state
        directory, with the same inputs — key for key, once that directory's
        path and the request's time are named alike."""
        group = self.group()
        kill.register_running(self.state, SID, group.pgid, group.pgid)
        code, obj, _, _ = self.json_of("--grace", "2")
        self.assertEqual(code, 0, obj["reason"])
        other = self.base / "other-state"
        other.mkdir()
        group_b = self.group()
        kill.register_running(other, SID, group_b.pgid, group_b.pgid)
        exe = bale.locate_executable(str(self.roots.ok), {}, lambda n: None)
        report = kill.KillReport(sid=SID, state_dir_source="--state-dir", cwd=str(self.repo),
                                 grace_seconds=2.0, bale=exe.as_json())
        report = kill.kill_session(other, SID, run=UnlockDouble(), executable=exe,
                                   cwd=str(self.repo), env={}, grace=2.0, report=report)
        expected = json.loads(json.dumps({"command": "kill", "ok": report.ok,
                                          **report.as_json()}))

        def alike(value, state):
            """The per-run values named alike: the state directory's path, the
            group's ids and the times. Everything else must be equal."""
            value = json.loads(json.dumps(value).replace(str(state), "<state>"))
            value["abort"]["requested_at"] = "<time>"
            value["process"].update(pgid="<pgid>", pid="<pgid>", started_at="<time>")
            return value

        self.assertEqual((obj["process"]["pgid"], expected["process"]["pgid"]),
                         (group.pgid, group_b.pgid))
        self.assertEqual(alike(obj, self.state), alike(expected, other))

    def test_every_refusal_is_named_and_nothing_is_done(self):
        code, out, err, runner = self.run_verb("--grace", "-1", "--json",
                                               sid="../escape")
        obj = json.loads(out)
        self.assertEqual((code, obj["ok"], obj["stopped_at"], obj["abort_requested"]),
                         (1, False, "refused", False))
        self.assertEqual(runner.calls, [])
        self.assertTrue(self.state_is_empty(), "nothing written on a refusal")
        reasons = " | ".join(obj["refusals"])
        for needle in ("'../escape' is not a session id", "--grace '-1'"):
            self.assertIn(needle, reasons)
        # The other refusals, one at a time.
        cases = {
            "is not a directory": ["--cwd", str(self.base / "absent")],
            "is not a number of seconds": ["--grace", "soon"],
            "not a finite": ["--grace", "inf"],
            "more than 600 seconds": ["--grace", "601"],
        }
        for needle, extra in cases.items():
            with self.subTest(needle=needle):
                code, obj, _, runner = self.json_of(*extra)
                self.assertEqual((code, obj["stopped_at"]), (1, "refused"))
                self.assertIn(needle, obj["reason"])
                self.assertEqual(runner.calls, [])
        self.assertTrue(self.state_is_empty())

    def test_a_state_directory_that_does_not_exist_is_refused_not_created(self):
        """A mistyped --state-dir must not become an ok kill that stopped
        nothing: the runtime records and reads in its own directory."""
        typo = self.base / "stte"
        code, out, err, runner = self.run_verb("--json")
        self.assertEqual(code, 0)
        for path in (typo, self.base / "a-file"):
            if path.name == "a-file":
                path.write_text("not a directory")
            with self.subTest(path=path.name):
                out, err = io.StringIO(), io.StringIO()
                runner = UnlockDouble()
                ctx = Context(env={}, stdout=out, stderr=err, which=lambda n: None,
                              stdin=io.BytesIO(b""), run=runner)
                code = main(["kill", SID, "--state-dir", str(path), "--cwd",
                             str(self.repo), "--bale-root", str(self.roots.ok),
                             "--json"], ctx=ctx)
                obj = json.loads(out.getvalue())
                self.assertEqual((code, obj["stopped_at"], runner.calls), (1, "refused", []))
                self.assertIn("does not exist" if path == typo else "is not a directory",
                              obj["reason"])
        self.assertFalse(typo.exists(), "a kill never creates its state directory")

    def test_a_current_directory_that_is_gone_is_a_refusal_not_a_traceback(self):
        gone = self.base / "gone"
        gone.mkdir()
        here = os.getcwd()
        os.chdir(gone)
        try:
            gone.rmdir()
            out = io.StringIO()
            ctx = Context(env={}, stdout=out, stderr=io.StringIO(), which=lambda n: None,
                          stdin=io.BytesIO(b""), run=UnlockDouble())
            code = main(["kill", SID, "--state-dir", str(self.state), "--bale-root",
                         str(self.roots.ok), "--json"], ctx=ctx)
        finally:
            os.chdir(here)
        obj = json.loads(out.getvalue())
        self.assertEqual((code, obj["stopped_at"]), (1, "refused"))
        self.assertIn("current directory cannot be resolved", obj["reason"])

    def test_no_state_directory_is_refused(self):
        out, err = io.StringIO(), io.StringIO()
        runner = UnlockDouble()
        ctx = Context(env={}, stdout=out, stderr=err, which=lambda n: None,
                      stdin=io.BytesIO(b""), run=runner)
        code = main(["kill", SID, "--cwd", str(self.repo), "--bale-root",
                     str(self.roots.ok), "--json"], ctx=ctx)
        obj = json.loads(out.getvalue())
        self.assertEqual((code, obj["stopped_at"], obj["state_dir"]), (1, "refused", None))
        self.assertIn("cannot resolve twine's state directory", obj["reason"])
        self.assertEqual(runner.calls, [])

    def test_the_pin_gate_comes_before_the_abort(self):
        """An unpinned bale refuses the whole kill: no abort request, no
        signal, no unlock."""
        for root in (self.roots.other, self.roots.absent):
            with self.subTest(root=root.name):
                out = io.StringIO()
                runner = UnlockDouble()
                ctx = Context(env={}, stdout=out, stderr=io.StringIO(),
                              which=lambda n: None, stdin=io.BytesIO(b""), run=runner)
                code = main(["kill", SID, "--state-dir", str(self.state), "--cwd",
                             str(self.repo), "--bale-root", str(root), "--json"], ctx=ctx)
                obj = json.loads(out.getvalue())
                self.assertEqual((code, obj["stopped_at"]), (1, "refused"))
                self.assertIn("pinned bale", obj["reason"])
                self.assertEqual(runner.calls, [])
                self.assertFalse(kill.abort_requested(self.state, SID))
                self.assertTrue(self.state_is_empty())

    def test_every_path_carries_the_same_keys(self):
        ok = self.json_of()[1]
        refused = self.json_of("--grace", "x")[1]
        closure_refused = self.json_of(runner=UnlockDouble(stdout=b"", exit_code=1))[1]
        with mock.patch.object(process, "group_members", return_value=[4242]), \
                mock.patch.object(process, "signal_group", return_value=None):
            rec = kill.RunningRecord(SID, 4242, 4242, "t", None,
                                     kill.running_path(self.state, SID))
            with mock.patch.object(kill, "read_running", return_value=rec):
                survivors = self.json_of("--grace", "0")[1]
        for obj in (refused, closure_refused, survivors):
            self.assertEqual(set(obj), set(ok))
        self.assertEqual(set(survivors["process"]),
                         {"pgid", "pid", "started_at", "signalled", "signals", "dead",
                          "survivors", "stale", "record_cleared", "record", "error"})
        self.assertEqual(survivors["process"]["signals"], ["SIGTERM", "SIGCONT", "SIGKILL"])
        self.assertEqual((survivors["stopped_at"], survivors["operator_line"]),
                         ("process", "kill -KILL -- -4242"))
        self.assertEqual((closure_refused["stopped_at"], closure_refused["operator_line"]),
                         ("closure", f"bale unlock {SID} --reason aborted"))

    def test_human_mode_names_each_step_and_the_hand_line(self):
        code, out, err, _ = self.run_verb()
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith(f"kill {SID}: done"), out)
        self.assertTrue(any(l.strip().startswith("abort:") for l in lines))
        self.assertIn("no running record", out)
        self.assertIn("closure: bale unlocked", out)
        code, out, err, _ = self.run_verb(runner=UnlockDouble(
            stdout=b"", exit_code=1, stderr=unlock_refusal_double(HOLD_REFUSAL)))
        self.assertEqual(code, 1)
        self.assertIn("NOT FINISHED (stopped at closure)", out.splitlines()[0])
        self.assertIn(f"finish by hand: bale revert {SID}", out)
        self.assertIn(HOLD_REFUSAL, err, "bale's stderr reaches twine's stderr")


class KillEndToEnd(StateCase):
    """The real entrypoint as a subprocess, a real setsid-led group, and a
    stub bale (a double: StubBale replays unlock_json_double's line)."""

    def stub(self, **kwargs) -> StubBale:
        stub = StubBale(**kwargs)
        self.addCleanup(stub.cleanup)
        return stub

    def test_kill_a_real_group_and_close_through_a_stub_bale(self):
        line = self.base / "unlock.json"
        line.write_bytes(unlock_json_double(SID))
        stub = self.stub(unlock_stdout=line)
        group = self.group(body='trap "" TERM; sleep 60 & echo $!; sleep 60 & echo $!; wait')
        kill.register_running(self.state, SID, group.pgid, group.pgid)
        run = run_cli("kill", SID, "--state-dir", str(self.state), "--cwd", str(self.repo),
                      "--grace", "0.3", "--json", bale_root=stub.root)
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["closed"]), (0, True, True), run.stderr)
        self.assertEqual(obj["process"]["signals"], ["SIGTERM", "SIGCONT", "SIGKILL"])
        self.assertEqual((obj["process"]["dead"], obj["process"]["survivors"]), (True, []))
        self.assertEqual(stub.argv(), ["unlock", SID, "--reason", "aborted", "--json"])
        self.assertEqual(Path(stub.cwd()).resolve(), self.repo.resolve())
        for pid in group.pids:
            self.assertTrue(dies_within(pid), f"{pid} outlived twine kill")
        self.assertTrue(kill.abort_requested(self.state, SID))

    def test_a_refusing_stub_is_not_ok_and_shows_bales_stderr(self):
        stub = self.stub(exit_code=1, stderr=unlock_refusal_double(
            f"session {SID} is not open; nothing to unlock. No sessions are open.").decode())
        run = run_cli("kill", SID, "--state-dir", str(self.state), "--cwd", str(self.repo),
                      "--json", bale_root=stub.root)
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["stopped_at"], obj["exit_code"]),
                         (1, False, "closure", 1))
        self.assertIn("is not open", obj["stderr"])
        self.assertIn("is not open", run.stderr)
        self.assertEqual(obj["operator_line"], f"bale unlock {SID} --reason aborted")
        self.assertNotIn("Traceback", run.stderr)


# ---------------------------------------------------------------------------
# 7. Guards: one unlock argv, nothing spawned, the stop key
# ---------------------------------------------------------------------------


class Guards(unittest.TestCase):

    def test_unlock_is_built_in_one_place_only(self):
        """The string "unlock" as an argv token, and "--reason", appear in
        twine's code only inside twine.bale.unlock_argv, whose argv is fixed:
        the sid, `--reason aborted`, `--json`, nothing else."""
        def tokens(node: ast.AST, value: str) -> int:
            return sum(1 for n in ast.walk(node)
                       if isinstance(n, ast.Constant) and n.value == value)

        found: dict[str, dict[str, int]] = {}
        for path in sorted((REPO_ROOT / "twine").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            rel = path.relative_to(REPO_ROOT).as_posix()
            for value in ("unlock", "--reason"):
                if tokens(tree, value):
                    found.setdefault(rel, {})[value] = tokens(tree, value)
            if rel == "twine/bale.py":
                builder = [f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
                           and f.name == "unlock_argv"]
                self.assertEqual(len(builder), 1)
                for value in ("unlock", "--reason"):
                    self.assertEqual(tokens(builder[0], value), tokens(tree, value),
                                     f"{value!r} built outside unlock_argv")
        self.assertEqual(found, {"twine/bale.py": {"unlock": 1, "--reason": 1}}, found)
        self.assertEqual(bale.unlock_argv(EXE, SID),
                         [str(EXE), "unlock", SID, "--reason", "aborted", "--json"])
        self.assertEqual(bale.UNLOCK_REASON, "aborted")
        for sid in ("-x", "", "a b", "--reason"):
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                bale.unlock_argv(EXE, sid)

    def test_twine_never_reverts(self):
        """`bale revert` is handed to the operator as a line, never run."""
        for path in sorted((REPO_ROOT / "twine").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            with self.subTest(module=path.name):
                self.assertFalse([n for n in ast.walk(tree)
                                  if isinstance(n, ast.Constant) and n.value == "revert"])

    def test_the_kill_modules_import_nothing_that_spawns_or_reaches_out(self):
        forbidden = {"subprocess", "multiprocessing", "pty", "asyncio", "pexpect",
                     "socket", "ssl", "http", "urllib", "ctypes"}
        for rel in ("twine/kill.py", "twine/commands/kill.py"):
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
            roots = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    roots.add(node.module.split(".")[0])
            with self.subTest(module=rel):
                self.assertFalse(roots & forbidden, roots & forbidden)

    def test_killed_is_the_tables_stop_and_its_move_is_close_aborted(self):
        with TRANSITIONS_TABLE.open("rb") as fh:
            table = tomllib.load(fh)
        self.assertIn(kill.STOP_KILLED, table["axis"]["stop"]["keys"])
        rows = [r for r in table["row"] if (r["axis"], r["key"]) == ("stop", kill.STOP_KILLED)]
        self.assertEqual([r["move"] for r in rows], ["close-aborted"])
        self.assertEqual(table["move"]["close-aborted"]["actor"], "twine")

    def test_the_verb_registers_from_its_own_module(self):
        self.assertEqual(kill_verb.COMMANDS[0].name, "kill")
        self.assertEqual(kill_verb.parse_grace("2.5"), 2.5)


if __name__ == "__main__":
    unittest.main()

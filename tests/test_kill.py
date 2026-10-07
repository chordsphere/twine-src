"""The kill-switch (D15; Arc 1 sessions 5b and 5c): twine/kill.py and
`twine kill`.

No test here, and nothing in the suite, runs a real `bale unlock`: every
unlock answer is one of the six `bale unlock … --json` lines recorded at
bale 0.4.49 (tests/helpers.py unlock_recording, replayed by RecordedUnlock
and StubBale; fixtures/README.md, "bale 0.4.49"), or bytes a test names as
not bale's at all — the doubles session 5b built from format_unlock_json's
docstring are gone (session 2026-10-07-twine-pin-049-001, contract §14.7).
The session id the tests kill is the one the recorded `aborted` close
names, 2026-10-07-sc-002, so the close is the recording's own. The
processes the kill kills are real `setsid`-led groups the tests start
(tests/helpers.py RealGroup) — and a test that asserts one is dead polls
for it (`dies_within`, brief §7) rather than checking once — and every state
directory is a temporary one
— never the real default: the in-process runs carry an empty environment.

Session 5c: the running record carries `groups` (every further group the
runtime registered, `register_group`), the kill signals every one of them
and re-reads the record once, and the pin gates the closure alone — an
unpinned or absent bale no longer refuses the abort or the signal.

Session 2026-10-06-twine-clear-group-003: `clear_group` forgets one group
once its run has returned with no survivor, under the writers' lock, and
`clear_running` takes that lock too, so a record the kill removed does not
come back; a cleared group is not signalled by the kill.

Sections:
  1. The between-calls abort
  2. The running record (and its groups; clearing one)
  3. The process-level kill (every recorded group)
  4. The aborted closure
  5. The kill, end to end (the function; the re-read)
  6. `twine kill`, the verb
  7. Guards: one unlock argv, nothing spawned, the stop key
"""

from __future__ import annotations

import ast
import errno
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

from tests.helpers import (PIN, UNLOCK_KEYS, UNLOCK_RECORDED_ABSENT_SID,
                           UNLOCK_RECORDED_READ_ONLY_SID, UNLOCK_RECORDED_SID, RealGroup,
                           RecordedUnlock, StubBale, TempRoots, dies_within, process_alive,
                           run_cli, unlock_recording)

# The session the recorded `aborted` close names (and whose HOLD refusal was
# recorded just before it): a test that wants the closure ok kills it.
SID = UNLOCK_RECORDED_SID
EXE = Path("/double/root/bin/bale")


def executable(path: Path = EXE, installed: str = PIN) -> bale.Executable:
    """A bale.Executable as locate_executable would build it for a root at
    `installed` — a value, not a bale: nothing is run but the double the
    test hands the closure."""
    root = bale.Root(path.parent.parent, "--bale-root", f"--bale-root {path.parent.parent}")
    return bale.Executable(root, path, installed, PIN, f"bin/VERSION reads {installed}")
# bale 0.4.49's HOLD-branch refusal, as recorded for this sid (fixtures/
# bale-0.4.49/scratch/unlock_sid_--json+unlock-refused+hold-branch.json):
# its `message`, which bale also printed on stderr as `[bale] error: <message>`
# — the text twine's kill still reads by its prefix (contract §14.5).
HOLD = unlock_recording("hold-branch")
HOLD_REFUSAL = HOLD.line["message"]
NOT_OPEN = unlock_recording("not-open")


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


# A well-formed record's six keys (brief §2.1): what register_running writes
# and what read_running requires, every one of them.
RECORD_KEYS = ("sid", "pgid", "pid", "started_at", "leader_start_ticks", "groups")
GROUP_KEYS = ("pgid", "leader_start_ticks", "registered_at")


def good_record(**overrides) -> dict:
    """A record that reads, for the malformed-record tests to break one key
    at a time. No process holds 4242 or 4243 for long; nothing signals it."""
    record = {"sid": SID, "pgid": 4242, "pid": 4243, "started_at": "t",
              "leader_start_ticks": None, "groups": []}
    record.update(overrides)
    return record


class RunningRecord(StateCase):

    def test_register_read_clear(self):
        group = self.group()
        rec = kill.register_running(self.state, SID, group.pgid, group.pgid,
                                    clock=lambda: "2026-10-04T01:00:00Z")
        self.assertEqual(rec.path, self.state / "running" / f"{SID}.json")
        written = json.loads(rec.path.read_text())
        self.assertEqual(tuple(written), RECORD_KEYS, "exactly the six keys, in order")
        self.assertEqual(written,
                         {"sid": SID, "pgid": group.pgid, "pid": group.pgid,
                          "started_at": "2026-10-04T01:00:00Z",
                          "leader_start_ticks": process.start_ticks(group.pgid),
                          "groups": []})
        self.assertIsInstance(rec.leader_start_ticks, int)
        self.assertEqual((rec.groups, rec.pgids), ((), [group.pgid]))
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

    def test_register_group_appends_in_order_and_rewrites_durably(self):
        """Session 5c: each registered group is one entry, in registration
        order, with its leader's start ticks read as the runtime's were; the
        runtime's own group is never repeated in `groups`."""
        runtime, first, second = self.group(), self.group(), self.group()
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid,
                              clock=lambda: "2026-10-05T00:00:00Z")
        grown = kill.register_group(self.state, SID, first.pgid,
                                    clock=lambda: "2026-10-05T00:00:01Z")
        self.assertEqual([g.pgid for g in grown.groups], [first.pgid])
        grown = kill.register_group(self.state, SID, second.pgid,
                                    clock=lambda: "2026-10-05T00:00:02Z")
        self.assertEqual(grown.pgids, [runtime.pgid, first.pgid, second.pgid])
        written = json.loads(grown.path.read_text())
        self.assertEqual(tuple(written), RECORD_KEYS)
        self.assertEqual(written["groups"], [
            {"pgid": first.pgid, "leader_start_ticks": process.start_ticks(first.pgid),
             "registered_at": "2026-10-05T00:00:01Z"},
            {"pgid": second.pgid, "leader_start_ticks": process.start_ticks(second.pgid),
             "registered_at": "2026-10-05T00:00:02Z"}])
        for entry in written["groups"]:
            self.assertEqual(tuple(entry), GROUP_KEYS)
            self.assertIsInstance(entry["leader_start_ticks"], int)
        self.assertEqual((written["pgid"], written["started_at"]),
                         (runtime.pgid, "2026-10-05T00:00:00Z"), "the runtime's part stands")
        self.assertEqual(kill.read_running(self.state, SID), grown)
        self.assertEqual(stat.S_IMODE(grown.path.stat().st_mode), 0o600)
        self.assertEqual(sorted(p.name for p in grown.path.parent.iterdir()),
                         [f"{SID}.json"], "no temp file left behind")

    def test_register_group_refuses_without_a_record_to_grow(self):
        """The runtime registers itself before it starts anything."""
        with self.assertRaises(kill.RunningRecordError) as caught:
            kill.register_group(self.state, SID, 4242)
        self.assertIn("no running record", str(caught.exception))
        self.assertIn("register_running", str(caught.exception))
        self.assertTrue(self.state_is_empty(), "nothing written")

    def test_register_group_refuses_the_runtimes_own_group_and_a_non_group(self):
        runtime = self.group()
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        before = kill.running_path(self.state, SID).read_bytes()
        with self.assertRaises(kill.RunningRecordError) as caught:
            kill.register_group(self.state, SID, runtime.pgid)
        self.assertIn("runtime's own", str(caught.exception))
        for pgid in (0, 1, -4, True, "7", None):
            with self.subTest(pgid=pgid), self.assertRaises(kill.RunningRecordError):
                kill.register_group(self.state, SID, pgid)
        self.assertEqual(kill.running_path(self.state, SID).read_bytes(), before,
                         "a refused registration leaves the record as it was")

    def test_concurrent_registrations_all_land(self):
        """The read-append-replace runs under a lock on running/: twenty
        hooks at once register twenty groups, none lost (session 5c's
        review found 3 of 20 landing without it)."""
        import threading
        runtime = self.group()
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        pgids = list(range(100_000, 100_020))
        errors: list[BaseException] = []
        gate = threading.Barrier(len(pgids))

        def register(pgid: int) -> None:
            try:
                gate.wait(5)
                kill.register_group(self.state, SID, pgid)
            except BaseException as exc:  # noqa: BLE001 — reported below
                errors.append(exc)

        threads = [threading.Thread(target=register, args=(p,)) for p in pgids]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(errors, [])
        record = kill.read_running(self.state, SID)
        self.assertEqual(sorted(g.pgid for g in record.groups), pgids)
        self.assertEqual(sorted(p.name for p in record.path.parent.iterdir()),
                         [f"{SID}.json"], "no lock file and no temp file beside the record")

    def test_register_group_refuses_a_malformed_record(self):
        path = kill.running_path(self.state, SID)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(good_record(groups="not an array")))
        with self.assertRaises(kill.RunningRecordError) as caught:
            kill.register_group(self.state, SID, 4244)
        self.assertIn("is not an array", str(caught.exception))

    def test_a_malformed_record_is_named_never_guessed(self):
        path = kill.running_path(self.state, SID)
        path.parent.mkdir(parents=True)
        good = good_record()
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

    def test_a_groups_array_that_is_not_one_is_named_fault_by_fault(self):
        """Session 5c, brief §7: a record without `groups`, or whose groups is
        not an array of entries, is malformed — each fault named. The
        five-key record of session 5b is one such record now."""
        path = kill.running_path(self.state, SID)
        path.parent.mkdir(parents=True)
        entry = {"pgid": 4250, "leader_start_ticks": None, "registered_at": "t"}
        cases = {
            "has no groups key": {k: v for k, v in good_record().items() if k != "groups"},
            "groups 'x' is not an array": good_record(groups="x"),
            "groups {} is not an array": good_record(groups={}),
            "groups[0] 7 is not a group entry": good_record(groups=[7]),
            "groups[0] has no pgid": good_record(
                groups=[{"leader_start_ticks": None, "registered_at": "t"}]),
            "groups[1] pgid 1 is not a process id above 1": good_record(
                groups=[entry, {**entry, "pgid": 1}]),
            "groups[0] pgid 0 is not": good_record(groups=[{**entry, "pgid": 0}]),
            "groups[0] pgid True is not": good_record(groups=[{**entry, "pgid": True}]),
            "groups[0] pgid '4250' is not": good_record(groups=[{**entry, "pgid": "4250"}]),
            "groups[0] leader_start_ticks -1 is not a tick count or null": good_record(
                groups=[{**entry, "leader_start_ticks": -1}]),
            "groups[0] leader_start_ticks 'now' is not": good_record(
                groups=[{**entry, "leader_start_ticks": "now"}]),
            "groups[0] has no registered_at": good_record(
                groups=[{"pgid": 4250, "leader_start_ticks": None}]),
            "groups[0] has no leader_start_ticks": good_record(
                groups=[{"pgid": 4250, "registered_at": "t"}]),
            "groups[0] registered_at None is not a timestamp": good_record(
                groups=[{**entry, "registered_at": None}]),
            "groups[0] registered_at 5 is not a timestamp": good_record(
                groups=[{**entry, "registered_at": 5}]),
            "groups[0] registered_at '' is not a timestamp": good_record(
                groups=[{**entry, "registered_at": ""}]),
        }
        for needle, record in cases.items():
            with self.subTest(needle=needle):
                path.write_text(json.dumps(record))
                with self.assertRaises(kill.RunningRecordError) as caught:
                    kill.read_running(self.state, SID)
                self.assertIn(needle, str(caught.exception))
                self.assertIn(str(path), str(caught.exception))
        # Two faults in one record are both named.
        path.write_text(json.dumps(good_record(pid=1, groups=[{**entry, "pgid": 1}])))
        with self.assertRaises(kill.RunningRecordError) as caught:
            kill.read_running(self.state, SID)
        self.assertIn("pid 1 is not", str(caught.exception))
        self.assertIn("groups[0] pgid 1 is not", str(caught.exception))
        # And a well-formed one with two entries reads as written.
        path.write_text(json.dumps(good_record(groups=[entry, {**entry, "pgid": 4251,
                                                                 "leader_start_ticks": 9}])))
        record = kill.read_running(self.state, SID)
        self.assertEqual(record.groups, (kill.GroupEntry(4250, None, "t"),
                                         kill.GroupEntry(4251, 9, "t")))
        self.assertEqual(record.pgids, [4242, 4250, 4251])


class ClearGroup(StateCase):
    """`clear_group` (session 2026-10-06-twine-clear-group-003): the loop
    forgets a group once its run has returned with no survivor, so the
    record holds what is alive. Brief §2.1's outcomes, one by one, and
    §2.3's with real groups."""

    RUNTIME, PID = 4242, 4243

    def setUp(self):
        super().setUp()
        # An empty /proc: the leaders' start ticks read as null, so the
        # numbers below need no live process behind them.
        self.noproc = self.base / "noproc"
        self.noproc.mkdir()
        self.path = kill.running_path(self.state, SID)
        self._releases: list = []

    def register(self, *pgids: int) -> kill.RunningRecord:
        record = kill.register_running(self.state, SID, self.RUNTIME, self.PID,
                                       clock=lambda: "2026-10-06T00:00:00Z",
                                       proc_root=self.noproc)
        for n, pgid in enumerate(pgids, 1):
            record = kill.register_group(self.state, SID, pgid,
                                         clock=lambda n=n: f"2026-10-06T00:00:{n:02d}Z",
                                         proc_root=self.noproc)
        return record

    def write(self, record: dict) -> bytes:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(record) + "\n").encode()
        self.path.write_bytes(raw)
        return raw

    def entries(self) -> list[dict]:
        return json.loads(self.path.read_text())["groups"]

    # --- True: the entry is gone, the rest as it was ------------------------

    def test_clear_removes_the_one_entry_and_rewrites_as_register_group_does(self):
        before = json.loads(self.register(5001, 5002, 5003).path.read_text())
        self.assertTrue(kill.clear_group(self.state, SID, 5002))
        after = json.loads(self.path.read_text())
        self.assertEqual(tuple(after), RECORD_KEYS, "exactly the six keys, in order")
        for key in RECORD_KEYS[:-1]:
            self.assertEqual(after[key], before[key], f"the runtime's {key} untouched")
        self.assertEqual(after["groups"], [before["groups"][0], before["groups"][2]],
                         "the other entries untouched and in their order")
        for entry in after["groups"]:
            self.assertEqual(tuple(entry), GROUP_KEYS)
        record = kill.read_running(self.state, SID)
        self.assertEqual(record.pgids, [self.RUNTIME, 5001, 5003])
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()),
                         [f"{SID}.json"], "no lock file and no temp file beside the record")
        # The last ones go too; the record stays, naming the runtime alone.
        self.assertTrue(kill.clear_group(self.state, SID, 5001))
        self.assertTrue(kill.clear_group(self.state, SID, 5003))
        self.assertEqual(kill.read_running(self.state, SID).pgids, [self.RUNTIME])
        self.assertEqual(json.loads(self.path.read_text())["groups"], [])

    def test_the_rewrite_is_the_same_durable_replace(self):
        self.register(5001)
        with mock.patch.object(kill, "_write_replacing",
                               wraps=kill._write_replacing) as replacing:
            self.assertTrue(kill.clear_group(self.state, SID, 5001))
        replacing.assert_called_once()
        self.assertEqual(replacing.call_args.args[0], self.path)

    def test_a_pgid_the_record_names_twice_is_forgotten_every_time(self):
        entry = {"pgid": 5001, "leader_start_ticks": None, "registered_at": "t1"}
        other = {"pgid": 5002, "leader_start_ticks": 7, "registered_at": "t2"}
        last = {"pgid": 5003, "leader_start_ticks": None, "registered_at": "t3"}
        self.write(good_record(groups=[entry, other, {**entry, "registered_at": "t4"},
                                       last]))
        self.assertTrue(kill.clear_group(self.state, SID, 5001))
        self.assertEqual(self.entries(), [other, last])

    # --- False: nothing to forget, nothing written --------------------------

    def test_a_group_the_record_does_not_name_is_false_and_nothing_is_written(self):
        self.register(5001)
        for pgid, why in ((5999, "never registered"), (5001, "cleared already")):
            if why == "cleared already":
                self.assertTrue(kill.clear_group(self.state, SID, 5001))
            before, inode = self.path.read_bytes(), self.path.stat().st_ino
            with self.subTest(why=why), \
                    mock.patch.object(kill, "_write_replacing") as replacing:
                self.assertFalse(kill.clear_group(self.state, SID, pgid))
                replacing.assert_not_called()
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(self.path.stat().st_ino, inode, "the file was not replaced")
            self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()),
                             [f"{SID}.json"])

    def test_no_record_is_false_and_creates_nothing(self):
        """A kill may have removed the record under the loop; a session
        between runs has none. No `running/` appears where there was none."""
        self.assertFalse(kill.clear_group(self.state, SID, 5001))
        self.assertTrue(self.state_is_empty(), "no running/ directory created")
        self.assertFalse(kill.clear_group(self.base / "no-such-state", SID, 5001))
        self.assertFalse((self.base / "no-such-state").exists())
        # running/ exists, holding another session's record: still False,
        # and that record untouched.
        other = "2026-10-06-other-001"
        kill.register_running(self.state, other, self.RUNTIME, self.PID,
                              proc_root=self.noproc)
        kill.register_group(self.state, other, 5001, proc_root=self.noproc)
        theirs = kill.running_path(self.state, other).read_bytes()
        self.assertFalse(kill.clear_group(self.state, SID, 5001))
        self.assertEqual(kill.running_path(self.state, other).read_bytes(), theirs)
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()),
                         [f"{other}.json"])

    def test_both_falses_are_logged_at_info(self):
        with self.assertLogs("twine.kill", logging.INFO) as logs:
            self.assertFalse(kill.clear_group(self.state, SID, 5001))
        self.assertIn("nothing to clear", "\n".join(logs.output))
        self.register()
        with self.assertLogs("twine.kill", logging.INFO) as logs:
            self.assertFalse(kill.clear_group(self.state, SID, 5001))
        self.assertTrue(all(line.startswith("INFO:") for line in logs.output))
        self.assertIn("not in it", "\n".join(logs.output))

    # --- refusals: RunningRecordError, the record untouched ------------------

    def test_a_pgid_that_could_not_be_a_group_is_refused_untouched(self):
        self.register(5001)
        before = self.path.read_bytes()
        for pgid in (0, 1, -4, True, False, "5001", None, 5001.0):
            with self.subTest(pgid=pgid), self.assertRaises(kill.RunningRecordError) as caught:
                kill.clear_group(self.state, SID, pgid)
            self.assertIn("is not a process id above 1", str(caught.exception))
        self.assertEqual(self.path.read_bytes(), before)
        # Refused before any record is looked for: nothing is created either.
        empty = self.base / "empty-state"
        empty.mkdir()
        with self.assertRaises(kill.RunningRecordError):
            kill.clear_group(empty, SID, 1)
        self.assertEqual(list(empty.iterdir()), [])

    def test_the_runtimes_own_group_is_refused_untouched(self):
        """It is forgotten with the whole record (clear_running), never one
        entry at a time."""
        self.register(5001)
        before = self.path.read_bytes()
        with self.assertRaises(kill.RunningRecordError) as caught:
            kill.clear_group(self.state, SID, self.RUNTIME)
        self.assertIn("runtime's own", str(caught.exception))
        self.assertIn("clear_running", str(caught.exception))
        self.assertEqual(self.path.read_bytes(), before)

    def test_a_malformed_record_is_refused_untouched_every_fault_named(self):
        entry = {"pgid": 5001, "leader_start_ticks": None, "registered_at": "t"}
        cases = {
            "not a JSON object": b"{nope",
            "has no groups key": json.dumps(
                {k: v for k, v in good_record().items() if k != "groups"}).encode(),
            "groups 'x' is not an array": json.dumps(good_record(groups="x")).encode(),
            "not '" + SID: json.dumps(good_record(sid="2026-10-06-other-001",
                                                  groups=[entry])).encode(),
        }
        for needle, raw in cases.items():
            with self.subTest(needle=needle):
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_bytes(raw)
                with self.assertRaises(kill.RunningRecordError) as caught:
                    kill.clear_group(self.state, SID, 5001)
                self.assertIn(needle, str(caught.exception))
                self.assertEqual(self.path.read_bytes(), raw)
        raw = self.write(good_record(pid=1, groups=[entry, {**entry, "pgid": 1}]))
        with self.assertRaises(kill.RunningRecordError) as caught:
            kill.clear_group(self.state, SID, 5001)
        self.assertIn("pid 1 is not", str(caught.exception))
        self.assertIn("groups[1] pgid 1 is not", str(caught.exception))
        self.assertEqual(self.path.read_bytes(), raw)

    def test_a_record_that_cannot_be_rewritten_is_kill_error_untouched(self):
        self.register(5001)
        before = self.path.read_bytes()
        with mock.patch.object(kill, "_write_replacing",
                               side_effect=OSError(28, "No space left on device")), \
                self.assertRaises(kill.KillError) as caught:
            kill.clear_group(self.state, SID, 5001)
        self.assertIn("No space left", str(caught.exception))
        self.assertEqual(self.path.read_bytes(), before)

    def test_a_sid_that_is_not_one_is_refused(self):
        with self.assertRaises(ValueError):
            kill.clear_group(self.state, "../escape", 5001)
        self.assertTrue(self.state_is_empty())

    # --- the lock -----------------------------------------------------------

    def hold_the_lock(self):
        """Take the writers' lock on running/ the way another process would:
        its own open file description, an exclusive flock. Returns release."""
        import fcntl
        fd = os.open(self.path.parent, os.O_RDONLY)
        fcntl.flock(fd, fcntl.LOCK_EX)
        released = []

        def release():
            if not released:
                released.append(True)
                os.close(fd)
        self.addCleanup(release)
        self._releases.append(release)
        return release

    def in_a_thread(self, fn, *args):
        import threading
        out: dict = {}
        done = threading.Event()

        def body():
            try:
                out["value"] = fn(*args)
            except BaseException as exc:  # noqa: BLE001 — asserted by the caller
                out["error"] = exc
            finally:
                done.set()
        thread = threading.Thread(target=body)
        thread.start()

        def release_then_join():
            # A failed assertion may leave the lock held: let go of it first,
            # or the join would wait out its timeout behind the test's own lock.
            for release in self._releases:
                release()
            thread.join(30)
        self.addCleanup(release_then_join)
        return done, out

    def test_clear_group_waits_for_the_lock_register_group_takes(self):
        self.register(5001)
        release = self.hold_the_lock()
        done, out = self.in_a_thread(kill.clear_group, self.state, SID, 5001)
        self.assertFalse(done.wait(0.3), "clear_group ran while the lock was held")
        self.assertEqual([e["pgid"] for e in self.entries()], [5001])
        release()
        self.assertTrue(done.wait(10))
        self.assertEqual(out, {"value": True})
        self.assertEqual(self.entries(), [])

    def test_concurrent_registrations_and_clears_lose_nothing(self):
        """Twenty writers at once — ten clears of groups already recorded,
        ten registrations of new ones: afterwards the record names exactly
        the groups registered and not cleared, the survivors of the first
        batch still in their order, ahead of the new ones."""
        import threading
        kept, doomed = [5001, 5003, 5005], list(range(6000, 6010))
        self.register(5001, *doomed[:5], 5003, *doomed[5:], 5005)
        fresh = list(range(7000, 7010))
        errors: list[BaseException] = []
        results: list[bool] = []
        gate = threading.Barrier(len(doomed) + len(fresh))

        def clear(pgid: int) -> None:
            try:
                gate.wait(5)
                results.append(kill.clear_group(self.state, SID, pgid))
            except BaseException as exc:  # noqa: BLE001 — reported below
                errors.append(exc)

        def register(pgid: int) -> None:
            try:
                gate.wait(5)
                kill.register_group(self.state, SID, pgid, proc_root=self.noproc)
            except BaseException as exc:  # noqa: BLE001 — reported below
                errors.append(exc)

        threads = ([threading.Thread(target=clear, args=(p,)) for p in doomed]
                   + [threading.Thread(target=register, args=(p,)) for p in fresh])
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(errors, [])
        self.assertEqual(results, [True] * len(doomed))
        pgids = [g.pgid for g in kill.read_running(self.state, SID).groups]
        self.assertEqual(pgids[:3], kept, "the uncleared survivors, in their order")
        self.assertEqual(sorted(pgids[3:]), fresh, "every new registration landed")
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()),
                         [f"{SID}.json"])

    # --- a record twine kill has removed does not come back ----------------

    def test_the_kills_removal_waits_for_a_clear_between_its_read_and_its_replace(self):
        """Staged deterministically: clear_group has read the record and is
        about to replace it when twine kill's clear_running arrives. The
        removal cannot slip in between (bounded here to 0.2 s, it gives up
        rather than remove), so the replace never re-creates a removed file;
        and once the clear is done, the removal lands and the record stays
        gone."""
        self.register(5001, 5002)
        real_replace = kill._write_replacing
        staged: dict = {}

        def the_kill_arrives_first(path, data):
            try:
                staged["cleared"] = kill.clear_running(self.state, SID)
            except kill.KillError as exc:
                staged["error"] = exc
            return real_replace(path, data)

        with mock.patch.object(kill, "CLEAR_LOCK_SECONDS", 0.2), \
                mock.patch.object(kill, "_write_replacing",
                                  side_effect=the_kill_arrives_first):
            self.assertTrue(kill.clear_group(self.state, SID, 5001))
        self.assertNotIn("cleared", staged, "the removal slipped between read and replace")
        self.assertEqual(staged["error"].errno, errno.EWOULDBLOCK)
        self.assertEqual([e["pgid"] for e in self.entries()], [5002])
        self.assertTrue(kill.clear_running(self.state, SID))
        self.assertFalse(self.path.exists())
        self.assertFalse(kill.clear_group(self.state, SID, 5002))
        self.assertFalse(self.path.exists(), "a clear after the removal re-creates nothing")
        self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_a_removal_racing_a_clear_is_never_undone(self):
        """The race with an unbounded wait: twine kill's clear_running starts
        while clear_group holds the record it read. Whatever the order, the
        record is gone at the end — the removal waits for the replace, then
        removes what it wrote."""
        self.register(5001)
        real_read = kill.read_running
        race: dict = {}

        def read_then_the_kill_clears(state_dir, sid):
            record = real_read(state_dir, sid)
            race["done"], race["out"] = self.in_a_thread(kill.clear_running, self.state, SID)
            self.assertFalse(race["done"].wait(0.3), "the removal did not wait for the lock")
            return record

        with mock.patch.object(kill, "read_running", side_effect=read_then_the_kill_clears):
            self.assertTrue(kill.clear_group(self.state, SID, 5001))
        self.assertTrue(race["done"].wait(10))
        self.assertEqual(race["out"], {"value": True})
        self.assertFalse(self.path.exists(), "the removed record came back")

    def test_a_kill_that_cannot_have_the_lock_leaves_the_record_and_still_closes(self):
        """The bound on clear_running's wait: a writer wedged holding the
        lock (here, the test) does not hang `twine kill`. The groups are
        gone, so the closure lands; the record — a cache — is left, and
        `record_cleared` says so."""
        runtime = self.group()
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        self.hold_the_lock()
        with mock.patch.object(kill, "CLEAR_LOCK_SECONDS", 0.2):
            report = kill.kill_session(self.state, SID, run=RecordedUnlock(),
                                       executable=executable(), cwd=self.repo, env={},
                                       grace=2)
        self.assertTrue(report.ok, report.reason)
        self.assertEqual((report.process.dead, report.process.record_cleared), (True, False))
        self.assertTrue(self.path.exists())
        for pid in runtime.pids:
            self.assertTrue(dies_within(pid), f"{pid} outlived the kill")

    def test_a_filesystem_that_refuses_the_lock_runs_unlocked_and_the_kill_finishes(self):
        """flock failing outright (ENOLCK, as on some network mounts) is the
        lock being unavailable, not a fault: logged, and the writers and the
        kill's removal go on unlocked, as they did before any lock existed."""
        runtime = self.group()
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        refused = OSError(errno.ENOLCK, "No locks available")
        with mock.patch.object(kill.fcntl, "flock", side_effect=refused), \
                self.assertLogs("twine.kill", logging.WARNING) as logs:
            kill.register_group(self.state, SID, 5001, proc_root=self.noproc)
            self.assertTrue(kill.clear_group(self.state, SID, 5001))
            report = kill.kill_session(self.state, SID, run=RecordedUnlock(),
                                       executable=executable(), cwd=self.repo, env={},
                                       grace=2)
        self.assertTrue(report.ok, report.reason)
        self.assertEqual([s.pgid for s in report.process.steps], [runtime.pgid])
        self.assertTrue(report.process.record_cleared)
        self.assertFalse(self.path.exists())
        self.assertIn("No locks available", "\n".join(logs.output))

    # --- §2.3: the kill signals what the record still names -----------------

    def test_a_cleared_group_is_not_signalled_by_the_kill(self):
        """A real group registered, then cleared, is alive after `twine kill`
        finishes with every other recorded group dead; the twin's
        `process.groups` lists only what the record still named."""
        runtime, tool_a, cleared, tool_b = (self.group(), self.group(), self.group(),
                                            self.group())
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        for g in (tool_a, cleared, tool_b):
            kill.register_group(self.state, SID, g.pgid)
        self.assertTrue(kill.clear_group(self.state, SID, cleared.pgid))
        report = kill.kill_session(self.state, SID, run=RecordedUnlock(),
                                   executable=executable(), cwd=self.repo, env={}, grace=2)
        self.assertTrue(report.ok, report.reason)
        for pid in runtime.pids + tool_a.pids + tool_b.pids:
            self.assertTrue(dies_within(pid), f"{pid} outlived the kill")
        for pid in cleared.pids:
            self.assertTrue(process_alive(pid), f"{pid} of the cleared group was signalled")
        twin = report.as_json()["process"]
        self.assertEqual([g["pgid"] for g in twin["groups"]], [tool_a.pgid, tool_b.pgid])
        self.assertEqual([s.pgid for s in report.process.steps],
                         [runtime.pgid, tool_a.pgid, tool_b.pgid])

    def test_the_loops_composition_register_on_spawn_clear_on_a_clean_return(self):
        """The rule contract §14.4 writes for the Arc 2 loop, composed by
        hand: the hook registers the tool's group the moment it exists, and
        the loop clears it once `run` returns with no survivor — leaving the
        record naming the runtime alone."""
        runtime = self.group()
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        seen: list[int] = []

        def hook(pid: int) -> None:
            seen.append(pid)
            kill.register_group(self.state, SID, pid)

        # The child waits for a line on stdin, which the seam feeds only
        # after the hook has returned: it reads the record once registered.
        result = process.run_process(["/bin/sh", "-c", f"read -r go; cat {self.path}"],
                                     stdin=b"go\n", timeout=10, on_spawn=hook)
        self.assertEqual(result.exit_code, 0, result.stderr)
        self.assertEqual([g["pgid"] for g in json.loads(result.stdout)["groups"]], seen,
                         "registered while it ran")
        self.assertEqual(result.group_survivors, ())
        self.assertTrue(kill.clear_group(self.state, SID, seen[0]))
        self.assertEqual(kill.read_running(self.state, SID).pgids, [runtime.pgid])


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

    # --- every recorded group (session 5c) ---------------------------------

    def with_groups(self, runtime: RealGroup, *more: RealGroup) -> kill.RunningRecord:
        record = kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        for group in more:
            record = kill.register_group(self.state, SID, group.pgid)
        return record

    def test_every_recorded_group_is_killed_the_runtimes_first(self):
        """Three real groups — the runtime's, one that honours SIGTERM, one
        that ignores it — all gone, each with its own signals, in order."""
        runtime = self.group()
        polite = self.group()
        stubborn = self.group(body='trap "" TERM; sleep 60 & echo $!; sleep 60 & echo $!; wait')
        sent: list[tuple[int, int]] = []
        real_signal = process.signal_group

        def spy(pgid, signum):
            sent.append((pgid, signum))
            return real_signal(pgid, signum)

        with mock.patch.object(process, "signal_group", side_effect=spy):
            step = kill.kill_group(self.with_groups(runtime, polite, stubborn),
                                   grace=0.4, wait=5)
        self.assertEqual((step.dead, step.survivors, step.error), (True, [], None))
        self.assertEqual([s.pgid for s in step.steps],
                         [runtime.pgid, polite.pgid, stubborn.pgid])
        self.assertEqual([g.pgid for g in step.groups], [polite.pgid, stubborn.pgid])
        self.assertEqual(step.signals, ["SIGTERM", "SIGCONT"], "the runtime's")
        self.assertEqual([g.signals for g in step.groups],
                         [["SIGTERM", "SIGCONT"], ["SIGTERM", "SIGCONT", "SIGKILL"]])
        self.assertEqual([pgid for pgid, _ in sent][:2], [runtime.pgid] * 2,
                         "the runtime's group is signalled first")
        self.assertLess(max(i for i, (p, _) in enumerate(sent) if p == polite.pgid),
                        min(i for i, (p, _) in enumerate(sent) if p == stubborn.pgid),
                        "then record order")
        for pid in runtime.pids + polite.pids + stubborn.pids:
            self.assertTrue(dies_within(pid), f"{pid} outlived the kill")
        twin = step.as_json()
        self.assertEqual([tuple(g) for g in twin["groups"]],
                         [("pgid", "signalled", "signals", "dead", "survivors", "stale")] * 2)
        self.assertEqual((twin["dead"], twin["survivors"], twin["signals"]),
                         (True, [], ["SIGTERM", "SIGCONT"]))

    def test_dead_is_the_whole_and_survivors_span_every_group(self):
        """One additional group will not die (a double): the step is not
        done, `survivors` is every surviving pid across the groups, sorted,
        and the error names the group."""
        rec = kill.RunningRecord(SID, 4242, 4242, "t", None, kill.running_path(self.state, SID),
                                 (kill.GroupEntry(4300, None, "t"),
                                  kill.GroupEntry(4400, None, "t")))
        alive = {4242: [], 4300: [4300, 4310], 4400: []}
        sent = []
        with mock.patch.object(process, "group_members", side_effect=lambda g, r: alive[g]), \
                mock.patch.object(process, "signal_group",
                                  side_effect=lambda g, s: sent.append((g, s))):
            step = kill.kill_group(rec, grace=0.05, wait=0.05)
        self.assertEqual(sent, [(4300, signal.SIGTERM), (4300, signal.SIGCONT),
                                (4300, signal.SIGKILL)], "only the live group is signalled")
        self.assertEqual((step.runtime.dead, step.dead, step.survivors), (True, False, [4300, 4310]))
        self.assertEqual([(g.pgid, g.dead, g.survivors) for g in step.groups],
                         [(4300, False, [4300, 4310]), (4400, True, [])])
        self.assertEqual(step.alive_groups, [4300])
        self.assertIn("process group 4300 still has live members", step.error)
        self.assertEqual(step.signals, [], "the runtime's group needed nothing")
        self.assertEqual(step.as_json()["groups"][0]["survivors"], [4300, 4310])

    def test_the_stale_check_is_per_group_on_its_own_ticks(self):
        """A group whose number now leads another process is gone and not
        touched; the group beside it is still killed."""
        runtime, reused, live = self.group(), self.group(), self.group()
        record = self.with_groups(runtime, reused, live)
        entries = list(record.groups)
        entries[0] = kill.GroupEntry(reused.pgid, entries[0].leader_start_ticks + 1, "t")
        record = kill.RunningRecord(SID, record.pgid, record.pid, record.started_at,
                                    record.leader_start_ticks, record.path, tuple(entries))
        step = kill.kill_group(record, grace=2, wait=2)
        self.assertEqual((step.dead, step.stale), (True, False), "the runtime's was real")
        self.assertEqual([(g.pgid, g.stale, g.dead, g.signals) for g in step.groups],
                         [(reused.pgid, True, True, []),
                          (live.pgid, False, True, ["SIGTERM", "SIGCONT"])])
        for pid in reused.pids:
            self.assertTrue(process_alive(pid), f"{pid} was signalled on a stale entry")
        for pid in runtime.pids + live.pids:
            self.assertTrue(dies_within(pid), f"{pid} outlived the kill")

    def test_twine_kills_own_group_stops_the_step_before_the_other_groups(self):
        """The runtime's group is twine kill's own: nothing is signalled, not
        the groups after it either — the runtime that could start more is
        not stopped, and the run from another shell takes them all."""
        own = os.getpgrp()
        tool = self.group()
        rec = kill.RunningRecord(SID, own, own, "t", None, kill.running_path(self.state, SID),
                                 (kill.GroupEntry(tool.pgid, None, "t"),))
        with mock.patch.object(process, "signal_group",
                               side_effect=AssertionError("signalled")):
            step = kill.kill_group(rec, grace=0, wait=0)
        self.assertEqual((step.dead, step.groups, step.runtime.refused), (False, [], True))
        self.assertIn("twine kill's own", step.error)
        self.assertEqual(step.alive_groups, [own])
        for pid in tool.pids:
            self.assertTrue(process_alive(pid), f"{pid} was signalled past the refusal")

    def test_a_group_recorded_twice_is_signalled_once(self):
        """A pgid already handled is not signalled again: by then its
        number could lead a stranger's group."""
        rec = kill.RunningRecord(SID, 4242, 4242, "t", None, kill.running_path(self.state, SID),
                                 (kill.GroupEntry(4300, None, "t"),
                                  kill.GroupEntry(4300, None, "t"),
                                  kill.GroupEntry(4242, None, "t")))
        with mock.patch.object(process, "group_members", return_value=[]), \
                mock.patch.object(process, "signal_group",
                                  side_effect=AssertionError("signalled")):
            step = kill.kill_group(rec)
        self.assertEqual([g.pgid for g in step.groups], [4300])
        self.assertTrue(step.dead)


# ---------------------------------------------------------------------------
# 4. The aborted closure
# ---------------------------------------------------------------------------


class AbortedClosure(StateCase):

    def close(self, runner, exe=None):
        return kill.close_aborted(runner, exe or executable(), SID, cwd=self.repo,
                                  env={"X": "1"})

    def test_the_one_argv_once(self):
        runner = RecordedUnlock()
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
        """The recorded not-open refusal (bale 0.4.49: exit 1, the
        `unlock-refused` line on stdout, `[bale] error: <message>` on
        stderr): not ok, bale's stderr reason named first, then what the
        line said instead of this close — its outcome, its sid (the one
        that was never open) and its null closure reason. The line is kept
        as bale's one JSON object (contract §14.6's `closure`)."""
        runner = RecordedUnlock(NOT_OPEN)
        closure = self.close(runner)
        self.assertFalse(closure.ok)
        self.assertEqual(len(runner.calls), 1, "a closure is never retried")
        self.assertEqual(closure.failures, [
            f"bale exited 1: [bale] error: session {UNLOCK_RECORDED_ABSENT_SID} is not open; "
            "nothing to unlock. No sessions are open.",
            "bale reported outcome 'unlock-refused', not 'unlocked'",
            f"bale reported sid {UNLOCK_RECORDED_ABSENT_SID!r}, not {SID!r}",
            "bale reported closure_reason None, not 'aborted'"])
        self.assertEqual(closure.operator_line, f"bale unlock {SID} --reason aborted")
        self.assertEqual(closure.unlock, NOT_OPEN.line)
        self.assertEqual((closure.unlock["reason"], closure.exit_code), ("not-open", 1))

    def test_the_hold_branch_refusal_hands_back_bales_own_remedy(self):
        """Row 17 of the 0.4.49 recordings: bale refused to unlock the
        session whose response had reached HOLD. Twine still keys the hand
        line on the stderr prefix `branch bale/<sid> exists`, which the
        recording's stderr carries; the line's `reason` is `hold-branch`
        (keying on it is the next session's)."""
        runner = RecordedUnlock(HOLD)
        closure = self.close(runner)
        self.assertFalse(closure.ok)
        self.assertTrue(closure.hold_branch)
        self.assertTrue(closure.stderr.startswith(f"[bale] error: branch bale/{SID} exists"))
        self.assertEqual((closure.unlock["reason"], closure.unlock["outcome"]),
                         ("hold-branch", "unlock-refused"))
        self.assertEqual(closure.operator_line, f"bale revert {SID}")
        self.assertEqual(len(runner.calls), 1)

    def test_a_line_that_is_not_this_close_is_not_ok(self):
        """Two recorded lines that are not this close — the no-op with
        nothing open (row 20) and the read-only session's close (row 19,
        another sid, closure reason `closed-read-only`) — and two stdouts
        that are no bale line at all."""
        read_only = unlock_recording("closed-read-only")
        cases = {
            "outcome 'no-op'": RecordedUnlock("no-op"),
            f"sid {UNLOCK_RECORDED_READ_ONLY_SID!r}": RecordedUnlock(read_only),
            "closure_reason 'closed-read-only'": RecordedUnlock(read_only),
            "not one JSON object (it began 'unlocked')": RecordedUnlock(stdout=b"unlocked\n"),
            "not one JSON object (it was empty)": RecordedUnlock(stdout=b""),
        }
        for needle, runner in cases.items():
            with self.subTest(needle=needle):
                closure = self.close(runner)
                self.assertFalse(closure.ok)
                self.assertEqual(closure.exit_code, 0)
                self.assertIn(needle, "; ".join(closure.failures))
                self.assertEqual(closure.operator_line,
                                 f"bale unlock {SID} --reason aborted")

    def test_a_timeout_is_not_ok_and_not_retried(self):
        runner = RecordedUnlock(timed_out=True)
        closure = self.close(runner)
        self.assertFalse(closure.ok)
        self.assertEqual(len(runner.calls), 1)
        self.assertIn("may or may not have closed", closure.failures[0])

    def test_an_unpinned_bale_is_never_started(self):
        """The closure checks the pin itself, so the loop cannot reach an
        unpinned bale by forgetting the gate."""
        runner = RecordedUnlock()
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
        runner = runner if runner is not None else RecordedUnlock()
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
        report, runner = self.kill(RecordedUnlock(HOLD))
        self.assertEqual((report.ok, report.stopped_at, report.closed),
                         (False, "closure", False))
        self.assertEqual(report.operator_line, f"bale revert {SID}")
        self.assertIn("twine never runs it", report.reason)
        self.assertEqual(report.as_json()["stderr"], HOLD.stderr.decode())
        self.assertEqual(report.as_json()["closure"], HOLD.line)

    # --- every recorded group, and the re-read (session 5c) ----------------

    def test_every_recorded_group_is_killed_before_the_closure(self):
        runtime, tool_a, tool_b = self.group(), self.group(), self.group()
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        kill.register_group(self.state, SID, tool_a.pgid)
        kill.register_group(self.state, SID, tool_b.pgid)
        report, runner = self.kill(grace=2)
        self.assertTrue(report.ok, report.reason)
        self.assertEqual([s.pgid for s in report.process.steps],
                         [runtime.pgid, tool_a.pgid, tool_b.pgid])
        self.assertEqual((report.process.dead, report.process.record_cleared), (True, True))
        self.assertIsNone(kill.read_running(self.state, SID))
        self.assertEqual(len(runner.calls), 1)
        for pid in runtime.pids + tool_a.pids + tool_b.pids:
            self.assertTrue(dies_within(pid), f"{pid} outlived the kill")

    def test_the_hand_line_names_every_group_with_survivors(self):
        """Brief §2.3: `kill -KILL -- -<pgid> -<pgid> …`, the runtime's first,
        then record order — only the groups not known to be gone."""
        rec = kill.RunningRecord(SID, 4242, 4242, "t", None, kill.running_path(self.state, SID),
                                 (kill.GroupEntry(4300, None, "t"),
                                  kill.GroupEntry(4400, None, "t"),
                                  kill.GroupEntry(4500, None, "t")))
        alive = {4242: [4242], 4300: [], 4400: [4401], 4500: [4500, 4501]}
        with mock.patch.object(kill, "read_running", return_value=rec), \
                mock.patch.object(process, "group_members", side_effect=lambda g, r: alive[g]), \
                mock.patch.object(process, "signal_group", return_value=None):
            report, runner = self.kill(grace=0, wait=0)
        self.assertEqual(runner.calls, [], "no closure while a member lives")
        self.assertEqual((report.stopped_at, report.operator_line),
                         ("process", "kill -KILL -- -4242 -4400 -4500"))
        twin = report.as_json()["process"]
        self.assertEqual((twin["dead"], twin["survivors"]), (False, [4242, 4401, 4500, 4501]))
        self.assertEqual([g["pgid"] for g in twin["groups"]], [4300, 4400, 4500])
        self.assertEqual([g["dead"] for g in twin["groups"]], [True, False, False])
        self.assertFalse(twin["record_cleared"], "a record whose groups live stays")
        # The runtime's group gone, one tool's alive: only the tool is named.
        alive = {4242: [], 4300: [], 4400: [4401], 4500: []}
        with mock.patch.object(kill, "read_running", return_value=rec), \
                mock.patch.object(process, "group_members", side_effect=lambda g, r: alive[g]), \
                mock.patch.object(process, "signal_group", return_value=None):
            report, runner = self.kill(grace=0, wait=0)
        self.assertEqual(report.operator_line, "kill -KILL -- -4400")
        self.assertEqual(runner.calls, [])

    def test_a_group_registered_during_the_kill_is_killed_on_the_re_read(self):
        """A hook racing the kill: after the first read, one more group is
        registered. The one re-read finds it; it is killed too, the record
        then cleared, the closure attempted once."""
        runtime, early, late = self.group(), self.group(), self.group()
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        kill.register_group(self.state, SID, early.pgid)
        real_kill_group = kill.kill_group

        def kill_group_then_a_hook_fires(record, **kwargs):
            step = real_kill_group(record, **kwargs)
            kill.register_group(self.state, SID, late.pgid)
            return step

        with mock.patch.object(kill, "kill_group", side_effect=kill_group_then_a_hook_fires):
            report, runner = self.kill(grace=2)
        self.assertTrue(report.ok, report.reason)
        self.assertEqual([s.pgid for s in report.process.steps],
                         [runtime.pgid, early.pgid, late.pgid])
        self.assertEqual(report.process.groups[-1].signals, ["SIGTERM", "SIGCONT"])
        self.assertTrue(report.process.record_cleared)
        self.assertIsNone(kill.read_running(self.state, SID))
        self.assertEqual(len(runner.calls), 1)
        for pid in runtime.pids + early.pids + late.pids:
            self.assertTrue(dies_within(pid), f"{pid} outlived the kill")
        twin = report.as_json()["process"]
        self.assertEqual([g["pgid"] for g in twin["groups"]], [early.pgid, late.pgid])

    def test_the_re_read_happens_once_and_only_after_the_groups_are_gone(self):
        """Two reads of the record in all: the first, and the one re-read
        once its groups are dead. A kill that stops with survivors re-reads
        nothing — it is not finished, and reads again when run again."""
        runtime = self.group()
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        real_read = kill.read_running
        reads = []
        with mock.patch.object(kill, "read_running",
                               side_effect=lambda *a: (reads.append(a), real_read(*a))[1]):
            report, _ = self.kill(grace=2)
        self.assertTrue(report.ok, report.reason)
        self.assertEqual(len(reads), 2)
        rec = kill.RunningRecord(SID, 4242, 4242, "t", None, kill.running_path(self.state, SID))
        reads.clear()
        with mock.patch.object(kill, "read_running",
                               side_effect=lambda *a: (reads.append(a), rec)[1]), \
                mock.patch.object(process, "group_members", return_value=[4242]), \
                mock.patch.object(process, "signal_group", return_value=None):
            report, _ = self.kill(grace=0, wait=0)
        self.assertEqual((report.stopped_at, len(reads)), ("process", 1))

    def test_a_record_that_turns_malformed_under_the_kill_stops_it(self):
        """The re-read finds a record that no longer reads: the groups killed
        so far are gone, but a group registered meanwhile may be unknown, so
        the step is not done, the record is left, and no close is handed out."""
        runtime = self.group()
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        real_kill_group = kill.kill_group
        path = kill.running_path(self.state, SID)

        def kill_group_then_the_record_breaks(record, **kwargs):
            step = real_kill_group(record, **kwargs)
            path.write_text("{broken")
            return step

        with mock.patch.object(kill, "kill_group", side_effect=kill_group_then_the_record_breaks):
            report, runner = self.kill(grace=2)
        self.assertEqual((report.ok, report.stopped_at, runner.calls), (False, "process", []))
        self.assertTrue(report.process.runtime.dead)
        self.assertFalse(report.process.dead)
        self.assertIn("changed under the kill", report.reason)
        self.assertIsNone(report.operator_line)
        self.assertTrue(path.exists(), "left for the operator")
        self.assertFalse(report.process.record_cleared)

    def test_a_record_removed_under_the_kill_is_nothing_more_to_do(self):
        runtime = self.group()
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        real_kill_group = kill.kill_group

        def kill_group_then_the_runtime_clears(record, **kwargs):
            step = real_kill_group(record, **kwargs)
            kill.clear_running(self.state, SID)
            return step

        with mock.patch.object(kill, "kill_group", side_effect=kill_group_then_the_runtime_clears):
            report, runner = self.kill(grace=2)
        self.assertTrue(report.ok, report.reason)
        self.assertFalse(report.process.record_cleared, "someone else did")
        self.assertEqual(len(runner.calls), 1)


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
        runner = runner if runner is not None else RecordedUnlock()
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
        self.assertEqual(obj["closure"], unlock_recording("aborted").line)
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
        report = kill.kill_session(other, SID, run=RecordedUnlock(), executable=exe,
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
                runner = RecordedUnlock()
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

    def test_a_state_directory_that_cannot_be_looked_at_is_a_refusal_not_a_traceback(self):
        """Session 5c's review: no search permission on a parent is a named
        refusal, as a missing directory is — and nothing is done."""
        with mock.patch("os.stat", side_effect=PermissionError(13, "Permission denied")):
            fault = kill_verb.state_dir_fault(self.state)
        self.assertEqual(fault, "cannot be read (Permission denied)")
        self.assertEqual((kill_verb.state_dir_fault(self.state),
                          kill_verb.state_dir_fault(self.base / "absent"),
                          kill_verb.state_dir_fault(self.roots.ok / "bin" / "VERSION")),
                         (None, "does not exist", "is not a directory"))
        if os.geteuid() == 0:
            self.skipTest("root bypasses mode bits; the verb's path cannot be made unreadable")
        parent = self.base / "private"
        (parent / "state").mkdir(parents=True)
        parent.chmod(0)
        # tearDown removes the temp tree first (it copes with the mode), so
        # the restore only applies when the directory is still there.
        self.addCleanup(lambda: parent.exists() and parent.chmod(0o700))
        out = io.StringIO()
        runner = RecordedUnlock()
        ctx = Context(env={}, stdout=out, stderr=io.StringIO(), which=lambda n: None,
                      stdin=io.BytesIO(b""), run=runner)
        code = main(["kill", SID, "--state-dir", str(parent / "state"), "--cwd",
                     str(self.repo), "--bale-root", str(self.roots.ok), "--json"], ctx=ctx)
        obj = json.loads(out.getvalue())
        self.assertEqual((code, obj["stopped_at"], runner.calls), (1, "refused", []))
        self.assertIn("cannot be read", obj["reason"])

    def test_a_current_directory_that_is_gone_is_a_refusal_not_a_traceback(self):
        gone = self.base / "gone"
        gone.mkdir()
        here = os.getcwd()
        os.chdir(gone)
        try:
            gone.rmdir()
            out = io.StringIO()
            ctx = Context(env={}, stdout=out, stderr=io.StringIO(), which=lambda n: None,
                          stdin=io.BytesIO(b""), run=RecordedUnlock())
            code = main(["kill", SID, "--state-dir", str(self.state), "--bale-root",
                         str(self.roots.ok), "--json"], ctx=ctx)
        finally:
            os.chdir(here)
        obj = json.loads(out.getvalue())
        self.assertEqual((code, obj["stopped_at"]), (1, "refused"))
        self.assertIn("current directory cannot be resolved", obj["reason"])

    def test_no_state_directory_is_refused(self):
        out, err = io.StringIO(), io.StringIO()
        runner = RecordedUnlock()
        ctx = Context(env={}, stdout=out, stderr=err, which=lambda n: None,
                      stdin=io.BytesIO(b""), run=runner)
        code = main(["kill", SID, "--cwd", str(self.repo), "--bale-root",
                     str(self.roots.ok), "--json"], ctx=ctx)
        obj = json.loads(out.getvalue())
        self.assertEqual((code, obj["stopped_at"], obj["state_dir"]), (1, "refused", None))
        self.assertIn("cannot resolve twine's state directory", obj["reason"])
        self.assertEqual(runner.calls, [])

    def test_the_pin_gates_the_closure_alone(self):
        """Session 5c, the sitting's correction to 5b: a bale that is not the
        pin, or is absent, is not a refusal. The abort request is written, a
        real group is killed, bale is never reached (the run-seam double
        records no call), and the kill stops at the closure with the drive
        refusal in `reason`, the unlock line to finish by hand, and the
        `bale` object saying what was found."""
        for root, found in ((self.roots.other, "0.4.46"), (self.roots.absent, None),
                            (self.base / "no-such-root", None)):
            with self.subTest(root=root.name):
                for sub in ("abort", "running"):
                    if (self.state / sub).is_dir():
                        for stale in (self.state / sub).iterdir():
                            stale.unlink()
                group = self.group()
                kill.register_running(self.state, SID, group.pgid, group.pgid)
                out = io.StringIO()
                runner = RecordedUnlock()
                ctx = Context(env={}, stdout=out, stderr=io.StringIO(),
                              which=lambda n: None, stdin=io.BytesIO(b""), run=runner)
                code = main(["kill", SID, "--state-dir", str(self.state), "--cwd",
                             str(self.repo), "--bale-root", str(root), "--grace", "2",
                             "--json"], ctx=ctx)
                obj = json.loads(out.getvalue())
                self.assertEqual((code, obj["ok"], obj["stopped_at"], obj["closed"],
                                  obj["refusals"]),
                                 (1, False, "closure", False, []))
                self.assertEqual(runner.calls, [], "bale is never reached")
                self.assertEqual((obj["ran"], obj["argv"], obj["closure"]), (False, None, None))
                self.assertIn("pinned bale", obj["reason"])
                self.assertEqual(obj["operator_line"], f"bale unlock {SID} --reason aborted")
                self.assertTrue(obj["abort_requested"])
                self.assertTrue(kill.abort_requested(self.state, SID))
                self.assertEqual((obj["process"]["dead"], obj["process"]["record_cleared"]),
                                 (True, True))
                for pid in group.pids:
                    self.assertTrue(dies_within(pid), f"{pid} outlived the kill")
                self.assertEqual((obj["bale"]["installed"], obj["bale"]["pin_matches"]),
                                 (found, False if found else None))
                self.assertEqual(obj["bale"]["root"], str(root), "what --bale-root named")

    def test_an_unpinned_bale_renders_not_finished_at_the_closure(self):
        code, out, err, runner = self.run_verb("--bale-root", str(self.roots.other))
        self.assertEqual((code, runner.calls), (1, []))
        lines = out.splitlines()
        self.assertIn("NOT FINISHED (stopped at closure)", lines[0])
        self.assertTrue(any(l.strip().startswith("abort:   requested") for l in lines), out)
        self.assertIn("closure: NOT CLOSED", out)
        self.assertIn("not the pin", out)
        self.assertIn(f"finish by hand: bale unlock {SID} --reason aborted", out)
        self.assertIn("the abort and the process kill go ahead; the closure will not", err)

    def test_a_pinned_bale_closes_as_before(self):
        group = self.group()
        kill.register_running(self.state, SID, group.pgid, group.pgid)
        code, obj, err, runner = self.json_of("--grace", "2")
        self.assertEqual((code, obj["ok"], obj["closed"], obj["bale"]["pin_matches"]),
                         (0, True, True, True))
        self.assertEqual(len(runner.calls), 1)
        for pid in group.pids:
            self.assertTrue(dies_within(pid), f"{pid} outlived the kill")

    def test_every_path_carries_the_same_keys(self):
        ok = self.json_of()[1]
        refused = self.json_of("--grace", "x")[1]
        closure_refused = self.json_of(runner=RecordedUnlock(NOT_OPEN))[1]
        unpinned = self.json_of("--bale-root", str(self.roots.other))[1]
        with mock.patch.object(process, "group_members", return_value=[4242]), \
                mock.patch.object(process, "signal_group", return_value=None):
            rec = kill.RunningRecord(SID, 4242, 4242, "t", None,
                                     kill.running_path(self.state, SID))
            with mock.patch.object(kill, "read_running", return_value=rec):
                survivors = self.json_of("--grace", "0")[1]
        for obj in (refused, closure_refused, unpinned, survivors):
            self.assertEqual(set(obj), set(ok))
        self.assertEqual(set(survivors["process"]),
                         {"pgid", "pid", "started_at", "signalled", "signals", "dead",
                          "survivors", "stale", "groups", "record_cleared", "record", "error"})
        self.assertEqual(survivors["process"]["signals"], ["SIGTERM", "SIGCONT", "SIGKILL"])
        self.assertEqual(survivors["process"]["groups"], [])
        self.assertEqual((survivors["stopped_at"], survivors["operator_line"]),
                         ("process", "kill -KILL -- -4242"))
        self.assertEqual((closure_refused["stopped_at"], closure_refused["operator_line"]),
                         ("closure", f"bale unlock {SID} --reason aborted"))
        self.assertEqual((unpinned["stopped_at"], unpinned["operator_line"]),
                         ("closure", f"bale unlock {SID} --reason aborted"))

    def test_human_mode_names_each_group(self):
        runtime, tool = self.group(), self.group()
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        kill.register_group(self.state, SID, tool.pgid)
        code, out, err, _ = self.run_verb("--grace", "2")
        self.assertEqual(code, 0, out)
        self.assertIn(f"process: group {runtime.pgid}: SIGTERM, SIGCONT; no member alive", out)
        self.assertIn(f"group {tool.pgid}: SIGTERM, SIGCONT; no member alive", out)
        self.assertIn("2 groups in all: none alive", out)
        for pid in runtime.pids + tool.pids:
            self.assertTrue(dies_within(pid), f"{pid} outlived the kill")

    def test_human_mode_names_each_step_and_the_hand_line(self):
        code, out, err, _ = self.run_verb()
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith(f"kill {SID}: done"), out)
        self.assertTrue(any(l.strip().startswith("abort:") for l in lines))
        self.assertIn("no running record", out)
        self.assertIn("closure: bale unlocked", out)
        code, out, err, _ = self.run_verb(runner=RecordedUnlock(HOLD))
        self.assertEqual(code, 1)
        self.assertIn("NOT FINISHED (stopped at closure)", out.splitlines()[0])
        self.assertIn(f"finish by hand: bale revert {SID}", out)
        self.assertIn(HOLD_REFUSAL, err, "bale's stderr reaches twine's stderr")


class KillEndToEnd(StateCase):
    """The real entrypoint as a subprocess, a real setsid-led group, and a
    stub bale (a double: StubBale replays the recorded `aborted` close, or a
    recorded refusal with the stderr line derived from it)."""

    def stub(self, **kwargs) -> StubBale:
        stub = StubBale(**kwargs)
        self.addCleanup(stub.cleanup)
        return stub

    def test_kill_a_real_group_and_close_through_a_stub_bale(self):
        stub = self.stub(unlock_stdout=unlock_recording("aborted").path)
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

    def test_kill_three_real_groups_and_close_through_a_stub_bale(self):
        """Brief §7's proof of §2.3's whole: the runtime's group and two more,
        registered as the hook would register them, `twine kill` run as a
        subprocess — every pid of all three dead, the record cleared, the
        stub saw exactly the one unlock argv, ok."""
        stub = self.stub(unlock_stdout=unlock_recording("aborted").path)
        runtime = self.group()
        tool_a = self.group(body='trap "" TERM; sleep 60 & echo $!; sleep 60 & echo $!; wait')
        tool_b = self.group()
        kill.register_running(self.state, SID, runtime.pgid, runtime.pgid)
        kill.register_group(self.state, SID, tool_a.pgid)
        kill.register_group(self.state, SID, tool_b.pgid)
        run = run_cli("kill", SID, "--state-dir", str(self.state), "--cwd", str(self.repo),
                      "--grace", "0.3", "--json", bale_root=stub.root)
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["closed"], obj["stopped_at"]),
                         (0, True, True, None), run.stderr)
        proc = obj["process"]
        self.assertEqual((proc["pgid"], proc["dead"], proc["survivors"], proc["record_cleared"]),
                         (runtime.pgid, True, [], True))
        self.assertEqual([g["pgid"] for g in proc["groups"]], [tool_a.pgid, tool_b.pgid])
        self.assertEqual([g["signals"] for g in proc["groups"]],
                         [["SIGTERM", "SIGCONT", "SIGKILL"], ["SIGTERM", "SIGCONT"]])
        self.assertTrue(all(g["dead"] and g["survivors"] == [] for g in proc["groups"]))
        self.assertEqual(stub.argv(), ["unlock", SID, "--reason", "aborted", "--json"])
        self.assertEqual(Path(stub.cwd()).resolve(), self.repo.resolve())
        for pid in runtime.pids + tool_a.pids + tool_b.pids:
            self.assertTrue(dies_within(pid), f"{pid} outlived twine kill")
        self.assertIsNone(kill.read_running(self.state, SID))
        self.assertTrue(kill.abort_requested(self.state, SID))
        self.assertNotIn("Traceback", run.stderr)

    def test_a_refusing_stub_is_not_ok_and_shows_bales_stderr(self):
        """The stub replays the recorded not-open refusal as bale 0.4.49
        printed it: the JSON line on stdout, exit 1, and on stderr the
        `[bale] error:` line derived from the recording."""
        stub = self.stub(unlock_stdout=NOT_OPEN.path, exit_code=NOT_OPEN.exit_code,
                         stderr=NOT_OPEN.stderr.decode())
        run = run_cli("kill", SID, "--state-dir", str(self.state), "--cwd", str(self.repo),
                      "--json", bale_root=stub.root)
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["stopped_at"], obj["exit_code"]),
                         (1, False, "closure", 1))
        self.assertIn("is not open", obj["stderr"])
        self.assertIn("is not open", run.stderr)
        self.assertEqual(obj["closure"], NOT_OPEN.line)
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

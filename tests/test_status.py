"""`twine status`: twine's own facts; ok is about twine, not bale — nor,
since session 5c, about whether its state directory resolves or exists, nor,
since session twine-status-inflight (0.11.0), about what `inflight/` holds."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from twine import CONSUMPTION_MANIFEST, FIXTURES_DIR, __version__, inflight

from tests.helpers import PIN, TempRoots, run_cli, run_inprocess


class Status(unittest.TestCase):

    def setUp(self):
        self.roots = TempRoots()
        self.addCleanup(self.roots.cleanup)

    def test_ok_without_any_bale_install(self):
        run = run_inprocess("status", "--json")
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"]), (0, True))
        self.assertFalse(obj["bale"]["ok"])
        self.assertIsNone(obj["bale"]["root"])

    def test_payload_keys_and_values(self):
        run = run_cli("status", "--json", bale_root=self.roots.ok)
        obj = json.loads(run.stdout)
        self.assertEqual(run.code, 0)
        self.assertEqual(obj["version"], __version__)
        self.assertEqual(obj["python"], platform.python_version())
        self.assertEqual(obj["pin"], PIN)
        self.assertEqual(Path(obj["consumption_manifest"]), CONSUMPTION_MANIFEST)
        self.assertEqual(Path(obj["fixtures"]), FIXTURES_DIR)
        self.assertTrue(obj["fixtures_present"])
        self.assertEqual(obj["bale"]["ok"], True)
        self.assertEqual(obj["bale"]["installed"], PIN)

    def test_bale_mismatch_rides_inside_and_status_stays_ok(self):
        run = run_cli("status", "--json", bale_root=self.roots.other)
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["bale"]["ok"]), (0, True, False))

    def test_unusable_manifest_makes_status_not_ok(self):
        with mock.patch("twine.commands.core.CONSUMPTION_MANIFEST",
                        self.roots.absent / "missing.toml"):
            run = run_inprocess("status", "--json")
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"]), (1, False))
        self.assertIsNone(obj["bale"])
        self.assertIn("unusable", obj["ok_reason"])

    def test_human_rendering(self):
        run = run_inprocess("status")
        self.assertEqual(run.code, 0)
        self.assertEqual(run.stdout.split("\n")[0], f"twine {__version__}")
        self.assertIn(str(CONSUMPTION_MANIFEST), run.stdout)
        self.assertIn(str(FIXTURES_DIR), run.stdout)


STATE_KEYS = ("state_dir", "state_dir_source", "state_dir_reason", "state_dir_exists",
              "state_present", "inflight_sids", "inflight_faults")
PRESENT_KEYS = ("spend_jsonl", "prices_toml", "abort", "running", "inflight")
# Two sids twine accepts (twine.kill.is_sid), and their record files' names.
SID = "2026-10-08-twine-status-inflight-004"
OTHER_SID = "2026-10-08-twine-exchange-vouch-005"


def record(state: Path, sid: str = SID) -> Path:
    """An in-flight record written the one way the format is written —
    twine.inflight.record_open, never by hand."""
    return inflight.record_open(state, sid, outcome="opened", cwd="/repo",
                                tarball="/repo/request.tar.gz", desk=None,
                                bundle_sha256="b" * 64, opener=f"opener of {sid}\n").path


def snapshot(root: Path) -> dict[str, tuple]:
    """Every path under `root` (and `root` itself) with its kind, mode,
    mtime and, for a file, its bytes' sha256 — so a write, a create, a
    chmod or a touch anywhere shows up as a difference."""
    out = {}
    for path in [root, *sorted(root.rglob("*"))]:
        st = path.lstat()
        digest = (hashlib.sha256(path.read_bytes()).hexdigest()
                  if path.is_file() and not path.is_symlink() else None)
        out[str(path.relative_to(root))] = (st.st_mode, st.st_mtime_ns, digest)
    return out


class StateDirectory(unittest.TestCase):
    """Session 5c (cost-spine-005's Proposal, carried through 5b): `status`
    reports where twine's state lives and what of it exists — and never
    creates it. ok is untouched: a state directory that does not resolve or
    exist is a fact about the machine, not a fault in twine."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="twine-status-")
        self.base = Path(self._dir.name)
        self.addCleanup(self._dir.cleanup)

    def status(self, *argv, env=None):
        run = run_inprocess("status", "--json", *argv, env=env)
        self.assertEqual(run.code, 0, run.stderr)
        obj = json.loads(run.stdout)
        self.assertTrue(obj["ok"])
        return obj

    def test_none_resolves_in_an_empty_environment_and_is_never_silent(self):
        obj = self.status()
        self.assertEqual({k: obj[k] for k in STATE_KEYS},
                         {"state_dir": None, "state_dir_source": None,
                          "state_dir_reason": obj["state_dir_reason"],
                          "state_dir_exists": None, "state_present": None,
                          "inflight_sids": None, "inflight_faults": None})
        self.assertIn("cannot resolve twine's state directory", obj["state_dir_reason"])
        self.assertIn("state dir:            none resolves — cannot resolve",
                      run_inprocess("status").stdout)

    def test_the_flag_names_a_directory_with_some_of_the_five_present(self):
        state = self.base / "state"
        (state / "abort").mkdir(parents=True)
        (state / "spend.jsonl").write_text("")
        (state / "running").write_text("a file where the directory should be")
        obj = self.status("--state-dir", str(state))
        self.assertEqual({k: obj[k] for k in STATE_KEYS},
                         {"state_dir": str(state), "state_dir_source": "--state-dir",
                          "state_dir_reason": None, "state_dir_exists": True,
                          "state_present": {"spend_jsonl": True, "prices_toml": False,
                                            "abort": True, "running": False,
                                            "inflight": False},
                          "inflight_sids": [], "inflight_faults": []})
        self.assertEqual(tuple(obj["state_present"]), PRESENT_KEYS)
        out = run_inprocess("status", "--state-dir", str(state)).stdout
        self.assertIn(f"state dir:            {state}  (from --state-dir)", out)
        self.assertIn("state present:        spend.jsonl, abort/  "
                      "(missing: prices.toml, running/, inflight/)", out)
        (state / "prices.toml").write_text("")
        (state / "running").unlink()
        (state / "running").mkdir()
        (state / "inflight").mkdir()
        obj = self.status("--state-dir", str(state))
        self.assertEqual(obj["state_present"], dict.fromkeys(PRESENT_KEYS, True))
        self.assertNotIn("missing", run_inprocess("status", "--state-dir", str(state)).stdout)

    def test_a_directory_that_does_not_exist_is_reported_and_never_created(self):
        missing = self.base / "not-yet"
        obj = self.status("--state-dir", str(missing))
        self.assertEqual((obj["state_dir"], obj["state_dir_exists"], obj["state_present"],
                          obj["inflight_sids"], obj["inflight_faults"]),
                         (str(missing), False, dict.fromkeys(PRESENT_KEYS, False), [], []))
        self.assertFalse(missing.exists(), "status never creates the state directory")
        out = run_inprocess("status", "--state-dir", str(missing)).stdout
        self.assertIn(f"state dir:            {missing}  (from --state-dir)  (does not exist)", out)
        self.assertNotIn("state present:", out)
        a_file = self.base / "a-file"
        a_file.write_text("not a directory")
        obj = self.status("--state-dir", str(a_file))
        self.assertEqual((obj["state_dir_exists"], obj["state_present"],
                          obj["inflight_sids"], obj["inflight_faults"]),
                         (False, dict.fromkeys(PRESENT_KEYS, False), [], []))

    def test_the_environment_rules_resolve_in_order_and_an_empty_flag_is_the_reason(self):
        home, xdg = self.base / "home", self.base / "xdg"
        env = {"HOME": str(home)}
        obj = self.status(env=env)
        self.assertEqual((obj["state_dir"], obj["state_dir_source"], obj["state_dir_exists"]),
                         (str(home / ".local" / "state" / "twine"), "HOME", False))
        env["XDG_STATE_HOME"] = str(xdg)
        obj = self.status(env=env)
        self.assertEqual((obj["state_dir"], obj["state_dir_source"]),
                         (str(xdg / "twine"), "XDG_STATE_HOME"))
        env["TWINE_STATE_DIR"] = str(self.base / "explicit")
        obj = self.status(env=env)
        self.assertEqual((obj["state_dir"], obj["state_dir_source"]),
                         (str(self.base / "explicit"), "TWINE_STATE_DIR"))
        obj = self.status("--state-dir", str(self.base / "flag"), env=env)
        self.assertEqual(obj["state_dir_source"], "--state-dir")
        obj = self.status("--state-dir", " ", env=env)
        self.assertEqual((obj["state_dir"], obj["state_dir_source"]), (None, None))
        self.assertIn("--state-dir is empty", obj["state_dir_reason"])
        self.assertFalse((home / ".local").exists(), "nothing created")

    @unittest.skipIf(os.geteuid() == 0, "root bypasses mode bits; the path cannot be made unreadable")
    def test_a_directory_that_cannot_be_looked_at_reads_as_absent_never_a_traceback(self):
        """Session 5c's review: a parent without search permission must be a
        fact (`state_dir_exists` false), never an internal error."""
        parent = self.base / "private"
        state = parent / "state"
        (state / "abort").mkdir(parents=True)
        parent.chmod(0)
        self.addCleanup(parent.chmod, 0o700)
        obj = self.status("--state-dir", str(state))
        self.assertEqual((obj["state_dir_exists"], obj["state_present"]),
                         (False, dict.fromkeys(PRESENT_KEYS, False)))

    def test_the_state_keys_ride_on_the_unusable_manifest_path_too(self):
        roots = TempRoots()
        self.addCleanup(roots.cleanup)
        record(self.base)
        with mock.patch("twine.commands.core.CONSUMPTION_MANIFEST",
                        roots.absent / "missing.toml"):
            run = run_inprocess("status", "--json", "--state-dir", str(self.base))
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"]), (1, False))
        self.assertEqual((obj["state_dir"], obj["state_dir_exists"]), (str(self.base), True))
        # All seven state keys ride here, the in-flight ones included.
        self.assertLessEqual(set(STATE_KEYS), set(obj))
        self.assertEqual((obj["state_present"], obj["inflight_sids"], obj["inflight_faults"]),
                         (dict(dict.fromkeys(PRESENT_KEYS, False), inflight=True), [SID], []))

    def test_the_subprocess_entrypoint_takes_the_flag(self):
        run = run_cli("status", "--json", "--state-dir", str(self.base))
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["state_dir"], obj["state_dir_source"]),
                         (0, str(self.base), "--state-dir"))


class InflightRecords(unittest.TestCase):
    """Session twine-status-inflight (carry-bundle-003's Proposal 1):
    `status` reads the in-flight records `carry bundle` keeps in
    `<state-dir>/inflight/` — `state_present.inflight`, `inflight_sids` and
    `inflight_faults` — reading only, and stays ok / exit 0 whatever is
    there. A file there that is not a record is named, never dropped."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="twine-status-inflight-")
        self.state = Path(self._dir.name) / "state"
        self.addCleanup(self._dir.cleanup)

    @property
    def records(self) -> Path:
        return self.state / "inflight"

    def status(self, *argv, env=None):
        run = run_inprocess("status", "--json", "--state-dir", str(self.state), *argv, env=env)
        self.assertEqual(run.code, 0, run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        obj = json.loads(run.stdout)
        self.assertTrue(obj["ok"])
        return obj

    def human(self) -> str:
        run = run_inprocess("status", "--state-dir", str(self.state))
        self.assertEqual(run.code, 0, run.stderr)
        return run.stdout

    def test_the_order_of_state_presents_keys_is_pinned(self):
        self.state.mkdir()
        obj = self.status()
        self.assertEqual(tuple(obj["state_present"]),
                         ("spend_jsonl", "prices_toml", "abort", "running", "inflight"))
        self.assertEqual(tuple(k for k in obj if k in STATE_KEYS), STATE_KEYS)

    def test_a_record_is_read_and_its_sid_listed(self):
        record(self.state)
        obj = self.status()
        self.assertEqual((obj["state_present"]["inflight"], obj["inflight_sids"],
                          obj["inflight_faults"]), (True, [SID], []))
        out = self.human()
        self.assertIn("state present:        inflight/  (missing: spend.jsonl, prices.toml, "
                      "abort/, running/)", out)
        self.assertIn(f"in-flight record:     {SID}\n", out)
        self.assertNotIn("in-flight fault", out)

    def test_the_sids_are_sorted_by_sid(self):
        # By file name `a.json` sorts after `a-b.json`; by sid `a` comes first.
        for sid in (OTHER_SID, "a-b", "a", SID):
            record(self.state, sid)
        obj = self.status()
        self.assertEqual(obj["inflight_sids"], [OTHER_SID, SID, "a", "a-b"])

    def test_no_inflight_directory_and_inflight_as_a_file(self):
        self.state.mkdir()
        (self.state / "spend.jsonl").write_text("")
        obj = self.status()
        self.assertEqual((obj["state_present"]["inflight"], obj["inflight_sids"],
                          obj["inflight_faults"]), (False, [], []))
        self.records.write_text("a file where the directory should be")
        obj = self.status()
        self.assertEqual((obj["state_present"]["inflight"], obj["inflight_sids"],
                          obj["inflight_faults"]), (False, [], []))
        self.assertIn("state present:        spend.jsonl  "
                      "(missing: prices.toml, abort/, running/, inflight/)", self.human())

    def test_an_empty_inflight_directory_is_present_with_nothing_in_it(self):
        self.records.mkdir(parents=True)
        obj = self.status()
        self.assertEqual((obj["state_present"]["inflight"], obj["inflight_sids"],
                          obj["inflight_faults"]), (True, [], []))
        self.assertNotIn("in-flight", self.human())

    def test_no_state_directory_resolves_both_keys_null(self):
        run = run_inprocess("status", "--json", env={})
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"]), (0, True))
        self.assertEqual((obj["state_present"], obj["inflight_sids"], obj["inflight_faults"]),
                         (None, None, None))

    def test_files_that_are_not_records_are_each_named_and_the_record_still_reads(self):
        record(self.state)
        (self.records / f"{OTHER_SID}.json").write_text("{}")
        (self.records / "not a sid.json").write_text("{}")
        (self.records / "junk.txt").write_text("junk")
        obj = self.status()
        self.assertEqual(obj["inflight_sids"], [SID])
        faults = obj["inflight_faults"]
        self.assertEqual(len(faults), 3, faults)
        by_name = dict(zip((f"{OTHER_SID}.json", "junk.txt", "not a sid.json"), faults))
        for name, fault in by_name.items():
            self.assertTrue(fault.startswith(name + " "), (name, fault))
            self.assertNotIn(str(self.records), fault, "the basename, not the path")
        self.assertIn("is not an in-flight record: the record lacks sid, cwd, tarball, opens",
                      by_name[f"{OTHER_SID}.json"])
        self.assertIn(f"its sid is None, not {OTHER_SID!r}", by_name[f"{OTHER_SID}.json"])
        self.assertEqual(by_name["junk.txt"],
                         "junk.txt is not an in-flight record: its name is not <sid>.json")
        self.assertEqual(by_name["not a sid.json"],
                         "not a sid.json is not an in-flight record: 'not a sid' is not a "
                         "session id twine accepts")
        out = self.human()
        self.assertIn(f"in-flight record:     {SID}\n", out)
        for fault in faults:
            self.assertIn(f"in-flight fault:      {fault}\n", out)

    def test_a_record_whose_sid_is_another_is_a_fault_not_a_sid(self):
        source = record(self.state, SID)
        (self.records / f"{OTHER_SID}.json").write_bytes(source.read_bytes())
        obj = self.status()
        self.assertEqual(obj["inflight_sids"], [SID])
        self.assertEqual(obj["inflight_faults"],
                         [f"{OTHER_SID}.json is not an in-flight record: "
                          f"its sid is {SID!r}, not {OTHER_SID!r}"])

    def test_a_record_that_is_not_json_and_one_that_is_a_directory(self):
        self.records.mkdir(parents=True)
        (self.records / f"{SID}.json").write_text("{")
        (self.records / f"{OTHER_SID}.json").mkdir()
        faults = self.status()["inflight_faults"]
        self.assertEqual(len(faults), 2, faults)
        self.assertTrue(faults[0].startswith(f"{OTHER_SID}.json cannot be read: "), faults[0])
        self.assertTrue(faults[1].startswith(f"{SID}.json is not a JSON object: "), faults[1])

    def test_a_dangling_link_is_named_not_skipped(self):
        self.records.mkdir(parents=True)
        (self.records / f"{SID}.json").symlink_to(self.records / "nowhere")
        obj = self.status()
        self.assertEqual(obj["inflight_sids"], [])
        self.assertEqual(obj["inflight_faults"],
                         [f"{SID}.json cannot be read: it was listed but no file is there now "
                          "(a dangling link, or removed while it was read)"])

    def test_a_write_left_unfinished_is_named_as_twines_temp_file(self):
        record(self.state)
        (self.records / ".twine-123-456.tmp").write_text("{")
        obj = self.status()
        self.assertEqual(obj["inflight_sids"], [SID])
        self.assertEqual(obj["inflight_faults"],
                         [".twine-123-456.tmp is not an in-flight record: it is the temp file "
                          "of a record write still in progress, or of one that did not "
                          "finish"])

    def test_names_that_cannot_be_printed_are_shown_as_their_repr_and_never_a_traceback(self):
        """A newline, or bytes that are not UTF-8, in a file name: both
        modes stay exit 0, the twin is one line, and the fault names the
        file by its repr. Run as a subprocess, so stdout's real encoding
        is the one that would refuse a lone surrogate."""
        self.records.mkdir(parents=True)
        (self.records / "two\nlines").write_text("")
        os.close(os.open(os.fsencode(self.records) + b"/bad-\xff.json",
                         os.O_WRONLY | os.O_CREAT, 0o600))
        run = run_cli("status", "--json", "--state-dir", str(self.state))
        self.assertEqual(run.code, 0, run.stderr)
        self.assertEqual(run.stdout.count("\n"), 1)
        obj = json.loads(run.stdout)
        self.assertEqual(obj["inflight_faults"],
                         ["'bad-\\udcff.json' is not an in-flight record: 'bad-\\udcff' is not a "
                          "session id twine accepts",
                          "'two\\nlines' is not an in-flight record: its name is not "
                          "<sid>.json"])
        run = run_cli("status", "--state-dir", str(self.state))
        self.assertEqual(run.code, 0, run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        self.assertIn("in-flight fault:      'two\\nlines' is not", run.stdout)

    def test_an_inflight_directory_that_cannot_be_listed_is_one_fault(self):
        """Decision 4 (notes.md §1): `inflight` true — it is there — no
        sids, and one fault naming `inflight/`; never a traceback, and never
        an empty listing that reads as "no records"."""
        record(self.state)
        listdir = os.listdir

        def refusing(path="."):
            if Path(path) == self.records:
                raise PermissionError(13, "Permission denied", str(path))
            return listdir(path)

        with mock.patch("twine.inflight.os.listdir", side_effect=refusing):
            obj = self.status()
        self.assertEqual((obj["state_present"]["inflight"], obj["inflight_sids"],
                          obj["inflight_faults"]),
                         (True, [], ["inflight/ cannot be listed: Permission denied"]))

    @unittest.skipIf(os.geteuid() == 0, "root bypasses mode bits; the path cannot be made unreadable")
    def test_an_inflight_directory_without_read_permission_is_one_fault(self):
        record(self.state)
        self.records.chmod(0o300)
        self.addCleanup(self.records.chmod, 0o700)
        obj = self.status()
        self.assertEqual((obj["state_present"]["inflight"], obj["inflight_sids"],
                          obj["inflight_faults"]),
                         (True, [], ["inflight/ cannot be listed: Permission denied"]))

    def test_status_creates_and_writes_nothing_with_or_without_inflight(self):
        """The directory diff before and after, on a state directory without
        `inflight/` and on one holding a record and junk beside it. (A
        state directory that does not exist is never created:
        StateDirectory.test_a_directory_that_does_not_exist_is_reported_and_never_created.)"""
        self.state.mkdir()
        (self.state / "spend.jsonl").write_text("")
        for label in ("without inflight/", "with inflight/"):
            with self.subTest(label):
                before = snapshot(self.state)
                self.status()
                self.human()
                run_cli("status", "--json", "--state-dir", str(self.state))
                self.assertEqual(snapshot(self.state), before)
            record(self.state)
            (self.records / "junk.txt").write_text("junk")
            (self.records / f"{OTHER_SID}.json").write_text("{}")

    def test_the_subprocess_twin_carries_the_record(self):
        record(self.state)
        run = run_cli("status", "--json", "--state-dir", str(self.state))
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["state_present"]["inflight"],
                          obj["inflight_sids"], obj["inflight_faults"]),
                         (0, True, True, [SID], []))


if __name__ == "__main__":
    unittest.main()

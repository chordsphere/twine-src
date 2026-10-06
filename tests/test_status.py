"""`twine status`: twine's own facts; ok is about twine, not bale — nor,
since session 5c, about whether its state directory resolves or exists."""

from __future__ import annotations

import json
import os
import platform
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from twine import CONSUMPTION_MANIFEST, FIXTURES_DIR, __version__

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
              "state_present")
PRESENT_KEYS = ("spend_jsonl", "prices_toml", "abort", "running")


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
                          "state_dir_exists": None, "state_present": None})
        self.assertIn("cannot resolve twine's state directory", obj["state_dir_reason"])
        self.assertIn("state dir:            none resolves — cannot resolve",
                      run_inprocess("status").stdout)

    def test_the_flag_names_a_directory_with_some_of_the_four_present(self):
        state = self.base / "state"
        (state / "abort").mkdir(parents=True)
        (state / "spend.jsonl").write_text("")
        (state / "running").write_text("a file where the directory should be")
        obj = self.status("--state-dir", str(state))
        self.assertEqual({k: obj[k] for k in STATE_KEYS},
                         {"state_dir": str(state), "state_dir_source": "--state-dir",
                          "state_dir_reason": None, "state_dir_exists": True,
                          "state_present": {"spend_jsonl": True, "prices_toml": False,
                                            "abort": True, "running": False}})
        self.assertEqual(tuple(obj["state_present"]), PRESENT_KEYS)
        out = run_inprocess("status", "--state-dir", str(state)).stdout
        self.assertIn(f"state dir:            {state}  (from --state-dir)", out)
        self.assertIn("state present:        spend.jsonl, abort/  (missing: prices.toml, running/)",
                      out)
        (state / "prices.toml").write_text("")
        (state / "running").unlink()
        (state / "running").mkdir()
        obj = self.status("--state-dir", str(state))
        self.assertEqual(obj["state_present"], dict.fromkeys(PRESENT_KEYS, True))
        self.assertNotIn("missing", run_inprocess("status", "--state-dir", str(state)).stdout)

    def test_a_directory_that_does_not_exist_is_reported_and_never_created(self):
        missing = self.base / "not-yet"
        obj = self.status("--state-dir", str(missing))
        self.assertEqual((obj["state_dir"], obj["state_dir_exists"], obj["state_present"]),
                         (str(missing), False, dict.fromkeys(PRESENT_KEYS, False)))
        self.assertFalse(missing.exists(), "status never creates the state directory")
        out = run_inprocess("status", "--state-dir", str(missing)).stdout
        self.assertIn(f"state dir:            {missing}  (from --state-dir)  (does not exist)", out)
        self.assertNotIn("state present:", out)
        a_file = self.base / "a-file"
        a_file.write_text("not a directory")
        obj = self.status("--state-dir", str(a_file))
        self.assertEqual((obj["state_dir_exists"], obj["state_present"]),
                         (False, dict.fromkeys(PRESENT_KEYS, False)))

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
        with mock.patch("twine.commands.core.CONSUMPTION_MANIFEST",
                        roots.absent / "missing.toml"):
            run = run_inprocess("status", "--json", "--state-dir", str(self.base))
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"]), (1, False))
        self.assertEqual((obj["state_dir"], obj["state_dir_exists"]), (str(self.base), True))

    def test_the_subprocess_entrypoint_takes_the_flag(self):
        run = run_cli("status", "--json", "--state-dir", str(self.base))
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["state_dir"], obj["state_dir_source"]),
                         (0, str(self.base), "--state-dir"))


if __name__ == "__main__":
    unittest.main()

"""`twine status`: twine's own facts; ok is about twine, not bale."""

from __future__ import annotations

import json
import platform
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


if __name__ == "__main__":
    unittest.main()

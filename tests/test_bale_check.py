"""`twine bale check` (D2): install-root resolution and the pin check,
against temp roots the tests build — never a real install."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from twine import CONSUMPTION_MANIFEST
from twine.bale import (ENV_ROOT, check, load_manifest, read_installed_version,
                        resolve_root)

from tests.helpers import PIN, TempRoots, run_cli, run_inprocess


class RootResolution(unittest.TestCase):

    def test_explicit_wins_over_env_and_path(self):
        root = resolve_root("/explicit", {ENV_ROOT: "/env"}, lambda n: "/path/bin/bale")
        self.assertEqual((root.path, root.source), (Path("/explicit"), "--bale-root"))

    def test_env_wins_over_path(self):
        root = resolve_root(None, {ENV_ROOT: "/env"}, lambda n: "/path/bin/bale")
        self.assertEqual((root.path, root.source), (Path("/env"), ENV_ROOT))

    def test_path_is_followed_to_its_real_bin_parent(self):
        roots = TempRoots()
        self.addCleanup(roots.cleanup)
        exe = roots.ok / "bin" / "bale"
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        link_dir = roots.ok.parent / "local-bin"
        link_dir.mkdir()
        link = link_dir / "bale"
        link.symlink_to(exe)
        root = resolve_root(None, {}, lambda n: str(link))
        self.assertEqual((root.path, root.source), (roots.ok, "PATH"))

    def test_nothing_found(self):
        root = resolve_root(None, {}, lambda n: None)
        self.assertFalse(root.found)
        self.assertIsNone(root.source)
        self.assertIn("no bale on PATH", root.detail)


class InstalledVersion(unittest.TestCase):

    def setUp(self):
        self.roots = TempRoots()
        self.addCleanup(self.roots.cleanup)

    def test_reads_and_strips(self):
        self.assertEqual(read_installed_version(self.roots.ok)[0], PIN)

    def test_absent_is_none_with_reason(self):
        version, detail = read_installed_version(self.roots.absent)
        self.assertIsNone(version)
        self.assertIn("unreadable", detail)

    def test_empty_is_none(self):
        (self.roots.absent / "bin").mkdir()
        (self.roots.absent / "bin" / "VERSION").write_text("\n", encoding="utf-8")
        self.assertIsNone(read_installed_version(self.roots.absent)[0])


class PinCheck(unittest.TestCase):

    def setUp(self):
        self.roots = TempRoots()
        self.addCleanup(self.roots.cleanup)
        self.manifest = load_manifest(CONSUMPTION_MANIFEST)

    def test_three_roots(self):
        cases = {
            self.roots.ok: (True, PIN),
            self.roots.other: (False, self.roots.other_version),
            self.roots.absent: (False, None),
        }
        for root, (ok, installed) in cases.items():
            with self.subTest(root=root.name):
                result = check(self.manifest, resolve_root(str(root), {}, lambda n: None))
                self.assertEqual((result.ok, result.installed, result.root),
                                 (ok, installed, root))
                self.assertEqual(result.pin, PIN)
                self.assertTrue(result.reason)

    def test_no_install(self):
        result = check(self.manifest, resolve_root(None, {}, lambda n: None))
        self.assertEqual((result.ok, result.installed, result.root), (False, None, None))

    def test_json_shape(self):
        result = check(self.manifest, resolve_root(str(self.roots.ok), {}, lambda n: None))
        self.assertEqual(set(result.as_json()),
                         {"pin", "installed", "root", "source", "ok", "reason"})


class CheckViaCli(unittest.TestCase):

    def setUp(self):
        self.roots = TempRoots()
        self.addCleanup(self.roots.cleanup)

    def test_subprocess_three_roots(self):
        expect = {"ok": (0, True, PIN), "other": (1, False, self.roots.other_version),
                  "absent": (1, False, None)}
        for name, (code, ok, installed) in expect.items():
            with self.subTest(root=name):
                run = run_cli("bale", "check", "--json", "--bale-root",
                              str(getattr(self.roots, name)))
                obj = json.loads(run.stdout)
                self.assertEqual((run.code, obj["ok"], obj["installed"], obj["pin"]),
                                 (code, ok, installed, PIN))
                self.assertEqual(obj["root"], str(getattr(self.roots, name)))
                self.assertNotIn("Traceback", run.stderr)

    def test_env_variable_resolves(self):
        run = run_cli("bale", "check", "--json", bale_root=self.roots.ok)
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["source"]), (0, True, ENV_ROOT))

    def test_human_rendering_carries_the_same_facts(self):
        run = run_inprocess("bale", "check", "--bale-root", str(self.roots.other))
        self.assertEqual(run.code, 1)
        self.assertIn(PIN, run.stdout)
        self.assertIn(self.roots.other_version, run.stdout)
        self.assertIn("FAIL", run.stdout)


if __name__ == "__main__":
    unittest.main()

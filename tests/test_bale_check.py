"""`twine bale check` (D2): install-root resolution and the gate, against
temp roots the tests build — never a real install.

Since session 2026-10-12-twine-pin-floor-002 the gate is a floor plus the
manifest's schema hashes (D2 as amended on 2026-10-08), where it was an
exact pin: ok exactly when `<root>/bin/VERSION` parses as three dotted
integers at or above the floor, compared as a tuple, and every file
`[bale.schemas]` names is under `<root>/schemas/` with that sha256. The
matrix below is the brief's: at the floor, above, far above, below,
unparsable, no schemas/, a missing file, a mismatched file — each reason
named, every failing fact at once, and no `pin` key anywhere."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from twine import CONSUMPTION_MANIFEST
from twine.bale import (ENV_ROOT, ManifestError, check, load_manifest, parse_version,
                        read_installed_version, resolve_root)

from tests.helpers import ABOVE, FLOOR, TempRoots, run_cli, run_inprocess


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
        self.assertEqual(read_installed_version(self.roots.ok)[0], FLOOR)

    def test_absent_is_none_with_reason(self):
        version, detail = read_installed_version(self.roots.absent)
        self.assertIsNone(version)
        self.assertIn("unreadable", detail)

    def test_empty_is_none(self):
        (self.roots.absent / "bin").mkdir()
        (self.roots.absent / "bin" / "VERSION").write_text("\n", encoding="utf-8")
        self.assertIsNone(read_installed_version(self.roots.absent)[0])


class VersionParsing(unittest.TestCase):

    def test_three_dotted_integers_and_nothing_else(self):
        """The gate compares tuples, so a version must be exactly three
        dotted integers: a suffix, a leading zero, two parts or whitespace
        inside is not one."""
        self.assertEqual(parse_version("0.4.51"), (0, 4, 51))
        self.assertEqual(parse_version("10.0.0"), (10, 0, 0))
        for text in ("0.4", "0.4.51.1", "0.4.51-rc1", "v0.4.51", "00.4.51", " 0.4.51",
                     "0.4.51\n", "", "0.4.x", None):
            with self.subTest(text=text):
                self.assertIsNone(parse_version(text))

    def test_compared_as_tuples_never_as_strings(self):
        """0.4.100 is above 0.4.51 and 0.4.9 below it, though a string
        comparison says the opposite of both."""
        self.assertGreater(parse_version("0.4.100"), parse_version(FLOOR))
        self.assertLess(parse_version("0.4.9"), parse_version(FLOOR))
        self.assertLess("0.4.100", FLOOR, "the string comparison the gate must not make")


class TheGate(unittest.TestCase):

    def setUp(self):
        self.roots = TempRoots()
        self.addCleanup(self.roots.cleanup)
        self.manifest = load_manifest(CONSUMPTION_MANIFEST)

    def result(self, root):
        return check(self.manifest, resolve_root(str(root), {}, lambda n: None))

    def test_the_manifest_carries_a_floor_and_no_pin(self):
        self.assertEqual(self.manifest.floor, FLOOR)
        self.assertNotIn("pin", self.manifest.data["bale"])
        self.assertFalse(hasattr(self.manifest, "pin"))

    def test_at_the_floor_above_and_far_above_are_admitted(self):
        for root, installed in ((self.roots.ok, FLOOR), (self.roots.above, ABOVE),
                                (self.roots.far_above, TempRoots.FAR_ABOVE)):
            with self.subTest(installed=installed):
                result = self.result(root)
                self.assertEqual((result.ok, result.installed, result.root, result.floor),
                                 (True, installed, root, FLOOR))
                self.assertTrue(result.floor_admits)
                self.assertTrue(result.schemas.ok)
                self.assertEqual(len(result.schemas.checked), 8)
                self.assertIn(f"at or above the floor {FLOOR}", result.reason)
                self.assertIn("all 8 schemas hash as the manifest pins them", result.reason)

    def test_below_the_floor_is_refused_naming_the_floor(self):
        for root, installed in ((self.roots.below, TempRoots.BELOW),
                                (self.roots.other, self.roots.other_version)):
            with self.subTest(installed=installed):
                result = self.result(root)
                self.assertFalse(result.ok)
                self.assertIs(result.floor_admits, False)
                self.assertTrue(result.schemas.ok, "only the version fails")
                self.assertEqual(result.reason,
                                 f"installed {installed} is below the floor {FLOOR}")

    def test_an_unparsable_or_unreadable_version_is_refused(self):
        result = self.result(self.roots.unparsable)
        self.assertFalse(result.ok)
        self.assertIsNone(result.floor_admits)
        self.assertEqual(result.installed, TempRoots.UNPARSABLE)
        self.assertIn("not a version of three dotted integers", result.reason)
        self.assertIn(repr(TempRoots.UNPARSABLE), result.reason)
        (self.roots.ok / "bin" / "VERSION").unlink()
        result = self.result(self.roots.ok)
        self.assertFalse(result.ok)
        self.assertIsNone(result.installed)
        self.assertIn("unreadable", result.reason)

    def test_no_schemas_directory_is_refused(self):
        result = self.result(self.roots.no_schemas)
        self.assertFalse(result.ok)
        self.assertTrue(result.floor_admits, "only the schemas fail")
        self.assertFalse(result.schemas.present)
        self.assertEqual(len(result.schemas.missing), 8)
        self.assertEqual(result.reason,
                         f"no schemas/ directory at {self.roots.no_schemas / 'schemas'}")

    def test_a_missing_file_is_refused_by_name(self):
        gone = "diagnostics.schema.json"
        (self.roots.ok / "schemas" / gone).unlink()
        result = self.result(self.roots.ok)
        self.assertFalse(result.ok)
        self.assertEqual((result.schemas.missing, result.schemas.mismatched), ((gone,), ()))
        self.assertEqual(len(result.schemas.checked), 7)
        self.assertEqual(result.reason, f"schemas missing from schemas/: {gone}")

    def test_a_mismatched_file_is_refused_by_name(self):
        result = self.result(self.roots.bad_schema)
        self.assertFalse(result.ok)
        self.assertEqual(result.schemas.mismatched, (TempRoots.ALTERED_SCHEMA,))
        self.assertEqual(result.schemas.missing, ())
        self.assertEqual(result.reason, "schemas that do not hash as the manifest pins "
                                        f"them: {TempRoots.ALTERED_SCHEMA}")

    def test_an_extra_schema_file_is_free(self):
        """The gate hashes what the manifest pins and nothing else: a ninth
        file under schemas/ is bale's to add."""
        (self.roots.above / "schemas" / "new-record.schema.json").write_text("{}\n")
        self.assertTrue(self.result(self.roots.above).ok)

    def test_every_failing_fact_is_named_at_once(self):
        """Below the floor, one schema missing and another mismatched: three
        sentences in one reason, none of them hiding the others."""
        root = self.roots.below
        (root / "schemas" / "diagnostics.schema.json").unlink()
        (root / "schemas" / TempRoots.ALTERED_SCHEMA).write_bytes(b"{}\n")
        result = self.result(root)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason.split("; "), [
            f"installed {TempRoots.BELOW} is below the floor {FLOOR}",
            "schemas missing from schemas/: diagnostics.schema.json",
            f"schemas that do not hash as the manifest pins them: {TempRoots.ALTERED_SCHEMA}"])

    def test_no_install(self):
        result = check(self.manifest, resolve_root(None, {}, lambda n: None))
        self.assertEqual((result.ok, result.installed, result.root, result.schemas),
                         (False, None, None, None))
        absent = self.result(self.roots.absent)
        self.assertFalse(absent.ok)
        self.assertIn("unreadable", absent.reason)
        self.assertIn("no schemas/ directory", absent.reason)

    def test_json_shape(self):
        """The keys: floor, installed, root, source, schemas, ok, reason — no
        `pin`. `schemas` is an object (dir, present, ok, checked, mismatched,
        missing), null only when no install was found."""
        obj = self.result(self.roots.bad_schema).as_json()
        self.assertEqual(set(obj), {"floor", "installed", "root", "source", "schemas",
                                    "ok", "reason"})
        self.assertNotIn("pin", obj)
        self.assertEqual(obj["schemas"], {
            "dir": str(self.roots.bad_schema / "schemas"), "present": True, "ok": False,
            "checked": sorted(self.manifest.schemas),
            "mismatched": [TempRoots.ALTERED_SCHEMA], "missing": []})
        none = check(self.manifest, resolve_root(None, {}, lambda n: None)).as_json()
        self.assertIsNone(none["schemas"])

    def test_a_manifest_that_still_says_pin_or_no_floor_is_refused(self):
        """The retired key is refused by name, never read as a floor; a
        floor that is not three dotted integers is refused too."""
        text = CONSUMPTION_MANIFEST.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for edited, says in ((text.replace(f'floor = "{FLOOR}"', f'pin = "{FLOOR}"'),
                                  "carries `pin`"),
                                 (text.replace(f'floor = "{FLOOR}"', 'floor = "0.4"'),
                                  "three dotted integers"),
                                 (text.replace(f'floor = "{FLOOR}"\n', ""), "floor must be")):
                with self.subTest(says=says):
                    self.assertNotEqual(edited, text)
                    path = Path(tmp) / "m.toml"
                    path.write_text(edited, encoding="utf-8")
                    with self.assertRaises(ManifestError) as caught:
                        load_manifest(path)
                    self.assertIn(says, str(caught.exception))


class CheckViaCli(unittest.TestCase):
    """`bin/twine bale check --json` end to end against the roots."""

    def setUp(self):
        self.roots = TempRoots()
        self.addCleanup(self.roots.cleanup)

    def test_subprocess_the_matrix(self):
        expect = {"ok": (0, True, FLOOR, None), "above": (0, True, ABOVE, None),
                  "far_above": (0, True, TempRoots.FAR_ABOVE, None),
                  "below": (1, False, TempRoots.BELOW, f"below the floor {FLOOR}"),
                  "other": (1, False, self.roots.other_version, f"below the floor {FLOOR}"),
                  "unparsable": (1, False, TempRoots.UNPARSABLE, "three dotted integers"),
                  "bad_schema": (1, False, FLOOR, TempRoots.ALTERED_SCHEMA),
                  "no_schemas": (1, False, FLOOR, "no schemas/ directory"),
                  "absent": (1, False, None, "unreadable")}
        for name, (code, ok, installed, says) in expect.items():
            with self.subTest(root=name):
                run = run_cli("bale", "check", "--json", "--bale-root",
                              str(getattr(self.roots, name)))
                obj = json.loads(run.stdout)
                self.assertEqual((run.code, obj["ok"], obj["installed"], obj["floor"]),
                                 (code, ok, installed, FLOOR))
                self.assertNotIn("pin", obj)
                self.assertEqual(obj["root"], str(getattr(self.roots, name)))
                if says is not None:
                    self.assertIn(says, obj["reason"])
                self.assertNotIn("Traceback", run.stderr)

    def test_env_variable_resolves(self):
        run = run_cli("bale", "check", "--json", bale_root=self.roots.ok)
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["source"]), (0, True, ENV_ROOT))

    def test_human_rendering_names_the_floor_and_the_schema_verdict(self):
        run = run_inprocess("bale", "check", "--bale-root", str(self.roots.other))
        self.assertEqual(run.code, 1)
        self.assertIn(f"floor:     {FLOOR}", run.stdout)
        self.assertIn(self.roots.other_version, run.stdout)
        self.assertIn("schemas:   all 8 hash as the manifest pins them", run.stdout)
        self.assertIn("FAIL", run.stdout)
        self.assertNotIn("pin:", run.stdout)
        bad = run_inprocess("bale", "check", "--bale-root", str(self.roots.bad_schema))
        self.assertEqual(bad.code, 1)
        self.assertIn(f"schemas:   NOT OK — schemas that do not hash as the manifest pins "
                      f"them: {TempRoots.ALTERED_SCHEMA}", bad.stdout)
        good = run_inprocess("bale", "check", "--bale-root", str(self.roots.above))
        self.assertEqual(good.code, 0)
        self.assertIn("check:     ok", good.stdout)


if __name__ == "__main__":
    unittest.main()

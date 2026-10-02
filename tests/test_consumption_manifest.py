"""share/bale-consumption.toml (D3, D4) as data a test can walk."""

from __future__ import annotations

import re
import tomllib
import unittest

from twine import CONSUMPTION_MANIFEST, REPO_ROOT, shapes
from twine.bale import ManifestError, load_manifest

from tests.helpers import (PIN, TempRoots, carried_relpath, emission_relpath,
                           fixture_relpath)

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SCHEMA_FILES = {
    "bundle-manifest.schema.json", "changelog-record.schema.json",
    "diagnostics.schema.json", "escalation-record.schema.json",
    "exchange-record.schema.json", "request-manifest.schema.json",
    "response-manifest.schema.json", "telemetry-record.schema.json",
}
SURFACE_REQUIRED = {"kind", "keys", "read_by", "written_against"}
VERB_REQUIRED = SURFACE_REQUIRED | {"verb", "flags", "argv", "cwd", "stdout"}
FILE_REQUIRED = SURFACE_REQUIRED | {"path"}
FORMAT_REQUIRED = SURFACE_REQUIRED | {"format", "locator", "home", "emitted_by",
                                      "fixtures"}
REQUIRED = {"file": FILE_REQUIRED, "verb": VERB_REQUIRED, "format": FORMAT_REQUIRED}
README_ROW = re.compile(r"^\| `(?P<file>[^`]+)` \| `(?P<cmd>[^`]+)` \|", re.M)


class ManifestParses(unittest.TestCase):

    def test_tomllib_parses_it(self):
        with CONSUMPTION_MANIFEST.open("rb") as fh:
            data = tomllib.load(fh)
        self.assertEqual(data["bale"]["pin"], PIN)

    def test_load_manifest(self):
        m = load_manifest()
        self.assertEqual(m.pin, PIN)
        self.assertEqual(m.path, CONSUMPTION_MANIFEST)

    def test_eight_schemas_with_sha256s(self):
        m = load_manifest()
        self.assertEqual(set(m.schemas), SCHEMA_FILES)
        for name, digest in m.schemas.items():
            self.assertRegex(digest, SHA256, name)


class SurfacesAreWalkable(unittest.TestCase):

    def setUp(self):
        self.manifest = load_manifest()

    def test_every_surface_has_the_required_fields(self):
        for s in self.manifest.surfaces:
            with self.subTest(surface=s.get("verb") or s.get("path") or s.get("format")):
                self.assertIn(s["kind"], REQUIRED)
                required = REQUIRED[s["kind"]]
                self.assertTrue(required <= set(s), f"missing {required - set(s)}")
                self.assertIsInstance(s["keys"], list)
                self.assertTrue(all(isinstance(k, str) for k in s["keys"]))
                self.assertEqual(s["written_against"], PIN)

    def test_bin_version_is_a_surface_read_by_bale_check(self):
        files = [s for s in self.manifest.surfaces if s["kind"] == "file"]
        self.assertEqual([s["path"] for s in files], ["bin/VERSION"])
        self.assertIn("bale check", files[0]["read_by"])

    def test_every_verb_surface_fixture_exists_and_follows_the_naming_rule(self):
        verbs = [s for s in self.manifest.surfaces if s["kind"] == "verb"]
        self.assertGreaterEqual(len(verbs), 3)
        for s in verbs:
            with self.subTest(argv=s["argv"]):
                self.assertEqual(s["fixture"], fixture_relpath(s["argv"], s["cwd"]))
                self.assertTrue((REPO_ROOT / s["fixture"]).is_file(), s["fixture"])
                self.assertEqual(s["argv"][0], s["verb"])
                for flag in s["flags"]:
                    self.assertIn(flag, s["argv"])

    def test_the_two_json_verbs_the_brief_names_are_recorded(self):
        argvs = [tuple(s["argv"]) for s in self.manifest.surfaces if s["kind"] == "verb"]
        self.assertIn(("status", "--json"), argvs)
        self.assertIn(("stats", "--json"), argvs)

    def test_one_format_entry_per_kind_take_parses(self):
        formats = [s["format"] for s in self.manifest.surfaces if s["kind"] == "format"]
        self.assertEqual(sorted(formats), sorted(shapes.KINDS))
        for s in self.manifest.surfaces:
            if s["kind"] == "format":
                self.assertEqual(s["read_by"], ["take"])

    def test_every_format_fixture_exists_follows_naming_and_parses_as_its_kind(self):
        """Each fixture parses, with take's parser, as one intact block of
        the entry's kind, and sits where the naming rule puts it — computed
        from facts the name does not supply: a crafter emission's argv from
        its fixtures/README.md row, a carried paste's identity from the
        block's own sentinel. The probe fixture is the crafter's bare
        script; a turn carries it fenced, so it is wrapped in a fence."""
        readme_cmds = {m["file"]: m["cmd"] for m in README_ROW.finditer(
            (REPO_ROOT / "fixtures" / "README.md").read_text(encoding="utf-8"))}
        for s in self.manifest.surfaces:
            if s["kind"] != "format":
                continue
            self.assertTrue(s["fixtures"], s["format"])
            for rel in s["fixtures"]:
                with self.subTest(format=s["format"], fixture=rel):
                    path = REPO_ROOT / rel
                    self.assertTrue(path.is_file(), rel)
                    text = shapes.normalize(path.read_bytes()).text
                    if s["format"] == shapes.PROBE:
                        text = "```bash\n" + text + "```\n"
                    blocks = shapes.find_blocks(text).blocks
                    self.assertEqual([(b.kind, b.ok) for b in blocks],
                                     [(s["format"], True)])
                    if path.parent.name == "crafter":
                        cmd = readme_cmds[rel.removeprefix("fixtures/")]
                        expected = emission_relpath("crafter", cmd.split()[1:])
                    else:
                        f = blocks[0].fields
                        expected = carried_relpath(s["format"],
                                                   f.get("slug") or f.get("sid"),
                                                   f.get("to"))
                    self.assertEqual(rel, expected)

    def test_wanted_surfaces_name_the_open_json_gap(self):
        wanted = self.manifest.data.get("wanted", [])
        gaps = {(w["verb"], tuple(w["flags"])) for w in wanted}
        self.assertIn(("open", ("--json",)), gaps)
        for w in wanted:
            self.assertTrue(w["needed_by"] and w["status"])


class ManifestRefusals(unittest.TestCase):

    def setUp(self):
        self.roots = TempRoots()
        self.addCleanup(self.roots.cleanup)
        self.scratch = self.roots.absent

    def test_missing_file(self):
        with self.assertRaises(ManifestError):
            load_manifest(self.scratch / "none.toml")

    def test_invalid_toml(self):
        p = self.scratch / "bad.toml"
        p.write_text("[bale\npin = ", encoding="utf-8")
        with self.assertRaises(ManifestError):
            load_manifest(p)

    def test_missing_pin(self):
        p = self.scratch / "nopin.toml"
        p.write_text("[bale]\n[bale.schemas]\n", encoding="utf-8")
        with self.assertRaises(ManifestError):
            load_manifest(p)


if __name__ == "__main__":
    unittest.main()

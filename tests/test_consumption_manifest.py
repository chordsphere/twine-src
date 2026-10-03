"""share/bale-consumption.toml (D3, D4) as data a test can walk."""

from __future__ import annotations

import re
import tomllib
import unittest

from twine import CONSUMPTION_MANIFEST, REPO_ROOT, shapes
from twine.bale import ManifestError, load_manifest
from twine.registry import load_registry

from tests.helpers import (PIN, Role, TempRoots, carried_relpath, emission_relpath,
                           fixture_key, fixture_relpath)

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
        """A verb surface with a recording points at it by the naming rule
        (the argv normalized: a `<role>` placeholder names its role). One
        without names its stand-in, and the file the rule would give does
        not exist — so recording it forces this entry to be updated."""
        verbs = [s for s in self.manifest.surfaces if s["kind"] == "verb"]
        self.assertGreaterEqual(len(verbs), 3)
        for s in verbs:
            with self.subTest(argv=s["argv"]):
                expected = fixture_relpath(s["argv"], s["cwd"])
                if "fixture" in s:
                    self.assertEqual(s["fixture"], expected)
                    self.assertTrue((REPO_ROOT / s["fixture"]).is_file(), s["fixture"])
                else:
                    self.assertFalse((REPO_ROOT / expected).exists(),
                                     f"{expected} is recorded; point `fixture` at it")
                    self.assertTrue((REPO_ROOT / s["stand_in"]).is_file(), s["stand_in"])
                    self.assertTrue(s["doubles"])
                self.assertEqual(s["argv"][0], s["verb"])
                for flag in s["flags"]:
                    self.assertIn(flag, s["argv"])

    def test_per_run_placeholders_are_the_roles_the_key_gives(self):
        """`<sid>` and `<tarball>` in a manifest argv sit exactly where the
        normalization puts a role of that name."""
        for s in self.manifest.surfaces:
            if s["kind"] != "verb":
                continue
            key = fixture_key(s["argv"])
            for token, keyed in zip(s["argv"], key):
                with self.subTest(argv=s["argv"], token=token):
                    if token.startswith("<"):
                        self.assertIsInstance(keyed, Role)
                        self.assertEqual(token, f"<{keyed}>")
                    elif token != "-":
                        self.assertNotIsInstance(keyed, Role)

    def test_the_carry_hand_offs_bale_surfaces(self):
        """Session 2b-ii: carry response reads `outcome` from the dry run;
        carry exchange reads relay's stdout as text (no key), with the
        crafter's exchange emission standing in for it."""
        by_verb = {s["verb"]: s for s in self.manifest.surfaces if s["kind"] == "verb"}
        apply, relay = by_verb["apply"], by_verb["relay"]
        self.assertEqual((apply["argv"], apply["keys"], apply["read_by"]),
                         (["apply", "--dry-run", "--json", "<tarball>"], ["outcome"],
                          ["carry response"]))
        self.assertEqual((relay["argv"], relay["keys"], relay["read_by"]),
                         (["relay", "<sid>", "-"], [], ["carry exchange"]))
        self.assertEqual(relay["stand_in"],
                         emission_relpath("crafter", ["--emit-block", "-"]))

    def test_the_two_json_verbs_the_brief_names_are_recorded(self):
        argvs = [tuple(s["argv"]) for s in self.manifest.surfaces if s["kind"] == "verb"]
        self.assertIn(("status", "--json"), argvs)
        self.assertIn(("stats", "--json"), argvs)

    def test_one_format_entry_per_kind_take_parses(self):
        formats = [s["format"] for s in self.manifest.surfaces if s["kind"] == "format"]
        self.assertEqual(sorted(formats), sorted(shapes.KINDS))
        # take reads every format; carry probe (session 2b-i) also reads
        # the probe it runs and the probe-output it verifies, and carry
        # exchange (session 2b-ii) the exchange block it relays.
        carried = {shapes.PROBE: ["carry probe", "take"],
                   shapes.PROBE_OUTPUT: ["carry probe", "take"],
                   shapes.EXCHANGE: ["carry exchange", "take"]}
        for s in self.manifest.surfaces:
            if s["kind"] == "format":
                expected = carried.get(s["format"], ["take"])
                self.assertEqual(s["read_by"], expected, s["format"])

    def test_every_read_by_names_a_registered_verb(self):
        verbs = set(load_registry())
        for s in self.manifest.surfaces:
            for name in s["read_by"]:
                self.assertIn(name, verbs, s.get("verb") or s.get("path") or s.get("format"))

    def test_relay_json_is_wanted_by_session_2b_ii(self):
        wanted = {w["verb"]: w for w in self.manifest.data.get("wanted", [])}
        self.assertIn("2b-ii", wanted["relay"]["needed_by"])

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

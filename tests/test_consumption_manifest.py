"""share/bale-consumption.toml (D3, D4) as data a test can walk."""

from __future__ import annotations

import json
import re
import tomllib
import unittest

from twine import CONSUMPTION_MANIFEST, REPO_ROOT, shapes
from twine.bale import ManifestError, load_manifest
from twine.registry import load_registry

from tests.helpers import (BALE_VOCABULARIES, GROUP_SEP, PIN, UNLOCK_KEYS, UNLOCK_RECORDINGS,
                           Role, TempRoots, carried_relpath, emission_relpath, fixture_key,
                           fixture_relpath, split_group, unlock_recording)

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SCHEMA_FILES = {
    "bundle-manifest.schema.json", "changelog-record.schema.json",
    "diagnostics.schema.json", "escalation-record.schema.json",
    "exchange-record.schema.json", "request-manifest.schema.json",
    "response-manifest.schema.json", "telemetry-record.schema.json",
}
# The eight schema hashes, unchanged from 0.4.45 to 0.4.49 (the manifest's
# header says who hashed them and when); pinned here so a silent edit of
# the manifest's table fails by name.
SCHEMA_SHA256 = {
    "bundle-manifest.schema.json": "3384ebcd52a08044356f30f1031f4389e9b4427d81602173b0c59f4f9f9cea23",
    "changelog-record.schema.json": "7b6d351c052dad8588b05e7592da78f9e9052a671ad6dae9395bfd6d531c5b5c",
    "diagnostics.schema.json": "bfeef3cc0a6b91b47b1c1c9084ca47349b23a6661b10c848da3b4ef28b413521",
    "escalation-record.schema.json": "16729aae82e20425f91b9fb343de6a74d00fa417ce3cd718767413deee550c41",
    "exchange-record.schema.json": "c9c291899103c4a73768ef930697722b89c5c3ef8f5b388c78c36741316cddc8",
    "request-manifest.schema.json": "70a0c2bd3b6b0d4cf17bc97010c2b7d58931527b7b3100aa984ca3576c075e3d",
    "response-manifest.schema.json": "02d2b6413d078e031641c99e09a9fea909555bdfcb9b2a8a110dbdce63f5817e",
    "telemetry-record.schema.json": "b79d7bf75c10f5799484f906954461e7379ef6d4a870bb7df8c08ce050b38825",
}
SURFACE_REQUIRED = {"kind", "keys", "read_by", "written_against"}
VERB_REQUIRED = SURFACE_REQUIRED | {"verb", "flags", "argv", "cwd", "stdout"}
FILE_REQUIRED = SURFACE_REQUIRED | {"path"}
FORMAT_REQUIRED = SURFACE_REQUIRED | {"format", "locator", "home", "emitted_by",
                                      "fixtures", "fixtures_version"}
REQUIRED = {"file": FILE_REQUIRED, "verb": VERB_REQUIRED, "format": FORMAT_REQUIRED}
ALSO_RECORDED_REQUIRED = {"argv", "cwd", "outcome", "fixture"}
VOCABULARY_REQUIRED = {"axis", "values", "home", "pointer", "also_at", "excluded",
                       "read_by", "written_against", "read_at", "note"}
README_ROW = re.compile(r"^\| `(?P<file>[^`]+)` \| `(?P<cmd>[^`]+)` \|", re.M)
# The unlock refusal's reason codes at 0.4.49 (UNLOCK_REFUSAL_REASONS in
# bin/bale_report.py, read by the desk): the closed set `reason` takes.
UNLOCK_REASONS = ["hold-branch", "not-open", "several-open", "not-a-repo", "integration-json"]


def expected_relpath(entry: dict) -> str:
    """The path the naming rule gives an argv recorded in `cwd` with the
    outcome group a verb entry (or an also_recorded row) implies: the
    outcome, plus the reason where one is named, when the fixture carries
    a group at all; the plain name otherwise."""
    group = None
    if GROUP_SEP in entry["fixture"].rsplit("/", 1)[-1]:
        group = entry["outcome"]
        if entry.get("reason"):
            group += GROUP_SEP + entry["reason"]
    return fixture_relpath(entry["argv"], entry["cwd"], group)


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

    def test_the_schema_hashes_are_unchanged_at_the_pin(self):
        """0.4.49's eight schemas hash to 0.4.45's values (the desk's
        reading of bale-src's context tarball, 2026-10-07)."""
        self.assertEqual(load_manifest().schemas, SCHEMA_SHA256)


class SurfacesAreWalkable(unittest.TestCase):

    def setUp(self):
        self.manifest = load_manifest()

    def verbs(self) -> list[dict]:
        return [s for s in self.manifest.surfaces if s["kind"] == "verb"]

    def by_verb_and_flags(self) -> dict[tuple, dict]:
        return {(s["verb"], tuple(s["flags"])): s for s in self.verbs()}

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
        (the argv normalized: a `<role>` placeholder names its role; an argv
        recorded with more than one outcome names its group), and so does
        each `also_recorded` row — another outcome of the same argv, or
        another argv of the verb — whose recorded line carries the outcome
        (and reason) the row states. One without a recording names its
        stand-in and its doubles, and the file the rule would give does
        not exist — so recording it forces this entry to be updated. At
        0.4.49 no verb surface is `unrecorded`."""
        verbs = self.verbs()
        self.assertGreaterEqual(len(verbs), 3)
        for s in verbs:
            with self.subTest(argv=s["argv"]):
                self.assertNotIn("unrecorded", s)
                if "fixture" in s:
                    path = REPO_ROOT / s["fixture"]
                    self.assertTrue(path.is_file(), s["fixture"])
                    outcome = (json.loads(path.read_bytes())["outcome"]
                               if path.suffix == ".json" else None)
                    self.assertEqual(s["fixture"], expected_relpath(
                        {**s, "outcome": outcome, "reason": None}))
                    for row in s.get("also_recorded", []):
                        with self.subTest(argv=s["argv"], also=row["fixture"]):
                            self.assertTrue(ALSO_RECORDED_REQUIRED <= set(row), row)
                            other = REPO_ROOT / row["fixture"]
                            self.assertTrue(other.is_file(), row["fixture"])
                            line = json.loads(other.read_bytes())
                            self.assertEqual(line["outcome"], row["outcome"])
                            if isinstance(line.get("reason"), str):
                                self.assertEqual(row.get("reason"), line["reason"])
                            self.assertEqual(row["fixture"], expected_relpath(row))
                            self.assertEqual(row["argv"][0], s["verb"])
                else:
                    expected = fixture_relpath(s["argv"], s["cwd"])
                    self.assertFalse((REPO_ROOT / expected).exists(),
                                     f"{expected} is recorded; point `fixture` at it")
                    self.assertTrue((REPO_ROOT / s["stand_in"]).is_file(), s["stand_in"])
                    self.assertTrue(s["doubles"])
                self.assertEqual(s["argv"][0], s["verb"])
                for flag in s["flags"]:
                    self.assertIn(flag, s["argv"])

    def test_per_run_placeholders_are_the_roles_the_key_gives(self):
        """`<sid>`, `<tarball>`, `<file>`, `<bundle>` and `<goal>` in a
        manifest argv sit exactly where the normalization puts a role of
        that name — on the surfaces and on every also_recorded row."""
        argvs = [s["argv"] for s in self.verbs()]
        argvs += [row["argv"] for s in self.verbs() for row in s.get("also_recorded", [])]
        seen: set[str] = set()
        for argv in argvs:
            key = fixture_key(argv)
            self.assertEqual(len(key), len(argv))
            for token, keyed in zip(argv, key):
                with self.subTest(argv=argv, token=token):
                    if token.startswith("<"):
                        self.assertIsInstance(keyed, Role)
                        self.assertEqual(token, f"<{keyed}>")
                        seen.add(str(keyed))
                    elif token != "-":
                        self.assertNotIsInstance(keyed, Role)
        self.assertEqual(seen, {"sid", "tarball", "file", "bundle", "goal"})

    def test_the_two_new_roles_normalize_as_the_readme_says(self):
        """Session 2026-10-07-twine-pin-049-001's rules: every positional
        after `open` is the bundle (with or without --check), the positional
        right after `pack` is the goal while a flag's value stays, and a
        `--slug` value is joined to its flag in the name."""
        self.assertEqual(fixture_key(["open", "/tmp/x.bale-bundle", "--json"]),
                         ["open", Role("bundle"), "--json"])
        self.assertEqual(fixture_key(["open", "--check", "/tmp/x.bale-bundle", "--json"]),
                         ["open", "--check", Role("bundle"), "--json"])
        self.assertEqual(fixture_key(["pack", "a goal with spaces", "--slug", "ro",
                                      "--read-only", "--no-readme", "--json"]),
                         ["pack", Role("goal"), "--slug", "ro", "--read-only",
                          "--no-readme", "--json"])
        self.assertEqual(fixture_relpath(["pack", "g", "--slug", "ro", "--read-only",
                                          "--no-readme", "--json"], "scratch"),
                         f"fixtures/bale-{PIN}/scratch/"
                         "pack_goal_--slug-ro_--read-only_--no-readme_--json.json")
        self.assertEqual(fixture_relpath(["open", "--check", "/b", "--json"], "repo"),
                         f"fixtures/bale-{PIN}/twine-src/open_--check_bundle_--json.json")
        self.assertEqual(fixture_relpath(["open", "/b", "--json"], "scratch", "opened"),
                         f"fixtures/bale-{PIN}/scratch/open_bundle_--json+opened.json")
        # A flag-led unlock or pack has no positional to replace.
        self.assertEqual(fixture_key(["pack", "--json"]), ["pack", "--json"])
        self.assertEqual(fixture_key(["unlock", "--integration", "--json"]),
                         ["unlock", "--integration", "--json"])
        self.assertEqual(split_group("unlock_sid_--json+unlock-refused+not-open"),
                         ("unlock_sid_--json", "unlock-refused+not-open"))
        self.assertEqual(split_group("unlock_--json"), ("unlock_--json", None))

    def test_the_carry_hand_offs_bale_surfaces(self):
        """Session 2b-ii: carry response reads `outcome` from the dry run;
        carry exchange reads relay's stdout as text (no key), with the
        crafter's exchange emission standing in for it. At 0.4.49 the dry
        run is recorded with its exit in the scratch repository, and the
        scope-drift refusal beside it."""
        by = self.by_verb_and_flags()
        apply, relay = by[("apply", ("--dry-run", "--json"))], by[("relay", ())]
        self.assertEqual((apply["argv"], apply["keys"], apply["read_by"], apply["cwd"]),
                         (["apply", "--dry-run", "--json", "<tarball>"], ["outcome"],
                          ["carry response"], "scratch"))
        self.assertEqual(apply["fixture"], fixture_relpath(apply["argv"], "scratch", "dry-run"))
        self.assertEqual([(r["outcome"], r["fixture"]) for r in apply["also_recorded"]],
                         [("scope-drift-refused",
                           fixture_relpath(apply["argv"], "scratch", "scope-drift-refused"))])
        self.assertEqual((relay["argv"], relay["keys"], relay["read_by"]),
                         (["relay", "<sid>", "-"], [], ["carry exchange"]))
        self.assertEqual(relay["stand_in"],
                         emission_relpath("crafter", ["--emit-block", "-"]))

    def test_the_kill_switchs_unlock_surface(self):
        """Session 5b: `twine kill` runs exactly `bale unlock <sid> --reason
        aborted --json` and reads format_unlock_json's keys — at 0.4.49 the
        three the refusal line added too. The `aborted` close is recorded
        (session 2026-10-07-twine-pin-049-001), the five other outcomes
        beside it; no double and no `unrecorded` remain, the refusal's
        reason codes are the closed set the entry records, and the
        recording the tests replay is the file the entry names."""
        unlock = self.by_verb_and_flags()[("unlock", ("--reason", "--json"))]
        self.assertEqual((unlock["argv"], unlock["keys"], unlock["read_by"]),
                         (["unlock", "<sid>", "--reason", "aborted", "--json"],
                          ["outcome", "sid", "closure_reason", "telemetry",
                           "reason", "message", "open_sessions"], ["kill"]))
        self.assertTrue(set(unlock["keys"]) <= set(UNLOCK_KEYS))
        self.assertEqual(unlock["read_at"], ["twine-unlock-contract", "twine-unlock-code"])
        self.assertNotIn("stand_in", unlock)
        self.assertNotIn("unrecorded", unlock)
        self.assertNotIn("doubles", unlock)
        self.assertIn("format_unlock_json", unlock["key_owner"])
        self.assertNotRegex(unlock["key_owner"], r"lines? \d", "the function is the pointer")
        self.assertEqual(unlock["vocabulary"], "closure-reason")
        self.assertIn("aborted", self.manifest.vocabularies["closure-reason"]["values"])
        self.assertIn("kill", self.manifest.vocabularies["closure-reason"]["read_by"])
        self.assertEqual(unlock["reasons"], UNLOCK_REASONS)
        self.assertIn("UNLOCK_REFUSAL_REASONS", unlock["reasons_home"])
        self.assertNotIn("unlock-reason", self.manifest.vocabularies, "not a table axis")
        self.assertEqual(fixture_relpath(unlock["argv"], unlock["cwd"]),
                         f"fixtures/bale-{PIN}/scratch/unlock_sid_--reason-aborted_--json.json")
        self.assertEqual(unlock["fixture"], unlock_recording("aborted").relpath)
        also = {(r["outcome"], r.get("reason")): r["fixture"] for r in unlock["also_recorded"]}
        self.assertEqual(also, {
            ("unlock-refused", "hold-branch"): unlock_recording("hold-branch").relpath,
            ("unlock-refused", "not-open"): unlock_recording("not-open").relpath,
            ("unlock-refused", "integration-json"): unlock_recording("integration-json").relpath,
            ("unlocked", None): unlock_recording("closed-read-only").relpath,
            ("no-op", None): unlock_recording("no-op").relpath,
        })
        self.assertEqual(len(UNLOCK_RECORDINGS), 1 + len(also))
        for reason in (r for (_, r) in also if r):
            self.assertIn(reason, UNLOCK_REASONS)

    def test_every_json_verb_the_pin_bump_recorded_is_a_surface(self):
        """status and stats (the brief of session core-002), and the four
        verbs the 0.4.49 probes recorded under --json."""
        argvs = {tuple(s["argv"]) for s in self.verbs()}
        self.assertIn(("status", "--json"), argvs)
        self.assertIn(("stats", "--json"), argvs)
        verbs_with_json = {s["verb"] for s in self.verbs() if "--json" in s["flags"]}
        self.assertEqual(verbs_with_json, {"status", "stats", "apply", "relay", "open",
                                           "pack", "unlock"})

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

    def test_relay_json_is_a_surface_now(self):
        """Session 2b-ii wanted `bale relay --json`; bale 0.4.48 added it and
        the pin bump recorded it: a verb surface, read by nothing yet, the
        flagless relay surface staying beside it for carry exchange."""
        by = self.by_verb_and_flags()
        relay = by[("relay", ("--json",))]
        self.assertEqual((relay["argv"], relay["keys"], relay["read_by"], relay["cwd"]),
                         (["relay", "<sid>", "<file>", "--json"], [], [], "scratch"))
        self.assertIn("format_relay_json", relay["key_owner"])
        self.assertEqual([(r["outcome"], r.get("reason")) for r in relay["also_recorded"]],
                         [("re-emitted", None), ("relay-refused", "ingest"),
                          ("relay-refused", "session-gate")])
        self.assertIn(("relay", ()), by, "the flagless surface stays")
        self.assertIn("2b-ii", relay["note"])

    def test_every_format_fixture_exists_follows_naming_and_parses_as_its_kind(self):
        """Each fixture parses, with take's parser, as one intact block of
        the entry's kind, and sits where the naming rule puts it — computed
        from facts the name does not supply: a crafter emission's argv from
        its fixtures/README.md row, a carried paste's identity from the
        block's own sentinel and its version from the entry's
        `fixtures_version`. The probe fixture is the crafter's bare script;
        a turn carries it fenced, so it is wrapped in a fence."""
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
                    self.assertTrue(rel.startswith(f"fixtures/bale-{s['fixtures_version']}/"),
                                    rel)
                    text = shapes.normalize(path.read_bytes()).text
                    if s["format"] == shapes.PROBE:
                        text = "```bash\n" + text + "```\n"
                    blocks = shapes.find_blocks(text).blocks
                    self.assertEqual([(b.kind, b.ok) for b in blocks],
                                     [(s["format"], True)])
                    if path.parent.name == "crafter":
                        self.assertEqual(s["fixtures_version"], PIN,
                                         "a crafter emission is re-recorded at the pin")
                        cmd = readme_cmds[rel.removeprefix("fixtures/")]
                        expected = emission_relpath("crafter", cmd.split()[1:])
                    else:
                        f = blocks[0].fields
                        expected = carried_relpath(s["format"],
                                                   f.get("slug") or f.get("sid"),
                                                   f.get("to"))
                        self.assertEqual(expected, carried_relpath(
                            s["format"], f.get("slug") or f.get("sid"), f.get("to"),
                            version=s["fixtures_version"]))
                    self.assertEqual(rel, expected)

    def test_the_carried_pastes_stay_under_the_version_that_printed_them(self):
        """The desk's preference, ratified by this landing: the two 0.4.45
        pastes are pointed at by path, not copied under bale-0.4.49/."""
        by_format = {s["format"]: s for s in self.manifest.surfaces if s["kind"] == "format"}
        self.assertEqual({k: v["fixtures_version"] for k, v in by_format.items()},
                         {"probe": PIN, "light": PIN, "exchange": PIN,
                          "probe-output": "0.4.45", "relay": "0.4.45"})
        self.assertFalse((REPO_ROOT / f"fixtures/bale-{PIN}/carried").exists())

    def test_no_wanted_surface_remains(self):
        """The three gaps the 0.4.45 manifest carried — `open --json`,
        `relay --json`, a reason-coded `unlock --json` refusal — landed in
        bale (0.4.47, 0.4.48) and are surfaces now; the shape stays in the
        header for the next gap."""
        self.assertEqual(self.manifest.data.get("wanted", []), [])
        by = self.by_verb_and_flags()
        for verb in ("open", "relay", "unlock"):
            with self.subTest(verb=verb):
                entry = next(s for (v, flags), s in by.items() if v == verb and "--json" in flags)
                self.assertIn("fixture", entry)
        header = CONSUMPTION_MANIFEST.read_text(encoding="utf-8").split("[bale]", 1)[0]
        self.assertIn("[[wanted]]", header)

    def test_open_json_is_a_surface_read_by_nothing_yet(self):
        """Arc 1 session 3's wanted verb, recorded: opened, second-desk and,
        with --check, rehearsed — read by [] until row 3's verb exists, the
        way --version reads nothing."""
        open_ = self.by_verb_and_flags()[("open", ("--json",))]
        self.assertEqual((open_["argv"], open_["keys"], open_["read_by"]),
                         (["open", "<bundle>", "--json"], [], []))
        self.assertIn("format_open_json", open_["key_owner"])
        self.assertIn("opener", open_["key_owner"])
        self.assertEqual([(r["argv"], r["cwd"], r["outcome"]) for r in open_["also_recorded"]],
                         [(["open", "<bundle>", "--json"], "scratch", "second-desk"),
                          (["open", "--check", "<bundle>", "--json"], "repo", "rehearsed")])
        pack = self.by_verb_and_flags()[("pack", ("--json",))]
        self.assertEqual((pack["argv"][:2], pack["read_by"]), (["pack", "<goal>"], []))
        self.assertIn("opener", pack["key_owner"])
        self.assertIn("opener", json.loads((REPO_ROOT / pack["fixture"]).read_bytes()))

    def test_the_unlock_refusal_line_is_what_the_entry_says(self):
        """Session 5c asked bale-src for a refusal printed as a JSON line
        with a reason code; 0.4.47's is recorded: outcome unlock-refused,
        a reason from the closed set, bale's message, nothing closed. No
        recording carries a stderr — none was recorded and none is derived
        (session 2026-10-07-twine-kill-reason-002): twine reads the refusal
        by its `reason`."""
        for name in ("hold-branch", "not-open", "integration-json"):
            with self.subTest(recording=name):
                rec = unlock_recording(name)
                self.assertEqual((rec.exit_code, rec.line["outcome"], rec.line["reason"]),
                                 (1, "unlock-refused", name))
                self.assertIn(rec.line["reason"], UNLOCK_REASONS)
                self.assertTrue(rec.line["message"])
                self.assertIsNone(rec.line["closure_reason"])
                self.assertEqual(tuple(rec.line), UNLOCK_KEYS)
                self.assertEqual(rec.stderr, b"")
        close = unlock_recording("aborted")
        self.assertEqual((close.exit_code, close.line["outcome"], close.line["closure_reason"],
                          close.line["reason"], close.stderr),
                         (0, "unlocked", "aborted", None, b""))


class VocabulariesAreWalkable(unittest.TestCase):
    """[[vocabulary]] (session 2026-10-03-twine-transitions-004): bale's three
    closed vocabularies, as data a pin bump diffs (D4), keyed on by the
    transition table's bale axes."""

    def setUp(self):
        self.manifest = load_manifest()
        self.entries = self.manifest.data["vocabulary"]

    def test_every_entry_has_the_required_fields(self):
        for entry in self.entries:
            with self.subTest(axis=entry.get("axis")):
                self.assertTrue(VOCABULARY_REQUIRED <= set(entry),
                                VOCABULARY_REQUIRED - set(entry))
                self.assertEqual(entry["written_against"], PIN)
                self.assertTrue(entry["read_at"] and entry["note"])
                for listed in ("values", "also_at", "excluded", "read_by", "read_at"):
                    self.assertIsInstance(entry[listed], list, listed)

    def test_the_three_vocabularies_are_bales_spellings_in_bales_order(self):
        """Held to the probe's lists (tests/helpers.py BALE_VOCABULARIES),
        exactly: no value more or fewer, none respelled, none reordered."""
        self.assertEqual({axis: v["values"] for axis, v in self.manifest.vocabularies.items()},
                         BALE_VOCABULARIES)

    def test_each_home_is_an_installed_file_twine_pins(self):
        """A schema home is one of the eight whose sha256 [bale.schemas]
        pins; a source-file home records the sha256 as read at the pin —
        bin/bale_report.py's at 0.4.49, format_apply_json at line 3040."""
        for entry in self.entries:
            with self.subTest(axis=entry["axis"]):
                home = entry["home"]
                if home.startswith("schemas/"):
                    self.assertIn(home.removeprefix("schemas/"), self.manifest.schemas)
                    self.assertNotIn("home_sha256", entry)
                    self.assertTrue(entry["pointer"].startswith("/properties/"))
                else:
                    self.assertTrue(home.startswith("bin/"), home)
                    self.assertRegex(entry["home_sha256"], SHA256)
        apply = self.manifest.vocabularies["apply-outcome"]
        self.assertEqual(apply["home_sha256"],
                         "20871bc61408ef9a21a2d14789399463cf5ed9a92802b951f6a1438fe75b0c78")
        self.assertIn("line 3040", apply["pointer"])

    def test_the_re_reading_at_the_pin_is_named_as_not_a_probe(self):
        """The pin bump re-read the vocabularies from bale-src's context
        tarball, not by probe; each entry's read_at says so beside the
        probe that first read it."""
        for entry in self.entries:
            with self.subTest(axis=entry["axis"]):
                self.assertTrue(entry["read_at"][0].startswith("twine-"))
                self.assertTrue(any("not a probe" in r and "0.4.49" in r
                                    for r in entry["read_at"][1:]), entry["read_at"])

    def test_null_is_excluded_from_the_closure_reasons_by_name(self):
        closure = self.manifest.vocabularies["closure-reason"]
        self.assertNotIn("null", closure["values"])
        self.assertEqual(len(closure["excluded"]), 1)
        self.assertTrue(closure["excluded"][0].startswith("null:"))

    def test_every_read_by_names_a_registered_verb(self):
        verbs = set(load_registry())
        for entry in self.entries:
            self.assertTrue(entry["read_by"], entry["axis"])
            for name in entry["read_by"]:
                self.assertIn(name, verbs, entry["axis"])

    def test_the_manifest_and_the_tables_bale_axes_agree(self):
        """The table's bale axes take their keys from these lists; its rows
        on those axes are exactly the lists' values (the brief's item 6)."""
        from twine.transitions import SOURCE_BALE, load_table
        table = load_table(manifest=self.manifest)
        bale_axes = {a.name: list(a.keys) for a in table.axes if a.source == SOURCE_BALE}
        self.assertEqual(bale_axes, {axis: v["values"]
                                     for axis, v in self.manifest.vocabularies.items()})
        for axis, values in bale_axes.items():
            with self.subTest(axis=axis):
                self.assertEqual(sorted(r.key for r in table.rows if r.axis == axis),
                                 sorted(values))

    def test_the_apply_surface_names_its_outcome_vocabulary(self):
        """`apply`'s `outcome` takes the apply-outcome values; the one
        carry response accepts is one of them, and so are the two
        recorded outcomes."""
        from twine.commands.carry_bale import DRY_RUN_OUTCOME
        apply = next(s for s in self.manifest.surfaces if s.get("verb") == "apply")
        self.assertEqual(apply["vocabulary"], "apply-outcome")
        self.assertIn("outcome", apply["keys"])
        values = self.manifest.vocabularies["apply-outcome"]["values"]
        self.assertIn(DRY_RUN_OUTCOME, values)
        for rel in [apply["fixture"], *(r["fixture"] for r in apply["also_recorded"])]:
            self.assertIn(json.loads((REPO_ROOT / rel).read_bytes())["outcome"], values)
        for s in self.manifest.surfaces:
            if "vocabulary" in s:
                self.assertIn(s["vocabulary"], self.manifest.vocabularies)


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

    def test_malformed_vocabularies_refuse_naming_why(self):
        head = f'[bale]\npin = "{PIN}"\n[bale.schemas]\n'
        cases = {
            "no axis": '[[vocabulary]]\nvalues = ["a"]\nhome = "h"\n',
            "two [[vocabulary]] entries": ('[[vocabulary]]\naxis = "x"\nvalues = ["a"]\nhome = "h"\n'
                            '[[vocabulary]]\naxis = "x"\nvalues = ["b"]\nhome = "h"\n'),
            "non-empty list": '[[vocabulary]]\naxis = "x"\nvalues = []\nhome = "h"\n',
            "repeats": '[[vocabulary]]\naxis = "x"\nvalues = ["a", "a"]\nhome = "h"\n',
            "no home": '[[vocabulary]]\naxis = "x"\nvalues = ["a"]\n',
        }
        for needle, body in cases.items():
            with self.subTest(case=needle):
                p = self.scratch / "vocab.toml"
                p.write_text(head + body, encoding="utf-8")
                with self.assertRaises(ManifestError) as caught:
                    load_manifest(p)
                self.assertIn(needle, str(caught.exception))


if __name__ == "__main__":
    unittest.main()

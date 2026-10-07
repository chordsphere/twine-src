"""fixtures/: every recorded output of the pinned version parses, is one
line, is named by the rule and is listed in fixtures/README.md with its
hash; the carried pastes a format entry points at (under the version that
printed them) differ from what arrived only by CRLF."""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from collections import defaultdict

from twine import FIXTURES_DIR
from twine.bale import load_manifest

from tests.helpers import (GROUP_SEP, PIN, UNLOCK_RECORDED_SID, UNRECORDED, fixture_stem,
                           fixture_key, split_group)

README = FIXTURES_DIR / "README.md"
# The exit cell is a number, or `unrecorded` when the recording did not
# capture it (session 2026-10-03-twine-carry-bale-002) — never a guess.
ROW = re.compile(r"^\| `(?P<file>[^`]+)` \| `(?P<cmd>[^`]+)` \| `[^`]+` "
                 r"\| (?P<exit>\d+|unrecorded) "
                 r"\| (?P<bytes>\d+) \| `(?P<sha>[0-9a-f]{64})` \|$", re.M)
# Every fixture row, whichever table: the file first, bytes and sha256 last.
ANY_ROW = re.compile(r"^\| `(?P<file>bale-[^`]+)` \|.*\| (?P<bytes>\d+) "
                     r"\| `(?P<sha>[0-9a-f]{64})` \|$", re.M)
# A carried paste's row also records the bytes as received.
CARRIED_ROW = re.compile(r"^\| `(?P<file>bale-[^`]+/carried/[^`]+)` \| [^|]+ "
                         r"\| CRLF (?P<rbytes>\d+) `(?P<rsha>[0-9a-f]{64})` "
                         r"\| (?P<bytes>\d+) \| `(?P<sha>[0-9a-f]{64})` \|$", re.M)
# The command each table's rows name, by fixture directory.
COMMAND_PREFIX = {"twine-src": "bale ", "anywhere": "bale ", "scratch": "bale ",
                  "crafter": "craft_response.py "}
PINNED = f"bale-{PIN}"
# The 0.4.49 dry run (fixtures/README.md, "bale 0.4.49", row 15): recorded
# in the scratch repository for its scoped session, with its exit.
DRY_RUN = f"{PINNED}/scratch/apply_--dry-run_--json_tarball+dry-run.json"
DRY_RUN_BYTES, DRY_RUN_SHA = 290, "266fc2539c08511d1ee29cb29442eacad6d6ebdab738723c3c0bf440fac8b955"


def recorded_files() -> list:
    return sorted(p for p in (FIXTURES_DIR / PINNED).rglob("*") if p.is_file())


def carried_files() -> list:
    """The carried pastes the manifest's format entries point at, under the
    version each names (fixtures_version) — not the pinned directory,
    which a paste never moves into."""
    found = []
    for s in load_manifest().surfaces:
        if s["kind"] == "format":
            for rel in s["fixtures"]:
                path = FIXTURES_DIR.parent / rel
                if path.parent.name == "carried":
                    found.append((s["fixtures_version"], path))
    return found


class FixturesParse(unittest.TestCase):

    def test_at_least_the_brief_s_three(self):
        names = {p.relative_to(FIXTURES_DIR).as_posix() for p in recorded_files()}
        self.assertLessEqual({f"{PINNED}/twine-src/status_--json.json",
                              f"{PINNED}/twine-src/stats_--json.json",
                              f"{PINNED}/anywhere/--version.txt"}, names)

    def test_every_json_fixture_is_one_object_line(self):
        for p in recorded_files():
            if p.suffix != ".json":
                continue
            with self.subTest(fixture=p.name):
                data = p.read_bytes()
                self.assertTrue(data.endswith(b"\n"))
                self.assertEqual(data.count(b"\n"), 1, "exactly one line")
                obj = json.loads(data)
                self.assertIsInstance(obj, dict)
                self.assertIn("outcome", obj)

    def test_status_fixture_names_the_pinned_version(self):
        obj = json.loads((FIXTURES_DIR / f"{PINNED}/twine-src/status_--json.json").read_bytes())
        self.assertEqual(obj["version"], PIN)

    def test_dry_run_fixture_is_the_recorded_line(self):
        """The 0.4.49 dry run, recorded by probe twine-049-scratch in the
        throwaway repository for its scoped session (session
        2026-10-07-twine-pin-049-001): byte-exact under its grouped name,
        exit 0 in its row — the 0.4.45 carried line, exit unrecorded, is
        history under bale-0.4.45/."""
        p = FIXTURES_DIR / DRY_RUN
        data = p.read_bytes()
        self.assertEqual((len(data), hashlib.sha256(data).hexdigest()),
                         (DRY_RUN_BYTES, DRY_RUN_SHA))
        obj = json.loads(data)
        self.assertEqual((obj["outcome"], obj["sid"]), ("dry-run", UNLOCK_RECORDED_SID))
        rows = {m["file"]: m["exit"] for m in ROW.finditer(README.read_text(encoding="utf-8"))}
        self.assertEqual(rows[DRY_RUN], "0")

    def test_version_fixture_is_bale_pin(self):
        text = (FIXTURES_DIR / f"{PINNED}/anywhere/--version.txt").read_text(encoding="utf-8")
        self.assertEqual(text, f"bale {PIN}\n")

    def test_the_pinned_directory_holds_the_twenty_three(self):
        """The pin bump landed twenty-three recordings: twenty bale argvs
        and the three crafter emissions (fixtures/README.md, bale 0.4.49)."""
        files = recorded_files()
        by_where = defaultdict(int)
        for p in files:
            by_where[p.parent.name] += 1
        self.assertEqual(dict(by_where), {"anywhere": 1, "twine-src": 6, "scratch": 13,
                                          "crafter": 3})


class NamedByTheRule(unittest.TestCase):
    """Every recorded bale argv's file is its normalized name, and an argv
    recorded with more than one outcome in the version carries its
    outcome group — `+<outcome>` and, where that still collides, `+<reason>`
    (fixtures/README.md, "Outcome groups") — never the plain name."""

    def setUp(self):
        self.text = README.read_text(encoding="utf-8")
        self.rows = {m["file"]: m for m in ROW.finditer(self.text)}

    def argv_files(self) -> list:
        return [p for p in recorded_files() if p.parent.name in ("twine-src", "anywhere", "scratch")]

    def test_each_name_is_its_commands_normalized_name(self):
        """The README row's command, normalized by fixture_key, spells the
        file's stem — so the per-run roles (sid, file, tarball, bundle,
        goal) are exactly where the rule puts them."""
        for p in self.argv_files():
            rel = p.relative_to(FIXTURES_DIR).as_posix()
            with self.subTest(fixture=rel):
                cmd = self.rows[rel]["cmd"]
                self.assertTrue(cmd.startswith("bale "))
                argv = cmd.split(" ")[1:]
                if argv[0] == "pack":
                    # the goal carries spaces: everything before --slug
                    cut = argv.index("--slug")
                    argv = ["pack", " ".join(argv[1:cut]), *argv[cut:]]
                stem, ext = fixture_stem(argv)
                self.assertEqual(p.suffix, ext)
                self.assertEqual(split_group(p.stem)[0], stem)
                self.assertEqual(fixture_key(argv), fixture_key(fixture_key(argv)),
                                 "normalizing is idempotent")

    def test_outcome_groups_follow_the_collision_rule(self):
        groups: dict[str, list] = defaultdict(list)
        for p in self.argv_files():
            stem, group = split_group(p.stem)
            groups[(stem, p.suffix)].append((p, group))
        for (stem, ext), members in groups.items():
            with self.subTest(argv=stem):
                if len(members) == 1:
                    self.assertIsNone(members[0][1], f"{stem}: recorded once, so no group")
                    continue
                lines = {p: json.loads(p.read_bytes()) for p, _ in members}
                outcomes = defaultdict(list)
                for p, group in members:
                    self.assertIsNotNone(group, f"{p.name}: recorded {len(members)} times, "
                                                "so every one carries a group")
                    parts = group.split(GROUP_SEP)
                    self.assertEqual(parts[0], lines[p]["outcome"], p.name)
                    outcomes[parts[0]].append((p, parts[1:]))
                for outcome, same in outcomes.items():
                    for p, rest in same:
                        if len(same) == 1:
                            self.assertEqual(rest, [], f"{p.name}: outcome alone suffices")
                            continue
                        self.assertEqual(len(rest), 1, f"{p.name}: one reason tag")
                        reason = lines[p].get("reason")
                        if isinstance(reason, str):
                            self.assertEqual(rest[0], reason, f"{p.name}: the line's reason")
                        else:
                            self.assertRegex(rest[0], r"^[a-z][a-z0-9-]*$",
                                             f"{p.name}: a tag the README assigns")
                            self.assertIn(f"`{outcome}{GROUP_SEP}{rest[0]}`", self.text,
                                          "the README's section explains the tag")

    def test_the_groups_this_section_names(self):
        """The grouped names, as fixtures/README.md's 0.4.49 section lists
        them — a reader's check that the rule produced what it says."""
        grouped = sorted(p.relative_to(FIXTURES_DIR / PINNED).as_posix()
                         for p in self.argv_files() if GROUP_SEP in p.name)
        self.assertEqual(grouped, [
            "scratch/apply_--dry-run_--json_tarball+dry-run.json",
            "scratch/apply_--dry-run_--json_tarball+scope-drift-refused.json",
            "scratch/open_bundle_--json+opened.json",
            "scratch/open_bundle_--json+second-desk.json",
            "scratch/relay_sid_file_--json+relay-refused+ingest.json",
            "scratch/relay_sid_file_--json+relay-refused+session-gate.json",
            "scratch/relay_sid_file_--json+relayed.json",
            "scratch/unlock_sid_--json+unlock-refused+hold-branch.json",
            "scratch/unlock_sid_--json+unlocked.json",
            "twine-src/unlock_sid_--json+unlock-refused+not-open.json",
        ])


class ReadmeListsEveryFixture(unittest.TestCase):

    def setUp(self):
        self.text = README.read_text(encoding="utf-8")

    def test_rows_match_files_bytes_and_hashes(self):
        """The pinned version's rows and files are the same set, byte for
        byte; earlier versions' rows stay as history and are not compared
        against the pinned directory."""
        rows = {m["file"]: m for m in ANY_ROW.finditer(self.text)
                if m["file"].startswith(PINNED + "/")}
        files = {p.relative_to(FIXTURES_DIR).as_posix(): p for p in recorded_files()}
        self.assertEqual(set(rows), set(files), "README rows and fixture files differ")
        for rel, p in files.items():
            with self.subTest(fixture=rel):
                data = p.read_bytes()
                self.assertEqual(int(rows[rel]["bytes"]), len(data))
                self.assertEqual(rows[rel]["sha"], hashlib.sha256(data).hexdigest())

    def test_earlier_versions_rows_still_match_their_files(self):
        """History stays readable: every row of every section names a file
        that exists with those bytes (bale-0.4.45/ is untouched)."""
        rows = {m["file"]: m for m in ANY_ROW.finditer(self.text)}
        self.assertTrue(any(f.startswith("bale-0.4.45/") for f in rows))
        for rel, m in rows.items():
            with self.subTest(fixture=rel):
                data = (FIXTURES_DIR / rel).read_bytes()
                self.assertEqual((int(m["bytes"]), m["sha"]),
                                 (len(data), hashlib.sha256(data).hexdigest()))

    def test_command_rows_name_their_emitter(self):
        """A recorded output's row names the command that printed it: a
        bale argv under twine-src/, scratch/ and anywhere/, the crafter
        under crafter/."""
        rows = {m["file"]: m for m in ROW.finditer(self.text)}
        for p in recorded_files():
            rel = p.relative_to(FIXTURES_DIR).as_posix()
            where = rel.split("/")[1]
            self.assertIn(where, COMMAND_PREFIX, rel)
            with self.subTest(fixture=rel):
                self.assertIn(rel, rows)
                self.assertTrue(rows[rel]["cmd"].startswith(COMMAND_PREFIX[where]))

    def test_an_unrecorded_exit_is_said_never_guessed(self):
        """Every row of the pinned section has its exit (the three probes
        printed each one); the `unrecorded` vocabulary stays for a row that
        lacks one — the 0.4.45 carried dry run is such a row, as history —
        and the player refuses to answer such a row without a named
        assumption (tests/test_process.py)."""
        rows = {m["file"]: m["exit"] for m in ROW.finditer(self.text)}
        pinned = {f: e for f, e in rows.items() if f.startswith(PINNED + "/")}
        self.assertEqual(len(pinned), 23)
        self.assertNotIn(UNRECORDED, pinned.values())
        # The refusals exited 1 — the line says so by its outcome — and
        # everything else 0.
        for rel, exit_cell in pinned.items():
            with self.subTest(fixture=rel):
                path = FIXTURES_DIR / rel
                refused = (path.suffix == ".json"
                           and json.loads(path.read_bytes())["outcome"].endswith("-refused"))
                self.assertEqual(exit_cell, "1" if refused else "0")
        history = "bale-0.4.45/twine-src/apply_--dry-run_--json_tarball.json"
        self.assertEqual(rows[history], UNRECORDED)

    def test_carried_pastes_differ_from_what_arrived_only_by_crlf(self):
        """A carried paste is landed CRLF -> LF and nothing else: the LFs
        turned back into CRLFs are the received bytes, by count and hash.
        The pastes are found through the manifest's format entries, under
        the version each names — they do not move at a pin bump."""
        rows = {m["file"]: m for m in CARRIED_ROW.finditer(self.text)}
        carried = carried_files()
        self.assertGreaterEqual(len(carried), 2)
        for version, p in carried:
            rel = p.relative_to(FIXTURES_DIR).as_posix()
            with self.subTest(fixture=rel):
                self.assertTrue(rel.startswith(f"bale-{version}/carried/"), rel)
                self.assertTrue(p.is_file(), rel)
                self.assertIn(rel, rows)
                data = p.read_bytes()
                self.assertNotIn(b"\r", data)
                received = data.replace(b"\n", b"\r\n")
                self.assertEqual(int(rows[rel]["rbytes"]), len(received))
                self.assertEqual(rows[rel]["rsha"], hashlib.sha256(received).hexdigest())
                self.assertEqual(int(rows[rel]["bytes"]), len(data))
                self.assertEqual(rows[rel]["sha"], hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main()

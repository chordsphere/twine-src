"""fixtures/: every recorded output parses, is one line, and is listed
in fixtures/README.md with its hash."""

from __future__ import annotations

import hashlib
import json
import re
import unittest

from twine import FIXTURES_DIR

from tests.helpers import PIN

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
COMMAND_PREFIX = {"twine-src": "bale ", "anywhere": "bale ",
                  "crafter": "craft_response.py "}


def recorded_files() -> list:
    return sorted(p for p in (FIXTURES_DIR / f"bale-{PIN}").rglob("*") if p.is_file())


class FixturesParse(unittest.TestCase):

    def test_at_least_the_brief_s_three(self):
        names = {p.relative_to(FIXTURES_DIR).as_posix() for p in recorded_files()}
        self.assertLessEqual({f"bale-{PIN}/twine-src/status_--json.json",
                              f"bale-{PIN}/twine-src/stats_--json.json",
                              f"bale-{PIN}/anywhere/--version.txt"}, names)

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
        obj = json.loads((FIXTURES_DIR / f"bale-{PIN}/twine-src/status_--json.json").read_bytes())
        self.assertEqual(obj["version"], PIN)

    def test_dry_run_fixture_is_the_recorded_line(self):
        """The architect's apply-dry-run-carry-probe.json, landed byte-exact
        under its normalized name (session 2026-10-03-twine-carry-bale-002)."""
        p = FIXTURES_DIR / f"bale-{PIN}/twine-src/apply_--dry-run_--json_tarball.json"
        data = p.read_bytes()
        self.assertEqual((len(data), hashlib.sha256(data).hexdigest()),
                         (315, "f5bd7e5bbb92363b2993e2aaba5816dc3428dd7acdc0c51e8e194a49c43471ce"))
        obj = json.loads(data)
        self.assertEqual((obj["outcome"], obj["sid"]),
                         ("dry-run", "2026-10-02-twine-carry-probe-002"))

    def test_version_fixture_is_bale_pin(self):
        text = (FIXTURES_DIR / f"bale-{PIN}/anywhere/--version.txt").read_text(encoding="utf-8")
        self.assertEqual(text, f"bale {PIN}\n")


class ReadmeListsEveryFixture(unittest.TestCase):

    def setUp(self):
        self.text = README.read_text(encoding="utf-8")

    def test_rows_match_files_bytes_and_hashes(self):
        rows = {m["file"]: m for m in ANY_ROW.finditer(self.text)}
        files = {p.relative_to(FIXTURES_DIR).as_posix(): p for p in recorded_files()}
        self.assertEqual(set(rows), set(files), "README rows and fixture files differ")
        for rel, p in files.items():
            with self.subTest(fixture=rel):
                data = p.read_bytes()
                self.assertEqual(int(rows[rel]["bytes"]), len(data))
                self.assertEqual(rows[rel]["sha"], hashlib.sha256(data).hexdigest())

    def test_command_rows_name_their_emitter(self):
        """A recorded output's row names the command that printed it: a
        bale argv under twine-src/ and anywhere/, the crafter under
        crafter/."""
        rows = {m["file"]: m for m in ROW.finditer(self.text)}
        for p in recorded_files():
            rel = p.relative_to(FIXTURES_DIR).as_posix()
            where = rel.split("/")[1]
            if where not in COMMAND_PREFIX:
                continue
            with self.subTest(fixture=rel):
                self.assertIn(rel, rows)
                self.assertTrue(rows[rel]["cmd"].startswith(COMMAND_PREFIX[where]))

    def test_an_unrecorded_exit_is_said_never_guessed(self):
        """The dry-run row's exit is `unrecorded`; every other recorded
        row's is 0."""
        rows = {m["file"]: m["exit"] for m in ROW.finditer(self.text)}
        dry = f"bale-{PIN}/twine-src/apply_--dry-run_--json_tarball.json"
        self.assertEqual(rows[dry], "unrecorded")
        self.assertIn("<tarball: unrecorded>",
                      next(m["cmd"] for m in ROW.finditer(self.text) if m["file"] == dry))
        self.assertEqual({e for f, e in rows.items() if f != dry}, {"0"})

    def test_carried_pastes_differ_from_what_arrived_only_by_crlf(self):
        """A carried paste is landed CRLF -> LF and nothing else: the LFs
        turned back into CRLFs are the received bytes, by count and hash."""
        rows = {m["file"]: m for m in CARRIED_ROW.finditer(self.text)}
        carried = [p for p in recorded_files() if p.parent.name == "carried"]
        self.assertGreaterEqual(len(carried), 2)
        for p in carried:
            rel = p.relative_to(FIXTURES_DIR).as_posix()
            with self.subTest(fixture=rel):
                self.assertIn(rel, rows)
                data = p.read_bytes()
                self.assertNotIn(b"\r", data)
                received = data.replace(b"\n", b"\r\n")
                self.assertEqual(int(rows[rel]["rbytes"]), len(received))
                self.assertEqual(rows[rel]["rsha"], hashlib.sha256(received).hexdigest())


if __name__ == "__main__":
    unittest.main()

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
ROW = re.compile(r"^\| `(?P<file>[^`]+)` \| `(?P<cmd>[^`]+)` \| `[^`]+` \| (?P<exit>\d+) "
                 r"\| (?P<bytes>\d+) \| `(?P<sha>[0-9a-f]{64})` \|$", re.M)


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

    def test_version_fixture_is_bale_pin(self):
        text = (FIXTURES_DIR / f"bale-{PIN}/anywhere/--version.txt").read_text(encoding="utf-8")
        self.assertEqual(text, f"bale {PIN}\n")


class ReadmeListsEveryFixture(unittest.TestCase):

    def test_rows_match_files_bytes_and_hashes(self):
        rows = {m["file"]: m for m in ROW.finditer(README.read_text(encoding="utf-8"))}
        files = {p.relative_to(FIXTURES_DIR).as_posix(): p for p in recorded_files()}
        self.assertEqual(set(rows), set(files), "README rows and fixture files differ")
        for rel, p in files.items():
            with self.subTest(fixture=rel):
                data = p.read_bytes()
                self.assertEqual(int(rows[rel]["bytes"]), len(data))
                self.assertEqual(rows[rel]["sha"], hashlib.sha256(data).hexdigest())
                self.assertTrue(rows[rel]["cmd"].startswith("bale "))


if __name__ == "__main__":
    unittest.main()

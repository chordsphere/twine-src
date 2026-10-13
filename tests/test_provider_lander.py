"""bin/twine-land-provider-recordings (Arc 2 R2): the lander of a
provider's wire recordings, the sibling of bin/twine-land-recordings.

It is run the way the operator runs it — `python3 -I -S -B` as a
subprocess, on the carried paste of 2026-10-13 and on edited copies of it
in temp trees (the edits are doubles of a paste, named as such: what a
truncated, tampered or mis-named paste-back would be). Nothing here
reaches a network.

Sections:
  1. --check on the real tree
  2. Landing into an empty tree
  3. What it refuses
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from twine import FIXTURES_DIR, REPO_ROOT

LANDER = REPO_ROOT / "bin" / "twine-land-provider-recordings"
PASTE = FIXTURES_DIR / "anthropic" / "carried" / "twine-anthropic-record-2026-10-13.txt"


def land(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", "-S", "-B", str(LANDER), *argv],
                          capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"})


def derived_files() -> list[str]:
    """What the paste derives, relative to fixtures/ — read from the tree's
    meta files (each names its request and response) plus the paste."""
    out = []
    for meta in sorted((FIXTURES_DIR / "anthropic").glob("*.meta.json")):
        m = json.loads(meta.read_bytes())
        out += [p for p in (m["request_file"], m["response_file"]) if p]
        out.append(meta.relative_to(FIXTURES_DIR).as_posix())
    return sorted(out + [PASTE.relative_to(FIXTURES_DIR).as_posix()])


class TempTree:
    """An empty repository with only fixtures/README.md copied (for the
    rows --check reads), and the paste written where the test says."""

    def __init__(self, test: unittest.TestCase) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="twine-provider-lander-")
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "fixtures").mkdir()
        shutil.copyfile(FIXTURES_DIR / "README.md", self.root / "fixtures" / "README.md")

    def paste(self, data: bytes, name: str = "paste.txt") -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path


def edited(old: str, new: str) -> bytes:
    """The carried paste with one edit — a double of a paste-back."""
    text = PASTE.read_text(encoding="utf-8")
    assert old in text, old
    return text.replace(old, new, 1).encode("utf-8")


class CheckTheRealTree(unittest.TestCase):

    def test_check_is_ok_and_writes_nothing(self):
        before = {p: p.stat().st_mtime_ns for p in (FIXTURES_DIR / "anthropic").rglob("*")}
        run = land(str(PASTE), "--check")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("ok", run.stderr)
        self.assertIn("15 recordings", run.stderr)
        self.assertEqual(run.stdout, "")
        after = {p: p.stat().st_mtime_ns for p in (FIXTURES_DIR / "anthropic").rglob("*")}
        self.assertEqual(before, after)

    def test_the_paste_derives_forty_five_files(self):
        self.assertEqual(len(derived_files()), 15 + 14 + 15 + 1)


class LandIntoAnEmptyTree(unittest.TestCase):

    def test_lands_every_file_byte_exact_and_prints_the_rows(self):
        tree = TempTree(self)
        run = land(str(PASTE), "--tree", str(tree.root))
        self.assertEqual(run.returncode, 0, run.stderr)
        landed = sorted(p.relative_to(tree.root / "fixtures").as_posix()
                        for p in (tree.root / "fixtures" / "anthropic").rglob("*")
                        if p.is_file())
        self.assertEqual(landed, derived_files())
        for rel in landed:
            with self.subTest(file=rel):
                self.assertEqual((tree.root / "fixtures" / rel).read_bytes(),
                                 (FIXTURES_DIR / rel).read_bytes())
        for rel in landed:
            data = (FIXTURES_DIR / rel).read_bytes()
            self.assertIn(f"| `{rel}` | {len(data)} | `{hashlib.sha256(data).hexdigest()}` |",
                          run.stdout)
        # the landed tree, with the real README, checks ok
        check = land(str(PASTE), "--check", "--tree", str(tree.root))
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_a_crlf_paste_lands_the_same_lf_bytes_and_says_crlf(self):
        tree = TempTree(self)
        crlf = tree.paste(PASTE.read_bytes().replace(b"\n", b"\r\n"))
        run = land(str(crlf), "--tree", str(tree.root))
        self.assertEqual(run.returncode, 0, run.stderr)
        rel = PASTE.relative_to(FIXTURES_DIR)
        self.assertEqual((tree.root / "fixtures" / rel).read_bytes(), PASTE.read_bytes())
        self.assertIn("CRLF 29240 `41e8fe66", run.stdout)
        self.assertEqual(land(str(crlf), "--check", "--tree", str(tree.root)).returncode, 0)

    def test_landing_twice_is_a_no_op(self):
        tree = TempTree(self)
        self.assertEqual(land(str(PASTE), "--tree", str(tree.root)).returncode, 0)
        again = land(str(PASTE), "--tree", str(tree.root))
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("0 written", again.stdout)


class WhatItRefuses(unittest.TestCase):

    def refused(self, data: bytes, *needles: str, check: bool = False) -> None:
        tree = TempTree(self)
        path = tree.paste(data)
        run = land(str(path), *(["--check"] if check else []), "--tree", str(tree.root))
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        self.assertIn("NOT OK", run.stderr)
        for needle in needles:
            self.assertIn(needle, run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        if not check:
            self.assertFalse((tree.root / "fixtures" / "anthropic").exists())

    def test_a_truncated_paste(self):
        self.refused(edited("--- integrity: 198 lines ---", "--- integrity: 199 lines ---"),
                     "the trailer counts 199")

    def test_a_tampered_copy(self):
        text = PASTE.read_text(encoding="utf-8")
        def body_of(line: str) -> bytes:
            return gzip.decompress(base64.b64decode(line.split(": ", 1)[1]))
        # the `text` recording's response: the one whose body says "twine"
        line = next(l for l in text.splitlines() if l.startswith("response-b64gz: ")
                    and b'"text":"twine"' in body_of(l))
        forged_body = body_of(line).replace(b'"text":"twine"', b'"text":"twain"')
        forged = base64.b64encode(gzip.compress(forged_body)).decode()
        self.refused(edited(line, "response-b64gz: " + forged), "decodes to sha256")

    def test_a_printed_count_that_disagrees(self):
        self.refused(edited("bytes 527\n", "bytes 528\n"), "recording text", "528")

    def test_a_name_used_twice(self):
        self.refused(edited("== rec max_tokens:", "== rec text:"), "appears twice")

    def test_a_name_that_is_not_a_file_name(self):
        self.refused(edited("== rec max_tokens:", "== rec ../max_tokens:"), "lowercase")

    def test_a_content_type_it_cannot_file(self):
        self.refused(edited("header content-type: application/json\nheader request-id: "
                            "req_011CfyJtCJPNHQqgvXD7ck7M",
                            "header content-type: text/html\nheader request-id: "
                            "req_011CfyJtCJPNHQqgvXD7ck7M"), "text/html")

    def test_a_line_it_does_not_know(self):
        self.refused(edited("response-summary: {}", "response-sumary: {}"),
                     "a line the lander does not know")

    def test_two_probe_blocks(self):
        self.refused(PASTE.read_bytes() * 2, "2 PROBE BEGIN lines")

    def test_a_file_with_other_bytes_is_never_replaced(self):
        tree = TempTree(self)
        target = tree.root / "fixtures" / "anthropic" / "text.response.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"{}")
        run = land(str(PASTE), "--tree", str(tree.root))
        self.assertEqual(run.returncode, 1)
        self.assertIn("text.response.json exists with other bytes", run.stderr)
        self.assertEqual(target.read_bytes(), b"{}")
        self.assertEqual(len(list(target.parent.iterdir())), 1)

    def test_check_names_a_differing_file_and_a_missing_row(self):
        tree = TempTree(self)
        self.assertEqual(land(str(PASTE), "--tree", str(tree.root)).returncode, 0)
        target = tree.root / "fixtures" / "anthropic" / "tool_use_stream.response.sse"
        target.write_bytes(target.read_bytes() + b"\n")
        run = land(str(PASTE), "--check", "--tree", str(tree.root))
        self.assertEqual(run.returncode, 1)
        self.assertIn("tool_use_stream.response.sse differs", run.stderr)
        target.write_bytes((FIXTURES_DIR / "anthropic" / target.name).read_bytes())
        readme = tree.root / "fixtures" / "README.md"
        text = readme.read_text(encoding="utf-8")
        row = next(l for l in text.splitlines() if l.startswith("| `anthropic/models.meta.json`"))
        readme.write_text(text.replace(row + "\n", ""), encoding="utf-8")
        run = land(str(PASTE), "--check", "--tree", str(tree.root))
        self.assertEqual(run.returncode, 1)
        self.assertIn("no row for anthropic/models.meta.json", run.stderr)

    def test_an_unreadable_paste_is_exit_2(self):
        run = land("/nonexistent/paste.txt")
        self.assertEqual(run.returncode, 2)
        self.assertNotIn("Traceback", run.stderr)


if __name__ == "__main__":
    unittest.main()

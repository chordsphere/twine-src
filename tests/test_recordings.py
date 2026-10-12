"""The recorder and the lander (session 2026-10-12-twine-pin-051-001;
contract §16): bin/twine-record-fixtures, the probe whose paste-back a pin
bump lands, and bin/twine-land-recordings, which lands it — and the naming
rule they share with tests/helpers.py (tests/fixture_rule.py).

No test here runs a bale. The lander is run as a subprocess against the
landed paste-back (fixtures/bale-0.4.51/carried/probe-output_twine-051-record.txt)
and against copies of it and of fixtures/ edited to be wrong, in temporary
directories. The recorder is checked as a script (bash -n, its header read
by `twine take`, its recordings matched to the paste's) and run once end to
end against a stub `bale` this file writes into a temp root — a double,
named as one, first on a PATH the test builds — to prove the slug argument
and its default.

Sections:
  1. Helpers
  2. The shared rule
  3. The lander, against the landed tree
  4. The lander, refusing
  5. The lander, landing
  6. The recorder
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from twine import FIXTURES_DIR, REPO_ROOT, shapes

from tests.fixture_rule import (CollisionError, Role, assign_groups, echoed_argv,
                                fixture_relpath_at, parse_rows, stderr_relpath)
from tests.helpers import PIN, fenced_probe, recorded_rows, run_cli

# ---------------------------------------------------------------------------
# 1. Helpers
# ---------------------------------------------------------------------------

LANDER = REPO_ROOT / "bin" / "twine-land-recordings"
RECORDER = REPO_ROOT / "bin" / "twine-record-fixtures"
PASTE_REL = f"fixtures/bale-{PIN}/carried/probe-output_twine-051-record.txt"
PASTE = REPO_ROOT / PASTE_REL
RECORDINGS = 24
HEADER = re.compile(r"^== recording: (\S+) \((.*)\)$", re.M)


def lander(*argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """bin/twine-land-recordings under `python3 -I -S -B`, as the checkpoint
    and validation.sh run it, from the tree root unless `cwd` is given."""
    return subprocess.run([sys.executable, "-I", "-S", "-B", str(LANDER), *argv],
                          cwd=str(cwd or REPO_ROOT), capture_output=True, text=True,
                          env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8"})


class TreeCopy:
    """A temp tree holding a copy of fixtures/ — what `--tree` points the
    lander at when a test edits something to be wrong."""

    def __init__(self) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="twine-lander-")
        self.root = Path(self._dir.name)
        shutil.copytree(FIXTURES_DIR, self.root / "fixtures")

    def path(self, rel: str) -> Path:
        return self.root / rel

    def cleanup(self) -> None:
        self._dir.cleanup()


def paste_text() -> str:
    return PASTE.read_bytes().decode("utf-8")


# ---------------------------------------------------------------------------
# 2. The shared rule
# ---------------------------------------------------------------------------


class TheSharedRule(unittest.TestCase):

    def test_echoed_argv_rejoins_only_packs_goal(self):
        """The recorder echoes `argv: $*`, so quoting is gone; the one
        positional that carries spaces is pack's goal, everything before
        its first flag. Any other verb splits on single spaces."""
        self.assertEqual(echoed_argv("bale pack twine-051-record: the read-only session "
                                     "--slug ro --read-only --no-readme --json"),
                         ["pack", "twine-051-record: the read-only session", "--slug", "ro",
                          "--read-only", "--no-readme", "--json"])
        self.assertEqual(echoed_argv("bale relay 2026-10-08-sc-002 - --json"),
                         ["relay", "2026-10-08-sc-002", "-", "--json"])
        self.assertEqual(echoed_argv("bale --version"), ["--version"])
        self.assertEqual(echoed_argv("bale pack --json"), ["pack", "--json"])
        with self.assertRaises(ValueError):
            echoed_argv("craft_response.py --probe x")

    def test_the_stdin_role_names_twines_relay_argv_and_stays_put(self):
        """`relay <sid> - --json` names relay_sid_stdin_--json, and a key
        already holding its roles normalizes to itself (the 0.4.49 rule
        respelled a Role as a positional, which read `stdin` as a file)."""
        argv = ["relay", "2026-10-08-sc-002", "-", "--json"]
        self.assertEqual(fixture_relpath_at("9.9.9", argv, "scratch", "relayed"),
                         "fixtures/bale-9.9.9/scratch/relay_sid_stdin_--json+relayed.json")
        from tests.fixture_rule import fixture_key
        key = fixture_key(argv)
        self.assertEqual(key, ["relay", Role("sid"), Role("stdin"), "--json"])
        self.assertEqual(fixture_key(key), key)

    def test_the_collision_rule_groups_by_outcome_then_reason(self):
        """Recorded once: no group. Several outcomes: `+<outcome>`. A shared
        outcome: `+<outcome>+<reason>`, the line's reason — and where the
        lines carry none, a refusal: a tag is the README's, never invented."""
        self.assertEqual(assign_groups([("a.json", "x", None)]), [None])
        self.assertEqual(assign_groups([("a.json", "opened", None),
                                        ("a.json", "open-refused", "not-found"),
                                        ("b.json", "no-op", None)]),
                         ["opened", "open-refused", None])
        self.assertEqual(assign_groups([("r.json", "relayed", None),
                                        ("r.json", "relay-refused", "not-open"),
                                        ("r.json", "relay-refused", "not-an-object")]),
                         ["relayed", "relay-refused+not-open", "relay-refused+not-an-object"])
        for bad in ([("r.json", "relay-refused", None), ("r.json", "relay-refused", "x")],
                    [("r.json", "relay-refused", "x"), ("r.json", "relay-refused", "x")],
                    [("r.json", None, None), ("r.json", "y", None)]):
            with self.subTest(case=bad), self.assertRaises(CollisionError):
                assign_groups(bad)

    def test_the_stderr_sibling_replaces_the_extension(self):
        self.assertEqual(stderr_relpath("fixtures/bale-9/scratch/unlock_--json.json"),
                         "fixtures/bale-9/scratch/unlock_--json.stderr")
        self.assertEqual(stderr_relpath("fixtures/bale-9/anywhere/--version.txt"),
                         "fixtures/bale-9/anywhere/--version.stderr")
        with self.assertRaises(ValueError):
            stderr_relpath("fixtures/bale-9/no-extension")


# ---------------------------------------------------------------------------
# 3. The lander, against the landed tree
# ---------------------------------------------------------------------------


class LanderChecksTheLandedTree(unittest.TestCase):

    def test_check_on_the_landed_paste_is_ok(self):
        """The checkpoint's own call: `--check` on the landed paste, from the
        tree root, exits 0 and writes nothing to stdout."""
        before = sorted(p.relative_to(FIXTURES_DIR).as_posix() for p in FIXTURES_DIR.rglob("*"))
        run = lander("--check", PASTE_REL)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "")
        self.assertIn(f"holds the {RECORDINGS} recordings of probe twine-051-record", run.stderr)
        after = sorted(p.relative_to(FIXTURES_DIR).as_posix() for p in FIXTURES_DIR.rglob("*"))
        self.assertEqual(before, after)

    def test_check_on_the_paste_as_it_arrived_is_ok_too(self):
        """The paste as received (every LF a CRLF again, 135428 bytes) is the
        same paste to the lander: CRLF is folded first, nothing else."""
        with tempfile.TemporaryDirectory() as tmp:
            crlf = Path(tmp) / "twine-051-record.txt"
            crlf.write_bytes(PASTE.read_bytes().replace(b"\n", b"\r\n"))
            self.assertEqual(hashlib.sha256(crlf.read_bytes()).hexdigest(),
                             "b1bb27d1d54b40dc75a086c36c719742e6170b647c93de94d5a86b2662063e01")
            run = lander(str(crlf), "--check")
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_the_version_defaults_to_the_paste_and_may_be_named(self):
        """V defaults to the paste's `install bin/VERSION:` line; naming
        another version checks that version's directory, which does not
        hold these files."""
        self.assertIn("install bin/VERSION: 0.4.51\n", paste_text())
        ok = lander(PASTE_REL, "--check", "--version", PIN)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        other = lander(PASTE_REL, "--check", "--version", "0.4.49")
        self.assertEqual(other.returncode, 1)
        self.assertIn("fixtures/bale-0.4.49/anywhere/--version.txt differs from the paste's "
                      "bytes", other.stderr)

    def test_the_rows_it_derives_are_the_readmes(self):
        """Every row the paste derives is in fixtures/README.md as the
        lander would print it (recorded_rows is the same parser), and they
        are the pinned section's rows, all of them."""
        pinned = {k: r for k, r in recorded_rows().items()
                  if k.startswith(f"fixtures/bale-{PIN}/")}
        self.assertEqual(len(pinned), RECORDINGS)
        self.assertEqual(len(HEADER.findall(paste_text())), RECORDINGS)


# ---------------------------------------------------------------------------
# 4. The lander, refusing
# ---------------------------------------------------------------------------


class LanderRefuses(unittest.TestCase):

    def setUp(self):
        self.tree = TreeCopy()
        self.addCleanup(self.tree.cleanup)

    def check(self, paste: Path | None = None) -> subprocess.CompletedProcess:
        return lander(str(paste or self.tree.path(PASTE_REL)), "--check",
                      "--tree", str(self.tree.root))

    def test_the_unedited_copy_is_ok(self):
        self.assertEqual(self.check().returncode, 0)

    def test_an_altered_recording_is_named(self):
        for rel in (f"fixtures/bale-{PIN}/scratch/relay_sid_stdin_--json+relayed.json",
                    f"fixtures/bale-{PIN}/twine-src/unlock_sid_--json+unlock-refused+not-open.stderr"):
            with self.subTest(file=rel):
                path = self.tree.path(rel)
                original = path.read_bytes()
                path.write_bytes(original + b" ")
                run = self.check()
                path.write_bytes(original)
                self.assertEqual(run.returncode, 1)
                self.assertIn(f"NOT OK — {rel} differs from the paste's bytes", run.stderr)

    def test_a_missing_file_an_extra_file_and_a_wrong_row_are_named(self):
        missing = f"fixtures/bale-{PIN}/anywhere/--version.stderr"
        self.tree.path(missing).unlink()
        run = self.check()
        self.assertEqual(run.returncode, 1)
        self.assertIn(f"{missing} is not in the tree", run.stderr)
        self.tree.path(missing).write_bytes(b"")
        extra = f"fixtures/bale-{PIN}/scratch/not-from-the-paste.json"
        self.tree.path(extra).write_bytes(b"{}\n")
        run = self.check()
        self.assertEqual(run.returncode, 1)
        self.assertIn(f"{extra} is under fixtures/bale-{PIN}/ but the paste does not derive it",
                      run.stderr)
        self.tree.path(extra).unlink()
        readme = self.tree.path("fixtures/README.md")
        text = readme.read_text(encoding="utf-8")
        row = next(line for line in text.splitlines()
                   if line.startswith(f"| `bale-{PIN}/scratch/unlock_--json.json`"))
        readme.write_text(text.replace(row, row.replace("| 39 |", "| 40 |")), encoding="utf-8")
        run = self.check()
        self.assertEqual(run.returncode, 1)
        self.assertIn(f"fixtures/README.md's row for bale-{PIN}/scratch/unlock_--json.json "
                      "differs", run.stderr)

    def test_a_bad_trailer_is_refused(self):
        """A truncated paste: one inner line gone, the trailer's count no
        longer the block's — refused before anything is decoded."""
        text = paste_text()
        cut = text.replace("recordings: 24\n", "", 1)
        paste = self.tree.root / "truncated.txt"
        paste.write_text(cut, encoding="utf-8")
        run = self.check(paste)
        self.assertEqual(run.returncode, 1)
        self.assertIn("the trailer counts 1444 lines; the block carries 1443", run.stderr)

    def test_a_stream_that_is_not_its_printed_hash_is_refused_naming_the_recording(self):
        text = paste_text()
        printed = "stderr sha256: 2e8ec66238b6879a63d7667cad8a197d8853d75d7aacab55b5cab26066cc475e"
        self.assertEqual(text.count(printed), 1)
        paste = self.tree.root / "edited.txt"
        paste.write_text(text.replace(printed, "stderr sha256: " + "0" * 64), encoding="utf-8")
        run = self.check(paste)
        self.assertEqual(run.returncode, 1)
        self.assertIn("recording 5 (unlock_sid_--json, unlock-refused: not-open; repo): "
                      "stderr decodes to sha256 2e8ec662", run.stderr)

    def test_a_paste_without_a_probe_block_is_refused_and_an_unreadable_one_is_a_usage_error(self):
        paste = self.tree.root / "prose.txt"
        paste.write_text("no block here\n", encoding="utf-8")
        run = self.check(paste)
        self.assertEqual(run.returncode, 1)
        self.assertIn("0 PROBE BEGIN lines", run.stderr)
        run = self.check(self.tree.root / "no-such-paste.txt")
        self.assertEqual(run.returncode, 2)
        self.assertIn("cannot read", run.stderr)


# ---------------------------------------------------------------------------
# 5. The lander, landing
# ---------------------------------------------------------------------------


class LanderLands(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="twine-land-")
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name)

    def test_landing_into_an_empty_tree_writes_the_trees_bytes_and_prints_its_rows(self):
        """Into a tree with no fixtures/: every recording, every sibling and
        the paste land byte for byte as the repository holds them, and the
        printed rows are the README's (the manifest lines name the
        manifest's paths). Nothing else is written."""
        run = lander(PASTE_REL, "--tree", str(self.root))
        self.assertEqual(run.returncode, 0, run.stderr)
        landed = sorted(p.relative_to(self.root).as_posix()
                        for p in self.root.rglob("*") if p.is_file())
        ours = sorted(p.relative_to(REPO_ROOT).as_posix()
                      for p in (FIXTURES_DIR / f"bale-{PIN}").rglob("*") if p.is_file())
        self.assertEqual(landed, ours)
        self.assertEqual(len(landed), 2 * RECORDINGS + 1)
        for rel in landed:
            with self.subTest(file=rel):
                self.assertEqual((self.root / rel).read_bytes(), (REPO_ROOT / rel).read_bytes())
        printed = parse_rows(run.stdout)
        readme = recorded_rows()
        self.assertEqual(len(printed), RECORDINGS)
        for key, row in printed.items():
            self.assertEqual(row, readme[key], key)
        manifest = (REPO_ROOT / "share" / "bale-consumption.toml").read_text(encoding="utf-8")
        for path in re.findall(r'fixture = "([^"]+)"', run.stdout):
            self.assertIn(f'"{path}"', manifest, path)
        self.assertIn('{argv = ["relay", "<sid>", "-", "--json"], cwd = "scratch", '
                      'outcome = "relayed", fixture = ', run.stdout)

    def test_landing_again_is_idempotent_and_never_replaces_other_bytes(self):
        self.assertEqual(lander(PASTE_REL, "--tree", str(self.root)).returncode, 0)
        self.assertEqual(lander(PASTE_REL, "--tree", str(self.root)).returncode, 0)
        target = self.root / f"fixtures/bale-{PIN}/scratch/unlock_--json.json"
        target.write_bytes(b"{}\n")
        run = lander(PASTE_REL, "--tree", str(self.root))
        self.assertEqual(run.returncode, 1)
        self.assertIn("unlock_--json.json exists with other bytes", run.stderr)
        self.assertEqual(target.read_bytes(), b"{}\n", "nothing was replaced")

    def test_the_lander_is_stdlib_and_imports_the_rule_not_a_copy(self):
        """The lander imports tests/fixture_rule.py — the module
        tests/helpers.py re-exports — and defines no naming function of its
        own; it imports nothing outside the standard library and that
        module, and nothing of bale's."""
        import ast
        tree = ast.parse(LANDER.read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        self.assertLessEqual(roots, set(sys.stdlib_module_names) | {"tests"})
        self.assertIn("from tests import fixture_rule as rule", LANDER.read_text(encoding="utf-8"))
        defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        self.assertFalse(defined & {"fixture_key", "fixture_stem", "fixture_relpath",
                                    "split_group", "assign_groups", "emission_relpath"})
        mode = LANDER.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR)
        self.assertEqual(LANDER.read_text(encoding="utf-8").split("\n", 1)[0],
                         "#!/usr/bin/env python3")


# ---------------------------------------------------------------------------
# 6. The recorder
# ---------------------------------------------------------------------------


class TheRecorder(unittest.TestCase):

    def test_it_is_executable_bash_and_parses(self):
        self.assertTrue(RECORDER.stat().st_mode & stat.S_IXUSR)
        self.assertEqual(RECORDER.read_text(encoding="utf-8").split("\n", 1)[0],
                         "#!/usr/bin/env bash")
        bash = shutil.which("bash") or "/bin/bash"
        run = subprocess.run([bash, "-n", str(RECORDER)], capture_output=True, text=True)
        self.assertEqual((run.returncode, run.stderr), (0, ""))

    def test_its_header_reads_as_a_probe_with_take(self):
        """It is a probe: fenced as a worker's turn carries one, `take`
        reads one intact probe block whose slug is the recorder's own."""
        with tempfile.TemporaryDirectory() as tmp:
            turn = Path(tmp) / "turn.txt"
            turn.write_text(fenced_probe(RECORDER.read_text(encoding="utf-8")), encoding="utf-8")
            run = run_cli("take", str(turn), "--json")
        obj = json.loads(run.stdout)
        self.assertEqual([(b["kind"], b["slug"], b["integrity"]["ok"]) for b in obj["blocks"]],
                         [(shapes.PROBE, "twine-record-fixtures", True)])

    def test_its_recordings_are_the_pastes_in_order(self):
        """The recorder is the probe that made the landed paste-back: its 24
        `rec` calls name the paste's 24 `== recording:` headers, label and
        annotation, in order — the slug is the one thing made an argument.
        The paste's text crossed clip.exe, which read its UTF-8 as code page
        437 (an em dash arrives as `ΓÇö`; fixtures/README.md, "bale 0.4.51"),
        so the script's annotations are compared as they arrived."""
        script = RECORDER.read_text(encoding="utf-8")
        calls = re.findall(r'^\s*rec "([^"]+)" "([^"]+)"', script, re.M)
        as_arrived = [(label, ann.encode("utf-8").decode("cp437")) for label, ann in calls]
        self.assertEqual(as_arrived, HEADER.findall(paste_text()))
        self.assertEqual(len(calls), RECORDINGS)
        self.assertNotIn("twine-051-record ===", script, "the sentinels name $SLUG")
        self.assertIn('echo "=== PROBE BEGIN $SLUG ==="', script)

    def test_the_slug_is_an_argument_defaulting_to_the_installed_version(self):
        """Run end to end against a stub bale (a double this test writes;
        bin/VERSION 9.9.9, no crafter — the steps that need one fail and
        say so, as the probe lets them): the paste-back is one intact
        probe-output block named twine-record-9.9.9 by default, or by the
        slug given; a slug that is not one is refused, exit 2."""
        bash = shutil.which("bash") or "/bin/bash"
        with tempfile.TemporaryDirectory(prefix="twine-recorder-") as tmp:
            base = Path(tmp)
            (base / "install" / "bin").mkdir(parents=True)
            (base / "install" / "schemas").mkdir()
            stub = base / "install" / "bin" / "bale"
            stub.write_text("#!/bin/sh\n# A test double written by tests/test_recordings.py "
                            "- not bale.\ncat >/dev/null 2>&1 </dev/null\nexit 0\n",
                            encoding="utf-8")
            stub.chmod(0o755)
            (base / "install" / "bin" / "VERSION").write_text("9.9.9\n", encoding="utf-8")
            (base / "install" / "bin" / "bale_report.py").write_text("", encoding="utf-8")
            (base / "path").mkdir()
            (base / "path" / "bale").symlink_to(stub)
            (base / "repo").mkdir()
            (base / "tmp").mkdir()
            env = {"PATH": f"{base / 'path'}:/usr/bin:/bin", "HOME": str(base),
                   "TMPDIR": str(base / "tmp"), "LC_ALL": "C.UTF-8"}

            def record(*argv: str) -> subprocess.CompletedProcess:
                return subprocess.run([bash, str(RECORDER), *argv], cwd=str(base / "repo"),
                                      env=env, capture_output=True, text=True, timeout=120)

            for argv, slug in (((), "twine-record-9.9.9"), (("my-slug-1",), "my-slug-1")):
                with self.subTest(slug=slug):
                    run = record(*argv)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    lines = run.stdout.splitlines()
                    self.assertEqual((lines[0], lines[-1]), (f"=== PROBE BEGIN {slug} ===",
                                                             f"=== PROBE END {slug} ==="))
                    blocks = shapes.find_blocks(run.stdout).blocks
                    self.assertEqual([(b.kind, b.ok) for b in blocks],
                                     [(shapes.PROBE_OUTPUT, True)])
                    self.assertIn("install bin/VERSION: 9.9.9", run.stdout)
            bad = record("Not A Slug")
            self.assertEqual(bad.returncode, 2)
            self.assertIn("must be lowercase", bad.stderr)
            self.assertEqual(list((base / "tmp").iterdir()), [], "the scratch is removed")


if __name__ == "__main__":
    unittest.main()

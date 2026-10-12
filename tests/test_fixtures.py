"""fixtures/: every recorded output of the pinned version parses, is one
line, is named by the rule, has its stderr sibling and is listed in
fixtures/README.md with both streams' hashes; every carried paste —
the ones a format entry points at, and a version's recordings' source
(under the version that printed each) — differs from what arrived only by
CRLF."""

from __future__ import annotations

import hashlib
import json
import unittest
from collections import defaultdict

from twine import FIXTURES_DIR
from twine.bale import load_manifest

from tests.fixture_rule import (CARRIED_ROW, RECORDING_ROW, STDERR_EXT, Row, echoed_argv,
                                format_row, parse_rows, stderr_relpath)
from tests.helpers import (GROUP_SEP, PIN, UNLOCK_RECORDED_SID, UNRECORDED, fixture_key,
                           fixture_stem, recorded_exits, recorded_rows, split_group)

README = FIXTURES_DIR / "README.md"
# The command each table's rows name, by fixture directory.
COMMAND_PREFIX = {"twine-src": "bale ", "anywhere": "bale ", "scratch": "bale ",
                  "crafter": "craft_response.py "}
PINNED = f"bale-{PIN}"
# The 0.4.51 dry run (fixtures/README.md, "bale 0.4.51"): recorded in the
# scratch repository for its scoped session, with its exit and its stderr.
DRY_RUN = f"{PINNED}/scratch/apply_--dry-run_--json_tarball+dry-run.json"
DRY_RUN_BYTES, DRY_RUN_SHA = 290, "7e7fd743b142148a90b145032709297c8ade1493595a5ba5a2ad8e5933d3cea8"
# The recorder's paste-back, the 0.4.51 recordings' source (fixtures/README.md,
# "bale 0.4.51", the carried table).
SOURCE_PASTE = f"{PINNED}/carried/probe-output_twine-051-record.txt"


def recorded_files() -> list:
    """Every recording file of the pinned version — stdout files and their
    `.stderr` siblings — that is, everything under bale-<pin>/ but the
    carried paste-back the recordings were landed from."""
    return sorted(p for p in (FIXTURES_DIR / PINNED).rglob("*")
                  if p.is_file() and p.parent.name != "carried")


def stdout_files() -> list:
    return [p for p in recorded_files() if p.suffix != STDERR_EXT]


def rel(p) -> str:
    return p.relative_to(FIXTURES_DIR).as_posix()


def carried_files() -> list:
    """The carried pastes the manifest's format entries point at, under the
    version each names (fixtures_version) — not the pinned directory,
    which a format's paste never moves into."""
    found = []
    for s in load_manifest().surfaces:
        if s["kind"] == "format":
            for path in s["fixtures"]:
                path = FIXTURES_DIR.parent / path
                if path.parent.name == "carried":
                    found.append((s["fixtures_version"], path))
    return found


class FixturesParse(unittest.TestCase):

    def test_at_least_the_brief_s_three(self):
        names = {rel(p) for p in recorded_files()}
        self.assertLessEqual({f"{PINNED}/twine-src/status_--json.json",
                              f"{PINNED}/twine-src/stats_--json.json",
                              f"{PINNED}/anywhere/--version.txt"}, names)

    def test_every_json_fixture_is_one_object_line(self):
        for p in stdout_files():
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
        """The 0.4.51 dry run, recorded by probe twine-051-record in the
        throwaway repository for its scoped session (session
        2026-10-12-twine-pin-051-001): byte-exact under its grouped name,
        exit 0 in its row, its stderr beside it — 0.4.49's and the 0.4.45
        carried line (exit unrecorded) are history."""
        p = FIXTURES_DIR / DRY_RUN
        data = p.read_bytes()
        self.assertEqual((len(data), hashlib.sha256(data).hexdigest()),
                         (DRY_RUN_BYTES, DRY_RUN_SHA))
        obj = json.loads(data)
        self.assertEqual((obj["outcome"], obj["sid"]), ("dry-run", UNLOCK_RECORDED_SID))
        row = recorded_rows()[f"fixtures/{DRY_RUN}"]
        self.assertEqual(row.exit, 0)
        self.assertEqual(row.stderr_bytes,
                         len((FIXTURES_DIR / stderr_relpath(DRY_RUN)).read_bytes()))

    def test_version_fixture_is_bale_pin(self):
        text = (FIXTURES_DIR / f"{PINNED}/anywhere/--version.txt").read_text(encoding="utf-8")
        self.assertEqual(text, f"bale {PIN}\n")

    def test_the_pinned_directory_holds_the_twenty_four(self):
        """The pin bump landed twenty-four recordings — twenty-one bale argvs
        and the three crafter emissions (fixtures/README.md, bale 0.4.51) —
        each with its stderr sibling, and the paste-back they came from."""
        by_where = defaultdict(int)
        for p in stdout_files():
            by_where[p.parent.name] += 1
        self.assertEqual(dict(by_where), {"anywhere": 1, "twine-src": 6, "scratch": 14,
                                          "crafter": 3})
        self.assertEqual(sum(by_where.values()), 24)
        siblings = [p for p in recorded_files() if p.suffix == STDERR_EXT]
        self.assertEqual(len(siblings), 24)
        carried = sorted(rel(p) for p in (FIXTURES_DIR / PINNED / "carried").iterdir())
        self.assertEqual(carried, [SOURCE_PASTE])

    def test_every_recording_has_its_stderr_sibling_and_nothing_else_does(self):
        """Each stdout file has exactly one `.stderr` sibling — the same
        name, the extension replaced — present even when bale printed
        nothing (zero bytes), and no sibling stands without its stdout."""
        stdouts = {rel(p) for p in stdout_files()}
        siblings = {rel(p) for p in recorded_files() if p.suffix == STDERR_EXT}
        self.assertEqual({stderr_relpath(r) for r in stdouts}, siblings)
        empty = sorted(r for r in siblings if not (FIXTURES_DIR / r).read_bytes())
        self.assertEqual(empty, [f"{PINNED}/anywhere/--version.stderr",
                                 f"{PINNED}/twine-src/stats_--json.stderr",
                                 f"{PINNED}/twine-src/stats_--sid-2026-10-01-twine-seed-001_--json.stderr",
                                 f"{PINNED}/twine-src/status_--json.stderr"])


class NamedByTheRule(unittest.TestCase):
    """Every recorded bale argv's file is its normalized name, and an argv
    recorded with more than one outcome in the version carries its
    outcome group — `+<outcome>` and, where that still collides, `+<reason>`
    (fixtures/README.md, "Outcome groups") — never the plain name."""

    def setUp(self):
        self.text = README.read_text(encoding="utf-8")
        self.rows = recorded_rows()

    def argv_files(self) -> list:
        return [p for p in stdout_files() if p.parent.name in ("twine-src", "anywhere", "scratch")]

    def test_each_name_is_its_commands_normalized_name(self):
        """The README row's command, read back as the recorder echoed it
        (fixture_rule.echoed_argv: pack's goal is everything before its
        first flag) and normalized by fixture_key, spells the file's stem —
        so the per-run roles (sid, stdin, tarball, bundle, goal) are exactly
        where the rule puts them."""
        for p in self.argv_files():
            with self.subTest(fixture=rel(p)):
                cmd = self.rows[f"fixtures/{rel(p)}"].command
                self.assertTrue(cmd.startswith("bale "))
                argv = echoed_argv(cmd)
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
        """The grouped names, as fixtures/README.md's 0.4.51 section lists
        them — a reader's check that the rule produced what it says: the
        open refusal is a third outcome (no reason needed), and both relay
        refusals carry their line's `reason` (no tag is the section's)."""
        grouped = sorted(p.relative_to(FIXTURES_DIR / PINNED).as_posix()
                         for p in self.argv_files() if GROUP_SEP in p.name)
        self.assertEqual(grouped, [
            "scratch/apply_--dry-run_--json_tarball+dry-run.json",
            "scratch/apply_--dry-run_--json_tarball+scope-drift-refused.json",
            "scratch/open_bundle_--json+open-refused.json",
            "scratch/open_bundle_--json+opened.json",
            "scratch/open_bundle_--json+second-desk.json",
            "scratch/relay_sid_stdin_--json+relay-refused+not-an-object.json",
            "scratch/relay_sid_stdin_--json+relay-refused+not-open.json",
            "scratch/relay_sid_stdin_--json+relayed.json",
            "scratch/unlock_sid_--json+unlock-refused+hold-branch.json",
            "scratch/unlock_sid_--json+unlocked.json",
            "twine-src/unlock_sid_--json+unlock-refused+not-open.json",
        ])


class ReadmeListsEveryFixture(unittest.TestCase):

    def setUp(self):
        self.text = README.read_text(encoding="utf-8")
        self.rows = recorded_rows()

    def test_rows_match_files_bytes_and_hashes(self):
        """The pinned version's rows and stdout files are the same set, byte
        for byte, and each row's two stderr columns are its sibling's bytes
        and sha256; earlier versions' rows stay as history and are not
        compared against the pinned directory."""
        rows = {k.removeprefix("fixtures/"): r for k, r in self.rows.items()
                if k.startswith(f"fixtures/{PINNED}/")}
        files = {rel(p): p for p in stdout_files()}
        self.assertEqual(set(rows), set(files), "README rows and fixture files differ")
        for name, p in files.items():
            with self.subTest(fixture=name):
                data = p.read_bytes()
                self.assertEqual((rows[name].bytes, rows[name].sha256),
                                 (len(data), hashlib.sha256(data).hexdigest()))
                self.assertTrue(rows[name].has_stderr, "a pinned row carries stderr")
                err = (FIXTURES_DIR / stderr_relpath(name)).read_bytes()
                self.assertEqual((rows[name].stderr_bytes, rows[name].stderr_sha256),
                                 (len(err), hashlib.sha256(err).hexdigest()))

    def test_earlier_versions_rows_still_match_their_files(self):
        """History stays readable: every row of every section names a file
        that exists with those bytes — and, on an eight-column row, a
        sibling with those stderr bytes (bale-0.4.45/ and bale-0.4.49/ are
        untouched; their six-column rows parse as rows without stderr)."""
        self.assertTrue(any(f.startswith("fixtures/bale-0.4.45/") for f in self.rows))
        self.assertTrue(any(f.startswith("fixtures/bale-0.4.49/") for f in self.rows))
        for path, row in self.rows.items():
            name = path.removeprefix("fixtures/")
            with self.subTest(fixture=name):
                data = (FIXTURES_DIR / name).read_bytes()
                self.assertEqual((row.bytes, row.sha256),
                                 (len(data), hashlib.sha256(data).hexdigest()))
                self.assertEqual(row.has_stderr, name.startswith(f"{PINNED}/"),
                                 "stderr columns exactly on the pinned (0.4.51) rows")
                if row.has_stderr:
                    err = (FIXTURES_DIR / stderr_relpath(name)).read_bytes()
                    self.assertEqual((row.stderr_bytes, row.stderr_sha256),
                                     (len(err), hashlib.sha256(err).hexdigest()))
        for m in CARRIED_ROW.finditer(self.text):
            with self.subTest(carried=m["file"]):
                data = (FIXTURES_DIR / m["file"]).read_bytes()
                self.assertEqual((int(m["bytes"]), m["sha"]),
                                 (len(data), hashlib.sha256(data).hexdigest()))

    def test_the_row_parser_reads_both_shapes(self):
        """fixture_rule.parse_rows (which the lander shares) reads the
        eight-column row of 0.4.51 on and the six-column history rows alike;
        recorded_exits is a view over recorded_rows, so the player's callers
        did not move; format_row writes back what it read."""
        six = ("| `bale-9.9.9/anywhere/--version.txt` | `bale --version` | `/tmp` | 0 | 12 "
               "| `" + "a" * 64 + "` |")
        eight = ("| `bale-9.9.9/scratch/unlock_--json.json` | `bale unlock --json` | `/x` "
                 "| unrecorded | 231 | `" + "b" * 64 + "` | 39 | `" + "c" * 64 + "` |")
        rows = parse_rows(six + "\n" + eight + "\n")
        self.assertEqual(rows["fixtures/bale-9.9.9/anywhere/--version.txt"],
                         Row("bale-9.9.9/anywhere/--version.txt", "bale --version", "/tmp", 0,
                             12, "a" * 64, None, None))
        both = rows["fixtures/bale-9.9.9/scratch/unlock_--json.json"]
        self.assertEqual((both.exit, both.stderr_bytes, both.stderr_sha256, both.has_stderr),
                         (UNRECORDED, 39, "c" * 64, True))
        self.assertEqual([format_row(r) for r in rows.values()], [six, eight])
        with self.assertRaises(ValueError):
            parse_rows(six + "\n" + six + "\n")
        self.assertEqual(recorded_exits(), {k: r.exit for k, r in recorded_rows().items()})
        self.assertEqual(len(RECORDING_ROW.findall(self.text)), len(self.rows))

    def test_command_rows_name_their_emitter(self):
        """A recorded output's row names the command that printed it: a
        bale argv under twine-src/, scratch/ and anywhere/, the crafter
        under crafter/."""
        for p in stdout_files():
            name = rel(p)
            where = name.split("/")[1]
            self.assertIn(where, COMMAND_PREFIX, name)
            with self.subTest(fixture=name):
                self.assertIn(f"fixtures/{name}", self.rows)
                self.assertTrue(self.rows[f"fixtures/{name}"].command.startswith(
                    COMMAND_PREFIX[where]))

    def test_an_unrecorded_exit_is_said_never_guessed(self):
        """Every row of the pinned section has its exit (the recorder
        printed each one); the `unrecorded` vocabulary stays for a row that
        lacks one — the 0.4.45 carried dry run is such a row, as history —
        and the player refuses to answer such a row without a named
        assumption (tests/test_process.py)."""
        pinned = {f: r.exit for f, r in self.rows.items()
                  if f.startswith(f"fixtures/{PINNED}/")}
        self.assertEqual(len(pinned), 24)
        self.assertNotIn(UNRECORDED, pinned.values())
        # The refusals exited 1 — the line says so by its outcome — and
        # everything else 0.
        for name, exit_code in pinned.items():
            with self.subTest(fixture=name):
                path = FIXTURES_DIR.parent / name
                refused = (path.suffix == ".json"
                           and json.loads(path.read_bytes())["outcome"].endswith("-refused"))
                self.assertEqual(exit_code, 1 if refused else 0)
        history = "fixtures/bale-0.4.45/twine-src/apply_--dry-run_--json_tarball.json"
        self.assertEqual(self.rows[history].exit, UNRECORDED)

    def test_carried_pastes_differ_from_what_arrived_only_by_crlf(self):
        """A carried paste is landed CRLF -> LF and nothing else: the LFs
        turned back into CRLFs are the received bytes, by count and hash.
        Three pastes: the two the manifest's format entries point at (under
        the version each names — they do not move at a pin bump) and the
        0.4.51 recordings' source, the recorder's paste-back, which no
        format entry names."""
        rows = {m["file"]: m for m in CARRIED_ROW.finditer(self.text)}
        on_disk = sorted(rel(p) for p in FIXTURES_DIR.glob("bale-*/carried/*") if p.is_file())
        self.assertEqual(sorted(rows), on_disk, "every carried file has its row, and only those")
        by_format = {rel(p) for _, p in carried_files()}
        self.assertEqual(len(by_format), 2)
        self.assertEqual(set(on_disk) - by_format, {SOURCE_PASTE})
        for version, p in carried_files():
            self.assertTrue(rel(p).startswith(f"bale-{version}/carried/"), rel(p))
        self.assertEqual(len(on_disk), 3)
        for name in on_disk:
            with self.subTest(fixture=name):
                m = rows[name]
                self.assertEqual(m["ending"], "CRLF")
                data = (FIXTURES_DIR / name).read_bytes()
                self.assertNotIn(b"\r", data)
                received = data.replace(b"\n", b"\r\n")
                self.assertEqual(int(m["rbytes"]), len(received))
                self.assertEqual(m["rsha"], hashlib.sha256(received).hexdigest())
                self.assertEqual(int(m["bytes"]), len(data))
                self.assertEqual(m["sha"], hashlib.sha256(data).hexdigest())

    def test_the_source_paste_is_the_one_the_brief_names(self):
        """The paste-back as the session received it (CRLF, 135428 bytes) and
        as landed (LF, 133981 bytes), by the sha256s brief §1 gives."""
        data = (FIXTURES_DIR / SOURCE_PASTE).read_bytes()
        self.assertEqual((len(data), hashlib.sha256(data).hexdigest()),
                         (133981, "dec7a229a8e108c2e2dd43a499e80ce473603201882f7422c1ef98dc7908a238"))
        received = data.replace(b"\n", b"\r\n")
        self.assertEqual((len(received), hashlib.sha256(received).hexdigest()),
                         (135428, "b1bb27d1d54b40dc75a086c36c719742e6170b647c93de94d5a86b2662063e01"))


if __name__ == "__main__":
    unittest.main()

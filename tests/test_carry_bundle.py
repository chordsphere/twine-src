"""`twine carry bundle` (Arc 1 session 3, "offline courier — emit") and the
in-flight record it keeps (twine/inflight.py). No test here reaches a bale
(T8): bale is the fixture player (tests.helpers.FixturePlayer) answering
from the three recorded `bale open … --json` lines, a run-seam double
(OpenDouble, below), or a stub executable (tests.helpers.StubBale).

What is recorded, and what stands in for what is not:

  - `bale open <bundle> --json`, recorded twice at bale 0.4.49 in the
    scratch repository (fixtures/bale-0.4.49/scratch/open_bundle_--json
    +opened.json and +second-desk.json, exit 0 each): the player answers the
    argv only when a test selects the group (SELECT_OPENED,
    SELECT_SECOND_DESK), with this test's directory as the scratch root.
  - `bale open --check <bundle> --json`, recorded once in ~/twine-src
    (fixtures/bale-0.4.49/twine-src/open_--check_bundle_--json.json, exit
    0): the player answers it with --cwd the repository root.
  - an open refusal: unrecorded (bale prints nothing on stdout and exits 1
    through fail(), its reason on stderr — BALE.md §6.7); an OpenDouble,
    named as one. So are a timeout, a capped stdout, a line with an outcome
    no bale emits (NOT_A_BALE_OUTCOME) and a recorded line with its `sid` or
    `opener` taken out — each built in this file from a recording's bytes or
    from nothing, and named a double where it is used.

Sections:
  1. Helpers and doubles
  2. Refused before bale starts
  3. The call: exactly the recorded argvs, once
  4. opened, and the record
  5. second-desk: appending, or a fresh record
  6. --check: a rehearsal writes nothing and needs no state directory
  7. Not ok: what bale said instead, and nothing recorded
  8. A record that cannot be written after the open
  9. The twin's keys on every path; nothing written but the record
 10. The in-flight record module
 11. Guards: one open argv; the record is never removed
 12. End to end, as a subprocess, against a stub bale
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import re
import stat
import tempfile
import threading
import unittest
from pathlib import Path

from twine import REPO_ROOT, bale, inflight
from twine.cli import Context, main
from twine.commands.carry_bale import BALE_STDOUT_CAP_BYTES
from twine.commands.carry_bundle import BUNDLE_TIMEOUT_SECONDS
from twine.process import RunResult

from tests.helpers import (NOT_A_BALE_OUTCOME, OPEN_KEY, OPEN_KEYS, OPEN_RECORDED_SID,
                           PIN, FixturePlayer, RecordingRunner, Run, StubBale, TempRoots,
                           open_recording, run_cli)

# ---------------------------------------------------------------------------
# 1. Helpers and doubles
# ---------------------------------------------------------------------------

SID = OPEN_RECORDED_SID
SELECT_OPENED = {OPEN_KEY: "opened"}
SELECT_SECOND_DESK = {OPEN_KEY: "second-desk"}
RECORD_KEYS = ("sid", "cwd", "tarball", "opens")
ENTRY_KEYS = ("outcome", "desk", "bundle_sha256", "opener_sha256", "recorded_at")
UTC_Z = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
# The twin's fixed names (brief §2.5), and the names beside them: every path
# carries exactly these, beside `command` and `ok`.
FIXED = {"bundle", "check", "ran", "exit_code", "open", "outcome", "sid", "desk",
         "tarball", "tarball_source", "opener", "record", "record_error", "stderr",
         "reason", "refusals"}
BESIDE = {"stdout", "argv", "stderr_truncated", "timed_out", "capped",
          "duration_seconds", "cwd", "state_dir", "state_dir_source", "bale"}
TWIN_KEYS = {"command", "ok"} | FIXED | BESIDE


def sha256_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class OpenDouble(RecordingRunner):
    """A double, not a recording: answers every call with a RunResult this
    file builds, standing in for a bale output nobody recorded — a refusal
    (nothing on stdout, exit 1), a timeout, a capped stdout, a line edited
    from a recording's bytes. Records each call."""

    def __init__(self, exit_code: int | None = 0, stdout: bytes = b"",
                 stderr: bytes = b"", timed_out: bool = False,
                 capped: bool = False) -> None:
        super().__init__(RunResult(argv=("bale",), exit_code=exit_code, stdout=stdout,
                                   stderr=stderr, timed_out=timed_out,
                                   stdout_capped=capped))


def edited_line(name: str, drop: str | None = None, **changes) -> bytes:
    """A double's stdout: the recording `name`'s line with `drop` taken out
    and `changes` applied — bytes no bale printed, named so where used."""
    line = dict(open_recording(name).line)
    if drop is not None:
        del line[drop]
    line.update(changes)
    return (json.dumps(line) + "\n").encode("utf-8")


ROOTS: TempRoots


def setUpModule():
    global ROOTS
    ROOTS = TempRoots()


def tearDownModule():
    ROOTS.cleanup()


def tree(directory: Path) -> set[str]:
    """Every file and directory under `directory`, relative, `/`-joined."""
    if not directory.exists():
        return set()
    return {p.relative_to(directory).as_posix() for p in directory.rglob("*")}


class Case(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="twine-carry-bundle-")
        self.dir = Path(self._dir.name).resolve()
        self.repo = self.dir / "scratch-repo"     # the scratch <where> of the player
        self.repo.mkdir()
        self.state = self.dir / "state"
        self.bundle = self.dir / "2026-10-07-twine-049-scoped.bale-bundle"
        self.bundle.write_bytes(b"a bundle: twine never reads it\n")

    def tearDown(self):
        self._dir.cleanup()

    def player(self, select: dict | None = None) -> FixturePlayer:
        return FixturePlayer(REPO_ROOT, scratch_root=self.repo,
                             select=SELECT_OPENED if select is None else select)

    def run_verb(self, *argv: str, runner, env: dict | None = None,
                 state: bool = True, cwd: Path | None = None) -> Run:
        """`twine carry bundle …` in-process, bale reached only through
        `runner`; --cwd the scratch repository and --state-dir this test's
        unless the test says otherwise; TWINE_BALE_ROOT a root at the pin."""
        # Defaults go first, so a test's `--` (before a dash-led BUNDLE)
        # stays the last option boundary.
        args = list(argv)
        if state and "--state-dir" not in args:
            args = ["--state-dir", str(self.state), *args]
        if "--cwd" not in args:
            args = ["--cwd", str(cwd or self.repo), *args]
        out, err = io.StringIO(), io.StringIO()
        ctx = Context(env=env if env is not None else {"TWINE_BALE_ROOT": ROOTS.ok.as_posix()},
                      stdout=out, stderr=err, which=lambda name: None,
                      stdin=io.BytesIO(b""), run=runner)
        code = main(["carry", "bundle", *args], ctx=ctx)
        return Run(code, out.getvalue(), err.getvalue())

    def twin(self, *argv: str, runner, **kw) -> tuple[Run, dict]:
        run = self.run_verb("--json", *argv, runner=runner, **kw)
        lines = run.stdout.split("\n")
        self.assertEqual((len(lines), lines[1]), (2, ""), f"one JSON line: {run.stdout!r}")
        obj = json.loads(lines[0])
        self.assertEqual(obj["command"], "carry bundle")
        self.assertEqual(set(obj), TWIN_KEYS, set(obj) ^ TWIN_KEYS)
        self.assertEqual(run.code, 0 if obj["ok"] else 1)
        self.assertNotIn("Traceback", run.stderr)
        return run, obj

    def record_file(self, sid: str = SID) -> Path:
        return self.state / "inflight" / f"{sid}.json"

    def read_record(self, sid: str = SID) -> dict:
        return json.loads(self.record_file(sid).read_text(encoding="utf-8"))

    def assert_refused(self, run: Run, obj: dict, runner, *needles: str) -> None:
        self.assertEqual((run.code, obj["ok"], obj["ran"], obj["exit_code"], obj["bundle"],
                          obj["argv"]), (1, False, False, None, None, None))
        self.assertEqual(runner.calls, [], "refused, yet bale was called")
        for needle in needles:
            self.assertIn(needle, obj["reason"])
        self.assertEqual("; ".join(obj["refusals"]), obj["reason"])
        self.assertEqual(tree(self.state), set(), "a refusal wrote state")


# ---------------------------------------------------------------------------
# 2. Refused before bale starts
# ---------------------------------------------------------------------------


class RefusedBeforeBale(Case):

    def test_an_empty_bundle_is_refused(self):
        runner = OpenDouble()
        run, obj = self.twin("", runner=runner)
        self.assert_refused(run, obj, runner, "BUNDLE is empty")

    def test_a_leading_dash_name_that_names_no_file_is_refused_unstarted(self):
        """Reached only after `--`, as argparse requires; twine still refuses
        it, since bale could read it as a flag."""
        runner = OpenDouble()
        for name in ("-x", "--no-sandbox", "--dry-run"):
            with self.subTest(name=name):
                run, obj = self.twin("--cwd", str(self.repo), "--state-dir", str(self.state),
                                     "--", name, runner=runner)
                self.assert_refused(run, obj, runner, f"BUNDLE {name!r}",
                                    "begins with `-`", "read it as a flag")

    def test_a_leading_dash_name_without_dashdash_is_argparses_usage_error(self):
        runner = OpenDouble()
        usage = io.StringIO()
        with contextlib.redirect_stderr(usage):   # argparse writes sys.stderr itself
            run = self.run_verb("-x", runner=runner)
        self.assertEqual((run.code, run.stdout, runner.calls), (2, "", []))
        self.assertIn("required: BUNDLE", usage.getvalue())

    def test_cwd_that_is_not_a_directory_is_refused(self):
        runner = OpenDouble()
        run, obj = self.twin(str(self.bundle), "--cwd", str(self.dir / "nope"), runner=runner)
        self.assert_refused(run, obj, runner, "--cwd", "is not a directory")

    def test_no_bale_found_or_not_the_pin_is_refused(self):
        for env, needle in (({}, "no bale install found"),
                            ({"TWINE_BALE_ROOT": ROOTS.other.as_posix()}, "not the pin"),
                            ({"TWINE_BALE_ROOT": ROOTS.absent.as_posix()},
                             "cannot tell this one's version")):
            with self.subTest(needle=needle):
                runner = OpenDouble()
                run, obj = self.twin(str(self.bundle), runner=runner, env=env)
                self.assert_refused(run, obj, runner, needle)

    def test_no_state_directory_resolving_is_refused_without_check(self):
        """No --state-dir, no $TWINE_STATE_DIR, XDG or HOME: refused before
        the open, since an open that could not be recorded is refused before
        it happens."""
        runner = OpenDouble(stdout=open_recording("opened").stdout)
        run, obj = self.twin(str(self.bundle), runner=runner, state=False)
        self.assert_refused(run, obj, runner, "cannot resolve twine's state directory",
                            "could not be recorded", "--check")
        self.assertEqual((obj["state_dir"], obj["state_dir_source"]), (None, None))

    def test_an_empty_state_dir_flag_is_refused(self):
        runner = OpenDouble()
        run, obj = self.twin(str(self.bundle), "--state-dir", "", runner=runner)
        self.assert_refused(run, obj, runner, "--state-dir is empty")

    def test_a_state_dir_that_exists_and_is_not_a_directory_is_refused(self):
        runner = OpenDouble()
        self.state.write_text("a file\n", encoding="utf-8")
        run, obj = self.twin(str(self.bundle), runner=runner)
        self.assertEqual((run.code, obj["ran"], runner.calls), (1, False, []))
        self.assertIn("is not a directory", obj["reason"])
        self.assertEqual(self.state.read_text(encoding="utf-8"), "a file\n")

    def test_a_state_dir_under_a_file_cannot_be_looked_at_and_is_refused(self):
        runner = OpenDouble()
        blocker = self.dir / "blocker"
        blocker.write_text("x", encoding="utf-8")
        run, obj = self.twin(str(self.bundle), "--state-dir", str(blocker / "state"),
                             runner=runner)
        self.assertEqual((run.code, obj["ran"], runner.calls), (1, False, []))
        self.assertIn("cannot be read", obj["reason"])

    def test_every_reason_is_named_at_once(self):
        runner = OpenDouble()
        run, obj = self.twin("--cwd", str(self.dir / "nope"), "--", "-x", runner=runner,
                             env={"TWINE_BALE_ROOT": ROOTS.other.as_posix()}, state=False)
        self.assertEqual(len(obj["refusals"]), 4, obj["refusals"])
        for needle, refusal in zip(("BUNDLE", "--cwd", "not the pin", "state directory"),
                                   obj["refusals"]):
            self.assertIn(needle, refusal)
        self.assertEqual(runner.calls, [])

    def test_human_mode_refused_is_one_line(self):
        runner = OpenDouble()
        run = self.run_verb("", runner=runner)
        self.assertEqual(run.code, 1)
        self.assertEqual(run.stdout.count("\n"), 1)
        self.assertTrue(run.stdout.startswith("carry bundle : refused — BUNDLE is empty"),
                        run.stdout)


# ---------------------------------------------------------------------------
# 3. The call: exactly the recorded argvs, once
# ---------------------------------------------------------------------------


class TheCall(Case):

    def test_the_argv_is_the_recorded_one_with_the_bundle_absolute(self):
        player = self.player()
        _, obj = self.twin(str(self.bundle), runner=player)
        self.assertEqual(player.calls, [[str(ROOTS.ok / "bin" / "bale"), "open",
                                         str(self.bundle), "--json"]])
        self.assertEqual((obj["argv"], obj["bundle"]), (player.calls[0], str(self.bundle)))

    def test_with_check_the_argv_is_the_recorded_check(self):
        player = FixturePlayer(REPO_ROOT)
        _, obj = self.twin(str(self.bundle), "--check", runner=player, cwd=REPO_ROOT)
        self.assertEqual(player.calls, [[str(ROOTS.ok / "bin" / "bale"), "open", "--check",
                                         str(self.bundle), "--json"]])
        self.assertTrue(obj["ok"], obj["reason"])

    def test_a_relative_name_of_an_existing_file_is_made_absolute(self):
        player = self.player()
        rel = os.path.relpath(self.bundle, Path.cwd())
        _, obj = self.twin(rel, runner=player)
        self.assertEqual((obj["ok"], obj["bundle"], player.calls[0][2]),
                         (True, str(self.bundle), str(self.bundle)))

    def test_a_tilde_name_is_expanded_when_it_names_a_file(self):
        player = self.player()
        home = self.dir / "home"
        home.mkdir()
        (home / "b.bale-bundle").write_bytes(b"x")
        old = os.environ.get("HOME")
        os.environ["HOME"] = str(home)
        try:
            _, obj = self.twin("~/b.bale-bundle", runner=player)
        finally:
            if old is None:
                del os.environ["HOME"]
            else:
                os.environ["HOME"] = old
        self.assertEqual(obj["bundle"], str(home / "b.bale-bundle"))

    def test_a_name_that_is_no_file_here_is_passed_as_given(self):
        """bale resolves it: its current directory, then apply.search_paths
        — the bare name the crafter prints works from Downloads."""
        player = self.player()
        _, obj = self.twin("2026-10-07-twine-049-scoped.bale-bundle", runner=player)
        self.assertEqual(player.calls[0][1:], ["open", "2026-10-07-twine-049-scoped.bale-bundle",
                                               "--json"])
        self.assertEqual(obj["bundle"], "2026-10-07-twine-049-scoped.bale-bundle")

    def test_a_name_too_long_to_stat_is_passed_as_given_not_a_traceback(self):
        player = self.player()
        long_name = "b" * 5000
        _, obj = self.twin(long_name, runner=player)
        self.assertEqual((obj["ok"], obj["bundle"]), (True, long_name))

    def test_an_existing_file_named_like_a_flag_is_passed_absolute(self):
        flaggy = self.dir / "--no-sandbox"
        flaggy.write_bytes(b"x")
        player = self.player()
        old = os.getcwd()
        os.chdir(self.dir)
        try:
            _, obj = self.twin("--cwd", str(self.repo), "--state-dir", str(self.state), "--",
                               "--no-sandbox", runner=player)
        finally:
            os.chdir(old)
        self.assertEqual((obj["ok"], player.calls[0][2]), (True, str(flaggy)))

    def test_the_seam_gets_the_cwd_no_stdin_the_long_timeout_and_the_cap(self):
        runner = OpenDouble(stdout=open_recording("opened").stdout)
        _, obj = self.twin(str(self.bundle), runner=runner)
        self.assertEqual(len(runner.calls), 1)
        call = runner.calls[0]
        self.assertEqual((call["cwd"], call["stdin"], call["timeout"], call["stdout_cap"]),
                         (str(self.repo), None, BUNDLE_TIMEOUT_SECONDS, BALE_STDOUT_CAP_BYTES))
        self.assertEqual(BUNDLE_TIMEOUT_SECONDS, 1800.0)
        self.assertEqual(call["env"], {"TWINE_BALE_ROOT": ROOTS.ok.as_posix()})
        self.assertEqual(obj["cwd"], str(self.repo))

    def test_cwd_defaults_to_the_current_directory(self):
        runner = OpenDouble(stdout=open_recording("opened").stdout)
        out, err = io.StringIO(), io.StringIO()
        ctx = Context(env={"TWINE_BALE_ROOT": ROOTS.ok.as_posix()}, stdout=out, stderr=err,
                      which=lambda n: None, stdin=io.BytesIO(b""), run=runner)
        main(["carry", "bundle", str(self.bundle), "--state-dir", str(self.state), "--json"],
             ctx=ctx)
        obj = json.loads(out.getvalue())
        self.assertEqual((obj["cwd"], runner.calls[0]["cwd"]),
                         (str(Path.cwd()), str(Path.cwd())))
        self.assertEqual(self.read_record()["cwd"], str(Path.cwd()))

    def test_open_argv_is_exactly_the_recorded_shapes(self):
        exe = Path("/r/bin/bale")
        self.assertEqual(bale.open_argv(exe, "/b/x.bale-bundle"),
                         ["/r/bin/bale", "open", "/b/x.bale-bundle", "--json"])
        self.assertEqual(bale.open_argv(exe, "x.bale-bundle", check=True),
                         ["/r/bin/bale", "open", "--check", "x.bale-bundle", "--json"])
        for bad in ("", "-x", "--dry-run"):
            with self.subTest(bundle=bad), self.assertRaises(ValueError):
                bale.open_argv(exe, bad)


# ---------------------------------------------------------------------------
# 4. opened, and the record
# ---------------------------------------------------------------------------


class Opened(Case):

    def test_opened_is_ok_and_the_record_has_exactly_its_keys_and_values(self):
        recording = open_recording("opened")
        run, obj = self.twin(str(self.bundle), runner=self.player())
        self.assertEqual((obj["ok"], obj["ran"], obj["exit_code"], obj["outcome"], obj["sid"],
                          obj["desk"]), (True, True, 0, "opened", SID, None))
        self.assertEqual(obj["open"], recording.line)
        self.assertEqual(tuple(recording.line), OPEN_KEYS)
        self.assertEqual((obj["tarball"], obj["tarball_source"]),
                         (recording.line["tarball"], "bale"))
        self.assertEqual(obj["opener"], recording.line["opener"])
        self.assertEqual((obj["record"], obj["record_error"], obj["reason"], obj["refusals"]),
                         (str(self.record_file()), None, None, []))
        self.assertEqual((obj["state_dir"], obj["state_dir_source"]),
                         (str(self.state), "--state-dir"))
        record = self.read_record()
        self.assertEqual(tuple(record), RECORD_KEYS)
        self.assertEqual((record["sid"], record["cwd"], record["tarball"]),
                         (SID, str(self.repo), recording.line["tarball"]))
        self.assertEqual(len(record["opens"]), 1)
        entry = record["opens"][0]
        self.assertEqual(tuple(entry), ENTRY_KEYS)
        self.assertEqual((entry["outcome"], entry["desk"], entry["bundle_sha256"],
                          entry["opener_sha256"]),
                         ("opened", None,
                          "223b026b178499c313e6cfbe871a7ec7aa560097c7791b2831dff0d1075e8a26",
                          sha256_text(recording.line["opener"])))
        self.assertRegex(entry["recorded_at"], UTC_Z)

    def test_human_stdout_is_byte_identical_to_the_recorded_opener(self):
        recording = open_recording("opened")
        run = self.run_verb(str(self.bundle), runner=self.player())
        self.assertEqual(run.code, 0)
        self.assertEqual(run.stdout.encode("utf-8"), recording.line["opener"].encode("utf-8"))
        self.assertTrue(recording.line["opener"].endswith("\n"))
        for needle in (f"session {SID}", "the first desk", recording.line["tarball"],
                       str(self.record_file()), "paste it into the new chat"):
            self.assertIn(needle, run.stderr)

    def test_an_opener_without_a_final_newline_gains_one(self):
        """A double: the recorded line with its opener's last LF taken off."""
        opener = open_recording("opened").line["opener"]
        runner = OpenDouble(stdout=edited_line("opened", opener=opener.rstrip("\n")))
        run = self.run_verb(str(self.bundle), runner=runner)
        self.assertEqual((run.code, run.stdout), (0, opener))

    def test_the_record_files_modes(self):
        self.twin(str(self.bundle), runner=self.player())
        directory = self.state / "inflight"
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.record_file().stat().st_mode), 0o600)

    def test_a_state_directory_that_does_not_exist_yet_is_created(self):
        deep = self.dir / "not" / "yet" / "state"
        _, obj = self.twin(str(self.bundle), "--state-dir", str(deep), runner=self.player())
        self.assertTrue(obj["ok"], obj["reason"])
        self.assertTrue((deep / "inflight" / f"{SID}.json").is_file())

    def test_the_state_directory_resolves_from_the_environment(self):
        env = {"TWINE_BALE_ROOT": ROOTS.ok.as_posix(), "TWINE_STATE_DIR": str(self.state)}
        _, obj = self.twin(str(self.bundle), runner=self.player(), env=env, state=False)
        self.assertEqual((obj["ok"], obj["state_dir"], obj["state_dir_source"]),
                         (True, str(self.state), "TWINE_STATE_DIR"))
        self.assertTrue(self.record_file().is_file())

    def test_opened_again_replaces_the_record_and_is_not_an_error(self):
        """The decision this session names: replacing a record on `opened`
        is not an error, so `record_error` stays null; stderr says so."""
        self.twin(str(self.bundle), runner=self.player())
        self.twin(str(self.bundle), runner=self.player(SELECT_SECOND_DESK))
        self.assertEqual(len(self.read_record()["opens"]), 2)
        run, obj = self.twin(str(self.bundle), runner=self.player())
        self.assertEqual((obj["ok"], obj["record_error"]), (True, None))
        self.assertEqual([e["outcome"] for e in self.read_record()["opens"]], ["opened"])
        self.assertIn("was replaced by this open", run.stderr)


# ---------------------------------------------------------------------------
# 5. second-desk: appending, or a fresh record
# ---------------------------------------------------------------------------


class SecondDesk(Case):

    def test_opened_then_second_desk_appends_and_takes_the_records_tarball(self):
        opened = open_recording("opened")
        second = open_recording("second-desk")
        self.assertIsNone(second.line["tarball"], "bale 0.4.49's second-desk names none")
        self.twin(str(self.bundle), runner=self.player())
        run, obj = self.twin(str(self.bundle), runner=self.player(SELECT_SECOND_DESK))
        self.assertEqual((obj["ok"], obj["outcome"], obj["desk"], obj["sid"]),
                         (True, "second-desk", "desk-2", SID))
        self.assertEqual((obj["tarball"], obj["tarball_source"]),
                         (opened.line["tarball"], "record"))
        self.assertEqual((obj["record"], obj["record_error"]), (str(self.record_file()), None))
        record = self.read_record()
        self.assertEqual(tuple(record), RECORD_KEYS)
        self.assertEqual(record["tarball"], opened.line["tarball"])
        self.assertEqual([(e["outcome"], e["desk"]) for e in record["opens"]],
                         [("opened", None), ("second-desk", "desk-2")])
        self.assertEqual(record["opens"][1]["opener_sha256"],
                         sha256_text(second.line["opener"]))
        self.assertEqual(tuple(record["opens"][1]), ENTRY_KEYS)
        self.assertIn("(from record)", run.stderr)
        self.assertIn("desk-2", run.stderr)

    def test_human_stdout_is_the_desk_2_opener(self):
        self.twin(str(self.bundle), runner=self.player())
        run = self.run_verb(str(self.bundle), runner=self.player(SELECT_SECOND_DESK))
        self.assertEqual(run.stdout, open_recording("second-desk").line["opener"])
        self.assertIn(f"{SID}@desk-2", run.stdout)

    def test_second_desk_with_no_record_writes_a_fresh_one_and_says_so(self):
        _, obj = self.twin(str(self.bundle), runner=self.player(SELECT_SECOND_DESK))
        self.assertEqual((obj["ok"], obj["tarball"], obj["tarball_source"]),
                         (True, None, None))
        self.assertEqual(obj["record"], str(self.record_file()))
        self.assertIn("no in-flight record", obj["record_error"])
        self.assertIn("fresh", obj["record_error"])
        record = self.read_record()
        self.assertEqual((record["tarball"], record["cwd"], len(record["opens"])),
                         (None, str(self.repo), 1))
        self.assertEqual(record["opens"][0]["outcome"], "second-desk")

    def test_second_desk_over_a_record_that_is_not_one_replaces_it_naming_why(self):
        self.record_file().parent.mkdir(parents=True)
        self.record_file().write_text('{"sid": "2026-10-07-sc-002"}\n', encoding="utf-8")
        run, obj = self.twin(str(self.bundle), runner=self.player(SELECT_SECOND_DESK))
        self.assertTrue(obj["ok"])
        self.assertIn("is not an in-flight record", obj["record_error"])
        self.assertIn("lacks cwd, tarball, opens", obj["record_error"])
        self.assertIn("fresh", obj["record_error"])
        self.assertEqual(self.read_record()["tarball"], None)
        self.assertIn("warning:", run.stderr)

    def test_bales_tarball_wins_when_its_second_desk_line_names_one(self):
        """A double: the recorded second-desk line with a tarball, as the
        bale-src follow-on will print it — bale's, tarball_source "bale"."""
        self.twin(str(self.bundle), runner=self.player())
        runner = OpenDouble(stdout=edited_line("second-desk", tarball="/from/bale.tar.gz"))
        _, obj = self.twin(str(self.bundle), runner=runner)
        self.assertEqual((obj["tarball"], obj["tarball_source"]), ("/from/bale.tar.gz", "bale"))
        self.assertEqual(self.read_record()["tarball"], open_recording("opened").line["tarball"],
                         "the record keeps the first open's tarball")

    def test_two_desks_at_once_lose_neither_entry(self):
        """The read-append-replace runs under the flock on inflight/."""
        self.twin(str(self.bundle), runner=self.player())
        opener = open_recording("second-desk").line["opener"]
        errors: list[BaseException] = []

        def desk(n: int) -> None:
            try:
                inflight.record_open(self.state, SID, outcome="second-desk",
                                     cwd=str(self.repo), tarball=None, desk=f"desk-{n}",
                                     bundle_sha256=None, opener=opener)
            except BaseException as exc:   # surfaced below, never swallowed
                errors.append(exc)

        threads = [threading.Thread(target=desk, args=(n,)) for n in range(2, 10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        desks = sorted(e["desk"] for e in self.read_record()["opens"][1:])
        self.assertEqual(desks, sorted(f"desk-{n}" for n in range(2, 10)))


# ---------------------------------------------------------------------------
# 6. --check: a rehearsal writes nothing and needs no state directory
# ---------------------------------------------------------------------------


class Check(Case):

    def test_check_is_ok_on_rehearsed_and_writes_nothing_under_a_given_state_dir(self):
        self.state.mkdir()
        before = tree(self.dir)
        run, obj = self.twin(str(self.bundle), "--check", runner=FixturePlayer(REPO_ROOT),
                             cwd=REPO_ROOT)
        self.assertEqual((obj["ok"], obj["outcome"], obj["sid"], obj["opener"], obj["check"]),
                         (True, "rehearsed", None, None, True))
        self.assertEqual(obj["open"], open_recording("rehearsed").line)
        self.assertEqual((obj["record"], obj["record_error"], obj["tarball"],
                          obj["tarball_source"], obj["state_dir"], obj["state_dir_source"]),
                         (None, None, None, None, None, None))
        self.assertEqual(tree(self.dir), before, "--check wrote something")
        self.assertIn("--state-dir is not read", run.stderr)

    def test_check_needs_no_state_directory(self):
        _, obj = self.twin(str(self.bundle), "--check", runner=FixturePlayer(REPO_ROOT),
                           cwd=REPO_ROOT, state=False)
        self.assertEqual((obj["ok"], obj["refusals"]), (True, []))
        self.assertFalse(self.state.exists())

    def test_check_human_mode_is_one_line(self):
        run = self.run_verb(str(self.bundle), "--check", runner=FixturePlayer(REPO_ROOT),
                            cwd=REPO_ROOT, state=False)
        self.assertEqual((run.code, run.stdout),
                         (0, f"carry bundle {self.bundle}: rehearsed — bale would open it "
                             "(nothing written)\n"))

    def test_rehearsed_without_check_is_not_ok_and_writes_nothing(self):
        """A double: the recorded rehearsal answered to a plain open."""
        runner = OpenDouble(stdout=open_recording("rehearsed").stdout)
        _, obj = self.twin(str(self.bundle), runner=runner)
        self.assertEqual((obj["ok"], obj["outcome"], obj["record"]), (False, "rehearsed", None))
        self.assertIn("outcome 'rehearsed'; an open wants 'opened' or 'second-desk'",
                      obj["reason"])
        self.assertEqual(tree(self.state), set())

    def test_opened_with_check_is_not_ok_and_writes_nothing(self):
        """A double: the recorded open answered to --check."""
        runner = OpenDouble(stdout=open_recording("opened").stdout)
        self.state.mkdir()
        _, obj = self.twin(str(self.bundle), "--check", runner=runner)
        self.assertEqual((obj["ok"], obj["outcome"], obj["record"], obj["tarball"]),
                         (False, "opened", None, None))
        self.assertIn("--check wants 'rehearsed'", obj["reason"])
        self.assertEqual(tree(self.state), set())


# ---------------------------------------------------------------------------
# 7. Not ok: what bale said instead, and nothing recorded
# ---------------------------------------------------------------------------


class NotOk(Case):

    def not_ok(self, runner, *needles: str) -> dict:
        run, obj = self.twin(str(self.bundle), runner=runner)
        self.assertEqual((run.code, obj["ok"], obj["ran"], obj["record"], obj["tarball"]),
                         (1, False, True, None, None))
        for needle in needles:
            self.assertIn(needle, obj["reason"])
        self.assertEqual(obj["refusals"], [])
        self.assertEqual(tree(self.state), set(), "a not-ok open recorded something")
        self.assertEqual(len(runner.calls), 1, "an open is never retried")
        human = self.run_verb(str(self.bundle), runner=OpenDouble(
            exit_code=runner.result.exit_code, stdout=runner.result.stdout,
            timed_out=runner.result.timed_out, capped=runner.result.stdout_capped))
        self.assertEqual(human.code, 1)
        self.assertEqual(human.stdout.count("\n"), 1)
        self.assertTrue(human.stdout.startswith(f"carry bundle {self.bundle}: NOT OK — "),
                        human.stdout)
        return obj

    def test_a_refusal_nothing_on_stdout_exit_1(self):
        """A double for bale's refusal (BALE.md §6.7: exit 1 through fail(),
        nothing on stdout, the reason on stderr) — no refusal is recorded."""
        obj = self.not_ok(OpenDouble(exit_code=1, stdout=b"",
                                     stderr=b"[bale] error: a double, not bale\n"),
                          "bale exited 1", "not one JSON object", "it was empty")
        self.assertEqual((obj["exit_code"], obj["open"], obj["stderr"]),
                         (1, None, "[bale] error: a double, not bale\n"))

    def test_bales_stderr_reaches_twines_stderr(self):
        runner = OpenDouble(exit_code=1, stderr=b"[bale] error: a double, not bale\n")
        run = self.run_verb(str(self.bundle), runner=runner)
        self.assertIn("[bale] error: a double, not bale", run.stderr)

    def test_a_timeout_says_the_session_may_or_may_not_be_open(self):
        obj = self.not_ok(OpenDouble(exit_code=None, timed_out=True),
                          f"did not finish within {BUNDLE_TIMEOUT_SECONDS:g}s",
                          "may or may not be open", "bale status", "never retries")
        self.assertEqual((obj["timed_out"], obj["exit_code"]), (True, None))

    def test_a_capped_stdout_is_not_ok_and_says_the_same(self):
        obj = self.not_ok(OpenDouble(exit_code=None, capped=True,
                                     stdout=open_recording("opened").stdout[:100]),
                          "stopped", "may or may not be open")
        self.assertTrue(obj["capped"])

    def test_a_line_with_another_outcome(self):
        obj = self.not_ok(OpenDouble(stdout=edited_line("opened", outcome=NOT_A_BALE_OUTCOME)),
                          f"outcome {NOT_A_BALE_OUTCOME!r}",
                          "an open wants 'opened' or 'second-desk'")
        self.assertEqual(obj["outcome"], NOT_A_BALE_OUTCOME)

    def test_a_line_missing_its_sid(self):
        """Doubles: the recorded open with its sid taken out, or not a sid."""
        self.not_ok(OpenDouble(stdout=edited_line("opened", drop="sid")),
                    "opened line has no sid twine accepts (sid None)")
        self.not_ok(OpenDouble(stdout=edited_line("opened", sid="-x ../y")),
                    "no sid twine accepts")

    def test_a_line_missing_its_opener(self):
        """Doubles: the recorded open with its opener taken out, or empty."""
        self.not_ok(OpenDouble(stdout=edited_line("opened", drop="opener")),
                    "opened line has no opener")
        self.not_ok(OpenDouble(stdout=edited_line("second-desk", opener="")),
                    "second-desk line has no opener")

    def test_a_line_carrying_text_that_is_not_utf8_is_not_ok_and_no_traceback(self):
        """A double: the recorded open with a lone-surrogate escape in its
        opener and tarball (a path with non-UTF-8 bytes, as Python's json
        writes one). twine can neither print nor record it as bale's: not
        ok, nothing recorded, the session named as maybe open, the twin
        writable as UTF-8 (`?` in place) and the raw line in `stdout`."""
        line = dict(open_recording("opened").line)
        line["opener"] = "opens /tmp/\udcff/x\n"
        line["tarball"] = "/tmp/\udcff/request.tar.gz"
        stdout = (json.dumps(line) + "\n").encode("ascii")
        self.assertIn(b"\\udcff", stdout)
        obj = self.not_ok(OpenDouble(stdout=stdout), "not UTF-8", "may be open",
                          "bale status", "never retries")
        self.assertEqual(obj["open"]["opener"], "opens /tmp/?/x\n")
        self.assertIn("\\udcff", obj["stdout"])
        json.dumps(obj, ensure_ascii=False).encode("utf-8")
        run = run_cli("carry", "bundle", str(self.bundle), "--cwd", str(self.repo),
                      "--state-dir", str(self.state), "--json",
                      bale_root=self._stub_replaying(stdout))
        self.assertEqual(run.code, 1, run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        self.assertFalse(json.loads(run.stdout)["ok"])

    def _stub_replaying(self, stdout: bytes) -> Path:
        line = self.dir / "line.json"
        line.write_bytes(stdout)
        stub = StubBale(open_stdout=line)
        self.addCleanup(stub.cleanup)
        return stub.root

    def test_a_non_zero_exit_beside_an_opened_line_is_not_ok(self):
        """A double for a contract bale keeps — its lines come with exit 0 —
        broken anyway: twine trusts the line only beside exit 0."""
        obj = self.not_ok(OpenDouble(exit_code=3, stdout=open_recording("opened").stdout),
                          "bale exited 3")
        self.assertEqual(obj["outcome"], "opened")

    def test_stdout_that_is_not_one_json_object(self):
        line = open_recording("opened").stdout
        for stdout in (b"[bale] usage\n", line + line, b"[1]\n"):
            with self.subTest(stdout=stdout[:20]):
                obj = self.not_ok(OpenDouble(stdout=stdout), "not one JSON object")
                self.assertEqual((obj["open"], obj["outcome"]), (None, None))

    def test_a_bale_that_cannot_be_started_is_a_refusal_after_the_argv(self):
        """The pinned root has no bin/bale: the real seam cannot start it."""
        out, err = io.StringIO(), io.StringIO()
        ctx = Context(env={"TWINE_BALE_ROOT": ROOTS.ok.as_posix()}, stdout=out, stderr=err,
                      which=lambda n: None, stdin=io.BytesIO(b""))
        code = main(["carry", "bundle", str(self.bundle), "--cwd", str(self.repo),
                     "--state-dir", str(self.state), "--json"], ctx=ctx)
        obj = json.loads(out.getvalue())
        self.assertEqual((code, obj["ok"], obj["ran"]), (1, False, False))
        self.assertIn("could not be started", obj["reason"])
        self.assertEqual(tree(self.state), set())


# ---------------------------------------------------------------------------
# 8. A record that cannot be written after the open
# ---------------------------------------------------------------------------


class RecordCannotBeWritten(Case):

    def test_ok_exit_0_record_null_and_the_error_named(self):
        """inflight/ is a file: the open happened, the record cannot land.
        The session is open in bale, so the verb stays ok — a failure would
        invite a retry, which would open another desk."""
        self.state.mkdir()
        (self.state / "inflight").write_text("not a directory\n", encoding="utf-8")
        run, obj = self.twin(str(self.bundle), runner=self.player())
        self.assertEqual((run.code, obj["ok"], obj["record"], obj["reason"]),
                         (0, True, None, None))
        self.assertIn("nothing is retried", obj["record_error"])
        self.assertIn("exists and is not a directory", obj["record_error"])
        self.assertEqual((obj["tarball"], obj["tarball_source"]),
                         (open_recording("opened").line["tarball"], "bale"))
        self.assertIn("warning: the open was not recorded", run.stderr)
        human = self.run_verb(str(self.bundle), runner=self.player())
        self.assertEqual((human.code, human.stdout),
                         (0, open_recording("opened").line["opener"]))
        self.assertIn("in-flight record not written", human.stderr)

    def test_a_record_path_that_is_a_directory(self):
        self.record_file().mkdir(parents=True)
        _, obj = self.twin(str(self.bundle), runner=self.player())
        self.assertEqual((obj["ok"], obj["record"]), (True, None))
        self.assertIn("cannot write the in-flight record", obj["record_error"])


# ---------------------------------------------------------------------------
# 9. The twin's keys on every path; nothing written but the record
# ---------------------------------------------------------------------------


class TwinAndWrites(Case):

    def test_the_twins_keys_are_the_same_on_every_path(self):
        """Case.twin asserts the exact key set on each run below: refused,
        not ok, opened, second-desk, rehearsed, a record that failed."""
        self.twin("", runner=OpenDouble())
        self.twin(str(self.bundle), runner=OpenDouble(exit_code=1))
        self.twin(str(self.bundle), runner=self.player())
        self.twin(str(self.bundle), runner=self.player(SELECT_SECOND_DESK))
        self.twin(str(self.bundle), "--check", runner=FixturePlayer(REPO_ROOT), cwd=REPO_ROOT)
        (self.state / "inflight" / f"{SID}.json").unlink()
        (self.state / "inflight").rmdir()
        (self.state / "inflight").write_text("x", encoding="utf-8")
        _, obj = self.twin(str(self.bundle), runner=self.player())
        self.assertIsNotNone(obj["record_error"])

    def test_the_verb_writes_nothing_but_the_record(self):
        """Where: <state-dir>/inflight/<sid>.json, and nowhere else — not
        the scratch repository (bale's, which the player stands in for), not
        beside the bundle. Nothing in Arc 1 removes it: a second open keeps
        it there."""
        before = tree(self.dir)
        self.twin(str(self.bundle), runner=self.player())
        self.twin(str(self.bundle), runner=self.player(SELECT_SECOND_DESK))
        self.assertEqual(tree(self.dir) - before,
                         {"state", "state/inflight", f"state/inflight/{SID}.json"})
        self.assertEqual(before - tree(self.dir), set())


# ---------------------------------------------------------------------------
# 10. The in-flight record module
# ---------------------------------------------------------------------------


class TheRecordModule(Case):

    def write_raw(self, obj) -> None:
        path = self.record_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")

    def good(self) -> dict:
        return {"sid": SID, "cwd": "/r", "tarball": None,
                "opens": [{"outcome": "opened", "desk": None, "bundle_sha256": None,
                           "opener_sha256": "ab", "recorded_at": "2026-10-07T00:00:00Z"}]}

    def test_no_record_reads_as_none(self):
        self.assertIsNone(inflight.read_inflight(self.state, SID))

    def test_a_well_formed_record_reads_back(self):
        self.write_raw(self.good())
        self.assertEqual(inflight.read_inflight(self.state, SID), self.good())

    def test_every_fault_is_named(self):
        cases = {
            "not json": ("{", "is not a JSON object"),
            "array": ("[]", "is not a JSON object"),
        }
        for label, (raw, needle) in cases.items():
            with self.subTest(case=label):
                self.write_raw(raw)
                with self.assertRaises(inflight.InflightRecordError) as caught:
                    inflight.read_inflight(self.state, SID)
                self.assertIn(needle, str(caught.exception))
        bad = self.good()
        bad.update(sid="other", cwd="relative", tarball=3, extra=1)
        bad["opens"][0].update(outcome="rehearsed", desk=2, opener_sha256="")
        del bad["opens"][0]["recorded_at"]
        self.write_raw(bad)
        with self.assertRaises(inflight.InflightRecordError) as caught:
            inflight.read_inflight(self.state, SID)
        message = str(caught.exception)
        for needle in ("keys the format does not name: 'extra'", "its sid is 'other'",
                       "cwd 'relative' is not an absolute path", "tarball 3",
                       "opens[0] lacks recorded_at", "opens[0].outcome 'rehearsed'",
                       "opens[0].desk 2", "opens[0].opener_sha256 ''"):
            self.assertIn(needle, message)
        self.write_raw(dict(self.good(), opens=[]))
        with self.assertRaises(inflight.InflightRecordError) as caught:
            inflight.read_inflight(self.state, SID)
        self.assertIn("not a non-empty array", str(caught.exception))

    def test_a_sid_that_is_not_one_is_refused(self):
        for sid in ("", "-x", "../x", "a b"):
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                inflight.inflight_path(self.state, sid)

    def test_record_open_refuses_an_outcome_that_opens_nothing(self):
        with self.assertRaises(ValueError):
            inflight.record_open(self.state, SID, outcome="rehearsed", cwd="/r",
                                 tarball=None, desk=None, bundle_sha256=None, opener="o")
        self.assertFalse(self.state.exists())

    def test_the_clock_is_injectable_and_the_hash_is_the_openers(self):
        rec = inflight.record_open(self.state, SID, outcome="opened", cwd="/r", tarball="/t",
                                   desk=None, bundle_sha256="b", opener="hello\n",
                                   clock=lambda: "2026-10-07T12:00:00Z")
        self.assertEqual(rec.record, {"sid": SID, "cwd": "/r", "tarball": "/t", "opens": [
            {"outcome": "opened", "desk": None, "bundle_sha256": "b",
             "opener_sha256": sha256_text("hello\n"), "recorded_at": "2026-10-07T12:00:00Z"}]})
        self.assertEqual((rec.found, rec.replaced, rec.fresh), (None, False, None))
        self.assertEqual(self.read_record(), rec.record)
        self.assertTrue(self.record_file().read_bytes().endswith(b"}\n"))

    # list_inflight (session twine-status-inflight): what `twine status`
    # reads the records through. Its rendering in `status` is
    # tests/test_status.py's InflightRecords.

    def test_list_inflight_with_no_inflight_directory_is_empty_and_creates_nothing(self):
        self.assertEqual(inflight.list_inflight(self.state), inflight.InflightListing((), ()))
        self.assertFalse(self.state.exists())
        self.state.mkdir()
        (self.state / "inflight").write_text("a file, not the directory")
        self.assertEqual(inflight.list_inflight(self.state), inflight.InflightListing((), ()))

    def test_list_inflight_reads_every_record_and_sorts_by_sid(self):
        for sid in ("b", "a-b", "a", SID):
            inflight.record_open(self.state, sid, outcome="opened", cwd="/r", tarball=None,
                                 desk=None, bundle_sha256=None, opener="o")
        listing = inflight.list_inflight(self.state)
        self.assertEqual(listing.sids, tuple(sorted(("b", "a-b", "a", SID))))
        self.assertLess(listing.sids.index("a"), listing.sids.index("a-b"))
        self.assertEqual(listing.faults, ())

    def test_list_inflight_names_each_entry_that_is_not_a_record_by_its_basename(self):
        inflight.record_open(self.state, SID, outcome="opened", cwd="/r", tarball=None,
                             desk=None, bundle_sha256=None, opener="o")
        bad = self.good()
        bad["opens"][0]["outcome"] = "rehearsed"
        self.write_raw(bad)                            # SID's record, now malformed
        (self.state / "inflight" / "README").write_text("notes")
        (self.state / "inflight" / "-x.json").write_text("{}")
        listing = inflight.list_inflight(self.state)
        self.assertEqual(listing.sids, ())
        self.assertEqual(listing.faults, (
            "-x.json is not an in-flight record: '-x' is not a session id twine accepts",
            f"{SID}.json is not an in-flight record: opens[0].outcome 'rehearsed' is not "
            "'opened' or 'second-desk'",
            "README is not an in-flight record: its name is not <sid>.json"))
        for fault in listing.faults:
            self.assertNotIn(str(self.state), fault)

    def test_list_inflight_faults_are_read_inflights_own_words(self):
        self.write_raw({})
        with self.assertRaises(inflight.InflightRecordError) as caught:
            inflight.read_inflight(self.state, SID)
        words = str(caught.exception)
        self.assertEqual(inflight.list_inflight(self.state).faults,
                         (f"{SID}.json" + words[len(str(self.record_file())):],))


# ---------------------------------------------------------------------------
# 11. Guards: one open argv; the record is never removed
# ---------------------------------------------------------------------------


class Guards(unittest.TestCase):

    def test_open_is_built_in_one_place_only(self):
        """The string "open" as an argv token appears in twine's code only
        inside twine.bale.open_argv, and in bale.py "--check" only there too;
        open_argv carries no other flag than --check and --json."""
        def tokens(node: ast.AST, value: str) -> int:
            # A dict key is a name, not an argv token: the JSON twin's `open`
            # key (bale's line, parsed) is spelled "open" too.
            keys = {id(k) for n in ast.walk(node) if isinstance(n, ast.Dict)
                    for k in n.keys if k is not None}
            return sum(1 for n in ast.walk(node)
                       if isinstance(n, ast.Constant) and n.value == value
                       and id(n) not in keys)

        found: dict[str, int] = {}
        for path in sorted((REPO_ROOT / "twine").rglob("*.py")):
            tree_ = ast.parse(path.read_text(encoding="utf-8"))
            rel = path.relative_to(REPO_ROOT).as_posix()
            if tokens(tree_, "open"):
                found[rel] = tokens(tree_, "open")
            if rel == "twine/bale.py":
                builder = [f for f in ast.walk(tree_) if isinstance(f, ast.FunctionDef)
                           and f.name == "open_argv"]
                self.assertEqual(len(builder), 1)
                for value in ("open", "--check"):
                    self.assertEqual(tokens(builder[0], value), tokens(tree_, value),
                                     f"{value!r} built outside open_argv")
                flags = {n.value for n in ast.walk(builder[0])
                         if isinstance(n, ast.Constant) and isinstance(n.value, str)
                         and n.value.startswith("--") and " " not in n.value}
                self.assertEqual(flags, {"--check", "--json"})
        self.assertEqual(found, {"twine/bale.py": 1}, found)

    def test_nothing_in_the_record_module_removes_a_record(self):
        """Nothing in Arc 1 removes an in-flight record (Arc 2's loop knows
        when a session closes): no unlink, remove, rmdir or rmtree in
        twine/inflight.py or the verb."""
        for rel in ("twine/inflight.py", "twine/commands/carry_bundle.py"):
            tree_ = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
            calls = {n.func.attr for n in ast.walk(tree_)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
            self.assertFalse(calls & {"unlink", "remove", "rmdir", "rmtree", "removedirs"},
                             rel)

    def test_the_verb_imports_nothing_that_runs_or_reaches_out(self):
        """bale runs through ctx.run only (cli-contract.md §10.6)."""
        forbidden = {"subprocess", "os", "shutil", "socket", "urllib", "http",
                     "multiprocessing", "pty", "asyncio", "ctypes"}
        tree_ = ast.parse((REPO_ROOT / "twine/commands/carry_bundle.py")
                          .read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree_):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        self.assertFalse(roots & forbidden, roots & forbidden)


# ---------------------------------------------------------------------------
# 12. End to end, as a subprocess, against a stub bale
# ---------------------------------------------------------------------------


class EndToEnd(Case):

    def setUp(self):
        super().setUp()
        self.stub = StubBale(open_stdout=open_recording("opened").path,
                             stderr="[bale] stub: not bale\n")
        self.addCleanup(self.stub.cleanup)

    def test_an_open_through_the_real_seam(self):
        recording = open_recording("opened")
        run = run_cli("carry", "bundle", str(self.bundle), "--cwd", str(self.repo),
                      "--state-dir", str(self.state), bale_root=self.stub.root)
        self.assertEqual(run.code, 0, run.stderr)
        self.assertEqual(run.stdout.encode("utf-8"), recording.line["opener"].encode("utf-8"))
        self.assertEqual(self.stub.argv(), ["open", str(self.bundle), "--json"])
        self.assertEqual(self.stub.cwd(), str(self.repo))
        self.assertIn("[bale] stub: not bale", run.stderr)
        record = self.read_record()
        self.assertEqual(tuple(record), RECORD_KEYS)
        self.assertEqual(tuple(record["opens"][0]), ENTRY_KEYS)
        self.assertEqual(record["tarball"], recording.line["tarball"])

    def test_the_json_twin_through_the_real_seam(self):
        run = run_cli("carry", "bundle", str(self.bundle), "--cwd", str(self.repo),
                      "--state-dir", str(self.state), "--json", bale_root=self.stub.root)
        obj = json.loads(run.stdout)
        self.assertEqual(set(obj), TWIN_KEYS)
        self.assertEqual((run.code, obj["ok"], obj["sid"], obj["bale"]["installed"]),
                         (0, True, SID, PIN))
        self.assertEqual(obj["stderr"], "[bale] stub: not bale\n")

    def test_a_version_other_than_the_pin_is_refused_and_never_run(self):
        (self.stub.root / "bin" / "VERSION").write_text("0.4.46\n", encoding="utf-8")
        run = run_cli("carry", "bundle", str(self.bundle), "--state-dir", str(self.state),
                      "--json", bale_root=self.stub.root)
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["ran"]), (1, False, False))
        self.assertIn(f"is 0.4.46, not the pin {PIN}", obj["reason"])
        self.assertIsNone(self.stub.argv(), "the stub was started")
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()

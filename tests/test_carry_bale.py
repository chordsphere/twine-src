"""`twine carry exchange` and `twine carry response` (Arc 1 session
2b-ii): the bale hand-offs. No test here reaches a bale (T8): bale is
the fixture player (tests.helpers.FixturePlayer, answering from
fixtures/), a run-seam double (BaleDouble, below), or a stub executable
(tests.helpers.StubBale) — and a bale on PATH is shown never to be the
one run.

What is recorded, and what stands in for what is not:

  - `bale apply --dry-run --json` on a clean response: recorded
    (fixtures/bale-0.4.45/twine-src/apply_--dry-run_--json_tarball.json);
    its exit code is unrecorded, so every test replaying it names the
    exit it assumes (ASSUMED_DRY_RUN_EXIT).
  - `bale relay <sid> -`: no output recorded. The crafter's exchange
    emission (fixtures/bale-0.4.45/crafter/--emit-block-stdin.txt)
    stands in for its stdout — TARBALL.md §5.9.2 pins the crafter's and
    relay's renderings of a record byte-identical — and is also the
    block a worker hands the courier.
  - every refusal, HOLD, non-zero exit or timeout from bale: unrecorded;
    BaleDouble results, each built in this file and named a double.

Sections:
  1. Helpers and doubles
  2. carry exchange: choosing and vouching for the block
  3. carry exchange: the relay call
  4. carry response: the tarball and the dry run
  5. carry response: never a merge (T12)
  6. End to end, as a subprocess, against a stub bale
  7. Finding bale: the tests never reach a real one
"""

from __future__ import annotations

import ast
import io
import json
import os
import shlex
import shutil
import tempfile
import unittest
from pathlib import Path

from twine import REPO_ROOT, bale
from twine.cli import Context, main
from twine.commands.carry_bale import BALE_STDOUT_CAP_BYTES, BALE_TIMEOUT_SECONDS
from twine.process import RunResult

from tests.helpers import (PIN, FixturePlayer, RecordingRunner, Run, StubBale,
                           TempRoots, carried_relpath, emission_relpath,
                           fixture_relpath, run_cli, turn)

# ---------------------------------------------------------------------------
# 1. Helpers and doubles
# ---------------------------------------------------------------------------

EXCHANGE = REPO_ROOT / emission_relpath("crafter", ["--emit-block", "-"])
EXCHANGE_SID = "2026-10-02-twine-take-read-001"
LIGHT = REPO_ROOT / emission_relpath("crafter", ["--light-block", "-"])
RELAY_TO_PLANNER = REPO_ROOT / carried_relpath(
    "relay", "2026-10-01-twine-seed-effort-003", "planner")
DRY_RUN = REPO_ROOT / fixture_relpath(["apply", "--dry-run", "--json", "/x.tar.gz"], "repo")
DRY_RUN_REL = DRY_RUN.relative_to(REPO_ROOT).as_posix()
# The dry-run fixture's exit code is unrecorded (fixtures/README.md). A
# dry run that printed outcome "dry-run" is taken to have exited 0 — an
# assumption, named here and nowhere else.
ASSUMED_DRY_RUN_EXIT = {DRY_RUN_REL: 0}

EXCHANGE_FIXED = {"sid", "block", "ran", "exit_code", "stdout", "stderr",
                  "reason", "refusals"}
RESPONSE_FIXED = {"tarball", "ran", "exit_code", "dry_run", "outcome", "apply_line",
                  "stderr", "reason", "refusals"}


class BaleDouble(RecordingRunner):
    """A double, not a recording: answers every call with a RunResult
    this file builds, standing in for a bale output nobody has recorded
    (a refusal, a HOLD, a non-zero exit, a timeout). Records each call."""

    def __init__(self, exit_code: int | None = 0, stdout: bytes = b"",
                 stderr: bytes = b"", timed_out: bool = False) -> None:
        super().__init__(RunResult(argv=("bale",), exit_code=exit_code,
                                   stdout=stdout, stderr=stderr,
                                   timed_out=timed_out))


class RecordingPlayer(FixturePlayer):
    """The fixture player, also recording each call's keywords (the base
    records argvs only) so a test can read the stdin and cwd it was given."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.kwargs: list[dict] = []

    def __call__(self, argv, **kwargs):
        self.kwargs.append(kwargs)
        return super().__call__(argv, **kwargs)


def run_verb(verb: str, *argv: str, runner, env: dict | None = None,
             stdin: bytes = b"") -> Run:
    """`twine carry <verb> …` in-process, bale reached only through
    `runner`. TWINE_BALE_ROOT names a temp root with bin/VERSION at the
    pin unless `env` says otherwise; nothing is looked up on PATH."""
    out, err = io.StringIO(), io.StringIO()
    ctx = Context(env=env if env is not None else {"TWINE_BALE_ROOT": ROOTS.ok.as_posix()},
                  stdout=out, stderr=err, which=lambda name: None,
                  stdin=io.BytesIO(stdin), run=runner)
    code = main(["carry", verb, *argv], ctx=ctx)
    return Run(code, out.getvalue(), err.getvalue())


def one_line(test: unittest.TestCase, stdout: str, command: str) -> dict:
    lines = stdout.split("\n")
    test.assertEqual((len(lines), lines[1]), (2, ""), f"one JSON line: {stdout!r}")
    obj = json.loads(lines[0])
    test.assertEqual(obj["command"], command)
    return obj


ROOTS: TempRoots


def setUpModule():
    global ROOTS
    ROOTS = TempRoots()


def tearDownModule():
    ROOTS.cleanup()


class TempCase(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="twine-carry-bale-")
        self.dir = Path(self._dir.name).resolve()

    def tearDown(self):
        self._dir.cleanup()

    def write(self, text: str | bytes, name: str = "turn.txt") -> Path:
        path = self.dir / name
        if isinstance(text, str):
            text = text.encode("utf-8")
        path.write_bytes(text)
        return path

    def exchange_turn(self, block: str | None = None, name: str = "turn.txt") -> Path:
        return self.write(turn("Carry this to the planner:", "",
                               block or EXCHANGE.read_text(encoding="utf-8"),
                               "Thanks."), name)

    def exchange(self, *argv: str, runner=None, **kw) -> tuple[Run, dict]:
        runner = runner if runner is not None else BaleDouble(stdout=EXCHANGE.read_bytes())
        run = run_verb("exchange", *argv, "--json", runner=runner, **kw)
        self.assertNotIn("Traceback", run.stderr)
        return run, one_line(self, run.stdout, "carry exchange")

    def response(self, *argv: str, runner=None, **kw) -> tuple[Run, dict]:
        runner = runner if runner is not None else RecordingPlayer(
            REPO_ROOT, assumed_exits=ASSUMED_DRY_RUN_EXIT)
        run = run_verb("response", *argv, "--json", runner=runner, **kw)
        self.assertNotIn("Traceback", run.stderr)
        return run, one_line(self, run.stdout, "carry response")

    def tarball(self, name: str = "response-2026-10-03-x-001.tar.gz") -> Path:
        return self.write(b"not inspected by twine\n", name)

    def assert_refused(self, run: Run, obj: dict, runner, *needles: str) -> None:
        """Refused before bale: exit 1, nothing ran, the seam never called,
        every reason in `reason` and listed in `refusals`."""
        self.assertEqual((run.code, obj["ok"], obj["ran"], obj["exit_code"]),
                         (1, False, False, None))
        self.assertEqual((obj["stdout"], runner.calls), ("", []),
                         "refused, yet bale was called")
        for needle in needles:
            self.assertIn(needle, obj["reason"])
        self.assertEqual("; ".join(obj["refusals"]), obj["reason"])


def exchange_text() -> str:
    return EXCHANGE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 2. carry exchange: choosing and vouching for the block
# ---------------------------------------------------------------------------


class ExchangeChoosesTheBlock(TempCase):

    def test_one_exchange_block_is_chosen_and_its_sid_reported(self):
        runner = BaleDouble(stdout=EXCHANGE.read_bytes())
        run, obj = self.exchange(str(self.exchange_turn()), runner=runner)
        self.assertEqual((run.code, obj["ok"], obj["sid"], obj["block"]),
                         (0, True, EXCHANGE_SID, 1))
        self.assertTrue(EXCHANGE_FIXED <= set(obj), EXCHANGE_FIXED - set(obj))

    def test_prose_has_no_exchange_block_refused(self):
        runner = BaleDouble()
        run, obj = self.exchange(str(self.write("Nothing to carry.\n")), runner=runner)
        self.assert_refused(run, obj, runner, "no exchange block")
        self.assertIsNone(obj["sid"])

    def test_two_exchange_blocks_without_block_refused_naming_both(self):
        runner = BaleDouble()
        path = self.write(turn(exchange_text(), "and again", exchange_text()))
        run, obj = self.exchange(str(path), runner=runner)
        self.assert_refused(run, obj, runner, "2 exchange blocks", "[1]", "[2]",
                            "--block")

    def test_block_number_picks_by_takes_numbering(self):
        """A light block, then two exchange blocks: take numbers the second
        exchange [3]; --block 3 relays exactly that block's lines."""
        second = exchange_text().replace(EXCHANGE_SID, "2026-10-03-twine-other-002", 1)
        path = self.write(turn(LIGHT.read_text(encoding="utf-8"), exchange_text(), second))
        take = json.loads(run_cli("take", str(path), "--json").stdout)
        self.assertEqual([b["kind"] for b in take["blocks"]],
                         ["light", "exchange", "exchange"])
        runner = BaleDouble(stdout=EXCHANGE.read_bytes())
        run, obj = self.exchange(str(path), "--block", "3", runner=runner)
        self.assertEqual((obj["ok"], obj["block"], obj["sid"]),
                         (True, 3, "2026-10-03-twine-other-002"))
        self.assertEqual(runner.calls[0]["stdin"], second.encode("utf-8"))

    def test_block_naming_another_kind_refused(self):
        runner = BaleDouble()
        path = self.write(turn(LIGHT.read_text(encoding="utf-8"), exchange_text()))
        run, obj = self.exchange(str(path), "--block", "1", runner=runner)
        self.assert_refused(run, obj, runner, "light block", "not an exchange")

    def test_a_relay_block_to_the_planner_is_never_carried(self):
        """cli-contract.md §9.4 (T14): carry exchange carries exchange
        blocks only, so a `to: planner` relay block cannot be pointed at."""
        runner = BaleDouble()
        path = self.write(turn(RELAY_TO_PLANNER.read_text(encoding="utf-8"),
                               exchange_text()))
        run, obj = self.exchange(str(path), "--block", "1", runner=runner)
        self.assert_refused(run, obj, runner, "relay block", "not an exchange")
        run, obj = self.exchange(str(self.write(
            RELAY_TO_PLANNER.read_bytes(), "relay.txt")), runner=runner)
        self.assert_refused(run, obj, runner, "no exchange block", "relay")

    def test_block_out_of_range_refused(self):
        runner = BaleDouble()
        for n in ("0", "2", "-1"):
            with self.subTest(block=n):
                run, obj = self.exchange(str(self.exchange_turn()), "--block", n,
                                         runner=runner)
                self.assert_refused(run, obj, runner, "names no block")

    def test_unreadable_and_non_utf8_input_refused(self):
        runner = BaleDouble()
        run, obj = self.exchange(str(self.dir / "missing.txt"), runner=runner)
        self.assert_refused(run, obj, runner, "cannot read")
        run, obj = self.exchange(str(self.write(b"\xff\xfe junk\n", "bad.txt")),
                                 runner=runner)
        self.assert_refused(run, obj, runner, "not UTF-8")


class ExchangeVouchesForTheBlock(TempCase):
    """Every integrity fault refuses before bale, naming the fault; the
    block is never repaired."""

    def faulty(self, block: str, fault: str) -> None:
        runner = BaleDouble()
        run, obj = self.exchange(str(self.exchange_turn(block)), runner=runner)
        self.assert_refused(run, obj, runner, "fails integrity", f"({fault})",
                            "never relays", "never repairs")
        self.assertFalse(obj["integrity"]["ok"])
        self.assertEqual(obj["integrity"]["fault"], fault)

    def test_mismatch(self):
        edited = exchange_text().replace('"round": 1', '"round": 2', 1)
        self.assertNotEqual(edited, exchange_text())
        self.faulty(edited, "mismatch")

    def test_unescaped_in_transit(self):
        """A carrier turned the body's \\u2014 escape into an em dash."""
        unescaped = exchange_text().replace("\\u2014", "—", 1)
        self.assertNotEqual(unescaped, exchange_text())
        self.faulty(unescaped, "unescaped-in-transit")

    def test_unclosed(self):
        cut = exchange_text().replace("BALE EXCHANGE END", "", 1)
        self.faulty(cut, "unclosed")

    def test_no_trailer(self):
        lines = exchange_text().split("\n")
        trailer = [i for i, ln in enumerate(lines) if ln.startswith("# sha256 ")]
        self.assertEqual(len(trailer), 1)
        del lines[trailer[0]]
        self.faulty("\n".join(lines), "no-trailer")

    def test_a_sid_that_could_read_as_a_flag_is_refused(self):
        """The trailer hashes the body, not the sentinel, so a block can be
        intact and still name a sid bale would read as a flag."""
        block = exchange_text().replace(f"BALE EXCHANGE BEGIN {EXCHANGE_SID}",
                                        "BALE EXCHANGE BEGIN --no-interact", 1)
        runner = BaleDouble()
        run, obj = self.exchange(str(self.exchange_turn(block)), runner=runner)
        self.assertTrue(obj["integrity"]["ok"])
        self.assert_refused(run, obj, runner, "not safe to pass to bale")
        with self.assertRaises(ValueError):
            bale.relay_argv(Path("/b/bin/bale"), "--no-interact")

    def test_every_reason_is_named_at_once(self):
        """An edited block and an unusable --cwd: both refusals, one call."""
        edited = exchange_text().replace('"round": 1', '"round": 2', 1)
        runner = BaleDouble()
        run, obj = self.exchange(str(self.exchange_turn(edited)), "--cwd",
                                 str(self.dir / "nope"), runner=runner)
        self.assertEqual(len(obj["refusals"]), 2, obj["refusals"])
        self.assertEqual(runner.calls, [])


# ---------------------------------------------------------------------------
# 3. carry exchange: the relay call
# ---------------------------------------------------------------------------


class ExchangeRelays(TempCase):

    def test_bale_relay_sid_dash_with_exactly_the_blocks_lines_on_stdin(self):
        """Prose around the block, CRLF line endings and a light block
        beside it: bale receives only the block, LF, one trailing newline —
        byte-for-byte the crafter's emission."""
        noisy = turn("Before the block.", LIGHT.read_text(encoding="utf-8"),
                     exchange_text(), "After it.").replace("\n", "\r\n")
        runner = BaleDouble(stdout=EXCHANGE.read_bytes())
        run, obj = self.exchange(str(self.write(noisy)), "--cwd", str(self.dir),
                                 runner=runner)
        self.assertEqual((run.code, obj["ok"]), (0, True), obj["reason"])
        self.assertEqual(len(runner.calls), 1)
        call = runner.calls[0]
        self.assertEqual(call["argv"], [str(ROOTS.ok / "bin" / "bale"), "relay",
                                        EXCHANGE_SID, "-"])
        self.assertEqual(call["stdin"], EXCHANGE.read_bytes())
        self.assertEqual((call["cwd"], call["timeout"], call["stdout_cap"]),
                         (str(self.dir), BALE_TIMEOUT_SECONDS, BALE_STDOUT_CAP_BYTES))
        self.assertEqual(call["env"], {"TWINE_BALE_ROOT": ROOTS.ok.as_posix()})
        self.assertEqual(obj["argv"], call["argv"])
        self.assertGreater(obj["input"]["crlf_normalized"], 0)

    def test_cwd_defaults_to_the_current_directory(self):
        runner = BaleDouble(stdout=EXCHANGE.read_bytes())
        _, obj = self.exchange(str(self.exchange_turn()), runner=runner)
        self.assertEqual((obj["cwd"], runner.calls[0]["cwd"]),
                         (str(Path.cwd()), str(Path.cwd())))

    def test_stdin_dash_reads_the_turn_from_stdin(self):
        runner = BaleDouble(stdout=EXCHANGE.read_bytes())
        _, obj = self.exchange("-", runner=runner,
                               stdin=self.exchange_turn().read_bytes())
        self.assertEqual((obj["ok"], obj["input"]["source"]), (True, "<stdin>"))
        self.assertEqual(runner.calls[0]["stdin"], EXCHANGE.read_bytes())

    def test_ok_json_carries_bales_stdout_and_stderr(self):
        runner = BaleDouble(stdout=EXCHANGE.read_bytes(),
                            stderr=b"[bale] double: round 2 recorded\n")
        run, obj = self.exchange(str(self.exchange_turn()), runner=runner)
        self.assertEqual((obj["ok"], obj["exit_code"], obj["reason"], obj["refusals"]),
                         (True, 0, None, []))
        self.assertEqual(obj["stdout"], exchange_text())
        self.assertEqual(obj["stderr"], "[bale] double: round 2 recorded\n")
        self.assertIn("[bale] double: round 2 recorded", run.stderr)

    def test_human_stdout_is_exactly_bales_stdout(self):
        runner = BaleDouble(stdout=EXCHANGE.read_bytes(), stderr=b"[bale] note\n")
        run = run_verb("exchange", str(self.exchange_turn()), runner=runner)
        self.assertEqual((run.code, run.stdout), (0, exchange_text()))
        self.assertIn("[bale] note", run.stderr)

    def test_bale_exiting_non_zero_is_not_ok_naming_the_status(self):
        runner = BaleDouble(exit_code=2, stdout=b"",
                            stderr=b"[bale] double: no open session\n")
        run, obj = self.exchange(str(self.exchange_turn()), runner=runner)
        self.assertEqual((run.code, obj["ok"], obj["ran"], obj["exit_code"]),
                         (1, False, True, 2))
        self.assertIn("bale exited 2", obj["reason"])
        self.assertEqual(obj["refusals"], [])
        self.assertEqual(obj["stderr"], "[bale] double: no open session\n")
        self.assertIn("no open session", run.stderr)

    def test_human_mode_not_ok_is_one_line_and_never_bales_stdout(self):
        runner = BaleDouble(exit_code=1, stdout=EXCHANGE.read_bytes(),
                            stderr=b"[bale] double: refused\n")
        run = run_verb("exchange", str(self.exchange_turn()), runner=runner)
        self.assertEqual(run.code, 1)
        self.assertEqual(len(run.stdout.splitlines()), 1)
        self.assertIn("NOT OK", run.stdout)
        self.assertIn("bale exited 1", run.stdout)
        self.assertIn("[bale] double: refused", run.stderr)
        self.assertNotIn("Traceback", run.stderr)

    def test_a_bale_that_times_out_is_not_ok(self):
        runner = BaleDouble(exit_code=None, timed_out=True)
        _, obj = self.exchange(str(self.exchange_turn()), runner=runner)
        self.assertEqual((obj["ok"], obj["ran"], obj["timed_out"], obj["exit_code"]),
                         (False, True, True, None))
        self.assertIn("did not finish", obj["reason"])

    def test_the_fixture_player_has_no_relay_recording(self):
        """Through the fixture player, relay finds no recorded output
        (relay_sid_stdin.txt is not recorded): the player refuses — which is
        why every relay test uses a double or the stub."""
        player = FixturePlayer(REPO_ROOT)
        with self.assertRaises(AssertionError) as caught:
            player([str(ROOTS.ok / "bin" / "bale"), "relay", EXCHANGE_SID, "-"],
                   cwd=REPO_ROOT)
        self.assertIn("relay_sid_stdin.txt", str(caught.exception))


# ---------------------------------------------------------------------------
# 4. carry response: the tarball and the dry run
# ---------------------------------------------------------------------------


class ResponseDryRuns(TempCase):

    def test_the_recorded_dry_run_is_ok_and_hands_back_the_apply_line(self):
        tarball = self.tarball()
        player = RecordingPlayer(REPO_ROOT, assumed_exits=ASSUMED_DRY_RUN_EXIT)
        run, obj = self.response(str(tarball), "--cwd", str(REPO_ROOT), runner=player)
        self.assertEqual((run.code, obj["ok"], obj["ran"], obj["exit_code"]),
                         (0, True, True, 0))
        self.assertTrue(RESPONSE_FIXED <= set(obj), RESPONSE_FIXED - set(obj))
        self.assertEqual(player.calls, [[str(ROOTS.ok / "bin" / "bale"), "apply",
                                         "--dry-run", "--json", str(tarball)]])
        self.assertEqual(player.kwargs[0]["stdin"], None)
        recorded = json.loads(DRY_RUN.read_bytes())
        self.assertEqual((obj["dry_run"], obj["outcome"]), (recorded, "dry-run"))
        self.assertEqual((obj["tarball"], obj["apply_line"]),
                         (str(tarball), f"bale apply {tarball}"))
        self.assertEqual((obj["reason"], obj["refusals"]), (None, []))

    def test_human_stdout_is_exactly_the_apply_line(self):
        tarball = self.tarball()
        player = FixturePlayer(REPO_ROOT, assumed_exits=ASSUMED_DRY_RUN_EXIT)
        run = run_verb("response", str(tarball), "--cwd", str(REPO_ROOT), runner=player)
        self.assertEqual((run.code, run.stdout), (0, f"bale apply {tarball}\n"))
        self.assertIn("nothing was applied", run.stderr)

    def test_a_relative_name_is_made_absolute_against_the_current_directory(self):
        tarball = self.tarball()
        rel = os.path.relpath(tarball, Path.cwd())
        runner = BaleDouble(stdout=DRY_RUN.read_bytes())
        _, obj = self.response(rel, runner=runner)
        self.assertEqual((obj["ok"], obj["tarball"]), (True, str(tarball)))
        self.assertEqual(runner.calls[0]["argv"][-1], str(tarball))

    def test_the_apply_line_quotes_only_when_the_shell_needs_it(self):
        for name in ("response-2026-10-03-x-001.tar.gz", "with space.tar.gz",
                     "it's.tar.gz", "$HOME.tar.gz"):
            with self.subTest(name=name):
                tarball = self.tarball(name)
                _, obj = self.response(str(tarball),
                                       runner=BaleDouble(stdout=DRY_RUN.read_bytes()))
                self.assertEqual(obj["apply_line"],
                                 "bale apply " + shlex.quote(str(tarball)))
                self.assertEqual(shlex.split(obj["apply_line"]),
                                 ["bale", "apply", str(tarball)])
                if " " not in name and "'" not in name and "$" not in name:
                    self.assertEqual(obj["apply_line"], f"bale apply {tarball}")

    def test_a_missing_tarball_is_refused_before_bale(self):
        runner = BaleDouble(stdout=DRY_RUN.read_bytes())
        run, obj = self.response(str(self.dir / "nope.tar.gz"), runner=runner)
        self.assertEqual((run.code, obj["ok"], obj["ran"], obj["tarball"],
                          obj["apply_line"]), (1, False, False, None, None))
        self.assertIn("no such file", obj["reason"])
        self.assertIn("does not search", obj["reason"])
        self.assertEqual(runner.calls, [])

    def test_a_directory_is_not_a_tarball(self):
        runner = BaleDouble(stdout=DRY_RUN.read_bytes())
        _, obj = self.response(str(self.dir), runner=runner)
        self.assertEqual((obj["ok"], obj["tarball"]), (False, None))
        self.assertIn("not a file", obj["reason"])
        self.assertEqual(runner.calls, [])

    def not_ok(self, runner: BaleDouble, *needles: str) -> dict:
        run, obj = self.response(str(self.tarball()), runner=runner)
        self.assertEqual((run.code, obj["ok"], obj["ran"], obj["apply_line"]),
                         (1, False, True, None))
        for needle in needles:
            self.assertIn(needle, obj["reason"])
        human = run_verb("response", str(self.tarball()), runner=runner)
        self.assertEqual(human.code, 1)
        self.assertEqual(len(human.stdout.splitlines()), 1)
        self.assertTrue(human.stdout.startswith("carry response "), human.stdout)
        self.assertNotIn("bale apply /", human.stdout)
        return obj

    def test_an_outcome_other_than_dry_run_is_named(self):
        """A double: exit 0, one JSON object, outcome "refused"."""
        obj = self.not_ok(BaleDouble(stdout=b'{"outcome": "refused", "sid": null}\n'),
                          "outcome 'refused'", "not 'dry-run'")
        self.assertEqual((obj["outcome"], obj["exit_code"]), ("refused", 0))
        self.assertEqual(obj["dry_run"], {"outcome": "refused", "sid": None})

    def test_a_non_zero_exit_is_named_with_the_outcome(self):
        """A double: exit 1, outcome "hold", stderr surfaced."""
        obj = self.not_ok(BaleDouble(exit_code=1, stdout=b'{"outcome": "hold"}\n',
                                     stderr=b"[bale] double: held\n"),
                          "bale exited 1", "outcome 'hold'")
        self.assertEqual((obj["exit_code"], obj["outcome"], obj["stderr"]),
                         (1, "hold", "[bale] double: held\n"))

    def test_a_non_zero_exit_with_the_dry_run_outcome_is_not_ok(self):
        obj = self.not_ok(BaleDouble(exit_code=3, stdout=DRY_RUN.read_bytes()),
                          "bale exited 3")
        self.assertEqual(obj["outcome"], "dry-run")

    def test_stdout_that_is_not_one_json_object(self):
        for stdout in (b"[bale] usage: something\n", b"",
                       DRY_RUN.read_bytes() + DRY_RUN.read_bytes(), b"[1, 2]\n"):
            with self.subTest(stdout=stdout[:30]):
                obj = self.not_ok(BaleDouble(stdout=stdout), "not one JSON object")
                self.assertEqual((obj["dry_run"], obj["outcome"]), (None, None))

    def test_a_dry_run_that_times_out(self):
        obj = self.not_ok(BaleDouble(exit_code=None, timed_out=True),
                          "did not finish")
        self.assertTrue(obj["timed_out"])


# ---------------------------------------------------------------------------
# 5. carry response: never a merge (T12)
# ---------------------------------------------------------------------------


class ResponseNeverMerges(TempCase):

    def test_whatever_the_name_the_argv_is_the_dry_run_and_nothing_else(self):
        """Files named like flags, or with spaces: each reaches bale as one
        absolute path after exactly `apply --dry-run --json`, and nothing
        else is in the argv."""
        for name in ("--no-interact", "-y", "x --admit y.tar.gz", "plain.tgz"):
            with self.subTest(name=name):
                path = self.tarball(name)
                runner = BaleDouble(stdout=DRY_RUN.read_bytes())
                run = run_verb("response", str(path), "--json", runner=runner)
                self.assertEqual(run.code, 0, run.stdout)
                self.assertEqual(len(runner.calls), 1)
                argv = runner.calls[0]["argv"]
                self.assertEqual(argv[1:], ["apply", "--dry-run", "--json", str(path)])
                self.assertTrue(os.path.isabs(argv[4]))

    def test_the_dry_run_flags_are_fixed(self):
        self.assertEqual(bale.DRY_RUN_FLAGS, ("--dry-run", "--json"))
        self.assertEqual(bale.dry_run_argv(Path("/r/bin/bale"), "/t/r.tar.gz"),
                         ["/r/bin/bale", "apply", "--dry-run", "--json", "/t/r.tar.gz"])
        with self.assertRaises(ValueError):
            bale.dry_run_argv(Path("/r/bin/bale"), "relative.tar.gz")

    def test_apply_is_built_in_one_place_only(self):
        """The string "apply" as an argv token appears in twine's code only
        inside twine.bale.dry_run_argv, which always adds --dry-run; no
        admission or override flag appears anywhere in twine's code."""
        def apply_tokens(node: ast.AST) -> int:
            return sum(1 for n in ast.walk(node)
                       if isinstance(n, ast.Constant) and n.value == "apply")

        found = {}
        for path in sorted((REPO_ROOT / "twine").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            rel = path.relative_to(REPO_ROOT).as_posix()
            if apply_tokens(tree):
                found[rel] = apply_tokens(tree)
            if rel == "twine/bale.py":
                builder = [f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
                           and f.name == "dry_run_argv"]
                self.assertEqual(len(builder), 1)
                self.assertEqual(apply_tokens(builder[0]), apply_tokens(tree),
                                 "\"apply\" built outside dry_run_argv")
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    for flag in ("--no-interact", "--admit", "--override", "--force",
                                 "--yes", "--no-dry-run"):
                        self.assertNotIn(flag, node.value.split(),
                                         f"{path.name} carries {flag}")
        self.assertEqual(found, {"twine/bale.py": 1}, found)


    def test_carry_bale_imports_nothing_that_runs_or_reaches_out(self):
        """bale is run through ctx.run only (cli-contract.md §10.6)."""
        forbidden = {"subprocess", "os", "shutil", "socket", "urllib", "http",
                     "multiprocessing", "pty", "asyncio", "ctypes"}
        tree = ast.parse((REPO_ROOT / "twine/commands/carry_bale.py")
                         .read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        self.assertFalse(roots & forbidden, roots & forbidden)


# ---------------------------------------------------------------------------
# 6. End to end, as a subprocess, against a stub bale
# ---------------------------------------------------------------------------


class EndToEnd(TempCase):

    def setUp(self):
        super().setUp()
        self.stub = StubBale(relay_stdout=EXCHANGE, apply_stdout=DRY_RUN,
                             stderr="[bale] stub: not bale\n")
        self.addCleanup(self.stub.cleanup)

    def test_carry_exchange_through_the_real_seam(self):
        path = self.exchange_turn()
        run = run_cli("carry", "exchange", str(path), "--cwd", str(self.dir), "--json",
                      bale_root=self.stub.root)
        obj = one_line(self, run.stdout, "carry exchange")
        self.assertEqual((run.code, obj["ok"], obj["exit_code"]), (0, True, 0),
                         obj["reason"])
        self.assertEqual(self.stub.argv(), ["relay", EXCHANGE_SID, "-"])
        self.assertEqual(self.stub.stdin(), EXCHANGE.read_bytes())
        self.assertEqual(self.stub.cwd(), str(self.dir))
        self.assertEqual(obj["stdout"], exchange_text())
        self.assertEqual(obj["bale"]["executable"], str(self.stub.executable))
        self.assertEqual((obj["bale"]["installed"], obj["bale"]["pin_matches"]),
                         (PIN, True))
        self.assertIn("[bale] stub: not bale", run.stderr)

    def test_carry_exchange_human_stdout_is_the_relayed_block(self):
        run = run_cli("carry", "exchange", str(self.exchange_turn()),
                      bale_root=self.stub.root)
        self.assertEqual((run.code, run.stdout), (0, exchange_text()))

    def test_carry_response_through_the_real_seam(self):
        tarball = self.tarball()
        run = run_cli("carry", "response", str(tarball), "--json",
                      bale_root=self.stub.root)
        obj = one_line(self, run.stdout, "carry response")
        self.assertEqual((run.code, obj["ok"], obj["apply_line"]),
                         (0, True, f"bale apply {tarball}"), obj["reason"])
        self.assertEqual(self.stub.argv(), ["apply", "--dry-run", "--json", str(tarball)])
        self.assertIsNone(self.stub.stdin())
        self.assertEqual(self.stub.cwd(), str(REPO_ROOT))
        human = run_cli("carry", "response", str(tarball), bale_root=self.stub.root)
        self.assertEqual((human.code, human.stdout), (0, f"bale apply {tarball}\n"))

    def test_a_stub_exiting_non_zero(self):
        failing = StubBale(apply_stdout=DRY_RUN, exit_code=4, stderr="[bale] stub: no\n")
        self.addCleanup(failing.cleanup)
        run = run_cli("carry", "response", str(self.tarball()), "--json",
                      bale_root=failing.root)
        obj = one_line(self, run.stdout, "carry response")
        self.assertEqual((run.code, obj["ok"], obj["exit_code"], obj["apply_line"]),
                         (1, False, 4, None))
        self.assertIn("bale exited 4", obj["reason"])
        self.assertEqual(obj["stderr"], "[bale] stub: no\n")
        self.assertNotIn("Traceback", run.stderr)

    def test_a_version_other_than_the_pin_is_said_not_gated(self):
        (self.stub.root / "bin" / "VERSION").write_text("0.4.46\n", encoding="utf-8")
        run = run_cli("carry", "response", str(self.tarball()), "--json",
                      bale_root=self.stub.root)
        obj = one_line(self, run.stdout, "carry response")
        self.assertEqual((obj["ok"], obj["bale"]["pin_matches"]), (True, False))
        self.assertIn("0.4.46", run.stderr)


# ---------------------------------------------------------------------------
# 7. Finding bale: the tests never reach a real one
# ---------------------------------------------------------------------------


class FindingBale(TempCase):

    def test_a_bale_on_path_is_never_run_by_the_cli_tests(self):
        """A `bale` on PATH that would leave a marker: run_cli pins
        TWINE_BALE_ROOT to a missing directory, so the verbs refuse
        (bale could not be started) and the PATH bale never runs."""
        bindir = self.dir / "bin"
        bindir.mkdir()
        marker = self.dir / "reached"
        fake = bindir / "bale"
        fake.write_text(f"#!{shutil.which('bash') or '/bin/bash'}\n"
                        f"touch {shlex.quote(str(marker))}\n", encoding="utf-8")
        fake.chmod(0o755)
        env = {"PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"}
        for argv in (["carry", "exchange", str(self.exchange_turn())],
                     ["carry", "response", str(self.tarball())]):
            with self.subTest(verb=argv[1]):
                run = run_cli(*argv, "--json", extra_env=env)
                obj = one_line(self, run.stdout, " ".join(argv[:2]))
                self.assertEqual((obj["ok"], obj["ran"]), (False, False))
                self.assertIn("could not be started", obj["reason"])
                self.assertEqual(obj["bale"]["source"], "TWINE_BALE_ROOT")
        self.assertFalse(marker.exists(), "a test reached the bale on PATH")

    def test_no_bale_anywhere_is_a_refusal(self):
        for verb, arg in (("exchange", str(self.exchange_turn())),
                          ("response", str(self.tarball()))):
            with self.subTest(verb=verb):
                runner = BaleDouble()
                run = run_verb(verb, arg, "--json", runner=runner, env={})
                obj = one_line(self, run.stdout, f"carry {verb}")
                self.assertEqual((run.code, obj["ok"], obj["ran"]), (1, False, False))
                self.assertIn("no bale install found", obj["reason"])
                self.assertIsNone(obj["bale"]["executable"])
                self.assertEqual(runner.calls, [])

    def test_bale_root_flag_wins_over_the_environment(self):
        runner = BaleDouble(stdout=DRY_RUN.read_bytes())
        _, obj = self.response(str(self.tarball()), "--bale-root", str(ROOTS.other),
                               runner=runner)
        self.assertEqual(runner.calls[0]["argv"][0], str(ROOTS.other / "bin" / "bale"))
        self.assertEqual((obj["bale"]["source"], obj["bale"]["installed"],
                          obj["bale"]["pin_matches"]),
                         ("--bale-root", ROOTS.other_version, False))

    def test_path_is_followed_to_the_install_root(self):
        """With no flag and no TWINE_BALE_ROOT, `bale` on PATH is followed
        to its real path and up to the root, as `bale check` does; the
        executable run is `<root>/bin/bale`. (`which` is injected: no real
        PATH is consulted.)"""
        runner = BaleDouble(stdout=DRY_RUN.read_bytes())
        out, err = io.StringIO(), io.StringIO()
        exe = ROOTS.ok / "bin" / "bale"
        ctx = Context(env={}, stdout=out, stderr=err, which=lambda name: str(exe),
                      stdin=io.BytesIO(b""), run=runner)
        code = main(["carry", "response", str(self.tarball()), "--json"], ctx=ctx)
        obj = one_line(self, out.getvalue(), "carry response")
        self.assertEqual((code, obj["bale"]["source"]), (0, "PATH"))
        self.assertEqual(runner.calls[0]["argv"][0], str(exe.resolve()))


if __name__ == "__main__":
    unittest.main()

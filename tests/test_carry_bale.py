"""`twine carry exchange` and `twine carry response` (Arc 1 session
2b-ii): the bale hand-offs. No test here reaches a bale (T8): bale is
the fixture player (tests.helpers.FixturePlayer, answering from
fixtures/), a run-seam double (RecordedRelay, tests/helpers.py, replaying
a recording; BaleDouble, below), or a stub executable
(tests.helpers.StubBale) — and a bale on PATH is shown never to be the
one run.

What is recorded, and what stands in for what is not:

  - `bale apply --dry-run --json` on a clean response: recorded at bale
    0.4.49 in a throwaway repository, with its exit (fixtures/bale-0.4.49/
    scratch/apply_--dry-run_--json_tarball+dry-run.json, exit 0) — the
    0.4.45 carried line, exit unrecorded, is history; the player answers
    the argv only when a test selects the `dry-run` group (SELECT_DRY_RUN),
    since the scope-drift refusal is recorded under the same argv
    (…+scope-drift-refused.json, exit 1), and replayed in section 4.
  - `bale relay <sid> - --json`, the one relay argv twine builds since
    session 2026-10-08-twine-carry-exchange-json-001: four `relay … --json`
    lines are recorded at 0.4.49 in the scratch repository — relayed,
    re-emitted, and the ingest and session-gate refusals — made with a
    file argument and replayed for twine's `-` by RecordedRelay on the
    assumption its docstring names (bale's `_read_relay_input` reads stdin
    for `-` exactly as it reads the file). The relayed line's own `block`
    is what the tests carry, so each recording answers for its own sid.
    The flagless `bale relay <sid> -` is retired, and with it its
    stand-in (the crafter's --emit-block emission, which stays the
    `exchange` format's fixture and still feeds the vouching tests here,
    where nothing reaches bale).
  - what no recording covers — a timeout, a capped stdout, a non-JSON
    stdout, an exit-1 empty stdout, an edited relay line, a returned
    `block` twine cannot vouch for (section 3's ExchangeVouchesForBalesBlock,
    since session 2026-10-08-twine-exchange-vouch-005: the recorded block
    is intact); the other two
    dry-run `*-refused` outcomes, every HOLD, non-zero exit or timeout of
    the dry run: doubles, each built in this file (RecordedRelay's
    `stdout=`/`exit_code=`/`timed_out=`/`capped=`, BaleDouble) and named
    a double.

Since Arc 1 session 4 the doubles speak bale's spellings: a refusal under
--dry-run is one of the three `*-refused` outcomes with exit 1, as bale's
format_apply_json documents (one of them recorded since the pin at
0.4.49); a bale error prints nothing on stdout and exits non-zero. The one
outcome no bale emits, used to prove twine names an outcome it does not
know, is spelled NOT_A_BALE_OUTCOME (tests/helpers.py) so no reader takes
it for bale's. And the carry verbs drive only the pinned bale (D2):
section 8.

Sections:
  1. Helpers and doubles
  2. carry exchange: choosing and vouching for the block
  3. carry exchange: the relay call
  4. carry response: the tarball and the dry run
  5. carry response: never a merge (T12)
  6. End to end, as a subprocess, against a stub bale
  7. Finding bale: the tests never reach a real one
  8. The pin gates (D2, decided by Arc 1 session 4)
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import shlex
import shutil
import tempfile
import unittest
from pathlib import Path

from twine import REPO_ROOT, bale, shapes
from twine.cli import Context, main
from twine.commands.carry_bale import (BALE_STDOUT_CAP_BYTES, BALE_TIMEOUT_SECONDS,
                                       VOUCH_FAILURE, ExchangeOutcome,
                                       vouch_for_relayed_block)
from twine.process import RunResult

from tests.helpers import (BALE_VOCABULARIES, NOT_A_BALE_OUTCOME, PIN, RELAY_FILE_KEY,
                           RELAY_KEYS, RELAY_RECORDED_ABSENT_SID, RELAY_RECORDED_SID,
                           FixturePlayer, RecordedRelay, RecordingRunner, Run, StubBale,
                           TempRoots, block_for_sid, carried_relpath, emission_relpath,
                           fixture_relpath, relay_recording, relayed_block, run_cli, turn)

# ---------------------------------------------------------------------------
# 1. Helpers and doubles
# ---------------------------------------------------------------------------

# The crafter's exchange emission (the `exchange` format's fixture): an
# intact block whose body carries a — escape, which the vouching tests
# edit. Since session 2026-10-08-twine-carry-exchange-json-001 it no longer
# stands in for relay's stdout; the tests that relay carry relayed_block().
EXCHANGE = REPO_ROOT / emission_relpath("crafter", ["--emit-block", "-"])
EXCHANGE_SID = "2026-10-02-twine-take-read-001"
# The relayed recording (bale 0.4.49, scratch repository, exit 0): the line
# RecordedRelay answers by default, and its own block, carried as input.
RELAYED = relay_recording("relayed")
LIGHT = REPO_ROOT / emission_relpath("crafter", ["--light-block", "-"])
RELAY_TO_PLANNER = REPO_ROOT / carried_relpath(
    "relay", "2026-10-01-twine-seed-effort-003", "planner")
DRY_RUN_ARGV = ["apply", "--dry-run", "--json", "/x.tar.gz"]
DRY_RUN_KEY = "apply_--dry-run_--json_tarball"
# The 0.4.49 dry run (recorded in the scratch repository, exit 0 in its
# row — no assumed exit remains) and the scope-drift refusal recorded under
# the same argv (exit 1); the player replays whichever a test selects.
DRY_RUN = REPO_ROOT / fixture_relpath(DRY_RUN_ARGV, "scratch", "dry-run")
DRIFT_REFUSED = REPO_ROOT / fixture_relpath(DRY_RUN_ARGV, "scratch", "scope-drift-refused")
SELECT_DRY_RUN = {DRY_RUN_KEY: "dry-run"}
SELECT_DRIFT_REFUSED = {DRY_RUN_KEY: "scope-drift-refused"}

EXCHANGE_FIXED = {"sid", "block", "ran", "exit_code", "stdout", "stderr",
                  "reason", "refusals", "relay", "outcome"}
# Bytes a test feeds as bale's stderr: not bale's, and spelled so.
NOT_BALES_STDERR = b"[twine test] not bale's stderr\n"
RESPONSE_FIXED = {"tarball", "ran", "exit_code", "dry_run", "outcome", "apply_line",
                  "stderr", "reason", "refusals"}
# What `bale apply --dry-run --json` may answer besides "dry-run", per bale
# 0.4.49's format_apply_json (unchanged since 0.4.45): a refusal, exit 1,
# stdout the one line — "Emitted under --dry-run too when the plan would
# refuse." The scope-drift one is recorded; the other two are doubles.
DRY_RUN_REFUSALS = [o for o in BALE_VOCABULARIES["apply-outcome"] if o.endswith("-refused")]
DRY_RUN_REFUSAL_EXIT = 1
RECORDED_REFUSAL = "scope-drift-refused"


class BaleDouble(RecordingRunner):
    """A double, not a recording: answers every call with a RunResult
    this file builds, standing in for a bale output nobody has recorded
    (a dry-run refusal, a HOLD, a non-zero exit, a timeout). Records each
    call. Since session 2026-10-08-twine-carry-exchange-json-001 it answers
    `carry response` only: `carry exchange` is answered by RecordedRelay."""

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
        """A pasted turn carrying `block` — by default the relayed
        recording's own block, so the default RecordedRelay answers for
        the sid it names."""
        return self.write(turn("Carry this to the planner:", "",
                               block or relayed_block(), "Thanks."), name)

    def exchange(self, *argv: str, runner=None, **kw) -> tuple[Run, dict]:
        runner = runner if runner is not None else RecordedRelay()
        run = run_verb("exchange", *argv, "--json", runner=runner, **kw)
        self.assertNotIn("Traceback", run.stderr)
        return run, one_line(self, run.stdout, "carry exchange")

    def exchange_human(self, *argv: str, runner) -> Run:
        """`carry exchange` without --json; never a traceback."""
        run = run_verb("exchange", *argv, runner=runner)
        self.assertNotIn("Traceback", run.stderr)
        return run

    def assert_relay_not_ok(self, runner, *needles: str, block: str | None = None,
                            exit_code: int = 1) -> dict:
        """Relayed, not ok: exit 1, bale ran once, every needle in the
        reason, no refusal; then the same call in human mode is one line —
        `NOT OK`, the reason — and never the block bale handed back."""
        path = self.exchange_turn(block)
        run, obj = self.exchange(str(path), runner=runner)
        self.assertEqual((run.code, obj["ok"], obj["ran"], obj["refusals"]),
                         (exit_code, False, True, []))
        self.assertEqual(len(runner.calls), 1)
        for needle in needles:
            self.assertIn(needle, obj["reason"])
        self.assertTrue(EXCHANGE_FIXED <= set(obj), EXCHANGE_FIXED - set(obj))
        human = self.exchange_human(str(path), runner=runner)
        self.assertEqual(human.code, 1)
        self.assertEqual(len(human.stdout.splitlines()), 1, human.stdout)
        self.assertTrue(human.stdout.startswith(f"carry exchange {path}: NOT OK — "),
                        human.stdout)
        self.assertNotIn("# sha256 ", human.stdout, "a block's trailer on stdout")
        self.assertNotIn("BALE EXCHANGE END", human.stdout)
        return obj

    def player(self, select: dict | None = None) -> "RecordingPlayer":
        """The fixture player with this test's directory as the scratch
        repository (where the 0.4.49 apply recordings were made) and the
        dry-run group selected unless the test selects another."""
        return RecordingPlayer(REPO_ROOT, scratch_root=self.dir,
                               select=SELECT_DRY_RUN if select is None else select)

    def response(self, *argv: str, runner=None, **kw) -> tuple[Run, dict]:
        runner = runner if runner is not None else self.player()
        if runner.__class__.__name__ == "RecordingPlayer" and "--cwd" not in argv:
            argv = (*argv, "--cwd", str(self.dir))
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
    """The crafter's exchange emission as text (the vouching tests' block)."""
    return EXCHANGE.read_text(encoding="utf-8")


def relay_line_double(**changes) -> bytes:
    """NOT bale's: the relayed recording's line with `changes` applied,
    re-serialized as one line — an edited line, to prove what twine
    refuses. Keys keep the recording's order; a new key goes last."""
    line = dict(RELAYED.line)
    line.update(changes)
    return (json.dumps(line) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# 2. carry exchange: choosing and vouching for the block
# ---------------------------------------------------------------------------


class ExchangeChoosesTheBlock(TempCase):

    def test_one_exchange_block_is_chosen_and_its_sid_reported(self):
        """The relayed recording's own block, alone in a turn: chosen as
        [1], its sid reported, and the recorded `relayed` line for that
        sid makes it ok — every fixed name present, `relay` the line and
        `outcome` its outcome."""
        runner = RecordedRelay()
        run, obj = self.exchange(str(self.exchange_turn()), runner=runner)
        self.assertEqual((run.code, obj["ok"], obj["sid"], obj["block"]),
                         (0, True, RELAY_RECORDED_SID, 1), obj["reason"])
        self.assertTrue(EXCHANGE_FIXED <= set(obj), EXCHANGE_FIXED - set(obj))
        self.assertEqual((obj["relay"], obj["outcome"]), (RELAYED.line, "relayed"))

    def test_prose_has_no_exchange_block_refused(self):
        runner = RecordedRelay()
        run, obj = self.exchange(str(self.write("Nothing to carry.\n")), runner=runner)
        self.assert_refused(run, obj, runner, "no exchange block")
        self.assertIsNone(obj["sid"])

    def test_two_exchange_blocks_without_block_refused_naming_both(self):
        runner = RecordedRelay()
        path = self.write(turn(exchange_text(), "and again", exchange_text()))
        run, obj = self.exchange(str(path), runner=runner)
        self.assert_refused(run, obj, runner, "2 exchange blocks", "[1]", "[2]",
                            "--block")

    def test_block_number_picks_by_takes_numbering(self):
        """A light block, then two exchange blocks — the crafter's, then
        the relayed recording's own: take numbers the second exchange [3];
        --block 3 relays exactly that block's lines, and the recording
        answers for the sid it names."""
        second = relayed_block()
        path = self.write(turn(LIGHT.read_text(encoding="utf-8"), exchange_text(), second))
        take = json.loads(run_cli("take", str(path), "--json").stdout)
        self.assertEqual([b["kind"] for b in take["blocks"]],
                         ["light", "exchange", "exchange"])
        runner = RecordedRelay()
        run, obj = self.exchange(str(path), "--block", "3", runner=runner)
        self.assertEqual((obj["ok"], obj["block"], obj["sid"]),
                         (True, 3, RELAY_RECORDED_SID), obj["reason"])
        self.assertEqual(runner.calls[0]["stdin"], second.encode("utf-8"))
        self.assertEqual(runner.calls[0]["argv"][2], RELAY_RECORDED_SID)

    def test_block_naming_another_kind_refused(self):
        runner = RecordedRelay()
        path = self.write(turn(LIGHT.read_text(encoding="utf-8"), exchange_text()))
        run, obj = self.exchange(str(path), "--block", "1", runner=runner)
        self.assert_refused(run, obj, runner, "light block", "not an exchange")

    def test_a_relay_block_to_the_planner_is_never_carried(self):
        """cli-contract.md §9.4 (T14): carry exchange carries exchange
        blocks only, so a `to: planner` relay block cannot be pointed at."""
        runner = RecordedRelay()
        path = self.write(turn(RELAY_TO_PLANNER.read_text(encoding="utf-8"),
                               exchange_text()))
        run, obj = self.exchange(str(path), "--block", "1", runner=runner)
        self.assert_refused(run, obj, runner, "relay block", "not an exchange")
        run, obj = self.exchange(str(self.write(
            RELAY_TO_PLANNER.read_bytes(), "relay.txt")), runner=runner)
        self.assert_refused(run, obj, runner, "no exchange block", "relay")

    def test_block_out_of_range_refused(self):
        runner = RecordedRelay()
        for n in ("0", "2", "-1"):
            with self.subTest(block=n):
                run, obj = self.exchange(str(self.exchange_turn()), "--block", n,
                                         runner=runner)
                self.assert_refused(run, obj, runner, "names no block")

    def test_unreadable_and_non_utf8_input_refused(self):
        runner = RecordedRelay()
        run, obj = self.exchange(str(self.dir / "missing.txt"), runner=runner)
        self.assert_refused(run, obj, runner, "cannot read")
        run, obj = self.exchange(str(self.write(b"\xff\xfe junk\n", "bad.txt")),
                                 runner=runner)
        self.assert_refused(run, obj, runner, "not UTF-8")


class ExchangeVouchesForTheBlock(TempCase):
    """Every integrity fault refuses before bale, naming the fault; the
    block is never repaired."""

    def faulty(self, block: str, fault: str) -> None:
        runner = RecordedRelay()
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
        runner = RecordedRelay()
        run, obj = self.exchange(str(self.exchange_turn(block)), runner=runner)
        self.assertTrue(obj["integrity"]["ok"])
        self.assert_refused(run, obj, runner, "not safe to pass to bale")
        with self.assertRaises(ValueError):
            bale.relay_argv(Path("/b/bin/bale"), "--no-interact")

    def test_every_reason_is_named_at_once(self):
        """An edited block and an unusable --cwd: both refusals, one call."""
        edited = exchange_text().replace('"round": 1', '"round": 2', 1)
        runner = RecordedRelay()
        run, obj = self.exchange(str(self.exchange_turn(edited)), "--cwd",
                                 str(self.dir / "nope"), runner=runner)
        self.assertEqual(len(obj["refusals"]), 2, obj["refusals"])
        self.assertEqual(runner.calls, [])


# ---------------------------------------------------------------------------
# 3. carry exchange: the relay call
# ---------------------------------------------------------------------------


class ExchangeRelays(TempCase):
    """The call, ok, and every way a relay line is not ok — against the
    four `relay --json` recordings (RecordedRelay, replayed for twine's
    argv on the assumption its docstring names) and, where no recording
    covers a case, doubles named as such."""

    def test_bale_relay_sid_dash_with_exactly_the_blocks_lines_on_stdin(self):
        """Prose around the block, CRLF line endings and a light block
        beside it: bale is called once, as `relay <sid> - --json`, and
        receives only the block — LF, one trailing newline — byte for byte
        the relayed recording's own block."""
        noisy = turn("Before the block.", LIGHT.read_text(encoding="utf-8"),
                     relayed_block(), "After it.").replace("\n", "\r\n")
        runner = RecordedRelay()
        run, obj = self.exchange(str(self.write(noisy)), "--cwd", str(self.dir),
                                 runner=runner)
        self.assertEqual((run.code, obj["ok"]), (0, True), obj["reason"])
        self.assertEqual(len(runner.calls), 1)
        call = runner.calls[0]
        self.assertEqual(call["argv"], [str(ROOTS.ok / "bin" / "bale"), "relay",
                                        RELAY_RECORDED_SID, "-", "--json"])
        self.assertEqual(call["stdin"], relayed_block().encode("utf-8"))
        self.assertEqual((call["cwd"], call["timeout"], call["stdout_cap"]),
                         (str(self.dir), BALE_TIMEOUT_SECONDS, BALE_STDOUT_CAP_BYTES))
        self.assertEqual(call["env"], {"TWINE_BALE_ROOT": ROOTS.ok.as_posix()})
        self.assertEqual(obj["argv"], call["argv"])
        self.assertGreater(obj["input"]["crlf_normalized"], 0)

    def test_the_relay_argv_is_fixed(self):
        """twine.bale.relay_argv builds exactly `relay <sid> - --json`."""
        self.assertEqual((bale.RELAY_INPUT, bale.RELAY_FLAGS), ("-", ("--json",)))
        self.assertEqual(bale.relay_argv(Path("/r/bin/bale"), RELAY_RECORDED_SID),
                         ["/r/bin/bale", "relay", RELAY_RECORDED_SID, "-", "--json"])

    def test_relay_is_built_in_one_place_only(self):
        """An argv carrying the token "relay" — a list or tuple display
        holding the string — is built in twine's code only inside
        twine.bale.relay_argv, which always adds `-` and `--json`; and
        relay_argv is called from carry_bale.py alone. (Elsewhere "relay"
        is the relay block kind's name and the twin's `relay` key, never an
        argv.)"""
        def relay_displays(node: ast.AST) -> list[ast.AST]:
            return [n for n in ast.walk(node) if isinstance(n, (ast.List, ast.Tuple))
                    and any(isinstance(e, ast.Constant) and e.value == "relay"
                            for e in n.elts)]

        found, callers = {}, []
        for path in sorted((REPO_ROOT / "twine").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            rel = path.relative_to(REPO_ROOT).as_posix()
            if relay_displays(tree):
                found[rel] = len(relay_displays(tree))
            if rel == "twine/bale.py":
                builder = [f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
                           and f.name == "relay_argv"]
                self.assertEqual(len(builder), 1)
                self.assertEqual(len(relay_displays(builder[0])),
                                 len(relay_displays(tree)),
                                 "a relay argv built outside relay_argv")
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "relay_argv"):
                    callers.append(rel)
        self.assertEqual(found, {"twine/bale.py": 1}, found)
        self.assertEqual(callers, ["twine/commands/carry_bale.py"])

    def test_cwd_defaults_to_the_current_directory(self):
        runner = RecordedRelay()
        _, obj = self.exchange(str(self.exchange_turn()), runner=runner)
        self.assertEqual((obj["cwd"], runner.calls[0]["cwd"]),
                         (str(Path.cwd()), str(Path.cwd())))

    def test_stdin_dash_reads_the_turn_from_stdin(self):
        runner = RecordedRelay()
        _, obj = self.exchange("-", runner=runner,
                               stdin=self.exchange_turn().read_bytes())
        self.assertEqual((obj["ok"], obj["input"]["source"]), (True, "<stdin>"),
                         obj["reason"])
        self.assertEqual(runner.calls[0]["stdin"], relayed_block().encode("utf-8"))

    def test_ok_json_carries_bales_stdout_and_stderr(self):
        """ok: the twin's `stdout` is bale's stdout as text — now the
        recorded JSON line, byte for byte — `relay` that line parsed and
        `outcome` its outcome; a stderr (bytes named as not bale's: no
        recording carries one) is reported and passed through."""
        runner = RecordedRelay(stderr=NOT_BALES_STDERR)
        run, obj = self.exchange(str(self.exchange_turn()), runner=runner)
        self.assertEqual((obj["ok"], obj["exit_code"], obj["reason"], obj["refusals"]),
                         (True, 0, None, []))
        self.assertEqual(obj["stdout"], RELAYED.stdout.decode("utf-8"))
        self.assertEqual((obj["relay"], obj["outcome"]), (RELAYED.line, "relayed"))
        self.assertEqual(tuple(obj["relay"]), RELAY_KEYS)
        self.assertEqual(obj["stderr"], NOT_BALES_STDERR.decode())
        self.assertIn(NOT_BALES_STDERR.decode().strip(), run.stderr)

    def test_human_stdout_is_exactly_the_lines_block(self):
        """ok, human mode: stdout is exactly the recorded line's `block` —
        what the flagless relay printed — never the JSON line."""
        runner = RecordedRelay(stderr=NOT_BALES_STDERR)
        run = self.exchange_human(str(self.exchange_turn()), runner=runner)
        self.assertEqual(run.code, 0, run.stdout)
        self.assertEqual(run.stdout.encode("utf-8"), RELAYED.line["block"].encode("utf-8"))
        self.assertNotIn('"outcome"', run.stdout)
        self.assertIn(NOT_BALES_STDERR.decode().strip(), run.stderr)

    def test_a_block_without_a_final_newline_gains_one(self):
        """NOT bale's: a relayed line whose block lacks its final newline
        (bale's always has one). Human stdout supplies it — nothing else
        differs."""
        block = RELAYED.line["block"]
        runner = RecordedRelay(stdout=relay_line_double(block=block.rstrip("\n")))
        run = self.exchange_human(str(self.exchange_turn()), runner=runner)
        self.assertEqual((run.code, run.stdout), (0, block))

    def test_each_recorded_refusal_is_not_ok_quoting_its_cause(self):
        """The two recorded `relay-refused` lines, exit 1: not ok, the
        reason naming the exit and quoting bale's `cause` whole, the twin's
        `relay` the line and `outcome` relay-refused. The session-gate line
        names a sid that was never open, so the carried block names it too
        (its sentinel edited; the trailer hashes the body only) — each
        recording answers for its own sid. Human mode: one line, never a
        block."""
        cases = {"ingest": None,
                 "session-gate": block_for_sid(RELAY_RECORDED_ABSENT_SID)}
        for name, block in cases.items():
            with self.subTest(recording=name):
                recording = relay_recording(name)
                self.assertEqual((recording.exit_code, recording.line["outcome"],
                                  recording.line["block"]), (1, "relay-refused", None))
                cause = recording.line["cause"]
                self.assertTrue(cause)
                obj = self.assert_relay_not_ok(
                    RecordedRelay(name), "bale exited 1", "relay-refused",
                    f'"{cause}"', block=block)
                self.assertEqual((obj["exit_code"], obj["relay"], obj["outcome"]),
                                 (1, recording.line, "relay-refused"))
                self.assertEqual(obj["stdout"], recording.stdout.decode("utf-8"))
                self.assertEqual(obj["sid"], recording.line["sid"])
                self.assertNotIn("names sid", obj["reason"], "the sids agree")

    def test_a_re_emission_recorded_nothing_and_is_not_ok(self):
        """The recorded `re-emitted` line (exit 0, the same block): bale
        recorded nothing — twine always passes the block, so it should
        never see one (RecordedRelay's docstring: this replays an argv twine
        never builds). Not ok, named, and the block is not printed."""
        recording = relay_recording("re-emitted")
        self.assertEqual((recording.exit_code, recording.line["block"]),
                         (0, RELAYED.line["block"]))
        obj = self.assert_relay_not_ok(RecordedRelay("re-emitted"), "'re-emitted'",
                                       "recorded nothing")
        self.assertEqual((obj["exit_code"], obj["outcome"]), (0, "re-emitted"))
        self.assertNotIn("bale exited", obj["reason"])

    def test_a_relayed_line_beside_exit_1_is_not_ok(self):
        """A double for a contract bale keeps — `relayed` comes with exit 0
        — broken anyway: the recorded relayed line beside exit 1. twine
        trusts the line only beside exit 0."""
        obj = self.assert_relay_not_ok(RecordedRelay(exit_code=1), "bale exited 1")
        self.assertEqual((obj["outcome"], obj["relay"]), ("relayed", RELAYED.line))
        self.assertEqual(obj["reason"], "bale exited 1")

    def test_a_relayed_line_naming_another_sid_is_not_ok(self):
        """NOT bale's (bale's `sid` is the argument as given): the relayed
        line edited to name another session."""
        other = "2026-10-08-twine-other-009"
        obj = self.assert_relay_not_ok(
            RecordedRelay(stdout=relay_line_double(sid=other)),
            f"names sid {other!r}", f"not the block's {RELAY_RECORDED_SID!r}",
            exit_code=1)
        self.assertEqual(obj["outcome"], "relayed")

    def test_a_relayed_line_with_a_null_or_empty_block_is_not_ok(self):
        """NOT bale's: the relayed line edited to carry no block, or an
        empty one, or one that is not a string."""
        for block, needle in ((None, "carries no block (block is null)"),
                              ("", "carries an empty block"),
                              (21, "carries no block (block is int)")):
            with self.subTest(block=block):
                obj = self.assert_relay_not_ok(
                    RecordedRelay(stdout=relay_line_double(block=block)), needle)
                self.assertEqual(obj["outcome"], "relayed")

    def test_an_outcome_bale_never_emits_is_named(self):
        """NOT bale's: NOT_A_BALE_OUTCOME, in no vocabulary of bale 0.4.49,
        on the relayed line otherwise intact, exit 0."""
        obj = self.assert_relay_not_ok(
            RecordedRelay(stdout=relay_line_double(outcome=NOT_A_BALE_OUTCOME)),
            f"outcome {NOT_A_BALE_OUTCOME!r}", "does not know", "not 'relayed'")
        self.assertEqual(obj["outcome"], NOT_A_BALE_OUTCOME)

    def test_bale_exiting_non_zero_is_not_ok_naming_the_status(self):
        """A double for what no recording covers — and what `relay --json`
        documents it never does: exit 1 with an empty stdout. Not ok, naming
        the exit and that there was no line; `relay` and `outcome` null;
        the stderr (named as not bale's) surfaced."""
        runner = RecordedRelay(stdout=b"", exit_code=1, stderr=NOT_BALES_STDERR)
        obj = self.assert_relay_not_ok(runner, "bale exited 1", "not one JSON object",
                                       "it was empty")
        self.assertEqual((obj["exit_code"], obj["relay"], obj["outcome"], obj["stdout"]),
                         (1, None, None, ""))
        self.assertEqual(obj["stderr"], NOT_BALES_STDERR.decode())

    def test_stdout_that_is_not_one_json_object(self):
        """Doubles, NOT bale's: the flagless relay's answer (the block as
        text, no line), a usage message, two lines, a JSON array — each
        with exit 0. Not ok; `relay` and `outcome` null; the block the
        flagless relay printed is never passed through."""
        for stdout in (RELAYED.line["block"].encode("utf-8"),
                       b"[twine test] usage: not bale\n",
                       RELAYED.stdout + RELAYED.stdout, b"[1, 2]\n"):
            with self.subTest(stdout=stdout[:30]):
                obj = self.assert_relay_not_ok(RecordedRelay(stdout=stdout),
                                               "not one JSON object", "it began")
                self.assertEqual((obj["relay"], obj["outcome"], obj["exit_code"]),
                                 (None, None, 0))

    def test_human_mode_not_ok_is_one_line_and_never_bales_stdout(self):
        """Not ok is one line naming why, never the block and never the JSON
        line: the recorded ingest refusal, and the recorded relayed line
        beside exit 1 (a double for a broken contract)."""
        for runner in (RecordedRelay("ingest"), RecordedRelay(exit_code=1)):
            with self.subTest(recording=runner.recording.relpath,
                              exit_code=runner.exit_code):
                run = self.exchange_human(str(self.exchange_turn()), runner=runner)
                self.assertEqual(run.code, 1)
                self.assertEqual(len(run.stdout.splitlines()), 1)
                self.assertIn("NOT OK", run.stdout)
                self.assertIn("bale exited 1", run.stdout)
                self.assertNotIn("# sha256 ", run.stdout, "a block's trailer on stdout")
                self.assertNotIn("BALE EXCHANGE END", run.stdout)
                self.assertNotIn('"outcome": ', run.stdout)

    def test_a_bale_that_times_out_is_not_ok(self):
        """A double: the seam killed the relay at its timeout."""
        obj = self.assert_relay_not_ok(RecordedRelay(timed_out=True), "did not finish",
                                       "not one JSON object")
        self.assertEqual((obj["timed_out"], obj["exit_code"], obj["relay"]),
                         (True, None, None))
        self.assertNotIn("bale exited", obj["reason"])

    def test_a_capped_stdout_is_not_ok(self):
        """A double: the seam stopped the relay when its stdout passed the
        cap — here mid-line, the recorded line cut short."""
        obj = self.assert_relay_not_ok(
            RecordedRelay(capped=True, stdout=RELAYED.stdout[:100]),
            "passed", "it was stopped", "not one JSON object")
        self.assertEqual((obj["capped"], obj["exit_code"], obj["relay"]),
                         (True, None, None))

    def test_the_twins_fixed_names_on_every_path(self):
        """Every fixed name, `relay` and `outcome` among them, on a refusal
        before bale, an ok relay, a recorded refusal and a stdout that is
        no line."""
        paths = {
            "refused before bale": (RecordedRelay(), str(self.write("No block.\n", "p.txt"))),
            "relayed": (RecordedRelay(), str(self.exchange_turn())),
            "relay-refused": (RecordedRelay("ingest"), str(self.exchange_turn())),
            "no line": (RecordedRelay(stdout=b""), str(self.exchange_turn())),
        }
        expected = {"refused before bale": (None, None), "relayed": (RELAYED.line, "relayed"),
                    "relay-refused": (relay_recording("ingest").line, "relay-refused"),
                    "no line": (None, None)}
        for name, (runner, path) in paths.items():
            with self.subTest(path=name):
                _, obj = self.exchange(path, runner=runner)
                self.assertTrue(EXCHANGE_FIXED <= set(obj), EXCHANGE_FIXED - set(obj))
                self.assertEqual((obj["relay"], obj["outcome"]), expected[name])

    def test_the_fixture_player_has_no_recording_of_twines_relay_argv(self):
        """Through the fixture player, twine's own argv finds no recording
        (`relay_sid_stdin_--json.json` was never recorded: the recordings
        were made with a file) — which is why RecordedRelay replays them
        for it, on a named assumption. The player does answer the recorded
        file argv, with the very bytes and exit RecordedRelay replays."""
        player = FixturePlayer(REPO_ROOT, scratch_root=self.dir,
                               select={RELAY_FILE_KEY: "relayed"})
        with self.assertRaises(AssertionError) as caught:
            player([str(ROOTS.ok / "bin" / "bale"), "relay", RELAY_RECORDED_SID, "-",
                    "--json"], cwd=self.dir)
        self.assertIn("relay_sid_stdin_--json.json", str(caught.exception))
        answer = player([str(ROOTS.ok / "bin" / "bale"), "relay", RELAY_RECORDED_SID,
                         "/tmp/manifest.json", "--json"], cwd=self.dir)
        replayed = RecordedRelay()([str(ROOTS.ok / "bin" / "bale"), "relay",
                                    RELAY_RECORDED_SID, "-", "--json"])
        self.assertEqual((answer.exit_code, answer.stdout), (0, RELAYED.stdout))
        self.assertEqual((replayed.exit_code, replayed.stdout), (0, RELAYED.stdout))

    def test_the_double_refuses_to_answer_for_another_sid(self):
        """RecordedRelay never replays a recording for a sid its line does
        not name — bale's `sid` is the argument as given — nor any argv but
        twine's."""
        with self.assertRaises(AssertionError) as caught:
            RecordedRelay()(["/b/bin/bale", "relay", EXCHANGE_SID, "-", "--json"])
        self.assertIn("answers for sid", str(caught.exception))
        for argv in (["/b/bin/bale", "relay", RELAY_RECORDED_SID, "-"],
                     ["/b/bin/bale", "relay", RELAY_RECORDED_SID, "/f", "--json"],
                     ["/b/bin/bale", "apply", "--dry-run", "--json", "/t.tgz"]):
            with self.subTest(argv=argv), self.assertRaises(AssertionError):
                RecordedRelay()(argv)

    def test_the_relayed_block_is_an_intact_exchange_block_of_its_sid(self):
        """The input the tests carry: `take` reads the relayed line's block
        as one exchange block of the recorded sid whose trailer holds; the
        session-gate variant (sentinel edited) stays intact."""
        for block, sid in ((relayed_block(), RELAY_RECORDED_SID),
                           (block_for_sid(RELAY_RECORDED_ABSENT_SID),
                            RELAY_RECORDED_ABSENT_SID)):
            with self.subTest(sid=sid):
                path = self.write(block, "block.txt")
                take = json.loads(run_cli("take", str(path), "--json").stdout)
                self.assertEqual([(b["kind"], b["sid"], b["integrity"]["ok"])
                                  for b in take["blocks"]], [("exchange", sid, True)])
        self.assertEqual(len(relayed_block().splitlines()), 21)
        self.assertTrue(relayed_block().endswith("\n"))


def trailer_digest(block: str) -> str:
    """The hex digest on `block`'s `# sha256 <hex>` trailer line."""
    found = [ln.split()[-1] for ln in block.split("\n") if ln.startswith("# sha256 ")]
    if len(found) != 1:
        raise AssertionError(f"not one trailer in {block[:60]!r}")
    return found[0]


def hand_built_exchange(sid: str, body: str | None) -> str:
    """NOT bale's: an exchange block built here, its header one comment
    line, its body `body` (None: no body at all) and its trailer the sha256
    of exactly that body — so the only fault left is what the body is."""
    lines = [f"BALE EXCHANGE BEGIN {sid}", "# [twine test] a hand-built block, not bale's"]
    if body is not None:
        lines.append(body.rstrip("\n"))
    digest = hashlib.sha256((body or "").encode("utf-8")).hexdigest()
    return "\n".join([*lines, f"# sha256 {digest}", "BALE EXCHANGE END"]) + "\n"


class ExchangeVouchesForBalesBlock(TempCase):
    """Since session 2026-10-08-twine-exchange-vouch-005 the block bale
    hands back is held to what twine asks of the block it carries in
    (cli-contract.md §11.2): exactly one block — its own lines, nothing
    around them — of kind `exchange`, intact by `take`'s rule (§9.2), of
    the carried block's session. Every block below is NOT bale's: the
    relayed recording's line with its `block` replaced (relay_line_double),
    answered by RecordedRelay with exit 0 — bale's line otherwise intact,
    so the vouch is the only thing that fails. The line was read and
    understood, so `outcome` stays `relayed` and `relay` is the line; the
    block is never printed."""

    def assert_not_vouched(self, block, *needles: str, line: bytes | None = None,
                           exit_code: int = 0) -> dict:
        """Not ok, exit 1, bale ran once, no refusal; `reason` holds every
        needle; the twin carries bale's line whole (`stdout`, `relay`) with
        `outcome` `relayed`. Human mode is one `NOT OK` line that is never
        the block: neither its trailer's digest, its body nor its END
        reaches stdout. (assert_relay_not_ok's `# sha256 ` heuristic does not
        fit here: take's own wording for a fault, which the reason quotes,
        names the `# sha256 <hex>` trailer.)"""
        line = relay_line_double(block=block) if line is None else line
        runner = RecordedRelay(stdout=line, exit_code=exit_code)
        path = self.exchange_turn()
        run, obj = self.exchange(str(path), runner=runner)
        self.assertEqual((run.code, obj["ok"], obj["ran"], obj["refusals"]),
                         (1, False, True, []), obj["reason"])
        self.assertEqual(len(runner.calls), 1)
        self.assertIn(VOUCH_FAILURE, obj["reason"])
        for needle in needles:
            self.assertIn(needle, obj["reason"])
        self.assertEqual((obj["stdout"], obj["relay"], obj["outcome"]),
                         (line.decode("utf-8"), json.loads(line), "relayed"))
        self.assertTrue(EXCHANGE_FIXED <= set(obj), EXCHANGE_FIXED - set(obj))
        human = self.exchange_human(str(path), runner=runner)
        self.assertEqual(human.code, 1)
        self.assertEqual(len(human.stdout.splitlines()), 1, human.stdout)
        self.assertTrue(human.stdout.startswith(f"carry exchange {path}: NOT OK — "),
                        human.stdout)
        self.assertIn(VOUCH_FAILURE, human.stdout)
        for never in (trailer_digest(relayed_block()), '"record_version"',
                      "BALE EXCHANGE END"):
            self.assertNotIn(never, human.stdout, "the block reached stdout")
        return obj

    def test_a_block_edited_after_its_trailer_is_mismatch(self):
        """The relayed block with its body edited (round 1 → 2) after the
        trailer was written: take's `mismatch`, and that is the whole
        reason — bale's line is otherwise as recorded."""
        edited = relayed_block().replace('"round": 1', '"round": 2', 1)
        self.assertNotEqual(edited, relayed_block())
        obj = self.assert_not_vouched(edited, "fails integrity (mismatch)",
                                      "never prints a block it cannot vouch for",
                                      "never repairs one")
        self.assertEqual(obj["reason"].count(VOUCH_FAILURE), 1, obj["reason"])
        self.assertTrue(obj["reason"].startswith(VOUCH_FAILURE), obj["reason"])
        self.assertNotIn("bale exited", obj["reason"])
        self.assertTrue(obj["integrity"]["ok"], "`integrity` stays the carried block's")

    def test_a_block_cut_short_is_no_trailer_or_unclosed(self):
        """The trailer line gone (`no-trailer`), and the block cut before
        its END (`unclosed`)."""
        lines = relayed_block().split("\n")
        without_trailer = "\n".join(ln for ln in lines if not ln.startswith("# sha256 "))
        cut = relayed_block().replace("BALE EXCHANGE END\n", "", 1)
        self.assertNotEqual(cut, relayed_block())
        for block, fault in ((without_trailer, "no-trailer"), (cut, "unclosed")):
            with self.subTest(fault=fault):
                obj = self.assert_not_vouched(block, f"fails integrity ({fault})")
                self.assertEqual(obj["reason"].count(VOUCH_FAILURE), 1, obj["reason"])

    def test_every_integrity_fault_is_named_in_takes_words(self):
        """The faults §9.2 names that the relayed block cannot show by
        editing alone: a carrier unescaping the crafter block's \\u2014
        (its sentinel naming the carried sid), a BEGIN with no sid, a header
        and no body, a body that matches its trailer but is not a JSON
        object (hand-built, NOT bale's)."""
        unescaped = block_for_sid(RELAY_RECORDED_SID,
                                  exchange_text().replace("\\u2014", "—", 1))
        no_sid = relayed_block().replace(f"BALE EXCHANGE BEGIN {RELAY_RECORDED_SID}",
                                         "BALE EXCHANGE BEGIN", 1)
        cases = {"unescaped-in-transit": unescaped, "no-sid": no_sid,
                 "no-body": hand_built_exchange(RELAY_RECORDED_SID, None),
                 "body-not-json": hand_built_exchange(RELAY_RECORDED_SID, "[1, 2]\n")}
        for fault, block in cases.items():
            with self.subTest(fault=fault):
                obj = self.assert_not_vouched(block, f"fails integrity ({fault})")
                self.assertEqual(obj["reason"].count(VOUCH_FAILURE), 1, obj["reason"])

    def test_two_intact_blocks_in_one_string(self):
        """Two intact blocks concatenated: not exactly one, both named."""
        obj = self.assert_not_vouched(
            relayed_block() + relayed_block(), "holds 2 blocks, not exactly one",
            f"[1] exchange {RELAY_RECORDED_SID}", f"[2] exchange {RELAY_RECORDED_SID}")
        self.assertEqual(obj["reason"].count(VOUCH_FAILURE), 1, obj["reason"])

    def test_text_around_the_one_block_is_not_vouched_for(self):
        """Decision 1 (exactness): bale prints the block alone, so prose
        before or after the one intact block, or a blank line around it,
        is a failure naming where the block sits — twine hands on exactly a
        block's own lines. (A missing final newline is the one difference
        tolerated: test_a_block_without_a_final_newline_gains_one.)"""
        cases = {"prose around": f"Carry this:\n{relayed_block()}Thanks.\n",
                 "a blank line before": "\n" + relayed_block(),
                 "a blank line after": relayed_block() + "\n"}
        spans = {"prose around": "lines 2–22 of 23", "a blank line before":
                 "lines 2–22 of 22", "a blank line after": "lines 1–21 of 22"}
        for name, block in cases.items():
            with self.subTest(case=name):
                obj = self.assert_not_vouched(block, "text around its one block",
                                              spans[name], "exactly a block's own lines")
                self.assertEqual(obj["reason"].count(VOUCH_FAILURE), 1, obj["reason"])

    def test_a_string_with_no_block_at_all(self):
        self.assert_not_vouched("[twine test] not bale's: no block here\n",
                                "holds no block at all")

    def test_a_light_block_in_place_of_the_exchange_block(self):
        """The crafter's light block, whole: one block, its own lines, but
        not an exchange block."""
        light = LIGHT.read_text(encoding="utf-8")
        obj = self.assert_not_vouched(light, "is a light block", "not an exchange block")
        self.assertEqual(obj["reason"].count(VOUCH_FAILURE), 1, obj["reason"])

    def test_an_intact_block_of_another_session(self):
        """block_for_sid: intact (the trailer hashes the body only), but its
        sentinel names another session — not the courier's next hop. The
        line's own `sid` is the carried block's, so only the vouch fails."""
        other = "2026-10-08-twine-other-009"
        obj = self.assert_not_vouched(
            block_for_sid(other), f"exchange block of session {other!r}",
            f"not of the carried block's {RELAY_RECORDED_SID!r}")
        self.assertNotIn("fails integrity", obj["reason"])
        self.assertNotIn("names sid", obj["reason"], "the line's sid is the block's")

    def test_every_difference_is_named_at_once(self):
        """The vouch is appended to the line's failures, never instead of
        them: a line naming another sid, carrying an edited block, beside
        exit 1."""
        other = "2026-10-08-twine-other-009"
        edited = relayed_block().replace('"round": 1', '"round": 2', 1)
        obj = self.assert_not_vouched(
            None, "bale exited 1", f"names sid {other!r}", "(mismatch)",
            line=relay_line_double(sid=other, block=edited), exit_code=1)
        self.assertLess(obj["reason"].index("bale exited 1"),
                        obj["reason"].index(VOUCH_FAILURE), "appended, not first")

    def test_a_crlf_block_is_read_as_take_reads_it_and_printed_as_bale_sent_it(self):
        """NOT bale's (bale's block is LF): the intact block with CRLF line
        endings. take normalizes CRLF before matching (§9.1), so twine can
        vouch for it; human stdout is still the line's `block`, byte for
        byte — twine never rewrites what it hands on."""
        crlf = relayed_block().replace("\n", "\r\n")
        runner = RecordedRelay(stdout=relay_line_double(block=crlf))
        run = self.exchange_human(str(self.exchange_turn()), runner=runner)
        self.assertEqual((run.code, run.stdout), (0, crlf), run.stdout[:200])

    def test_the_recorded_block_is_vouched_for(self):
        """The relayed recording's own block passes the vouch as it stands:
        the function adds no failure for it (the existing ok tests,
        unmoved, prove the verb end to end)."""
        outcome = ExchangeOutcome(source="x")
        outcome.block = shapes.find_blocks(relayed_block()).blocks[0]
        vouch_for_relayed_block(outcome, RELAYED.line["block"])
        self.assertEqual(outcome.failures, [])


# ---------------------------------------------------------------------------
# 4. carry response: the tarball and the dry run
# ---------------------------------------------------------------------------


class ResponseDryRuns(TempCase):

    def test_the_recorded_dry_run_is_ok_and_hands_back_the_apply_line(self):
        tarball = self.tarball()
        player = self.player()
        run, obj = self.response(str(tarball), "--cwd", str(self.dir), runner=player)
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
        player = FixturePlayer(REPO_ROOT, scratch_root=self.dir, select=SELECT_DRY_RUN)
        run = run_verb("response", str(tarball), "--cwd", str(self.dir), runner=player)
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

    def test_the_recorded_scope_drift_refusal_is_not_ok(self):
        """The refusal the 2b-ii carry-forward owed, recorded at 0.4.49 (a
        response adding `other.txt` beside the forecast's `hello.txt`):
        exit 1, the line on stdout with `drift` naming the path and bale's
        remedy line — replayed through the player by selecting its group.
        Not ok, naming the exit and the outcome, no apply line."""
        player = self.player(SELECT_DRIFT_REFUSED)
        run, obj = self.response(str(self.tarball()), runner=player)
        self.assertEqual((run.code, obj["ok"], obj["ran"], obj["exit_code"],
                          obj["outcome"], obj["apply_line"]),
                         (1, False, True, 1, RECORDED_REFUSAL, None))
        recorded = json.loads(DRIFT_REFUSED.read_bytes())
        self.assertEqual(obj["dry_run"], recorded)
        self.assertEqual(recorded["drift"]["out_of_scope_paths"], ["other.txt"])
        self.assertIn("--allow-out-of-scope", recorded["drift"]["remedy"])
        for needle in ("bale exited 1", f"outcome {RECORDED_REFUSAL!r}", "not 'dry-run'"):
            self.assertIn(needle, obj["reason"])
        self.assertEqual(obj["stderr"], "", "no row records stderr")
        self.assertEqual(len(player.calls), 1)

    def test_each_dry_run_refusal_is_named_with_its_exit(self):
        """Doubles in bale's spelling: each of the three *-refused outcomes,
        exit 1, stdout the one JSON line — what format_apply_json documents
        under --dry-run when the plan would refuse (the scope-drift one is
        also recorded: the test above). Not ok, naming both the exit and
        the outcome, bale's stderr surfaced."""
        self.assertEqual(DRY_RUN_REFUSALS, ["scope-drift-refused",
                                            "required-check-refused",
                                            "base-drift-refused"])
        self.assertIn(RECORDED_REFUSAL, DRY_RUN_REFUSALS)
        for outcome in DRY_RUN_REFUSALS:
            with self.subTest(outcome=outcome):
                line = json.dumps({"outcome": outcome, "sid": "2026-10-03-x-001"})
                obj = self.not_ok(BaleDouble(exit_code=DRY_RUN_REFUSAL_EXIT,
                                             stdout=(line + "\n").encode(),
                                             stderr=b"[bale] double: refused\n"),
                                  f"bale exited {DRY_RUN_REFUSAL_EXIT}",
                                  f"outcome {outcome!r}", "not 'dry-run'")
                self.assertEqual((obj["exit_code"], obj["outcome"], obj["stderr"]),
                                 (1, outcome, "[bale] double: refused\n"))
                self.assertEqual(obj["refusals"], [])

    def test_a_bale_error_prints_nothing_and_exits_non_zero(self):
        """A double for bale's error path: nothing on stdout (bale's consumer
        contract: errors exit through fail(), stderr, non-zero), exit 2."""
        obj = self.not_ok(BaleDouble(exit_code=2, stdout=b"",
                                     stderr=b"[bale] double: no open session\n"),
                          "bale exited 2", "not one JSON object", "it was empty")
        self.assertEqual((obj["exit_code"], obj["dry_run"], obj["outcome"], obj["stdout"]),
                         (2, None, None, ""))
        self.assertEqual(obj["stderr"], "[bale] double: no open session\n")

    def test_an_outcome_bale_never_emits_is_named(self):
        """Not bale's: NOT_A_BALE_OUTCOME is in no vocabulary of bale
        0.4.49, spelled so it cannot be taken for one. Exit 0 and a JSON
        line, as a dry run's; twine still names the outcome it does not
        know and hands back no apply line."""
        self.assertNotIn(NOT_A_BALE_OUTCOME,
                         {v for values in BALE_VOCABULARIES.values() for v in values})
        line = json.dumps({"outcome": NOT_A_BALE_OUTCOME}) + "\n"
        obj = self.not_ok(BaleDouble(stdout=line.encode()),
                          f"outcome {NOT_A_BALE_OUTCOME!r}", "not 'dry-run'")
        self.assertEqual((obj["outcome"], obj["exit_code"]), (NOT_A_BALE_OUTCOME, 0))

    def test_a_non_zero_exit_with_the_dry_run_outcome_is_not_ok(self):
        """A double for a contract bale documents it keeps — its dry-run
        line comes with exit 0 — broken anyway: twine trusts the outcome
        only beside exit 0."""
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
        self.stub = StubBale(relay_stdout=RELAYED.path, apply_stdout=DRY_RUN,
                             stderr="[bale] stub: not bale\n")
        self.addCleanup(self.stub.cleanup)

    def test_carry_exchange_through_the_real_seam(self):
        """The stub replays the relayed recording's line (exit 0): bale was
        run as `relay <sid> - --json` with the block's bytes on stdin, and
        the twin carries the line as `stdout`, parsed as `relay`."""
        path = self.exchange_turn()
        run = run_cli("carry", "exchange", str(path), "--cwd", str(self.dir), "--json",
                      bale_root=self.stub.root)
        obj = one_line(self, run.stdout, "carry exchange")
        self.assertEqual((run.code, obj["ok"], obj["exit_code"]), (0, True, 0),
                         obj["reason"])
        self.assertEqual(self.stub.argv(), ["relay", RELAY_RECORDED_SID, "-", "--json"])
        self.assertEqual(self.stub.stdin(), relayed_block().encode("utf-8"))
        self.assertEqual(self.stub.cwd(), str(self.dir))
        self.assertEqual(obj["stdout"], RELAYED.stdout.decode("utf-8"))
        self.assertEqual((obj["relay"], obj["outcome"]), (RELAYED.line, "relayed"))
        self.assertEqual(obj["bale"]["executable"], str(self.stub.executable))
        self.assertEqual((obj["bale"]["installed"], obj["bale"]["pin_matches"]),
                         (PIN, True))
        self.assertIn("[bale] stub: not bale", run.stderr)

    def test_carry_exchange_human_stdout_is_the_relayed_block(self):
        """Human mode through the real seam: stdout is byte for byte the
        recorded line's `block` — the operator's `> next.txt` unchanged."""
        run = run_cli("carry", "exchange", str(self.exchange_turn()),
                      bale_root=self.stub.root)
        self.assertEqual(run.code, 0, run.stdout)
        self.assertEqual(run.stdout.encode("utf-8"), RELAYED.line["block"].encode("utf-8"))

    def test_a_recorded_refusal_through_the_real_seam(self):
        """The stub replays the ingest refusal (exit 1): not ok, the cause
        quoted, human stdout one line."""
        refused = relay_recording("ingest")
        stub = StubBale(relay_stdout=refused.path, exit_code=refused.exit_code)
        self.addCleanup(stub.cleanup)
        run = run_cli("carry", "exchange", str(self.exchange_turn()), "--json",
                      bale_root=stub.root)
        obj = one_line(self, run.stdout, "carry exchange")
        self.assertEqual((run.code, obj["ok"], obj["exit_code"], obj["outcome"]),
                         (1, False, 1, "relay-refused"))
        self.assertIn(f'"{refused.line["cause"]}"', obj["reason"])
        human = run_cli("carry", "exchange", str(self.exchange_turn()),
                        bale_root=stub.root)
        self.assertEqual((human.code, len(human.stdout.splitlines())), (1, 1))
        self.assertNotIn("Traceback", run.stderr + human.stderr)

    def test_a_block_twine_cannot_vouch_for_through_the_real_seam(self):
        """The stub replays a line that is NOT bale's: the relayed
        recording's line, exit 0, its `block` edited after the trailer
        (round 1 → 2). Not ok, exit 1, the reason naming `mismatch`; the
        twin carries the line and `outcome` `relayed`; human stdout is one
        `NOT OK` line, never the block; no traceback."""
        edited = relayed_block().replace('"round": 1', '"round": 2', 1)
        line = self.write(relay_line_double(block=edited), "edited-relay-line.json")
        stub = StubBale(relay_stdout=line)
        self.addCleanup(stub.cleanup)
        run = run_cli("carry", "exchange", str(self.exchange_turn()), "--json",
                      bale_root=stub.root)
        obj = one_line(self, run.stdout, "carry exchange")
        self.assertEqual((run.code, obj["ok"], obj["exit_code"], obj["outcome"]),
                         (1, False, 0, "relayed"))
        self.assertEqual(obj["relay"], json.loads(line.read_bytes()))
        self.assertIn("(mismatch)", obj["reason"])
        self.assertEqual(stub.argv(), ["relay", RELAY_RECORDED_SID, "-", "--json"])
        human = run_cli("carry", "exchange", str(self.exchange_turn()),
                        bale_root=stub.root)
        self.assertEqual((human.code, len(human.stdout.splitlines())), (1, 1))
        self.assertIn("NOT OK", human.stdout)
        self.assertIn("(mismatch)", human.stdout)
        self.assertNotIn("BALE EXCHANGE", human.stdout)
        self.assertNotIn(trailer_digest(edited), human.stdout)
        self.assertNotIn("Traceback", run.stderr + human.stderr)

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
        """A bale error, as bale's contract has it: nothing on stdout, exit 4."""
        failing = StubBale(exit_code=4, stderr="[bale] stub: no\n")
        self.addCleanup(failing.cleanup)
        run = run_cli("carry", "response", str(self.tarball()), "--json",
                      bale_root=failing.root)
        obj = one_line(self, run.stdout, "carry response")
        self.assertEqual((run.code, obj["ok"], obj["exit_code"], obj["apply_line"]),
                         (1, False, 4, None))
        self.assertIn("bale exited 4", obj["reason"])
        self.assertEqual((obj["stdout"], obj["stderr"]), ("", "[bale] stub: no\n"))
        self.assertNotIn("Traceback", run.stderr)

    def test_a_version_other_than_the_pin_is_refused_and_never_run(self):
        """D2, decided by session 4: the stub at 0.4.46 is never started."""
        (self.stub.root / "bin" / "VERSION").write_text("0.4.46\n", encoding="utf-8")
        for argv in (["carry", "response", str(self.tarball())],
                     ["carry", "exchange", str(self.exchange_turn())]):
            with self.subTest(verb=argv[1]):
                run = run_cli(*argv, "--json", bale_root=self.stub.root)
                obj = one_line(self, run.stdout, " ".join(argv[:2]))
                self.assertEqual((run.code, obj["ok"], obj["ran"], obj["exit_code"]),
                                 (1, False, False, None))
                self.assertEqual((obj["bale"]["installed"], obj["bale"]["pin_matches"]),
                                 ("0.4.46", False))
                self.assertIn(f"is 0.4.46, not the pin {PIN}", obj["reason"])
                self.assertEqual(obj["refusals"], [obj["reason"]])
                self.assertIsNone(self.stub.argv(), "the stub was started")


# ---------------------------------------------------------------------------
# 7. Finding bale: the tests never reach a real one
# ---------------------------------------------------------------------------


class FindingBale(TempCase):

    def test_a_bale_on_path_is_never_run_by_the_cli_tests(self):
        """A `bale` on PATH that would leave a marker: run_cli pins
        TWINE_BALE_ROOT to a missing directory, so the verbs refuse — no
        readable bin/VERSION there, and twine drives only the pinned bale
        (D2) — and the PATH bale never runs."""
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
                self.assertIn("cannot tell this one's version", obj["reason"])
                self.assertEqual(obj["bale"]["source"], "TWINE_BALE_ROOT")
        self.assertFalse(marker.exists(), "a test reached the bale on PATH")

    def test_a_pinned_root_with_no_bin_bale_could_not_be_started(self):
        """The VERSION reads the pin, but there is no bin/bale: learned by
        starting it, through the real seam — a refusal, ran false."""
        for argv in (["carry", "exchange", str(self.exchange_turn())],
                     ["carry", "response", str(self.tarball())]):
            with self.subTest(verb=argv[1]):
                run = run_cli(*argv, "--json", bale_root=ROOTS.ok)
                obj = one_line(self, run.stdout, " ".join(argv[:2]))
                self.assertEqual((run.code, obj["ok"], obj["ran"]), (1, False, False))
                self.assertIn("could not be started", obj["reason"])
                self.assertEqual(obj["bale"]["pin_matches"], True)

    def test_no_bale_anywhere_is_a_refusal(self):
        for verb, arg in (("exchange", str(self.exchange_turn())),
                          ("response", str(self.tarball()))):
            with self.subTest(verb=verb):
                runner = RecordedRelay() if verb == "exchange" else BaleDouble()
                run = run_verb(verb, arg, "--json", runner=runner, env={})
                obj = one_line(self, run.stdout, f"carry {verb}")
                self.assertEqual((run.code, obj["ok"], obj["ran"]), (1, False, False))
                self.assertIn("no bale install found", obj["reason"])
                self.assertIsNone(obj["bale"]["executable"])
                self.assertEqual(runner.calls, [])

    def test_bale_root_flag_wins_over_the_environment(self):
        """--bale-root names a root at another version while TWINE_BALE_ROOT
        names one at the pin: the flag's root is the one found (and, not
        being the pin, refused — section 8)."""
        runner = BaleDouble(stdout=DRY_RUN.read_bytes())
        _, obj = self.response(str(self.tarball()), "--bale-root", str(ROOTS.other),
                               runner=runner)
        self.assertEqual(obj["bale"]["executable"], str(ROOTS.other / "bin" / "bale"))
        self.assertEqual((obj["bale"]["source"], obj["bale"]["installed"],
                          obj["bale"]["pin_matches"]),
                         ("--bale-root", ROOTS.other_version, False))
        self.assertEqual(runner.calls, [])

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


# ---------------------------------------------------------------------------
# 8. The pin gates (D2, decided by Arc 1 session 4)
# ---------------------------------------------------------------------------


class ThePinGates(TempCase):
    """The carry verbs drive only a bale whose bin/VERSION is the pin. The
    transition table keys on bale 0.4.49's outcome and closure
    vocabularies; another version may answer in spellings it has no move
    for, so the version is checked before bale starts — never after."""

    def both(self, root: Path) -> list[tuple[str, Run, dict, object]]:
        """Each carry verb at `root`: exchange answered by the relayed
        recording (RecordedRelay), response by the recorded dry run's bytes."""
        out = []
        for verb, arg in (("exchange", str(self.exchange_turn())),
                          ("response", str(self.tarball()))):
            runner = (RecordedRelay() if verb == "exchange"
                      else BaleDouble(stdout=DRY_RUN.read_bytes()))
            run = run_verb(verb, arg, "--json", runner=runner,
                           env={"TWINE_BALE_ROOT": root.as_posix()})
            out.append((verb, run, one_line(self, run.stdout, f"carry {verb}"), runner))
        return out

    def test_another_version_is_refused_before_bale_starts(self):
        for verb, run, obj, runner in self.both(ROOTS.other):
            with self.subTest(verb=verb):
                self.assert_refused(run, obj, runner, f"is {ROOTS.other_version}",
                                    f"not the pin {PIN}", "(D2)",
                                    "bump the pin in a session")
                self.assertEqual(obj["bale"]["pin_matches"], False)

    def test_an_unreadable_version_is_refused_before_bale_starts(self):
        for verb, run, obj, runner in self.both(ROOTS.absent):
            with self.subTest(verb=verb):
                self.assert_refused(run, obj, runner, "cannot tell this one's version",
                                    f"the pinned bale {PIN}")
                self.assertIsNone(obj["bale"]["installed"])

    def test_the_pinned_version_is_driven(self):
        for verb, run, obj, runner in self.both(ROOTS.ok):
            with self.subTest(verb=verb):
                self.assertEqual((run.code, obj["ok"], obj["ran"]), (0, True, True))
                self.assertEqual(len(runner.calls), 1)
                self.assertEqual(obj["bale"]["pin_matches"], True)

    def test_a_refused_version_is_one_reason_among_the_others(self):
        """The gate is a refusal like any other: named beside the rest, all
        at once, before anything runs."""
        runner = BaleDouble()
        run = run_verb("response", str(self.dir / "nope.tar.gz"), "--json",
                       runner=runner, env={"TWINE_BALE_ROOT": ROOTS.other.as_posix()})
        obj = one_line(self, run.stdout, "carry response")
        self.assertEqual(len(obj["refusals"]), 2, obj["refusals"])
        self.assertIn("no such file", obj["refusals"][0])
        self.assertIn("not the pin", obj["refusals"][1])
        self.assertEqual(runner.calls, [])

    def test_the_gate_reads_the_pin_from_the_manifest_never_a_literal(self):
        executable = bale.locate_executable(str(ROOTS.ok), {}, lambda name: None)
        self.assertEqual((executable.pin, executable.drive_refusal), (PIN, None))
        unknown = bale.Executable(executable.root, executable.path, PIN, None, "")
        self.assertIn("the pin is unknown", unknown.drive_refusal)


if __name__ == "__main__":
    unittest.main()

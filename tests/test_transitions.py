"""The transition table (D17; Arc 1 session 4): share/transitions.toml,
twine/transitions.py, and `twine transitions`.

The test that fails by name is TheTableIsTotal.test_every_key_of_every_axis
_has_a_declared_move: it walks every key of every axis with its own logic
(assert_total, below — independent of twine.transitions' checker) and fails
naming each axis and key without a row, each row whose move is undeclared,
and each bale-axis key that is not bale's spelling. DetectorsFire proves
each of those detectors fires, in assert_total and in the module, against
tables edited to be wrong: a row removed, an undeclared move, an invented
key, and the other faults the module names.

Sections:
  1. Helpers: the real table, edited copies, the independent check
  2. The real table is total
  3. Its content: the pinned moves, actors, T12, the stop set
  4. The detectors fire
  5. `twine transitions`, the verb
"""

from __future__ import annotations

import ast
import copy
import io
import json
import re
import tempfile
import tomllib
import unittest
from pathlib import Path

from twine import REPO_ROOT, TRANSITIONS_TABLE, transitions
from twine.bale import load_manifest
from twine.cli import Context, main
from twine.process import RunError

from tests.helpers import (BALE_VOCABULARIES, NOT_A_BALE_OUTCOME, PIN, Run, TempRoots,
                           run_cli)

# ---------------------------------------------------------------------------
# 1. Helpers: the real table, edited copies, the independent check
# ---------------------------------------------------------------------------

AXES = ("telemetry-outcome", "closure-reason", "apply-outcome", "stop")
BALE_AXES = ("telemetry-outcome", "closure-reason", "apply-outcome")
# The ten stop keys the session-4 brief pins (§3 item 2), verbatim.
PINNED_STOPS = ["end-turn", "max-tokens", "model-refusal", "window-exhausted",
                "rate-limited", "overloaded", "network-failure", "timeout",
                "tool-error", "malformed-shape"]
# Stop keys session 4 added, each flagged in its notes.md (D15), and the
# one session 5b added: cap-unchecked, the pre-call check that could not
# run (cost-spine-005's Proposal, ratified at continue-twine-006).
ADDED_STOPS = ["cap-reached", "killed", "cap-unchecked"]


def raw_table() -> dict:
    """The table file as TOML data, fresh each call so a test can edit it."""
    with TRANSITIONS_TABLE.open("rb") as fh:
        return tomllib.load(fh)


def load(data: dict | None = None, manifest=None) -> transitions.Table:
    """The table checked against the real consumption manifest (or the one
    given), from `data` when a test edited it, else from the file."""
    manifest = manifest if manifest is not None else load_manifest()
    return transitions.load_table(TRANSITIONS_TABLE, manifest, data=data)


def drop_row(data: dict, axis: str, key: str) -> dict:
    before = len(data["row"])
    data["row"] = [r for r in data["row"] if (r["axis"], r["key"]) != (axis, key)]
    assert len(data["row"]) == before - 1, (axis, key)
    return data


def row_of(data: dict, axis: str, key: str) -> dict:
    return next(r for r in data["row"] if (r["axis"], r["key"]) == (axis, key))


def assert_total(test: unittest.TestCase, table_data: dict,
                 vocabularies: dict[str, list[str]]) -> None:
    """The test that fails by name, as a function so DetectorsFire can
    prove it fires. Its logic is its own — it reads the raw table data and
    the vocabularies, not twine.transitions' verdict — and one failure
    names every fault at once:

      - "<axis> '<key>' has no move" for a key of an axis without a row;
      - "<axis> '<key>' names the undeclared move '<move>'" for a row whose
        move is not a declared move with an actor and a description;
      - "<axis> '<key>' is not bale's spelling" for a row on a bale axis
        whose key is not in bale's vocabulary.
    """
    moves = {name for name, spec in table_data.get("move", {}).items()
             if isinstance(spec, dict) and spec.get("actor") in transitions.ACTORS
             and isinstance(spec.get("description"), str)
             and spec["description"].strip()}
    keys: dict[str, list[str]] = {}
    for name, spec in table_data.get("axis", {}).items():
        keys[name] = (list(vocabularies.get(name, [])) if spec.get("source") == "bale"
                      else list(spec.get("keys", [])))
    rows = {(r.get("axis"), r.get("key")): r.get("move") for r in table_data.get("row", [])}
    faults = []
    for axis, axis_keys in keys.items():
        for key in axis_keys:
            if (axis, key) not in rows:
                faults.append(f"{axis} {key!r} has no move")
    for (axis, key), move in rows.items():
        if move not in moves:
            faults.append(f"{axis} {key!r} names the undeclared move {move!r}")
        if axis in vocabularies and key not in vocabularies[axis]:
            faults.append(f"{axis} {key!r} is not bale's spelling")
    test.assertEqual(faults, [], "the transition table is not total:\n  "
                     + "\n  ".join(faults))


def manifest_vocabularies() -> dict[str, list[str]]:
    return {axis: list(v["values"]) for axis, v in load_manifest().vocabularies.items()}


# ---------------------------------------------------------------------------
# 2. The real table is total
# ---------------------------------------------------------------------------


class TheTableIsTotal(unittest.TestCase):

    def test_every_key_of_every_axis_has_a_declared_move(self):
        """D17's test: fails naming the axis and the key of any outcome,
        closure reason or stop without a move."""
        assert_total(self, raw_table(), manifest_vocabularies())

    def test_the_module_finds_no_problem(self):
        table = load()
        self.assertEqual([p.message for p in table.problems], [])
        self.assertTrue(table.ok)

    def test_four_axes_in_order(self):
        self.assertEqual([a.name for a in load().axes], list(AXES))

    def test_one_row_per_key_and_no_row_outside_the_keys(self):
        table = load()
        for axis in table.axes:
            with self.subTest(axis=axis.name):
                row_keys = [r.key for r in table.rows if r.axis == axis.name]
                self.assertEqual(sorted(row_keys), sorted(axis.keys))
                self.assertEqual(len(row_keys), len(set(row_keys)))

    def test_bale_axes_carry_exactly_bales_spellings(self):
        """The three bale axes' keys are bale 0.4.45's spellings, no more and
        no fewer, in bale's order — held to the probe's lists, not to the
        manifest alone."""
        table = load()
        for name in BALE_AXES:
            with self.subTest(axis=name):
                axis = table.axis(name)
                self.assertEqual(axis.source, "bale")
                self.assertEqual(list(axis.keys), BALE_VOCABULARIES[name])
                self.assertEqual(sorted(r.key for r in table.rows if r.axis == name),
                                 sorted(BALE_VOCABULARIES[name]))
        self.assertEqual({n: len(table.axis(n).keys) for n in BALE_AXES},
                         {"telemetry-outcome": 13, "closure-reason": 9,
                          "apply-outcome": 9})

    def test_null_is_not_a_closure_key(self):
        self.assertNotIn(None, load().axis("closure-reason").keys)
        self.assertNotIn("null", load().axis("closure-reason").keys)

    def test_the_table_is_written_against_the_pin(self):
        table = load()
        self.assertEqual((table.written_against, table.pin), (PIN, PIN))

    def test_no_axis_has_a_catch_all_key(self):
        for axis in load().axes:
            for key in axis.keys:
                self.assertNotIn(key.lower(), transitions.CATCH_ALL_KEYS,
                                 f"{axis.name} {key!r}")

    def test_no_move_is_unused(self):
        self.assertEqual(transitions.unused_moves(load()), [])


# ---------------------------------------------------------------------------
# 3. Its content: the pinned moves, actors, T12, the stop set
# ---------------------------------------------------------------------------


class TheMoves(unittest.TestCase):

    def setUp(self):
        self.table = load()
        self.rows = {(r.axis, r.key): r.move for r in self.table.rows}

    def test_the_two_moves_d17_ratified(self):
        """D17: a well-formed HOLD gets revert and repack; a malformed
        response, and a malformed shape, get respawn from the request."""
        self.assertEqual(self.rows[("telemetry-outcome", "held")], "revert-and-repack")
        self.assertEqual(self.rows[("apply-outcome", "held")], "revert-and-repack")
        self.assertEqual(self.rows[("closure-reason", "malformed_response")],
                         "respawn-from-request")
        self.assertEqual(self.rows[("stop", "malformed-shape")], "respawn-from-request")

    def test_every_move_has_exactly_one_actor_and_one_sentence(self):
        for move in self.table.moves.values():
            with self.subTest(move=move.name):
                self.assertIn(move.actor, ("twine", "operator", "planner"))
                self.assertTrue(move.description.endswith("."), move.description)
                self.assertIsNone(re.search(r"[.!?] [A-Z]", move.description),
                                  f"more than one sentence: {move.description}")
                self.assertTrue(move.grounds, "say where the move comes from")

    def test_no_move_has_twine_merge_or_apply_anything(self):
        """T12: a move twine performs never merges or applies; the one move
        that applies is the operator's, after twine handed the line back."""
        doing = re.compile(r"\b(merg\w*|appl(y|ies|ied|ying)|admit\w*)\b", re.I)
        for move in self.table.moves.values():
            if move.actor == "twine":
                with self.subTest(move=move.name):
                    self.assertIsNone(doing.search(move.description), move.description)
                    self.assertIsNone(doing.search(move.name), move.name)
        self.assertEqual(self.table.moves[self.rows[("apply-outcome", "dry-run")]].actor,
                         "operator")

    def test_a_move_that_needs_a_decision_is_never_twines(self):
        """N4: twine holds no intent. Every move whose description says
        something is decided, chosen or triaged names the planner or the
        operator."""
        deciding = re.compile(r"\b(decid\w*|triag\w*|choos\w*|rewords?)\b", re.I)
        for move in self.table.moves.values():
            if deciding.search(move.description):
                with self.subTest(move=move.name):
                    self.assertNotEqual(move.actor, "twine", move.description)

    def test_the_stop_set_is_the_brief_s_ten_plus_the_three_added(self):
        stop = list(self.table.axis("stop").keys)
        self.assertEqual(stop, PINNED_STOPS + ADDED_STOPS)
        self.assertEqual(self.table.axis("stop").source, "twine")

    def test_a_kill_closes_aborted_and_aborted_has_its_own_move(self):
        """D15: a kill leaves an aborted closure; the closure then has a row."""
        kill = self.table.moves[self.rows[("stop", "killed")]]
        self.assertIn("`aborted`", kill.description)
        self.assertIn(("closure-reason", "aborted"), self.rows)

    def test_cap_unchecked_is_the_operators_and_not_stop_at_cap(self):
        """Session 5b: a check that could not run has its own move, the
        operator's, distinct from the cap refusal's."""
        move = self.table.moves[self.rows[("stop", "cap-unchecked")]]
        self.assertEqual((move.name, move.actor), ("fix-and-resume", "operator"))
        self.assertNotEqual(move.name, self.rows[("stop", "cap-reached")])

    def test_unlocked_defers_to_its_closure_reason(self):
        move = self.table.moves[self.rows[("telemetry-outcome", "unlocked")]]
        self.assertIn("closure-reason", move.description)


# ---------------------------------------------------------------------------
# 4. The detectors fire
# ---------------------------------------------------------------------------


class DetectorsFire(unittest.TestCase):
    """Each fault, made on purpose in a copy of the table: assert_total
    (the test that fails by name) fails naming it, and the module reports
    it as a problem naming the same axis and key, or move."""

    def assert_named(self, data: dict, *needles: str,
                     vocabularies: dict[str, list[str]] | None = None) -> None:
        with self.assertRaises(AssertionError) as caught:
            assert_total(self, data, vocabularies or manifest_vocabularies())
        for needle in needles:
            self.assertIn(needle, str(caught.exception))

    def problems(self, data: dict, manifest=None) -> list[transitions.Problem]:
        table = load(data, manifest)
        self.assertFalse(table.ok)
        return table.problems

    def test_a_row_removed_is_named_on_every_axis(self):
        for axis, key in (("telemetry-outcome", "opened"),
                          ("closure-reason", "no_response"),
                          ("apply-outcome", "dry-run"), ("stop", "window-exhausted")):
            with self.subTest(axis=axis, key=key):
                data = drop_row(raw_table(), axis, key)
                self.assert_named(data, f"{axis} {key!r} has no move")
                self.assertEqual([(p.kind, p.axis, p.key) for p in self.problems(data)],
                                 [("missing-row", axis, key)])

    def test_an_undeclared_move_is_named(self):
        data = raw_table()
        row_of(data, "apply-outcome", "held")["move"] = "merge-it-anyway"
        self.assert_named(data, "apply-outcome 'held' names the undeclared move "
                                "'merge-it-anyway'")
        [problem] = self.problems(data)
        self.assertEqual((problem.kind, problem.axis, problem.key, problem.move),
                         ("undeclared-move", "apply-outcome", "held", "merge-it-anyway"))
        self.assertIn("'merge-it-anyway'", problem.message)

    def test_a_deleted_move_names_every_row_that_used_it(self):
        data = raw_table()
        del data["move"]["retry-with-backoff"]
        named = {p.key for p in self.problems(data) if p.kind == "undeclared-move"}
        self.assertEqual(named, {"rate-limited", "overloaded", "network-failure",
                                 "timeout"})

    def test_an_invented_key_on_a_bale_axis_is_named(self):
        """The two spellings carry-bale-002's doubles invented, `refused`
        and `hold`, are exactly what this detector exists to catch."""
        for axis, key in (("apply-outcome", "refused"), ("apply-outcome", "hold"),
                          ("telemetry-outcome", "default"),
                          ("closure-reason", "timeout")):
            with self.subTest(axis=axis, key=key):
                data = raw_table()
                data["row"].append({"axis": axis, "key": key, "move": "record-closed",
                                    "means": "invented"})
                self.assert_named(data, f"{axis} {key!r} is not bale's spelling")
                [problem] = self.problems(data)
                self.assertEqual((problem.kind, problem.axis, problem.key),
                                 ("unknown-key", axis, key))
                self.assertIn(f"bale {PIN}'s spellings", problem.message)

    def test_a_misspelled_bale_key_is_both_invented_and_missing(self):
        """`no-response` for bale's `no_response`: the row is not bale's
        spelling, and bale's spelling has no row."""
        data = raw_table()
        row_of(data, "closure-reason", "no_response")["key"] = "no-response"
        self.assert_named(data, "closure-reason 'no-response' is not bale's spelling",
                          "closure-reason 'no_response' has no move")
        kinds = sorted((p.kind, p.key) for p in self.problems(data))
        self.assertEqual(kinds, [("missing-row", "no_response"),
                                 ("unknown-key", "no-response")])

    def test_a_duplicate_row_is_named(self):
        data = raw_table()
        data["row"].append(dict(row_of(data, "stop", "timeout"), move="split-goal"))
        self.assertEqual([(p.kind, p.axis, p.key) for p in self.problems(data)],
                         [("duplicate-row", "stop", "timeout")])

    def test_a_move_without_exactly_one_actor_is_not_declared(self):
        for actor in ("nobody", "twine operator", None, ["twine", "planner"]):
            with self.subTest(actor=actor):
                data = raw_table()
                if actor is None:
                    del data["move"]["record-closed"]["actor"]
                else:
                    data["move"]["record-closed"]["actor"] = actor
                self.assert_named(data, "names the undeclared move 'record-closed'")
                [problem] = self.problems(data)
                self.assertEqual((problem.kind, problem.move),
                                 ("malformed-move", "record-closed"))

    def test_a_move_without_a_description_is_not_declared(self):
        data = raw_table()
        data["move"]["split-goal"]["description"] = "  "
        self.assertEqual([(p.kind, p.move) for p in self.problems(data)],
                         [("malformed-move", "split-goal")])

    def test_a_catch_all_stop_key_is_refused_and_needs_a_row(self):
        data = raw_table()
        data["axis"]["stop"]["keys"].append("other")
        kinds = sorted((p.kind, p.key) for p in self.problems(data))
        self.assertEqual(kinds, [("catch-all-key", "other"), ("missing-row", "other")])

    def test_a_bale_axis_may_not_declare_its_own_keys(self):
        data = raw_table()
        data["axis"]["apply-outcome"]["keys"] = BALE_VOCABULARIES["apply-outcome"]
        kinds = {p.kind for p in self.problems(data)}
        self.assertIn("malformed-axis", kinds)

    def test_a_row_on_an_undeclared_axis_is_named(self):
        data = raw_table()
        data["row"].append({"axis": "provider", "key": "overloaded",
                            "move": "retry-with-backoff", "means": "x"})
        self.assertEqual([(p.kind, p.axis) for p in self.problems(data)],
                         [("unknown-axis", "provider")])

    def test_a_pin_bump_adding_a_spelling_is_named_until_it_has_a_row(self):
        """D4 carried through to the moves: re-read vocabularies with a new
        outcome make the table not total, naming the new key."""
        manifest = load_manifest()
        bumped = copy.deepcopy(manifest.vocabularies)
        bumped["telemetry-outcome"]["values"].append("newly-invented-by-bale")
        manifest = type(manifest)(manifest.path, manifest.pin, manifest.schemas,
                                  manifest.surfaces, manifest.data, bumped)
        self.assertEqual([(p.kind, p.axis, p.key) for p in self.problems(raw_table(),
                                                                          manifest)],
                         [("missing-row", "telemetry-outcome", "newly-invented-by-bale")])
        self.assert_named(raw_table(), "telemetry-outcome 'newly-invented-by-bale' has "
                          "no move", vocabularies={a: list(v["values"])
                                                   for a, v in bumped.items()})

    def test_a_vocabulary_without_an_axis_and_an_axis_without_a_vocabulary(self):
        manifest = load_manifest()
        vocab = copy.deepcopy(manifest.vocabularies)
        vocab["command"] = {"axis": "command", "values": ["apply", "retry"],
                            "home": "schemas/telemetry-record.schema.json"}
        del vocab["closure-reason"]
        edited = type(manifest)(manifest.path, manifest.pin, manifest.schemas,
                                manifest.surfaces, manifest.data, vocab)
        kinds = sorted((p.kind, p.axis) for p in self.problems(raw_table(), edited))
        self.assertIn(("missing-axis", "command"), kinds)
        self.assertIn(("missing-vocabulary", "closure-reason"), kinds)
        # Each closure-reason row is then a key the (empty) axis lacks.
        self.assertIn(("unknown-key", "closure-reason"), kinds)

    def test_no_manifest_means_no_bale_keys_never_a_default(self):
        table = transitions.load_table(TRANSITIONS_TABLE, None,
                                       "the consumption manifest is unusable: x")
        self.assertFalse(table.ok)
        missing = {p.axis for p in table.problems if p.kind == "missing-vocabulary"}
        self.assertEqual(missing, set(BALE_AXES))
        self.assertTrue(all("unusable: x" in p.message for p in table.problems
                            if p.kind == "missing-vocabulary"))

    def test_an_unreadable_table_is_unusable(self):
        table = transitions.load_table(Path("/nonexistent/transitions.toml"),
                                       load_manifest())
        self.assertEqual([p.kind for p in table.problems], ["unusable"])


# ---------------------------------------------------------------------------
# 5. `twine transitions`, the verb
# ---------------------------------------------------------------------------


def one_line(test: unittest.TestCase, stdout: str) -> dict:
    lines = stdout.split("\n")
    test.assertEqual((len(lines), lines[1]), (2, ""), f"one JSON line: {stdout!r}")
    obj = json.loads(lines[0])
    test.assertEqual(obj["command"], "transitions")
    return obj


def write_table(directory: Path, data: dict) -> Path:
    """`data` as a TOML table file — written by a minimal emitter for the
    shapes the table uses (strings, ints, string lists, tables, arrays of
    tables), so a test can hand the verb a broken table by path."""
    def value(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, int):
            return str(v)
        if isinstance(v, str):
            return json.dumps(v)
        if isinstance(v, list):
            return "[" + ", ".join(value(x) for x in v) + "]"
        raise TypeError(v)

    def scalars(spec: dict) -> list[str]:
        return [f"{json.dumps(k)} = {value(v)}" for k, v in spec.items()]

    out = ["[table]", *scalars(data.get("table", {}))]
    for group in ("axis", "move"):
        for name, spec in data.get(group, {}).items():
            out += ["", f"[{group}.{json.dumps(name)}]", *scalars(spec)]
    for row in data.get("row", []):
        out += ["", "[[row]]", *scalars(row)]
    path = directory / "transitions.toml"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    with path.open("rb") as fh:
        assert tomllib.load(fh) == data, "write_table must round-trip"
    return path


class TheVerb(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="twine-transitions-")
        self.dir = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def test_json_twin_as_a_subprocess(self):
        run = run_cli("transitions", "--json")
        obj = one_line(self, run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["reason"], obj["problems"]),
                         (0, True, None, []))
        self.assertEqual(len(obj["rows"]), 13 + 9 + 9 + 13)
        self.assertEqual(obj["counts"]["rows"], 44)
        for row in obj["rows"]:
            for key in ("axis", "key", "move"):
                self.assertIsInstance(row[key], str, row)
            self.assertIn(row["move"], obj["moves"])
        for name, move in obj["moves"].items():
            self.assertIsInstance(move["actor"], str, name)
            self.assertIsInstance(move["description"], str, name)
        self.assertEqual([a["name"] for a in obj["axes"]], list(AXES))
        self.assertEqual((obj["written_against"], obj["pin"]), (PIN, PIN))
        self.assertEqual(obj["table"], str(TRANSITIONS_TABLE))
        self.assertNotIn("Traceback", run.stderr)

    def test_rows_render_in_axis_then_vocabulary_order(self):
        obj = one_line(self, run_cli("transitions", "--json").stdout)
        expected = [(a, k) for a in BALE_AXES for k in BALE_VOCABULARIES[a]]
        expected += [("stop", k) for k in PINNED_STOPS + ADDED_STOPS]
        self.assertEqual([(r["axis"], r["key"]) for r in obj["rows"]], expected)

    def test_human_mode_prints_every_row_and_move(self):
        run = run_cli("transitions")
        self.assertEqual(run.code, 0)
        self.assertTrue(run.stdout.startswith("transition table "), run.stdout[:80])
        self.assertIn(": ok\n", run.stdout.split("\n", 1)[0] + "\n")
        for axis in AXES:
            self.assertIn(f"\n{axis}  (", run.stdout)
        self.assertIn("held", run.stdout)
        self.assertIn("-> revert-and-repack", run.stdout)
        self.assertIn("\nmoves\n", run.stdout)
        for line in run.stdout.splitlines():
            self.assertFalse(line.startswith("{"))

    def test_a_broken_table_is_exit_1_naming_each_fault(self):
        data = drop_row(raw_table(), "closure-reason", "aborted")
        row_of(data, "stop", "killed")["move"] = "no-such-move"
        data["row"].append({"axis": "apply-outcome", "key": "refused",
                            "move": "record-closed", "means": "invented"})
        path = write_table(self.dir, data)
        run = run_cli("transitions", "--table", str(path), "--json")
        obj = one_line(self, run.stdout)
        self.assertEqual((run.code, obj["ok"]), (1, False))
        self.assertEqual(sorted((p["kind"], p["axis"], p["key"]) for p in obj["problems"]),
                         [("missing-row", "closure-reason", "aborted"),
                          ("undeclared-move", "stop", "killed"),
                          ("unknown-key", "apply-outcome", "refused")])
        for needle in ("closure-reason 'aborted'", "'no-such-move'",
                       "apply-outcome 'refused'"):
            self.assertIn(needle, obj["reason"])
        self.assertNotIn("Traceback", run.stderr)
        human = run_cli("transitions", "--table", str(path))
        self.assertEqual(human.code, 1)
        self.assertIn("NOT OK", human.stdout.splitlines()[0])
        self.assertIn("missing-row: closure-reason 'aborted' has no row", human.stdout)

    def test_an_unreadable_table_is_exit_1_not_a_traceback(self):
        run = run_cli("transitions", "--table", str(self.dir / "absent.toml"), "--json")
        obj = one_line(self, run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["problems"][0]["kind"]),
                         (1, False, "unusable"))
        self.assertNotIn("Traceback", run.stderr)

    def test_reads_no_bale_runs_nothing_reaches_nothing(self):
        """The verb's ok is the table's alone: in-process with a seam that
        refuses to run, a `which` that refuses to look and an environment
        naming a bale at another version, it is ok, and none was touched."""
        touched = []

        def no_run(argv, **kwargs):
            touched.append(("run", list(argv)))
            raise RunError("transitions must not run anything")

        def no_which(name):
            touched.append(("which", name))
            return None

        roots = TempRoots()
        self.addCleanup(roots.cleanup)
        for env in ({}, {"TWINE_BALE_ROOT": str(roots.other)},
                    {"TWINE_BALE_ROOT": str(roots.absent)}):
            with self.subTest(env=env):
                out, err = io.StringIO(), io.StringIO()
                ctx = Context(env=env, stdout=out, stderr=err, which=no_which,
                              stdin=io.BytesIO(b""), run=no_run)
                code = main(["transitions", "--json"], ctx=ctx)
                obj = one_line(self, out.getvalue())
                self.assertEqual((code, obj["ok"]), (0, True))
        self.assertEqual(touched, [])

    def test_the_verb_and_the_module_import_nothing_that_runs_or_reaches_out(self):
        forbidden = {"subprocess", "os", "shutil", "socket", "urllib", "http",
                     "multiprocessing", "pty", "asyncio", "ctypes", "twine.process"}
        for rel in ("twine/transitions.py", "twine/commands/transitions.py"):
            with self.subTest(file=rel):
                tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
                names = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        names.update(a.name for a in node.names)
                        names.update(a.name.split(".")[0] for a in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        names.add(node.module)
                        names.add(node.module.split(".")[0])
                self.assertFalse(names & forbidden, names & forbidden)


if __name__ == "__main__":
    unittest.main()

"""twine-run-telemetry: `runs.jsonl`, `twine stats`, `twine transcript` and the
session's cost file on every apply line (cli-contract.md §18.7a, §20, §21).

How it is driven, as tests/test_run.py is: the pieces in-process where a
child shows nothing more (`twine.runs`, `twine.cost`, `twine.transcript_view`),
and `bin/twine` as a child process against the stub bale (a double, never
bale) with the fake adapter for what a run leaves behind — one `runs.jsonl`
line per run on every outcome, the cost file beside an apply line. No model
anywhere, and the key (a sentinel) is never in a line.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from twine import bale, cost, kill, runs, spend, transcript_view
from twine.commands import run as run_verb
from twine.runtime import loop as runloop

from tests.helpers import (DOUBLE_MODEL, DOUBLE_MODEL_UNPRICED, SpendStateDouble, run_cli,
                           run_inprocess)
from tests.test_resume import QUESTION, ResumeBed, ResumeCase
from tests.test_run import (DELIVER_SHELL, DRIFT, SENTINEL_KEY, SID, Bed, BedCase, LoopBed,
                            light, request_tarball, stop, tools, usage)

DELIVER = [tools(("write_file", {"path": "draft.txt", "content": "draft\n"}), n=1),
           tools(("shell", {"command": DELIVER_SHELL}), n=2),
           tools(("deliver", {"tarball": "response.tar.gz"}), n=3)]


def line_of(bed: Bed) -> list[dict]:
    """Every line of the bed's runs.jsonl, parsed."""
    path = bed.state / runs.RUNS_NAME
    return [json.loads(raw) for raw in path.read_text(encoding="utf-8").splitlines()]


def a_record(**changes) -> dict:
    """A valid run record the tests edit: a delivered `run` of `SID`."""
    record = {
        "record_version": 1, "sid": SID, "command": "run", "desk": None,
        "started_at": "2026-10-15T10:00:00+00:00", "ended_at": "2026-10-15T10:00:05+00:00",
        "wall_seconds": 5.0, "outcome": "delivered", "stop": None,
        "move": "operator-applies", "actor": "operator", "shape": None, "reason": None,
        "turns": 3, "tool_calls": 2, "retries": 0, "continuations": 0,
        "usage": {"input": 300, "output": 60, "thinking": None, "cache_read": 0,
                  "cache_write": 0},
        "cost_usd": 0.5, "cap_usd": 5.0, "adapter": "fake", "model": "fake", "window": None,
        "resumed_from": None, "rewarm": None,
        "tools": {"shell": {"calls": 2, "errors": 1, "seconds": 1.5}},
        "events": {"window_warned": 0, "continuations": 0, "retries": 0, "heartbeats": 0,
                   "transcript_faults": 0, "inflight_error": 0, "group_survivors": 0},
        "transcript": None, "sandbox": None, "inflight": "removed", "cost_file": None,
        runs.APPLY: None}
    record.update(changes)
    return record


def write_lines(path: Path, *records) -> None:
    path.write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n"
                            for r in records), encoding="utf-8")


def tree(path: Path) -> dict[str, str]:
    """Every file under `path` with its sha256 and mode, and every directory:
    what a write-nothing verb must leave as it found it."""
    seen = {}
    for p in sorted(path.rglob("*")):
        rel = p.relative_to(path).as_posix()
        if p.is_dir():
            seen[rel + "/"] = oct(p.stat().st_mode)
        else:
            seen[rel] = hashlib.sha256(p.read_bytes()).hexdigest() + oct(p.stat().st_mode)
    return seen


# ---------------------------------------------------------------------------
# 1. The cost file
# ---------------------------------------------------------------------------


class TheCostFile(unittest.TestCase):

    def setUp(self):
        self.spent = SpendStateDouble()
        self.addCleanup(self.spent.cleanup)
        self.state = self.spent.path

    def test_bale_s_six_keys_summed_over_every_record_of_the_sid(self):
        self.spent.call("s-1", input=100, output=20, cache_read=50, cache_write=10)
        self.spent.call("s-1", input=1, output=2, thinking=7)
        self.spent.call("other", input=999, output=999)
        path = cost.write_cost_file(self.state, "s-1")
        self.assertEqual(path, self.state / "cost" / "s-1.json")
        obj = json.loads(path.read_text())
        self.assertEqual(tuple(obj), cost.KEYS)
        self.assertEqual(tuple(obj), ("tokens_in", "tokens_out", "usd", "model_tier",
                                      "calls", "models"))
        # tokens_in: input + cache reads + cache writes; tokens_out: output + thinking
        self.assertEqual((obj["tokens_in"], obj["tokens_out"]), (100 + 50 + 10 + 1, 20 + 2 + 7))
        self.assertEqual((obj["model_tier"], obj["calls"], obj["models"]),
                         (None, 2, [DOUBLE_MODEL]))
        # priced as `spend totals` prices it: the thinking at the output price
        totals = spend.spend_totals(self.state, self.spent.prices, "s-1")
        self.assertEqual(obj["usd"], spend.usd(totals.sessions[0].cost_usd))

    def test_the_mode_the_directory_and_a_snapshot_replaced_whole(self):
        self.spent.call("s-1", input=100)
        path = cost.write_cost_file(self.state, "s-1")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        first = json.loads(path.read_text())
        self.spent.call("s-1", input=100)
        again = cost.write_cost_file(self.state, "s-1")
        self.assertEqual(again, path)
        self.assertEqual(json.loads(path.read_text())["calls"], 2)
        self.assertEqual(first["calls"], 1, "a snapshot, not a log")
        self.assertEqual(os.listdir(path.parent), ["s-1.json"], "no temporary file is left")

    def test_the_models_are_sorted_and_unique(self):
        for model in ("zz-model", DOUBLE_MODEL, "zz-model"):
            self.spent.call("s-1", model=model, input=1)
        self.assertEqual(cost.session_cost(self.state, "s-1").as_json()["models"],
                         [DOUBLE_MODEL, "zz-model"])

    def test_usd_is_null_when_any_record_is_unpriced_and_the_file_is_still_written(self):
        self.spent.call("s-1", input=100)
        self.spent.call("s-1", model=DOUBLE_MODEL_UNPRICED, input=100)
        obj = json.loads(cost.write_cost_file(self.state, "s-1").read_text())
        self.assertEqual((obj["usd"], obj["calls"]), (None, 2))

    def test_no_price_file_is_a_null_usd_not_a_failure(self):
        bare = SpendStateDouble(prices=None)
        self.addCleanup(bare.cleanup)
        bare.call("s-1", input=100)
        obj = json.loads(cost.write_cost_file(bare.path, "s-1").read_text())
        self.assertEqual((obj["usd"], obj["tokens_in"]), (None, 100))

    def test_a_session_with_no_records_costs_nothing(self):
        obj = json.loads(cost.write_cost_file(self.state, "never-spent").read_text())
        self.assertEqual(obj, {"tokens_in": 0, "tokens_out": 0, "usd": 0.0,
                               "model_tier": None, "calls": 0, "models": []})

    def test_a_stream_that_does_not_parse_is_never_summed(self):
        self.spent.call("s-1", input=100)
        with open(self.spent.stream, "a") as fh:
            fh.write("not json\n")
        with self.assertRaises(cost.CostFileError) as raised:
            cost.write_cost_file(self.state, "s-1")
        self.assertIn("cannot be summed", str(raised.exception))
        self.assertFalse((self.state / "cost").exists(), "nothing is written for a guess")

    def test_a_directory_that_cannot_be_made_is_named(self):
        self.spent.call("s-1", input=100)
        (self.state / "cost").write_text("a file where the directory should be")
        with self.assertRaises(cost.CostFileError) as raised:
            cost.write_cost_file(self.state, "s-1")
        self.assertIn("cannot be written", str(raised.exception))

    def test_a_sid_that_is_not_one_is_refused(self):
        with self.assertRaises(cost.CostFileError):
            cost.write_cost_file(self.state, "../escape")

    def test_the_costed_line_and_its_fallback(self):
        self.spent.call("s-1", input=100)
        costed = cost.costed_apply_line(self.state, "s-1", "/t/a tarball.tar.gz")
        self.assertEqual(costed.line, f"bale apply '/t/a tarball.tar.gz' --cost-file "
                                      f"{self.state}/cost/s-1.json")
        self.assertEqual((costed.path, costed.error), (self.state / "cost" / "s-1.json", None))
        (self.state / "cost" / "s-1.json").unlink()
        (self.state / "cost").rmdir()
        (self.state / "cost").write_text("blocked")
        with self.assertLogs("twine.cost", "WARNING"):
            plain = cost.costed_apply_line(self.state, "s-1", "/t/r.tar.gz")
        self.assertEqual(plain.line, "bale apply /t/r.tar.gz")
        self.assertIsNone(plain.path)
        self.assertIn("cannot be written", plain.error)

    def test_the_line_is_built_beside_apply_line(self):
        self.assertEqual(bale.apply_cost_line("/t/r.tar.gz", "/s/cost/x.json"),
                         "bale apply /t/r.tar.gz --cost-file /s/cost/x.json")
        self.assertEqual(bale.apply_cost_line("/t/a b.tar.gz", "/s d/x.json"),
                         "bale apply '/t/a b.tar.gz' --cost-file '/s d/x.json'")
        self.assertNotIn("--cost-file", " ".join(
            bale.dry_run_argv(Path("/r/bin/bale"), "/t/r.tar.gz")))


# ---------------------------------------------------------------------------
# 2. The record, its file and the aggregation
# ---------------------------------------------------------------------------


class TheRunsRecord(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="twine-runs-")
        self.addCleanup(self._dir.cleanup)
        self.state = Path(self._dir.name) / "state"

    def test_the_keys_are_pinned_whole_and_in_order(self):
        self.assertEqual(
            runs.KEYS,
            ("record_version", "sid", "command", "desk", "started_at", "ended_at",
             "wall_seconds", "outcome", "stop", "move", "actor", "shape", "reason", "turns",
             "tool_calls", "retries", "continuations", "usage", "cost_usd", "cap_usd",
             "adapter", "model", "window", "resumed_from", "rewarm", "tools", "events",
             "transcript", "sandbox", "inflight", "cost_file", "apply"))
        self.assertEqual(tuple(a_record()), runs.KEYS)
        self.assertEqual(runs.record_faults(a_record()), [])
        self.assertEqual(runs.EVENT_KEYS, ("window_warned", "continuations", "retries",
                                           "heartbeats", "transcript_faults", "inflight_error",
                                           "group_survivors"))

    def test_the_eight_outcomes_are_the_loop_s(self):
        self.assertEqual(runs.OUTCOMES, runloop.OUTCOMES)

    def test_a_line_is_judged_against_the_record(self):
        record = a_record()
        shuffled = {k: record[k] for k in reversed(list(record))}
        self.assertIn("the keys are not in the record's order", runs.record_faults(shuffled)[0])
        self.assertTrue(runs.record_faults({k: v for k, v in record.items() if k != "sid"}))
        for bad in ({"outcome": "won"}, {"command": "kill"}, {"record_version": 2},
                    {"turns": "3"}, {"turns": True}, {"started_at": "yesterday"},
                    {"started_at": "2026-10-15T10:00:00"}, {"wall_seconds": None},
                    {"usage": {"input": 1}}, {"tools": {"shell": {"calls": 1}}},
                    {"events": {}}, {"inflight": "gone"}, {runs.APPLY: "applied"},
                    {"desk": "desk-2"}, {"window": {"size": 1}}):
            with self.subTest(bad=bad):
                self.assertTrue(runs.record_faults(a_record(**bad)), bad)
        self.assertEqual(runs.record_faults([]), ["not a JSON object"])

    def test_one_append_creates_the_file_0600_and_never_rewrites(self):
        path = runs.append_run(self.state, a_record())
        self.assertEqual(path, self.state / "runs.jsonl")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o700)
        runs.append_run(self.state, a_record(sid="other", outcome="ended"))
        lines = path.read_text().splitlines()
        self.assertEqual([json.loads(l)["sid"] for l in lines], [SID, "other"])
        self.assertEqual(lines[0], json.dumps(a_record()), "the first line is as written")

    def test_a_malformed_record_writes_nothing(self):
        with self.assertRaises(ValueError):
            runs.append_run(self.state, a_record(outcome="won"))
        self.assertFalse((self.state / "runs.jsonl").exists())

    def test_a_torn_last_line_is_ended_not_glued_onto(self):
        runs.append_run(self.state, a_record())
        path = self.state / "runs.jsonl"
        with open(path, "ab") as fh:
            fh.write(b'{"record_version": 1, "sid": "to')       # a write torn by a crash
        runs.append_run(self.state, a_record(sid="after"))
        read = runs.read_runs(path)
        self.assertEqual([r["sid"] for _, r in read.records], [SID, "after"])
        self.assertEqual(len(read.faults), 1)
        self.assertTrue(read.faults[0].startswith("line 2: not JSON"), read.faults)

    def test_reading_names_every_line_that_is_not_a_record_and_goes_on(self):
        path = self.state
        path.mkdir()
        path = path / "runs.jsonl"
        write_lines(path, a_record(), "", "not json", "[1]", {"record_version": 1},
                    '{"sid": "a", "sid": "b"}', a_record(sid="last"))
        read = runs.read_runs(path)
        self.assertEqual((read.present, read.lines, len(read.records)), (True, 7, 2))
        self.assertEqual([f.split(":")[0] for f in read.faults],
                         ["line 2", "line 3", "line 4", "line 5", "line 6"])
        self.assertIn("blank", read.faults[0])
        self.assertIn("not JSON", read.faults[1])
        self.assertIn("not a run record", read.faults[3])
        self.assertIn("duplicate key", read.faults[4])
        path.write_bytes(b"\xff\xfe\n")
        self.assertIn("not UTF-8", runs.read_runs(path).faults[0])

    def test_an_absent_file_is_empty_and_an_unreadable_one_says_why(self):
        read = runs.read_runs(self.state / "runs.jsonl")
        self.assertEqual((read.present, read.lines, read.records, read.faults), (False, 0, [], []))
        (self.state / "runs.jsonl").mkdir(parents=True)        # a directory, not a file
        self.assertIn("cannot be read", runs.read_runs(self.state / "runs.jsonl").unreadable)


class TheAggregate(unittest.TestCase):

    def records(self) -> list[dict]:
        return [
            a_record(),
            a_record(sid="two", outcome="ended", command="resume", turns=1, tool_calls=0,
                     cost_usd=0.25, wall_seconds=2.0, started_at="2026-10-16T09:00:00+00:00",
                     tools={}),
            a_record(sid="three", outcome="delivered", turns=5, cost_usd=None,
                     wall_seconds=11.0, started_at="2026-10-17T23:59:59+00:00",
                     tools={"shell": {"calls": 3, "errors": 0, "seconds": 0.5},
                            "deliver": {"calls": 1, "errors": 0, "seconds": 0.001}}),
            a_record(sid="three", outcome="cap-reached", command="resume", turns=0,
                     tool_calls=0, retries=2, cost_usd=0.0, wall_seconds=0.5, tools={},
                     started_at="2026-10-18T00:00:00+02:00"),
        ]

    def file(self, *extra: str) -> runs.RunsFile:
        tmp = tempfile.TemporaryDirectory(prefix="twine-agg-")
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "runs.jsonl"
        write_lines(path, *self.records(), *extra)
        return runs.read_runs(path)

    def test_the_sums_and_the_counts(self):
        report = runs.aggregate(self.file())
        self.assertEqual(list(report), ["runs", "faults", "sessions", "by_outcome",
                                        "by_command", "turns", "tool_calls", "retries",
                                        "cost_usd", "unpriced_runs", "wall_seconds",
                                        "by_tool", "delivered"])
        self.assertEqual((report["runs"], report["faults"], report["sessions"]), (4, [], 3))
        self.assertEqual(report["by_outcome"],
                         {"delivered": 2, "suspended": 0, "ended": 1, "stopped": 0,
                          "killed": 0, "cap-reached": 1, "cap-unchecked": 0, "refused": 0})
        self.assertEqual(list(report["by_outcome"]), list(runs.OUTCOMES))
        self.assertEqual(report["by_command"], {"run": 2, "resume": 2})
        self.assertEqual((report["turns"], report["tool_calls"], report["retries"]), (9, 4, 2))
        self.assertEqual((report["cost_usd"], report["unpriced_runs"]), (0.75, 1))
        self.assertEqual(report["wall_seconds"], 18.5)
        self.assertEqual(report["by_tool"],
                         {"deliver": {"calls": 1, "errors": 0, "seconds": 0.001},
                          "shell": {"calls": 5, "errors": 1, "seconds": 2.0}})
        # the means are over the delivered runs; the cost's over those that were priced
        self.assertEqual(report["delivered"],
                         {"runs": 2, "mean_cost_usd": 0.5, "mean_turns": 4.0,
                          "mean_wall_seconds": 8.0})

    def test_nothing_delivered_means_null_means(self):
        report = runs.aggregate(runs.RunsFile(Path("/nowhere")))
        self.assertEqual(report["delivered"], {"runs": 0, "mean_cost_usd": None,
                                               "mean_turns": None, "mean_wall_seconds": None})
        self.assertEqual((report["runs"], report["cost_usd"], report["by_tool"]), (0, 0.0, {}))
        self.assertEqual(set(report["by_outcome"].values()), {0})

    def test_since_is_inclusive_and_against_started_at_in_utc(self):
        # the fourth run started 2026-10-18T00:00+02:00, which is the 17th in UTC
        self.assertEqual(runs.aggregate(self.file(), since=runs.parse_since("2026-10-17"))["runs"], 2)
        self.assertEqual(runs.aggregate(self.file(), since=runs.parse_since("2026-10-18"))["runs"], 0)
        self.assertEqual(runs.aggregate(self.file(), since=runs.parse_since("2026-10-16"))["runs"], 3)
        self.assertEqual(runs.aggregate(self.file(), since=runs.parse_since("2026-10-15"))["runs"], 4)

    def test_sid_and_since_intersect(self):
        file = self.file()
        self.assertEqual(runs.aggregate(file, sid="three")["runs"], 2)
        both = runs.aggregate(file, sid="three", since=runs.parse_since("2026-10-18"))
        self.assertEqual(both["runs"], 0)
        both = runs.aggregate(file, sid="three", since=runs.parse_since("2026-10-17"))
        self.assertEqual((both["runs"], both["sessions"]), (2, 1))

    def test_a_bad_line_is_a_fault_and_never_a_member(self):
        report = runs.aggregate(self.file("garbage"))
        self.assertEqual(report["runs"], 4)
        self.assertEqual(len(report["faults"]), 1)
        self.assertTrue(report["faults"][0].startswith("line 5: "))

    def test_since_is_an_iso_date_and_nothing_else(self):
        for bad in ("2026-10", "20261015", "2026-13-01", "yesterday", "2026-10-15T00:00", ""):
            with self.assertRaises(ValueError, msg=bad):
                runs.parse_since(bad)


# ---------------------------------------------------------------------------
# 3. The story
# ---------------------------------------------------------------------------


class TheStory(unittest.TestCase):

    def entry(self, obj: dict, number: int = 1) -> dict:
        return transcript_view.story_entry(number, obj)

    def test_each_kind_has_its_summary(self):
        shown = {
            "run-start": ({"adapter": "fake", "model": "m", "window": {"size": 1000},
                           "resumed_from": None}, "fake, model m, window 1000, not resumed"),
            "check": ({"call": 1, "input_estimate": 50, "input_basis": "counted",
                       "check": {"admitted": True}}, "estimate 50 (counted), admitted"),
            "request": ({"call": 2, "messages_total": 5, "appended": [1, 2], "sent": False},
                        "5 messages, 2 appended, sent: false"),
            "turn": ({"call": 1, "turn": {"stop": "end-turn", "tool_calls": []}},
                     "stop end-turn"),
            "window": ({"call": 1, "used": 700, "size": 1000, "warned": True},
                       "700 of 1000 (warned)"),
            "tool-result": ({"call": 1, "result": {"is_error": False, "content": "abcde"}},
                            "ok, 5 characters"),
            "move": ({"call": 1, "move": "retry-with-backoff", "did": "waited"},
                     "retry-with-backoff: waited"),
            "retry": ({"call": 1, "stop": "rate-limited", "attempt": 2, "wait_seconds": 4},
                      "rate-limited, attempt 2, wait 4s"),
            "abort": ({"path": "/s/abort/x.json"}, "/s/abort/x.json"),
            "adapter-error": ({"call": 1, "error": "BoundaryError", "message": "bad"},
                              "BoundaryError: bad"),
            "run-end": ({"twin": {"outcome": "stopped", "stop": "max-tokens",
                                  "move": "continue-turn"}},
                        "stopped, stop max-tokens, move continue-turn"),
        }
        for kind, (obj, summary) in shown.items():
            with self.subTest(kind=kind):
                got = self.entry({"seq": 7, "kind": kind, **obj})
                self.assertEqual(got["summary"], summary)
                self.assertEqual(got["seq"], 7)
        self.assertEqual(self.entry({"seq": 7, "kind": "turn", "call": 2, "turn": {
            "tool_calls": [{"name": "shell"}, {"name": "deliver"}]}})["summary"],
            "asks for shell, deliver")
        self.assertEqual(self.entry({"seq": 1, "kind": "run-start", "adapter": "x", "model": "y",
                                     "window": {"size": None}, "resumed_from": 12}
                                    )["summary"], "x, model y, window unknown, resumed from line 12")
        self.assertEqual(self.entry({"seq": 1, "kind": "check", "input_estimate": 1,
                                     "input_basis": "estimated",
                                     "check": {"admitted": False, "stop": "cap-reached"}}
                                    )["summary"], "estimate 1 (estimated), refused (cap-reached)")
        self.assertEqual(self.entry({"seq": 9, "kind": "run-end", "internal_error": True}
                                    )["summary"], "internal error")

    def test_a_tool_call_names_its_argument_cut_at_80_characters(self):
        command = "echo " + "x" * 200
        got = self.entry({"seq": 1, "kind": "tool-call", "call": 1, "name": "shell",
                          "arguments": {"command": command}})
        self.assertEqual(got["summary"], "shell " + command[:80] + "...")
        got = self.entry({"seq": 1, "kind": "tool-call", "call": 1, "name": "read_file",
                          "arguments": {"path": "request/README.md"}})
        self.assertEqual(got["summary"], "read_file request/README.md")
        multi = self.entry({"seq": 1, "kind": "tool-call", "call": 1, "name": "shell",
                            "arguments": {"command": "a\nb"}})
        self.assertEqual(multi["summary"], "shell a b", "one line whatever the argument held")

    def test_the_call_is_null_where_the_line_has_none_and_the_line_reads_so(self):
        got = self.entry({"seq": 3, "kind": "run-end", "twin": {"outcome": "ended"}})
        self.assertEqual((got["call"], transcript_view.story_line(got)), (None, "3 run-end ended"))
        called = self.entry({"seq": 4, "kind": "tool-result", "call": 2,
                             "result": {"is_error": True, "content": ""}})
        self.assertEqual(transcript_view.story_line(called), "4 tool-result [call 2] error, 0 characters")
        self.assertEqual(list(called), ["seq", "kind", "call", "summary"])

    def test_a_kind_it_does_not_know_is_listed_with_no_summary(self):
        got = self.entry({"seq": 2, "kind": "from-the-future"})
        self.assertEqual((got["summary"], transcript_view.story_line(got)),
                         ("", "2 from-the-future"))

    def test_reading_numbers_the_lines_and_reports_the_ones_that_are_not_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_bytes(b'{"seq": 1, "kind": "run-start"}\n\nnope\n[2]\n'
                             b'{"seq": 5, "kind": "run-end"}\n{"seq": 6, "ki')
            got = transcript_view.read_transcript(path)
        self.assertEqual((got.present, got.lines, [n for n, _ in got.entries]),
                         (True, 6, [1, 5]))
        self.assertEqual([f.split(":")[0] for f in got.faults],
                         ["line 2", "line 3", "line 4", "line 6"])
        self.assertIn("torn", got.faults[-1])


# ---------------------------------------------------------------------------
# 4. A run leaves one line, whatever its outcome
# ---------------------------------------------------------------------------


class TheRunLine(BedCase):

    def test_a_delivered_run_s_line_key_for_key(self):
        bed = self.bed()
        twin = bed.twin(DELIVER)
        (record,) = line_of(bed)
        self.assertEqual(tuple(record), runs.KEYS)
        self.assertEqual(runs.record_faults(record), [])
        self.assertEqual((record["record_version"], record["sid"], record["command"]),
                         (1, SID, "run"))
        self.assertIsNone(record["desk"], "the recorded `opened` line is the first desk: null")
        self.assertEqual((record["outcome"], record["stop"], record["move"], record["actor"],
                          record["shape"], record["reason"]),
                         ("delivered", None, "operator-applies", "operator", None, None))
        self.assertEqual((record["turns"], record["tool_calls"], record["retries"],
                          record["continuations"]), (3, 3, 0, 0))
        # the twin's, where the twin has them
        for key in ("usage", "cost_usd", "cap_usd", "adapter", "model", "window",
                    "resumed_from", "rewarm", "transcript", "sandbox", "inflight"):
            self.assertEqual(record[key], twin[key], key)
        self.assertEqual((record["cost_usd"], record["cap_usd"], record["adapter"],
                          record["inflight"]), (0.00042, 5.0, "fake", "removed"))
        self.assertEqual(set(record["tools"]), {"write_file", "shell", "deliver"})
        for entry in record["tools"].values():
            self.assertEqual((tuple(entry), entry["calls"], entry["errors"]),
                             (("calls", "errors", "seconds"), 1, 0))
            self.assertGreaterEqual(entry["seconds"], 0)
        self.assertEqual(record["events"], {"window_warned": 0, "continuations": 0,
                                            "retries": 0, "heartbeats": 0,
                                            "transcript_faults": 0, "inflight_error": 0,
                                            "group_survivors": 0})
        self.assertEqual(record["cost_file"], str(bed.state / "cost" / f"{SID}.json"))
        self.assertIsNone(record[runs.APPLY])
        # the times: UTC with an offset, the wall time from before `bale open`
        self.assertRegex(record["started_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")
        self.assertRegex(record["ended_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")
        self.assertLessEqual(record["started_at"], record["ended_at"])
        self.assertGreater(record["wall_seconds"], 0)
        self.assertEqual(oct(stat.S_IMODE((bed.state / "runs.jsonl").stat().st_mode)), "0o600")

    def test_every_outcome_writes_a_line(self):
        seen = {}

        def check(name, bed, twin):
            lines = line_of(bed)
            self.assertEqual(len(lines), 1, name)
            self.assertEqual(lines[0]["outcome"], twin["outcome"], name)
            self.assertEqual(runs.record_faults(lines[0]), [], name)
            seen[twin["outcome"]] = lines[0]

        bed = self.bed()
        check("delivered", bed, bed.twin(DELIVER))
        bed = self.bed()
        check("suspended", bed, bed.twin([stop("end-turn", light())]))
        bed = self.bed()
        check("ended", bed, bed.twin([stop("end-turn", "all done, nothing to deliver")]))
        bed = self.bed()
        check("stopped", bed, bed.twin([stop("rate-limited", retry_after=0,
                                             usage=usage(0, 0))] * 6))
        bed = self.bed()
        kill.request_abort(bed.state, SID)
        check("killed", bed, bed.twin([stop("end-turn", "never played")]))
        bed = self.bed()
        check("cap-reached", bed, bed.twin([stop("end-turn", "x")], cap="0.000001"))
        bed = self.bed(prices=False)
        check("cap-unchecked", bed, bed.twin([stop("end-turn", "x")]))
        self.assertEqual(set(seen), set(runs.OUTCOMES) - {"refused"})
        self.assertEqual(seen["stopped"]["retries"], 5)
        self.assertEqual(seen["stopped"]["events"]["retries"], 5)
        self.assertEqual((seen["killed"]["turns"], seen["killed"]["cost_usd"]), (0, 0.0))
        self.assertEqual(seen["cap-unchecked"]["cost_usd"], 0.0)
        self.assertIsNone(seen["suspended"]["cost_file"], "a light block names no apply line")

    def test_a_refusal_after_the_open_writes_a_line_and_one_before_writes_none(self):
        evil = Path(tempfile.mkdtemp(prefix="twine-evil-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(evil, ignore_errors=True))
        bed = self.bed(request=request_tarball(evil / "evil.tar.gz",
                                               {"../escaped.txt": b"x"}))
        twin = bed.twin([stop("end-turn", "never played")])
        self.assertEqual(twin["outcome"], "refused")
        (record,) = line_of(bed)
        self.assertEqual((record["outcome"], record["sid"], record["turns"], record["tools"]),
                         ("refused", SID, 0, {}))
        self.assertIsNone(record["transcript"])
        self.assertIn("the `data` filter refuses", record["reason"])
        # before a sid exists: the fake adapter with no script is the verb's own refusal
        bare = self.bed()
        result = bare.run(None)
        self.assertEqual(result.code, 1)
        self.assertFalse((bare.state / "runs.jsonl").exists(), "no sid, no line")

    def test_each_run_adds_its_line_and_never_touches_the_earlier_ones(self):
        bed = self.bed()
        bed.twin([stop("end-turn", "first")])
        before = (bed.state / "runs.jsonl").read_bytes()
        bed.twin([stop("end-turn", "second")])
        after = (bed.state / "runs.jsonl").read_bytes()
        self.assertTrue(after.startswith(before))
        self.assertEqual(len(line_of(bed)), 2)

    def test_the_tools_are_counted_with_their_errors_and_the_events_the_run_met(self):
        bed = self.bed()
        twin = bed.twin([tools(("read_file", {"path": "no/such/file"}),
                               ("list_dir", {}), n=1),
                         stop("max-tokens", "partial", usage=usage(10, 10)),
                         tools(("list_dir", {}), n=3),
                         stop("end-turn", "done")])
        self.assertEqual(twin["outcome"], "ended")
        (record,) = line_of(bed)
        self.assertEqual({k: (v["calls"], v["errors"]) for k, v in record["tools"].items()},
                         {"read_file": (1, 1), "list_dir": (2, 0)})
        self.assertEqual((record["continuations"], record["events"]["continuations"],
                          record["tool_calls"]), (1, 1, 3))

    def test_the_key_is_never_in_the_state_directory(self):
        bed = self.bed()
        bed.twin(DELIVER)
        bed.twin([stop("end-turn", "second")])
        for path in bed.every_file():
            self.assertNotIn(SENTINEL_KEY.encode(), path.read_bytes(), str(path))

    def test_status_names_runs_jsonl_as_the_eighth_boolean(self):
        bed = self.bed()
        before = run_cli("status", "--json", "--state-dir", str(bed.state))
        self.assertFalse(json.loads(before.stdout)["state_present"]["runs_jsonl"])
        bed.twin([stop("end-turn", "done")])
        after = json.loads(run_cli("status", "--json", "--state-dir", str(bed.state)).stdout)
        self.assertTrue(after["state_present"]["runs_jsonl"])
        self.assertEqual(list(after["state_present"])[-1], "runs_jsonl")
        self.assertEqual(len(after["state_present"]), 8)
        human = run_cli("status", "--state-dir", str(bed.state)).stdout
        self.assertIn("runs.jsonl", human.split("state present:")[1].split("\n")[0])

    def test_a_line_that_cannot_be_written_is_a_warning_not_a_change_of_outcome(self):
        bed = self.bed()
        (bed.state / "runs.jsonl").mkdir()          # a directory where the file should be
        twin = bed.twin([stop("end-turn", "done")])
        self.assertEqual(twin["outcome"], "ended")
        self.assertIn("no runs.jsonl line was written", twin["_stderr"])


class TheDesk(unittest.TestCase):
    """bale spells the first desk null and a later one `desk-N`; the record's
    `desk` is an integer or null."""

    def test_desk_number(self):
        for given, wanted in ((None, None), ("desk-2", 2), ("desk-12", 12), (3, 3),
                              ("desk-", None), ("desk-x", None), ("", None), (True, None),
                              (2.5, None), ("second", None)):
            with self.subTest(given=given):
                got = run_verb.desk_number(given)
                self.assertEqual(got, wanted)


class TheHeartbeatsAndTheTools(unittest.TestCase):
    """The loop's own tally: `tools[*].seconds` is wall time around `run_tool`,
    `heartbeats` the heartbeat lines printed."""

    def test_the_loop_tallies_its_tools_and_heartbeats(self):
        lines: list[str] = []
        bed = LoopBed(self, [tools(("shell", {"command": "sleep 0.3"}), n=1),
                             stop("end-turn", "done")], progress=lines.append,
                      heartbeat_seconds=0.05)
        result = bed.run()
        beats = [l for l in lines if "still running" in l]
        self.assertTrue(beats)
        self.assertEqual(result.heartbeats, len(beats))
        self.assertEqual((result.tools["shell"]["calls"], result.tools["shell"]["errors"]),
                         (1, 0))
        self.assertGreaterEqual(result.tools["shell"]["seconds"], 0)

    def test_a_tool_error_is_counted_as_one(self):
        bed = LoopBed(self, [tools(("read_file", {"path": "missing"}), n=1),
                             stop("end-turn", "done")])
        result = bed.run()
        self.assertEqual((result.tools["read_file"]["calls"], result.tools["read_file"]["errors"]),
                         (1, 1))
        self.assertEqual(result.heartbeats, 0)


# ---------------------------------------------------------------------------
# 5. The cost file beside the apply line, in a run and across a resume
# ---------------------------------------------------------------------------


class TheCostFileInTheRun(ResumeCase):

    def plan(self, bed: ResumeBed) -> dict:
        result = bed.resume(None, "--plan", answer=None, cap=None)
        obj = json.loads(result.stdout)
        self.assertEqual(result.code, 0 if obj["ok"] else 1, result.stderr)
        return obj

    def cost_of(self, bed: Bed) -> dict:
        return json.loads((bed.state / "cost" / f"{SID}.json").read_text())

    def test_the_cost_file_sums_the_whole_session_across_a_suspend_and_a_resume(self):
        bed = self.bed(with_tools=True)
        first = bed.twin([tools(("list_dir", {}), n=1),
                          tools(("escalate", {"blocking": True, "questions": [QUESTION]}), n=2)])
        self.assertEqual(first["outcome"], "suspended", first["reason"])
        # escalate's clarification form is an apply: its file holds the two calls so far
        self.assertEqual(self.cost_of(bed)["calls"], 2)
        self.assertIn(f" --cost-file {bed.state / 'cost' / (SID + '.json')}", first["apply_line"])
        self.assertEqual(first["next"][0], first["apply_line"])
        self.assertIn("--answer -", first["next"][1])
        second = bed.resume_twin([tools(("shell", {"command": DELIVER_SHELL}), n=1),
                                  tools(("deliver", {"tarball": "response.tar.gz"}), n=2)])
        self.assertEqual(second["outcome"], "delivered", second["reason"])
        both = self.cost_of(bed)
        self.assertEqual((both["calls"], both["models"], both["model_tier"]),
                         (4, ["fake"], None), "every run, resume and desk of the sid")
        self.assertEqual((both["tokens_in"], both["tokens_out"]), (400, 80))
        self.assertEqual(second["apply_line"], f"bale apply {second['tarball']} --cost-file "
                                               f"{bed.state / 'cost' / (SID + '.json')}")
        # the two runs' own lines: the run's, then the resume's
        run_line, resume_line = line_of(bed)
        self.assertEqual((run_line["command"], run_line["outcome"], run_line["turns"]),
                         ("run", "suspended", 2))
        self.assertEqual((resume_line["command"], resume_line["outcome"], resume_line["turns"]),
                         ("resume", "delivered", 2))
        self.assertIsNone(resume_line["desk"], "a resume has no open")
        self.assertIsNotNone(resume_line["resumed_from"])
        self.assertEqual(resume_line["rewarm"], second["rewarm"])
        self.assertEqual(resume_line["tools"]["shell"]["calls"], 1)
        self.assertEqual(resume_line["cost_file"], str(bed.state / "cost" / f"{SID}.json"))
        # bale saw the open and the two dry runs: never a --cost-file on a dry run
        for call in bed.stub.calls():
            if call[0] == "apply":
                self.assertIn("--dry-run", call)
                self.assertNotIn("--cost-file", call)

    def test_a_cost_file_that_cannot_be_written_is_a_warning_and_the_plain_line(self):
        bed = self.bed()
        (bed.state / "cost").write_text("a file where the directory should be")
        twin = bed.twin(DELIVER)
        self.assertEqual(twin["outcome"], "delivered", twin["reason"])
        tarball = Path(twin["sandbox"]) / "response.tar.gz"
        self.assertEqual(twin["apply_line"], f"bale apply {tarball.resolve()}")
        self.assertIsNone(twin["cost_file"])
        self.assertIn("cannot be written", twin["cost_file_error"])
        self.assertIn("warning: no cost file was written", twin["_stderr"])
        self.assertEqual(twin["next"], [twin["apply_line"]], "the apply is not held up")
        self.assertIsNone(line_of(bed)[0]["cost_file"])

    def test_the_admit_line_carries_the_file_and_falls_back_to_plain(self):
        bed = self.bed(dry_run=DRIFT, apply_exit=1)
        twin = bed.twin([tools(("shell", {"command": DELIVER_SHELL}), n=1),
                         tools(("deliver", {"tarball": "response.tar.gz"}), n=2)])
        admit = twin["next"][0]
        cost_file = bed.state / "cost" / f"{SID}.json"
        self.assertIn(f"--cost-file {cost_file} --allow-out-of-scope other.txt", admit)
        self.assertEqual(self.cost_of(bed)["calls"], 2)
        self.assertEqual(line_of(bed)[0]["cost_file"], str(cost_file))
        # the same refusal where the file cannot be written: the plain admit line
        blocked = self.bed(dry_run=DRIFT, apply_exit=1)
        (blocked.state / "cost").write_text("blocked")
        twin = blocked.twin([tools(("shell", {"command": DELIVER_SHELL}), n=1),
                             tools(("deliver", {"tarball": "response.tar.gz"}), n=2)])
        self.assertTrue(twin["next"][0].endswith(" --allow-out-of-scope other.txt"))
        self.assertNotIn("--cost-file", twin["next"][0])
        self.assertIn("cannot be written", twin["cost_file_error"])
        self.assertIn("warning: no cost file was written", twin["_stderr"])

    def test_the_plan_writes_nothing_and_names_the_file_only_when_it_is_there(self):
        bed = self.bed(dry_run=DRIFT, apply_exit=1)
        twin = bed.twin([tools(("shell", {"command": DELIVER_SHELL}), n=1),
                         tools(("deliver", {"tarball": "response.tar.gz"}), n=2)])
        before = tree(bed.state)
        plan = self.plan(bed)
        self.assertEqual(plan["next"][0], twin["next"][0])
        self.assertEqual(tree(bed.state), before, "a plan writes nothing")
        (bed.state / "cost" / f"{SID}.json").unlink()
        self.assertNotIn("--cost-file", self.plan(bed)["next"][0],
                         "bale would refuse a --cost-file on a file that is not there")


# ---------------------------------------------------------------------------
# 6. `twine stats` and `twine transcript`, as the shell runs them
# ---------------------------------------------------------------------------


STATS_KEYS = ["command", "ok", "path", "runs", "faults", "sessions", "by_outcome",
              "by_command", "turns", "tool_calls", "retries", "cost_usd", "unpriced_runs",
              "wall_seconds", "by_tool", "delivered", "since", "sid", "reason"]
TRANSCRIPT_KEYS = ["command", "ok", "sid", "path", "lines", "runs", "faults", "story", "reason"]


class TheStatsVerb(BedCase):

    def stats(self, bed: Bed, *extra: str) -> dict:
        result = run_cli("stats", "--state-dir", str(bed.state), *extra, "--json")
        lines = result.stdout.split("\n")
        self.assertEqual((len(lines), lines[1]), (2, ""), result.stdout)
        obj = json.loads(lines[0])
        self.assertEqual(result.code, 0 if obj["ok"] else 1, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return obj

    def test_an_absent_file_is_an_honest_empty_report(self):
        bed = self.bed()
        before = tree(bed.state)
        obj = self.stats(bed)
        self.assertEqual(list(obj), STATS_KEYS)
        self.assertEqual((obj["ok"], obj["runs"], obj["faults"], obj["sessions"],
                          obj["cost_usd"], obj["reason"]), (True, 0, [], 0, 0.0, None))
        self.assertEqual(obj["path"], str(bed.state / "runs.jsonl"))
        self.assertEqual(set(obj["by_outcome"].values()), {0})
        self.assertEqual(list(obj["by_outcome"]), list(runs.OUTCOMES))
        self.assertEqual(obj["by_command"], {"run": 0, "resume": 0})
        self.assertEqual(obj["delivered"], {"runs": 0, "mean_cost_usd": None,
                                            "mean_turns": None, "mean_wall_seconds": None})
        self.assertEqual(tree(bed.state), before, "stats creates nothing")
        (bed.state / "runs.jsonl").write_text("")
        self.assertEqual(self.stats(bed)["runs"], 0, "an empty file is the same report")

    def test_stats_over_the_runs_a_bed_made(self):
        bed = self.bed()
        bed.twin(DELIVER)
        bed.twin([stop("end-turn", "no delivery")])
        bed.twin([stop("end-turn", "x")], cap="0.000001")
        obj = self.stats(bed)
        self.assertEqual((obj["runs"], obj["sessions"], obj["faults"]), (3, 1, []))
        self.assertEqual({k: v for k, v in obj["by_outcome"].items() if v},
                         {"delivered": 1, "ended": 1, "cap-reached": 1})
        self.assertEqual(obj["by_command"], {"run": 3, "resume": 0})
        self.assertEqual((obj["turns"], obj["tool_calls"], obj["retries"]), (4, 3, 0))
        self.assertEqual((obj["cost_usd"], obj["unpriced_runs"]), (0.00056, 0))
        self.assertEqual({k: v["calls"] for k, v in obj["by_tool"].items()},
                         {"deliver": 1, "shell": 1, "write_file": 1})
        self.assertEqual(obj["delivered"]["runs"], 1)
        self.assertEqual((obj["delivered"]["mean_cost_usd"], obj["delivered"]["mean_turns"]),
                         (0.00042, 3.0))
        self.assertEqual((obj["since"], obj["sid"]), (None, None))
        mine = self.stats(bed, "--sid", SID)
        self.assertEqual((mine["runs"], mine["sid"]), (3, SID))
        self.assertEqual(self.stats(bed, "--sid", "someone-else")["runs"], 0)
        self.assertEqual(self.stats(bed, "--since", "2999-01-01")["runs"], 0)
        today = runs.utc_stamp()[:10]
        both = self.stats(bed, "--since", today, "--sid", SID)
        self.assertEqual((both["runs"], both["since"], both["sid"]), (3, today, SID))

    def test_a_bad_line_is_named_and_the_rest_is_counted(self):
        bed = self.bed()
        bed.twin([stop("end-turn", "x")])
        with open(bed.state / "runs.jsonl", "a") as fh:
            fh.write("this is not a record\n")
        obj = self.stats(bed)
        self.assertEqual((obj["ok"], obj["runs"]), (True, 1))
        self.assertEqual(len(obj["faults"]), 1)
        self.assertTrue(obj["faults"][0].startswith("line 2: not JSON"), obj["faults"])

    def test_not_ok_when_the_file_cannot_be_read_or_since_is_not_a_date(self):
        bed = self.bed()
        (bed.state / "runs.jsonl").mkdir()
        obj = self.stats(bed)
        self.assertEqual((obj["ok"], obj["runs"]), (False, 0))
        self.assertIn("cannot be read", obj["reason"])
        self.assertEqual(list(obj), STATS_KEYS)
        other = self.bed()
        obj = self.stats(other, "--since", "last-tuesday")
        self.assertFalse(obj["ok"])
        self.assertIn("--since", obj["reason"])
        self.assertEqual(obj["since"], "last-tuesday")

    def test_not_ok_when_no_state_directory_resolves(self):
        result = run_cli("stats", "--json", extra_env={"HOME": "", "TWINE_STATE_DIR": "",
                                                       "XDG_STATE_HOME": ""})
        obj = json.loads(result.stdout)
        self.assertEqual((result.code, obj["ok"], obj["path"]), (1, False, None))
        self.assertTrue(obj["reason"])

    def test_human_mode_is_one_line_per_key_in_order(self):
        bed = self.bed()
        bed.twin(DELIVER)
        result = run_cli("stats", "--state-dir", str(bed.state))
        self.assertEqual(result.code, 0, result.stderr)
        lines = result.stdout.rstrip("\n").split("\n")
        top = [l.split(":")[0] for l in lines if not l.startswith(" ")]
        self.assertEqual(top, ["path", "runs", "faults", "sessions", "by_outcome",
                               "by_command", "turns", "tool_calls", "retries", "cost_usd",
                               "unpriced_runs", "wall_seconds", "by_tool", "delivered",
                               "since", "sid", "reason"])
        self.assertIn("  delivered: 1", lines)
        self.assertIn("  run: 1", lines)
        self.assertTrue(any(l.startswith("  shell: 1 calls, 0 errors, ") for l in lines))
        self.assertEqual([l for l in lines if l.startswith("{")], [])

    def test_stats_and_transcript_write_nothing(self):
        bed = self.bed()
        bed.twin(DELIVER)
        bed.twin([stop("end-turn", "x")])
        before = tree(bed.state)
        for argv in (("stats",), ("stats", "--sid", SID), ("stats", "--since", "2020-01-01"),
                     ("transcript", SID), ("transcript", SID, "--from", "5"),
                     ("transcript", "no-such-sid")):
            with self.subTest(argv=argv):
                for extra in ((), ("--json",)):
                    run_cli(*argv, "--state-dir", str(bed.state), *extra)
        self.assertEqual(tree(bed.state), before)
        # nor a state directory that is not there
        missing = bed.base / "not-yet"
        run_cli("stats", "--state-dir", str(missing), "--json")
        run_cli("transcript", SID, "--state-dir", str(missing), "--json")
        self.assertFalse(missing.exists())


class TheTranscriptVerb(BedCase):

    def story(self, bed: Bed, *extra: str, sid: str = SID) -> dict:
        result = run_cli("transcript", sid, "--state-dir", str(bed.state), *extra, "--json")
        lines = result.stdout.split("\n")
        self.assertEqual((len(lines), lines[1]), (2, ""), result.stdout)
        obj = json.loads(lines[0])
        self.assertEqual(result.code, 0 if obj["ok"] else 1, result.stderr)
        return obj

    def test_the_story_matches_the_transcript_line_for_line(self):
        bed = self.bed()
        bed.twin(DELIVER)
        written = bed.transcript()
        obj = self.story(bed)
        self.assertEqual(list(obj), TRANSCRIPT_KEYS)
        self.assertEqual((obj["ok"], obj["sid"], obj["lines"], obj["runs"], obj["faults"],
                          obj["reason"]), (True, SID, len(written), 1, [], None))
        self.assertEqual(obj["path"], str(bed.state / "transcripts" / f"{SID}.jsonl"))
        self.assertEqual([(e["seq"], e["kind"], e["call"]) for e in obj["story"]],
                         [(l["seq"], l["kind"], l.get("call")) for l in written])
        for entry in obj["story"]:
            self.assertEqual(list(entry), ["seq", "kind", "call", "summary"])
        by_kind = {}
        for entry in obj["story"]:
            by_kind.setdefault(entry["kind"], entry["summary"])
        self.assertEqual(by_kind["run-start"], "fake, model fake, window unknown, not resumed")
        self.assertEqual(by_kind["turn"], "asks for write_file")
        self.assertEqual(by_kind["tool-call"], "write_file draft.txt")
        self.assertEqual(obj["story"][-1]["summary"], "delivered, move operator-applies")
        self.assertEqual(obj["story"][-1]["kind"], "run-end")

    def test_human_mode_is_a_line_per_transcript_line(self):
        bed = self.bed()
        bed.twin(DELIVER)
        result = run_cli("transcript", SID, "--state-dir", str(bed.state))
        lines = result.stdout.rstrip("\n").split("\n")
        story = self.story(bed)["story"]
        self.assertEqual(len(lines), len(story))
        self.assertEqual(lines[0], "1 run-start fake, model fake, window unknown, not resumed")
        self.assertRegex(lines[1], r"^2 check \[call 1\] estimate \d+ \(estimated\), admitted$")
        self.assertTrue(all(l.split(" ")[0] == str(i) for i, l in enumerate(lines, 1)))

    def test_from_starts_at_that_seq(self):
        bed = self.bed()
        bed.twin(DELIVER)
        everything = self.story(bed)["story"]
        obj = self.story(bed, "--from", "20")
        self.assertEqual([e["seq"] for e in obj["story"]],
                         [e["seq"] for e in everything if e["seq"] >= 20])
        self.assertEqual(obj["lines"], len(everything), "lines is what was read")
        self.assertEqual(self.story(bed, "--from", "999")["story"], [])

    def test_a_resumed_transcript_has_two_run_starts(self):
        bed = ResumeBed(with_tools=True)
        self.addCleanup(bed.cleanup)
        bed.twin([tools(("escalate", {"blocking": True, "questions": [QUESTION]}), n=1)])
        bed.resume_twin([stop("end-turn", "done")])
        obj = self.story(bed)
        self.assertEqual(obj["runs"], 2)
        starts = [e for e in obj["story"] if e["kind"] == "run-start"]
        self.assertIn("not resumed", starts[0]["summary"])
        self.assertIn("resumed from line", starts[1]["summary"])

    def test_a_torn_last_line_is_reported_and_not_refused(self):
        bed = self.bed()
        bed.twin([stop("end-turn", "x")])
        written = len(bed.transcript())
        path = bed.state / "transcripts" / f"{SID}.jsonl"
        with open(path, "ab") as fh:
            fh.write(b'{"seq": 99, "kind": "turn", "ca')
        obj = self.story(bed)
        self.assertTrue(obj["ok"])
        self.assertEqual(len(obj["faults"]), 1)
        self.assertIn("torn", obj["faults"][0])
        self.assertEqual(obj["lines"], written + 1)

    def test_not_ok_without_a_state_directory_a_transcript_or_a_sid(self):
        bed = self.bed()
        absent = self.story(bed, sid="2026-01-01-never-ran-001")
        self.assertEqual((absent["ok"], absent["lines"], absent["story"]), (False, 0, []))
        self.assertIn("does not exist", absent["reason"])
        self.assertEqual(list(absent), TRANSCRIPT_KEYS)
        refused = self.story(bed, sid="../../etc/passwd")
        self.assertFalse(refused["ok"])
        self.assertIsNone(refused["path"])
        result = run_cli("transcript", SID, "--json", extra_env={"HOME": "", "TWINE_STATE_DIR": "",
                                                                 "XDG_STATE_HOME": ""})
        none = json.loads(result.stdout)
        self.assertEqual((result.code, none["ok"], none["path"]), (1, False, None))


class TheDocsNameTheTelemetry(unittest.TestCase):
    """The contract docs, the index and the README carry the file and the verbs."""

    def read(self, name: str) -> str:
        from twine import REPO_ROOT
        return (REPO_ROOT / name).read_text(encoding="utf-8")

    def test_the_cli_contract_names_the_record_and_the_verbs(self):
        text = self.read("claude/context/cli-contract.md")
        for key in runs.KEYS:
            self.assertIn(f"`{key}`", text, key)
        for needle in ("runs.jsonl", "twine stats", "twine transcript", "--cost-file",
                       "runs_jsonl", "cost/<sid>.json", "tokens_in", "model_tier"):
            self.assertIn(needle, text, needle)

    def test_the_other_docs(self):
        self.assertIn("runs.jsonl", self.read("claude/context/runtime-contract.md"))
        self.assertIn("runs.jsonl", self.read("claude/INDEX.md"))
        readme = self.read("README.md")
        self.assertIn("runs.jsonl", readme)
        self.assertIn("twine stats", readme)
        self.assertIn("twine transcript", readme)
        self.assertEqual(self.read("VERSION").strip(), "0.26.0")


if __name__ == "__main__":
    unittest.main()

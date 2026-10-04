"""The cost spine (Arc 1 session 5a; D15 without the kill-switch): the
usage record and its writer, the stream reader, the operator's prices,
the running totals, the hard cap's pre-call check, and the two verbs over
them, `twine spend totals` and `twine spend check`.

Every usage value here is a twine record built from `usage_double`, and
every price is `PRICES_DOUBLE`'s or a table written inline below — all
doubles, named as such (tests/helpers.py). No provider usage has been
recorded; nothing here claims to be an API response. Each test uses its
own temporary state directory and never the real default.
"""

from __future__ import annotations

import ast
import io
import json
import re
import stat
import tomllib
import unittest
from decimal import Decimal
from pathlib import Path

from twine import REPO_ROOT, TRANSITIONS_TABLE, spend
from twine.cli import Context, main

from tests.helpers import (DOUBLE_MODEL, DOUBLE_MODEL_DEAR_CACHE, DOUBLE_MODEL_UNPRICED,
                           PRICES_DOUBLE, SpendStateDouble, run_cli, run_inprocess,
                           usage_double)

D = Decimal


def json_line(stdout: str) -> dict:
    lines = stdout.split("\n")
    assert len(lines) == 2 and lines[1] == "", f"not one line: {stdout!r}"
    return json.loads(lines[0])


class StateCase(unittest.TestCase):
    """A fresh state directory double per test."""

    prices: str | None = PRICES_DOUBLE

    def setUp(self):
        self.state = SpendStateDouble(prices=self.prices)
        self.addCleanup(self.state.cleanup)

    def totals(self, sid=None, prices_path=None):
        return spend.spend_totals(self.state.path, prices_path, sid)

    def check(self, sid="s1", cap="1", model=DOUBLE_MODEL, input_tokens=0,
              max_output=0, prices_path=None):
        return spend.check_call(self.state.path, sid=sid, cap_usd=D(cap), model=model,
                                input_tokens=input_tokens, max_output_tokens=max_output,
                                prices_path=prices_path)


# ---------------------------------------------------------------------------
# 1. The state directory (brief item 2)
# ---------------------------------------------------------------------------


class StateDirectory(unittest.TestCase):

    def test_flag_then_env_then_xdg_then_home(self):
        env = {"TWINE_STATE_DIR": "/e", "XDG_STATE_HOME": "/x", "HOME": "/h"}
        self.assertEqual(spend.resolve_state_dir("/f", env),
                         spend.StateDir(Path("/f"), "--state-dir"))
        self.assertEqual(spend.resolve_state_dir(None, env),
                         spend.StateDir(Path("/e"), "TWINE_STATE_DIR"))
        env.pop("TWINE_STATE_DIR")
        self.assertEqual(spend.resolve_state_dir(None, env),
                         spend.StateDir(Path("/x/twine"), "XDG_STATE_HOME"))
        env.pop("XDG_STATE_HOME")
        self.assertEqual(spend.resolve_state_dir(None, env),
                         spend.StateDir(Path("/h/.local/state/twine"), "HOME"))

    def test_relative_xdg_state_home_is_ignored(self):
        """The XDG spec: a relative path in $XDG_STATE_HOME is invalid and
        ignored, so the default falls through to $HOME."""
        got = spend.resolve_state_dir(None, {"XDG_STATE_HOME": "rel", "HOME": "/h"})
        self.assertEqual(got.path, Path("/h/.local/state/twine"))

    def test_nothing_set_is_a_refusal_never_the_working_directory(self):
        for env in ({}, {"HOME": ""}, {"HOME": "relative"}, {"XDG_STATE_HOME": "rel"}):
            with self.subTest(env=env):
                with self.assertRaises(spend.SpendError) as caught:
                    spend.resolve_state_dir(None, env)
                self.assertEqual(caught.exception.kind, "no-state-dir")

    def test_the_cli_refuses_rather_than_touch_a_default(self):
        """In-process with an empty environment: no state directory can be
        resolved, so both verbs refuse, exit 1, and nothing is written."""
        before = sorted(p.name for p in REPO_ROOT.iterdir())
        for argv in (["spend", "totals"],
                     ["spend", "check", "--sid", "s", "--cap", "1", "--model",
                      DOUBLE_MODEL, "--input", "1", "--max-output", "1"]):
            with self.subTest(argv=argv):
                run = run_inprocess(*argv, "--json")
                obj = json_line(run.stdout)
                self.assertEqual((run.code, obj["ok"], obj["refusal"]),
                                 (1, False, "no-state-dir"))
                self.assertIsNone(obj["state_dir"])
        self.assertEqual(sorted(p.name for p in REPO_ROOT.iterdir()), before)

    def test_an_empty_flag_is_refused_never_read_as_absent(self):
        """`--state-dir ""` or `--prices ""` was asked for and names nothing:
        a bad-argument refusal, never a fall-through to the default."""
        with self.assertRaises(spend.SpendError) as caught:
            spend.resolve_state_dir("", {"HOME": "/h"})
        self.assertEqual(caught.exception.kind, "bad-argument")
        with self.assertRaises(spend.SpendError):
            spend.resolve_prices_path(" ", Path("/s"))
        state = SpendStateDouble()
        self.addCleanup(state.cleanup)
        env = {"HOME": str(state.path)}
        for argv in (["spend", "totals", "--state-dir="],
                     ["spend", "totals", "--state-dir", str(state.path), "--prices="],
                     ["spend", "check", "--state-dir=", "--sid", "s", "--cap", "1",
                      "--model", DOUBLE_MODEL, "--input", "1", "--max-output", "1"]):
            with self.subTest(argv=argv):
                run = run_inprocess(*argv, "--json", env=env)
                obj = json_line(run.stdout)
                self.assertEqual((run.code, obj["ok"], obj["refusal"]),
                                 (1, False, "bad-argument"))
        self.assertEqual(sorted(p.name for p in state.path.iterdir()), ["prices.toml"],
                         "the HOME default was never resolved or written")

    def test_twine_state_dir_reaches_the_cli(self):
        state = SpendStateDouble()
        self.addCleanup(state.cleanup)
        state.call("s1", input=10)
        run = run_cli("spend", "totals", "--json",
                      extra_env={"TWINE_STATE_DIR": str(state.path)})
        obj = json_line(run.stdout)
        self.assertEqual((run.code, obj["state_dir"], obj["state_dir_source"]),
                         (0, str(state.path), "TWINE_STATE_DIR"))


# ---------------------------------------------------------------------------
# 2. The usage record and its writer (brief item 1)
# ---------------------------------------------------------------------------


class UsageRecordShape(StateCase):

    def test_one_line_per_call_with_the_required_keys(self):
        self.state.call("s1", input=5, output=7, thinking=3, cache_read=11, cache_write=13)
        self.state.call("s2", served_sid="s1", input=1)
        lines = self.state.stream.read_text(encoding="utf-8").split("\n")
        self.assertEqual(lines[-1], "", "every line ends with LF")
        first, second = (json.loads(line) for line in lines[:-1])
        self.assertEqual(list(first)[:4], ["sid", "served_sid", "model", "tokens"])
        self.assertIsNone(first["served_sid"], "served_sid is present and null")
        self.assertEqual(second["served_sid"], "s1")
        self.assertEqual(first["model"], DOUBLE_MODEL)
        self.assertEqual(first["tokens"], {"input": 5, "output": 7, "thinking": 3,
                                           "cache_read": 11, "cache_write": 13})
        self.assertEqual(first["recorded_at"], "2026-10-03T00:00:00Z")

    def test_thinking_may_be_null_and_nothing_else_may(self):
        self.state.call("s1", output=4, thinking=None)
        self.assertIsNone(json.loads(self.state.stream.read_text())["tokens"]["thinking"])
        for name in ("input", "output", "cache_read", "cache_write"):
            with self.subTest(token_class=name):
                tokens = usage_double()
                tokens[name] = None
                with self.assertRaises(spend.RecordError):
                    spend.append_record(self.state.path, sid="s1", model=DOUBLE_MODEL,
                                        tokens=tokens)

    def test_the_writer_refuses_a_bad_record_and_writes_nothing(self):
        bad = {
            "a negative count": dict(sid="s1", model=DOUBLE_MODEL,
                                     tokens=usage_double(input=-1)),
            "a bool": dict(sid="s1", model=DOUBLE_MODEL, tokens=usage_double(output=True)),
            "a float": dict(sid="s1", model=DOUBLE_MODEL, tokens=usage_double(input=1.0)),
            "a missing class": dict(sid="s1", model=DOUBLE_MODEL,
                                    tokens={"input": 1, "output": 1, "thinking": None,
                                            "cache_read": 0}),
            "a sixth class": dict(sid="s1", model=DOUBLE_MODEL,
                                  tokens={**usage_double(), "audio": 1}),
            "an empty sid": dict(sid="", model=DOUBLE_MODEL, tokens=usage_double()),
            "an empty model": dict(sid="s1", model=" ", tokens=usage_double()),
            "served_sid naming itself": dict(sid="s1", served_sid="s1", model=DOUBLE_MODEL,
                                             tokens=usage_double()),
            "extra setting a required key": dict(sid="s1", model=DOUBLE_MODEL,
                                                 tokens=usage_double(),
                                                 extra={"model": "other"}),
        }
        for what, kwargs in bad.items():
            with self.subTest(what):
                with self.assertRaises(spend.RecordError):
                    spend.append_record(self.state.path, **kwargs)
                self.assertFalse(self.state.stream.exists(), "nothing was written")

    def test_extra_keys_are_kept_by_the_writer_and_the_reader(self):
        spend.append_record(self.state.path, sid="s1", model=DOUBLE_MODEL,
                            tokens=usage_double(input=1),
                            extra={"call_id": "c-1", "stop": "end-turn"})
        self.state.raw('{"sid": "s2", "served_sid": null, "model": "double-model-a", '
                       '"tokens": {"input": 1, "output": 0, "thinking": null, '
                       '"cache_read": 0, "cache_write": 0}, "future_key": [1, 2]}\n')
        stream = spend.read_stream(self.state.stream)
        self.assertTrue(stream.ok, stream.problems)
        self.assertEqual(stream.records[0].extra["call_id"], "c-1")
        self.assertEqual(stream.records[1].extra, {"future_key": [1, 2]})

    def test_the_writer_creates_the_directory_and_keeps_the_file_private(self):
        target = self.state.path / "nested" / "state"
        spend.append_record(target, sid="s1", model=DOUBLE_MODEL, tokens=usage_double())
        mode = stat.S_IMODE((target / "spend.jsonl").stat().st_mode)
        self.assertEqual(mode & 0o077, 0, oct(mode))

    def test_the_writer_refuses_to_append_onto_a_torn_line(self):
        self.state.call("s1", input=1)
        self.state.raw('{"sid": "s1"')          # a torn write: no LF
        before = self.state.stream.read_bytes()
        with self.assertRaises(spend.SpendError) as caught:
            self.state.call("s1", input=2)
        self.assertEqual(caught.exception.kind, "malformed-stream")
        self.assertEqual(self.state.stream.read_bytes(), before)

    def test_what_the_writer_writes_the_reader_reads_back(self):
        written = [self.state.call("s1", input=3, thinking=None),
                   self.state.call("c1", served_sid="s1", output=2, thinking=9)]
        stream = spend.read_stream(self.state.stream)
        self.assertTrue(stream.ok)
        self.assertEqual([r.as_json() for r in stream.records],
                         [r.as_json() for r in written])
        self.assertEqual([r.line for r in stream.records], [1, 2])


# ---------------------------------------------------------------------------
# 3. Reading the stream: a malformed line is named, never skipped
# ---------------------------------------------------------------------------

GOOD = ('{"sid": "s1", "served_sid": null, "model": "double-model-a", "tokens": '
        '{"input": 1, "output": 1, "thinking": null, "cache_read": 0, '
        '"cache_write": 0}}\n')


class StreamReading(StateCase):

    def test_absent_and_empty_streams_are_empty(self):
        stream = spend.read_stream(self.state.stream)
        self.assertEqual((stream.present, stream.ok, stream.records), (False, True, []))
        self.state.stream.write_bytes(b"")
        stream = spend.read_stream(self.state.stream)
        self.assertEqual((stream.present, stream.ok, stream.records), (True, True, []))

    def test_each_kind_of_bad_line_is_named_by_its_number(self):
        bad_lines = {
            "not JSON": "{nope\n",
            "blank": "   \n",
            "not UTF-8": b"\xff\xfe\n",
            "duplicate key": GOOD.replace('"model": "double-model-a"',
                                          '"model": "a", "model": "b"'),
            "missing required key 'served_sid'": GOOD.replace('"served_sid": null, ', ""),
            "is negative": GOOD.replace('"input": 1', '"input": -1'),
            "outside the five classes": GOOD.replace('"cache_write": 0',
                                                     '"cache_write": 0, "audio": 2'),
            "not a JSON object": "[1, 2]\n",
            "must be a non-negative integer": GOOD.replace('"output": 1', '"output": 1.5'),
            "equals 'sid'": GOOD.replace('"served_sid": null', '"served_sid": "s1"'),
        }
        for expected, line in bad_lines.items():
            with self.subTest(expected):
                self.state.stream.write_bytes(b"")
                self.state.raw(GOOD)
                self.state.raw(line)
                self.state.raw(GOOD)
                stream = spend.read_stream(self.state.stream)
                self.assertFalse(stream.ok)
                self.assertEqual([p.line for p in stream.problems], [2])
                self.assertIn(expected, stream.problems[0].message)
                self.assertEqual(len(stream.records), 2, "good lines still read")
                self.assertEqual(stream.refusal().kind, "malformed-stream")

    def test_a_torn_last_line_is_named(self):
        self.state.raw(GOOD + GOOD.rstrip("\n"))
        stream = spend.read_stream(self.state.stream)
        self.assertEqual([(p.line, p.message) for p in stream.problems],
                         [(2, "not newline-terminated (a torn write?)")])

    def test_every_bad_line_is_reported_not_just_the_first(self):
        self.state.raw("x\n" + GOOD + "y\n" + "\n")
        stream = spend.read_stream(self.state.stream)
        self.assertEqual([p.line for p in stream.problems], [1, 3, 4])
        self.assertIn("3 line(s) are not usage records", stream.refusal().message)

    def test_an_unreadable_stream_is_its_own_refusal(self):
        self.state.stream.mkdir()     # a directory where the file should be
        stream = spend.read_stream(self.state.stream)
        self.assertFalse(stream.ok)
        self.assertEqual(stream.refusal().kind, "unreadable-stream")


# ---------------------------------------------------------------------------
# 4. Prices are operator data (brief item 3)
# ---------------------------------------------------------------------------


class Prices(StateCase):

    def write_prices(self, text: str) -> Path:
        self.state.prices.write_text(text, encoding="utf-8")
        return self.state.prices

    def test_a_valid_table_is_exact_and_keeps_other_keys(self):
        table = spend.load_prices(self.state.prices)
        row = table.models[DOUBLE_MODEL]
        self.assertEqual((row.input, row.output, row.cache_read, row.cache_write),
                         (D("3"), D("15"), D("0.3"), D("3.75")))
        self.assertIsInstance(row.cache_read, Decimal, "parsed exactly, never a float")
        self.assertEqual(row.extra["as_of"], "never")
        self.assertEqual(row.of("thinking"), row.output, "thinking bills as output (D20)")

    def test_an_absent_file_says_twine_ships_no_prices(self):
        self.state.prices.unlink()
        with self.assertRaises(spend.SpendError) as caught:
            spend.load_prices(self.state.prices)
        self.assertEqual(caught.exception.kind, "no-prices")
        self.assertIn("twine ships no prices", caught.exception.message)

    def test_a_malformed_file_is_refused_naming_the_fault(self):
        row = '[model."m"]\ninput = 1\noutput = 1\ncache_read = 1\ncache_write = 1\n'
        cases = {
            "not valid TOML": "[model.\n",
            "must be a table": 'model = "x"\n',
            "not a table": '[model]\nm = 3\n',
            "no 'cache_write' price": row.replace("cache_write = 1\n", ""),
            "must be a number": row.replace("input = 1", 'input = "1"'),
            "must be a number ": row.replace("input = 1", "input = true"),
            "is negative": row.replace("output = 1", "output = -0.5"),
            "is not finite": row.replace("output = 1", "output = inf"),
            "is not finite ": row.replace("output = 1", "output = nan"),
        }
        for expected, text in cases.items():
            with self.subTest(expected):
                with self.assertRaises(spend.SpendError) as caught:
                    spend.load_prices(self.write_prices(text))
                self.assertEqual(caught.exception.kind, "malformed-prices")
                self.assertIn(expected.strip(), caught.exception.message)

    def test_one_bad_row_refuses_the_whole_file(self):
        """A typo in a row you will use tomorrow is reported today."""
        with self.assertRaises(spend.SpendError) as caught:
            spend.load_prices(self.write_prices(
                PRICES_DOUBLE + '\n[model."typo"]\ninput = 1\noutput = 1\n'
                'cache_read = 1\ncache_wirte = 1\n'))
        self.assertIn("model 'typo'", caught.exception.message)

    def test_twine_ships_no_price_file_and_no_price_values(self):
        """Brief item 3: no price file, and no price table with a number in
        it, in anything twine ships — the only ones are the tests' doubles.
        (The contract shows the table's shape with placeholders.)

        The scan reads only twine's own shipped paths (SHIPPED_PATHS), never
        the whole tree: a repository also holds the planner's blind
        checkpoints (claude/checkpoints/, which no worker-authored test may
        read), archived responses, and — in bale's staging — a response's
        own validation.sh, each of which may legitimately carry a price
        double and none of which twine ships."""
        table_with_a_price = re.compile(
            r'\[model\."[^"\n]*"\][^\[]*?\b(input|output|cache_read|cache_write)'
            r'\s*=\s*[-+0-9.]')
        shipped = shipped_files()
        self.assertTrue(any(p.name == "spend.py" for p in shipped), "the scan sees twine/")
        self.assertFalse([p for p in shipped if p.name == "prices.toml"])
        self.assertFalse((REPO_ROOT / "prices.toml").exists())
        for path in shipped:
            text = path.read_text(encoding="utf-8", errors="replace")
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                self.assertIsNone(table_with_a_price.search(text))
        self.assertIsNotNone(table_with_a_price.search(PRICES_DOUBLE),
                             "the pattern finds a price table when there is one")

    def test_the_scan_never_reads_checkpoints_responses_or_tests(self):
        for path in shipped_files():
            rel = path.relative_to(REPO_ROOT).as_posix()
            with self.subTest(path=rel):
                self.assertFalse(rel.startswith(("claude/checkpoints/", "claude/responses/",
                                                 "tests/")), rel)
                self.assertNotEqual(rel, "validation.sh")


# What twine ships, for the no-prices scan: its code, its data, its docs.
# Deliberately an allow-list: claude/checkpoints/ (blind, the planner's),
# claude/responses/ (archives), tests/ (the doubles' home) and anything a
# bale staging copy adds beside the tree are never read.
SHIPPED_PATHS = ("bin", "twine", "share", "fixtures", "claude/context", "claude/INDEX.md",
                 "README.md", "VERSION", "twine-seed.md", "bale.toml")


def shipped_files() -> list[Path]:
    files: list[Path] = []
    for rel in SHIPPED_PATHS:
        path = REPO_ROOT / rel
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(p for p in sorted(path.rglob("*"))
                         if p.is_file() and "__pycache__" not in p.parts)
    return files


# ---------------------------------------------------------------------------
# 5. Cost: exact, thinking at the output price
# ---------------------------------------------------------------------------


class Cost(StateCase):

    def price(self, model=DOUBLE_MODEL):
        return spend.load_prices(self.state.prices).models[model]

    def test_a_call_costs_its_four_classes_plus_thinking_at_output(self):
        record = self.state.call("s1", input=1000, output=200, thinking=50,
                                 cache_read=100, cache_write=10)
        # 1000*3 + 200*15 + 50*15 + 100*0.3 + 10*3.75 = 6817.5 per million
        self.assertEqual(spend.record_cost(record, self.price()), D("0.0068175"))

    def test_null_thinking_adds_nothing_beyond_output(self):
        record = self.state.call("s1", output=200, thinking=None)
        self.assertEqual(spend.record_cost(record, self.price()), D("0.003"))

    def test_the_worst_case_takes_the_dearest_input_side_price(self):
        a = self.price()
        self.assertEqual(a.dearest_input_side(), ("cache_write", D("3.75")))
        self.assertEqual(spend.worst_case_cost(a, 1000, 100), D("0.00525"))
        b = self.price(DOUBLE_MODEL_DEAR_CACHE)
        self.assertEqual(b.dearest_input_side(), ("cache_read", D("5")))
        self.assertEqual(spend.worst_case_cost(b, 1_000_000, 1_000_000), D("7"))
        plain = spend.ModelPrice("p", D(9), D(1), D(1), D(1))
        self.assertEqual(plain.dearest_input_side(), ("input", D(9)))


# ---------------------------------------------------------------------------
# 6. Running totals (brief item 4)
# ---------------------------------------------------------------------------


class Totals(StateCase):

    def test_an_absent_or_empty_stream_is_ok_with_no_sessions_and_no_prices_read(self):
        self.state.prices.unlink()        # not needed: nothing to price
        report = self.totals()
        self.assertEqual((report.ok, report.sessions, report.prices_read,
                          report.total_cost_usd), (True, [], False, D(0)))
        self.state.stream.write_bytes(b"")
        self.assertTrue(self.totals().ok)

    def test_per_session_calls_tokens_and_cost(self):
        self.state.call("s1", input=1000, output=200, thinking=50)
        self.state.call("s2", input=10, thinking=None)
        self.state.call("s1", output=100, thinking=None, cache_read=1000)
        report = self.totals()
        self.assertTrue(report.ok, report.reason)
        rows = {s.sid: s.as_json() for s in report.sessions}
        self.assertEqual(list(rows), ["s1", "s2"], "order of first appearance")
        self.assertEqual(rows["s1"]["calls"], 2)
        self.assertEqual(rows["s1"]["tokens"], {"input": 1000, "output": 300,
                                                "thinking": 50, "cache_read": 1000,
                                                "cache_write": 0})
        self.assertEqual(rows["s2"]["tokens"]["thinking"], None,
                         "null only when every record had null")
        # s1: 3000 + 3000 + 750 + 1500 + 300 = 8550 per million
        self.assertEqual(report.sessions[0].cost_usd, D("0.00855"))
        self.assertEqual(report.sessions[1].cost_usd, D("0.00003"))
        self.assertEqual(report.total_cost_usd, D("0.00858"))

    def test_served_spend_lands_on_the_served_session_and_the_total_counts_once(self):
        self.state.call("parent", input=1_000_000)                        # $3
        self.state.call("child", served_sid="parent", output=1_000_000)   # $15
        self.state.call("cmp", served_sid="parent", cache_read=1_000_000)  # $0.3
        report = self.totals()
        rows = {s.sid: s for s in report.sessions}
        self.assertEqual((rows["parent"].cost_usd, rows["parent"].served_cost_usd,
                          rows["parent"].served_calls), (D(3), D("15.3"), 2))
        self.assertEqual((rows["child"].cost_usd, rows["child"].served_cost_usd),
                         (D(15), D(0)))
        self.assertEqual(report.total_cost_usd, D("18.3"), "each record counted once")

    def test_a_session_named_only_as_served_has_a_row_with_no_calls(self):
        self.state.call("child", served_sid="parent", input=10)
        row = {s.sid: s for s in self.totals().sessions}["parent"].as_json()
        self.assertEqual((row["calls"], row["cost_usd"], row["served_calls"]), (0, 0.0, 1))
        self.assertEqual(row["tokens"]["thinking"], 0, "no records: 0, never null")

    def test_sid_names_one_row_and_the_total_stays_the_streams(self):
        self.state.call("s1", input=1_000_000)
        self.state.call("s2", input=1_000_000)
        report = self.totals(sid="s2")
        self.assertEqual([s.sid for s in report.sessions], ["s2"])
        self.assertEqual(report.total_cost_usd, D(6))
        self.assertEqual(self.totals(sid="nobody").sessions, [])

    def test_an_unpriced_model_is_not_ok_and_never_a_zero(self):
        self.state.call("s1", input=10)
        self.state.call("s2", model=DOUBLE_MODEL_UNPRICED, input=10)
        report = self.totals()
        self.assertEqual((report.ok, report.refusal, report.unpriced_models),
                         (False, "unpriced-model", [DOUBLE_MODEL_UNPRICED]))
        self.assertIn(DOUBLE_MODEL_UNPRICED, report.reason)
        self.assertIsNone(report.total_cost_usd)
        self.assertTrue(all(s.cost_usd is None for s in report.sessions),
                        "no partial sum is reported")
        self.assertEqual(report.sessions[0].tokens["input"], 10, "tokens still shown")

    def test_a_malformed_line_is_not_ok_naming_it(self):
        self.state.call("s1", input=10)
        self.state.raw("garbage\n")
        report = self.totals()
        self.assertEqual((report.ok, report.refusal, report.sessions),
                         (False, "malformed-stream", []))
        self.assertEqual([p.line for p in report.problems], [2])
        self.assertIn("line 2", report.reason)

    def test_records_with_no_price_file_is_a_refusal(self):
        self.state.call("s1", input=10)
        self.state.prices.unlink()
        report = self.totals()
        self.assertEqual((report.ok, report.refusal), (False, "no-prices"))


# ---------------------------------------------------------------------------
# 7. The hard cap's pre-call check (brief item 5)
# ---------------------------------------------------------------------------


class PreCallCheck(StateCase):

    def test_admitted_at_exactly_the_cap_and_refused_just_over(self):
        self.state.call("s1", input=1_000_000)                       # spend so far $3
        # worst case: 1000 input at cache_write 3.75 + 100 output at 15 = $0.00525
        at_cap = self.check(cap="3.00525", input_tokens=1000, max_output=100)
        self.assertTrue(at_cap.admitted, at_cap.reason)
        self.assertEqual((at_cap.stop, at_cap.refusal), (None, None))
        over = self.check(cap="3.00524999", input_tokens=1000, max_output=100)
        self.assertFalse(over.admitted)
        self.assertEqual((over.stop, over.refusal), ("cap-reached", "cap-reached"))

    def test_the_comparison_is_exact_where_doubles_would_refuse(self):
        """0.1 + 0.2 > 0.3 in binary floating point; the check is decimal."""
        self.state.prices.write_text('[model."m"]\ninput = 0.1\noutput = 0.2\n'
                                     'cache_read = 0\ncache_write = 0\n')
        self.state.call("s1", model="m", input=1_000_000)             # $0.1
        check = self.check(cap="0.3", model="m", max_output=1_000_000)  # + $0.2
        self.assertTrue(check.admitted, check.reason)
        self.assertGreater(0.1 + 0.2, 0.3, "the double comparison this test guards")

    def test_a_refusal_carries_the_numbers_and_never_shrinks_the_call(self):
        self.state.call("s1", input=1_000_000)
        check = self.check(cap="3", input_tokens=1000, max_output=100)
        obj = check.as_json()
        self.assertEqual((obj["spend_so_far_usd"], obj["worst_case_usd"], obj["cap_usd"],
                          obj["projected_usd"]), (3.0, 0.00525, 3.0, 3.00525))
        self.assertEqual((obj["input_tokens"], obj["max_output_tokens"]), (1000, 100),
                         "the call as asked, unchanged")
        self.assertIn("not shrunk to fit", obj["reason"])
        for key in obj:
            for word in ("fit", "allow", "suggest", "shrink", "headroom", "remaining"):
                self.assertNotIn(word, key, "no key offers a smaller call")

    def test_spend_that_served_the_session_counts_against_its_cap(self):
        self.state.call("child", served_sid="s1", output=1_000_000)   # $15 for s1
        self.state.call("other", input=10_000_000)                    # $30, not s1's
        check = self.check(sid="s1", cap="15")
        self.assertTrue(check.admitted)
        self.assertEqual((check.own_cost_usd, check.served_cost_usd,
                          check.spend_so_far_usd, check.calls_so_far),
                         (D(0), D(15), D(15), 0))
        self.assertFalse(self.check(sid="s1", cap="15", input_tokens=1).admitted)

    def test_an_unpriced_model_is_never_admitted(self):
        check = self.check(model=DOUBLE_MODEL_UNPRICED, cap="1000000")
        self.assertEqual((check.admitted, check.refusal, check.stop),
                         (False, "unpriced-model", "cap-unchecked"))
        self.assertEqual(check.unpriced_models, [DOUBLE_MODEL_UNPRICED])

    def test_an_unpriced_model_in_the_sessions_history_is_never_admitted(self):
        self.state.call("s1", model=DOUBLE_MODEL_UNPRICED, input=1)
        check = self.check(cap="1000000")
        self.assertEqual((check.admitted, check.refusal), (False, "unpriced-model"))
        self.assertIn(DOUBLE_MODEL_UNPRICED, check.reason)
        # Another session's unpriced history is not this session's spend.
        self.assertTrue(self.check(sid="s2", cap="1").admitted)

    def test_an_uncheckable_cap_is_never_an_admission(self):
        cases = {}
        self.state.call("s1", input=1)
        self.state.raw("not json\n")
        cases["malformed-stream"] = self.check()
        self.state.stream.unlink()
        self.state.stream.mkdir()
        cases["unreadable-stream"] = self.check()
        self.state.stream.rmdir()
        self.state.prices.write_text("[model.\n")
        cases["malformed-prices"] = self.check()
        self.state.prices.unlink()
        cases["no-prices"] = self.check()
        for kind, check in cases.items():
            with self.subTest(kind):
                self.assertEqual((check.admitted, check.ok, check.refusal, check.stop),
                                 (False, False, kind, "cap-unchecked"))

    def test_bad_arguments_are_refused_by_the_function_too(self):
        for kwargs in (dict(cap_usd=D(-1)), dict(cap_usd=D("NaN")),
                       dict(cap_usd=D("Infinity")), dict(cap_usd=1.0),
                       dict(input_tokens=-1), dict(input_tokens=1.5),
                       dict(max_output_tokens=True), dict(sid=""), dict(model="")):
            with self.subTest(kwargs=kwargs):
                args = dict(sid="s1", cap_usd=D(1), model=DOUBLE_MODEL, input_tokens=0,
                            max_output_tokens=0)
                args.update(kwargs)
                check = spend.check_call(self.state.path, **args)
                self.assertEqual((check.admitted, check.refusal, check.stop),
                                 (False, "bad-argument", "cap-unchecked"))

    def test_the_check_writes_nothing(self):
        self.state.call("s1", input=1)
        before = {p.name: p.read_bytes() for p in self.state.path.iterdir()}
        self.check(cap="0", input_tokens=10)
        self.check(cap="100")
        self.assertEqual({p.name: p.read_bytes() for p in self.state.path.iterdir()},
                         before)

    def test_stop_is_the_transition_tables_key_for_stop_at_cap(self):
        with TRANSITIONS_TABLE.open("rb") as fh:
            table = tomllib.load(fh)
        self.assertIn(spend.STOP_CAP_REACHED, table["axis"]["stop"]["keys"])
        rows = [r for r in table["row"]
                if (r["axis"], r["key"]) == ("stop", spend.STOP_CAP_REACHED)]
        self.assertEqual([r["move"] for r in rows], ["stop-at-cap"])

    def test_every_other_refusal_stops_cap_unchecked_with_an_operator_move(self):
        """Session 5b: a check that could not run names its own stop key,
        whose move is the operator's and is not stop-at-cap — raising the
        cap is the wrong remedy for a missing price (cost-spine-005's
        Proposal, ratified)."""
        with TRANSITIONS_TABLE.open("rb") as fh:
            table = tomllib.load(fh)
        keys = table["axis"]["stop"]["keys"]
        self.assertEqual(keys[-2:], ["killed", spend.STOP_CAP_UNCHECKED])
        rows = [r for r in table["row"]
                if (r["axis"], r["key"]) == ("stop", spend.STOP_CAP_UNCHECKED)]
        self.assertEqual([r["move"] for r in rows], ["fix-and-resume"])
        move = table["move"]["fix-and-resume"]
        self.assertEqual(move["actor"], "operator")
        for fault in ("price row", "stream line", "state directory"):
            self.assertIn(fault, move["description"])
        for kind in spend.REFUSALS:
            with self.subTest(refusal=kind):
                check = spend.CallCheck(sid="s1", model=DOUBLE_MODEL, cap_usd=None,
                                        input_tokens=None, max_output_tokens=None,
                                        state_dir=Path(), stream=Path(), prices=Path())
                check.refuse(spend.SpendError(kind, "a refusal double"))
                expected = ("cap-reached" if kind == "cap-reached"
                            else "cap-unchecked")
                self.assertEqual((check.admitted, check.stop), (False, expected))
                self.assertIn(check.stop, keys)


# ---------------------------------------------------------------------------
# 8. The two verbs (brief items 4, 5 and 7)
# ---------------------------------------------------------------------------


class SpendTotalsVerb(StateCase):

    def test_json_twin_keys(self):
        self.state.call("s1", input=1000, output=200, thinking=50)
        self.state.call("c1", served_sid="s1", output=10)
        run = run_cli("spend", "totals", "--state-dir", str(self.state.path), "--json")
        obj = json_line(run.stdout)
        self.assertEqual((run.code, obj["command"], obj["ok"]), (0, "spend totals", True))
        self.assertIsInstance(obj["total_cost_usd"], float)
        for row in obj["sessions"]:
            self.assertLessEqual({"sid", "calls", "tokens", "cost_usd",
                                  "served_cost_usd"}, set(row))
            self.assertEqual(list(row["tokens"]), list(spend.TOKEN_CLASSES))
            self.assertIsInstance(row["cost_usd"], float)
            self.assertIsInstance(row["served_cost_usd"], float)
        self.assertNotIn("Traceback", run.stderr)

    def test_the_verb_and_the_function_agree(self):
        """One function, two faces: the CLI's numbers are spend_totals'."""
        self.state.call("s1", input=12345, output=678, thinking=9, cache_read=10)
        self.state.call("c1", served_sid="s1", cache_write=77)
        obj = json_line(run_inprocess("spend", "totals", "--state-dir",
                                      str(self.state.path), "--json").stdout)
        expected = self.totals().as_json()
        self.assertEqual(obj["sessions"], expected["sessions"])
        self.assertEqual(obj["total_cost_usd"], expected["total_cost_usd"])

    def test_not_ok_is_exit_1_one_line_no_traceback(self):
        self.state.call("s1", input=1)
        self.state.raw("{\n")
        run = run_cli("spend", "totals", "--state-dir", str(self.state.path), "--json")
        obj = json_line(run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["refusal"]),
                         (1, False, "malformed-stream"))
        self.assertEqual(obj["problems"][0]["line"], 2)
        self.assertNotIn("Traceback", run.stderr)

    def test_prices_flag_names_the_file(self):
        self.state.call("s1", input=1_000_000)
        other = self.state.path.parent / "elsewhere.toml"
        other.write_text(PRICES_DOUBLE.replace("input = 3\n", "input = 7\n", 1))
        self.state.prices.unlink()
        obj = json_line(run_inprocess("spend", "totals", "--state-dir",
                                      str(self.state.path), "--prices", str(other),
                                      "--json").stdout)
        self.assertEqual((obj["ok"], obj["total_cost_usd"], obj["prices_source"]),
                         (True, 7.0, "--prices"))

    def test_every_path_carries_the_same_keys(self):
        ok = json_line(run_inprocess("spend", "totals", "--state-dir",
                                     str(self.state.path), "--json").stdout)
        nowhere = json_line(run_inprocess("spend", "totals", "--json").stdout)
        self.state.raw("x\n")
        malformed = json_line(run_inprocess("spend", "totals", "--state-dir",
                                            str(self.state.path), "--json").stdout)
        self.assertEqual(set(nowhere), set(ok))
        self.assertEqual(set(malformed), set(ok))
        self.assertEqual((nowhere["state_dir"], nowhere["total_cost_usd"]), (None, None))

    def test_human_mode(self):
        run = run_inprocess("spend", "totals", "--state-dir", str(self.state.path))
        self.assertEqual(run.code, 0)
        self.assertIn("no spend recorded", run.stdout)
        self.state.call("s1", model=DOUBLE_MODEL_UNPRICED, input=1)
        run = run_inprocess("spend", "totals", "--state-dir", str(self.state.path))
        self.assertEqual(run.code, 1)
        self.assertIn("NOT OK (unpriced-model)", run.stdout.splitlines()[0])


class SpendCheckVerb(StateCase):

    def argv(self, cap="1", *extra):
        return ["spend", "check", "--state-dir", str(self.state.path), "--sid", "s1",
                "--cap", cap, "--model", DOUBLE_MODEL, "--input", "1000",
                "--max-output", "100", *extra]

    def test_admitted_is_exit_0(self):
        run = run_cli(*self.argv("1"), "--json")
        obj = json_line(run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["admitted"], obj["stop"]),
                         (0, True, True, None))

    def test_refused_by_the_cap_is_exit_1_with_stop_and_the_numbers(self):
        self.state.call("s1", input=1_000_000)
        run = run_cli(*self.argv("3"), "--json")
        obj = json_line(run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["stop"], obj["refusal"]),
                         (1, False, "cap-reached", "cap-reached"))
        self.assertEqual((obj["spend_so_far_usd"], obj["worst_case_usd"], obj["cap_usd"]),
                         (3.0, 0.00525, 3.0))
        self.assertNotIn("Traceback", run.stderr)
        human = run_inprocess(*self.argv("3"))
        self.assertIn("REFUSED (cap-reached)", human.stdout)
        self.assertIn("not shrunk to fit", human.stdout)

    def test_the_verb_and_the_function_agree(self):
        self.state.call("s1", input=4321, thinking=5, output=8)
        self.state.call("c1", served_sid="s1", cache_read=999)
        obj = json_line(run_inprocess(*self.argv("0.5"), "--json").stdout)
        expected = self.check(cap="0.5", input_tokens=1000, max_output=100).as_json()
        for key, value in expected.items():
            self.assertEqual(obj[key], value, key)

    def test_a_bad_value_is_a_named_refusal_not_a_usage_error(self):
        for flag, value in (("--cap", "five"), ("--cap", "-1"), ("--cap", "nan"),
                            ("--input", "1.5"), ("--max-output", "-3")):
            with self.subTest(flag=flag, value=value):
                argv = self.argv("1")
                argv[argv.index(flag) + 1] = value
                run = run_inprocess(*argv, "--json")
                obj = json_line(run.stdout)
                self.assertEqual((run.code, obj["admitted"], obj["refusal"]),
                                 (1, False, "bad-argument"))
                self.assertIn(flag, obj["reason"])

    def test_every_path_carries_the_same_keys(self):
        """Admitted, refused by the cap, unpriced, a bad value and no state
        directory: one key set, the uncomputed values null."""
        admitted = json_line(run_inprocess(*self.argv("1"), "--json").stdout)
        refused = json_line(run_inprocess(*self.argv("0"), "--json").stdout)
        unpriced = self.argv("1")
        unpriced[unpriced.index("--model") + 1] = DOUBLE_MODEL_UNPRICED
        unpriced = json_line(run_inprocess(*unpriced, "--json").stdout)
        bad = json_line(run_inprocess(*self.argv("x"), "--json").stdout)
        nowhere = self.argv("1")
        del nowhere[2:4]                                   # no --state-dir
        nowhere = json_line(run_inprocess(*nowhere, "--json").stdout)
        for obj in (refused, unpriced, bad, nowhere):
            self.assertEqual(set(obj), set(admitted))
        self.assertEqual((bad["refusal"], bad["spend_so_far_usd"], bad["cap_usd"]),
                         ("bad-argument", None, None))
        self.assertEqual((nowhere["refusal"], nowhere["state_dir"], nowhere["stream"]),
                         ("no-state-dir", None, None))
        for obj in (unpriced, bad, nowhere):
            self.assertEqual(obj["stop"], "cap-unchecked", obj["refusal"])
        self.assertEqual((admitted["stop"], refused["stop"]), (None, "cap-reached"))
        self.assertIsNone(unpriced["worst_case_usd"])

    def test_a_missing_flag_is_argparses_usage_error(self):
        argv = self.argv("1")
        del argv[argv.index("--model"):argv.index("--model") + 2]
        run = run_cli(*argv, "--json")
        self.assertEqual((run.code, run.stdout), (2, ""))

    def test_an_unpriced_model_is_exit_1_never_admitted(self):
        argv = self.argv("100")
        argv[argv.index("--model") + 1] = DOUBLE_MODEL_UNPRICED
        run = run_cli(*argv, "--json")
        obj = json_line(run.stdout)
        self.assertEqual((run.code, obj["admitted"], obj["refusal"], obj["stop"]),
                         (1, False, "unpriced-model", "cap-unchecked"))


# ---------------------------------------------------------------------------
# 9. No network, no subprocess, no provider SDK (T8)
# ---------------------------------------------------------------------------


class NoNetworkNoSdk(unittest.TestCase):

    FORBIDDEN = {"socket", "ssl", "http", "urllib", "subprocess", "multiprocessing",
                 "asyncio", "requests", "httpx", "aiohttp", "anthropic", "openai"}

    def test_the_spend_modules_import_nothing_that_reaches_out(self):
        for rel in ("twine/spend.py", "twine/commands/spend.py"):
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
            roots = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    roots.add(node.module.split(".")[0])
            with self.subTest(module=rel):
                self.assertFalse(roots & self.FORBIDDEN, roots & self.FORBIDDEN)

    def test_the_verbs_never_touch_the_run_seam(self):
        state = SpendStateDouble()
        self.addCleanup(state.cleanup)
        state.call("s1", input=1)

        def refuse(*args, **kwargs):
            raise AssertionError("a spend verb reached ctx.run")

        for argv in (["spend", "totals"],
                     ["spend", "check", "--sid", "s1", "--cap", "1", "--model",
                      DOUBLE_MODEL, "--input", "1", "--max-output", "1"]):
            with self.subTest(argv=argv):
                out = io.StringIO()
                ctx = Context(env={}, stdout=out, stderr=io.StringIO(),
                              which=lambda n: None, stdin=io.BytesIO(b""), run=refuse)
                code = main([*argv, "--state-dir", str(state.path), "--json"], ctx=ctx)
                self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()

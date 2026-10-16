"""Window accounting (Arc 2 R5; runtime-contract.md §7.4–§7.6, cli-contract.md
§18). No model anywhere: the fake adapter plays a script (T8), and the
Anthropic adapter's one `GET /v1/models` at spawn is held to the recording
in tests/test_anthropic.py.

  - **End to end** (`WindowEndToEnd`): `bin/twine run --window N` as a child
    process against StubBale (tests/test_run.py's Bed): the warning line in
    what was sent and never in the transcript's tool-result line, exhaustion
    before a call, the order before a call, an unknown window, the twin.
  - **In-process** (`WindowInTheLoop`): the loop over the fake with a Window
    handed in — the continue-turn and probe-hop turns, the counted cap
    estimate, a call that counts nothing.
  - **The pieces** (`TheWindow`, `TheStatement`, `TheMoveBookAndTheKey`):
    twine/runtime/window.py, the statement at the boundary, the table's row.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from twine import TRANSITIONS_TABLE, CONSUMPTION_MANIFEST, transitions
from twine.bale import load_manifest
from twine.runtime import loop as runloop
from twine.runtime.boundary import Adapter, Boundary
from twine.runtime.terms import WindowStatement, WindowStatementError
from twine.runtime.window import (WARNING_TEMPLATE, WINDOW_WARN_FRACTION, Window,
                                  input_side)
from twine.spend import Tokens
from twine.transitions import load_table

from tests.helpers import AbortWhenSeen, fenced_probe, filled_probe
from tests.test_run import (FAKE_MODEL, SID, TWIN_KEYS, Bed, LoopBed, stop, tools, usage)

# The R5 brief's line, verbatim, with N, M and P to fill.
BRIEF_LINE = ("[window: {N} of {M} input tokens in use ({P}%); the window does not compact "
              "— finish and deliver, or escalate; past 100% the run stops window-exhausted]")
R5_TWIN_KEYS = TWIN_KEYS + ("window", "resumed_from", "rewarm")


def line(n: int, m: int) -> str:
    return BRIEF_LINE.format(N=n, M=m, P=n * 100 // m)


class WindowCase(unittest.TestCase):

    def bed(self, **kw) -> Bed:
        bed = Bed(**kw)
        self.addCleanup(bed.cleanup)
        return bed

    @staticmethod
    def of(lines: list[dict], kind: str) -> list[dict]:
        return [l for l in lines if l["kind"] == kind]


# ---------------------------------------------------------------------------
# 1. End to end, through bin/twine
# ---------------------------------------------------------------------------


class WindowEndToEnd(WindowCase):

    def test_the_warning_is_the_last_line_of_every_tool_result_sent_once_warned(self):
        """700 of 1000 is not warned; 850 is (80%), and every tool result
        sent after carries the brief's line — in the request the model got,
        never in the transcript's tool-result line."""
        bed = self.bed()
        twin = bed.twin([tools(("list_dir", {}), n=1, input=600, cache_read=100),
                         tools(("list_dir", {}), ("read_file", {"path": "nope"}), n=2,
                               input=50, cache_read=700, cache_write=100),
                         tools(("list_dir", {}), n=3, input=900),
                         stop("end-turn", "done", usage=usage(950))],
                        "--window", "1000")
        lines = bed.transcript()
        windows = self.of(lines, "window")
        self.assertEqual([(w["call"], w["used"], w["size"], w["fraction"], w["warned"])
                          for w in windows],
                         [(1, 700, 1000, 0.7, False), (2, 850, 1000, 0.85, True),
                          (3, 900, 1000, 0.9, True), (4, 950, 1000, 0.95, True)])
        requests = self.of(lines, "request")
        # Call 2's request: the results of call 1, not warned.
        first = requests[1]["appended"][-1]["content"]
        self.assertFalse(any("[window:" in b["content"] for b in first))
        # Call 3's request: both results of call 2 end with the line.
        second = requests[2]["appended"][-1]["content"]
        self.assertEqual(len(second), 2)
        for block in second:
            self.assertTrue(block["content"].endswith("\n" + line(850, 1000)), block)
        self.assertTrue(second[1]["is_error"], "a failed tool's result carries it too")
        # Call 4's request: the numbers are the last call's.
        third = requests[3]["appended"][-1]["content"][0]["content"]
        self.assertTrue(third.endswith("\n" + line(900, 1000)))
        self.assertEqual(third.count("[window:"), 1)
        # The transcript's tool-result lines are the results as the tools gave them.
        for result in self.of(lines, "tool-result"):
            self.assertNotIn("[window:", result["result"]["content"])
        self.assertEqual(twin["window"], {"size": 1000, "used": 950, "warned": True,
                                          "source": "flag"})
        self.assertEqual(lines[0]["window"]["source"], "flag")

    def test_exhaustion_stops_before_the_call_that_would_pass_it(self):
        bed = self.bed()
        twin = bed.twin([tools(("list_dir", {}), n=1, input=990, cache_write=10),
                         stop("end-turn", "never played")], "--window", "1000")
        self.assertEqual((twin["outcome"], twin["stop"], twin["move"], twin["actor"],
                          twin["turns"]),
                         ("stopped", "window-exhausted", "split-goal", "planner", 1))
        self.assertIn("1000 of 1000", twin["reason"])
        self.assertIn("call 2 was not made", twin["reason"])
        self.assertEqual(len(bed.records()), 1, "one call made, one spend record")
        self.assertEqual(twin["window"], {"size": 1000, "used": 1000, "warned": True,
                                          "source": "flag"})
        lines = bed.transcript()
        moves = [l for l in self.of(lines, "move") if l["stop"] == "window-exhausted"]
        self.assertEqual(len(moves), 1)
        self.assertEqual((moves[0]["call"], moves[0]["move"], moves[0]["actor"]),
                         (2, "split-goal", "planner"))
        self.assertIn("the call was not made", moves[0]["did"])
        self.assertEqual(len(self.of(lines, "check")), 1, "the cap check never ran for call 2")
        # The results of call 1 were never sent: the last request line says so.
        unsent = self.of(lines, "request")[-1]
        self.assertIs(unsent["sent"], False)
        self.assertEqual(unsent["appended"][-1]["content"][0]["type"], "tool_result")

    def test_the_order_before_a_call_abort_max_turns_window_cap(self):
        """twine's --max-turns before the window; the window before the cap."""
        # --max-turns wins over an exhausted window.
        bed = self.bed()
        twin = bed.twin([tools(("list_dir", {}), n=1, input=5000)], "--window", "1000",
                        "--max-turns", "1")
        self.assertEqual((twin["outcome"], twin["shape"]), ("ended", "max-turns"))
        # The window wins over a cap the next call would pass: call 1 spends
        # a dollar of the double's prices, the cap is a cent.
        bed = self.bed()
        twin = bed.twin([tools(("list_dir", {}), n=1, input=1_000_000)], "--window", "1000",
                        "--max-tokens", "10", cap="0.01")
        self.assertEqual((twin["outcome"], twin["stop"]), ("stopped", "window-exhausted"))
        # The abort file wins over everything: set while call 1's own tool runs
        # (the cage cannot reach the state directory: the command touches a
        # marker in its home and the operator's side writes the request).
        bed = self.bed()
        marker = bed.state / "sandbox" / SID / "home" / "go"
        with AbortWhenSeen(bed.state, SID, marker) as operator:
            twin = bed.twin([tools(("shell", {"command": "touch go; sleep 2"}), n=1,
                                   input=5000)], "--window", "1000")
        self.assertTrue(operator.seen)
        self.assertEqual(twin["outcome"], "killed")

    def test_an_unknown_window_counts_and_never_warns_or_stops(self):
        bed = self.bed()
        twin = bed.twin([tools(("list_dir", {}), n=1, input=10_000_000),
                         tools(("list_dir", {}), n=2, input=20_000_000),
                         stop("end-turn", "done", usage=usage(30_000_000))], cap="1000")
        self.assertEqual((twin["outcome"], twin["turns"]), ("ended", 3))
        self.assertEqual(twin["window"], {"size": None, "used": 30_000_000, "warned": False,
                                          "source": "unknown"})
        self.assertIn("fake adapter", twin["window_reason"])
        windows = self.of(bed.transcript(), "window")
        self.assertEqual([(w["size"], w["fraction"], w["warned"]) for w in windows],
                         [(None, None, False)] * 3)
        self.assertIn("window: size unknown", twin["_stderr"])
        for request in self.of(bed.transcript(), "request"):
            self.assertNotIn("[window:", json.dumps(request["appended"]))

    def test_the_twin_s_new_keys_follow_r4_s(self):
        bed = self.bed()
        twin = bed.twin([stop("end-turn", "done", usage=usage(10))])
        self.assertEqual(tuple(twin)[2:2 + len(R5_TWIN_KEYS)], R5_TWIN_KEYS)
        self.assertEqual(twin["window"], {"size": None, "used": 10, "warned": False,
                                          "source": "unknown"})
        self.assertIsNone(twin["resumed_from"])
        self.assertIsNone(twin["rewarm"], "twine run carries rewarm null")
        end = bed.transcript()[-1]["twin"]
        self.assertEqual(end["window"], twin["window"])
        self.assertIn("resumed_from", end)
        self.assertIsNone(bed.transcript()[0]["resumed_from"])

    def test_no_calls_is_used_zero(self):
        bed = self.bed()
        twin = bed.twin([stop("end-turn", "never")], "--window", "50", cap="0.000001")
        self.assertEqual((twin["outcome"], twin["turns"]), ("cap-reached", 0))
        self.assertEqual(twin["window"], {"size": 50, "used": 0, "warned": False,
                                          "source": "flag"})

    def test_a_window_that_is_not_positive_refuses_before_bale_opens(self):
        for value in ("0", "-5"):
            with self.subTest(window=value):
                bed = self.bed()
                twin = bed.twin([stop("end-turn")], "--window", value)
                self.assertEqual(twin["outcome"], "refused")
                self.assertIn(f"--window {value} is not a positive number", twin["reason"])
                self.assertIsNone(twin["window"])
                self.assertEqual(bed.stub.calls(), [])

    def test_the_provider_s_own_refusal_keeps_its_row(self):
        bed = self.bed()
        twin = bed.twin([stop("window-exhausted", reason="the provider said so")],
                        "--window", "1000000")
        self.assertEqual((twin["outcome"], twin["stop"], twin["move"], twin["turns"]),
                         ("stopped", "window-exhausted", "split-goal", 1))
        self.assertIn("the provider said so", twin["reason"])


# ---------------------------------------------------------------------------
# 2. In the loop
# ---------------------------------------------------------------------------


class WindowInTheLoop(unittest.TestCase):

    def bed(self, script, size: int | None, **kw) -> LoopBed:
        bed = LoopBed(self, script, **kw)
        bed.loop.window = Window.from_flag(size) if size else Window.unknown("a test's")
        return bed

    def test_the_continue_turn_carries_the_line(self):
        bed = self.bed([stop("max-tokens", "half", usage=usage(90)),
                        stop("end-turn", "whole")], 100)
        bed.run()
        _, second = bed.adapter.requests
        cont = second.messages[-1]["content"]
        self.assertEqual(cont[-1], {"type": "text",
                                    "text": runloop.CONTINUE_TEXT + "\n" + line(90, 100)})

    def test_the_probe_hop_carries_the_line(self):
        bed = self.bed([stop("end-turn", fenced_probe(filled_probe()), usage=usage(81)),
                        stop("end-turn", "thanks")], 100)
        bed.run()
        _, second = bed.adapter.requests
        fed = second.messages[-1]
        self.assertEqual(fed["role"], "user")
        self.assertIn("=== PROBE BEGIN", fed["content"])
        self.assertTrue(fed["content"].endswith("\n" + line(81, 100)))

    def test_the_cap_check_prices_the_count_plus_what_was_appended(self):
        bed = self.bed([tools(("list_dir", {}), n=1, input=500, cache_read=20),
                        stop("end-turn", "done")], None)
        bed.run()
        checks = [l for l in self.lines(bed) if l["kind"] == "check"]
        self.assertEqual(checks[0]["input_basis"], "estimated")
        self.assertEqual(checks[0]["input_estimate"],
                         runloop.estimate_input_tokens(bed.prompt,
                                                       bed.adapter.requests[0].messages))
        appended = bed.adapter.requests[1].messages[1:]
        self.assertEqual(checks[1]["input_basis"], "counted")
        self.assertEqual(checks[1]["input_estimate"],
                         520 + runloop.estimate_appended_tokens(appended))
        self.assertLess(checks[1]["input_estimate"],
                        runloop.estimate_input_tokens(bed.prompt,
                                                      bed.adapter.requests[1].messages)
                        + 520)

    def test_a_call_that_counts_nothing_keeps_the_count(self):
        """A retry stop the provider answered with no usage is not an empty
        window: `used` stays, and the window line says what the call said."""
        bed = self.bed([tools(("list_dir", {}), n=1, input=700),
                        stop("overloaded", retry_after=0, usage=usage(0, 0)),
                        stop("end-turn", "done", usage=usage(710))], 1000)
        result = bed.run()
        self.assertEqual(result.outcome, "ended")
        windows = [l for l in self.lines(bed) if l["kind"] == "window"]
        self.assertEqual([(w["used"], w["call_input"]) for w in windows],
                         [(700, 700), (700, 0), (710, 710)])

    def test_first_usage_is_the_first_call_s(self):
        bed = self.bed([tools(("list_dir", {}), n=1, input=7, cache_write=3),
                        stop("end-turn", "done", usage=usage(9))], None)
        result = bed.run()
        self.assertEqual(result.first_usage, usage(7, 20, None, 0, 3))

    @staticmethod
    def lines(bed: LoopBed) -> list[dict]:
        from twine import transcript
        return list(transcript.read_lines(bed.transcript.path))


# ---------------------------------------------------------------------------
# 3. The pieces
# ---------------------------------------------------------------------------


class TheWindow(unittest.TestCase):

    def test_the_template_is_the_brief_s_line(self):
        self.assertEqual(WARNING_TEMPLATE.format(used=12, size=34, percent=35,
                                                 stop=transitions.STOP_WINDOW_EXHAUSTED),
                         BRIEF_LINE.format(N=12, M=34, P=35))
        self.assertEqual(WINDOW_WARN_FRACTION, 0.8)

    def test_count_warn_and_exhaust(self):
        w = Window.from_flag(1000)
        self.assertEqual((w.used, w.counted, w.warned, w.exhausted), (0, False, False, False))
        self.assertIsNone(w.warning())
        self.assertEqual(w.noted("x"), "x")
        self.assertEqual(w.count(1, Tokens(799, 5, None, 0, 0)),
                         {"call": 1, "used": 799, "size": 1000, "fraction": 0.799,
                          "warned": False, "call_input": 799})
        w.count(2, Tokens(500, 5, None, 300, 0))
        self.assertTrue(w.warned)
        self.assertEqual(w.warning(), line(800, 1000))
        w.count(3, Tokens(10, 5, None, 0, 0))
        self.assertTrue(w.warned, "a warned run stays warned")
        self.assertEqual(w.warning(), line(10, 1000))
        self.assertFalse(w.exhausted)
        w.count(4, Tokens(0, 0, None, 999, 1))
        self.assertTrue(w.exhausted)
        self.assertEqual(w.as_json(), {"size": 1000, "used": 1000, "warned": True,
                                       "source": "flag"})

    def test_the_percentage_is_floored(self):
        w = Window.from_flag(1000)
        w.count(1, Tokens(999, 0, None, 0, 0))
        self.assertIn("(99%)", w.warning())

    def test_noted_puts_the_line_last(self):
        w = Window.from_flag(10)
        w.count(1, Tokens(9, 0, None, 0, 0))
        self.assertEqual(w.noted("out"), "out\n" + line(9, 10))
        self.assertEqual(w.noted("out\n"), "out\n" + line(9, 10))
        self.assertEqual(w.noted(""), line(9, 10))

    def test_an_unknown_window_never_warns(self):
        w = Window.stated(WindowStatement(None, "no model"))
        w.count(1, Tokens(10**9, 0, None, 0, 0))
        self.assertEqual((w.warned, w.exhausted, w.fraction(), w.source, w.reason),
                         (False, False, None, "unknown", "no model"))

    def test_input_side(self):
        self.assertEqual(input_side(Tokens(1, 100, 7, 20, 300)), 321)

    def test_a_window_is_coherent(self):
        for bad in ({"size": 0, "source": "flag"}, {"size": None, "source": "flag"},
                    {"size": 5, "source": "unknown"}, {"size": 5, "source": "guess"}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    Window(**bad)


class TheStatement(unittest.TestCase):

    def test_the_shape(self):
        self.assertTrue(WindowStatement(5).known)
        for bad in ((0, None), (True, None), (None, None), (None, "  "), (5.0, None)):
            with self.subTest(bad=bad):
                with self.assertRaises(WindowStatementError):
                    WindowStatement(*bad)

    def test_the_fake_states_unknown(self):
        bed = LoopBed(self, [stop("end-turn")])
        statement = Boundary(bed.adapter).context_window()
        self.assertEqual(statement.size, None)
        self.assertIn("fake adapter", statement.reason)

    def test_a_statement_that_breaks_the_shape_is_unknown_not_a_crash(self):
        bed = LoopBed(self, [stop("end-turn")])
        boundary = Boundary(bed.adapter)
        for behaviour, needle in ((lambda: (_ for _ in ()).throw(RuntimeError("boom")),
                                   "RuntimeError: boom"),
                                  (lambda: 1000, "stated its context window as a int")):
            with self.subTest(needle=needle):
                bed.adapter.context_window = behaviour
                with self.assertLogs("twine.runtime.boundary", "ERROR"):
                    statement = boundary.context_window()
                self.assertIsNone(statement.size)
                self.assertIn(needle, statement.reason)

    def test_the_base_adapter_states_unknown(self):
        self.assertIn("context_window", vars(Adapter))
        self.assertNotIn("context_window", Adapter.__abstractmethods__)


class TheMoveBookAndTheKey(unittest.TestCase):

    def test_the_key_is_the_table_s_and_not_a_loop_key(self):
        table = load_table(TRANSITIONS_TABLE, load_manifest(CONSUMPTION_MANIFEST))
        axis = table.axis("stop")
        self.assertIn(transitions.STOP_WINDOW_EXHAUSTED, axis.keys)
        self.assertNotIn(transitions.STOP_WINDOW_EXHAUSTED, axis.loop_keys)
        self.assertEqual(runloop.MoveBook(table).stop_move(
            transitions.STOP_WINDOW_EXHAUSTED).name, "split-goal")

    def test_a_table_without_its_row_is_a_fault(self):
        text = TRANSITIONS_TABLE.read_text(encoding="utf-8")
        row = re.search(r'\[\[row\]\]\naxis = "stop"\nkey = "window-exhausted"\n.*?\n\n', text,
                        re.S)
        self.assertIsNotNone(row)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.toml"
            path.write_text(text.replace(row.group(0), ""), encoding="utf-8")
            faults = runloop.MoveBook(load_table(path, load_manifest(CONSUMPTION_MANIFEST))
                                      ).faults()
        self.assertTrue(any("'window-exhausted'" in f and "no row" in f for f in faults),
                        faults)

    def test_the_window_module_spells_no_stop_key(self):
        import ast
        from twine import REPO_ROOT
        keys = set(load_table().axis("stop").keys)
        for rel in ("twine/runtime/window.py", "twine/runtime/resume.py",
                    "twine/runtime/tools/escalate.py"):
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
            spelled = {n.value for n in ast.walk(tree)
                       if isinstance(n, ast.Constant) and isinstance(n.value, str)
                       and n.value in keys}
            with self.subTest(file=rel):
                self.assertEqual(spelled, set())


if __name__ == "__main__":
    unittest.main()

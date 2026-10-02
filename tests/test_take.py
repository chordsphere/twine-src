"""`twine take` and its parse layer, twine.shapes (Arc 1 session 2a).

The recorded and carried fixtures are the positive cases. Every negative
is derived from their bytes here — a line dropped, a byte flipped, an
escape unescaped, an END sentinel cut, the whole converted to CRLF — so
nothing under fixtures/ is invented and nothing here is hand-typed bale
output. Sections:

  1. Fixtures and derivation helpers
  2. Each kind, positive              (the fixtures as recorded)
  3. Each kind, derived negatives
  4. Normalization, nesting, order, shape
  5. The verb: --json, exit codes, stdin, -I -S, never executes
"""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from twine import REPO_ROOT, shapes

from tests.helpers import carried_relpath, emission_relpath, run_cli, run_inprocess

# ---------------------------------------------------------------------------
# 1. Fixtures and derivation helpers
# ---------------------------------------------------------------------------

PROBE_SCRIPT = REPO_ROOT / emission_relpath("crafter", ["--probe", "twine-take-fixture"])
LIGHT = REPO_ROOT / emission_relpath("crafter", ["--light-block", "-"])
EXCHANGE = REPO_ROOT / emission_relpath("crafter", ["--emit-block", "-"])
PROBE_OUTPUT = REPO_ROOT / carried_relpath("probe-output", "twine-take-specimens")
RELAY = REPO_ROOT / carried_relpath("relay", "2026-10-01-twine-seed-effort-003", "planner")
SID = "2026-10-02-twine-take-read-001"


def text_of(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def fenced(script: str, info: str = "bash") -> str:
    """A probe as a worker's turn carries it: the crafter's script in a fence."""
    return f"```{info}\n{script}```\n"


def take(text: str) -> shapes.Report:
    return shapes.find_blocks(shapes.normalize(text.encode("utf-8")).text)


def only(report: shapes.Report) -> shapes.Block:
    assert len(report.blocks) == 1, [b.as_json() for b in report.blocks]
    return report.blocks[0]


def drop_line(text: str, predicate) -> str:
    """The text without the first line `predicate` accepts."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if predicate(line):
            return "\n".join(lines[:i] + lines[i + 1:])
    raise AssertionError("no line matched the predicate")


def to_crlf(text: str) -> str:
    return text.replace("\n", "\r\n")


# ---------------------------------------------------------------------------
# 2. Each kind, positive
# ---------------------------------------------------------------------------


class Positives(unittest.TestCase):

    def test_probe_block_fenced_is_found_with_slug_and_verbatim_script(self):
        script = text_of(PROBE_SCRIPT)
        block = only(take("Here is the probe.\n\n" + fenced(script) + "\nPaste it back.\n"))
        self.assertEqual((block.kind, block.ok), ("probe", True))
        self.assertEqual(block.fields["slug"], "twine-take-fixture")
        self.assertEqual(block.fields["script"], script)
        self.assertEqual(block.fields["fence_info"], "bash")

    def test_bare_probe_script_is_prose_its_quoted_sentinels_are_not_sentinels(self):
        """The scaffold's `echo "=== PROBE BEGIN … ==="` lines quote a
        sentinel inside a line; whole-line anchoring leaves them alone."""
        script = text_of(PROBE_SCRIPT)
        self.assertIn('echo "=== PROBE BEGIN twine-take-fixture ==="', script)
        report = take(script)
        self.assertEqual((report.shape, report.blocks, report.ok), ("prose", [], True))

    def test_probe_output_trailer_verifies(self):
        block = only(take(text_of(PROBE_OUTPUT)))
        self.assertEqual((block.kind, block.fields["slug"], block.ok),
                         ("probe-output", "twine-take-specimens", True))
        self.assertEqual(block.integrity, {"ok": True, "basis": "line-count",
                                           "expected_lines": 661, "found_lines": 661})

    def test_light_block_rows_are_keyed_by_manifest_fields(self):
        block = only(take(text_of(LIGHT)))
        self.assertEqual((block.kind, block.fields["sid"], block.ok), ("light", SID, True))
        rows = block.fields["questions"]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(set(row), {"question", "context", "default_assumption",
                                        "why_blocked"})

    def test_light_rows_equal_the_exchange_records_rows(self):
        """The two crafter emissions rendered one manifest: the light
        block's parsed rows are the exchange record's four fields."""
        light = only(take(text_of(LIGHT))).fields["questions"]
        record = only(take(text_of(EXCHANGE))).fields["record"]
        keys = ("question", "context", "default_assumption", "why_blocked")
        self.assertEqual(light, [{k: q[k] for k in keys} for q in record["questions"]])

    def test_exchange_block_verifies_and_reports_round_from_record(self):
        block = only(take(text_of(EXCHANGE)))
        self.assertEqual((block.kind, block.fields["sid"], block.ok), ("exchange", SID, True))
        self.assertEqual((block.fields["round"], block.fields["from"]), (1, "worker"))
        self.assertEqual(block.fields["record"]["session_id"], SID)
        trailer = [ln for ln in text_of(EXCHANGE).split("\n") if ln.startswith("# sha256 ")]
        self.assertEqual(block.integrity["expected_sha256"], trailer[0].split()[-1])
        self.assertEqual(block.integrity["found_sha256"], block.integrity["expected_sha256"])

    def test_relay_block_reports_sid_and_addressee(self):
        block = only(take(text_of(RELAY)))
        self.assertEqual((block.kind, block.fields, block.ok),
                         ("relay", {"sid": "2026-10-01-twine-seed-effort-003",
                                    "to": "planner"}, True))
        self.assertEqual((block.start_line, block.end_line), (1, 174))


# ---------------------------------------------------------------------------
# 3. Each kind, derived negatives
# ---------------------------------------------------------------------------


def cut_end(text: str) -> str:
    """The text with its last END sentinel line removed."""
    lines = text.split("\n")
    for i in range(len(lines) - 1, -1, -1):
        if shapes._orphan_end(lines[i]) is not None:
            return "\n".join(lines[:i] + lines[i + 1:])
    raise AssertionError("no END sentinel")


class Negatives(unittest.TestCase):

    def assert_not_ok(self, text: str, kind: str) -> shapes.Block:
        report = take(text)
        self.assertFalse(report.ok)
        bad = [b for b in report.blocks if not b.ok]
        self.assertTrue(bad)
        self.assertEqual(bad[0].kind, kind)
        self.assertFalse(bad[0].integrity["ok"])
        self.assertTrue(bad[0].error)
        return bad[0]

    def test_cut_end_sentinel_is_malformed_for_every_sentinel_kind(self):
        for path, kind in ((PROBE_OUTPUT, "probe-output"), (LIGHT, "light"),
                           (EXCHANGE, "exchange"), (RELAY, "relay")):
            with self.subTest(kind=kind):
                block = self.assert_not_ok(cut_end(text_of(path)), kind)
                self.assertIn("never closes", block.error)

    def test_unclosed_probe_fence_is_malformed(self):
        text = fenced(text_of(PROBE_SCRIPT)).rstrip("`\n") + "\n"
        self.assertIn("never closes", self.assert_not_ok(text, "probe").error)

    def test_probe_output_missing_a_line_fails_its_trailer(self):
        text = drop_line(text_of(PROBE_OUTPUT), lambda ln: ln.startswith("uname: "))
        block = self.assert_not_ok(text, "probe-output")
        self.assertEqual((block.integrity["expected_lines"], block.integrity["found_lines"]),
                         (661, 660))

    def test_probe_output_without_its_trailer_fails(self):
        text = drop_line(text_of(PROBE_OUTPUT), lambda ln: ln.startswith("--- integrity:"))
        self.assertIn("trailer", self.assert_not_ok(text, "probe-output").error)

    def test_exchange_flipped_byte_is_a_mismatch(self):
        text = text_of(EXCHANGE).replace('"round": 1,', '"round": 2,')
        block = self.assert_not_ok(text, "exchange")
        self.assertEqual(block.integrity["fault"], "mismatch")
        self.assertEqual(block.fields["round"], 2)   # the body still parsed

    def test_exchange_missing_a_body_line_is_a_mismatch(self):
        text = drop_line(text_of(EXCHANGE), lambda ln: '"priority"' in ln)
        self.assertEqual(self.assert_not_ok(text, "exchange").integrity["fault"], "mismatch")

    def test_exchange_unescaped_in_transit_is_named(self):
        original = text_of(EXCHANGE)
        self.assertIn("\\u2014", original)
        text = original.replace("\\u2014", "—")
        block = self.assert_not_ok(text, "exchange")
        self.assertEqual(block.integrity["fault"], "unescaped-in-transit")
        self.assertEqual((block.fields["round"], block.fields["from"]), (1, "worker"))
        self.assertNotIn("record", block.fields)

    def test_exchange_without_trailer_fails(self):
        text = drop_line(text_of(EXCHANGE), lambda ln: ln.startswith("# sha256 "))
        self.assertEqual(self.assert_not_ok(text, "exchange").integrity["fault"], "no-trailer")

    def test_light_missing_a_label_line_is_malformed(self):
        text = drop_line(text_of(LIGHT), lambda ln: ln.strip().startswith("would assume:"))
        self.assertIn("would assume", self.assert_not_ok(text, "light").error)

    def test_light_missing_reply_line_is_malformed(self):
        text = drop_line(text_of(LIGHT), lambda ln: ln.startswith("Reply:"))
        self.assertIn("Reply", self.assert_not_ok(text, "light").error)

    def test_begin_cut_leaves_an_orphan_end_reported(self):
        for path, kind in ((PROBE_OUTPUT, "probe-output"), (LIGHT, "light"),
                           (EXCHANGE, "exchange"), (RELAY, "relay")):
            with self.subTest(kind=kind):
                text = text_of(path).split("\n", 1)[1]
                block = self.assert_not_ok(text, kind)
                self.assertIn("no BEGIN", block.error)


# ---------------------------------------------------------------------------
# 4. Normalization, nesting, order, shape
# ---------------------------------------------------------------------------


class Normalization(unittest.TestCase):

    def test_crlf_input_reads_as_lf_for_every_fixture(self):
        for path in (PROBE_OUTPUT, LIGHT, EXCHANGE, RELAY):
            with self.subTest(fixture=path.name):
                lf = take(text_of(path)).as_json()
                crlf = take(to_crlf(text_of(path))).as_json()
                self.assertEqual(crlf, lf)
                self.assertTrue(all(b["integrity"]["ok"] for b in crlf["blocks"]))

    def test_normalize_counts_crlf_and_leaves_a_lone_cr(self):
        norm = shapes.normalize(b"a\r\nb\rc\r\n")
        self.assertEqual((norm.text, norm.crlf_replaced), ("a\nb\rc\n", 2))

    def test_bom_is_dropped_and_non_utf8_refused(self):
        self.assertTrue(shapes.normalize(b"\xef\xbb\xbfhi").bom_stripped)
        with self.assertRaises(ValueError):
            shapes.normalize(b"\xff\xfe bad")


class NoNesting(unittest.TestCase):

    def test_probe_output_carrying_light_and_exchange_lines_is_one_block(self):
        """The recorded probe output carries a whole-line LIGHT BEGIN and
        BALE EXCHANGE BEGIN (the emissions it recorded); a span is opaque."""
        text = text_of(PROBE_OUTPUT)
        self.assertIn("\n=== LIGHT BEGIN " + SID + " ===\n", text)
        self.assertIn("\nBALE EXCHANGE BEGIN " + SID + "\n", text)
        self.assertEqual([b.kind for b in take(text).blocks], ["probe-output"])

    def test_relay_containing_sentinel_lines_is_one_block(self):
        """A relay that inlines another block's sentinels is still one block."""
        lines = text_of(RELAY).split("\n")
        inner = text_of(LIGHT).rstrip("\n").split("\n") + text_of(EXCHANGE).rstrip("\n").split("\n")
        text = "\n".join(lines[:5] + inner + lines[5:])
        block = only(take(text))
        self.assertEqual((block.kind, block.ok), ("relay", True))

    def test_indented_relay_end_does_not_close(self):
        """bale's _inline_lines indents an inlined sentinel two spaces."""
        lines = text_of(RELAY).split("\n")
        text = "\n".join(lines[:5] + ["  " + lines[-1]] + lines[5:])
        block = only(take(text))
        self.assertEqual(block.end_line, len(lines) + 1)


class OrderAndShape(unittest.TestCase):

    def test_prose_is_shape_prose_ok(self):
        report = take("Nothing to carry here.\nJust words.\n")
        self.assertEqual(report.as_json(), {"shape": "prose", "blocks": []})
        self.assertTrue(report.ok)

    def test_shape_is_the_last_block_and_blocks_are_in_order(self):
        text = ("Notes first.\n" + text_of(LIGHT) + "\nthen\n"
                + fenced(text_of(PROBE_SCRIPT)) + text_of(EXCHANGE) + "\nprose\n")
        report = take(text)
        self.assertEqual([b.kind for b in report.blocks], ["light", "probe", "exchange"])
        self.assertEqual(report.shape, "exchange")
        self.assertTrue(report.ok)

    def test_a_fence_around_an_exchange_block_is_transparent(self):
        """bale's own parser ignores a chat's fence lines; so does take."""
        report = take("```\n" + text_of(EXCHANGE) + "```\nafter\n")
        self.assertEqual([(b.kind, b.ok) for b in report.blocks], [("exchange", True)])

    def test_a_closing_fence_is_not_mistaken_for_a_probe_opener(self):
        text = "```\nplain\n```\nprose\n" + fenced(text_of(PROBE_SCRIPT))
        self.assertEqual([b.kind for b in take(text).blocks], ["probe"])


# ---------------------------------------------------------------------------
# 5. The verb
# ---------------------------------------------------------------------------


def one_line(test: unittest.TestCase, stdout: str) -> dict:
    lines = stdout.split("\n")
    test.assertEqual((len(lines), lines[1]), (2, ""), f"one JSON line: {stdout!r}")
    obj = json.loads(lines[0])
    test.assertEqual(obj["command"], "take")
    return obj


class Verb(unittest.TestCase):

    def test_each_fixture_subprocess_one_line_exit_zero(self):
        for path, kind in ((PROBE_OUTPUT, "probe-output"), (LIGHT, "light"),
                           (EXCHANGE, "exchange"), (RELAY, "relay")):
            with self.subTest(kind=kind):
                run = run_cli("take", str(path), "--json")
                obj = one_line(self, run.stdout)
                self.assertEqual((run.code, obj["ok"], obj["shape"]), (0, True, kind))
                self.assertEqual(obj["input"]["bytes"], path.stat().st_size)

    def test_derived_negative_exit_one_one_line_no_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "cut.txt"
            bad.write_text(drop_line(text_of(PROBE_OUTPUT),
                                     lambda ln: ln.startswith("uname: ")), encoding="utf-8")
            run = run_cli("take", str(bad), "--json")
        obj = one_line(self, run.stdout)
        self.assertEqual((run.code, obj["ok"]), (1, False))
        self.assertFalse(obj["blocks"][0]["integrity"]["ok"])
        self.assertIn("error", obj["blocks"][0])
        self.assertNotIn("Traceback", run.stderr)

    def test_stdin_dash_reads_bytes_crlf_included(self):
        data = to_crlf(text_of(EXCHANGE)).encode("utf-8")
        run = run_cli("take", "-", "--json", stdin=data)
        obj = one_line(self, run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["shape"]), (0, True, "exchange"))
        self.assertEqual(obj["input"]["source"], "<stdin>")
        self.assertEqual(obj["input"]["crlf_normalized"], 34)

    def test_stdin_inprocess(self):
        run = run_inprocess("take", "-", "--json", stdin=RELAY.read_bytes())
        obj = one_line(self, run.stdout)
        self.assertEqual(obj["blocks"][0]["to"], "planner")

    def test_unreadable_and_non_utf8_inputs_are_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as d:
            junk = Path(d) / "junk.bin"
            junk.write_bytes(b"\xff\xfe\x00 not text")
            for argv in (["take", str(Path(d) / "missing.txt")], ["take", str(junk)]):
                with self.subTest(argv=argv[-1]):
                    run = run_cli(*argv, "--json")
                    obj = one_line(self, run.stdout)
                    self.assertEqual((run.code, obj["ok"], obj["shape"]), (1, False, None))
                    self.assertTrue(obj["input_error"])
                    self.assertNotIn("Traceback", run.stderr)

    def test_human_lines_one_per_block(self):
        run = run_inprocess("take", str(PROBE_OUTPUT))
        lines = run.stdout.rstrip("\n").split("\n")
        self.assertEqual(len(lines), 2)
        self.assertIn("shape probe-output", lines[0])
        self.assertIn("slug=twine-take-specimens", lines[1])
        self.assertIn("integrity ok (661 lines)", lines[1])

    def test_a_probe_with_a_side_effect_is_never_run(self):
        """A probe block whose script writes a marker file is read and
        reported; the marker never appears."""
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "executed"
            script = text_of(PROBE_SCRIPT).replace(
                "probe() {\n", f"probe() {{\n  touch '{marker}'\n", 1)
            turn = Path(d) / "turn.txt"
            turn.write_text("Run this:\n" + fenced(script), encoding="utf-8")
            for argv in (["take", str(turn), "--json"], ["take", str(turn)]):
                run = run_cli(*argv)
                self.assertEqual(run.code, 0)
            run = run_cli("take", "-", "--json", stdin=turn.read_bytes())
            obj = one_line(self, run.stdout)
            self.assertIn(f"touch '{marker}'", obj["blocks"][0]["script"])
            self.assertFalse(marker.exists(), "take executed the probe it read")

    def test_take_imports_nothing_that_can_run_or_reach_out(self):
        """The parse layer and the verb import no process, OS-command or
        network module — `take` executes nothing by construction."""
        forbidden = {"subprocess", "os", "shutil", "socket", "urllib", "http",
                     "multiprocessing", "pty", "asyncio", "ctypes"}
        for rel in ("twine/shapes.py", "twine/commands/take.py"):
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
            roots = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    roots.add(node.module.split(".")[0])
            with self.subTest(file=rel):
                self.assertFalse(roots & forbidden, roots & forbidden)


if __name__ == "__main__":
    unittest.main()

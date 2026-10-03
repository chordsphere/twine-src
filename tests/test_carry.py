"""`twine carry probe` (Arc 1 session 2b-i): choosing the block, the
refusals, nothing executing without --run, the run and its verified
paste-back, and the ways a run is ran-but-not-ok.

Every probe here is the crafter's recorded scaffold
(fixtures/bale-0.4.45/crafter/--probe-twine-take-fixture.txt) with its
placeholders filled mechanically by tests.helpers.filled_probe, or a
byte-level derivation of that — never a script typed from scratch.
Probes that must prove "nothing ran" write a marker file into the test's
own temp directory, named through the environment. Sections:

  1. Helpers
  2. Choosing the block
  3. Refused before running
  4. Without --run: shown, never executed
  5. With --run: the verified paste-back
  6. Ran, but not ok
  7. The seam: what carry probe hands ctx.run
"""

from __future__ import annotations

import ast
import io
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from twine import REPO_ROOT, shapes
from twine.cli import Context, main
from twine.commands.carry import STDOUT_CAP_BYTES
from twine.process import RunResult, run_process

from tests.helpers import (PROBE_SLUG, RecordingRunner, Run, emission_relpath,
                           dies_within, fenced_probe, filled_probe, run_cli,
                           scaffold, turn)

# ---------------------------------------------------------------------------
# 1. Helpers
# ---------------------------------------------------------------------------

LIGHT = REPO_ROOT / emission_relpath("crafter", ["--light-block", "-"])
FIXED_KEYS = {"slug", "ran", "confined", "exit_code", "timed_out", "integrity",
              "output"}
MARKER_ENV = "TWINE_TEST_MARKER"
MARKER_BODY = 'touch "$TWINE_TEST_MARKER"\necho "--- section: marker ---"\necho touched'


def one_line(test: unittest.TestCase, stdout: str) -> dict:
    lines = stdout.split("\n")
    test.assertEqual((len(lines), lines[1]), (2, ""), f"one JSON line: {stdout!r}")
    obj = json.loads(lines[0])
    test.assertEqual(obj["command"], "carry probe")
    return obj


def run_carry(*argv: str, runner=None, env: dict | None = None,
              stdin: bytes = b"") -> Run:
    """In-process, with the real bash lookup and (by default) the real
    runner — or a double through the seam."""
    out, err = io.StringIO(), io.StringIO()
    ctx = Context(env=env if env is not None else {"PATH": os.environ.get("PATH", "")},
                  stdout=out, stderr=err, which=shutil.which,
                  stdin=io.BytesIO(stdin), run=runner or run_process)
    code = main(["carry", "probe", *argv], ctx=ctx)
    return Run(code, out.getvalue(), err.getvalue())


class TempCase(unittest.TestCase):
    """A temp dir per test, a marker path inside it, a writer for turns."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="twine-carry-")
        self.dir = Path(self._dir.name)
        self.marker = self.dir / "executed"
        self.env = {MARKER_ENV: str(self.marker)}

    def tearDown(self):
        self._dir.cleanup()

    def write(self, text: str, name: str = "turn.txt") -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def probe_turn(self, script: str | None = None, name: str = "turn.txt") -> Path:
        return self.write(turn("Run this and paste the output back:", "",
                               fenced_probe(script or filled_probe()),
                               "Thanks."), name)

    def assert_refused(self, obj: dict, code: int, *needles: str) -> None:
        self.assertEqual((code, obj["ok"], obj["ran"]), (1, False, False))
        self.assertIsNone(obj["exit_code"])
        for needle in needles:
            self.assertIn(needle, obj["reason"])


# ---------------------------------------------------------------------------
# 2. Choosing the block
# ---------------------------------------------------------------------------


class ChoosingTheBlock(TempCase):

    def test_prose_has_no_probe_block_refused(self):
        path = self.write("Nothing to run here.\n")
        run = run_cli("carry", "probe", str(path), "--json")
        obj = one_line(self, run.stdout)
        self.assert_refused(obj, run.code, "no probe block")
        self.assertIsNone(obj["slug"])

    def test_two_probes_without_block_refused_naming_both(self):
        script = filled_probe()
        path = self.write(turn(fenced_probe(script), "and", fenced_probe(script)))
        run = run_cli("carry", "probe", str(path), "--json", "--run",
                      extra_env=self.env)
        obj = one_line(self, run.stdout)
        self.assert_refused(obj, run.code, "2 probe blocks", "[1]", "[2]", "--block")
        self.assertFalse(self.marker.exists())

    def test_block_number_is_takes_number_among_all_blocks(self):
        """A light block first, then two probes: `take` prints the second
        probe as [3]; `--block 3` picks it, and its body is the one run."""
        first = filled_probe(body='echo "--- section: first ---"\necho first')
        second = filled_probe(body='echo "--- section: second ---"\necho second')
        path = self.write(turn(LIGHT.read_text(encoding="utf-8"),
                               fenced_probe(first), fenced_probe(second)))
        take = json.loads(run_cli("take", str(path), "--json").stdout)
        self.assertEqual([b["kind"] for b in take["blocks"]],
                         ["light", "probe", "probe"])
        run = run_cli("carry", "probe", str(path), "--block", "3", "--run", "--json")
        obj = one_line(self, run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["block"]), (0, True, 3))
        self.assertIn("\nsecond\n", obj["output"])
        self.assertEqual(obj["script"], take["blocks"][2]["script"])

    def test_block_naming_a_non_probe_refused(self):
        path = self.write(turn(LIGHT.read_text(encoding="utf-8"),
                               fenced_probe(filled_probe(body=MARKER_BODY))))
        run = run_cli("carry", "probe", str(path), "--block", "1", "--run", "--json",
                      extra_env=self.env)
        self.assert_refused(one_line(self, run.stdout), run.code, "light", "not a probe")
        self.assertFalse(self.marker.exists())

    def test_block_out_of_range_refused(self):
        path = self.probe_turn()
        for n in ("0", "2", "-1"):
            with self.subTest(block=n):
                run = run_cli("carry", "probe", str(path), "--block", n, "--json")
                self.assert_refused(one_line(self, run.stdout), run.code, "names no block")

    def test_one_probe_among_other_blocks_needs_no_block_flag(self):
        path = self.write(turn(LIGHT.read_text(encoding="utf-8"),
                               fenced_probe(filled_probe())))
        obj = one_line(self, run_cli("carry", "probe", str(path), "--json").stdout)
        self.assertEqual((obj["ok"], obj["block"], obj["slug"]), (True, 2, PROBE_SLUG))


# ---------------------------------------------------------------------------
# 3. Refused before running
# ---------------------------------------------------------------------------


def without_read_only(script: str) -> str:
    lines = script.split("\n")
    kept = [ln for ln in lines if not ln.startswith("# Read-only:")]
    assert len(kept) == len(lines) - 1
    return "\n".join(kept)


def with_marker(script: str) -> str:
    """The script with a marker-touching line first in probe()'s body."""
    return script.replace("probe() {\n", 'probe() {\n  touch "$TWINE_TEST_MARKER"\n', 1)


class RefusedBeforeRunning(TempCase):

    def refused_both_ways(self, path: Path, *needles: str) -> None:
        """Refused with --run and without, through the CLI (marker never
        appears) and in-process (the seam is never called)."""
        for extra in ([], ["--run"]):
            with self.subTest(run=bool(extra)):
                run = run_cli("carry", "probe", str(path), "--json", *extra,
                              extra_env=self.env)
                self.assert_refused(one_line(self, run.stdout), run.code, *needles)
                self.assertNotIn("Traceback", run.stderr)
                runner = RecordingRunner()
                run = run_carry(str(path), "--json", *extra, runner=runner)
                self.assertEqual(run.code, 1)
                self.assertEqual(runner.calls, [], "refused, yet the seam was called")
        self.assertFalse(self.marker.exists(), "a refused probe executed")

    def test_unfilled_scaffold_refused(self):
        script = with_marker(scaffold())
        self.assertIn("TODO(worker)", script)
        self.refused_both_ways(self.probe_turn(script), "TODO(worker)", "unfilled")

    def test_one_leftover_todo_anywhere_refused(self):
        script = with_marker(filled_probe()).replace(
            '  echo "bash ok"\n', '  echo "bash ok"\n  # TODO(worker): one more section\n', 1)
        self.assertEqual(script.count("TODO(worker)"), 1)
        self.refused_both_ways(self.probe_turn(script), "TODO(worker)")

    def test_no_read_only_header_line_refused(self):
        script = with_marker(without_read_only(filled_probe()))
        self.refused_both_ways(self.probe_turn(script), "Read-only")

    def test_an_empty_read_only_declaration_declares_nothing(self):
        script = with_marker(filled_probe()).replace(
            "# Read-only: writes nothing anywhere; stdout is the only output.",
            "# Read-only:")
        self.refused_both_ways(self.probe_turn(script), "Read-only")

    def test_malformed_unclosed_fence_refused(self):
        text = fenced_probe(with_marker(filled_probe())).rstrip("`\n") + "\n"
        self.refused_both_ways(self.write(text), "malformed", "never closes")

    def test_existing_out_refused_and_left_untouched(self):
        out = self.dir / "paste.txt"
        out.write_bytes(b"precious\n")
        path = self.probe_turn(with_marker(filled_probe()))
        self.refused_both_ways_with(path, ["--out", str(out)], "already exists")
        self.assertEqual(out.read_bytes(), b"precious\n")

    def refused_both_ways_with(self, path: Path, flags: list[str], *needles: str):
        for extra in ([], ["--run"]):
            run = run_cli("carry", "probe", str(path), "--json", *flags, *extra,
                          extra_env=self.env)
            self.assert_refused(one_line(self, run.stdout), run.code, *needles)
        self.assertFalse(self.marker.exists())

    def test_bad_timeout_and_cwd_refused(self):
        path = self.probe_turn(with_marker(filled_probe()))
        self.refused_both_ways_with(path, ["--timeout", "0"], "--timeout")
        self.refused_both_ways_with(path, ["--cwd", str(self.dir / "nope")],
                                    "not a directory")

    def test_every_reason_is_named_at_once(self):
        script = without_read_only(scaffold())
        run = run_cli("carry", "probe", str(self.probe_turn(script)), "--json")
        obj = one_line(self, run.stdout)
        self.assertEqual(len(obj["refusals"]), 2, obj["refusals"])

    def test_unreadable_input_refused_without_traceback(self):
        run = run_cli("carry", "probe", str(self.dir / "missing.txt"), "--json")
        self.assert_refused(one_line(self, run.stdout), run.code, "cannot read")
        self.assertNotIn("Traceback", run.stderr)

    def test_human_mode_refusal_is_one_line_naming_why(self):
        run = run_cli("carry", "probe", str(self.probe_turn(scaffold())), "--run")
        self.assertEqual(run.code, 1)
        self.assertEqual(len(run.stdout.splitlines()), 1)
        self.assertIn("refused", run.stdout)
        self.assertIn("TODO(worker)", run.stdout)


# ---------------------------------------------------------------------------
# 4. Without --run: shown, never executed
# ---------------------------------------------------------------------------


class WithoutRun(TempCase):

    def test_side_effecting_probe_leaves_no_trace(self):
        path = self.probe_turn(filled_probe(body=MARKER_BODY))
        for extra in (["--json"], []):
            run = run_cli("carry", "probe", str(path), *extra, extra_env=self.env)
            self.assertEqual(run.code, 0)
        run = run_cli("carry", "probe", "-", "--json", extra_env=self.env,
                      stdin=path.read_bytes())
        obj = one_line(self, run.stdout)
        self.assertEqual((obj["ok"], obj["ran"], obj["exit_code"], obj["output"]),
                         (True, False, None, ""))
        self.assertFalse(self.marker.exists(), "carry probe ran without --run")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["turn.txt"])

    def test_the_seam_is_never_called_without_run(self):
        runner = RecordingRunner()
        run = run_carry(str(self.probe_turn()), "--json", runner=runner)
        self.assertEqual(run.code, 0)
        self.assertEqual(runner.calls, [])

    def test_json_reports_slug_header_and_script(self):
        script = filled_probe()
        obj = one_line(self, run_cli("carry", "probe", str(self.probe_turn(script)),
                                     "--json").stdout)
        self.assertTrue(FIXED_KEYS <= set(obj), FIXED_KEYS - set(obj))
        self.assertEqual((obj["slug"], obj["script"], obj["confined"], obj["timed_out"]),
                         (PROBE_SLUG, script, False, False))
        self.assertEqual(obj["header"][0], "#!/usr/bin/env bash")
        self.assertTrue(obj["header"][1].startswith(f"# PROBE {PROBE_SLUG}: "))
        self.assertTrue(any(h.startswith("# Read-only:") for h in obj["header"]))
        self.assertIsInstance(obj["integrity"], dict)
        self.assertFalse(obj["integrity"]["ok"])

    def test_human_stdout_is_exactly_the_script(self):
        script = filled_probe()
        run = run_cli("carry", "probe", str(self.probe_turn(script)))
        self.assertEqual((run.code, run.stdout), (0, script))
        self.assertIn("not run", run.stderr)
        self.assertIn("--run", run.stderr)


# ---------------------------------------------------------------------------
# 5. With --run: the verified paste-back
# ---------------------------------------------------------------------------


class WithRun(TempCase):

    def test_paste_back_verifies_and_reads_back_through_take(self):
        path = self.probe_turn()
        run = run_cli("carry", "probe", str(path), "--run", "--json")
        obj = one_line(self, run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["ran"], obj["exit_code"],
                          obj["timed_out"], obj["confined"]),
                         (0, True, True, 0, False, False))
        self.assertTrue(FIXED_KEYS <= set(obj))
        out = obj["output"]
        self.assertTrue(out.startswith(f"=== PROBE BEGIN {PROBE_SLUG} ===\n"))
        self.assertTrue(out.endswith(f"=== PROBE END {PROBE_SLUG} ===\n"))
        self.assertNotIn("\r", out)
        self.assertEqual(obj["integrity"], {"ok": True, "basis": "line-count",
                                            "expected_lines": 2, "found_lines": 2})
        report = shapes.find_blocks(out)
        self.assertEqual([(b.kind, b.ok, b.fields["slug"]) for b in report.blocks],
                         [("probe-output", True, PROBE_SLUG)])
        back = json.loads(run_cli("take", "-", "--json", stdin=out.encode()).stdout)
        self.assertEqual((back["ok"], back["shape"], len(back["blocks"])),
                         (True, "probe-output", 1))

    def test_human_stdout_is_exactly_the_paste_back(self):
        path = self.probe_turn()
        expected = one_line(self, run_cli("carry", "probe", str(path), "--run",
                                          "--json").stdout)["output"]
        run = run_cli("carry", "probe", str(path), "--run")
        self.assertEqual((run.code, run.stdout), (0, expected))
        self.assertIn("unconfined", run.stderr)

    def test_out_writes_the_paste_back_and_only_that(self):
        out = self.dir / "paste.txt"
        path = self.probe_turn()
        run = run_cli("carry", "probe", str(path), "--run", "--json", "--out", str(out))
        obj = one_line(self, run.stdout)
        self.assertEqual((run.code, obj["out"]), (0, str(out)))
        self.assertEqual(out.read_bytes(), obj["output"].encode("utf-8"))
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()),
                         ["paste.txt", "turn.txt"])

    def test_stdin_and_crlf_turn(self):
        data = self.probe_turn().read_bytes().replace(b"\n", b"\r\n")
        obj = one_line(self, run_cli("carry", "probe", "-", "--run", "--json",
                                     stdin=data).stdout)
        self.assertEqual((obj["ok"], obj["input"]["source"]), (True, "<stdin>"))
        self.assertGreater(obj["input"]["crlf_normalized"], 0)

    def test_runs_in_cwd_and_inherits_the_environment(self):
        body = ('echo "--- section: where ---"\npwd\n'
                'echo "--- section: env ---"\necho "marker=$TWINE_TEST_MARKER"')
        path = self.probe_turn(filled_probe(body=body))
        obj = one_line(self, run_cli("carry", "probe", str(path), "--run", "--json",
                                     "--cwd", str(self.dir), extra_env=self.env).stdout)
        self.assertTrue(obj["ok"], obj["reason"])
        self.assertIn(f"\n{self.dir.resolve()}\n", obj["output"])
        self.assertIn(f"\nmarker={self.marker}\n", obj["output"])
        self.assertEqual(obj["cwd"], str(self.dir.resolve()))

    def test_stderr_is_reported_not_carried(self):
        body = 'echo "--- section: s ---"\necho visible'
        script = filled_probe(body=body).replace(
            "emit_probe_block\n", "emit_probe_block\necho 'to stderr' >&2\n", 1)
        obj = one_line(self, run_cli("carry", "probe", str(self.probe_turn(script)),
                                     "--run", "--json").stdout)
        self.assertTrue(obj["ok"], obj["reason"])
        self.assertEqual(obj["stderr"], "to stderr\n")
        self.assertNotIn("to stderr", obj["output"])

    def test_isolated_entrypoint_runs_carry_probe(self):
        """run_cli is `python3 -I -S -B bin/twine`; the verb works there."""
        run = run_cli("carry", "probe", str(self.probe_turn()), "--run", "--json")
        self.assertEqual(run.code, 0)
        self.assertNotIn("Traceback", run.stderr)


# ---------------------------------------------------------------------------
# 6. Ran, but not ok
# ---------------------------------------------------------------------------


class RanButNotOk(TempCase):

    def ran_not_ok(self, script: str, *needles: str, flags: tuple = ()) -> dict:
        run = run_cli("carry", "probe", str(self.probe_turn(script)), "--run", "--json",
                      *flags, extra_env=self.env)
        obj = one_line(self, run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["ran"]), (1, False, True))
        self.assertNotIn("Traceback", run.stderr)
        for needle in needles:
            self.assertIn(needle, obj["reason"])
        return obj

    def test_wrong_trailer_count(self):
        """A line printed between the output and its trailer: the trailer
        counts one less than the block carries."""
        script = filled_probe().replace(
            "  printf '%s\\n' \"$out\"\n", "  printf '%s\\n' \"$out\"\n  echo extra\n", 1)
        self.assertIn("echo extra", script)
        obj = self.ran_not_ok(script, "integrity")
        self.assertEqual(obj["exit_code"], 0)
        self.assertFalse(obj["integrity"]["ok"])
        self.assertEqual((obj["integrity"]["expected_lines"],
                          obj["integrity"]["found_lines"]), (2, 3))
        self.assertIn("extra", obj["output"], "the found block is still reported")

    def test_human_mode_not_ok_prints_no_paste_back(self):
        script = filled_probe().replace(
            "  printf '%s\\n' \"$out\"\n", "  printf '%s\\n' \"$out\"\n  echo extra\n", 1)
        run = run_cli("carry", "probe", str(self.probe_turn(script)), "--run")
        self.assertEqual(run.code, 1)
        self.assertNotIn("=== PROBE BEGIN", run.stdout)
        self.assertIn("NOT OK", run.stdout)

    def test_slug_mismatch(self):
        script = filled_probe().replace(f"BEGIN {PROBE_SLUG} ===", "BEGIN other-slug ===") \
                               .replace(f"END {PROBE_SLUG} ===", "END other-slug ===")
        obj = self.ran_not_ok(script, "slug")
        self.assertTrue(obj["integrity"]["ok"])

    def test_nonzero_exit(self):
        script = filled_probe().replace("emit_probe_block\n", "emit_probe_block\nexit 3\n", 1)
        self.assertEqual(self.ran_not_ok(script, "exited 3")["exit_code"], 3)

    def test_no_output_block_at_all(self):
        """A file-based (§4.4) probe writes ./probe-output/ and prints no
        block; it is ran-but-not-ok, never built for."""
        script = filled_probe().replace("emit_probe_block\n", "true\n", 1)
        obj = self.ran_not_ok(script, "no `=== PROBE BEGIN")
        self.assertEqual(obj["output"], "")

    def test_two_output_blocks(self):
        script = filled_probe().replace(
            "emit_probe_block\n", "emit_probe_block\nemit_probe_block\n", 1)
        self.ran_not_ok(script, "2 probe-output blocks")

    def test_output_past_the_cap_is_stopped_and_not_ok(self):
        n = STDOUT_CAP_BYTES + 4096
        body = f'echo "--- section: flood ---"\nhead -c {n} /dev/zero | tr "\\\\0" x'
        obj = self.ran_not_ok(filled_probe(body=body), "cap", str(STDOUT_CAP_BYTES))
        self.assertTrue(obj["capped"])
        self.assertIsNone(obj["exit_code"])
        self.assertEqual(obj["stdout_cap_bytes"], STDOUT_CAP_BYTES)

    def test_timeout_stops_a_sleeping_child_promptly(self):
        body = ('echo "--- section: sleeper ---"\n'
                'sleep 60 &\necho "$!" > "$TWINE_TEST_MARKER"\nwait')
        started = time.monotonic()
        obj = self.ran_not_ok(filled_probe(body=body), "timed out",
                              flags=("--timeout", "1"))
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 15, f"the run outlived its timeout: {elapsed:.1f}s")
        self.assertEqual((obj["timed_out"], obj["exit_code"]), (True, None))
        child = int(self.marker.read_text().strip())
        self.assertTrue(dies_within(child), f"sleep {child} outlived the timeout")

    def test_out_not_written_when_not_ok(self):
        out = self.dir / "paste.txt"
        script = filled_probe().replace("emit_probe_block\n", "emit_probe_block\nexit 3\n", 1)
        self.ran_not_ok(script, "exited 3", flags=("--out", str(out)))
        self.assertFalse(out.exists())


# ---------------------------------------------------------------------------
# 7. The seam: what carry probe hands ctx.run
# ---------------------------------------------------------------------------


class ThroughTheSeam(TempCase):

    def test_bash_dash_c_the_script_with_timeout_cap_env_and_no_stdin(self):
        script = filled_probe()
        runner = RecordingRunner()
        env = {"PATH": os.environ.get("PATH", ""), "PROBE_ENV": "x"}
        run_carry(str(self.probe_turn(script)), "--run", "--json", "--timeout", "7",
                  "--cwd", str(self.dir), runner=runner, env=env)
        self.assertEqual(len(runner.calls), 1)
        call = runner.calls[0]
        self.assertEqual(Path(call["argv"][0]).name, "bash")
        self.assertEqual(call["argv"][1:3], ["-c", script])
        self.assertEqual((call["timeout"], call["stdout_cap"], call["stdin"]),
                         (7.0, STDOUT_CAP_BYTES, None))
        self.assertEqual(call["env"], env)
        self.assertEqual(Path(call["cwd"]), self.dir.resolve())

    def test_verification_reads_the_seams_bytes(self):
        """A double answering with a real paste-back (CRLF, as a transport
        would add) verifies; the output is LF."""
        real = one_line(self, run_cli("carry", "probe", str(self.probe_turn()),
                                      "--run", "--json").stdout)["output"]
        canned = RunResult(argv=("bash",), exit_code=0,
                           stdout=("noise before\n" + real).replace("\n", "\r\n").encode(),
                           stderr=b"")
        run = run_carry(str(self.probe_turn()), "--run", "--json",
                        runner=RecordingRunner(canned))
        obj = one_line(self, run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["output"]), (0, True, real))

    def test_confined_is_read_from_the_runner_and_nowhere_else(self):
        """The one `confined` switch point (session 2b-ii, from 2b-i's
        Proposals): the flag follows twine.process.runner_confines(ctx.run).
        The real runner and every Arc 1 double report false; a double that
        declares `confines = True` stands in for Arc 2's sandbox runner."""
        class ConfiningDouble(RecordingRunner):
            confines = True
        for runner, expected in ((RecordingRunner(), False), (ConfiningDouble(), True),
                                 (run_process, False)):
            with self.subTest(runner=type(runner).__name__):
                obj = one_line(self, run_carry(str(self.probe_turn()), "--json",
                                               runner=runner).stdout)
                self.assertIs(obj["confined"], expected)
        source = (REPO_ROOT / "twine/commands/carry.py").read_text(encoding="utf-8")
        self.assertNotIn('"confined": False', source)

    def test_carry_imports_nothing_that_runs_or_reaches_out(self):
        forbidden = {"subprocess", "os", "shutil", "socket", "urllib", "http",
                     "multiprocessing", "pty", "asyncio", "ctypes"}
        tree = ast.parse((REPO_ROOT / "twine/commands/carry.py").read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        self.assertFalse(roots & forbidden, roots & forbidden)


if __name__ == "__main__":
    unittest.main()

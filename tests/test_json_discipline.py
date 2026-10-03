"""The --json discipline, every verb: exactly one JSON object line on
stdout with `command` and `ok`; exit 0 iff ok, 1 on a reported failure,
2 only on an internal error; a handled failure never prints a traceback."""

from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from pathlib import Path

from twine.cli import Context, run_command
from twine.registry import Command, Result, load_registry

from twine import REPO_ROOT

from tests.helpers import (StubBale, TempRoots, emission_relpath, fenced_probe,
                           filled_probe, fixture_relpath, run_cli, run_inprocess)


def one_json_line(test: unittest.TestCase, stdout: str, command: str) -> dict:
    lines = stdout.split("\n")
    test.assertEqual(len(lines), 2, f"stdout must be exactly one line: {stdout!r}")
    test.assertEqual(lines[1], "", "stdout must end with one newline")
    obj = json.loads(lines[0])
    test.assertIsInstance(obj, dict)
    test.assertEqual(obj["command"], command)
    test.assertIsInstance(obj["ok"], bool)
    return obj


class EveryVerbHasAJsonTwin(unittest.TestCase):

    def setUp(self):
        self.roots = TempRoots()
        self._turns = tempfile.TemporaryDirectory(prefix="twine-json-")
        self.probe_turn = Path(self._turns.name) / "turn.txt"
        self.probe_turn.write_text(fenced_probe(filled_probe()), encoding="utf-8")
        # The two bale hand-offs run a stub bale (a double, never bale):
        # relay replays the crafter's exchange emission, apply the recorded
        # dry-run line.
        self.exchange = REPO_ROOT / emission_relpath("crafter", ["--emit-block", "-"])
        self.dry_run = REPO_ROOT / fixture_relpath(
            ["apply", "--dry-run", "--json", "/any/response.tar.gz"], "repo")
        self.stub = StubBale(relay_stdout=self.exchange, apply_stdout=self.dry_run)

    def tearDown(self):
        self.roots.cleanup()
        self._turns.cleanup()
        self.stub.cleanup()

    def argv_for(self, name: str) -> list[str]:
        """A happy-path argv per verb; bale check against the ok root, take
        on a recorded light block (an intact block: ok true, exit 0), carry
        probe on a turn carrying one filled probe, shown and not run (ok
        true, exit 0; nothing executes without --run); carry exchange on the
        crafter's exchange block and carry response on an existing file,
        each against the stub bale (ok true, exit 0); transitions on the
        real table (ok true, exit 0; it reads no bale)."""
        argv = name.split(" ")
        if name == "bale check":
            argv += ["--bale-root", str(self.roots.ok)]
        if name == "take":
            argv.append(str(REPO_ROOT / emission_relpath(
                "crafter", ["--light-block", "-"])))
        if name == "carry probe":
            argv.append(str(self.probe_turn))
        if name == "carry exchange":
            argv += [str(self.exchange), "--bale-root", str(self.stub.root)]
        if name == "carry response":
            argv += [str(self.dry_run), "--bale-root", str(self.stub.root)]
        return argv

    def test_every_registered_verb_emits_one_line_subprocess(self):
        for name, cmd in load_registry().items():
            with self.subTest(verb=name):
                self.assertTrue(cmd.json, f"{name} should have a --json twin")
                run = run_cli(*self.argv_for(name), "--json")
                obj = one_json_line(self, run.stdout, name)
                self.assertEqual(run.code, 0 if obj["ok"] else 1)
                self.assertNotIn("Traceback", run.stderr)

    def test_every_registered_verb_emits_one_line_inprocess(self):
        for name in load_registry():
            with self.subTest(verb=name):
                run = run_inprocess(*self.argv_for(name), "--json")
                obj = one_json_line(self, run.stdout, name)
                self.assertEqual(run.code, 0 if obj["ok"] else 1)

    def test_without_json_stdout_is_readable_lines(self):
        """No line of human stdout is the JSON twin. (A line may still
        start with `{`: carry exchange prints bale's paste block exactly,
        and its body is the exchange record's JSON — what it carries, not
        twine's twin.)"""
        for name in load_registry():
            with self.subTest(verb=name):
                run = run_inprocess(*self.argv_for(name))
                self.assertTrue(run.stdout.strip(), "human output expected")
                for line in run.stdout.rstrip("\n").split("\n"):
                    self.assertFalse(is_json_twin(line),
                                     "no JSON twin on stdout without --json")
                if name != "carry exchange":
                    for line in run.stdout.rstrip("\n").split("\n"):
                        self.assertFalse(line.startswith("{"),
                                         "no JSON on stdout without --json")


def is_json_twin(line: str) -> bool:
    """Whether `line` is a twine JSON twin: one object with command and ok."""
    try:
        obj = json.loads(line)
    except ValueError:
        return False
    return isinstance(obj, dict) and {"command", "ok"} <= set(obj)


class ExitCodes(unittest.TestCase):

    def setUp(self):
        self.roots = TempRoots()

    def tearDown(self):
        self.roots.cleanup()

    def test_reported_failure_is_exit_1_with_one_line_and_no_traceback(self):
        run = run_cli("bale", "check", "--json", "--bale-root", str(self.roots.other))
        obj = one_json_line(self, run.stdout, "bale check")
        self.assertFalse(obj["ok"])
        self.assertEqual(run.code, 1)
        self.assertNotIn("Traceback", run.stderr)

    def test_internal_error_is_exit_2_with_one_line_then_traceback(self):
        def boom(ctx, args):
            raise ValueError("deliberate")
        cmd = Command(name="boom", summary="raises", handler=boom)
        out, err = io.StringIO(), io.StringIO()
        ctx = Context(env={}, stdout=out, stderr=err, which=lambda n: None)
        code = run_command(cmd, argparse.Namespace(json=True), ctx)
        self.assertEqual(code, 2)
        obj = one_json_line(self, out.getvalue(), "boom")
        self.assertFalse(obj["ok"])
        self.assertEqual(obj["error"]["type"], "ValueError")
        self.assertIn("Traceback", err.getvalue())

    def test_internal_error_without_json_still_exit_2(self):
        def boom(ctx, args):
            raise RuntimeError("deliberate")
        cmd = Command(name="boom", summary="raises", handler=boom)
        out, err = io.StringIO(), io.StringIO()
        ctx = Context(env={}, stdout=out, stderr=err, which=lambda n: None)
        code = run_command(cmd, argparse.Namespace(json=False), ctx)
        self.assertEqual(code, 2)
        self.assertIn("internal error", out.getvalue())
        self.assertIn("Traceback", err.getvalue())

    def test_usage_error_is_exit_2_with_empty_stdout(self):
        run = run_cli("no-such-verb", "--json")
        self.assertEqual(run.code, 2)
        self.assertEqual(run.stdout, "")
        self.assertIn("usage:", run.stderr)

    def test_result_payload_cannot_override_command_or_ok(self):
        """A handler payload carrying command/ok keys loses to the
        dispatcher's — the contract's two keys are the dispatcher's."""
        def sneaky(ctx, args):
            return Result(True, {"command": "other", "ok": False, "x": 1})
        cmd = Command(name="sneaky", summary="s", handler=sneaky)
        out = io.StringIO()
        ctx = Context(env={}, stdout=out, stderr=io.StringIO(), which=lambda n: None)
        code = run_command(cmd, argparse.Namespace(json=True), ctx)
        obj = one_json_line(self, out.getvalue(), "sneaky")
        self.assertEqual((code, obj["ok"], obj["command"]), (0, True, "sneaky"))


if __name__ == "__main__":
    unittest.main()

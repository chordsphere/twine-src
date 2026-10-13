"""`twine run` and the loop (Arc 2 R4; cli-contract.md §18, runtime-contract.md
§7). No model anywhere: the fake adapter plays a script throughout (T8), the
same script format a `--script` file carries (runtime-contract.md §3).

How it is driven:

  - **End to end** (`RunEndToEnd` and its neighbours): `bin/twine run` as a
    child process (`run_cli`), against `StubBale` — a double, never bale —
    replaying the recorded `open` line (bale 0.4.51, `opened`) with its
    `tarball` pointed at a request tarball the test builds (its `opener`
    kept: the line is edited, so it is named as not bale's) and the recorded
    dry run (`dry-run`, or `scope-drift-refused` with its exit 1). Real tools
    in a real sandbox under a temporary state directory; a price table
    double (invented prices) for the fake's model. The verb runs in a child
    because it makes itself its group's leader (setsid) — never the test
    runner's own process (R3's lesson).
  - **In-process** (`TheLoop` and below): `twine.runtime.loop.Loop` built
    from the fake (reached by name through the adapter registry), a real
    sandbox and transcript, a fake sleep and a scripted abort — for what a
    child cannot show cheaply: the backoff schedule, the requests the fake
    was given, the conversation's shape.
  - **The registration order** (`RegistrationOrder`): the verb in-process
    with `lead_own_group` stood in by a child process group (`RealGroup`) and
    a run seam that wraps the real one, which sees the running record on the
    sandbox's detection spawn.
"""

from __future__ import annotations

import ast
import copy
import io
import json
import os
import tarfile
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from twine import (CONSUMPTION_MANIFEST, REPO_ROOT, TRANSITIONS_TABLE, inflight, kill,
                   process, spend, transcript as transcripts)
from twine.bale import load_manifest
from twine.cli import Context, main
from twine.runtime import loop as runloop
from twine.runtime.adapters import anthropic
from twine.runtime.boundary import Boundary, SpawnSettings, Turn
from twine.runtime.sandbox import Sandbox
from twine.runtime.terms import ThinkingSettings, ToolCall
from twine.runtime.tooling import load_tool_registry
from twine.spend import Tokens
from twine.transitions import load_table

from tests.helpers import (RealGroup, StubBale, fenced_probe, filled_probe,
                           fixture_relpath, open_recording, run_cli)


def the_table():
    """The transition table as `twine run` loads it: with the consumption
    manifest, so the bale axes (apply-outcome among them) have their keys."""
    return load_table(TRANSITIONS_TABLE, load_manifest(CONSUMPTION_MANIFEST))


SID = "2026-10-08-sc-002"          # the recorded open line's session
SENTINEL_KEY = "sk-ant-twine-r4-sentinel-not-a-key-0000"
FAKE_MODEL = "fake"
# A price table double: invented prices for the fake's model id, not any
# provider's (twine ships no prices, §13.4).
PRICES_DOUBLE = """\
# A test double written by tests/test_run.py: invented prices.
[model."fake"]
input = 1
output = 2
cache_read = 0.1
cache_write = 1.25
"""
DRY_RUN = REPO_ROOT / fixture_relpath(["apply", "--dry-run", "--json", "/x.tar.gz"],
                                      "scratch", "dry-run")
DRIFT = REPO_ROOT / fixture_relpath(["apply", "--dry-run", "--json", "/x.tar.gz"],
                                    "scratch", "scope-drift-refused")
TWIN_KEYS = ("sid", "outcome", "stop", "move", "shape", "reason", "turns", "tool_calls",
             "retries", "block", "tarball", "apply_line", "dry_run", "usage", "cost_usd",
             "transcript", "sandbox", "inflight", "open")
RETRYABLE = ("rate-limited", "overloaded", "provider-error", "network-failure", "timeout")


def usage(input: int = 100, output: int = 20, thinking: int | None = None,
          cache_read: int = 0, cache_write: int = 0) -> dict:
    return {"input": input, "output": output, "thinking": thinking,
            "cache_read": cache_read, "cache_write": cache_write}


def tools(*calls: tuple[str, dict], n: int = 0, **use) -> dict:
    """A scripted turn that asks for tools."""
    return {"tool_calls": [{"id": f"t{n}-{i}", "name": name, "arguments": args}
                           for i, (name, args) in enumerate(calls)],
            "stop": None, "usage": usage(**use)}


def stop(key: str, text: str = "", **extra) -> dict:
    """A scripted turn that stops with `key`."""
    use = extra.pop("usage", usage())
    return {"text": text, "stop": key, "usage": use, **extra}


def light(sid: str = SID) -> str:
    return (f"=== LIGHT BEGIN {sid} ===\n"
            "[1] question:     which file?\n"
            "    while doing:  reading the brief\n"
            "    would assume: the first\n"
            "    why blocked:  two match\n"
            'Reply: answer inline, "as assumed", or "formal".\n'
            f"=== LIGHT END {sid} ===\n")


DELIVER_SHELL = ("mkdir -p out/response-002 && printf 'notes\\n' > out/response-002/notes.md "
                 "&& tar -czf response.tar.gz -C out response-002")


def request_tarball(path: Path, members: dict[str, bytes] | None = None, *,
                    top: str = "request-002") -> Path:
    """A request tarball as bale lays one out: one top directory."""
    members = members if members is not None else {
        "manifest.json": b'{"session_id": "2026-10-08-sc-002"}\n',
        "AGENT.md": b"# AGENT.md\n", "README.md": b"# Brief\n",
        "context/hello.txt": b"hello\n", "tools/craft_response.py": b"# crafter\n"}
    with tarfile.open(path, "w:gz") as tf:
        if top:
            info = tarfile.TarInfo(top)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            tf.addfile(info)
        for name, body in members.items():
            info = tarfile.TarInfo(f"{top}/{name}" if top else name)
            info.size = len(body)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(body))
    return path


class Bed:
    """One end-to-end bed: a temporary state directory with the price
    double, a repository, a bundle file the stub never reads, a request
    tarball, and a StubBale replaying the recorded `opened` line — edited so
    its `tarball` is this request (not bale's bytes, so named as a double) —
    and a recorded dry run."""

    def __init__(self, dry_run: Path = DRY_RUN, apply_exit: int = 0,
                 prices: bool = True, request: Path | None = None) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="twine-run-")
        self.base = Path(self._dir.name)
        self.state = self.base / "state"
        self.state.mkdir()
        if prices:
            (self.state / "prices.toml").write_text(PRICES_DOUBLE, encoding="utf-8")
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.bundle = self.base / "r4.bale-bundle"
        self.bundle.write_text("a bundle the stub never reads\n", encoding="utf-8")
        self.request = request or request_tarball(self.base / "request-r4.tar.gz")
        line = json.loads(open_recording("opened").path.read_bytes())
        line["tarball"] = str(self.request)
        self.opened = self.base / "opened-edited.json"
        self.opened.write_text(json.dumps(line) + "\n", encoding="utf-8")
        self.opener = line["opener"]
        self.stub = StubBale(open_stdout=self.opened, apply_stdout=dry_run,
                             exit_codes={"apply": apply_exit})
        self.script_path = self.base / "script.json"

    def run(self, script: list | None, *extra: str, json_mode: bool = True,
            env: dict[str, str] | None = None, cap: str = "5"):
        argv = ["run", str(self.bundle), "--cap", cap, "--adapter", "fake",
                "--state-dir", str(self.state), "--cwd", str(self.repo),
                "--bale-root", str(self.stub.root)]
        if script is not None:
            self.script_path.write_text(json.dumps(script), encoding="utf-8")
            argv += ["--script", str(self.script_path)]
        argv += list(extra)
        if json_mode:
            argv.append("--json")
        result = run_cli(*argv, extra_env={"ANTHROPIC_API_KEY": SENTINEL_KEY, **(env or {})})
        return result

    def twin(self, script, *extra: str, **kw) -> dict:
        result = self.run(script, *extra, **kw)
        lines = result.stdout.split("\n")
        assert len(lines) == 2 and lines[1] == "", result.stdout + result.stderr
        obj = json.loads(lines[0])
        assert result.code == (0 if obj["ok"] else 1), (result.code, result.stderr)
        assert "Traceback" not in result.stderr, result.stderr
        obj["_stderr"] = result.stderr
        return obj

    def transcript(self) -> list[dict]:
        return list(transcripts.read_lines(transcripts.transcript_path(self.state, SID)))

    def records(self) -> list[spend.UsageRecord]:
        return spend.read_stream(self.state / spend.STREAM_NAME).records

    def every_file(self) -> list[Path]:
        return [p for p in self.state.rglob("*") if p.is_file()]

    def cleanup(self) -> None:
        self.stub.cleanup()
        self._dir.cleanup()


class BedCase(unittest.TestCase):

    def bed(self, **kw) -> Bed:
        bed = Bed(**kw)
        self.addCleanup(bed.cleanup)
        return bed

    def assert_kept(self, bed: Bed, twin: dict) -> None:
        """Record and home kept; the running record gone."""
        self.assertEqual(twin["inflight"], "kept")
        record = inflight.read_inflight(bed.state, SID)
        self.assertIsNotNone(record)
        self.assertTrue(Path(twin["sandbox"]).is_dir())
        self.assertIsNone(kill.read_running(bed.state, SID))


# ---------------------------------------------------------------------------
# 1. End to end, through bin/twine
# ---------------------------------------------------------------------------


class RunEndToEnd(BedCase):

    def test_the_delivered_path(self):
        """Write a file, tar it with shell, deliver it: the dry run is clean,
        the apply line printed alone, the in-flight record removed, the home
        kept, the running record cleared."""
        bed = self.bed()
        script = [tools(("write_file", {"path": "draft.txt", "content": "draft\n"}), n=1),
                  tools(("shell", {"command": DELIVER_SHELL}), n=2),
                  tools(("deliver", {"tarball": "response.tar.gz"}), n=3)]
        twin = bed.twin(script)
        home = bed.state / "sandbox" / SID / "home"
        tarball = home / "response.tar.gz"
        self.assertEqual(twin["outcome"], "delivered")
        self.assertTrue(twin["ok"])
        self.assertEqual((twin["stop"], twin["move"], twin["actor"]),
                         (None, "operator-applies", "operator"))
        self.assertEqual(twin["tarball"], str(tarball.resolve()))
        self.assertEqual(twin["apply_line"], f"bale apply {tarball.resolve()}")
        self.assertEqual(twin["dry_run"]["outcome"], "dry-run")
        self.assertEqual((twin["turns"], twin["tool_calls"], twin["retries"]), (3, 3, 0))
        self.assertEqual(twin["inflight"], "removed")
        self.assertIsNone(inflight.read_inflight(bed.state, SID))
        self.assertTrue(tarball.is_file(), "the home is kept: the tarball lives there")
        self.assertEqual((home / "draft.txt").read_text(), "draft\n")
        self.assertIsNone(kill.read_running(bed.state, SID))
        self.assertEqual(twin["running"]["cleared"], True)
        # bale saw exactly the open and the dry run, nothing else (T12).
        calls = bed.stub.calls()
        self.assertEqual([c[0] for c in calls], ["open", "apply"])
        self.assertEqual(calls[0], ["open", str(bed.bundle), "--json"])
        self.assertEqual(calls[1], ["apply", "--dry-run", "--json", str(tarball.resolve())])
        # Human mode: the apply line alone on stdout.
        bed2 = self.bed()
        human = bed2.run(script, json_mode=False)
        self.assertEqual(human.code, 0, human.stderr)
        tarball2 = (bed2.state / "sandbox" / SID / "home" / "response.tar.gz").resolve()
        self.assertEqual(human.stdout, f"bale apply {tarball2}\n")
        self.assertIn("run: call 1:", human.stderr)

    def test_the_request_is_unpacked_at_request(self):
        bed = self.bed()
        twin = bed.twin([tools(("list_dir", {"path": "request"}), n=1),
                         stop("end-turn", "done")])
        request = bed.state / "sandbox" / SID / "home" / "request"
        self.assertEqual((request / "manifest.json").read_bytes(),
                         b'{"session_id": "2026-10-08-sc-002"}\n')
        self.assertEqual((request / "context" / "hello.txt").read_text(), "hello\n")
        self.assertEqual(twin["request"]["stripped"], "request-002")
        result = next(l for l in bed.transcript() if l["kind"] == "tool-result")["result"]
        self.assertEqual([e["name"] for e in result["entries"]],
                         ["AGENT.md", "README.md", "context", "manifest.json", "tools"])

    def test_ended_on_prose(self):
        bed = self.bed()
        twin = bed.twin([stop("end-turn", "I read it and I am done.")])
        self.assertEqual((twin["outcome"], twin["shape"], twin["stop"], twin["move"]),
                         ("ended", "prose", None, None))
        self.assertFalse(twin["ok"])
        self.assertIn("prose", twin["reason"])
        self.assert_kept(bed, twin)
        human = self.bed().run([stop("end-turn", "done")], json_mode=False)
        self.assertEqual(human.code, 1)
        self.assertRegex(human.stdout, rf"^run {SID}: ended, shape prose — .*\n$")

    def test_suspended_on_escalate(self):
        bed = self.bed()
        question = {"question": "which file?", "while_doing": "reading the brief",
                    "would_assume": "the first", "why_blocked": "two match"}
        script = [tools(("escalate", {"questions": [question]}),
                        ("shell", {"command": "touch never-run"}), n=1)]
        twin = bed.twin(script)
        self.assertEqual((twin["outcome"], twin["stop"], twin["shape"]),
                         ("suspended", None, None))
        self.assertIn(f"=== LIGHT BEGIN {SID} ===", twin["block"])
        self.assertEqual(twin["tool_calls"], 1, "nothing else runs that turn")
        self.assertFalse((bed.state / "sandbox" / SID / "home" / "never-run").exists())
        self.assert_kept(bed, twin)
        human = self.bed().run(script, json_mode=False)
        self.assertEqual(human.code, 1)
        self.assertTrue(human.stdout.startswith(f"=== LIGHT BEGIN {SID} ===\n"))
        self.assertTrue(human.stdout.endswith(f"=== LIGHT END {SID} ===\n"))

    def test_suspended_on_a_light_block_in_the_final_text(self):
        bed = self.bed()
        twin = bed.twin([stop("end-turn", "I need one answer.\n\n" + light())])
        self.assertEqual(twin["outcome"], "suspended")
        self.assertEqual(twin["block"], light())
        self.assert_kept(bed, twin)
        human = self.bed().run([stop("end-turn", light())], json_mode=False)
        self.assertEqual(human.stdout, light())

    def test_a_light_block_for_another_sid_is_not_carried(self):
        twin = self.bed().twin([stop("end-turn", light("2026-01-01-other-001"))])
        self.assertEqual((twin["outcome"], twin["shape"], twin["move"]),
                         ("ended", "light", "classify-final-text"))
        self.assertEqual(twin["stop"], "end-turn")

    def test_a_probe_block_in_the_final_text_is_run_and_its_output_fed_back(self):
        bed = self.bed()
        block = fenced_probe(filled_probe())
        twin = bed.twin([stop("end-turn", "I need a fact.\n\n" + block),
                         stop("end-turn", "Thanks; done.")])
        self.assertEqual((twin["outcome"], twin["turns"], twin["tool_calls"]),
                         ("ended", 2, 1))
        lines = bed.transcript()
        result = next(l for l in lines if l["kind"] == "tool-result")["result"]
        self.assertFalse(result["is_error"], result["content"])
        self.assertEqual(result["name"], "probe")
        second = [l for l in lines if l["kind"] == "request"][1]
        fed_back = second["appended"][-1]
        self.assertEqual(fed_back, {"role": "user", "content": result["content"]})
        self.assertIn("=== PROBE BEGIN twine-take-fixture ===", fed_back["content"])

    def test_max_turns(self):
        bed = self.bed()
        script = [tools(("list_dir", {}), n=i) for i in range(4)]
        twin = bed.twin(script, "--max-turns", "2")
        self.assertEqual((twin["outcome"], twin["shape"], twin["stop"], twin["turns"]),
                         ("ended", "max-turns", None, 2))
        self.assertIn("--max-turns", twin["reason"])
        self.assertEqual(len(bed.records()), 2)

    def test_the_dry_run_refused_is_stopped_with_its_move(self):
        bed = self.bed(dry_run=DRIFT, apply_exit=1)
        twin = bed.twin([tools(("shell", {"command": DELIVER_SHELL}), n=1),
                         tools(("deliver", {"tarball": "response.tar.gz"}), n=2)])
        self.assertEqual((twin["outcome"], twin["move"], twin["actor"], twin["apply_line"]),
                         ("stopped", "admit-or-return", "operator", None))
        self.assertEqual(twin["dry_run"]["outcome"], "scope-drift-refused")
        self.assertIn("scope-drift-refused", twin["reason"])
        self.assert_kept(bed, twin)

    def test_a_failed_tool_goes_back_as_its_result(self):
        """return-tool-error: deliver of a file that is not there is an
        error result, and the turn goes on."""
        bed = self.bed()
        twin = bed.twin([tools(("deliver", {"tarball": "missing.tar.gz"}),
                               ("no_such_tool", {}), n=1),
                         stop("end-turn", "giving up")])
        self.assertEqual((twin["outcome"], twin["tool_calls"]), ("ended", 2))
        results = [l["result"] for l in bed.transcript() if l["kind"] == "tool-result"]
        self.assertEqual([r["is_error"] for r in results], [True, True])
        moves = [l for l in bed.transcript() if l["kind"] == "move"
                 and l["move"] == "return-tool-error"]
        self.assertEqual(len(moves), 2)
        sent = [l for l in bed.transcript() if l["kind"] == "request"][1]["appended"][-1]
        self.assertEqual([b["is_error"] for b in sent["content"]], [True, True])


class TheStops(BedCase):

    def test_each_retryable_stop_is_retried_then_stopped_after_five(self):
        for key in RETRYABLE:
            with self.subTest(stop=key):
                bed = self.bed()
                script = [stop(key, retry_after=0, usage=usage(0, 0))] * 6
                twin = bed.twin(script)
                self.assertEqual((twin["outcome"], twin["stop"], twin["move"],
                                  twin["turns"], twin["retries"]),
                                 ("stopped", key, "retry-with-backoff", 6, 5))
                self.assertIn("5 retries", twin["reason"])
                retries = [l for l in bed.transcript() if l["kind"] == "retry"]
                self.assertEqual([r["attempt"] for r in retries], [1, 2, 3, 4, 5])
                self.assertEqual({r["wait_seconds"] for r in retries}, {0})
                self.assertEqual(len(bed.records()), 6, "one spend record per call")

    def test_a_retry_that_succeeds_goes_on(self):
        bed = self.bed()
        twin = bed.twin([stop("overloaded", retry_after=0), stop("end-turn", "done")])
        self.assertEqual((twin["outcome"], twin["turns"], twin["retries"]), ("ended", 2, 1))

    def test_max_tokens_is_continued_and_then_stopped(self):
        bed = self.bed()
        twin = bed.twin([stop("max-tokens", f"part {i}") for i in range(4)])
        self.assertEqual((twin["outcome"], twin["stop"], twin["move"], twin["turns"]),
                         ("stopped", "max-tokens", "continue-turn", 4))
        self.assertIn("3 continuations", twin["reason"])
        requests = [l for l in bed.transcript() if l["kind"] == "request"]
        cont = requests[1]["appended"]
        self.assertEqual(cont[0], {"role": "assistant",
                                   "content": [{"type": "text", "text": "part 0"}]})
        self.assertEqual(cont[1]["role"], "user")
        self.assertEqual(cont[1]["content"][-1],
                         {"type": "text", "text": runloop.CONTINUE_TEXT})

    def test_max_tokens_continued_then_finished(self):
        twin = self.bed().twin([stop("max-tokens", "half"), stop("end-turn", "whole")])
        self.assertEqual((twin["outcome"], twin["shape"], twin["turns"]),
                         ("ended", "prose", 2))

    def test_the_provider_s_refusals_stop_with_the_table_s_move(self):
        cases = {"request-refused": ("fix-request", "operator"),
                 "model-refusal": ("reword-brief", "planner"),
                 "window-exhausted": ("split-goal", "planner"),
                 "malformed-shape": ("respawn-from-request", "planner")}
        for key, (move, actor) in cases.items():
            with self.subTest(stop=key):
                bed = self.bed()
                twin = bed.twin([stop(key, reason=f"the provider said {key}")])
                self.assertEqual((twin["outcome"], twin["stop"], twin["move"],
                                  twin["actor"], twin["turns"]),
                                 ("stopped", key, move, actor, 1))
                self.assertIn(f"the provider said {key}", twin["reason"])
                self.assert_kept(bed, twin)

    def test_killed_when_the_abort_file_is_set_before_the_first_call(self):
        bed = self.bed()
        kill.request_abort(bed.state, SID)
        twin = bed.twin([stop("end-turn", "never played")])
        self.assertEqual((twin["outcome"], twin["stop"], twin["move"], twin["turns"]),
                         ("killed", "killed", "close-aborted", 0))
        self.assertEqual(bed.records(), [])
        self.assertEqual([c[0] for c in bed.stub.calls()], ["open"], "the loop never unlocks")
        self.assert_kept(bed, twin)
        self.assertIn("abort", [l["kind"] for l in bed.transcript()])

    def test_killed_when_the_abort_file_appears_between_calls(self):
        bed = self.bed()
        abort = kill.abort_path(bed.state, SID)
        command = f"mkdir -p {abort.parent} && echo '{{}}' > {abort}"
        twin = bed.twin([tools(("shell", {"command": command}), n=1),
                         stop("end-turn", "never played")])
        self.assertEqual((twin["outcome"], twin["turns"], twin["tool_calls"]),
                         ("killed", 1, 1))
        self.assertEqual(len(bed.records()), 1)

    def test_cap_reached_before_the_first_call(self):
        bed = self.bed()
        twin = bed.twin([stop("end-turn", "never played")], cap="0.000001")
        self.assertEqual((twin["outcome"], twin["stop"], twin["move"], twin["turns"]),
                         ("cap-reached", "cap-reached", "stop-at-cap", 0))
        self.assertEqual(twin["check"]["refusal"], "cap-reached")
        self.assertIn("cap-reached", twin["reason"])
        self.assertEqual(bed.records(), [])
        self.assert_kept(bed, twin)

    def test_cap_unchecked_without_prices(self):
        bed = self.bed(prices=False)
        twin = bed.twin([stop("end-turn", "never played")])
        self.assertEqual((twin["outcome"], twin["stop"], twin["move"], twin["turns"]),
                         ("cap-unchecked", "cap-unchecked", "fix-and-resume", 0))
        self.assertEqual(twin["check"]["refusal"], "no-prices")
        self.assertEqual(twin["cost_usd"], 0.0, "no call, nothing spent")

    def test_an_adapter_defect_is_stopped_with_no_move(self):
        """A provider's word scripted where twine's belongs: the boundary
        refuses the turn; the loop stops, naming the defect."""
        bed = self.bed()
        twin = bed.twin([stop("end_turn", "a provider's word")])
        self.assertEqual((twin["outcome"], twin["stop"], twin["move"], twin["turns"]),
                         ("stopped", None, None, 1))
        self.assertIn("boundary", twin["reason"])

    def test_a_script_that_runs_out_is_stopped(self):
        twin = self.bed().twin([tools(("list_dir", {}), n=1)])
        self.assertEqual((twin["outcome"], twin["turns"]), ("stopped", 2))
        self.assertIn("FakeScriptExhausted", twin["reason"])


class TheRecords(BedCase):

    def test_the_transcript_lines_and_their_order(self):
        bed = self.bed()
        bed.twin([tools(("list_dir", {}), n=1), stop("end-turn", "done")])
        lines = bed.transcript()
        self.assertEqual([l["kind"] for l in lines],
                         ["run-start", "check", "request", "turn", "tool-call", "tool-result",
                          "move", "check", "request", "turn", "move", "run-end"])
        self.assertEqual([l["seq"] for l in lines], list(range(1, len(lines) + 1)))
        for line in lines:
            self.assertEqual(list(line)[:3], ["at", "seq", "kind"])
        start = lines[0]
        self.assertEqual((start["adapter"], start["model"], start["open"]),
                         ("fake", FAKE_MODEL, {"sid": SID, "tarball": str(bed.request)}))
        self.assertEqual(start["system"]["note"], runloop.SURFACE_NOTE)
        first = lines[2]["appended"]
        self.assertEqual(first, [{"role": "user", "content": bed.opener}],
                         "the opener is the first turn, verbatim")
        end = lines[-1]["twin"]
        self.assertEqual((end["command"], end["outcome"]), ("run", "ended"))

    def test_a_second_run_appends_and_seq_continues(self):
        bed = self.bed()
        bed.twin([stop("end-turn", "first")])
        first = bed.transcript()
        bed.twin([stop("end-turn", "second")])
        lines = bed.transcript()
        self.assertEqual(lines[:len(first)], first, "never rewritten")
        self.assertEqual([l["seq"] for l in lines], list(range(1, len(lines) + 1)))
        self.assertEqual([l["kind"] for l in lines].count("run-start"), 2)

    def test_the_key_reaches_nothing(self):
        """A sentinel ANTHROPIC_API_KEY in twine's environment is in no file
        under the state directory after a run, and bale never sees it."""
        bed = self.bed()
        bed.twin([tools(("shell", {"command": "env > env.txt"}), n=1),
                  tools(("shell", {"command": DELIVER_SHELL}), n=2),
                  tools(("deliver", {"tarball": "response.tar.gz"}), n=3)])
        files = bed.every_file()
        self.assertTrue(any(p.name == "env.txt" for p in files))
        for path in files:
            with self.subTest(file=str(path.relative_to(bed.state))):
                self.assertNotIn(SENTINEL_KEY.encode(), path.read_bytes())
        environments = bed.stub.environments()
        self.assertIn("--- open", environments)
        self.assertIn("--- apply", environments)
        self.assertNotIn(SENTINEL_KEY, environments)
        self.assertNotIn("ANTHROPIC_API_KEY", environments)

    def test_the_spend_stream_gains_one_record_per_call(self):
        bed = self.bed()
        twin = bed.twin([tools(("list_dir", {}), n=1, input=100, output=10, cache_write=50),
                         stop("end-turn", "done", usage=usage(30, 5, 7, 40, 0))])
        records = bed.records()
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertEqual((record.sid, record.served_sid, record.model),
                             (SID, None, FAKE_MODEL))
        self.assertEqual(records[0].tokens, Tokens(100, 10, None, 0, 50))
        self.assertEqual(records[1].tokens, Tokens(30, 5, 7, 40, 0))
        self.assertEqual(twin["usage"], {"input": 130, "output": 15, "thinking": 7,
                                         "cache_read": 40, "cache_write": 50})
        # The double's prices: (130*1 + 15*2 + 7*2 + 40*0.1 + 50*1.25) / 1e6
        self.assertAlmostEqual(twin["cost_usd"], 240.5 / 1_000_000)

    def test_the_in_flight_record_s_runtime_fields(self):
        bed = self.bed()
        twin = bed.twin([stop("end-turn", "done")])
        record = inflight.read_inflight(bed.state, SID)
        runtime = record["runtime"]
        self.assertEqual(tuple(runtime), inflight.RUNTIME_KEYS)
        self.assertEqual((runtime["adapter"], runtime["model"], runtime["sandbox_home"],
                          runtime["transcript"]),
                         ("fake", FAKE_MODEL, twin["sandbox"], twin["transcript"]))
        self.assertEqual(runtime["pgid"], twin["running"]["pgid"])
        self.assertEqual(tuple(record)[:4], inflight.RECORD_KEYS)

    def test_status_lists_what_a_run_keeps(self):
        bed = self.bed()
        bed.twin([stop("end-turn", "done")])
        status = json.loads(run_cli("status", "--json", "--state-dir", str(bed.state)).stdout)
        self.assertEqual((status["transcript_sids"], status["sandbox_sids"],
                          status["inflight_sids"]), ([SID], [SID], [SID]))
        self.assertTrue(status["state_present"]["transcripts"])
        self.assertTrue(status["state_present"]["sandbox"])


class Refusals(BedCase):

    def assert_refused(self, twin: dict, needle: str) -> None:
        self.assertEqual((twin["outcome"], twin["ok"], twin["turns"]), ("refused", False, 0))
        self.assertIn(needle, twin["reason"])
        self.assertEqual(tuple(twin)[2:2 + len(TWIN_KEYS)], TWIN_KEYS)

    def test_anthropic_without_a_key_is_refused_before_bale_open(self):
        bed = self.bed()
        result = run_cli("run", str(bed.bundle), "--cap", "1", "--model", "m",
                         "--state-dir", str(bed.state), "--bale-root", str(bed.stub.root),
                         "--json")
        twin = json.loads(result.stdout)
        self.assertEqual(result.code, 1)
        self.assert_refused(twin, "ANTHROPIC_API_KEY is not set")
        self.assertIsNone(bed.stub.argv(), "bale open was never called")
        self.assertIsNone(twin["open"])

    def test_anthropic_without_a_model_and_with_a_script(self):
        bed = self.bed()
        bed.script_path.write_text("[]")
        result = run_cli("run", str(bed.bundle), "--cap", "1", "--script",
                         str(bed.script_path), "--state-dir", str(bed.state), "--json",
                         extra_env={"ANTHROPIC_API_KEY": SENTINEL_KEY})
        twin = json.loads(result.stdout)
        self.assert_refused(twin, "needs --model")
        self.assertIn("--script is the fake adapter's", twin["reason"])
        self.assertNotIn(SENTINEL_KEY, result.stdout + result.stderr)

    def test_fake_without_a_script_and_a_bad_script(self):
        bed = self.bed()
        self.assert_refused(bed.twin(None), "--adapter fake needs --script")
        self.assert_refused(bed.twin([{"stop": "end-turn"}]), "lacks 'usage'")
        bed.script_path.write_text("not json")
        result = bed.run(None, "--script", str(bed.script_path))
        self.assert_refused(json.loads(result.stdout), "is not a JSON script")
        self.assertIsNone(bed.stub.argv())

    def test_a_cap_that_is_not_dollars_and_an_absent_cap(self):
        bed = self.bed()
        self.assert_refused(bed.twin([stop("end-turn")], cap="lots"), "--cap")
        absent = run_cli("run", str(bed.bundle), "--adapter", "fake", "--json")
        self.assertEqual((absent.code, absent.stdout), (2, ""))
        self.assertIn("--cap", absent.stderr)

    def test_an_escaping_member_refuses_the_run(self):
        base = Path(tempfile.mkdtemp(prefix="twine-run-evil-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(base, ignore_errors=True))
        evil = request_tarball(base / "evil.tar.gz",
                               {"manifest.json": b"{}\n", "../../escaped.txt": b"out\n"})
        bed = self.bed(request=evil)
        twin = bed.twin([stop("end-turn", "never played")])
        self.assert_refused(twin, "the `data` filter refuses")
        self.assertIsNone(twin["transcript"])
        self.assertFalse(list(bed.base.rglob("escaped.txt")))
        self.assertFalse((bed.state / "sandbox" / SID / "home" / "request").exists())
        self.assertIsNone(kill.read_running(bed.state, SID), "the running record is cleared")
        self.assertIn(f"session {SID} is open in bale", twin["reason"])
        self.assertEqual(twin["inflight"], "kept")

    def test_bale_refusing_the_open_is_the_run_s_refusal(self):
        bed = self.bed()
        stub = StubBale(open_stdout=open_recording("open-refused").path, exit_code=1)
        self.addCleanup(stub.cleanup)
        bed.script_path.write_text(json.dumps([stop("end-turn")]))
        result = run_cli("run", str(bed.bundle), "--cap", "1", "--adapter", "fake",
                         "--script", str(bed.script_path), "--state-dir", str(bed.state),
                         "--bale-root", str(stub.root), "--json")
        twin = json.loads(result.stdout)
        self.assert_refused(twin, "bale refused the open")
        self.assertEqual(twin["open"]["outcome"], "open-refused")
        self.assertIsNone(twin["sid"])
        self.assertIsNone(twin["inflight"])


# ---------------------------------------------------------------------------
# 2. The registration order, in-process with a stand-in group
# ---------------------------------------------------------------------------


class RegistrationOrder(unittest.TestCase):

    def test_the_record_exists_before_the_sandbox_s_first_spawn_and_is_cleared(self):
        bed = Bed()
        self.addCleanup(bed.cleanup)
        group = RealGroup()
        self.addCleanup(group.cleanup)
        seen: list[tuple[list[str], object]] = []

        def seam(argv, **kw):
            if argv[0] == "unshare" and argv[-1] == "true":
                seen.append((list(argv), kill.read_running(bed.state, SID)))
            return process.run_process(argv, **kw)

        bed.script_path.write_text(json.dumps([stop("end-turn", "done")]))
        out, err = io.StringIO(), io.StringIO()
        ctx = Context(env={"PATH": os.environ.get("PATH", "")}, stdout=out, stderr=err,
                      which=lambda name: None, stdin=io.BytesIO(b""), run=seam)
        stand_in = process.OwnGroup(pid=group.pgid, pgid=group.pgid, setsid=False)
        with mock.patch("twine.commands.run.lead_own_group", return_value=stand_in):
            code = main(["run", str(bed.bundle), "--cap", "1", "--adapter", "fake",
                         "--script", str(bed.script_path), "--state-dir", str(bed.state),
                         "--cwd", str(bed.repo), "--bale-root", str(bed.stub.root),
                         "--json"], ctx=ctx)
        twin = json.loads(out.getvalue())
        self.assertEqual((code, twin["outcome"]), (1, "ended"), err.getvalue())
        self.assertEqual(len(seen), 1, "the detection spawn went through the seam")
        argv, record = seen[0]
        self.assertIsNotNone(record, "registered before the sandbox's first spawn")
        self.assertEqual((record.pgid, record.pid), (group.pgid, group.pgid))
        self.assertIsNone(kill.read_running(bed.state, SID), "cleared at the end")
        self.assertEqual(twin["running"], {"pid": group.pgid, "pgid": group.pgid,
                                           "setsid": False, "registered": True,
                                           "cleared": True, "note": None})


class LeadOwnGroup(unittest.TestCase):

    def test_a_child_that_is_not_its_group_s_leader_becomes_one(self):
        """Run in a child: never in the test runner's own process."""
        code = ("import json, os, sys; sys.path.insert(0, %r)\n"
                "from twine import process\n"
                "before = os.getpgrp()\n"
                "g = process.lead_own_group()\n"
                "again = process.lead_own_group()\n"
                "print(json.dumps([before, g.as_json(), again.as_json(), os.getpid()]))\n"
                % str(REPO_ROOT))
        import subprocess
        import sys
        proc = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True,
                              text=True, timeout=30)
        before, first, again, pid = json.loads(proc.stdout)
        self.assertNotEqual(before, pid)
        self.assertEqual(first, {"pid": pid, "pgid": pid, "setsid": True})
        self.assertEqual(again, {"pid": pid, "pgid": pid, "setsid": False})


# ---------------------------------------------------------------------------
# 3. The loop, in-process
# ---------------------------------------------------------------------------


class LoopBed:
    """A Loop over the fake (by name, through the adapter registry), a real
    sandbox (no running record: its spawns run unregistered, logged) and a
    real transcript in a temporary state directory, a fake sleep, a
    scripted abort and a recorded `deliver`."""

    def __init__(self, test: unittest.TestCase, script: list, *, thinking: bool = True,
                 max_turns: int = 200, cap: str = "5", abort_after: int | None = None,
                 prices: bool = True) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="twine-loop-")
        test.addCleanup(self._dir.cleanup)
        self.state = Path(self._dir.name) / "state"
        self.state.mkdir()
        if prices:
            (self.state / "prices.toml").write_text(PRICES_DOUBLE, encoding="utf-8")
        repo = Path(self._dir.name) / "repo"
        repo.mkdir()
        self.sandbox = Sandbox.create(self.state, SID, repo=repo)
        self.tools = load_tool_registry()
        self.prompt = runloop.system_prompt(self.tools)
        settings = ThinkingSettings(enabled=True, adaptive=True) if thinking else \
            ThinkingSettings(enabled=False)
        fake = runloop.adapter_class("fake")
        self.adapter = fake(SpawnSettings(FAKE_MODEL, 16000, settings), script)
        self.slept: list[float] = []
        self.delivered: list[Path] = []
        self.abort_checks = 0
        self.abort_after = abort_after
        self.transcript = transcripts.Transcript.open(self.state, SID)
        self.loop = runloop.Loop(
            boundary=Boundary(self.adapter), sandbox=self.sandbox,
            transcript=self.transcript,
            settings=runloop.LoopSettings(sid=SID, state_dir=self.state,
                                          cap_usd=Decimal(cap), model=FAKE_MODEL,
                                          max_tokens=16000, max_turns=max_turns),
            prompt=self.prompt, moves=runloop.MoveBook(the_table()), tools=self.tools,
            deliver=self.deliver, messages=[runloop.user_message("the opener")],
            sleep=self.slept.append, abort=self.abort)

    def abort(self, state_dir, sid) -> bool:
        self.abort_checks += 1
        return self.abort_after is not None and self.abort_checks > self.abort_after

    def deliver(self, path: Path) -> runloop.Delivery:
        self.delivered.append(path)
        return runloop.Delivery(ok=True, tarball=str(path), apply_line=f"bale apply {path}",
                                dry_run={"outcome": "dry-run"}, outcome="dry-run",
                                reason=None, twin={"double": True})

    def run(self) -> runloop.LoopResult:
        return self.loop.run()


class TheLoop(unittest.TestCase):

    def test_the_backoff_schedule_without_retry_after(self):
        bed = LoopBed(self, [stop("rate-limited", usage=usage(0, 0))] * 6)
        result = bed.run()
        self.assertEqual((result.outcome, result.retries, result.turns), ("stopped", 5, 6))
        # 2, 4, 8, 16, 32 seconds, slept a second at a time between abort checks.
        self.assertEqual(sum(bed.slept), 2 + 4 + 8 + 16 + 32)
        self.assertTrue(all(s <= 1.0 for s in bed.slept))

    def test_retry_after_is_honoured(self):
        bed = LoopBed(self, [stop("overloaded", retry_after=3.5), stop("end-turn", "ok")])
        result = bed.run()
        self.assertEqual((result.outcome, result.retries), ("ended", 1))
        self.assertEqual(sum(bed.slept), 3.5)

    def test_the_abort_interrupts_a_backoff(self):
        # Abort checks: before call 1 (no), then each second of the 2 s wait.
        bed = LoopBed(self, [stop("timeout")] * 3, abort_after=2)
        result = bed.run()
        self.assertEqual((result.outcome, result.stop, result.turns), ("killed", "killed", 1))
        self.assertIn("while waiting", result.reason)

    def test_the_requests_the_fake_was_given(self):
        """The opener first; the tools offered every call are the
        registry's seven; the conversation only grows (D12)."""
        bed = LoopBed(self, [tools(("list_dir", {}), n=1), stop("end-turn", "done")])
        bed.run()
        first, second = bed.adapter.requests
        self.assertEqual(first.messages, ({"role": "user", "content": "the opener"},))
        self.assertEqual(first.tools, bed.tools.specs())
        self.assertEqual([t.name for t in first.tools],
                         ["shell", "read_file", "write_file", "list_dir", "probe",
                          "escalate", "deliver"])
        self.assertEqual(second.messages[:1], first.messages)
        self.assertEqual([m["role"] for m in second.messages], ["user", "assistant", "user"])
        self.assertEqual(second.messages[1]["content"][0]["type"], "tool_use")
        self.assertEqual(second.messages[2]["content"][0]["type"], "tool_result")

    def test_deliver_hands_the_resolved_path_and_skips_the_rest(self):
        bed = LoopBed(self, [tools(("write_file", {"path": "r.tar.gz", "content": "x"}),
                                   ("deliver", {"tarball": "r.tar.gz"}),
                                   ("write_file", {"path": "late", "content": "x"}), n=1)])
        result = bed.run()
        self.assertEqual(result.outcome, "delivered")
        self.assertEqual(bed.delivered, [(bed.sandbox.home / "r.tar.gz").resolve()])
        self.assertFalse((bed.sandbox.home / "late").exists())
        last = bed.loop.messages[-1]["content"]
        self.assertEqual([b.get("is_error", False) for b in last], [False, False, True])
        self.assertIn("not run", last[2]["content"])

    def test_max_turns_stops_before_the_next_call(self):
        bed = LoopBed(self, [tools(("list_dir", {}), n=i) for i in range(5)], max_turns=3)
        result = bed.run()
        self.assertEqual((result.outcome, result.shape, result.turns), ("ended", "max-turns", 3))
        self.assertEqual(bed.adapter.remaining, 2)

    def test_a_thinking_turn_on_a_thinking_off_session_is_a_defect(self):
        bed = LoopBed(self, [stop("end-turn", "x", thinking="hm")], thinking=False)
        result = bed.run()
        self.assertEqual((result.outcome, result.stop), ("stopped", None))
        self.assertIn("thinking", result.reason)


class TheSystemPrompt(unittest.TestCase):

    def test_it_holds_the_tools_and_the_note_and_nothing_about_the_model(self):
        prompt = runloop.system_prompt(load_tool_registry())
        self.assertEqual(set(prompt.as_json()), {"note", "tools"})
        self.assertEqual([t["name"] for t in prompt.tool_json()],
                         ["shell", "read_file", "write_file", "list_dir", "probe",
                          "escalate", "deliver"])
        note = prompt.note
        for needle in ("request/", "manifest.json", "AGENT.md", "README.md", "context/",
                       "read_file", "list_dir", "deliver", "craft_response.py",
                       "escalate", "probe"):
            with self.subTest(must_say=needle):
                self.assertIn(needle, note)
        lowered = note.lower()
        for needle in ("anthropic", "claude", "openai", "gpt", "haiku", "sonnet", "opus",
                       "fable", "fake", "model", "provider", SID, "twine-051"):
            with self.subTest(must_not_say=needle):
                self.assertNotIn(needle.lower(), lowered)

    def test_it_is_a_constant(self):
        a = runloop.system_prompt(load_tool_registry())
        b = runloop.system_prompt(load_tool_registry())
        self.assertEqual(a, b)


class TheEstimate(unittest.TestCase):

    def test_it_counts_bytes_halved_and_grows_with_the_conversation(self):
        prompt = runloop.system_prompt(load_tool_registry())
        small = runloop.estimate_input_tokens(prompt, [runloop.user_message("hi")])
        big = runloop.estimate_input_tokens(prompt, [runloop.user_message("hi" * 5000)])
        self.assertGreaterEqual(big - small, (10000 - 2) // 2)
        body = json.dumps({"system": prompt.note, "tools": prompt.tool_json(),
                           "messages": [runloop.user_message("hi")]}, ensure_ascii=False)
        self.assertEqual(small, -(-len(body.encode()) // 2))


class TheConversationShape(unittest.TestCase):
    """The loop's messages are the shape the Anthropic adapter's helpers
    build — held to them, so the two cannot drift."""

    def test_the_helpers_agree_with_the_adapter_s(self):
        results = [("a", "fine", False), ("b", "broke", True)]
        self.assertEqual(runloop.tool_result_message(results),
                         anthropic.tool_result_message(results))
        self.assertEqual(runloop.user_message("hi"), anthropic.user_message("hi"))
        content = ({"type": "thinking", "thinking": "t", "signature": "s"},
                   {"type": "text", "text": "x"},
                   {"type": "tool_use", "id": "a", "name": "shell",
                    "input": {"command": "ls"}, "caller": {"type": "direct"}})
        turn = Turn(text="x", thinking="t", tool_calls=(ToolCall("a", "shell",
                                                                  {"command": "ls"}),),
                    stop=None, usage=Tokens(1, 1, None, 0, 0), content=content)
        self.assertEqual(runloop.assistant_message(runloop.assistant_blocks(turn)),
                         anthropic.assistant_message(turn))

    def test_without_content_the_blocks_are_built_from_text_and_calls(self):
        turn = Turn(text="", thinking=None, tool_calls=(ToolCall("a", "ls", {}),), stop=None,
                    usage=Tokens(1, 1, None, 0, 0))
        self.assertEqual(runloop.assistant_blocks(turn),
                         [{"type": "tool_use", "id": "a", "name": "ls", "input": {}}])

    def test_a_cut_off_tool_use_is_answered_before_the_continue(self):
        blocks = [{"type": "text", "text": "half"},
                  {"type": "tool_use", "id": "x", "name": "shell", "input": {}}]
        message = runloop.continue_message(blocks)
        self.assertEqual(message["content"][0]["tool_use_id"], "x")
        self.assertTrue(message["content"][0]["is_error"])
        self.assertEqual(message["content"][-1]["text"], runloop.CONTINUE_TEXT)

    def test_clip_marks_the_cut_on_a_character_boundary(self):
        self.assertEqual(runloop.clip("short"), "short")
        cut = runloop.clip("é" * 40000)
        self.assertTrue(cut.endswith("[twine: cut at 65536 bytes of 80000]"))
        self.assertLessEqual(len(cut.split("\n[twine")[0].encode()), 65536)


class TheRequestOnDisk(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="twine-unpack-")
        self.addCleanup(self._dir.cleanup)
        self.base = Path(self._dir.name)
        self.home = self.base / "home"
        self.home.mkdir()

    def test_the_top_directory_is_stripped(self):
        tarball = request_tarball(self.base / "r.tar.gz")
        unpacked = runloop.unpack_request(tarball, self.home)
        self.assertEqual(unpacked.stripped, "request-002")
        self.assertTrue((self.home / "request" / "manifest.json").is_file())
        self.assertTrue((self.home / "request" / "tools" / "craft_response.py").is_file())

    def test_a_dot_slash_prefix_and_no_top_directory(self):
        path = self.base / "dot.tar.gz"
        with tarfile.open(path, "w:gz") as tf:
            for name in ("./request-009/manifest.json", "./request-009/AGENT.md"):
                info = tarfile.TarInfo(name)
                info.size = 2
                tf.addfile(info, io.BytesIO(b"{}"))
        self.assertEqual(runloop.unpack_request(path, self.home).stripped, "request-009")
        self.assertTrue((self.home / "request" / "AGENT.md").is_file())
        flat = request_tarball(self.base / "flat.tar.gz", {"a.txt": b"a", "b.txt": b"b"},
                               top="")
        home2 = self.base / "home2"
        home2.mkdir()
        self.assertIsNone(runloop.unpack_request(flat, home2).stripped)
        self.assertTrue((home2 / "request" / "a.txt").is_file())

    def test_escaping_members_refuse_everything(self):
        cases = {"dotdot": ("../out.txt", tarfile.REGTYPE, ""),
                 "symlink-out": ("link", tarfile.SYMTYPE, "/etc/passwd"),
                 "symlink-up": ("link", tarfile.SYMTYPE, "../../outside"),
                 "hardlink-out": ("link", tarfile.LNKTYPE, "../../etc/passwd")}
        for name, (member, kind, target) in cases.items():
            with self.subTest(case=name):
                path = self.base / f"{name}.tar.gz"
                with tarfile.open(path, "w:gz") as tf:
                    good = tarfile.TarInfo("ok.txt")
                    good.size = 2
                    tf.addfile(good, io.BytesIO(b"ok"))
                    bad = tarfile.TarInfo(member)
                    bad.type = kind
                    bad.linkname = target
                    bad.size = 0 if kind != tarfile.REGTYPE else 3
                    tf.addfile(bad, io.BytesIO(b"bad") if kind == tarfile.REGTYPE else None)
                home = self.base / f"home-{name}"
                home.mkdir()
                with self.assertRaisesRegex(runloop.LoopError, "refuses"):
                    runloop.unpack_request(path, home)
                self.assertFalse((home / "request" / "ok.txt").exists(),
                                 "nothing is extracted when one member refuses")

    def test_an_absolute_name_is_kept_inside(self):
        """The `data` filter strips a leading `/`: the member lands under
        request/, never at its absolute path."""
        path = self.base / "abs.tar.gz"
        name = f"/tmp/twine-r4-absolute-{os.getpid()}.txt"
        with tarfile.open(path, "w:gz") as tf:
            info = tarfile.TarInfo(name)
            info.size = 2
            tf.addfile(info, io.BytesIO(b"ok"))
        runloop.unpack_request(path, self.home)
        self.assertFalse(Path(name).exists())
        self.assertTrue((self.home / "request" / name.lstrip("/")).is_file())

    def test_not_a_tarball(self):
        junk = self.base / "junk.tar.gz"
        junk.write_bytes(b"not a tarball")
        with self.assertRaisesRegex(runloop.LoopError, "cannot be opened"):
            runloop.unpack_request(junk, self.home)


class TheMoveBook(unittest.TestCase):

    def test_the_moves_come_from_the_table(self):
        book = runloop.MoveBook(the_table())
        self.assertEqual(book.faults(), [])
        self.assertEqual(book.stop_move("end-turn").name, "classify-final-text")
        self.assertEqual(book.stop_move("rate-limited").name, "retry-with-backoff")
        self.assertEqual(book.apply_move("dry-run").name, "operator-applies")
        self.assertIsNone(book.apply_move("twine-test-not-a-bale-outcome"))
        self.assertIsNone(book.stop_move(None))

    def test_a_table_without_a_move_the_loop_performs_is_a_fault(self):
        table = the_table()
        trimmed = copy.copy(table)
        trimmed.moves = {k: v for k, v in table.moves.items() if k != "continue-turn"}
        faults = runloop.MoveBook(trimmed).faults()
        self.assertTrue(any("'continue-turn'" in f for f in faults), faults)

    def test_the_loop_spells_no_stop_key_and_imports_no_process_module(self):
        """The one spelling is the table's; nothing under twine/runtime/ or
        the verb imports subprocess or os (processes go through the seam,
        the group through twine.process)."""
        keys = set(load_table().axis("stop").keys)
        for rel in ("twine/runtime/loop.py", "twine/commands/run.py"):
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
            roots = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    roots.add(node.module.split(".")[0])
            with self.subTest(file=rel):
                self.assertEqual(roots & {"subprocess", "os", "socket", "multiprocessing",
                                          "pty"}, set())
                if rel.startswith("twine/runtime/"):
                    spelled = {n.value for n in ast.walk(tree)
                               if isinstance(n, ast.Constant) and n.value in keys}
                    self.assertEqual(spelled, set())


class UsageAndCost(unittest.TestCase):

    def record(self, **tokens) -> spend.UsageRecord:
        return spend.parse_record({"sid": SID, "served_sid": None, "model": FAKE_MODEL,
                                   "tokens": usage(**tokens)})

    def test_usage_sum(self):
        self.assertEqual(runloop.usage_sum([]), usage(0, 0, 0, 0, 0))
        self.assertEqual(runloop.usage_sum([self.record(input=1, output=2)] * 2),
                         usage(2, 4, None, 0, 0))
        self.assertEqual(runloop.usage_sum([self.record(input=1, output=2, thinking=3),
                                            self.record(input=1, output=2)]),
                         usage(2, 4, 3, 0, 0))

    def test_run_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            prices = Path(tmp) / "prices.toml"
            self.assertIsNone(runloop.run_cost([self.record()], prices))
            self.assertEqual(runloop.run_cost([], prices), Decimal(0))
            prices.write_text(PRICES_DOUBLE, encoding="utf-8")
            self.assertEqual(runloop.run_cost([self.record(input=1_000_000, output=0)], prices),
                             Decimal(1))


class TheTranscriptModule(unittest.TestCase):

    def test_seq_continues_and_a_torn_line_is_ended(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            t = transcripts.Transcript.open(state, SID, clock=lambda: "T")
            t.append("one", x=1)
            t.append("two")
            with t.path.open("ab") as fh:
                fh.write(b'{"seq": 99, "kind": "torn')
            again = transcripts.Transcript.open(state, SID, clock=lambda: "T")
            self.assertEqual((again.next_seq, again.torn_before), (3, True))
            again.append("three")
            lines = list(transcripts.read_lines(t.path))
            self.assertEqual([l["seq"] for l in lines], [1, 2, 3])
            self.assertTrue(lines[-1]["torn_before"])
            self.assertEqual(oct(t.path.stat().st_mode & 0o777), "0o600")
            with self.assertRaises(ValueError):
                t.append("bad", seq=5)

    def test_list_transcripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(transcripts.list_transcripts(Path(tmp)), ((), ()))
            transcripts.Transcript.open(Path(tmp), SID).append("x")
            (Path(tmp) / "transcripts" / "junk").write_text("")
            sids, faults = transcripts.list_transcripts(Path(tmp))
            self.assertEqual(sids, (SID,))
            self.assertEqual(len(faults), 1)


class TheInflightRuntimeFields(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="twine-inflight-r4-")
        self.addCleanup(self._dir.cleanup)
        self.state = Path(self._dir.name)

    def open(self, outcome="opened"):
        return inflight.record_open(self.state, SID, outcome=outcome, cwd="/repo",
                                    tarball="/repo/req.tar.gz", desk=None,
                                    bundle_sha256="b" * 64, opener="opener\n")

    def fields(self, **over):
        base = inflight.runtime_fields(adapter="fake", model="fake", sandbox_home="/s/home",
                                       transcript="/s/t.jsonl", pgid=4242,
                                       clock=lambda: "2026-10-13T00:00:00Z")
        base.update(over)
        return base

    def test_written_read_kept_on_a_second_desk_and_dropped_on_an_open(self):
        self.open()
        written = inflight.record_runtime(self.state, SID, self.fields())
        self.assertEqual(tuple(written), (*inflight.RECORD_KEYS, "runtime"))
        self.assertEqual(inflight.read_inflight(self.state, SID)["runtime"], self.fields())
        self.open("second-desk")
        record = inflight.read_inflight(self.state, SID)
        self.assertEqual((len(record["opens"]), record["runtime"]), (2, self.fields()))
        self.open("opened")
        self.assertNotIn("runtime", inflight.read_inflight(self.state, SID))
        self.assertEqual(inflight.list_inflight(self.state).sids, (SID,))

    def test_refused_without_a_record_and_for_bad_fields(self):
        with self.assertRaises(inflight.InflightError):
            inflight.record_runtime(self.state, SID, self.fields())
        self.open()
        for bad in (self.fields(pgid=1), self.fields(transcript="relative"),
                    {k: v for k, v in self.fields().items() if k != "model"}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    inflight.record_runtime(self.state, SID, bad)

    def test_a_malformed_runtime_is_a_named_fault(self):
        path = self.open().path
        obj = json.loads(path.read_text())
        obj["runtime"] = {"adapter": "fake"}
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(inflight.InflightRecordError, "runtime lacks"):
            inflight.read_inflight(self.state, SID)

    def test_remove_inflight(self):
        self.assertFalse(inflight.remove_inflight(self.state, SID))
        self.open()
        self.assertTrue(inflight.remove_inflight(self.state, SID))
        self.assertIsNone(inflight.read_inflight(self.state, SID))
        self.assertFalse(inflight.remove_inflight(self.state, SID))


class TheAnthropicSpawn(unittest.TestCase):
    """The verb's anthropic path up to the first call, constructed only — no
    transport is called (T8): the surface note is the adapter's system text,
    the model, max_tokens and thinking are spawn-time constants, and the key
    sits in the adapter alone."""

    def build(self, thinking: str):
        import argparse
        from twine.commands import run as run_verb
        args = argparse.Namespace(adapter="anthropic", max_tokens=1234, thinking=thinking)
        report = run_verb.RunReport(bundle="b", adapter="anthropic", model="claude-x")
        prompt = runloop.system_prompt(load_tool_registry())
        cls = runloop.adapter_class("anthropic")
        return run_verb.build_adapter(args, report, cls, None, SENTINEL_KEY, prompt), prompt

    def test_the_spawn_time_constants(self):
        adapter, prompt = self.build("adaptive")
        self.assertEqual(adapter.system, prompt.note)
        self.assertEqual((adapter.settings.model, adapter.settings.max_tokens),
                         ("claude-x", 1234))
        self.assertEqual(adapter.thinking_param, {"type": "adaptive"})
        self.assertTrue(adapter.settings.thinking.adaptive)
        off, _ = self.build("off")
        self.assertEqual(off.thinking_param, {"type": "disabled"})
        self.assertFalse(off.settings.thinking.enabled)
        self.assertNotIn(SENTINEL_KEY, repr(adapter))
        Boundary(adapter)   # the boundary hosts it


class TheFakeScriptsNewKeys(unittest.TestCase):

    def test_retry_after_and_reason_are_carried_and_checked(self):
        from twine.runtime.adapters.fake import FakeScript, FakeScriptError
        played = FakeScript.from_data([stop("rate-limited", retry_after=1.5,
                                            reason="slow down")]).turns[0]
        self.assertEqual((played.retry_after, played.reason), (1.5, "slow down"))
        for bad in ({"retry_after": "soon"}, {"retry_after": True}, {"reason": 3}):
            with self.subTest(bad=bad):
                with self.assertRaises(FakeScriptError):
                    FakeScript.from_data([stop("end-turn", **bad)])


if __name__ == "__main__":
    unittest.main()

"""`twine resume` and escalate's clarification form (Arc 2 R5; D23;
cli-contract.md §19, runtime-contract.md §6.6, §7.9). No model anywhere: the
fake adapter plays a script (T8).

How it is driven:

  - **End to end** (`SuspendThenResume`, `TheClarificationForm`,
    `ResumeRefusals`): `bin/twine run` and then `bin/twine resume` as child
    processes against StubBale (tests/test_run.py's Bed) — a double, never
    bale — replaying the recorded `opened` line for the run (its `tarball`
    edited to the request the test builds, so named as not bale's) and none
    for the resume, and the recorded clean dry run for every `apply
    --dry-run`. The clarification response's dry run: bale 0.4.52 prints
    outcome `dry-run` with `verdict` and `merge` null for one (the brief's
    fact, bin/bale_apply.py's clarification fork); no recording of that line
    exists, so the recorded `dry-run` line of a normal response stands in —
    its `verdict` and `merge` are already null — named here as not a
    recording of the clarification fork, until one is recorded (the
    architect's, by probe).
  - **The rebuild** (`TheRebuild`): twine.runtime.resume.read_conversation on
    transcripts the tests write.
  - **The registration order** (`ResumeRegistration`): the verb in-process,
    `lead_own_group` stood in by a child group, as tests/test_run.py does.
  - **The pinned tools** (`ThePinnedBaleTools`): tests/bale_tools/, bale's
    own request-carried crafter and lint, held to their sha256.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from twine import inflight, kill, process, transcript as transcripts
from twine.cli import Context, main
from twine.runtime.resume import ResumeError, read_conversation

from tests.helpers import (BALE_TOOLS, BALE_TOOLS_SHA256, RealGroup, StubBale,
                           request_tool_members, run_cli)
from tests.test_run import (DELIVER_SHELL, DRY_RUN, SENTINEL_KEY, SID, TWIN_KEYS, Bed,
                            light, request_tarball, stop, tools, usage)

R5_TWIN_KEYS = TWIN_KEYS + ("window", "resumed_from", "rewarm")
# A double of the worker-facing block `bale relay` prints for an answered
# clarification — not bale's bytes: resume carries the answer as opaque text.
ANSWER_BLOCK = ("BALE EXCHANGE BEGIN 2026-10-08-sc-002\n"
                "# a double written by tests/test_resume.py — not bale's relay block\n"
                '{"from": "planner", "round": 2, "answers": [{"question_round": 1, '
                '"answer": "as-recommended"}]}\n'
                "BALE EXCHANGE END\n")
QUESTION = {"question": "which file?", "while_doing": "reading the brief",
            "would_assume": "the first", "why_blocked": "two match"}


class ResumeBed(Bed):
    """tests/test_run.py's Bed, plus `resume`: `bin/twine resume SID` against
    the same state directory and stub, the answer from a file (or stdin)."""

    def __init__(self, **kw) -> None:
        if kw.pop("with_tools", False):
            base = Path(tempfile.mkdtemp(prefix="twine-resume-request-"))
            self._request_dir = base
            members = {"manifest.json": json.dumps({"session_id": SID,
                                                     "goal": "R5's test goal"}).encode(),
                       "AGENT.md": b"# AGENT.md\n", "README.md": b"# Brief\n",
                       **request_tool_members()}
            kw["request"] = request_tarball(base / "request-r5.tar.gz", members)
        super().__init__(**kw)
        self.answer_path = self.base / "answer.txt"
        self.resume_script = self.base / "resume-script.json"

    def resume(self, script, *extra: str, answer: str | None = "as assumed\n",
               json_mode: bool = True, stdin: bytes | None = None,
               env: dict[str, str] | None = None, cap: str | None = "5"):
        argv = ["resume", SID, "--state-dir", str(self.state), "--bale-root",
                str(self.stub.root)]
        if cap is not None:
            argv += ["--cap", cap]
        if answer is not None:
            self.answer_path.write_text(answer, encoding="utf-8")
            argv += ["--answer", str(self.answer_path)]
        if script is not None:
            self.resume_script.write_text(json.dumps(script), encoding="utf-8")
            argv += ["--script", str(self.resume_script)]
        argv += list(extra)
        if json_mode:
            argv.append("--json")
        return run_cli(*argv, stdin=stdin,
                       extra_env={"ANTHROPIC_API_KEY": SENTINEL_KEY, **(env or {})})

    def resume_twin(self, script, *extra: str, **kw) -> dict:
        result = self.resume(script, *extra, **kw)
        lines = result.stdout.split("\n")
        assert len(lines) == 2 and lines[1] == "", result.stdout + result.stderr
        obj = json.loads(lines[0])
        assert result.code == (0 if obj["ok"] else 1), (result.code, result.stderr)
        assert "Traceback" not in result.stderr, result.stderr
        obj["_stderr"] = result.stderr
        return obj

    def cleanup(self) -> None:
        super().cleanup()
        request_dir = getattr(self, "_request_dir", None)
        if request_dir is not None:
            import shutil
            shutil.rmtree(request_dir, ignore_errors=True)


class ResumeCase(unittest.TestCase):

    def bed(self, **kw) -> ResumeBed:
        bed = ResumeBed(**kw)
        self.addCleanup(bed.cleanup)
        return bed

    @staticmethod
    def of(lines, kind):
        return [l for l in lines if l["kind"] == kind]

    def suspended(self, bed: ResumeBed, *extra: str) -> dict:
        twin = bed.twin([tools(("list_dir", {}), n=1),
                         tools(("escalate", {"questions": [QUESTION]}),
                               ("shell", {"command": "touch never-run"}), n=2)], *extra)
        self.assertEqual(twin["outcome"], "suspended", twin["reason"])
        return twin


# ---------------------------------------------------------------------------
# 1. Suspend, then resume
# ---------------------------------------------------------------------------


class SuspendThenResume(ResumeCase):

    DELIVER = [tools(("shell", {"command": DELIVER_SHELL}), n=10, input=4000,
                     cache_read=0, cache_write=0),
               tools(("deliver", {"tarball": "response.tar.gz"}), n=11)]

    def test_suspended_on_escalate_then_resumed_to_delivered(self):
        bed = self.bed()
        self.suspended(bed)
        before = bed.transcript()
        last_total = self.of(before, "request")[-1]["messages_total"]
        twin = bed.resume_twin(self.DELIVER, answer="[1] the second one\n")
        self.assertEqual((twin["command"], twin["outcome"], twin["ok"]),
                         ("resume", "delivered", True), twin["reason"])
        self.assertEqual(tuple(twin)[2:2 + len(R5_TWIN_KEYS)], R5_TWIN_KEYS)
        self.assertIsNone(twin["open"])
        self.assertEqual(twin["resumed_from"], before[-1]["seq"])
        self.assertEqual(twin["rewarm"], usage(4000, 20, None, 0, 0),
                         "D23's re-warm cost: the first call's tokens")
        self.assertEqual((twin["turns"], twin["tool_calls"]), (2, 2))
        self.assertEqual(twin["inflight"], "removed")
        self.assertIsNone(inflight.read_inflight(bed.state, SID))
        # bale: the run's open and nothing else; the resume's dry run alone.
        self.assertEqual([c[0] for c in bed.stub.calls()], ["open", "apply"])
        lines = bed.transcript()
        self.assertEqual(lines[:len(before)], before, "the transcript is appended to")
        self.assertEqual([l["seq"] for l in lines], list(range(1, len(lines) + 1)))
        start = lines[len(before)]
        self.assertEqual((start["kind"], start["resumed_from"], start["open"]),
                         ("run-start", before[-1]["seq"], None))
        self.assertEqual((start["adapter"], start["model"], start["max_tokens"],
                          start["thinking"]), ("fake", "fake", 16000, "adaptive"))
        first = self.of(lines[len(before):], "request")[0]
        self.assertEqual(first["messages_total"], last_total + 1)
        self.assertEqual(first["appended"], [{"role": "user",
                                              "content": "[1] the second one\n"}])
        self.assertEqual(lines[-1]["twin"]["command"], "resume")

    def test_the_rebuilt_conversation_is_the_one_sent_plus_the_answer(self):
        """Joined across both runs, the request lines are the conversation:
        the opener, the turns, the escalate result and the not-run result —
        then the answer — and the resumed run sent all of it."""
        bed = self.bed()
        self.suspended(bed)
        bed.resume_twin(self.DELIVER)
        conversation = read_conversation(transcripts.transcript_path(bed.state, SID))
        messages = conversation.messages
        self.assertEqual(messages[0], {"role": "user", "content": bed.opener})
        roles = [m["role"] for m in messages]
        self.assertEqual(roles[:6], ["user", "assistant", "user", "assistant", "user", "user"])
        results = messages[4]["content"]
        self.assertIn("=== LIGHT BEGIN", results[0]["content"])
        self.assertIn("not run", results[1]["content"])
        self.assertEqual(messages[5], {"role": "user", "content": "as assumed\n"})
        self.assertEqual(conversation.runs, 2)

    def test_the_final_text_s_light_block_is_in_what_is_resumed(self):
        """A light block in the final text: the assistant's turn was never
        sent, so its `sent: false` line carries it, and the resumed
        conversation holds it before the answer."""
        bed = self.bed()
        twin = bed.twin([stop("end-turn", "One question.\n\n" + light())])
        self.assertEqual(twin["outcome"], "suspended")
        bed.resume_twin([stop("end-turn", "done")])
        messages = read_conversation(transcripts.transcript_path(bed.state, SID)).messages
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertIn("=== LIGHT BEGIN", messages[1]["content"][0]["text"])
        self.assertEqual(messages[2], {"role": "user", "content": "as assumed\n"})

    def test_the_answer_from_stdin_and_human_mode(self):
        bed = self.bed()
        self.suspended(bed)
        human = bed.resume(self.DELIVER, "--answer", "-", answer=None, json_mode=False,
                           stdin=b"from stdin\n")
        self.assertEqual(human.code, 0, human.stderr)
        tarball = (bed.state / "sandbox" / SID / "home" / "response.tar.gz").resolve()
        self.assertEqual(human.stdout, f"bale apply {tarball}\n")
        self.assertIn("resume: ", human.stderr)
        first = [l for l in bed.transcript() if l["kind"] == "request"][-3]
        self.assertEqual(first["appended"], [{"role": "user", "content": "from stdin\n"}])

    def test_a_resumed_run_can_suspend_again_and_resume_again(self):
        bed = self.bed()
        self.suspended(bed)
        again = bed.resume_twin([tools(("escalate", {"questions": [QUESTION]}), n=5)])
        self.assertEqual((again["outcome"], again["command"]), ("suspended", "resume"))
        self.assertIn(f"=== LIGHT BEGIN {SID} ===", again["block"])
        self.assertEqual(again["inflight"], "kept")
        self.assertIsNone(kill.read_running(bed.state, SID), "the running record is cleared")
        final = bed.resume_twin(self.DELIVER, answer="second answer\n")
        self.assertEqual(final["outcome"], "delivered", final["reason"])
        starts = self.of(bed.transcript(), "run-start")
        self.assertEqual([s["resumed_from"] is None for s in starts], [True, False, False])
        self.assertEqual(final["resumed_from"], starts[2]["seq"] - 1)
        conversation = read_conversation(transcripts.transcript_path(bed.state, SID))
        self.assertEqual(conversation.runs, 3)
        answers = [m for m in conversation.messages
                   if m == {"role": "user", "content": "second answer\n"}]
        self.assertEqual(len(answers), 1)

    def test_a_stopped_run_is_resumed_too(self):
        bed = self.bed()
        twin = bed.twin([stop("model-refusal", reason="the provider said no")])
        self.assertEqual(twin["outcome"], "stopped")
        resumed = bed.resume_twin([stop("end-turn", "reworded, done")], answer="reworded\n")
        self.assertEqual((resumed["outcome"], resumed["shape"]), ("ended", "prose"))

    def test_the_window_on_a_resume(self):
        bed = self.bed()
        self.suspended(bed)
        twin = bed.resume_twin([tools(("list_dir", {}), n=1, input=1000),
                                stop("end-turn", "never")], "--window", "1000")
        self.assertEqual((twin["outcome"], twin["stop"], twin["turns"]),
                         ("stopped", "window-exhausted", 1))
        self.assertEqual(twin["window"], {"size": 1000, "used": 1000, "warned": True,
                                          "source": "flag"})
        self.assertEqual(twin["rewarm"], usage(1000))

    def test_the_same_constants_are_accepted(self):
        bed = self.bed()
        bed.twin([stop("end-turn", light())], "--max-tokens", "500", "--thinking", "off")
        twin = bed.resume_twin([stop("end-turn", "done")], "--max-tokens", "500",
                               "--thinking", "off", "--model", "fake")
        self.assertEqual(twin["outcome"], "ended", twin["reason"])
        start = self.of(bed.transcript(), "run-start")[-1]
        self.assertEqual((start["max_tokens"], start["thinking"]), (500, "off"))


# ---------------------------------------------------------------------------
# 2. escalate's clarification form, through the verb
# ---------------------------------------------------------------------------


class TheClarificationForm(ResumeCase):

    def test_suspended_on_the_clarification_tarball_then_resumed(self):
        bed = self.bed(with_tools=True)
        questions = [dict(QUESTION, question=f"question {n}?") for n in range(1, 5)]
        twin = bed.twin([tools(("escalate", {"questions": questions, "blocking": True}),
                               ("shell", {"command": "touch never-run"}), n=1)])
        self.assertEqual((twin["outcome"], twin["stop"], twin["block"]),
                         ("suspended", None, None), twin["reason"])
        home = (bed.state / "sandbox" / SID / "home").resolve()
        tarball = home / "escalations" / "1" / f"response-{SID}.tar.gz"
        self.assertEqual(twin["tarball"], str(tarball))
        self.assertEqual(twin["apply_line"], f"bale apply {tarball}")
        self.assertEqual(twin["dry_run"]["outcome"], "dry-run")
        self.assertEqual((twin["move"], twin["actor"]), ("operator-applies", "operator"))
        self.assertFalse((home / "never-run").exists())
        self.assertEqual(twin["inflight"], "kept")
        self.assertEqual(bed.stub.calls()[1], ["apply", "--dry-run", "--json", str(tarball)])
        # The tarball: one top directory, a clarification manifest.
        with tarfile.open(tarball) as tf:
            manifest = json.load(tf.extractfile("response-002/manifest.json"))
        self.assertEqual((manifest["response_kind"], len(manifest["questions"])),
                         ("clarification", 4))
        self.assertIn("R5's test goal", manifest["summary"])
        result = next(l for l in bed.transcript() if l["kind"] == "tool-result")["result"]
        self.assertEqual((result["kind"], result["suspend"], result["questions"]),
                         ("clarification", True, 4))
        self.assertEqual(result["sha256"], hashlib.sha256(tarball.read_bytes()).hexdigest())
        # Human mode: the apply line alone.
        human_bed = self.bed(with_tools=True)
        human = human_bed.run([tools(("escalate", {"questions": [QUESTION],
                                                   "blocking": True}), n=1)],
                              json_mode=False)
        self.assertEqual(human.code, 1)
        self.assertTrue(human.stdout.startswith("bale apply "), human.stdout)
        self.assertEqual(len(human.stdout.splitlines()), 1)
        # The operator applies it; the planner answers; bale relays the block.
        resumed = bed.resume_twin(SuspendThenResume.DELIVER, answer=ANSWER_BLOCK)
        self.assertEqual(resumed["outcome"], "delivered", resumed["reason"])
        first = [l for l in bed.transcript() if l["kind"] == "request"][-3]
        self.assertEqual(first["appended"], [{"role": "user", "content": ANSWER_BLOCK}])

    def test_a_dry_run_that_is_not_clean_stops_the_run(self):
        from tests.test_run import DRIFT
        bed = self.bed(with_tools=True, dry_run=DRIFT, apply_exit=1)
        twin = bed.twin([tools(("escalate", {"questions": [QUESTION], "blocking": True}),
                               n=1)])
        self.assertEqual((twin["outcome"], twin["move"], twin["apply_line"]),
                         ("stopped", "admit-or-return", None))
        self.assertIn("clarification response did not pass the dry run", twin["reason"])

    def test_without_the_crafter_it_is_a_tool_error_and_the_turn_goes_on(self):
        bed = self.bed()   # the default request carries a placeholder, not the crafter
        bed_request = bed.state / "sandbox" / SID / "home" / "request" / "tools"
        twin = bed.twin([tools(("shell", {"command": "rm request/tools/craft_response.py"}),
                               n=1),
                         tools(("escalate", {"questions": [QUESTION], "blocking": True}),
                               n=2),
                         stop("end-turn", "gave up")])
        self.assertFalse((bed_request / "craft_response.py").exists())
        self.assertEqual((twin["outcome"], twin["tool_calls"]), ("ended", 2))
        result = [l for l in bed.transcript() if l["kind"] == "tool-result"][-1]["result"]
        self.assertTrue(result["is_error"])
        self.assertIn("carries no crafter", result["content"])


# ---------------------------------------------------------------------------
# 3. Refused before anything starts
# ---------------------------------------------------------------------------


class ResumeRefusals(ResumeCase):

    def assert_refused(self, twin: dict, *needles: str) -> None:
        self.assertEqual((twin["command"], twin["outcome"], twin["ok"], twin["turns"]),
                         ("resume", "refused", False, 0))
        for needle in needles:
            self.assertIn(needle, twin["reason"])
        self.assertEqual(tuple(twin)[2:2 + len(R5_TWIN_KEYS)], R5_TWIN_KEYS)
        self.assertIsNone(twin["running"], "nothing was registered")

    def kept(self) -> ResumeBed:
        bed = self.bed()
        self.suspended(bed)
        self.calls = len(bed.stub.calls())
        return bed

    def assert_nothing_happened(self, bed: ResumeBed, before: list[dict]) -> None:
        self.assertEqual(bed.transcript(), before, "the transcript is untouched")
        self.assertEqual(len(bed.stub.calls()), self.calls, "bale was not called")
        self.assertIsNone(kill.read_running(bed.state, SID))

    def test_no_kept_session(self):
        bed = self.bed()
        (bed.state / "inflight").mkdir()
        twin = bed.resume_twin([stop("end-turn")])
        self.assert_refused(twin, f"no in-flight record of {SID}", "delivered")
        self.assertEqual(bed.stub.calls(), [])

    def test_a_delivered_session(self):
        bed = self.bed()
        bed.twin([tools(("shell", {"command": DELIVER_SHELL}), n=1),
                  tools(("deliver", {"tarball": "response.tar.gz"}), n=2)])
        self.assert_refused(bed.resume_twin([stop("end-turn")]), "it was delivered")

    def test_a_record_without_runtime_fields(self):
        bed = self.bed()
        inflight.record_open(bed.state, SID, outcome="opened", cwd=str(bed.repo),
                             tarball=str(bed.request), desk=None, bundle_sha256="b" * 64,
                             opener="opener\n")
        self.assert_refused(bed.resume_twin([stop("end-turn")]), "has no runtime fields")

    def test_the_transcript_missing_or_unreadable(self):
        bed = self.kept()
        path = transcripts.transcript_path(bed.state, SID)
        saved = path.read_bytes()
        path.unlink()
        self.assert_refused(bed.resume_twin([stop("end-turn")]), "does not exist")
        path.write_bytes(saved + b"not json at all\n")
        self.assert_refused(bed.resume_twin([stop("end-turn")]), "is not JSON")
        path.write_bytes(saved[:-1])
        self.assert_refused(bed.resume_twin([stop("end-turn")]), "torn")
        self.assertEqual(len(bed.stub.calls()), self.calls)

    def test_the_answer_missing_empty_or_unreadable(self):
        bed = self.kept()
        before = bed.transcript()
        self.assert_refused(bed.resume_twin([stop("end-turn")], answer=None),
                            "--answer FILE|- is required")
        self.assert_refused(bed.resume_twin([stop("end-turn")], answer="  \n"), "is empty")
        self.assert_refused(bed.resume_twin([stop("end-turn")], "--answer", "-", answer=None,
                                            stdin=b""), "--answer - is empty")
        self.assert_refused(bed.resume_twin([stop("end-turn")], "--answer",
                                            str(bed.base / "nope.txt"), answer=None),
                            "no such file")
        bed.answer_path.write_bytes(b"\xff\xfe")
        self.assert_refused(bed.resume_twin([stop("end-turn")], "--answer",
                                            str(bed.answer_path), answer=None), "not UTF-8")
        self.assert_nothing_happened(bed, before)

    def test_the_cap_absent_or_not_dollars(self):
        bed = self.kept()
        self.assert_refused(bed.resume_twin([stop("end-turn")], cap=None),
                            "--cap USD is required", "D15")
        self.assert_refused(bed.resume_twin([stop("end-turn")], cap="lots"), "--cap")

    def test_the_adapter_s_arguments(self):
        bed = self.kept()
        self.assert_refused(bed.resume_twin(None), "the fake adapter, which needs --script")
        bed.resume_script.write_text("not json")
        self.assert_refused(bed.resume_twin(None, "--script", str(bed.resume_script)),
                            "is not a JSON script")
        # The record says anthropic: a script refuses, and so does a missing key.
        record = inflight.read_inflight(bed.state, SID)
        inflight.record_runtime(bed.state, SID, {**record["runtime"], "adapter": "anthropic",
                                                 "model": "claude-x"})
        self.assert_refused(bed.resume_twin([stop("end-turn")],
                                            env={"ANTHROPIC_API_KEY": ""}),
                            "--script is the fake adapter's", "ANTHROPIC_API_KEY is not set")

    def test_spawn_time_constants_that_differ(self):
        bed = self.kept()
        twin = bed.resume_twin([stop("end-turn")], "--model", "other", "--max-tokens", "99",
                               "--thinking", "off")
        self.assert_refused(twin, "--model other differs from the transcript's 'fake'",
                            "--max-tokens 99 differs from the transcript's 16000",
                            "--thinking off differs from the transcript's 'adaptive'",
                            "D12")

    def test_every_reason_at_once(self):
        bed = self.kept()
        twin = bed.resume_twin(None, "--max-turns", "0", "--window", "0", "--model", "x",
                               answer=None, cap=None)
        self.assert_refused(twin, "--cap USD is required", "--answer FILE|- is required",
                            "--max-turns 0", "--window 0", "needs --script",
                            "--model x differs")
        self.assertEqual(len(twin["refusals"]), 6, twin["refusals"])

    def test_a_sid_twine_does_not_accept_and_a_state_dir_that_is_not_there(self):
        bed = self.bed()
        result = run_cli("resume", "../escape", "--cap", "1", "--answer", "-",
                         "--state-dir", str(bed.base / "absent"), "--json", stdin=b"x")
        twin = json.loads(result.stdout)
        self.assertEqual((result.code, twin["sid"]), (1, None))
        self.assert_refused(twin, "is not a session id twine accepts", "does not exist")

    def test_the_sandbox_home_gone(self):
        bed = self.kept()
        import shutil
        shutil.rmtree(bed.state / "sandbox" / SID / "home" / "request")
        self.assert_refused(bed.resume_twin([stop("end-turn")]), "holds no request/")
        shutil.rmtree(bed.state / "sandbox" / SID)
        self.assert_refused(bed.resume_twin([stop("end-turn")]), "does not exist")


# ---------------------------------------------------------------------------
# 4. The rebuild
# ---------------------------------------------------------------------------


class TheRebuild(unittest.TestCase):

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="twine-rebuild-")
        self.addCleanup(self._dir.cleanup)
        self.state = Path(self._dir.name)

    def write(self, *events) -> Path:
        t = transcripts.Transcript.open(self.state, SID, clock=lambda: "T")
        for kind, fields in events:
            t.append(kind, **fields)
        return t.path

    START = ("run-start", {"adapter": "fake", "model": "fake", "max_tokens": 10,
                           "thinking": "off"})

    @staticmethod
    def req(total, *messages, **extra):
        return ("request", {"call": 1, "messages_total": total, "appended": list(messages),
                            **extra})

    U = {"role": "user", "content": "u"}
    A = {"role": "assistant", "content": [{"type": "text", "text": "a"}]}

    def test_joined_in_order_sent_false_included(self):
        path = self.write(self.START, self.req(1, self.U), ("turn", {}),
                          self.req(3, self.A, self.U), self.req(4, self.A, sent=False))
        c = read_conversation(path)
        self.assertEqual(c.messages, (self.U, self.A, self.U, self.A))
        self.assertEqual((c.last_seq, c.request_lines, c.runs), (5, 3, 1))
        self.assertEqual(c.run_start.as_json(), {"seq": 1, "adapter": "fake", "model": "fake",
                                                 "max_tokens": 10, "thinking": "off"})

    def test_a_fresh_run_starts_over_and_a_resumed_one_continues(self):
        path = self.write(self.START, self.req(1, self.U), self.START, self.req(1, self.U),
                          self.req(2, self.A), ("run-start", {**self.START[1],
                                                               "resumed_from": 5}),
                          self.req(3, self.U))
        c = read_conversation(path)
        self.assertEqual((c.messages, c.runs), ((self.U, self.A, self.U), 2))

    def test_refusals(self):
        cases = {
            "no run-start": ([self.req(1, self.U)], "no run-start"),
            "no request": ([self.START, ("turn", {})], "no request line"),
            "a count that disagrees": ([self.START, self.req(2, self.U)],
                                       "messages_total 2"),
            "a bad message": ([self.START, self.req(1, {"role": "system", "content": "x"})],
                              "never wrote"),
            "no appended": ([self.START, ("request", {"messages_total": 1})],
                            "no `appended` list"),
            "a bad run-start": ([("run-start", {"adapter": "fake"}), self.req(1, self.U)],
                                "max_tokens"),
        }
        for name, (events, needle) in cases.items():
            with self.subTest(case=name):
                path = transcripts.transcript_path(self.state, SID)
                if path.exists():
                    path.unlink()
                path = self.write(*events)
                with self.assertRaises(ResumeError) as caught:
                    read_conversation(path)
                self.assertIn(needle, str(caught.exception))
        with self.assertRaisesRegex(ResumeError, "does not exist"):
            read_conversation(self.state / "nope.jsonl")


# ---------------------------------------------------------------------------
# 5. The registration order, in-process with a stand-in group
# ---------------------------------------------------------------------------


class ResumeRegistration(ResumeCase):

    def test_the_record_exists_before_the_sandbox_s_first_spawn_and_is_cleared(self):
        bed = self.bed()
        bed.twin([stop("end-turn", light())])
        group = RealGroup()
        self.addCleanup(group.cleanup)
        seen = []

        def seam(argv, **kw):
            if argv[0] == "unshare" and argv[-1] == "true":
                seen.append(kill.read_running(bed.state, SID))
            return process.run_process(argv, **kw)

        bed.resume_script.write_text(json.dumps([stop("end-turn", "done")]))
        bed.answer_path.write_text("as assumed\n")
        out, err = io.StringIO(), io.StringIO()
        ctx = Context(env={"PATH": os.environ.get("PATH", "")}, stdout=out, stderr=err,
                      which=lambda name: None, stdin=io.BytesIO(b""), run=seam)
        stand_in = process.OwnGroup(pid=group.pgid, pgid=group.pgid, setsid=False)
        with mock.patch("twine.commands.resume.lead_own_group", return_value=stand_in):
            code = main(["resume", SID, "--cap", "1", "--answer", str(bed.answer_path),
                         "--script", str(bed.resume_script), "--state-dir", str(bed.state),
                         "--bale-root", str(bed.stub.root), "--json"], ctx=ctx)
        twin = json.loads(out.getvalue())
        self.assertEqual((code, twin["outcome"]), (1, "ended"), err.getvalue())
        self.assertEqual(len(seen), 1)
        self.assertIsNotNone(seen[0], "registered before the sandbox's first spawn")
        self.assertEqual(seen[0].pgid, group.pgid)
        self.assertIsNone(kill.read_running(bed.state, SID), "cleared at the end")
        record = inflight.read_inflight(bed.state, SID)
        self.assertEqual(record["runtime"]["pgid"], group.pgid, "the runtime fields replaced")


# ---------------------------------------------------------------------------
# 6. The pinned bale tools
# ---------------------------------------------------------------------------


class ThePinnedBaleTools(unittest.TestCase):

    def test_the_copies_hash_as_pinned(self):
        self.assertEqual(sorted(p.name for p in BALE_TOOLS.iterdir()),
                         sorted(BALE_TOOLS_SHA256))
        for name, sha in BALE_TOOLS_SHA256.items():
            with self.subTest(tool=name):
                self.assertEqual(hashlib.sha256((BALE_TOOLS / name).read_bytes()).hexdigest(),
                                 sha)


if __name__ == "__main__":
    unittest.main()

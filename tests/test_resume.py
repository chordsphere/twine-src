"""`twine resume` and escalate's clarification form (Arc 2 R5; D23;
cli-contract.md §19, runtime-contract.md §6.6, §7.9), and since
twine-run-recovery the recovery rule: a kept session resumes — a raised cap, no
`--answer` but twine's own `RESUME_TEXT`, `--cap +USD`, `--plan`, every ending's
`next`, a `killed` one refused. No model anywhere: the fake adapter plays a
script (T8).

How it is driven:

  - **Recovery** (`TheResumeRule` and the classes after it): the same child
    processes and stub as below; `twine.recovery`'s own pieces in-process
    (`TheRecoveryReading`).

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
import shlex
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from twine import inflight, kill, process, transcript as transcripts
from twine.cli import Context, main
from twine import recovery, spend
from twine.runtime.resume import RESUME_TEXT, ResumeError, read_conversation

from tests.helpers import (BALE_TOOLS, BALE_TOOLS_SHA256, RealGroup, StubBale,
                           request_tool_members, run_cli)
from tests.test_run import (DELIVER_SHELL, DRIFT, DRY_RUN, PRICES_DOUBLE, SENTINEL_KEY, SID,
                            TWIN_KEYS, Bed,
                            light, request_tarball, stop, summary_at, tools, usage)

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
                          start["thinking"]), ("fake", "fake", 32000, "adaptive"))
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

    def test_the_last_progress_line_of_a_resume_is_its_summary(self):
        """twine-run-ergonomics, item 6: after every other line, `summary:`
        — this run's calls, tool calls, retries, cost and wall time."""
        bed = self.bed()
        self.suspended(bed)
        twin = bed.resume_twin(self.DELIVER)
        shown = twin["_stderr"].rstrip("\n").split("\n")
        last = shown[summary_at(shown)]
        self.assertRegex(last, r"^\[twine\] resume: summary: delivered, move operator-applies, "
                               r"2 calls, 2 tool calls, 0 retries, \$\d+\.\d\d(\d\d)?, \d+s$")
        for line in twin["_stderr"].splitlines():
            if "call 1:" in line and "asks for" in line:
                self.assertRegex(line, r"\$\d+\.\d\d(\d\d)?, \d+s")

    def test_the_answer_from_stdin_and_human_mode(self):
        bed = self.bed()
        self.suspended(bed)
        human = bed.resume(self.DELIVER, "--answer", "-", answer=None, json_mode=False,
                           stdin=b"from stdin\n")
        self.assertEqual(human.code, 0, human.stderr)
        tarball = (bed.state / "sandbox" / SID / "home" / "response.tar.gz").resolve()
        self.assertEqual(human.stdout, f"bale apply {tarball} --cost-file "
                                       f"{bed.state / 'cost' / (SID + '.json')}\n")
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
        self.assertEqual((twin["outcome"], twin["stop"]), ("suspended", None), twin["reason"])
        # twine-run-ergonomics, item 7: the twin's `block` is the exchange
        # paste block, beside the tarball, the apply line and the dry run.
        from twine import shapes
        found = shapes.find_blocks(twin["block"]).blocks
        self.assertEqual([b.kind for b in found], ["exchange"])
        self.assertTrue(found[0].ok, found[0].error)
        self.assertEqual((found[0].fields["sid"], found[0].fields["from"]), (SID, "worker"))
        self.assertEqual([q["question"] for q in found[0].fields["record"]["questions"]],
                         [f"question {n}?" for n in range(1, 5)])
        home = (bed.state / "sandbox" / SID / "home").resolve()
        tarball = home / "escalations" / "1" / f"response-{SID}.tar.gz"
        self.assertEqual(twin["tarball"], str(tarball))
        self.assertEqual(twin["apply_line"], f"bale apply {tarball} --cost-file "
                                             f"{bed.state / 'cost' / (SID + '.json')}")
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
                            "--max-tokens 99 differs from the transcript's 32000",
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
# 5. The recovery rule (twine-run-recovery)
# ---------------------------------------------------------------------------

# The user message a resume with no answer appends, byte for byte, as the
# brief pins it — spelled out here, not imported, so the test holds the
# constant to the bytes.
EXACT_RESUME_TEXT = "This session was stopped and has been resumed; continue from where you left off."
# A call that costs $1.10 at the price double's $1 per million input tokens:
# under a cap of 1.05 it is admitted (the worst case is cents) and spends the
# cap; the next call is refused.
BURN = {"input": 1_100_000, "output": 0}
SPENT_CAP = "1.05"
PLAN_KEYS = ("plan", "sid", "outcome", "stop", "move", "actor", "resumable", "why", "window",
             "calls", "spend_usd", "per_call_usd", "next_call_worst_usd", "suggested_cap_usd",
             "last_tools", "home", "next", "reason")


class RecoveryCase(ResumeCase):

    def capped(self, bed: ResumeBed, **kw) -> dict:
        """A run stopped `cap-reached` after one call that spent the cap."""
        twin = bed.twin([tools(("list_dir", {}), n=1, **BURN), stop("end-turn", "never")],
                        cap=SPENT_CAP, **kw)
        self.assertEqual((twin["outcome"], twin["stop"], twin["turns"]),
                         ("cap-reached", "cap-reached", 1), twin["reason"])
        return twin

    def plan(self, bed: ResumeBed, *extra: str) -> dict:
        result = bed.resume(None, "--plan", *extra, answer=None, cap=None)
        obj = json.loads(result.stdout)
        self.assertEqual(result.code, 0 if obj["ok"] else 1, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return obj

    def snapshot(self, bed: ResumeBed) -> dict[str, bytes]:
        return {str(p.relative_to(bed.state)): p.read_bytes()
                for p in sorted(bed.state.rglob("*")) if p.is_file()}

    def spend_lines(self, bed: ResumeBed) -> int:
        return len(bed.records())


class TheResumeRule(RecoveryCase):
    """Outcomes 2, 3 and 4: a cap-reached run resumes under a raised cap;
    killed is refused; --answer is optional but on `suspended`."""

    def test_the_same_cap_ends_cap_reached_before_any_call(self):
        bed = self.bed()
        self.capped(bed)
        before_records, before_bale = self.spend_lines(bed), len(bed.stub.calls())
        twin = bed.resume_twin([stop("end-turn", "never")], answer=None, cap=SPENT_CAP)
        self.assertEqual((twin["command"], twin["outcome"], twin["stop"], twin["turns"]),
                         ("resume", "cap-reached", "cap-reached", 0))
        self.assertIn("already spent", twin["reason"])
        self.assertIn("$1.1", twin["reason"], "the reason names the spend so far")
        self.assertEqual(self.spend_lines(bed), before_records, "no new spend line")
        self.assertEqual(len(bed.stub.calls()), before_bale)
        self.assertEqual(twin["usage"]["input"], 0)

    def test_a_raised_cap_makes_the_next_call(self):
        bed = self.bed()
        self.capped(bed)
        before = self.spend_lines(bed)
        twin = bed.resume_twin([stop("end-turn", "now done")], answer=None, cap="5")
        self.assertEqual((twin["outcome"], twin["shape"], twin["turns"]), ("ended", "prose", 1))
        self.assertEqual(self.spend_lines(bed), before + 1)
        self.assertEqual(twin["cap_usd"], 5.0)

    def test_a_plus_cap_is_the_spend_so_far_plus_the_amount(self):
        bed = self.bed()
        self.capped(bed)
        twin = bed.resume_twin([stop("end-turn", "now done")], answer=None, cap="+2")
        self.assertEqual((twin["outcome"], twin["turns"], twin["cap_usd"]), ("ended", 1, 3.1))
        start = self.of(bed.transcript(), "run-start")[-1]
        self.assertEqual((start["cap_given"], start["cap_usd"]), ("+2", 3.1))
        first = self.of(bed.transcript(), "run-start")[0]
        self.assertEqual((first["cap_given"], first["cap_usd"]), (SPENT_CAP, 1.05))

    def test_a_plus_cap_for_a_second_desk_on_twine_run(self):
        bed = self.bed()
        fresh = bed.twin([stop("end-turn", "done")], cap="+2")
        self.assertEqual((fresh["cap_usd"], fresh["outcome"]), (2.0, "ended"))
        self.assertEqual(self.of(bed.transcript(), "run-start")[0]["cap_given"], "+2")
        second = self.bed()
        self.capped(second)
        again = second.twin([stop("end-turn", "done")], cap="+2")
        self.assertEqual(again["cap_usd"], 3.1)

    def test_a_plus_cap_that_is_not_dollars_or_cannot_be_priced(self):
        bed = self.bed()
        self.capped(bed)
        for bad in ("+", "+lots", "++1", "+-1"):
            twin = bed.resume_twin(None, answer=None, cap=bad)
            self.assertEqual(twin["outcome"], "refused", bad)
            self.assertIn("--cap", twin["reason"])
        (bed.state / "prices.toml").unlink()
        twin = bed.resume_twin([stop("end-turn")], answer=None, cap="+2")
        self.assertEqual(twin["outcome"], "refused")
        self.assertIn("--cap +2", twin["reason"])
        self.assertIn("cannot be added", twin["reason"])
        self.assertEqual(twin["turns"], 0)

    def test_a_stopped_run_resumed_without_an_answer_carries_resume_text(self):
        self.assertEqual(RESUME_TEXT.encode("utf-8"), EXACT_RESUME_TEXT.encode("utf-8"))
        bed = self.bed()
        bed.twin([stop("model-refusal", reason="the provider said no")])
        twin = bed.resume_twin([stop("end-turn", "carrying on")], answer=None)
        self.assertEqual((twin["outcome"], twin["shape"]), ("ended", "prose"), twin["reason"])
        lines = bed.transcript()
        start = self.of(lines, "run-start")[-1]
        self.assertEqual(start["answer"], {
            "source": "twine", "chars": len(EXACT_RESUME_TEXT),
            "sha256": hashlib.sha256(EXACT_RESUME_TEXT.encode("utf-8")).hexdigest()})
        sent = [l for l in self.of(lines, "request") if l["seq"] > start["seq"]][0]
        self.assertEqual(sent["appended"], [{"role": "user", "content": EXACT_RESUME_TEXT}])
        raw = transcripts.transcript_path(bed.state, SID).read_bytes()
        self.assertIn(json.dumps(EXACT_RESUME_TEXT).encode("utf-8"), raw)

    def test_every_resumable_outcome_goes_on_without_an_answer(self):
        """stopped (above), cap-reached, ended — and a cap-unchecked one, once
        its fault (the missing price row) is fixed."""
        bed = self.bed()
        self.capped(bed)
        twin = bed.resume_twin([stop("end-turn", "done")], answer=None, cap="5")
        self.assertEqual(self.of(bed.transcript(), "run-start")[-1]["answer"]["source"], "twine")
        self.assertEqual(twin["outcome"], "ended")
        again = bed.resume_twin([stop("end-turn", "done again")], answer=None, cap="6")
        self.assertEqual((again["outcome"], again["turns"]), ("ended", 1))
        unchecked = self.bed()
        (unchecked.state / "prices.toml").write_text("# no rows\n", encoding="utf-8")
        first = unchecked.twin([stop("end-turn")])
        self.assertEqual((first["outcome"], first["stop"]), ("cap-unchecked", "cap-unchecked"))
        (unchecked.state / "prices.toml").write_text(PRICES_DOUBLE, encoding="utf-8")
        fixed = unchecked.resume_twin([stop("end-turn", "done")], answer=None)
        self.assertEqual(fixed["outcome"], "ended", fixed["reason"])

    def test_an_answer_given_is_still_used_verbatim(self):
        bed = self.bed()
        self.capped(bed)
        bed.resume_twin([stop("end-turn", "done")], answer="the real answer\n", cap="5")
        start = self.of(bed.transcript(), "run-start")[-1]
        self.assertEqual(start["answer"]["source"], str(bed.answer_path))
        sent = [l for l in self.of(bed.transcript(), "request") if l["seq"] > start["seq"]][0]
        self.assertEqual(sent["appended"], [{"role": "user", "content": "the real answer\n"}])

    def test_a_suspended_session_still_needs_its_answer(self):
        bed = self.bed()
        self.suspended(bed)
        before = bed.transcript()
        twin = bed.resume_twin([stop("end-turn")], answer=None)
        self.assertEqual((twin["outcome"], twin["turns"]), ("refused", 0))
        self.assertIn("--answer FILE|- is required on a suspended session", twin["reason"])
        self.assertEqual(bed.transcript(), before, "nothing was written")

    def test_a_killed_session_is_refused_with_the_respawn_path(self):
        bed = self.bed()
        kill.request_abort(bed.state, SID)
        killed = bed.twin([stop("end-turn")])
        self.assertEqual((killed["outcome"], killed["stop"], killed["turns"]),
                         ("killed", "killed", 0))
        self.assertEqual(killed["next"], [], "a kill names no resume line")
        self.assertIn("respawn-from-request", killed["_stderr"])
        self.assertIn("no resume line", killed["_stderr"])
        before = bed.transcript()
        # the abort request standing, and then (removed) the transcript's own word
        for removed in (False, True):
            if removed:
                kill.abort_path(bed.state, SID).unlink()
            twin = bed.resume_twin([stop("end-turn")], answer=None)
            self.assertEqual((twin["outcome"], twin["turns"]), ("refused", 0), removed)
            for needle in ("was killed", "aborted", "respawn-from-request", "stays a close"):
                self.assertIn(needle, twin["reason"])
        self.assertEqual(bed.transcript(), before)
        self.assertIsNone(kill.read_running(bed.state, SID))
        self.assertEqual([c[0] for c in bed.stub.calls()], ["open"], "bale saw only the open")

    def test_a_delivered_session_names_its_apply_line(self):
        bed = self.bed()
        twin = bed.twin([tools(("shell", {"command": DELIVER_SHELL}), n=1),
                         tools(("deliver", {"tarball": "response.tar.gz"}), n=2)])
        refused = bed.resume_twin([stop("end-turn")], answer=None)
        self.assertIn("it was delivered", refused["reason"])
        self.assertIn(twin["apply_line"], refused["reason"])


class TheRawFileIsNeverOverwritten(unittest.TestCase):

    def test_a_resumed_run_keeps_the_first_run_s_raw_file(self):
        from tests import test_anthropic as T
        from tests.test_run import (FAKE_MODEL, StreamTransport, anthropic_bed,
                                    the_table, transcript_lines)
        from twine.runtime import loop as runloop
        from twine.runtime.adapters import anthropic
        from twine.runtime.boundary import Boundary
        first_body = T.derived_ceiling(T.text_block(0, "first half", stop=False), "end_turn")
        second_body = T.derived_ceiling(T.text_block(0, "second half", stop=False), "end_turn")
        bed, _ = anthropic_bed(self, first_body)
        self.assertEqual(bed.run().stop, "malformed-shape")
        kept = transcripts.raw_path(bed.state, SID, 1)
        self.assertEqual(kept.read_bytes(), first_body[2])
        # the resumed run: its call numbers restart from 1
        adapter = anthropic.AnthropicAdapter(
            env={anthropic.KEY_VARIABLE: SENTINEL_KEY}, transport=StreamTransport(second_body),
            model=FAKE_MODEL, system=bed.prompt.note)
        again = runloop.Loop(
            boundary=Boundary(adapter), sandbox=bed.sandbox, transcript=bed.transcript,
            settings=runloop.LoopSettings(sid=SID, state_dir=bed.state,
                                          cap_usd=bed.loop.settings.cap_usd, model=FAKE_MODEL,
                                          max_tokens=16000),
            prompt=bed.prompt, moves=runloop.MoveBook(the_table()), tools=bed.tools,
            deliver=bed.deliver, messages=[runloop.user_message("again")], sleep=lambda s: None)
        self.assertEqual(again.run().stop, "malformed-shape")
        self.assertEqual(kept.read_bytes(), first_body[2], "the first run's file is as it was")
        second = transcripts.raw_path(bed.state, SID, 1, 2)
        self.assertEqual(second.name, f"{SID}.call-1-2.raw")
        self.assertEqual(second.read_bytes(), second_body[2])
        self.assertEqual([l["raw"] for l in transcript_lines(bed, "turn")],
                         [str(kept), str(second)])
        self.assertEqual(transcripts.list_transcripts(bed.state), ((SID,), ()))


class TheEndingsNameTheirNextCommand(RecoveryCase):
    """Outcome 7: the twin's `next` and the human `next:` lines."""

    def carried(self, bed: ResumeBed) -> str:
        return (f"--state-dir {shlex.quote(str(bed.state))} --bale-root "
                f"{shlex.quote(str(bed.stub.root))} --cwd {shlex.quote(str(bed.repo))}")

    def test_next_is_the_last_name_beside_the_fixed_ones(self):
        bed = self.bed()
        twin = bed.twin([stop("end-turn", "done")])
        self.assertEqual(list(twin)[-2:], ["next", "_stderr"])
        resumed = bed.resume_twin([stop("end-turn", "again")], answer=None)
        self.assertEqual(list(resumed)[-2:], ["next", "_stderr"])
        refused = bed.resume_twin(None, answer=None, cap="lots")
        self.assertEqual(refused["next"], [])

    def test_cap_reached_names_the_resume_line_with_the_suggested_cap(self):
        bed = self.bed()
        twin = self.capped(bed)
        (line,) = twin["next"]
        plan = self.plan(bed)
        suggested = plan["suggested_cap_usd"]
        self.assertEqual(line, f"twine resume {SID} --cap {suggested:.2f} {self.carried(bed)}")
        shown = [l for l in twin["_stderr"].splitlines() if l.startswith("[twine] next: ")]
        self.assertEqual(shown, [f"[twine] next: {line}"])
        self.assertEqual(twin["_stderr"].splitlines()[-1], shown[0], "after the summary line")

    def test_the_line_run_makes_the_next_call(self):
        bed = self.bed()
        twin = self.capped(bed)
        argv = shlex.split(twin["next"][0])
        self.assertEqual(argv[:3], ["twine", "resume", SID])
        bed.resume_script.write_text(json.dumps([stop("end-turn", "on we go")]), encoding="utf-8")
        before = self.spend_lines(bed)
        result = run_cli(*argv[1:], "--script", str(bed.resume_script), "--json",
                         extra_env={"ANTHROPIC_API_KEY": SENTINEL_KEY})
        obj = json.loads(result.stdout)
        self.assertEqual((obj["outcome"], obj["turns"]), ("ended", 1), obj["reason"])
        self.assertEqual(self.spend_lines(bed), before + 1)
        self.assertEqual(self.of(bed.transcript(), "run-start")[-1]["cap_given"],
                         argv[argv.index("--cap") + 1])

    def test_ended_and_suspended_and_delivered(self):
        bed = self.bed()
        ended = bed.twin([stop("end-turn", "done, I think")])
        self.assertEqual(len(ended["next"]), 1)
        self.assertRegex(ended["next"][0], rf"^twine resume {SID} --cap \d+\.\d\d --state-dir ")
        light_bed = self.bed()
        light_twin = light_bed.twin([stop("end-turn", light())])
        self.assertEqual(light_twin["outcome"], "suspended")
        self.assertRegex(light_twin["next"][0],
                         rf"^twine resume {SID} --cap \d+\.\d\d --answer - --state-dir ")
        delivered_bed = self.bed()
        delivered = delivered_bed.twin([tools(("shell", {"command": DELIVER_SHELL}), n=1),
                                        tools(("deliver", {"tarball": "response.tar.gz"}), n=2)])
        self.assertEqual(delivered["next"], [delivered["apply_line"]])
        self.assertTrue(delivered["_stderr"].rstrip("\n").endswith(
            f"[twine] next: {delivered['apply_line']}"))

    def test_the_clarification_form_names_the_apply_line(self):
        bed = self.bed(with_tools=True)
        question = {"question": "which file?", "while_doing": "reading", "would_assume": "the first",
                    "why_blocked": "two match"}
        twin = bed.twin([tools(("escalate", {"blocking": True, "questions": [question]}), n=1)])
        self.assertEqual(twin["outcome"], "suspended", twin["reason"])
        # twine-run-telemetry: after its apply line, the resume that follows the
        # planner's relayed answer (recovery's Proposal 2).
        apply_line, again = twin["next"]
        self.assertEqual(apply_line, twin["apply_line"])
        self.assertIn(" --cost-file ", apply_line)
        self.assertRegex(again, rf"^twine resume {SID} --cap \d+\.\d\d --answer - --state-dir ")

    def test_window_exhausted_names_no_command_and_says_why(self):
        bed = self.bed()
        twin = bed.twin([tools(("list_dir", {}), n=1, input=1000), stop("end-turn", "never")],
                        "--window", "1000")
        self.assertEqual((twin["outcome"], twin["stop"]), ("stopped", "window-exhausted"))
        self.assertEqual(twin["next"], [])
        self.assertIn("window-exhausted: no resume line", twin["_stderr"])
        self.assertIn("split", twin["_stderr"])

    def test_a_scope_drift_refusal_names_bale_s_admit_line_and_the_resume_line(self):
        bed = self.bed(dry_run=DRIFT, apply_exit=1)
        twin = bed.twin([tools(("shell", {"command": DELIVER_SHELL}), n=1),
                         tools(("deliver", {"tarball": "response.tar.gz"}), n=2)])
        self.assertEqual((twin["outcome"], twin["move"]), ("stopped", "admit-or-return"))
        admit, again = twin["next"]
        cost_file = bed.state / "cost" / f"{SID}.json"
        self.assertEqual(admit, f"bale apply {shlex.quote(twin['tarball'])} --cost-file "
                                f"{cost_file} --allow-out-of-scope other.txt")
        self.assertTrue(cost_file.is_file(), "the admit line is an apply: its file is written")
        self.assertEqual(twin["cost_file"], str(cost_file))
        self.assertRegex(again, rf"^twine resume {SID} --cap \d+\.\d\d --state-dir ")
        self.assertIn("enumerated in the response's notes.md", twin["_stderr"])
        shown = [l for l in twin["_stderr"].splitlines() if l.startswith("[twine] next: ")]
        self.assertEqual(shown, [f"[twine] next: {admit}", f"[twine] next: {again}"])
        # twine never runs it: bale saw the open and the dry run
        self.assertEqual([c[0] for c in bed.stub.calls()], ["open", "apply"])
        self.assertIn("--dry-run", bed.stub.calls()[1])
        # the plan reads the same line off the transcript
        plan = self.plan(bed)
        self.assertEqual(plan["next"][0], admit)
        self.assertTrue(plan["resumable"])

    def test_a_resumed_run_names_its_next_too(self):
        bed = self.bed()
        self.capped(bed)
        twin = bed.resume_twin([stop("end-turn", "done")], answer=None, cap="5")
        self.assertEqual(len(twin["next"]), 1)
        self.assertTrue(twin["next"][0].startswith(f"twine resume {SID} --cap "))
        self.assertTrue(twin["_stderr"].rstrip("\n").splitlines()[-1].startswith("[twine] next: "))

    def test_a_run_that_cannot_be_priced_names_the_plan_line(self):
        bed = self.bed()
        (bed.state / "prices.toml").write_text("# no rows\n", encoding="utf-8")
        twin = bed.twin([stop("end-turn")])
        self.assertEqual(twin["outcome"], "cap-unchecked")
        self.assertEqual(twin["next"], [f"twine resume {SID} --plan {self.carried(bed).split(' --bale-root')[0]}"
                                        f" --bale-root {shlex.quote(str(bed.stub.root))}"
                                        f" --cwd {shlex.quote(str(bed.repo))}"])


class ThePlan(RecoveryCase):
    """Outcome 5: `twine resume SID --plan`."""

    def test_the_twin_its_key_order_and_the_suggested_cap(self):
        bed = self.bed()
        self.capped(bed)
        plan = self.plan(bed)
        self.assertEqual(tuple(plan), ("command", "ok") + PLAN_KEYS)
        self.assertEqual((plan["command"], plan["ok"], plan["plan"], plan["sid"]),
                         ("resume", True, True, SID))
        self.assertEqual((plan["outcome"], plan["stop"], plan["move"], plan["actor"]),
                         ("cap-reached", "cap-reached", "stop-at-cap", "operator"))
        self.assertEqual((plan["resumable"], plan["why"]), (True, None))
        self.assertEqual((plan["calls"], plan["spend_usd"], plan["per_call_usd"]), (1, 1.1, 1.1))
        self.assertEqual(plan["window"], {"used": 1_100_000, "size": None, "fraction": None},
                         "the fake states no size: the last window line's used, no fraction")
        self.assertGreater(plan["next_call_worst_usd"], 0)
        floor = plan["spend_usd"] + plan["next_call_worst_usd"]
        self.assertGreater(plan["suggested_cap_usd"], floor)
        self.assertEqual(round(plan["suggested_cap_usd"], 2), plan["suggested_cap_usd"])
        self.assertEqual(plan["last_tools"], [{"call": 1, "name": "list_dir", "what": "."}])
        home = plan["home"]
        self.assertEqual(home["path"], str(bed.state / "sandbox" / SID / "home"))
        self.assertTrue(home["exists"])
        self.assertEqual(home["entries"], sorted(home["entries"]))
        self.assertIn("request", home["entries"])
        self.assertIn("spent", plan["reason"])

    def test_it_writes_nothing_and_starts_nothing(self):
        bed = self.bed()
        self.capped(bed)
        before, calls = self.snapshot(bed), len(bed.stub.calls())
        plan = self.plan(bed)
        self.assertTrue(plan["ok"])
        self.assertEqual(self.snapshot(bed), before, "no file of the state directory changed")
        self.assertEqual(len(bed.stub.calls()), calls, "no bale started")
        self.assertIsNone(kill.read_running(bed.state, SID))
        # it needs neither a cap nor an answer nor a script — and ignores them
        result = bed.resume(None, "--plan", "--json", answer="x\n", cap="3", json_mode=False)
        self.assertEqual(json.loads(result.stdout.splitlines()[0])["plan"], True)
        self.assertIn("ignored", result.stderr)

    def test_the_suggested_cap_arithmetic_is_stated_in_human_mode(self):
        bed = self.bed()
        self.capped(bed)
        result = bed.resume(None, "--plan", answer=None, cap=None, json_mode=False)
        self.assertEqual(result.code, 0, result.stderr)
        lines = result.stdout.splitlines()
        text = result.stdout
        for needle in ("outcome: cap-reached", "resumable: yes", "calls: 1",
                       "spend so far: $1.1", "next call's worst case: $", "suggested cap: $",
                       "re-warm of the window at the cache-write price", "40 calls at $1.1",
                       "rounded up to the cent", "last tool: call 1 list_dir", "home: "):
            self.assertIn(needle, text)
        next_at = [i for i, l in enumerate(lines) if l.startswith("next: ")]
        self.assertEqual(next_at, [len(lines) - 1], "the next lines are last")

    def test_its_next_line_with_its_cap_makes_the_next_call(self):
        bed = self.bed()
        self.capped(bed)
        plan = self.plan(bed)
        (line,) = plan["next"]
        argv = shlex.split(line)
        self.assertEqual(argv[:5], ["twine", "resume", SID, "--cap", f"{plan['suggested_cap_usd']:.2f}"])
        bed.resume_script.write_text(json.dumps([stop("end-turn", "on")]), encoding="utf-8")
        result = run_cli(*argv[1:], "--script", str(bed.resume_script), "--json",
                         extra_env={"ANTHROPIC_API_KEY": SENTINEL_KEY})
        obj = json.loads(result.stdout)
        self.assertEqual((obj["outcome"], obj["turns"]), ("ended", 1), obj["reason"])

    def test_a_suspended_session_resumes_with_an_answer(self):
        bed = self.bed()
        self.suspended(bed)
        plan = self.plan(bed)
        self.assertEqual((plan["outcome"], plan["resumable"]), ("suspended", True))
        self.assertEqual([t["name"] for t in plan["last_tools"]], ["list_dir", "escalate"])
        self.assertRegex(plan["next"][0], rf"^twine resume {SID} --cap \d+\.\d\d --answer - ")

    def test_a_killed_session_is_not_resumable(self):
        bed = self.bed()
        kill.request_abort(bed.state, SID)
        bed.twin([stop("end-turn")])
        kill.abort_path(bed.state, SID).unlink()
        plan = self.plan(bed)
        self.assertEqual((plan["ok"], plan["outcome"], plan["resumable"]), (True, "killed", False))
        self.assertIn("respawn-from-request", plan["why"])
        self.assertEqual((plan["next"], plan["suggested_cap_usd"]), ([], None))

    def test_a_delivered_session_is_not_resumable_and_names_its_apply_line(self):
        bed = self.bed()
        twin = bed.twin([tools(("shell", {"command": DELIVER_SHELL}), n=1),
                         tools(("deliver", {"tarball": "response.tar.gz"}), n=2)])
        plan = self.plan(bed)
        self.assertEqual((plan["ok"], plan["outcome"], plan["resumable"]),
                         (True, "delivered", False))
        self.assertIn("delivered", plan["why"])
        self.assertEqual(plan["next"], [twin["apply_line"]])

    def test_a_session_that_cannot_be_read(self):
        bed = self.bed()
        plan = self.plan(bed)
        self.assertEqual((plan["ok"], plan["resumable"], plan["outcome"]), (False, False, None))
        self.assertIn("does not exist", plan["why"])
        self.assertEqual(plan["reason"], plan["why"])
        self.assertEqual(tuple(plan), ("command", "ok") + PLAN_KEYS)
        result = run_cli("resume", "../escape", "--plan", "--json",
                         "--state-dir", str(bed.state))
        obj = json.loads(result.stdout)
        self.assertEqual((result.code, obj["ok"], obj["sid"]), (1, False, None))
        result = run_cli("resume", SID, "--plan", "--state-dir", str(bed.base / "absent"))
        self.assertEqual(result.code, 1)
        self.assertIn("cannot be read", result.stdout)

    def test_a_home_that_is_gone_is_not_resumable(self):
        bed = self.bed()
        self.capped(bed)
        import shutil
        shutil.rmtree(bed.state / "sandbox" / SID)
        plan = self.plan(bed)
        self.assertEqual((plan["ok"], plan["resumable"]), (True, False))
        self.assertIn("does not exist", plan["why"])
        self.assertEqual(plan["home"]["exists"], False)
        self.assertEqual(plan["home"]["entries"], [])

    def test_an_unpriced_session_suggests_no_cap(self):
        bed = self.bed()
        self.capped(bed)
        (bed.state / "prices.toml").write_text("# no rows\n", encoding="utf-8")
        plan = self.plan(bed)
        self.assertTrue(plan["ok"])
        for key in ("spend_usd", "per_call_usd", "next_call_worst_usd", "suggested_cap_usd"):
            self.assertIsNone(plan[key], key)
        self.assertEqual((plan["calls"], plan["next"]), (1, []))

    def test_the_last_tools_are_ten_and_cut_at_110_characters(self):
        bed = self.bed()
        calls = [tools(("shell", {"command": "echo " + "y" * 200 + f" {n}"}), n=n)
                 for n in range(1, 13)]
        bed.twin(calls + [stop("end-turn", "done")])
        plan = self.plan(bed)
        self.assertEqual(len(plan["last_tools"]), 10)
        self.assertEqual([t["call"] for t in plan["last_tools"]], list(range(3, 13)))
        what = plan["last_tools"][0]["what"]
        self.assertEqual(what, ("echo " + "y" * 200)[:110] + "...")

    def test_a_window_reading_is_the_last_window_line(self):
        bed = self.bed()
        bed.twin([tools(("list_dir", {}), n=1, input=500),
                  stop("end-turn", "done", usage=usage(input=700))], "--window", "2000")
        plan = self.plan(bed)
        self.assertEqual(plan["window"], {"used": 700, "size": 2000, "fraction": 0.35})


class TheRecoveryReading(unittest.TestCase):
    """twine.recovery's own pieces, in-process."""

    def test_parse_cap(self):
        plain = recovery.parse_cap(" 5 ")
        self.assertEqual((plain.given, plain.amount, plain.relative), ("5", spend.parse_usd("5"), False))
        plus = recovery.parse_cap("+0.25")
        self.assertEqual((plus.given, str(plus.amount), plus.relative), ("+0.25", "0.25", True))
        self.assertEqual(plus.absolute(spend.parse_usd("1.1")), spend.parse_usd("1.35"))
        self.assertIsNone(plus.absolute(None))
        self.assertEqual(plain.absolute(None), plain.amount)
        for bad in ("", "+", "lots", "+lots", "-1", "+-1", "++1", "nan", "+inf"):
            with self.assertRaises(ValueError, msg=bad):
                recovery.parse_cap(bad)

    def test_the_admit_line_is_built_from_the_dry_run_s_drift(self):
        line = json.loads(DRIFT.read_bytes())
        self.assertEqual(recovery.admit_line("/t/response.tar.gz", line),
                         "bale apply /t/response.tar.gz --allow-out-of-scope other.txt")
        # the recorded remedy is the same line, for the tarball bale named
        self.assertEqual(line["drift"]["remedy"],
                         "bale apply 'drift-response-2026-10-08-sc-002.tar.gz' "
                         "--allow-out-of-scope 'other.txt'")
        many = {"outcome": "scope-drift-refused",
                "drift": {"out_of_scope_paths": ["a b.txt", "c.txt"]}}
        self.assertEqual(recovery.admit_line("/t/a tarball.tar.gz", many),
                         "bale apply '/t/a tarball.tar.gz' --allow-out-of-scope 'a b.txt' "
                         "--allow-out-of-scope c.txt")
        for other in (None, {"outcome": "dry-run", "drift": None},
                      {"outcome": "scope-drift-refused", "drift": None},
                      {"outcome": "scope-drift-refused", "drift": {"out_of_scope_paths": []}},
                      {"outcome": "scope-drift-refused", "drift": {"out_of_scope_paths": [1]}}):
            self.assertIsNone(recovery.admit_line("/t/x.tar.gz", other))
        self.assertIsNone(recovery.admit_line("", line))
        # with the session's cost file, the admit line is an apply like any other
        self.assertEqual(recovery.admit_line("/t/r.tar.gz", line, "/s/cost/x.json"),
                         "bale apply /t/r.tar.gz --cost-file /s/cost/x.json "
                         "--allow-out-of-scope other.txt")

    def test_the_next_lines_by_outcome(self):
        carried = recovery.Carried(state_dir="/s d", bale_root="/b", cwd=None, prices="/p")
        nxt = lambda **kw: recovery.next_commands(  # noqa: E731
            "2026-10-08-sc-002", suggested=spend.parse_usd("1.5"), carried=carried, **kw)
        resume = ("twine resume 2026-10-08-sc-002 --cap 1.50 --state-dir '/s d' --bale-root /b "
                  "--prices /p")
        for outcome, stop_key in (("cap-reached", "cap-reached"), ("cap-unchecked", "cap-unchecked"),
                                  ("stopped", "adapter-defect"), ("stopped", "malformed-shape"),
                                  ("stopped", "max-tokens"), ("ended", None)):
            self.assertEqual(nxt(outcome=outcome, stop=stop_key), [resume], (outcome, stop_key))
        self.assertEqual(nxt(outcome="killed", stop="killed"), [])
        self.assertEqual(nxt(outcome="stopped", stop="window-exhausted"), [])
        self.assertEqual(nxt(outcome="refused", stop=None), [])
        self.assertEqual(nxt(outcome="delivered", stop=None, apply_line="bale apply /t"),
                         ["bale apply /t"])
        self.assertEqual(nxt(outcome="suspended", stop=None, apply_line="bale apply /t"),
                         ["bale apply /t",
                          resume.replace("--cap 1.50", "--cap 1.50 --answer -")])
        self.assertEqual(recovery.next_commands(
            "s", outcome="suspended", stop=None, apply_line="bale apply /t", suggested=None,
            carried=recovery.Carried(), plannable=False), ["bale apply /t"])
        self.assertEqual(recovery.next_commands(
            "s", outcome="suspended", stop=None, apply_line="bale apply /t", suggested=None,
            carried=recovery.Carried()),
            ["bale apply /t", "twine resume s --plan"])
        self.assertEqual(nxt(outcome="suspended", stop=None, light_block=True),
                         [resume.replace("--cap 1.50", "--cap 1.50 --answer -")])
        # no suggestion: the plan line, which says why
        self.assertEqual(recovery.next_commands("s", outcome="ended", stop=None, suggested=None,
                                                carried=recovery.Carried()),
                         ["twine resume s --plan"])
        self.assertEqual(nxt(outcome="stopped", stop=None, tarball="/t/r.tar.gz",
                             dry_run={"outcome": "scope-drift-refused",
                                      "drift": {"out_of_scope_paths": ["x"]}}),
                         ["bale apply /t/r.tar.gz --allow-out-of-scope x", resume])
        self.assertEqual(nxt(outcome="stopped", stop=None, tarball="/t/r.tar.gz",
                             cost_file="/s d/cost/s.json",
                             dry_run={"outcome": "scope-drift-refused",
                                      "drift": {"out_of_scope_paths": ["x"]}}),
                         ["bale apply /t/r.tar.gz --cost-file '/s d/cost/s.json' "
                          "--allow-out-of-scope x", resume])

    def test_the_suggested_cap_is_above_the_floor_and_rounded_up(self):
        """advise() over a session the test writes: one record, priced by the
        price double; the rule is the module's docstring."""
        import tempfile
        from decimal import Decimal
        from twine.runtime.resume import Conversation, RunStart
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / "prices.toml").write_text(
                '[model."fake"]\ninput = 1\noutput = 2\ncache_read = 0.1\ncache_write = 1.25\n')
            spend.append_record(state, sid=SID, model="fake", served_sid=None,
                                tokens={"input": 1_000_000, "output": 0, "thinking": None,
                                        "cache_read": 0, "cache_write": 0}, extra={"call": 1})
            conversation = Conversation(
                messages=({"role": "user", "content": "hi"},), last_seq=3, request_lines=1, runs=1,
                run_start=RunStart(seq=1, adapter="fake", model="fake", max_tokens=1000,
                                   thinking="off"))
            advice = recovery.advise(state, SID, conversation,
                                     {"used": 100_000, "size": 200_000, "fraction": 0.5}, None)
            self.assertIsNone(advice.problem)
            self.assertEqual((advice.calls, advice.spent, advice.per_call),
                             (1, Decimal(1), Decimal(1)))
            self.assertEqual(advice.rewarm, Decimal("0.125"))     # 100k tokens at $1.25 per M
            self.assertGreater(advice.worst, Decimal("0.002"))    # 1000 output tokens at $2 per M, and input
            expected = recovery.round_up_to_cent(
                Decimal(1) + advice.rewarm + 40 * Decimal(1) + advice.worst)
            self.assertEqual(advice.suggested, expected)
            self.assertEqual(advice.suggested, advice.suggested.quantize(Decimal("0.01")))
            self.assertGreater(advice.suggested, advice.spent + advice.worst)
            self.assertIn("40 calls at $1", advice.arithmetic())
            # unpriced: nothing is estimated
            (state / "prices.toml").write_text("# none\n")
            blind = recovery.advise(state, SID, conversation, None, None)
            self.assertEqual((blind.spent, blind.worst, blind.suggested), (None, None, None))
            self.assertIn("no price row", blind.problem)
            self.assertEqual(blind.calls, 1)

    def test_round_up_to_cent_and_the_floor(self):
        from decimal import Decimal
        self.assertEqual(recovery.round_up_to_cent(Decimal("1.001")), Decimal("1.01"))
        self.assertEqual(recovery.round_up_to_cent(Decimal("1.01")), Decimal("1.01"))


class TheDocsAndTheTable(unittest.TestCase):
    """Outcomes 1, 9 and 10: the rule where the operator reads it."""

    def table(self):
        from tests.test_run import the_table
        return the_table()

    def test_three_descriptions_name_twine_resume(self):
        moves = self.table().moves
        for name in ("fix-adapter", "stop-at-cap", "respawn-from-request"):
            self.assertIn("`twine resume", moves[name].description, name)
            self.assertIn("2026-10-15-twine-run-recovery-003", moves[name].grounds, name)
        self.assertNotIn("runs the session again", moves["fix-adapter"].description)
        self.assertIn("kept", moves["respawn-from-request"].description)
        self.assertIn("last resort", moves["respawn-from-request"].description)

    def test_the_readme_names_the_verb_and_the_sixteen_keys(self):
        from twine import REPO_ROOT
        text = " ".join((REPO_ROOT / "README.md").read_text(encoding="utf-8").split())
        for needle in ("twine resume", "sixteen keys", "four `loop_keys`", "--plan"):
            self.assertTrue(needle in text, f"the README does not say {needle!r}")
        self.assertEqual((REPO_ROOT / "VERSION").read_text().strip(), "0.26.0")


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

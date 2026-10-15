"""The Anthropic adapter (Arc 2 R2): twine/runtime/adapters/anthropic.py
held to the fifteen wire recordings of 2026-10-13 (fixtures/anthropic/,
landed from the architect's probe `twine-anthropic-record` by
bin/twine-land-provider-recordings) — and, for what could not be recorded,
to doubles built from those recordings' bytes, each named as one.

No test here reaches a network or reads a key (T8): the transport is the
recorded bytes, and the key is a sentinel the tests invent and then look
for everywhere the adapter writes. The one test that talks to the API is
tests/test_anthropic_live.py, gated, run by hand.

Sections:
  1. The recordings and their helpers
  2. stop_key and error_key
  3. build_request, and the round trip the recordings prove
  4. read_response on every JSON recording
  5. read_stream on every stream, whole and split at every byte
  6. Doubles: what could not be recorded
  7. The key
  8. The adapter, and through the boundary
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import hashlib
import inspect
import io
import json
import logging
import re
import tempfile
import unittest
from pathlib import Path

from twine import FIXTURES_DIR, REPO_ROOT, TRANSITIONS_TABLE, transitions
from twine.runtime.adapters import anthropic as A
from twine.runtime.adapters.anthropic import (AnthropicAdapter, AnthropicConfigError,
                                              ConversationEdited, Outcome, RequestShapeError,
                                              UnreadableUsage, build_request, error_key,
                                              read_response, read_stream, stop_key)
from twine.runtime.boundary import Boundary, BoundaryError, Request, Turn
from twine.runtime.registry import load_runtime_registry
from twine.runtime.terms import ToolCall, ToolSpec
from twine.spend import Tokens

PROVIDER_DIR = FIXTURES_DIR / "anthropic"
PASTE = PROVIDER_DIR / "carried" / "twine-anthropic-record-2026-10-13.txt"

# The brief's §3 table, verbatim: (request sha256 or None, response bytes,
# response sha256). The paste's: 29,039 bytes LF; received CRLF as 29,240.
BRIEF = {
    "models": (None, 14233, "d744304435f479b8350556098dbf9cc5c3a4d94814351dfdcc073623d4afce13"),
    "text": ("f874bb9125f432e6a5aa5ebd4964125d6792872d100c919fc775e1c10828f1a1", 527,
             "b9330f4527da18c36006c76905134be6ead1bd61980a17d02dcf117c823c11a3"),
    "text_stream": ("7364a117e4583cff95db45733fc2a7ac9fec66e9b9355f66cfb8ec61a7b14467", 1258,
                    "ff21be177393814ab673b742cb0ea22ad80d22f9ee6ac68d84c681a49fd141b5"),
    "max_tokens": ("4a8c485ec97d5179a2a481ed4cdc4f3e1b5e3da0c7db11bdde1b6c8160c35029", 536,
                   "258f687adf36abbd828b39bc886ab360f1677fbb957eb378f0ec3f28e7de25fd"),
    "max_tokens_stream": ("3b828585dec98edf6c557a8f72ca8f0736339de31aca71e6753ab5c6cd15e5e0",
                          1266,
                          "5b74e39103d928b54390010db3f80b5643fc19326987d4861be9d1a213b659bc"),
    "tool_use": ("e35be61c7d9347e59825ddb4267a5f4cd7bf213272ae4f48dd20d201cf0f1a36", 631,
                 "712d0ac17cd9439f426b00300a68e8c8eef10834c7fecbc1607c09b8830e89ee"),
    "tool_use_stream": ("45665e3e977936e29f4e51e9e5a2a6efc7ee559eba3d757b1aa4939107b0a5bd",
                        1795,
                        "9a0ee0617a853e634650710792baef74c067e0566ee666b1e1cf5cd945d396d7"),
    "tool_result": ("d5d067e11a7eee68deb08a87242adbbdd59b9ba58e346a82fe1def0deff0d8a0", 552,
                    "3090a163575dedb1158041ef1507946ee8777f8e9e141996bf2ddc4515905785"),
    "tool_result_error": ("ebc86720085f5a219382d1a1c56d49c609376b8c1e0b6bc48488245433ae7e21",
                          642,
                          "248e6b96cd39b32725d7de3dad99cd737ba120382b2901edbc0463efc0eb5137"),
    "thinking_stream": ("1b46a648951e2c91bdb2d3cde8f00e3c6381a2f647f56cdfeba9c31ed4a02606",
                        2566,
                        "2c159fc05ba61367ab9c0f52346a7d75787783bc22f5c25d35e1af27bb831988"),
    "cache_write": ("eef65b5ead7166b24c483142a365762133a3d5c551d7c1e4af355f73cbf1a6d0", 530,
                    "b857ef93e7081d52231d0d7e2bd51b9d715d0aa25a35d3deb5d306a904469f51"),
    "cache_read": ("9b0521f6aea591eb5436d770cfcf0329bc92807a74ac9167d60c5bb9b8fbe460", 527,
                   "ad4dafd70c4656126f0d2416e880ecef05add216f508e718615e6d0e883b7ff0"),
    "error_401": ("088074b66073201ecd0f9b33719bbe75d12a7e902cd4a7f63a5968ccae7ed15f", 130,
                  "822bfc574d1a7489ef21c556d4dcd30c4aaa7ab4be7b00d275a1fbd74800b661"),
    "error_404_model": ("cce91afb6514cbc46fcb0b44dcd346dd8f4422a951b331ae7d455835d2acf801", 133,
                        "ed007a184db21677ff8ee6621308461008e960182b70f75313e48ef9cf3bf174"),
    "error_400": ("2050f12e5179384323c5c6304369a047c9e4b9932002b706a3c89b7876f1a5c3", 138,
                  "5c8bd802a47e72312fddd1dd662e8258e30edeb0dd3d7d630d07bfbf71313dc7"),
}
PASTE_BYTES, PASTE_SHA = 29039, "4d1bfd63ef6746546c13962aad08f3ee726e4d81284b69cb21ea4a1bbd5da92d"
PASTE_CRLF_BYTES, PASTE_CRLF_SHA_PREFIX = 29240, "41e8fe66"

JSON_MESSAGES = ("text", "max_tokens", "tool_use", "tool_result", "tool_result_error",
                 "cache_write", "cache_read")
REFUSALS = ("error_401", "error_404_model", "error_400")
STREAMS = ("text_stream", "max_tokens_stream", "tool_use_stream", "thinking_stream")

# A key no provider issued: what the tests hand the adapter and then look
# for in everything it writes.
SENTINEL = "sk-ant-twine-test-sentinel-7f3a9c2e5b"
ENV = {A.KEY_VARIABLE: SENTINEL}


# ---------------------------------------------------------------------------
# 1. The recordings and their helpers
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Rec:
    """One landed recording: its meta, the request it sent (or None) and the
    response bytes."""

    name: str
    meta: dict
    request: bytes | None
    response: bytes

    @property
    def status(self) -> int:
        return self.meta["status"]

    @property
    def headers(self) -> dict:
        return dict(self.meta["headers"])

    @property
    def request_json(self) -> dict:
        return json.loads(self.request)

    @property
    def sse(self) -> bool:
        return self.meta["response_file"].endswith(".sse")


def rec(name: str) -> Rec:
    meta = json.loads((PROVIDER_DIR / f"{name}.meta.json").read_bytes())
    request = (FIXTURES_DIR / meta["request_file"]).read_bytes() if meta["request_file"] else None
    return Rec(name, meta, request, (FIXTURES_DIR / meta["response_file"]).read_bytes())


def read(r: Rec, *, split: int | None = None, **kwargs) -> Outcome:
    """A recording through the reader its content type picks; a stream in
    chunks of `split` bytes (every byte when 1), else whole."""
    if r.sse:
        body = r.response
        size = split or len(body)
        return read_stream(r.status, r.headers,
                           [body[i:i + size] for i in range(0, len(body), size)], **kwargs)
    return read_response(r.status, r.headers, r.response, **kwargs)


class RecordedTransport:
    """The tests' transport: answers each call with the next (status,
    headers, body) it was given, the body in chunks of `split` bytes, and
    records every call. Raises an exception instead when one is queued."""

    def __init__(self, *answers, split: int | None = None) -> None:
        self.answers = list(answers)
        self.split = split
        self.calls: list[tuple[str, str, dict, bytes | None]] = []

    @classmethod
    def of(cls, *names: str, split: int | None = None) -> "RecordedTransport":
        return cls(*[(r.status, r.headers, r.response) for r in map(rec, names)], split=split)

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        status, headers, data = answer
        if callable(data):
            return status, headers, data()
        size = self.split or max(len(data), 1)
        return status, headers, [data[i:i + size] for i in range(0, len(data), size)]

    def sent(self, n: int = -1) -> dict:
        return json.loads(self.calls[n][3])


def adapter(*names: str, split: int | None = None, **settings) -> AnthropicAdapter:
    return AnthropicAdapter(env=ENV, transport=RecordedTransport.of(*names, split=split),
                            **settings)


READ_FILE = {"name": "read_file",
             "description": "Read a UTF-8 text file in the working directory and return its "
                            "contents.",
             "input_schema": {"type": "object", "properties": {"path": {
                 "type": "string",
                 "description": "the file's path, relative to the working directory"}},
                 "required": ["path"]}}


class TheRecordings(unittest.TestCase):
    """The fifteen landed byte-exact (the brief's §3 hashes), each what its
    meta file says, and no key anywhere in them."""

    def test_fifteen_recordings_and_the_paste_by_sha256(self):
        self.assertEqual(sorted(p.name.split(".")[0] for p in PROVIDER_DIR.glob("*.meta.json")),
                         sorted(BRIEF))
        for name, (request_sha, size, response_sha) in BRIEF.items():
            with self.subTest(recording=name):
                r = rec(name)
                self.assertEqual((len(r.response), hashlib.sha256(r.response).hexdigest()),
                                 (size, response_sha))
                self.assertEqual(None if r.request is None
                                 else hashlib.sha256(r.request).hexdigest(), request_sha)
                self.assertEqual(r.meta["response_sha256"], response_sha)
                self.assertEqual(r.meta["request_sha256"], request_sha)
                self.assertEqual(r.meta["recorded_at"], "2026-10-13T00:43:12Z")
        data = PASTE.read_bytes()
        self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (PASTE_BYTES, PASTE_SHA))
        crlf = data.replace(b"\n", b"\r\n")
        self.assertEqual(len(crlf), PASTE_CRLF_BYTES)
        self.assertTrue(hashlib.sha256(crlf).hexdigest().startswith(PASTE_CRLF_SHA_PREFIX))

    def test_each_meta_has_the_pinned_keys(self):
        for name in BRIEF:
            with self.subTest(recording=name):
                meta = rec(name).meta
                for key in ("method", "path", "status", "headers", "request_sha256",
                            "response_sha256", "recorded_at"):
                    self.assertIn(key, meta)
                raw = (PROVIDER_DIR / f"{name}.meta.json").read_bytes()
                self.assertEqual(raw.count(b"\n"), 1)
                self.assertTrue(raw.endswith(b"\n"))

    def test_the_bodies_are_json_and_the_streams_sse(self):
        for name in BRIEF:
            with self.subTest(recording=name):
                r = rec(name)
                if r.request is not None:
                    self.assertIsInstance(r.request_json, dict)
                if r.sse:
                    self.assertTrue(r.headers["content-type"].startswith("text/event-stream"))
                    self.assertTrue(r.response.startswith(b"event: message_start\n"))
                else:
                    self.assertEqual(r.headers["content-type"], "application/json")
                    self.assertIsInstance(json.loads(r.response), dict)

    def test_no_key_is_in_any_recording(self):
        """The probe printed `key: set (environment)`; the bogus key of the
        401 rode in a header the probe never printed."""
        for path in sorted(PROVIDER_DIR.rglob("*")):
            if path.is_file():
                with self.subTest(file=path.name):
                    data = path.read_bytes()
                    self.assertNotIn(b"sk-ant-", data)
                    self.assertNotIn(b"x-api-key:", data.lower())
        self.assertIn(b"key: set (environment)", PASTE.read_bytes())

    def test_the_models_recording_says_what_the_brief_says(self):
        models = {m["id"]: m for m in json.loads(rec("models").response)["data"]}
        types = models["claude-haiku-5-5"]["capabilities"]["thinking"]["types"]
        self.assertEqual({k: v["supported"] for k, v in types.items()},
                         {"enabled": False, "adaptive": True, "disabled": True})
        for model in ("claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"):
            self.assertFalse(models[model]["capabilities"]["thinking"]["types"]["disabled"]
                             ["supported"], model)
        self.assertGreater(models["claude-haiku-5-5"]["max_tokens"], A.DEFAULT_MAX_TOKENS)


# ---------------------------------------------------------------------------
# 2. stop_key and error_key
# ---------------------------------------------------------------------------


class StopAndErrorKeys(unittest.TestCase):
    """Total over the table's rows, refusing nothing silently — and each the
    table's word, never spelled in the adapter (test_runtime holds that)."""

    def test_stop_key_over_every_stop_reason_row(self):
        mapping = transitions.provider_mapping("anthropic")
        words = mapping.words("stop_reason")
        self.assertEqual(set(words), {"end_turn", "tool_use", "max_tokens", "refusal",
                                      "model_context_window_exceeded", "stop_sequence",
                                      "pause_turn"})
        for word in words:
            with self.subTest(word=word):
                self.assertEqual(stop_key(word), mapping.get("stop_reason", word).stop)
        self.assertIsNone(stop_key("tool_use"))
        self.assertEqual((stop_key("end_turn"), stop_key("max_tokens"), stop_key("refusal")),
                         ("end-turn", "max-tokens", "model-refusal"))

    def test_an_unlisted_or_absent_stop_reason_is_malformed_shape(self):
        for word in ("compaction", "", "END_TURN", None, 7):
            with self.subTest(word=word):
                self.assertEqual(stop_key(word), "malformed-shape")

    def test_error_key_over_every_status_and_error_type_row(self):
        mapping = transitions.provider_mapping("anthropic")
        for word in mapping.words("status"):
            with self.subTest(status=word):
                self.assertEqual(error_key(int(word), None, None),
                                 mapping.get("status", word).stop)
        for word in mapping.words("error_type"):
            with self.subTest(error_type=word):
                self.assertEqual(error_key(None, word, None),
                                 mapping.get("error_type", word).stop)
                self.assertEqual(error_key(200, word, None),
                                 mapping.get("error_type", word).stop)

    def test_the_brief_s_rows(self):
        for status in (400, 401, 402, 403, 404, 409, 413):
            self.assertEqual(error_key(status, None, None), "request-refused")
        self.assertEqual(error_key(429, "rate_limit_error", None), "rate-limited")
        self.assertEqual(error_key(529, "overloaded_error", None), "overloaded")
        self.assertEqual(error_key(500, "api_error", None), "provider-error")
        self.assertEqual(error_key(504, "timeout_error", None), "timeout")
        self.assertEqual(error_key(None, None, TimeoutError("read timed out")), "timeout")
        self.assertEqual(error_key(None, None, ConnectionResetError("reset")),
                         "network-failure")
        self.assertEqual(error_key(None, None, OSError("unreachable")), "network-failure")

    def test_the_status_decides_an_http_error_never_its_type(self):
        """An HTTP error's error.type is kept in the reason, never dispatched
        on; an unlisted status is malformed-shape, never a nearer guess."""
        self.assertEqual(error_key(529, "invalid_request_error", None), "overloaded")
        for status in (418, 502, 503, 301, 201):
            with self.subTest(status=status):
                self.assertEqual(error_key(status, "overloaded_error", None),
                                 "malformed-shape")

    def test_an_unlisted_stream_error_type_is_network_failure(self):
        self.assertEqual(error_key(None, "gremlin_error", None), "network-failure")
        self.assertEqual(error_key(200, "gremlin_error", None), "network-failure")

    def test_nothing_to_classify_refuses_loudly(self):
        for args in ((None, None, None), (200, None, None)):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    error_key(*args)
        with self.assertRaises(TypeError):
            error_key("429", None, None)

    def test_a_table_the_mapping_cannot_stand_on_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = TRANSITIONS_TABLE.read_text(encoding="utf-8")
            body = text.replace('word = "529"\nstop = "overloaded"', 'word = "529"\nstop = "killed"')
            self.assertNotEqual(body, text)
            path = Path(tmp) / "t.toml"
            path.write_text(body, encoding="utf-8")
            with self.assertRaises(transitions.TableError) as caught:
                error_key(529, None, None, table=path)
            self.assertIn("loop key", str(caught.exception))
            with self.assertRaises(transitions.TableError):
                stop_key("end_turn", table=path)


# ---------------------------------------------------------------------------
# 3. build_request, and the round trip the recordings prove
# ---------------------------------------------------------------------------


def built(**overrides) -> dict:
    kwargs = dict(model="claude-haiku-5-5", max_tokens=64,
                  system="You are a worker in a test harness. Answer tersely.",
                  messages=[{"role": "user", "content": "hi"}], tools=[READ_FILE],
                  thinking={"type": "adaptive"})
    kwargs.update(overrides)
    return build_request(**kwargs)


def breakpoints(obj) -> int:
    """How many cache_control markers a body carries, anywhere."""
    if isinstance(obj, dict):
        return (1 if "cache_control" in obj else 0) + sum(breakpoints(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(breakpoints(v) for v in obj)
    return 0


class BuildRequest(unittest.TestCase):

    def test_the_shape(self):
        body = built()
        self.assertEqual(set(body), {"model", "max_tokens", "system", "tools", "thinking",
                                     "messages", "stream"})
        self.assertEqual(body["system"], [{"type": "text", "text": "You are a worker in a "
                                           "test harness. Answer tersely.",
                                           "cache_control": {"type": "ephemeral"}}])
        self.assertEqual(body["thinking"], {"type": "adaptive"})
        self.assertIs(body["stream"], True)
        self.assertEqual((body["model"], body["max_tokens"]), ("claude-haiku-5-5", 64))

    def test_three_breakpoints_system_last_tool_last_block(self):
        second = dict(READ_FILE, name="list_dir")
        body = built(tools=[READ_FILE, second],
                     messages=[{"role": "user", "content": "a"},
                               {"role": "assistant", "content": [{"type": "text", "text": "b"}]},
                               {"role": "user", "content": [{"type": "text", "text": "c"},
                                                            {"type": "text", "text": "d"}]}])
        self.assertEqual(breakpoints(body), 3)
        self.assertNotIn("cache_control", body["tools"][0])
        self.assertEqual(body["tools"][1]["cache_control"], {"type": "ephemeral"})
        last = body["messages"][-1]["content"]
        self.assertEqual(last[-1]["cache_control"], {"type": "ephemeral"})
        self.assertNotIn("cache_control", last[0])
        self.assertEqual(body["messages"][0], {"role": "user", "content": "a"})

    def test_a_string_last_message_becomes_one_marked_text_block(self):
        body = built(messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(body["messages"], [{"role": "user", "content": [
            {"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}]}])

    def test_what_is_absent_is_absent(self):
        body = built(system=None, tools=[], thinking=None, stream=False)
        self.assertEqual(set(body), {"model", "max_tokens", "messages", "stream"})
        self.assertIs(body["stream"], False)
        self.assertEqual(breakpoints(body), 1)

    def test_never_the_knobs_twine_does_not_turn(self):
        for kwargs in ({}, {"thinking": None}, {"stream": False}):
            body = built(**kwargs)
            for key in ("stop_sequences", "temperature", "top_p", "top_k", "metadata",
                        "tool_choice"):
                self.assertNotIn(key, body)

    def test_thinking_passes_as_given(self):
        for thinking in ({"type": "adaptive"}, {"type": "enabled", "budget_tokens": 1024},
                         {"type": "disabled"}):
            with self.subTest(thinking=thinking):
                self.assertEqual(built(thinking=thinking)["thinking"], thinking)

    def test_pure(self):
        messages = [{"role": "user", "content": [{"type": "text", "text": "x"}]}]
        tools = [copy.deepcopy(READ_FILE)]
        thinking = {"type": "adaptive"}
        before = copy.deepcopy((messages, tools, thinking))
        built(messages=messages, tools=tools, thinking=thinking)
        self.assertEqual((messages, tools, thinking), before)

    def test_pinned_keyword_only_and_unknown_keywords_refuse(self):
        params = inspect.signature(build_request).parameters
        self.assertEqual(list(params), ["model", "max_tokens", "system", "messages", "tools",
                                        "thinking", "stream"])
        self.assertTrue(all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params.values()))
        self.assertIs(params["stream"].default, True)
        with self.assertRaises(TypeError):
            built(temperature=0.5)
        with self.assertRaises(TypeError):
            build_request("claude-haiku-5-5", 64, None, [], [], None)  # type: ignore[misc]

    def test_a_part_of_the_wrong_shape_refuses(self):
        for overrides in ({"model": ""}, {"max_tokens": 0}, {"max_tokens": True},
                          {"system": ""}, {"messages": "hi"}, {"messages": [{"role": "user"}]},
                          {"tools": [dict(READ_FILE, cache_control={"type": "ephemeral"})]},
                          {"tools": [{"type": "web_search_20250305", "name": "web"}]},
                          {"thinking": "adaptive"}, {"stream": "yes"}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(RequestShapeError):
                    built(**overrides)

    def test_the_cache_recordings_system_block_is_what_the_builder_makes(self):
        """cache_write's request put cache_control on the system block — the
        first breakpoint, as build_request writes it."""
        sent = rec("cache_write").request_json
        body = build_request(model=sent["model"], max_tokens=sent["max_tokens"],
                             system=sent["system"][0]["text"], messages=sent["messages"],
                             tools=[], thinking=None, stream=False)
        self.assertEqual(body["system"], sent["system"])
        # cache_read sent the same prefix (system and its breakpoint) with
        # another question: the prefix is what the cache keyed on.
        self.assertEqual(rec("cache_read").request_json["system"], sent["system"])
        self.assertEqual(read(rec("cache_write")).usage, Tokens(18, 3, 0, 0, 2556))
        self.assertEqual(read(rec("cache_read")).usage, Tokens(18, 3, 0, 2556, 0))

    def test_the_round_trip_the_tool_result_recordings_prove(self):
        """The tool_result request is the round trip: the tool_use request's
        messages, the parsed turn's content carried back verbatim (`caller`
        and all), and the result. The conversation helpers reproduce its
        messages exactly — with is_error for tool_result_error — and the
        builder sends them with the one breakpoint added."""
        first = rec("tool_use").request_json
        outcome = read(rec("tool_use"))
        for name, result in (("tool_result", ("twine is the process layer.\n", False)),
                             ("tool_result_error", ("read_file: notes.txt: no such file",
                                                    True))):
            with self.subTest(recording=name):
                want = rec(name).request_json
                conversation = A.Conversation()
                for message in first["messages"]:
                    conversation.user(message["content"])
                conversation.assistant(outcome)
                conversation.tool_results([(outcome.tool_calls[0].id, *result)])
                self.assertEqual(list(conversation.messages), want["messages"])
                body = build_request(model=want["model"], max_tokens=want["max_tokens"],
                                     system=want["system"], messages=want["messages"],
                                     tools=want["tools"], thinking=None, stream=False)
                marked = copy.deepcopy(want["messages"])
                marked[-1]["content"][-1]["cache_control"] = {"type": "ephemeral"}
                self.assertEqual(body["messages"], marked)
                self.assertEqual(body["messages"][1], want["messages"][1])
                self.assertIn("caller", body["messages"][1]["content"][0])


# ---------------------------------------------------------------------------
# 4. read_response on every JSON recording
# ---------------------------------------------------------------------------

PINNED_KEYS = {"stop", "reason", "text", "tool_calls", "thinking", "content", "usage",
               "retry_after", "request_id", "raw_stop_reason"}


class ReadResponse(unittest.TestCase):

    def test_every_json_message(self):
        want = {
            "text": ("end-turn", "twine", Tokens(37, 4, 0, 0, 0)),
            "max_tokens": ("max-tokens", "Rope is made", Tokens(37, 5, 0, 0, 0)),
            "tool_use": (None, "", Tokens(437, 51, 0, 0, 0)),
            "tool_result": ("end-turn", 'The first word is "twine".', Tokens(502, 10, 0, 0, 0)),
            "tool_result_error": ("end-turn", None, Tokens(512, 39, 0, 0, 0)),
            "cache_write": ("end-turn", "49", Tokens(18, 3, 0, 0, 2556)),
            "cache_read": ("end-turn", "81", Tokens(18, 3, 0, 2556, 0)),
        }
        for name in JSON_MESSAGES:
            with self.subTest(recording=name):
                r = rec(name)
                o = read(r)
                stop, text, usage = want[name]
                self.assertEqual(o.stop, stop)
                if text is not None:
                    self.assertEqual(o.text, text)
                self.assertEqual(o.usage, usage)
                self.assertEqual(o.request_id, r.headers["request-id"])
                self.assertEqual(o.raw_stop_reason, json.loads(r.response)["stop_reason"])
                self.assertIsNone(o.retry_after)
                self.assertEqual(o.content, tuple(json.loads(r.response)["content"]))
                self.assertLessEqual(PINNED_KEYS, set(o.as_json()))
        self.assertIn("doesn't exist", read(rec("tool_result_error")).text)

    def test_the_tool_call(self):
        o = read(rec("tool_use"))
        self.assertEqual(o.as_json()["tool_calls"], [{"id": "toolu_01FRmgqdpXibQfEW3UHF2DVn",
                                                      "name": "read_file",
                                                      "arguments": {"path": "notes.txt"}}])
        self.assertIsNone(o.reason)
        self.assertEqual(o.content[0]["caller"], {"type": "direct"})

    def test_reason_only_when_the_stop_is_not_the_ordinary_end(self):
        self.assertIsNone(read(rec("text")).reason)
        reason = read(rec("max_tokens")).reason
        self.assertIn("max_tokens", reason)

    def test_the_three_refusals(self):
        said = {"error_401": ("authentication_error", "invalid x-api-key", 401),
                "error_404_model": ("not_found_error", "model: no-such-model-2026", 404),
                "error_400": ("invalid_request_error", "messages: Field required", 400)}
        for name in REFUSALS:
            with self.subTest(recording=name):
                r = rec(name)
                o = read(r)
                etype, message, status = said[name]
                self.assertEqual(o.stop, "request-refused")
                self.assertIn(f'{etype}: "{message}"', o.reason)
                self.assertIsNone(o.usage)
                self.assertEqual(o.as_json()["usage"], None)
                self.assertEqual((o.raw_stop_reason, o.status), (etype, status))
                self.assertEqual(o.request_id, r.headers["request-id"])
                self.assertEqual((o.text, o.tool_calls, o.content), ("", (), ()))

    def test_as_json_is_json(self):
        for name in JSON_MESSAGES + REFUSALS + STREAMS:
            with self.subTest(recording=name):
                obj = read(rec(name)).as_json()
                self.assertEqual(json.loads(json.dumps(obj)), obj)


# ---------------------------------------------------------------------------
# 5. read_stream on every stream, whole and split at every byte
# ---------------------------------------------------------------------------


class ReadStream(unittest.TestCase):

    def test_every_stream_whole_and_split_at_every_byte(self):
        for name in STREAMS:
            r = rec(name)
            whole = read(r).as_json()
            for split in (1, 2, 3, 7, 64, 333):
                with self.subTest(recording=name, split=split):
                    self.assertEqual(read(r, split=split).as_json(), whole)

    def test_streamed_equals_unstreamed(self):
        """The streaming contract: the finished turn is the unstreamed one's
        (same text, stop, usage) — the recordings are two calls, so ids
        differ, and the cases below are the ones the model answered alike."""
        for streamed, plain in (("text_stream", "text"), ("max_tokens_stream", "max_tokens")):
            with self.subTest(stream=streamed):
                a, b = read(rec(streamed)), read(rec(plain))
                self.assertEqual((a.stop, a.text, a.usage), (b.stop, b.text, b.usage))
                self.assertEqual([dict(c) for c in a.content], [dict(c) for c in b.content])

    def test_the_tool_use_stream_assembles_its_arguments_from_four_pieces(self):
        r = rec("tool_use_stream")
        pieces = [json.loads(line[len("data: "):])["delta"]["partial_json"]
                  for line in r.response.decode().splitlines()
                  if "input_json_delta" in line]
        self.assertEqual(pieces, ["", '{"path"', ': "note', 's.txt"}'])
        o = read(r, split=1)
        self.assertIsNone(o.stop)
        self.assertEqual(o.as_json()["tool_calls"], [{"id": "toolu_01KQPVZ2fcGYsWmkAujZaLHK",
                                                      "name": "read_file",
                                                      "arguments": {"path": "notes.txt"}}])
        self.assertEqual(o.content[0]["input"], {"path": "notes.txt"})
        self.assertEqual(o.content[0]["caller"], {"type": "direct"})
        self.assertEqual(o.usage, Tokens(437, 51, 0, 0, 0))

    def test_the_thinking_stream(self):
        o = read(rec("thinking_stream"), split=1)
        self.assertEqual(o.stop, "end-turn")
        self.assertEqual(o.text, "391")
        self.assertEqual(len(o.thinking), 1)
        self.assertEqual(o.thinking[0]["thinking"], "")
        self.assertTrue(o.thinking[0]["signature"].startswith("CAQS7gQK"))
        self.assertEqual([b["type"] for b in o.content], ["thinking", "text"])
        self.assertEqual(o.content[0], {"type": "thinking", "thinking": "",
                                        "signature": o.thinking[0]["signature"]})
        # output 33 less thinking 30: message_delta's usage, cumulative, final
        self.assertEqual(o.usage, Tokens(49, 3, 30, 0, 0))

    def test_the_padded_data_lines(self):
        """The recordings pad the event data with spaces inside it (before
        the closing brace: `{"type":"message_stop"        }`): a reader that
        compares strings instead of parsing JSON fails here."""
        for name in STREAMS:
            with self.subTest(recording=name):
                body = rec(name).response.decode()
                padded = [line for line in body.splitlines()
                          if line.startswith("data: ") and re.search(r"\S {2,}\}$", line)]
                self.assertGreater(len(padded), 3)
                self.assertNotIn('data: {"type":"message_stop"}', body)
                self.assertIn(read(rec(name)).stop, ("end-turn", "max-tokens", None))

    def test_ping_and_an_unknown_event_are_ignored(self):
        """A double: text_stream with an event type twine does not know
        added after its ping."""
        body = rec("text_stream").response
        self.assertIn(b"event: ping\n", body)
        double = body.replace(b'data: {"type": "ping"}\n\n', b'data: {"type": "ping"}\n\n'
                              b'event: telemetry_hint\ndata: {"type":"telemetry_hint",'
                              b'"hint":"x"}\n\n', 1)
        self.assertNotEqual(double, body)
        whole = read(rec("text_stream")).as_json()
        self.assertEqual(read_stream(200, rec("text_stream").headers, [double]).as_json(), whole)
        no_ping = body.replace(b'event: ping\ndata: {"type": "ping"}\n\n', b"")
        self.assertEqual(read_stream(200, {}, [no_ping]).as_json()["text"], "twine")

    def test_crlf_line_ends_are_read_alike(self):
        body = rec("text_stream").response.replace(b"\n", b"\r\n")
        self.assertEqual(read_stream(200, {}, [body[i:i + 5] for i in range(0, len(body), 5)])
                         .as_json()["text"], "twine")

    def test_the_observer_sees_the_deltas_and_cannot_fail_the_call(self):
        seen = []
        o = read(rec("thinking_stream"), split=1, observer=lambda k, t: seen.append((k, t)))
        self.assertEqual(seen, [("text", "391")])   # the thinking delta was empty
        def broken(kind, text):
            raise RuntimeError("the shell went away")
        with self.assertLogs("twine.runtime.adapters.anthropic", level="WARNING") as logs:
            o2 = read(rec("text_stream"), observer=broken)
        self.assertEqual((o2.stop, o2.text), ("end-turn", "twine"))
        self.assertIn("observer failed", "\n".join(logs.output))
        self.assertEqual(o.stop, "end-turn")


# ---------------------------------------------------------------------------
# 6. Doubles: what could not be recorded
# ---------------------------------------------------------------------------


def error_double(status: int, etype: str, message: str, **headers: str):
    """An HTTP error built from error_401's bytes: its object, with the
    type and message replaced — a double, named as one."""
    r = rec("error_401")
    obj = json.loads(r.response)
    obj["error"] = {"type": etype, "message": message}
    hdrs = dict(r.headers)
    hdrs.update({k.replace("_", "-"): v for k, v in headers.items()})
    return status, hdrs, json.dumps(obj, separators=(",", ":")).encode()


def message_double(source: str, old: bytes, new: bytes) -> tuple[int, dict, bytes]:
    """A recording's bytes with one edit — a double, named as one."""
    r = rec(source)
    assert old in r.response, (source, old)
    return r.status, r.headers, r.response.replace(old, new, 1)


def stream_cut_before(name: str, marker: bytes) -> tuple[int, dict, bytes]:
    r = rec(name)
    return r.status, r.headers, r.response[:r.response.index(marker)]


class Doubles(unittest.TestCase):

    def outcome(self, double) -> Outcome:
        status, headers, body = double
        if headers.get("content-type", "").startswith("text/event-stream"):
            return read_stream(status, headers, [body[i:i + 1] for i in range(len(body))])
        return read_response(status, headers, body)

    def test_429_with_and_without_retry_after(self):
        o = self.outcome(error_double(429, "rate_limit_error", "Number of requests exceeded",
                                      retry_after="17"))
        self.assertEqual((o.stop, o.retry_after, o.usage), ("rate-limited", 17, None))
        self.assertIn('rate_limit_error: "Number of requests exceeded"', o.reason)
        self.assertEqual(o.as_json()["retry_after"], 17)
        o = self.outcome(error_double(429, "rate_limit_error", "slow down"))
        self.assertEqual((o.stop, o.retry_after), ("rate-limited", None))
        o = self.outcome(error_double(429, "rate_limit_error", "x", retry_after="2.5"))
        self.assertEqual(o.retry_after, 2.5)
        o = self.outcome(error_double(429, "rate_limit_error", "x",
                                      retry_after="Wed, 21 Oct 2026 07:28:00 GMT"))
        self.assertIsNone(o.retry_after)
        self.assertIn("retry-after", o.reason)

    def test_500_504_529(self):
        for status, etype, key in ((500, "api_error", "provider-error"),
                                   (504, "timeout_error", "timeout"),
                                   (529, "overloaded_error", "overloaded")):
            with self.subTest(status=status):
                o = self.outcome(error_double(status, etype, "Internal server error"))
                self.assertEqual((o.stop, o.raw_stop_reason, o.usage), (key, etype, None))
                self.assertIn(etype, o.reason)

    def test_an_error_body_that_is_not_json_is_still_its_status(self):
        o = read_response(529, {"content-type": "text/html"}, b"<html>overloaded</html>")
        self.assertEqual((o.stop, o.raw_stop_reason), ("overloaded", None))
        self.assertIn("not an error object", o.reason)

    def test_an_unlisted_status_is_malformed_shape_naming_it(self):
        o = self.outcome(error_double(418, "invalid_request_error", "teapot"))
        self.assertEqual(o.stop, "malformed-shape")
        self.assertIn("418", o.reason)

    def test_an_sse_error_event_carrying_overloaded_error(self):
        r = rec("text_stream")
        cut = r.response.index(b"event: content_block_delta")
        body = (r.response[:cut] + b'event: error\ndata: {"type":"error","error":'
                b'{"type":"overloaded_error","message":"Overloaded"}  }\n\n')
        o = self.outcome((200, r.headers, body))
        self.assertEqual((o.stop, o.raw_stop_reason, o.usage), ("overloaded", "overloaded_error",
                                                                None))
        self.assertIn('overloaded_error: "Overloaded"', o.reason)
        self.assertEqual((o.text, o.content), ("", ()))
        for etype, key in (("api_error", "provider-error"), ("rate_limit_error", "rate-limited"),
                           ("invalid_request_error", "request-refused"),
                           ("gremlin_error", "network-failure")):
            with self.subTest(error_type=etype):
                b2 = body.replace(b"overloaded_error", etype.encode())
                self.assertEqual(self.outcome((200, r.headers, b2)).stop, key)

    def test_a_stream_cut_before_message_stop(self):
        o = self.outcome(stream_cut_before("text_stream", b"event: message_stop"))
        self.assertEqual(o.stop, "network-failure")
        self.assertIn("without message_stop", o.reason)
        # the usage reported so far is kept: message_delta's had arrived
        self.assertEqual(o.usage, Tokens(37, 4, 0, 0, 0))
        o = self.outcome(stream_cut_before("text_stream", b"event: content_block_start"))
        self.assertEqual((o.stop, o.usage), ("network-failure", Tokens(37, 4, None, 0, 0)))
        o = self.outcome((200, rec("text_stream").headers, b""))
        self.assertEqual((o.stop, o.usage), ("network-failure", None))

    def test_a_stream_cut_mid_line(self):
        """The desk's ruling on the HOLD of 2026-10-13: an unterminated
        trailing `data:` line is where the connection was cut, not an event.
        Byte 754 of text_stream cuts inside the content_block_delta's data —
        network-failure, naming the three complete events (message_start,
        content_block_start, ping), never malformed-shape."""
        r = rec("text_stream")
        cut = r.response[:754]
        last_event = cut[cut.rindex(b"\n\n") + 2:]
        self.assertTrue(last_event.startswith(b"event: content_block_delta\ndata: {"))
        self.assertNotIn(b"\n\n", last_event)
        for split in (None, 1, 7):
            with self.subTest(split=split):
                size = split or len(cut)
                o = read_stream(200, r.headers, [cut[i:i + size]
                                                 for i in range(0, len(cut), size)])
                self.assertEqual(o.stop, "network-failure", o.reason)
                self.assertIn("after 3 complete events without message_stop", o.reason)
                self.assertIn("unterminated", o.reason)
                self.assertEqual(o.raw_stop_reason, None)
                self.assertEqual(o.usage, Tokens(37, 4, None, 0, 0))
                self.assertEqual((o.text, o.content), ("", ()))

    def test_every_cut_short_of_a_terminated_message_stop_is_network_failure(self):
        """Clean cuts and mid-line cuts alike, at every byte of every stream:
        until the blank line after message_stop has arrived, the stream did
        not end — so every proper prefix is network-failure, and only the
        whole recording reads as its stop."""
        for name in STREAMS:
            r = rec(name)
            whole = read(r).stop
            self.assertNotEqual(whole, "network-failure")
            stops = {read_stream(200, r.headers, [r.response[:k]]).stop
                     for k in range(len(r.response))}
            with self.subTest(recording=name):
                self.assertEqual(stops, {"network-failure"})

    def test_a_cut_inside_a_utf_8_character_is_a_cut(self):
        """A double: text_stream's delta text with a two-byte character in
        it, cut between its two bytes — undecodable, and not judged."""
        r = rec("text_stream")
        body = r.response.replace(b'"text":"twine"', '"text":"twéine"'.encode("utf-8"), 1)
        at = body.index("é".encode("utf-8")) + 1     # between the character's two bytes
        self.assertRaises(UnicodeDecodeError, body[:at].decode, "utf-8")
        o = read_stream(200, r.headers, [body[:at]])
        self.assertEqual(o.stop, "network-failure", o.reason)
        self.assertEqual(read_stream(200, r.headers, [body]).text, "twéine")

    def test_a_malformed_event_is_judged_only_if_the_stream_ended(self):
        """malformed-shape is for a terminated event in a stream that ended;
        the same bad event in a stream that was then cut is a cut."""
        r = rec("text_stream")
        bad = r.response.replace(b'data: {"type":"content_block_stop"',
                                 b'data: {type:content_block_stop', 1)
        self.assertNotEqual(bad, r.response)
        self.assertEqual(read_stream(200, r.headers, [bad]).stop, "malformed-shape")
        cut = read_stream(200, r.headers, [bad[:bad.index(b"event: message_stop")]])
        self.assertEqual(cut.stop, "network-failure")
        self.assertIn("could not be placed", cut.reason)
        # a terminated message_stop whose data is fine but whose blank line
        # never came: the stream did not end
        self.assertEqual(read_stream(200, r.headers, [r.response[:-1]]).stop,
                         "network-failure")

    def test_pause_turn_and_stop_sequence(self):
        for word in (b"pause_turn", b"stop_sequence"):
            with self.subTest(stop_reason=word):
                o = self.outcome(message_double("text", b'"stop_reason":"end_turn"',
                                                b'"stop_reason":"' + word + b'"'))
                self.assertEqual((o.stop, o.raw_stop_reason), ("malformed-shape", word.decode()))
                self.assertIn(word.decode(), o.reason)

    def test_refusal_and_the_window(self):
        o = self.outcome(message_double("text", b'"stop_reason":"end_turn","stop_sequence":null,'
                                        b'"stop_details":null',
                                        b'"stop_reason":"refusal","stop_sequence":null,'
                                        b'"stop_details":{"type":"refusal","category":"x"}'))
        self.assertEqual(o.stop, "model-refusal")
        self.assertIn('"category": "x"', o.reason)
        o = self.outcome(message_double("text", b'"stop_reason":"end_turn"',
                                        b'"stop_reason":"model_context_window_exceeded"'))
        self.assertEqual(o.stop, "window-exhausted")
        o = self.outcome(message_double("text", b'"stop_reason":"end_turn"',
                                        b'"stop_reason":"compaction"'))
        self.assertEqual(o.stop, "malformed-shape")
        self.assertIn("'compaction' has no mapping row", o.reason)

    def test_a_non_json_200(self):
        o = read_response(200, {"content-type": "application/json"}, b"<html>hi</html>")
        self.assertEqual(o.stop, "malformed-shape")
        self.assertIn("not JSON", o.reason)

    def test_an_unknown_block_type(self):
        o = self.outcome(message_double("text", b'{"type":"text","text":"twine"}',
                                        b'{"type":"citation_card","text":"twine"}'))
        self.assertEqual(o.stop, "malformed-shape")
        self.assertIn("citation_card", o.reason)
        self.assertEqual(o.usage, Tokens(37, 4, 0, 0, 0))   # readable, so kept
        r = rec("text_stream")
        body = r.response.replace(b'"content_block":{"type":"text","text":""}',
                                  b'"content_block":{"type":"citation_card","text":""}', 1)
        self.assertNotEqual(body, r.response)
        self.assertEqual(read_stream(200, r.headers, [body]).stop, "malformed-shape")

    def test_a_message_without_its_parts(self):
        for key in (b'"usage":', b'"content":', b'"stop_reason":'):
            with self.subTest(missing=key):
                r = rec("text")
                obj = json.loads(r.response)
                del obj[key.decode().strip('":')]
                o = read_response(200, r.headers, json.dumps(obj).encode())
                self.assertEqual(o.stop, "malformed-shape")

    def test_a_usage_from_anthropic_refuses(self):
        o = self.outcome(message_double("text", b'"input_tokens":37', b'"input_tokens":-1'))
        self.assertEqual((o.stop, o.usage), ("malformed-shape", None))
        self.assertIn("input_tokens", o.usage_fault)
        with self.assertRaises(UnreadableUsage):
            o.to_turn()

    def test_the_two_shapes_a_turn_cannot_have(self):
        o = self.outcome(message_double("text", b'"stop_reason":"end_turn"',
                                        b'"stop_reason":"tool_use"'))
        self.assertEqual(o.stop, "malformed-shape")
        self.assertIn("no tool_use block", o.reason)
        o = self.outcome(message_double("tool_use", b'"stop_reason":"tool_use"',
                                        b'"stop_reason":"end_turn"'))
        self.assertEqual(o.stop, "malformed-shape")
        o = self.outcome(message_double("tool_use", b'"stop_reason":"tool_use"',
                                        b'"stop_reason":"max_tokens"'))
        self.assertEqual(o.stop, "max-tokens")
        self.assertEqual(o.to_turn().tool_calls, ())   # a stopped turn asks for nothing

    def test_streams_that_cannot_be_placed(self):
        r = rec("text_stream")
        cases = {
            "no message_delta": r.response.replace(
                r.response[r.response.index(b"event: message_delta"):
                           r.response.index(b"event: message_stop")], b""),
            "not utf-8": r.response.replace(b'"text":"twine"', b'"text":"tw\xffine"'),
            "data not json": r.response.replace(b'data: {"type":"content_block_stop"',
                                                b'data: {type:content_block_stop', 1),
            "delta before start": r.response.replace(
                r.response[r.response.index(b"event: message_start"):
                           r.response.index(b"event: content_block_start")], b""),
            "a delta for no block": r.response.replace(b'"index":0,"delta"', b'"index":5,"delta"'),
            "a delta of an unknown type": r.response.replace(b'"text_delta"', b'"citations_delta"'),
        }
        for name, body in cases.items():
            with self.subTest(case=name):
                self.assertNotEqual(body, r.response)
                o = read_stream(200, r.headers, [body[i:i + 3] for i in range(0, len(body), 3)])
                self.assertEqual(o.stop, "malformed-shape", o.reason)

    def test_transport_exceptions(self):
        timeout = A._failure(A._context(None, None, TRANSITIONS_TABLE), TimeoutError("timed out"),
                             "before any answer")
        self.assertEqual((timeout.stop, timeout.raw_stop_reason), ("timeout", "TimeoutError"))
        r = rec("text_stream")

        def cut_mid_stream():
            yield r.response[:r.response.index(b"event: content_block_start")]
            raise TimeoutError("The read operation timed out")
        o = read_stream(200, r.headers, cut_mid_stream())
        self.assertEqual((o.stop, o.raw_stop_reason), ("timeout", "TimeoutError"))
        self.assertIn("after 1 complete events", o.reason)

        def reset():
            yield r.response[:10]
            raise ConnectionResetError("reset by peer")
        o = read_stream(200, r.headers, reset())
        self.assertEqual((o.stop, o.raw_stop_reason), ("network-failure", "ConnectionResetError"))

    def test_a_reader_fault_is_not_called_a_transport_failure(self):
        """Only an exception the transport raises while a chunk is drawn is
        classified; a fault of the reader's own propagates."""
        with self.assertRaises(TypeError):
            read_stream(200, {}, [object()])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# 7. The key
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 6b. The ceiling inside a block (twine-run-ergonomics, finding 2)
# ---------------------------------------------------------------------------
#
# The stream that ended at the output ceiling with a block open is not
# recorded (the architect's, by probe). Every specimen below is DERIVED, not
# recorded: max_tokens_stream's bytes with its last content_block_stop
# removed, and streams assembled from that recording's own head and tail.

MAX_TOKENS_TAIL_MARKER = b"event: message_delta"


def sse(name: str, data: dict) -> bytes:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()


def derived_open_text() -> tuple[int, dict, bytes]:
    """DERIVED specimen: max_tokens_stream with its last (only)
    content_block_stop removed: block 0 is open at message_stop."""
    r = rec("max_tokens_stream")
    start = r.response.index(b"event: content_block_stop")
    end = r.response.index(MAX_TOKENS_TAIL_MARKER)
    return r.status, r.headers, r.response[:start] + r.response[end:]


def derived_ceiling(blocks: bytes, stop_reason: str = "max_tokens") -> tuple[int, dict, bytes]:
    """DERIVED specimen: max_tokens_stream's message_start and its message_delta
    and message_stop around `blocks` (events written here), the stop_reason
    replaced when asked."""
    r = rec("max_tokens_stream")
    head = r.response[:r.response.index(b"event: content_block_start")]
    tail = r.response[r.response.index(MAX_TOKENS_TAIL_MARKER):]
    tail = tail.replace(b'"stop_reason":"max_tokens"', f'"stop_reason":"{stop_reason}"'.encode())
    return r.status, r.headers, head + blocks + tail


def block_start(index: int, block: dict) -> bytes:
    return sse("content_block_start", {"type": "content_block_start", "index": index,
                                       "content_block": block})


def block_delta(index: int, delta: dict) -> bytes:
    return sse("content_block_delta", {"type": "content_block_delta", "index": index,
                                       "delta": delta})


def block_stop(index: int) -> bytes:
    return sse("content_block_stop", {"type": "content_block_stop", "index": index})


def tool_block(index: int, *pieces: str, stop: bool = False) -> bytes:
    body = block_start(index, {"type": "tool_use", "id": f"toolu_cut{index}",
                               "name": "write_file", "input": {}})
    for piece in pieces:
        body += block_delta(index, {"type": "input_json_delta", "partial_json": piece})
    return body + (block_stop(index) if stop else b"")


def text_block(index: int, text: str, *, stop: bool = True) -> bytes:
    return (block_start(index, {"type": "text", "text": ""})
            + block_delta(index, {"type": "text_delta", "text": text})
            + (block_stop(index) if stop else b""))


class TheCeilingInsideABlock(unittest.TestCase):

    def read(self, double, **kw) -> Outcome:
        status, headers, body = double
        return read_stream(status, headers, [body[i:i + 11] for i in range(0, len(body), 11)],
                           **kw)

    def test_the_derived_specimen_is_the_recording_with_its_last_stop_removed(self):
        recorded = rec("max_tokens_stream").response
        _, _, derived = derived_open_text()
        self.assertEqual(recorded.count(b"event: content_block_stop"), 1)
        self.assertNotIn(b"content_block_stop", derived)
        self.assertEqual(len(recorded) - len(derived),
                         len(recorded[recorded.index(b"event: content_block_stop"):
                                      recorded.index(MAX_TOKENS_TAIL_MARKER)]))

    def test_an_open_text_block_at_max_tokens_is_a_max_tokens_turn(self):
        o = self.read(derived_open_text())
        whole = read(rec("max_tokens_stream"))
        self.assertEqual(o.stop, "max-tokens")
        self.assertEqual(o.stop, whole.stop)
        self.assertEqual(o.raw_stop_reason, "max_tokens")
        self.assertFalse(o.malformed)
        self.assertIsNone(o.raw)
        self.assertIsNone(o.cut_tool_call)
        # carried as far as it got: the same text the closed stream has
        self.assertEqual([dict(b) for b in o.content], [dict(b) for b in whole.content])
        self.assertEqual((o.text, o.usage), (whole.text, whole.usage))
        turn = o.to_turn()
        self.assertEqual((turn.stop, turn.text, turn.tool_calls), ("max-tokens", "Rope is made",
                                                                  ()))

    def test_with_any_other_stop_reason_an_open_block_is_still_malformed(self):
        for stop_reason in ("end_turn", "tool_use", "stop_sequence", "refusal"):
            with self.subTest(stop_reason=stop_reason):
                double = derived_ceiling(text_block(0, "half", stop=False), stop_reason)
                o = self.read(double)
                self.assertEqual(o.stop, "malformed-shape")
                self.assertTrue(o.malformed)
                self.assertIn("message_stop with block(s) [0] still open", o.reason)
        o = self.read(derived_ceiling(text_block(0, "half", stop=False), "max_tokens"))
        self.assertEqual(o.stop, "max-tokens")

    def test_an_open_tool_use_block_whose_input_does_not_parse_is_not_carried(self):
        pieces = ('{"path": "big.txt", ', '"content": "the first of many lines')
        double = derived_ceiling(text_block(0, "Writing it.") + tool_block(1, *pieces))
        o = self.read(double)
        self.assertEqual(o.stop, "max-tokens")
        self.assertEqual([b["type"] for b in o.content], ["text"])
        self.assertEqual(o.tool_calls, ())
        self.assertEqual(o.cut_tool_call, {"id": "toolu_cut1", "name": "write_file",
                                           "partial_json": "".join(pieces)})
        self.assertIn("'write_file' tool_use block whose input was not complete", o.reason)
        turn = o.to_turn()
        self.assertEqual((turn.stop, turn.tool_calls), ("max-tokens", ()))
        self.assertEqual(dict(turn.cut_tool_call), o.cut_tool_call)
        self.assertEqual(turn.content, o.content)
        for split in (1, 5):
            status, headers, body = double
            again = read_stream(status, headers, [body[i:i + split]
                                                  for i in range(0, len(body), split)])
            self.assertEqual((again.content, again.cut_tool_call), (o.content, o.cut_tool_call))

    def test_a_tool_use_block_that_opened_and_wrote_nothing_is_not_carried_either(self):
        o = self.read(derived_ceiling(tool_block(0)))
        self.assertEqual((o.stop, o.content), ("max-tokens", ()))
        self.assertEqual(o.cut_tool_call, {"id": "toolu_cut0", "name": "write_file",
                                           "partial_json": ""})

    def test_closed_tool_use_blocks_stay_and_an_open_one_whose_input_parses_is_carried(self):
        closed = tool_block(0, '{"path": "a.txt", "content": "A"}', stop=True)
        done = tool_block(1, '{"path": "b.txt", ', '"content": "B"}')   # no stop: it parsed
        o = self.read(derived_ceiling(closed + done))
        self.assertEqual(o.stop, "max-tokens")
        self.assertEqual([b["input"]["path"] for b in o.content], ["a.txt", "b.txt"])
        self.assertIsNone(o.cut_tool_call)
        # the turn asks for no tools (it was cut): the loop answers both "not run"
        self.assertEqual(o.to_turn().tool_calls, ())

    def test_an_open_thinking_block_is_carried_as_far_as_it_got(self):
        thinking = (block_start(0, {"type": "thinking", "thinking": "", "signature": ""})
                    + block_delta(0, {"type": "thinking_delta", "thinking": "Let me see"}))
        o = self.read(derived_ceiling(thinking))
        self.assertEqual(o.stop, "max-tokens")
        self.assertEqual([b["type"] for b in o.content], ["thinking"])
        self.assertEqual(o.content[0]["thinking"], "Let me see")
        self.assertEqual(o.to_turn().thinking, "Let me see")

    def test_a_malformed_stream_that_is_not_a_ceiling_keeps_its_reason(self):
        o = self.read(message_double("max_tokens_stream", b'{"type":"message_delta"',
                                     b'{"type":"nonsense_delta"'))
        self.assertEqual(o.stop, "malformed-shape")
        self.assertIn("without a message_delta", o.reason)


class TheRawBody(unittest.TestCase):
    """The response body, kept for a call that ends malformed-shape — and for
    no other (twine-run-ergonomics, finding 2). The adapter hands it over on
    the Outcome and the Turn; the loop writes it (tests/test_run.py)."""

    def call(self, double, *, split: int = 7) -> Turn:
        status, headers, body = double
        transport = RecordedTransport((status, headers, body), split=split)
        a = AnthropicAdapter(env=ENV, transport=transport)
        return a.call(Request(({"role": "user", "content": "x"},)))

    def test_a_stream_that_ends_malformed_keeps_every_byte_it_drew(self):
        double = message_double("text_stream", b'{"type":"message_delta"',
                                b'{"type":"nonsense_delta"')
        # the reader keeps drawing after a fault, to the end of the stream
        turn = self.call(double, split=5)
        self.assertEqual(turn.stop, "malformed-shape")
        self.assertEqual(turn.raw, double[2])

    def test_the_open_block_at_another_stop_keeps_the_stream(self):
        double = derived_ceiling(text_block(0, "half", stop=False), "end_turn")
        turn = self.call(double)
        self.assertEqual((turn.stop, turn.raw), ("malformed-shape", double[2]))

    def test_a_json_body_that_is_not_a_message_keeps_the_body(self):
        r = rec("text")
        body = b'{"type": "message", "content": "not a list"}'
        turn = self.call((200, r.headers, body))
        self.assertEqual((turn.stop, turn.raw), ("malformed-shape", body))

    def test_a_200_of_an_unknown_content_type_keeps_the_body(self):
        turn = self.call((200, {"content-type": "text/html"}, b"<html>hi</html>"))
        self.assertEqual((turn.stop, turn.raw), ("malformed-shape", b"<html>hi</html>"))

    def test_nothing_is_kept_for_any_other_outcome(self):
        for name in ("text", "text_stream", "tool_use_stream", "max_tokens_stream",
                     "thinking_stream", "error_401", "error_400", "error_404_model"):
            with self.subTest(recording=name):
                r = rec(name)
                turn = self.call((r.status, r.headers, r.response))
                self.assertIsNone(turn.raw)
                self.assertIsNone(turn.cut_tool_call)
        turn = self.call(derived_open_text())
        self.assertEqual((turn.stop, turn.raw), ("max-tokens", None))
        status, headers, body = error_double(529, "overloaded_error", "busy")
        self.assertIsNone(self.call((status, headers, body)).raw)

    def test_a_transport_that_fails_mid_stream_keeps_nothing(self):
        def broken():
            yield b"event: message_start\n"
            raise ConnectionResetError("reset")
        transport = RecordedTransport((200, rec("text_stream").headers, broken))
        turn = AnthropicAdapter(env=ENV, transport=transport).call(
            Request(({"role": "user", "content": "x"},)))
        self.assertEqual(turn.stop, "network-failure")
        self.assertIsNone(turn.raw)

    def test_the_outcome_json_is_unchanged(self):
        """The pinned as_json() gains no key: the raw body and the cut call
        ride beside it."""
        o = read(rec("text"))
        self.assertEqual(set(o.as_json()), {
            "stop", "reason", "text", "tool_calls", "thinking", "content", "usage",
            "retry_after", "request_id", "raw_stop_reason", "status", "usage_fault"})
        self.assertEqual(set(o.to_turn().as_json()), {
            "text", "thinking", "tool_calls", "stop", "usage", "provider_stop", "content",
            "retry_after", "request_id", "reason"})


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record) + repr(record.args))


class TheKey(unittest.TestCase):

    def test_construction_refuses_without_it(self):
        for env in ({}, {A.KEY_VARIABLE: ""}, {A.KEY_VARIABLE: "   "},
                    {"ANTHROPIC_KEY": SENTINEL}):
            with self.subTest(env=sorted(env)):
                with self.assertRaises(AnthropicConfigError) as caught:
                    AnthropicAdapter(env=env, transport=RecordedTransport())
                self.assertIn(A.KEY_VARIABLE, str(caught.exception))
        with self.assertRaises(AnthropicConfigError):
            AnthropicAdapter(env=None, transport=RecordedTransport())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            AnthropicAdapter(ENV, RecordedTransport())  # type: ignore[misc]

    def test_the_key_is_read_from_the_mapping_given_never_the_process(self):
        source = (REPO_ROOT / "twine/runtime/adapters/anthropic.py").read_text(encoding="utf-8")
        self.assertNotRegex(source, r"\bos\.environ\b|\bgetenv\b|^import os|^from os ")

    def test_it_goes_into_x_api_key_and_nowhere_else(self):
        handler = _Capture()
        twine_log = logging.getLogger("twine")
        old_level = twine_log.level
        twine_log.addHandler(handler)
        twine_log.setLevel(logging.DEBUG)
        self.addCleanup(twine_log.removeHandler, handler)
        self.addCleanup(twine_log.setLevel, old_level)
        stderr = io.StringIO()
        written: list[str] = []
        with contextlib.redirect_stderr(stderr):
            transport = RecordedTransport.of(*JSON_MESSAGES, *REFUSALS, *STREAMS, split=3)
            a = AnthropicAdapter(env=ENV, transport=transport)
            for _ in range(len(JSON_MESSAGES + REFUSALS + STREAMS)):
                o = a.call(build_request(model="claude-haiku-5-5", max_tokens=32, system=None,
                                         messages=[{"role": "user", "content": "hi"}], tools=[],
                                         thinking=None))
                written.append(json.dumps(o.as_json()))
                try:
                    written.append(json.dumps(o.to_turn().as_json()))
                except Exception as exc:
                    written.append(str(exc))
            # Through the boundary, and a turn the boundary refuses.
            b = Boundary(AnthropicAdapter(env=ENV, transport=RecordedTransport.of(
                "thinking_stream"), thinking=None))
            with self.assertRaises(BoundaryError) as caught:
                b.call(Request(({"role": "user", "content": "x"},)))
            written.append(str(caught.exception))
            for bad in ({}, {A.KEY_VARIABLE: ""}):
                try:
                    AnthropicAdapter(env=bad, transport=transport)
                except AnthropicConfigError as exc:
                    written.append(str(exc))
            written.append(repr(a))
            written.append(str(vars(a).get("settings")))
        for method, url, headers, body in transport.calls:
            self.assertEqual((method, url), ("POST", "https://api.anthropic.com/v1/messages"))
            self.assertEqual(headers, {"x-api-key": SENTINEL, "anthropic-version": "2023-06-01",
                                       "content-type": "application/json"})
            self.assertNotIn(SENTINEL.encode(), body)
        self.assertEqual(len(transport.calls), 14)
        self.assertGreater(len(handler.records), 14)
        for where, texts in (("output", written), ("log", handler.records),
                             ("stderr", [stderr.getvalue()])):
            for text in texts:
                with self.subTest(where=where):
                    self.assertNotIn(SENTINEL, text)

    def test_a_reason_that_would_carry_it_is_scrubbed(self):
        """Should a transport's exception quote the key, the reason does not."""
        transport = RecordedTransport(ConnectionError(f"proxy refused key {SENTINEL}"))
        o = AnthropicAdapter(env=ENV, transport=transport).call(
            built(messages=[{"role": "user", "content": "x"}]))
        self.assertEqual(o.stop, "network-failure")
        self.assertNotIn(SENTINEL, json.dumps(o.as_json()))
        self.assertIn(f"[{A.KEY_VARIABLE}]", o.reason)

    def test_no_fixture_or_test_carries_a_key(self):
        """The sentinel is the tests' invention; no real key is anywhere."""
        for path in sorted((REPO_ROOT / "tests").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertFalse(re.search(r"sk-ant-api\d\d-", text), path.name)


# ---------------------------------------------------------------------------
# 8. The adapter, and through the boundary
# ---------------------------------------------------------------------------


class TheAdapter(unittest.TestCase):

    def test_registered_and_implementing_five(self):
        self.assertEqual(AnthropicAdapter.name, "anthropic")
        self.assertEqual(AnthropicAdapter.implements,
                         frozenset({"tool-calling", "thinking", "usage-accounting",
                                    "prompt-caching", "streaming"}))
        self.assertEqual(AnthropicAdapter.tool_protocol, "native")
        registry = load_runtime_registry()
        self.assertTrue(registry.ok, [p.message for p in registry.problems])
        self.assertIn("anthropic", [a.name for a in registry.adapters])

    def test_constructible_with_env_and_transport_alone(self):
        a = AnthropicAdapter(env=ENV, transport=RecordedTransport())
        self.assertEqual(a.settings.model, "claude-haiku-5-5")
        self.assertEqual(a.settings.max_tokens, A.DEFAULT_MAX_TOKENS)
        self.assertEqual(a.thinking_param, {"type": "adaptive"})
        self.assertTrue(a.settings.thinking.adaptive)
        self.assertTrue(a.stream)
        self.assertIsNone(a.system)

    def test_call_with_a_body_returns_its_outcome(self):
        transport = RecordedTransport.of("text")
        a = AnthropicAdapter(env=ENV, transport=transport)
        body = rec("text").request_json
        o = a.call(body)
        self.assertIsInstance(o, Outcome)
        self.assertEqual((o.stop, o.text), ("end-turn", "twine"))
        self.assertEqual(transport.sent(), body)

    def test_the_content_type_picks_the_reader(self):
        r = rec("text_stream")
        o = AnthropicAdapter(env=ENV, transport=RecordedTransport.of("text_stream", split=1)
                             ).call({"model": "m"})
        self.assertEqual((o.stop, o.text), ("end-turn", "twine"))
        weird = (200, {"content-type": "text/html; charset=utf-8"}, b"<html></html>")
        o = AnthropicAdapter(env=ENV, transport=RecordedTransport(weird)).call({"model": "m"})
        self.assertEqual(o.stop, "malformed-shape")
        self.assertIn("text/html", o.reason)
        self.assertIsNotNone(r)

    def test_a_transport_that_cannot_talk_is_an_outcome(self):
        for exc, key in ((TimeoutError("timed out"), "timeout"),
                         (ConnectionRefusedError("refused"), "network-failure")):
            with self.subTest(exc=type(exc).__name__):
                o = AnthropicAdapter(env=ENV, transport=RecordedTransport(exc)).call({"m": 1})
                self.assertEqual((o.stop, o.status, o.raw_stop_reason),
                                 (key, None, type(exc).__name__))
                self.assertEqual(o.to_turn().usage, Tokens(0, 0, None, 0, 0))

    def test_the_tool_exchange_through_the_boundary(self):
        """tool_use then tool_result, recorded, through the boundary: the
        first turn asks for read_file, the loop appends the assistant's
        blocks and the result, the second ends the turn."""
        transport = RecordedTransport.of("tool_use", "tool_result")
        first_request = rec("tool_use").request_json
        a = AnthropicAdapter(env=ENV, transport=transport, max_tokens=256,
                             system=first_request["system"], thinking=None, stream=False)
        b = Boundary(a)
        spec = ToolSpec(READ_FILE["name"], READ_FILE["description"], READ_FILE["input_schema"])
        conversation = A.Conversation(first_request["messages"][0]["content"])
        first = b.call(Request(conversation.messages, (spec,)))
        self.assertTrue(first.continues)
        self.assertEqual(first.tool_calls, (ToolCall("toolu_01FRmgqdpXibQfEW3UHF2DVn",
                                                     "read_file", {"path": "notes.txt"}),))
        self.assertEqual(first.usage, Tokens(437, 51, 0, 0, 0))
        self.assertEqual(first.request_id, "req_011CfyJtUQkgdsUcQzvdZ8mk")
        self.assertEqual(first.provider_stop, "tool_use")
        sent = transport.sent(0)
        self.assertEqual(sent["tools"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(sent["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertNotIn("thinking", sent)
        conversation.assistant(first)
        conversation.tool_results([(first.tool_calls[0].id, "twine is the process layer.\n",
                                    False)])
        second = b.call(Request(conversation.messages, (spec,)))
        self.assertEqual((second.stop, second.text), ("end-turn", 'The first word is "twine".'))
        self.assertIn(second.stop, transitions.stop_keys())
        sent = transport.sent(1)
        want = rec("tool_result").request_json["messages"]
        self.assertEqual(sent["messages"][:2], want[:2])
        self.assertEqual(sent["messages"][2]["content"][0]["tool_use_id"],
                         want[2]["content"][0]["tool_use_id"])
        self.assertEqual(b.calls, 2)

    def test_a_stream_with_thinking_through_the_boundary(self):
        b = Boundary(adapter("thinking_stream", split=1))
        turn = b.call(Request(({"role": "user", "content": "What is 17 * 23?"},)))
        self.assertEqual((turn.stop, turn.text, turn.thinking), ("end-turn", "391", ""))
        self.assertEqual(turn.usage, Tokens(49, 3, 30, 0, 0))
        self.assertEqual(turn.content[0]["type"], "thinking")

    def test_thinking_off_refuses_a_turn_that_thought(self):
        """Decision 2: a thinking block counts as thinking even when its
        text is empty — a session spawned with thinking off is refused one."""
        b = Boundary(adapter("thinking_stream", thinking=None))
        self.assertFalse(b.settings.thinking.enabled)
        with self.assertRaises(BoundaryError) as caught:
            b.call(Request(({"role": "user", "content": "x"},)))
        self.assertIn("thinking off", str(caught.exception))

    def test_a_refusal_through_the_boundary(self):
        b = Boundary(adapter("error_401"))
        turn = b.call(Request(({"role": "user", "content": "hi"},)))
        self.assertEqual(turn.stop, "request-refused")
        self.assertEqual(turn.usage, Tokens(0, 0, None, 0, 0))
        self.assertIn('authentication_error: "invalid x-api-key"', turn.reason)
        self.assertEqual(turn.provider_stop, "authentication_error")

    def test_every_recording_through_the_boundary(self):
        for name in JSON_MESSAGES + REFUSALS + STREAMS:
            with self.subTest(recording=name):
                b = Boundary(adapter(name, split=2))
                turn = b.call(Request(({"role": "user", "content": "x"},)))
                self.assertIsInstance(turn, Turn)

    def test_the_conversation_is_append_only(self):
        a = adapter("text", "text")
        a.call(Request(({"role": "user", "content": "one"},)))
        with self.assertRaises(ConversationEdited):
            a.call(Request(({"role": "user", "content": "edited"},)))

    def test_the_spawn_time_constants(self):
        a = adapter("text", model="claude-sonnet-5-5", max_tokens=100,
                    thinking={"type": "enabled", "budget_tokens": 50}, system="be brief",
                    stream=False)
        a.call(Request(({"role": "user", "content": "x"},)))
        sent = a._transport.sent()
        self.assertEqual((sent["model"], sent["max_tokens"], sent["thinking"], sent["stream"]),
                         ("claude-sonnet-5-5", 100, {"type": "enabled", "budget_tokens": 50},
                          False))
        self.assertEqual(list(inspect.signature(AnthropicAdapter.call).parameters),
                         ["self", "body"])
        names = {n for n, _ in inspect.getmembers(AnthropicAdapter, callable)
                 if not n.startswith("_")}
        self.assertFalse({n for n in names if n.startswith("set")}, names)
        with self.assertRaises(AttributeError):
            a.settings = None  # type: ignore[misc]

    def test_settings_that_refuse(self):
        for settings in ({"thinking": {"type": "sometimes"}}, {"thinking": "adaptive"},
                         {"thinking": {"type": "enabled"}},
                         {"thinking": {"type": "enabled", "budget_tokens": 20000}},
                         {"max_tokens": 0}, {"model": ""}, {"system": ""}, {"stream": 1}):
            with self.subTest(settings=settings):
                with self.assertRaises(AnthropicConfigError):
                    AnthropicAdapter(env=ENV, transport=RecordedTransport(), **settings)
        off = AnthropicAdapter(env=ENV, transport=RecordedTransport(),
                               thinking={"type": "disabled"})
        self.assertFalse(off.settings.thinking.enabled)
        self.assertEqual(off.thinking_param, {"type": "disabled"})

    def test_a_mapping_onto_a_loop_key_refuses_the_adapter(self):
        """R1 §1.5's defect, removed: a table whose Anthropic mapping lands on
        a loop key is refused before the adapter exists (and a turn
        stopping with one is refused at the boundary: test_runtime)."""
        with tempfile.TemporaryDirectory() as tmp:
            text = TRANSITIONS_TABLE.read_text(encoding="utf-8")
            body = text.replace('word = "end_turn"\nstop = "end-turn"',
                                'word = "end_turn"\nstop = "cap-reached"')
            self.assertNotEqual(body, text)
            path = Path(tmp) / "t.toml"
            path.write_text(body, encoding="utf-8")
            with self.assertRaises(AnthropicConfigError) as caught:
                AnthropicAdapter(env=ENV, transport=RecordedTransport(), table=path)
            self.assertIn("loop key", str(caught.exception))

    def test_the_adapter_module_spells_no_stop_key(self):
        """Its words come from the table (the R1 test walks every runtime
        module; this one names the adapter's file outright)."""
        import ast
        keys = set(transitions.stop_keys())
        tree = ast.parse((REPO_ROOT / "twine/runtime/adapters/anthropic.py")
                         .read_text(encoding="utf-8"))
        spelled = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                   and n.value in keys}
        self.assertEqual(spelled, set())


class TheRealTransport(unittest.TestCase):
    """twine/runtime/transport.py without a socket: what can be held
    offline (the live smoke test holds the rest, by hand)."""

    def test_it_speaks_https_only_and_opens_nothing_otherwise(self):
        from twine.runtime.transport import https_transport
        transport = https_transport(timeout=1.0)
        for url in ("http://api.anthropic.com/v1/messages", "file:///etc/passwd",
                    "https:///v1/messages"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    transport("POST", url, {}, b"{}")

    def test_headers_are_lowercased_and_a_repeat_is_joined(self):
        from twine.runtime import transport as T

        class Response:
            def getheaders(self):
                return [("Content-Type", "text/event-stream"), ("Request-Id", "req_1"),
                        ("Via", "a"), ("via", "b")]
        self.assertEqual(T._headers(Response()), {"content-type": "text/event-stream",
                                                  "request-id": "req_1", "via": "a, b"})

    def test_the_body_arrives_as_read_and_the_connection_closes(self):
        from twine.runtime import transport as T
        body = rec("text_stream").response
        closed = []

        class Response:
            def __init__(self):
                self.left = body

            def read1(self, n):
                piece, self.left = self.left[:min(n, 100)], self.left[min(n, 100):]
                return piece

        class Connection:
            def close(self):
                closed.append(True)
        chunks = list(T._chunks(Connection(), Response(), 65536))
        self.assertEqual(b"".join(chunks), body)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(closed, [True])
        self.assertEqual(read_stream(200, {}, chunks).text, "twine")
        # a reader that stops early still closes it
        gen = T._chunks(Connection(), Response(), 65536)
        next(gen)
        gen.close()
        self.assertEqual(closed, [True, True])

    def test_transport_error_is_a_connection_error(self):
        from twine.runtime.transport import TransportError
        self.assertTrue(issubclass(TransportError, ConnectionError))
        self.assertEqual(error_key(None, None, TransportError("bad status line")),
                         "network-failure")


class TheContextWindow(unittest.TestCase):
    """Arc 2 R5: the adapter states its model's window at spawn from one
    `GET /v1/models`, held to the 2026-10-13 recording (`models`): its
    entries' `max_input_tokens` — 1000000 for every 5.x model, 200000 for
    claude-opus-4-5-20251101. What the recording cannot show (a model not
    listed, a failure, an HTTP error, more pages) is a double built from its
    bytes or a sibling recording's, named as such."""

    MODELS = rec("models")

    def adapter(self, *answers, model="claude-haiku-5-5"):
        transport = RecordedTransport(*answers)
        return AnthropicAdapter(env=ENV, transport=transport, model=model), transport

    def test_held_to_the_recording(self):
        listed = {m["id"]: m["max_input_tokens"]
                  for m in json.loads(self.MODELS.response)["data"]}
        self.assertEqual(listed["claude-opus-4-5-20251101"], 200000)
        for model in ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5",
                      "claude-fable-5-1", "claude-opus-4-5-20251101"):
            with self.subTest(model=model):
                a, transport = self.adapter((self.MODELS.status, self.MODELS.headers,
                                             self.MODELS.response), model=model)
                statement = a.context_window()
                self.assertEqual((statement.size, statement.reason), (listed[model], None))
                self.assertEqual(transport.calls, [
                    ("GET", "https://api.anthropic.com/v1/models",
                     {"x-api-key": SENTINEL, "anthropic-version": "2023-06-01"}, None)])
                self.assertEqual(self.MODELS.meta["method"], "GET")
                self.assertEqual(self.MODELS.meta["path"], "/v1/models")
        self.assertEqual(listed["claude-opus-5-5"], 1000000)

    def test_one_call_per_spawn(self):
        a, transport = self.adapter((self.MODELS.status, self.MODELS.headers,
                                     self.MODELS.response))
        first, second = a.context_window(), a.context_window()
        self.assertEqual(first, second)
        self.assertEqual((len(transport.calls), a.window_calls), (1, 1))
        self.assertEqual(a.calls, 0, "no Messages call was made")

    def test_a_model_not_listed_is_unknown_and_says_so(self):
        a, _ = self.adapter((200, self.MODELS.headers, self.MODELS.response),
                            model="claude-not-a-model")
        statement = a.context_window()
        self.assertIsNone(statement.size)
        self.assertIn("'claude-not-a-model' is not among the 14 model(s)", statement.reason)
        # A double: the recording's page with has_more set — twine reads one page.
        page = json.loads(self.MODELS.response)
        page["has_more"] = True
        b, _ = self.adapter((200, self.MODELS.headers, json.dumps(page).encode()),
                            model="claude-not-a-model")
        self.assertIn("more pages, which twine does not read", b.context_window().reason)

    def test_failures_are_unknown_never_a_raise(self):
        error_401 = rec("error_401")   # the Messages recording's error body: same shape
        cases = {
            "transport": (ConnectionRefusedError(f"refused, key {SENTINEL}"),
                          "failed before an answer (ConnectionRefusedError"),
            "http error": ((401, error_401.headers, error_401.response),
                           "answered HTTP 401 (authentication_error:"),
            "not json": ((200, {"content-type": "application/json"}, b"<html>"),
                         "not JSON"),
            "not the listing": ((200, {"content-type": "application/json"}, b'{"x": 1}'),
                                "without a `data` list"),
            "another type": ((200, {"content-type": "text/html"}, b"{}"),
                             "content-type is 'text/html'"),
            "no count": ((200, {"content-type": "application/json"},
                          b'{"data": [{"id": "claude-haiku-5-5"}]}'),
                         "without a positive integer max_input_tokens"),
        }
        for name, (answer, needle) in cases.items():
            with self.subTest(case=name):
                a, _ = self.adapter(answer)
                statement = a.context_window()
                self.assertIsNone(statement.size)
                self.assertIn(needle, statement.reason)
                self.assertNotIn(SENTINEL, statement.reason)

    def test_the_verb_asks_once_unless_window_fixes_it(self):
        import argparse
        from twine.cli import Context
        from twine.commands import run as run_verb
        from twine.runtime.boundary import Boundary
        ctx = Context(env={}, stdout=io.StringIO(), stderr=io.StringIO())
        a, transport = self.adapter((self.MODELS.status, self.MODELS.headers,
                                     self.MODELS.response), model="claude-sonnet-5-5")
        window = run_verb.spawn_window(ctx, argparse.Namespace(window=None), Boundary(a))
        self.assertEqual((window.size, window.source, len(transport.calls)),
                         (1000000, "adapter", 1))
        b, transport = self.adapter()
        window = run_verb.spawn_window(ctx, argparse.Namespace(window=4096), Boundary(b))
        self.assertEqual((window.size, window.source, transport.calls), (4096, "flag", []))


if __name__ == "__main__":
    unittest.main()

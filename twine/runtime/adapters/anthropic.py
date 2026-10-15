"""The Anthropic adapter, `anthropic` — the Messages API behind the
boundary (Arc 2 R2; claude/context/runtime-contract.md §5 is its contract).

It speaks `POST https://api.anthropic.com/v1/messages` (headers
`x-api-key`, `anthropic-version: 2023-06-01`, `content-type:
application/json`) over the stdlib, through a **transport seam**
(twine.runtime.transport): one callable handed in at construction — the
tests hand recorded bytes, and when none is given the adapter builds the
real one, `https_transport`, the only place twine opens a socket. The
`anthropic` SDK is not used and no module under twine/ imports it: its
retries and parsing would hide exactly the paths the transition table
owns.

  build_request   the request body, pure: system as one text block, tools
                  as given, thinking passed through, and the three prompt-
                  cache breakpoints (the system block, the last tool, the
                  last content block of the last message); never
                  stop_sequences, temperature, top_p, top_k, metadata or
                  tool_choice
  read_response   a JSON answer (a message, or an error body) as an Outcome
  read_stream     an SSE answer as an Outcome — chunks split anywhere, the
                  data lines parsed as JSON (the recordings pad them with
                  spaces), `ping` and unknown events ignored, the usage the
                  message_start's overlaid with the message_delta's
                  (cumulative, final); the stop_reason is taken before an
                  open block is judged: a stream that ended at the output
                  ceiling inside a block is a max_tokens turn, its closed
                  blocks and an open text or thinking block kept, an open
                  tool_use block whose input did not parse left out
                  (twine-run-ergonomics, runtime-contract §5.4)
  stop_key        a stop_reason onto the stop axis
  error_key       an HTTP status, an error type or a transport exception
                  onto the stop axis
  read_models_window  a `GET /v1/models` answer as the window of a model
                  (Arc 2 R5): its `max_input_tokens`, or unknown with why
  AnthropicAdapter  the boundary adapter: the key from the environment it
                  is given, the spawn-time constants, `call`, and since R5
                  `context_window` — one `GET /v1/models` per spawn

**The stop and error mapping is data**: share/transitions.toml's
`[[mapping]]` rows for the provider `anthropic`, read through
twine.transitions.provider_mapping. No stop key is spelled here (a test
holds every module under twine/runtime/ to that); stop_key and error_key
look the provider's word up, and a word no row lists takes the row of the
condition that names the case (`unlisted-stop-reason`, `unlisted-status`,
`unclassified-stream-error`, …) — never a guess at a nearer key.

**The key** is `ANTHROPIC_API_KEY` in the environment mapping the adapter
is given (`env=`; this module never reaches for the process environment),
read once at construction; absent or empty, construction refuses naming the
variable. It goes into the `x-api-key` header and nowhere else: no Turn,
Outcome, reason, exception, log line or repr carries it, and every reason
the adapter writes is scrubbed of it besides.

Sections:
  1. Constants and errors          (~line 79)
  2. The mapping: stop_key, error_key   (~line 152)
  3. The request                   (~line 241)
  4. The Outcome                   (~line 368)
  5. Reading a response            (~line 457)
  6. Reading a stream              (~line 645)
  7. The conversation (append-only)   (~line 931)
  8. The adapter                   (~line 985)
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, ClassVar, Iterable, Mapping, Sequence

from twine import TRANSITIONS_TABLE
from twine.runtime.boundary import Adapter, Request, SpawnSettings, Turn
from twine.runtime.terms import NATIVE, ThinkingSettings, ToolCall, ToolSpec, WindowStatement
from twine.runtime.transport import Transport, https_transport
from twine.runtime.usage import UsageMappingError, from_anthropic
from twine.spend import Tokens
from twine.transitions import ProviderMapping, TableError, WordMapping, provider_mapping

log = logging.getLogger("twine.runtime.adapters.anthropic")

# ---------------------------------------------------------------------------
# 1. Constants and errors
# ---------------------------------------------------------------------------

PROVIDER = "anthropic"
API_BASE = "https://api.anthropic.com"
MESSAGES_PATH = "/v1/messages"
MESSAGES_URL = API_BASE + MESSAGES_PATH
# Where the adapter reads its model's context window at spawn (Arc 2 R5):
# the model listing, whose entries carry `max_input_tokens` (the 2026-10-13
# recording, fixtures/anthropic/models.response.json). One page, as
# recorded: no query string.
MODELS_PATH = "/v1/models"
MODELS_URL = API_BASE + MODELS_PATH
API_VERSION = "2023-06-01"
KEY_VARIABLE = "ANTHROPIC_API_KEY"

DEFAULT_MODEL = "claude-haiku-5-5"
# The output ceiling per call when none is given: well under every 5.x
# model's 128000 (the 2026-10-13 /v1/models recording), with room for
# adaptive thinking. The loop (R4) will pass its own.
DEFAULT_MAX_TOKENS = 16000
# D12: thinking is a spawn-time constant; adaptive is what the loop passes
# (the 5.x models refuse `enabled`; Sonnet 5.5, Opus 5.5 and the Fable
# models refuse `disabled`).
DEFAULT_THINKING: Mapping[str, Any] = {"type": "adaptive"}
THINKING_TYPES = ("adaptive", "enabled", "disabled")

CACHE_CONTROL: Mapping[str, str] = {"type": "ephemeral"}
JSON_MEDIA = "application/json"
SSE_MEDIA = "text/event-stream"
# The content blocks an assistant turn may carry back (brief (d)); any
# other type is a shape twine never asked for.
BLOCK_FIELDS: Mapping[str, tuple[str, ...]] = {
    "text": ("text",),
    "tool_use": ("id", "name", "input"),
    "thinking": ("thinking", "signature"),
    "redacted_thinking": ("data",),
}
CANONICAL_TOOL_KEYS = frozenset({"name", "description", "input_schema"})
# The provider's own words the readers use structurally (never stop keys —
# these are Anthropic's spellings): the two ordinary endings, which carry
# no reason, and the one stop that may cut a tool_use block short.
ORDINARY_ENDINGS = ("end_turn", "tool_use")
CUT_SHORT = "max_tokens"
# The mapping's conditions the adapter meets (twine.transitions.CONDITIONS).
C_SOCKET_TIMEOUT = "socket-timeout"
C_CONNECTION = "connection-error"
C_STREAM_CUT = "stream-cut"
C_UNCLASSIFIED = "unclassified-stream-error"
C_UNLISTED_STOP = "unlisted-stop-reason"
C_UNLISTED_STATUS = "unlisted-status"
C_MALFORMED = "malformed-body"

ZERO_USAGE = Tokens(input=0, output=0, thinking=None, cache_read=0, cache_write=0)


class AnthropicConfigError(ValueError):
    """The adapter cannot be built: no key, an incoherent setting, or a
    transition table whose Anthropic mapping is unusable. Raised before
    any call; the message never carries the key."""


class RequestShapeError(ValueError):
    """build_request was handed something that is not a request's part."""


class ConversationEdited(ValueError):
    """A Request whose messages do not extend the last one sent: the
    conversation is append-only (D12), and an edited prefix would both
    break the cache and lie about what the model saw."""


class UnreadableUsage(RuntimeError):
    """The provider answered, and its usage cannot be read: the turn cannot
    be recorded without guessing a number, so the adapter raises (runtime-
    contract §1.4) rather than hand the boundary a Turn."""


# ---------------------------------------------------------------------------
# 2. The mapping: stop_key, error_key
# ---------------------------------------------------------------------------


@lru_cache(maxsize=16)
def _mapping_at(path: str, mtime_ns: int, size: int) -> ProviderMapping:
    return provider_mapping(PROVIDER, Path(path))


def anthropic_mapping(table: Path = TRANSITIONS_TABLE) -> ProviderMapping:
    """The table's `anthropic` mapping, read once per version of the file
    (keyed on its path, mtime and size). Raises TableError when the table,
    its stop axis or this provider's mapping is unusable."""
    try:
        st = Path(table).stat()
    except OSError:
        return provider_mapping(PROVIDER, Path(table))   # raises, naming why
    return _mapping_at(str(table), st.st_mtime_ns, st.st_size)


def _stop_row(stop_reason: Any, mapping: ProviderMapping) -> tuple[WordMapping, bool]:
    """The row a stop_reason takes, and whether the word itself is listed
    (False: the row is a condition's — unlisted, or not a word at all)."""
    if not isinstance(stop_reason, str):
        return mapping.condition(C_MALFORMED), False
    row = mapping.get("stop_reason", stop_reason)
    if row is not None:
        return row, True
    return mapping.condition(C_UNLISTED_STOP), False


def stop_key(stop_reason: str | None, *, table: Path = TRANSITIONS_TABLE) -> str | None:
    """A message's stop_reason as a key of the stop axis, or None when the
    turn goes on (it asked for tools). A word no row lists is the
    `unlisted-stop-reason` condition's key; a null stop_reason (a message
    without one) is the `malformed-body` condition's. Never raises for a
    word; raises TableError when the table cannot stand behind the
    mapping."""
    row, _ = _stop_row(stop_reason, anthropic_mapping(table))
    return row.stop


def _error_row(status: int | None, error_type: str | None, exc: BaseException | None,
               mapping: ProviderMapping) -> tuple[WordMapping, str]:
    """The row an error takes, and how it was found (for the reason)."""
    if exc is not None:
        word = C_SOCKET_TIMEOUT if isinstance(exc, TimeoutError) else C_CONNECTION
        return mapping.condition(word), f"condition {word}"
    if status is not None and status != 200:
        if isinstance(status, bool) or not isinstance(status, int):
            raise TypeError(f"status must be an int, not {status!r}")
        row = mapping.get("status", str(status))
        if row is not None:
            return row, f"HTTP status {status}"
        return mapping.condition(C_UNLISTED_STATUS), f"HTTP status {status}, unlisted"
    if error_type is not None:
        row = mapping.get("error_type", str(error_type))
        if row is not None:
            return row, f"error type {error_type}"
        return mapping.condition(C_UNCLASSIFIED), f"error type {error_type}, unlisted"
    raise ValueError("error_key needs an exception, an HTTP status other than 200, or an "
                     "error type: there is nothing to classify")


def error_key(status: int | None, error_type: str | None, exc: BaseException | None,
              *, table: Path = TRANSITIONS_TABLE) -> str:
    """An error as a key of the stop axis. Total over the table's rows and
    refusing nothing silently:

      exc given        a TimeoutError is `socket-timeout`'s key, any other
                       exception `connection-error`'s (the transport's
                       failure to talk)
      status not 200   the status row decides (an HTTP error's error.type
                       is kept in the reason, never dispatched on); a status
                       no row lists is `unlisted-status`'s key
      else error_type  an SSE error event inside a 200: its error.type's
                       row, or `unclassified-stream-error`'s key

    Raises ValueError when given nothing to classify (no exception, no
    status but 200, no error type), and TableError when the table cannot
    stand behind the mapping."""
    row, _ = _error_row(status, error_type, exc, anthropic_mapping(table))
    if row.stop is None:   # check_mappings allows `continues` on any word
        raise TableError(f"the {PROVIDER} mapping says an error continues the turn "
                         f"({row.on} {row.word!r}); an error stops it")
    return row.stop


# ---------------------------------------------------------------------------
# 3. The request
# ---------------------------------------------------------------------------


def _plain(value: Any, what: str) -> Any:
    """A JSON-shaped copy of `value` (mappings to dicts, sequences to
    lists), or RequestShapeError naming `what` when it is not JSON."""
    try:
        return json.loads(json.dumps(value, default=_unmapping))
    except (TypeError, ValueError) as exc:
        raise RequestShapeError(f"{what} is not JSON-shaped: {exc}") from None


def _unmapping(value: Any) -> Any:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (tuple, set, frozenset)):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON")


def _mark_last_block(messages: list[dict[str, Any]]) -> None:
    """The third breakpoint: cache_control on the last content block of the
    last message (a string content becomes one text block to carry it). A
    thinking block takes no cache_control, so a last block of that kind is
    left unmarked, and said so."""
    if not messages:
        return
    last = messages[-1]
    content = last.get("content")
    if isinstance(content, str):
        last["content"] = [{"type": "text", "text": content,
                            "cache_control": dict(CACHE_CONTROL)}]
    elif isinstance(content, list) and content and isinstance(content[-1], dict):
        if content[-1].get("type") in ("thinking", "redacted_thinking"):
            log.debug("last block is %s: no cache breakpoint on it",
                      content[-1].get("type"))
            return
        content[-1]["cache_control"] = dict(CACHE_CONTROL)


def build_request(*, model: str, max_tokens: int, system: str | None,
                  messages: list[dict], tools: list[dict], thinking: dict | None,
                  stream: bool = True) -> dict:
    """The Messages API request body. Pure: nothing given is modified.

    `messages` are API-shaped already (the conversation's own blocks, as
    received — runtime-contract §5.6); `tools` are canonical
    `{name, description, input_schema}` objects, exactly those keys. The
    body carries `model`, `max_tokens`, `messages` and `stream`; `system`
    as a list of one text block when given; `tools` when non-empty;
    `thinking` only when given, as given (D12 — which shapes a model
    accepts is the provider's answer, a 400). Prompt caching (D12): three
    of the API's four breakpoints, `cache_control: {"type": "ephemeral"}`
    on the system block, on the last tool, and on the last content block of
    the last message. Never stop_sequences, temperature, top_p, top_k,
    metadata or tool_choice. Unknown keyword arguments refuse (TypeError);
    a part of the wrong type refuses (RequestShapeError)."""
    faults = []
    if not isinstance(model, str) or not model.strip():
        faults.append(f"model must be a non-empty string, not {model!r}")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        faults.append(f"max_tokens must be a positive integer, not {max_tokens!r}")
    if system is not None and (not isinstance(system, str) or not system.strip()):
        faults.append("system must be a non-empty string or None")
    if not isinstance(messages, list) or not all(
            isinstance(m, Mapping) and "role" in m and "content" in m for m in messages):
        faults.append("messages must be a list of objects with a role and content")
    if not isinstance(tools, list):
        faults.append("tools must be a list")
    else:
        for n, tool in enumerate(tools, 1):
            if not isinstance(tool, Mapping) or set(tool) != CANONICAL_TOOL_KEYS:
                faults.append(f"tool {n} must be exactly {{name, description, "
                              f"input_schema}}, not {sorted(tool) if isinstance(tool, Mapping) else tool!r}")
    if thinking is not None and not isinstance(thinking, Mapping):
        faults.append(f"thinking must be an object or None, not {thinking!r}")
    if not isinstance(stream, bool):
        faults.append(f"stream must be a bool, not {stream!r}")
    if faults:
        raise RequestShapeError("build_request: " + "; ".join(faults))
    body: dict[str, Any] = {"model": model, "max_tokens": max_tokens}
    if system is not None:
        body["system"] = [{"type": "text", "text": system,
                           "cache_control": dict(CACHE_CONTROL)}]
    if tools:
        offered = _plain(tools, "tools")
        offered[-1]["cache_control"] = dict(CACHE_CONTROL)
        body["tools"] = offered
    if thinking is not None:
        body["thinking"] = _plain(thinking, "thinking")
    sent = _plain(messages, "messages")
    _mark_last_block(sent)
    body["messages"] = sent
    body["stream"] = stream
    return body


def tool_dict(tool: ToolSpec) -> dict[str, Any]:
    """R1's ToolSpec as the canonical object build_request takes."""
    return {"name": tool.name, "description": tool.description,
            "input_schema": _plain(tool.input_schema, f"tool {tool.name!r}'s input_schema")}


def thinking_settings(thinking: Mapping[str, Any] | None) -> ThinkingSettings:
    """The thinking parameter as R1's spawn-time ThinkingSettings — what the
    boundary checks a turn against. None and `disabled` are off; `adaptive`
    is on with no budget; `enabled` is on with its `budget_tokens`. Any
    other shape refuses (AnthropicConfigError): the adapter must know
    whether thinking is on."""
    if thinking is None:
        return ThinkingSettings(enabled=False)
    if not isinstance(thinking, Mapping) or thinking.get("type") not in THINKING_TYPES:
        raise AnthropicConfigError(f"thinking must be None or an object whose type is one "
                                   f"of {', '.join(THINKING_TYPES)}, not {thinking!r}")
    kind = thinking["type"]
    try:
        if kind == "adaptive":
            return ThinkingSettings(enabled=True, adaptive=True)
        if kind == "enabled":
            return ThinkingSettings(enabled=True, budget_tokens=thinking.get("budget_tokens"))
        return ThinkingSettings(enabled=False)
    except ValueError as exc:
        raise AnthropicConfigError(f"thinking {dict(thinking)!r}: {exc}") from None


# ---------------------------------------------------------------------------
# 4. The Outcome
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    """One call's answer, read: what the provider said, translated, beside
    the untranslated fact. `as_json()` is pinned (runtime-contract §5.4).

    stop             a key of the stop axis, or None when the turn asks for
                     tools
    reason           a sentence when stop is not the ordinary end (None for
                     end_turn and tool_use)
    text             the text blocks' text, in order ("" when none)
    tool_calls       ToolCall per tool_use block, in order
    thinking         {"thinking", "signature"} per thinking block and
                     {"data"} per redacted_thinking block, in order
    content          the assistant's blocks as the API would want them back
                     (every key it sent), in order; () when the call failed
    usage            the provider's usage as Tokens; None when it reported
                     none (a refusal, a failure before an answer)
    usage_fault      why a usage the provider did report cannot be read
                     (then usage is None and the turn cannot be recorded)
    retry_after      seconds from a retry-after header, else None
    request_id       the request-id header, else None
    raw_stop_reason  the provider's stop_reason, or the error.type, or the
                     exception's class — the untranslated fact
    status           the HTTP status (None when no answer came)

    Beside them, three facts that are not pinned in `as_json()` (the
    transcript's `turn` line carries them under keys of the loop's own):

    malformed        True when the call ended in the `malformed-body`
                     condition, whatever the detail (the one door is
                     `_Context.malformed`)
    raw              the response body as the transport drew it, headers
                     aside — set by the adapter, and only on a malformed
                     call (the loop writes it to `<sid>.call-<N>.raw`)
    cut_tool_call    {"id", "name", "partial_json"} of the `tool_use` block a
                     stream ended inside at the output ceiling, whose input
                     never parsed: the block is not in `content` (a
                     `tool_use` the API would refuse is never sent back);
                     None otherwise
    """

    stop: str | None
    reason: str | None
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    thinking: tuple[Mapping[str, str], ...] = ()
    content: tuple[Mapping[str, Any], ...] = ()
    usage: Tokens | None = None
    usage_fault: str | None = None
    retry_after: float | int | None = None
    request_id: str | None = None
    raw_stop_reason: str | None = None
    status: int | None = None
    malformed: bool = False
    raw: bytes | None = None
    cut_tool_call: Mapping[str, Any] | None = None

    @property
    def continues(self) -> bool:
        return self.stop is None

    def as_json(self) -> dict[str, Any]:
        return {
            "stop": self.stop,
            "reason": self.reason,
            "text": self.text,
            "tool_calls": [c.as_json() for c in self.tool_calls],
            "thinking": [dict(t) for t in self.thinking],
            "content": copy.deepcopy([dict(b) for b in self.content]),
            "usage": None if self.usage is None else self.usage.as_json(),
            "retry_after": self.retry_after,
            "request_id": self.request_id,
            "raw_stop_reason": self.raw_stop_reason,
            "status": self.status,
            "usage_fault": self.usage_fault,
        }

    def to_turn(self) -> Turn:
        """The boundary's Turn. Thinking is "present" when the turn carried
        any thinking or redacted_thinking block, even one whose text is
        empty (the 2026-10-13 thinking_stream recording's is): `thinking`
        is then their text joined ("" for that one), else None. Tool calls
        ride only on a turn that continues. A call the provider answered
        with no usage (an HTTP error, a failure before any answer) bills
        nothing: its Turn's usage is zero. A usage reported and unreadable
        raises UnreadableUsage — the turn cannot be recorded without a
        guess."""
        if self.usage_fault is not None:
            raise UnreadableUsage(f"{PROVIDER}: the provider answered (status "
                                  f"{self.status}) with a usage twine cannot read: "
                                  f"{self.usage_fault}")
        thinking = ("".join(t.get("thinking", "") for t in self.thinking)
                    if self.thinking else None)
        return Turn(text=self.text, thinking=thinking,
                    tool_calls=self.tool_calls if self.stop is None else (),
                    stop=self.stop, usage=self.usage if self.usage is not None else ZERO_USAGE,
                    provider_stop=self.raw_stop_reason,
                    content=tuple(copy.deepcopy(dict(b)) for b in self.content),
                    retry_after=self.retry_after, request_id=self.request_id,
                    reason=self.reason, raw=self.raw,
                    cut_tool_call=(None if self.cut_tool_call is None
                                   else copy.deepcopy(dict(self.cut_tool_call))))


# ---------------------------------------------------------------------------
# 5. Reading a response
# ---------------------------------------------------------------------------


def _lower(headers: Mapping[str, str] | None) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in (headers or {}).items()}


def _retry_after(headers: Mapping[str, str]) -> tuple[float | int | None, str | None]:
    """Seconds from a retry-after header, and a note when one was sent and
    is not a non-negative number of seconds (an HTTP-date is not read: the
    loop's backoff decides then, R4)."""
    raw = headers.get("retry-after")
    if raw is None:
        return None, None
    text = raw.strip()
    try:
        value: float | int = int(text)
    except ValueError:
        try:
            value = float(text)
        except ValueError:
            return None, f"a retry-after header twine does not read as seconds ({raw!r})"
    if value < 0 or value != value or value in (float("inf"),):
        return None, f"a retry-after header that is not a non-negative number ({raw!r})"
    return value, None


@dataclass
class _Context:
    """What every reader carries into an Outcome: the call's headers'
    facts and the mapping."""

    status: int | None
    request_id: str | None
    retry_after: float | int | None
    retry_note: str | None
    mapping: ProviderMapping

    def outcome(self, stop: str | None, reason: str | None, **fields: Any) -> Outcome:
        if self.retry_note:
            reason = f"{reason}; {self.retry_note}" if reason else self.retry_note
        return Outcome(stop=stop, reason=reason, retry_after=self.retry_after,
                       request_id=self.request_id, status=self.status, **fields)

    def malformed(self, detail: str, **fields: Any) -> Outcome:
        row = self.mapping.condition(C_MALFORMED)
        return self.outcome(row.stop, f"{detail}: {row.means}", malformed=True, **fields)


def _context(status: int | None, headers: Mapping[str, str] | None,
             table: Path) -> _Context:
    hdrs = _lower(headers)
    retry, note = _retry_after(hdrs)
    return _Context(status, hdrs.get("request-id"), retry, note, anthropic_mapping(table))


def _quote(error: Any) -> tuple[str | None, str | None]:
    """An error object's type and message, when they are strings."""
    if not isinstance(error, Mapping):
        return None, None
    etype, message = error.get("type"), error.get("message")
    return (etype if isinstance(etype, str) else None,
            message if isinstance(message, str) else None)


def _error_outcome(ctx: _Context, status: int, body: bytes) -> Outcome:
    """An HTTP error: its status decides the key; the error body's type and
    message are quoted whole in the reason; nothing is billed."""
    etype = message = None
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = None
    if isinstance(parsed, Mapping):
        etype, message = _quote(parsed.get("error"))
    row, how = _error_row(status, etype, None, ctx.mapping)
    said = (f'{etype}: "{message}"' if etype and message is not None
            else etype or f"a body that is not an error object ({len(body)} bytes)")
    return ctx.outcome(row.stop, f"HTTP {status}, {said} — {row.means} ({how})",
                       raw_stop_reason=etype)


def _check_block(n: int, block: Any) -> str | None:
    """Why a content block is not one twine can carry back, or None."""
    if not isinstance(block, Mapping):
        return f"content block {n} is not an object"
    kind = block.get("type")
    if kind not in BLOCK_FIELDS:
        return f"content block {n} has the type {kind!r}, not one of {', '.join(BLOCK_FIELDS)}"
    for name in BLOCK_FIELDS[kind]:
        if name not in block:
            return f"content block {n} ({kind}) has no {name!r}"
    if kind == "tool_use":
        if not isinstance(block["input"], Mapping):
            return f"content block {n} (tool_use) has an input that is not an object"
        if not isinstance(block["id"], str) or not isinstance(block["name"], str):
            return f"content block {n} (tool_use) has an id or a name that is not a string"
    elif kind == "redacted_thinking":
        if not isinstance(block["data"], str):
            return f"content block {n} (redacted_thinking) has data that is not a string"
    else:
        for name in BLOCK_FIELDS[kind]:
            if not isinstance(block[name], str):
                return f"content block {n} ({kind}) has a {name} that is not a string"
    return None


def _finish(ctx: _Context, content: list[Any], stop_reason: Any, stop_details: Any,
            usage_obj: Any, cut_tool_call: Mapping[str, Any] | None = None) -> Outcome:
    """A complete message — from a JSON body or an assembled stream — as an
    Outcome: the blocks checked, the usage mapped, the stop_reason looked
    up, and the two held to each other (a turn asks for tools or stops).
    `cut_tool_call` is the stream reader's: a `tool_use` block the output
    ceiling cut short, left out of `content`, named in the reason and kept
    on the Outcome for the transcript."""
    usage: Tokens | None = None
    usage_fault = None
    try:
        usage = from_anthropic(usage_obj)
    except UsageMappingError as exc:
        usage_fault = str(exc)
    for n, block in enumerate(content, 1):
        fault = _check_block(n, block)
        if fault:
            return ctx.malformed(fault, usage=usage, usage_fault=usage_fault,
                                 raw_stop_reason=stop_reason if isinstance(stop_reason, str)
                                 else None)
    if usage_fault is not None:
        return ctx.malformed(f"the usage cannot be read ({usage_fault})",
                             usage_fault=usage_fault,
                             raw_stop_reason=stop_reason if isinstance(stop_reason, str)
                             else None)
    row, listed = _stop_row(stop_reason, ctx.mapping)
    raw = stop_reason if isinstance(stop_reason, str) else None
    blocks = tuple(copy.deepcopy(dict(b)) for b in content)
    calls = tuple(ToolCall(b["id"], b["name"], copy.deepcopy(dict(b["input"])))
                  for b in blocks if b["type"] == "tool_use")
    if not listed:
        detail = (f"stop_reason {stop_reason!r} has no mapping row" if raw
                  else "the message has no stop_reason")
        return ctx.outcome(row.stop, f"{detail}: {row.means}", usage=usage,
                           raw_stop_reason=raw)
    if row.continues and not calls:
        return ctx.malformed(f"stop_reason {raw!r} asks for tools and the message carries "
                             "no tool_use block", usage=usage, raw_stop_reason=raw)
    if calls and not row.continues and raw != CUT_SHORT:
        return ctx.malformed(f"stop_reason {raw!r} with {len(calls)} tool_use block(s): a "
                             "turn asks for tools or stops", usage=usage, raw_stop_reason=raw)
    reason = None
    if raw not in ORDINARY_ENDINGS:
        reason = f"{row.means} (stop_reason {raw!r})"
        if stop_details is not None:
            reason += f"; stop_details {json.dumps(stop_details, ensure_ascii=False)}"
        if cut_tool_call is not None:
            reason += (f"; the stream ended inside a {cut_tool_call['name']!r} tool_use "
                       "block whose input was not complete, so the block is not carried")
    thinking = tuple(({"thinking": b["thinking"], "signature": b["signature"]}
                      if b["type"] == "thinking" else {"data": b["data"]})
                     for b in blocks if b["type"] in ("thinking", "redacted_thinking"))
    text = "".join(b["text"] for b in blocks if b["type"] == "text")
    return ctx.outcome(row.stop, reason, text=text, tool_calls=calls, thinking=thinking,
                       content=blocks, usage=usage, raw_stop_reason=raw,
                       cut_tool_call=None if cut_tool_call is None else dict(cut_tool_call))


def read_response(status: int, headers: Mapping[str, str], body: bytes, *,
                  table: Path = TRANSITIONS_TABLE) -> Outcome:
    """A JSON answer as an Outcome. A status other than 200 is an error:
    its status row decides (error_key), the error body's type and message
    quoted whole in the reason, usage None. A 200 must be a message: JSON,
    an object with `content` (a list of the four block types), a
    `stop_reason` and a `usage` from_anthropic reads — anything else is the
    `malformed-body` condition's key, naming what is wrong."""
    ctx = _context(status, headers, table)
    if status != 200:
        return _error_outcome(ctx, status, body)
    try:
        message = json.loads(body)
    except ValueError as exc:
        return ctx.malformed(f"the 200 body is not JSON ({exc})")
    if not isinstance(message, Mapping):
        return ctx.malformed("the 200 body is not a JSON object")
    if message.get("type", "message") != "message":
        return ctx.malformed(f"the 200 body is a {message.get('type')!r}, not a message")
    missing = [k for k in ("content", "stop_reason", "usage") if k not in message]
    if missing:
        return ctx.malformed(f"the message has no {', '.join(missing)}")
    if not isinstance(message["content"], list):
        return ctx.malformed("the message's content is not a list")
    return _finish(ctx, message["content"], message["stop_reason"],
                   message.get("stop_details"), message["usage"])


# ---------------------------------------------------------------------------
# 6. Reading a stream
# ---------------------------------------------------------------------------


Observer = Callable[[str, str], None]


class _StreamFault(Exception):
    """An event the stream reader cannot place; becomes malformed-body."""


class _TransportBroke(Exception):
    """The transport raised while the reader drew a chunk: carries the
    transport's exception, so only a failure of the transport — never a
    fault of the reader's own — is classified as one."""

    def __init__(self, exc: Exception) -> None:
        super().__init__(f"{type(exc).__name__}: {exc}")
        self.exc = exc


def _drawn(chunks: Iterable[bytes]) -> Iterable[bytes]:
    """The chunks, with any exception the transport raises while one is
    drawn wrapped as _TransportBroke."""
    iterator = iter(chunks)
    while True:
        try:
            chunk = next(iterator)
        except StopIteration:
            return
        except Exception as exc:
            raise _TransportBroke(exc) from exc
        yield chunk


@dataclass
class _Assembly:
    """A stream being assembled into the message it describes."""

    started: bool = False
    usage: dict[str, Any] = field(default_factory=dict)
    blocks: dict[int, dict[str, Any]] = field(default_factory=dict)
    partial_json: dict[int, list[str]] = field(default_factory=dict)
    closed: set[int] = field(default_factory=set)
    stop_reason: Any = None
    stop_details: Any = None
    delta_seen: bool = False
    events: int = 0


def _merge_usage(into: dict[str, Any], delta: Mapping[str, Any]) -> None:
    """message_delta's usage over message_start's: its counts are
    cumulative totals, so they replace; a count it omits (or sends null)
    keeps message_start's value (as the SDK's accumulator does)."""
    for key, value in delta.items():
        if value is not None:
            into[key] = copy.deepcopy(value)


def _observe(observer: Observer | None, kind: str, text: str, state: dict[str, bool]) -> None:
    """Hand a delta to the observer; an observer that fails does not fail
    the call (the streaming contract) — it is logged once and dropped."""
    if observer is None or not text or state.get("failed"):
        return
    try:
        observer(kind, text)
    except Exception as exc:   # the observer's fault, never the call's
        state["failed"] = True
        log.warning("stream observer failed (%s: %s); the call goes on without it",
                    type(exc).__name__, exc)


def _event(a: _Assembly, data: Mapping[str, Any], observer: Observer | None,
           state: dict[str, bool]) -> str | None:
    """Apply one event to the assembly. Returns "stop" at message_stop and
    "error" at an error event; raises _StreamFault for one it cannot
    place. `ping` and event types it does not know are ignored."""
    kind = data.get("type")
    if kind == "message_start":
        message = data.get("message")
        if not isinstance(message, Mapping) or not isinstance(message.get("usage", {}), Mapping):
            raise _StreamFault("message_start carries no message object")
        a.started = True
        a.usage = copy.deepcopy(dict(message.get("usage") or {}))
        return None
    if kind in ("ping", None):
        return None
    if kind == "error":
        return "error"
    if kind == "message_stop":
        return "stop"
    if kind not in ("content_block_start", "content_block_delta", "content_block_stop",
                    "message_delta"):
        log.debug("stream event %r ignored", kind)
        return None
    if not a.started:
        raise _StreamFault(f"{kind} before message_start")
    if kind == "message_delta":
        delta = data.get("delta")
        if not isinstance(delta, Mapping):
            raise _StreamFault("message_delta carries no delta object")
        a.stop_reason = delta.get("stop_reason")
        a.stop_details = delta.get("stop_details")
        usage = data.get("usage")
        if usage is not None:
            if not isinstance(usage, Mapping):
                raise _StreamFault("message_delta's usage is not an object")
            _merge_usage(a.usage, usage)
        a.delta_seen = True
        return None
    index = data.get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        raise _StreamFault(f"{kind} has no integer index")
    if kind == "content_block_start":
        block = data.get("content_block")
        if not isinstance(block, Mapping) or index in a.blocks:
            raise _StreamFault(f"content_block_start {index} carries no block, or a second")
        a.blocks[index] = copy.deepcopy(dict(block))
        return None
    block = a.blocks.get(index)
    if block is None or index in a.closed:
        raise _StreamFault(f"{kind} for block {index}, which is not open")
    if kind == "content_block_stop":
        a.closed.add(index)
        if index in a.partial_json:
            joined = "".join(a.partial_json.pop(index))
            try:
                block["input"] = json.loads(joined) if joined else {}
            except ValueError as exc:
                raise _StreamFault(f"block {index}'s input_json_delta pieces do not join "
                                   f"into JSON ({exc})") from None
        return None
    delta = data.get("delta")
    dkind = delta.get("type") if isinstance(delta, Mapping) else None
    pairs = {"text_delta": ("text", "text"), "thinking_delta": ("thinking", "thinking"),
             "signature_delta": ("thinking", "signature"),
             "input_json_delta": ("tool_use", "partial_json")}
    if dkind not in pairs:
        raise _StreamFault(f"block {index} has a delta of type {dkind!r}, not one twine reads")
    want, key = pairs[dkind]
    piece = delta.get(key)
    if block.get("type") != want or not isinstance(piece, str):
        raise _StreamFault(f"block {index} ({block.get('type')}) has a {dkind} it cannot carry")
    if dkind == "input_json_delta":
        a.partial_json.setdefault(index, []).append(piece)
    elif dkind == "signature_delta":
        block["signature"] = block.get("signature", "") + piece
    else:
        block[key] = block.get(key, "") + piece
        _observe(observer, "text" if dkind == "text_delta" else "thinking", piece, state)
    return None


@dataclass
class _Tail:
    """What followed the last complete event when the chunks ran out: the
    bytes of an unterminated event — where the connection was cut."""

    trailing: int = 0


def _decode_event(lines: list[bytes]) -> tuple[str | None, str | None, str | None] | None:
    """One terminated event's lines as (event name, data, fault): `data:`
    lines joined with "\\n", a field's one leading space dropped, comment
    lines and other fields ignored. None when the event carries no data
    (nothing to dispatch); a fault when its bytes are not UTF-8."""
    name: str | None = None
    data: list[str] = []
    for raw in lines:
        try:
            line = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            return name, None, f"is not UTF-8 ({exc})"
        if line.startswith(":"):
            continue
        fieldname, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if fieldname == "event":
            name = value
        elif fieldname == "data":
            data.append(value)
    if not data:
        return None
    return name, "\n".join(data), None


def _events(chunks: Iterable[bytes], tail: _Tail
            ) -> Iterable[tuple[str | None, str | None, str | None]]:
    """Server-sent events from byte chunks split anywhere, one per
    **terminated** event — its lines followed by a blank line — as (event
    name, data, fault). Lines end at LF (a CR before it is dropped). Bytes
    are decoded only once their event is terminated: an unterminated
    trailing event — a `data:` line with no blank line after it, or half of
    one — is not an event but where the connection was cut, so it is
    never parsed, never judged, and only counted (`tail.trailing`, in
    bytes). A transport exception propagates to the caller."""
    buffer = b""
    lines: list[bytes] = []
    for chunk in chunks:
        buffer += bytes(chunk)
        while b"\n" in buffer:
            raw, buffer = buffer.split(b"\n", 1)
            raw = raw.rstrip(b"\r")
            if raw:
                lines.append(raw)
                continue
            if lines:
                event = _decode_event(lines)
                lines = []
                if event is not None:
                    yield event
    tail.trailing = len(buffer) + sum(len(line) + 1 for line in lines)


def _event_data(n: int, name: str | None, raw: str) -> Mapping[str, Any]:
    """A terminated event's data as an object, or _StreamFault naming it."""
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise _StreamFault(f"event {n} ({name}) has data that is not JSON ({exc})") from None
    if not isinstance(data, Mapping):
        raise _StreamFault(f"event {n} ({name}) has data that is not an object")
    return data


def _ends_stream(name: str | None, raw: str | None) -> bool:
    """Whether a terminated event is the stream's end — message_stop, or an
    error event — read from its data's type when that parses, else from
    its `event:` name. Used to decide whether a stream ended before its
    end was reached, without judging the event's shape."""
    kind = name
    if raw is not None:
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        if isinstance(data, Mapping) and isinstance(data.get("type"), str):
            kind = data["type"]
    return kind in ("message_stop", "error")


def read_stream(status: int, headers: Mapping[str, str], chunks: Iterable[bytes], *,
                table: Path = TRANSITIONS_TABLE, observer: Observer | None = None) -> Outcome:
    """An SSE answer as an Outcome. Chunks may split the body anywhere.
    Each terminated event's data is parsed as JSON (so padding is no
    matter); `ping` and event types twine does not know are ignored; text
    and thinking deltas reach `observer(kind, text)` as they arrive, when
    one is given.

    **Whether the stream ended comes first** (the desk's ruling on the HOLD
    of 2026-10-13): an unterminated trailing event is not an event but
    where the connection was cut, so a stream whose complete events never
    reach message_stop (or an error event) is the `stream-cut` condition —
    `network-failure` — whatever trails it and whatever an earlier event
    looked like, the reason naming how many complete events arrived. A
    transport exception mid-stream is its own key (error_key with the
    exception). Either keeps the usage reported so far.

    Only a stream that did end is judged: an event that cannot be placed
    (data not JSON, not UTF-8, not the documented shape, message_stop
    without message_delta) makes it `malformed-body`. The message is
    assembled from message_start, the content blocks and message_delta (its
    stop_reason, and its usage over message_start's) and finished like a
    JSON message at message_stop. An `error` event ends the stream: its
    error.type decides (error_key), usage None. A status other than 200 is
    read as read_response reads it."""
    if status != 200:
        try:
            body = b"".join(bytes(c) for c in chunks)
        except Exception as exc:
            ctx = _context(status, headers, table)
            return _failure(ctx, exc, "reading the error body")
        return read_response(status, headers, body, table=table)
    ctx = _context(status, headers, table)
    a = _Assembly()
    state: dict[str, bool] = {}
    tail = _Tail()
    fault: str | None = None   # the first event that could not be placed
    try:
        for name, raw, bad in _events(_drawn(chunks), tail):
            a.events += 1
            n = a.events
            if fault is not None:
                # Judging is suspended until the stream proves it ended.
                if _ends_stream(name, raw):
                    return ctx.malformed(fault, **_partial_usage(a))
                continue
            try:
                if bad is not None:
                    raise _StreamFault(f"event {n} ({name}) {bad}")
                data = _event_data(n, name, raw)  # type: ignore[arg-type]
                ended = _event(a, data, observer, state)
                if ended == "error":
                    etype, message = _quote(data.get("error"))
                    if etype is None:
                        row = ctx.mapping.condition(C_UNCLASSIFIED)
                        how = "an error event without an error type"
                    else:
                        row, how = _error_row(None, etype, None, ctx.mapping)
                    said = f'{etype}: "{message}"' if message is not None else f"{etype}"
                    return ctx.outcome(row.stop, f"the stream ended with an error event after "
                                       f"{n - 1} complete events, {said} — {row.means} ({how})",
                                       raw_stop_reason=etype)
                if ended == "stop":
                    if not a.delta_seen:
                        raise _StreamFault("message_stop without a message_delta: no "
                                           "stop_reason or final usage")
                    unclosed = sorted(set(a.blocks) - a.closed)
                    if unclosed and a.stop_reason == CUT_SHORT:
                        # The stop_reason is taken before an open block is
                        # judged: a stream that ended at the output ceiling
                        # inside a block is the turn that was cut short.
                        content, cut = _cut_blocks(a, unclosed)
                        return _finish(ctx, content, a.stop_reason, a.stop_details,
                                       a.usage, cut)
                    if unclosed:
                        raise _StreamFault(f"message_stop with block(s) {unclosed} still open")
                    content = [a.blocks[i] for i in sorted(a.blocks)]
                    return _finish(ctx, content, a.stop_reason, a.stop_details, a.usage)
            except _StreamFault as exc:
                fault = str(exc)
                if _ends_stream(name, raw):
                    return ctx.malformed(fault, **_partial_usage(a))
    except _TransportBroke as broke:   # the transport failed mid-stream
        return _failure(ctx, broke.exc, f"after {a.events} complete events",
                        **_partial_usage(a))
    row = ctx.mapping.condition(C_STREAM_CUT)
    detail = f"the stream ended after {a.events} complete events without message_stop"
    if tail.trailing:
        detail += (f", {tail.trailing} bytes of an unterminated event trailing (where the "
                   "connection was cut; not an event, so not judged)")
    if fault is not None:
        detail += (f"; an earlier event could not be placed ({fault}), but a stream that "
                   "never ended is judged as cut")
    return ctx.outcome(row.stop, f"{detail}: {row.means}", **_partial_usage(a))


def _cut_blocks(a: _Assembly, unclosed: Sequence[int]
                ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """The content of a stream that ended at the output ceiling with
    block(s) still open: every block in order, the closed ones as they are
    and an open `text` or `thinking` block as far as it got. An open
    `tool_use` block is carried only when the pieces of its input joined
    parse as an object (a ceiling that fell exactly between the last piece
    and the block's stop); otherwise it is left out — a tool_use the API
    would refuse is never sent back — and returned as the second value,
    `{"id", "name", "partial_json"}`, for the transcript. Pure of the
    assembly: nothing is edited."""
    content: list[dict[str, Any]] = []
    cut: dict[str, Any] | None = None
    for index in sorted(a.blocks):
        block = copy.deepcopy(a.blocks[index])
        if index not in unclosed:
            content.append(block)
            continue
        if block.get("type") != "tool_use":
            if block.get("type") == "thinking":
                block.setdefault("signature", "")   # the signature comes last
            content.append(block)
            continue
        joined = "".join(a.partial_json.get(index, []))
        try:
            parsed = json.loads(joined) if joined else None
        except ValueError:
            parsed = None
        if isinstance(parsed, Mapping):
            block["input"] = parsed
            content.append(block)
            continue
        cut = {"id": block.get("id"), "name": block.get("name"), "partial_json": joined}
    return content, cut


def _partial_usage(a: _Assembly) -> dict[str, Any]:
    """The usage reported before a stream failed, when it can be read —
    message_start's, overlaid by message_delta's if it came. None when no
    message_start arrived; never a guess."""
    if not a.started:
        return {}
    try:
        return {"usage": from_anthropic(a.usage)}
    except UsageMappingError:
        return {}


def _failure(ctx: _Context, exc: BaseException, when: str, **fields: Any) -> Outcome:
    """A transport exception as an Outcome: error_key's condition row, the
    exception's class as the raw fact."""
    row, how = _error_row(None, None, exc, ctx.mapping)
    return ctx.outcome(row.stop, f"{type(exc).__name__} {when}: {exc} — {row.means} ({how})",
                       raw_stop_reason=type(exc).__name__, **fields)


# ---------------------------------------------------------------------------
# 7. The conversation (append-only)
# ---------------------------------------------------------------------------


def assistant_message(turn: Turn | Outcome) -> dict[str, Any]:
    """The assistant message the next request carries: the turn's content
    blocks exactly as received (every key the API sent — the 2026-10-13
    tool_result recording sends `caller` back and the API takes it; a
    modified or dropped thinking block it rejects)."""
    return {"role": "assistant", "content": copy.deepcopy([dict(b) for b in turn.content])}


def tool_result_message(results: Sequence[tuple[str, str, bool]]) -> dict[str, Any]:
    """The user message carrying tool results: one `tool_result` block per
    (tool_use_id, content, failed), `is_error: true` when the tool failed
    (the model reads it and answers accordingly — tool_result_error)."""
    blocks = []
    for tool_use_id, content, failed in results:
        block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tool_use_id,
                                 "content": content}
        if failed:
            block["is_error"] = True
        blocks.append(block)
    return {"role": "user", "content": blocks}


def user_message(text: str) -> dict[str, Any]:
    return {"role": "user", "content": text}


class Conversation:
    """An append-only conversation in the API's own shape (D12): messages
    are added, never edited; `messages` is a tuple of copies."""

    def __init__(self, first: str | None = None) -> None:
        self._messages: list[dict[str, Any]] = []
        if first is not None:
            self.user(first)

    @property
    def messages(self) -> tuple[dict[str, Any], ...]:
        return tuple(copy.deepcopy(self._messages))

    def user(self, text: str) -> None:
        self._messages.append(user_message(text))

    def assistant(self, turn: Turn | Outcome) -> None:
        self._messages.append(assistant_message(turn))

    def tool_results(self, results: Sequence[tuple[str, str, bool]]) -> None:
        self._messages.append(tool_result_message(results))


# ---------------------------------------------------------------------------
# 8. The adapter
# ---------------------------------------------------------------------------


def _media(headers: Mapping[str, str]) -> str:
    return _lower(headers).get("content-type", "").split(";", 1)[0].strip().lower()


def read_models_window(status: int, headers: Mapping[str, str], body: bytes,
                       model: str) -> WindowStatement:
    """The context window of `model` from a `GET /v1/models` answer (Arc 2
    R5), pure: the listed entry's `max_input_tokens` when the listing is a
    200 JSON page carrying an entry with that `id` and a positive integer
    there; otherwise unknown, the reason saying why — an HTTP error (its
    `error.type` and `message` quoted), a body that is not the listing, a
    model not listed (and whether the listing said it had more pages, which
    twine does not read), an entry without the count. Never raises for the
    provider's answer: an unknown window is not a refusal."""
    where = f"GET {MODELS_PATH}"
    if status != 200:
        detail = ""
        try:
            error = json.loads(body.decode("utf-8")).get("error")
            kind, message = _quote(error)
            if kind or message:
                detail = f" ({kind}: {message})"
        except (ValueError, AttributeError, UnicodeDecodeError):
            pass
        return WindowStatement(None, f"{where} answered HTTP {status}{detail}; the window of "
                                     f"{model!r} is unknown")
    media = _media(headers)
    if media != JSON_MEDIA:
        return WindowStatement(None, f"{where} answered a 200 whose content-type is "
                                     f"{media or 'absent'!r}, not {JSON_MEDIA}; the window of "
                                     f"{model!r} is unknown")
    try:
        listing = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return WindowStatement(None, f"{where} answered a body that is not JSON ({exc}); the "
                                     f"window of {model!r} is unknown")
    data = listing.get("data") if isinstance(listing, dict) else None
    if not isinstance(data, list):
        return WindowStatement(None, f"{where} answered JSON without a `data` list of models; "
                                     f"the window of {model!r} is unknown")
    entry = next((m for m in data if isinstance(m, dict) and m.get("id") == model), None)
    if entry is None:
        more = (" and says it has more pages, which twine does not read"
                if listing.get("has_more") is True else "")
        return WindowStatement(None, f"{model!r} is not among the {len(data)} model(s) "
                                     f"{where} lists{more}; its window is unknown")
    size = entry.get("max_input_tokens")
    if type(size) is not int or size <= 0:
        return WindowStatement(None, f"{where} lists {model!r} without a positive integer "
                                     f"max_input_tokens (it has {size!r}); its window is "
                                     "unknown")
    return WindowStatement(size, None)


class AnthropicAdapter(Adapter):
    """The Messages API behind the boundary.

        AnthropicAdapter(env=..., transport=..., **settings)

    `env` is the environment mapping the key is read from
    (`ANTHROPIC_API_KEY`, once, here); `transport` the seam (default: the
    real one, https_transport). Settings, each a spawn-time constant
    (D12): `model` (default claude-haiku-5-5), `max_tokens` (16000),
    `thinking` (`{"type": "adaptive"}`; None sends none), `system` (None),
    `stream` (True), `timeout` (the real transport's, seconds), `observer`
    (streamed deltas, optional), `table` (the transition table; a test's).

    `call(body)` takes a request body (a dict, as build_request makes) and
    returns its Outcome; `call(request)` takes R1's Request — the
    boundary's path — builds the body from the conversation and the tools,
    and returns the Turn. One method answers both because both are pinned:
    the oracle's `adapter.call(body) -> Outcome`, and R1's Adapter.call.
    """

    name: ClassVar[str] = "anthropic"
    implements: ClassVar[frozenset[str]] = frozenset({
        "tool-calling", "thinking", "usage-accounting", "prompt-caching", "streaming"})
    tool_protocol: ClassVar[str] = NATIVE
    provider: ClassVar[str] = PROVIDER

    def __init__(self, *, env: Mapping[str, str], transport: Transport | None = None,
                 model: str = DEFAULT_MODEL, max_tokens: int = DEFAULT_MAX_TOKENS,
                 thinking: Mapping[str, Any] | None = DEFAULT_THINKING,
                 system: str | None = None, stream: bool = True,
                 timeout: float | None = None, observer: Observer | None = None,
                 table: Path = TRANSITIONS_TABLE) -> None:
        if not isinstance(env, Mapping):
            raise AnthropicConfigError(f"env must be the environment mapping the key is read "
                                       f"from, not {type(env).__name__}")
        key = env.get(KEY_VARIABLE)
        if not isinstance(key, str) or not key.strip():
            raise AnthropicConfigError(f"{KEY_VARIABLE} is not set (or is empty) in the "
                                       "environment the adapter was given: the Anthropic "
                                       "adapter does not start without its key")
        try:
            settings = SpawnSettings(model=model, max_tokens=max_tokens,
                                     thinking=thinking_settings(thinking))
        except AnthropicConfigError:
            raise
        except ValueError as exc:
            raise AnthropicConfigError(str(exc)) from None
        if system is not None and (not isinstance(system, str) or not system.strip()):
            raise AnthropicConfigError("system must be a non-empty string or None")
        if not isinstance(stream, bool):
            raise AnthropicConfigError(f"stream must be a bool, not {stream!r}")
        try:
            self._mapping = anthropic_mapping(Path(table))
        except TableError as exc:
            raise AnthropicConfigError(f"the transition table cannot stand behind the "
                                       f"{PROVIDER} mapping: {exc}") from None
        super().__init__(settings)
        self.__key = key
        self._table = Path(table)
        self._thinking = None if thinking is None else copy.deepcopy(dict(thinking))
        self._system = system
        self._stream = stream
        self._observer = observer
        if transport is None:
            transport = (https_transport() if timeout is None
                         else https_transport(timeout=timeout))
        self._transport = transport
        self._sent: tuple[dict[str, Any], ...] = ()
        self.calls = 0
        # The context window, read once per spawn (R5): None until asked.
        self._window: WindowStatement | None = None
        self.window_calls = 0
        log.info("%s adapter up: model %r, max_tokens %d, thinking %s, stream %s",
                 PROVIDER, model, max_tokens, self._thinking, stream)

    def __repr__(self) -> str:
        return (f"AnthropicAdapter(model={self.settings.model!r}, "
                f"max_tokens={self.settings.max_tokens}, stream={self._stream})")

    @property
    def stream(self) -> bool:
        return self._stream

    @property
    def system(self) -> str | None:
        return self._system

    @property
    def thinking_param(self) -> dict[str, Any] | None:
        """The thinking parameter every request carries, as given (a copy)."""
        return copy.deepcopy(self._thinking)

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.__key, "anthropic-version": API_VERSION,
                "content-type": JSON_MEDIA}

    def _scrub(self, text: str | None) -> str | None:
        """A reason with the key, should any path have put it there,
        replaced by the variable's name."""
        if text is None or self.__key not in text:
            return text
        log.warning("a reason carried the key; it was scrubbed")
        return text.replace(self.__key, f"[{KEY_VARIABLE}]")

    def context_window(self) -> WindowStatement:
        """The model's context window, stated at spawn (Arc 2 R5): one
        `GET /v1/models` through the transport seam — the key in
        `x-api-key` and `anthropic-version`, no body — read by
        read_models_window, then held: a second ask answers from the first,
        so a spawn costs one call, never one per model call. A transport
        that fails states unknown, and says so; nothing here raises for the
        provider or the network."""
        if self._window is not None:
            return self._window
        self.window_calls += 1
        headers = {"x-api-key": self.__key, "anthropic-version": API_VERSION}
        model = self.settings.model
        log.info("%s: GET %s for the context window of %r", PROVIDER, MODELS_PATH, model)
        try:
            status, response_headers, chunks = self._transport("GET", MODELS_URL, headers, None)
            body = b"".join(bytes(c) for c in chunks)
        except Exception as exc:   # the transport could not talk: unknown, said
            statement = WindowStatement(None, f"GET {MODELS_PATH} failed before an answer "
                                              f"({type(exc).__name__}: {exc}); the window "
                                              f"of {model!r} is unknown")
        else:
            statement = read_models_window(status, response_headers, body, model)
        if statement.reason is not None:
            statement = WindowStatement(statement.size, self._scrub(statement.reason))
        log.info("%s: the window of %r is %s", PROVIDER, model,
                 statement.size if statement.known else f"unknown ({statement.reason})")
        self._window = statement
        return statement

    def call(self, body: Request | Mapping[str, Any]) -> Turn | Outcome:  # type: ignore[override]
        """`call(body: dict) -> Outcome`, or `call(request: Request) -> Turn`
        (the boundary's path). Anything else is a TypeError."""
        if isinstance(body, Request):
            return self.turn(body)
        if isinstance(body, Mapping):
            return self.send(body)
        raise TypeError(f"call takes a request body (a dict) or a Request, not "
                        f"{type(body).__name__}")

    def send(self, body: Mapping[str, Any]) -> Outcome:
        """One request through the transport — POST to the Messages API
        with the three headers — read by content type. Never raises for a
        provider outcome or a transport failure: both are Outcomes."""
        self.calls += 1
        n = self.calls
        try:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise RequestShapeError(f"the request body is not JSON: {exc}") from None
        log.info("%s call %d: POST %s (%d bytes, model %r, stream %s)", PROVIDER, n,
                 MESSAGES_PATH, len(payload), body.get("model"), body.get("stream"))
        try:
            status, headers, chunks = self._transport("POST", MESSAGES_URL, self._headers(),
                                                      payload)
        except Exception as exc:   # the transport could not talk: an outcome
            outcome = _failure(_context(None, None, self._table), exc, "before any answer")
        else:
            outcome = self._read(status, headers, chunks)
        outcome = _replace_reason(outcome, self._scrub(outcome.reason))
        log.info("%s call %d: status %s, stop %s (%s), request-id %s", PROVIDER, n,
                 outcome.status, outcome.stop if outcome.stop is not None else "continues",
                 outcome.raw_stop_reason, outcome.request_id)
        return outcome

    def _read(self, status: int, headers: Mapping[str, str],
              chunks: Iterable[bytes]) -> Outcome:
        media = _media(headers)
        if status == 200 and media == SSE_MEDIA:
            drawn = _Drawn(chunks)
            outcome = read_stream(status, headers, drawn, table=self._table,
                                  observer=self._observer)
            return _keep_raw(outcome, drawn.body)
        try:
            body = b"".join(bytes(c) for c in chunks)
        except Exception as exc:
            return _failure(_context(status, headers, self._table), exc,
                            "reading the response body")
        if status != 200 or media == JSON_MEDIA:
            return _keep_raw(read_response(status, headers, body, table=self._table), body)
        return _keep_raw(_context(status, headers, self._table).malformed(
            f"a 200 whose content-type is {media or 'absent'!r}, neither {JSON_MEDIA} nor "
            f"{SSE_MEDIA}"), body)

    def turn(self, request: Request) -> Turn:
        """The boundary's path: the Request's messages (API-shaped, append-
        only — each request extends the last one sent, or ConversationEdited)
        and tools, the spawn-time constants, one call, the Turn."""
        messages = [_plain(m, "a message") for m in request.messages]
        if messages[:len(self._sent)] != list(self._sent):
            raise ConversationEdited(f"{PROVIDER}: the request's messages do not extend the "
                                     f"{len(self._sent)} sent last call; the conversation is "
                                     "append-only (D12)")
        body = build_request(model=self.settings.model, max_tokens=self.settings.max_tokens,
                             system=self._system, messages=messages,
                             tools=[tool_dict(t) for t in request.tools],
                             thinking=self._thinking, stream=self._stream)
        outcome = self.send(body)
        self._sent = tuple(messages)
        return outcome.to_turn()


class _Drawn:
    """The chunks a stream reader draws, remembered as they are drawn: the
    response body as the transport delivered it (headers aside), so a call
    that ends `malformed-body` can keep what the reader was given. An
    iterable the reader walks once."""

    def __init__(self, chunks: Iterable[bytes]) -> None:
        self._chunks = chunks
        self._seen = bytearray()

    def __iter__(self) -> Iterable[bytes]:
        for chunk in self._chunks:
            self._seen += bytes(chunk)
            yield chunk

    @property
    def body(self) -> bytes:
        return bytes(self._seen)


def _keep_raw(outcome: Outcome, body: bytes) -> Outcome:
    """The Outcome with the response body attached when — and only when — the
    call ended in the `malformed-body` condition, whatever the detail. No
    other outcome keeps a byte (the loop writes what it is handed)."""
    return replace(outcome, raw=body) if outcome.malformed else outcome


def _replace_reason(outcome: Outcome, reason: str | None) -> Outcome:
    return outcome if reason == outcome.reason else replace(outcome, reason=reason)


ADAPTERS = (AnthropicAdapter,)

__all__ = ["ADAPTERS", "API_VERSION", "AnthropicAdapter", "AnthropicConfigError",
           "Conversation", "ConversationEdited", "KEY_VARIABLE", "MESSAGES_URL", "Outcome",
           "RequestShapeError", "UnreadableUsage", "anthropic_mapping", "assistant_message",
           "MODELS_URL", "build_request", "error_key", "read_models_window", "read_response",
           "read_stream", "stop_key", "thinking_settings", "tool_dict", "tool_result_message",
           "user_message"]

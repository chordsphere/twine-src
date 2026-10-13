"""The fake transport adapter, `fake` — scripted, for twine's own tests
(T8: twine's tests never reach a model API). claude/context/
runtime-contract.md §3 is its contract.

It is handed, at spawn, the turns it will answer with — a script — and
plays them back through the boundary one per call, so the boundary's
behaviour is observable without a model. It is the seam T8's 2026-10-01
annotation deferred to Arc 2, "where the first API-shaped call exists to
fake". Registered, so `twine runtime list` shows it; driven by the tests
and by nothing else in twine.

A script is a list of turns, each a JSON-shaped object (so a test can
write one as data, or load one from a file):

    {"text":       "…",          optional, default ""
     "thinking":   "…" | null,   optional, default null
     "tool_calls": [{"id": "…", "name": "…", "arguments": {…}}, …],
                                 optional, default []
     "stop":       "end-turn" | … | null,   required: null when the turn
                                 asks for tools
     "usage":      {"input": n, "output": n, "thinking": n | null,
                    "cache_read": n, "cache_write": n}   required: twine's
                                 five classes, exactly}

Any other key, or a value of the wrong type, refuses the script when it is
built (FakeScriptError, naming the turn and the key) — never at playback.

What the fake does not do: reach a network, read a key, stream, cache,
count a window, choose or invent a turn, or map anything. Its stop mapping
is the identity — a scripted stop reaches the boundary exactly as written,
so a provider's word scripted where twine's belongs (`end_turn`,
`tool_use`) is refused there, which is the point: the adapter's mapping is
the only place a provider's word becomes twine's. Its usage mapping is the
identity too: the script is already in twine's classes. A call past the
script's end raises FakeScriptExhausted rather than answering.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, Sequence

from twine.runtime.boundary import Adapter, Request, SpawnSettings, Turn
from twine.runtime.terms import NATIVE, ToolCall
from twine.spend import TOKEN_CLASSES, Tokens

log = logging.getLogger("twine.runtime.adapters.fake")

TURN_KEYS = ("text", "thinking", "tool_calls", "stop", "usage")
REQUIRED_TURN_KEYS = ("stop", "usage")
TOOL_CALL_KEYS = ("id", "name", "arguments")


class FakeScriptError(ValueError):
    """A script the fake cannot play; the message names the turn and key."""


class FakeScriptExhausted(RuntimeError):
    """The fake was called more times than its script has turns."""


@dataclass(frozen=True)
class FakeScript:
    """A parsed script: the turns, in order, already in twine's terms."""

    turns: tuple[Turn, ...]

    @classmethod
    def from_data(cls, data: Sequence[Mapping[str, Any]]) -> "FakeScript":
        """Parse a script, or FakeScriptError naming every fault by turn."""
        if isinstance(data, (str, bytes)) or not isinstance(data, Sequence):
            raise FakeScriptError(f"a script is a list of turns, not {type(data).__name__}")
        if not data:
            raise FakeScriptError("a script has at least one turn")
        faults: list[str] = []
        turns: list[Turn] = []
        for n, raw in enumerate(data, 1):
            turn = _parse_turn(n, raw, faults)
            if turn is not None:
                turns.append(turn)
        if faults:
            raise FakeScriptError("fake script: " + "; ".join(faults))
        return cls(tuple(turns))


def _parse_turn(n: int, raw: Any, faults: list[str]) -> Turn | None:
    where = f"turn {n}"
    if not isinstance(raw, Mapping):
        faults.append(f"{where} is not an object")
        return None
    before = len(faults)
    unknown = sorted(set(raw) - set(TURN_KEYS))
    if unknown:
        faults.append(f"{where} has unknown key(s) {', '.join(map(repr, unknown))}")
    missing = [k for k in REQUIRED_TURN_KEYS if k not in raw]
    if missing:
        faults.append(f"{where} lacks {', '.join(map(repr, missing))}")
    text = raw.get("text", "")
    if not isinstance(text, str):
        faults.append(f"{where}: text must be a string")
    thinking = raw.get("thinking")
    if thinking is not None and not isinstance(thinking, str):
        faults.append(f"{where}: thinking must be a string or null")
    stop = raw.get("stop")
    if stop is not None and not isinstance(stop, str):
        faults.append(f"{where}: stop must be a string or null")
    calls = _parse_calls(where, raw.get("tool_calls", []), faults)
    usage = _parse_usage(where, raw.get("usage"), faults) if "usage" in raw else None
    if len(faults) > before or usage is None:
        return None
    return Turn(text=text, thinking=thinking, tool_calls=calls, stop=stop, usage=usage,
                provider_stop=stop)


def _parse_calls(where: str, raw: Any, faults: list[str]) -> tuple[ToolCall, ...]:
    if not isinstance(raw, list):
        faults.append(f"{where}: tool_calls must be a list")
        return ()
    calls = []
    for m, call in enumerate(raw, 1):
        if not isinstance(call, Mapping) or set(call) != set(TOOL_CALL_KEYS):
            faults.append(f"{where}: tool call {m} must be an object with exactly "
                          f"{', '.join(TOOL_CALL_KEYS)}")
            continue
        if not isinstance(call["arguments"], Mapping):
            faults.append(f"{where}: tool call {m}'s arguments must be an object")
            continue
        calls.append(ToolCall(id=call["id"], name=call["name"],
                              arguments=dict(call["arguments"])))
    return tuple(calls)


def _parse_usage(where: str, raw: Any, faults: list[str]) -> Tokens | None:
    if not isinstance(raw, Mapping) or set(raw) != set(TOKEN_CLASSES):
        faults.append(f"{where}: usage must be an object with exactly the five classes "
                      f"({', '.join(TOKEN_CLASSES)})")
        return None
    # Built as given: the boundary, not the fake, judges the counts — so a
    # test can script a bad count and watch the boundary refuse it.
    return Tokens(**{name: raw[name] for name in TOKEN_CLASSES})


class FakeAdapter(Adapter):
    """The scripted adapter. Construct it with the spawn settings and a
    script (a FakeScript, or the list FakeScript.from_data parses); each
    `call` answers with the next scripted turn and records the request it
    was given (`requests`), so a test can see what crossed the boundary."""

    name: ClassVar[str] = "fake"
    implements: ClassVar[frozenset[str]] = frozenset(
        {"tool-calling", "thinking", "usage-accounting"})
    tool_protocol: ClassVar[str] = NATIVE

    def __init__(self, settings: SpawnSettings,
                 script: FakeScript | Sequence[Mapping[str, Any]]) -> None:
        super().__init__(settings)
        self.script = script if isinstance(script, FakeScript) else FakeScript.from_data(script)
        self.requests: list[Request] = []
        log.debug("fake adapter spawned: %d scripted turn(s), model %r", len(self.script.turns),
                  settings.model)

    @property
    def remaining(self) -> int:
        """How many scripted turns are left to play."""
        return len(self.script.turns) - len(self.requests)

    def call(self, request: Request) -> Turn:
        played = len(self.requests)
        if played >= len(self.script.turns):
            raise FakeScriptExhausted(
                f"fake adapter: call {played + 1}, and the script has "
                f"{len(self.script.turns)} turn(s)")
        self.requests.append(request)
        turn = self.script.turns[played]
        log.debug("fake adapter: call %d plays scripted turn %d (stop %r)", played + 1,
                  played + 1, turn.stop)
        return turn


ADAPTERS = (FakeAdapter,)

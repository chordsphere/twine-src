"""The adapter boundary (twine-seed.md T6, Q-3; proposed at Arc 2 R1 and
ratified as written on 2026-10-12 — claude/context/runtime-contract.md §1
is its contract).

A model adapter implements `Adapter`: one call in, one `Turn` out. The
boundary (`Boundary`) wraps an adapter and holds every turn to the
contract before the loop (R4) sees it. Q-3 names four things the boundary
abstracts:

  tool calling  a turn either asks for tools (ToolCall tuples, no stop) or
                stops; native tool use or the text tool protocol behind it
                (the text protocol's wire is TQ-3, R6 — the seam is the
                adapter's `tool_protocol`, and the boundary refuses `text`
                until a parser exists)
  thinking      the model and thinking settings are SpawnSettings, handed
                to the adapter once at construction and never again (D12)
  usage         every turn's usage is a twine.spend.Tokens — the five
                classes — mapped by the provider's function in the
                usage-accounting capability's module; the loop
                appends it (R4), the boundary only checks it
  the stop set  every stop is a key of share/transitions.toml's `stop`
                axis, read through twine.transitions.stop_keys — the one
                spelling. The adapter's own mapping is the only place a
                provider's stop word becomes twine's: the boundary
                translates nothing, and refuses a stop the axis lacks —
                and, since Arc 2 R2, a stop the axis lists among its
                `loop_keys` (twine.transitions.loop_keys): those are the
                loop's to produce, never an adapter's.

A boundary refusal is a BoundaryError naming the adapter, the call and
every fault. It is an adapter defect, not a model outcome: what the loop
does with one is R4's to decide (D17: it will have a move).

Nothing here reaches a network, reads a key or imports outside the
stdlib and twine.
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Mapping

from twine import TRANSITIONS_TABLE
from twine.runtime.contract import NAME_PATTERN
# The shapes come from twine.runtime.terms, never from a capability module:
# the registry must be able to report a capability module missing while
# this module — and so every verb — still imports.
from twine.runtime.terms import (NATIVE, TEXT, TOOL_PROTOCOLS, ThinkingSettings, ToolCall,
                                 ToolSpec, token_faults, tool_call_faults)
from twine.spend import Tokens
from twine.transitions import TableError, loop_keys, stop_keys

log = logging.getLogger("twine.runtime.boundary")

# The capabilities every adapter behind the boundary implements: the three
# of Q-3's four that are capabilities (the stop set is the boundary's own,
# not a capability). Each is a name the declaration lists; a test holds
# them to it.
BOUNDARY_CAPABILITIES = ("tool-calling", "thinking", "usage-accounting")


class BoundaryError(Exception):
    """An adapter, or a turn it returned, that breaks the boundary's
    contract. `faults` lists every reason; the message names the adapter."""

    def __init__(self, adapter: str, faults: list[str], *, call: int | None = None) -> None:
        where = f"adapter {adapter!r}" + (f", call {call}" if call is not None else "")
        super().__init__(f"{where}: " + "; ".join(faults))
        self.adapter = adapter
        self.call = call
        self.faults = list(faults)


# ---------------------------------------------------------------------------
# What crosses the boundary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpawnSettings:
    """The spawn-time constants (D12): the model a session runs on, its
    output ceiling per call, and its thinking settings. Handed to the
    adapter at construction; frozen, and taken by no method after."""

    model: str
    max_tokens: int
    thinking: ThinkingSettings

    def __post_init__(self) -> None:
        faults = []
        if not isinstance(self.model, str) or not self.model.strip():
            faults.append(f"model must be a non-empty string, not {self.model!r}")
        if type(self.max_tokens) is not int or self.max_tokens <= 0:
            faults.append(f"max_tokens must be a positive integer, not {self.max_tokens!r}")
        if not isinstance(self.thinking, ThinkingSettings):
            faults.append("thinking must be a ThinkingSettings")
        elif (self.thinking.budget_tokens is not None and type(self.max_tokens) is int
              and self.thinking.budget_tokens >= self.max_tokens):
            faults.append(f"the thinking budget ({self.thinking.budget_tokens}) must be "
                          f"below max_tokens ({self.max_tokens})")
        if faults:
            raise ValueError("spawn settings: " + "; ".join(faults))

    def as_json(self) -> dict[str, Any]:
        return {"model": self.model, "max_tokens": self.max_tokens,
                "thinking": self.thinking.as_json()}


@dataclass(frozen=True)
class Request:
    """One call's input: the conversation so far, append-only (D12) — a
    tuple of message objects whose shape the loop (R4) fixes — and the
    tools offered. A tuple, so nothing edits an earlier turn in place."""

    messages: tuple[Mapping[str, Any], ...]
    tools: tuple[ToolSpec, ...] = ()


@dataclass(frozen=True)
class Turn:
    """What one call answers with, in twine's terms.

    text        the model's visible text ("" when it wrote none)
    thinking    its thinking text, or None (D20: rendered by the shell)
    tool_calls  the tools it asked for, in order; () when none
    stop        None when the turn asks for tools — the worker's turn goes
                on — otherwise the key of the stop axis it stopped with
    usage       the call's tokens, the five classes
    provider_stop  the provider's own stop word, as the adapter received
                it, for diagnosis only: nothing dispatches on it

    Added at Arc 2 R2, each defaulting so an adapter that has none of them
    (the fake) is unchanged:

    content     the assistant's content blocks exactly as the provider
                would want them back — what the next request's assistant
                turn carries (D12: append-only; a provider may reject a
                modified or dropped thinking block); () when none
    retry_after seconds the provider asked to wait before a retry (a
                `retry-after` header), or None
    request_id  the provider's id for the call, for diagnosis, or None
    reason      a sentence saying why the turn stopped, when the stop is
                not a plain end (a refusal quotes the provider's error type
                and message whole); None otherwise
    """

    text: str
    thinking: str | None
    tool_calls: tuple[ToolCall, ...]
    stop: str | None
    usage: Tokens
    provider_stop: str | None = None
    content: tuple[Mapping[str, Any], ...] = ()
    retry_after: float | None = None
    request_id: str | None = None
    reason: str | None = None

    @property
    def continues(self) -> bool:
        """True when the turn asked for tools and the worker's turn goes on."""
        return self.stop is None

    def as_json(self) -> dict[str, Any]:
        return {"text": self.text, "thinking": self.thinking,
                "tool_calls": [c.as_json() for c in self.tool_calls],
                "stop": self.stop, "usage": self.usage.as_json(),
                "provider_stop": self.provider_stop,
                "content": [dict(block) for block in self.content],
                "retry_after": self.retry_after, "request_id": self.request_id,
                "reason": self.reason}


# ---------------------------------------------------------------------------
# The interface an adapter implements
# ---------------------------------------------------------------------------


class Adapter(abc.ABC):
    """A model adapter — "a chosen set of capabilities" (§4.1).

    Class attributes, declared by every adapter and read by the registry
    without constructing one:

      name           the adapter's registered name (lowercase, hyphens)
      implements     the capability names it implements, each one the
                     declaration lists; at least BOUNDARY_CAPABILITIES
      tool_protocol  `native` or `text` (TOOL_PROTOCOLS)

    The constructor takes the SpawnSettings and keeps them (D12); `call`
    takes a Request and returns a Turn in twine's terms — the provider's
    stop word already mapped onto the stop axis, its usage already mapped
    onto Tokens. There is deliberately no method that takes a model or
    thinking settings.
    """

    name: ClassVar[str]
    implements: ClassVar[frozenset[str]]
    tool_protocol: ClassVar[str]

    def __init__(self, settings: SpawnSettings) -> None:
        if not isinstance(settings, SpawnSettings):
            raise TypeError(f"{type(self).__name__} needs SpawnSettings, not "
                            f"{type(settings).__name__}")
        self._settings = settings

    @property
    def settings(self) -> SpawnSettings:
        """The spawn-time constants, read-only."""
        return self._settings

    @abc.abstractmethod
    def call(self, request: Request) -> Turn:
        """One model call. Raises only for a fault of the adapter's own
        (a broken transport, an unreadable usage); a provider outcome —
        a refusal, a rate limit, the window's edge — is a Turn whose stop
        names it."""


def adapter_class_faults(cls: Any) -> list[str]:
    """Every reason `cls` cannot be registered as an adapter; [] when it
    can. Checks the declared class attributes only — never constructs."""
    if not (isinstance(cls, type) and issubclass(cls, Adapter)):
        return [f"{cls!r} is not an Adapter subclass"]
    found: list[str] = []
    name = getattr(cls, "name", None)
    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        found.append(f"{cls.__name__}.name {name!r} is not a lowercase hyphenated name")
    implements = getattr(cls, "implements", None)
    if not isinstance(implements, frozenset) or not all(isinstance(c, str) for c in implements):
        found.append(f"{cls.__name__}.implements must be a frozenset of capability names")
    protocol = getattr(cls, "tool_protocol", None)
    if protocol not in TOOL_PROTOCOLS:
        found.append(f"{cls.__name__}.tool_protocol {protocol!r} is not one of "
                     f"{', '.join(TOOL_PROTOCOLS)}")
    if getattr(cls, "__abstractmethods__", None):
        found.append(f"{cls.__name__} leaves abstract: "
                     f"{', '.join(sorted(cls.__abstractmethods__))}")
    return found


# ---------------------------------------------------------------------------
# The boundary
# ---------------------------------------------------------------------------


class Boundary:
    """One adapter, held to the contract. Construct it once per session
    (at spawn) and call through it; it never retries, translates or
    repairs — it passes a conforming turn through and refuses any other.

    `table` is the transition table the stop set is read from; the default
    is share/transitions.toml, and only a test names another."""

    def __init__(self, adapter: Adapter, *, table: Path = TRANSITIONS_TABLE) -> None:
        cls = type(adapter)
        faults = adapter_class_faults(cls)
        if not isinstance(adapter, Adapter):
            raise BoundaryError(repr(adapter), ["not an Adapter"])
        name = getattr(cls, "name", cls.__name__)
        missing = [c for c in BOUNDARY_CAPABILITIES if c not in getattr(cls, "implements", ())]
        if missing:
            faults.append(f"does not implement {', '.join(missing)}: every adapter behind "
                          "the boundary implements " + ", ".join(BOUNDARY_CAPABILITIES))
        if getattr(cls, "tool_protocol", None) == TEXT:
            faults.append("declares the text tool protocol, whose wire is TQ-3 (R6): no "
                          "parser exists yet, so the boundary will not run it")
        if faults:
            raise BoundaryError(name, faults)
        try:
            self.stop_set: tuple[str, ...] = stop_keys(table)
            # The stops the loop produces and no adapter may (the cost
            # spine's, the kill-switch's): read from the table, never
            # spelled here (Arc 2 R2; R1 §1.5 recorded the gap as a defect).
            self.loop_set: tuple[str, ...] = loop_keys(table)
        except TableError as exc:
            raise BoundaryError(name, [f"cannot read the stop set: {exc}"]) from exc
        self.adapter = adapter
        self.calls = 0
        log.info("boundary up: adapter %r (%s), model %r, thinking %s; stop set of %d "
                 "keys", name, cls.tool_protocol, adapter.settings.model,
                 adapter.settings.thinking.as_json(), len(self.stop_set))

    @property
    def name(self) -> str:
        return type(self.adapter).name

    @property
    def settings(self) -> SpawnSettings:
        return self.adapter.settings

    def call(self, request: Request) -> Turn:
        """Call the adapter once and return its turn, or raise
        BoundaryError naming every way the turn breaks the contract."""
        if not isinstance(request, Request):
            raise BoundaryError(self.name, [f"the request must be a Request, not "
                                            f"{type(request).__name__}"])
        self.calls += 1
        n = self.calls
        log.debug("call %d to %r: %d messages, %d tools", n, self.name,
                  len(request.messages), len(request.tools))
        turn = self.adapter.call(request)
        faults = self.turn_faults(turn)
        if faults:
            log.warning("call %d to %r refused: %s", n, self.name, "; ".join(faults))
            raise BoundaryError(self.name, faults, call=n)
        log.info("call %d to %r: %s, %d tool call(s), usage %s", n, self.name,
                 "continues" if turn.continues else f"stop {turn.stop}",
                 len(turn.tool_calls), turn.usage.as_json())
        return turn

    def turn_faults(self, turn: Any) -> list[str]:
        """Every way `turn` breaks the contract; [] when it conforms."""
        if not isinstance(turn, Turn):
            return [f"returned a {type(turn).__name__}, not a Turn"]
        found: list[str] = []
        if not isinstance(turn.text, str):
            found.append(f"text must be a string, not {type(turn.text).__name__}")
        if turn.thinking is not None:
            if not isinstance(turn.thinking, str):
                found.append(f"thinking must be a string or None, not "
                             f"{type(turn.thinking).__name__}")
            elif not self.settings.thinking.enabled:
                found.append("carries thinking text, and the session was spawned with "
                             "thinking off (D12)")
        found += tool_call_faults(turn.tool_calls)
        if turn.stop is None:
            if not turn.tool_calls:
                found.append("neither asks for a tool nor stops: a turn with no tool "
                             "call must stop with a key of the stop axis")
        else:
            if turn.stop not in self.stop_set:
                found.append(f"stop {turn.stop!r} is not a key of the stop axis "
                             f"({', '.join(self.stop_set)}); the adapter maps its "
                             "provider's stop words, the boundary translates nothing")
            elif turn.stop in self.loop_set:
                found.append(f"stop {turn.stop!r} is one of the axis's loop keys "
                             f"({', '.join(self.loop_set)}): the loop produces it, and "
                             "an adapter's mapping never may")
            if turn.tool_calls:
                found.append(f"asks for {len(turn.tool_calls)} tool call(s) and stops "
                             f"({turn.stop!r}); a turn does one or the other")
        found += token_faults(turn.usage)
        if turn.provider_stop is not None and not isinstance(turn.provider_stop, str):
            found.append("provider_stop must be a string or None")
        if not isinstance(turn.content, tuple) or not all(
                isinstance(block, Mapping) for block in turn.content):
            found.append("content must be a tuple of content blocks (objects)")
        retry = turn.retry_after
        if retry is not None and (isinstance(retry, bool) or not isinstance(retry, (int, float))
                                  or retry < 0):
            found.append(f"retry_after must be a non-negative number of seconds or None, "
                         f"not {retry!r}")
        for name in ("request_id", "reason"):
            value = getattr(turn, name)
            if value is not None and not isinstance(value, str):
                found.append(f"{name} must be a string or None")
        return found


__all__ = ["Adapter", "BOUNDARY_CAPABILITIES", "Boundary", "BoundaryError", "NATIVE",
           "Request", "SpawnSettings", "TEXT", "Turn", "adapter_class_faults"]

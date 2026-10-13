"""twine's terms at the adapter boundary: the shapes the boundary, the
adapters and the loop share — a tool offered and a tool call, the tool
protocols, the spawn-time thinking settings, and the check that usage is a
Tokens the spend stream accepts.

Why this is not a capability module (Arc 2 R1, corrected after the HOLD
of 2026-10-12): a capability module is a registry entry, and the registry
must be able to report one as missing — `twine runtime list` NOT OK,
naming it — while every verb still loads. So nothing outside
twine/runtime/capabilities/ imports a capability module; the registry
alone reaches them, by its own guarded import. What the boundary and the
adapters need at import time lives here instead, and a test walks every
module under twine/ to hold that line.

The capability modules' contracts describe these shapes
(`tool-calling`: ToolSpec, ToolCall, TOOL_PROTOCOLS; `thinking`:
ThinkingSettings; `usage-accounting`: token_faults); this module is where
the code is. Pure; stdlib and twine.spend only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from twine.spend import TOKEN_CLASSES, Tokens

# ---------------------------------------------------------------------------
# Tool calling (T6, §4.2) — the provider-neutral shape both paths produce
# ---------------------------------------------------------------------------

NATIVE = "native"
TEXT = "text"
# How an adapter carries tool calls. Closed: an adapter names exactly one.
# The text protocol's wire is TQ-3 (R6); until a parser exists the boundary
# refuses an adapter that names it.
TOOL_PROTOCOLS = (NATIVE, TEXT)


@dataclass(frozen=True)
class ToolSpec:
    """A tool the runtime offers the model: its name, a description and a
    JSON-schema object for its input. The adapter translates it into the
    provider's form; the canonical set is R3's."""

    name: str
    description: str
    input_schema: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    """One tool call the model asked for, in twine's own shape.

    id         the call's id, unique within its turn: the result the loop
               returns names it (the provider's id where it has one)
    name       the tool's name, as the model spelled it — the boundary does
               not refuse an unknown name: a call to a tool that does not
               exist is a tool error the loop returns as a result (§4.3),
               never a crash
    arguments  the call's input, a JSON object, read-only
    """

    id: str
    name: str
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        # Frozen means the binding; the mapping itself is made read-only
        # too, so nothing downstream edits what the model asked for.
        if isinstance(self.arguments, dict):
            object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))

    def as_json(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "arguments": dict(self.arguments)}


def tool_call_faults(calls: Any) -> list[str]:
    """Every reason `calls` is not a turn's tool calls; [] when it is.

    A tuple of ToolCall, each with a non-empty string id and name, a
    mapping for its arguments, and no id used twice."""
    if not isinstance(calls, tuple):
        return [f"tool_calls must be a tuple of ToolCall, not {type(calls).__name__}"]
    found: list[str] = []
    seen: set[str] = set()
    for n, call in enumerate(calls, 1):
        if not isinstance(call, ToolCall):
            found.append(f"tool call {n} is not a ToolCall ({type(call).__name__})")
            continue
        if not isinstance(call.id, str) or not call.id.strip():
            found.append(f"tool call {n} has no id")
        elif call.id in seen:
            found.append(f"tool call id {call.id!r} is used twice in one turn")
        else:
            seen.add(call.id)
        if not isinstance(call.name, str) or not call.name.strip():
            found.append(f"tool call {n} has no tool name")
        if not isinstance(call.arguments, Mapping):
            found.append(f"tool call {n} ({call.name!r}) has arguments that are not "
                         "an object")
    return found


# ---------------------------------------------------------------------------
# Thinking (D12, D20) — a spawn-time constant
# ---------------------------------------------------------------------------


class ThinkingSettingsError(ValueError):
    """Thinking settings that are not a coherent spawn-time constant."""


@dataclass(frozen=True)
class ThinkingSettings:
    """Whether the worker thinks, and with what budget — fixed at spawn.

    enabled        thinking on or off for the whole session
    budget_tokens  the thinking budget when enabled with a budget: a
                   positive integer; None when thinking is off (a budget
                   with thinking off is refused — a setting that does
                   nothing is a wrong fact) or adaptive
    adaptive       thinking on with no budget: the model decides how much
                   to think (Anthropic's `{"type": "adaptive"}`, the only
                   thinking the 5.x models accept besides off — Arc 2 R2's
                   recording of /v1/models). Needs enabled and no budget.
    """

    enabled: bool
    budget_tokens: int | None = None
    adaptive: bool = False

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ThinkingSettingsError(f"enabled must be a bool, not {self.enabled!r}")
        if type(self.adaptive) is not bool:
            raise ThinkingSettingsError(f"adaptive must be a bool, not {self.adaptive!r}")
        if self.adaptive:
            if not self.enabled or self.budget_tokens is not None:
                raise ThinkingSettingsError(
                    "adaptive thinking is thinking enabled with no budget_tokens, not "
                    f"enabled={self.enabled!r}, budget_tokens={self.budget_tokens!r}")
        elif self.enabled:
            if type(self.budget_tokens) is not int or self.budget_tokens <= 0:
                raise ThinkingSettingsError(
                    "thinking enabled needs a positive integer budget_tokens (or "
                    f"adaptive), not {self.budget_tokens!r}")
        elif self.budget_tokens is not None:
            raise ThinkingSettingsError(
                f"thinking is off, so budget_tokens must be None, not {self.budget_tokens!r}")

    def as_json(self) -> dict[str, object]:
        return {"enabled": self.enabled, "budget_tokens": self.budget_tokens,
                "adaptive": self.adaptive}


THINKING_OFF = ThinkingSettings(enabled=False)


# ---------------------------------------------------------------------------
# Usage (D15) — the boundary's check on what an adapter hands back
# ---------------------------------------------------------------------------


def token_faults(tokens: Any) -> list[str]:
    """Every reason `tokens` is not a Tokens the spend stream accepts; []
    when it is: a Tokens whose classes are non-negative ints, `thinking`
    also allowed None (the provider did not report it separately)."""
    if not isinstance(tokens, Tokens):
        return [f"usage must be a twine.spend.Tokens, not {type(tokens).__name__}"]
    found: list[str] = []
    for name in TOKEN_CLASSES:
        value = getattr(tokens, name)
        if name == "thinking" and value is None:
            continue
        if type(value) is not int:
            found.append(f"tokens.{name} must be a non-negative integer"
                         f"{' or None' if name == 'thinking' else ''}, not {value!r}")
        elif value < 0:
            found.append(f"tokens.{name} is negative ({value})")
    return found


# ---------------------------------------------------------------------------
# The context window (Arc 2 R5) — what an adapter states at spawn
# ---------------------------------------------------------------------------


class WindowStatementError(ValueError):
    """A window statement that is not one: a size that is not a positive
    integer, or an unknown size with no reason."""


@dataclass(frozen=True)
class WindowStatement:
    """What an adapter says, at spawn, of its model's context window — the
    window-accounting contract's first obligation: "state the model's
    context window size at spawn, or say it is unknown".

    size    the window in input tokens, a positive integer; None when the
            adapter cannot say (its model is not listed, the provider's
            listing failed, it has no model at all)
    reason  why the size is unknown — required then, and None when the
            size is known: an unknown never goes unexplained

    Unknown is not a refusal: the run proceeds, counts the window from each
    call's usage, and cannot warn or stop on it (runtime-contract.md §7.4).
    The window's accounting is the runtime's (twine/runtime/window.py), so
    this is the one thing an adapter contributes to it besides its usage.
    """

    size: int | None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.size is not None and (type(self.size) is not int or self.size <= 0):
            raise WindowStatementError(f"a window size must be a positive integer of tokens "
                                       f"or None, not {self.size!r}")
        if self.reason is not None and not isinstance(self.reason, str):
            raise WindowStatementError(f"a window statement's reason must be a string, not "
                                       f"{type(self.reason).__name__}")
        if self.size is None and not (self.reason or "").strip():
            raise WindowStatementError("a window statement that says the size is unknown "
                                       "must say why")

    @property
    def known(self) -> bool:
        return self.size is not None

    def as_json(self) -> dict[str, object]:
        return {"size": self.size, "reason": self.reason}

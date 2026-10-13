"""The context window, counted (Arc 2 R5; twine-seed.md §4.3 "Window
management", D12, D17; claude/context/runtime-contract.md §7.4–§7.6).

API calls do not compact, and D12's append-only prefixes mean twine never
compacts silently either. So the runtime counts the window instead, warns
the worker in the conversation when it runs thin — so AGENT.md §11's
bail-to-handoff fires — and treats exhaustion as an outcome with a move.
This module is that accounting; the loop (twine/runtime/loop.py) drives it.

  the size     fixed for the run: `twine run --window N` (source `flag`), or
               what the adapter states at spawn (Adapter.context_window,
               source `adapter`), or unknown (source `unknown`, with the
               adapter's reason). Unknown is not a refusal: the run counts
               and cannot warn or stop on the window.
  the count    after each call, `used` = that call's input + cache_read +
               cache_write — the prompt as the provider counted it, exact
               and the provider's own (Tokens' input side). 0 before the
               first call. What was appended since the last call is not
               counted toward the decisions: the numbers the worker reads
               are counts, never estimates (the provider's own refusal,
               mapped at R2, is the backstop for that gap). A call whose
               input side is 0 — one the provider answered with no count,
               an error before any answer — leaves `used` as it was: every
               prompt carries the system note, so a zero is a call that was
               not counted, never an empty window.
  the warning  once the size is known and `used` is at or past
               WINDOW_WARN_FRACTION of it, the run is *warned*, and stays
               warned: from then on every tool result the loop returns to
               the model carries `warning()` as its last line (`noted`),
               as do the continue-turn user turn and the probe hop's user
               turn — appended to what the model reads, never to the
               transcript's `tool-result` line, never by editing an earlier
               turn (the capability's promise).
  exhaustion   once the size is known and `used` is at or past it, the next
               call is not made: the loop stops `window-exhausted`, whose
               move (`split-goal`) is the planner's (D17).

The runtime implements window-accounting itself, not an adapter (the
declaration's `implemented_by` names this module; runtime-contract.md §2.1).
An adapter's part is to state the size and report its usage. Nothing here
spells a stop key (the one spelling is the table's; twine.transitions holds
the constant), reaches a process, a network or the environment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from twine.runtime.terms import WindowStatement
from twine.spend import Tokens
from twine.transitions import STOP_WINDOW_EXHAUSTED

log = logging.getLogger("twine.runtime.window")

# The runtime implements this capability itself: twine/runtime/
# capabilities.toml's `implemented_by` names this module, and the registry
# holds the declaration to this tuple (runtime-contract.md §2.3).
IMPLEMENTS = ("window-accounting",)

# The fraction of the window in use at which the run is warned (the brief's
# one constant).
WINDOW_WARN_FRACTION = 0.8

# Where the size came from (the twin's `window.source`).
SOURCE_FLAG = "flag"
SOURCE_ADAPTER = "adapter"
SOURCE_UNKNOWN = "unknown"
SOURCES = (SOURCE_FLAG, SOURCE_ADAPTER, SOURCE_UNKNOWN)

# The line a warned run's tool results end with: N the last call's used,
# M the size, P the integer percentage (N * 100 // M). Verbatim from the R5
# brief; the stop key is the table's, interpolated, never spelled here.
WARNING_TEMPLATE = ("[window: {used} of {size} input tokens in use ({percent}%); the "
                    "window does not compact — finish and deliver, or escalate; past "
                    "100% the run stops {stop}]")


def input_side(tokens: Tokens) -> int:
    """A call's prompt as the provider counted it: input + cache_read +
    cache_write (the three input-side classes of twine.spend.Tokens)."""
    return tokens.input + tokens.cache_read + tokens.cache_write


@dataclass
class Window:
    """One run's window: its size and where it came from, and what the
    calls so far have counted. Build it with `from_flag`, `stated` or
    `unknown`; `count` after every call that returned a turn."""

    size: int | None
    source: str
    reason: str | None = None
    used: int = 0
    counted_calls: int = 0
    warned: bool = False

    def __post_init__(self) -> None:
        if self.source not in SOURCES:
            raise ValueError(f"window source {self.source!r} is not one of "
                             f"{', '.join(SOURCES)}")
        if self.size is not None and (type(self.size) is not int or self.size <= 0):
            raise ValueError(f"a window size must be a positive integer, not {self.size!r}")
        if (self.size is None) != (self.source == SOURCE_UNKNOWN):
            raise ValueError("a window has a size exactly when its source is not unknown")

    # --- building ----------------------------------------------------------

    @classmethod
    def from_flag(cls, size: int) -> "Window":
        """`--window N`: the operator fixed the size; the adapter is not asked."""
        return cls(size=size, source=SOURCE_FLAG)

    @classmethod
    def stated(cls, statement: WindowStatement) -> "Window":
        """The adapter's statement at spawn: its size, or unknown with its
        reason."""
        if statement.known:
            return cls(size=statement.size, source=SOURCE_ADAPTER)
        return cls(size=None, source=SOURCE_UNKNOWN, reason=statement.reason)

    @classmethod
    def unknown(cls, reason: str) -> "Window":
        return cls(size=None, source=SOURCE_UNKNOWN, reason=reason)

    # --- what it knows -----------------------------------------------------

    @property
    def known(self) -> bool:
        return self.size is not None

    @property
    def counted(self) -> bool:
        """Whether a call has counted the window yet (a `used` exists)."""
        return self.counted_calls > 0

    @property
    def exhausted(self) -> bool:
        """The size is known and `used` is at or past it: the next call is
        not made."""
        return self.size is not None and self.used >= self.size

    def fraction(self) -> float | None:
        return None if self.size is None else self.used / self.size

    def percent(self) -> int | None:
        return None if self.size is None else self.used * 100 // self.size

    # --- counting ----------------------------------------------------------

    def count(self, call: int, tokens: Tokens) -> dict[str, Any]:
        """Count one call's usage and return the transcript's `window` line
        (beside `at`, `seq` and `kind`): `call`, `used`, `size`, `fraction`
        (null when the size is unknown), `warned`, and `call_input` — this
        call's own input side, which is `used` unless the provider counted
        nothing for the call (then `used` is kept)."""
        own = input_side(tokens)
        if own > 0:
            self.used = own
            self.counted_calls += 1
        else:
            log.info("call %d reported no input-side tokens; the window in use stays %d",
                     call, self.used)
        if (not self.warned and self.size is not None
                and self.used >= self.size * WINDOW_WARN_FRACTION):
            self.warned = True
            log.info("call %d: the window runs thin — %d of %d input tokens in use "
                     "(%d%%); the worker is warned from now on", call, self.used,
                     self.size, self.percent())
        return {"call": call, "used": self.used, "size": self.size,
                "fraction": self.fraction(), "warned": self.warned, "call_input": own}

    # --- the warning -------------------------------------------------------

    def warning(self) -> str | None:
        """The warning line, numbers filled in, when the run is warned;
        None otherwise."""
        if not self.warned or self.size is None:
            return None
        return WARNING_TEMPLATE.format(used=self.used, size=self.size,
                                       percent=self.percent(), stop=STOP_WINDOW_EXHAUSTED)

    def noted(self, text: str) -> str:
        """`text` as the model reads it: unchanged when the run is not
        warned; otherwise with the warning as its last line."""
        line = self.warning()
        if line is None:
            return text
        if not text:
            return line
        return text + ("" if text.endswith("\n") else "\n") + line

    def exhausted_reason(self, next_call: int) -> str:
        return (f"the context window is exhausted: {self.used} of {self.size} input tokens "
                f"were in use after the last call ({self.percent()}%), so call {next_call} "
                "was not made — the window does not compact, and the goal is the planner's "
                "to split")

    # --- rendering ---------------------------------------------------------

    def as_json(self) -> dict[str, Any]:
        """The twin's `window` (cli-contract.md §18.5): exactly `size`,
        `used`, `warned`, `source`."""
        return {"size": self.size, "used": self.used, "warned": self.warned,
                "source": self.source}

    def start_json(self) -> dict[str, Any]:
        """The `run-start` line's `window`: the size, where it came from,
        and why it is unknown when it is."""
        return {"size": self.size, "source": self.source, "reason": self.reason,
                "warn_fraction": WINDOW_WARN_FRACTION}

    def describe(self) -> str:
        if self.size is None:
            return (f"size unknown ({self.reason}); the run counts the window and cannot "
                    "warn or stop on it")
        where = "--window" if self.source == SOURCE_FLAG else "the adapter's statement"
        return (f"{self.size} input tokens (from {where}); warned at "
                f"{WINDOW_WARN_FRACTION:.0%}, stopped before a call at 100%")


__all__ = ["IMPLEMENTS", "SOURCES", "SOURCE_ADAPTER", "SOURCE_FLAG", "SOURCE_UNKNOWN",
           "WARNING_TEMPLATE", "WINDOW_WARN_FRACTION", "Window", "input_side"]

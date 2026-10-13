"""Provider usage mappings: each provider's usage object as twine's five
token classes (twine.spend.Tokens) — the code of the usage-accounting
capability (D15, D12, D20, Q-3; claude/context/runtime-contract.md §4).

Why the code is here and not in twine/runtime/capabilities/
usage_accounting.py, where Arc 2 R1 put it: a model adapter calls its
provider's mapping on every turn, and nothing outside capabilities/ may
import a capability module — the registry must be able to report one
missing (`twine runtime list` NOT OK, naming it) while every verb, and
every adapter, still loads. R1 moved ThinkingSettings and token_faults to
twine/runtime/terms.py for the same reason after the HOLD of 2026-10-12;
the Anthropic adapter (R2) is the first caller of from_anthropic outside
the tests, so the mapping moved the same way. The capability module still
exports it — `twine.runtime.capabilities.usage_accounting.from_anthropic`
is this function, the same object — and keeps the CONTRACT.

The mappings are pure functions, one per provider, each held to a
recording: `from_anthropic` to the Messages API `usage` object the
architect recorded on 2026-10-08
(fixtures/anthropic/messages-usage-2026-10-08.json) and to the fifteen
wire recordings of 2026-10-13 (fixtures/anthropic/*.response.*). A usage
the mapping cannot read raises UsageMappingError naming the fault — never
a Tokens with a guessed number, because a wrong fact is worse than a
missing one. Pure; stdlib and twine.spend only.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from twine.spend import Tokens

log = logging.getLogger("twine.runtime.usage")


class UsageMappingError(ValueError):
    """A provider usage object the mapping cannot turn into Tokens; the
    message names the provider and every fault."""


# ---------------------------------------------------------------------------
# Anthropic — the Messages API's `usage` object
# ---------------------------------------------------------------------------

ANTHROPIC = "anthropic"
# The keys the mapping reads. Every other key (`service_tier`,
# `inference_geo`, `cache_creation`'s 5m/1h split, …) is ignored: the spine
# has one `cache_write` class and keeps no split at R1.
A_INPUT = "input_tokens"
A_OUTPUT = "output_tokens"
A_CACHE_READ = "cache_read_input_tokens"
A_CACHE_WRITE = "cache_creation_input_tokens"
A_OUTPUT_DETAILS = "output_tokens_details"
A_THINKING = "thinking_tokens"


def _count(usage: Mapping[str, Any], key: str, where: str, faults: list[str],
           *, required: bool, nullable: bool = False) -> int | None:
    """One count from `usage`: a non-negative int, or a fault recorded.
    An absent optional key is None (the caller says what absence means);
    an absent required key is a fault. `null` is a non-integer, and a
    fault — unless the key is `nullable`, when it reads as absent (the
    provider's own types say the count may be null: see from_anthropic)."""
    if key not in usage or (nullable and usage[key] is None):
        if required:
            faults.append(f"{where}{key} is missing")
        return None
    value = usage[key]
    # bool is an int subclass; JSON true is not a count.
    if type(value) is not int:
        faults.append(f"{where}{key} must be a non-negative integer, not {value!r}")
        return None
    if value < 0:
        faults.append(f"{where}{key} is negative ({value})")
        return None
    return value


def from_anthropic(usage: Mapping[str, Any]) -> Tokens:
    """The Anthropic Messages API's `usage` object as twine's Tokens. Pure.

    | class       | from                                                    |
    |-------------|---------------------------------------------------------|
    | input       | input_tokens (required)                                 |
    | output      | output_tokens (required), less thinking when reported   |
    | thinking    | output_tokens_details.thinking_tokens; None when        |
    |             | output_tokens_details (or thinking_tokens in it) is     |
    |             | absent                                                  |
    | cache_read  | cache_read_input_tokens; 0 when absent or null          |
    | cache_write | cache_creation_input_tokens; 0 when absent or null      |

    Anthropic counts thinking inside `output_tokens`. The spine's classes
    are disjoint and `spend.record_cost` bills `thinking` on top of
    `output` at the output price, so when the provider reports thinking
    separately, `output` is `output_tokens - thinking_tokens`: each token
    is counted, and billed, once (Tokens' docstring: never counted twice).
    When it does not, `thinking` is None and `output` is `output_tokens`
    whole. A thinking count above output_tokens cannot be inside it and is
    refused.

    Raises UsageMappingError — never returns a guessed Tokens — when
    `usage` is not an object, `input_tokens` or `output_tokens` is missing,
    any count it reads is not a non-negative integer (null included, except
    the two cache counts, where null reads as absent — Arc 2 R2), or
    `output_tokens_details` is present and not an object.
    """
    if not isinstance(usage, Mapping):
        raise UsageMappingError(f"{ANTHROPIC} usage must be an object, not "
                                f"{type(usage).__name__}")
    faults: list[str] = []
    input_tokens = _count(usage, A_INPUT, "", faults, required=True)
    output_tokens = _count(usage, A_OUTPUT, "", faults, required=True)
    # The two cache counts may be null as well as absent: the SDK types both
    # Optional[int] = None (anthropic 1.13.0, types/usage.py and
    # types/message_delta_usage.py; Arc 2 R2's reading, brief §5 item 4), so
    # null reads as absent — 0 — and is no longer refused. Every other count
    # the mapping reads stays refused when null (the SDK types input_tokens,
    # output_tokens and thinking_tokens as int).
    cache_read = _count(usage, A_CACHE_READ, "", faults, required=False, nullable=True)
    cache_write = _count(usage, A_CACHE_WRITE, "", faults, required=False, nullable=True)
    thinking: int | None = None
    if A_OUTPUT_DETAILS in usage:
        details = usage[A_OUTPUT_DETAILS]
        if not isinstance(details, Mapping):
            faults.append(f"{A_OUTPUT_DETAILS} must be an object, not {details!r}")
        else:
            thinking = _count(details, A_THINKING, f"{A_OUTPUT_DETAILS}.", faults,
                              required=False)
    if (not faults and thinking is not None and output_tokens is not None
            and thinking > output_tokens):
        faults.append(f"{A_OUTPUT_DETAILS}.{A_THINKING} ({thinking}) exceeds "
                      f"{A_OUTPUT} ({output_tokens}), which counts it")
    if faults:
        log.warning("%s usage refused: %s", ANTHROPIC, "; ".join(faults))
        raise UsageMappingError(f"{ANTHROPIC} usage: " + "; ".join(faults))
    assert input_tokens is not None and output_tokens is not None
    tokens = Tokens(
        input=input_tokens,
        output=output_tokens - (thinking or 0),
        thinking=thinking,
        cache_read=cache_read if cache_read is not None else 0,
        cache_write=cache_write if cache_write is not None else 0,
    )
    log.debug("%s usage mapped: %s", ANTHROPIC, tokens.as_json())
    return tokens


__all__ = ["ANTHROPIC", "UsageMappingError", "from_anthropic"]

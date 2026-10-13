"""usage-accounting — a call's usage as twine's five token classes (D15,
D12, D20, Q-3).

Every model call's usage becomes one twine.spend.Tokens — `input`,
`output`, `thinking`, `cache_read`, `cache_write`, disjoint — and the loop
(R4) appends it to the spend stream through `spend.append_record`. R1
builds the mapping, not the appending.

The mappings are pure functions, one per provider, each held to a
recording: `from_anthropic` is the first, held to the Messages API `usage`
object the architect recorded on 2026-10-08
(fixtures/anthropic/messages-usage-2026-10-08.json). A usage the mapping
cannot read raises UsageMappingError naming the fault — never a Tokens
with a guessed number, because a wrong fact is worse than a missing one.

The boundary's check that what an adapter hands back is a Tokens the
spine accepts (`token_faults`) is code in twine.runtime.terms: nothing
outside this directory imports a capability module, so the registry can
report this one missing while every verb still loads. Only the loop (R4)
and the adapters that map a provider (R2's) call from_anthropic, and they
reach it through the module the declaration names.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from twine.runtime.contract import Contract
from twine.spend import Tokens

log = logging.getLogger("twine.runtime.usage_accounting")


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
           *, required: bool) -> int | None:
    """One count from `usage`: a non-negative int, or a fault recorded.
    An absent optional key is None (the caller says what absence means);
    an absent required key is a fault. `null` is a non-integer, and a
    fault, whether or not the key is required."""
    if key not in usage:
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
    | cache_read  | cache_read_input_tokens; 0 when absent                  |
    | cache_write | cache_creation_input_tokens; 0 when absent              |

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
    any count it reads is not a non-negative integer (null included), or
    `output_tokens_details` is present and not an object.
    """
    if not isinstance(usage, Mapping):
        raise UsageMappingError(f"{ANTHROPIC} usage must be an object, not "
                                f"{type(usage).__name__}")
    faults: list[str] = []
    input_tokens = _count(usage, A_INPUT, "", faults, required=True)
    output_tokens = _count(usage, A_OUTPUT, "", faults, required=True)
    cache_read = _count(usage, A_CACHE_READ, "", faults, required=False)
    cache_write = _count(usage, A_CACHE_WRITE, "", faults, required=False)
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


CONTRACT = Contract(
    capability="usage-accounting",
    purpose=("Every model call's usage becomes one twine.spend.Tokens — input, "
             "output, thinking, cache_read, cache_write, disjoint — so the cost "
             "spine prices it and the hard cap counts it. Each provider has one pure "
             "mapping, held to a recording of that provider's usage object; "
             "from_anthropic is the first."),
    adapter_must=(
        "return every turn's usage as a twine.spend.Tokens, mapped by its "
        "provider's function in this module — never the provider's object",
        "count each token in exactly one class: thinking the provider counts "
        "inside output is taken out of output when it is reported separately",
        "refuse a usage it cannot read (a missing or non-integer count) by raising, "
        "never by guessing a number or defaulting a required count to 0",
        "report thinking as None, not 0, when the provider does not count it "
        "separately",
    ),
    runtime_promises=(
        "the boundary refuses a turn whose usage is not a Tokens of non-negative "
        "integers (thinking also None)",
        "the loop (R4) appends each turn's Tokens to the spend stream through "
        "spend.append_record, once per call; R1 appends nothing",
        "cache classes absent from a provider's usage are 0, and no provider "
        "split (Anthropic's 5m/1h cache_creation) is kept at R1",
    ),
    lands=("R1: Tokens at the boundary, the fake adapter's scripted usage and "
           "from_anthropic over the 2026-10-08 recording; R2: the Anthropic adapter "
           "calls from_anthropic; R4: the loop appends"),
    grounds=("D15", "D12", "D20", "Q-3", "twine.spend.Tokens"),
)

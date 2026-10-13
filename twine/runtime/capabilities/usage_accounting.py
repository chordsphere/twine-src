"""usage-accounting — a call's usage as twine's five token classes (D15,
D12, D20, Q-3).

Every model call's usage becomes one twine.spend.Tokens — `input`,
`output`, `thinking`, `cache_read`, `cache_write`, disjoint — and the loop
(R4) appends it to the spend stream through `spend.append_record`. R1
built the mapping; R2's Anthropic adapter calls it on every turn; nothing
appends yet.

This module is the capability's registry entry: its CONTRACT, and the
provider mappings re-exported — `from_anthropic` and `UsageMappingError`
are twine.runtime.usage's, the same objects. The code moved there at Arc 2
R2 because the Anthropic adapter calls it, and nothing outside this
directory may import a capability module (the registry must be able to
report this one missing while every verb, and every adapter, still loads)
— the same move R1 made for token_faults, which lives in
twine.runtime.terms.
"""

from __future__ import annotations

from twine.runtime.contract import Contract
# The mappings' code is twine.runtime.usage (not a capability module); this
# module re-exports it so the declaration's module still exports what §2.1
# says it does.
from twine.runtime.usage import ANTHROPIC, UsageMappingError, from_anthropic

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
           "calls from_anthropic on every turn (twine.runtime.usage, re-exported "
           "here), held to the fifteen recordings of 2026-10-13; R4: the loop appends"),
    grounds=("D15", "D12", "D20", "Q-3", "twine.spend.Tokens"),
)


__all__ = ["ANTHROPIC", "CONTRACT", "UsageMappingError", "from_anthropic"]

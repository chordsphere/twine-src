"""prompt-caching — declared at Arc 2 R1; implemented by the Anthropic
adapter (R2). Its contract is CONTRACT below (claude/context/
runtime-contract.md §2); nothing implements it yet."""

from __future__ import annotations

from twine.runtime.contract import Contract

CONTRACT = Contract(
    capability="prompt-caching",
    purpose=("The conversation is an append-only, stable prefix — the system prompt "
             "(tool definitions and the surface note only), the opener as the first "
             "user turn, then turns appended and never edited — and the adapter marks "
             "it for the provider's cache, so each call re-reads what the last one "
             "wrote. Twine never compacts silently; it counts instead (D12)."),
    adapter_must=(
        "mark the stable prefix for the provider's cache where the provider has one, "
        "and never reorder, rewrite or drop an earlier part of the conversation",
        "report the cache's reads and writes in the call's Tokens as cache_read and "
        "cache_write (0 where the provider has no cache)",
        "keep the docs and tool definitions pinned at spawn: nothing that would "
        "invalidate the cache changes mid-session (the model and thinking settings "
        "are spawn-time constants)",
    ),
    runtime_promises=(
        "the loop only appends to the conversation it hands the adapter; the request "
        "is a tuple, never edited in place",
        "cache reads and writes are first-class rows in the cost accounting (D12), "
        "priced at the operator's cache_read and cache_write prices",
    ),
    lands="declared at R1; R2 (the Anthropic adapter) implements it",
    grounds=("D12", "D11", "twine-seed.md §4.1", "twine-seed.md §4.3"),
)

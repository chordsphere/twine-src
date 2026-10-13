"""window-accounting — declared at Arc 2 R1; its counting and cold resume
are R5's. Its contract is CONTRACT below (claude/context/runtime-contract.md
§2); nothing implements it yet."""

from __future__ import annotations

from twine.runtime.contract import Contract

CONTRACT = Contract(
    capability="window-accounting",
    purpose=("API calls do not compact, and D12's append-only prefixes mean twine "
             "never compacts silently either: it counts the context window instead — "
             "from the provider's usage, or an estimate for an open model — warns the "
             "worker as a tool result when the window runs thin, so AGENT.md §11's "
             "bail-to-handoff fires, and treats exhaustion as an outcome with a move."),
    adapter_must=(
        "state the model's context window size at spawn, or say it is unknown",
        "report each call's input-side tokens (input, cache_read, cache_write) so the "
        "window in use can be counted; an adapter for a provider that reports none "
        "estimates, and says it estimated",
        "map the provider's context-overflow refusal onto the `window-exhausted` "
        "stop, never onto a retry",
    ),
    runtime_promises=(
        "the warning reaches the worker as a tool result, in the conversation, never "
        "as a mutation of earlier turns",
        "exhaustion stops the turn with `window-exhausted`, which the transition "
        "table gives a move (D17); nothing is summarized or dropped to make room",
    ),
    lands="declared at R1; R5 implements the counting, the warning and cold resume",
    grounds=("twine-seed.md §4.3 (window management)", "D12", "D17", "D21"),
)

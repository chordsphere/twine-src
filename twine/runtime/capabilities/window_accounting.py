"""window-accounting — declared at Arc 2 R1; implemented at R5 (session
2026-10-13-twine-runtime-window-009) by the runtime itself:
twine/runtime/window.py, the declaration's `implemented_by`, which the loop
drives. Its contract is CONTRACT below (claude/context/runtime-contract.md
§2, §7.4–§7.6)."""

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
    lands=("declared at R1; implemented at R5 (session "
           "2026-10-13-twine-runtime-window-009) by the runtime, twine/runtime/window.py: "
           "the size from `twine run --window N` or the adapter's statement at spawn (the "
           "Anthropic adapter's one GET /v1/models; the fake states unknown); `used` = each "
           "call's input + cache_read + cache_write; warned at 80%, every tool result's "
           "last line then the warning; the call not made at 100%, stop window-exhausted, "
           "move split-goal"),
    grounds=("twine-seed.md §4.3 (window management)", "D12", "D17", "D21"),
)

"""thinking — extended thinking as a spawn-time constant (D12, D20, Q-3).

D12: per-worker model and thinking settings are spawn-time constants,
never mid-session knobs — changing thinking settings invalidates the
message cache. So the settings are a frozen value handed to the adapter
when the session spawns (twine.runtime.boundary.SpawnSettings carries
them), and nothing on the boundary or the adapter interface takes them
again: there is no setter to call.

D20's accounting half is the cost spine's: thinking bills as output, and
twine.spend.Tokens' `thinking` class is the provider's own count when it
reports one (`None` when it does not). The rendering half is the shell's.

This module is the capability's registry entry: its CONTRACT.
ThinkingSettings itself is code in twine.runtime.terms, because nothing
outside this directory may import a capability module (the registry must
be able to report this one missing while every verb still loads).
"""

from __future__ import annotations

from twine.runtime.contract import Contract

CONTRACT = Contract(
    capability="thinking",
    purpose=("Extended thinking, on or off with its budget, fixed when the worker "
             "spawns and never changed in the session: the settings are part of the "
             "stable prefix the cache keys on (D12). A turn may carry the model's "
             "thinking text for the shell to render (D20); its tokens are counted by "
             "usage accounting."),
    adapter_must=(
        "take the model and the thinking settings once, at construction (spawn), "
        "and send them unchanged on every call of the session",
        "translate ThinkingSettings into the provider's thinking parameters, and "
        "the provider's thinking blocks into the turn's `thinking` text",
        "never return thinking text from a session spawned with thinking off",
    ),
    runtime_promises=(
        "SpawnSettings and ThinkingSettings are frozen, and no boundary or adapter "
        "method takes a model or thinking argument: there is nothing to change "
        "mid-session",
        "the boundary refuses a turn carrying thinking text when the adapter was "
        "spawned with thinking off",
        "incoherent settings (thinking on with neither a positive budget nor "
        "adaptive, a budget with thinking off, adaptive with a budget) are refused "
        "when they are built, before any spawn",
    ),
    lands=("R1: the settings, the boundary's checks and the fake adapter; R2: "
           "Anthropic's thinking parameter passed as given (adaptive by default, "
           "ThinkingSettings(adaptive=True)), its thinking and redacted_thinking blocks "
           "carried back verbatim, a turn with any thinking block counted as thinking"),
    grounds=("D12", "D20", "Q-3", "twine-seed.md §4.1"),
)

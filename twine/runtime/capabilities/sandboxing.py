"""sandboxing — declared at Arc 2 R1; implemented in R3 with the canonical
tools. Its contract is CONTRACT below (claude/context/runtime-contract.md
§2); nothing implements it yet."""

from __future__ import annotations

from twine.runtime.contract import Contract

CONTRACT = Contract(
    capability="sandboxing",
    purpose=("Twine builds the cage its workers' tools run in: a per-sid sandbox "
             "home holding the include set on disk (D11), network off, `unshare` "
             "where available. Confinement of validation and checkpoints stays "
             "bale's; this is the worker's cage only (D10: tool access only)."),
    adapter_must=(
        "nothing provider-specific: the cage is the runtime's, and every adapter's "
        "tool calls run in it alike",
        "never run a tool itself — an adapter translates calls and results, the "
        "runtime executes them in the cage",
    ),
    runtime_promises=(
        "every tool of the canonical surface runs with its working directory and "
        "every path it touches inside the session's sandbox home",
        "network is off inside the cage; where `unshare` is unavailable the runtime "
        "says so (`confined: false`, as `carry probe` does), never silently",
        "every process a tool starts is registered with the kill-switch's running "
        "record through the run seam's spawn hook",
    ),
    lands="declared at R1; R3 implements it with the canonical tools and the spawn hook",
    grounds=("twine-seed.md §4.3 (sandbox)", "D10", "D11", "D15"),
)

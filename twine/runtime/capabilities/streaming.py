"""streaming — declared at Arc 2 R1; implemented by the Anthropic adapter
in a later Arc 2 session. Its contract is CONTRACT below
(claude/context/runtime-contract.md §2); nothing implements it yet."""

from __future__ import annotations

from twine.runtime.contract import Contract

CONTRACT = Contract(
    capability="streaming",
    purpose=("A call's text and thinking are delivered as the model produces them, "
             "so a watcher (the shell, later) sees the worker think and write (D20); "
             "the finished turn the boundary checks is the same turn an unstreamed "
             "call would have returned."),
    adapter_must=(
        "deliver deltas — text and thinking, in order — to the observer the runtime "
        "hands it, and nothing else through that channel",
        "assemble the finished Turn (text, thinking, tool calls, stop, usage) exactly "
        "as the unstreamed call would, and return it through the boundary as usual",
        "map an interrupted stream onto a stop of the stop axis (`network-failure`, "
        "`timeout`, `overloaded`), never onto a truncated turn that looks finished",
    ),
    runtime_promises=(
        "streamed deltas are a view, never the record: the transcript and the spend "
        "stream are written from the finished turn alone",
        "an observer that fails does not fail the call",
    ),
    lands="declared at R1; implemented with the Anthropic adapter (R2 or a later Arc 2 session)",
    grounds=("D20", "twine-seed.md §4.1", "twine-seed.md §5.2"),
)

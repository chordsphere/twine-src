"""streaming — declared at Arc 2 R1; implemented by the Anthropic adapter
at R2 (`anthropic`: `stream: true`, the SSE reader assembling the turn
from chunks split anywhere, text and thinking deltas to an observer —
claude/context/runtime-contract.md §5.4). Its contract is CONTRACT below
(runtime-contract §2)."""

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
    lands=("declared at R1; implemented at R2 by the Anthropic adapter: the SSE reader, "
           "held to the four stream recordings of 2026-10-13 split at every byte, and "
           "the observer the adapter is given"),
    grounds=("D20", "twine-seed.md §4.1", "twine-seed.md §5.2"),
)

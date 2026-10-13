"""suspend-resume — declared at Arc 2 R1; implemented after the loop (R4),
with window accounting's cold resume (R5). Its contract is CONTRACT below
(claude/context/runtime-contract.md §2); nothing implements it yet."""

from __future__ import annotations

from twine.runtime.contract import Contract

CONTRACT = Contract(
    capability="suspend-resume",
    purpose=("A worker blocked on a clarification goes cold (D23): its transcript "
             "is persisted append-only, the session is suspended, and on the "
             "planner's answer the transcript is re-warmed — replayed as the same "
             "stable prefix, the answer appended — and the worker continues under "
             "the same session id."),
    adapter_must=(
        "accept a persisted conversation as a prefix and continue it, with the "
        "model and thinking settings it was spawned with",
        "hold nothing a resume needs outside the transcript: no provider-side "
        "session state the runtime cannot persist",
    ),
    runtime_promises=(
        "the transcript is kept durably and append-only, as a log and not a record "
        "of intent (TQ-1's answer)",
        "a resume appends the answer and never edits an earlier turn, so the prefix "
        "the cache keys on is unchanged",
    ),
    lands="declared at R1; implemented after R4's loop, with R5's cold resume",
    grounds=("D23", "TQ-1", "twine-seed.md §4.3", "D12"),
)

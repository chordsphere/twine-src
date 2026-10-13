"""suspend-resume — declared at Arc 2 R1; implemented at R5 (session
2026-10-13-twine-runtime-window-009), with window accounting, by the runtime
itself: twine/runtime/resume.py, the declaration's `implemented_by`, which
`twine resume` (twine/commands/resume.py) drives. Its contract is CONTRACT
below (claude/context/runtime-contract.md §2, §7.9)."""

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
    lands=("declared at R1; implemented at R5 (session "
           "2026-10-13-twine-runtime-window-009) by the runtime, twine/runtime/resume.py, "
           "and the verb `twine resume SID --cap USD --answer FILE|-`: the conversation "
           "rebuilt from the transcript's request lines (appended, joined, sent: false "
           "included), the answer appended as one user message, the loop re-run cold "
           "under the same sid with the transcript's spawn-time constants; the first "
           "call's usage is the twin's rewarm (D23's named field); escalate's "
           "clarification form suspends a run on a response tarball the operator applies"),
    grounds=("D23", "TQ-1", "twine-seed.md §4.3", "D12"),
)

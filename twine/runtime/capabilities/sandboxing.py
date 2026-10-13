"""sandboxing — declared at Arc 2 R1; implemented at R3, by the runtime
itself (twine/runtime/sandbox.py, the declaration's `implemented_by`), not by
an adapter. Its contract is CONTRACT below (claude/context/runtime-contract.md
§2, §6)."""

from __future__ import annotations

from twine.runtime.contract import Contract

CONTRACT = Contract(
    capability="sandboxing",
    purpose=("Twine builds the cage its workers' tools run in: a per-sid sandbox "
             "home under the state directory, the file tools' paths confined to it, "
             "a minimal environment that never carries the provider key, network off "
             "through `unshare` where available, and every process a tool starts "
             "registered with the kill-switch. Confinement of validation and "
             "checkpoints stays bale's; this is the worker's cage only (D10: tool "
             "access only)."),
    adapter_must=(
        "nothing provider-specific: the cage is the runtime's, and every adapter's "
        "tool calls run in it alike",
        "never run a tool itself — an adapter translates calls and results, the "
        "runtime executes them in the cage; an adapter that claims this capability "
        "is a status-mismatch",
    ),
    runtime_promises=(
        "every file tool of the canonical surface resolves its path inside the "
        "session's sandbox home, symlinks resolved — an absolute path, a `..` or a "
        "symlink out is a tool error naming the cage — and `shell` runs with the home "
        "as its working directory",
        "the cage's environment is PATH, HOME, TMPDIR and LANG and nothing else it "
        "was not told to pass; ANTHROPIC_API_KEY never reaches it",
        "network is off inside the cage where `unshare -rn` works, and the sandbox "
        "reports `network: \"off\"` and `confines: true` — declared by the sandbox's "
        "runner, the one switch point; where it does not work the sandbox says so "
        "(`network: \"unconfined\"`, `confines: false`, the reason), never silently",
        "every process a tool starts is registered with the kill-switch's running "
        "record through the run seam's spawn hook when the session has one, and "
        "cleared once its run returns with no survivor",
        "exactly one tool leaves the cage — `probe`, by D13 — and the tool "
        "declaration says so",
    ),
    lands=("declared at R1; implemented at R3 (session "
           "2026-10-13-twine-runtime-tools-003) by twine/runtime/sandbox.py with the "
           "seven canonical tools (twine/runtime/tools/); the loop that uses them is "
           "R4's"),
    grounds=("twine-seed.md §4.3 (sandbox)", "D10", "D11", "D13", "D15"),
)

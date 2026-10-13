"""tool-calling — the model asks for tools and gets results (T6, §4.2, Q-3).

Two ways behind one boundary: **native** tool use where the provider has
it (Anthropic `tool_use`; OpenAI-style function calling), and the strict
**text tool protocol** where it does not — one sentinel-bracketed block
per call, parsed strictly. The text protocol's wire is TQ-3 and lands with
the OpenAI-compatible adapter (R6): at R1 the protocol is a declared value
an adapter may name, and the boundary refuses an adapter that names it,
because no parser exists to stand behind it.

This module is the capability's registry entry: its CONTRACT. The shape
both paths produce — a ToolSpec the runtime offers, a ToolCall the model
asks for, the tool protocols — is code in twine.runtime.terms, because
nothing outside this directory may import a capability module (the
registry must be able to report this one missing while every verb still
loads). The canonical tool surface itself (`shell`, `read_file`,
`write_file`, `list_dir`, `probe`, `escalate`, `deliver`) is R3's.
"""

from __future__ import annotations

from twine.runtime.contract import Contract

CONTRACT = Contract(
    capability="tool-calling",
    purpose=("The model asks for tools and gets their results, through one "
             "canonical tool surface (twine's own, R3) whatever the provider. "
             "Two paths sit behind the same boundary: native tool use where the "
             "provider has it, and the strict text tool protocol where it does "
             "not; only the adapter knows which path it is on."),
    adapter_must=(
        "declare exactly one tool protocol: `native` or `text` (twine.runtime.terms.TOOL_PROTOCOLS)",
        "translate each offered ToolSpec into the provider's tool form, and the "
        "provider's tool-call blocks back into ToolCall (id, name, arguments as a "
        "JSON object) — never passing a provider block through",
        "end a turn that asks for tools with no stop (stop None) and at least one "
        "ToolCall, every id unique within the turn",
        "on the text protocol, parse strictly — a block that does not parse is "
        "the `malformed-shape` stop, never a guessed call (TQ-3; R6)",
    ),
    runtime_promises=(
        "the boundary refuses a turn whose tool calls are not ToolCall tuples, "
        "lack an id or a name, or reuse an id",
        "a call to a tool that does not exist is returned to the model as a tool "
        "error, never a crash and never a boundary refusal (§4.3)",
        "an adapter declaring the text protocol is refused at the boundary until "
        "the parser exists (TQ-3, R6), rather than run without one",
    ),
    lands=("R1: the shape (ToolSpec, ToolCall), the boundary's checks and the fake "
           "adapter's native calls; R2: Anthropic `tool_use`; R3: the canonical "
           "tools; R6: the text protocol's wire and the OpenAI-compatible adapter"),
    grounds=("T6", "twine-seed.md §4.2", "Q-3", "TQ-3", "D17 (malformed_response)"),
)

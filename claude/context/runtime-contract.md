# The twine runtime contract

> What a model adapter implements, what the runtime promises it, how the
> runtime's capabilities are declared, and how a provider's usage becomes
> twine's. The sibling of `cli-contract.md`, which stays the verbs'
> (`twine runtime list` and `show` are its §17). Each line here is
> asserted by a test under `tests/` (`tests/test_runtime.py`) and by the
> landing session's `validation.sh`. Landed by session
> `2026-10-12-twine-runtime-registry-007` (Arc 2 R1). **§1 and §2 are
> proposals awaiting the architect's ratification**: §1 is Q-3's contract
> text ("the agent authoring Arc 2's first runtime session writes it, the
> architect ratifies"), §2 is TQ-2's file shape ("Arc 2's first runtime
> session proposes; the architect ratifies"). A later session that
> changes a line changes it here in the same response.

What exists after R1, and what does not: the registry, the boundary, the
fake adapter and `from_anthropic`. No adapter reaches a provider; nothing
calls a model; nothing appends to the spend stream; nothing under
`twine/` reaches a network or reads a key. R2 adds the Anthropic adapter
(the SDK as an optional extra inside it, the key), R3 the canonical tools
and the sandbox, R4 the loop (`twine run <bundle>`), R5 window
accounting's counting and cold resume, R6 the text tool protocol's wire
and the OpenAI-compatible adapter.

## 1. The adapter boundary (Q-3; proposed)

The code is `twine/runtime/boundary.py`, with the shapes it shares with
the adapters in `twine/runtime/terms.py` (§2.1). A **model adapter** is a class
that implements `Adapter`; the **boundary** (`Boundary`) wraps one
adapter for one session and holds every turn it returns to this contract
before the loop sees it. Q-3 names four things the boundary abstracts:
tool calling, thinking, usage accounting and the stop set. The first
three are capabilities (§2) every adapter behind the boundary implements
(`BOUNDARY_CAPABILITIES`); the stop set is the boundary's own.

### 1.1 The shape of a call

- An adapter declares three class attributes, read without constructing
  it: `name` (lowercase words joined by hyphens, unique among registered
  adapters), `implements` (a frozenset of capability names, each one the
  declaration lists, at least `tool-calling`, `thinking` and
  `usage-accounting`) and `tool_protocol` (`native` or `text`).
- It is constructed once per session, at spawn, with `SpawnSettings` —
  `model`, `max_tokens`, `thinking` — and keeps them (`settings`,
  read-only).
- `call(request) -> Turn` is its one method. `Request` is the
  conversation so far (a tuple of message objects — append-only, never
  edited in place; their shape is R4's) and the tools offered (a tuple of
  `ToolSpec`).
- A `Turn` is twine's, not the provider's: `text` (a string, `""` when
  none), `thinking` (a string or `None`), `tool_calls` (a tuple of
  `ToolCall`, `()` when none), `stop` (a key of the stop axis, or `None`),
  `usage` (a `twine.spend.Tokens`) and `provider_stop` (the provider's own
  word, kept for diagnosis; nothing dispatches on it).
- `call` raises only for the adapter's own fault (a broken transport, a
  usage it cannot read). A provider *outcome* — a refusal, a rate limit,
  the window's edge, an overload — is a `Turn` whose `stop` names it.

### 1.2 Tool calling

- **An adapter must** declare exactly one tool protocol; translate each
  `ToolSpec` into the provider's tool form and each provider tool-call
  block back into a `ToolCall` (`id`, `name`, `arguments` — a JSON
  object), never passing a provider block through; and end a turn that
  asks for tools with `stop` `None` and at least one call, each `id`
  unique within the turn.
- **The boundary promises** to refuse a turn whose tool calls are not a
  tuple of `ToolCall`, lack an id or a name, carry arguments that are not
  an object, or reuse an id. It does **not** refuse a call to a tool that
  does not exist: that is a tool error the loop returns to the model as a
  result, never a crash (§4.3 of the seed).
- **A turn does one thing.** It asks for tools (`stop` `None`, the
  worker's turn goes on — `Turn.continues`) or it stops (`stop` a key of
  the axis, no tool calls). A turn with both, or with neither, is
  refused.
- **The text tool protocol** is a declared value with a seam and no wire:
  its bytes are TQ-3, R6's. Until a parser exists the boundary refuses an
  adapter whose `tool_protocol` is `text`, naming TQ-3, rather than run it
  without one. When R6 lands the parser, a block that does not parse is
  the `malformed-shape` stop (D17's `respawn-from-request` move), never a
  guessed call.

### 1.3 Thinking

- **The model and the thinking settings are spawn-time constants**
  (D12). `SpawnSettings` and `ThinkingSettings` are frozen; no method of
  `Adapter` or `Boundary` takes a model or thinking argument, and none
  sets one. Changing either means a new session.
- `ThinkingSettings(enabled, budget_tokens)`: thinking on needs a
  positive integer budget below `max_tokens`; thinking off needs
  `budget_tokens` `None`. Incoherent settings are refused when built,
  before any spawn.
- **An adapter must** send the settings unchanged on every call, and map
  the provider's thinking blocks into `Turn.thinking`.
- **The boundary promises** to refuse a turn that carries thinking text
  from a session spawned with thinking off.

### 1.4 Usage accounting, and where usage goes

- **An adapter must** return every turn's usage as a `twine.spend.Tokens`
  — `input`, `output`, `thinking`, `cache_read`, `cache_write` — mapped by
  its provider's function in `twine/runtime/capabilities/
  usage_accounting.py` (§4), never the provider's object, and raise
  rather than guess when the provider's usage cannot be read.
- **The boundary promises** to refuse a turn whose usage is not a
  `Tokens` of non-negative integers (`thinking` also `None`) — the same
  rule the spend stream's reader applies, so a turn the boundary passes
  is a record the spine accepts.
- **Where usage goes:** the loop (R4) appends each turn's `Tokens` to the
  spend stream (`<state-dir>/spend.jsonl`, cli-contract §13) through
  `spend.append_record`, once per call, after the boundary passed it, and
  checks the cap (`spend.check_call`) before the next. R1 builds the
  mapping and the check; it appends nothing.

### 1.5 The stop set — one spelling

- **The boundary's stop set is the transition table's `stop` axis**:
  `share/transitions.toml`'s `[axis.stop] keys`, read through
  `twine.transitions.stop_keys()` when the boundary is built. It is
  spelled there and nowhere else; no module under `twine/runtime/`
  carries a stop key as a string, and a test holds them to that.
  `stop_keys` refuses (and the boundary with it) a table that cannot be
  read, has no `stop` axis, takes the axis's keys from anywhere but the
  table, or spells a catch-all key.
- **An adapter must** map its provider's stop words onto the axis. That
  mapping is the only place a provider's word becomes twine's: the
  boundary translates nothing, so a provider's word that reaches it
  (`end_turn`, `tool_use`, `max_tokens`) is refused, naming the stop and
  the axis. The exact provider names are verified against the SDK when an
  adapter is built (R2), never named here from memory.
- `cap-reached`, `cap-unchecked` and `killed` are keys of the axis that
  the loop, not a provider, produces (the cost spine, the kill-switch).
  The boundary accepts every key of the axis; an adapter that maps a
  provider word onto one of those three is a defect for review — the
  boundary does not police the subset, because naming it would spell
  stop keys a second time.
- Every key has a move in the table (D17: no default case), so a turn
  the boundary passes always stops with an outcome twine knows what to
  do with.

### 1.6 Refusals

A boundary refusal is a `BoundaryError` naming the adapter, the call
number and every fault (`faults`). It is an adapter defect, never a model
outcome; what the loop does with one is R4's to decide, and it will be a
row of the transition table. The boundary never retries, repairs or
translates a turn.

## 2. The capability registry (TQ-2; proposed)

The code is `twine/runtime/registry.py`; the verbs are cli-contract §17.
The runtime applies N5's rule to itself (T7, §4.1): every runtime
operation is a named capability with a declared contract.

### 2.1 The file shape

- **The declaration** is `twine/runtime/capabilities.toml`: one
  `[[capability]]` per capability, exactly four keys — `name`
  (lowercase, hyphenated), `module` (dotted, directly under
  `twine.runtime.capabilities` — `twine.runtime.capabilities.tool_calling`
  is `twine/runtime/capabilities/tool_calling.py` — importable as written
  and printed as written), `status` (§2.3), `summary` (one line). Its
  order is the order every renderer lists.
- **The modules** are `twine/runtime/capabilities/<name>.py`, one per
  capability, each exposing a module-level `CONTRACT`; `usage_accounting`
  also exports the provider mappings (`from_anthropic`, §4).
- **Nothing outside `twine/runtime/capabilities/` imports a capability
  module, and no capability module imports another.** The registry alone
  reaches them, by its guarded import, so a missing module is a
  `missing-module` problem `twine runtime list` names — never an import
  failure that takes `load_registry()`, and with it every verb, down. The
  shapes the boundary and the adapters need at import time — `ToolSpec`,
  `ToolCall`, `TOOL_PROTOCOLS`, `ThinkingSettings`, `token_faults` — are
  code in `twine/runtime/terms.py`, which is not a capability module.
  `tests/test_runtime.py` walks every module under `twine/` to hold this,
  and removes each listed module in turn on a copy of the tree: `runtime
  list` NOT OK, exit 1, that capability named; `runtime show` of it NOT OK;
  `twine commands` ok; every verb's `--help` exit 0. (Added after the HOLD
  of 2026-10-12, whose probe found `boundary.py` importing `thinking`.)
- **The contract object** (`twine/runtime/contract.py`, `Contract`):
  `capability` (the name it is the contract for — it must equal the
  declaration's), `purpose` (a paragraph), `adapter_must` (what an
  implementing adapter must do, one obligation per entry),
  `runtime_promises` (what the runtime promises in return), `lands`
  (which Arc 2 session implements it, and what exists now) and `grounds`
  (the seed entries it derives from). Every field non-empty. Data, not a
  docstring, so `show` renders it and a test checks it whole.
- **The adapters** declare which capabilities they implement — not the
  capabilities which adapters implement them. §4.1 reads both ways ("an
  adapter is a chosen set of them"); this side is chosen because the code
  that implements a capability lives in the adapter, and because R2 and R6
  each add an adapter: with the set on the adapter, a new adapter is one
  new module, and no capability module is edited (the same concurrency
  reason `twine/commands/` discovers its modules). Adapters are discovered
  by listing `twine/runtime/adapters/` (each module's `ADAPTERS` tuple);
  the registry derives every capability's `adapters` from their sets.

### 2.2 Parity, by name

The registry is ok exactly when every one of these holds; each failure is
a problem naming what is at fault:

| kind | names |
|---|---|
| `stray-module` | a module under `twine/runtime/capabilities/` the declaration does not list — by its module name |
| `missing-module` | a declared capability whose module is absent — by the capability |
| `unloadable-module` | a declared module that raises on import, with the exception |
| `no-contract` | a module without a `CONTRACT`, or whose `CONTRACT` is not a `Contract` |
| `contract-mismatch` | a `CONTRACT` naming another capability than the entry that points at it |
| `malformed-contract` | a `CONTRACT` with an empty field |
| `status-mismatch` | a status the adapters contradict (§2.3) |
| `unloadable-adapter` | an adapters module that raises on import or has no `ADAPTERS` |
| `malformed-adapter` | an adapter class the boundary cannot host (§1.1's attributes) |
| `duplicate-adapter` | two adapters under one name |
| `unknown-capability` | an adapter implementing a capability the declaration does not list |

A **malformed declaration** — unreadable, not TOML, no entries, a
top-level key other than `capability`, an entry with a missing or unknown
key, a bad name, a status outside the three, a module not directly under
`twine.runtime.capabilities`, a name or a module declared twice — is not a problem but a
refusal: `load_declaration` raises `DeclarationError` naming every bad
entry, as `twine.registry.validate_command` refuses a bad `Command`, and
the verbs report it NOT OK with that reason.

### 2.3 The statuses

A closed set of three:

| status | means | held to |
|---|---|---|
| `declared` | the contract is written; nothing implements it yet | no registered adapter implements it |
| `implemented` | at least one registered adapter implements it | at least one does |
| `experimental` | listed, never silently absent (§4.1) | either — the marker says the contract may still move |

### 2.4 The eight at R1

| capability | status | module (under `twine.runtime.capabilities.`) | lands |
|---|---|---|---|
| `tool-calling` | implemented (`fake`) | `tool_calling` | R2 Anthropic `tool_use`; R3 the canonical tools; R6 the text protocol |
| `thinking` | implemented (`fake`) | `thinking` | R2 Anthropic's parameters and blocks |
| `prompt-caching` | declared | `prompt_caching` | R2 |
| `window-accounting` | declared | `window_accounting` | R5 |
| `streaming` | declared | `streaming` | with the Anthropic adapter |
| `sandboxing` | declared | `sandboxing` | R3 |
| `suspend-resume` | declared | `suspend_resume` | after R4, with R5's cold resume |
| `usage-accounting` | implemented (`fake`) | `usage_accounting` | R2 calls `from_anthropic`; R4 appends |

Each declared capability's contract is written from the seed's §4.1 and
§4.3 so that the session implementing it implements a declaration rather
than inventing one; `twine runtime show <name>` renders it. `delegate`
(§4.5, the first experimental capability) is R8's and is not declared.

## 3. The fake adapter

`twine/runtime/adapters/fake.py`, registered as `fake`: a scripted
transport for twine's own tests (T8), implementing `tool-calling`,
`thinking` and `usage-accounting` with the `native` tool protocol. The
tests drive it, and nothing else in twine does (a test holds that no
module under `twine/` but its own names it).

**A script** is a list of turns, each an object:

| key | value | |
|---|---|---|
| `text` | a string | optional, default `""` |
| `thinking` | a string or `null` | optional, default `null` |
| `tool_calls` | a list of `{"id", "name", "arguments"}` objects, exactly those keys, `arguments` an object | optional, default `[]` |
| `stop` | a string, or `null` when the turn asks for tools | required |
| `usage` | `{"input", "output", "thinking", "cache_read", "cache_write"}`, exactly the five classes | required |

Any other key, or a value of the wrong type, refuses the script when it
is built (`FakeScriptError`, naming the turn and the key) — never at
playback. Each `call` plays the next turn and records the request it was
given (`requests`); a call past the script's end raises
`FakeScriptExhausted` instead of answering.

**What it cannot do:** reach a network, read a key, stream, cache, count a
window, choose or invent a turn — or map anything. Its stop mapping is the
identity, so a provider's word scripted where twine's belongs reaches the
boundary unmapped and is refused there (§1.5); its usage mapping is the
identity, since a script is already in twine's classes, and the counts are
judged by the boundary, not by the fake, so a test can script a bad count
and watch it refused.

## 4. Provider usage mappings

One pure function per provider in
`twine/runtime/capabilities/usage_accounting.py`, each held to a
recording under `fixtures/<provider>/` (fixtures/README.md, "Provider
recordings"). A mapping returns a `twine.spend.Tokens` or raises
`UsageMappingError` (a `ValueError`) naming the provider and every fault —
never a `Tokens` with a guessed number: a wrong fact is worse than a
missing one.

### 4.1 Anthropic — `from_anthropic(usage) -> Tokens`

From the Messages API's `usage` object, as recorded on 2026-10-08
(`fixtures/anthropic/messages-usage-2026-10-08.json`,
`claude-haiku-5-5`, which maps to `Tokens(input=18, output=4, thinking=0,
cache_read=0, cache_write=0)`):

| class | from |
|---|---|
| `input` | `input_tokens` — required |
| `output` | `output_tokens` — required — **less the thinking count when one is reported** |
| `thinking` | `output_tokens_details.thinking_tokens`; `None` when `output_tokens_details`, or `thinking_tokens` within it, is absent |
| `cache_read` | `cache_read_input_tokens`; `0` when absent |
| `cache_write` | `cache_creation_input_tokens`; `0` when absent |

- **Thinking is counted once.** The provider counts thinking inside
  `output_tokens`. `Tokens`' classes are disjoint ("tokens counted in
  `thinking` are not also in `output`") and `spend.record_cost` bills
  `thinking` on top of `output` at the output price (D20), so carrying
  `output_tokens` whole beside a reported thinking count would bill those
  tokens twice. When thinking is reported, `output` is `output_tokens -
  thinking_tokens`; when it is not, `thinking` is `None` and `output` is
  `output_tokens` whole — either way the call's cost is `output_tokens` at
  the output price. A thinking count above `output_tokens` cannot be
  inside it and is refused.
- **Refused:** `usage` not an object; `input_tokens` or `output_tokens`
  missing; any count the mapping reads that is not a non-negative integer
  — a float, a string, a boolean or `null` included; `output_tokens_details`
  present and not an object.
- **Ignored:** every other key — `service_tier`, `inference_geo`,
  `cache_creation`'s 5m/1h split (the spine has one `cache_write` class;
  the split is kept nowhere at R1), and any key the API adds later.
- Pure: the input is not modified, nothing is read or written.

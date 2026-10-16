# The twine runtime contract

> What a model adapter implements, what the runtime promises it, how the
> runtime's capabilities are declared, and how a provider's usage becomes
> twine's. The sibling of `cli-contract.md`, which stays the verbs'
> (`twine runtime list` and `show` are its §17). Each line here is
> asserted by a test under `tests/` (`tests/test_runtime.py`,
> `tests/test_anthropic.py`, `tests/test_runtime_tools.py`,
> `tests/test_run.py`, since R5 `tests/test_window.py` and
> `tests/test_resume.py`) and by the landing session's `validation.sh`. Landed by session
> `2026-10-12-twine-runtime-registry-007` (Arc 2 R1); §1 (Q-3) and §2 (TQ-2)
> were ratified as written on 2026-10-12. §5 and the lines of §1–§4 that say
> "R2" are session `2026-10-13-twine-runtime-anthropic-002`'s (Arc 2 R2). §6
> and the lines of §2 that say "R3" are session
> `2026-10-13-twine-runtime-tools-003`'s (Arc 2 R3). §7, §3's `retry_after`
> and `reason` and the lines of §1, §2 and §6 that say "R4" are session
> `2026-10-13-twine-runtime-run-004`'s (Arc 2 R4). §7.9 and the lines of
> §1–§7 that say "R5" are session `2026-10-13-twine-runtime-window-009`'s
> (Arc 2 R5), awaiting review. §6.3 (the cage), §6.4 (`filesystem`,
> `filesystem_reason`, `confines`), §6.7 (the hook under the PID namespace)
> and §7.7 (homes are pruned, by the verb) are session
> `2026-10-16-twine-sandbox-confine-001`'s. A later session that changes a
> line changes it here in the same response.

What exists after R4, and what does not: the registry, the boundary, the
fake adapter, `from_anthropic`, the Anthropic adapter (§5) — the first
code under `twine/` that reaches a network (through one module,
`twine/runtime/transport.py`) and reads a key (from the environment mapping
it is given) — since R3 the seven canonical tools and the per-sid sandbox
they run in (§6), the first code under `twine/runtime/` that starts a
process (through the run seam it is handed), and since R4 the loop (§7,
`twine/runtime/loop.py`; the verb is `twine run`, cli-contract.md §18): the
first code that calls a model on its own, runs the tools it asks for and
appends to the spend stream. R2 does **not** use the `anthropic` SDK
(§5.1). Since R5 the window is counted from each call's usage, warned in the
worker's tool results and an outcome at its edge (§7.4,
`twine/runtime/window.py`), `escalate` has its clarification form (§6.6),
and a kept session resumes cold from its transcript (§7.9,
`twine/runtime/resume.py`; the verb is `twine resume`, cli-contract.md §19).
R6 adds the text tool protocol's wire and the OpenAI-compatible adapter.

## 1. The adapter boundary (Q-3; ratified 2026-10-12)

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
  read-only). (An adapter's own constructor may take its settings as
  keywords and build the `SpawnSettings` itself, as the Anthropic adapter
  does, §5.7.)
- `call(request) -> Turn` is its one method. `Request` is the
  conversation so far (a tuple of message objects — append-only, never
  edited in place; their shape is R4's) and the tools offered (a tuple of
  `ToolSpec`).
- A `Turn` is twine's, not the provider's: `text` (a string, `""` when
  none), `thinking` (a string or `None`), `tool_calls` (a tuple of
  `ToolCall`, `()` when none), `stop` (a key of the stop axis, or `None`),
  `usage` (a `twine.spend.Tokens`) and `provider_stop` (the provider's own
  word, kept for diagnosis; nothing dispatches on it). Since R2, four more,
  each defaulting so an adapter without them (the fake) is unchanged:
  `content` (the assistant's content blocks exactly as the provider would
  want them back — what the next request's assistant turn carries, §5.6;
  `()` by default), `retry_after` (seconds a provider asked to wait, or
  `None`), `request_id` (the provider's id for the call, or `None`) and
  `reason` (a sentence saying why the turn stopped when it is not a plain
  end, or `None`). The boundary checks their types. Since twine-run-ergonomics
  two more, each `None` by default and neither in `Turn.as_json()`: `raw`
  (the response body as the transport drew it, headers aside — an adapter
  sets it only on a call that ended `malformed-shape`; the loop writes it,
  §7.6) and `cut_tool_call` (`{"id", "name", "partial_json"}` of a tool call
  the output ceiling cut off before its input was complete, §5.4).
- `call` raises only for the adapter's own fault (a broken transport, a
  usage it cannot read). A provider *outcome* — a refusal, a rate limit,
  the window's edge, an overload — is a `Turn` whose `stop` names it.
- **`context_window() -> WindowStatement`** (R5; `twine/runtime/terms.py`):
  the model's context window, stated once at spawn — window-accounting's
  first obligation, "state the model's context window size at spawn, or say
  it is unknown". `WindowStatement(size, reason)`: `size` a positive integer
  of input tokens or `None`; `reason` required when the size is unknown and
  `None` when it is known. `Adapter`'s default says unknown (the fake keeps
  it); the Anthropic adapter reads `GET /v1/models` (§5.7). The boundary's
  `context_window()` passes it through held to the shape: an adapter that
  raises, or answers with anything but a `WindowStatement`, is logged and
  read as unknown with the fault in the reason — never a crash at spawn, and
  never a refusal: an unknown window is counted and cannot warn or stop
  (§7.4). It is not a capability an adapter declares in `implements` (the
  window's accounting is the runtime's, §2.1).

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
- `ThinkingSettings(enabled, budget_tokens, adaptive)`: thinking on needs
  a positive integer budget below `max_tokens`, or `adaptive` (R2: on with
  no budget — the model decides; Anthropic's `{"type": "adaptive"}`, the
  only thinking the 5.x models accept besides off); thinking off needs
  `budget_tokens` `None` and `adaptive` false. Incoherent settings are
  refused when built, before any spawn.
- **An adapter must** send the settings unchanged on every call, and map
  the provider's thinking blocks into `Turn.thinking`.
- **The boundary promises** to refuse a turn that carries thinking text
  from a session spawned with thinking off. "Thinking text" is any string,
  the empty one included: an adapter reports thinking as present when the
  provider returned a thinking block, even one whose text is empty (§5.6).

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
- **Where usage goes:** the loop (R4, §7.4) appends each turn's `Tokens` to
  the spend stream (`<state-dir>/spend.jsonl`, cli-contract §13) through
  `spend.append_record`, once per call, after the boundary passed it and
  before anything else is done with the turn, and checks the cap
  (`spend.check_call`) before the next. R1 built the mapping and the check.

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
  the axis. The exact provider names were verified when the first adapter
  was built (R2): against the 2026-10-13 recordings, and against the SDK's
  `StopReason` literal (`anthropic` 1.13.0, read from its wheel: `end_turn`,
  `max_tokens`, `stop_sequence`, `tool_use`, `pause_turn`, `refusal`,
  `model_context_window_exceeded`) — the seven the mapping rows list.
- `cap-reached`, `cap-unchecked`, `killed` and `adapter-defect` are keys of
  the axis that the loop, not a provider, produces (the cost spine, the
  kill-switch, and — since the adapter-defect session — an adapter that broke
  the boundary's contract or raised, §1.6).
  Since R2 the table says so itself — `[axis.stop] loop_keys`, read
  through `twine.transitions.loop_keys()`, which refuses a table without
  them as `stop_keys()` refuses one without the axis — and **the boundary
  refuses a turn an adapter stops with a loop key**, naming it: an
  adapter's mapping never produces one. (R1 recorded the gap as a defect
  for review because naming the subset would have spelled stop keys a
  second time; the table's `loop_keys` is the one spelling.) The table's
  checker refuses a provider mapping onto a loop key too, so an adapter
  whose mapping would produce one does not start (§5.5).
- **Where a provider's words become twine's** (R2): the transition
  table's `[[mapping]]` rows, one per provider word, read through
  `twine.transitions.provider_mapping(<provider>)` (cli-contract §12.2).
  The adapter looks words up there; it spells no stop key.
- Every key has a move in the table (D17: no default case), so a turn
  the boundary passes always stops with an outcome twine knows what to
  do with.

### 1.6 Refusals

A boundary refusal is a `BoundaryError` naming the adapter, the call
number and every fault (`faults`). It is an adapter defect, never a model
outcome. R1 promised that what the loop does with one "will be a row of the
transition table"; R4's brief forbade new rows, so for a while the loop ended
the run `stopped` on one carrying neither a stop key nor a move. The row is now the
table's: **`adapter-defect`**, a loop key of the `stop` axis (§1.5) — the
loop reports it and no adapter may produce it — whose move is the operator's
**`fix-adapter`** (ruled at sitting 2026-10-13-open-milestone-2-006; not
`respawn-from-request`, whose actor is the planner and whose premise is a
malformed *response* — an adapter defect is twine's own bug and the planner
has nothing to decide about it). The loop (§7.4) ends the run `stopped` with
that stop, move and actor on a boundary refusal and on an adapter that
raises alike, the refusal or the exception quoted in the reason; nothing of
that call is in the spend stream. The boundary never retries, repairs or
translates a turn, and spells neither the key nor the move: it learns the
key only through the table's `loop_keys`.

## 2. The capability registry (TQ-2; ratified 2026-10-12)

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
  also exports the provider mappings (`from_anthropic`, §4), whose code
  lives in `twine/runtime/usage.py` since R2 (the adapter calls it, and
  may not import a capability module).
- **Nothing outside `twine/runtime/capabilities/` imports a capability
  module, and no capability module imports another.** The registry alone
  reaches them, by its guarded import, so a missing module is a
  `missing-module` problem `twine runtime list` names — never an import
  failure that takes `load_registry()`, and with it every verb, down. The
  shapes the boundary and the adapters need at import time — `ToolSpec`,
  `ToolCall`, `TOOL_PROTOCOLS`, `ThinkingSettings`, `token_faults` — are
  code in `twine/runtime/terms.py`, which is not a capability module; the
  provider usage mappings an adapter calls are code in
  `twine/runtime/usage.py`, for the same reason (R2).
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
- **The runtime's own capabilities** (R3). A capability the runtime
  implements itself, never an adapter — `sandboxing`: the cage is the
  runtime's, and an adapter must never run a tool — carries a fifth,
  optional key, `implemented_by`: the runtime module that implements it,
  dotted, directly under `twine.runtime` and not one of its packages
  (`capabilities`, `adapters`, `tools`); anything else refuses the
  declaration. That module lists the capability in a module-level
  `IMPLEMENTS` tuple, as an adapter lists its set (`twine.runtime.sandbox`:
  `IMPLEMENTS = ("sandboxing",)`; since R5 `twine.runtime.window`:
  `("window-accounting",)` and `twine.runtime.resume`: `("suspend-resume",)`
  — the window is counted and the conversation re-warmed by the runtime,
  whatever adapter is behind the boundary). `runtime list` prints it in each row as
  `implemented_by` (`null` for the rest). Why a key and not the loop as a
  pseudo-adapter: an adapter must implement the boundary's three and
  answer `call`, which a sandbox cannot, and a pseudo-adapter would put
  every runtime capability under a name `runtime list` prints beside
  `anthropic` and `fake` as if it were one.
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
| `missing-implementer` | (R3) an `implemented_by` module that does not import, or whose `IMPLEMENTS` does not list the capability |

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
| `declared` | the contract is written; nothing implements it yet | no registered adapter implements it, and it has no `implemented_by` |
| `implemented` | at least one registered adapter implements it — or, for a runtime capability, its `implemented_by` module does | at least one does; for a runtime capability, the module imports and lists it |
| `experimental` | listed, never silently absent (§4.1) | either — the marker says the contract may still move |

The status check is held, not loosened, for a runtime capability (R3):
`implemented` with an `implemented_by` that does not stand behind it is a
`missing-implementer` and a `status-mismatch`; `declared` beside an
`implemented_by` is a `status-mismatch`; and an adapter claiming a
capability that carries `implemented_by` is a `status-mismatch` naming it —
an adapter never implements a runtime capability.

### 2.4 The eight, at R5

| capability | status | module (under `twine.runtime.capabilities.`) | lands |
|---|---|---|---|
| `tool-calling` | implemented (`anthropic`, `fake`) | `tool_calling` | R2 Anthropic `tool_use` (landed); R3 the canonical tools (landed: §6 — the tools are the runtime's, the status the adapters'); R6 the text protocol |
| `thinking` | implemented (`anthropic`, `fake`) | `thinking` | R2 Anthropic's parameter and blocks (landed) |
| `prompt-caching` | implemented (`anthropic`) | `prompt_caching` | R2 (landed: §5.3) |
| `window-accounting` | implemented (the runtime: `implemented_by` `twine.runtime.window`) | `window_accounting` | R5 (landed: §7.4–§7.6 — the size from `--window` or the adapter's statement, §1.1; `used` counted from each call's usage; the warning at 80%; exhaustion before a call) |
| `streaming` | implemented (`anthropic`) | `streaming` | R2 (landed: §5.4) |
| `sandboxing` | implemented (the runtime: `implemented_by` `twine.runtime.sandbox`) | `sandboxing` | R3 (landed: §6) |
| `suspend-resume` | implemented (the runtime: `implemented_by` `twine.runtime.resume`) | `suspend_resume` | R5 (landed: §7.9 — `twine resume`, the conversation rebuilt from the transcript; §6.6 — escalate's clarification form) |
| `usage-accounting` | implemented (`anthropic`, `fake`) | `usage_accounting` | R2 calls `from_anthropic` (landed); R4 appends (landed: §7.4) |

At R1 three were implemented (the fake's) and five declared; R2 moved
`prompt-caching` and `streaming`; R3 moved `sandboxing`, implemented by the
runtime itself (§2.1); R5 moved `window-accounting` and `suspend-resume`,
implemented by the runtime too, and none is `declared` now.

Each capability's contract was written from the seed's §4.1 and §4.3
before the session implementing it, so that it implemented a declaration
rather than inventing one — R5's two unchanged but for `lands`; `twine
runtime show <name>` renders it. `delegate`
(§4.5, the first experimental capability) is R8's and is not declared.

## 3. The fake adapter

`twine/runtime/adapters/fake.py`, registered as `fake`: a scripted
transport for twine's own tests (T8), implementing `tool-calling`,
`thinking` and `usage-accounting` with the `native` tool protocol. The
tests drive it — and since R4 `twine run --adapter fake --script FILE`
(cli-contract §18), the loop run with no model, from the same script file
the tests write; the verb reaches it by name through the adapter registry
(`twine.runtime.loop.adapter_class`), so no module under `twine/` but its
own names its class (a test holds that).

**A script** is a list of turns, each an object:

| key | value | |
|---|---|---|
| `text` | a string | optional, default `""` |
| `thinking` | a string or `null` | optional, default `null` |
| `tool_calls` | a list of `{"id", "name", "arguments"}` objects, exactly those keys, `arguments` an object | optional, default `[]` |
| `stop` | a string, or `null` when the turn asks for tools | required |
| `usage` | `{"input", "output", "thinking", "cache_read", "cache_write"}`, exactly the five classes | required |
| `retry_after` | a number of seconds, or `null` — `Turn.retry_after` (R4: the loop's backoff reads it) | optional, default `null` |
| `reason` | a string, or `null` — `Turn.reason` (R4: the loop carries it) | optional, default `null` |

Any other key, or a value of the wrong type, refuses the script when it
is built (`FakeScriptError`, naming the turn and the key) — never at
playback. Each `call` plays the next turn and records the request it was
given (`requests`); a call past the script's end raises
`FakeScriptExhausted` instead of answering.

**What it cannot do:** reach a network, read a key, stream, cache, state a
window (its `context_window()` says unknown, R5 — a test names one with
`twine run --window N`), choose or invent a turn — or map anything. Its stop mapping is the
identity, so a provider's word scripted where twine's belongs reaches the
boundary unmapped and is refused there (§1.5); its usage mapping is the
identity, since a script is already in twine's classes, and the counts are
judged by the boundary, not by the fake, so a test can script a bad count
and watch it refused.

## 4. Provider usage mappings

One pure function per provider in `twine/runtime/usage.py` (since R2;
re-exported by `twine/runtime/capabilities/usage_accounting.py`, the
declaration's module, as the same objects), each held to a recording under
`fixtures/<provider>/` (fixtures/README.md, "Provider recordings"). A mapping returns a `twine.spend.Tokens` or raises
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
| `cache_read` | `cache_read_input_tokens`; `0` when absent or `null` (R2) |
| `cache_write` | `cache_creation_input_tokens`; `0` when absent or `null` (R2) |

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
  — a float, a string, a boolean or `null` included, except that the two
  cache counts read `null` as absent; `output_tokens_details` present and
  not an object.
- **`null` cache counts (R2).** R1 refused them ("the recordings never
  carry `null`"); R2's brief kept the refusal "unless the SDK's types say
  otherwise". They do: `anthropic` 1.13.0 types `cache_creation_input_tokens`
  and `cache_read_input_tokens` `Optional[int] = None` in both `Usage`
  (`types/usage.py`) and `MessageDeltaUsage` (`types/message_delta_usage.py`)
  — the SDK read from its wheel, never imported by twine. So `null` is a
  value the provider may send for them and reads as absent, `0`. The SDK
  types `input_tokens`, `output_tokens` and `thinking_tokens` as `int` in
  `Usage`, and those stay refused when `null`. (`MessageDeltaUsage` types
  `input_tokens` optional too: the stream reader keeps message_start's
  count when message_delta omits it, §5.4.)
- **Ignored:** every other key — `service_tier`, `inference_geo`,
  `cache_creation`'s 5m/1h split (the spine has one `cache_write` class;
  the split is kept nowhere at R1), and any key the API adds later.
- Pure: the input is not modified, nothing is read or written.
- **Held to the wire** since R2: every `usage` in the fifteen recordings of
  2026-10-13 maps — `thinking_stream`'s to `Tokens(49, 3, 30, 0, 0)`
  (`output_tokens` 33 less `thinking_tokens` 30), `cache_write`'s and
  `cache_read`'s to 2556 in `cache_write` and `cache_read`.

## 5. The Anthropic adapter (Arc 2 R2)

`twine/runtime/adapters/anthropic.py`, registered as **`anthropic`**,
implementing `tool-calling` (native), `thinking`, `usage-accounting`,
`prompt-caching` and `streaming`. It speaks the Messages API —
`POST https://api.anthropic.com/v1/messages`, headers `x-api-key`,
`anthropic-version: 2023-06-01`, `content-type: application/json` — over
the standard library, held to the fifteen recordings of 2026-10-13
(`fixtures/anthropic/`, §5.9) and tested with doubles built from their
bytes for what could not be recorded. Its tests are
`tests/test_anthropic.py`; the one live call is
`tests/test_anthropic_live.py`, gated (§5.10).

### 5.1 The transport seam

```
transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None)
    -> (status: int, headers: Mapping[str, str], chunks: Iterable[bytes])
```

One callable, handed to the adapter at construction (`transport=`).
`chunks` may split the body anywhere, byte by byte included; the readers do
not care where. A transport raises for a failure to talk — `TimeoutError`
for a socket timeout, `ConnectionError` or another `OSError` for the rest
(`TransportError`, a `ConnectionError`, wraps the stdlib's
`http.client.HTTPException`) — when called or while a chunk is drawn.

The real transport is `https_transport()` in **`twine/runtime/transport.py`,
the only place twine opens a socket**: `http.client` over `ssl`'s default
context, one connection per request, `read1` so a stream's events arrive as
sent, a socket timeout (600 s by default; the adapter's `timeout=`), no
retries, no redirects, no proxy. The adapter builds it when given no
transport. A test walks every module under `twine/` and finds `socket`,
`ssl`, `http`, `urllib.request` or a provider SDK imported by that file
alone. **The `anthropic` SDK is not used**: T9 permits it inside this
adapter, and R2 declines it — its retries and parsing would hide exactly
the paths the transition table owns. No module under `twine/` imports it.

### 5.2 The key

`ANTHROPIC_API_KEY`, read once at construction from the environment
mapping the adapter is **given** (`env=`; the module never reaches for the
process environment — a test walks it for `environ` and `getenv`).
Absent, empty or blank: construction refuses (`AnthropicConfigError`),
naming the variable, before any call. The key goes into the `x-api-key`
header and nowhere else: never into a `Turn`, an `Outcome`, a reason, an
exception message, a log line, a JSON twin, a `repr`, a transcript or a
fixture. Every reason the adapter writes is scrubbed of it besides (a
transport whose exception quoted it would be named `[ANTHROPIC_API_KEY]`).
The tests prove it with a sentinel key: sent in `x-api-key` on every call
and found in no `Outcome.as_json()`, `Turn.as_json()`, `str(exc)`, log
record (every `twine` logger at DEBUG) or stderr.

### 5.3 The request — `build_request`

```
build_request(*, model: str, max_tokens: int, system: str | None,
              messages: list[dict], tools: list[dict], thinking: dict | None,
              stream: bool = True) -> dict
```

Pure and keyword-only; an unknown keyword is a `TypeError`, a part of the
wrong shape a `RequestShapeError`. `messages` are API-shaped already (the
conversation's own blocks, §5.6); `tools` are canonical
`{name, description, input_schema}` objects, exactly those keys (R1's
`ToolSpec` becomes one through `tool_dict`; a server tool's shape is
refused). The body: `model`, `max_tokens`, `messages`, `stream`; `system`
as **a list of one text block** when given; `tools` when non-empty;
`thinking` only when given, **passed as given** (D12: a spawn-time
constant; which shape a model accepts is the provider's answer — the
2026-10-13 `/v1/models` recording shows `enabled` refused by every 5.x
model and `disabled` by Sonnet 5.5, Opus 5.5 and the Fable models; a 400 is
`request-refused`).

**Prompt caching** (D12): `cache_control: {"type": "ephemeral"}` on the
system block, on the **last** tool, and on the **last content block of the
last message** (a string content becomes one text block to carry it; a
last block that is a thinking block takes none) — three of the four
breakpoints the API allows. The stable-prefix discipline is the caller's:
the loop never edits a prior turn (§5.6).

**Never sent:** `stop_sequences`, `temperature`, `top_p`, `top_k`,
`metadata`, `tool_choice` (`auto` is the default, and forced tool use is
refused by the 5.5 models).

### 5.4 The readers — `read_response`, `read_stream`, and `Outcome`

```
read_response(status, headers, body: bytes) -> Outcome
read_stream(status, headers, chunks: Iterable[bytes]) -> Outcome
```

The adapter picks by `content-type`: `application/json` →
`read_response`, `text/event-stream` → `read_stream`; a non-200 is read as
an error whatever its type; a 200 that is neither is `malformed-shape`.

`read_response`: a status other than 200 is an error — the status row
decides (§5.5), the error body's `error.type` and `message` quoted whole in
the reason, `usage` null. A 200 must be a message: JSON, an object with
`content` (blocks of the four types below), `stop_reason` and a `usage`
`from_anthropic` reads; anything else is `malformed-shape` naming what is
wrong.

`read_stream`: server-sent events from chunks split anywhere (LF line
ends, a CR before one dropped); each event's `data` is **parsed as JSON**
— the recordings pad it with spaces inside the object, so a reader
comparing strings fails; `ping` and event types twine does not know are
ignored. The message is assembled from `message_start`,
`content_block_start`/`_delta`/`_stop` (`text_delta`, `thinking_delta`,
`signature_delta`, `input_json_delta` — the pieces joined and parsed at the
block's stop, `""` joined being `{}`) and `message_delta` — its
`stop_reason`, and its **usage over message_start's** (cumulative, final;
a count it omits or sends null keeps message_start's, as the SDK's
accumulator does) — and finished like a JSON message at `message_stop`. An
`error` event ends the stream: its `error.type` decides, no `message_stop`
expected. **Whether the stream ended is decided before any event is
judged** (the desk's ruling on the HOLD of 2026-10-13): an event is its
lines and the blank line after them, and its bytes are decoded only then;
an unterminated trailing event — a `data:` line with no blank line after
it, or half of one — is not an event but where the connection was cut, and
is never parsed. So a stream whose complete events never reach
`message_stop` (or an `error` event) is `network-failure` (`stream-cut`)
whatever trails it and whatever an earlier event looked like, the reason
naming how many complete events arrived; a transport exception mid-stream
is its own key (§5.5); both keep the usage reported so far. Only in a
stream that did end is an event that cannot be placed (a delta for no open
block, a delta of an unknown type, data that is not JSON or not UTF-8,
`message_stop` without `message_delta`) `malformed-shape`.

**The stop reason is taken before an open block is judged** (twine-run-ergonomics,
finding 2). A stream that reaches `message_stop` with a content block still
open and `message_delta`'s `stop_reason` `max_tokens` ended at the output
ceiling inside the block: it is the **`max-tokens`** turn (the table's
`continue-turn`), never `malformed-shape`. The closed blocks are the turn's
content as they are; an open `text` or `thinking` block is carried as far as
it got (a `thinking` block with no signature yet carries `""`); an open
`tool_use` block is carried only when the pieces of its input, joined,
parse as an object — otherwise it is **not** carried (a `tool_use` the API
would refuse is never sent back), its id, name and partial input going to the
`Turn`'s `cut_tool_call` and to the transcript's `turn` line under
`cut_tool_input` (§7.6), and its name into the turn's `reason`. With any other
`stop_reason` an open block at `message_stop` stays `malformed-body` as it
was. **The raw stream is kept on any `malformed-shape`**: the adapter remembers
the chunks the reader draws (or the body it joined) and, when the call ends in
the `malformed-body` condition — whatever the detail — hands them to the
loop on `Outcome.raw` and `Turn.raw`; the loop writes them to
`<state-dir>/transcripts/<sid>.call-<N>.raw` (mode 0600, `N` the call number;
`<sid>.call-<N>-<K>.raw` when a resumed run reaches a call number again, §7.6)
and names the file in the `turn` line's `raw` key (§7.6). No other outcome
keeps a byte, and the key is never in it: it is a response body. Text
and thinking deltas reach an `observer(kind, text)` as they arrive, when
the adapter is given one; an observer that fails is logged and dropped,
never failing the call (the streaming contract).

**`Outcome.as_json()`** — pinned; a dict with at least:

| key | value |
|---|---|
| `stop` | a key of the `stop` axis, or `null` when the turn asks for tools |
| `reason` | a sentence when `stop` is not `end-turn`/`null` — for a refusal, the provider's `error.type` and its `message` quoted whole, never dispatched on |
| `text` | the text blocks' text, concatenated in order (`""` when none) |
| `tool_calls` | `[{"id", "name", "arguments"}]`, `arguments` the parsed object (from `input`, or from the joined `input_json_delta` strings; `""` joined is `{}`) |
| `thinking` | `[{"thinking", "signature"}]` for `thinking` blocks and `{"data"}` for `redacted_thinking`, in order |
| `content` | the assistant content blocks exactly as the API would want them back — `text`, `tool_use` (`id`, `name`, `input`), `thinking` (`thinking`, `signature`), `redacted_thinking` (`data`) — in order, every key the API sent kept (§5.6) |
| `usage` | `from_anthropic(usage).as_json()` — the five classes — from the response's `usage`, or for a stream from the `message_delta` event's (over `message_start`'s); `null` on a refusal |
| `retry_after` | seconds from a `retry-after` header when present (an HTTP-date is not read: `null`, and the reason says so), else `null` |
| `request_id` | the `request-id` header when present |
| `raw_stop_reason` | the provider's `stop_reason` word, or the `error.type`, or the exception class — the untranslated fact beside the translation |

and beside them `status` (the HTTP status; `null` when no answer came) and
`usage_fault` (why a usage the provider did report cannot be read).

`Outcome.to_turn()` is the boundary's `Turn`: tool calls ride only on a
turn that continues; a call answered with no usage (an HTTP error, a
failure before any answer) bills nothing, so its usage is zero; a 200 whose
usage cannot be read raises `UnreadableUsage` (§1.4: raise rather than
guess) — the `Outcome` says `malformed-shape` either way.

### 5.5 The stop and error mapping

Two pure functions over the transition table's `[[mapping]]` rows for the
provider `anthropic` (`twine.transitions.provider_mapping`; the adapter
spells no stop key):

```
stop_key(stop_reason: str | None) -> str | None
error_key(status: int | None, error_type: str | None, exc: BaseException | None) -> str
```

| provider | twine `stop` | note |
|---|---|---|
| `stop_reason` `end_turn` | `end-turn` | |
| `tool_use` | `null` | the turn continues with tool results |
| `max_tokens` | `max-tokens` | |
| `refusal` | `model-refusal` | an HTTP 200; `stop_details` kept in `reason` when present |
| `model_context_window_exceeded` | `window-exhausted` | |
| `stop_sequence`, `pause_turn`, anything else | `malformed-shape` | twine sends no stop sequences and no server tools, so these are shapes it never asked for; `reason` names the word |
| HTTP 400 `invalid_request_error`, 401 `authentication_error`, 402 `billing_error`, 403 `permission_error`, 404 `not_found_error`, 409 `conflict_error`, 413 `request_too_large` | **`request-refused`** (new key) | twine's request or credentials are wrong; nothing is retried |
| 429 `rate_limit_error` | `rate-limited` | `retry_after` from the header when present |
| 529 `overloaded_error` | `overloaded` | |
| 500 `api_error` | **`provider-error`** (new key) | retried with backoff, like overload |
| 504 `timeout_error`; a socket timeout | `timeout` | |
| a connection error, a stream that ends before `message_stop`, an SSE `error` event you cannot classify | `network-failure` | |
| an SSE `error` event | by its `error.type` through the same rows (`overloaded_error` → `overloaded`, `api_error` → `provider-error`, `rate_limit_error` → `rate-limited`, the 4xx types → `request-refused`) | the stream was a 200; the error event is the stream's end and is classified first — no `message_stop` is expected after it |
| a 200 body that is not JSON or not SSE, a message without `content`/`stop_reason`/`usage`, a content block of a type not in (d), a usage `from_anthropic` refuses | `malformed-shape` | |

Any other HTTP status is `malformed-shape` with the status in the reason —
never a guess at a nearer key. Backoff itself is the loop's (R4): R2
classifies and surfaces `retry_after`.

How the rows carry it: `on = "stop_reason"` rows for the seven words,
`on = "status"` rows for the eleven statuses, `on = "error_type"` rows for
the eleven types (for SSE error events), and `on = "condition"` rows for
what no provider word names — `socket-timeout`, `connection-error`,
`stream-cut`, `unclassified-stream-error`, `unlisted-stop-reason`,
`unlisted-status`, `malformed-body` — each provider mapping all seven. An
HTTP error's **status** decides its key; its `error.type` is kept in the
reason. A word no row lists takes its condition's row ("anything else",
"any other HTTP status" — named rows, not a default case). `error_key`
refuses (`ValueError`) a call with nothing to classify, and both raise
`TableError` when the table cannot stand behind the mapping — as does the
adapter's construction (`AnthropicConfigError`), so an adapter whose
mapping would produce a loop key never starts.

### 5.6 The conversation: append-only, and the thinking-block rule

The adapter's conversation state is the API's own blocks, kept as
received (D12): the assistant blocks of every turn exactly as the API sent
them — **every key**, `caller` on a `tool_use` included (the 2026-10-13
`tool_result` request carries it back and the API takes it) — and tool
results as `tool_result` blocks (`tool_use_id`, `content`, `is_error: true`
when the tool failed — the `tool_result_error` recording shows the model
reads it and answers about the failure). **The API rejects a modified or
dropped thinking block**: a `thinking` block's `thinking` and `signature`,
and a `redacted_thinking` block's `data`, go back byte for byte, in place.
`assistant_message`, `tool_result_message` and `Conversation` build these;
the tests reproduce the `tool_result` and `tool_result_error` requests'
`messages` from the `tool_use` recording's parsed content plus the result,
exactly. On the boundary's path the adapter refuses (`ConversationEdited`)
a `Request` whose messages do not extend the ones it sent last.

A turn carrying any `thinking` or `redacted_thinking` block counts as
thinking (`Turn.thinking` is their text joined — `""` for the
`thinking_stream` recording's empty one), so a session spawned with
thinking off is refused such a turn at the boundary (§1.3).

### 5.7 The adapter — `AnthropicAdapter`

`AnthropicAdapter(env=..., transport=..., **settings)`, constructible with
`env` and `transport` alone. Settings, each a spawn-time constant (D12):
`model` (`claude-haiku-5-5`), `max_tokens` (16000), `thinking`
(`{"type": "adaptive"}`; `None` sends none; `enabled` with its
`budget_tokens`, `disabled` — any other shape refuses, since the boundary
must know whether thinking is on: `ThinkingSettings` adaptive, budgeted or
off), `system` (`None`), `stream` (`True`), `timeout` (the real
transport's), `observer` (streamed deltas), `table` (a test's transition
table). Incoherent settings refuse at construction (`AnthropicConfigError`).

`adapter.call(body: dict) -> Outcome` runs one request through the
transport and reads the answer by content type. `adapter.call(request:
Request) -> Turn` is R1's `Adapter.call`, the boundary's path: the
request's messages (append-only, §5.6) and tools, the spawn-time
constants, `build_request`, one call, `Outcome.to_turn()`.

**`adapter.context_window() -> WindowStatement`** (R5, §1.1): one `GET
https://api.anthropic.com/v1/models` through the transport seam — headers
`x-api-key` and `anthropic-version`, no body, no query (one page, as the
2026-10-13 `models` recording was taken) — read by
`read_models_window(status, headers, body, model)`, pure: the entry whose
`id` is the model, its `max_input_tokens` (1000000 for every 5.x model in
the recording, 200000 for `claude-opus-4-5-20251101`). Unknown, the reason
saying why, for an HTTP error (`error.type` and `message` quoted), a body
that is not the JSON listing, a model the page does not list (and whether
the page says `has_more`, which twine does not follow), an entry without a
positive integer count, and a transport that fails. The answer is **held per
adapter**: a second ask answers from the first, so a spawn costs one call
(`window_calls`); the verb asks once, at spawn, and only when `--window` does
not fix the size. Reasons are scrubbed of the key as every reason is. One method takes
both because both are pinned (the brief's `call(body)` and R1's
`call(request)`); `send(body)` and `turn(request)` are the two halves by
name. Neither ever raises for a provider outcome or a transport failure —
both are outcomes with a stop; it raises for the caller's fault (a body
that is not JSON, an edited conversation) and for an unreadable usage.

### 5.8 What it does not do

No retries or backoff (R4's), no appending to `spend.jsonl` (R4's), no
tools' bodies or sandbox (R3's), no window counting — it states the size
(§5.7) and reports usage; the count is the runtime's (§7.4, R5) — no server
tools, batches, files, citations, structured outputs, `tool_choice` or
`output_config`, no SDK, no proxy.

### 5.9 The recordings, and their lander

The paste-back of probe `twine-anthropic-record` (the architect, his own
key, 2026-10-13T00:43:12Z, `claude-haiku-5-5`) is carried at
`fixtures/anthropic/carried/twine-anthropic-record-2026-10-13.txt` (29,039
bytes LF; received CRLF, 29,240) and landed by
**`bin/twine-land-provider-recordings PASTE [--check] [--tree DIR]`**, the
sibling of `bin/twine-land-recordings`: per `== rec <name>` it decodes the
`request-b64gz`/`response-b64gz` streams, verifies each against its
printed sha256 and byte count, and writes `<name>.request.json`,
`<name>.response.json` or `.sse` (by `content-type`) and `<name>.meta.json`
under `fixtures/anthropic/`; `--check` verifies a landed tree and its
`fixtures/README.md` rows and writes nothing. fixtures/README.md,
"Provider recordings", is the rule and the rows.

### 5.10 The live smoke test

`tests/test_anthropic_live.py`: the `text` call against
`claude-haiku-5-5`, non-streamed and streamed, through the real transport
and the boundary — skipped unless `TWINE_LIVE_SMOKE=1` **and**
`ANTHROPIC_API_KEY` is set. It never runs under bale (network off, T8); the
architect runs it by hand.

## 6. The tools and the sandbox (Arc 2 R3)

The canonical tool surface (T6, §4.2 of the seed) and the cage the
workers' tools run in (§4.3, "Sandbox"). The code is
`twine/runtime/tooling.py` (what a tool and a result are, the declaration
and its parity, the argument check, `run_tool`), `twine/runtime/tools.toml`
and `twine/runtime/tools/` (the seven), and `twine/runtime/sandbox.py`; the
verb is `twine runtime tools` (cli-contract §17.6); the tests are
`tests/test_runtime_tools.py`, real processes throughout and no model. Since
R4 the loop calls them (§7.4), through `run_tool`, in the sandbox `twine run`
makes.

### 6.1 The declaration, and parity by name

`twine/runtime/tools.toml` declares the tools the way `capabilities.toml`
declares the capabilities (§2): one `[[tool]]` per tool, exactly three keys
— `name` (lowercase words joined by `_`, as the model is offered it),
`module` (dotted, directly under `twine.runtime.tools`), `leaves_cage` (a
boolean) — in the order every renderer lists them and the loop offers them.
Each module under `twine/runtime/tools/` exposes a module-level **`TOOL`**
(`twine.runtime.tooling.Tool`): its `spec` (R1's `ToolSpec` — `name`,
`description`, `input_schema`), `leaves_cage`, its `result_keys` (§6.2),
the `error_defaults` an error result carries for them, and its executor.
Why a declaration beside `TOOL` rather than a `TOOLS` tuple per module
discovered like `COMMANDS`: parity needs two sides — a discovered tuple is
its own declaration and could never be found missing — and what leaves the
cage is the one fact a reviewer must read without opening code, so it is
declared where the reviewer reads, and the registry holds the module's
`TOOL` to it.

The registry (`load_tool_registry`) is ok exactly when every one of these
holds; each failure is a problem naming what is at fault:

| kind | names |
|---|---|
| `stray-module` | a module under `twine/runtime/tools/` the declaration does not list — by its module name |
| `missing-module` | a declared tool whose module is absent — by the tool |
| `unloadable-module` | a declared module that raises on import, with the exception |
| `no-tool` | a module without a `TOOL`, or whose `TOOL` is not a `Tool` |
| `tool-mismatch` | a `TOOL` whose spec names another tool than its entry |
| `malformed-tool` | a `TOOL` not whole: an empty description, an input schema outside the subset (§6.2), result keys that repeat a base key, `error_defaults` not covering exactly the result keys |
| `cage-mismatch` | a `TOOL.leaves_cage` that disagrees with the declaration |

A malformed declaration (unreadable, not TOML, no `[[tool]]`, a top-level
key other than `tool`, an entry with a missing or unknown key, a bad name, a
module not directly under `twine.runtime.tools`, a `leaves_cage` that is not
a boolean, a name or module declared twice) is refused (`DeclarationError`,
every bad entry named), as §2.2's is. The registry reaches the modules by its
own guarded import, so a missing one is a named problem and never an import
failure that takes a verb down.

### 6.2 The seven, their inputs and their results

Every input schema is JSON Schema with `type: object` and
`additionalProperties: false`, written in a **subset** `tooling.py` checks
without a dependency (T9): `type` (object, string, integer, number, boolean,
array), `properties`, `required`, `additionalProperties: false`, `items`,
`minItems`, `maxItems`, `minLength`, `exclusiveMinimum`, `description`. A
schema using anything else is a `malformed-tool`, so no call is waved
through a keyword nobody checks. (Since R5 `escalate`'s `questions` has no
`maxItems`: the light form's count of three is the executor's, the
clarification form takes more.) Every spec passes R2's `tool_dict` and
`build_request` unchanged (a test sends all seven).

| tool | input | leaves the cage |
|---|---|---|
| `shell` | `command` (string, run by `bash -c`); optional `timeout` (seconds, > 0, capped by the sandbox's maximum, which is also the default) | no |
| `read_file` | `path` | no |
| `write_file` | `path`, `content` (UTF-8 text; parents created; an existing file replaced, a directory refused) | no |
| `list_dir` | `path` (default `.`, the home) | no |
| `probe` | `block` (a probe block in bale's shape — the fence included — as text) | **yes** (§6.5) |
| `escalate` | `questions`: objects, each `question`, `while_doing`, `would_assume`, `why_blocked` (non-empty strings) — one to three, one line each, for the light form; one or more with `blocking: true`; optional `blocking` (boolean, default false: R5's clarification form) | no (§6.6) |
| `deliver` | `tarball` (a path inside the home) | no |

Every tool returns a **`ToolResult`**; `as_json()` is `name`, `content` (a
string: what the model reads back), `is_error` (a boolean), then the tool's
pinned keys, in this order:

| tool | beyond `name`, `content`, `is_error` |
|---|---|
| `shell` | `exit_code` (int, or `null` when killed), `stdout`, `stderr` (decoded UTF-8, an undecodable byte replaced by U+FFFD; both whole — the cap on what the model reads, below, is on `content` alone), `timed_out`, `stdout_capped`, `duration_seconds` (`null` when nothing ran) |
| `read_file` | `path` (as resolved, relative to the home), `size` (bytes) |
| `write_file` | `path`, `size` (bytes written) |
| `list_dir` | `path`, `entries` — `[{name, kind, size}]`, sorted by name; `kind` from the entry itself, never followed: `file`, `dir`, `link` or `other`; `size` a file's bytes, `null` for the rest |
| `probe` | `slug`, `leaves_cage` (always `true`), `exit_code`, `lines` (the integrity trailer's count) |
| `escalate` | `kind` (`"light"`, or since R5 `"clarification"`), `suspend` (`true`; `false` on an error), `questions` (the count), and since R5 `path` (the clarification response tarball, relative to the home) and `sha256`, and since twine-run-ergonomics `block` (the exchange paste block, §6.6) — all three `null` on the light form and on an error |
| `deliver` | `delivered` (`true`; `false` on an error), `path`, `size`, `sha256` |

An error result carries the same keys, those the tool could not know `null`
(`entries` `[]`). A call that reached no tool — an unknown name, a tool that
cannot load — carries the three base keys alone.

**A tool error is a result, never an exception** (§4.3 of the seed: "tool
error (returned as a result, never a crash)"). `run_tool(sandbox, name,
arguments) -> ToolResult` never raises: an unknown name (the result names
the seven), arguments the schema refuses (each fault named: a missing
argument, an unknown one, a wrong type, a bound), a path outside the cage, a
missing file, non-UTF-8 bytes, a file over the read cap, a timeout, the
stdout cap, a spawn the kill-switch cannot stand behind, a tool that raised
(logged with its traceback; the result names the exception) — each is
`is_error: true` with a sentence naming the fault. **A command that exits
non-zero is not a tool error**: `shell`'s result carries the exit code,
stdout and stderr, and `is_error` is false. The loop (R4) hands `content`
and `is_error` to the adapter's `tool_result` block (§5.6) as they are.

**`shell`'s `content`**: stdout; then, when there is any, stderr
under a `[stderr]` line; then one bracketed line saying how it ended —
`[exit N]`, `[exit -N: killed by SIGNAME]`, `[killed: timed out after Ts; the
command and its children were stopped]` or `[killed: stdout passed 262144
bytes; …]` — and `[stderr cut at 65536 bytes]` when the seam truncated it.
**What the model reads back of stdout is at most 32768 bytes (32 KiB)**
(twine-run-ergonomics, finding 4: the model carries every byte it reads
through every later call): cut on a character boundary and marked, on a line of
its own, `[stdout cut at 32768 bytes of <total>; read it in parts]`, `<total>`
the bytes there were. Stderr's share in `content` is cut the same way at the
same number, its marker naming `stderr`
(`[stderr cut at 32768 bytes of <total>; read it in parts]`). **The command is
not stopped at that point**: it runs to its end, its timeout or the seam's own
stdout cap — **262144 bytes (256 KiB)**, `carry probe`'s number (cli-contract
§10.3), past which the group is killed, the result is an error and the exit
line says so, as before; `is_error` stays false for a command that completed;
and the result's `exit_code`, `stdout`, `stderr` and `stdout_capped` fields
and the transcript's 64 KiB clip are as they were. `read_file` refuses a file
over 256 KiB (read it in parts with `shell`) — untouched. The 256 KiB figures
were R3's choice, not the brief's; the 32 KiB is the model's.

### 6.3 The sandbox and the cage

`Sandbox.create(state_dir, sid, *, repo, run=twine.process.run_process,
env=None, max_timeout=600)` makes one sandbox per sid. Its **home** is
`<state-dir>/sandbox/<sid>/home/`, created mode 0700 with `tmp/` inside it,
and reused when it exists (a session's files survive its runs). Refused at
creation (`SandboxError`): a sid twine would not name a file by
(`twine.kill.is_sid`), a `repo` that is not a directory, a `max_timeout`
that is not a positive finite number, a home that cannot be made, an `env`
that does not map names to strings, and a running record that cannot be
read (§6.7).

**The cage rules** (`Sandbox.resolve`), every file tool's path through them:
the path is a non-empty string relative to the home; **an absolute path** is
refused (one pointing inside the home too — the tools speak relative
paths); **a `..` component** is refused wherever it stands; and the path is
resolved, symlinks followed, and **refused when it lands outside the home**
— a symlink pointing out, a symlinked directory leading out. Each refusal is
a tool error naming the cage (the home's path). A symlink that stays inside
is followed, and the result reports the resolved path. A NUL byte is
refused. A residual, named below.

**What is confined: the cage** (twine-sandbox-confine, 0.27.0). The file
tools are path-confined, above. `shell` — and the clarification form's
crafter and lint (§6.6), which run through the same runner — runs **in a
user, network, mount and PID namespace**: `unshare -rnmpf --kill-child`
around a short `sh` script (`CAGE_SCRIPT` in `twine/runtime/sandbox.py`,
every path an argument, none spliced into its text) that builds a private
root in tmpfs on `<state-dir>/sandbox/<sid>/root/` (an empty directory made
beside the home) and pivots into it. What the command sees:

- **the home, writable, at its own absolute path** — `HOME`, `TMPDIR`, the
  working directory and every path a transcript shows stay true. It is the
  only writable tree the cage has besides an empty private `/tmp`, a private
  `/dev/shm` and the cage's own `/dev`'s ordinary devices (`null`, `zero`,
  `full`, `random`, `urandom`, `tty`, `fd`, `stdin`, `stdout`, `stderr`);
  `/`, `/dev` itself, `/usr`, `/bin`, `/sbin`, `/lib*` and the `/etc` files
  are read-only;
- **what bash, python3, tar, git and coreutils need, read-only**: `/usr`,
  `/bin`, `/sbin`, `/lib`, `/lib32`, `/lib64`, `/libx32` bound recursively
  (symlinks of a merged `/usr` recreated as symlinks) and these `/etc`
  entries copied, those that exist: `ld.so.cache`, `ld.so.conf`,
  `ld.so.conf.d`, `passwd`, `group`, `nsswitch.conf`, `hosts`, `localtime`,
  `timezone`, `alternatives`, `gitconfig`, `os-release`, `mime.types`. A
  call can name more (`Sandbox.spawn(readonly=…)`): `escalate` names the
  interpreter twine runs on — `sys.prefix`, `sys.base_prefix` and the
  directory it is started from — and the sandbox drops what the system
  directories already show, so a pyenv or a virtual environment under the
  operator's home is shown, read-only, at its own path, and nothing else of it
  is;
- **nothing else of the host**: not the operator's home outside the sandbox
  home, not `/mnt`, `/media`, `/run` or `/sys`, not the host's `/tmp`, not
  the repository the session was opened in, not the state directory beyond
  the home — the directories on the way to the home exist, empty but for the
  way to it and read-only, so its absolute path resolves (they are a small
  tmpfs of the cage's own, made at the shallowest of them the private root
  lacks and remounted read-only once the home is bound; a state directory
  under the host's `/tmp` puts that tmpfs inside the cage's private `/tmp`,
  which stays writable beside it);
- **`/proc` the cage's own**: a fresh procfs of the new PID namespace; no
  host process is visible, and the command is the namespace's init (`$$` is
  1);
- **no network**, as before (§6.4);
- **no way to undo it**: `CAP_SYS_ADMIN` and `CAP_SYS_CHROOT` are dropped from
  the command's bounding set (and `no_new_privs` set), so it can neither
  mount nor chroot. The cage's user is the operator, mapped to root inside the
  user namespace (`-r`): the files it makes in the home are the operator's.

**When a call returns, no process it started is alive.** The command is the
PID namespace's init; when it exits the kernel kills every other process of
the namespace, whether it was backgrounded, left the process group or called
`setsid`. The same holds when the seam kills the run (a timeout, the stdout
cap) or `twine kill` does (§6.7).

**The setup**, in order, each step named on stderr if it stops the script
(`twine cage: stopped while <step>`): the tmpfs root; `/tmp`; a fresh `/proc`;
`/dev`; the system directories and named read-only trees (each `--rbind`ed,
then the mount and every submount under it remounted read-only — a
non-recursive bind of a tree with locked submounts is refused in a user
namespace, and a recursive one leaves them writable); the `/etc` copies (a
copy that fails is skipped — an absent `/etc` entry, never a failed cage); the
home (a read-only tmpfs for the way to it, then `--rbind` at its own path); the
root remounted read-only; `pivot_root`
into it with the old root detached (`chroot` where `pivot_root` is refused —
a chrooted bale, an unusual root — the capabilities above dropped the same);
the working directory; the command. The mount namespace is private: nothing
the cage mounts reaches the host.

**Honest when it cannot.** At creation the sandbox runs the whole cage on
`true` through the seam (§6.4). Where the namespaces cannot be made — no
`unshare`, a refusal (no unprivileged user, mount or PID namespaces), a
timeout, a setup step that fails — the sandbox runs as it did at R3 (`shell` is
cwd'd in the home and not confined to it: a command can `cd /` and read or
write whatever the operator's user can) and **says so**: `filesystem:
"unconfined"` with a `filesystem_reason`, exactly as the network rule does,
never silently (§6.4). A model that is told the filesystem is unconfined is
told the truth; one that is told it is confined has it.

**Residuals, named.** The check and the open of a file tool are two steps, so
a process racing them could swap a component for a symlink in between; the
only process that could is the worker's own `shell`, which can still make a
symlink inside the home — one pointing out lands, in the cage, on a path that
is not there. `/proc` is the namespace's
own, but its `sys` tree and the kernel's other ordinary files are as visible
to a user-namespace root as to any user. The copies of `/etc` files are
snapshots taken at each call. A host that mounts something under a system
directory shows it, read-only, in the cage. `probe` leaves the cage by design
(§6.5): unchanged.

### 6.4 The environment, the network rule and `confines`

**The environment** is minimal: `PATH`, `HOME` (the home), `TMPDIR` (its
`tmp/`) and `LANG`, and nothing else the sandbox was not told to pass. By
default `PATH` and `LANG` are inherited **by name only**, through
`twine.process.inherited_environment` (no module under `twine/runtime/`
touches the process environment, a test holds it); when unset they fall
back to `/usr/local/bin:/usr/bin:/bin` and `C.UTF-8`. `env=` replaces the
inherited pair with what the caller passes; `HOME` and `TMPDIR` are always
the sandbox's. **`ANTHROPIC_API_KEY` never reaches the cage**: it is never
inherited, and when a caller passes it, it is dropped and the drop logged
(by name, never the value). A test sets a sentinel key in the parent and
runs `env` in the cage.

**Detection.** At creation the sandbox runs the **whole cage on `true`**
through the run seam (`unshare -rnmpf --kill-child`, the setup script, then
`true` — registered like any spawn, §6.7). When it exits 0 both rules hold: the
network is off and the filesystem confined, and every argv the sandbox's runner
runs is wrapped (§6.3): **`network: "off"`, `filesystem: "confined"`**. When it
does not — `unshare` cannot start, it exits otherwise, it times out, a setup
step fails — each half is tried alone, the network as `unshare -rn true`
(`-rn -- <argv>`: a new user namespace, so no privilege is needed, mapping the
operator to root inside it; a new network namespace with only a loopback,
down) and the filesystem as the cage without `-n` (`unshare -rmpf
--kill-child`), and the sandbox keeps what works: **`network:
"unconfined"`** with `reason`, and/or **`filesystem: "unconfined"`** with
`filesystem_reason`, each the failing step's own message (`unshare` missing, a
refusal's stderr, the timeout, or the cage's `twine cage: stopped while …`
line). Where each half works alone but not together the network is off and the
filesystem unconfined, the whole cage's failure the reason.

**`confines`** — cli-contract §10.5's switch, made: the sandbox's runner,
`SandboxRunner`, a wrapper around the runner the sandbox was handed (the
default one unless a test hands its own), declares `confines` **true exactly
when the network is off and the filesystem is confined**; the sandbox reads it
back through `twine.process.runner_confines` and nothing else sets it. A
sandbox whose filesystem is unconfined does not confine, whatever its network.

**`Sandbox.as_json()`**: `sid`, `home`, `repo`, `network`, **`filesystem`**,
`confines`, `max_timeout`, then `reason` when the network is unconfined and
**`filesystem_reason`** when the filesystem is (each absent when its half is
confined). The transcript's `run-start` line carries it as `sandbox`; `twine
run`'s and `twine resume`'s twin carries `filesystem` right after `network`
(cli-contract §18.5), and their stderr line says both.

### 6.5 What leaves the cage, and why: `probe`

Exactly one tool leaves the cage, and the declaration says so. **`probe`**
(D13: it "closes the paste-back hop") runs a probe block against **the real
repository** — the sandbox's `repo`, its working directory — and returns the
paste-back. It reuses `twine carry probe`'s machinery
(`twine/probing.py` — a module that is neither a command nor the CLI, so
nothing under `twine/runtime/` imports `twine.cli` or a `twine.commands`
module; the helpers lived in `twine/commands/carry.py` until session
`2026-10-13-twine-housekeeping-probe-008`), not a copy of it: the block found by
`twine.shapes` (exactly one probe block, `choose_block`), held to the same
readiness rules (`check_block_ready` — intact, no unfilled `TODO(worker)`, a
`# Read-only:` header line; split out of `check_ready` at R3), run by
`run_probe` (bash through the seam, `carry probe`'s 300-second timeout, at
most the sandbox's maximum, and its 256 KiB cap) and verified by
`verify_output` (exactly one intact `probe-output` block of the probe's
slug). `run_probe` takes a seam — the run seam, `which`, `env` and `info` —
not a `Context`: the tool builds a `probing.Seam` over the sandbox's runner,
the cage's `PATH` and the cage's environment, and logs the lines it collects.
`content` is that block — BEGIN through END, the paste that closes
the hop — and a test reads it back with `twine.shapes`.

It runs through the sandbox's **unwrapped** runner, not the cage's: the
network and the filesystem are the operator's, as §10.5 says of `carry
probe`. Confinement is the read-only declaration's and the operator's; R3
does not pretend otherwise, and says `leaves_cage: true` on every result. Two
things it does that `carry probe` does not: the script gets **the cage's
minimal environment**, so it never sees `ANTHROPIC_API_KEY` or anything
else of the operator's (a model-authored script that could print the key
into its paste-back must not have it); and its process group is registered
with the kill-switch (§6.7).

### 6.6 `escalate` and `deliver`

**`escalate`** wraps bale's shape, never a fork (D13 as annotated): the light
question block (TARBALL.md §5.10) — `=== LIGHT BEGIN <sid> ===`, per
question the four-label rows (`[n] question:`, `while doing:`, `would
assume:`, `why blocked:`), `Reply: answer inline, "as assumed", or
"formal".`, `=== LIGHT END <sid> ===`, the sid the sandbox's. Before it is
returned it is read back with `twine.shapes`: exactly one `light` block,
intact, for the sid, its rows the ones given — or the call is an error. One
to three questions (admission is a count); a fourth, none, a field empty or
not one line is an error (a fourth names the clarification form). The result
is the block as `content`, `kind: "light"`, `suspend: true`, `path` and
`sha256` null — the loop stops the worker's turn and carries the block.

**The clarification form** (R5; `blocking: true`; TARBALL.md §5.9): one or
more questions — the light tier's count of three does not bind; the
clarification response's schema does (`questions[]` non-empty, each row the
four fields, none empty; a row may span lines). The tool **writes the
clarification response tarball** in the home and names it, wrapping bale's
shape and never forking it (D13):

1. **the crafter**, request-carried, scaffolds the response directory: in
   the cage through the sandbox's runner (the cage's environment, network
   off and the filesystem confined where they can be, registered with the
   kill-switch, the home its working directory, the interpreter's own tree
   shown read-only when it is not under a system directory), on the
   interpreter twine runs on —
   `<python> -I -B request/tools/craft_response.py
   escalations/<k>/response-NNN --sid <sid> --kind clarification
   --questions N --write`: the manifest skeleton and the crafter's `apply.sh`
   and no-op `validation.sh`. A request without the crafter, a crafter that
   exits non-zero, or a skeleton that is not a clarification with N rows is
   an error naming it;
2. **the judgment fields** are filled from the arguments: each row's
   `question`, `context` (`while_doing`), `default_assumption`
   (`would_assume`) and `why_blocked`, and `summary` — what the session was
   asked to do (the request manifest's `goal`) and that it is blocked on the
   questions;
3. **the lint**, request-carried (`request/tools/response_lint.py <dir>
   --json`), judges it the same way, when the request carries it: a finding
   is an error naming each (`code: message`); a request without it is said
   in `content` and logged, and the dry run judges alone;
4. **the tarball**, as a response tarball is built (TARBALL.md §5.1, one
   top directory `response-NNN/`, NNN the sid's counter):
   `escalations/<k>/response-<sid>.tar.gz` (§10.1 step 11's name), `k` the
   first number not taken, so every round of a session's escalations is
   kept;
5. **the paste block** (twine-run-ergonomics): TARBALL.md §5.9.2's second
   transport — the same record for a courier who pastes — rendered by the
   request-carried crafter in the cage, `<python> -I -B
   request/tools/craft_response.py --emit-block
   escalations/<k>/response-NNN/manifest.json`, and read back with
   `twine.shapes`: exactly one `exchange` block, intact (its sha256 trailer
   holds), for the sid. A crafter that exits non-zero, or renders anything
   else, is an error result naming `--emit-block` — as a crafter that cannot
   scaffold is. The round is the crafter's default, 1.

The result: `kind: "clarification"`, `suspend: true`, `questions` (the
count), `path`, `sha256` and `block` (the paste block's text); its `content`
is the sentence it always was followed by the block. The loop treats it as
`deliver` and suspend
(§7.4): `carry response` on the tarball, then the run ends `suspended`
with the twin's `tarball`, `apply_line` and `dry_run` set and `block` the
paste block — or `stopped` when the dry run is not clean, as a bad delivery
is. Human mode on stdout stays the apply line alone (cli-contract §18.7). The
operator applies the line; bale suspends the session and prints the
planner's paste block; the planner answers and `bale relay` carries it; and
`twine resume <sid> --answer <the worker-facing block>` continues (§7.9).
The light form is unchanged: its `block` key is `null`.

**`deliver`** names the response tarball the courier will carry: the path
through the cage rules, a regular file, readable; the result is
`delivered: true`, `path` (inside the home), `size` and `sha256`. Running
`carry response` on it is the loop's (R4).

### 6.7 The kill-switch hook

Everything the sandbox starts — `shell`, `probe`, and the detection at
creation — goes through `Sandbox.spawn`, the composition cli-contract §14.4
prescribes for the loop:

- when **a running record for the sid exists**, the seam is handed
  `on_spawn=lambda pid: register_group(state_dir, sid, pid)`, so the tool's
  group is in the record before the child does anything (§10.6); when the
  run returns with `group_survivors` empty, `clear_group(state_dir, sid,
  pid)` forgets it, so a long session's record stays what is alive. A run
  that returns survivors leaves its entry for `twine kill`, logged;
- **without a record** (the loop registers itself first, R4; a test, or the
  architect at a terminal, has none) the run proceeds unregistered and that
  is logged — never refused;
- a record that **cannot be read** refuses the spawn — a tool error (a
  `SandboxError` at creation), nothing started: a group the kill could not
  find must not start. A hook that cannot register (`register_group`
  refusing) is the seam's case: it kills the child before it runs and
  re-raises, and the tool returns an error naming it. A clear that fails is
  logged; the record is a cache, and `twine kill` finds the group dead.

**Which pid the hook registers, and why the kill reaches the cage.** Under
the cage the child the seam starts is the outer `unshare` (a session leader, so
its pid is its group id — the pid the hook registers). It forks the cage's
setup script into the new PID namespace, and that script `exec`s into the
command, which is the namespace's **init**: its pid in the cage is 1 (a test
reads `$$` back and sees 1, and reads the registered pid's name and sees
`unshare`), its pid on the host is another, and it stays in the registered
process group. `twine kill` signals that group, SIGTERM then SIGKILL as
before (§14.4 of the CLI contract): the outer `unshare` dies of the SIGTERM and
`--kill-child` makes the init die with it; the SIGKILL, if it comes, reaches
the init directly, since it is a member of the group; and **when the init dies
the kernel kills every other process of the PID namespace** — the command's
children, the ones that left the group with `setsid` among them — so a group
that the kill finds dead leaves nothing of the call behind. The seam's own
kill at a timeout is the same signal. Where the filesystem is unconfined the
sandbox wraps as it did at R3: under `unshare -rn` without `--fork` the
wrapped command replaces `unshare` in place, so the registered pid is the
command's own (and a `setsid` child escapes the group, the report's
`unconfined` already said); with no `unshare` at all the child is the command.

## 7. The loop (Arc 2 R4)

The loop that hosts a worker session from `bale open` to the apply line —
what makes the architect stop being the courier on the worker side. The
code is `twine/runtime/loop.py` (the loop as functions and one class,
`Loop`, so R5's resume and R8's `ask` re-warm a transcript through the same
code); the verb is `twine run BUNDLE` (`twine/commands/run.py`,
cli-contract §18), which assembles what the loop needs, and since R5 `twine
resume SID` (`twine/commands/resume.py`, cli-contract §19; §7.9). The window
the loop counts is `twine/runtime/window.py`. The tests are
`tests/test_run.py`, and since R5 `tests/test_window.py` and
`tests/test_resume.py`: the fake adapter throughout, no model.

### 7.1 The sequence

`twine run` performs these in order, each refusing loudly before the next
(cli-contract §18.2 names every refusal). A refusal before the first model
call is outcome `refused`, exit 1, nothing recorded beyond what `carry
bundle` recorded.

0. **The verb's own refusals**, before anything starts: the adapter and its
   arguments (`--model` with `anthropic`; `--script` with `fake` only,
   parsed by `FakeScript.from_data`, so a bad script refuses before bale
   opens; `ANTHROPIC_API_KEY` set in the environment twine was started
   with, for `anthropic`), the cap, the limits (since R5 `--window`, a
   positive number of tokens when given), the state directory, the
   tool registry (ok, `twine runtime tools`'s) and the transition table
   (`MoveBook.faults()`: the table total, every move the loop performs
   declared, a row with a declared move for every stop the loop reports —
   since R5 `window-exhausted` among them, a key of the axis and not a
   loop key).
1. **`carry bundle`** — `twine.commands.carry_bundle.open_bundle`, the
   function, not a subprocess: `bale open <bundle> --json` through the seam,
   the in-flight record written (cli-contract §15.4). Its refusals are the
   verb's. `opened` and `second-desk` both proceed (a second desk is a
   second runtime on the same session: allowed, recorded). An open that
   names no request tarball refuses.
2. **The key** goes to the adapter and nothing else. The courier's bale
   calls (`open`, `apply --dry-run`) get twine's environment *without*
   `ANTHROPIC_API_KEY` — bale needs no key, and a variable it never sees
   is one it cannot print — the cage never has it (§6.4), and no
   transcript line, record, twin or log line carries it: the Anthropic
   adapter is handed `env={"ANTHROPIC_API_KEY": key}` and keeps it in its
   `x-api-key` header (§5.2).
3. **The running record**: `twine.process.lead_own_group()` (the runtime
   made its own group's leader with `os.setsid()` when it is not one —
   under a PID namespace an inherited group reads as 0, the R3 HOLD's
   lesson; a process started from an interactive shell leads its group
   already and is left alone), then `kill.register_running(state_dir, sid,
   pgid, pid)` — **before anything is spawned**, the sandbox's cage
   detection included (a test's wrapping runner sees the record on that
   spawn).
4. **The sandbox** (`Sandbox.create(state_dir, sid, repo=<the open's cwd>,
   run=<the seam>)`, §6) and **the request unpacked** at `<home>/request/`
   (`unpack_request`, D11): every member as it is in the tarball, through
   `tarfile`'s `data` filter, under bale's one top-level directory
   (`request-NNN/`), which is stripped so `request/manifest.json` is the
   manifest (a tarball whose members share no one top directory is
   unpacked as it is). Every member goes through the filter **before
   anything is written**: one that would escape — `..`, a symlink or hard
   link pointing out, a device — refuses the run and nothing is extracted.
   (The filter strips a leading `/` from an absolute name, so such a member
   lands inside `request/`; it is not an escape.) A later run of the same
   session writes each member again over what is there.
5. **The adapter**, behind the boundary (§1): `anthropic` (§5) with the
   model, `max_tokens` and thinking as spawn-time constants (D12) and the
   surface note as its system text; or `fake` with the script. Each is
   found by name through the adapter registry (`adapter_class`). Then **the
   window** (R5): `--window N` fixes its size (source `flag`, the adapter
   not asked); absent, the adapter states it (§1.1 — the Anthropic
   adapter's one `GET /v1/models`, source `adapter`; the fake's unknown,
   source `unknown`, with the adapter's reason). Unknown is not a refusal.
6. **The transcript** opened (§7.6); its `run-start` line carries the
   window (`size`, `source`, `reason`, `warn_fraction`) and `resumed_from`
   null.
7. **The in-flight record's `runtime` fields** (`inflight.record_runtime`,
   cli-contract §15.4): `adapter`, `model`, `sandbox_home`, `transcript`,
   `started_at`, `pgid`. A record that cannot take them (none was written,
   say) is a warning and the run goes on — the record is a cache.
8. **The loop**, §7.4.

### 7.2 The system prompt and the surface note

**Model-agnostic, and only the tool definitions and the surface note**
(D11, §4.3): `SystemPrompt(note, tools)`, the note `SURFACE_NOTE` and the
tools the registry's seven specs in the declaration's order. A spawn-time
constant (D12: prompt-cache stable) — the same text for every session, so
it names no sid either. A native-tool adapter carries the tools in its own
field and the note as its system text (the Anthropic adapter's `system`);
the fake has no system text and is handed the tools on every `Request`.

The note's text is twine's (decision 1 of the R4 brief), pinned only in
what it must say, and a test holds each:

- the request lies at `request/` in the working directory —
  `manifest.json`, `AGENT.md`, `README.md` (the brief), `context/` — and is
  read with `read_file` and `list_dir`, not found in the conversation;
- the session ends by calling `deliver` with the response tarball, built in
  the cage (`request/tools/craft_response.py` is in the request);
- a question for the planner is `escalate`; a probe for the operator's
  machine is `probe`;
- and, since twine-run-ergonomics (the one deliberate edit of this
  cache-stable constant, ratified at the sitting of 2026-10-13, and the only
  one: no later session edits it without a ruling), six things about working
  here, each held by a test on its stem — case-insensitive, markdown
  stripped: **list your home first** (a previous desk's work may already be
  in it — `list`, `first`); **read ranges, never whole files** (every byte
  printed is re-read on every later call — `range`); **write large files in
  parts** (`in parts`); **never background a command and poll it**
  (`background`); **the request carries no schemas: the lint judges the
  manifest** (`lint`, `judge`); and **the window line exists** (the last line
  of a tool result when the window runs thin, §7.4 — `window`) **and
  `escalate`'s `blocking: true` form exists** (`blocking`);
- and **nothing about the model, the provider or the task** (a test
  searches it for provider and model names, `model`, `provider`, and the
  session's sid).

### 7.3 The conversation's shape

R1 left the message objects' shape to R4. It is the Messages API's own
(§5.6): `{"role": "user" | "assistant", "content": …}`, content a string or
a list of blocks — `text`, `tool_use`, `tool_result`, `thinking`,
`redacted_thinking` — because the first adapter speaks it and keeps a turn's
blocks byte for byte; an adapter for another wire (R6) translates from it.
The loop's helpers (`user_message`, `assistant_message`,
`tool_result_message`) build exactly what the Anthropic adapter's do for the
same input, and a test holds them to it, without the loop importing a
provider's module.

- **The first turn is the opener**, verbatim from bale's open line: one
  user message, the text the operator used to paste into a worker chat.
- **An assistant turn** carries the turn's own `content` blocks exactly as
  the adapter received them when it has any (a thinking block goes back
  byte for byte, §5.6); an adapter with none (the fake) gets blocks built
  from its text and tool calls. Thinking without blocks is not rebuilt (its
  signature is the provider's to write).
- **Tool results** are one user message, a `tool_result` block per call in
  order, `is_error: true` when the tool failed.
- **Append-only** (D12): nothing earlier is edited; each `Request` is the
  whole conversation so far and the tools.

### 7.4 Each call, and the moves the loop performs

Until an outcome, in this order — and **every step is a transcript line
before the next begins** (§7.6). Before a call: the abort file, twine's
`--max-turns`, **the window** (R5), then the cap.

1. **The abort file** (`kill.abort_requested`, cli-contract §14.3): set →
   outcome `killed`, stop `killed`. Its move, `close-aborted`, is `twine
   kill`'s to finish: the loop exits and **never unlocks**.
2. **twine's own limit**: when `--max-turns` calls have been made, the loop
   stops before the next one (decision 4) — outcome `ended`, `shape`
   `"max-turns"`, no stop key: a limit twine imposes on itself is not a key
   of the axis.
3. **The window** (R5; `twine.runtime.window`): when the size is known and
   the last call's `used` (below) is at or past it, **the call is not
   made**: outcome `stopped`, stop `window-exhausted`, the table's move for
   it (`split-goal`, the planner's), the `move` line saying the call was not
   made, the twin's `turns` the calls actually made. The stop key is the
   table's and is not one of its `loop_keys` — a provider maps onto it too
   (Anthropic's `model_context_window_exceeded`, R2, which keeps mapping to
   the same stop); its one spelling in code is
   `twine.transitions.STOP_WINDOW_EXHAUSTED`, and `MoveBook.faults` holds the
   table to a row for it whose move is declared, so `twine run` refuses a
   table without one before it opens anything.
4. **The pre-call check** (`spend.check_call`, §13.8) with the cap, the
   model, the input estimate (§7.5) and `max_tokens`: `cap-reached` and
   `cap-unchecked` are outcomes of the same name, stop the same key, the
   check's `refusal` and `reason` carried; the call is not made.
5. **The call** through the boundary. Its usage is appended to
   `spend.jsonl` (`spend.append_record`: the sid's own, `served_sid` null,
   `extra` the call number, the stop and the adapter, and the provider's
   request id when there is one) **before anything else is done with the
   turn** — one record per call, a zero-usage refusal included. Then **the
   count** (R5): `used` = that call's `input + cache_read + cache_write` —
   the prompt as the provider counted it, `Tokens`' input side, exact and
   the provider's own; 0 before the first call. One `window` line per call
   that returned a turn (§7.6). The window decisions key on `used` alone:
   what was appended since the last call is not counted toward them (the
   provider's own refusal is the backstop for that gap), so the numbers the
   worker reads are counts, never estimates. A call whose input side is 0 —
   one the provider answered with no count, an error before any answer —
   leaves `used` as it was: every prompt carries the system note, so a zero
   is an uncounted call, never an empty window. When the size is known and
   `used` is at or past `0.8 × size` (`WINDOW_WARN_FRACTION`, one constant)
   the run is **warned**, and stays warned: from then on **every tool
   result the loop returns to the model carries, as its last line**,

   ```text
   [window: N of M input tokens in use (P%); the window does not compact — finish and deliver, or escalate; past 100% the run stops window-exhausted]
   ```

   `N` the last call's `used`, `M` the size, `P` `N * 100 // M` — appended
   to the result's `content` the model reads (after an LF unless the content
   already ends with one; the line alone when the content is empty), never
   to the transcript's `tool-result` line, never by editing an earlier turn
   (the capability's promise). The `continue-turn` user message (its text
   and each "not run" result in it) and the probe hop's user turn carry the
   same line while warned; so do the "not run" results of a turn that ended
   the run, which a resume sends. A usage the
   stream refuses ends the run `stopped`: the loop does not spend what it
   cannot count. A `BoundaryError`, or an adapter that raises (the fake's
   script running out, an unreadable usage, an edited conversation), ends
   the run `stopped` with the stop **`adapter-defect`**, the move
   `fix-adapter` and the actor `operator` — an adapter defect, not a model
   outcome (§1.6). The transcript's `adapter-error` line is followed by a
   `move` line for it, as every other stop gets one, and the spend stream is
   untouched: no turn, no record, no `window` line. (`twine run` refuses before it opens
   anything on a table that does not declare `adapter-defect` among the
   `stop` axis's `loop_keys` with a row, as for every key the loop reports.)
6. **The move**, by the transition table — the `stop` axis row's move, read
   through `MoveBook`, never a second dispatch table:

| the turn | the table's move | what the loop does |
|---|---|---|
| asks for tools (`stop` null) | — | runs each call in order through `run_tool`; each result goes back as a `tool_result`, `is_error` carried — a failed tool is **`return-tool-error`**, returned and never a crash. A result with `suspend: true` (`escalate`) → outcome **`suspended`**, the light block carried — or, when the result names a tarball (`path`: escalate's clarification form, R5, §6.6), `carry response` on it first, then **`suspended`** with the tarball, the apply line and the dry run (`stopped` when the dry run is not clean); a result with `delivered: true` (`deliver`) → `carry response` on the tarball (§7.7). Nothing after any of these runs in that turn: each later call is answered `is_error` "not run" so the conversation stays whole for a resume |
| `end-turn` | `classify-final-text` | `shapes.find_blocks` on the turn's text: a **light** block, intact and for this sid → **`suspended`** (as `escalate`); one that is not → `ended`, shape `light`; a **probe** block → run through the `probe` tool, its content (the paste-back, or why it did not run) the next user turn — D13's hop closed; **prose** or any other shape → **`ended`**, `shape` the report's |
| `max-tokens` | `continue-turn` | the partial content kept as an assistant turn, then a user turn: a `tool_result` "not run" for any `tool_use` block the partial turn holds (the API refuses one left unanswered), then the request to continue (decision 3: ending on a user turn needs no prefill, which not every model allows) — and, since twine-run-ergonomics, when the turn was cut inside a tool call whose input did not complete (§5.4: that call is not among the partial content), a second sentence in the same text block: that the call was cut off before its input was complete and not run, to be made again in smaller pieces, a large file written in parts (`CUT_CALL_TEXT`). At most 3 continuations in a row, then `stopped` |
| `rate-limited`, `overloaded`, `provider-error`, `network-failure`, `timeout` | `retry-with-backoff` | the same call again after `Turn.retry_after` seconds when the provider named them, else 2, 4, 8, 16, 32; at most 5 retries of one call, then `stopped`, the stop and the attempts in `reason`. The wait sleeps a second at a time and checks the abort file between: an abort meanwhile is `killed` |
| `request-refused`, `model-refusal`, `window-exhausted`, `malformed-shape`, `tool-error` | `fix-request`, `reword-brief`, `split-goal`, `respawn-from-request`, `return-tool-error` | **`stopped`**, the stop key and `Turn.reason` carried, the move and its actor named for whoever performs it |
| `cap-reached`, `cap-unchecked`, `killed`, `adapter-defect` | `stop-at-cap`, `fix-and-resume`, `close-aborted`, `fix-adapter` | never from an adapter (the boundary refuses them, §1.5): the loop's own, steps 1, 4 and 5 (`adapter-defect` ends the run `stopped`; the other three are outcomes of their own name) |
| `window-exhausted`, before a call (R5) | `split-goal` | the loop's own too, step 3, beside the provider's: `stopped`, the call not made |

A `tool-error` stop on the API side — a provider saying a tool failed — is
`stopped` like the refusals: the loop's own `return-tool-error` is the
tool-result path in the first row. The `continue-turn` move's description
in the table says what the loop does: at most three continuations in a row,
past which the run stops `stopped` with the stop the turn carried,
`max-tokens`, for the planner to read (the table was reconciled with the loop
at the adapter-defect session; `Loop.continue_turn` did not change).

### 7.5 The input estimate

`estimate_input_tokens(prompt, messages)` (decision 2): the request as
twine would send it — the note, the tool definitions and the messages,
JSON-encoded — in UTF-8 bytes, divided by **2** and rounded up. An estimate
by characters, acceptable at R4, and deliberately high: a token is three to
four bytes of English or code and only the densest text (hex, base64) comes
near two, so the worst case the check prices is above the real one.

Since R5, **once a call has counted the window** the check prices the
window's `used` plus `estimate_appended_tokens(messages)` — the same bytes
/ 2 of the messages appended since the last call alone (0 when nothing was,
a retry) — tighter than the estimate of the whole request, and still above
the real number. Before the first counted call of a run (a resumed run's
first call included) it prices the whole-request estimate. The `check`
line says which (`input_basis`: `counted` or `estimated`).

### 7.6 The transcript

`<state-dir>/transcripts/<sid>.jsonl` (`twine/transcript.py`; TQ-1: a log,
durable, append-only, never a record of intent), created if absent (the
directory 0700, the file 0600), every line one `O_APPEND` write and an
fsync, **never rewritten**. A transcript that exists when a run starts is
appended to with a `run-start` line — R5 resumes here — its `seq`
continuing; a torn last line (a run killed mid-write) is ended with an LF
first and the next line says `torn_before`. Each line is one object, `at`
(UTC), `seq` (1-based, continuing across runs) and `kind` first:

| `kind` | the event |
|---|---|
| `run-start` | `adapter`, `model`, `max_tokens`, `thinking`, `sandbox` (§6.4's `as_json`), `request` (where it was unpacked), `open` (the open's `sid` and `tarball` — not its twin; null on a resume), `group` (the runtime's pid, pgid, whether it called setsid), `cap_usd`, since twine-run-recovery `cap_given` (the `--cap` as typed, `+2` or `5`, beside `cap_usd`, the absolute cap it worked out), `max_turns`, `system` (the prompt: the note and the tools), and since R5 `window` (`size`, `source`, `reason`, `warn_fraction`) and `resumed_from` (null on `twine run`; on `twine resume` the `seq` of the line before it, beside `answer` — its source (a path, `stdin`, or `twine` when no answer was given and `RESUME_TEXT` was sent, §7.9), sha256 and length — and `rebuilt`, what was re-warmed) |
| `check` | `call`, `input_estimate`, `input_basis` (R5: `counted` or `estimated`, §7.5), `check` (the pre-call check's twin) |
| `request` | `call`, `messages_total`, `appended` — the messages added since the last `request` line, so the lines' `appended` lists, joined, are the conversation as sent, with no quadratic growth (the key never appears: the adapter has no path for it to). When the run ends with messages no `request` line holds — the tool results of a turn that ended it, and since R5 the final assistant turn of an `end-turn` (a light block, prose), the results a window stop left unsent — a last one with `sent: false` carries them, so the joined lines are the whole conversation a resume rebuilds (§7.9) |
| `turn` | `call`, `turn` (`Turn.as_json()`), and `spend_error` when the usage could not be appended; and since twine-run-ergonomics, beside `turn`: `raw` — the path of `<state-dir>/transcripts/<sid>.call-<N>.raw`, the response body kept (mode 0600, `N` the call number) when the call ended `malformed-shape`, whatever the detail (§5.4), and absent on every other turn (`raw: null` with `raw_error` when the file could not be written; a resumed run's numbering restarts, so since twine-run-recovery a raw file is **never overwritten**: it is created exclusively, and a name already taken gives `<sid>.call-<N>-2.raw`, then `-3`, … — the first run's file keeps its name and the line's `raw` names whichever file the body went to); and `cut_tool_input` — `{"id", "name", "partial_json"}` of the tool call a `max-tokens` turn was cut inside, whose input never completed and which is therefore not in the turn's content (§5.4), absent otherwise |
| `window` | (R5) after each `turn`: `call`, `used`, `size` (null when unknown), `fraction` (`used / size`, null when unknown), `warned`, and `call_input` (this call's own input side; `used` is kept when it is 0, §7.4) |
| `tool-call` | `call`, `id`, `name`, `arguments` (and `source: "final-text"` for a probe hop) |
| `tool-result` | `call`, `id`, `result` — the result's `as_json()`, every string over 64 KiB (`content`, `shell`'s `stdout` and `stderr`) cut with the cut marked |
| `move` | `call`, `stop`, `move`, `actor`, `did` — what the loop did (and `shape`, or the `carry_response` twin, where they apply) |
| `retry` | `call`, `stop`, `move`, `attempt`, `wait_seconds`, `retry_after` |
| `abort` | `when`, `path`, `move` |
| `adapter-error` | `call`, `error`, `message` (and `faults`, for a boundary refusal) |
| `run-end` | `twin` — the run's JSON twin (cli-contract §18.5), its `next` included; a recovery reading (§7.9) takes the last one's `outcome`, `stop`, `move`, `actor`, `reason`, and for a refused delivery its `tarball` and `dry_run` |

The sid's `spend.jsonl` lines are the money; the transcript is the story. A
line that cannot be written is logged and named in the twin's
`transcript_faults`; the run goes on (the spend stream and the running
record are what the cap and the kill stand on).

### 7.7 Outcomes, and what is kept and removed

| outcome | when |
|---|---|
| `delivered` | `deliver` named a tarball and `carry response` (`check_response`, the function: `bale apply --dry-run --json <path>`, §11.3) ran clean. The move is the `apply-outcome` row's for `dry-run`, `operator-applies` |
| `suspended` | `escalate` — its light form, or (R5) its clarification form once the dry run of the tarball it wrote is clean — or an intact light block for this sid in the final text |
| `ended` | the final text was prose or another shape (the worker finished without delivering — the planner's to read), or twine's turn limit (`shape` `max-turns`) |
| `stopped` | a stop whose move is not the loop's (since R5 the window's edge before a call among them), a bound reached (retries, continuations), the dry run not clean (a delivery's, or a clarification response's) (its outcome's `apply-outcome` row names the move — `admit-or-return`, `return-to-worker`, `repack-on-new-base` — which is the operator's or the planner's; the loop reports it), an adapter defect (stop `adapter-defect`, move `fix-adapter`, the operator's) — **resumable** like every kept-home outcome but `killed` (§7.9): the record and the home are kept |
| `killed`, `cap-reached`, `cap-unchecked` | the loop's own stops, before a call. `cap-reached` and `cap-unchecked` resume (§7.9); `killed` is closed in bale and is not resumed |
| `refused` | the verb refused before the first model call |

**On any outcome** the running record is cleared (`kill.clear_running`):
nothing is left for `twine kill` to kill once the loop has exited, and a
record for a dead runtime would mislead it — **unless** the record still
names a tool's group, whose run returned with live members (§6.7): then it
is kept, for `twine kill <sid>`, and the twin says so. **On `delivered`
only** the in-flight record is removed (`inflight.remove_inflight`, R3's
lifecycle proposal, half of it) and the sandbox home is **kept** — the
response tarball lives there until the operator applies it. What removes a
home is a verb, since twine never sees the apply: **`twine sandbox prune`**
(cli-contract §22; `twine/prune.py`) removes `<state-dir>/sandbox/<sid>/` for
each kept home whose session bale's own record
(`<repo>/<agent_dir>/telemetry/<sid>.json`, `attempts[].outcome` only) says was
applied, and keeps the rest each with why — and never one whose session has an
in-flight or a running record. On `suspended`, `ended`, `stopped`, `killed` and the
`cap-*` outcomes the record and the home are kept, for `twine resume` (§7.9)
and for the planner.

**On every outcome, once the run has a sid**, `twine run` and `twine resume`
append **one line to `<state-dir>/runs.jsonl`** (twine-run-telemetry;
`cli-contract.md` §20.1) — `delivered`, `suspended`, `ended`, `stopped`,
`killed`, `cap-reached`, `cap-unchecked`, and `refused` after the open — so a
rate over the runs has no numerator-only exits. The line is the twin's names
plus what the loop tallies and the twin does not carry: per tool `calls`,
`errors` and wall `seconds` around `run_tool` (a probe hop's included), the
`continue-turn` moves made, and the heartbeat lines printed (`LoopResult.tools`,
`.continuations`, `.heartbeats`). The loop never reads the file. Where the
loop's `deliver` hands the courier's line back, twine has first written the
session's cost file and the apply line it returns names it (§18.7a): the
loop's `apply_line` on `delivered` and on escalate's clarification form is
`bale apply <tarball> --cost-file <path>`, and the `run-end` twin and the
`carry_response` the `move` line carries say the same.

### 7.8 What it does not do

It applies nothing (T12: the only apply argv is `bale apply --dry-run
--json`), unlocks nothing (a kill's closure is `twine kill`'s), resumes only
through `twine resume` and only cold (§7.9: no cache is held hot — holding
hot on the extended-cache tier is D23's later knob, the effort machinery's),
counts the window and never estimates it toward a decision (§7.4: a size it
does not know it cannot warn or stop on), speaks no text protocol (R6),
removes no sandbox home itself (`twine sandbox prune` does, §7.7), and never
compacts, summarizes or drops a turn to make room (D12).

### 7.9 Cold resume — `twine resume` (Arc 2 R5; D23)

A worker blocked on an escalation goes cold (D23): nothing is held hot, the
cache expires, and the conversation is re-warmed from the transcript on the
answer. The verb is `twine resume SID --cap USD [--answer FILE|-]`
(`twine/commands/resume.py`, cli-contract §19); the reading is
`twine/runtime/resume.py`, suspend-resume's `implemented_by`.

- **The rule** (twine-run-recovery). A run `twine run` or `twine resume`
  left `stopped`, `cap-reached`, `cap-unchecked`, `ended` or `suspended`
  resumes with `twine resume`, in its kept home, from its transcript;
  `respawn-from-request` is the last resort, for a home that is gone or a
  session bale has closed. The transition table says it where the operator
  reads it: the descriptions of `fix-adapter`, `stop-at-cap` and
  `respawn-from-request` each name `twine resume`.
- **What it resumes.** A session `twine run` left `suspended` — a light
  block, or the clarification form (§6.6) — or `ended`, `stopped`,
  `cap-*`: any run whose in-flight record (with its `runtime` fields) and
  transcript are kept. `delivered` removed the record, so a delivered
  session is refused (its reason names the apply line the transcript
  recorded). **`killed` is refused, before anything starts**: `twine kill`
  closes the session in bale (`bale unlock <sid> --reason aborted`, §14.5),
  so a resumed worker could rebuild the conversation but no response it
  delivered could be dry-run or applied under that sid — a kill stays a
  close, and the reason names the `aborted` closure and the respawn path
  (`respawn-from-request`, the planner's). The refusal's test is the
  transcript's last `run-end` outcome `killed`, or an abort request still
  standing for the sid (it would end the loop `killed` before any call).
- **The cap is cumulative per session.** `spend.check_call` admits a call
  when the spend so far plus the call's worst case is at most the cap, so a
  `cap-reached` run resumed under the **same** cap refuses its first call
  `cap-reached` again — `turns` 0, no new line in `spend.jsonl`, the twin's
  `reason` saying the cap is spent (when the spend so far is at or past it)
  and naming the spend so far — and under a **raised** cap it makes its next
  call. The ending is the loop's first pre-call check, not a refusal of the
  verb's (the session is open, the running record is written, the transcript
  gets its `run-start` and the unsent answer). `--cap +USD` is the spend so
  far plus that amount (cli-contract §19.1).
- **The answer, and `RESUME_TEXT`.** `--answer` is required on a
  `suspended` run (the last `run-end` outcome; an answer is what a
  suspended worker waits for) and optional on every other. Given, it is the
  next user message verbatim, as before. Absent, the next user message is,
  byte for byte, `RESUME_TEXT` — `twine.runtime.resume.RESUME_TEXT`, one
  constant:

  ```
  This session was stopped and has been resumed; continue from where you left off.
  ```

  and the `run-start`'s `answer` object says `source: "twine"` (with the
  sha256 and length of those bytes). The constant spells no stop key.
- **`--plan`: the recovery reading** (`twine resume SID --plan`,
  `twine/recovery.py` and `twine/commands/resume.py`). It reads the
  session's transcript, its `spend.jsonl` records, its in-flight record and
  its sandbox home; it **writes nothing, starts no bale and calls no
  model**, and says whether the session resumes (the rule and the `killed`
  refusal) and with what line. The facts are the transcript's last
  `run-end` twin (outcome, stop, move, actor, and for a refused delivery
  its tarball and the dry run's line), its last `window` line, its last ten
  `tool-call` lines, the sid's spend records priced as `twine spend totals
  --sid` prices them (own cost and what served the session), and the
  pre-call check's worst case for the next call (the rebuilt conversation
  plus `RESUME_TEXT`, estimated as §7.5 estimates, at the dearest
  input-side price, and `max_tokens` at the output price). Nothing that
  cannot be priced is estimated: those figures are null, with the reason.
  **The suggested cap** is a number of dollars at two decimals, strictly
  above the spend plus the next call's worst case, so the resumed run's
  first call is admitted; above that floor: the spend so far, plus a
  re-warm of the window at the cache-write price (the window tokens in use,
  or the input estimate when no call counted a window), plus forty calls at
  the mean of the last ten calls (0 with no calls yet), plus the worst case,
  rounded up to the cent — and one cent more when that is not above the
  floor. The human rendering states the sum.
- **`next`: every ending names its next command** (twine-run-recovery; the
  twin's `next` and human mode's `next: <command>` lines, cli-contract
  §18.7). The resume line — `twine resume SID --cap <suggested>`, with the
  `--state-dir`, `--bale-root`, `--cwd` and `--prices` the run was given — is
  named for `cap-reached`, `cap-unchecked` (once its fault is fixed),
  `ended`, and every `stopped` but the two below; when no cap can be
  suggested (an unpriced model, a transcript a resume cannot rebuild) it is
  `twine resume SID --plan` instead. A dry run refused `scope-drift-refused`
  names bale's own admit line, `bale apply <tarball> --allow-out-of-scope
  <path>` for each path of the dry run's `drift.out_of_scope_paths`, then
  the resume line; **twine never runs the admit line** (T12). `killed` names
  no command — the respawn path is said in words — and `window-exhausted`
  none (the planner's split). `delivered` and the clarification form's
  `suspended` name the apply line; a light block's `suspended` the resume
  line with `--answer -`.
- **The rebuild** (`read_conversation`). Every complete line read as JSON,
  in order. A `run-start` without `resumed_from` begins a new conversation
  (a second desk's `twine run` starts over from the opener); one with it
  continues the last. The conversation is every `request` line's `appended`
  since then, in order, `sent: false` lines included — each line's
  `messages_total` checked against the conversation joined so far — and the
  constants of the last `run-start` (`adapter`, `model`, `max_tokens`,
  `thinking`). Refused, every fault named (`ResumeError`): no such file, a
  line that is not a JSON object, a torn last line (a run killed mid-write:
  the tail may be missing), no `run-start`, no `request` line, a message the
  loop never wrote, a count that disagrees.
- **The sequence**, then as `twine run`'s from §7.1 step 3: the running
  record; the sandbox reused (`Sandbox.create` on the existing home — the
  request is already unpacked there and is not unpacked again; `request`
  in the `run-start` line names it, `members` null); the adapter spawned
  with the transcript's constants and the key as before, and the window
  (`--window`, or the adapter's statement); the transcript appended to —
  a `run-start` carrying `resumed_from` (the `seq` of the last line before
  it), `open` null; the in-flight record's `runtime` fields replaced; the
  loop with **the rebuilt conversation plus one user message whose text is
  the answer**, verbatim — the packer's words for a light block, or the
  worker-facing block `bale relay` printed for a clarification — and
  `logged` = the rebuilt count, so the resumed run's first `request` line
  carries `messages_total` = the previous last + 1 and `appended` = that
  one message. `seq` continues; nothing earlier is edited, so the prefix the
  cache keys on is unchanged. The bale calls are the dry run's alone: no
  `bale open` (the session is open in bale already).
- **The re-warm cost** (D23's "named telemetry field"): the twin's
  `rewarm` — the resumed run's first call's `Tokens` (the five classes),
  null until that call is made; `twine run` carries it null. A run counts
  its own window from its own calls: `used` is 0 until the resumed run's
  first call reports.
- **Outcomes, and what is kept and removed**: as §7.7's. A resumed run can
  suspend again; a transcript carries any number of runs.

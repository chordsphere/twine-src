# The twine runtime contract

> What a model adapter implements, what the runtime promises it, how the
> runtime's capabilities are declared, and how a provider's usage becomes
> twine's. The sibling of `cli-contract.md`, which stays the verbs'
> (`twine runtime list` and `show` are its §17). Each line here is
> asserted by a test under `tests/` (`tests/test_runtime.py`,
> `tests/test_anthropic.py`) and by the landing session's `validation.sh`.
> Landed by session `2026-10-12-twine-runtime-registry-007` (Arc 2 R1);
> §1 (Q-3) and §2 (TQ-2) were ratified as written on 2026-10-12. §5 and the
> lines of §1–§4 that say "R2" are session
> `2026-10-13-twine-runtime-anthropic-002`'s (Arc 2 R2), awaiting review. A
> later session that changes a line changes it here in the same response.

What exists after R2, and what does not: the registry, the boundary, the
fake adapter, `from_anthropic`, and the Anthropic adapter (§5) — the first
code under `twine/` that reaches a network (through one module,
`twine/runtime/transport.py`) and reads a key (from the environment mapping
it is given). Nothing calls a model on its own: no loop exists to call
it, and nothing appends to the spend stream. R2 does **not** use the
`anthropic` SDK (§5.1). R3 adds the canonical tools and the sandbox, R4 the
loop (`twine run <bundle>`), R5 window accounting's counting and cold
resume, R6 the text tool protocol's wire and the OpenAI-compatible adapter.

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
  end, or `None`). The boundary checks their types.
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
  the axis. The exact provider names were verified when the first adapter
  was built (R2): against the 2026-10-13 recordings, and against the SDK's
  `StopReason` literal (`anthropic` 1.13.0, read from its wheel: `end_turn`,
  `max_tokens`, `stop_sequence`, `tool_use`, `pause_turn`, `refusal`,
  `model_context_window_exceeded`) — the seven the mapping rows list.
- `cap-reached`, `cap-unchecked` and `killed` are keys of the axis that
  the loop, not a provider, produces (the cost spine, the kill-switch).
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
outcome; what the loop does with one is R4's to decide, and it will be a
row of the transition table. The boundary never retries, repairs or
translates a turn.

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

### 2.4 The eight, at R2

| capability | status | module (under `twine.runtime.capabilities.`) | lands |
|---|---|---|---|
| `tool-calling` | implemented (`anthropic`, `fake`) | `tool_calling` | R2 Anthropic `tool_use` (landed); R3 the canonical tools; R6 the text protocol |
| `thinking` | implemented (`anthropic`, `fake`) | `thinking` | R2 Anthropic's parameter and blocks (landed) |
| `prompt-caching` | implemented (`anthropic`) | `prompt_caching` | R2 (landed: §5.3) |
| `window-accounting` | declared | `window_accounting` | R5 |
| `streaming` | implemented (`anthropic`) | `streaming` | R2 (landed: §5.4) |
| `sandboxing` | declared | `sandboxing` | R3 |
| `suspend-resume` | declared | `suspend_resume` | after R4, with R5's cold resume |
| `usage-accounting` | implemented (`anthropic`, `fake`) | `usage_accounting` | R2 calls `from_anthropic` (landed); R4 appends |

At R1 three were implemented (the fake's) and five declared; R2 moved
`prompt-caching` and `streaming`.

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
`message_stop` without `message_delta`) `malformed-shape`. Text
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
constants, `build_request`, one call, `Outcome.to_turn()`. One method takes
both because both are pinned (the brief's `call(body)` and R1's
`call(request)`); `send(body)` and `turn(request)` are the two halves by
name. Neither ever raises for a provider outcome or a transport failure —
both are outcomes with a stop; it raises for the caller's fault (a body
that is not JSON, an edited conversation) and for an unreadable usage.

### 5.8 What it does not do

No retries or backoff (R4's), no appending to `spend.jsonl` (R4's), no
tools' bodies or sandbox (R3's), no window counting (R5's), no server
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

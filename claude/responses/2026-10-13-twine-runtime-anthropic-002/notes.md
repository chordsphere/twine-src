# notes — 2026-10-13-twine-runtime-anthropic-002 (Arc 2 R2, the Anthropic adapter)

Everything the brief asked for landed: the adapter behind the boundary over a
stdlib transport seam, the fifteen recordings byte-exact through a new lander,
the stop and error mapping in the table with the two new keys and `loop_keys`,
`written_against` at the floor, the key from `ANTHROPIC_API_KEY` and nowhere
else, and one gated live smoke test. The suite went from 757 to 873 (869 in the held response). No path
outside the forecast; nothing under `fixtures/bale-*`, `twine-seed.md`,
`bin/twine` or `share/bale-consumption.toml` moved. Below are the decisions
for you to ratify (§1), what surprised me (§2), where I'd look first (§3),
what validation did (§4) and the seed annotation (§5).


## 0. The correction (HOLD of 2026-10-13)

This response re-attempts the held one (`corrects` is this session's own id).
The blind checkpoint's probe was *a stream cut before message_stop →
network-failure*, and the desk ruled the oracle right.

**The defect.** At the end of the chunks, `_events` flushed whatever was
pending — the half-received `data:` line included — into the JSON parser. So
a cut in the middle of a line, such as byte 754 of `text_stream` inside the
`content_block_delta`, came out `malformed-shape` ("data that is not JSON")
when it is a cut. My clean-cut tests all cut at event boundaries, so they
never saw it.

**The fix** (`read_stream` and `_events`, nothing else in the reader):

- An event is its lines plus the blank line after them, and its bytes are
  decoded only then. An unterminated trailing event is never parsed; its
  bytes are only counted.
- A stream whose complete events never reach `message_stop` (or an `error`
  event) is `stream-cut`, i.e. `network-failure`. Its reason names how many
  complete events arrived and how many unterminated bytes trailed.
- If an earlier terminated event could not be placed, judging is suspended
  until the stream proves it ended. A stream that ends is `malformed-shape`
  for that event. A stream that is then cut is `network-failure`, and the
  reason notes the earlier fault.
- A `message_stop` whose closing blank line never arrived is a cut. That
  follows the ruling, which says an event is only an event once its blank
  line has arrived; I've flagged it as a judgment call in the manifest.

**The tests** (`tests/test_anthropic.py`, 4 new; suite 869 → 873):

- The byte-754 cut, whole and split at 1 and 7 bytes, naming "after 3 complete
  events".
- Every proper prefix of each of the four streams is `network-failure`.
- A cut between the two bytes of a UTF-8 character.
- A malformed event judged only when its stream ended.

Against the held adapter, those four plus the transport test (whose reason
now says "complete events") fail, 10 failures across subtests. Against the
corrected one, all pass.

**Docs:** `runtime-contract.md` §5.4 states the ruling.

**Validation:** the only change is `SUITE_FLOOR`, now 873. Everything else in
the landing is byte-identical to the held response; the only changed files
are `twine/runtime/adapters/anthropic.py`, `tests/test_anthropic.py` and
`claude/context/runtime-contract.md`.

## 1. Decisions and deviations, for ratification

The brief's four open items first, then the calls I made that it didn't
anticipate.

1. **`Outcome`** (brief §5.1) is a frozen dataclass in the adapter module.
   `as_json()` carries the ten pinned keys plus `status` (the HTTP status,
   null when no answer came) and `usage_fault` (why a reported usage can't be
   read). It has `to_turn()` for the boundary.
2. **An empty thinking block counts as thinking** (§5.2). A turn carrying any
   `thinking` or `redacted_thinking` block has `Turn.thinking` set to their text
   joined: `""` for `thinking_stream`, not `None`. The consequence is that a
   session spawned with thinking off is refused that turn at the boundary,
   which is the point. A test proves it with the recording.
3. **`meta.json` keys** (§5.3). The pinned ones come first, then `name`,
   `seconds`, `note`, `request_bytes`, `response_bytes`, `request_file`,
   `response_file` and `probe`. Each file is one JSON line with its newline.
4. **Null cache counts: the SDK says otherwise, so I changed R1's rule** (§5.4).
   I downloaded the `anthropic` 1.13.0 wheel (pip, into scratch) and read it
   without importing it into twine. `types/usage.py` and
   `types/message_delta_usage.py` both type `cache_creation_input_tokens` and
   `cache_read_input_tokens` as `Optional[int] = None`. Following your rule,
   `from_anthropic` now reads null for those two as absent, i.e. 0. Null for
   `input_tokens`, `output_tokens` and `thinking_tokens` (typed `int`) is still
   refused. One caveat: Stainless-generated types use `Optional` for "may be
   omitted" as well as "may be null". If you read them that way, revert this
   one line in `twine/runtime/usage.py` (the `nullable=True` on the two cache
   reads) and the R1 test's nullable carve-out.
5. **The mapping is data in the table, as `[[mapping]]` rows.** R1 forbids any
   module under `twine/runtime/` from spelling a stop key, and a test enforces
   it. So `stop_key("end_turn")` cannot return `"end-turn"` from code, and the
   brief's "as rows of the table" became literal. Each row is `provider`, `on`
   (`stop_reason` | `error_type` | `status` | `condition`), `word`, and either
   `stop` or `continues = true`, plus `means`. That gives 36 rows for Anthropic.
   - The brief's "anything else" and "any other HTTP status" are named
     **condition** rows, not a default case: `socket-timeout`,
     `connection-error`, `stream-cut`, `unclassified-stream-error`,
     `unlisted-stop-reason`, `unlisted-status`, `malformed-body`. Every
     provider must map all seven.
   - `twine transitions` checks the rows with five new problem kinds
     (malformed, unknown stop, loop-key mapped, duplicate, missing condition).
   - `provider_mapping()` refuses a table with any fault for that provider, so
     an adapter whose mapping would produce a loop key never constructs.
   - `Problem` gained a `provider` field (in its JSON too). The JSON twin
     gained `mappings`, `counts.mappings` and `axes[].loop_keys`.
     cli-contract §12 documents all of it.
6. **One `call()` serves both pinned signatures.** The brief pins
   `adapter.call(body: dict) -> Outcome`, and R1's `Adapter.call(request) ->
   Turn` is what the boundary invokes. `AnthropicAdapter.call(body)` therefore
   dispatches on type: a `Request` returns a `Turn`, a mapping returns an
   `Outcome`, anything else is a TypeError. `send(body)` and `turn(request)`
   are the two halves by name. If you'd rather the boundary call `turn()`,
   that's an R1 interface change; I didn't make it.
7. **`Turn` gained four fields** (the brief asked me to flag this): `content`,
   `retry_after`, `request_id` and `reason`. All default, so `fake` is
   unchanged; the boundary type-checks them, and `as_json()` carries them.
8. **`ThinkingSettings` gained `adaptive`.** R1's type couldn't express
   "thinking on, no budget", which is the default the loop passes. Adaptive
   requires `enabled` and no budget, and `SpawnSettings` only checks the
   budget against `max_tokens` when there is one. The adapter refuses any
   thinking shape other than adaptive, enabled-with-budget or disabled/None,
   because the boundary must know whether thinking is on.
9. **`from_anthropic`'s code moved to `twine/runtime/usage.py`.** The adapter
   must call it, and R1's HOLD-born rule says nothing outside `capabilities/`
   imports a capability module. The "remove each module in turn" test would
   otherwise show an extra `unloadable-adapter`. `usage_accounting.py`
   re-exports the same objects. R1's test that pinned
   `from_anthropic.__module__` to the capability module now pins the new home
   and the identity.
10. **`content` keeps every key the API sent.** The brief's table lists the
    fields per block type, but the `tool_result` recording sends `caller` back
    and the API accepts it, and the round-trip test asserts the request's
    `messages` exactly. So blocks are kept as received, which is a superset of
    the listed fields.
11. **For an HTTP error, the status decides the key.** The error body's
    `error.type` goes into the reason and `raw_stop_reason`. The `error_type`
    rows serve SSE error events, which arrive inside a 200. So a 418 carrying
    `overloaded_error` is `malformed-shape`, per "never a guess at a nearer
    key".
12. **Usage on a turn the provider didn't bill.** An HTTP error, or a transport
    failure before any answer, has `Outcome.usage` null (pinned) and
    `Turn.usage` zero, because the boundary needs a `Tokens`. I'm asserting
    unbilled; that's an assumption. A 200 whose usage can't be read is
    `malformed-shape` in the `Outcome`, but `to_turn()` raises
    `UnreadableUsage`, per R1 §1.4 ("raise rather than guess").
13. **Stream usage is message_start's, overlaid by message_delta's.** That is
    what the SDK's accumulator does: a count the delta omits or nulls keeps
    the start's value. On every recording the result equals message_delta's
    alone, e.g. `Tokens(49, 3, 30, 0, 0)` for `thinking_stream`. A stream cut
    before `message_stop` keeps whatever usage had been reported, rather than
    zero.
14. **The new keys sit after `malformed-shape`** (provider keys together, the
    loop's three still last). R1's spend test that reads `keys[-2:]` stays true.
15. **`tool_use` blocks under a non-tool stop.** These are allowed only with
    `max_tokens`, where a call was cut short; the `Turn` then carries no calls
    and the blocks stay in `content`. Any other stop with tool blocks, or
    `tool_use` with none, is `malformed-shape`.
16. **Defaults and the transport.**
    - `max_tokens` defaults to 16000.
    - `https_transport` is https-only, one connection per call, uses `read1`
      so stream events arrive as sent, and has a 600 s socket timeout
      (`timeout=` overrides it).
    - It has no proxy, retries or redirects. It has not been run against the
      network here: the live test is the first time it will be.
17. **The conversation is append-only on the boundary path.** A `Request`
    whose messages don't extend the last ones sent raises `ConversationEdited`.
18. **The lander's `--check` reads `fixtures/README.md`'s rows**, like its
    sibling does. Unlike the sibling, it doesn't refuse extra files under
    `fixtures/anthropic/`, because R1's usage object and later probes
    legitimately live there.
19. **The README row shows the paste as received**: CRLF, 29,240 bytes,
    `41e8fe66…`. The brief gave me the LF bytes, and that row reconstructs
    CRLF by re-CRLFing them, as pin-051's row does.
20. **Ratification housekeeping.** In files I was editing anyway, R1's
    "proposed, awaiting ratification" now reads ratified 2026-10-12
    (runtime-contract §1/§2 headings, `boundary.py`, `runtime/__init__.py`,
    `capabilities.toml`). `contract.py` and `registry.py` still say
    "proposed"; I left them, and listed them under Proposals.
21. **R1 tests I changed** (tests/ is in the forecast, but they were R1's
    assertions):
    - `test_three_implemented_five_declared` → `test_five_implemented_three_declared`.
    - The parity detectors now use `window-accounting`, since `streaming` is
      implemented.
    - `test_every_stop_on_the_axis_passes` → `…_but_the_loops`.
    - The null-cache carve-out.
    - `__module__`.
    - The network-import test now names `transport.py` as its one exception.
    - The one-JSON-line rule is scoped to carried emissions and meta files.
    - `test_the_table_is_written_against_a_version_the_floor_keeps` →
      `test_the_table_is_written_against_the_floor`.

## 2. What surprised me

- **The SSE padding is inside the JSON object.** It sits before the closing
  brace (`{"type":"message_stop"        }`), not after it. A
  `str.strip()`-then-compare reader fails on it. `json.loads` doesn't care,
  and the test asserts the padding is there.
- **`python3 -I -m unittest tests.test_anthropic_live` can't import `tests`**,
  because `-I` drops the cwd from `sys.path`. The run line in the live test's
  docstring and in README uses `unittest discover -s tests -t . -p
  test_anthropic_live.py`. validation.sh first tripped on exactly this.
- The `/v1/models` recording shows Haiku 5.5 accepts `disabled` and Sonnet and
  Opus 5.5 don't, so `thinking=None` (send nothing) is safest for a session that
  wants none.

## 3. Where I'd look first on review

- `twine/runtime/adapters/anthropic.py`:
  - `_finish` (§5): the block checks and the "tools or stop" consistency rule.
  - `read_stream` and `_event` (§6).
  - `_error_row` (§2): the status-versus-type precedence.
- `share/transitions.toml`'s mapping section, against brief (e). The test
  `test_the_anthropic_mapping_is_the_brief_s_table` holds an independent copy.
- `twine/transitions.py`: `load_mappings`, `check_mappings`,
  `provider_mapping`, `loop_keys`.
- `runtime-contract.md` §5.5 carries (e)'s table verbatim; the paragraph after
  it says how the rows carry it.

## 4. Validation

`validation.sh` runs 14 claimed checks plus the unclaimed syntax and exec-bit
checks, all `python3 -I -B`, logging to `.validation-logs/<ts>/`. It never
reads `claude/checkpoints/`. I ran it in a simulated staging copy (base tree,
`files/` overlaid, `apply.sh` run, the manifest as `.bale-manifest.json`):

- **Twice on the changed tree:** exit 0 both times, every claim `[agree]`.
  Claims are `observed`.
- **Once on the unmodified tree:** exit 1. Ten session assertions failed, as
  they should. Four passed there too, by design: they are absence guards (no
  `anthropic` import, `fixtures/bale-*` untouched, the three untouched files,
  no `__pycache__`).

The untouched-files check reads `changes[]` from the staged manifest. It holds
`twine-seed.md` by hash only while `twine-seed-tidy8` hasn't landed first, so
that parallel session can't turn this check red.

## 5. The seed annotation (for tidy9, verbatim and complete)

Under §5.2, after R1's annotation:

> [2026-10-13-twine-runtime-anthropic-002: R2 landed — the Anthropic adapter (`twine/runtime/adapters/anthropic.py`, registered `anthropic`, implementing `tool-calling`, `thinking` and `usage-accounting` and, now `implemented`, `prompt-caching` and `streaming`) over a stdlib transport seam (`twine/runtime/transport.py`, the only place twine opens a socket; the `anthropic` SDK is not used), its key read from `ANTHROPIC_API_KEY` in the environment it is given and sent in `x-api-key` and nowhere else; the readers (`read_response`, `read_stream`, the `Outcome` whose `as_json()` is pinned) and `build_request` with three prompt-cache breakpoints; the stop and error mapping as `[[mapping]]` rows of `share/transitions.toml`, whose `stop` axis gained `request-refused` (move `fix-request`, the operator's) and `provider-error` (`retry-with-backoff`) and declares `loop_keys` (`cap-reached`, `cap-unchecked`, `killed`), which the boundary now refuses from an adapter, with `written_against` at the floor, 0.4.51; the fifteen recordings of 2026-10-13 under `fixtures/anthropic/` and their lander, `bin/twine-land-provider-recordings`; the gated live smoke test, `tests/test_anthropic_live.py`; and `VERSION` 0.17.0.]

Under T8, one sentence:

> [2026-10-13-twine-runtime-anthropic-002: the first provider recordings of the wire — fifteen Messages API exchanges the architect made on 2026-10-13 with his own key through probe `twine-anthropic-record`, carried as its paste-back and landed byte-exact by `bin/twine-land-provider-recordings` — live under `fixtures/anthropic/` (beside R1's 2026-10-08 usage object), and the Anthropic adapter's tests replay them through its transport seam.]

## Proposals

- **What:** let R4 run the live smoke test once, by hand, before the loop
  depends on the real transport, and record an SSE `error` event and a 429 if
  either turns up.
  **Why:** `https_transport` has only been exercised offline here: header
  joining, chunking and close on fakes, and the https-only refusal. The
  error-event and rate-limit paths are tested only on doubles built from the
  recordings' bytes.
  **Scope hints:** `tests/test_anthropic_live.py`; a second
  provider-recording probe would land through the same lander.
- **What:** add `HTTPS_PROXY` support to `https_transport`, if your machines
  ever sit behind a proxy (`http.client` `set_tunnel`).
  **Why:** the transport connects directly; no proxy was asked for and none was
  needed when recording.
  **Scope hints:** `twine/runtime/transport.py` only.
- **What:** restate R1's "proposed" in `twine/runtime/contract.py`'s and
  `twine/runtime/registry.py`'s docstrings as ratified, and change "at the pin"
  to "at the floor" in `twine/commands/transitions.py`'s description.
  **Why:** both are stale since 2026-10-12. I left them because this session
  didn't otherwise touch those files.
  **Scope hints:** three docstrings, no behaviour.
- **What:** have R4 read `Turn.retry_after` for the backoff and `Turn.reason`
  for the operator's `fix-request` message.
  **Why:** R2 surfaces both and nothing consumes them yet.
  **Scope hints:** the loop.

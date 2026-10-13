# notes — 2026-10-12-twine-runtime-registry-007 (Arc 2 R1), corrected

This response corrects the held one (`corrects`:
`2026-10-12-twine-runtime-registry-007`). The desk ruled that probes 1
and 3 were the oracle's defects and amended them: the `implements` key
is accepted, and `output = output_tokens − thinking_tokens` stands.
Probe 2 was mine, and §0 is the fix. Everything else is the held
response unchanged, apart from the counts and the docs that describe the
fix. Every changed path is still inside the forecast, so there are no
forecast departures.

## 0. The correction — probe 2

**The defect.** `twine/runtime/boundary.py` imported
`twine.runtime.capabilities.thinking`, `.tool_calling` and
`.usage_accounting` at module level, and `fake.py` imported
`.tool_calling`. The import chain is `cli.main` → `load_registry()` →
`twine.commands.runtime` → `twine.runtime.registry` → `boundary`. So with
any one of those three files removed, every twine verb died at load with
a traceback, instead of `runtime list` reporting the `missing-module` it
was built to report. My validation's removal check happened to delete
`streaming.py`, a declared capability nothing imports, so it could not
see this.

**The fix.**
- The shapes the boundary and the adapters need at import time —
  `ToolSpec`, `ToolCall`, `TOOL_PROTOCOLS`/`NATIVE`/`TEXT`,
  `ThinkingSettings` (+ its error, `THINKING_OFF`) and `token_faults` —
  moved, unchanged, into the new `twine/runtime/terms.py`. That module is
  not a capability module.
- `tool_calling.py` and `thinking.py` now carry only their `CONTRACT`,
  and `usage_accounting.py` carries its `CONTRACT`, `from_anthropic` and
  `UsageMappingError`.
- `boundary.py` and `fake.py` import from `terms`. Nothing outside
  `twine/runtime/capabilities/` imports a capability module, and no
  capability module imports another. The registry's guarded
  `import_capability` is the only way in.

I chose to move the types out rather than resolve capability modules
through the registry at import time. The boundary needs the types when it
is defined, so a lazy lookup would only move the failure from import to
first use. A capability module should stay a registry entry that nothing
else depends on.

**The tests** (`tests/test_runtime.py`, three new):
- `RemovingAnyListedModule.test_each_listed_module_removed_in_turn`. For
  each of the eight declaration entries it builds its own copy of
  `twine/`, `bin/`, `share/` and `VERSION`, deletes that module, and
  checks, all in fresh interpreters:
  - `runtime list --json` is NOT OK, exit 1, with problems exactly
    `[("missing-module", <that capability>)]` and its name in `reason`;
  - `runtime show <it>` is NOT OK;
  - `twine commands --json` is ok;
  - every registered verb's `--help` exits 0 with no traceback.
- `NothingImportsACapabilityModule` (two tests): an AST walk of every
  module under `twine/` outside the capabilities directory, and of every
  capability module, failing on any import of a capability module.

Against the held tree, these fail exactly on the defect: the three
implemented modules' subtests, plus `boundary.py` and `fake.py` in the
import walk. Against this tree they pass.

`validation.sh` gained the same check, "each listed capability module
removed in turn", over all eight modules. The suite floor is now 757.

**Docs:**
- `runtime-contract.md` §2.1 states the import rule and where the shapes
  live, and §1 points at `terms.py`;
- cli-contract §17.5 names the new test;
- the docstrings of `twine/runtime/__init__.py`, `registry.py` and
  `capabilities/__init__.py` follow suit.

## 1. Decisions for ratification

**1.1 TQ-2's file shape (proposed; `runtime-contract.md` §2).**
- The declaration is `twine/runtime/capabilities.toml`. Each
  `[[capability]]` has exactly four keys: `name`, `module`, `status`,
  `summary`. `module` is the full dotted name
  (`twine.runtime.capabilities.tool_calling`), so the TOML value, the
  JSON twin's `module` and `importlib` all use one spelling. A module
  not directly under `twine.runtime.capabilities` is refused.
- The contract is data: `twine/runtime/contract.py`'s frozen
  `Contract`. Its fields are `capability`, `purpose`, `adapter_must`,
  `runtime_promises`, `lands` and `grounds`, and each module exposes one
  as `CONTRACT`. The registry checks that `CONTRACT.capability` equals
  the declaration's name and that no field is empty.
- **Which side declares implementation: the adapter.** Each adapter
  class carries `implements` (a frozenset), and the registry derives
  every capability's `adapters` from those sets. I chose this side for
  two reasons. The code that implements a capability lives in the
  adapter. And R2 and R6 each add an adapter: with the set on the
  adapter, each is one new module under `twine/runtime/adapters/`
  (discovered like `twine/commands/`), and no capability module is
  edited.
- Status lives in the declaration and is held to the adapters.
  `declared` with an implementing adapter, or `implemented` with none,
  is a `status-mismatch`. `experimental` passes either way.
- A malformed declaration is a `DeclarationError` naming every bad
  entry; the verbs report it NOT OK with that reason. A parity or loading
  fault is a named problem on the registry, not an exception.

**1.2 Q-3's contract text (proposed; `runtime-contract.md` §1; the
shapes it names now live in `twine/runtime/terms.py`, §0).** It is
written as a contract: what an adapter must do and what the boundary
promises, for each of tool calling, thinking, usage accounting and the
stop set. Three interpretive calls in it you should check:
- **A turn either asks for tools or stops, never both.** The stop axis
  has no `tool-use` key, and the seed's §4.3 says `end_turn` *with no
  tool call* ends a worker's turn. So a turn that asks for tools has
  `stop` `None` (`Turn.continues`), and the boundary refuses a turn with
  both or neither. R2 maps Anthropic's `tool_use` stop reason onto
  `stop` `None`.
- **The boundary accepts every key of the axis**, including the
  loop-only `cap-reached`, `cap-unchecked` and `killed`. Refusing a
  provider's mapping onto those three would mean spelling them in
  code, which is exactly the second spelling the brief forbids. It is
  written down as a defect for review, and Proposal 3 suggests a
  table-side fix.
- **The boundary does not refuse an unknown tool name.** Per §4.3 that
  is a tool error the loop returns as a result, not a crash. It does
  refuse malformed calls: missing ids or names, reused ids, arguments
  that are not an object.
- The boundary also refuses an adapter declaring the `text` tool
  protocol, naming TQ-3, because no parser exists yet. That refusal is
  the R6 seam.
- `BOUNDARY_CAPABILITIES` spells the three capability names in
  `boundary.py`. These are capability names, not stop keys, and a test
  holds them to the declaration.

**1.3 The fake adapter's script format (`runtime-contract.md` §3).** A
list of turn objects: `text`, `thinking`, `tool_calls` (each with
exactly `id`/`name`/`arguments`), `stop` (required, `null` when asking
for tools) and `usage` (required, exactly the five classes). Unknown
keys refuse at build time, naming the turn. The fake's stop and usage
mappings are both the identity. So a provider word scripted as a stop
(`end_turn`) reaches the boundary unmapped and is refused, which is how
the tests show that the adapter's mapping is the only translation. The
fake does not judge counts either: a test can script a bad count and
watch the boundary refuse it.

**1.4 `twine runtime list` does not render contracts** — only `show`
does. The list stays one screen and ends with a pointer to `show`.

**1.5 DEVIATION, ratified at the HOLD — `from_anthropic`'s `output`
class.** (The desk ruled the brief's table wrong and this mapping
correct, and amended the checkpoint's probe 3; kept as shipped.) The brief's
table maps `output` ← `output_tokens` whole, and `thinking` ←
`output_tokens_details.thinking_tokens`. Shipped as written, that bills
thinking twice:
- `twine.spend`'s classes are disjoint ("tokens counted in `thinking`
  are not also in `output`").
- `spend.record_cost` adds `thinking × output price` on top of
  `output × output price`.

So a call with 40 output tokens, 25 of them thinking, would cost 65
output-priced tokens. The brief's own justification ("never counted
twice") is the intent, so I implemented that: when thinking is
reported, `output = output_tokens − thinking_tokens`, and a thinking
count above `output_tokens` is refused. When thinking is not reported,
`output` is `output_tokens` whole and `thinking` is `None`, exactly as
the brief says.
- On the recording (thinking 0) both readings give `Tokens(18, 4, 0, 0,
  0)`.
- `tests/test_runtime.py` proves the cost equals `output_tokens` at the
  output price.
- (Held response: "Checkpoint risk: if the blind checkpoint asserts
  `output == output_tokens` on an edited copy with nonzero thinking, it
  will HOLD on this line." It did, as probe 3; the desk ratified the
  mapping.)

**1.6 DEVIATION — `cli-contract.md` §17, not §16.** §16 already exists
(the recorder and the lander). Section numbers are stable, so the
runtime verbs are §17, and the section says so in one line.

**1.7 Strictness on `null`.** `from_anthropic` refuses a `null` count,
even for the optional cache keys ("a non-integer … count raises"). If
R2 finds against the SDK that the API sends `null` for an absent cache
count, the fix is to treat `null` as absent for those two keys only.
That is a one-line change, and I'd rather it be a recorded decision
than a guess now.

**1.8 Fixture walks: nothing moved.** `tests/test_fixtures.py`,
`tests/fixture_rule.py` and `bin/twine-land-recordings` already walk
`fixtures/bale-*` only (glob `bale-*`, `FIXTURES_DIR / PINNED`, and
regexes anchored on `` `bale- ``). The new `fixtures/anthropic/` sits
beside them untouched, its README row has a shape none of their
regexes match, and no test was moved or rescoped.

**1.9 Two files touched outside §1–§4's list, both inside the
forecast.**
- `twine/transitions.py` gained `stop_keys()`, the "through
  `twine.transitions`" reader. It refuses a table without a usable
  `stop` axis rather than returning a guess, and leaves the rest of the
  module unchanged.
- `claude/context/cli-contract.md` §13.1 said "No provider usage has
  been recorded yet", which stopped being true this session. I added a
  dated parenthesis rather than editing the paragraph.

## 2. Where to look closely

- `twine/runtime/boundary.py` `Boundary.turn_faults`: this is the
  contract in code.
- `twine/runtime/capabilities/usage_accounting.py` `from_anthropic`:
  see §1.5.
- `twine/runtime/registry.py` `import_capability`: for a directory
  other than the real one (tests' copies only), it loads by file path
  and registers the module in `sys.modules` for the duration of the
  import only. A dataclass body needs that; without it every module
  defining a dataclass fails to load. The real package always imports
  normally.
- The five `declared` contracts (`prompt_caching`, `window_accounting`,
  `streaming`, `sandboxing`, `suspend_resume`). These are my reading of
  §4.1 and §4.3. Each is what R2–R5 will implement against, so wording
  you disagree with is cheaper to fix now.

## 3. Tests

- `tests/test_runtime.py`, new, 98 tests (95 in the held response, plus
  §0's three) in seven sections:
  - the declaration (the eight in §4.1 order, the four keys, every entry
    loads, the closed status set, three implemented and five declared,
    `delegate` absent);
  - every malformed declaration refused;
  - parity by name with the test's own directory listing and tomllib
    (each failing by the name at fault), and each detector fired on a
    copy edited to be wrong;
  - `from_anthropic` on the recording and edited copies;
  - the stop set equal to the table's axis three ways, no stop key
    spelled under `twine/runtime/`, and `stop_keys` refusing broken
    tables;
  - the fake through the boundary (the tool-call-then-`end-turn`
    exchange, every axis key passing, provider words refused,
    both/neither, bad usage, thinking off, ids), spawn-time constants,
    adapters the boundary cannot host, and script refusals;
  - the verbs: JSON twins, human lines, never touching `ctx.run`, an
    unknown name, and a copy of the tree with a module planted, one
    removed and the declaration broken, run end to end;
  - no forbidden import and no environment read under `twine/runtime/`;
  - the recording's README row.
- `tests/test_registry.py`:
  `test_this_sessions_verbs_are_registered` gains `runtime list` and
  `runtime show`, and there is one new test,
  `test_discovers_runtime_module_as_a_group`.
- `tests/test_json_discipline.py`: `argv_for` gives `runtime show` a
  name (`usage-accounting`), so the two discipline tests cover both new
  verbs.

**Count:** 658 before, **757** after (98 + 1 new); `OK (skipped=3)` as
before.

## 4. Validation

`validation.sh` runs everything from the staged root under `python3 -I
-B`:
- syntax of every module;
- the suite, requiring at least 757 tests;
- the three `runtime` checks end to end, including a planted module and
  a removed one on temp copies;
- since the correction, each of the eight listed modules removed in turn
  on its own copy: `runtime list` NOT OK naming that capability, `twine
  commands` ok, every verb's `--help` exit 0 (§0);
- the recording's bytes and hash, and `from_anthropic` on it;
- the import walk;
- all 90 files under `fixtures/bale-*` checked by sha256 against the
  request manifest's `base_files`, with none added or removed;
- the four untouched files by sha256;
- `VERSION` checked with `cmp`;
- the crafted INDEX-coherence block, adapted in two ways:
  - the crafter's `if ! … then exit_code=1` wrapper became the
    `run_check` wrapper's job;
  - entries that are `<…>` placeholders are exempted and printed as a
    `[SKIP]`. INDEX deliberately lists twine's state-directory files as
    `<state-dir>/spend.jsonl` ("not in this repository"), and the stock
    block fails on that pre-existing entry. The exemption is
    commented in the script.
- no `__pycache__`.

It never reads `claude/checkpoints/`: no walk descends there, and the
pycache `find` prunes it.

I ran it twice on a staged copy (the base tree with `files/` overlaid,
`apply.sh` run, and the manifest placed as `.bale-manifest.json`). Both
runs passed.

I also ran it once on the unmodified tree. Every session-specific check
failed there, as it should: the suite floor, the five runtime-verb
checks (the per-module removal among them), the recording, `from_anthropic`, the import walk (its file does
not exist yet), `VERSION` and INDEX coverage. The only checks that
passed are the ones asserting what must *not* change, plus two that are
never session-specific: syntax, the `fixtures/bale-*` and four-file
hashes, and no bytecode. The one claim, the suite, is `observed`.

## 5. The seed annotation (for tidy8)

Verbatim and complete. Under §5.2, after the Arc 2 cut's annotation:

[2026-10-12-twine-runtime-registry-007: R1 landed — the capability registry (`twine/runtime/capabilities.toml` declaring the eight capabilities §4.1 names, one module each under `twine/runtime/capabilities/` with its contract, three `implemented` — `tool-calling`, `thinking`, `usage-accounting`, by the fake adapter — and five `declared`, parity by name), the adapter boundary (`twine/runtime/boundary.py`) with its one stop spelling — the transition table's `stop` axis, read through `twine.transitions.stop_keys` and spelled nowhere in code — the fake transport adapter `fake` the tests drive, `from_anthropic` held to the architect's 2026-10-08 recording (`fixtures/anthropic/messages-usage-2026-10-08.json`), the two verbs `twine runtime list` and `twine runtime show`, and `VERSION` 0.16.0.]

Under the register's TQ-2:

[2026-10-12-twine-runtime-registry-007: proposed, awaiting ratification — the shape is written in `claude/context/runtime-contract.md` §2: the declaration `twine/runtime/capabilities.toml` (name, dotted module, status, summary), one module per capability exposing a `Contract`, three statuses held to the adapters, and each adapter declaring the capabilities it implements.]

Under the register's Q-3:

[2026-10-12-twine-runtime-registry-007: proposed, awaiting ratification — the contract text is `claude/context/runtime-contract.md` §1, the four things the boundary abstracts each with what an adapter must do and what the boundary promises, implemented by `twine/runtime/boundary.py`.]

## Proposals

**1. Correct two stale "no provider usage recorded" lines.**
- *What:* `twine/spend.py`'s module docstring says a provider mapping
  will be "verified against a recording when one exists; none exists
  yet", and `tests/helpers.py` (around line 736) says the same. Change
  both to point at `from_anthropic` and the recording.
- *Why:* both are false now. I left them alone because neither file is
  in §1–§4's list and `spend.py` is the spine.
- *Scope hints:* two docstrings; R2 is a natural place.

**2. Verify the Anthropic edges against the SDK in R2 before mapping.**
- *What:* check the exact `stop_reason` names (`end_turn`, `tool_use` →
  `None`, `max_tokens`, `refusal`, …) and whether `usage` ever carries
  `null` for the cache counts (§1.7).
- *Why:* the seed already says stop names are verified against the SDK
  when the loop is built. `from_anthropic`'s strictness on `null` is the
  one place my choice could bite a real response.

**3. Say in the table which stop keys a provider may produce.**
- *What:* add a per-key marker to `share/transitions.toml`'s `stop`
  axis saying who produces it. For example, a `loop_keys` list naming
  `cap-reached`, `cap-unchecked` and `killed`.
- *Why:* the boundary could then refuse an adapter that maps a
  provider word onto a loop-only stop, without spelling a stop key in
  code (§1.2).
- *Scope hints:* `share/transitions.toml` is R2's per the brief (it
  already owns the provider axis's moves); `twine.transitions` would
  expose the subset beside `stop_keys`.

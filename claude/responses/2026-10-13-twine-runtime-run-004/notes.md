# Notes — 2026-10-13-twine-runtime-run-004 (Arc 2 R4, `twine run`)

`twine run BUNDLE` exists and runs end to end with the fake adapter against a
stub bale: open, register, sandbox, unpack, spawn, transcript, loop, dry run,
apply line. 1027 tests (958 + 69), `VERSION` 0.19.0. The loop is
`twine/runtime/loop.py`; the verb `twine/commands/run.py`; the contract
`runtime-contract.md` §7 and `cli-contract.md` §18. Everything shipped is
inside the forecast; no `forecast_departures`.

## 1. Decisions the brief left to me (brief §4)

1. **The surface note** is `loop.SURFACE_NOTE`, four short paragraphs: no one
   reads the conversation live; the working directory is the sandbox home and
   file tools take relative paths; the request is at `request/`
   (`manifest.json`, `AGENT.md`, `README.md` — the brief — `context/`), read
   with `read_file`/`list_dir`, not in the conversation; `shell` is bash in
   the home with no network where the sandbox can turn it off; the session
   ends with `deliver` on a tarball built in the home (the crafter and lint
   are under `request/tools/`); `escalate` for the planner, `probe` for the
   operator's machine; a turn ending with neither a tool call nor a deliver
   ends the session. It names no sid, so it is one constant for every
   session (cache-stable). A test holds each required item and searches it
   for provider and model names, `model`, `provider` and the sid.
2. **The input estimate**: the request as twine would send it (note, tool
   definitions, messages), JSON-encoded, UTF-8 bytes **/ 2**, rounded up.
   Deliberately high: English and code run 3–4 bytes a token, and only hex
   or base64 come near 2, so the check prices a worst case above the real one
   rather than below it. Easy to tune: `BYTES_PER_TOKEN_ESTIMATE`.
3. **Continue-turn**: the partial content is kept as its own assistant turn,
   unedited (so a thinking block goes back byte for byte), followed by a user
   turn. Never folded into the user turn, and never ending on the assistant
   turn (no prefill: the recorded `/v1/models` carries no prefill capability
   to check, so the user-turn ending is the safe one). The user turn first
   answers any `tool_use` block in the partial content with an `is_error`
   "not run" result — the API refuses a tool_use left unanswered — then says:
   "Your last turn stopped at the output limit before it was finished.
   Continue exactly where it stopped; do not repeat what you already wrote."
4. **`--max-turns`** stops before call N+1 (after the abort check, before the
   cap check), so `turns` equals N. Retries count as calls.
5. **Progress on stderr by default**, one `[twine] run: …` line per step,
   both modes. A run is long and unattended and that is the operator's only
   live view; `--verbose` adds the leveled log lines as for every verb.

## 2. Where I departed from the brief, and why (please ratify or correct)

- **The in-flight reader did not keep unknown keys.** The brief said "a
  reader keeps unknown keys, so Arc 1 readers are unaffected". In fact
  `read_inflight` refuses any key but the four (and `twine status` names such a
  record a fault). Rather than loosen it, I named the key: `runtime` is an
  optional fifth key with exactly its six (`RUNTIME_KEYS`), validated like
  the rest. `carry bundle`, `status` and `run` all read the same record.
  `_compose` keeps an earlier `runtime` on a `second-desk` append, and an
  `opened` drops it with the rest of the record.
- **`request` transcript lines carry deltas, not the whole list.** Each line
  has `appended` (the messages added since the last `request` line) and
  `messages_total`. Joined, the lines are the conversation as sent. Logging
  the whole list per call grows quadratically: 200 calls over a 500 KB
  conversation is tens of MB. After a turn that ends the run, one more line
  with `sent: false` carries the tool results that never went out, so R5 can
  rebuild the whole conversation.
- **`continue-turn` past its bound.** The table's description says "past the
  bound the turn stops as malformed-shape". The brief says `stopped`. The
  loop reports `stopped` with the stop the turn actually carried,
  `max-tokens`, and its move `continue-turn`. If you want the table's reading
  (stop `malformed-shape` → `respawn-from-request`), that is a one-line
  change in `Loop.continue_turn`; one of the two texts should change.
- **An adapter defect has no row.** R1's §1.6 said a `BoundaryError` "will be
  a row of the transition table". Your brief forbids new rows, so a boundary
  refusal, or an adapter that raises (the fake's script running out, an
  unreadable usage, an edited conversation), ends the run `stopped` with stop
  and move null and the defect quoted. Proposed below.
- **`move` after a dry run is the `apply-outcome` row's.** The twin's `move`
  is "the table's move for `stop`"; on a deliver, `stop` is null. You also
  wrote that the loop reports the apply-outcome row's move, so `move` carries
  it: `operator-applies` on `delivered`, `admit-or-return` on a
  `scope-drift-refused` dry run, and so on, with `actor` beside it.
- **`stop` on `ended`.** I followed your table literally: null on prose and on
  `max-turns`. On the rarer `ended` shapes (an exchange block, a light block
  for another sid) it is `end-turn` with move `classify-final-text`. A light
  block that is not intact, or not this sid's, is not carried: `ended`,
  shape `light`, with the reason.
- **The running record is not cleared while it names a live tool group.**
  The brief says the record is cleared on any outcome. When a tool's run
  returned with `group_survivors`, its entry stays in the record (R3 §6.7),
  and clearing the record would hide that group from `twine kill`. In that
  case only, the record is kept and `running.note` says why. Normal runs
  clear it (tested).
- **The key is kept from bale too.** The courier's `open` and
  `apply --dry-run` run in twine's environment *minus* `ANTHROPIC_API_KEY`
  (a `dataclasses.replace`d Context). This only applies inside `twine run`:
  `carry bundle` and `carry response` run by hand keep Arc 1's behaviour.
  A test reads the environment the stub bale saw.
- **The request's top directory is stripped.** "Every member as it is in the
  tarball" read literally would put the manifest at
  `request/request-004/manifest.json`, which contradicts the surface note's
  `request/manifest.json`. `unpack_request` strips bale's one top-level
  directory (and unpacks a tarball without one as it is). Every member goes
  through the `data` filter before anything is written, so a refusal
  extracts nothing. One thing to know: the filter **strips** a leading `/`
  rather than refusing it, so an absolute name lands inside `request/`. That
  is not an escape and the run goes on (tested). `..`, links pointing out and
  devices refuse.
- **`--thinking off` sends `{"type": "disabled"}`**, not nothing. Sending
  nothing leaves the model's default, which may think, and the boundary
  refuses a thinking turn on a session spawned with thinking off. Sonnet
  5.5, Opus 5.5 and the Fable models refuse `disabled` (R2's recording);
  that comes back as `request-refused` → `fix-request`.
- **Code outside the three new files, all inside the forecast:**
  `twine/process.py` gained `lead_own_group` (setsid lives there because no
  module under `twine/runtime/`, nor `run.py`, may import `os`).
  `twine/transcript.py` is a new top-level state module beside
  `spend`/`inflight`/`kill`. `carry_bundle.open_bundle` and
  `carry_bale.check_response` are the two verbs' bodies split out, unchanged,
  so `run` calls functions, not subprocesses. The fake's script gained two
  optional keys, `retry_after` and `reason` — needed for "retried with the
  scripted `retry_after`" — documented in contract §3. `twine status` grew
  `transcripts`/`sandbox` in `state_present` (now seven keys) and four list
  keys, which changed six pinned assertions in `tests/test_status.py`.
  `StubBale` grew `exit_codes`, `calls()` and `environments()`. The
  "nothing removes an in-flight record" guard in `test_carry_bundle.py` now
  allows exactly `remove_inflight`, called only from `run.py`. The R3 test
  docstring "nothing drives the fake" is reworded: `run --adapter fake`
  does, reaching it by name through the registry.
- **`setsid` and the terminal.** Typed at an interactive prompt, `twine run`
  already leads its own group (job control gives each job one), so nothing
  changes and Ctrl-C still reaches it. setsid happens only when it is not a
  leader (a script without job control, a test child, a PID namespace).
  That leaves the controlling terminal, so Ctrl-C from a parent script's
  terminal no longer reaches it; `twine kill` does.

## 3. Where to look on review

- `Loop.move` and the three it dispatches to: the one branch is on the
  **move name** the stop row names (never on a stop key, which nothing under
  `twine/runtime/` spells; the loop's own outcomes come from
  `spend.STOP_CAP_*` and `kill.STOP_KILLED`).
- `Loop.run_tools`: the order of transcript lines and the "not run" answers
  after `escalate`/`deliver`.
- `run.cmd_run` / `finish_running`: the `finally` that clears the record on
  every path, internal errors included (which still exit 2 via the
  dispatcher, after a `run-end` line).
- `unpack_request`: the filter pass before any write.
- The anthropic path is constructed in a test (`TheAnthropicSpawn`) but never
  called — no model in the tests, as the brief requires. The first real call
  is yours, by hand.

## Proposals

- **What:** a stop key and row for an adapter defect — a boundary refusal or
  an adapter's own exception (`adapter-defect` → probably
  `respawn-from-request`, or a twine/operator move that names the adapter).
  **Why:** R1 §1.6 promised one and D17 wants no path without a move; R4 had
  to report it as a move-less `stopped`. **Scope:** `share/transitions.toml`,
  `Loop.call`, the boundary's docstring; a table session.
- **What:** reconcile `continue-turn`'s table description with the loop: past
  three continuations, `stopped` with stop `max-tokens`, or `malformed-shape`.
  **Why:** the two texts disagree today (§2). **Scope:** one description, or
  `Loop.continue_turn`.
- **What:** R5 rebuilds the conversation from the transcript's `request` lines
  (`appended` joined, `sent: false` included) and re-runs the loop with
  `Loop(messages=…)`. **Why:** the shape was chosen for it (§2); the loop
  already takes its starting messages as an argument. **Scope:** R5.
- **What:** the other half of R3's lifecycle proposal: removing a delivered
  session's sandbox home once its response is applied (`twine status` lists
  them now). **Why:** homes accumulate, and a delivered home holds only the
  tarball the operator already applied. **Scope:** a verb or an `apply`-time
  step; out of scope here.
- **What:** a gated live smoke of `twine run --adapter anthropic` beside
  `tests/test_anthropic_live.py` (skipped unless `TWINE_LIVE_SMOKE=1` and a
  key), driving a one-turn bundle to `ended`. **Why:** nothing in the tree has
  run the loop against a real model, and the system prompt, the cache
  breakpoints and the continue turn only meet the provider there.
  **Scope:** `tests/`, a throwaway bundle.

## 5. The seed annotation (verbatim and complete, for tidy9)

Under §5.2, after R3's annotation:

> [2026-10-13-twine-runtime-run-004: R4 landed — `twine run BUNDLE`
> (`twine/commands/run.py` over `twine/runtime/loop.py`). The sequence:
> `carry bundle` opens the session; the runtime leads its own process group
> and registers it in the running record before it spawns anything; the
> sandbox is made and the request unpacked at `request/` with tarfile's
> `data` filter; the adapter (`anthropic`, or `fake` with `--script`) is
> spawned behind the boundary, the key handed to it and to nothing else; the
> transcript and the in-flight record's `runtime` fields are written; and the
> loop runs — the opener as the first turn under a model-agnostic system
> prompt, the abort file and the pre-call cap check before every call, each
> call's usage appended to `spend.jsonl`, and the transition table's moves
> performed from its rows (`classify-final-text`; `continue-turn`, at most
> three times; `retry-with-backoff`, at most five retries; `return-tool-error`
> for a failed tool; every other move named and the run stopped). The
> outcomes: `delivered` (the dry run clean, the apply line printed — twine
> applies nothing), `suspended`, `ended`, `stopped`, `killed`, `cap-reached`,
> `cap-unchecked`, `refused`. Every step is a line of
> `<state-dir>/transcripts/<sid>.jsonl`. On any end the running record is
> cleared; on `delivered` the in-flight record is removed and the sandbox home
> kept; otherwise both are kept. `VERSION` 0.19.0. With R1–R4 landed, the
> first milestone of the Arc 2 cut is reached: the worker side of the courier
> is twine's.]

Under D11:

> [2026-10-13-twine-runtime-run-004: landed — the include set sits on disk at
> `request/` in the worker's sandbox home, the opener is the first user turn,
> and the system prompt holds only the tool definitions and the surface note
> (runtime-contract.md §7.1–§7.2).]

Under TQ-1:

> [2026-10-13-twine-runtime-run-004: landed — a hosted session's transcript
> lives at `<state-dir>/transcripts/<sid>.jsonl`, one append-only JSON line
> per step (`run-start`, `check`, `request`, `turn`, `tool-call`,
> `tool-result`, `move`, `retry`, `abort`, `adapter-error`, `run-end`), its
> `seq` continuing across runs (runtime-contract.md §7.6).]

Under §4.4:

> [2026-10-13-twine-runtime-run-004: the loop exists, so both obligations are
> now due — the bale-src `AGENT.md` §11.7 surface row for twine-hosted API
> workers, and nisaba-src's `nisaba-seed.md` §3.3 annotation; the desk's to
> send.]

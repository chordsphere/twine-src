# notes — 2026-10-03-twine-cost-spine-005 (Arc 1 session 5a, the cost spine)

## Re-attempt after the HOLD

This response corrects this session's first one (`corrects` names it). Both judges held: the
checkpoint on its probe "the suite passes", and my validation on the suite and on its own
no-prices check. There were two faults, both in tests. The cost spine's code is
unchanged; the contract changes by one sentence (§13.4).

**1. My no-prices test scanned the whole tree.** It meant to prove twine ships no prices, but
it read every file except `tests/` and dot-paths. In bale's staging, two more files sit in the
tree: the response's own `validation.sh`, which writes a price double for its end-to-end check,
and the blind checkpoint, which carries one of its own. The test found both and failed the suite under
the checkpoint and under my validation. My `validation.sh` had the same whole-tree check. That
was a defect in the test, not in the work, but it is still mine.

It was also wrong in principle. A worker-authored test has no business reading
`claude/checkpoints/`. Mine did, and its failure message put a fragment of the checkpoint into
the relay block. I have not used that fragment for anything. The fix removes the path entirely:
the test and the `validation.sh` check now read only what twine ships, by allow-list (`bin/`,
`twine/`, `share/`, `fixtures/`, `claude/context/`, `claude/INDEX.md`, `README.md`, `VERSION`,
`twine-seed.md`, `bale.toml`). A new test asserts the scan never reads `claude/checkpoints/`,
`claude/responses/`, `tests/` or `validation.sh`. I reproduced the HOLD's staging conditions
here: the old test fails on exactly the relay's two paths, and the new one passes.

**2. A race in two pre-existing timeout tests** (`test_process.py`, `test_carry.py`; landed in
2b-i). The runner SIGKILLs the process group and returns once the pipes close. A killed `sleep`
closes its file descriptors slightly before the kernel marks it a zombie, so one
`process_alive` check right after the run can catch it in that gap. The gap is wider on a loaded
machine, and the checkpoint and validation ran back to back in a sandbox. It did not reproduce
here, 0 of 30 runs under CPU load, so I am reasoning from the code, not from a recording.

The fix is in the tests: `tests/helpers.py` `dies_within` polls for up to 3 s, used at the
three single checks (two in `test_process.py`, one in `test_carry.py`). Each test's own elapsed
bound is unchanged, so "promptly" is still asserted. I did not change `twine/process.py` to
wait for every member of the group to be reaped. The contract (§10.6) promises the group is
killed, not that the run returns after its last member is gone, and that is a design question
for whoever next touches the runner. If the HOLD's sleep was in fact a kill that missed, this
fix will not hide it: a live process past 3 s still fails, naming the pid.

`tests/test_process.py` and `tests/test_carry.py` are new to this response's change set. Both
are inside the `tests/` forecast, so there are still no departures.

The suite is now 322 tests (60 in `tests/test_spend.py`), green on Python 3.11, 3.12 and 3.13.

## The session's work

This session lands D15's cost spine without the kill-switch: twine's usage record, the running
totals over it, and the hard cap's pre-call check. They live in one pure module,
`twine/spend.py`, with two thin verbs over it, `twine spend totals` and `twine spend check`.
`VERSION` is now 0.5.0. The suite has grown from 261 tests to 322 (60 of them in
`tests/test_spend.py`) and is green on Python 3.11, 3.12 and 3.13.

Every path is inside the write forecast, so there are no departures to admit. `twine-seed.md`,
`fixtures/`, `share/`, `bale.toml` and `bin/twine` are untouched, and `validation.sh` checks each
of them by hash. No probe was needed. Nothing reaches a network, a subprocess or a provider SDK,
and nothing in the tree claims to be an API response.

## What landed, against the brief's items

1. **The record.** Each line of `<state-dir>/spend.jsonl` carries `sid`, `served_sid` (present,
   nullable), `model`, and `tokens` with exactly the five classes. Twine's writer adds
   `recorded_at`, and readers keep any other key. One validation rule, `record_faults`, serves both
   the writer and the reader, so a line the writer accepts is always a line the reader accepts.
2. **The state directory.** Resolved as the brief orders it, with one addition (below).
3. **Prices.** Operator data in TOML. Twine ships none, and a test scans the shipped tree for a
   price table with a number in it. An unpriced model is the refusal `unpriced-model`, naming it.
4. **`spend totals`.** Carries the brief's keys, plus `served_calls` and `models` per session.
5. **`spend check`.** Implements the brief's inequality. A refusal by the cap carries `stop:
   "cap-reached"` and the numbers. Every other refusal names itself and is never an admission.
6. **Q-6.** Proposed below, as the brief asks.
7. **One function, two faces.** The loop calls `spend_totals` and `check_call`, and so do the
   verbs. A test asserts that the verb's JSON equals the function's `as_json()`.
8. **Docs.** Contract §13 and its §2 line, README, INDEX and `VERSION`. §13.1 is where a reader of
   the stream learns that no provider usage is recorded yet and that `twine-usage-record` will
   record it.

## Decisions to ratify

These are the calls I made where the brief left room, roughly in the order I'd want them read.

- **Money is exact.** Prices parse as `Decimal` (`tomllib`'s `parse_float`), the cap parses as a
  `Decimal`, and every sum and the cap comparison are made on exact values. Only the JSON twin
  rounds, to a double, at the edge, and the contract says so. Without this, a session at exactly
  its cap would be refused or admitted depending on float noise. A test pins the case: $0.1 spent
  plus a $0.2 worst case against a $0.3 cap is admitted, where doubles would refuse.
- **A record whose `served_sid` equals its `sid` is malformed.** The brief says `served_sid` is
  `null` when the call served its own session. A self-naming record would be counted twice in the
  check's "own plus served", so the writer refuses it and the reader names it, rather than
  silently treating it as null.
- **A session named only as a `served_sid` gets a totals row** with `calls: 0` and its served
  cost. Otherwise "what did the dial cost session S" (T11) would have no row to read whenever S
  made no calls of its own. In that row `thinking` is `0`, not `null`, because `null` means "the
  provider did not report thinking", and no call was made.
- **Totals price every record.** An unpriced model anywhere in the stream makes `spend totals`
  not ok, even with `--sid`, because `total_cost_usd` is the whole stream's. Tokens and calls
  still render; every cost is `null`, since a partial sum is never reported as a total. The
  check is narrower: it prices only the session's own and served records plus the call's model,
  so another session's unpriced history does not block a call. A malformed line anywhere blocks
  both, because a stream that cannot be read whole cannot say what any session spent.
- **The price file is validated whole.** A typo in a row you will use tomorrow is reported
  today. `spend totals` reads the price file only when there is a record to price, so an empty
  or absent stream is ok with no price file at all.
- **No state directory is a refusal.** With no flag, no `$TWINE_STATE_DIR`, and no absolute
  `$XDG_STATE_HOME` or `$HOME`, the verbs refuse with `no-state-dir`. The working directory is
  never a fallback: that is exactly how spend would land in a project's tree. A relative
  `$XDG_STATE_HOME` is ignored, per the XDG spec. A side effect is that the test helpers' empty
  environments make any test that forgot `--state-dir` refuse loudly instead of touching a real
  path.
- **An empty `--state-dir` or `--prices` is refused** (`bad-argument`), never read as an absent
  flag. An explicit request for a location must not quietly become the real default. An empty
  environment variable still counts as unset, as is conventional.
- **A bad `--cap`, `--input` or `--max-output` value is a named refusal** (`bad-argument`, exit
  1), not an argparse usage error. This matches `carry probe`'s `--timeout` refusal and keeps
  the one-JSON-line contract. A missing flag is still argparse's exit 2.
- **The writer is durable and refuses to glue.** It makes one `O_APPEND` write, then an fsync,
  creating the directory as 0700 and the file as 0600. It refuses to append onto a stream whose
  last line is not LF-terminated, because gluing a record to a torn line would corrupt both; the
  reader names such a line. N4 says spend history is the one thing deleting twine's state loses,
  so I treated it as worth an fsync per call.
- **`refusal` is a closed set** (`twine.spend.REFUSALS`, 8 kinds), and `stop` is set only on
  `cap-reached`. A cap that cannot be checked has `stop: null` and its own refusal. The Arc 2
  loop still needs a stop key for that case. The table is out of scope here, so it is proposed
  below.
- **Report shape.** Every path through a verb, including no state directory and a bad argument,
  emits the same key set, with uncomputed values `null`. A test walks the paths and asserts this.

## What is not known, and where it will bite

- **Cache-write tiers.** The record has one `cache_write` class and the price row one
  `cache_write` price, as the brief pins. If the `twine-usage-record` recording shows a provider
  reporting cache writes at more than one price, one class cannot carry that. The adapter would
  then need a sixth class, or a price per tier, and that change would be visible in the record.
  I have not guessed which; the recording decides it.
- **Thinking reported separately or not.** Both cases are handled: `thinking: null` means it is
  inside `output`. The worst case bounds thinking inside `--max-output` at the output price
  either way, so the check does not depend on which the provider does.
- **`model_identity`.** I filled it as `anthropic:claude-opus-5-5`, the session's configured
  model identifier. The serving model can differ from the configured one, and I cannot see a
  picker to confirm it.

## Q-6: the hard cap's scope, proposed

The seed recommends both per-session and per-arc caps, checked before each call, configured in
the office's house rules. I agree, and this is the shape I'd propose:

- **Two envelopes per call, both checked, the tighter binds.** A call is admitted only if every
  envelope it falls in admits it. A refusal names which envelope refused (`envelope: "session"`
  or `"arc"`) beside `stop: "cap-reached"`. One stop key covers both, and the move `stop-at-cap`
  already describes the arc case ("in-flight work hands off as a bailout would").
- **Per-session**, as landed: own plus served spend against the session's cap.
- **Per-arc.** An arc is keyed on the **office's arc id**: the drafting-table's identifier for
  the plan its sessions belong to. Membership (which sids are in arc A) is the office's
  declaration, read by twine and never inferred from sid slugs or dates (N4: twine holds no
  intent). Arc spend so far is computed from the records whose `sid` **or** `served_sid` is a
  member, **each record counted once**. Summing the members' "own plus served" would count
  twice a record where one member served another (a compare session in the same arc as the
  session it compared).
- **The record grows no `arc` key.** Membership stays in the office, so a split, a supersede or
  a re-planned arc never asks anyone to rewrite append-only spend history. The cost is that an
  arc's spend is only computable with the office's membership in hand. I think that is right:
  the arc is the office's concept.
- **House-rule shape** (illustrative; values are the operator's):

  ```toml
  [cap]
  session_usd = <USD>                 # default per-session cap
  [cap.work_class."<class>"]
  session_usd = <USD>                 # per work class, overriding the default
  [cap.arc."<office arc id>"]
  usd = <USD>                         # one envelope per arc
  ```

  An absent cap is a refusal to call, never "uncapped". That is D15's "refuse loudly" applied to
  configuration, and the operator who wants a large cap writes one.
- **The function's shape when it lands.** `check_call` takes a list of envelopes (a name, a cap,
  a sid set) instead of one cap. The per-session check is then the one-envelope case, so today's
  callers do not change.

A per-operator, per-period cap (a monthly wallet) is a third envelope of the same kind. I would
leave it until the scheduler has something to spend unattended.

On **Q-8**, twine's side is now real: the stream exists and is the owner. Whether bale's
`attempts[].cost` mirrors it remains bale-src's question. The record's `sid` and `served_sid`
are what a mirror would key on.

## An independent check

Before packing, a separate agent that had not seen the work checked the code and the contract
against brief §3. It ran the CLI on hand-made cases with invented models and prices, and worked
the arithmetic by hand. It confirmed every pinned interface and found one gap: `--state-dir=`
(empty) fell through to the `$HOME` default. That is now refused, with a test, as above. It also
listed the readings I chose where the brief was silent, and they are the ones in "Decisions to
ratify".

## Places to look closely

- `twine/spend.py` `check_call`: the order of the refusals (arguments, stream, prices, unpriced,
  cap) and the reason texts.
- `twine/spend.py` `accumulate`: served attribution, and the "no partial sums" rule.
- Contract §13.6 and §13.7: the refusal tables are the interface the loop will key on.

## Validation

`validation.sh` ran twice, as TARBALL.md §7.2 asks.

**On a staged tree**, built the way the HOLD showed bale's staging to be: the base with
`files/` overlaid, `apply.sh` run, the manifest at `.bale-manifest.json`, `validation.sh` at the
root, and a stand-in checkpoint at `claude/checkpoints/<sid>.sh` carrying a price double. Result:
exit 0, all 9 checks `[PASS]`, and the claim reconciled `[agree]`. I ran it a second time with
eight busy loops pinning the CPUs, and it passed again. It takes about 17 s, most of it the suite.
Afterwards the staged tree matched my working tree byte for byte, apart from what staging adds.

**On the unmodified base:** exit 1. The five session assertions `[FAIL]`: syntax (the new files
are absent), the version, the registry, end to end, and the docs. The four invariants pass on
both trees, as they should:

- the suite;
- the untouched-paths hashes;
- no prices shipped (now also with the stand-in checkpoint present, which the first response's
  check would have failed on);
- no bytecode.

The end-to-end check runs the real entrypoint under `-I -S` against a temp state directory
double, with invented prices for an invented model. It checks: totals with served spend;
admitted at exactly the cap; refused one hundredth of a cent under it, with `stop` and the
call's numbers unchanged; an unpriced model; a malformed line named by number; and that the
checks wrote nothing.

The `claims` block holds one claim, the suite: `pass`, observed. The session assertions are
listed in `validation_will_run` and not claimed, because a project-level check exists
(TARBALL.md §5.3).

## Proposals

### A stop key for a cap that cannot be checked

**What.** Add a twelfth key to the `stop` axis, say `cap-unchecked`, for a pre-call check that
could not run: an unpriced model, a malformed or unreadable stream, a missing price file. Give it
an operator move, something like "fix the named fault (write the price row, repair the line),
then resume". It should not be `stop-at-cap`, whose description says the cap refused and offers
raising it, which is the wrong remedy for a missing price.

**Why.** Today `check_call` returns `stop: null` for those cases, because `share/` is out of
scope and I would not overload `cap-reached`. The Arc 2 loop must still stop with some key, and
D17 allows no default case.

**Scope hints.** `share/transitions.toml` (one axis key, one row, one move),
`twine/spend.py` (`refuse` sets the new key for the non-cap refusals),
`tests/test_transitions.py`, and contract §12.2 and §13.7. This must land before Arc 2's loop
dispatches on the check, and could ride with session 5b.

### Seed annotations for D15, Q-6 and Q-8, for a seed tidy session

**What.** Three dated annotations for `twine-seed.md`, proposed verbatim.

Beneath D15:

> [2026-10-03-twine-cost-spine-005: landed in part — the spine: `twine/spend.py` and `twine spend
> totals|check`; the usage record (`<state-dir>/spend.jsonl`, five disjoint token classes, a
> nullable `served_sid`), prices as operator data (twine ships none; an unpriced model is a
> refusal), and the hard cap's pre-call check (own + served spend plus the worst case, at most the
> cap, else `cap-reached`, never shrunk). The kill-switch is session 5b's.]

Beneath Q-6:

> [2026-10-03-twine-cost-spine-005: proposed — per-session and per-arc envelopes, both checked
> before each call, the tighter binds; an arc keyed on the office's arc id with membership the
> office's declaration, arc spend counting each record once; no `arc` key in the record; an
> absent cap refuses. Shape in the session's notes.md; the architect ratifies.]

Beneath Q-8:

> [2026-10-03-twine-cost-spine-005: twine-side landed — the stream exists and is the owner;
> bale's mirror remains bale-src's.]

**Why.** `twine-seed.md` is out of scope here, and these are the seed's to carry.

**Scope hints.** `twine-seed.md` only. The §5.1 road's row 5 could gain a "5a landed" marker in
the same pass.

### `twine status` reports where spend lives

**What.** `status` gains `state_dir`, `state_dir_source`, and whether `spend.jsonl` and
`prices.toml` are present.

**Why.** An operator wondering "is twine recording, and where" should not need to know the
resolution order. `status` is the verb for twine's own facts.

**Scope hints.** `twine/commands/core.py` and `tests/test_status.py`; read-only, a few lines,
through `spend.resolve_state_dir`. It is independent of everything else and could be folded into
any session that touches `core.py`.

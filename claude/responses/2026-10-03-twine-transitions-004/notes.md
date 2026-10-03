# notes — 2026-10-03-twine-transitions-004 (Arc 1 session 4, the transition table)

This session lands the transition table (D17) as data, `twine transitions` to render it, and the test
that fails by name. It also records bale's three vocabularies in the consumption manifest, makes
the doubles speak bale's spellings, and decides the pin question. `VERSION` is now 0.4.0, and the
suite has grown from 207 tests to 261, green on Python 3.11, 3.12 and 3.13.

Every path is inside the write forecast, so there are no departures to admit. `twine-seed.md`,
`fixtures/` and `bale.toml` are untouched, and `validation.sh` checks all three by hash. No probe was
needed: the brief's §2 gave every fact the work turned on. No bale is reached anywhere, not by the
tests and not by `validation.sh`.

## The pin decision: it gates (please ratify)

**What landed.** `carry exchange` and `carry response` now refuse, before starting bale, any bale
whose `bin/VERSION` is not the pin. They also refuse one whose version cannot be read, and any bale
at all when the pin itself is unknown. It is an ordinary refusal: `ran: false`, exit 1, the reason
in `refusals` beside any others. The code is `twine.bale.Executable.drive_refusal`, called from
`carry_bale.locate`. There is no override flag. `bale check` and `status` are unchanged: they report
a mismatch and drive nothing. The contract's §11.1 carries the rule and its reason.

**Why.** Carry-bale-002's report-only reading was ratified provisionally, "while twine reads one key".
That condition is now gone, and four things follow:

1. **The table keys on the pinned version's vocabularies.** D17's promise is that every path
   taken has a defined response. That promise only holds for a bale whose outcomes are the keys the
   table has. A 0.4.46 that adds an outcome produces a path with no move, which is the surprise D17
   rules out. The gate makes the promise true by construction: the only bale twine drives is the
   one whose vocabulary the table covers.
2. **D2 already says this.** It reads: "refuses to drive a bale whose `bin/VERSION` mismatches the
   pin … never ambient." The provisional reading was the exception to D2, and its reason has
   expired.
3. **The pin bump is now mechanical.** The vocabularies are data in the manifest (item 6) and the
   table takes its keys from them. So a pin bump goes like this: re-probe the vocabularies, update the
   manifest, and `twine transitions` goes not-ok naming each new key until someone writes it a row.
   D4's diff then carries through to the moves, and the gate is what forces that path.
4. **Gating now is cheap.** Gating after the table starts dispatching would not be. Today
   `carry response` fails closed on an unknown outcome anyway, so the gate costs an operator with a
   newer bale very little. Once session 3, or Arc 2's loop, dispatches on rows, a version drift
   would mean a lookup that finds nothing at runtime.

**The cost.** An operator who upgrades bale before twine loses the courier's two hand-offs until
the pin is bumped. I think that is the right friction, but say so if you would rather have an
explicit escape hatch. If you do, it should be a pin-bump procedure rather than a flag.

**A scope tension, flagged.** The manifest's `out_of_scope` says "what carry exchange and carry
response do; only their tests' doubles change". Brief item 8 says "Land the decision in the code
and the contract", and the only code that drives bale is those two verbs. I read item 8 as the
named exception. The change is confined to `locate`: one function, three lines. If you meant the
decision to land somewhere else, reverting it is that function, plus the
`drive_refusal`-dependent tests in `test_carry_bale.py` §7 and §8.

## The table

**Where things live.**

- **Data:** `share/transitions.toml`. TOML, so it is diffable, readable without Python, and
  parsed by `tomllib`, the same as the consumption manifest.
- **Loader and checker:** `twine/transitions.py`. It is pure and returns a `Table` with a list of
  `Problem`s.
- **Verb:** `twine/commands/transitions.py`. Its module is discovered by the registry; no shared
  list was edited.

**One home for bale's spellings (a deviation worth a look).** The brief wants the vocabularies in the
manifest (item 6) and the table keyed on them (item 1). I did not write the 31 bale keys twice.
Instead, the table's three bale axes declare `source = "bale"`, and the loader takes their keys
from the manifest's `[[vocabulary]]` entry of the same name. The `stop` axis is twine's own and
declares its `keys` in the table.

Rows are still one per key, written out by hand, each naming a move. Three consequences:

- An invented key on a bale axis is detectable as "not one of bale 0.4.45's spellings".
- A bale axis may not declare its own `keys`. That is refused as `malformed-axis`.
- The brief's agreement test (manifest lists == table bale-axis keys) holds in two layers. It holds
  structurally, and it is also asserted, with the manifest held separately to the probes' lists
  (`tests/helpers.py` `BALE_VOCABULARIES`, copied from brief §2).

The cost is that `twine transitions` reads two of twine's files, not one. Brief item 4 says the
verb's `ok` "depends on the table alone, never on whether bale is installed". I read "the table" as
twine's table data including the vocabularies it keys on. Whatever the reading, no bale install is
consulted, and a test runs the verb with a refusing seam, a refusing `which` and three different
`TWINE_BALE_ROOT`s.

**The `ok` rule, exactly as the brief words it.** `ok` is true exactly when every key of every axis
has one row and every row's move is declared. Three readings keep the "exactly":

- **"Declared".** A move counts as declared only when it is whole: exactly one actor from
  `twine`/`operator`/`planner`, and a non-empty description. A move without both is reported as
  `malformed-move` and left undeclared.
- **"One row per key".** This rules out duplicates (`duplicate-row`) and rows for keys an axis
  lacks (`unknown-key`, `unknown-axis`).
- **Things that are not faults.** Unused moves are reported in `unused_moves` but do not make the
  table not-ok. Today there are none. `written_against` (0.4.45) is not part of `ok` either: the
  tests assert it equals the pin.

Other problems the loader names:

- `missing-vocabulary`: a bale axis with nothing in the manifest.
- `missing-axis`: a vocabulary the manifest records for an axis the table lacks. This catches a
  pin bump that adds a whole vocabulary.
- `catch-all-key`: `*`, `default`, `other` and similar spellings, on any axis. This is the brief's
  "no catch-all key" made literal.
- `unusable`: the table file cannot be read or parsed.

**`--table PATH`** is the verb's only input. It checks a draft or an edited copy against the same
vocabularies, and the CLI's not-ok path is tested through it.

### The stop set: the brief's ten, plus two (flagged)

I added **`cap-reached`** and **`killed`**, both from D15. D15 describes the cost spine's hard cap,
"checked *before* each call", and the kill-switch, which "leaves a durable `aborted`-class closure
record". Both are ways a worker turn stops that none of the ten names, and session 5 is the one
that builds them. Without these keys, session 5 would have to extend a vocabulary that later
sessions key on.

`killed` maps to `close-aborted` (actor twine), and `closure-reason` `aborted` has its own row. The
kill therefore becomes a durable record, and that record has a defined next move.

I deliberately did not add any provider-specific name (`stop_sequence`, `pause_turn` and the like).
D17's annotation says none is named from memory.

### The moves: the assignments I'd most like read

There are 25 moves: 10 twine, 5 operator, 10 planner. `twine transitions` prints them all, each
with its `grounds`. The two pinned moves are where the brief put them: `revert-and-repack` for
`held` on both axes, and `respawn-from-request` for `malformed_response` and `malformed-shape`.
These are the calls that were mine:

- **`dry-run` → `operator-applies` (operator).** T12 made visible: twine has handed back the line,
  and the merge is the operator's. A test asserts that no twine-actor move's name or description
  says merge, apply or admit.
- **`unlocked` → `close-by-reason` (twine).** Bale reports `unlocked` for every registry close, and
  the reason is what carries the meaning. So the telemetry row defers to the closure-reason row
  rather than guessing. This seemed better than giving `unlocked` a move of its own that would be
  wrong for half its causes.
- **`rejected` → `diagnose-rejection` (operator).** This is apply's error path. Some rejections
  are a malformed response, which closes `malformed_response` and respawns. Others are
  environmental: a lock, no open session. Telling them apart means reading the session log, so the
  move belongs to the operator.
- **`crash-debris` and `no_response` → `respawn-from-request`.** For both, the work never arrived.
  `crash-debris`'s schema description was cut by the probe, so I am reading it as "the session was
  left behind by a crash", and under either plausible reading respawn is right.
  PLANNER.md §16 lists silence separately and gives no move for it, so respawn there is my reading.
  The move's description carries §16's bound: past the retry bound, re-decompose.
- **`abandoned`, `master-closeout`, `aborted` → `release-to-planner` (planner).** A deliberate
  close. Whether the goal comes back is the planner's call.
- **`required-check-refused` → `return-to-worker` (planner).** The common fix is that the worker
  re-ships with the check declared. The planner owns it because sometimes the required-check pin is
  what is wrong.
- **`window-exhausted` → `split-goal` (planner).** This follows AGENT.md §11.2 and §11.5: respawning
  the same goal into the same window fails the same way. I chose this over `package-handoff`
  because an exhausted window leaves no `handoff.md`.
- **`max-tokens` → `continue-turn` (twine)**, bounded, falling to `malformed-shape` past the bound.
  **`rate-limited`, `overloaded`, `network-failure`, `timeout` → `retry-with-backoff` (twine)**,
  bounded, then the stop is named to the operator. These are mechanical, so they are twine's (N4
  holds). A test asserts that no twine move's description says it decides, triages, chooses or
  rewords.
- **`model-refusal` → `reword-brief` (planner).** This is the 45-arc specimen: twine never
  rephrases a request.

## The doubles (item 7)

The two invented spellings are gone. `test_carry_bale.py` now uses:

- **Refusals.** Each of the three `*-refused` outcomes, with exit 1 and the line on stdout, as
  `format_apply_json` documents under `--dry-run`. These are subtests, and each asserts that the
  reason names both the exit and the outcome.
- **A bale error.** Nothing on stdout, exit 2, stderr surfaced. The end-to-end `StubBale` failure
  now prints nothing too.
- **An unknown outcome.** `NOT_A_BALE_OUTCOME = "twine-test-not-a-bale-outcome"` in
  `tests/helpers.py`, with a test asserting it is in none of bale's lists.

Two doubles break a contract bale documents, and I kept them with that labelled in their
docstrings:

- `test_a_non_zero_exit_with_the_dry_run_outcome_is_not_ok`: a `dry-run` line with exit 3.
- `test_human_mode_not_ok_is_one_line_and_never_bales_stdout`: relay printing a block beside exit 1.

Neither invents a spelling. Both prove twine does not trust stdout without exit 0, which is worth
keeping even though bale says it never happens.

`DetectorsFire` in `test_transitions.py` deliberately uses `refused` and `hold` as invented table
keys. That is the detector they exist to trip, and the docstring says so.

`ASSUMED_DRY_RUN_EXIT` stays an assumption. Its comment now cites bale's documented "(exit 0)" and
says that a documented exit is not a recorded one. No `fixtures/README.md` row changes.

## What I noticed

- **A trap in TOML `[[row]]` blocks.** Removing a row by matching three of its four lines leaves the
  fourth (`means`) attached to the row above it, which `tomllib` then refuses as a duplicate key. My
  first `validation.sh` run caught this in my own detector check, not in the table. The check now
  cuts the whole block.
- **`apply-outcome` `read_by`.** I listed only `transitions` for the vocabulary. `carry response`
  reads the surface's `outcome` key and compares it to one value, `dry-run`; it does not read the
  vocabulary. The apply surface names the vocabulary through its new `vocabulary` key instead.

## Places to look closely

- `share/transitions.toml`: the moves' descriptions and actors. This is the review the brief said
  was "read at review".
- `twine/bale.py`, `Executable.drive_refusal`: the three refusal texts and their order.
- `twine/transitions.py`, `load_axes`: the bale/twine source split, which is the single-home design
  above.

## Validation

`validation.sh` ran twice, as TARBALL.md §7.2 asks.

**On a staged tree** (the base with `files/` overlaid, `apply.sh` run, and the manifest at
`.bale-manifest.json`): exit 0, all 16 checks `[PASS]`, and the claim reconciled `[agree]`. It takes
about 15 s, most of it the suite. Afterwards the staged tree matched my working tree byte for byte,
apart from `.validation-logs/`.

**On the unmodified base:** exit 1. Every session-specific assertion `[FAIL]`s, along with the two
syntax checks, because the new files are absent. The four invariants pass on both trees, as they
should:

- the suite (the old suite is green on the old tree);
- the pin and the schema-hash block;
- "twine-seed.md, fixtures/ and bale.toml untouched";
- no bytecode.

The `claims` block holds one claim, the suite: `pass`, observed. The session assertions are listed
in `validation_will_run` and not claimed, because a project-level check exists (TARBALL.md §5.3).

## Proposals

### D17's landing annotation and the pin decision's record, for a seed tidy session

**What.** Two dated annotations for `twine-seed.md`, proposed verbatim.

Beneath D17:

> [2026-10-03-twine-transitions-004: landed — `share/transitions.toml`, rendered by `twine
> transitions`: bale 0.4.45's 13 telemetry outcomes, 9 closure reasons and the 9 outcomes `bale apply
> --json` prints (a third vocabulary the seed did not name, read by probe at sitting
> 2026-10-03-continue-twine-003), keyed on the consumption manifest's `[[vocabulary]]` data, plus
> twine's stop set — the sitting's ten and `cap-reached` and `killed` from D15 — 43 rows over 25
> declared moves, each with one actor (twine, operator or planner), no default case. The ratified
> edges hold: `held` gets `revert-and-repack`, `malformed_response` and `malformed-shape` get
> `respawn-from-request`. `tests/test_transitions.py` fails by name on any key without a move.]

Beneath D2:

> [2026-10-03-twine-transitions-004: carried, and now enforced on the courier — `carry exchange`
> and `carry response` refuse a bale whose `bin/VERSION` is not the pin, or cannot be read, before
> starting it; carry-bale-002's provisional report-only reading ended when the transition table
> keyed on the pinned version's whole vocabulary.]

**Why.** The brief puts both in a seed tidy session (§4).

**Scope hints.** `twine-seed.md` only. The §5.1 road row 4 could gain a "landed" marker in the same
pass.

### Twine's own refusals as an axis

**What.** A fifth axis, `courier`, for the ways twine's own verbs stop before or around bale. This
covers integrity faults, the pin gate, an unreadable input, and a timeout or cap on a bale call,
each with a move.

**Why.** D17 says "every path taken should have a defined response". The table now covers bale's
outcomes and the runtime's stops, but not the courier's own refusals. Today a human reads the
reason string; a scheduler (Arc 3) will need a key. The pin gate this session added is a new such
path.

**Scope hints.** `share/transitions.toml`, `twine/commands/carry*.py` (each refusal tagged with its
key), contract §10 to §12. This is best done before Arc 3, and it needs no bale fact.

### Let `carry response` name the move for the outcome it saw

**What.** Add a non-gating `move` (and `actor`) to `carry response`'s JSON twin, looked up from the
`apply-outcome` row for `outcome`.

**Why.** It is the first consumer of the table, and it makes a refusal's next step machine-readable
for the shell. I left it out because what `carry response` does is out of scope this session.

**Scope hints.** `twine/commands/carry_bale.py`, contract §11.3. It depends on nothing else.

### The recording probe is still owed

**What.** Carry-bale-002's first Proposal stands: record a refusal's JSON and exit code from `bale
apply --dry-run --json`, the clean dry run's exit, and `bale relay <sid>` re-emission.

**Why.** The doubles now speak bale's documented spellings, but they are still doubles. Brief §2.5
explains why this probe could not run: a dry run writes the session log, and twine-src has no
thread.

**Scope hints.** As before: `fixtures/`, `fixtures/README.md`, the manifest's apply and relay
surfaces, and the doubles. A refusal is easiest to record in a scratch repository with a deliberate
scope drift.

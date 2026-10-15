# notes — 2026-10-15-twine-gate-contract-001

The gate is the floor plus bale's contract now. `twine bale check` runs
`<root>/bin/bale contract --json` through `ctx.run` and holds the line to
what the manifest says twine reads. The schema hashes are gone, and the
gate reads nothing under `schemas/`. The attachment was the line the probe
read (8549 bytes, `bab19c6d…0334`), so it landed byte-exact as
`fixtures/contract/bale-0.4.55.json`. The suite runs 1154 tests (it was
1113), all green under `python3 -I -B -m unittest discover -s tests -t .`.

## Seed annotations owed (verbatim from the brief, for the next tidy)

Under D2 (after its last bracket), and under §5.2 after R5's bracket:

> [<sid>: the gate is the floor plus bale's contract — `bale contract
> --json` checked against what twine reads (the table's three vocabularies,
> the keys of each line twine reads, the outcomes and the one reason it
> dispatches on); the schema hashes are gone. Ruled by the architect on
> 2026-10-15 at sitting 2026-10-13-open-hardening-011: "i thought we got rid
> of the pin sessions by pinning a contract?" Floor 0.4.54, recordings
> 0.4.51, contract line `fixtures/contract/bale-0.4.55.json`. `VERSION`
> 0.23.0.]

`<sid>` is `2026-10-15-twine-gate-contract-001`.

## The decisions the brief left to me

- **Where the check lives.** Section 4 of `twine/bale.py` is rewritten as
  "The gate: the floor and bale's contract". It has `ContractVerdict`,
  `check_contract` (the run and its failures), `contract_findings` (a pure
  function from the manifest, the parsed line and `bin/VERSION` to
  problems, moved facts and notes), `contract_not_asked`, and `check`. The
  timeout is 30 s and the stdout cap is 1 MiB. bale prints about 8.5 KB
  from in-memory tables, so either limit means something is wrong.
  `contract_argv` sits in section 5 beside the other argv builders.
- **`[bale.schemas]` left in a manifest is refused**, by name, the same way
  `pin` is. Any `[bale]` key other than the three is refused too, since
  the brief says "these three keys exactly".
- **`schemas_match` became `contract_ok`.** It is null when the gate never
  asked: no root, no manifest, or an install below the floor. Every twin
  that carried the old key (the carry verbs and `kill`) now carries the
  new one, and cli-contract §11.1 says so.
- **helpers.** `FLOOR = "0.4.54"`, and the new `RECORDINGS = "0.4.51"`
  drives every fixture path. `TempRoots.ok` is 0.4.55, so the carried line
  replays byte-exact. `at_floor` is 0.4.54, `above` is 0.4.56, `far_above`
  is 0.4.100, `below` is 0.4.53, and `other` stays 0.4.46. `bad_schema` and
  `no_schemas` are now admitted. Four new roots are refused on the contract
  alone: `lacks_key`, `adds_outcome`, `lacks_hold_branch` and `disagrees`.
  Every line other than the carried one is built by `contract_line` or
  `edited_contract` and named as a double.

## Other calls worth a look on review

- **Below the floor, the contract is not run.** No bale below 0.4.54 has
  the verb, so the reason says `bale contract --json was not run (no bale
  below the floor 0.4.54 has it)`. When `bin/VERSION` is unreadable or
  unparsable the contract still runs, so every failing fact gets named.
- **What "added" is measured against.** The brief says added values in
  `open-outcome`, `relay-outcome` and `unlock-outcome` are reported, not
  refused. That needs a recorded baseline, so the open, relay and unlock
  surfaces gained `outcome_vocabulary` plus `outcomes`, copied from the
  0.4.55 line. Every reading verb surface also gained `contract_lines`,
  which names the `json_keys` lines its reader reads; the manifest refuses
  a reading surface without it. A recorded value that twine does not
  dispatch on and that the contract drops (say `no-op`) is also a note.
- **The dispatch table.** `twine.bale.DISPATCHED_OUTCOMES` holds the nine
  outcomes the readers branch on. `DISPATCHED_REASONS` holds `hold-branch`,
  keyed by its reader `kill` rather than by the bale verb. Keying it on
  `"unlock"` broke `test_unlock_is_built_in_one_place_only`, and keying by
  reader matches how `surface_keys` already works. The readers keep their
  own constants, and `tests/test_bale_check.py` `WhatTwineDispatchesOn`
  holds each one equal to the table. I didn't move the constants, because
  `twine/inflight.py` (which owns `OPENED`/`SECOND_DESK`) is outside the
  forecast.
- **A `[[surface]]` for `contract --json` itself.** D3 says the manifest
  lists every bale surface twine reads, and this is now one. It uses
  `carried` where other surfaces use `fixture`, because the line lives
  outside `fixtures/bale-<V>/`. `read_by` is `bale check` and `status`
  only, since every other reader is unique on its own surface.
  `test_consumption_manifest.py` accepts the `carried` form.
- **Run-seam doubles and the gate's extra call.** The gate now runs bale
  through the same seam the verbs use. Every double (`RecordingRunner`,
  `FixturePlayer`, `RecordedUnlock`, `RecordedRelay`, and through them
  `BaleDouble`/`OpenDouble`) answers `contract --json` by running the
  root's own `bin/bale` double for real (`answer_contract`). It records
  that call in `gate_calls`, not `calls`, so every existing "bale was
  never started" assertion keeps its meaning. `StubBale`'s script answers
  the call before it records anything.
- **The refusal text.** `drive_refusal` composes two parts. When the
  contract read cleanly and something twine reads moved, it says "bale
  changed something twine reads (named above) … a recording session lands
  the new spelling". When anything else failed, it says "twine drives only
  a bale at or above the floor … whose contract … states everything twine
  reads". It never says "raise the floor", and the tests assert that.
- **One carry-bundle test was re-aimed.** In
  `test_a_bale_that_cannot_be_started_is_a_refusal_after_the_argv`, a root
  with no `bin/bale` is now refused by the gate itself, because the gate
  starts it. To keep testing the "RunError after the argv" path, the test
  uses a runner that answers the gate and then fails to start the open.
- **The transition table's header is stale now** but untouched, per the
  constraint. It says `written_against` is "the manifest's floor", and
  0.4.51 is now the manifest's `recordings`. `test_transitions.py` holds
  `(written_against, floor) == (RECORDINGS, FLOOR)`. See Proposals.
- **validation.sh runs the suite ungated**, about 160 s, which is past
  TARBALL.md §7.6's two-minute target. The brief names the suite as the
  session's validation, so I left it ungated, and `validation_will_run`
  says "~160 s". The four session-specific checks (the carried bytes, the
  `[bale]` table and VERSION, admit, refuse) fail on the unmodified tree
  and pass with the change. The preservation checks (protected bytes, the
  lander's `--check`, `transitions`) and the suite pass on both, as they
  should.
- **Small observation:** `bale check` against a root with no `bin/bale`
  now prints `[twine ERROR] twine.process: run: cannot start …` on stderr.
  That line is `process.py`'s own log when a start fails. The JSON is
  still one line, and the reason names it.

## Outside the write forecast

- `twine/__init__.py`: one docstring line. The package's module map said
  the gate was "the floor and the schema hashes", and brief item 7 asks
  every mention of the schema hashes to go. It's documentation only, no
  code. It is also in `feedback.self_reported.forecast_departures`.

## Proposals

- **What:** Teach the recorder to record `bale contract --json` and the
  lander to land it as `fixtures/contract/bale-<V>.json` with its README
  row.
  **Why:** a recording session now needs the contract line beside the
  paste-back (cli-contract §16 step 1 says so), and today a person carries
  it by hand. The lander also has a stale comment at
  `bin/twine-land-recordings:480` about "the schemas the gate hashes".
  **Scope hints:** `bin/twine-record-fixtures`, `bin/twine-land-recordings`,
  `tests/test_recordings.py`. Both tools were out of scope here.
- **What:** Restate `share/transitions.toml`'s header: `written_against` is
  the version the bale axes were re-read at (the manifest's `recordings`),
  and the gate's contract check keeps the axes true above the floor.
  **Why:** the header still calls 0.4.51 "the manifest's floor", and since
  this session it isn't. The constraint kept the file untouched.
  **Scope hints:** the header comment only. No row moves.
- **What:** Carry the contract's notes, not just `contract_ok`, into the
  carry verbs' and `kill`'s `bale` object, or print them on stderr.
  **Why:** a value bale adds is reported only by `twine bale check` and
  `twine status` today. An operator who only ever runs `carry bundle` or
  `run` never sees it until it matters.
  **Scope hints:** `Executable.as_json` and cli-contract §11.1. It changes
  a twin's keys, so it is a contract change.

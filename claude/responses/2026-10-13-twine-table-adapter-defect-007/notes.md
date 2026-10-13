# Notes — 2026-10-13-twine-table-adapter-defect-007

Desk 2 of the session (the chat was joined, not opened); nothing about the
work differs for that.

The brief held up against the tree. Every `base_files` hash in the request
agrees with the bytes I was given, so there was nothing to flag about the
one dirty working-tree change the registry line mentions: whatever it is, it
is not in a file this session touched.

## What changed

- **`share/transitions.toml`**: `adapter-defect` is in the stop axis's `keys`
  and `loop_keys`; one `[[row]]` for `(stop, adapter-defect)` with move
  `fix-adapter`; `[move.fix-adapter]` transported verbatim from the brief
  (actor `operator`); `[move.continue-turn]`'s description replaced with the
  brief's sentence; the header comment's `loop_keys` sentence now names the
  four keys and what each one is, plus a line for this session. `written_against`
  stays `0.4.51`. `twine transitions` is ok: 47 rows over 28 moves.
- **`twine/runtime/loop.py`**: a boundary refusal and an adapter that raises
  both end the run through one new method, `Loop.adapter_defect`: outcome
  `stopped`, stop `adapter-defect`, move `fix-adapter`, actor `operator`, and
  a `move` line in the transcript after the `adapter-error` line (the other
  stops each get one; this path did not). The spend stream is untouched, as
  before. `Loop.continue_turn` did not change.
- **`twine/runtime/boundary.py`**: the module docstring's paragraph on a
  refusal says what is now true.
- **`twine/transitions.py`**: `STOP_ADAPTER_DEFECT` (see below).
- **Docs**: `runtime-contract.md` §1.5 (the loop-key bullet), §1.6 (rewritten),
  §7.4 (step 4, the moves-table row for the four loop keys, the
  `continue-turn` paragraph replaced by the reconciled fact), §7.7's
  `stopped` row, and the "table stays as R2 left it" clause of step 2 (no
  longer true once the table moved); `cli-contract.md` §12 (the stop row:
  sixteen keys, four loop keys; the loop-keys paragraph; the moves paragraph
  and the row/move counts, 47 and 28), §18.2 (the refusal list now includes a
  table that does not declare a loop-reported key), §18.4, §18.5 (`stop` is
  not null on an adapter defect), and the tests paragraph. `claude/INDEX.md`
  is untouched: its `transitions.toml` line does not count `loop_keys`.
- **`VERSION`** → `0.20.0`.

## The spelling's home: `twine.transitions.STOP_ADAPTER_DEFECT`

Not `twine/runtime/` (a test holds that no module there spells a stop key),
and not `spend.py` or `kill.py`, which are the cost spine's and the
kill-switch's, not the loop's. `twine/transitions.py` already holds
`STOP_AXIS`, the loop imports from it, and it is the module that loads the
table the key lives in. `loop.ADAPTER_DEFECT` is the loop's name for it. The
boundary spells nothing: it learns the key through `loop_keys`, as before
(`boundary.py` has no code change at all, only its docstring).

One addition the brief did not ask for: `MoveBook.faults()` now also refuses a
table that does not declare each key the loop reports itself
(`cap-reached`, `cap-unchecked`, `killed`, `adapter-defect`) among the stop
axis's `loop_keys`, or whose row has no declared move. `twine run` already
refused, before opening anything, on a table lacking a move the loop performs;
this is the same discipline for the keys, and without it the loop's
`adapter_defect` would quietly report `move: null` on an old table. One test
holds it (`TheMoveBook.test_a_table_without_the_adapter_defect_key_or_row_is_a_fault`,
four sub-cases). Cheap to drop if you would rather the table check stay as it was.

## The order in `keys`

Appended last: `…, "killed", "cap-unchecked", "adapter-defect"`. R2's reason
for ordering — the provider's keys together, the loop's last — still holds, and
`loop_keys` follows the same order. The rows render in `keys` order, so the new
row is the last of the stop axis.

## Test pins that moved, by name

- `tests/test_spend.py` `PreCallCheck.test_every_other_refusal_stops_cap_unchecked_with_an_operator_move`:
  `keys[-2:]` → `keys[-3:] == ["killed", "cap-unchecked", "adapter-defect"]`.
- `tests/test_transitions.py`: `LOOP_KEYS` (four), `STOPS` (gains the new key),
  `ADDED_STOPS` untouched; the rows count `13 + 9 + 9 + 15` → `… + 16` and
  `counts["rows"]` 46 → 47 (`TheVerb.test_json_twin_as_a_subprocess`); two tests
  renamed for what they now say
  (`…_ten_plus_r2_s_two_plus_the_loops_four`, `test_loop_keys_are_the_loops_four_read_from_the_table`).
- `tests/test_runtime.py`: `FakeThroughTheBoundary.test_every_stop_on_the_axis_passes_but_the_loops`
  asserts the four-key set — and, because it walks every loop key, now also holds
  that the boundary refuses a turn stopped `adapter-defect`, naming it;
  `TheStopSet.test_stop_keys_refuses_a_table_without_a_usable_stop_axis`'s
  `catch-all` case edited its replacement anchor (the last key of the `keys`
  line is no longer `"cap-unchecked"`).
- `tests/test_run.py`: `test_an_adapter_defect_is_stopped_with_no_move` →
  `test_an_adapter_defect_is_stopped_adapter_defect_with_fix_adapter` (asserts
  stop, move, actor, turns, no spend record); `test_a_script_that_runs_out_is_stopped`
  → `…_stopped_adapter_defect`; `test_a_thinking_turn_on_a_thinking_off_session_is_a_defect`
  asserts the key, move and actor.

Added: `TheStops.test_an_adapter_defect_leaves_an_adapter_error_line_then_a_move_line`
(the transcript's order and the twin's stop), `TheLoop.test_an_adapter_that_raises_anything_is_an_adapter_defect`
(a bare `RuntimeError` out of `call`), the `MoveBook` test above,
`test_adapter_defect_is_a_loop_key_with_the_operators_fix_adapter`,
`test_continue_turn_says_what_the_loop_does` and
`test_no_provider_word_may_map_onto_adapter_defect` in `test_transitions.py`.
The suite is **1033 tests** (1027 + 6), green, skipped=5 as before.

## Validation, observed

`validation.sh` ran on the landed tree (a copy of the mirror laid over the
base) and on the unmodified base:

- landed: every check passed, the suite at 1033 tests;
- base: `transition table facts`, `twine transitions --json is ok`, `the loop
  reads adapter-defect …`, `VERSION is 0.20.0` and `docs reconciled` all
  **fail**, as the brief required of every change assertion. Three checks pass
  on the base by nature, not because they fail to test the change: the suite
  (1027 ≥ 1027), `no stop key spelled under twine/runtime/` and `untouched: …`
  are guards that must hold both before and after.

`twine-seed.md` is not in the files I was given, so the untouched check holds
it only as "not among the manifest's `changes[]`" (in staging; skipped with a
line elsewhere). `bin/twine` and `share/bale-consumption.toml` are held by
sha256 of the base's bytes, and `fixtures/` by the same manifest rule.

## Anything the brief got wrong

Nothing material. Two small things: the brief's §1.6 quote is the base text,
and §1.6 is also where the "R1 said … will be a row" sentence sits, so I kept
the history in one clause rather than deleting it; and `cli-contract.md`'s
"46 rows over 27 moves" sentence, which the brief did not list, needed the new
counts (47 and 28), so I changed it with the rest of §12.

## Proposals

1. **The project `README.md`** (not in this session's forecast, so untouched)
   still says, in the transitions bullet, "Since Arc 2 R2 (0.17.0) the stop set
   has fifteen keys … names its three `loop_keys`". True as dated, but a reader
   will take it as current; a clause there ("sixteen and four since 0.20.0") is
   worth a sentence in whichever session next edits the README.
2. **`fix-adapter` and a second desk.** The move's text says the operator runs
   the session again "on the same bundle (a second desk)". Until R5's resume
   exists, a rerun starts the conversation over from the opener with the
   transcript appended to; that is the honest meaning of "again", and R5 may
   want the description to say "resumes" once it can.

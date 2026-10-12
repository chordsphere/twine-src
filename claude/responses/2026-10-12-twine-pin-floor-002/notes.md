# notes — 2026-10-12-twine-pin-floor-002

D2 is a floor. twine now drives any bale at or above `0.4.51` whose
installed schemas hash as the manifest pins them. The four line readers
check the manifest's keys on the line they read, and the eight schemas
are fixtures. The suite runs 639 tests (597 before). `validation.sh`
passes on the staged tree and fails its session checks on the unmodified
one. Nothing was re-recorded, and every pre-existing file under
`fixtures/` is byte-identical.

## 1. Decisions to ratify

The four the brief left to me (§5):

1. **`bale check`'s `schemas` object and its human line.** The object
   is `{dir, present, ok, checked, mismatched, missing}`:
   - `checked` lists every pinned file that was found and hashed,
     matching or not.
   - `mismatched` and `missing` are names, each list sorted.
   - `present` says whether `schemas/` is a directory at all. With no
     `schemas/`, every file is `missing` and the reason says so once
     ("no schemas/ directory at …") rather than listing eight files.
   - `schemas` is null only when no install was found.

   The human line is either `schemas:   all 8 hash as the manifest
   pins them` or `schemas:   NOT OK — <the schema facts>`. The floor's
   line reads `floor:     0.4.51 (twine drives this bale or any above
   it)`. The reasons come in a fixed order: version facts first, then
   schema facts. Each failing fact is its own `; `-joined sentence.
   Pinned in contract §5.
2. **The key-check helper.** It is `twine.bale.missing_keys_failure(manifest,
   reader, line)` in a new §6 of `twine/bale.py`, with
   `surface_keys(manifest, reader)` beside it.
   - **Keyed on the reader, not the bale verb.** The helper takes the
     twine verb's registered name (`carry exchange`, `carry response`,
     `carry bundle`, `kill`), which the manifest already records in
     `read_by`. I tried keying on the bale verb first, but that put
     `"apply"`, `"open"` and `"unlock"` literals into the readers. The
     three existing "built in one place only" guards count exactly
     those literals and failed, and I'd rather not loosen them. So
     each reader module now holds its registered name as a constant
     (`READER_EXCHANGE`, `READER_RESPONSE`, `carry_bundle.READER`,
     `kill.READER`), and the `Command(name=…)` uses the same constant.
     That gives one spelling.
   - **Wording:** "bale's relay line lacks the key 'cause', which the
     consumption manifest lists for the relay surface (bale relay
     <sid> - --json); existing keys are never removed, so this bale is
     not the contract twine reads". Several missing keys are named
     together.
   - **Presence only.** A null value counts as present, and an extra
     key is free.
   - **An unusable manifest makes the line not ok, named.** That
     can't be reached in practice, because the gate already refuses
     to start bale when the floor is unknown. The helper still never
     silently passes.
3. **Tuples for the gate, the string in the twin.**
   - `parse_version` accepts exactly three dotted integers: no
     leading zero, no suffix, no whitespace.
   - The comparison is a tuple, and a test proves `0.4.100` is above
     `0.4.51`.
   - The twin reports `installed` as the string bale wrote.
   - `Executable` gained `verdict`: `bale check`'s own `CheckResult`,
     computed in `locate_executable`. So `drive_refusal` and `bale
     check` cannot disagree, and `drive_refusal` just reads the
     verdict.
   - The twin's `bale` object is `executable, root, source, installed,
     floor, floor_admits, schemas_match`. `floor_admits` is the
     version half only. I added `schemas_match` for the other half,
     because "admits" on its own would hide which half refused.
     **Please confirm** that's the reading you wanted: you might have
     meant `floor_admits` to be the whole gate's verdict.
4. **`TempRoots.other` stays**, still 0.4.46 and still below the
   floor, now with schemas, so the version alone refuses it. The new
   roots sit beside it: `above` (0.4.52), `far_above` (0.4.100),
   `below` (0.4.49), `bad_schema`, `no_schemas`, `unparsable`.

Other calls I made:

5. **`twine transitions --json` reports `floor`, not `pin`.** `Manifest.pin`
   no longer exists (the manifest carries no `pin`), so
   `twine/transitions.py` had to change regardless. I renamed its
   JSON key and human line rather than keep a `pin` key that holds
   the floor. The contract (§12.3, §12.4) says so. This file is a
   forecast departure (§2).
6. **`load_manifest` refuses more than it used to:**
   - a `[bale]` that still carries `pin`, named as the retired key;
   - a `floor` that isn't three dotted integers;
   - an **empty** `[bale.schemas]`: a gate that hashes nothing admits
     anything;
   - a schema name that isn't a plain file name, so the gate never
     hashes outside `schemas/`.
7. **`carry bundle` after an open whose line lacks a key.** The verb
   is not ok, so nothing is recorded. The reason adds "the session may
   be open: `bale status` in <cwd> says which", the same as the other
   accepted-open-but-not-ok paths (the surrogate case). Under
   `--check` it doesn't add that.
8. **"§2 item 2" in brief §4.** I couldn't place it literally. §2's
   second bullet is about module discovery. I put "the gate is a
   floor" on §2's verbs bullet, where `bale check` is named. Move it
   if you meant something else.

## 2. Paths outside the forecast

Both are required by the goal:

- **`bin/twine-land-recordings`** — `--check` refused any file under
  `fixtures/bale-<V>/` that the paste doesn't derive. The brief pins
  the schemas at `fixtures/bale-0.4.51/schemas/`, so without this
  change the lander's own check fails on the landed tree (that is the
  pin-051 checkpoint's call, and its tests broke).
  - The fix makes `--check` skip that one subdirectory and leaves
    everything else alone.
  - The subdirectory is named once in `tests/fixture_rule.py`
    (`SCHEMAS_WHERE`, `schemas_relpath_at`), the shared rule.
  - The file keeps its exec bit: `apply.sh` restores it and
    `validation.sh` asserts it.
- **`twine/transitions.py`** — it read `manifest.pin`, which is gone.
  See §1 item 5.

## 3. Tests that moved

639 tests now, 597 before. Renamed and rewritten (old name → new name):

- `test_bale_check.py`
  - `PinCheck.test_three_roots` → `TheGate.test_at_the_floor_above_and_far_above_are_admitted`,
    `test_below_the_floor_is_refused_naming_the_floor`,
    `test_an_unparsable_or_unreadable_version_is_refused`,
    `test_no_schemas_directory_is_refused`,
    `test_a_missing_file_is_refused_by_name`,
    `test_a_mismatched_file_is_refused_by_name`
  - `PinCheck.test_json_shape` / `test_no_install` → `TheGate.test_json_shape` / `test_no_install`
  - `CheckViaCli.test_subprocess_three_roots` → `test_subprocess_the_matrix`
  - `test_human_rendering_carries_the_same_facts` → `test_human_rendering_names_the_floor_and_the_schema_verdict`
- `test_carry_bale.py`
  - `EndToEnd.test_a_version_other_than_the_pin_is_refused_and_never_run` → `test_below_the_floor_is_refused_and_never_run`
  - `FindingBale.test_a_pinned_root_with_no_bin_bale_could_not_be_started` → `test_an_admitted_root_with_no_bin_bale_could_not_be_started`
  - `ThePinGates` → `TheGate`:
    - `test_another_version_is_refused_before_bale_starts` → `test_below_the_floor_is_refused_before_bale_starts`
    - `test_the_pinned_version_is_driven` → `test_at_and_above_the_floor_are_driven`
    - `test_an_unreadable_version_is_refused_before_bale_starts` → `test_an_unreadable_or_unparsable_version_is_refused_before_bale_starts`
    - `test_a_refused_version_is_one_reason_among_the_others` → `test_a_refused_bale_is_one_reason_among_the_others`
    - `test_the_gate_reads_the_pin_from_the_manifest_never_a_literal` → `test_the_gate_reads_the_floor_from_the_manifest_never_a_literal`
- `test_carry_bundle.py`
  - `EndToEnd.test_a_version_other_than_the_pin_is_refused_and_never_run` → `test_below_the_floor_is_refused_and_never_run`
  - `RefusedBeforeBale.test_no_bale_found_or_not_the_pin_is_refused` → `test_no_bale_found_or_one_the_gate_refuses_is_refused`
- `test_kill.py`
  - `AbortedClosure.test_an_unpinned_bale_is_never_started` → `test_a_bale_the_gate_refuses_is_never_started`
  - `KillVerb.test_the_pin_gates_the_closure_alone` → `test_the_gate_gates_the_closure_alone`
  - `test_an_unpinned_bale_renders_not_finished_at_the_closure` → `test_a_refused_bale_renders_not_finished_at_the_closure`
  - `test_a_pinned_bale_closes_as_before` → `test_an_admitted_bale_closes_as_before`
- `test_consumption_manifest.py`
  - `test_the_schema_hashes_are_unchanged_at_the_pin` → `…_at_the_floor`
  - `ManifestRefusals.test_missing_pin` → `test_missing_floor`
- `test_transitions.py`
  - `test_the_table_is_written_against_a_version_the_pin_keeps` → `…_the_floor_keeps`

New tests:

- `test_bale_check.py`
  - `VersionParsing` (2 tests)
  - `TheGate.test_the_manifest_carries_a_floor_and_no_pin`
  - `test_an_extra_schema_file_is_free`
  - `test_every_failing_fact_is_named_at_once`
  - `test_a_manifest_that_still_says_pin_or_no_floor_is_refused`
- `test_carry_bale.py`
  - `EndToEnd.test_above_the_floor_is_driven`
  - `test_a_schema_that_does_not_hash_as_pinned_is_refused_and_never_run`
  - `test_the_key_check_end_to_end`
  - `TheGate.test_schemas_that_do_not_hash_as_pinned_are_refused_before_bale_starts`
  - `TheKeysOnTheLine` (6 tests: relay and apply lines each lacking a listed key, several keys missing at once, a null key is present, an extra key is free, a missing key named beside the outcome failure)
- `test_carry_bundle.py`
  - `EndToEnd.test_above_the_floor_is_driven`
  - `test_a_schema_that_does_not_hash_as_pinned_is_refused_and_never_run`
  - `TheKeysOnTheLine` (3 tests)
- `test_kill.py`
  - `AbortedClosure.test_a_bale_above_the_floor_closes`
  - `test_an_unlock_line_lacking_a_listed_key_is_not_ok_naming_it`
  - `test_a_missing_key_is_named_beside_the_refusal`
  - `test_an_extra_key_on_the_unlock_line_is_free`
  - `KillVerb.test_the_unlock_key_check_through_the_verb`
- `test_consumption_manifest.py`
  - `test_the_schema_fixtures_hash_as_the_manifest_says`
  - `test_schemas_must_be_plain_names_and_not_empty`
  - `TheKeysOnTheLine.test_each_reader_has_one_surface_with_keys`
  - `test_every_recording_of_a_read_surface_carries_every_listed_key`: the test that makes the key check safe; every recorded outcome of the four surfaces carries every listed key.
- `test_fixtures.py`: `SchemaFixtures` (4 tests)
- `test_status.py`
  - `test_a_bale_above_the_floor_is_ok_inside`
  - `test_a_bad_schema_rides_inside_and_status_stays_ok`
  - `InflightRecords.test_the_temp_name_is_kills_exported_test_never_a_copy`

Edited in place:

- `test_status.py`: `test_payload_keys_and_values`, `test_unusable_manifest_makes_status_not_ok`, `test_human_rendering` (`floor`)
- `test_carry_bale.py`: `FindingBale.test_a_bale_on_path_is_never_run_by_the_cli_tests`, `test_bale_root_flag_wins_over_the_environment`, `EndToEnd.test_carry_exchange_through_the_real_seam`
- `test_carry_bundle.py`: `test_every_reason_is_named_at_once`
- `test_kill.py`: `test_ok_is_exit_0_with_the_fixed_keys`
- `test_transitions.py`: `test_a_pin_bump_adding_a_spelling_is_named_until_it_has_a_row`, `test_a_vocabulary_without_an_axis_and_an_axis_without_a_vocabulary`, `test_json_twin_as_a_subprocess`
- `test_consumption_manifest.py`: `test_tomllib_parses_it`, `test_load_manifest`, `test_malformed_vocabularies_refuse_naming_why`
- `test_fixtures.py`: `recorded_files()` now excludes `schemas/`
- `test_recordings.py`: `LanderLands.test_landing_into_an_empty_tree_writes_the_trees_bytes_and_prints_its_rows` (schemas aside)
- `test_process.py` and the rest: `PIN` → `FLOOR` only.
- `test_json_discipline.py` didn't change: its stub roots gained schemas through `TempRoots`.

`tests/helpers.py` has `FLOOR`, `ABOVE`, `SCHEMA_FIXTURES`,
`install_schemas`, `make_root`, `drop_key`, the new `TempRoots`, and
`StubBale` with schemas. `test_kill.executable()` now builds the gate's
verdict as `bale.check` would. It reads no disk.

## 4. What the probe and the attachment established

You attached `bale-0.4.51-schemas.tar.gz` (30,420 bytes, sha256
`b6e62172…614e1`, as the brief gives) after probe
`twine-floor-schemas` had already run (2026-10-12T14:10:33Z, 605 inner
lines, trailer matching). The probe established:

- **Root resolution.** `bale` on PATH resolves to
  `/home/chordsphere/bale`, with `bin/VERSION` 0.4.52.
- **The install's schemas.** All eight files in its `schemas/` match
  their pins, and there are no other files. Byte counts: 6915, 5077,
  2992, 5547, 6457, 15000, 26227, 49179 (117,394 in all).
- **The payload.** It decoded (sha256 `c8287fd9…`) to the same eight
  files as the attachment, file for file. The fixtures are those
  bytes.
- **twine-src.** Head is `9271b10` (the per-session checkpoint
  commit), `VERSION` 0.13.0, latest applied
  `applied/2026-10-12-twine-pin-051-001`, manifest still at
  `pin = "0.4.51"`, no `fixtures/bale-0.4.51/schemas` yet. The only
  untracked files are telemetry. So this builds on pin-051 as landed.
- **The two archived proposals** the brief named but the request
  didn't carry: status-inflight-004 (`is_temp_name`; `status` as a
  reader in contract §8) and exchange-vouch-005 (the vouch doubles
  clause). All three are done:
  - `is_temp_name` is exported from `twine/kill.py`, and `inflight`
    uses it with no regex of its own.
  - Contract §8 names `status`.
  - The relay surface's `doubles` gained a second entry naming the
    vouch doubles. pin-051 hadn't added it.

## 5. The seed annotation (for tidy7, verbatim and complete)

Under **D2**, after pin-051's annotation:

> [2026-10-12-twine-pin-floor-002: amended — D2 is a floor. The ruling of
> the sitting `2026-10-08-open-arc2-003`, its light block answered "as
> assumed" on 2026-10-08:
>
> > [1] question:     Relax D2 from an exact pin to a floor plus the manifest's key-and-schema contract?
> >     while doing:  deciding what the pin-051 brief and a twine-pin-floor session carry
> >     would assume: yes — floor >= 0.4.51, schemas by hash, keys per surface on the first line read
> >     why blocked:  D2 and T8 are seed rulings; the gate's meaning is yours to change
>
> The gate is now a floor plus schema hashes plus the per-surface key
> check: twine drives any bale whose `bin/VERSION` is at or above the
> floor — `[bale] floor` in the consumption manifest, `0.4.51`, the
> version the recordings were made at, raised only by a recording
> session — and whose installed `schemas/` hash as `[bale.schemas]` pins
> them; it refuses one below the floor, one whose version cannot be read
> or parsed, and one whose schemas differ or are missing; and every verb
> that reads a bale `--json` line checks, on that line, that each key the
> manifest lists for its surface is present (an extra key is free). The
> exact pin and the "bump the pin" upgrade retire: an install that moves
> without touching a listed key or a pinned schema needs nothing, and one
> that does needs a recording session. 0.4.52 was the first install
> admitted without a recording (probe `twine-052-delta`, 2026-10-12).
> `VERSION` 0.14.0.]

Under **T8**, one line:

> [2026-10-12-twine-pin-floor-002: the fixtures directory is named by the
> floor — `fixtures/bale-<floor>/`, the version the recordings were made
> at.]

D17 is unchanged. The key check and the schema hashes exist so that
D17's "no surprises" holds above the floor, and I said so in contract
§11.1 rather than annotating D17.

## 6. Where to look, and what I'm unsure of

- **`model_identity`** is `anthropic:claude-opus-5-5`. That's the
  identifier this session is configured with. The model actually
  serving a turn isn't something the session can attest.
- **The key check's reach.** It checks what the manifest lists today.
  The apply surface lists one key (`outcome`). If you want the apply
  line held to more than twine reads, that's a manifest edit, and the
  tests will follow from `keys`.
- **Two out-of-forecast mentions of "pin" stay**, because both files
  are outside the forecast and neither is wrong enough to need a
  departure: `twine/__init__.py`'s module map ("the pin check") and
  `twine/commands/transitions.py`'s help text ("bale's spellings at
  the pin"). See Proposals.
- **Two lines in renamed tests grew from 96 to 97 characters** with
  `PIN` → `FLOOR`. There's no linter config in the tree, so I left
  them.

## Proposals

**What.** Re-word the two leftover "pin" mentions: `twine/__init__.py`'s
module map ("the pin check" → "the gate: floor, schema hashes") and
`twine/commands/transitions.py`'s description ("spellings at the pin" →
"at the floor").
**Why.** Both still describe D2 as an exact pin, in text an operator
reads (`--help`, the package docstring). Neither file was in this
session's forecast, and I'd rather not add two more departures for
wording.
**Scope hints.** Those two files only, in whichever session next
touches either.

**What.** Record 0.4.52's crafter probe scaffold (`c167f5b5…`) as a
`probe` specimen beside 0.4.51's.
**Why.** fixtures/README.md now says crafter emissions are re-recorded
when the crafter's sha256 moves, and 0.4.52's has moved (a bound line
and a bounded capture). `take` reads the sentinels and the trailer, so
nothing breaks today, but the rule now owes a recording. The brief
already queued this as a later small session; this just confirms the
rule now points at it.
**Scope hints.** `fixtures/bale-0.4.52/crafter/` or a carried
specimen. It can't raise the floor (nothing twine reads moved), so it's
a specimen, not a recording session.

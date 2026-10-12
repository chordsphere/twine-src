# notes.md — 2026-10-12-twine-pin-051-001 (the pin to bale 0.4.51, recorded with stderr)

The pin is 0.4.51 and `VERSION` is 0.13.0. The twenty-four recordings of
probe `twine-051-record` are under `fixtures/bale-0.4.51/`, each with a
`.stderr` sibling. I landed them with the new `bin/twine-land-recordings`
from the paste-back, and the paste-back lands too, under
`carried/`, as their source. The recorder is `bin/twine-record-fixtures`.
The relay stdin assumption is gone from all four places it lived. No verb's
code changed: every file under `twine/` and `bin/twine` hashes as it did.

Seventy files change: seventeen modified and fifty-three created. Every one
is inside the forecast, so there are no forecast departures. `twine/bale.py`
was in the forecast and is untouched: `load_manifest` passes `reasons`
through as data and never needed to know relay's. The suite went from 568
to 597 tests and is green on python 3.13 as root, with no network and no
bale. The only bale-like thing the tests run is one stub `bale` that
`tests/test_recordings.py` writes.

**One thing to look at before you apply.** This request was packed by bale
**0.4.52** (`provenance.bale_version`, and `BALE_HELP.md`'s header), so your
install has moved past 0.4.51 since the 2026-10-08 probes. The goal pins
0.4.51 exactly, and that is what I did. But at an exact pin of 0.4.51, every
carry verb and `twine kill` will refuse your 0.4.52 install (D2), just as
they refused 0.4.51 against the 0.4.49 pin. That lasts until
`twine-pin-floor` lands. The floor session will also need a recording, or
at least a reading, of 0.4.52's surfaces to claim the key-and-schema
contract holds. The recorder now makes that one run of
`bin/twine-record-fixtures`. See Proposals.

## 1. The four decisions brief §7 left to me

**1. Where the naming rule lives: `tests/fixture_rule.py`, not
`twine/fixtures.py`.** I meant to use `twine/` and stopped. Four guards
walk every module under `twine/` and hold that only `twine/bale.py`
carries the argv tokens `"relay"`, `"apply"`, `"unlock"` and `"open"`
(`test_relay_is_built_in_one_place_only`, `test_apply_is_built_in_one_place_only`,
`test_unlock_is_built_in_one_place_only`, and carry-bundle's `open` guard).
`fixture_key` spells all four, so moving it under `twine/` would mean
loosening those guards for code that builds no argv. Instead the rule is a
pure, stdlib-only module under `tests/` (inside the forecast) that imports
nothing from twine. Every path function takes the version explicitly.
`tests/helpers.py` re-exports it with `PIN` as the default, so no caller
moved. The lander puts its own repository on `sys.path` (as `bin/twine`
does) and does `from tests import fixture_rule as rule`. A test asserts it
defines no naming function of its own. One small, deliberate change came
with the move: `fixture_key` now keeps a token that is already a `Role` in
place. The 0.4.49 version turned roles back into strings, so normalizing
`relay sid stdin` again read `stdin` as a file. That never mattered while
relay was recorded with a file. It would have broken the idempotence check
on the new stdin names.

**2. The lander's output: printed, on stdout.** Without `--check`, it
writes only under `fixtures/bale-<V>/` and prints three things: the
section's eight-column rows (with the header), the carried table's row, and
one inline table per recording in the manifest's `also_recorded` shape,
grouped by verb, with the crafter paths last. Placing them is the worker's
job. I used those printed rows verbatim for the 0.4.51 section, and
`--check` holds the README to them. Three additions beyond the brief's
signature, for you to ratify:
- `--tree DIR`, so the tests can check and land into temp copies.
- `--check` also fails on a file under `fixtures/bale-<V>/` that the paste
  does not derive.
- Landing refuses, before writing anything, to replace a file that holds
  other bytes. Landing twice is a no-op.

Exit 2 is reserved for usage errors and a paste that can't be read.

**3. `Recording.stderr`: eager.** It is read when the recording is read, by
the new `read_recording` and `recorded_stderr`, and held to the row's
stderr bytes and sha256. A sibling whose bytes differ from its row is a
loud failure, not a replay. The files are small, and eager keeps
`Recording` a frozen value. `FixturePlayer` reads its rows once at
construction.

**4. Wording, and the sibling's name.** The sibling replaces the extension
rather than appending to it: `unlock_sid_--json+unlocked.json` sits beside
`unlock_sid_--json+unlocked.stderr`. I read "the same name and the
extension `.stderr`" that way. Wherever stderr is now a fact I said
"recorded byte-exact" and named what it holds. In the history paragraphs I
left the older sentence in place and said in one sentence that it is
history: the kill-reason-002 paragraph in `tests/helpers.py`'s docstring,
the 0.4.49 section's "stderr" paragraph, and the one-derivation story in
contract §14.7.

## 2. What the paste-back said, and where it differs from the brief

All 24 rows I decoded match brief §2's table: every exit, byte count and
both sha256s, in the brief's order, compared by script and not by eye. The
paste matches both hashes in brief §1 (CRLF `b1bb27d1…`, LF `dec7a229…`,
133981 bytes), its trailer counts 1444 lines, and the recorder script you
attached hashes to `81468367…`. I also confirmed these brief facts against
the bytes: `stats --sid`, the no-op unlock, the probe scaffold and the light
block are byte-identical to 0.4.49's; open has 23 keys and relay has 13;
`second-desk` carries the outbox tarball; and the relayed round's stderr
says `paste block read from <stdin> (trailer verified)`.

A further fact: the block the tests carry (the relayed line's own `block`)
is byte for byte the stdin that round was recorded with: 964 bytes,
`7921f0df…`. So the relay replay now answers exactly the call it was
recorded for, and a test says so.

Two places where the bytes say a bit more than the brief:

- **The unlock refusals' stderr is not *only* `[bale] error: <message>`.**
  For `not-open` and `integration-json` it is exactly that line plus a
  newline. For `hold-branch`, the same line comes after bale's
  `[bale] unlock: 2026-10-08-sc-002` progress line. So the true statement
  is that each refusal's stderr *ends with* the error line. The manifest's
  "beside `[bale] error: <message>` on stderr" stands, and
  `test_the_unlock_refusal_line_is_what_the_entry_says` checks the exact
  prefix for each recording. The relay and open refusals carry
  `[bale] error: <cause>` as a line; for `not-an-object` it sits between
  two `[bale] relay:` lines.
- **The paste's text crossed clip.exe as code page 437.** That is how you
  get `ΓÇö` for an em dash, in the headers as well as in the raw spans. The
  lander never reads text it doesn't need: the annotations' place tokens
  are ASCII, and the bytes come from the gzip copies.
  `test_its_recordings_are_the_pastes_in_order` compares the recorder's
  `rec` annotations to the paste's headers after encoding them the same way.

**The transition table, which the brief didn't predict.**
`share/transitions.toml` says `written_against = "0.4.49"`. Its header
calls that "equal to the manifest's pin", and two tests held it equal to
`PIN`. The request's constraint keeps the file untouched, so I left it.
`twine transitions` stays ok, since it reports both versions and gates on
neither. The vocabularies didn't move, so 0.4.49 is still true of what the
table keys on. I rewrote the two tests to assert exactly that:
`test_the_table_is_written_against_a_version_the_pin_keeps`, and the
subprocess twin test. Contract §12.4 says the table may lag the pin. If you
would rather the table say 0.4.51, that is a one-line edit for whichever
session next touches it (Proposals).

**The recorder, landed with the one change.** The slug is an argument
(`bin/twine-record-fixtures [SLUG]`, default `twine-record-<installed
version>`). It is validated: lowercase letters, digits, `.` and `-`, else
exit 2. It only names the sentinels. I also rewrote the header comment
(its `# PROBE` slug, its usage lines and its "Why"), because the old
lines named `twine-051-record.sh`. The recordings' own text is unchanged:
the goals, bundle names, `no-such-sid-twine-051` and the specimen
summaries are per-run values the names carry by role, so they stay. Two
quirks I left alone, because the brief said everything else stays:
- The environment line `clipboard key in the project bale.toml: 0` prints
  `0` twice (`grep -c` prints 0 and exits 1, then `|| echo 0` adds
  another).
- `argv:` echoes `$*` unquoted. That is why the shared rule has
  `echoed_argv`, which treats pack's goal as everything before its first
  flag.

Both are in Proposals.

## 3. Every test that moved, by name

`tests/test_fixtures.py` (rewritten around the eight-column rows):
- `test_dry_run_fixture_is_the_recorded_line`: 290 bytes, `7e7fd743…`, sid
  `2026-10-08-sc-002`, exit 0, stderr as its row.
- `test_the_pinned_directory_holds_the_twenty_three` →
  `test_the_pinned_directory_holds_the_twenty_four`: 1/6/14/3, plus 24
  siblings and the one carried paste.
- New: `test_every_recording_has_its_stderr_sibling_and_nothing_else_does`.
  It also names the four empty siblings.
- `NamedByTheRule`: all three tests read stdout files only.
  `test_each_name_is_its_commands_normalized_name` uses
  `fixture_rule.echoed_argv`. `test_the_groups_this_section_names` lists
  the eleven grouped names, with `+open-refused` and the two
  `+relay-refused+<reason>`.
- `test_rows_match_files_bytes_and_hashes`: now checks the stderr columns.
- `test_earlier_versions_rows_still_match_their_files`: uses the shared
  parser. The 0.4.45 and 0.4.49 rows read as rows without stderr. It also
  checks carried rows. The old regex had misread the new eight-column rows'
  stderr columns as their stdout.
- New: `test_the_row_parser_reads_both_shapes`.
- `test_command_rows_name_their_emitter`.
- `test_an_unrecorded_exit_is_said_never_guessed`: now expects 24.
- `test_carried_pastes_differ_from_what_arrived_only_by_crlf`: covers three
  pastes. It finds every file under `bale-*/carried/`, and each must have
  its row.
- New: `test_the_source_paste_is_the_one_the_brief_names`.

`tests/test_consumption_manifest.py`:
- `expected_relpath` → `expected_relpaths`, which runs the shared
  collision rule over a surface's recordings.
- `test_the_schema_hashes_are_unchanged_at_the_pin`: the header must say a
  probe re-hashed them.
- `test_every_verb_surface_fixture_exists_and_follows_the_naming_rule`.
- `test_per_run_placeholders_are_the_roles_the_key_gives`: no `<file>` is
  left.
- `test_relay_json_is_read_by_carry_exchange`: argv
  `relay <sid> - --json`, the new `also_recorded`, and the note.
- New: `test_the_relay_refusals_reason_is_bales_closed_set`.
- `test_the_carried_pastes_stay_under_the_version_that_printed_them`: the
  pin's `carried/` holds exactly the source paste, which no format entry
  names.
- `test_open_json_is_read_by_carry_bundle`: 23 keys, `open-refused`
  `not-found`, `second-desk`'s tarball, and the note.
- `test_the_unlock_refusal_line_is_what_the_entry_says`: the stderr
  against the line.
- `test_each_home_is_an_installed_file_twine_pins`: `1f4f2c75…`, line 3426.
- `test_the_re_reading_at_the_pin_is_named_as_not_a_probe`: both readings.
- Docstrings: `test_the_kill_switchs_unlock_surface`,
  `test_every_json_verb_the_pin_bump_recorded_is_a_surface`.

`tests/test_kill.py`:
- The module docstring keeps kill-reason-002's paragraph as history and
  gains a 0.4.51 paragraph.
- The `HOLD` comment and the `hold_line_with` docstring changed. It still
  answers `b""`, now named as such: the recorded HOLD stderr names the
  branch, which would muddy what an edited line proves.
- `test_a_refusal_is_not_ok_names_bales_reason_and_is_never_retried`: this
  is the "recorded `[bale] error:` line passes through byte-exact" test.
  The first failure is now `bale exited 1: [bale] error: …`. A
  `stderr=b""` run keeps "with nothing on stderr".
- `test_the_hold_branch_refusal_hands_back_bales_own_remedy`: the recorded
  stderr is reported, and the first failure quotes its last line.
- `test_a_refused_closure_says_where_it_stopped`: the twin's `stderr` is
  the recording's.
- `test_human_mode_names_each_step_and_the_hand_line`: the empty-stderr run
  passes `stderr=b""`, and a new fourth run shows the recorded stderr after
  "bale's stderr follows".
- `test_a_stub_printing_the_hold_line_with_nothing_on_stderr_hands_back_revert`:
  passes `stderr=""` to keep the reproduction's condition.
- Docstrings: `KillEndToEnd`, `test_a_line_that_is_not_this_close_is_not_ok`.
- Every test that fed `NOT_BALES_STDERR` is unchanged.

`tests/test_carry_bale.py` (section 3 and the dry run):
- New: `test_the_recorded_stderr_is_reported_and_passed_through`.
- New: `test_the_block_twine_carries_is_the_stdin_bale_was_recorded_with`.
- `test_each_recorded_refusal_is_not_ok_quoting_its_cause`: now uses
  `not-an-object` and `not-open`. Bale's stderr passes through, and the
  `reason` code is not quoted.
- `test_human_mode_not_ok_is_one_line_and_never_bales_stdout`.
- `test_the_twins_fixed_names_on_every_path`.
- `test_the_fixture_player_has_no_recording_of_twines_relay_argv` →
  `test_the_fixture_player_answers_twines_relay_argv_from_the_recording`,
  its opposite. The player answers twine's argv with the stdout, exit and
  stderr `RecordedRelay` replays. It refuses without a selection, naming
  all three. It finds nothing for a file argument.
- `test_the_recorded_scope_drift_refusal_is_not_ok`: the twin's `stderr`
  is the recorded one.
- `test_a_recorded_refusal_through_the_real_seam`: uses `not-an-object`,
  and its stderr reaches twine's.
- Docstrings: the module docstring, `test_ok_json_carries_bales_stdout_and_stderr`,
  `test_the_relayed_block_is_an_intact_exchange_block_of_its_sid`,
  `test_an_outcome_bale_never_emits_is_named`, and `TempCase.player`.

`tests/test_carry_bundle.py`:
- `test_opened_is_ok_and_the_record_has_exactly_its_keys_and_values`: the
  new bundle sha, `RECORDED_BUNDLE_SHA256`.
- `test_opened_then_second_desk_appends_and_takes_the_records_tarball` →
  `…_takes_bales_tarball`: `tarball_source` is `"bale"`, and stderr says
  "(from bale)".
- `test_second_desk_with_no_record_writes_a_fresh_one_and_says_so`: the
  twin carries bale's tarball while the fresh record keeps null. This is
  the test that says the behaviour stands until `twine-bundle-051`.
- `test_second_desk_over_a_record_that_is_not_one_replaces_it_naming_why`:
  the fake record now names `SID`.
- `test_bales_tarball_wins_when_its_second_desk_line_names_one`: docstring
  only. The double still edits the tarball, because the recorded one
  equals the record's.
- New: `test_the_recorded_refusal_is_not_ok_and_records_nothing`, the
  player with `SELECT_REFUSED`.
- `test_a_refusal_nothing_on_stdout_exit_1` →
  `test_a_bale_that_stopped_before_writing_its_line_is_not_ok`: the double
  is kept and named as the stopped-before-a-line case.
- The module docstring.

`tests/test_process.py`:
- `test_fixture_player_answers_a_recorded_bale_argv` (stderr).
- New: `test_fixture_player_answers_the_stderr_recorded_beside_stdout`. It
  covers the not-open stderr and a sibling that is not its row's bytes.
- `test_fixture_player_refuses_an_unrecorded_exit_without_a_named_assumption`:
  docstring only.

`tests/test_transitions.py`:
- `test_the_table_is_written_against_the_pin` →
  `test_the_table_is_written_against_a_version_the_pin_keeps`.
- `test_json_twin_as_a_subprocess`.
- Docstring: `test_bale_axes_carry_exactly_bales_spellings`.

Comments and docstrings only, in three more files:
- `tests/test_json_discipline.py`: setUp comments.
- `tests/test_carry.py`: the module docstring.
- `tests/__init__.py`: the layout.

`tests/test_take.py` is untouched. It reads the crafter paths through
`emission_relpath` at the pin, and the 0.4.51 emissions satisfy it as they
are.

New: `tests/test_recordings.py`, 21 tests:
- The shared rule:
  - `echoed_argv`.
  - The stdin role.
  - The collision rule, including its refusal.
  - The sibling name.
- The lander against the landed tree:
  - `--check` ok on the LF and the CRLF paste.
  - The version default.
  - The rows.
- The lander refusing, in temp copies:
  - An altered recording or sibling, named.
  - A missing file, an extra file and a wrong README row, each named.
  - A bad trailer.
  - A stream hash that doesn't match.
  - A paste with no block, and an unreadable one.
- The lander landing:
  - Into an empty tree, byte-identical, its printed rows being the
    README's.
  - Idempotent, and never replacing other bytes.
  - Stdlib-only, importing the rule rather than copying it.
- The recorder:
  - `bash -n`.
  - `take` reads it as probe `twine-record-fixtures`.
  - Its 24 `rec` calls are the paste's headers in order.
  - The slug default and argument, run once end to end against a stub
    `bale` first on a PATH the test builds.

`StubBale`'s `stderr` default changed from `""` to `None`. `None` replays
the recording's sibling, and any string, `""` included, replaces it. No
existing caller relied on the old default meaning "nothing" while also
replaying a recording whose stderr mattered. The suite is the proof.

## 4. validation.sh

It has thirteen checks. It runs from the staged root under `python3 -I -B`
(the lander and `bin/twine` under `-I -S -B`), writes only under
`.validation-logs/<ts>/` (TMPDIR included), and its one tree walk, the
`__pycache__` sweep, prunes `claude/checkpoints/`. Notes on some of them:
- The 24 recordings and their siblings are checked against brief §2's
  table by `sha256sum -c` and a size table, and the file count is checked
  too.
- The 33 files under `bale-0.4.45/` and `bale-0.4.49/` are checked by
  sha256, with a count.
- `bale check` runs against stub roots at 0.4.51 (ok) and 0.4.49 (exit 1).
- The untouched set is `bin/twine`, `share/transitions.toml` and all 19
  modules under `twine/`. That set is stronger than the brief's list,
  because "no verb changed" covers the whole package.
- `twine-seed.md` is not in the request, so I can't hash it. The script
  checks instead that `.bale-manifest.json`'s `changes[]` doesn't name it,
  and prints `[SKIP]` with that reason outside staging.

I ran it twice. On a staged copy (the tree I was given, plus `files/`, plus
`apply.sh`, plus the manifest) all thirteen pass in about 60 seconds. On the
unmodified tree every session check fails. Five pass on both by design:
the suite (568 there), the history hashes, the untouched set,
`twine-seed.md`, and no `__pycache__`. Those five guard "unchanged" or
"still green", so they can't fail on the old tree. The two claims, the suite
and the lander's `--check`, are `observed` from the staged run. The
checkpoint's call, `bin/twine-land-recordings --check
fixtures/bale-0.4.51/carried/probe-output_twine-051-record.txt` from the
tree root, exits 0. That is check 3.

## 5. The seed annotation (out of scope here; for tidy7)

Under D2, after the 2026-10-07-twine-pin-049-001 annotation, verbatim:

> [2026-10-12-twine-pin-051-001: the second deliberate bump — the pin
> moved from 0.4.49 to 0.4.51 (`VERSION` 0.13.0), twenty-four recordings
> made by one probe on 2026-10-08 (`twine-051-record`, stdout and stderr,
> each stream's bytes carried as a gzip+base64 copy) and landed by
> `bin/twine-land-recordings` from its paste-back, which lands beside them
> as their source; every recording's stderr is a `.stderr` sibling and its
> README row carries it; the probe itself landed as the recorder,
> `bin/twine-record-fixtures`; `bale relay <sid> - --json` is recorded
> under twine's own argv, retiring the stdin assumption the 0.4.49 file
> recordings rested on; the schemas re-hashed by the probe and the
> vocabularies re-read, all unchanged; no verb changed. This is the last
> exact pin: D2 becomes a floor plus the consumption manifest's
> key-and-schema contract in `twine-pin-floor`.]

At the end of §5.1's road annotations, verbatim:

> [2026-10-12-twine-pin-051-001: the pin at bale 0.4.51 (`VERSION`
> 0.13.0) — twenty-four recordings with their stderr, landed from one
> paste-back by the new lander, the recorder landed beside it, the relay
> stdin assumption retired, no verb changed; the last exact pin before
> `twine-pin-floor`.]

## Proposals

**What.** Make `twine-pin-floor` the session that admits 0.4.52. Before
it does, run `bin/twine-record-fixtures` against 0.4.52 and land the
paste-back (`--check` makes the landing verifiable), so the floor's
key-and-schema claim is checked against bytes.
**Why.** This request was packed by bale 0.4.52, so your install is past
the exact pin this session sets. Every carry verb and `twine kill` will
refuse it until the floor lands. A floor that admits a version nobody
recorded would claim a contract on a reading alone. The recorder makes
the recording cheap.
**Scope hints.** The same files this session touched. The lander needs no
change for a new version.

**What.** Restate `share/transitions.toml`'s `written_against`, and its
header's "(equal to the manifest's pin)", at the next session allowed to
touch the table. Under a floor, it is probably "the earliest version
whose vocabularies these keys are".
**Why.** It says 0.4.49 beside a 0.4.51 pin, and the header sentence is
now false. Nothing gates on the value, and the two tests now pin the gap
explicitly rather than hide it.
**Scope hints.** `share/transitions.toml` (the `[table]` key and its header
comment), `tests/test_transitions.py` (the two tests named in §3),
contract §12.4.

**What.** Two small recorder fixes for the next recording:
- Print `argv:` shell-quoted, for example with `printf '%q '`, so a
  recorded argv round-trips without `echoed_argv`'s pack rule.
- Fix the doubled `0` on the clipboard-key line, for example with
  `grep -c … || true`.

**Why.** The lander special-cases pack's goal only because `$*` loses the
quoting. The doubled `0` splits one environment line in two (harmless,
but it reads like a fault).
**Scope hints.** `bin/twine-record-fixtures`, with `echoed_argv` and the
lander's command cell in step. Keep the `== recording:` header unchanged,
since the lander and a test read it.

**What.** In `twine-bundle-051`, refresh the code comments that still cite
bale 0.4.49's open and unlock behaviour as current. They were left alone
because the request kept `twine/commands/*.py`, `twine/kill.py` and
`twine/inflight.py` untouched:
- `twine/inflight.py:30`: "bale 0.4.49's `second-desk` line carries…".
- The `format_open_json, bale 0.4.49` comments in `twine/inflight.py` and
  `twine/commands/carry_bundle.py`.

**Why.** They cite 0.4.49 fixture paths, which still exist as history, so
they aren't wrong. But the second-desk sentence describes a line that has
named a tarball since 0.4.50, and that session is the one changing that
behaviour.
**Scope hints.** `twine/inflight.py`, `twine/commands/carry_bundle.py`,
`twine/kill.py` lines ~130 and ~955.

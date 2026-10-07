# notes.md — 2026-10-07-twine-pin-049-001 (the pin to bale 0.4.49)

The pin is 0.4.49, the twenty-three recordings are landed, the `[[wanted]]`
entries are surfaces, the unlock doubles are gone and `VERSION` is 0.8.0.
Forty files change: seventeen modified, twenty-three created, every one
inside the forecast (`twine/bale.py` is in the forecast and untouched —
nothing in it names the pin). No verb's behaviour changes. The suite went
from 435 to 449 tests (the brief counts 434 at tidy5; the tree shipped here
runs 435, so one more landed with tidy5 than the carry-forward counted) and
is green on 3.11, 3.12 and 3.13, as root and as an unprivileged user (where
the one root-skipped test runs too), with no network and no bale.

## 1. The recordings

Every `--- raw: … ---` span of the three paste-backs, CRLF folded to LF,
hashed to the sha256 and byte count the probe printed beside it — twenty of
twenty-three. Rows 21–23 (the crafter emissions) did not: their raw spans
hold em dashes `clip.exe` mangled, and for them the gzip+base64 copy
decoded to the hashing bytes, as §2 of the brief said it would. All
twenty-three match the brief's table row for row (label, exit, bytes,
sha256). Nothing was repaired. As the brief predicted: row 7 (`stats --sid`)
and row 22 (the light block) are byte-identical to the 0.4.45 fixtures; the
exchange block differs only in `created_at` and its trailer; the probe
scaffold differs only in its tail (the clipboard copy through `bale
clipboard`, where 0.4.45 had remedy text in comments).

The recovery script is not shipped (it is a one-off against the three
pastes, not project code); `validation.sh` carries the twenty-three hashes
and byte counts as a `sha256sum -c` list and a size table, so the landing is
re-checkable from the tree alone.

## 2. Decisions to ratify (brief §9)

**The scratch `<where>` is `scratch/`.** `fixture_relpath(argv, "scratch")`
lands there; `fixtures/README.md` states the repository's facts (git head
`9548cb7` on `main`, one committed `hello.txt`, no `bale.toml`, the
operator's global one in force). `twine-src/` holds rows 2–7, `anywhere/`
row 1 (`--version` ran in `~/twine-src` this time; its output depends on no
directory, so it stays where 0.4.45's was), `scratch/` rows 8–20.

**Two roles.** Every positional after `open` is `bundle`
(`open_bundle_--json`, `open_--check_bundle_--json`); the positional right
after `pack` is `goal`, while a flag's value stays
(`pack_goal_--slug-ro_--read-only_--no-readme_--json`). `relay <sid> <file>
--json` needed no new rule — session 2b-ii's `file` role already covered it.

**Outcome groups.** When a version's directory tree (across every `<where>`)
holds more than one recording of a normalized argv, each carries
`+<outcome>` between the name and the extension, and `+<reason>` only where
two share the outcome — the line's own `reason` when it has one, else a
short tag the README assigns (relay's refusals carry a `cause` sentence, no
code: `ingest`, `session-gate`). An argv recorded once keeps the plain
name. I scoped the collision to the whole version rather than one `<where>`
so that `unlock_sid_--json`'s three recordings read alike wherever they
sit: `+unlock-refused+not-open` (twine-src), `+unlock-refused+hold-branch`
and `+unlocked` (scratch). `+` is the separator because neither `_` nor `-`
is free and a dot would collide with the extension. `tests/test_fixtures.py`
`NamedByTheRule` checks the rule against the files — every name is its
README row's command normalized, every group follows the collision rule,
and the ten grouped names are listed verbatim.

**How the player selects.** `FixturePlayer(repo_root, assumed_exits=,
scratch_root=, select=)`: `where` is `repo` for `repo_root`, `scratch` for
`scratch_root` (the directory a test names as the throwaway repository),
else `anywhere`; a grouped argv is answered only when `select` names the
group for its normalized name (`{"apply_--dry-run_--json_tarball":
"dry-run"}`), and otherwise refused, naming the candidates — the same
"name your assumption where you use it" posture as `assumed_exits`, which
stays though no 0.4.49 row needs it (`test_process` proves the refusal with
a patched exit table). A plain name beside grouped ones is an error, not a
pick.

**`StubBale` and `RecordedUnlock`.** `StubBale` is unchanged in shape: it
replays whatever file `unlock_stdout` names, now a recording's path, with
`exit_code` and `stderr` the test passes from the recording. `UnlockDouble`
is replaced by `RecordedUnlock(recording="aborted", *, stdout=None,
timed_out=False)`: it answers twine's one unlock argv with a recording's
stdout, exit and stderr; `stdout=` replaces the bytes only with bytes that
are not bale's (`b"unlocked\n"`, `b""`), to prove what twine refuses.
`unlock_recording(name)` reads the six by the names the tests call them
(`aborted`, `hold-branch`, `closed-read-only`, `no-op`, `not-open`,
`integration-json`) and returns path, stdout, exit (from the README row),
stderr and the parsed line.

**The one stderr derivation — please look at this.** No row records stderr
byte-exact (the probes print its first lines; `clip.exe` mangled the em
dash). For every `unlock-refused` recording the probe's first stderr line
is `[bale] error: <message>` with the same text as the line's `message`
key, so `unlock_recording` answers a refusal's stderr as `[bale] error: ` +
`message` + LF, and says it is a derivation (fixtures/README.md, "stderr,
and the one derivation"; contract §14.7). Without it the HOLD-branch test
could not exercise the hand line twine still keys on stderr. If you would
rather no derived byte reach a test, the alternative is recording stderr
byte-exact in a later probe (a gzip+base64 copy of each stderr), and the
HOLD tests go to a double until then — say so and I will switch.

**The refusals' argv.** Rows 3 and 17 were recorded as `unlock <sid>
--json`, without `--reason aborted`; the tests replay them for twine's argv
on the assumption that bale refuses before the reason matters. Named in
`RecordedUnlock`'s docstring, the README and the manifest's feedback.

**The carried pastes stay under `bale-0.4.45/`** — the desk's preference.
Format entries carry `fixtures_version` (the pin for the three crafter
emissions, `0.4.45` for the two pastes) and `carried_relpath` reads it from
the manifest's entry (an explicit `version=` overrides). The README's
`carried/` bullet says why a copy would be wrong.

**`also_recorded` and `reasons`.** Further recordings of a verb ride its
surface as inline tables `{argv, cwd, outcome, reason?, fixture}` — the
apply refusal, relay's three, open's two, unlock's five — each checked by
the naming test against its own line's `outcome`/`reason`. The unlock
refusal's five codes are `reasons` with `reasons_home`, on the surface, not
an axis, as §3.2 ruled. The `cwd` of a surface recorded in the scratch
repository is `scratch` (the header comment now says `cwd` is where the
recording ran, which is where twine runs it — a repo whose session it is).

**The format entries' wording.** `fixtures_version` is the key; each
entry's note says why its version is what it is (re-recorded at the pin;
printed by 0.4.45 and unchanged at 0.4.49 — the three new paste-backs carry
the same sentinels and trailer; no 0.4.49 apply carried).

**`pack --json`'s key_owner.** I do not have bale-src; the entry names
"bale pack --json's report in bin/bale_report.py" with the keys the
recorded line carries and the `opener` key the brief names, and says so.
`format_open_json` / `format_relay_json` are the brief's names.

**The probe specimen's tail.** `filled_probe()` cuts the 0.4.49 scaffold's
clipboard tail by default (`SCAFFOLD_TAIL_OPEN`), because `carry probe
--run` runs the script under the operator's PATH and the tail would hand
the block to a real `bale clipboard` on your machine — a clipboard write
from a test. `filled_probe(clipboard_tail=True)` keeps it, and one test
runs it twice under a PATH it builds (bash, wc, tr and a stub `bale`
recording its argv and stdin; then without the stub): the paste-back is
unaffected, the stub saw exactly `clipboard --block "probe block"` with the
block on stdin, and without a bale stderr carries the two `[clipboard]`
notices after the probe's own line. Contract §10.3 gained the sentence the
brief asked for.

**The dry-run exit.** `ASSUMED_DRY_RUN_EXIT` is retired: row 15 has its
exit (0). The carry-response tests pass `--cwd <the test's dir>` and a
player with that directory as `scratch_root` — mirroring the recording,
which was made in a throwaway repository.

**`twine kill`'s tests kill `2026-10-07-sc-002`.** The recorded close names
that sid, and `close_aborted` checks `sid`; so `SID` in `test_kill.py` is
`UNLOCK_RECORDED_SID`, `HOLD_REFUSAL` is row 17's `message`, and
`test_json_discipline`'s `KILL_SID` is the same sid.

**What a 0.4.49 refusal makes twine say** (code untouched, input new): a
refusal now has a JSON line on stdout, so after "bale exited 1: [bale]
error: …" the closure also names `outcome 'unlock-refused', not
'unlocked'`, the sid when it is another's, and `closure_reason None, not
'aborted'`, and keeps the line as `closure.unlock` (the twin's `closure`,
§14.6). The refusal tests assert exactly that; contract §14.5 says it.
`test_a_line_that_is_not_this_close_is_not_ok` now uses two recordings
(the no-op; the read-only close for "another sid" and "another reason")
and two non-bale stdouts.

## 3. Every test rewritten, by name

`tests/test_fixtures.py`: `test_dry_run_fixture_is_the_recorded_line` (row
15: 290 bytes, `266fc2…`, sid `2026-10-07-sc-002`, exit 0 in its row);
`test_an_unrecorded_exit_is_said_never_guessed` (every pinned row has an
exit — refusals 1, the rest 0 — the 0.4.45 dry-run row still says
`unrecorded` as history; the player's refusal is tested in
`test_process`); `test_rows_match_files_bytes_and_hashes` (scoped to
`bale-<pin>/`); `test_command_rows_name_their_emitter` (knows `scratch/`);
`test_carried_pastes_differ_from_what_arrived_only_by_crlf` (finds the
pastes through the manifest's format entries, under `fixtures_version`).
New: `test_the_pinned_directory_holds_the_twenty_three`,
`test_earlier_versions_rows_still_match_their_files`, and the
`NamedByTheRule` class (three tests).

`tests/test_consumption_manifest.py`:
`test_wanted_surfaces_name_the_open_json_gap` →
`test_open_json_is_a_surface_read_by_nothing_yet` (also covers `pack`);
`test_relay_json_is_wanted_by_session_2b_ii` →
`test_relay_json_is_a_surface_now`; `test_the_unlock_json_refusal_is_wanted`
→ `test_the_unlock_refusal_line_is_what_the_entry_says`; plus
`test_no_wanted_surface_remains`. `test_the_two_json_verbs_the_brief_names_are_recorded`
→ `test_every_json_verb_the_pin_bump_recorded_is_a_surface`.
`test_every_verb_surface_fixture_exists_and_follows_the_naming_rule`
(groups and `also_recorded`), `test_per_run_placeholders_are_the_roles_the_key_gives`
(the five roles, on surfaces and rows), `test_the_carry_hand_offs_bale_surfaces`
(the scratch dry run and its refusal), `test_the_kill_switchs_unlock_surface`
(the 0.4.49 facts), `test_each_home_is_an_installed_file_twine_pins`
(the new hash and line), `test_the_apply_surface_names_its_outcome_vocabulary`
(the recorded outcomes are in the vocabulary), `test_malformed_vocabularies_refuse_naming_why`
(the head reads `PIN`). New: `test_the_schema_hashes_are_unchanged_at_the_pin`,
`test_the_two_new_roles_normalize_as_the_readme_says`,
`test_the_carried_pastes_stay_under_the_version_that_printed_them`,
`test_the_re_reading_at_the_pin_is_named_as_not_a_probe`; `FORMAT_REQUIRED`
gains `fixtures_version`.

`tests/test_kill.py`: every `UnlockDouble()` → `RecordedUnlock()`;
`test_a_refusal_is_not_ok_names_bales_reason_and_is_never_retried`,
`test_the_hold_branch_refusal_hands_back_bales_own_remedy`,
`test_a_line_that_is_not_this_close_is_not_ok`,
`test_a_timeout_is_not_ok_and_not_retried`,
`test_a_refused_closure_says_where_it_stopped`,
`test_ok_is_exit_0_with_the_fixed_keys` (the twin's `closure` is the
recording's line), `test_every_path_carries_the_same_keys`,
`test_human_mode_names_each_step_and_the_hand_line`, and the three
`KillEndToEnd` tests (the stub on recordings). `UNLOCK_KEYS` is the
recorded twelve.

`tests/test_carry.py`: `test_stderr_is_reported_not_carried` keeps its
assertion on the tail-less specimen; new
`test_the_scaffolds_clipboard_tail_reaches_only_a_bale_the_test_puts_on_path`.

`tests/test_carry_bale.py`: `test_the_recorded_dry_run_is_ok_and_hands_back_the_apply_line`
and `test_human_stdout_is_exactly_the_apply_line` (scratch player, group
selected); `test_each_dry_run_refusal_is_named_with_its_exit` keeps the
doubles and points at the new `test_the_recorded_scope_drift_refusal_is_not_ok`;
`test_a_version_other_than_the_pin_is_refused_and_never_run` (the pin
literal reads `PIN`); `TempCase.response` adds `--cwd <test dir>` when the
runner is the player.

`tests/test_json_discipline.py`: the setup (recording paths, `KILL_SID`).
`tests/test_process.py`: `test_every_run_seam_double_accepts_the_hook`,
`test_fixture_player_answers_a_recorded_bale_argv` (pinned paths); new
`test_fixture_player_selects_an_outcome_group_only_when_told`,
`test_fixture_player_refuses_an_unrecorded_exit_without_a_named_assumption`.
`tests/test_transitions.py`: one docstring.

## 4. Things worth a look at review

- `tests/helpers.py` now imports `twine.bale.load_manifest` (for
  `fixtures_version`), so a manifest that fails to parse breaks the
  helpers' import loudly — intended, but it is a new coupling.
- `fixture_relpath` kept its `(argv, cwd)` signature with `group` added
  third, so every existing caller still reads the same.
- `claude/context/cli-contract.md` §6 is now a long paragraph; I added
  the new keys in the places the old sentences had them rather than
  restructuring, since the doc rows are what the tests cite.
- The 0.4.45 section of `fixtures/README.md` is untouched text; the
  top prose and the new section are the only edits there.
- `tests/__init__.py` needed no change (its inventory names files, not
  doubles).

## 5. The seed annotation (out of scope here; for the next tidy)

Under D2 (after the 2026-10-03-twine-transitions-004 annotation) and at
the end of §5.1's road annotations, verbatim:

> [2026-10-07-twine-pin-049-001: the first deliberate bump — the pin
> moved from 0.4.45 to 0.4.49 (`VERSION` 0.8.0), the replay suite
> re-recorded against the installed bale by three probes on 2026-10-07
> (twenty-three fixtures, a throwaway repository for the verbs that
> write), the three `[[wanted]]` surfaces bale-src landed at twine's
> asking (`open --json`, `relay --json`, the reason-coded unlock refusal)
> retired into the consumption manifest, the vocabularies re-read and
> unchanged, the unlock doubles replaced by recordings. No verb changed;
> `twine kill` still reads the HOLD refusal by its stderr prefix until
> `twine-kill-reason` keys it on the recorded `reason` code.]

And T8's parenthesis "(`claude/fixtures/bale-0.4.45/*.json` …)" is
office-src's layout, not twine's; it can stand as history.

## Proposals

**What.** `twine-kill-reason` (the brief's §8 next session): key the hand
line on `closure.unlock["reason"] == "hold-branch"` from the recorded
refusal line, retiring `HOLD_BRANCH_REFUSAL`'s text match, and drop the
derived stderr from the tests with it.
**Why.** Row 17's line carries the code; the only reason the tests still
derive a stderr byte string is that twine reads the text. Once the code is
the key, every unlock answer in the suite is recorded bytes and nothing
else.
**Scope hints.** `twine/kill.py` `Closure.hold_branch`, `tests/test_kill.py`,
`tests/helpers.py` `unlock_recording` (drop the derivation), contract §14.2
and §14.5, `fixtures/README.md`'s stderr paragraph. After this session.

**What.** Record stderr byte-exact in the next recording probe: beside each
`--- raw: … ---` stdout span, a gzip+base64 copy of stderr with its own
sha256, so a row can carry a stderr column and the player can answer it.
**Why.** This session's one derivation exists because stderr crossed
`clip.exe` as plain text; a gzip copy survives the paste (rows 21–23 proved
the route). `carry response` and `twine kill` both surface bale's stderr,
and today the tests can only assert it empty or derived.
**Scope hints.** The probe author's side (the desk); `fixtures/README.md`'s
row shape; `FixturePlayer`'s stderr answer; `recorded_exits` → a row parser.

**What.** When `carry exchange` moves to `relay --json` (the session after
Arc 1 row 3), take the `block` key of the recorded `relayed` line as what
it prints, and the two recorded refusals as its not-ok cases; retire the
flagless relay surface's stand-in with that.
**Why.** Rows 11–14 are recorded now; the stand-in and the `BaleDouble`
relay refusals are the last stand-ins on the carry verbs.
**Scope hints.** `twine/commands/carry_bale.py`, the relay surfaces in the
manifest, `tests/test_carry_bale.py` section 3.

**What.** Decide whether `carry probe --run` should run a probe under a
PATH without `bale` (or pass `--no-clipboard`-style control), now that the
scaffold's tail reaches a real `bale clipboard` on the operator's machine.
**Why.** The tail is a convenience for a human pasting; under `carry probe
--run` the paste-back is already captured (`output`, `--out`), so the
clipboard copy is a side effect the courier did not ask for — harmless, but
unannounced. Not changed here (no verb's behaviour changes this session);
the contract now states the fact.
**Scope hints.** `twine/commands/carry.py` (the env it hands bash), contract
§10.3, `tests/test_carry.py`'s tail test (which already builds the PATH
either way).

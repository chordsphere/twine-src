# notes.md — 2026-10-08-twine-status-inflight-004 (`twine status` reads the in-flight records)

Every path I changed is in the forecast. Two forecast paths stayed
untouched, `claude/INDEX.md` and `tests/test_json_discipline.py`; §4 says
why. `VERSION` went from 0.10.0 to 0.11.0, and the suite went from 536 tests
to 556.

The reader is a new `twine.inflight.list_inflight(state_dir) ->
InflightListing(sids, faults)`. `core.state_dir_facts` calls it only when
`inflight/` is a directory. `read_inflight` is unchanged. It is not loosened,
and its own words become the fault text, with the full path cut down to the
basename.

## 1. The four decisions brief §5 left to me

1. **Human wording.** Records print as one line per sid:
   `in-flight record:     <sid>`. Faults print as one line per fault,
   `in-flight fault:      <fault>`, and only when there are any. Neither
   line appears for an empty `inflight/`. `inflight/` goes on the
   `state present:` line with the other four. **This deviates from your
   suggestion** of one `in-flight faults:` line. The reason is that a
   single fault from `read_inflight` already joins its own parts with `"; "`
   (`… lacks sid, cwd; its sid is None, not '…'`). Put several of those on
   one line and you can't tell where one file's sentence ends and the next
   begins. With one line per file, each line is greppable by file name.
   The labels are padded to the same 22-column field as the other `status`
   lines.
2. **The listing lives in `twine/inflight.py`**, next to `read_inflight`.
   The format's reader stays beside its writer, and the Arc 2 loop can call
   it without importing a verb module. `core.py` just renders what it gets
   back.
3. **What a bad name says.** There are three wordings, all
   `<name> is not an in-flight record: …`:
   - a name without `.json`: `its name is not <sid>.json`;
   - a `.json` whose stem `is_sid` refuses: `'<stem>' is not a session id
     twine accepts`;
   - twine's own atomic-write temp file (`.twine-<pid>-<ns>.tmp`, the shape
     of `kill._temp_name`): `it is the temp file of a record write still in
     progress, or of one that did not finish`. It is still a fault. The
     wording only tells the operator that it is twine's leftover and not
     someone else's junk. The regex copies `_temp_name`'s shape, which is a
     coupling (see Proposals). If `_temp_name` changes, such a file falls
     back to the generic wording and is still named, so nothing goes silent.
4. **An `inflight/` that cannot be listed** is a fault, not a pair of empty
   lists. `inflight` stays true because the directory is there,
   `inflight_sids` is `[]`, and `inflight_faults` is
   `["inflight/ cannot be listed: <strerror>"]`. Reporting true with `[]`
   and `[]` would read exactly like "no sessions in flight", which is the
   silent skip AGENT.md §6 calls a bug. There is no traceback, and status
   stays exit 0.

## 2. Other choices worth ratifying

- **Unprintable names are shown as their `repr`.** Without this, a real
  crash was possible. The twin is written with `ensure_ascii=False`, and
  `os.listdir` hands back non-UTF-8 bytes as lone surrogates. A file named
  `bad-\xff.json` in `inflight/` would therefore have made both modes raise
  on write, giving exit 2. A newline in a name would also have split a human
  line. `_shown()` prints a name as it is when `str.isprintable()`, and as
  its `repr` otherwise. A subprocess test pins both cases.
- **A dangling link or vanished file is a fault.** `read_inflight` returns
  `None` on `FileNotFoundError`, which means "no record". Taking that at
  face value would have dropped a dangling `<sid>.json` symlink without a
  word. The fault reads: `cannot be read: it was listed but no file is there
  now (a dangling link, or removed while it was read)`.
- **No `flock` on the read.** `carry bundle` replaces records atomically, so
  a reader sees whole records. Taking the lock writes nothing, but it would
  make `status` block behind a desk mid-write.
- **The brief's `not-a-sid.json` is a sid.** `is_sid` accepts `not-a-sid`
  under the regex `[A-Za-z0-9][A-Za-z0-9._-]*`. So the junk test uses
  `not a sid.json` (with spaces), and the module test uses `-x.json`. A
  `not-a-sid.json` holding `{}` would still be a fault, through
  `read_inflight` ("lacks sid, …").
- **Ordering.** `inflight_sids` is sorted by sid, not by file name: `a`
  comes before `a-b`, while `a.json` sorts after `a-b.json`. A test pins
  this. `inflight_faults` is in file-name order.
- **Test placement.** The new status tests are a sibling class,
  `InflightRecords`, in `tests/test_status.py`. They are not inside
  `StateDirectory`, which the brief named as their home. The new class
  needs its own fixture (a `state/` under the temp dir) and helpers. I
  extended `StateDirectory`'s existing tests wherever they pinned four
  members. If you want them in one class, folding them in is mechanical.
- `state_present`'s order is pinned literally:
  `("spend_jsonl", "prices_toml", "abort", "running", "inflight")`. The
  seven state keys' order in the twin is pinned too.

## 3. Every test that moved, by name

`tests/test_status.py`. `STATE_KEYS` grows to seven, `PRESENT_KEYS` to
five, and there are new `record()` and `snapshot()` helpers.
- `StateDirectory.test_none_resolves_in_an_empty_environment_and_is_never_silent`
  now also expects `inflight_sids` and `inflight_faults` to be null.
- `StateDirectory.test_the_flag_names_a_directory_with_some_of_the_four_present`
  is renamed `…_five_present`. It now expects `inflight` false and both
  lists `[]`, and the human `(missing: …)` list now ends in `inflight/`. Its
  all-present half makes `inflight/` too.
- `StateDirectory.test_a_directory_that_does_not_exist_is_reported_and_never_created`
  expects five falses and `[]`/`[]` for both the missing directory and the
  one that is a file.
- `StateDirectory.test_the_state_keys_ride_on_the_unusable_manifest_path_too`
  now writes a record. It asserts that all seven keys are present on that
  path and that the record is read there.
- New, `InflightRecords`:
  - `test_the_order_of_state_presents_keys_is_pinned`
  - `test_a_record_is_read_and_its_sid_listed`
  - `test_the_sids_are_sorted_by_sid`
  - `test_no_inflight_directory_and_inflight_as_a_file`
  - `test_an_empty_inflight_directory_is_present_with_nothing_in_it`
  - `test_no_state_directory_resolves_both_keys_null`
  - `test_files_that_are_not_records_are_each_named_and_the_record_still_reads`
  - `test_a_record_whose_sid_is_another_is_a_fault_not_a_sid`
  - `test_a_record_that_is_not_json_and_one_that_is_a_directory`
  - `test_a_dangling_link_is_named_not_skipped`
  - `test_a_write_left_unfinished_is_named_as_twines_temp_file`
  - `test_names_that_cannot_be_printed_are_shown_as_their_repr_and_never_a_traceback`
  - `test_an_inflight_directory_that_cannot_be_listed_is_one_fault` (mocks
    `os.listdir` for that one path, so it runs as root too)
  - `test_an_inflight_directory_without_read_permission_is_one_fault`
    (skipped as root)
  - `test_status_creates_and_writes_nothing_with_or_without_inflight`
    (snapshots mode, mtime and sha256 of every path, before and after, in
    both modes and as a subprocess)
  - `test_the_subprocess_twin_carries_the_record`

`tests/test_carry_bundle.py`, `TheRecordModule` (all new):
`test_list_inflight_with_no_inflight_directory_is_empty_and_creates_nothing`,
`test_list_inflight_reads_every_record_and_sorts_by_sid`,
`test_list_inflight_names_each_entry_that_is_not_a_record_by_its_basename`,
`test_list_inflight_faults_are_read_inflights_own_words`.

`tests/test_json_discipline.py` did not move. Its `status` case runs the
verb with no `--state-dir` and checks only the one-line, `command`/`ok`
envelope. It never fixes `status`'s key set.

Every record a test reads is written through `inflight.record_open`, as
the brief asked. Hand-written files appear only where a test needs
something that is *not* a record.

## 4. validation.sh, and what it can and cannot tell

I ran it twice, as §7.2 asks:
- **With the change** (staged copy plus `.bale-manifest.json`): everything
  passed, the suite ran 556 tests, and every claim agreed.
- **On the unmodified tree**: these failed: every end-to-end case (record,
  none, unresolvable, junk), the human sid line, the `VERSION` cmp, and all
  five contract assertions. The suite (536), the untouched set, the
  no-`__pycache__` check, and the creates-nothing tree diff passed. Those
  four are constraint guards, true before and after, which is the point of
  them.

What the script cannot pin:
- `twine-seed.md` and any fixture file the request did not ship have no
  sha256 the worker can know. The 42 shipped files (fixtures, `share/`,
  `bin/twine`, the three named modules, `INDEX.md`,
  `test_json_discipline.py`) are pinned by hash. Beyond that, the script
  reads `.bale-manifest.json` and fails if `changes[]` names
  `twine-seed.md` or anything under `fixtures/` or `share/`. Outside
  staging, that check prints a `[SKIP]` with the reason.
- I ran in this container as root, so the two mode-bit tests skip there:
  the 5c one and my unreadable-`inflight/` one. I ran both as `nobody` on a
  copy of the tree, and both pass.
- Every Python run is `python3 -I -B`, with `PYTHONDONTWRITEBYTECODE=1` and
  `TMPDIR` pointing under `.validation-logs/<ts>/`. The `__pycache__` sweep
  prunes `claude/checkpoints/` without reading it.

**`claude/INDEX.md`, untouched.** Its state-directory bullet still says
`twine status` "reports which state directory twine resolves and what of it
exists (§4)", which is still true and now covers more. "Pull when a session
… opens, tracks or closes a session twine carried in" is also still true.
The explainer's `status` clause ("its keys, and since session 5c the state
directory it resolves") makes no claim that became false. None of its
sentences says that nothing reads the record.

I reviewed the two request-carried tools before running them: their
imports, every write site, and the modes I used (`--write`,
`--validation-epilogue`, `--emit-feedback-mechanical`). Both are stdlib
only, with no subprocess and no network, and they write only into the
response directory. I did not read all 5,800 lines.

`model_identity` is the session's configured model id. The surface showed
the configured id, but not proof of which model served every turn.

## 5. The seed annotation (out of scope here; for the next tidy)

Place this at the end of `twine-seed.md` §5.1's road annotations, after the
last one there, verbatim:

> [2026-10-08-twine-status-inflight-004: `twine status` reads the in-flight
> records — `state_present` gains a fifth member, `inflight` (after
> `running`), and two keys ride beside it: `inflight_sids`, the sids whose
> `<state-dir>/inflight/<sid>.json` `read_inflight` accepts, sorted, and
> `inflight_faults`, one sentence per other entry in `inflight/`, naming it
> (both null when no state directory resolves). The reading is
> `twine.inflight.list_inflight`; it writes, creates and locks nothing, and
> `status` stays ok / exit 0 whatever `inflight/` holds. Nothing removes a
> record yet. `VERSION` 0.11.0.]

## Proposals

**What.** Export the temp-file name test from `twine/kill.py`, as an
`is_temp_name(name)` beside `_temp_name`, and have `inflight.list_inflight`
import it instead of copying its regex.
**Why.** `list_inflight` names `.twine-<pid>-<ns>.tmp` as "twine's own
unfinished write" by matching `_temp_name`'s shape, which it has to restate.
If the shape drifts, nothing goes silent (the file is still a fault), but
the friendlier wording would quietly stop appearing.
**Scope hints.** `twine/kill.py`, `twine/inflight.py`,
`tests/test_status.py`'s `test_a_write_left_unfinished_is_named_as_twines_temp_file`.
It is small enough to ride along with the next session that touches
`kill.py`.

**What.** Contract §8's sentence on which verbs touch temp state
directories in tests ("The spend verbs (§13), `kill` (§14) and `carry
bundle` (§15) read and write only temp state directories…") could name
`status` as a reader too.
**Why.** It isn't false today, since `status` only reads, but since 5c the
`status` tests build state directories as well, and a reader checking that
sentence for "what touches state in tests" would miss them.
**Scope hints.** `claude/context/cli-contract.md` §8, one clause. It could
go in the `twine-exchange-vouch` or `twine-pin-051` session, both of which
edit the contract anyway.

# notes.md — 2026-10-07-twine-kill-reason-002 (the hand line keyed on `reason`)

`twine kill` now hands back `bale revert <sid>` because the line bale
printed says `outcome` `unlock-refused` and `reason` `hold-branch`, and for
no other reason. The text match is gone, the tests replay no derived stderr,
and the prose that said otherwise moved. Eight files change, all modified,
all inside the forecast. `README.md` and `claude/INDEX.md` are untouched:
neither has a sentence about the mechanism. README's "for a session that
reached HOLD, bale's own `bale revert <sid>`" is still true. `VERSION` is
0.8.1. The suite went from 449 to 455 tests, green on 3.13 as root (the two
skips are the same two as at 0.8.0). No network was used, and no bale was
run except a stub.

I checked the desk's reproduction both ways with `bin/twine` against a stub
that prints the recorded HOLD line, exits 1 and writes nothing on stderr.
The 0.8.0 tree I was given gives exactly what brief §3 quotes:
`operator_line` `bale unlock 2026-10-07-sc-002 --reason aborted`. The 0.8.1
tree gives `bale revert 2026-10-07-sc-002`, and its `reason` ends with the
HOLD sentence. That run is now in the suite
(`test_a_stub_printing_the_hold_line_with_nothing_on_stderr_hands_back_revert`)
and in `validation.sh`.

The seam held (brief §6): nothing under `twine/commands/` reads
`hold_branch` or `HOLD_BRANCH_REFUSAL`. `twine/commands/kill.py` reads only
`closure.stderr` to pass it through, and that code is unchanged.

## 1. The three decisions brief §7 left to me

**Where the code goes in the failure text.** It goes in the outcome
entry, beside the outcome: `bale reported outcome 'unlock-refused'
(reason 'hold-branch'), not 'unlocked'`. The not-open refusal reads the
same way with `(reason 'not-open')`. The code is added only when the
outcome differs from `unlocked` and the line carries a non-null `reason`.
That way a close that is otherwise ok can never gain a failure: no ok-ness
changes, as §2.3 asks. The HOLD problem sentence now reads `bale refused
because the session reached HOLD (reason 'hold-branch'); its remedy, …`.
Both the twin's `reason` and the human `closure:` line carry
`hold-branch`. The tests assert both.

For the record, here is the HOLD refusal's full `reason` now:
`bale exited 1 with nothing on stderr; bale reported outcome
'unlock-refused' (reason 'hold-branch'), not 'unlocked'; bale reported
closure_reason None, not 'aborted'; bale refused because the session
reached HOLD (reason 'hold-branch'); its remedy, `bale revert
2026-10-07-sc-002`, touches git and is the operator's — twine never runs
it`. The code appears twice: once as what bale said, once in why the hand
line is revert. I kept both because they answer different questions. If
the repetition reads badly, the HOLD sentence can drop its parenthesis
without changing what §2.2 requires (the outcome entry already names it).

**`HOLD_REFUSAL` in `tests/test_kill.py`: dropped.** Its one use was the
stderr passthrough assertion. That assertion now feeds `NOT_BALES_STDERR`,
a constant the file names as bytes bale never printed. A second constant,
`HOLD_TEXT_NOT_BALES`, carries `branch bale/<sid> exists` labelled as
written by the test. It is used only to prove the text no longer sets the
hand line.

**`_read_unlock_line`'s not-JSON branch.** The logic is unchanged. The
docstring now says a refusal is a line like any other, read and named,
and that the empty stdout beside a non-zero exit is "a bale that stopped
before writing one — not the refusal". The exit entry already says bale
failed, so nothing more is said there.

## 2. Other choices worth ratifying

- **The exit entry still quotes stderr.** `bale exited 1: <last stderr
  line>`, or `… with nothing on stderr`. I read that as reporting, not a
  decision. §2.1 says stderr is "evidence, not a key", and §4 expects
  "the exit entry reads as twine words an empty stderr". I renamed the
  local from `refusal` to `said` and added a comment, because the old name
  implied the stderr was the refusal.
- **`hold_branch` does not check the line's `sid`.** The brief says
  "exactly when … `outcome` … and `reason`", so I matched that literally.
  A line with another sid still gets the sid failure, so the closure is
  not ok either way.
- **New constants in `twine/kill.py`:** `UNLOCK_REFUSED_OUTCOME` and
  `HOLD_BRANCH_REASON`. They sit where `HOLD_BRANCH_REFUSAL` was, under a
  comment that names the fixture and the closed reason set.
  `tests/helpers.py` already had `UNLOCK_REFUSED`; `test_kill.py` now
  imports and uses it, so it is no longer dead.
- **A guard test I added** (`Guards.test_no_decision_in_the_kill_module_reads_bales_stderr_text`).
  It walks `twine/kill.py`'s AST and fails on any comparison, `if`/`while`
  test or text-matching call that touches a `stderr`, or any string
  constant holding `branch bale/`. It is a heuristic, not a proof: it
  catches the 0.8.0 shape (`… in self.stderr`) and the obvious ways back,
  not every possible one. It would also catch someone adding an `if
  closure.stderr:` branch to `kill.py`. The verb's passthrough check is in
  `twine/commands/kill.py`, which the guard does not scan.
- **`share/bale-consumption.toml`'s unlock `stdout` value still says
  "beside `[bale] error: <message>` on stderr".** The brief limits this
  file's edit to the `note`, and that sentence describes bale's output as
  the probes showed it, not twine's key. Once the stderr-recording probe
  lands, it is worth checking that sentence against real bytes. In §14.5
  of the contract I worded the same fact as "bale's error text on stderr
  (the probes show it; no row records it byte-exact)", so the contract no
  longer quotes an unrecorded string.

## 3. Every test that moved, by name

`tests/test_kill.py`:
- Module docstring: a paragraph for this session. The comment above `HOLD`
  now names the code and says the stderr is empty. `HOLD_REFUSAL` is
  gone. New: `NOT_BALES_STDERR`, `HOLD_TEXT_NOT_BALES`,
  `unlock_refusal_reasons()` (reads the unlock surface's `reasons` from
  the consumption manifest, not a restated list) and `hold_line_with(**changes)`
  (the HOLD line with keys replaced, labelled as bytes bale never printed).
- `test_a_refusal_is_not_ok_names_bales_reason_and_is_never_retried`: the
  first failure is now `bale exited 1 with nothing on stderr`, and the
  outcome entry names `not-open`. Also asserts `stderr == ""` and
  `hold_branch` false.
- `test_the_hold_branch_refusal_hands_back_bales_own_remedy`: `hold_branch`
  from the line with the recording's empty stderr; the exact failures,
  which name `hold-branch`; `bale revert`.
- New `test_the_hold_text_on_stderr_without_the_code_is_not_hold_branch`:
  the HOLD line with its `reason` swapped for each of the other four codes,
  plus the HOLD text on stderr. No `hold_branch`, the unlock line, and the
  stderr still quoted in the exit entry.
- New `test_the_hold_code_with_nothing_on_stderr_is_hold_branch`: the HOLD
  line with `b""` and with an unrelated stderr sets it either way.
- New `test_hold_branch_wants_both_the_outcome_and_the_reason_from_a_line`:
  false on timeout, empty stdout, non-JSON stdout (each with the HOLD text
  on stderr), `outcome` `no-op`, `reason` null, and `reason` set to the
  message text.
- `test_a_refused_closure_says_where_it_stopped`: `as_json()["stderr"]` is
  `""` (and `stderr_truncated` false). `reason` carries both `hold-branch`
  mentions.
- New `test_a_refusal_with_another_code_names_it_and_hands_back_the_unlock_line`
  (`KillSession`, the not-open line through `kill_session`).
- `test_human_mode_names_each_step_and_the_hand_line`: the HOLD run feeds
  `NOT_BALES_STDERR` through the override and asserts it reaches twine's
  stderr. The `closure:` line names `hold-branch`. A second run with empty
  stderr gives the same hand line and no "bale's stderr follows".
- `KillEndToEnd` docstring, and
  `test_a_refusing_stub_is_not_ok_and_shows_bales_stderr`: the stub's
  `stderr=` is `NOT_BALES_STDERR`, asserted equal in `obj["stderr"]` and
  present in the process's stderr. The reason names `not-open`.
- New `test_a_stub_printing_the_hold_line_with_nothing_on_stderr_hands_back_revert`:
  the desk's reproduction as a subprocess.
- New `Guards.test_no_decision_in_the_kill_module_reads_bales_stderr_text`
  (see §2).

`tests/helpers.py`: the module docstring gains this session. `Recording`'s
docstring says its stderr is always empty. `unlock_recording` returns
`b""` for every recording; the derivation and its paragraph are gone, and
`[bale] error:` appears nowhere in the file. `RecordedUnlock` takes
`stderr: bytes | None = None` (bytes that are not bale's), also used on the
`timed_out` path. Its "answers … with a RECORDING's bytes" sentence is
still true. `Recording`, `UNLOCK_RECORDINGS`, `StubBale` and the other
parameters keep their names and shapes.

`tests/test_consumption_manifest.py`:
`test_the_unlock_refusal_line_is_what_the_entry_says` asserts `rec.stderr
== b""` (the docstring says why). Nothing else in the file moved.

No assertion was dropped without a true replacement. Every assertion that
rested on a derived stderr now asserts the empty stderr, a named non-bale
stderr, or the code.

## 4. validation.sh, and what it can and cannot tell

Ten checks. The script writes only under `.validation-logs/<ts>/`; it
points `TMPDIR` at a `tmp/` there for the suite and the stub run, and runs
`python3 -I -B`. I ran it twice in a staging copy (the tree I was given,
plus `files/`, plus `apply.sh`). On the changed tree, all ten pass. On the
unmodified tree, six of the session checks fail as they should. The suite,
the twin-keys check and the untouched-set check pass on both. That is by
design: they guard constraints that say "unchanged", so they cannot fail
on the old tree. I list them so the pattern isn't misread as a weak
assertion. The claims are `observed` (from those runs), not predicted.

The untouched-set hashes were computed from the tree the request carried.
They match the two values the brief gives (`twine-seed.md`, `bin/twine`).
The fixtures check also asserts the file counts (23 and 10), so an added
file fails too. Two prose-only edits are pinned beyond sha256 of the
untouched set:
- `fixtures/README.md`'s 48 table rows, hashed.
- The whole consumption manifest, hashed as parsed data with only the
  unlock surface's `note` set aside.

The script reads nothing under `claude/checkpoints/`.

## 5. The seed annotation (out of scope here; for the next tidy)

At the end of D15's annotations (after the
2026-10-06-twine-clear-group-003 one), verbatim:

> [2026-10-07-twine-kill-reason-002: landed — `twine kill`'s hand line
> keys on the recorded refusal's reason code, not on bale's stderr: `bale
> revert <sid>` exactly when the unlock line twine read says `outcome`
> `unlock-refused` and `reason` `hold-branch`, the unlock line for any
> other reason or none, and the failures name the code. Twine reads no
> stderr text (it is still reported and passed through), the tests replay
> no stderr derived from a recording, and `VERSION` is 0.8.1. The
> `[[wanted]]` reason-coded refusal session 5c asked bale-src for is now
> what the kill decides on.]

The pin bump's own D2 annotation ends "`twine kill` still reads the HOLD
refusal by its stderr prefix until `twine-kill-reason` keys it on the
recorded `reason` code". If both annotations land in the same tidy, that
clause can stay as history, since the line above says it happened.

## Proposals

**What.** Once the stderr-recording probe lands, check the unlock
surface's `stdout` sentence in `share/bale-consumption.toml` ("beside
`[bale] error: <message>` on stderr") against the recorded bytes. Then
give `Recording` a stderr read from a row instead of `b""`.
**Why.** This session left that sentence alone (the brief limited the
file to the `note`). It is the last place in the tree that quotes a stderr
string no row records.
**Scope hints.** `share/bale-consumption.toml`, `fixtures/README.md`'s row
shape, `tests/helpers.py` `unlock_recording`. Only after the probe, which
the brief already queues with the desk's next recording probe.

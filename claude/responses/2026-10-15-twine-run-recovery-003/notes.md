# Notes — 2026-10-15-twine-run-recovery-003

Session `twine-run-recovery`, the hardening wave's second. All eleven
outcomes are in; the suite is 1249 tests (the base 1209 and 40 new), green
under `python3 -I -B -m unittest discover -s tests -t .`, and `validation.sh`
passes on a staging copy of the tree (about two minutes, dominated by the
suite). I did not see the blind checkpoint. Everything below that says
"flagged" is a choice I made where the brief left it to me, or a small
departure the brief did not foresee.

## Forecast departures (one path)

- **`twine/recovery.py`** — new file, outside `resolved_scope`. The shared
  reading (the transcript's last `run-end` twin, window and last tools; the
  spend priced as `spend totals --sid` prices it; the suggested cap; the
  `--cap +USD` parser; the `next` lines and bale's admit line) is needed by
  `twine run` *and* `twine resume`, and `commands/resume.py` already imports
  `commands/run.py`, so it could not live in `resume.py` without a cycle, and
  putting ~300 lines of money arithmetic into the verb module that also
  hosts the run report seemed worse than one new module. It writes nothing,
  spawns nothing and spells no stop key (the loop's constants are read from
  `twine.runtime.loop`). Its tests are in `tests/test_resume.py`
  (`TheRecoveryReading`, `ThePlan`, …), which is in scope; no new test file.

## What changed, by outcome

1. **The rule** is in `commands/resume.py`'s and `run.py`'s docstrings,
   runtime-contract §7.9 and §7.7's rows, cli-contract §18.4 and §19, and in
   the table: `fix-adapter`, `stop-at-cap` and `respawn-from-request` each
   name `twine resume` (their `grounds` carry this sid). `share/
   transitions.toml` changed only there and in the header's session
   sentence — which grew from a clause to a five-line sentence; I read "the
   header's session line" as that paragraph. `twine transitions --json`: ok,
   47 rows over 28 moves.
2. **`cap-reached` under the same cap** ends `cap-reached` before any call
   (`turns` 0, no new line in `spend.jsonl`); under a raised cap it makes the
   next call. Flagged, per your fourth decision: it is the **loop's first
   pre-call check**, as it fell out, not a refusal in the verb's list — the
   running record is written, the transcript gets its `run-start`, and the
   unsent answer lands in a `request` line with `sent: false`. What changed is
   the reason: `loop.refused_reason` says the cap is already spent and names
   the spend so far when spend ≥ cap (otherwise the old sentence). A
   consequence worth knowing: each such resume appends one more user turn to
   the conversation (the twin of any other `sent: false` tail).
3. **`killed` is refused** before anything starts, naming the `aborted`
   closure and `respawn-from-request`. Flagged addition: it also refuses when
   an abort request is still standing for the sid, not only when the last
   `run-end` says `killed` — a standing abort would end a resumed loop
   `killed` before its first call anyway, after having appended an answer.
4. **`--answer`** is optional except on `suspended` (decided by the
   transcript's last `run-end` outcome). Absent, the user message is
   `RESUME_TEXT` byte for byte (`twine/runtime/resume.py`; the `run-start`
   `answer` says `source: "twine"`). A run whose last run never ended
   (`run-start` with no `run-end`) counts as not suspended. `validation.sh`
   holds the constant to its bytes with `cmp`.
5. **`--plan`** — see "The plan" below.
6. **`--cap +USD`** on `resume` and `run`. On `run` the sid is only known
   after bale opens the session, so the cap is worked out right after the
   open (spend that cannot be priced is a refusal there, with the session
   open and the existing "nothing ran" sentence). `run-start` gains
   `cap_given`, the text as typed, beside `cap_usd` (new key, after
   `cap_usd`; nothing read it before).
7. **`next`** is the last name of the twin; human mode prints `[twine] next:
   <command>` lines after the summary. See "next" below.
8. **Raw files** are created exclusively; a name taken gives
   `<sid>.call-<N>-2.raw`, `-3`, … (flagged naming). The first run's file
   keeps its name, `list_transcripts` still counts none of them as a fault,
   and the `turn` line's `raw` names the file used. A name held by something
   that is not a regular file is still a named `raw_error`, not walked around.
9. **README**: the stop-set sentence (sixteen keys, four `loop_keys`; the
   fifteen/three history is kept inside it), the `run` bullet's window and
   `next` sentences, a new `resume` bullet carrying the rule, and two lines in
   "Running it". `VERSION` 0.25.0.
10. **Docs**: runtime-contract §5 (the raw name), §7.6 (rows for `run-start`,
    `turn`, `run-end`), §7.7, §7.9; cli-contract §18 heading/§18.1/§18.4/
    §18.5/§18.7, §19 heading/§19.1/§19.2/§19.4 (the plan's twin as a table)/
    §19.5/§19.6.
11. **Seed annotation** — below.

## The plan (decisions to ratify)

- `ok` is true when the sid, the state directory and a transcript that
  rebuilds as a conversation are all fine. A session that is **not**
  resumable but readable (delivered, home gone, killed) is `ok: true,
  resumable: false` with `why` — the plan could be read; exit 0. A transcript
  that cannot be rebuilt (torn, missing) is `ok: false`.
- `reason` is the last run's own reason when `ok`; the unreadable reason
  (same as `why`) when not.
- `suggested_cap_usd` is null when the session is not resumable or cannot be
  priced. **The rule**: spend so far + a re-warm of the window at the
  cache-write price (the last `window` line's `used`, or the input estimate
  when none) + 40 calls at the mean of the last ten + the next call's worst
  case, rounded up to the cent, and one cent more if that is not above
  `spend + worst`. With no calls yet the forty-call term is 0. The worst case
  is priced exactly as the resumed run's first pre-call check will price it:
  the rebuilt conversation plus `RESUME_TEXT`, estimated by `estimate_input_
  tokens`, at the dearest input-side price, `max_tokens` at the output price.
  A longer `--answer` on a suspended session makes the real first call
  dearer than the plan's; the re-warm and forty-call terms are the slack.
  The human line states the sum.
- `--plan` accepts and **ignores** `--cap`, `--answer`, `--script`,
  `--model`, `--max-tokens`, `--thinking` and `--window` (said on stderr),
  so a test bed or an operator can add `--plan` to a resume line they already
  have. It reads `--state-dir` and `--prices`.
- `last_tools[].what` is `loop.tool_argument` with a `limit` parameter (new,
  default 80) set to 110.
- For a refused delivery the admit line is read from the **last `run-end`
  twin** (`tarball`, `dry_run.drift`), not from the `move` line's
  `carry_response`; same facts, and `run` has them in hand without the
  transcript. A session whose last run never ended has none.
- A transcript with a **torn last line** (a run killed mid-write) still
  refuses to resume (`ResumeError`, unchanged); `--plan` reports it
  `ok: false`. See Proposals.

## `next`

- Resume line (`twine resume SID --cap <suggested>`, plus the `--state-dir`,
  `--bale-root` and `--cwd` the run was given): `cap-reached`,
  `cap-unchecked`, `ended`, and every `stopped` except the two below.
  Flagged: it also carries `--prices` when given (the suggestion was priced
  from it), and it does **not** carry `--script` — the plan cannot know the
  fake's script path, and the fake is the tests' adapter. When no cap can be
  suggested (unpriced model — i.e. `cap-unchecked` for want of a price row —
  or a transcript a resume cannot rebuild) the line is `twine resume SID
  --plan`, which says why; inside the plan itself that case is empty rather
  than a plan naming a plan.
- `scope-drift-refused`: `[admit line, resume line]`. The admit line is
  `bale apply <tarball> --allow-out-of-scope <path>` for each of the
  recorded `drift.out_of_scope_paths` (bale's own refusal prints one flag per
  path). **It is built with `bale.apply_line`**: `test_apply_is_built_in_one_
  place_only` pins the string "apply" as an argv token to `twine/bale.py`, and
  my first draft (a literal `["bale", "apply", …]`) failed it, rightly. Twine
  runs nothing; the human output says the departures are enumerated in the
  response's `notes.md` first.
- `killed`: empty, with the respawn path in words on stderr.
  `window-exhausted`: empty, with the split said in words. By the rule such a
  session *is* resumable (the plan says `resumable: true`), but a cold
  resume re-warms the same too-big conversation; the table's move is the
  planner's split and I left `next` empty as the brief says.
- `delivered`: `[apply line]`; `suspended`: `[apply line]` for the
  clarification form, and `twine resume SID --cap <suggested> --answer -` for a
  light block (the brief's `--answer -` line, with the `--cap` it needs to
  run). A `refused` run names nothing.

## Existing tests changed (so you can look at them first)

- `test_run.py`: `test_the_last_progress_line_is_the_summary` and
  `test_the_summary_names_the_stop_and_the_move_and_the_retries` — the summary
  is still the last *progress* line; the `next:` lines now follow it, so they
  read the summary at `summary_at(lines)` and assert only `next:`/no-command
  words come after. `test_the_transcript_writer`: "replaced, never appended"
  became "never overwritten".
- `test_resume.py`: `test_the_last_progress_line_of_a_resume_is_its_summary`
  likewise. The rest of the file is additive.

## Things I checked and did not change

- `fixtures/`, `share/bale-consumption.toml`, `twine-seed.md`, `bin/twine`
  are untouched (`validation.sh` compares 141 files by sha256, against the
  request's). `twine kill`'s closure is untouched. No stop key is spelled
  under `twine/runtime/` (`RESUME_TEXT` is a sentence; the new `loop` code
  reads the check's own `refusal`/`stop`).
- A resumed `cap-reached` run's conversation ends with a tool-result user
  turn and then the appended `RESUME_TEXT` user turn — two consecutive user
  messages. The Messages API merges adjacent same-role turns; I did not run it
  against the live API, and the tests use the fake.

## Seed annotation (for the next tidy; under §5.2, after ergonomics' bracket)

[2026-10-15-twine-run-recovery-003: recovery mechanized. The rule: a run
`twine run` or `twine resume` left `stopped`, `cap-reached`, `cap-unchecked`,
`ended` or `suspended` resumes with `twine resume`, in its kept home, from its
transcript; `respawn-from-request` is the last resort, for a home that is gone
or a session bale has closed. The table says it where the operator reads it —
the descriptions of `fix-adapter`, `stop-at-cap` and `respawn-from-request` each
name `twine resume`. `killed` is not resumed: `twine kill` closes the session in
bale as `aborted`, so no response a resumed worker delivered could be dry-run or
applied under that sid, and `twine resume` refuses it before anything starts,
naming the respawn path (a standing abort request is refused the same way). The
cap is cumulative per session: a `cap-reached` run resumed under the same cap
ends `cap-reached` again before any call (`turns` 0, no new spend line, the
reason saying the cap is spent and naming the spend so far), and under a higher
one makes its next call; `--cap +USD`, on `resume` and on `run` for a second
desk, is the session's spend so far plus that amount, the twin's `cap_usd` the
absolute cap and the `run-start` line's `cap_given` the text as typed.
`--answer` is required only on a `suspended` run; on any other resumable outcome
an absent answer is `RESUME_TEXT`, "This session was stopped and has been
resumed; continue from where you left off.", sent byte for byte with the
`run-start` `answer` saying `source: "twine"`. `twine resume SID --plan` reads
the session — its transcript, `spend.jsonl`, in-flight record and sandbox home —
and writes nothing, starts no bale and calls no model: whether it resumes and
why not, the last window, the calls, the spend priced as `spend totals --sid`
prices it, the mean of the last ten calls, the next call's worst case as the
cap check will price it, the last ten tool calls, the home's top-level names, a
suggested cap (strictly above the spend plus that worst case; the spend, a
re-warm of the window at the cache-write price, forty calls at the mean, and the
worst case, rounded up to the cent) and the `next` lines. Every ending of
`twine run` and `twine resume` names its next command — the twin's `next`, its
last name, and a `next: <command>` line per entry on stderr after the summary:
the resume line with the suggested cap for a stop a resume goes on from; for a
dry run bale refused `scope-drift-refused`, bale's own `--allow-out-of-scope`
admit line built from the line's `drift` — never run by twine (T12) — and the
resume line that returns the work to the worker; the apply line on `delivered`;
nothing on `killed` (the respawn is said in words) and on `window-exhausted`
(the planner's split). A resumed run's raw response files are created
exclusively and never overwrite the first run's: `<sid>.call-<N>-2.raw`, `-3`.
New: `twine/recovery.py`, the shared reading. `VERSION` 0.25.0.]

## Proposals

### A torn transcript is the one recovery a crash leaves

- **What**: let `twine resume` (and `--plan`) recover a session whose runtime
  died mid-write — a transcript whose last line has no LF, no `run-end` — by
  rebuilding from the last complete `request` line and saying what was lost.
- **Why**: the brief's rule is "every non-delivered outcome with a kept home",
  and a SIGKILLed run has no outcome at all; `read_conversation` refuses a torn
  last line by design ("the conversation may be missing its tail"), so the
  operator's only path is the hand-written one this session set out to remove.
  The plan already reports it (`ok: false`, the fault named).
- **Scope hints**: `twine/runtime/resume.py` (a refusal that is a warning when
  the torn line is the last and the `messages_total` chain holds up to it);
  needs a ruling on whether a torn tail is ever safe to drop.

### The clarification form's second step

- **What**: for a `suspended` run on escalate's clarification form, `next`
  names only the apply line; after the planner's answer is relayed the
  operator needs `twine resume SID --cap … --answer -`, which only `--plan`
  prints.
- **Why**: "every ending naming its next command" holds for the apply line,
  but the line after it is not on screen; naming both in order is a one-line
  change in `recovery.next_commands` if you want it (I kept the brief's
  "the apply line").
- **Scope hints**: `twine/recovery.py` `next_commands`; the two contract
  sentences; the tests that pin `next == [apply_line]`.

### `twine status` could name the resumable sessions

- **What**: `status` already lists the sids of in-flight records, transcripts
  and sandbox homes; it could name, per kept session, its last outcome and
  whether `--plan` says it resumes.
- **Why**: a second desk's first question is "what is there to resume"; the
  facts are now one function (`recovery.read_story`) away.
- **Scope hints**: `twine/commands/core.py`; the `status` twin's key set is
  pinned, so a new key is a contract change.

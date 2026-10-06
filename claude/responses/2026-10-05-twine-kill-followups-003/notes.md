# notes — 2026-10-05-twine-kill-followups-003 (the kill follow-ups, 5c)

## The session's work

All four items land; `VERSION` is 0.7.0. Fifteen files changed, every one inside the write
forecast (`twine/`, `tests/`, `share/bale-consumption.toml`, `claude/context/cli-contract.md`,
`claude/INDEX.md`, `README.md`, `VERSION`), so there are no departures. `bin/twine`, `fixtures/`,
`twine-seed.md`, `bale.toml` and `share/transitions.toml` are untouched and `validation.sh` checks
each by hash; the table stays total at 44 rows, 13 stop keys. The suite grows from 381 to 416 tests
and is green on Python 3.11, 3.12 and 3.13, as root and as an unprivileged user. **No real
`bale unlock` ran anywhere**: not in the suite, not in `validation.sh`, not by hand. Every unlock
answer is a double built from `format_unlock_json`'s key contract and named as one; the stub bale
`validation.sh` writes says so in its second line. No probe was needed; the brief was right that
every bale fact is in the tree.

1. **The pin gates the closure alone** (`twine/commands/kill.py`). The verb still locates bale
   first so the `bale` object reports what was found on every path, but it calls
   `bale.locate_executable` directly now rather than `carry_bale.locate`, whose whole job is to
   append the drive refusal to `refusals`. Nothing else changed in the verb: `close_aborted`
   already refused an unpinned executable without starting it, so an unpinned or absent bale ends
   `stopped_at: "closure"`, `closed: false`, exit 1, the drive refusal in `reason`, the unlock line
   as `operator_line`, and human mode `NOT FINISHED (stopped at closure)`. The one line of stderr I
   added says, before the steps run, that the closure will not land and why. 5b's notes offered the
   other shape ("move `locate` after `kill_session`'s first two steps"); I did not take it, because
   locating first is what keeps `bale` reported on the refused path too, which the brief asks for.
   The old `test_the_pin_gate_comes_before_the_abort` is gone; three tests replace it (another
   pin, an absent `bin/VERSION`, a root that does not exist — each writes the abort, kills a real
   group, never reaches bale; and a pinned bale closes as before).
2. **The record carries `groups`, the seam has a hook, the kill takes every group**
   (`twine/kill.py`, `twine/process.py`, `tests/helpers.py`). The record is the brief's six keys
   to the byte, in that order; `register_group` is the function the brief names, with its
   signature; `read_running` requires every key and names every fault, the brief's four and the
   rest (a missing entry key, an entry that is not an object, a non-array). The hook is `on_spawn`
   on `run_process` and on the `Runner` protocol, called right after `Popen` and before the stdin
   feeder and the collector — a test spies on both and asserts the order, not just the effect. The
   kill is restructured around one primitive, `kill_one_group(pgid, leader_start_ticks)`, which is
   5b's `kill_group` body unchanged; `kill_group(record)` runs it on the runtime's group and then
   on each of `record.groups` (`kill_more`), and `kill_session` re-reads once
   (`_kill_registered_since`) before it clears the record. `ProcessStep` keeps 5b's keys for the
   runtime's group and gains `groups`; `dead`, `survivors`, `error` and the hand line are the
   whole's. The twin's `process.groups` entries carry exactly the six keys the brief lists. Human
   mode prints one line per group and a `N groups in all:` line when there is more than one.
3. **`twine status` reports where state lives** (`twine/commands/core.py`): the five keys, pinned
   as the brief pins them, `--state-dir`, `ok` untouched, nothing created, two human lines (`state
   dir:` and `state present:`, or `state dir: none resolves — <reason>`). The keys ride on the
   unusable-manifest path too, computed before the manifest is loaded.
4. **The `[[wanted]]` entry** is the third in `share/bale-consumption.toml`, in the shape of the
   two before it; `test_the_unlock_json_refusal_is_wanted` asserts it beside the existing walk.

Docs: contract §4 (the rows, `--state-dir`, the one-line human forms), §10.6 (the hook; also
`group_survivors` in the `RunResult` signature, which 5b added to the prose but not to the block),
§14's opening, §14.1 (the pin paragraph replaces the last bullet; the sentence "The pin is checked
before the abort is requested" is gone from the tree), §14.2 (every group, the re-read, the hand
line row), §14.4 (rewritten: the six-key table, `register_group`, the groups' faults, runtime-first,
"What `dead` covers, and what it does not" replaces "One group, not every group" and the closing
sentence the brief names), §14.6, §14.8 and the header. `README.md`'s verb list, run lines and kill
paragraph; `claude/INDEX.md`'s record and contract lines; the module docstrings of `twine/kill.py`,
`twine/process.py`, `twine/commands/kill.py`, `twine/commands/core.py` and the package.

## Decisions to ratify

- **`register_group` takes an exclusive `flock` on the `running/` directory** around its
  read-append-replace. The brief says "rewrites the record durably, the way `register_running`
  writes it", and it does; the lock is on top. The independent review (below) ran twenty
  registrations at once without it and 3 of 20 landed — the next `twine kill` reported `ok` and
  left 51 pids running, which is precisely the mystery D15 forbids. Locking the directory rather
  than a lock file keeps `running/` holding records and nothing else (a test asserts no other file
  appears). Where `fcntl` is missing the call proceeds unlocked and logs it. The contract says so
  in §14.4. If you would rather hold the loop to "one child at a time" and keep the record writer
  lock-free, it is one function to revert.
- **When the runtime's recorded group is twine kill's own, the groups after it are not signalled
  either.** 5b's contract said "the step stops" and the first draft of the loop went on to the
  other groups anyway; the reviewer caught the disagreement. I kept the contract's word: the
  runtime that could start more is not stopped, so the run from another shell takes them all.
  The hand line then names the runtime's group only (`alive_groups` is what was not killed).
- **The one re-read also kills a runtime that re-registered under a new pgid.** The brief names
  "any group registered since"; a runtime whose `pgid` changed between the two reads is, to the
  kill, one more group it did not know. It is treated as such and appears in `process.groups`.
- **A record that becomes malformed on the re-read stops the process step** (`dead` false,
  `operator_line` null, the record left in place, the reason saying a group registered meanwhile
  may be unknown). One that is gone on the re-read is nothing more to do; `record_cleared` reads
  false then, because someone else cleared it. Both are tested.
- **A pgid the record names twice, or that equals the runtime's, is signalled once and reported
  once.** By the second time its number could lead a stranger's group.
- **The reader tolerates keys the format does not name**, on the record and on an entry, as 5b's
  did; "exactly these six keys" binds what twine writes and which keys the reader requires. A
  stricter reader is one line if you want it.
- **`twine status --state-dir ' '`** reports `state_dir: null` with spend's `bad-argument` text as
  `state_dir_reason` rather than refusing: `status` is read-only and `ok` stays about twine.
- **An unreadable state directory is a named refusal of `twine kill`, and reads as absent to
  `status`.** Not in the brief: the review found `Path.is_dir()` raising `PermissionError` when a
  parent lacks search permission, which was a traceback (exit 2) in both verbs. `kill` now says
  `cannot be read (Permission denied)` and does nothing; `status` reports `state_dir_exists`
  false. The suite runs as root in bale's sandbox, where mode bits do not bite, so the two tests
  that make a directory unreadable skip under root and ran green here as `nobody`; the `kill`
  test also unit-tests `state_dir_fault` with a patched `os.stat`, which runs everywhere.
- **`model_identity`** is `anthropic:claude-fable-5-1`, the session's configured model; the
  serving model can differ and I cannot see a picker.

## The hand line

`kill -KILL -- -<pgid> -<pgid> …` names every group not known to be gone — survivors, no `/proc`,
twine kill's own — the runtime's first, then record order, which is the same set 5b's table named
for one group. A record whose runtime group is gone but one tool still lives hands out that tool's
pgid alone. Tested in `test_the_hand_line_names_every_group_with_survivors`.

## What I noticed in the existing code

- A tool that finished leaves its entry in `groups`: nothing removes one when a run returns. The
  kill copes (nothing alive, nothing signalled, `dead` true; a reused number is caught by its
  leader's ticks or, when the reuse is not a group leader, by `group_members` finding no member),
  so a long session's record grows by one entry per tool and stays correct. The first Proposal
  below is the tidy.
- The verbs' `--state-dir` help text is now written three times (`spend`, `kill`, `status`) with
  three different second halves; each says what its verb does with the directory, so I left them.

## An independent check

Before packing, a separate agent that had not seen the work reviewed the diff against the brief,
ran the suite and the CLI in a scratch copy, and tried to break the code. It confirmed every pinned
outcome and found:

- the `PermissionError` traceback in `status` and `kill` (fixed, above);
- the lost registrations under concurrency (the lock, above);
- the own-group disagreement between contract and loop (fixed, above);
- a hook-ordering test that did not test the order (it spies on the feeder and the collector now);
- a group entry missing `leader_start_ticks` reading as null (every entry key is required now);
- a duplicated pgid dropped from the twin without a word (the contract says "reported once");
- a stale docstring and an unbound local in a test helper (fixed).

Nothing it found blocked a pinned outcome. All of it is fixed, each with a test where a test
applies.

## Validation

`validation.sh` has 12 checks and the claims block. Every Python in it runs under `-B`, the crafted
epilogue included (its `python3 -` became `python3 -B -`, noted in the paste). It announces its two
write locations first (`.validation-logs/<stamp>/` under the staging root and one temp directory
under `$TMPDIR`, removed at exit), writes nowhere else, never walks `claude/checkpoints/` or
`claude/responses/`, and never reads itself. It ran twice (TARBALL.md §7.2):

- **On a staged tree** built as bale stages it — base plus `files/`, `apply.sh` run, the manifest at
  `.bale-manifest.json`, a stand-in checkpoint at `claude/checkpoints/<sid>.sh` that nothing reads.
  Exit 0, all 12 `[PASS]`, the one claim `[agree]`; about 40 s, most of it the suite. The staged tree
  afterwards held nothing new but the logs and no `__pycache__`.
- **On the unmodified base.** Exit 1: the eight session assertions `[FAIL]` by name (the version,
  the record and the hook, the end-to-end kill, the pin gate, status, the wanted entry, the docs,
  the registry) and the four others pass on both trees (syntax, the suite, the untouched hashes, no
  bytecode).

The end-to-end check starts three real `setsid`-led groups (one ignoring SIGTERM), registers them
as the runtime and the hook would, runs the real entrypoint under `-I -S -B` with an empty
environment against a temp state directory and a stub bale root, and asserts every one of the nine
pids dead (polled), the record cleared, the abort present, `process.groups` with the two tools'
signal lists, and the stub's argv exactly `unlock <sid> --reason aborted --json` in `--cwd`. A second
stub at 0.4.46 proves the pin: abort written, group dead, the stub never started, stopped at the
closure. The first draft of that check captured the group starters' stdout through a pipe the
sleeps inherited, so the capture waited on the sleeps and the kill found dead groups; the starters
write pids to files now, and the signal-list assertions are what prove the groups were alive.

The `claims` block has one claim, the suite: `pass`, observed. The session assertions are listed and
not claimed, because a project-level check exists (TARBALL.md §5.3).

## Proposals

### Seed annotations for this session, for the next seed tidy

**What.** Two texts for `twine-seed.md`, verbatim-ready. Beneath D15, after the kill-switch-002
annotation:

> [2026-10-05-twine-kill-followups-003: landed — the kill's follow-ups. The pin gates the closure
> alone (the sitting's correction to 5b, on the worker's reading of D15): the abort and the
> process kill run with any bale or none, and an unpinned bale stops the kill at the closure with
> the unlock line. The running record carries `groups` — exactly six keys, one entry per group the
> runtime registers through the run seam's `on_spawn` hook (`twine.kill.register_group`, the moment
> a tool exists, under a lock) — and `twine kill` signals every one of them, the runtime's first,
> re-reads the record once for a group registered meanwhile, and is done only when no member of any
> is alive; `dead` is the record's whole. Two residuals, named in contract §14.4: pid reuse past a
> full wrap, and the window between a child's `Popen` and its hook's write in a runtime that is
> itself SIGKILLed. `twine status` reports which state directory twine resolves and what of it
> exists. The `[[wanted]]` entry asks bale-src for a JSON unlock refusal with a reason code;
> twine keys the `bale revert` hand line on the stderr text until then.]

On the §5.1 road, after the row5-001 annotation:

> [2026-10-05-twine-kill-followups-003: the kill follow-ups landed (`VERSION` 0.7.0): the pin
> gate moved to the closure, the running record's `groups` and the seam's spawn hook, `twine
> status`'s state directory, the unlock `[[wanted]]`. Arc 2's loop composes the hook with the
> record (`on_spawn=lambda pid: register_group(state_dir, sid, pid)`) and may now run a tool.]

**Why.** `twine-seed.md` is out of scope by name (brief §6); the texts are the seed's to carry.

**Scope hints.** `twine-seed.md` only, in the next seed tidy.

### Let the loop forget a group once its run returns

**What.** A `clear_group(state_dir, sid, pgid)` (or `unregister_group`) beside `register_group`,
under the same lock, that removes one entry — called by the Arc 2 loop after `run_process`
returns, since the seam guarantees the group is gone or its survivors are named.

**Why.** Today an entry stays until the record is cleared, so a long session's record grows by one
entry per tool. The kill handles the stale entries correctly (nothing alive, nothing signalled),
but a kill that signals four hundred dead numbers before it reaches the live one is slower than it
needs to be, and the pid-reuse residual's odds grow with the number of stale entries. Keeping the
record to what is alive is the tidy. Not this session's: nothing composes the hook with the record
yet.

**Scope hints.** `twine/kill.py`, contract §14.4 and §14.8, `tests/test_kill.py`; before or with
the Arc 2 loop's brief.

### Arc 2's loop: where the hook goes and what to do when it raises

**What.** When the loop's brief is written: the hook is passed on every `run` the loop makes (a
tool, bale through the seam alike); a hook that raises `RunningRecordError` (no record — the loop
forgot to register itself; a malformed record) is the seam killing that child and the exception
reaching the loop, which should stop `killed`-adjacent rather than retry; and the loop registers
itself with `register_running` once, before its first call, never again (a second call forgets the
groups).

**Why.** All three are what the code does now; writing them into the loop's brief keeps the
loop from relearning them. The exemption in the carry-forward's fourth bullet (the loop's own
closure while it is the last member of its group) belongs beside them.

**Scope hints.** The Arc 2 sitting's brief for the loop; no twine-src file.

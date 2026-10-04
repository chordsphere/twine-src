# notes — 2026-10-04-twine-kill-switch-002 (Arc 1 road 5b, the kill-switch)

## Re-attempt after the HOLD

This response corrects this session's first one (`corrects` names it). The HOLD named one fault of
mine: `tests/test_process.py` `test_a_member_with_its_pipes_closed_dies_with_the_run` asserted a
killed `sleep` was dead with one `process_alive` check, where brief §7 asks tests that kill processes
to poll (`dies_within`). That is exactly cost-spine-005's race: a SIGKILLed process closes its
descriptors before the kernel marks it a zombie, so one check right after the run can catch it in
the gap. It now polls for up to 3 s. A sleep the runner never killed would still be alive after 3 s
and still fail the test, so the test still catches the bug it was written for.

The same single check was in five other places I wrote, and §7 binds all of them, so they poll too:

- `test_process.py` `test_the_run_returns_only_once_its_group_is_gone` (it still asserts the
  runner's own guarantee, `group_survivors == ()`, directly);
- four post-kill checks in `tests/test_kill.py`;
- the end-to-end check in `validation.sh`.

The stale-record test's check that the processes are still *alive* stays single: nothing races
there. No code under `twine/` changed. Only `tests/test_process.py`, `tests/test_kill.py` and
`validation.sh` differ from the first response.

Ratified at the desk and unchanged here: the running record carries `sid` beside `pgid`, `pid` and
`started_at`, and a record whose `sid` is missing or differs is malformed (`read_running`; tested in
`test_a_malformed_record_is_named_never_guessed`).

`validation.sh` was re-run twice (TARBALL.md §7.2):

- on a staged tree with the stand-in checkpoint present: exit 0, all 12 checks `[PASS]`, the claim
  `[agree]`;
- on the unmodified base: exit 1, with the same nine `[FAIL]`s as before and the three invariants
  passing.

The suite is green on Python 3.11, 3.12 and 3.13 (381 tests).

## The session's work

This session lands D15's kill-switch in its three layers, `twine kill`, and the `cap-unchecked`
stop key. `VERSION` is 0.6.0. The suite has grown from 322 tests to 381 (49 of them in the new
`tests/test_kill.py`) and is green on Python 3.11, 3.12 and 3.13.

All 22 paths are inside the write forecast, so there are no departures. `bin/twine`, `fixtures/`,
`twine-seed.md` and `bale.toml` are untouched, and `validation.sh` checks each by hash. No probe was
needed: §2 of the brief held every bale fact I used. **No real `bale unlock` ran anywhere**, in the
suite, in `validation.sh` or by hand. Every unlock answer is a double built from §2.1's key
contract, named as one.

## What landed, against the brief's items

1. **`twine kill SID [--state-dir] [--cwd] [--bale-root] [--grace] [--json]`** is in
   `twine/commands/kill.py`, which the registry discovers; no shared list changed. It collects every
   refusal first and does nothing if there is any. The pin gate comes before the abort. Then it runs
   the three steps in order, reports each, and stops short of the closure while anything of the group
   lives. When it cannot finish, it reports where it stopped (`stopped_at`) and gives the hand line
   (`operator_line`). The JSON twin carries every key the brief lists, plus `stopped_at`, `telemetry`
   and the bale call's own fields. Every path carries the same key set.
2. **The loop's functions** are in `twine/kill.py`: `request_abort`, `abort_requested`,
   `close_aborted(run, executable, sid, cwd=, env=)` (it takes the seam's runner), and `kill_session`,
   which the verb is thin over. The `killed` stop key is `kill.STOP_KILLED`. A test runs the verb, then
   runs `kill_session` on its own in a second state directory against a second real group, and
   compares the two key for key. My first version of that test compared one object with itself; the
   review caught it.
3. **The running record**: `register_running`, `clear_running` and `read_running`, at
   `<state-dir>/running/<sid>.json`. A malformed record is a named refusal of the process step. The
   abort request still lands.
4. **`cap-unchecked`** is the thirteenth stop key, after `killed`, with one row and the operator move
   `fix-and-resume`. The table is total at 44 rows. `CallCheck.refuse` sets the key for every refusal
   that is not `cap-reached`, and `STOP_CAP_UNCHECKED` sits beside `STOP_CAP_REACHED`. A test walks
   every kind in `spend.REFUSALS`.
5. **The consumption manifest** has a new unlock `[[surface]]` with the brief's fields. Two small
   additions to its shape:
   - **`unrecorded`.** A verb with no recording used to need a `stand_in` file, and nothing recorded
     can stand in for unlock. The entry now says `unrecorded` and names its doubles instead. The
     header and `test_consumption_manifest.py` learned the field.
   - **`read_by`.** The `closure-reason` vocabulary is now also `read_by` kill.
6. **Docs**: contract §14 is new, and §2, §6, §7, §8, §10.6, §11.1, §12.2, §13 and §13.7 were edited,
   along with the header. `claude/INDEX.md`, `README.md` and `VERSION` are updated too.
7. **The runner** is covered in its own section below.

## Decisions to ratify

These are roughly in the order I'd want them read.

- **The pin gate comes first, as the brief orders, but I read D15 the other way.** A kill-switch that
  will not stop a runaway session because `bin/VERSION` differs from the pin is not "foolproof", and
  the pin exists for the closure (the table's vocabulary), not for the signal. A half-done kill is
  already a reported state: it has `stopped_at` and a hand line. So I would gate only the closure: the
  abort request and the process kill would run with any bale, or none. I built what the brief says. The
  flip is one block in `cmd_kill` (move `locate` after `kill_session`'s first two steps) plus the
  closure's own pin check, which already exists. Your call.
- **A state directory that does not exist is refused, and `twine kill` never creates one.** The
  review found the failure: a mistyped `--state-dir` got a fresh directory, an abort request nobody
  reads, "no running record", a closure, and `ok: true`, while the runtime ran on. A runtime that ran
  creates the directory (`register_running`), so a missing one means a typo or a session that never ran
  under twine. The refusal text says to use `bale unlock <sid> --reason aborted` for the latter. One
  consequence: today, with no Arc 2 runtime, a `twine kill` against the default state directory is
  refused on a machine where nothing has created it yet. The functions themselves still create
  directories, because the runtime's calls must.
- **The running record carries `leader_start_ticks`.** This is the group leader's start time from
  `/proc/<pgid>/stat`, or null. If a live process now holds that number with another start time, the
  recorded group is gone, because Linux never reuses a pid still in use as a group id. The record is
  then `stale`, nothing is signalled, and the closure proceeds. Without this, a record left behind by a
  dead runtime could have `twine kill` SIGTERM a stranger's group after pid wrap-around. One residual
  case is unprotected: the original group dies, its number is reused by a new group, that group's
  leader dies, and its members remain. That needs a full pid wrap plus that sequence, so I accept it.
- **Once the group is confirmed gone, `twine kill` removes the running record.** It is a cache, and a
  stale pgid is what a later kill could misdirect. A malformed record is left for the operator.
- **SIGCONT follows SIGTERM** (`signals: ["SIGTERM", "SIGCONT", ...]`). A stopped member never sees
  SIGTERM until it is continued, so without SIGCONT the grace is wasted on it. This was the review's
  suggestion.
- **Hand lines** (contract §14.2's table):
  - While the recorded group is not known to be gone, the line is `kill -KILL -- -<pgid>`, whichever
    step stopped first. A close is never handed out while a member may live; the review caught a path
    where it was.
  - A malformed record gives `null`, because the record names no group. The reason says to find and
    stop the runtime first.
  - A HOLD refusal gives `bale revert <sid>`.
  - Everything else gives the unlock line.
- **Twine reads one bale stderr text**, the HOLD refusal's prefix `branch bale/<sid> exists`, to hand
  back bale's own remedy. That is the one place twine keys on a refusal's words rather than on its exit
  and stdout. The manifest's unlock surface records it as a surface a pin bump re-reads. Every other
  refusal is surfaced verbatim, and its last line is in `reason`.
- **An abort request that cannot be written stops the kill short of the closure**, but the process kill
  still runs. Stopping spend never waits on a file write. Closing `aborted` without the request it
  records seemed wrong.
- **`abort_requested` fails closed.** Only a path that does not exist reads False; an unreadable state
  directory, or a file where `abort/` should be, reads True. Any file at the path is a request, whatever
  its content.
- **`close_aborted` checks the pin itself** and takes the `bale.Executable`, not a path. That way the
  Arc 2 loop cannot reach an unpinned bale by forgetting the gate.
- **Smaller bounds**: `--grace` is at most 600 s. A sid is at most 200 characters, because it names a
  file and the temp file's name is short whatever the sid's. The unlock call has a 120 s timeout and a
  1 MiB stdout cap. There is no retry; a timed-out unlock says it may or may not have closed.
- **`twine/commands/carry_bale.py` changed by one function.** `resolve_cwd` turned a deleted current
  directory into a traceback. `kill` reuses that function, so I fixed it there, and the carry verbs gain
  the same refusal. The file is inside the `twine/` forecast.

## The runner (brief item 7, §2.5's open question)

**My reading: `run_process` now kills and waits for the whole group, and twine kill does not rely on
it.** Contract §10.6 states the promise. However a run ends, the group gets SIGKILL. The run then
returns only once no member is alive, or after `GROUP_GRACE_SECONDS` (2 s) with the survivors named in
the new `RunResult.group_survivors` field, which defaults to `()`. All of this happens before the child
is reaped: the loop learns of the exit with a non-reaping `waitid(..., WNOWAIT)`, so the zombie keeps
holding the group id and neither the kill nor the wait can reach a reused number.

Why it changed more than I meant: the independent review found a race in the base runner. When a
child exits in the same instant its pipes reach EOF, the read loop ended before it saw the exit, and
the `finally` checked `proc.poll()` (which reaps) and **skipped the group kill**. A backgrounded member
that held no pipe (`sleep … >/dev/null &`) then outlived the run. I reproduced it on the unmodified base:
2 of 40 runs left the sleep alive. This plausibly also explains cost-spine-005's HOLD sleep, which those
notes could not reproduce.

My first fix killed the group unconditionally. That widened another pre-existing window: a child that
closes its pipes in its exit handler (`cat`) could be SIGKILLed just before exiting and reported as
exit -9. Under load that happened in 5 of 1500 runs, against 1 of 1500 on the base. The runner now gives
such a child up to `PIPE_GRACE_SECONDS` to exit on its own before the group kill. The result is 0 of
1500 under load.

Two new tests pin both cases: 25 runs of the escaped-sleep case and 200 of `cat`. The existing timeout
tests keep their `dies_within` polling: it is harmless, and taking it out is not this session's
business. A new test asserts the single check the guarantee now allows.

## What is not known, and where it will bite

- **No unlock output is recorded.** Every answer is a double built from `format_unlock_json`'s
  docstring. If the queued recordings show anything else (key order, whitespace, a key the docstring
  omits), the doubles are wrong and the recording replaces them. Twine reads only `outcome`, `sid`,
  `closure_reason` and `telemetry`, and parses the line as JSON, so order and whitespace cannot matter.
- **The process kill depends on `/proc`.** Without it the group is still signalled but never reported
  dead, so the closure never happens. That fails closed. The architect's machine and bale's sandbox both
  have `/proc`; the existing timeout tests already relied on it.
- **The loop's own closure is awkward against ruling 3.** When the Arc 2 loop observes the abort and
  runs `close_aborted`, the loop's own process, a member of the recorded group, is alive by definition.
  `kill_session` holds the line; `close_aborted` does not check. I think the loop's case is fine, since
  it stops before any further call and only it remains, but the planner should say so when Arc 2 builds
  the loop.
- **`model_identity`** is `anthropic:claude-opus-5-5`, the session's configured model. The serving model
  can differ, and I cannot see a picker.

## An independent check

Before packing, a separate agent that had not seen the work reviewed the diff against the brief. It ran
the suite and the CLI against stub bales it wrote, and tried to break the code. It confirmed the pinned
interfaces and found:

- the runner race (above);
- the wrong hand line when the abort fails while members live;
- the mistyped-`--state-dir` ok kill;
- tracebacks on a deeply nested record (a `RecursionError`) and on a deleted current directory;
- `abort_requested` failing open on `NotADirectoryError`;
- an over-long temp file name;
- an unbounded `--grace`;
- the missing SIGCONT;
- two contract sentences that overclaimed;
- the self-comparing test.

All of these are fixed, each with a test. I sent the fixes back; it confirmed each held and found the
-9 regression above, which is now fixed too. One finding is deliberately not fixed, and it is the first
Proposal.

## Validation

`validation.sh` has 12 checks. It ran twice, as TARBALL.md §7.2 asks:

- **On a staged tree.** I built it as bale stages: base plus `files/`, `apply.sh` run, the manifest at
  `.bale-manifest.json`, and a stand-in checkpoint at `claude/checkpoints/<sid>.sh` that nothing reads.
  Exit 0, all 12 `[PASS]`, and the one claim reconciled `[agree]`. Run again with eight busy loops on two
  CPUs, it passed again. It takes about 27 s, most of it the suite. Afterwards the staged tree matched my
  working tree byte for byte, apart from what staging adds.
- **On the unmodified base.** Exit 1. Nine checks `[FAIL]`: syntax (the new files are absent) and the
  eight session assertions (version, registry, transitions, spend's stop, kill end to end, the
  refusing stub, the refusals, and docs). The three invariants pass on both trees: the suite, the untouched hashes, and no
  bytecode.

The end-to-end check:

- starts a real `setsid`-led group whose members ignore SIGTERM, and records it with `register_running`;
- runs the real entrypoint under `-I -S` with an empty environment against a temp state directory and a
  stub bale root;
- asserts SIGTERM, SIGCONT, SIGKILL, every pid dead, the record cleared, the abort file present, and that
  the stub saw exactly `unlock <sid> --reason aborted --json` in `--cwd`.

The stub is a double that `validation.sh` writes and labels. A refusing stub (exit 1, empty stdout) is
not ok and shows its stderr. An unpinned stub, and a state directory that does not exist, are refused
with nothing written and nothing started. The script never walks the tree and never reads
`claude/checkpoints/`, `claude/responses/` or itself.

The `claims` block has one claim, the suite: `pass`, observed. The session assertions are listed and
not claimed, because a project-level check exists (TARBALL.md §5.3).

## Proposals

### Seed annotation for D15, and a road marker, for the next seed tidy

**What.** Two lines for `twine-seed.md`, verbatim-ready. Beneath D15:

> [2026-10-04-twine-kill-switch-002: landed — the kill-switch's three layers: the between-calls abort
> (`<state-dir>/abort/<sid>.json`, checked by `twine.kill.abort_requested` before every call; observed,
> the loop stops `killed` and closes), the process-level kill (the runtime's running record
> `<state-dir>/running/<sid>.json`; SIGTERM, SIGCONT, a grace, SIGKILL, finished only when no member of
> the group is alive, else the survivors named), and the `aborted` closure (exactly `bale unlock <sid>
> --reason aborted --json`, pinned bale, once, never while a member lives). The operator's line is
> `twine kill <sid>`. The cost spine's uncheckable cap stops `cap-unchecked` (move `fix-and-resume`,
> the operator's). The record covers one process group; the runtime's tools in groups of their own are
> Arc 2's (contract §14.4).]

On the §5.1 road, row 5:

> 5a landed as `2026-10-03-twine-cost-spine-005`; 5b landed as `2026-10-04-twine-kill-switch-002`.

**Why.** `twine-seed.md` is another open session's forecast, so these are the seed's to carry.

**Scope hints.** `twine-seed.md` only, after `2026-10-04-twine-seed-landings-001` closes.

### The runtime must record every process group it starts (Arc 2)

**What.** When the Arc 2 runtime is built, every process it starts must be inside a group `twine kill`
knows. There are two shapes:

- **(a)** The running record holds a list of groups. The seam gains a spawn hook that registers each
  child's group the moment `Popen` returns, before the child is fed input. `twine kill` signals each
  group and waits for all of them.
- **(b)** The runtime starts its tools inside its own group rather than a new session. This breaks
  `run_process`'s "kill the child's group on timeout" without killing the runtime.

I lean to (a).

**Why.** `run_process` starts every child with `start_new_session=True`, so a tool the runtime runs
through the seam leads its own group. Today `twine kill` would report `dead` and close `aborted` while
that tool runs on. The review demonstrated it with a `sleep 45` started through `run_process`. Nothing
runs under twine yet, so nothing is missed today. Contract §14.4 says what `dead` does and does not
cover, and the manifest's `deferred` lists it.

**Scope hints.** `twine/process.py` (a spawn hook on the runner), `twine/kill.py` (`RunningRecord` grows
`groups`, `kill_group` loops over them) and contract §10.6 and §14.4. This must land before Arc 2's loop
runs a tool.

### Ask bale-src for a machine-readable unlock refusal

**What.** A `[[wanted]]` entry for `bale unlock --json` to print a refusal as a JSON line too, with a
reason code (for example `hold-branch`, `not-open`, `several-open`), as `bale apply --json` does for its
`*-refused` outcomes.

**Why.** Twine now keys one decision, the `bale revert` hand line, on the words of a stderr message. A
reworded message would silently downgrade it to the unlock line. That fails safe (bale would refuse
again, naming the branch), but a code is the contract.

**Scope hints.** `share/bale-consumption.toml` (`[[wanted]]`) here; the change itself is bale-src's.

### Carried, still open: `twine status` reports where state lives

cost-spine-005's Proposal, still open and now more useful. `status` would gain `state_dir`,
`state_dir_source`, and whether `spend.jsonl`, `prices.toml`, `abort/` and `running/` exist. An operator
whose `twine kill` was refused for a missing state directory would find out from `status` which one
twine resolves. The change is in `twine/commands/core.py` and `tests/test_status.py`.

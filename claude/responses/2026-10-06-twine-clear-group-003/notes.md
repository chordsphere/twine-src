# notes — 2026-10-06-twine-clear-group-003 (clear_group, the kill's second follow-up)

## The session's work

`clear_group(state_dir, sid, pgid) -> bool` lands beside `register_group` in `twine/kill.py`, with
the signature pinned as written and no keyword extras. `VERSION` is 0.7.1. Six files change, all of
them inside the write forecast, so there are no departures. `tests/helpers.py` was forecast but
needed nothing, because `RealGroup`, `StubBale` and the unlock doubles already covered every case.

`twine-seed.md`, `twine/process.py`, `share/`, `fixtures/`, `bin/twine` and `bale.toml` are
untouched, and `validation.sh` checks each by hash. The suite grows from 416 to 434 tests (eighteen
new, all in `ClearGroup`). It is green on Python 3.11, 3.12 and 3.13, as root (2 skips, 5c's
unreadable-directory tests) and as `nobody` (0 skips).

Before building I checked the tree against brief §8: `VERSION` read 0.7.0, `twine.kill` had no
`clear_group`, the seed hashed to `a8147460…` at 1392 lines, and the suite ran 416 tests green on
the shipped bytes.

What `clear_group` does, outcome by outcome (brief §2.1). The docstring and contract §14.4 say the
same in their own words.

- **True.** It removes every entry of `groups` naming the pgid (one normally, each of them when
  the record names it twice). It rewrites the record through `_write_record`, the same durable
  temp-fsync-replace-fsync path `register_group` uses. The six keys, the runtime's four values and
  the other entries stay untouched and in their order.
- **False.** It returns False, writing nothing and creating nothing, when the record names no such
  group and when there is no record. An absent `running/` stays absent, because `_locked` never
  creates the directory and the write path is never reached. Both cases log at info.
- **Refusals.** `RunningRecordError` comes back, with the record untouched, for:
  - a pgid that is not an integer above 1 (checked first, before any path is built, so a bad pgid
    creates nothing even with no record);
  - the runtime's own group (the message points at `clear_running`);
  - a malformed record (`read_running`'s faults, every one named).

  A rewrite that fails is `KillError`.
- **Lock.** It runs under the exclusive `flock` on `running/` that `register_group` takes.

The kill itself is unchanged: `kill_group`, `kill_more`, the re-read and the hand line are
byte-identical in the diff. A cleared real group survives `twine kill`, and the twin names only the
groups still recorded. A unit test and the end-to-end validation check both show this.

Docs:

- **Contract §14.4.** The `clear_group` paragraph sits after "Nothing writes it in Arc 1 but the
  tests.", followed by a bolded **composition rule** paragraph for the Arc 2 loop.
- **Contract §14.8.** The line is added verbatim, between `register_group`'s two lines and
  `clear_running`'s, with a `# raises …` comment.
- **Contract §14 header.** This session's id now sits beside 5c's.
- **`claude/INDEX.md`.** The record "grows as it starts tools and shrinks as they return with
  nothing left alive (`clear_group`)".
- **`README.md`.** I took the optional clause (see below).
- **`twine/kill.py`'s module docstring.** Layer 2 now names `clear_group` beside `register_group`.
  The docstring's section line numbers are refreshed.

## Decisions to ratify

- **No resurrection: `clear_running` takes the same lock.** Brief §2.1 left the mechanism to me. A
  re-check under the lock before the replace would only narrow the window, because the kill's
  `unlink` does not take the lock and could still land between the re-check and `os.replace`. With
  `clear_running` inside the lock, two orders are possible, and in neither does a removed record
  come back:
  - a clear that has read the record finishes its replace before the removal runs;
  - a clear that starts after the removal reads no record and writes nothing.

  Two tests stage this:
  - `test_the_kills_removal_waits_for_a_clear_between_its_read_and_its_replace` is deterministic
    and single-threaded. It patches `_write_replacing` so that the kill's `clear_running` arrives
    between the clear's read and its replace.
  - `test_a_removal_racing_a_clear_is_never_undone` is threaded. It patches `read_running`, so
    the removal starts while the clear holds the record.

  Both fail with `clear_running` unlocked; I checked by mutation.
- **`clear_running`'s wait for the lock is bounded at `CLEAR_LOCK_SECONDS = 5.0`.** The brief did
  not ask for this; I added it so the new lock cannot regress D15.
  - **Why it is needed.** The lock is the `running/` directory's, shared by every session's record.
    A runtime stopped (SIGSTOP, ^Z) in the middle of a `register_group` would otherwise make any
    session's `twine kill` hang forever at its last step.
  - **What happens past the bound.** `clear_running` raises `KillError` and the record is left in
    place. `kill_session` already catches that `KillError` as "the groups are gone but … (a cache)".
    So the kill reports `record_cleared: false` and still attempts the closure, because every
    group is dead by then.
  - **Tests.** `test_a_kill_that_cannot_have_the_lock_leaves_the_record_and_still_closes` covers
    it, holding the lock from the test with the bound patched to 0.2 s.
  - **The writers do not get a bound.** `register_group` and `clear_group` still wait unbounded,
    as `register_group` did in 5c.
  - **If you would rather the kill wait without a bound,** it is one argument to remove.
- **A `flock` the filesystem refuses outright counts as "flock unavailable".** Errors such as
  `ENOLCK` on some network mounts are treated as no lock rather than as a fault: they are logged
  and the body runs unlocked, which is what the code did before any lock existed. The independent
  review (below) found that without this, a refused `flock` reached `twine kill` as a bare
  `OSError` (exit 2, the closure never attempted). That would have been a regression, since the
  kill's removal goes through the lock now. `register_group`'s unbounded `flock` already had this
  exposure in 5c; it is covered by the same change. The contract says so ("no `fcntl`, or a
  filesystem that refuses the lock (`ENOLCK`)"). Tested with a patched `fcntl.flock`.
- **One knock-on to flag: `register_group` racing the kill's removal now refuses instead of
  resurrecting.** In 5c, a hook whose `register_group` had read the record before the kill's
  `unlink` would `os.replace` it back into existence: a record naming a closed session's groups. Now
  that hook either lands before the removal or finds no record and raises `RunningRecordError`, and
  the seam then SIGKILLs that child (§10.6). The kill only reaches the removal once the runtime is
  dead, so the window was theoretical in either form. I judge the new behaviour the right one (a
  live tool from a closed session is D15's mystery), but it is a change to `register_group`'s race
  behaviour that the brief did not name.
- **No `clock=` or `proc_root=` on `clear_group`.** It stamps nothing and reads no `/proc`.
- **No liveness check inside `clear_group`.** The rule "clear only after a survivor-free return" is
  the caller's, written into contract §14.4. A `/proc` check inside would add a refusal the brief
  does not list, and could refuse wrongly on a reused number.
- **The README clause: taken.** Without it, "its own group, and every group it started since"
  becomes false once the loop clears entries.
- **Both Falses log at `info`, not `warning`.** The brief calls neither a fault.
- **Check order.** The pgid is checked before the sid, as in `register_group`. A call with both
  wrong raises `RunningRecordError` rather than `ValueError`.
- **`model_identity`** is `anthropic:claude-opus-5-5`. That is the session's configured model; the
  model serving it can differ, and I cannot see a picker.

## What I noticed in the existing code

- **The composition rule's premise holds only where there is `/proc`.** Contract §10.6 says that
  without `/proc` the seam skips its group wait and `group_survivors` is `()`. So on such a
  platform, "returned with no survivor" is not evidence that the group is gone. `twine kill` cannot
  confirm a group dead there either (it never reports `dead`), so neither choice is good. I did not
  put this in §14.4 because it concerns the seam's promise, not the record. It belongs in the Arc 2
  loop's brief (Proposals).
- **The lock covers the whole `running/` directory, so every session's writers serialize.** At one
  read and one replace per call that costs nothing, and it is why the kill's wait needed a bound.

## An independent check

Before packing, a separate agent that had not seen the work reviewed the diff against the brief.
It:

- ran the suite on 3.11, 3.12 and 3.13, as root and as `nobody`;
- confirmed the out-of-scope files are byte-identical;
- mutation-tested the work eight ways, each of which a `ClearGroup` test caught.

It found:

- **Blocking: a racy test.** In the composition test, the child ran `cat` before the hook had
  written. It failed 7 times in 20 under CPU load. Fixed: the child now waits for a line on stdin
  (`read -r go`, as 5c's hook test does), which the seam feeds only after the hook. 24 parallel
  runs of the class are green.
- **Should-fix: the `ENOLCK` regression.** Fixed and tested, as above.
- **Nit: cleanup order.** On a failed assertion while the test held the lock, the thread join waited
  30 s. Fixed: release first, then join.
- **Nit: the INDEX wording.** It now says "with nothing left alive".

## Validation

`validation.sh` has 9 checks and the claims block. It:

- announces its two write locations first: `.validation-logs/<stamp>/` under the staging root, and
  one temp directory under `$TMPDIR` that also serves as the suite's TMPDIR and is removed at exit;
- runs every Python under `-B`, and every heredoc Python under `-I -B`, including the crafted
  epilogue (its `python3 -` became `python3 -I -B -`);
- looks for `__pycache__` only under `twine/`, `tests/` and `bin/`;
- never walks `claude/checkpoints/` or `claude/responses/`, and never reads itself;
- compares bytes with `cmp` (`VERSION`) and `sha256sum -c` (the untouched files).

It ran twice (TARBALL.md §7.2):

- **On a staged tree built as bale stages it:** the base plus `files/`, `apply.sh` run, the
  manifest at `.bale-manifest.json`, and a stand-in checkpoint nothing reads. Exit 0, all 9
  `[PASS]`, the one claim `[agree]`, about 41 s (the suite is about 39 s). Afterwards the staged
  tree held nothing new but the logs, there was no `__pycache__`, and the temp directory was gone.
- **On the unmodified base:** exit 1. These five session assertions `[FAIL]` by name:
  - `session: VERSION is 0.7.1`
  - `session: clear_group's outcomes (brief §2.1)`
  - `session: a cleared group survives twine kill (real groups, the verb end to end)`
  - `session: contract §14.4, §14.8 and its header carry clear_group`
  - `session: INDEX.md, README.md and kill.py's docstring name the clear`

  The other four pass on both trees: the syntax, the suite, no bytecode, and the untouched hashes.

The end-to-end check starts four real `setsid`-led groups (one ignoring SIGTERM). It registers
three as the runtime and the hook would, then registers the fourth and clears it. It runs the real
entrypoint under `-I -S -B` with a minimal environment against a stub bale. The stub is a double: a
bash script replaying a line built from `format_unlock_json`'s key contract, which the script says
in its second line. The check asserts:

- every recorded pid is dead (polled);
- every pid of the cleared group is still alive;
- `process.groups` names exactly the two tools;
- the record is cleared;
- the stub saw exactly `unlock <sid> --reason aborted --json`.

No real `bale unlock` ran anywhere.

The untouched check hashes the 13 files of `share/` and `fixtures/` that `context/` carries. It
does not assert those directories hold nothing else, because the real tree may hold fixtures the
request did not ship.

The `claims` block has one claim, the suite: `pass`, observed. The session assertions are listed
and not claimed, because a project-level check exists (TARBALL.md §5.3).

## Proposals

### Seed annotations for this session, for the next seed tidy

**What.** Two texts for `twine-seed.md`, verbatim-ready. The first goes beneath D15, after the
kill-followups-003 annotation:

> [2026-10-06-twine-clear-group-003: landed — `twine.kill.clear_group(state_dir, sid, pgid)`
> forgets a group once its run has returned with no survivor, so the running record holds what is
> alive rather than one entry per tool. It runs under `register_group`'s lock on `running/`, and
> `clear_running` takes that lock too (bounded, so a wedged writer cannot hang the kill), so a
> record `twine kill` removed never comes back. The loop calls it itself after `run` returns with
> `group_survivors` empty; an entry whose run returned survivors stays for the kill (contract
> §14.4). `twine kill` is unchanged and does not signal a cleared group.]

The second goes on the §5.1 road, after the tidy4-001 row-2 marker:

> [2026-10-06-twine-clear-group-003: `clear_group` landed (`VERSION` 0.7.1): the record's
> registered groups can now be forgotten as their runs return. Arc 2's loop composes
> `on_spawn=lambda pid: register_group(state_dir, sid, pid)` with `clear_group(state_dir, sid,
> pid)` after a survivor-free return.]

**Why.** `twine-seed.md` is out of scope by name (brief §6). The texts are the seed's to carry.

**Scope hints.** `twine-seed.md` only, in the next seed tidy.

### Arc 2's loop brief: when to clear, and what the answers mean

**What.** When the loop's brief is written, beside kill-followups-003's third Proposal (where the
hook goes, what to do when it raises), add these four points:

- Call `clear_group` only after a `run` whose `group_survivors` is empty. A `RunError`, a hook that
  raised, or a result with survivors leaves the entry for the kill.
- A `False` from `clear_group` is not an error. The kill may have removed the record under the
  loop, which the loop learns from `abort_requested` anyway.
- A `RunningRecordError` from `clear_group` (malformed record, or the runtime's own pgid) is the
  same class of fault as the hook raising.
- Without `/proc`, `group_survivors` is `()` unverified (§10.6), so the loop should not clear on
  such a platform. Alternatively, the brief can declare Linux the only host, which is already true
  in practice.

**Why.** All four are what the code does now, or what its premise needs. The fourth is the gap
noted above.

**Scope hints.** The Arc 2 sitting's brief for the loop; no twine-src file.

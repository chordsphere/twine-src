# notes.md — 2026-10-07-twine-carry-bundle-003 (`twine carry bundle`, Arc 1 row 3)

`twine carry bundle BUNDLE` now runs `bale open <bundle> --json`. With
`--check` it runs `bale open --check <bundle> --json`. Those are the two
recorded argvs and the only `open` argvs twine builds. The call runs once,
never retried, with an 1800-second timeout. On `opened` or `second-desk`,
human stdout is exactly bale's `opener`, and stderr names the sid, the desk,
the request tarball and the record. The open is recorded in
`<state-dir>/inflight/<sid>.json` with exactly the brief's four keys and five
entry keys.

Fifteen files change: three created, twelve modified, all inside the
forecast. `VERSION` is 0.9.0. The suite went from 455 to 521 tests, green on
Python 3.13 as root, with the same two skips as at 0.8.1. No network was used,
and no bale was run except stubs. `twine-seed.md`, `bin/twine`,
`share/transitions.toml` and every file under `fixtures/` are byte-identical,
and `validation.sh` checks all of them by sha256.

## 1. The three decisions brief §5 left to me

**Where the code lives.** The verb is in a new `twine/commands/carry_bundle.py`.
I didn't put it in `carry_bale.py`, because `__init__.py` says a family may
span modules to keep sessions file-disjoint, and this verb has its own
state. The record is in a new `twine/inflight.py`. `_write_replacing` and
`_locked` (and `DIR_MODE`, `RECORD_SUFFIX`, `is_sid`, `utc_now`) are
**imported** from `twine/kill.py`, not moved, so `kill.py` is unchanged and
its tests don't move. One cosmetic cost: `_locked` and `_flock` log "the
running record is changed unlocked" when flock is unavailable, and that
wording now also covers the in-flight record. It is not worth touching
`kill.py` for. The Proposals cover moving these helpers if a third writer
appears.

**Wording.** The reasons and diagnostics are in §15.2–§15.5 of the
contract, and the tests pin their key phrases. Some examples:

- `BUNDLE '-x' names no existing file and begins with `-`, so bale could
  read it as a flag; name the file by a path (./-x)`
- `bale reported outcome 'rehearsed'; an open wants 'opened' or 'second-desk'`
- `… ; --check wants 'rehearsed'`
- `bale's opened line has no sid twine accepts (sid None)`
- `… has no opener (opener '')`
- `bale was stopped before it finished, so the session may or may not be
  open: `bale status` in <cwd> says which — twine never retries an open`.
  This follows call_bale's own `bale did not finish within 1800s and was
  killed`, and it is used for both a timeout and a capped stdout.
- A refusal to resolve a state directory gets the suffix `— carry bundle
  records each open in twine's state directory (inflight/<sid>.json), and
  an open that could not be recorded is refused before it happens;
  rehearse with --check, which needs none`.
- A record that could not be written: `<why> — the session is open in bale,
  so this is not a failure and nothing is retried (a retry would open
  another desk)`.

**Replacing a stale record on `opened` is not named in `record_error`.**
It is not an error: the open bale just reported is the session's now.
`record_error` stays null. stderr says `an earlier in-flight record of
<sid> was replaced by this open (<path>)`, and `Recorded.replaced` carries
it for a caller. If you'd rather the twin show it, a `record_error`-style
sentence is a one-line change in `record()`. I kept the key's meaning
narrow: why it was not written, or why it was replaced *fresh*.

## 2. Other choices worth ratifying

1. **`carry_bale.call_bale` gained a keyword, `timeout=BALE_TIMEOUT_SECONDS`.**
   Brief §1 named `call_bale` as a piece to reuse, but its 300 seconds was
   hard-coded and §2.3 needs 1800. The default is unchanged, so `carry
   exchange` and `carry response` behave exactly as before and their tests
   are unedited. The timeout failure now prints the timeout it was given.
   The file is under `twine/commands/`, which §7 forecasts.
2. **A state directory that "cannot be looked at" is refused too, not only
   one that "exists and is not a directory".** This means the third answer of
   `kill.state_dir_fault`: a parent that is a file (ENOTDIR), or no search
   permission. §2.2 names only the second, but §1 points at
   `state_dir_fault` and §2.2's rule is "an open that could not be recorded
   is refused before it happens". A path twine cannot stat is one it cannot
   write. A state directory that **does not exist yet is accepted**: the
   writer creates it with `mkdir(parents=True, mode=0o700)`, as spend's
   writer does. That means intermediate parents get default permissions,
   like `mkdir -p`. `twine kill` still refuses a missing state directory,
   for its own reason (§14.1). The difference is deliberate, and §15.2
   says so.
3. **`second-desk` appending keeps the record's `cwd`** (the first open's) as
   well as its `tarball`. The entry has no `cwd` of its own, and the brief's
   shape has one per record. If a desk ran elsewhere, that is logged at INFO.
4. **A fresh `second-desk` record has `tarball` null even if bale's line
   gave one.** This is §2.4 read literally ("a fresh record with tarball
   null"). The twin's `tarball` is still bale's in that case, with
   `tarball_source` `"bale"`. Today bale 0.4.49's `second-desk` line always
   says null, so the two can't differ yet. Once the bale-src follow-on lands
   they can. The Proposals cover this.
5. **`read_inflight` is strict: exactly the four keys and each entry's
   exactly five.** An extra key is a fault, not ignored as `read_running`
   ignores it. This keeps "exactly these keys" true after an append. A
   record with an extra key is replaced fresh on `second-desk` rather than
   appended to, and `record_error` names the key.
6. **When `bundle` is set in the twin.** `bundle` is set once the argv is
   built. So a bale that could not be started (`RunError`, a refusal with
   `ran` false) still shows the argument it would have been given. I read
   "null when refused before that" as "before the argument was handed to
   the seam". `argv` follows the same rule.
7. **`tarball` is null on every not-ok path** and on a rehearsal. §2.5 defines
   it as §2.4's, which is an ok-path value. On an ok open, if bale's
   `bundle.sha256`, `desk` or `tarball` is not a string, the record holds
   null for it. None of these are among the ok conditions, so I didn't add
   any.
8. **`--state-dir` under `--check` is ignored, not validated.** Even an
   empty `--state-dir ""` passes under `--check`. stderr says the flag is
   not read. §2.2 says `--check` "never reads" a state directory, and
   refusing a malformed flag it ignores would be a kind of reading.
9. **The `opened` diagnostics** say "the first desk" when bale's `desk` is
   null.
10. **A relative BUNDLE when the current directory is gone** is passed as
    given, with an info line. It can't be made absolute, and bale running in
    `--cwd` resolves it there. Without `--cwd`, the missing current directory
    is already a refusal.
11. **A line carrying text that is not UTF-8 is not ok.** This covers a
    lone-surrogate escape such as `\udcff`, which is how Python's json
    prints a path with non-UTF-8 bytes. §2.4's rule only asks for "a
    non-empty string", but such an opener can't be written to a UTF-8
    stdout, and the twin can't be either. Before this fix it was a
    traceback after the session had opened, which is exactly the
    retry-inviting failure §2.4 rules out. Now it is a named failure. The
    reason says the session may be open and that `bale status` tells which.
    `open` shows `?` in place of the bad text, and `stdout` keeps bale's raw
    line. Nothing is recorded, because the record would not hold bale's
    text. The alternative was ok, with replacement characters in the opener
    and tarball. That would hand the operator text bale never printed, so I
    didn't take it. This is a departure from §2.4's letter, made to keep
    "no traceback"; if you'd rather have the alternative, it is a few lines
    in `read_line`. The reviewer pass found this (§4).
12. **A BUNDLE name twine cannot stat is passed as given.** That covers a
    name too long to stat, or one under a directory twine can't search.
    `Path.is_file()` raises on those rather than returning False, so this
    is a caught `OSError` and an info line. The leading-`-` refusal still
    applies to such a name. (`carry_bale.resolve_cwd`'s `is_dir()` has the
    same exposure for `--cwd`. It predates this session and I left it.)
13. **An existing `inflight/` keeps its mode.** The directory is 0700 when
    twine creates it. An `inflight/` that is already there is not chmod-ed,
    the same way `kill.py`'s and `spend.py`'s writers leave their
    directories as found. The file is always 0600. §15.4 says so. If §2.4
    meant to enforce 0700 on an existing directory, that is one `chmod` in
    `record_open`.
14. **The `open` guard counts argv tokens, not dict keys.**
    `test_open_is_built_in_one_place_only` follows the unlock guard's shape,
    but it skips constants that are dict keys. The twin's `"open"` key is
    spelled like the verb. Every other `"open"` constant in `twine/` must be
    inside `bale.open_argv`. Within `bale.py`, `"--check"` must be too, and
    `open_argv`'s only flags are `--check` and `--json`.

## 3. Every test that moved, by name

The brief predicted four suite pins would move. Those four moved and nothing
else did:

- `tests/test_consumption_manifest.py`:
  `test_open_json_is_a_surface_read_by_nothing_yet` →
  **`test_open_json_is_read_by_carry_bundle`**. It now pins `keys` ==
  `["outcome", "sid", "tarball", "opener", "desk", "bundle"]` and `read_by`
  == `["carry bundle"]`. It also checks that each named key is among
  `format_open_json`'s 21 (`tests/helpers.py` `OPEN_KEYS`), that all three
  recordings carry exactly those 21 in order, and that the note names the
  verb. The `also_recorded` and `pack` assertions are kept as they were.
- `tests/test_registry.py` `test_this_sessions_verbs_are_registered`: the set
  gains `carry bundle`.
- `tests/test_registry.py` `test_discovers_carry_module_as_a_group`: it also
  asserts `twine.commands.carry_bundle` is discovered. The carry group is now
  `["carry bundle", "carry exchange", "carry probe", "carry response"]`.
- `tests/test_json_discipline.py` `argv_for`: `carry bundle` is
  `<existing file> --check --bale-root <stub>`. The stub replays the recorded
  rehearsal. `setUp` writes the bundle file and passes
  `open_stdout=open_recording("rehearsed").path` to `StubBale`.

`tests/helpers.py` grows without changing anything existing. `StubBale`
takes `open_stdout=`. `OPEN_KEYS`, `OPEN_KEY`, `OPEN_RECORDED_SID`,
`OPEN_RECORDINGS` and `open_recording(name)` read the three open lines the
way `unlock_recording` reads the unlock lines.

**`tests/test_carry_bundle.py` is new, with 66 tests** in twelve sections.
They cover every bullet of brief §3. The recordings are replayed through the
fixture player: `opened` and `second-desk` with the test's directory as the
scratch root and the group selected, `rehearsed` with `--cwd` set to the
repo root. Every double is named as one (`OpenDouble`, `edited_line`): the
refusal (exit 1, nothing on stdout), a timeout, a capped stdout, a line with
`NOT_A_BALE_OUTCOME`, a line missing `sid` or `opener`, a non-zero exit
beside an `opened` line, and a `second-desk` line carrying a tarball. Beyond
the brief's list, it also covers:

- the exact twin key set on each of six paths;
- a tree diff proving the verb writes only `state/inflight/<sid>.json`;
- an AST check that neither `inflight.py` nor the verb calls
  `unlink`/`remove`/`rmdir`/`rmtree`;
- the record's modes (0700 and 0600);
- eight threads recording `second-desk` at once, so the flock is shown
  losing no entry;
- `read_inflight`'s faults, each named;
- an end-to-end subprocess run against `StubBale`;
- the pin gate;
- a non-UTF-8 line, end to end;
- a 5000-character BUNDLE.

**A cold review.** Before shipping, a separate agent that hadn't seen the
work being built reviewed the diff against the brief. It found no departure
I hadn't flagged. It found the two traceback paths fixed in §2 items 11–12,
and it raised the directory-mode reading in item 13. It also noted that
when bale's `desk` is not a string, the twin shows bale's raw value while
the record stores null (item 7). I kept that: the twin reports bale's line,
and the record keeps only typed values.

## 4. validation.sh, and what it can and cannot tell

There are ten checks. The script writes only under
`.validation-logs/<ts>/`. `TMPDIR` points at a `tmp/` there for the suite,
the two stub runs and their state directories. It runs `python3 -I -B`, and
`bin/twine` as `python3 -I -S -B` under `env -i`, with no HOME, so no real
state directory can resolve. It reads nothing under `claude/checkpoints/`.
The checks:

1. file syntax (python, toml);
2. the suite;
3. the suite has at least 455 tests;
4. the brief's end-to-end run: the stub replays `opened`. It checks that
   stdout is byte-equal to the recording's opener, that the stub saw
   exactly `open <abs> --json` in `--cwd`, the record's exact keys and
   values, the modes, that only the record exists under the state
   directory, and that nothing is in `--cwd`;
5. a `--check` end-to-end run with no state directory resolvable: one exact
   stdout line, the exact argv, nothing written;
6. the untouched set by sha256: the brief's two hashes, `transitions.toml`,
   and all 34 files under `fixtures/`, with a check that no fixture file was
   added;
7. `bin/twine` is executable;
8. `VERSION` compared with `cmp` against `0.9.0\n`;
9. §15's heading, the open surface's `read_by`/`keys`/note, the unchanged
   pin, and README/INDEX naming the verb;
10. no `__pycache__` in the tree.

I ran it twice, as §7.2 asks. In a staging copy (the given tree plus
`files/`) all ten pass in about 40 s. On the unmodified tree, checks 4, 5, 8
and 9 fail as they should. Checks 1–3, 6, 7 and 10 pass on both, by design:
they guard "unchanged" or "still works" constraints, which hold on the old
tree too. The claims are `observed` from those runs.

## 5. The seed annotation (out of scope here; for the next tidy)

At the end of §5.1's annotations (after the 2026-10-06-twine-clear-group-003
one), verbatim:

> [2026-10-07-twine-carry-bundle-003: row 3 landed — `twine carry bundle`
> runs `bale open <bundle> --json` itself (an open merges nothing; `--check`
> rehearses with `bale open --check <bundle> --json`), once, never retried,
> and prints exactly bale's opener; stderr names the request tarball. The
> in-flight record is `<state-dir>/inflight/<sid>.json` — `sid`, `cwd`,
> `tarball`, and one `opens` entry per desk — written on `opened` or
> `second-desk` only, and it is where a second desk finds the tarball bale
> 0.4.49's `second-desk` line leaves null. It is a cache of bale's open line
> and the invocation, not of `bale status --json` as the 2026-10-01
> annotation above sketched it; dispatch facts (adapter, sandbox home,
> transcript) are Arc 2's to add. Nothing removes it yet. `VERSION` 0.9.0.
> With rows 0–5 landed, Arc 1 is complete.]

The 2026-10-01 annotation said the in-flight record would be "derived from
`bale status --json` plus twine's own dispatch facts". The brief's record is
derived from the open line instead, so the new annotation says so rather
than leaving the older sketch looking unmet.

## Proposals

**What.** Teach `twine status` about `inflight/`. Add a fifth
`state_present` boolean, and possibly a list of the sids with records.
**Why.** `status` already reports `abort/` and `running/`, and the brief
lists "twine status reading the records" as a next session. A record nobody
reads is only useful to the next `second-desk`.
**Scope hints.** `twine/commands/core.py`, contract §4, `tests/test_status.py`.
It uses `inflight.INFLIGHT_SUBDIR` and `read_inflight`.

**What.** When bale-src makes `second-desk`'s `tarball` non-null, revisit
two things in §2.4. First, whether a *fresh* `second-desk` record should
keep bale's tarball instead of null. Second, whether an appended record
should adopt a tarball when its own is null.
**Why.** Today the two can't differ (bale's is always null). After that bale
change, the literal rule throws away a value bale printed. That cuts against
the record being "every value bale's".
**Scope hints.** `twine/inflight.py` `_compose`. This needs a pin bump and a
re-recorded `second-desk` line first.

**What.** Move `_write_replacing`, `_locked`, `_flock`, `_fsync_dir` and
`_temp_name` out of `twine/kill.py` into a small shared module, such as
`twine/durable.py`, with neutral log wording.
**Why.** Two record writers now import private helpers from the
kill-switch. Their warning text says "running record" even when the
in-flight record is being written.
**Scope hints.** `twine/kill.py` (import only), `twine/inflight.py`. A
refactor session with `kill.py`'s tests unchanged. It is not worth doing
until a third writer appears.

**What.** Add `inflight` to `twine/__init__.py`'s module list.
**Why.** That docstring is the package's map. The brief said nothing else
under `twine/` changes, so I left it.
**Scope hints.** One docstring paragraph, for the next session that touches
`twine/__init__.py`.

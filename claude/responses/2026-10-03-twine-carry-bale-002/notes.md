# notes — 2026-10-03-twine-carry-bale-002 (Arc 1 session 2b-ii)

This session lands `twine carry exchange` and `twine carry response`, the dry-run fixture, the
normalized-argv fixture player, and the contract's §11. It also prepares the `confined` switch
point. `VERSION` is now 0.3.0, and the suite has grown from 154 tests to 207.

Every path is inside the write forecast, so there are no departures to admit. `twine-seed.md`,
`claude/INDEX.md` and `bale.toml` are untouched; `validation.sh` asserts that none of them is in
`changes[]`. No probe was needed. No bale is reached anywhere: not by the tests, and not by
`validation.sh`.

## Where the code lives

- **The verbs.** Both are in a new module, `twine/commands/carry_bale.py`. The registry already
  assembled a group from several modules, so `carry` now spans `carry.py` and `carry_bale.py`.
- **Shared reading.** `carry.py` gave up two things so that both modules share one "never a
  guess" rule:
  - `read_turn` now also returns the normalized text, which `block_text` slices.
  - `choose_block` takes the kind (`probe` or `exchange`).

  The probe messages are unchanged with one exception: the article before a kind that starts
  with a vowel is now right (`names an exchange block`, which used to read `a exchange`). All 39
  existing `carry probe` tests pass unedited; this session adds a 40th, for `confined`.
- **Building bale argvs.** This happens only in `twine/bale.py` §5:
  - `relay_argv` builds `bale relay <sid> -`.
  - `dry_run_argv` builds `bale apply --dry-run --json <abs path>`.

  A test walks every `.py` under `twine/` and asserts two things: the string `"apply"` occurs
  once, inside `dry_run_argv`, and no string constant carries `--no-interact`, `--admit`,
  `--override`, `--force` or `--yes`. `validation.sh` repeats the check.

## The JSON twins as landed

**`carry exchange`.** The brief's fixed names come first, in this order: `sid`, `block`, `ran`,
`exit_code`, `stdout`, `stderr`, `reason`, `refusals`. Beside them:

- `integrity`: the chosen block's, as `take` reports it.
- `argv`: what was handed to the seam, or null.
- `stderr_truncated`, `timed_out`, `capped`, `duration_seconds`.
- `cwd`.
- `bale`: an object with `executable`, `root`, `source`, `installed`, `pin` and `pin_matches`.
- `input`: as `take`'s.

**`carry response`.** The fixed names come first, in this order: `tarball`, `ran`, `exit_code`,
`dry_run`, `outcome`, `apply_line`, `stderr`, `reason`, `refusals`. Beside them: `stdout`, `argv`,
`stderr_truncated`, `timed_out`, `capped`, `duration_seconds`, `cwd`, `bale`.

Both verbs follow the same conventions:

- `reason` is every refusal and failure, joined with `; `.
- `refusals` lists only the reasons bale was not called. A run that went wrong (a non-zero exit, a
  bad outcome, a timeout) has `refusals: []`, `ran: true` and the reason in `reason`.

Contract §11.2 and §11.3 carry the tables, and `validation.sh` checks that every fixed key is
named there.

## The fixture

- **Path:** `fixtures/bale-0.4.45/twine-src/apply_--dry-run_--json_tarball.json`.
- **Bytes:** 315, sha256 `f5bd7e5bbb92363b2993e2aaba5816dc3428dd7acdc0c51e8e194a49c43471ce`. I wrote
  it from the brief's fenced line plus one newline, and the hash matched the probe's before
  anything else was built.
- **Its README row:**

  ```
  | `bale-0.4.45/twine-src/apply_--dry-run_--json_tarball.json` | `bale apply --dry-run --json <tarball: unrecorded>` | `/home/chordsphere/twine-src` | unrecorded | 315 | `f5bd…71ce` |
  ```

  A paragraph under the table gives its provenance: probe `twine-2b-ii-fixture`, the Downloads
  path, what its own fields say, and what is unknown (the tarball argument, hence the argv's
  order, and the exit status).
- **Name.** The name follows the extended naming rule. A per-run value is replaced by its role, and
  a role forms its own `_` group, so `relay <sid> -` names `relay_sid_stdin.txt` and
  `apply --dry-run --json <path>` names `apply_--dry-run_--json_tarball.json`. That is the 2b-i
  Proposal's spelling. `fixtures/README.md` has a two-row table of the per-verb normalizations.
- **Exit codes.** `FixturePlayer` now answers the exit code the README row records, as the 2b-i
  Proposal asked. For an `unrecorded` exit it refuses unless the test names the code it assumes
  (`assumed_exits=`). The one assumption in the suite is `ASSUMED_DRY_RUN_EXIT = {…: 0}` in
  `tests/test_carry_bale.py`, with a comment saying so.
- **stderr.** No row records stderr. The player answers stderr empty, and the README says so.
  Adding a stderr column waits for a recording that has stderr to put in it.

## How bale is found, and how the tests keep a real bale out

The executable is `<root>/bin/bale`, with the root resolved exactly as `bale check` resolves it:

1. `--bale-root` (new on both verbs);
2. else `TWINE_BALE_ROOT`;
3. else `command -v bale`, followed to its real path and up to the install root.

That reuse is the isolation. `run_cli` already pins `TWINE_BALE_ROOT` to a missing directory, so
under the CLI tests the new verbs try `/…/no-bale-here/bin/bale`, fail to start it, and refuse.
Two places prove a PATH bale is never run: `FindingBale.test_a_bale_on_path_is_never_run_by_the_cli_tests`
and a `validation.sh` check. Each puts a `bale` on PATH that would touch a marker, and requires
that the marker never appears **and** that both verbs ran and refused with "could not be
started", so the check cannot pass vacuously.

Whether `bin/bale` exists is learned by starting it. A `RunError` is a refusal with `ran: false`,
not a separate existence check.

The installed `bin/VERSION` is reported beside the pin and said on stderr when it differs. It is
**not** gated on: the operator runs the bale they have. Please ratify.

Within the suite, bale is always one of three doubles:

- the fixture player;
- `BaleDouble`, a canned `RunResult`, defined and named in the test file;
- `StubBale`, a `bin/bale` bash script that `tests/helpers.py` writes into a temp root. It replays
  given bytes and records its argv, cwd and stdin. Tests pass it as `--bale-root`, which drives the
  real seam end to end in a subprocess.

`validation.sh` writes its own stub the same way under a `mktemp -d` that it removes.

## Which doubles stand in for what is unrecorded

- **`bale relay`'s stdout.** The crafter's `--emit-block` emission stands in, per TARBALL.md
  §5.9.2. It is also the block the worker hands the courier, so in the happy-path tests the stdin
  and stdout bytes are the same file. That is a weak spot: no test sees a relay reply that differs
  from what went in. A recording fixes it (see Proposals).
- **Non-zero exits, refusals, HOLDs, timeouts.** These use `BaleDouble` and the `StubBale` exit
  codes. The JSON in those doubles (`{"outcome": "refused"}`, `{"outcome": "hold"}`) is invented
  and labelled as a double. Twine reads only `outcome` from it, and how bale really spells a
  refusal is unknown.
- **The consumption manifest says the same, as data.** The new `relay` verb surface has no
  `fixture`; instead it has `stand_in` and `doubles`. The `apply` surface lists its `doubles` too.
  `test_consumption_manifest` requires that a fixture-less surface name a stand-in, and that the
  file the naming rule would give does **not** exist. So recording `relay_sid_stdin.txt` turns
  that test red until the entry points at the recording.

## Readings of the brief I had to make (please ratify)

1. **`tarball` is null unless the named file exists.** I read "null when refused before resolving
   one" as "resolving the name to an existing file". When the file is missing, the absolute path
   that was tried is named in `reason`. A directory is refused as "not a file".
2. **`--cwd DIR` and `--bale-root DIR` on both verbs.** Neither is in the brief. `--cwd` defaults
   to the current directory, which is the brief's rule; it exists so the shell and the tests can
   name the repo explicitly, the way `carry probe --cwd` does. `--bale-root` mirrors `bale check`.
   The JSON reports both (`cwd`, `bale.source`).
3. **A sentinel sid that could read as a flag is refused before relay.** This refusal is not in
   the brief's list. The sha256 trailer covers the body, not the `BALE EXCHANGE BEGIN <sid>` line,
   so an intact block could name `--no-interact` as its sid, and bale's argparse would read it as
   a flag. The rule is a floor, not bale's sid grammar: the sid must start with a letter or digit
   and contain only letters, digits, `.`, `_` and `-`. The tarball path needs no such guard,
   because it is absolute and starts with `/`.
4. **"One JSON object" means `json.loads` of the whole stdout gives a dict.** Two JSON lines fail,
   and so does a `[bale] …` line before the object. A pretty-printed object over several lines
   would pass. I saw no reason to be stricter than the brief.
5. **`carry exchange` does not inspect bale's reply.** ok is exactly exit 0, as the brief says.
   It would be easy to report whether the reply parses as an intact exchange block, but that adds
   a judgment the brief didn't ask for. Proposed below instead.
6. **Human mode.** On ok, `carry exchange` prints bale's stdout exactly, adding a final newline
   only if bale's output lacked one; `carry response` prints exactly the apply line. bale's stderr
   is echoed to twine's stderr in both modes, with a `[twine] bale's stderr follows` line before
   it.
7. **Timeouts and caps.** Neither is in the brief: 300 s and 4 MiB of stdout per bale call. A call
   past either is killed and reported (`timed_out`, `capped`) and is not ok. Neither verb is
   long-running, so these bound a stuck bale and nothing else.
8. **`test_json_discipline` changed one rule.** Its human-mode check forbade any stdout line that
   starts with `{`. `carry exchange` prints bale's paste block, whose body is JSON, so the check
   now forbids the JSON *twin* (an object with `command` and `ok`) for every verb, and keeps the
   old `{` rule for every verb except `carry exchange`.
9. **The `confined` Proposal: prepared, not built.** `twine.process.runner_confines(runner)` reads
   a runner's declared `confines`. `run_process.confines = False`, and an undeclared runner is
   false. `carry probe` sets `confined` from `runner_confines(ctx.run)`, and the literal `False`
   is gone from `carry.py`. Every Arc 1 result still reports false. Arc 2's wrapper declares
   `confines = True`, and nothing else infers the flag.
10. **The relay `[[wanted]]` entry.** Its `needed_by` now says 2b-ii landed without
    `relay --json`, passing stdout through as text. It still names 2b-ii, so the existing test
    holds.

## Places to look closely

- `twine/commands/carry_bale.py`, `call_bale`. This is where a `RunError` becomes a refusal and a
  killed or non-zero run becomes a failure. It is also why `ran` and `refusals` can disagree in
  one direction only: a bale that cannot be started has `ran: false` and lands in `refusals`.
- `tests/helpers.py`, `fixture_key` and `fixture_relpath`. When the argv contains no `Role`,
  `fixture_relpath` normalizes it first. Every existing name is unchanged; the manifest walk and
  `test_process`'s player test confirm it.
- `twine/bale.py` §5, the only argv builders.

## Validation

`validation.sh` ran twice, as TARBALL.md §7.2 asks.

**On a staged tree** (the base with `files/` overlaid, `apply.sh` run, and the manifest placed at
`.bale-manifest.json`): exit 0, every check `[PASS]`, and the claim reconciled `[agree]`. The run
takes about 12 s, most of it the suite. Afterwards the staged tree matched my working tree byte
for byte, apart from the `.validation-logs/` directory it announces.

**On the unmodified base:** exit 1. Every session-specific assertion `[FAIL]`s:

- `VERSION`;
- the fixture;
- both `carry response` checks and the three `carry exchange` checks;
- PATH isolation;
- T12;
- contract §11;
- `carry_bale.py`'s index header;
- syntax and parse, because the new files are absent.

These pass on both trees, as invariants should:

- the suite (the old suite is green on the old tree);
- "the sibling's forecast is not in this change set";
- no bytecode;
- the index headers of `bale.py`, `process.py` and `carry.py`. They were coherent before this
  session and still are after its edits.

The `claims` block holds one claim, the suite: `pass`, observed. The session-specific assertions
are listed in `validation_will_run` but not claimed, because a project-level check exists
(TARBALL.md §5.3).

## Proposals

### Record bale's unrecorded outputs with one read-only probe

**What.** One probe, run in `~/twine-src`, that captures:

- `bale relay <sid>` with **no** file argument for a session that has a thread. Per TARBALL.md
  §5.9.2 this re-emits the latest round and records nothing, so it is read-only.
- `bale apply --dry-run --json` on a deliberately malformed tarball: the refusal JSON and its exit
  code.
- The exit code and stderr hash of the clean dry run, re-run on any open session's response.

**Why.** Today relay's real output, every refusal, and the dry run's exit code are doubles or
assumptions. The manifest's relay surface and `ASSUMED_DRY_RUN_EXIT` mark exactly what a recording
would replace. The re-emit form is `relay <sid>`, not `relay <sid> -`, so it needs its own
normalized name (`relay_sid.txt` by the current rule).

**Scope hints.** `fixtures/`, `fixtures/README.md` (a stderr column then has something in it),
`share/bale-consumption.toml`, and `tests/test_carry_bale.py`'s doubles. This only works if a
session with a thread exists.

### `carry exchange` could report what it was handed back

**What.** Read bale's stdout with `twine.shapes` and add a non-gating `reply` object to the JSON
twin (kind, sid, round, from, integrity).

**Why.** The courier carries that block next. Knowing it is intact before the paste is the same
courtesy `carry probe` gives its paste-back. I left it out because the brief fixes ok as exit 0.

**Scope hints.** `twine/commands/carry_bale.py` and contract §11.2. Wait until relay's output is
recorded, so the test reads real bytes.

### INDEX entry for the contract page (the sibling tidy session's file)

**What.** `claude/INDEX.md`'s entry for `context/cli-contract.md` could mention two things. First,
§11: the bale hand-offs (`carry exchange`, `carry response`), how bale is found, T12's one `apply`
argv. Second, the per-run fixture names. The `fixtures/README.md` entry could gain "per-run values
named by role; exit codes, `unrecorded` where not captured".

**Why.** The INDEX describes the contract as ending at `carry probe` and the run seam. I didn't
edit it because it is the open `twine-seed-tidy` session's forecast.

**Scope hints.** `claude/INDEX.md` only, after `twine-seed-tidy` lands.

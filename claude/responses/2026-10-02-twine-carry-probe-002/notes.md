# notes — 2026-10-02-twine-carry-probe-002 (Arc 1 session 2b-i)

`twine carry probe` and the run seam. Everything is inside the write
forecast, so there are no departures to admit. `twine-seed.md` and
`bale.toml` are untouched. No bale verb is called anywhere. No probe
was needed: the session is hermetic, as the brief predicted.

## The seam's signature, and why

```
ctx.run(argv, *, cwd=None, stdin=None, timeout=None, env=None, stdout_cap=None)
    -> RunResult(argv, exit_code, stdout, stderr, timed_out,
                 stdout_capped, stderr_truncated, duration_seconds)
```

It lives in `twine/process.py`. The default is `run_process`, and the
field is `Context.run`. Spawn failures raise `RunError` (an `OSError`).
Everything after the spawn comes back as a `RunResult`. Handlers never
import `subprocess`, and `test_process.py` asserts that for every module
under `twine/commands/`.

I added two parameters beyond the brief's list:

- **`env`**, so handlers pass `ctx.env` explicitly and the injected
  environment in tests is the one the child sees.
- **`stdout_cap`**, because a cap has to be enforced *while reading*. A
  probe that runs `yes` would otherwise fill memory long before the
  timeout. Capping after the fact doesn't bound anything.

`exit_code` is `None` whenever the runner killed the child (timeout or
cap). That matches the brief's "null when it did not run or was
killed".

## The cap

**262144 bytes (256 KiB) of stdout.** The largest probe output recorded
so far is the specimens paste at 37,521 bytes, so this is about seven
times that. It is still something a person can carry. When a run
passes the cap, the group is killed immediately rather than drained
until the timeout. The run then reports `capped: true` and
`exit_code: null`, and it is not ok. stderr gets its own 64 KiB
retention cap, but it keeps being drained past that, so a chatty probe
never blocks on a full pipe. The number appears in the contract page,
in `--help`, in the JSON (`stdout_cap_bytes`) and in the reason when
the cap bites. `validation.sh` checks that the contract's number equals
the code's.

## How the timeout reaches children

Each child starts with `start_new_session=True`, so it leads its own
process group. The runner sends SIGKILL to the **group** (`os.killpg`)
in three cases:

- the deadline passes;
- stdout passes the cap;
- the script itself exits.

The third case is the one worth reviewing. Without it, a probe that
runs `sleep 30 &` and exits leaves the sleep holding our stdout pipe,
and the run would hang until the timeout. With it, nothing a probe
backgrounded outlives the probe. After the kill, the runner waits up to
2s for the pipes to reach EOF.

What this can't reach: a grandchild that calls `setsid` itself leaves
the group. The runner logs that, closes its ends of the pipes after the
grace period, and moves on. It is not a sandbox, and the contract says
so in §10.5.

The tests check it twice:

- **The seam:** `bash -c 'sleep 30 & echo $!; wait'` with a 1s timeout.
- **The verb:** a fixture-derived probe whose body backgrounds
  `sleep 60` and records its pid, run with `--timeout 1`.

Both assert the run returns promptly and that the sleep is gone. In
this container PID 1 never reaps orphans, so a killed sleep lingers as
a zombie. `process_alive` therefore treats state `Z` as dead.

## Decisions to ratify

1. **The readiness refusals apply with or without `--run`.** I read
   "Refused before running, even with `--run`" as "these hold
   regardless; not even `--run` gets past them". So an unfilled scaffold
   shown without `--run` is exit 1, refused. Its header and script are
   still reported in the JSON. The other reading would let a block
   report `ok: true` and then refuse once `--run` is added, which seemed
   worse for a shell keying on `ok`. The manifest's constraint only
   requires the `--run` half, and both readings satisfy that.
2. **`--out` is written only when the run is ok.** I read "when the run
   produced one" as "produced *the paste-back*", which is defined as
   the verified block. An unverified block in an operator-named file
   looks carry-able when it isn't. The write uses exclusive create
   (`open(…, "xb")`), so a file that appears mid-run is refused rather
   than clobbered.
3. **Human-mode stdout.** Without `--run`, stdout is exactly the script,
   so `carry probe f > p.sh` gives the bytes `--run` would run. With
   `--run` and ok, stdout is exactly the paste-back. With `--run` and
   not ok, stdout is one `NOT OK — reason` line, never the unverified
   block. That block stays in the JSON twin's `output`, and the script's
   stderr goes to stderr.
4. **How bash gets the script.** It runs as
   `bash -c <script> twine-probe-<slug>` with stdin `/dev/null`. This
   writes no temp file, so `--out` stays the only write. It also means a
   probe that reads stdin can't consume its own script, and `carry
   probe -` having consumed our stdin doesn't matter. Linux caps a
   single argv string at 128 KiB, so a larger script fails to spawn.
   That surfaces as a refusal ("bash could not be started"), never a
   traceback. Real probes are about 2 KB.
5. **The header** is the script's leading run of `#` lines, including
   the shebang. A `# Read-only:` line with nothing after the colon
   declares nothing, and is refused.
6. **Parsing stayed in `twine.shapes`.** It gains `probe_header`,
   `probe_read_only_line`, the `PROBE_READ_ONLY` / `UNFILLED_SENTINEL`
   constants, and `block_text`, which returns a block's own lines as a
   courier carries them. `carry.py` parses nothing itself.
7. **Other blocks in a probe's stdout don't fail the run.** The rule
   counts only `probe-output` blocks. A probe that also prints, say, a
   light block is judged on its `probe-output` alone. I couldn't find a
   reason to be stricter than the brief.
8. **§4.4 file-based probes** aren't built for. One prints no
   `probe-output` block, so it is ran-but-not-ok
   (`test_no_output_block_at_all`).

## Places to look closely

- `twine/process.py` `_collect`: the select loop, the three kill points,
  and the grace break.
- `twine/commands/carry.py` `cmd_carry_probe`: the order is read →
  choose → readiness → (only on `--run`) run → verify → `--out`.
  `test_the_seam_is_never_called_without_run` and the refusal tests
  assert the seam's call list is empty.
- The JSON twin carries the seven fixed keys plus `block`, `capped`,
  `stdout_cap_bytes`, `reason`, `refusals`, `header`, `script`,
  `run_requested`, `cwd`, `timeout_seconds`, `duration_seconds`,
  `stderr`, `stderr_truncated`, `out`, and `input`. When nothing ran,
  `integrity` is still an object: `ok: false` with an `error` saying so.

## Validation

I ran it twice:

- **On the staged tree** (base copy with `files/` overlaid): exit 0,
  every check `[PASS]`. The claims reconciliation and the INDEX-coverage
  half `[SKIP]` outside bale staging, as designed.
- **On the unmodified tree:** exit 1. Every carry-probe assertion, the
  version, the contract page, the manifest row and the two new
  index-header targets `[FAIL]`.

Some checks pass on both trees, and that's expected:

- the unittest suite (the old suite is green on the old tree);
- the seed's sha256;
- no bytecode;
- INDEX entries resolving;
- the index headers of `shapes.py` and `cli.py`, which were already
  coherent and still are after this session's edits.

These are invariants the brief pins ("untouched", "no bytecode", the
suite passes), so they can't fail on the base. They guard against this
change breaking them.

Every probe `validation.sh` runs is derived at run time from the
crafter fixture by the same mechanical fill the tests use. It writes
only under `.validation-logs/<ts>/` and a `mktemp -d` directory it
removes on exit, and it says so first. The whole run takes about 14s.
The suite (154 tests, 101 before) takes about 10s of that, mostly the
real timeout and cap runs.

## Proposals

### 2b-ii: key the fixture player on a normalized argv, not the raw one

**What.** `FixturePlayer` (in `tests/helpers.py`) answers
`fixture_relpath(argv[1:], where)`. That works for `bale status --json`.
It breaks for 2b-ii's two verbs, because their argvs carry per-run
values:

- `bale relay <sid> -` carries a session id. I suggest keying it as
  `relay_sid_stdin`, since the sid is in the block and the fixture
  doesn't need it.
- `bale apply --dry-run --json <tarball>` carries a temp path. I suggest
  keying the tarball by its basename, or by a role token
  (`apply_--dry-run_--json_tarball`).

The player should take a small normalizer (argv → key argv) that 2b-ii
writes per verb. `fixtures/README.md` would record the normalization
beside each row.

**Why.** A raw-argv key would mint a new fixture name per sid or temp
dir, and `fixture_relpath` would happily compute a path that never
exists.

**Scope hints.** `tests/helpers.py` `FixturePlayer` and
`fixture_relpath`; `fixtures/README.md`'s naming rule; the recording
probe for `bale relay` and `bale apply --dry-run --json`.

### 2b-ii: record exit codes and stderr beside stdout fixtures

**What.** Have the recording probe print each command's exit code and a
stderr hash, and land them in a sidecar or in the README row. The
player would then return those instead of the assumed 0 / empty.

**Why.** `bale apply --dry-run --json` on a HOLD exits non-zero. 2b-ii
must distinguish that from a refusal. Today's fixtures (all exit 0)
can't express it, and the player answers exit 0 for everything.

**Scope hints.** The recording probe; `FixturePlayer`; the
`fixtures/README.md` table already has an exit column to read from.

### 2b-ii: pass stdin bytes through the seam for `bale relay -`

**What.** Use `ctx.run(["bale", "relay", sid, "-"], stdin=block_bytes)`
with `block_bytes = shapes.block_text(text, block).encode()`. That's
the exchange block's own lines, sliced the way `carry probe` slices its
paste-back, per 2a's proposal.

**Why.** The seam already feeds stdin from a thread and closes it, and
`block_text` already produces the exact carried bytes, so 2b-ii needs
no new plumbing.

**Scope hints.** `twine/commands/carry.py` (`carry exchange` beside
`carry probe`); `twine.shapes.block_text`.

### Arc 2: `confined` needs one switch point

**What.** When the sandbox lands, have it wrap the argv inside a runner,
for example `run_confined = wrap(run_process, policy)`. `carry probe`
would choose the runner and set `confined` from which one it chose. The
flag shouldn't be inferred anywhere else.

**Why.** `confined` is a literal `False` in `Outcome.payload` today. A
runner-level switch keeps the claim and the mechanism in one place.

**Scope hints.** `twine/process.py`, `Context.run`, and
`twine/commands/carry.py` `Outcome.payload`.

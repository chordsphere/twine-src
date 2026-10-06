# twine

twine is the process layer of the Nisaba suite: the harness that
carries bale sessions between a planner and a worker, hosts the
sessions a model runs, and — later — spawns sessions from what the
office declares. Three faces, one core: the **courier** (moves bale's
four shapes and applies, relays and runs them), the **runtime** (hosts
a session: the model-call loop, the tool surface, the sandbox, window
accounting, the cost spine and kill-switch, the model adapters), and
the **scheduler** (reads the drafting-table, opens bundles, dispatches
to the runtime or to a person, enforces the cap). Headless; holds no
intent; rendered by the Nisaba shell.

## What exists

Arc 1 (the courier) session 1 landed twine's core:

- `bin/twine` — the CLI. One command registry (`twine/registry.py`)
  is the single source for the verbs; argparse, `--help` and
  `twine commands` are rendered from it, and every verb has a `--json`
  twin that emits exactly one JSON object line on stdout.
- Verbs: `commands` (list the registry), `status` (twine's own facts —
  since session 5c also where its state directory resolves, whether it
  exists, and whether `spend.jsonl`, `prices.toml`, `abort/` and
  `running/` are in it; it never creates the directory),
  `bale check` (the installed bale's `bin/VERSION` against the pin),
  and `take` (session 2a): read a pasted turn, find each bale shape in
  it — probe, probe output, light block, exchange block, relay block —
  verify its integrity trailer and report, executing nothing.
- `carry probe` (session 2b-i): show the probe block in a pasted turn;
  only on an explicit `--run`, run it with bash (unconfined — your
  privileges and network — with a timeout that kills its children and a
  256 KiB output cap) and print the verified paste-back.
- `carry exchange` and `carry response` (session 2b-ii): the bale
  hand-offs. `carry exchange` hands the exchange block in a pasted turn
  — only an intact one, exactly its own lines — to `bale relay <sid> -`
  and prints the block bale hands back. `carry response` runs
  `bale apply --dry-run --json` on a response tarball and, on a clean dry
  run, prints the one `bale apply <path>` line for you to run. twine
  never applies anything itself: the merge stays yours. Both drive only
  the pinned bale: a `bin/VERSION` other than the pin, or one that
  cannot be read, is refused before bale starts (D2).
- `transitions` (session 4): the transition table (D17), as data in
  `share/transitions.toml` — bale 0.4.45's 13 telemetry outcomes, 9
  closure reasons and the 9 outcomes `bale apply --json` prints, plus
  twine's own stop set for the runtime, each with a move: what happens
  next and who does it (twine, the operator or the planner). No default
  case. `twine transitions` renders it and is ok only when every key of
  every axis has a row and every row's move is declared; it reads no
  bale install.
- `spend totals` and `spend check` (session 5a): the cost spine (D15).
  Twine's usage record is an append-only stream,
  `spend.jsonl` in twine's state directory (`--state-dir`, else
  `$TWINE_STATE_DIR`, else `${XDG_STATE_HOME:-$HOME/.local/state}/twine`
  — never inside a project's tree): one line per model call, tokens by class
  (input, output, thinking, cache read, cache write), and a reserved
  `served_sid` for spend that served another session. `spend totals`
  renders the running totals per session; `spend check` is the hard cap's
  pre-call check — it admits a call only if the session's spend so far plus
  the call's worst-case cost is at most the cap, and otherwise refuses with
  `stop: "cap-reached"`, never shrinking the call to fit; a check that cannot
  run at all (an unpriced model, a broken stream, no price file) refuses
  with `stop: "cap-unchecked"`, whose remedy is to fix the named fault, not
  to raise the cap. **twine ships no
  prices**: you write them, per model, in `prices.toml`, and an unpriced
  model is a refusal, never an estimate. No provider's usage has been
  recorded yet (the gated probe `twine-usage-record` will), so the spine
  reads only twine's own record; mapping a provider onto it is Arc 2's.
- `kill` (sessions 5b and 5c): the kill-switch (D15), in three layers.
  `twine kill <sid>` requests the **between-calls abort** — a file in
  twine's state directory, `abort/<sid>.json`, that the runtime's loop will
  check before every model call; it survives the runtime's death. Then the
  **process-level kill**: if the session's runtime recorded its process
  groups (`running/<sid>.json` — its own group, and every group it started
  since, registered by the run seam's spawn hook the moment a tool
  exists), twine signals each of them — the runtime's first, then the rest
  in order; SIGTERM, then SIGKILL after `--grace` seconds — and waits until
  no member of any of them is alive, or names the survivors and stops; it
  re-reads the record once for a group registered while it ran. The state
  directory must be the runtime's and must exist: a kill never creates
  one, because an abort written where the runtime does not look stops
  nothing (`twine status` says which directory twine resolves). Then, only
  when nothing of the session is still running, the **`aborted` closure**:
  twine runs exactly `bale unlock <sid> --reason aborted --json`, with the
  pinned bale, once, so the kill leaves a durable record in bale. The abort
  and the kill run with any bale or none — a kill-switch must work when
  the harness is wedged, and an install drifted off the pin is one way it
  can be; only the closure needs the pin, and without it the kill stops
  there and hands you the unlock line. When it cannot finish, it says where
  it stopped and prints the one line that finishes by hand — the signal for
  every group with survivors, the unlock line, or, for a session that
  reached HOLD, bale's own `bale revert <sid>`, which stays yours: twine
  never reverts, merges or applies anything. Nothing records a running
  group yet (the runtime is Arc 2's), so today a kill requests the abort
  and closes the session.
- `share/bale-consumption.toml` — the bale version pin (`0.4.45`) and
  the consumption manifest: the schema hashes, every bale surface
  twine reads, and the three vocabularies the transition table keys on,
  as data.
- `fixtures/` — recorded `bale … --json` outputs from the pinned
  version, the crafter's emissions, and carried pastes of bale output,
  byte-exact; the only bale the tests ever see.
- `tests/` — the stdlib `unittest` suite.

Stdlib only; python 3.11 or newer. The courier reads (`take`), runs a
probe with consent (`carry probe`), relays an exchange block (`carry
exchange`) and dry-runs a response (`carry response`), and its
transition table names a move for every outcome bale reports and every
way a runtime turn will stop. The cost spine records spend, totals it and
checks the hard cap before a call, and the kill-switch can stop a session
from outside and close it `aborted`; nothing makes a call yet. twine does
not yet emit requests (Arc 1 session 3) or dispatch on the table, and there
is no model adapter or sandbox (Arc 2).

## Running it

```
python3 -I -S bin/twine --help
python3 -I -S bin/twine --version
python3 -I -S bin/twine commands --json
python3 -I -S bin/twine status [--state-dir DIR]              # twine's facts; where its state lives
python3 -I -S bin/twine bale check --json [--bale-root DIR]
python3 -I -S bin/twine take turn.txt --json     # or `take -` to read stdin
python3 -I -S bin/twine carry probe turn.txt               # show the probe; runs nothing
python3 -I -S bin/twine carry probe turn.txt --run > paste.txt   # run it; stdout is the paste-back
python3 -I -S bin/twine carry exchange turn.txt > next.txt       # relay the block; stdout is bale's reply block
python3 -I -S bin/twine carry response response-<sid>.tar.gz     # dry-run it; stdout is the `bale apply` line
python3 -I -S bin/twine transitions [--json]                     # the transition table; ok when it is total
python3 -I -S bin/twine spend totals [--sid SID] [--json]        # spend per session, at your prices
python3 -I -S bin/twine spend check --sid SID --cap USD --model M --input N --max-output N   # admit or refuse one call
python3 -I -S bin/twine kill SID [--grace SECONDS] [--json]     # abort, kill its process groups, close it `aborted`
```

`-I -S` (isolated, no site-packages) is how the entrypoint is meant to
run and how a reviewer checks the stdlib-only claim; plain
`bin/twine …` works too. `bale check`, `carry exchange`, `carry
response` and `kill` find the install from `--bale-root`, else `$TWINE_BALE_ROOT`,
else `bale` on `PATH`; the two carry verbs and `kill` run bale in the
current directory (or `--cwd`), which should be the repo whose session
they carry or kill; `kill` writes its abort request in the state
directory below. The spend verbs read twine's state directory and never write
it; the price file is yours to write there (or name with `--prices`):
one `[model."<id>"]` table per model with `input`, `output`, `cache_read`
and `cache_write` in US dollars per million tokens. The
interface each verb promises — the `--json` discipline, the exit
codes, the keys — is [`claude/context/cli-contract.md`](claude/context/cli-contract.md).

## Running the tests

From the repository root:

```
python3 -B -m unittest discover -s tests -t .
```

No network, no bale install, no third-party module (bash is needed —
`carry probe`'s tests run real probe scripts): `bale check` is
exercised against temp roots the tests build, and the recorded
outputs under `fixtures/` — with doubles, named as such, for the bale
outputs nobody has recorded yet — stand in for a live bale. A `bale` on
your `PATH` is never the one a test runs.

## Where things are

The spec lives in [`twine-seed.md`](twine-seed.md): identity, the
sitting's rulings (T1–T14), the carried inputs from tedder-src's
`harness-seed.md` (D1–D24, with this repo's status on each), the
runtime's design, the road (three arcs), and the open questions. Every
later answer about twine accretes there. The doc map is
[`claude/INDEX.md`](claude/INDEX.md).

Where twine sits: Nisaba is one shell over three cores with
dependencies pointing strictly downward — bale carries sessions and
depends on nothing; office declares what a session carries and holds
a project's progression, and depends on bale; twine drives bale's
verbs and reads office's declarations, and depends on both; the shell
renders all three and depends on twine only optionally. The diagram
and the definitions are `nisaba-seed.md` §1 in nisaba-src, which this
repository points at rather than copies.

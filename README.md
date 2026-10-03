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
- Verbs: `commands` (list the registry), `status` (twine's own facts),
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
  never applies anything itself: the merge stays yours.
- `share/bale-consumption.toml` — the bale version pin (`0.4.45`) and
  the consumption manifest: the schema hashes and every bale surface
  twine reads, as data.
- `fixtures/` — recorded `bale … --json` outputs from the pinned
  version, the crafter's emissions, and carried pastes of bale output,
  byte-exact; the only bale the tests ever see.
- `tests/` — the stdlib `unittest` suite.

Stdlib only; python 3.11 or newer. The courier reads (`take`), runs a
probe with consent (`carry probe`), relays an exchange block (`carry
exchange`) and dry-runs a response (`carry response`), but does not yet
emit requests (Arc 1 session 3); no transition table (4), no cost spine
(5), no model adapter or sandbox (Arc 2).

## Running it

```
python3 -I -S bin/twine --help
python3 -I -S bin/twine --version
python3 -I -S bin/twine commands --json
python3 -I -S bin/twine status
python3 -I -S bin/twine bale check --json [--bale-root DIR]
python3 -I -S bin/twine take turn.txt --json     # or `take -` to read stdin
python3 -I -S bin/twine carry probe turn.txt               # show the probe; runs nothing
python3 -I -S bin/twine carry probe turn.txt --run > paste.txt   # run it; stdout is the paste-back
python3 -I -S bin/twine carry exchange turn.txt > next.txt       # relay the block; stdout is bale's reply block
python3 -I -S bin/twine carry response response-<sid>.tar.gz     # dry-run it; stdout is the `bale apply` line
```

`-I -S` (isolated, no site-packages) is how the entrypoint is meant to
run and how a reviewer checks the stdlib-only claim; plain
`bin/twine …` works too. `bale check`, `carry exchange` and `carry
response` find the install from `--bale-root`, else `$TWINE_BALE_ROOT`,
else `bale` on `PATH`; the two carry verbs run bale in the current
directory (or `--cwd`), which should be the repo whose session they
carry. The
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

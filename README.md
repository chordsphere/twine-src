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
  `bale check` (the installed bale's `bin/VERSION` against the pin).
- `share/bale-consumption.toml` — the bale version pin (`0.4.45`) and
  the consumption manifest: the schema hashes and every bale surface
  twine reads, as data.
- `fixtures/` — recorded `bale … --json` outputs from the pinned
  version, byte-exact; the only bale the tests ever see.
- `tests/` — the stdlib `unittest` suite.

Stdlib only; python 3.11 or newer. No courier verbs yet (sessions 2
and 3), no transition table (4), no cost spine (5), no model adapter
(Arc 2).

## Running it

```
python3 -I -S bin/twine --help
python3 -I -S bin/twine --version
python3 -I -S bin/twine commands --json
python3 -I -S bin/twine status
python3 -I -S bin/twine bale check --json [--bale-root DIR]
```

`-I -S` (isolated, no site-packages) is how the entrypoint is meant to
run and how a reviewer checks the stdlib-only claim; plain
`bin/twine …` works too. `bale check` finds the install from
`--bale-root`, else `$TWINE_BALE_ROOT`, else `bale` on `PATH`. The
interface each verb promises — the `--json` discipline, the exit
codes, the keys — is [`claude/context/cli-contract.md`](claude/context/cli-contract.md).

## Running the tests

From the repository root:

```
python3 -B -m unittest discover -s tests -t .
```

No network, no bale install, no third-party module: `bale check` is
exercised against temp roots the tests build, and the recorded
outputs under `fixtures/` stand in for a live bale.

## Where things are

The spec lives in [`twine-seed.md`](twine-seed.md): identity, the
sitting's rulings (T1–T10), the carried inputs from tedder-src's
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

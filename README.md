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
  exists, and whether `spend.jsonl`, `prices.toml`, `abort/`, `running/`
  and `inflight/` are in it — since 0.19.0 `transcripts/` and `sandbox/`
  too — and since 0.11.0 the sids whose in-flight records read there and
  every file in `inflight/` that is not one, named, and since 0.19.0 the
  sids of the transcripts and sandbox homes `twine run` keeps; it never
  creates the directory, and writes nothing),
  `bale check` (the gate, D2: since 0.14.0 a floor — ok when the
  installed bale's `bin/VERSION` is at or above the floor, `0.4.51`, and
  every schema the manifest pins is installed under `schemas/` with its
  sha256; each failing fact named otherwise),
  and `take` (session 2a): read a pasted turn, find each bale shape in
  it — probe, probe output, light block, exchange block, relay block —
  verify its integrity trailer and report, executing nothing.
- `carry probe` (session 2b-i): show the probe block in a pasted turn;
  only on an explicit `--run`, run it with bash (unconfined — your
  privileges and network — with a timeout that kills its children and a
  256 KiB output cap) and print the verified paste-back.
- `carry exchange` and `carry response` (session 2b-ii): the bale
  hand-offs. `carry exchange` hands the exchange block in a pasted turn
  — only an intact one, exactly its own lines — to `bale relay <sid> -
  --json`, reads the one line bale answers with, and prints the block it
  hands back, an intact one: a block it cannot vouch for is never printed
  (on a refusal, the reason quotes bale's cause). `carry response` runs
  `bale apply --dry-run --json` on a response tarball and, on a clean dry
  run, prints the one `bale apply <path>` line for you to run. twine
  never applies anything itself: the merge stays yours. Both drive only
  a bale the gate admits — exactly one `bale check` reports ok; one below
  the floor, whose `bin/VERSION` cannot be read, or whose schemas do not
  hash as pinned is refused before bale starts (D2) — and both check, on
  the line bale answers with, every key the consumption manifest lists
  for that surface: a line lacking one is not ok, the key named.
- `carry bundle` (session 3, the last courier row): carries a planner's
  bundle into bale. It runs `bale open <bundle> --json` itself — an open
  merges nothing, and an unwanted session is closed with `bale unlock` —
  once, never retried, and prints exactly bale's `opener`, the text you
  paste into the new chat; stderr names the request tarball to attach.
  `--check` rehearses with `bale open --check` and writes nothing. Each
  open is recorded in twine's state directory as
  `inflight/<sid>.json` — the sid, where bale ran, the request tarball,
  and one entry per desk — so a second desk on the same session (bale's
  `second-desk`) is handed the request tarball: bale's own when its line
  names one (bale 0.4.50 on), else the record's. Since 0.15.0 the record
  keeps that tarball too: a second desk's fresh record holds bale's, and
  an appended one keeps its own or, holding none, adopts bale's. The
  record is a cache of what bale printed; nothing removes it yet. A
  refusal bale prints (`open-refused`, bale 0.4.50 on) is NOT OK, naming
  bale's reason code and quoting its cause; nothing is recorded. Without
  `--check` an open is refused unless a state directory
  resolves (an open that could not be recorded is refused before it
  happens); the same gate and the same key check on bale's line as the
  other carry verbs.
- `transitions` (session 4): the transition table (D17), as data in
  `share/transitions.toml` — the 13 telemetry outcomes of the bale at the floor, 9
  closure reasons and the 9 outcomes `bale apply --json` prints, plus
  twine's own stop set for the runtime, each with a move: what happens
  next and who does it (twine, the operator or the planner). No default
  case. `twine transitions` renders it and is ok only when every key of
  every axis has a row and every row's move is declared; it reads no
  bale install. Since Arc 2 R2 (0.17.0) the stop set has fifteen keys —
  `request-refused` (the provider refused the request; the operator fixes
  it, nothing is retried) and `provider-error` (retried with backoff) are
  new — and names its three `loop_keys` (`cap-reached`, `cap-unchecked`,
  `killed`: the loop's, never an adapter's); the table's
  `written_against` is the floor; and the table carries the first
  provider's mapping — every Anthropic stop reason, HTTP status and error
  type, and the conditions no provider word names, each onto a stop key —
  as `[[mapping]]` rows the adapter reads.
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
  model is a refusal, never an estimate. The spine reads only twine's own
  record; mapping a provider's usage onto it is the runtime's (since Arc 2
  R1, `from_anthropic`, below).
- `kill` (sessions 5b and 5c): the kill-switch (D15), in three layers.
  `twine kill <sid>` requests the **between-calls abort** — a file in
  twine's state directory, `abort/<sid>.json`, that the runtime's loop will
  check before every model call; it survives the runtime's death. Then the
  **process-level kill**: if the session's runtime recorded its process
  groups (`running/<sid>.json` — its own group, and every group it started
  since, registered by the run seam's spawn hook the moment a tool
  exists and forgotten by the loop once its run returns with none of it
  alive), twine signals each of them — the runtime's first, then the rest
  in order; SIGTERM, then SIGKILL after `--grace` seconds — and waits until
  no member of any of them is alive, or names the survivors and stops; it
  re-reads the record once for a group registered while it ran. The state
  directory must be the runtime's and must exist: a kill never creates
  one, because an abort written where the runtime does not look stops
  nothing (`twine status` says which directory twine resolves). Then, only
  when nothing of the session is still running, the **`aborted` closure**:
  twine runs exactly `bale unlock <sid> --reason aborted --json`, with a
  bale the gate admits, once, so the kill leaves a durable record in bale
  (and checks the line's listed keys, as the carry verbs do). The abort
  and the kill run with any bale or none — a kill-switch must work when
  the harness is wedged, and an install the gate refuses is one way it
  can be; only the closure needs the gate, and without it the kill stops
  there and hands you the unlock line. When it cannot finish, it says where
  it stopped and prints the one line that finishes by hand — the signal for
  every group with survivors, the unlock line, or, for a session that
  reached HOLD, bale's own `bale revert <sid>`, which stays yours: twine
  never reverts, merges or applies anything. Since R4 `twine run`
  registers its own group before it starts anything and the sandbox every
  tool's group, so a kill stops a hosted session's runtime and tools, then
  closes it.
- `runtime list` and `runtime show` (Arc 2 R1, 0.16.0; R2, 0.17.0): the runtime's
  first foundations, under `twine/runtime/`. Every runtime operation is a
  named **capability** with a declared contract — one module per
  capability under `twine/runtime/capabilities/`, listed by
  `twine/runtime/capabilities.toml` — eight of them: `tool-calling`,
  `thinking`, `usage-accounting`, `prompt-caching` and `streaming`
  *implemented* by the adapters, `sandboxing` *implemented* by the runtime
  itself since R3, and `window-accounting` and `suspend-resume` *declared*
  (their contracts written, nothing implementing them yet).
  `twine runtime list` renders the registry and is ok only when the
  declaration and the directory agree by name and every entry loads — a
  stray module or a missing one is named; `twine runtime show <name>`
  renders one capability's contract. Beside the registry sits the
  **adapter boundary** (`twine/runtime/boundary.py`): the interface a
  model adapter implements — tool calls, thinking fixed at spawn, usage as
  the cost spine's five token classes, and a stop that is always a key of
  the transition table's `stop` axis, read from the table and spelled
  nowhere else (and never one of the loop's keys). Two adapters are
  registered: `fake`, a scripted transport the tests drive and nothing
  else does, and since R2 **`anthropic`** — the Messages API over the
  standard library (no SDK), through a transport seam the tests feed
  recorded bytes and, in use, `twine/runtime/transport.py`, the only place
  twine opens a socket. It reads `ANTHROPIC_API_KEY` from the environment
  it is given and puts it in the `x-api-key` header and nowhere else;
  builds each request with three prompt-cache breakpoints; reads JSON and
  streamed answers alike; and maps every stop reason and error through the
  transition table's rows. It is held to fifteen exchanges the architect
  recorded on 2026-10-13 (`fixtures/anthropic/`), and `from_anthropic`, the
  usage mapping, to those and to the 2026-10-08 usage object. Since R4
  the loop calls it (`twine run`, below). The contract is
  [`claude/context/runtime-contract.md`](claude/context/runtime-contract.md).
- `runtime tools` (Arc 2 R3, 0.18.0): the **canonical tool surface** —
  `shell`, `read_file`, `write_file`, `list_dir`, `probe`, `escalate`,
  `deliver` — declared in `twine/runtime/tools.toml`, one module each under
  `twine/runtime/tools/`, held to each other by name as the capabilities
  are; `twine runtime tools` lists each with its description, input schema
  and whether it leaves the cage, and is ok only when the two agree. Every
  tool returns a result — a failure is a result with `is_error` true, never
  an exception. They run in a per-session **sandbox**
  (`twine/runtime/sandbox.py`): a home under the state directory,
  `sandbox/<sid>/home/`, to which every file path is confined (absolute
  paths, `..` and symlinks out refused); a minimal environment — `PATH`,
  `HOME`, `TMPDIR`, `LANG`, never `ANTHROPIC_API_KEY`; the network off
  through `unshare -rn` where this machine allows it, and said plainly
  where it does not (`network: "unconfined"`, the reason). `shell` runs
  `bash -c` there with a timeout that reaches its children and a 256 KiB
  stdout cap. Every process a tool starts is registered with the
  kill-switch's running record while it runs and cleared after, so
  `twine kill` reaches tools too. `probe` is the one tool that leaves the
  cage: it runs a read-only probe block against the real repository and
  returns the verified paste-back, as `carry probe --run` does; `escalate`
  emits a light question block and asks the loop to suspend; `deliver`
  names the response tarball the courier will carry. Since R4 the loop
  runs them.
- `run` (Arc 2 R4, 0.19.0): **the loop** — twine hosts a worker session
  from `bale open` to the apply line, and the operator stops being the
  courier on the worker side. Three lines:

  ```
  twine run planned.bale-bundle --model <model> --cap 5   # open, run the worker, dry-run its response
  bale apply <path>                                       # the line it printed — yours to run
  twine kill <sid>                                        # only if you want it stopped
  ```

  `twine run` opens the bundle (`carry bundle`), registers itself with the
  kill-switch, makes the session's sandbox and unpacks the request at
  `request/` in it, and hands the model the opener as its first turn under
  a system prompt that holds only the tools and a short note on where it
  is. Before every call it checks the abort file and the hard cap (`--cap`
  is required); after every call it appends the usage to `spend.jsonl`;
  every turn's move comes from the transition table — tools run in the
  cage, a cut-off turn continued, a rate limit retried with backoff, the
  final text read as `take` reads a paste. When the worker calls
  `deliver`, the tarball is dry-run with bale (`carry response`) and the
  `bale apply` line printed — twine never applies. `escalate` (or a light
  block in the final text) suspends the run and prints the block; anything
  else ends it with its stop and the move named. Every step is a line in
  `<state-dir>/transcripts/<sid>.jsonl`, append-only. `ANTHROPIC_API_KEY`
  reaches the model adapter and nothing else — not bale, not the cage, not
  a file. `--adapter fake --script FILE` runs the same loop with no model,
  from a scripted list of turns (how the tests drive it). Contract §18 and
  `runtime-contract.md` §7.
- `share/bale-consumption.toml` — the floor (`0.4.51`: twine drives any
  bale at or above it whose installed schemas hash as pinned — an exact
  pin until 0.14.0) and the consumption manifest: the schema hashes, every
  bale surface twine reads and the keys it reads from each (checked
  present on every line), and the three vocabularies the transition table
  keys on, as data. An install that moves without touching a listed key
  or a pinned schema needs nothing — 0.4.52 was the first, admitted with
  nothing re-recorded; one that does needs a recording session, which
  raises the floor (contract §6, §16).
- `fixtures/` — recorded `bale … --json` outputs from the floor's
  version (twenty-four at 0.4.51, each with the stderr bale printed beside
  it, including every outcome of `bale unlock --json` the kill-switch's
  tests replay, the four `bale open --json` lines `carry bundle`'s tests
  replay and `bale relay <sid> - --json` under twine's own argv), the
  crafter's emissions, and carried pastes of bale output — among them the
  recorder's paste-back the 0.4.51 recordings were landed from — and the
  eight `schemas/*.json` the gate hashes, under `fixtures/bale-0.4.51/schemas/`,
  byte-exact; the only bale the tests ever see. Earlier versions'
  recordings stay as history. Since Arc 2 R1, `fixtures/anthropic/` holds
  provider recordings under a rule of their own — the Messages API `usage`
  object `from_anthropic` is held to, and since R2 the wire of 2026-10-13:
  fifteen requests and responses (four of them streams), each with a meta
  file, and the probe's paste-back they were landed from.
- `bin/twine-record-fixtures` and `bin/twine-land-recordings` — the
  recorder and the lander a recording session runs: the probe that records every
  bale surface twine reads, stdout and stderr, and the tool that lands its
  paste-back under `fixtures/bale-<version>/` (or, with `--check`, proves
  the tree still holds exactly it). Not twine verbs; contract §16.
- `bin/twine-land-provider-recordings` (Arc 2 R2) — their sibling for a
  model provider's wire: lands a provider-recording probe's paste-back
  under `fixtures/anthropic/` (or, with `--check`, proves the tree and
  `fixtures/README.md`'s rows still hold exactly it).
  `runtime-contract.md` §5.9.
- `tests/` — the stdlib `unittest` suite.

Stdlib only; python 3.11 or newer. The courier reads (`take`), runs a
probe with consent (`carry probe`), relays an exchange block (`carry
exchange`), dry-runs a response (`carry response`) and opens a bundle
(`carry bundle`), and its
transition table names a move for every outcome bale reports and every
way a runtime turn will stop. The cost spine records spend, totals it and
checks the hard cap before a call, and the kill-switch can stop a session
from outside and close it `aborted`. The runtime (Arc 2) has its capability
registry, its adapter boundary, a fake adapter for the tests, the
Anthropic adapter, the seven canonical tools with the sandbox they run
in, and since R4 the loop, `twine run`, which performs the table's moves
for every way a turn stops.

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
python3 -I -S bin/twine carry exchange turn.txt > next.txt       # relay the block (bale relay <sid> - --json); stdout is bale's reply block
python3 -I -S bin/twine carry response response-<sid>.tar.gz     # dry-run it; stdout is the `bale apply` line
python3 -I -S bin/twine carry bundle <stem>.bale-bundle > opener.txt   # open it; stdout is the opener to paste
python3 -I -S bin/twine carry bundle <stem>.bale-bundle --check  # rehearse; nothing written
python3 -I -S bin/twine transitions [--json]                     # the transition table; ok when it is total
python3 -I -S bin/twine spend totals [--sid SID] [--json]        # spend per session, at your prices
python3 -I -S bin/twine spend check --sid SID --cap USD --model M --input N --max-output N   # admit or refuse one call
python3 -I -S bin/twine kill SID [--grace SECONDS] [--json]     # abort, kill its process groups, close it `aborted`
python3 -I -S bin/twine runtime list [--json]                    # the runtime's capabilities and adapters; ok when parity holds
python3 -I -S bin/twine runtime show NAME [--json]               # one capability and its declared contract
python3 -I -S bin/twine runtime tools [--json]                   # the canonical tools; ok when parity holds
python3 -I -S bin/twine run <stem>.bale-bundle --model M --cap USD [--json]   # host the worker; stdout is the `bale apply` line
python3 -I -S bin/twine run <stem>.bale-bundle --adapter fake --script turns.json --cap USD   # the same loop, no model
```

A recording session — needed only when an install moves a listed key or
a pinned schema, and it raises the floor (contract §16) — runs the two
maintenance tools beside them:

```
bin/twine-record-fixtures [SLUG] > paste-back.txt       # in ~/twine-src, the new bale on PATH: record every surface
python3 -I -S -B bin/twine-land-recordings paste-back.txt          # land it under fixtures/bale-<version>/, print the rows
python3 -I -S -B bin/twine-land-recordings fixtures/bale-0.4.51/carried/probe-output_twine-051-record.txt --check
python3 -I -S -B bin/twine-land-provider-recordings fixtures/anthropic/carried/twine-anthropic-record-2026-10-13.txt --check
```

`-I -S` (isolated, no site-packages) is how the entrypoint is meant to
run and how a reviewer checks the stdlib-only claim; plain
`bin/twine …` works too. `bale check`, `carry exchange`, `carry
response`, `carry bundle` and `kill` find the install from `--bale-root`, else `$TWINE_BALE_ROOT`,
else `bale` on `PATH`; the three carry verbs that run bale and `kill` run
it in the current directory (or `--cwd`), which should be the repo whose
session they carry, open or kill; `kill` writes its abort request, and
`carry bundle` its in-flight record, in the state directory below. The spend verbs read twine's state directory and never write
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
`carry probe`'s and the tools' tests run real scripts, and the sandbox's
use `unshare` where the machine has it, asserting either outcome): `bale check` is
exercised against temp roots the tests build, each carrying the schema
fixtures so the gate admits it as it admits your install, and the recorded
outputs under `fixtures/` — with doubles, named as such, for the bale
outputs nobody has recorded yet — stand in for a live bale. A `bale` on
your `PATH` is never the one a test runs. Nor does a test reach a model:
the Anthropic adapter's tests replay the recordings under
`fixtures/anthropic/`. The one live call is a smoke test you run by hand,
skipped unless both gates are open:

```
TWINE_LIVE_SMOKE=1 ANTHROPIC_API_KEY=… python3 -B -m unittest discover -s tests -t . -p test_anthropic_live.py -v
```

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

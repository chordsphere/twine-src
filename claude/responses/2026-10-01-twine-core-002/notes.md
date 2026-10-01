# notes.md — 2026-10-01-twine-core-002

Twenty-four files created, two modified (`README.md`, `claude/INDEX.md`),
all inside the whole-tree forecast; nothing deleted. One probe
(`twine-core-fixtures`, pre-build), no clarification, no light block.
Budget comfortable throughout; no compaction. 60 tests, all green here
(python 3.13) — your machine's 3.12.3 is inside the floor (see "Python
floor" below).

## The probe, and what it established

The brief's §6 named a `context-bale-src.tar.gz` for `bale_report.py`'s
key docstrings and the schema files; the request carried only the
eight `context/` paths the manifest lists (session 0 hit the same
gap). So the first turn ended on a probe that recorded the fixtures
and read those docstrings off your install with `ast` — parsing
source text, no bale code run, nothing imported (T10 is about twine's
code; a read-only probe on your machine is the sanctioned surface).
You ran it; the paste was complete (integrity trailer 665 lines,
matched) once I stripped the 667 CRLFs the chat added, as session 0's
worker did. What it established, the part this response relies on:

- **bale 0.4.45 at `/home/chordsphere/bale`**, `~/.local/bin/bale`
  → `~/bale/bin/bale` (readlink), `bin/VERSION` is `0.4.45\n` (7 bytes,
  sha256 `76b4e873…`). The eight `schemas/*.json` sha256s equal the
  brief's §4 values exactly; they are now `[bale.schemas]` in the
  consumption manifest.
- **The four fixtures**, byte-exact: `bale status --json` (1488 bytes),
  `bale stats --json` (8121), `bale stats --sid 2026-10-01-twine-seed-001
  --json` (4026), all run in `~/twine-src`, and `bale --version` (12
  bytes, `bale 0.4.45\n`) from `/tmp`. The probe printed `wc -c` and
  sha256 of the raw bytes beside each; the landed files match both
  after CRLF stripping, and `validation.sh` embeds the four hashes.
  Each JSON output is one line with a trailing newline, as bale emits
  it.
- **`bale open` has no `--json`** in 0.4.45 (`bale open [-h]
  [--verbose] [--no-sandbox] [--check | --dry-run] bundle`), and
  neither has `bale relay` (`bale relay [-h] sid [file]`). Both are
  `[[wanted]]` entries in the manifest.
- **The key contracts**, from the docstrings: `format_status_json`
  (outcome, version, sid, repo, session, staging, outbox, applied,
  sessions, scopes, integration_lock, config — the fixture carries
  all twelve), `format_stats_json` (outcome, epoch, coverage, filters,
  corpus, classes, closure_mix, churn, cross_checks, packers,
  doc_epochs, members), `format_session_dossier_json` (outcome,
  session_id, found, record, attempts, lineage). The manifest's
  `key_owner` fields point at them; `keys` is `[]` everywhere, since
  twine reads nothing from these yet.
- **twine-src at recording:** head `0c01dcb`, master, tag
  `applied/2026-10-01-twine-seed-001`; `claude/checkpoints/2026-10-01-twine-core-002.sh`
  tracked (the pack committed it); untracked
  `claude/telemetry/2026-09-29-begin-harness-001.json` and
  `claude/telemetry/2026-10-01-twine-core-002.json` — both bale's, left
  alone. The `status` fixture's `sid` is
  `2026-09-29-begin-harness-001`: bale's lock state names the
  *earliest* open session, not this one. Session 3's in-flight record
  should know that `sid` is not "the session I'm working on".

The probe output is chat-ephemeral; this section is its durable
record (TARBALL.md §4.5).

## Brief §4, checked

Nothing wrong. Python 3.12.3 at `/usr/bin/python3`; bale's path and
link; the schema hashes; `bale open`'s flag surface; the verb table
(`bale --help` lists the sixteen verbs the brief's §4 splits into
with/without `--json`). I did not re-verify the global `user/bale.toml`
facts; nothing here depends on them.

## The layout, and why

`bin/twine` is a thin entrypoint — version guard, `sys.path` from its
own `__file__`, hand over — above a package `twine/` of three modules
and a subpackage: `registry.py` (the Command/Argument/Result data
types, discovery, validation), `cli.py` (the parser rendered from the
registry, `Context`, dispatch and the `--json` discipline),
`bale.py` (root resolution, `bin/VERSION`, the consumption manifest,
the pin check), and `commands/core.py` (the three verbs as data plus
their handlers). CODE.md says start at the smallest unit that works,
and three ~200-line modules is not that — the seam that earns the
split is concurrency, not size: the seed says sessions 2, 3 and 4 are
file-disjoint and may run beside each other, and a single-file core
would put every one of them on the same file. So the registry is
*assembled by listing* `twine/commands/` (sorted, each module's
`COMMANDS` tuple, duplicates and group-prefix collisions refused at
load): session 2 lands `twine/commands/take.py` and `tests/test_take.py`,
session 3 `emit.py` and its tests, and neither touches a file the
other forecasts. The registry is still one object (`load_registry()`)
and still the single source — the parser, `--help` and `twine
commands` render from it, and the parity test walks the built parser
and compares leaf paths to registry names. If you would rather have a
static tuple and serialize the sessions, it is a ten-line change in
`registry.py`; I think discovery is the right call and said so in the
contract page.

The `--json` discipline lives in one place, `cli.run_command`: the
dispatcher owns stdout, builds `{"command", "ok", …payload}`, maps
`ok` to exit 0/1, and on an internal error still emits the one line
(`ok` false, an `error` object) before the traceback goes to stderr
and the exit is 2. Handlers return a `Result(ok, payload, lines)` and
write nothing to stdout. A payload that tries to set `command` or `ok`
is logged and ignored — the two contract keys are the dispatcher's.

## Decisions to ratify

- **Python floor is 3.11, not T9's 3.10+.** The brief fixes `tomllib`
  as the manifest's parser and `tomllib` is 3.11+. `bin/twine` refuses
  an older interpreter with one stderr line, exit 2. This is a seed
  annotation for the sitting (T9), not something I edited into the seed.
- **The contracts page is `claude/context/cli-contract.md`**, not a
  `docs/` page: DOCS.md §1 puts explainers under `claude/context/`,
  and the crafter's INDEX-coherence block only checks coverage for
  docs under `claude/`, so this placement is the one that is
  mechanically enforced. `fixtures/README.md` lives beside the
  fixtures as the brief asked and is INDEX-listed with a `../` path.
- **`share/bale-consumption.toml` is listed in `claude/INDEX.md`**
  under a "Schemas & data contracts" heading (DOCS.md's inventory
  row). It is data, not a doc, but session 3 will drill down to it and
  INDEX is how it finds things; delete the heading if you disagree.
- **`pyproject.toml` deferred** (`manifest.deferred`): nothing to
  install, the entrypoint locates its package by path, and the suite
  runs from the repo root; the Arc 2 adapter venv is where a pyproject
  first earns its place.
- **Usage errors exit 2 with nothing on stdout** (argparse's own
  behavior: unknown verb, `twine bale` with no sub-command, a bad
  flag). The contract page says a consumer that got no stdout line
  read a usage error. Making usage errors emit a JSON line would mean
  re-implementing argparse's error path; not worth it yet.
- **`status --bale-root`** exists beside `bale check --bale-root`, so
  the bale result inside `status` can be pointed at a root the same
  way (the tests use it). The brief did not ask for it; drop it if you
  want `status` flag-free.
- **`bin/twine` sets `sys.dont_write_bytecode`** before importing the
  package: `-I` ignores `PYTHONDONTWRITEBYTECODE`, so without this a
  plain `python3 -I -S bin/twine` run leaves `twine/__pycache__/` in
  the tree; `tests/test_entrypoint.py` proves it does not.

## The manifest entry shape

`[bale] pin`, `[bale.schemas]` (file → sha256), then one `[[surface]]`
per thing twine reads from bale, kind `file` (`path`) or `verb`
(`verb`, `flags` — flag names only — `argv` — the exact vector —
`cwd`, `stdout`); every entry carries `keys` (the JSON keys twine
reads, `[]` where none), `read_by` (the twine verbs that read it),
`written_against`, and a verb entry carries `fixture` (asserted equal
to `fixture_relpath(argv, cwd)`) and `key_owner`. `[[wanted]]` names
a surface a later session needs that the pin lacks. Five surfaces
today: `bin/VERSION` (read by `bale check` and `status`), `status
--json`, `stats --json`, `stats --sid … --json`, `--version`; two
wanted: `open --json`, `relay --json`. The header comment spells the
shape; `tests/test_consumption_manifest.py` walks it.

## Where to look at review

- **`twine/cli.py` `run_command`** — the discipline in twenty lines.
- **`twine/registry.py` `load_registry`** — discovery and the two
  refusals (duplicate name; a name that is another verb's group
  prefix, which argparse cannot express).
- **`twine/bale.py` `resolve_root`** — the three rules in the brief's
  order; `check` never raises.
- **`tests/helpers.py`** — every CLI subprocess runs with
  `TWINE_BALE_ROOT` pinned to a directory that does not exist, so a
  bale on your PATH can never reach a verdict; `fixture_relpath` is
  the naming rule as code.
- **`validation.sh`** ran on a staging copy with the change applied
  and `.bale-manifest.json` in place (22 PASS, every claim `[agree]`,
  INDEX coverage 1 doc), and on the unmodified tree (every
  change-testing check fails; the untouched-files check, "INDEX
  entries resolve" and "no bytecode" pass on both, as constraint
  assertions should). It writes a scratch directory (`mktemp -d`,
  removed at exit) and `.validation-logs/<stamp>/`, both announced at
  the top; python runs with `-B` and `PYTHONDONTWRITEBYTECODE=1`.

## Claims

Every session-specific assertion is claimed `pass` with
`claim_basis: observed` — the runs above. `file syntax (py, json,
toml)` is mechanical and unclaimed. `model_identity` is
`anthropic:claude-fable-5.1`, the model string this surface is
configured with; the surface itself says the serving model may differ
from that line, so read it as the self-report it is.

## Proposals

### Sessions 2 and 3 share three data files — decide ownership before they pack

**What.** `share/bale-consumption.toml`, `fixtures/README.md` and
`claude/context/cli-contract.md` are append-targets for both courier
sessions: each records new fixtures (a `[[surface]]` entry and a
README row per fixture) and adds verbs the contract page should name.
The code and tests are disjoint by construction (one module and one
test file each), but these three are not. Either serialize 2 before
3, or give one session the three files in its forecast and have the
other ship its entries as a `notes.md` Proposal for a follow-up, or
accept the admission at apply. Bale's pack gate refuses intersecting
forecasts, so this is a decision for the sitting, not a surprise at
apply.

**Why.** The seed says the two sessions are file-disjoint and may run
beside each other; the layout I laid down makes that true for code,
and I would rather name the three exceptions now than have one
session refused at pack.

**Scope hints.** The two briefs' `--write` forecasts; the three files
above.

### What sessions 2 and 3 should know about the registry

**What.** A verb family is one module under `twine/commands/`
exposing `COMMANDS`; a `Command` is data (`name` as the space-joined
path, `summary`, `handler`, `arguments` as `Argument` rows, `json`);
a handler takes `(Context, Namespace)` and returns `Result(ok,
payload, lines)`, writing to `ctx.stderr` only. `Context` carries
`env`, `which` and the two streams so tests inject them. The thing
neither verb has yet is a way to *run* `bale`: add a `run` callable
to `Context` (subprocess by default, a fixture player in tests keyed
by `fixture_relpath(argv, cwd)`) in the first session that needs it —
session 2's `bale apply --no-interact --json` — and session 3 reuses
it. The parity test and `commands --json` pick up new verbs with no
edit; `tests/test_json_discipline.py` runs every registered verb's
happy path, so a new verb that needs arguments to run should extend
`argv_for` there (one line) or ship its own discipline test.

**Why.** Two sessions authored together will otherwise each invent
the runner seam; the `Context` field is the one place it fits.

**Scope hints.** `twine/cli.py` (`Context`), `tests/helpers.py`
(a fixture player beside `fixture_relpath`); session 2 first, 3 reuses.

### `bale open --json` and `bale relay --json` are a bale-src session before session 3 (and 2)

**What.** Land `--json` on `bale open` (the request tarball path and
the opener, per the seed's row 3) and on `bale relay` (the paste
block is stdout today; a JSON twin would carry the block as a field
plus the thread's round) in bale-src, then bump twine's pin and the
two `[[wanted]]` entries become `[[surface]]` entries.

**Why.** The sitting already carries `open --json` as a probable
bale-src slip; session 3 cannot test against a surface that does not
exist, and parsing `bale open`'s human output would be the kind of
fragile read the consumption manifest exists to prevent. `relay` is
the same shape of gap for session 2.

**Scope hints.** bale-src `bin/bale_open.py`, `bin/bale_relay.py`,
`bin/bale_report.py` (a `format_open_json` — the probe found none);
then a twine-src pin-bump session that re-records fixtures.

### Seed annotations for the sitting

**What.** Three dated annotations beneath `twine-seed.md` entries, for
the sitting that authors sessions 2 and 3: T9 — the floor is 3.11
(`tomllib`); T8 — the fixtures layout landed in session 1 as the
ruling accepted, the fake-transport seam deferred to Arc 2 as the
brief corrected; §5.1 row 1 — landed, with the registry discovered
from `twine/commands/` and the three verbs named.

**Why.** The seed is the `amendment_target`; this session cannot
write there (a layout decision is not a seed answer, per the brief),
so the facts travel here.

**Scope hints.** `twine-seed.md` T8, T9, §5.1; one bracketed
paragraph each.

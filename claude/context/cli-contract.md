# The `twine` CLI contract

> What the shell, the parity test, and Arc 1's later sessions build
> on. These are interface outcomes: each line here is asserted by a
> test under `tests/` and by the session's `validation.sh`. Landed by
> session `2026-10-01-twine-core-002`, extended by
> `2026-10-02-twine-take-read-001` (§9, and the lines naming `take` or
> the `format` kind), by `2026-10-02-twine-carry-probe-002` (§10, the
> run seam, and the lines naming `carry probe`) and by
> `2026-10-03-twine-carry-bale-002` (§11, and the lines naming `carry
> exchange`, `carry response`, per-run values or recorded exits) and by
> `2026-10-03-twine-transitions-004` (§12, the `[[vocabulary]]` lines of
> §6, and §11.1's pin gate) and by `2026-10-03-twine-cost-spine-005` (§13,
> and the lines naming `spend`) and by `2026-10-04-twine-kill-switch-002`
> (§14, the `cap-unchecked` lines of §12.2 and §13.7, §10.6's group wait,
> the `unrecorded` line of §6, and the lines naming `kill` or `unlock`) and
> by `2026-10-05-twine-kill-followups-003` (§4's state-directory rows,
> §10.6's spawn hook, the running record's `groups` and the pin gate's move
> to the closure in §14) and by `2026-10-07-twine-pin-049-001` (the pin at
> bale 0.4.49: §6's `also_recorded`, `fixtures_version` and `reasons`
> lines and the end of `[[wanted]]`, §7's third `<where>` and outcome
> groups, §10.3's scaffold tail, §11.4 and §14.7 on what is recorded, and
> §14.5's refusal line) and by `2026-10-07-twine-kill-reason-002` (the hand
> line keyed on the refusal line's `reason` code: §6's and §14.7's stderr
> lines, §14.2's HOLD row and §14.5) and by
> `2026-10-07-twine-carry-bundle-003` (§15, and the lines naming `carry
> bundle`, `open` or the in-flight record in §2, §6 and §8) and by
> `2026-10-08-twine-status-inflight-004` (§4's in-flight rows and the
> prose after them, and the lines of §15.4 and §15.7 naming who reads the
> record) and by `2026-10-12-twine-pin-051-001` (the pin at bale 0.4.51,
> recorded with stderr: §6's pin, relay `reasons` and 0.4.51 lines, §7's
> stderr siblings, the relay row recorded and the carried source paste,
> §8's lines on the two tools, §10.3, §11.3, §11.4, §12.2, §12.4, §14.5,
> §14.7, §15.4 and §15.6 on what is recorded at 0.4.51, and §16, the
> recorder and the lander) and by `2026-10-12-twine-pin-floor-002` (D2 a
> floor, as amended at the sitting `2026-10-08-open-arc2-003`: §2's `bale
> check` line, §4's `floor`, §5, §6's `floor`, key check and bump
> procedure, §7's schemas, §8's roots and `status`, §11.1's gate and the
> key check in §11.2, §11.3, §14.5 and §15.4, §11.4, §14.7 and §15.6 on the
> edited lines, §12's `floor`, §14.1, §14.2, §14.8, §15.2 and §16's
> procedure); a later session that changes a line changes it here in the
> same response.

## 1. The entrypoint

- `bin/twine` is executable, shebang `#!/usr/bin/env python3`. It
  locates its package from its own path (`__file__`), never from the
  working directory or `PYTHONPATH`, so it runs under
  `python3 -I -S bin/twine …` — isolated mode, no site-packages —
  which is also how a reviewer checks the stdlib-only claim (T9).
- Python 3.11 or newer (`tomllib` is the floor); an older interpreter
  exits 2 with one line on stderr.
- `twine --version` prints exactly one line, `twine <version>`, where
  `<version>` is the one line of the repo-root `VERSION` file.
  `twine --help` exits 0.
- An `-I` run writes no bytecode: the entrypoint sets
  `sys.dont_write_bytecode` before the package imports, so the tree
  never grows a `__pycache__/`.

## 2. The command registry (N5)

- One registry (`twine/registry.py`) is the single source for the
  verbs: the argparse wiring, `--help`, and `twine commands` are all
  rendered from it, and `tests/test_registry.py` asserts the parser and
  the registry agree.
- The registry is assembled by discovering the modules under
  `twine/commands/` (sorted); each exposes a `COMMANDS` tuple. A new
  verb family is a new module — no shared list to edit, so
  file-disjoint sessions add verbs beside each other. A duplicate name,
  a name that is also another verb's group prefix, or a malformed
  `Command` refuses at load.
- Verb names are the full space-joined path: `"bale check"`. The JSON
  `command` key carries the same string.
- Verbs today: `commands`, `status`, `bale check` (the gate, D2: since
  session `2026-10-12-twine-pin-floor-002` a **floor** — any bale at or
  above it whose installed schemas hash as the manifest pins them — where
  it was an exact pin; §5), `take`, the
  `carry` group — `carry probe` (`twine/commands/carry.py`), `carry
  exchange` and `carry response` (`twine/commands/carry_bale.py`), `carry
  bundle` (`twine/commands/carry_bundle.py`, §15) —
  `transitions` (`twine/commands/transitions.py`, §12), the `spend`
  group — `spend totals` and `spend check` (`twine/commands/spend.py`,
  §13) — and `kill` (`twine/commands/kill.py`, §14). One group's verbs
  may live in several modules; the parser assembles the group from all
  of them.
- `twine commands --json` emits
  `{"command": "commands", "ok": true, "commands": [{"name", "summary",
  "json", "cli_only"}, …]}` — every registered verb, in registry order,
  no omissions. A CLI-only verb is listed with `cli_only: true`, never
  absent; `cli_only` is derived from `json` so the two cannot disagree.

## 3. The `--json` discipline, every verb

- With `--json`, exactly one line on stdout: a JSON object with at
  least `"command"` (the verb path) and `"ok"` (a boolean). Everything
  informational goes to stderr (`[twine] …` lines; `--verbose` adds
  leveled log lines).
- Exit 0 when `ok` is true; 1 when the verb ran and reports not-ok (a
  failed check); 2 only on an internal error — and even then the one
  JSON line is emitted first, `ok` false with an `error` object
  (`type`, `message`), before the traceback goes to stderr. A handled
  failure never prints a traceback.
- Without `--json`, the same facts as readable lines on stdout; the
  exit code is the same.
- A usage error (unknown verb, missing sub-command, bad flag) is
  argparse's: usage on stderr, nothing on stdout, exit 2. It is not an
  internal error, but it shares the code; a consumer that got no stdout
  line read a usage error.
- `command` and `ok` are the dispatcher's: a handler payload cannot set
  them (an attempt is logged and ignored).

## 4. `twine status [--json] [--bale-root DIR] [--state-dir DIR]`

Twine's own facts, no bale repo state (reading `bale status --json` is
session 3's):

| key | value |
|---|---|
| `version` | twine's version (`VERSION`) |
| `python` | the interpreter's version |
| `repo_root` | the repository root, located from the package |
| `consumption_manifest` | absolute path of `share/bale-consumption.toml` |
| `fixtures` | absolute path of `fixtures/`; `fixtures_present` says whether it exists |
| `floor` | the manifest's `[bale] floor` (since session `2026-10-12-twine-pin-floor-002`; `pin` before, and no `pin` key now), or null when the manifest is unusable |
| `bale` | the `bale check` result object (§5), or null when the manifest is unusable |
| `state_dir` | the directory `spend.resolve_state_dir` resolves (§13.2's rules: `--state-dir`, else `$TWINE_STATE_DIR`, else XDG, else `$HOME`), as a string; `null` when none resolves (session 5c) |
| `state_dir_source` | `"--state-dir"`, `"TWINE_STATE_DIR"`, `"XDG_STATE_HOME"` or `"HOME"`; `null` when none resolves |
| `state_dir_reason` | `null` when one resolves; otherwise the refusal text (`spend.SpendError`'s message) — a null `state_dir` is never silent |
| `state_dir_exists` | whether it exists and is a directory; `null` when none resolves |
| `state_present` | `null` when none resolves; otherwise an object with five booleans, in this order — `spend_jsonl`, `prices_toml`, `abort`, `running`, `inflight` — whether `<state-dir>/spend.jsonl`, `<state-dir>/prices.toml`, `<state-dir>/abort/`, `<state-dir>/running/` and `<state-dir>/inflight/` exist (the two files as files, the three directories as directories: a file named `inflight` reads false); all false when the directory itself does not exist |
| `inflight_sids` | the sids whose `<state-dir>/inflight/<sid>.json` reads as an in-flight record (`twine.inflight.read_inflight` accepts it, §15.7), sorted; `[]` when `inflight/` is absent, not a directory, or holds no record; `null` when no state directory resolves (session `twine-status-inflight`) |
| `inflight_faults` | one string per entry in `inflight/` that is not a record, in name order, each naming the entry by its basename and saying why (below); `[]` when every entry reads (or there is none, or no `inflight/`); `null` when no state directory resolves |
| `ok_reason` | why `ok` is what it is |

`ok` is true when twine itself is intact — the manifest parses and its
floor resolves (`ok_reason` "manifest parses and the floor resolves") —
regardless of whether a bale install is present; the bale result rides
inside, and a bale the gate refuses there leaves `status` at exit 0.
Human mode prints `floor: <version>` and the check's verdict line. An unusable manifest is `ok` false, exit 1 (the state keys ride on
that path too).

`--state-dir DIR` is the same argument the spend verbs and `kill` take,
so an operator can ask what a given flag resolves to — an operator whose
`twine kill` was refused for a missing state directory (§14.1) finds out
here which one twine resolves. A state directory that does not resolve,
or does not exist, is a fact about the machine, not a fault in twine:
`status` stays exit 0 with the nulls or falses above, and **never creates
the directory**. Human mode says so in one line each — `state dir: <path>
(from <source>)`, with `(does not exist)` when it does not, then `state
present: …` naming what is there and what is missing; or `state dir:
none resolves — <reason>`.

**The in-flight records** (session `twine-status-inflight`) are the files
`carry bundle` keeps at `<state-dir>/inflight/<sid>.json` (§15.4). `status`
**reads them and never writes them** — no record, no directory, no lock and
no temp file is created, and `inflight/` is listed and each record read
without taking `carry bundle`'s `flock` (a record is replaced atomically, so
a reader sees the old record or the new, never half). `inflight_sids` lists
every record that reads; every other entry in `inflight/` is named in
`inflight_faults` — a silent skip is a bug — as one of:

- a name that is not `<sid>.json` for a sid twine accepts
  (`twine.kill.is_sid`): `<name> is not an in-flight record: its name is not
  <sid>.json`, or `… '<stem>' is not a session id twine accepts`; twine's
  own temp file from an atomic write (`.twine-<pid>-<ns>.tmp`) is named as
  that — `… it is the temp file of a record write still in progress, or of
  one that did not finish`;
- a `<sid>.json` that `read_inflight` refuses: its words, the full path cut
  to the basename (`<sid>.json is not an in-flight record: its sid is …,
  not …`, `<sid>.json is not a JSON object: …`, `<sid>.json cannot be read:
  …`). The reader is not loosened for `status`: a file that is almost a
  record is a fault, named;
- a `<sid>.json` listed but gone when read (a dangling link, or removed in
  between): `<name> cannot be read: it was listed but no file is there
  now …`;
- an `inflight/` that cannot be listed (no read permission): `inflight`
  stays true, `inflight_sids` `[]`, and one fault, `inflight/ cannot be
  listed: <reason>` — never a traceback, and never an empty listing that
  would read as "no records".

A name that is not printable text — a newline in it, or bytes that are not
UTF-8 — is shown as its Python `repr`, so it can break neither a human line
nor the twin's encoding. Whatever `inflight/` holds, `status` stays `ok`
and exit 0: like a missing state directory, junk there is a fact about the
machine, not a fault in twine. Human mode names `inflight/` on the `state
present:` line with the other four, then one `in-flight record: <sid>` line
per record and one `in-flight fault: <fault>` line per fault (neither when
there are none); the unresolved and does-not-exist renderings keep their one
line each. The reading is `twine.inflight.list_inflight` (§15.7).

## 5. `twine bale check [--json] [--bale-root DIR]` (D2)

The gate. Since session `2026-10-12-twine-pin-floor-002` (D2 as amended
at the sitting `2026-10-08-open-arc2-003`) it is a **floor** plus the
manifest's schema hashes, where it was an exact pin: twine drives any bale
at or above the floor whose installed schemas hash as the manifest pins
them. The floor is the version the recordings were made at, raised only
by a recording session (§6, §16).

- Resolves the install root, first rule that answers: `--bale-root`,
  else the environment variable `TWINE_BALE_ROOT`, else `command -v
  bale` followed to its real path and up to the directory holding
  `bin/` (`~/.local/bin/bale` → `~/bale/bin/bale` → `~/bale`).
- Reads `<root>/bin/VERSION`, strips it, and parses it as **three dotted
  integers** (no leading zero, no suffix: `0.4.51-rc1` does not parse);
  compares it to the manifest's `[bale] floor` **as a tuple** — `0.4.100`
  is above `0.4.51`, though a string comparison says otherwise.
- Hashes, with sha256, every file `[bale.schemas]` names under
  `<root>/schemas/`. A file `[bale.schemas]` does not name is free.
- **ok**, exit 0, exactly when the root resolves, `bin/VERSION` reads and
  parses, compares at or above the floor, and every named schema exists
  under `<root>/schemas/` with that hash. Otherwise not ok, exit 1, one
  JSON line, no traceback, the reason naming **each failing fact at once**,
  `; `-joined, in this order: no install found (alone); `bin/VERSION`
  unreadable or empty, or `<path> reads '<text>', which is not a version
  of three dotted integers`, or `installed <v> is below the floor
  <floor>`; then `no schemas/ directory at <root>/schemas`, or `schemas
  missing from schemas/: <names>` and `schemas that do not hash as the
  manifest pins them: <names>`. ok's reason: `installed <v> is at or above
  the floor <floor>, and all 8 schemas hash as the manifest pins them`.
- JSON: `floor`, `installed` (null when unreadable), `root` (null when
  no install was found), `source` (`"--bale-root"`, `"TWINE_BALE_ROOT"`,
  `"PATH"`, or null), `schemas`, `ok`, `reason` — **no `pin` key**.
  `schemas` is null when no install was found, else an object: `dir`
  (`<root>/schemas`), `present` (whether it is a directory), `ok`,
  `checked` (every named file found and hashed, matching or not, sorted),
  `mismatched` and `missing` (sorted; with no `schemas/`, every named file
  is missing and the reason says so once).
- Human mode: `floor: <floor> (twine drives this bale or any above it)`,
  `installed:`, `root:`, `schemas: all 8 hash as the manifest pins them`
  or `schemas: NOT OK — <the schema facts>`, then `check: ok — …` or
  `check: FAIL — <reason>`.

## 6. The consumption manifest (D3, D4)

`share/bale-consumption.toml`, parsed by `tomllib`: `[bale] floor` —
`0.4.51`, the version the recordings were made at (session
`2026-10-12-twine-pin-floor-002` made it a floor; until then the key was
`pin`, an exact version — `0.4.51` since session
`2026-10-12-twine-pin-051-001`, the last exact pin — and `load_manifest`
now refuses a `[bale]` that still carries `pin`, by name) — a
`[bale.schemas]` table of the eight installed schema files to their sha256
(unchanged from 0.4.45 through 0.4.51, hashed at 0.4.51 by a probe; the
header says who hashed them and when; the files themselves are
`fixtures/bale-0.4.51/schemas/`, §7), which is **the gate's second half**
(§5), one `[[surface]]` per bale surface twine reads (the file
`bin/VERSION` and each recorded `--json` verb: `kind`, `verb`, `flags`,
`argv`, `cwd`, `stdout`, `keys` — the JSON keys twine reads, `[]`
where none yet — `key_owner`, `read_by`, `fixture`, `written_against`;
a per-run value in `argv` is written `<role>` (§7); a verb recorded
under more than one outcome, or under another argv of it, lists each
further recording as an `also_recorded` row — `argv`, `cwd`, `outcome`,
`reason` when the line has one, `fixture` — which the tests replay where
twine's one argv would meet that outcome; a verb with no recording has
no `fixture` and names its `stand_in` and the `doubles` standing in for
it, until a recording replaces them — none since session
`2026-10-08-twine-carry-exchange-json-001` retired the flagless `relay`
surface, whose stand-in was the crafter's exchange emission; no verb is
`unrecorded` at 0.4.49 or 0.4.51, the shapes staying for the next such gap; `read_at`, the probes
that read a contract from bale's source, stays where one did; `reasons`
with `reasons_home` records a closed set a key takes that is not a
table axis — the unlock refusal's five reason codes (§14.5) and, since
0.4.51, the relay refusal's twenty-two (`RELAY_REFUSAL_REASONS`, bale
0.4.50, in bale's order with the fallback `unclassified`; twine reads no
relay `reason` — it dispatches on `outcome` and quotes `cause`, §11.2);
and, `kind = "format"`, each text format `take` parses out of a paste:
`format`, `locator`, `home`, `emitted_by`, `fixtures`, `fixtures_version`
— the bale version that emitted those files: for a crafter emission the
version its last recording was made at (the floor's), re-recorded when the
crafter's sha256 moves (§7; "at every pin" until the floor); the version
that printed a carried paste, which stays under that version's directory
(§7) — `keys`,
`read_by`, `written_against`),
`[[wanted]]` for a surface a later session needs that the bale at the
floor lacks — none at 0.4.49 or 0.4.51 (`bale open --json`, `bale relay --json` and the
reason-coded `bale unlock --json` refusal the 0.4.45 manifest wanted
landed in bale 0.4.47–0.4.48 and are surfaces); the shape stays in the
header for the next gap — and
`[[vocabulary]]` for each closed set of spellings bale declares that
the transition table keys on (§12): `axis` (the table axis whose keys
they are), `values` (bale's spellings, in bale's order), `home` (the
installed schema, whose hash `[bale.schemas]` pins, or the bale source
file, with its `home_sha256`), `pointer`, `also_at`, `excluded` (enum
members that are not keys — the closure enum's `null`), `read_by`,
`written_against`, `read_at` (the probes or readings that read them).
Three are recorded for 0.4.51, unchanged from 0.4.45 value for value:
`telemetry-outcome` (13), `closure-reason` (9) and `apply-outcome` (9,
`format_apply_json`'s docstring, at `bin/bale_report.py` line 3426 of
0.4.51 — line 3040 of 0.4.49); a verb surface whose key takes one of them names it as
`vocabulary` (`apply`'s `outcome` is `apply-outcome`). A recording
session (a pin bump, until the floor) re-reads them — by probe, or, as the bumps to 0.4.49 and 0.4.51 did, from
bale-src's context tarball, `read_at` saying which and that it was not a
probe (at 0.4.51 the schema homes' hashes were a probe's, `twine-051-record`)
— and diffs them as data (D4). The 0.4.51 lines, beside 0.4.49's: `open
--json` carries 23 keys (`reason` and `cause` after the 21) and prints a
refusal line; `relay --json` carries 13 (`reason` last); every other
recorded line keeps its shape (fixtures/README.md, "bale 0.4.51"). The verbs twine runs today: `bale apply
--dry-run --json <tarball>` (read by `carry response`: the key
`outcome`), `bale relay <sid> - --json` (read by `carry exchange`: the
keys `outcome`, `sid`, `block` and `cause`; §11.2 — recorded under this
very argv since 0.4.51, §11.4) and `bale unlock <sid> --reason
aborted --json` (read by
`kill`: the keys `outcome`, `sid`, `closure_reason` and `telemetry`,
and since 0.4.49 the refusal line's `reason`, `message` and
`open_sessions`; §14) and `bale open <bundle> --json` / `bale open
--check <bundle> --json` (read by `carry bundle`: the keys `outcome`,
`sid`, `tarball`, `opener`, `desk` and `bundle`; §15); `bale pack --json`
is a recorded surface read by nothing yet. The
file's header comment spells the entry shapes;
`tests/test_consumption_manifest.py` walks them. `twine.bale.load_manifest`
refuses a `[[vocabulary]]` entry without an axis or a home, a second
entry for one axis, or values that are empty or repeat; and (since session
`2026-10-12-twine-pin-floor-002`) a `[bale]` without a `floor` of three
dotted integers, one still carrying `pin`, an empty `[bale.schemas]` (a
gate that hashed nothing would admit anything), and a schema name that is
not a plain file name under `schemas/`.

**The keys on the line** (same session; D2 as amended). Every verb that
reads a bale `--json` line checks, **on that line**, that each key the
manifest lists for the surface it reads (`keys`, found by the reader's
name in `read_by`) is present: `carry exchange` on the relay line (§11.2),
`carry response` on the apply line (§11.3), `carry bundle` on the open
line (§15.4), `kill` on the unlock line (§14.5). Presence is all it asks —
a key whose value is null is present, since bale prints every key on every
outcome (every recorded line of the four surfaces carries every listed
key, and a test walks them) — and a key the manifest does not list is
free. A line lacking one is not ok, `ran` true, the reason `bale's <verb>
line lacks the key(s) '<k>'[, …], which the consumption manifest lists for
the <verb> surface (bale <argv>); existing keys are never removed, so this
bale is not the contract twine reads`, appended beside whatever else the
line fails. One helper, `twine.bale.missing_keys_failure`, called from the
four readers. The two schema-homed vocabularies are held fixed by the
gate (their schema's hash is pinned in `[bale.schemas]`); the one homed in
`bin/bale_report.py` (`apply-outcome`) is held by twine naming an outcome
it does not know (§11.3), which it always has.

**Moving the install under the floor** (the bump procedure, same session).
An install that moves without touching a key this file lists or a schema
it pins **needs nothing**: the gate admits it, the key check passes, and
nothing is re-recorded — 0.4.52 was the first (probe `twine-052-delta`,
2026-10-12: `bin/bale`, `bale_report.py`, `bale_relay.py`, `bale_open.py`
and all eight schemas byte-identical to 0.4.51's; only the crafter moved).
An install that touches one — a schema's hash, a listed key, or a
vocabulary twine dispatches on — **needs a recording session** (§16): the
recordings are re-made at the new version, the vocabularies re-read, the
fixtures land under `fixtures/bale-<new>/`, and the session **raises the
floor** to that version. Until it lands, the gate refuses an install whose
schemas moved, and the key check refuses a line that lost a listed key —
named, never a surprise (D17). The floor is never raised without a
recording, and never lowered.

## 7. Fixtures

`fixtures/README.md` carries the rule and the per-file provenance.
The path of a recorded output is
`fixtures/bale-<version>/<where>/<verb>_<flag[-value…]>[_…][+<group>].<ext>`;
`tests/helpers.py`'s `fixture_relpath(argv, cwd, group)` computes it — the
rule itself is `tests/fixture_rule.py`, which `bin/twine-land-recordings`
imports too (§16), so the lander and the tests cannot name a recording
differently — and each manifest surface's `fixture` (and each
`also_recorded` row's) is asserted equal to it, its outcome group
assigned by the same collision rule. `<where>` is `twine-src/` (the packing repo),
`anywhere/` (an output that depends on no directory) or, since the pin at
0.4.49, `scratch/` — a throwaway repository a probe created and removed,
where the verbs that write (pack, open, relay, unlock, apply) were
recorded; its facts are in the README's section. Every `.json` fixture is
one object line with a trailing newline. The tests read the floor's
directory (`FLOOR` in `tests/helpers.py`, `PIN` until session
`2026-10-12-twine-pin-floor-002`: the floor is the version the recordings
were made at, so it names the directory); earlier versions' directories
and README sections stay as history.

**The schemas** (same session). The eight files the gate hashes (§5)
land byte-exact under the floor's directory, `fixtures/bale-0.4.51/schemas/<name>.json`,
named as installed — from the operator's `bale-src` context tarball of
2026-10-07 at 0.4.51, every hash equal to the manifest's and to the
operator's 0.4.52 install's. They are not recordings: no argv printed
them, they have no stderr sibling, the lander neither derives nor checks
them (`tests/fixture_rule.py` `SCHEMAS_WHERE`, §16), and the README lists
them in a table of their own (`| file | bytes | sha256 |`), which
`tests/test_fixtures.py` holds to the files and to `[bale.schemas]`. Every
stub install root the tests build copies them (`tests/helpers.py`
`install_schemas`), so the gate admits a stub exactly as it admits the
operator's install.

A **per-run value** — a session id read out of a block, a tarball's
path, a bundle file, a pack's goal — never enters a name: `fixture_key(argv)`
replaces it with its role, and a role is a `_` group of its own. `bale
relay <sid> - --json`, twine's argv, names `relay_sid_stdin_--json.json`
— recorded since 0.4.51 (§11.4; 0.4.49's recordings were `bale relay
<sid> <file> --json`'s, `relay_sid_file_--json…json`); `bale apply --dry-run --json
<tarball>` names `apply_--dry-run_--json_tarball.json`; `bale unlock <sid>
--reason aborted --json` names `unlock_sid_--reason-aborted_--json.json`
(recorded at 0.4.49 and 0.4.51: §14.7); `bale open [--check] <bundle> --json` names
`open_bundle_--json.json` / `open_--check_bundle_--json.json`, and `bale
pack <goal> --slug ro … --json` `pack_goal_--slug-ro_…_--json.json` (a
flag's value stays). An **outcome group**: when a version holds more than
one recording of a normalized argv, each carries `+<outcome>` from its
line and, where that still collides, `+<reason>` — the line's `reason`,
or a tag the README assigns when the line has none (0.4.49's relay
refusals, which had only a `cause`; at 0.4.51 every collision is told by
the line's own `reason`: `+relay-refused+not-an-object`,
`+relay-refused+not-open`, and `+open-refused`, a third outcome, needing
none) — and the player (`FixturePlayer`) answers such an argv only when the test
selects the group (`select={...}`), refusing otherwise and naming the
candidates. A row's **exit** column is the exit code the fixture player
answers; a row that did not capture it says `unrecorded`, and the player
answers it only when the test names the code it assumes (every 0.4.49 and
0.4.51 row has its exit; the rule stays). **stderr is recorded** since
0.4.51: every recording's stderr lands byte-exact beside its stdout file
as a sibling — the same name, the extension `.stderr` (empty when bale
printed nothing; the file exists) — and its row gains two columns, the
sibling's bytes and sha256 (the eight-column row: `file`, `command`, `ran
in`, `exit`, `bytes`, `sha256`, `stderr bytes`, `stderr sha256`; the
six-column rows of 0.4.45 and 0.4.49 stay as history, read as rows without
stderr). The player answers the sibling's bytes, held to the row
(`tests/helpers.py` `recorded_stderr`), and so do the recordings' readers
and replays (§11.4, §14.7, §15.6); nothing about a stderr is derived. A
test that needs a stderr bale never printed still feeds bytes it names as
not bale's.

A fixture that is not a bale argv's stdout keeps the version directory:
a crafter emission is `fixtures/bale-<version>/crafter/<flag[-value…]>[_…].txt`
(`-` spelled `stdin`; `emission_relpath(tool, argv)`, at the floor;
re-recorded when the crafter's sha256 moves — the recorder prints it — not
at every version: 0.4.52's crafter, `c167f5b5…`, moved, and its probe
scaffold is a specimen for a later session, not a gate), and an
architect-carried paste of bale output is
`fixtures/bale-<version>/carried/<kind>_<identity>[_to-<addressee>].txt`
(`carried_relpath(kind, identity, to)`, whose version is the one the
manifest's format entry names as `fixtures_version` — a paste stays under
the version that printed it when the floor moves, never copied), landed
CRLF→LF with both hashes in the README. Since 0.4.51 a version's
`carried/` also holds the **source of its recordings**: the recorder's
paste-back, `probe-output_<slug>.txt`, landed the same way, from which the
lander derived every recording, sibling and row (§16). It is no format
entry's fixture (the `probe-output` entry keeps the 0.4.45 paste as its
specimen); `--check` reads it.

## 8. Tests

`tests/` is a package; the suite is stdlib `unittest`:

```
python3 -B -m unittest discover -s tests -t .
```

from the repository root — no network, no bale install, no third-party
module, and no bale reached whatever is on `PATH`: a verb that runs bale
(§11, §15) runs it through the seam, and the tests hand the seam the fixture
player, a double that replays a recording (`RecordedUnlock`,
`RecordedRelay`) or one named as not bale's (`BaleDouble`), or a stub `bin/bale` they write into a
temp root (`tests/helpers.py` `StubBale`, passed as `--bale-root`). `bash` is required: `carry probe`'s tests run real probe scripts,
each derived from the crafter's recorded scaffold by filling its
placeholders mechanically (`tests/helpers.py` `filled_probe`). `bale check` is tested against temp roots the tests build
(`tests/helpers.py` `TempRoots`, each carrying the eight schema fixtures
unless it says otherwise: `bin/VERSION` at the floor, above it (0.4.52),
far above it (0.4.100), below it (0.4.49 and 0.4.46), unparsable, absent;
at the floor with one schema altered, and with no `schemas/`), never a
real install, and every CLI subprocess runs with `TWINE_BALE_ROOT`
pinned to a temp directory so a bale on `PATH` cannot leak into a
verdict. The probe the tests run ends before the recorded scaffold's
clipboard tail (§10.3), which would hand the block to a `bale` on PATH;
the one test that keeps the tail builds the PATH it runs under. The
spend verbs (§13), `kill` (§14) and `carry bundle` (§15) read and write
only temp state directories the tests build, and `status` (§4) reads only
such directories, never the real default
(§13.9, §14.8, §15.7); no test runs a real `bale unlock`, `bale open` or
`bale relay` — the kill's tests replay the recorded unlock lines (§14.7),
`carry bundle`'s the recorded open lines (§15.6), and `carry exchange`'s
the recorded relay lines (§11.4). The recorder and the lander (§16) are
tested in `tests/test_recordings.py`: the lander as a subprocess against
the landed paste-back and edited copies of it and of `fixtures/` in temp
trees; the recorder as a script (`bash -n`, its header read by `take`, its
recordings matched to the paste's) and once end to end against a stub
`bale` the test writes, first on a PATH the test builds.

## 9. `twine take FILE [--json]` — the courier's read

Text in, structured facts out. `FILE` is a path, or `-` for stdin. It
**executes nothing it reads, writes nothing, calls no bale verb and
reaches no network** — a probe block is reported, never run (running
one, with consent, is `carry probe`'s: §10). The parse
layer is `twine/shapes.py` (pure); the verb is `twine/commands/take.py`.

### 9.1 Input

Read as bytes and decoded as UTF-8 (a leading BOM is dropped; bytes that
are not UTF-8 are a not-ok result). Every CRLF becomes LF before
anything is matched; a lone CR is left alone.

### 9.2 The five kinds, and the no-nest rule

| kind | located by | integrity |
|---|---|---|
| `probe` | a fenced code block (three or more backticks, closed by a fence at least as long) whose first five lines include `# PROBE <slug>: …` | structural: the fence closes |
| `probe-output` | `=== PROBE BEGIN <slug> ===` … `=== PROBE END <slug> ===` | line count: `--- integrity: N lines ---`, the last inner line, where N is the number of lines between BEGIN and it |
| `light` | `=== LIGHT BEGIN <sid> ===` … `=== LIGHT END <sid> ===` | structural: closes, and every entry has its four labeled lines in order, numbered from 1, then the `Reply:` line |
| `exchange` | `BALE EXCHANGE BEGIN <sid>` … `BALE EXCHANGE END` | sha256, exactly bale's rule (`bin/bale_relay.py` `parse_exchange_input`) |
| `relay` | `=== RELAY BEGIN <sid> to <planner\|worker> ===` … `=== RELAY END <sid> to <same> ===` | structural: the matching END arrives |

- **Sentinels are whole lines.** The `===` ones start at column 0
  (trailing whitespace tolerated): bale's `_inline_lines` defuses an
  inlined sentinel by indenting it, so an indented line is content. The
  exchange ones tolerate surrounding whitespace, as bale's parser does.
  A sentinel quoted inside a line (`echo "=== PROBE BEGIN … ==="`) is
  not one.
- **Spans do not nest.** Once a span opens, every line until its own
  END — same slug or sid, same addressee — is its content, whatever it
  looks like. A relay block quoting notes, or a probe's output carrying
  the blocks it recorded, is one block.
- **A fence that is not a probe is transparent**: the shapes inside it
  are found, as bale's parser ignores a chat's fence lines.
- **An END sentinel with no BEGIN** before it (a paste cut at the top)
  is reported as a malformed block of its kind.
- **Exchange integrity**: the header is the leading `#` lines; the
  trailer is the last non-blank inner line, `# sha256 <hex>`; the body
  is everything between, joined with LF plus one trailing LF; its sha256
  must equal the trailer's. When it does not but
  `json.dumps(record, indent=2) + "\n"` does, the fault is
  `unescaped-in-transit` (a carrier turned `\uXXXX` escapes into
  characters); otherwise `mismatch`. Other faults: `unclosed`,
  `no-sid`, `no-body`, `no-trailer`, `body-not-json`.

### 9.3 The JSON twin

One line (§3), with `command` `"take"`, `ok`, and:

| key | value |
|---|---|
| `shape` | the kind of the **last** block — the shape the turn ended in — or `"prose"` when there is none; `null` when the input could not be read |
| `blocks` | every block, in input order; `[]` for prose |
| `input` | `source` (the path, or `"<stdin>"`), `bytes`, `lines`, `crlf_normalized`, `bom_stripped` |
| `input_error` | present only when the input could not be read or decoded |

Each block: `kind`; its identity and parse results; `start_line` and
`end_line` (1-based, inclusive, in the normalized input; an unclosed
span ends at the last line); `integrity`, always with `ok` and `basis`
(`"structural"`, `"line-count"` or `"sha256"`); and `error`, present
exactly when `integrity.ok` is false.

| kind | fields |
|---|---|
| `probe` | `slug`, `fence_info`, `script` (the fence's content, verbatim, LF-terminated) |
| `probe-output` | `slug`; `integrity.expected_lines`, `integrity.found_lines` |
| `light` | `sid`; `questions`, a list of `{question, context, default_assumption, why_blocked}` — the clarification manifest's field names, so one row feeds either courier |
| `exchange` | `sid` (the sentinel's); `round`, `from` (the record's, when the body parsed, else null); `record` (only when integrity holds); `integrity.expected_sha256`, `integrity.found_sha256`, `integrity.fault` when not ok |
| `relay` | `sid`, `to` (`"planner"` or `"worker"`) |

`ok` is false when any block fails integrity or is malformed, or the
input cannot be read: exit 1, one line, no traceback. Otherwise `ok` is
true and the exit 0, prose included. Without `--json`: a summary line,
then one line per block — kind, identity, line range, integrity.

### 9.4 Routing relay blocks — a rule for 2b and every later router

**A relay block addressed `to: planner` is never delivered to a
worker.** On a HOLD, bale's planner block inlines the session log's
checkpoint band (`bin/bale_report.py` `format_hold_relay_planner`: "both
session-log bands inlined"), so carrying it into a worker session would
teach the worker its grader (TARBALL.md §7). The worker block is
spec-safe by construction (`format_hold_relay_worker` has no parameter
for the checkpoint's output). `take` only reports `to`; a router that
delivers blocks keys on it, and treats a `to: planner` block whose
destination is a worker session as a refusal, not a choice.

## 10. `twine carry probe FILE [--block N] [--run] [--cwd DIR] [--timeout SECONDS] [--out PATH] [--json]`

The courier runs a probe — only with the operator's explicit consent,
given per invocation as `--run`. The verb is
`twine/commands/carry.py` (the `carry` family); it reads through
`twine.shapes` (§9) and runs through the seam (§10.6). It calls no bale
verb.

### 10.1 Finding the block

`FILE` (a path, or `-` for stdin) is read exactly as `take` reads it
(§9.1–§9.2). The candidates are its `probe` blocks. `--block N` names one
by the number `take` prints for it — its 1-based position among **all**
blocks, not among probes. Without `--block`, exactly one probe block
must be present. No probe block, more than one without `--block`, or a
`--block` that names no block or a block of another kind: refused.
Never a guess.

### 10.2 Refused before running

Each of these refuses the invocation — `ok` false, `ran` false,
`exit_code` null, exit 1, every applicable reason named in `reason` and
listed in `refusals` — **with or without `--run`**; a block that would
be refused is never reported ok, and nothing runs:

- the block is malformed (its `integrity.ok` from the parse is false —
  an unclosed fence);
- the script carries the crafter's unfilled-placeholder sentinel
  `TODO(worker)` anywhere (an unfilled scaffold: "not ready to paste");
- its purpose header — the leading run of `#` lines, shebang included —
  has no `# Read-only: <text>` line (TARBALL.md §4.2's header
  confirming the script is read-only; an empty declaration declares
  nothing);
- `--out PATH` names a path that exists;
- `--timeout` is not positive, `--cwd` is not a directory, or (with
  `--run`) no `bash` is on `PATH`.

### 10.3 Without `--run`, and with it

**Without `--run`** nothing executes and nothing is written: the chosen
block is reported (`slug`, `header`, `script`); `ok` true, `ran` false,
exit 0. Human mode prints **exactly the script** on stdout, so the
operator reads what `--run` would run; the summary goes to stderr.

**With `--run`** the script is handed to `bash -c <script>` through the
seam: in `--cwd` (default: the current directory), inheriting the
operator's environment, stdin `/dev/null`, no file written. `--timeout`
(default 300 seconds) is enforced on the whole process group: on expiry
the script **and its children** are killed (SIGKILL to the group — a
`sleep` or a pipeline cannot outlive the timeout or hold the pipes
open), `timed_out` is true and `exit_code` null. The group is also
killed the moment the script itself exits, so nothing it backgrounded
lingers. **Captured stdout is capped at 262144 bytes (256 KiB)** —
seven times the largest probe output recorded so far; past the cap the
group is killed, `capped` is true, `exit_code` null, and the run is not
ok. stderr is captured (up to 64 KiB, `stderr_truncated` when more) and
reported in `stderr`; it is never part of the paste-back.

stdout is then read with `twine.shapes`. **`ok` is true exactly when the
script exited 0, did not time out, was not capped, and its stdout
carries exactly one `probe-output` block, with the probe's slug, whose
integrity holds.** `output` is that block — its lines from BEGIN
through END, LF line endings, one trailing newline — the paste-back the
operator carries; `twine take` reads it as one intact `probe-output`
block. Otherwise `ok` false, `ran` true, exit 1, the reason named, and
`output` the best candidate found (the block with the probe's slug, else
the first) or `""`.

Human mode with `--run`: on ok, stdout is **exactly the paste-back**
(`twine carry probe f --run > paste.txt` captures what is carried);
otherwise stdout is one line naming why, and the script's stderr goes
to stderr. Progress and diagnostics always go to stderr.

`--out PATH` writes the paste-back to PATH, created exclusively, only
when the run is ok; an existing PATH is refused before running (§10.2)
and a PATH that appears during the run is not overwritten. It is the
only file `carry probe` ever writes, and only where the operator named.

A file-based probe (TARBALL.md §4.4, writing `./probe-output/`) is not
supported: it prints no `probe-output` block, so it is ran-but-not-ok.

The crafter's scaffold at bale 0.4.49 (byte-identical at 0.4.51) ends in a **clipboard tail**: after
`emit_probe_block` it pipes the block into `bale clipboard --block "probe
block"` through whatever `bale` is on PATH, and with none prints two
`[clipboard]` notices on stderr (the 0.4.45 tail was remedy text in
comments). `carry probe --run` runs the script as given — the tail
included, under the operator's PATH — so a probe built on the 0.4.49
scaffold copies its own paste-back where a current bale is installed,
and its stderr carries the notices where none is; neither reaches
`output`, which is the block alone.

### 10.4 The JSON twin

One line (§3), `command` `"carry probe"`. Fixed names — 2b-ii, the
shell and the oracle read them:

| key | value |
|---|---|
| `slug` | the chosen probe's slug; null when no block was chosen |
| `ran` | whether bash was started |
| `confined` | **always `false` in Arc 1** (§10.5) |
| `exit_code` | the script's exit status; null when it did not run or was killed (timeout, cap) |
| `timed_out` | the timeout expired and the group was killed |
| `integrity` | the paste-back block's integrity, as §9.3 reports it (`ok`, `basis` `"line-count"`, `expected_lines`, `found_lines`), plus `error` when not ok — including when nothing ran |
| `output` | the paste-back (§10.3), or the best candidate when not ok, or `""` |

And beside them: `block` (the number `take` prints), `capped`,
`stdout_cap_bytes`, `reason` (null when ok), `refusals`, `header`,
`script`, `run_requested`, `cwd`, `timeout_seconds`,
`duration_seconds`, `stderr`, `stderr_truncated`, `out` (the path
written, or null), `input` (as `take`'s).

### 10.5 `confined: false`

The script runs with the operator's privileges, environment, files and
network — exactly what the operator gets by reading the block and
pasting it into a terminal, which is what `--run` replaces. Twine
checks that the purpose header **declares** the script read-only; it
cannot make it so. The timeout, the process-group kill and the output
cap bound how long and how much; they confine nothing. Arc 2's sandbox
is what makes `confined` true. The flag has one switch point: it is read
from the runner, `twine.process.runner_confines(ctx.run)` (a runner
declares `confines`; the default runner declares false, and one that
does not say is false), and set nowhere else — Arc 2's sandbox runner,
a wrapper around the default one, is what will declare true.

### 10.6 The run seam

`Context.run` is the one way a handler runs a subprocess
(`twine/process.py`); no module under `twine/commands/` imports a
process-spawning module, and a test asserts it. The signature 2b-ii
builds on:

```
run(argv: Sequence[str], *, cwd: str | Path | None = None,
    stdin: bytes | None = None, timeout: float | None = None,
    env: Mapping[str, str] | None = None,
    stdout_cap: int | None = None,
    on_spawn: Callable[[int], None] | None = None) -> RunResult

RunResult(argv, exit_code: int | None, stdout: bytes, stderr: bytes,
          timed_out: bool, stdout_capped: bool, stderr_truncated: bool,
          duration_seconds: float, group_survivors: tuple[int, ...])
```

`cwd` None inherits the caller's; `env` None inherits the process
environment (handlers pass `ctx.env`); `stdin` None is `/dev/null`;
`timeout` None waits; `stdout_cap` None is 16 MiB. `exit_code` is None
when the runner killed the child. A process that cannot start raises
`RunError` (an `OSError`); everything after the start is a `RunResult`.
The default, `run_process`, starts the child as a new session (its own
process group) and kills the group on timeout, on the cap, and when
the child exits; a grandchild that leaves the group with `setsid` is
beyond its reach (it waits two seconds for the pipes, then logs and
gives up).

**The spawn hook** (session 5c). `on_spawn`, when given, is called once
with the child's pid — which is its pgid, since the child starts a new
session — **the moment `Popen` returns, before stdin is fed and before
the collector starts**, so a runtime can register the group with `twine
kill` before the child has done anything: the Arc 2 loop composes
`run(argv, …, on_spawn=lambda pid: register_group(state_dir, sid, pid))`
(§14.4). A hook that raises must not leave the child running unattended:
the runner SIGKILLs the child's group, waits for it, reaps the child and
re-raises the hook's exception unchanged. Every runner takes the keyword,
the doubles in `tests/helpers.py` included (they record it and never call
it — a double spawns nothing). Nothing in Arc 1 wires the hook to the
record for real; a test does, end to end (a child started through
`run_process` with the hook registering into a temp state directory reads
itself back out of that directory's record while it runs). `twine kill`
never reads the hook; the record is all it relies on.

**The group wait** (session 5b). However the run ended — the child's exit,
the timeout, the cap, or the pipes reaching EOF in the same instant the
child exits (before session 5b that last case could skip the kill, leaving
a member that held no pipe alive) — `run_process` sends SIGKILL to the
group, then returns only once no member of it is alive, or after two more
seconds (`GROUP_GRACE_SECONDS`), naming the members still alive in
`RunResult.group_survivors` (a tuple of pids, default `()`) and logging
them. Both happen before the child is reaped — the runner learns of the
exit without reaping (`waitid` with `WNOWAIT`) — so the child's zombie still
holds the group id and neither can reach a group that reused the number. When
the pipes reach EOF with no timeout or cap, the runner first gives the
child up to two seconds (`PIPE_GRACE_SECONDS`) to exit on its own — a child
that closes its pipes in its exit handler (coreutils `cat`) would otherwise
be killed in that gap and reported as the runner's SIGKILL — so a clean
exit's code is always the child's own. A member is alive unless the kernel
reports it a zombie or dead: a SIGKILLed process closes its descriptors
before it becomes a zombie, and before this wait a caller could see the
pipes close while a member still ran (session 5a's HOLD). Members are
read from `/proc`; where there is none the wait is skipped and logged and
`group_survivors` is `()`. So a `RunResult` promises: the group was sent
SIGKILL, and — on Linux — nothing of it was alive when the run returned,
or the survivors are named. It promises nothing about a process that left
the group. `twine kill` does not rely on it: its group wait is its own
(§14.4). Tests inject a double with the same signature:
`tests/helpers.py` carries `RecordingRunner` and `FixturePlayer`, the
latter answering a `bale …` argv from `fixture_relpath(argv[1:], where)`
— the argv normalized, per-run values replaced by their roles — with
the exit code `fixtures/README.md` records for it (§7).

## 11. The bale hand-offs: `carry exchange` and `carry response`

The courier hands bale what it carried. Both verbs live in
`twine/commands/carry_bale.py`, run bale only through the seam (§10.6)
and build its argv only in `twine/bale.py` (`relay_argv`,
`dry_run_argv`). Neither writes a file. Both read one JSON line from bale
(`carry exchange` since session
`2026-10-08-twine-carry-exchange-json-001`).

### 11.1 Finding bale

The executable is `<root>/bin/bale`, the root resolved exactly as `bale
check` resolves it (§5): `--bale-root DIR`, else `TWINE_BALE_ROOT`, else
`command -v bale` followed to its real path and up. No root found is a
refusal; so, since session 5b, is a current directory that no longer
exists when `--cwd` is not given; a root with no runnable `bin/bale` is learned by starting it,
also a refusal (`ran` false). What is known of the install is reported
in `bale`: `executable`, `root`, `source`, `installed`, `floor`,
`floor_admits` (whether `installed` is at or above the floor, compared as a
tuple; null when either is unknown or does not parse) and `schemas_match`
(whether every schema the manifest pins is installed with its hash; null
when the gate never looked) — `pin` and `pin_matches` until session
`2026-10-12-twine-pin-floor-002`, and neither key now.

**The gate** (D2; decided by session `2026-10-03-twine-transitions-004`,
superseding carry-bale-002's report-only reading; a floor since session
`2026-10-12-twine-pin-floor-002`, D2 as amended at the sitting
`2026-10-08-open-arc2-003`, where it was an exact pin). Both verbs drive
exactly the installs `bale check` admits (§5) and refuse every other
before bale is started: one below the floor, one whose `bin/VERSION`
cannot be read or does not parse as three dotted integers, one whose
installed schemas are missing or do not hash as `[bale.schemas]` pins
them, and any bale when the floor itself is unknown (the manifest
unusable) — `ok` false, `ran` false, exit 1, the reason, in the floor's
words, in `refusals` beside any other (`twine.bale.Executable.drive_refusal`,
which reads `bale check`'s own verdict, so the two cannot disagree). The
transition table (§12) keys on bale's outcome and closure vocabularies:
the floor is the version they were read at, the schema hashes hold the
two schema-homed ones fixed above it, and the key check on each line
(§6) catches a listed key gone. A bale the gate refuses may answer in a
spelling the table has no move for, which is the surprise D17 rules out.
Raising the floor is a recording session (§6, §16) — never ambient. There
is no override flag. `bale check` and `status` report the verdict; they
drive nothing.

bale runs in `--cwd DIR` (default: the current
directory — the repo whose session the block or tarball belongs to),
with twine's environment, a 300-second timeout and a 4 MiB stdout cap;
a call past either is killed and is not ok. bale's stderr always
reaches twine's stderr, and the JSON `stderr`.

### 11.2 `twine carry exchange FILE [--block N] [--cwd DIR] [--bale-root DIR] [--json]`

- **Finding the block.** `FILE` (a path, or `-`) is read exactly as
  `take` reads it (§9.1–§9.2). The candidates are its `exchange` blocks;
  `--block N` names one by the number `take` prints (its position among
  all blocks); without it, exactly one must be present. None, more than
  one without `--block`, or a `--block` naming no block or a block of
  another kind: refused, never a guess. A `relay` block is never a
  candidate, so a `to: planner` block cannot be carried (§9.4).
- **Refused before calling bale**, every reason named at once: the
  block's integrity does not hold (the reason names the fault —
  `mismatch`, `unescaped-in-transit`, `unclosed`, `no-sid`, `no-body`,
  `no-trailer`, `body-not-json`; twine never relays a block it cannot
  vouch for, and never repairs one); its sentinel sid could be read by
  bale as a flag (it must start with a letter or digit and hold only
  letters, digits, `.`, `_`, `-` — the trailer hashes the body, not the
  sentinel); the input is unreadable or not UTF-8; `--cwd` is not a
  directory; no bale is found or startable.
- **The call.** `bale relay <sid> - --json`, `<sid>` the block's sentinel
  sid, with stdin exactly the block's own lines — BEGIN through END, LF,
  one trailing newline (`shapes.block_text`). Nothing else from the input
  reaches bale. This is the only `relay` argv twine builds
  (`twine.bale.relay_argv`; a test asserts no other code builds one);
  the flagless `bale relay <sid> -` it replaced is retired. With `--json`
  bale prints exactly one line on stdout on every path, refusals included
  (`format_relay_json`, bale 0.4.48): twelve keys in a fixed order —
  `outcome`, `sid`, `round`, `from`, `awaiting`, `kind`, `preserved`,
  `block`, `log`, `clipboard`, `cause`, `telemetry` — exit 0 for
  `relayed` and `re-emitted`, 1 for `relay-refused`; its `block` is
  byte-identical to what the flagless form printed, and its `sid` is the
  argument as given.
- **ok** exactly when bale exits 0 and its stdout is one JSON object
  carrying every key the manifest lists for the relay surface (`outcome`,
  `sid`, `block`, `cause`; §6's key check, since session
  `2026-10-12-twine-pin-floor-002`), whose `outcome` is `"relayed"`, whose
  `sid` is the block's sid, and
  whose `block` is a non-empty string that twine can **vouch for** —
  the block bale hands back is the one the courier carries next, so it is
  held to what twine asked of the block it carried in (since session
  `2026-10-08-twine-exchange-vouch-005`). Read as `take` reads text
  (CRLF→LF first, §9.1, then §9.2's scanner), the string must be
  **exactly one block** — its own lines, BEGIN through END, nothing
  before or after them; a missing final newline is the one difference
  tolerated, since human mode supplies it — of kind `exchange`, whose
  integrity holds (the trailer matches and the body is a JSON object:
  §9.2's rule, `integrity.ok` in §9.3's terms) and whose sentinel sid is
  the carried block's (bale's answer is the counterpart-facing block of
  the same session; a block of another session is not the courier's
  next hop). Otherwise not ok, exit 1, the
  reason naming each thing that differs, at once: bale's exit status (or
  that it timed out or was capped); on `relay-refused`, bale's `cause`,
  quoted whole — the only account of why; twine names it and never
  dispatches on its wording, which bale documents as its stderr text and
  free to change; a listed key absent from the line (§6, the key and the
  surface named); an outcome other than `relayed` — `re-emitted` named as
  having recorded nothing (twine always passes the block, so it should
  never see one), any other value named as one twine does not know; a
  `sid` that is not the block's; a `block` that is null, not a string, or
  empty; a stdout that is not one JSON object (empty, or not JSON); and,
  appended after those, each way the block fails the vouch, every one
  opening `twine cannot vouch for the block bale handed back:` — no block
  at all; more than one (each named by number, kind and sid); text around
  the one block (where it sits, by line); a block of another kind; a
  failed integrity, named by `take`'s fault (`mismatch`,
  `unescaped-in-transit`, `unclosed`, `no-sid`, `no-body`, `no-trailer`,
  `body-not-json`) with `take`'s account of it; an exchange block of
  another session. A block that fails the vouch is never repaired. The
  line was still read and understood: `outcome` stays `relayed` and
  `relay` carries the line whole; what failed is the vouch. bale's
  stderr surfaced; no traceback.
- **Human mode**: on ok, stdout is exactly the line's `block` — the
  block the courier carries next, byte for byte what the flagless relay
  printed, so `twine carry exchange turn.txt > next.txt` is unchanged (a
  final newline is supplied if the block lacked one); otherwise one line,
  `carry exchange FILE: refused — …` or `… NOT OK — …`, never the block.
  A block twine could not vouch for is never printed, on any path: the
  twin's `stdout` is bale's JSON line as on every path, and human stdout
  is the one `NOT OK` line.

The JSON twin, `command` `"carry exchange"`. Fixed names:

| key | value |
|---|---|
| `sid` | the chosen block's sentinel sid; null when none was chosen |
| `block` | the number `take` prints for it; null when none was chosen |
| `ran` | whether bale was started |
| `exit_code` | bale's exit status; null when it did not run or was killed |
| `stdout` | bale's stdout as text — the JSON line; `""` when it did not run |
| `stderr` | bale's stderr as text |
| `reason` | every refusal and failure, `; `-joined; null when ok |
| `refusals` | the reasons bale was not called, in order |
| `relay` | bale's line parsed, when stdout is one JSON object; else null |
| `outcome` | `relay`'s `outcome`, or null |

`relay` and `outcome` joined the fixed names in session
`2026-10-08-twine-carry-exchange-json-001` (`VERSION` 0.10.0), present
on every path; `stdout` has carried the JSON line, not the block, since
then. twine reads the line's `outcome`, `sid`, `block` and `cause` and
carries the rest whole in `relay` (the consumption manifest's `keys`).
And beside them: `integrity` (the chosen block's, as §9.3 reports it, or
null), `argv` (the argv handed to the seam; null when none was),
`stderr_truncated`, `timed_out`, `capped`, `duration_seconds`, `cwd`,
`bale` (§11.1), `input` (as `take`'s).

### 11.3 `twine carry response TARBALL [--cwd DIR] [--bale-root DIR] [--json]`

The courier checks a response tarball with bale and hands the operator
the line that applies it. **It never applies anything** (T12).

- **Refused before calling bale**: `TARBALL` is not an existing file
  (made absolute against the current directory, `~` expanded; no search
  path — the operator names the file); `--cwd` is not a directory; no
  bale is found or startable.
- **The call.** `bale apply --dry-run --json <absolute path>`, stdin
  `/dev/null`. This is the only `apply` argv twine can build
  (`twine.bale.dry_run_argv`; a test asserts no other code builds one):
  never without `--dry-run`, never an admission or override flag — a
  refusal is surfaced, never admitted. The path is absolute, so it can
  never read as a flag.
- **ok** exactly when bale exits 0 and its stdout is one JSON object
  carrying the key the manifest lists for the apply surface (`outcome`;
  §6's key check, since session `2026-10-12-twine-pin-floor-002`) whose
  `outcome` is `"dry-run"`. Otherwise not ok, exit 1, the reason naming
  what bale said — its exit status, a listed key absent (named, with the
  surface), its outcome, or that its stdout was not one JSON object —
  bale's stderr surfaced; no traceback.
  Under `--dry-run` bale 0.4.51 documents three answers
  (`format_apply_json`'s docstring, unchanged since 0.4.45): `dry-run`
  with exit 0; `scope-drift-refused`, `required-check-refused` or
  `base-drift-refused` with exit 1, the line still on stdout; or an error
  path, nothing on stdout and a non-zero exit (telemetry `rejected`). The
  first two are recorded (§11.4); the rest documented, not recorded. The
  transition table's `apply-outcome` axis gives each its move.
- **The apply line**, on ok only: `bale apply ` and the absolute path,
  quoted by Python's `shlex.quote` (only when the shell needs it) — one
  line, pasteable as is.
- **Human mode**: on ok, stdout is exactly the apply line and a newline;
  otherwise one line naming why. Diagnostics go to stderr.

The JSON twin, `command` `"carry response"`. Fixed names:

| key | value |
|---|---|
| `tarball` | the absolute path; null when it is not an existing file |
| `ran` | whether bale was started |
| `exit_code` | bale's exit status; null when it did not run or was killed |
| `dry_run` | bale's stdout parsed, when it is one JSON object; else null |
| `outcome` | `dry_run`'s `outcome`, or null |
| `apply_line` | the line on ok; null otherwise |
| `stderr` | bale's stderr as text |
| `reason` | every refusal and failure, `; `-joined; null when ok |
| `refusals` | the reasons bale was not called, in order |

And beside them: `stdout` (bale's, as text), `argv`, `stderr_truncated`,
`timed_out`, `capped`, `duration_seconds`, `cwd`, `bale` (§11.1).

### 11.4 What is recorded, and what stands in

The clean dry run is recorded at bale 0.4.49 with its exit, and again at
0.4.51 with its stderr
(`fixtures/bale-0.4.51/scratch/apply_--dry-run_--json_tarball+dry-run.json`,
exit 0, in the scratch repository for its scoped session), and so is the
scope-drift refusal the 2b-ii carry-forward owed (`…+scope-drift-refused.json`,
exit 1, `drift` naming the out-of-scope path and bale's remedy line) —
the tests replay each by selecting its group (§7). **`bale relay --json`
is recorded at 0.4.51 under twine's own argv**, `relay <sid> - --json`,
in the scratch repository, four lines, each with its exit and its stderr:
`relayed` (`…/scratch/relay_sid_stdin_--json+relayed.json`, exit 0, round 1
of `2026-10-08-sc-002`, the paste block on stdin — bale's stderr says
`paste block read from <stdin> (trailer verified)` — its `block` the
counterpart's paste block), `re-emitted` (`relay_sid_--json.json`, exit 0,
run with no input), and two `relay-refused` lines, exit 1, each named by
its line's `reason` — `…+relay-refused+not-an-object.json` (stdin neither a
paste block nor JSON) and `…+relay-refused+not-open.json` (the block under
a sid not open, `no-such-sid-twine-051`). **The stdin form is recorded,
so the assumption is gone**: 0.4.49's recordings were made with a file
argument and replayed for `-` on a reading of `_read_relay_input`; the
0.4.51 ones are the call twine makes — the block the tests carry is byte
for byte the stdin the relayed round was recorded with (964 bytes,
`7921f0df…`) — and the fixture player answers twine's argv from them
(`RecordedRelay` replays the same bytes, exit and stderr). What still
stands in: the `re-emitted` line answers an argv twine never builds, so
replaying it proves only that twine never accepts one; the `not-an-object`
refusal, bale's answer to stdin that was no block, stands for any refusal
of what bale ingested when replayed for a block twine vouched for. The
relayed line's own `block` is the input the tests carry (an intact
exchange block of `2026-10-08-sc-002`: `take` reads it as one `exchange`
block whose trailer holds), so each recording answers for its own sid; the
not-open line is replayed for that block with its sentinel naming the
refused sid (the trailer hashes the body, not the sentinel). **Retired with the flagless relay**: its
manifest surface, its stand-in (the crafter's `--emit-block` emission,
which stays the `exchange` format's fixture, `take` reading it) and the
`BaleDouble` relay answers. What no relay recording covers — a timeout, a
capped stdout, a stdout that is not one JSON object, an exit-1 empty
stdout, an edited line — is a double named as such (`RecordedRelay` with
bytes or an exit named as not bale's). So is every block twine cannot vouch
for (since session `2026-10-08-twine-exchange-vouch-005`; the recorded
`relayed` block is intact, so no recording shows one): the relayed line
with its `block` replaced — edited after its trailer, its trailer or END
cut, the crafter's block unescaped in transit, a BEGIN with no sid, two
blocks in one string, prose or a blank line around the block, no block,
the crafter's light block, the block naming another sid — and blocks
`tests/test_carry_bale.py` builds by hand for `no-body` and
`body-not-json`, each named as not bale's; one is replayed end to end
through `StubBale`. So is every line that lacks a key the manifest lists
(since session `2026-10-12-twine-pin-floor-002`, §6's key check; bale
prints every key on every outcome, so no recording shows one): the relayed
recording with one listed key deleted — absent, not null — each of
`outcome`, `sid`, `block` and `cause`, and two at once, one replayed end to
end through `StubBale`; the recorded dry run with `outcome` deleted; and,
to prove an extra key is free, each with a key bale never printed added —
`tests/helpers.py` `drop_key`, every such line named as not bale's. For
the dry run, the other two
`*-refused` outcomes, every HOLD, non-zero exit and timeout are doubles
in the tests, named as such, never a file under `fixtures/`; a
recording replaces one. The doubles speak bale's spellings (since session
4): a refusal under `--dry-run` is a `*-refused` outcome with exit 1, a
bale error prints nothing on stdout and exits non-zero, and the one
outcome no bale emits — used to prove twine names an outcome it does not
know — is spelled `twine-test-not-a-bale-outcome` (`tests/helpers.py`
`NOT_A_BALE_OUTCOME`).

## 12. `twine transitions [--table PATH] [--json]` — the transition table (D17)

Every way a worker session or turn can end, each with a declared move;
no default case. The data is `share/transitions.toml`; the loader and
checker is `twine/transitions.py` (pure); the verb is
`twine/commands/transitions.py`. Architect's requirement (D17),
verbatim: "there shouldn't be any surprises, and every path taken should
have a defined response."

### 12.1 What it reads, and what it never does

The table file and the consumption manifest (§6) — two of twine's own
files — and nothing else. It **reads no bale install, runs no subprocess
(it never calls `ctx.run`), consults no `--bale-root`,
`TWINE_BALE_ROOT` or `PATH`, and reaches no network**; neither module
imports a process-spawning or network module, and a test asserts both.
Its `ok` is the table's alone: the same whether or not bale is
installed, and whatever version is. `--table PATH` checks another table
file against the same vocabularies (a draft, or a test's edited copy).

### 12.2 The table

Four axes, rendered in this order:

| axis | keys | source |
|---|---|---|
| `telemetry-outcome` | the 13 telemetry outcomes of the bale at the floor (0.4.51's; unchanged since 0.4.45, and held fixed above the floor by the schema's pinned hash) | §6 `[[vocabulary]]` |
| `closure-reason` | the 9 closure reasons of the bale at the floor (0.4.51's; unchanged since 0.4.45, held as above; `null`, "not closed", is not a key) | §6 `[[vocabulary]]` |
| `apply-outcome` | the 9 outcomes `bale apply --json` prints | §6 `[[vocabulary]]` |
| `stop` | twine's API-side stop set, declared in the table: `end-turn`, `max-tokens`, `model-refusal`, `window-exhausted`, `rate-limited`, `overloaded`, `network-failure`, `timeout`, `tool-error`, `malformed-shape`, `cap-reached`, `killed`, `cap-unchecked` (13; the last added by session 5b) | the table's `keys` |

A bale axis takes its keys from the manifest's vocabulary of the same
name and never declares its own, so its keys are exactly bale's
spellings, no more and no fewer. The stop names are twine's: each model
adapter maps its provider's stop reasons onto them when the loop is
built (Arc 2), verified against the SDK then. A **move** has a name, an
`actor` — exactly one of `twine`, `operator`, `planner`; a move needing a
decision is never twine's (N4) — and a one-sentence `description` of
what happens next. No move has twine merge or apply anything (T12).
Two moves are D17's, ratified: `revert-and-repack` for `held` (both
`telemetry-outcome` and `apply-outcome`), and `respawn-from-request`
for `malformed_response` (`closure-reason`) and `malformed-shape`
(`stop`). The cost spine's two stops have two moves: `cap-reached` is
`stop-at-cap` (the cap refused; raise it or close), and `cap-unchecked` is
`fix-and-resume`, the operator's — the check could not run, so the remedy
is to fix the named fault (write the price row, repair the stream line,
name a state directory) and resume, never to raise the cap. `killed` is
`close-aborted`, twine's (§14). The table has 44 rows.

### 12.3 ok, and the problems that make it false

`ok` is true **exactly when every key of every axis has one row and
every row's move is declared**. Otherwise `ok` false, exit 1, one JSON
line, no traceback, and each fault a problem naming what is at fault:

| kind | names |
|---|---|
| `missing-row` | the axis and key with no row |
| `duplicate-row` | the axis and key with more than one |
| `unknown-key` | a row's axis and key that is not one of the axis's keys — on a bale axis, "not one of bale <floor>'s spellings" |
| `unknown-axis` | a row's axis no `[axis.*]` declares |
| `undeclared-move` | the row's axis and key, and the move it names |
| `malformed-move` | a move without exactly one actor of the three, or without a description: it is not declared |
| `missing-vocabulary` | a bale axis the manifest records no vocabulary for (or the manifest is unusable) |
| `missing-axis` | a vocabulary the manifest records for an axis the table lacks |
| `catch-all-key` | a key spelled as a default case (`*`, `default`, `other`, …) on any axis |
| `malformed-axis`, `malformed-row` | the axis or row that does not have the table's shape |
| `unusable` | the table file cannot be read or parsed |

### 12.4 The JSON twin

One line (§3), `command` `"transitions"`. Fixed names:

| key | value |
|---|---|
| `rows` | every row: `axis`, `key`, `move` (strings), plus `actor` (the move's, or null when it is not declared) and `means`; in axis order, then the key's place in its vocabulary; rows refused as unknown follow |
| `moves` | an object keyed by move name: `actor`, `description` (strings), `grounds`, `rows` (how many name it) |
| `problems` | each fault: `kind`, `axis`, `key`, `move` (null where not applicable), `message` |
| `reason` | every problem's message, `; `-joined; null when ok |

And beside them: `table` (the file read), `written_against` (the bale
version the table's bale axes are spelled for — still `0.4.49` at the
0.4.51 floor, since the table was left untouched when the vocabularies did
not move; reported beside `floor`, never gated on), `floor` (the
manifest's; `pin` until session `2026-10-12-twine-pin-floor-002`, and no
`pin` key now),
`axes` (each `name`, `source`, `home`, `means`, `keys`), `counts`
(`axes`, `keys`, `rows`, `moves`), `unused_moves` (declared moves no row
names — reported, not a fault).

Human mode prints the same facts: the verdict line, each axis with one
line per row (`key -> move [actor]`), the moves with their actors and
descriptions, and every problem.

### 12.5 Tests

`tests/test_transitions.py` walks every key of every axis with logic of
its own and fails naming each axis and key without a move, each row
whose move is undeclared, and each bale-axis key that is not bale's
spelling; it proves each detector fires against tables edited to be
wrong (a row removed, an undeclared move, an invented key — the retired
doubles' `refused` and `hold` among them — and the module's other
problems). The bale axes are held to `tests/helpers.py`
`BALE_VOCABULARIES`, the probe's lists, and
`tests/test_consumption_manifest.py` asserts the manifest's lists and
the table's bale-axis keys agree.

## 13. `twine spend` — the cost spine (D15)

Arc 1 session 5a. Twine's usage record, the running totals over it, and
the hard cap's pre-call check. The kill-switch — the between-calls abort,
the process-level kill and the `aborted` closure — is session 5b's: §14. The pure module is `twine/spend.py`; the verbs are
`twine/commands/spend.py`. Doctrine: PLANNER.md §17, "refuse loudly, never
degrade silently".

### 13.1 What is known, and what is not

**No provider usage has been recorded yet.** Nobody has seen what a
provider's API returns as usage: its field names, whether it reports
thinking separately, its cache-write tiers. The gated probe
**`twine-usage-record`** is what will record it; it waits on a funded key.
So the spine **never sees a provider's shape**: it reads and writes only
twine's own usage record (§13.3), in twine's own five token classes.
Mapping a provider's usage onto that record is the model adapter's job
(Arc 2), verified against that recording when it exists. Every usage value
in `tests/` is a twine record built by `tests/helpers.py`
`usage_double`, named as a double; nothing in the tree claims to be an API
response.

**Twine ships no prices** (§13.4). Neither module makes a network call,
starts a subprocess (the verbs never call `ctx.run`) or imports a provider
SDK; a test asserts the imports.

### 13.2 The state directory

`--state-dir DIR` on every spend verb, else `$TWINE_STATE_DIR`, else
`${XDG_STATE_HOME:-$HOME/.local/state}/twine` — first rule that answers. A
relative `$XDG_STATE_HOME` is ignored (the XDG spec). With none of them
set, the verbs refuse (`no-state-dir`) rather than invent a location; the
working directory is never a fallback. An empty `--state-dir` or `--prices`
names nothing and is refused (`bad-argument`), never read as an absent flag;
an empty environment variable is unset. The JSON names the directory and
the rule (`state_dir`, `state_dir_source`: `"--state-dir"`,
`"TWINE_STATE_DIR"`, `"XDG_STATE_HOME"` or `"HOME"`).

Spend never lands inside a bale project's working tree by default: it would
dirty the tree bale checks, and it is twine's state, not the project's
(N4: deleting twine's state loses "spend history and nothing else"). The
tests never touch the real default; each uses its own temporary
directory.

### 13.3 The usage record: `<state-dir>/spend.jsonl`

Twine's durable spend stream. **Append-only, one JSON object per line, one
line per model call**, UTF-8, every line LF-terminated. Required keys:

| key | value |
|---|---|
| `sid` | the session the call ran in (a non-empty string) |
| `served_sid` | the session the spend served, or `null`. T11's envelope: a `delegate` child or a `compare` session bills to the session it served. Reserved now, nullable, and `null` when the call served its own session — a record whose `served_sid` equals its `sid` is malformed (it would count twice against that session) |
| `model` | the model id the call ran on (a non-empty string) |
| `tokens` | an object with exactly five keys, `input`, `output`, `thinking`, `cache_read`, `cache_write`; each a non-negative integer, except `thinking`, which is `null` when the provider does not report thinking separately |

The classes are **disjoint**: tokens counted in `thinking` are not also in
`output`. When `thinking` is `null` the provider's thinking tokens are
inside `output`, counted once. Cached thinking that is read back counts as
`cache_read` (D20: "cached thinking reads count as input").

Other keys are allowed. Twine's writer adds `recorded_at` (UTC, RFC 3339,
seconds) and takes any other key a caller passes (a call id, a stop
reason). **A reader keeps unknown keys and never fails on them.**

The writer is `twine.spend.append_record(state_dir, sid=, model=, tokens=,
served_sid=None, extra=None)` — the Arc 2 loop's, after every call; no verb
writes the stream. It validates the record by the same rule the reader
applies (`record_faults`) before a byte is written, creates the directory
(mode 0700) and the file (0600) when absent, writes the line with one
`O_APPEND` write and fsyncs it, and refuses to append onto a stream whose
last line is not LF-terminated (a torn write), leaving it untouched.

A **malformed line** — not UTF-8, not JSON, blank, a JSON value that is not
an object, a duplicate key, a missing required key, a `tokens` without
exactly the five classes, a count that is negative or not an integer
(`true` and `1.5` are not counts), a torn last line — makes the stream
unusable. It is named by its 1-based line number and **never skipped
silently**; every bad line is reported, not just the first.

### 13.4 Prices are operator data

- **The file:** `--prices PATH`, else `<state-dir>/prices.toml`. One table
  per model id, in US dollars per million tokens:

  ```toml
  [model."<model id>"]
  input = <USD per million tokens>
  output = <USD per million tokens>
  cache_read = <USD per million tokens>
  cache_write = <USD per million tokens>
  source = "<where the price was read>"      # optional, yours
  as_of = "<date>"                           # optional, yours
  ```

  All four classes are required; each a finite, non-negative number. Other
  keys, in a row or at the top, are the operator's and are kept. Thinking
  has no price of its own: it is **billed at the model's `output` price**
  (D20).
- **What ships:** twine ships no price file and no price values. The
  tests' price tables are doubles with invented prices for invented model
  ids (`tests/helpers.py` `PRICES_DOUBLE`), and a test asserts that no
  price file, and no price table with a number in it, is in anything twine
  ships — `bin/`, `twine/`, `share/`, `fixtures/` and the docs. The scan is
  an allow-list: it never reads `claude/checkpoints/` (blind), archived
  responses or `tests/`.
- **Refusals:** a model with no price row is `unpriced-model`, naming it;
  an absent file is `no-prices` (it says twine ships none); a file that is
  not TOML, whose `model` is not a table of tables, or any row of which
  lacks a class or carries a bad value is `malformed-prices`, naming each
  fault. The whole file is validated, not only the rows a caller needs.
  None is ever a zero, a guess or a skip.

### 13.5 Cost

For one call: `(input × input_price + output × output_price + cache_read ×
cache_read_price + cache_write × cache_write_price + thinking ×
output_price) / 1 000 000`, the thinking term only when `thinking` is not
`null`. Prices are parsed as decimals and the arithmetic is exact
(`decimal.Decimal`): every sum and the cap comparison are made on the
exact value. The JSON numbers are that value rounded to a double at the
edge; a check's decision was made on the exact value, not on them. Human
output prints the exact amount (`$0.0068175`).

### 13.6 `twine spend totals [--sid SID] [--state-dir DIR] [--prices PATH] [--json]`

Renders the stream: per session, the call count, the token totals by
class, and the cost. Writes nothing.

The JSON twin, beside `command` and `ok`. Fixed names:

| key | value |
|---|---|
| `sessions` | one object per session in the stream, in order of first appearance (as `sid` or as `served_sid`); only the named one with `--sid` (`[]` when the stream has none for it) |
| `total_cost_usd` | the whole stream's cost, each record counted once — whatever `--sid` says; a JSON number, or `null` when the stream cannot be priced or read |

Each session object:

| key | value |
|---|---|
| `sid` | the session |
| `calls` | its own records (`sid` is this session), an int |
| `tokens` | the five classes summed over its own records. `thinking` is the sum of the non-null values, and `null` only when every one of its records had `null` (a session with no records of its own reports `0`) |
| `cost_usd` | its own records' cost, a JSON number |
| `served_cost_usd` | the cost of records whose `served_sid` is this session, a JSON number |
| `served_calls` | how many records those are |
| `models` | the model ids of its own records, sorted |

A session the stream names only as a `served_sid` has a row with
`calls: 0`. And beside them: `sid` (the `--sid` given, or null), `records`,
`unpriced_models`, `refusal`, `reason`, `problems` (each `{line, message}`,
at most 50) and `problems_total`, `state_dir`, `state_dir_source`, `stream`,
`stream_present`, `prices`, `prices_source` (`"--prices"` or
`"state-dir"`), `prices_read`.

**ok.** An empty or absent stream is `ok` true with `sessions: []`; the
price file is not read (there is nothing to price). Otherwise every record
is priced. Not ok — exit 1, one JSON line, no traceback, `refusal` naming
the fault and `reason` saying it:

| `refusal` | when | what still renders |
|---|---|---|
| `malformed-stream` | a line is not a usage record (§13.3), named by number in `problems` and `reason` | `sessions: []` — a partly read stream is not totalled |
| `unreadable-stream` | `spend.jsonl` exists and cannot be read | `sessions: []` |
| `no-prices`, `malformed-prices` | the price file is absent or not a price table (§13.4) | the sessions' calls and tokens; every cost `null` |
| `unpriced-model` | any record's model has no price row; `unpriced_models` lists them | the sessions' calls and tokens; every cost `null` — a partial sum is never reported as a total |
| `no-state-dir`, `bad-argument` | §13.2 (including an empty `--state-dir` or `--prices`); a `--sid` that is not a session id | nothing; the paths `null` when unresolved |

Human mode: a verdict line, then per session a line of calls and costs and
a line of tokens; each line problem.

### 13.7 `twine spend check --sid SID --cap USD --model MODEL --input N --max-output N [--state-dir DIR] [--prices PATH] [--json]`

**The hard cap's pre-call check.** What the Arc 2 loop will run, as a
function (§13.8), before every model call; here it can be run by hand. It
writes nothing. It admits the call only if

    spend so far + worst case <= cap

- **Spend so far** is the session's own `cost_usd` plus its
  `served_cost_usd` (§13.6). T11: what an effort mechanism spent for this
  session counts against its envelope. Other sessions' spend does not.
- **The worst case** prices all `--input` tokens at the dearest input-side
  price the model has — the largest of `input`, `cache_read` and
  `cache_write` — and all `--max-output` tokens at the `output` price.
  Thinking falls inside the output bound, at the output price.
- **The cap** is a per-session value passed in (`--cap`, in US dollars, or
  the function's argument). Where its value comes from — the office's house
  rules (Q-6) — is not this session's.

**Admitted:** `ok` true, `admitted` true, `stop` null, exit 0. **Refused
by the cap:** `ok` false, exit 1, `refusal` and **`stop` both
`"cap-reached"`** — the key on the transition table's `stop` axis whose
move is `stop-at-cap` (§12) — and the numbers that decided it. **A refusal never shrinks the call to
fit**: the call as asked (`input_tokens`, `max_output_tokens`) is reported
unchanged, and nothing in the result offers a smaller one.

**If the cap cannot be checked, the call does not happen.** Each of these
is `ok` false, `admitted` false, exit 1, **`stop` `"cap-unchecked"`** (the
`stop` key whose move is `fix-and-resume`, the operator's; session 5b),
its own `refusal` and `reason` — never an admission:

| `refusal` | when |
|---|---|
| `unpriced-model` | the call's model, or a model in the session's own or served records, has no price row (`unpriced_models` names them); another session's unpriced history does not block this session |
| `no-prices`, `malformed-prices` | §13.4 |
| `malformed-stream`, `unreadable-stream` | §13.3: anywhere in the stream — a stream that cannot be read whole cannot say what this session spent |
| `bad-argument` | `--cap` is not a finite, non-negative number; `--input` or `--max-output` is not a non-negative integer (a named refusal, exit 1 — not a usage error); `--sid` or `--model` is empty; `--state-dir` or `--prices` is empty |
| `no-state-dir` | §13.2 |

A missing flag is argparse's usage error (exit 2, nothing on stdout, §3).

The JSON twin, beside `command` and `ok`. Fixed names:

| key | value |
|---|---|
| `admitted` | whether the call may be made; equal to `ok` |
| `stop` | `null` when admitted; `"cap-reached"` exactly when the cap refused the call; `"cap-unchecked"` for every other refusal (`twine.spend.STOP_CAP_REACHED`, `STOP_CAP_UNCHECKED`) — so the loop always stops with a key the table has a move for |
| `refusal`, `reason` | why it was not admitted; `null` when admitted |
| `spend_so_far_usd` | own + served, a JSON number |
| `worst_case_usd` | the call's worst-case cost |
| `cap_usd` | the cap |
| `projected_usd` | spend so far + worst case: what was compared with the cap |

And beside them: `sid`, `model`, `own_cost_usd`, `served_cost_usd`,
`calls_so_far` (the session's own records), `input_tokens`,
`max_output_tokens`, `input_price_class` (which input-side class was
dearest), `input_price_usd_per_mtok`, `output_price_usd_per_mtok`,
`unpriced_models`, `problems`, `problems_total`, `state_dir`,
`state_dir_source`, `stream`, `prices`, `prices_source`. The money fields
are `null` when the check could not compute them.

Human mode: one verdict line — `admitted`, `REFUSED (cap-reached) — the call
is not made, and it is not shrunk to fit`, or `NOT CHECKED (<refusal>; stop
cap-unchecked) — …; the call is not made` — then the arithmetic.

### 13.8 One function, two faces

The verbs are thin over `twine/spend.py`, and the Arc 2 loop calls the same
functions, so it never re-implements the check:

```
spend_totals(state_dir: Path, prices_path: Path | None = None,
             sid: str | None = None) -> TotalsReport
check_call(state_dir: Path, *, sid: str, cap_usd: Decimal, model: str,
           input_tokens: int, max_output_tokens: int,
           prices_path: Path | None = None) -> CallCheck
append_record(state_dir: Path, *, sid: str, model: str,
              tokens: Mapping[str, int | None], served_sid: str | None = None,
              extra: Mapping[str, Any] | None = None) -> UsageRecord
resolve_state_dir(flag: str | None, env: Mapping[str, str]) -> StateDir
```

`prices_path` None is `<state_dir>/prices.toml`. Neither `spend_totals` nor
`check_call` raises for a fault it anticipates: each returns a report whose
`ok` (the check's `admitted`) is false and whose `refusal` is one of the
closed set `twine.spend.REFUSALS`. A caller that reads only `admitted`
fails closed. `as_json()` on each report is the verb's payload; a test
asserts the verb's JSON equals the function's.

### 13.9 Tests

`tests/test_spend.py`. Every stream is written through `append_record` or,
for a line the writer would refuse, raw bytes, into a
`tests/helpers.py` `SpendStateDouble` (a temp directory); every usage value
is `usage_double`, every price `PRICES_DOUBLE` or a table written inline —
doubles, named as such, for invented model ids. No test resolves the real
default state directory: the in-process runs have an empty environment,
and the subprocess runs carry no `HOME`, so a verb without `--state-dir`
refuses.

## 14. `twine kill SID [--state-dir DIR] [--cwd DIR] [--bale-root DIR] [--grace SECONDS] [--json]` — the kill-switch (D15)

Arc 1 session 5b, corrected and extended by session 5c
(`2026-10-05-twine-kill-followups-003`) and by
`2026-10-06-twine-clear-group-003`. D15, the architect's words: "every
session spawn should come with a foolproof kill-switch and running total
of the money used through the api, including a hard cap for budget
reasons"; the kill "must work when the harness itself is wedged". The
running total and the cap are §13's. This is the kill-switch, in three
layers: the **between-calls abort**, the **process-level kill** and the
**`aborted` closure**. The module is `twine/kill.py`; the verb is
`twine/commands/kill.py`, thin over it. `twine kill` is the operator's one
line; the Arc 2 loop calls the same functions (§14.8).

### 14.1 Refused before anything is done

Every reason named at once, in `refusals` and `reason`; `ok` false, exit 1,
`stopped_at` `"refused"`, and **nothing is done** — no file written, no
signal sent, no bale started:

- SID is not a session id: it must start with a letter or digit, hold
  only letters, digits, `.`, `_`, `-` (the rule `relay_argv` applies, §11.2;
  it names a file and is passed to bale as an argument) and be at most 200
  characters (`twine.kill.is_sid`);
- no state directory (§13.2's resolution and refusals: `--state-dir`, else
  `$TWINE_STATE_DIR`, else XDG, else refused; never the working directory;
  an empty `--state-dir` is refused), **or one that does not exist** (or is
  not a directory, or cannot be looked at — no search permission on a
  parent — each a named refusal, never a traceback). A kill never creates
  the directory it reports to: the
  runtime writes its running record there and the loop reads its abort
  request there, so a kill written anywhere else — a mistyped `--state-dir`
  — would be an ok kill that stopped nothing. A session that never ran
  under twine has nothing to kill; the reason names `bale unlock <sid>
  --reason aborted` for it (`twine status` says which directory twine
  resolves, §4);
- `--cwd` is not a directory, or, without `--cwd`, the current directory no
  longer exists;
- `--grace` is not a finite, non-negative number of seconds of at most 600
  (a named refusal, not a usage error).

A bale that is absent, unreadable or one the gate refuses (§11.1: below
the floor, a version that does not parse, schemas that do not hash as
pinned; not the pin, until session `2026-10-12-twine-pin-floor-002`) is
**not a refusal** (session 5c, the sitting's correction to 5b, on the
worker's reading of D15: the kill must work when the harness itself is
wedged, and an install the gate refuses is one of the ways it can be; the
gate exists for the closure's vocabulary, D17, not for the signal). The
bale is still located first, so the `bale` object reports what was found
on every path, but `refusals` stays empty on its account: the abort
request is written and the recorded groups are signalled and waited for,
exactly as with an admitted bale. **The gate gates the closure alone** —
`close_aborted` checks
`Executable.drive_refusal` itself and fails without starting bale (§14.5)
— so such a kill ends `stopped_at` `"closure"`, `closed` false, `ok` false,
exit 1, with the drive refusal in `reason` and the unlock line as
`operator_line`; human mode says `NOT FINISHED (stopped at closure)` and
gives the hand line.

A missing SID is argparse's usage error (exit 2, nothing on stdout, §3).

### 14.2 The three steps, in order

1. **Request the between-calls abort** (§14.3) — durably, idempotently.
2. **Kill every recorded process group**, if the session's runtime recorded
   its groups (§14.4): the runtime's own group first (so it can start
   nothing more), then every group in the record's `groups`, in record
   order — to each, SIGTERM, then SIGCONT (a stopped member sees SIGTERM
   only once continued), up to `--grace` seconds (default 5) for its
   members to go, SIGKILL if any remain, then up to 5 more seconds; the
   stale check (§14.4) per group on its own `leader_start_ticks`. The step
   is done only when **no member of any of them is alive** (or each is
   stale, or the record names no groups beyond the runtime's); otherwise it
   names every surviving pid, across all groups, and stops. Once they are
   gone the record is **re-read once**, and a group registered since (a
   hook racing the kill) is killed the same way; only then is the record
   removed. No running record is not a fault — a session between runs, or
   one whose runtime never started, has no process to kill, and `process`
   is `null`. A malformed record is a named refusal of this step (the abort
   request still lands), never a guess at a pgid.
3. **Close the session in bale with `aborted`** (§14.5) — only when the
   abort request stands and no process of any recorded group is alive (or
   none was recorded), and only with a bale the gate admits (§14.1). **No closure
   is attempted while a member of a killed group is alive**: a record that
   says `aborted` while the worker's shell still runs is the mystery D15
   forbids.

Each step is reported on stderr as it happens, and in the twin. `ok` is
true exactly when all three landed; exit 0. Otherwise exit 1, `stopped_at`
names the first step that did not complete — `abort`, `process` or
`closure` — and `operator_line` is the one line that finishes by hand:

| stopped at | `operator_line` |
|---|---|
| any step, while a recorded group is not known to be gone (survivors, no `/proc`, twine kill's own group) — whichever step stopped first | `kill -KILL -- -<pgid> -<pgid> …` — the signal and every group with survivors (every group not known to be gone), the runtime's first, then record order; one group, one pgid; then run `twine kill` again to close. A close is never handed out while a member may live |
| `process`, the record malformed — on the first read, or on the re-read | `null` — no one line finishes it safely: the record names no group (or a group registered meanwhile may be unknown), and the reason says to find and stop the session's runtime before closing it |
| `abort` (the request could not be written), no group alive | the unlock line; the reason says the abort request is missing |
| `closure`, bale refused because the session reached HOLD (its line's `outcome` is `unlock-refused` and its `reason` is `hold-branch`) | `bale revert <sid>` — bale's own remedy, which touches git and so stays the operator's; **twine never runs `revert`** |
| `closure`, any other refusal, a timeout, a line that was not the close (one lacking a listed key among them), or a bale that is absent or that the gate refuses | `bale unlock <sid> --reason aborted` (run in the repo whose session it is) |
| nothing (ok), or `refused` | `null` — nothing is left, or nothing was done: fix the named fault and run `twine kill` again |

Requesting the abort is idempotent. Running `twine kill` again after a
kill that stopped short finishes it; after one that closed the session, the
abort request and the process step are no-ops and bale refuses the closure
("not open") — not ok, exit 1, the refusal surfaced.

### 14.3 The abort request: `<state-dir>/abort/<sid>.json`

One file per session: a JSON object, `sid` and `requested_at` (UTC, RFC
3339), written durably (a temp file, fsynced, hard-linked into place, the
directory fsynced; the directory 0700, the file 0600) and only if absent —
the first request's time stands. **Its presence is the signal**: the loop
reads any file at that path, whatever its content, as a request. It
survives the runtime's death and needs no runtime to exist. It is twine's
record of intent to stop, and is never removed by twine.

`abort_requested(state_dir, sid)` is what the Arc 2 loop checks before every
model call, beside `check_call` (§13.8). Only a path that does not exist
reads as no request. A request that cannot be looked for — the state
directory unreadable, or a file where `abort/` should be — reads as
**requested** and is logged: a kill-switch that cannot be read stops the loop rather than letting
it spend (fail closed). Observed, the loop stops with the `stop` key
`killed` (`twine.kill.STOP_KILLED`; its move is `close-aborted`, twine's,
§12.2) and runs the closure (§14.5).

### 14.4 The running record, and the process kill

The runtime (Arc 2) records, before it starts a model call or a tool, the
process group it runs in: `register_running(state_dir, sid, pgid, pid)`
writes `<state-dir>/running/<sid>.json` durably, replacing an older one
(the directory is created when absent: the runtime's is the state
directory). The record is one JSON object with **exactly these six keys**
(session 5c; 5b's five and `groups`):

| key | value |
|---|---|
| `sid` | the session's; a record whose `sid` is missing or differs is malformed |
| `pgid`, `pid`, `started_at`, `leader_start_ticks` | the runtime's own group: its id, the runtime's pid, when it registered (UTC, RFC 3339), and the group leader's start time (`/proc/<pgid>/stat` field 22, or `null` when it could not be read) |
| `groups` | a JSON array, one object per **additional** group the runtime started and registered, in registration order: `{"pgid": <int above 1>, "leader_start_ticks": <int ≥ 0 or null>, "registered_at": <UTC, RFC 3339>}`; `[]` when none. The runtime's own group is **not** repeated in it |

`register_running` writes `groups: []`. `register_group(state_dir, sid,
pgid)` appends one entry — the leader's start ticks read as
`register_running` reads them, `registered_at` stamped — rewrites the
record durably the same way, and returns the grown `RunningRecord`; it
refuses (`RunningRecordError`) when there is no record to grow (the runtime
registers itself before it starts anything), when the record is malformed,
when `pgid` could not be a group to kill, and when it is the runtime's own.
It is what the seam's spawn hook calls (§10.6): the Arc 2 loop composes
`run(argv, …, on_spawn=lambda pid: register_group(state_dir, sid, pid))`,
so every tool's group is in the record the moment the tool exists. The
read-append-replace runs under an exclusive `flock` on the `running/`
directory (no lock file is added beside the record), so two registrations
at once cannot lose each other's entry. `clear_running(state_dir, sid)`
removes the record on a clean end. The record is a **cache** in N4's
sense (re-derivable; deleting it loses nothing of record), unlike
`spend.jsonl`. Nothing writes it in Arc 1 but the tests.

`clear_group(state_dir, sid, pgid)` (`2026-10-06-twine-clear-group-003`)
forgets one group: it removes **every entry of `groups` whose `pgid` is
`pgid`** — one, normally; each of them when the record names it twice (the
kill signals such a pgid once and reports it once; the clear forgets it the
same way) — rewrites the record durably as `register_group` does, still
exactly the six keys, the runtime's four values and every other entry
untouched and in their order, and returns `true`. It returns **`false`,
writing and creating nothing** (no `running/` appears where there was none),
when the record names no such group and when there is no record — a `twine
kill` may have removed it, and a session between runs has none; both are
logged, and neither is a fault: the record is a cache, and a group already
forgotten is what the caller wanted. It **refuses** (`RunningRecordError`,
the record untouched) a `pgid` that could not be a group to kill (an
integer above 1, never a bool), **the runtime's own group** (the record's
`pgid`, which is forgotten only with the whole record, by `clear_running`,
never one entry at a time) and a malformed record (`read_running`'s faults,
each named); `KillError` when the record cannot be rewritten. It runs
**under the same exclusive `flock` on `running/`** as `register_group`, so a
registration and a clear at once lose nothing of each other: afterwards the
record names exactly the groups registered and not cleared, in registration
order. `clear_running` takes that lock too, so a clear racing `twine kill`'s
removal either finishes before it or finds no record and writes nothing — a
record the kill removed **does not come back**. `clear_running`'s wait for
the lock is bounded (5 seconds; the lock is the directory's, shared by every
session's record, and a kill must not hang behind a wedged writer): past it
the record is left in place, `KillError` says so, and `twine kill` goes on
with `record_cleared` false — the groups are gone and the record is a cache.
Where `flock` is unavailable — no `fcntl`, or a filesystem that refuses the
lock (`ENOLCK`) — all three run unlocked and log it.

**The composition rule, for the Arc 2 loop.** The loop calls
`clear_group(state_dir, sid, pid)` itself, after a `run` returns with
`RunResult.group_survivors` empty — the seam's promise that the group is
gone (§10.6); the seam gets no hook for it. **An entry whose run returned
survivors stays in the record** for `twine kill` to reach: the loop never
forgets a group that may be alive. Driven so, the record holds only what is
alive — the runtime's own group and the tools still running — instead of
growing by one entry per tool for as long as the session runs. Nothing in
Arc 1 calls `clear_group` but the tests.

`read_running` requires every key. A pgid or pid that is not an integer
above 1 is refused at registration and is malformed on reading (0 would
signal the signaller's own group, 1 is init's); so is a record that is not
one JSON object, whose `sid` is not the file's, whose `started_at` is not a
non-empty string, whose `leader_start_ticks` is neither a non-negative
integer nor null, **or whose `groups` key is missing or is not an array of
such objects** — an entry that is not an object, lacks `pgid`, whose `pgid`
is not an integer above 1, whose `leader_start_ticks` is neither a
non-negative integer nor null, or whose `registered_at` is not a non-empty
string, or lacks any of the three keys; each fault named (a five-key
record of session 5b's format is one such record now, and the fault says
so). A key the format does not name is ignored on reading, as it was in 5b.

`twine kill` needs nothing from the runtime but this record (brief ruling
5): it is its own process, reads the state directory and signals; it never
reads the hook. Members of a group are read from `/proc` (a member is alive
unless the kernel reports it a zombie or dead). It signals **the runtime's
own group first**, so the runtime can start nothing more, then every group
in `groups`, in record order — each with the same SIGTERM, SIGCONT, grace,
SIGKILL and bounded wait (§14.2). Before signalling a group:

- it is **twine kill's own** process group → not signalled, and the step
  stops there: the groups after it are not signalled either, since the
  runtime that could start more is not stopped ("run twine kill from
  another shell", which takes them all);
- **stale**: its entry carries `leader_start_ticks`, and a live process now
  holds its number with another start time → that group is gone (Linux
  never hands out a pid still in use as a group id), so nothing is
  signalled, its `stale` and `dead` are true, and the kill goes on to the
  next group;
- **no member alive** → nothing is signalled; its `dead` is true.

Without `/proc` a group is still signalled, but it is never reported dead:
the step stops, saying its members cannot be enumerated. The step is
**done only when no member of any recorded group is alive** (or each is
stale, or the record names no groups beyond the runtime's): `dead` is the
record's whole, not the runtime's group alone, and `survivors` is every
surviving pid across all groups. A pgid the record names twice is signalled
once and reported once — by then its number could lead a stranger's group.

**The re-read.** Once its groups are gone, `twine kill` re-reads the record
once and treats any group registered since — a hook racing the kill — as
one more to kill the same way; a runtime that re-registered under another
number counts as such a group. Only then is the record removed (a cache,
so a later kill cannot signal a number that has been reused;
`record_cleared` says whether it did) and the closure attempted. A record
that is gone on the re-read is nothing more to do; one that has become
malformed stops the step (a group registered meanwhile may be unknown) and
is left in place, as a record malformed on the first read is left for the
operator.

**What `dead` covers, and what it does not.** `dead` means every group the
record named — on the first read and on the re-read — is gone. Two
residuals are accepted, bounded and named. The pid-reuse residual (session
5b): a recorded group dies, its number is reused by a new group, that
group's leader dies and its members remain — a full pid wrap plus that
sequence, which `leader_start_ticks` cannot tell apart. The hook's window
(session 5c): between a child's `Popen` returning and its hook's write to
the record, a runtime that is itself SIGKILLed leaves that one child
unrecorded, and no re-read can find it; the window is the hook's write,
which the seam performs before it feeds the child a byte (§10.6). A
process that left its group with `setsid` is outside every group and
outside this record, as it is outside the runner's reach.

### 14.5 The closure: `bale unlock <sid> --reason aborted --json`

Run through the seam (§10.6), with a bale the gate admits (§11.1), in
`--cwd` (default: the current directory — the repo whose session SID is),
with twine's environment, stdin `/dev/null`, a 120-second timeout and a 1
MiB stdout cap, and only with a bale the gate admits: `close_aborted`
checks the gate itself (`Executable.drive_refusal`) and fails without
starting a bale it refuses — below the floor, or schemas that do not hash
as pinned — so the loop cannot reach one by forgetting the gate. **This
is the only `unlock` argv twine builds**
(`twine.bale.unlock_argv`; a test asserts no other code builds one): the
sid always explicit — `bale unlock` with no sid closes whichever one session
is open — the reason always `aborted` — without it bale infers
`closed-read-only` or `abandoned` — never the flag that clears the lock past
a HOLD branch, never another flag, and **never a retry**. `bale unlock`
performs no git operation and merges nothing (T12 is untouched).

**ok** exactly when bale exits 0 and its stdout is one JSON object carrying
every key the manifest lists for the unlock surface (`outcome`, `sid`,
`closure_reason`, `telemetry`, `reason`, `message`, `open_sessions`; §6's
key check, since session `2026-10-12-twine-pin-floor-002` — a line lacking
one is not ok, `ran` true, the key and the surface named beside whatever
else the line fails, and the hand line chosen as below) whose
`outcome` is `"unlocked"`, whose `sid` is SID and whose `closure_reason` is
`"aborted"`; its `telemetry` (the closure record's repo-relative path, or
null) is reported. Otherwise not ok: bale's exit, its stderr and what its
stdout said instead. Since bale 0.4.47 a refusal under `--json` prints one
JSON line too — `outcome` `"unlock-refused"`, a `reason` from the closed set
`hold-branch`, `not-open`, `several-open`, `not-a-repo`, `integration-json`,
bale's `message`, `open_sessions`, the close's keys null — exit 1, and
bale's stderr ending with `[bale] error: <message>` (recorded byte-exact
since 0.4.51, beside the line: §14.7); twine reads that line as
it reads any (it is the twin's `closure`, §14.6) and names, after bale's
exit (quoting the last line of its stderr, or saying it had nothing on
stderr), each of `outcome`, `sid` and `closure_reason` that is not this
close's — the `outcome` with the line's `reason` code beside it, so a
refusal's failures read `bale reported outcome 'unlock-refused' (reason
'hold-branch'), not 'unlocked'`. Exit and stdout tell a close from a
refusal, and **twine reads no stderr text**: the hand line (§14.2) is
`bale revert <sid>` exactly when the line twine read says `outcome`
`unlock-refused` and `reason` `hold-branch`, and the unlock line for any
other reason, any other line or none (since session
`2026-10-07-twine-kill-reason-002`; before it the HOLD refusal was told by
the text `branch bale/<sid> exists` on stderr). bale's stderr is still
captured, reported (`stderr`, `stderr_truncated`) and passed through —
evidence, never a key. twine drives no bale the gate refuses, and every
bale it admits prints the line on every refusal, so there is no text
fallback. A closure that timed
out may or may not have closed the session; the reason says so, and `bale
status` is how to tell.

The closure is `close_aborted(run, executable, sid, cwd=, env=)`, shared by
the verb and the loop (§14.8).

### 14.6 The JSON twin

One line (§3), `command` `"kill"`. Fixed names:

| key | value |
|---|---|
| `sid` | SID as given |
| `abort_requested` | the abort request stands (written now, or already) |
| `process` | `null` when no running record was found; else an object: `pgid`, `pid`, `started_at` (the record's; null when it was malformed), `signalled` (whether a signal was delivered to the runtime's group), `signals` (those delivered to it, in order: `"SIGTERM"`, `"SIGCONT"`, `"SIGKILL"`), `stale` (the runtime's group's), `dead` (true only when **every** recorded group is gone, §14.4), `survivors` (every pid still alive across all groups, sorted; `[]` when dead), `groups` (session 5c: an array in signalling order, one object per additional group — the record's, then any the re-read found — with `pgid`, `signalled`, `signals`, `dead`, `survivors`, `stale`; `[]` when the record named none), `record_cleared`, `record` (its path), `error` (why the step could not finish — the whole's, each group's fault named — or null) |
| `closed` | bale closed the session `aborted` (§14.5's ok) |
| `closure` | bale's one JSON object, parsed; null when bale was not reached or printed none |
| `telemetry` | `closure`'s `telemetry`, or null |
| `operator_line` | the line that finishes by hand (§14.2), or null |
| `stopped_at` | `"refused"`, `"abort"`, `"process"`, `"closure"`, or null when ok |
| `reason` | every refusal and failure, `; `-joined; null when ok |
| `refusals` | the reasons nothing was done (§14.1), in order |

And beside them: `abort` (`path`, `already_requested`, `requested_at`),
`argv`, `ran`, `exit_code`, `stdout`, `stderr`, `stderr_truncated`,
`timed_out`, `capped`, `duration_seconds` (the bale call, as §11.2's),
`state_dir`, `state_dir_source`, `cwd`, `grace_seconds`, `bale` (§11.1).
Every path — refused, stopped at any step, ok — carries the same key set,
the uncomputed values null.

Human mode: a verdict line — `kill SID: done — …`, `kill SID: refused —
nothing was done: …` or `kill SID: NOT FINISHED (stopped at <step>) — …` —
then one line per step (`abort:`, `process:`, `closure:`), the `process:`
step one line per group (`group <pgid>: <signals>; <state>`, the runtime's
first) with a `N groups in all: …` line when there is more than one, and,
when there is one, `finish by hand: <operator_line>`. bale's stderr goes
to stderr.

### 14.7 What is recorded, and what stands in

**Six `bale unlock … --json` lines are recorded at bale 0.4.51**, each
with its exit and its stderr (session `2026-10-12-twine-pin-051-001`, by
probe `twine-051-record`; first recorded at 0.4.49 by session
`2026-10-07-twine-pin-049-001`; `fixtures/README.md`, "bale 0.4.51"): the
`aborted` close twine's own argv asks for
(`fixtures/bale-0.4.51/scratch/unlock_sid_--reason-aborted_--json.json`,
exit 0), the HOLD-branch refusal recorded just before it
(`…/scratch/unlock_sid_--json+unlock-refused+hold-branch.json`, exit 1),
the `closed-read-only` close of a read-only session and the no-op with
nothing open (both in the scratch repository), and in `~/twine-src` the
`not-open` and `integration-json` refusals. Their lines carry
`format_unlock_json`'s twelve keys, in order: the nine of 0.4.45 —
`outcome`, `sid`, `log`, `closure_reason`, `session_dir_wiped`,
`branch_preserved`, `telemetry`, `debris`, `sweep` — and the three bale
0.4.47 added for the refusal line, `reason`, `message`, `open_sessions`
(null on a close). The docstring was first read from 0.4.45's source by
the probes `twine-unlock-contract` and `twine-unlock-code` (2026-10-04);
the recordings are the contract now. **The doubles are gone**: session 5b's
`unlock_json_double`, `unlock_refusal_double`, `UnlockDouble` and the
double stdout of `StubBale` are replaced by `tests/helpers.py`'s
`unlock_recording(name)` and `RecordedUnlock`, the run-seam double that
replays a recording for twine's argv, and `StubBale` replays a recording's
file — a recording replaces the doubles and never joins them, as this
section said it would. **stderr is recorded and replayed** (since 0.4.51):
each refusal's stderr ends with `[bale] error: <message>` and a newline,
the line's own `message` — the HOLD refusal's after bale's `[bale] unlock:
<sid>` line — and `unlock_recording` returns it, `RecordedUnlock` and
`StubBale` replay it, and it reaches the closure's `stderr`, the exit
entry's quoted last line and twine's own stderr byte for byte; the
consumption manifest's `stdout` sentence ("beside `[bale] error:
<message>` on stderr") is recorded fact. (At 0.4.49 no row recorded
stderr; one refusal's was derived from its line until session
`2026-10-07-twine-kill-reason-002` retired the derivation with the text
match it fed.) twine still reads no decision from it: the hand line keys on
the line's `reason` (§14.5), and the recorded HOLD stderr — which carries
the text the hand line was once keyed on — changes nothing. A test that
proves stderr passes through and decides nothing may still feed bytes it
names as not bale's (`RecordedUnlock(stderr=…)`, `StubBale(stderr=…)`, an
empty stderr among them), as `RecordedUnlock(stdout=…)` does for stdout —
which, since session `2026-10-12-twine-pin-floor-002`, also feeds the
key check (§14.5) the recorded close and the HOLD refusal with one listed
key deleted (`tests/helpers.py` `drop_key`), and the close with a key bale
never printed added, each named as not bale's: no recording lacks a listed
key, since bale prints every key on every outcome.
One fact the tests name where they use it: the refusals were recorded under
`unlock <sid> --json`, without `--reason aborted`, and are replayed for
twine's argv on the assumption that bale refuses before the reason
matters. The session the tests kill is the recorded close's own,
`2026-10-08-sc-002`; the manifest's `unlock` surface points at the close
and lists the five other recordings as `also_recorded` (§6).

### 14.8 One function, two faces

The verb is thin over `twine/kill.py`, and the Arc 2 loop calls the same
functions:

```
request_abort(state_dir: Path, sid: str) -> AbortRequest     # raises KillError
abort_requested(state_dir: Path, sid: str) -> bool           # before every call
register_running(state_dir: Path, sid: str, pgid: int, pid: int) -> RunningRecord
register_group(state_dir: Path, sid: str, pgid: int, *, clock=, proc_root=) -> RunningRecord
                                                             # raises RunningRecordError, KillError
clear_group(state_dir: Path, sid: str, pgid: int) -> bool    # raises RunningRecordError, KillError
clear_running(state_dir: Path, sid: str) -> bool
read_running(state_dir: Path, sid: str) -> RunningRecord | None   # raises RunningRecordError
kill_one_group(pgid: int, leader_start_ticks: int | None, *, grace, wait) -> GroupStep
kill_group(record: RunningRecord, *, grace: float, wait: float) -> ProcessStep
                                                             # the runtime's group, then record.groups
close_aborted(run: Runner, executable: bale.Executable, sid: str, *, cwd, env) -> Closure
kill_session(state_dir: Path, sid: str, *, run: Runner, executable: bale.Executable,
             cwd, env, grace: float = 5.0, wait: float = 5.0) -> KillReport
STOP_KILLED = "killed"
```

`RunningRecord` carries `groups: tuple[GroupEntry, ...]` (`GroupEntry`:
`pgid`, `leader_start_ticks`, `registered_at`) and `pgids`, every group it
names with the runtime's first. `ProcessStep` carries `runtime` (the
runtime's `GroupStep`) and `groups` (the additional groups' steps, in
signalling order); its `dead`, `survivors`, `error` and `alive_groups` are
the whole's. `close_aborted` takes the seam's runner, so the tests inject a
double, and the executable as `locate_executable` found it, whose gate
verdict it checks — the one place the kill checks the gate (§14.1); the
caller has checked
that no member of any group is alive. `KillReport.as_json()` is the verb's
payload; a test asserts the verb's JSON equals the function's. Neither
module spawns a process or reaches a network: bale runs through the runner
it is handed, and signals and `/proc` reads go through `twine/process.py`'s
group helpers (`group_members`, `signal_group`, `read_stat`,
`wait_group_gone`).

The tests (`tests/test_kill.py`) kill real `setsid`-led process groups they
start (`tests/helpers.py` `RealGroup`) — one that honours SIGTERM, one that
ignores it, one with a stopped member, and records naming the runtime's
group and two more — and drive survivors, a missing `/proc`, twine kill's
own group, a hook racing the kill and a record that breaks under it
through doubles of the group helpers and of the module's own functions.
`twine kill` is run as a subprocess against a stub bale (`StubBale`) with
three real groups recorded: every pid dead, the record cleared, the stub
seeing exactly the one unlock argv. Every state directory is a temporary
one; the in-process runs carry an empty environment, so a verb without
`--state-dir` refuses rather than touch the real default; tests that wait
on a kill poll rather than check once.

## 15. `twine carry bundle BUNDLE [--check] [--cwd DIR] [--bale-root DIR] [--state-dir DIR] [--json]`

Arc 1 session 3, row 3 of `twine-seed.md` §5.1, "offline courier — emit"
(`2026-10-07-twine-carry-bundle-003`): the courier carries a planner's
bundle into bale with `bale open --json` and hands back what opens the
worker's chat — bale's `opener` and the request tarball — and keeps the
session's **in-flight record**, twine's one piece of state besides spend.
The verb is `twine/commands/carry_bundle.py`; the record is
`twine/inflight.py`.

### 15.1 Who runs `bale open`

twine does (brief ruling 1). In Arc 1 the operator runs twine's verbs and
twine runs bale. `carry response` only rehearses and hands back a line
because `bale apply` merges and T12 bars twine from merging; **`bale open`
merges nothing** — it packs a session, and an unwanted one is closed with
`bale unlock` — so a plain `carry bundle` opens, and `--check` rehearses.

### 15.2 Refused before calling bale

Every reason named at once, in `refusals` and `reason`; `ok` false, `ran`
false, exit 1, **bale not started**, nothing written:

- `BUNDLE` is empty, or — when it names no existing file — begins with `-`,
  so bale could read it as a flag (argparse lets the operator reach such a
  name only after `--`; twine refuses it anyway). An existing file whose
  name begins with `-` is fine: it is passed by its absolute path;
- `--cwd` is not a directory, or, without `--cwd`, the current directory no
  longer exists;
- no bale is found or startable, or the gate refuses it — below the
  floor, a `bin/VERSION` that cannot be read or does not parse, schemas
  that do not hash as pinned (§11.1; an exact pin until session
  `2026-10-12-twine-pin-floor-002`);
- **without `--check` only:** no state directory resolves (§13.2's rules
  and refusals, `no-state-dir` and `bad-argument`, as `twine spend` and
  `twine kill` resolve it), or the one that resolves exists and is not a
  directory, or cannot be looked at (a parent that is a file, no search
  permission — `twine kill`'s `state_dir_fault`, each a named refusal). **An
  open that could not be recorded is refused before it happens.** A state
  directory that does not exist yet is not refused: the record's writer
  creates it (0700), as spend's writer does. `--check` needs no state
  directory and never reads or writes one; `--state-dir` under `--check`
  is ignored, and stderr says so.

### 15.3 The call

- `BUNDLE` naming an existing file — relative to twine's current
  directory, `~` expanded — is passed as its absolute path; otherwise it is
  passed **exactly as given**, for bale to resolve by its own rules (the
  current directory, then `apply.search_paths`, so the bare file name the
  crafter prints works from the Downloads directory). A name twine cannot
  stat — too long, or under a directory it cannot search — is passed as
  given too, never a traceback.
- The argv is exactly `<bale> open <bundle> --json`, or with `--check`
  exactly `<bale> open --check <bundle> --json` — the two recorded argvs
  (§15.6). **This is the only `open` argv twine builds**
  (`twine.bale.open_argv`; a test asserts no other code builds one): never
  `--dry-run`, `--verbose` or `--no-sandbox`, never another flag.
- It runs through the seam (§10.6) in `--cwd` (default: the current
  directory), stdin `/dev/null`, twine's environment, a 4 MiB stdout cap
  and a **1800-second timeout** — an open runs the bundle's checkpoint
  dry-run, which may run a whole suite, so §11.1's 300 seconds is too short
  (`carry_bale.call_bale` takes the verb's timeout). **Never retried**: a
  call that timed out or was capped may or may not have opened a session;
  the reason says so, and `bale status` is how to tell. bale's stderr
  always reaches twine's stderr and the twin's `stderr`.

### 15.4 ok, and the in-flight record

**ok** exactly when bale exits 0 and its stdout is one JSON object
carrying every key the manifest lists for the open surface (`outcome`,
`sid`, `tarball`, `opener`, `desk`, `bundle`; §6's key check, since session
`2026-10-12-twine-pin-floor-002`) whose
`outcome` is `"opened"` or `"second-desk"` (without `--check`) or
`"rehearsed"` (with it), and, for the first two, whose `sid` is a string
twine accepts as a sid (`twine.kill.is_sid`, §14.1's rule) and whose
`opener` is a non-empty string. Otherwise not ok, exit 1, the reason
naming what bale said instead — its exit (`bale exited N`), the outcome it
gave and the one the mode wanted (`bale reported outcome 'rehearsed'; an
open wants 'opened' or 'second-desk'`, `…; --check wants 'rehearsed'`), a
missing sid or opener (`bale's opened line has no sid twine accepts`, `…
has no opener`), a listed key absent from the line (named with the surface;
after `opened` or `second-desk` the reason adds that the session may be
open — `bale status` in `--cwd` says which — since no record is written
for a line twine did not accept), a stdout that is not one JSON object, or a line carrying
text that is not UTF-8 (a lone-surrogate escape, as a path with non-UTF-8
bytes prints: twine can neither print nor record it as bale's, so `open`
shows `?` in its place, `stdout` keeps the raw line, and the reason says
the session may be open) — bale's stderr surfaced; no traceback;
**nothing recorded**. A line that came with a
non-zero exit is still parsed and reported (`open`, `outcome`), never
trusted.

**The in-flight record**, on ok with `opened` or `second-desk` only:
`<state-dir>/inflight/<sid>.json`, the directory 0700 (when twine creates
it; an existing `inflight/` keeps the mode it has), the file 0600,
written by atomic replace (a temp file, fsynced, renamed over the record,
the directory fsynced) under an exclusive `flock` on `<state-dir>/inflight/`
— `twine/kill.py`'s `_write_replacing` and `_locked`, imported. Exactly
these keys, in this order:

```
{"sid": <sid>, "cwd": <the absolute directory bale ran in>,
 "tarball": <bale's tarball from the opened line, or null>,
 "opens": [{"outcome": "opened" | "second-desk",
            "desk": <bale's desk: null | "desk-2" | …>,
            "bundle_sha256": <bale's bundle.sha256>,
            "opener_sha256": <sha256 of the opener's UTF-8 bytes>,
            "recorded_at": <UTC, ISO 8601, Z>}]}
```

- `opened` writes a record holding that one open, **replacing** any record
  of the same sid. Replacing is not an error: `record_error` stays null, and
  stderr says an earlier record was replaced.
- `second-desk` **appends** its entry to the record of that sid, keeping
  its `tarball` and `cwd` (the first open's). With no record, or one that
  cannot be read as this shape (§15.7), it writes a **fresh** record —
  `tarball` null, this invocation's `cwd`, only this entry — and
  `record_error` says which (`no in-flight record of <sid> to append …`, or
  the faults of the record it replaced), with a warning on stderr; the verb
  stays ok.
- **The tarball a second desk needs:** bale 0.4.49's `second-desk` line had
  `tarball` null; since bale 0.4.50 it names the outbox path when the file
  exists (the 0.4.51 recording carries it). On `second-desk` the twin's
  `tarball` is bale's when bale gives one, else the record's (a fresh
  second-desk record still keeps `tarball` null — taking bale's there is
  `twine-bundle-051`'s); `tarball_source` says which — `"bale"`,
  `"record"`, or null when neither has one. On `opened` it is bale's,
  `tarball_source` `"bale"` (null when bale gave none).
- **A record that cannot be written after a successful open does not make
  the verb not ok**: the session is open in bale, and a failure that
  invited a retry would open another desk. `record` is null, `record_error`
  names why, a warning goes to stderr, exit 0.
- The record is a **cache** in N4's sense: every value in it is bale's
  (from the line it printed) or the invocation's (`cwd`, `recorded_at`).
  Deleting it loses nothing bale does not know. **Nothing in Arc 1 removes
  it** (Arc 2's loop knows when a session closes). Two verbs read it:
  `carry bundle` itself, and `twine status` (§4, session
  `twine-status-inflight`), which lists the records and names what in
  `inflight/` is not one, writing nothing. A test pins that the record is
  the only file `carry bundle` writes, and where.

### 15.5 Output

- **Human mode, ok, `opened` or `second-desk`:** stdout is **exactly
  bale's `opener`** — its bytes, a final LF supplied if it lacked one — what
  the operator pastes into the new chat. Diagnostics on stderr name the
  sid, the desk (`the first desk`, or bale's `desk-2`, …), the request
  tarball to attach (and where it came from) or that none is known, and the
  record's path or `record_error`.
- **Human mode, ok, `rehearsed`:** one stdout line, `carry bundle BUNDLE:
  rehearsed — bale would open it (nothing written)`.
- **Human mode, not ok:** one stdout line, `carry bundle BUNDLE: refused —
  …` (bale not started) or `carry bundle BUNDLE: NOT OK — …`. `BUNDLE` in
  the human lines is the argument as the operator gave it.

The JSON twin, `command` `"carry bundle"`. Fixed names, present on every
path:

| key | value |
|---|---|
| `bundle` | the argument as passed to bale; null when refused before that |
| `check` | whether `--check` was given |
| `ran` | whether bale was started |
| `exit_code` | bale's exit; null when it did not run or was killed |
| `open` | bale's stdout parsed, when it is one JSON object; else null |
| `outcome` | `open`'s `outcome`, or null |
| `sid` | `open`'s `sid`, or null |
| `desk` | `open`'s `desk`, or null |
| `tarball` | §15.4's, or null (null on every not-ok path and on a rehearsal) |
| `tarball_source` | `"bale"`, `"record"` or null |
| `opener` | `open`'s `opener`, or null |
| `record` | the record's path when written; else null |
| `record_error` | why it was not written or was replaced fresh; else null |
| `stderr` | bale's stderr as text |
| `reason` | every refusal and failure, `; `-joined; null when ok |
| `refusals` | the reasons bale was not called, in order |

And beside them: `stdout` (bale's, as text), `argv` (the argv handed to
the seam; null when none was), `stderr_truncated`, `timed_out`, `capped`,
`duration_seconds`, `cwd`, `state_dir`, `state_dir_source` (both null under
`--check`, and when none resolves), `bale` (§11.1). Every path — refused,
not ok, opened, second-desk, rehearsed, a record that failed — carries
exactly this key set.

### 15.6 What is recorded, and what stands in

Four `bale open … --json` lines are recorded at bale 0.4.51
(`fixtures/README.md`, "bale 0.4.51"), each with its exit, its stderr and
`format_open_json`'s 23 keys — 0.4.49's 21 and the two a refusal fills
since bale 0.4.50, `reason` and `cause`: `open <bundle> --json` in the
scratch repository as `opened`
(`fixtures/bale-0.4.51/scratch/open_bundle_--json+opened.json`, exit 0,
sid `2026-10-08-sc-002`, `desk` null, a tarball), the same bundle opened
again as `second-desk` (`…+second-desk.json`, exit 0, `desk` `"desk-2"`,
the desk-2 opener and, since 0.4.50, the same outbox `tarball` — 0.4.49's
was null), and a bundle file that does not exist as `open-refused`
(`…+open-refused.json`, **exit 1, a line on stdout**: `reason` `not-found`,
one of bale's `OPEN_REFUSAL_REASONS`, 15 codes with the fallback
`unclassified`, its `cause`, and `[bale] error: <cause>` on stderr); and
`open --check <bundle> --json` in `~/twine-src` as `rehearsed`
(`fixtures/bale-0.4.51/twine-src/open_--check_bundle_--json.json`, `sid`
and `opener` null, `rehearsal` `"check"`). twine's argv is exactly these,
so the fixture player answers them with the recordings, the test selecting
`opened`, `second-desk` or `open-refused` for the grouped name (§7);
`tests/helpers.py`'s `open_recording(name)` reads them and
`StubBale(open_stdout=…)` replays one (and its stderr) as a subprocess.
**The refusal is recorded**: `carry bundle` reads it as it reads any line
that is not an open — not ok, `bale exited 1` and the outcome named, the
line reported (`open`, `outcome`), nothing recorded — and reads neither
`reason` nor `cause` yet (that is `twine-bundle-051`'s, as is the fresh
second-desk record keeping bale's tarball, §15.4). The exit-1,
nothing-on-stdout case — bale's refusal at 0.4.49 (BALE.md §6.7 then:
`fail()`, the reason on stderr) — stays a double named as such
(`OpenDouble` in `tests/test_carry_bundle.py`), now the case of a bale
that stopped before writing its line, as do a timeout, a capped stdout, a
line with an outcome no bale emits (`NOT_A_BALE_OUTCOME`) and a recorded
line with its `sid`, `opener` or `tarball` edited — and, since session
`2026-10-12-twine-pin-floor-002`, the `opened` and `rehearsed` lines with
one listed key deleted, and the `opened` line with a key bale never
printed added (§6's key check), each named as not bale's.

### 15.7 One function, two faces

The verb is thin over `twine/inflight.py`, which the Arc 2 loop can call
and `twine status` does (§4, through `list_inflight`):

```
INFLIGHT_SUBDIR = "inflight"
RECORD_KEYS = ("sid", "cwd", "tarball", "opens")
OPEN_KEYS = ("outcome", "desk", "bundle_sha256", "opener_sha256", "recorded_at")
inflight_path(state_dir: Path, sid: str) -> Path                  # raises ValueError
read_inflight(state_dir: Path, sid: str) -> dict | None           # raises InflightRecordError
list_inflight(state_dir: Path) -> InflightListing                 # never raises for what is there
record_open(state_dir: Path, sid: str, *, outcome, cwd, tarball, desk,
            bundle_sha256, opener, clock=utc_now) -> Recorded     # raises InflightError
```

`read_inflight` requires exactly the record's four keys and each entry's
five — a key missing or extra, a `sid` not the file's, a `cwd` that is not
absolute, a `tarball` neither a string nor null, `opens` not a non-empty
array, an entry whose `outcome` is not `opened` or `second-desk`, whose
`desk` or `bundle_sha256` is neither a string nor null, or whose
`opener_sha256` or `recorded_at` is not a non-empty string is a fault, each
named. `Recorded` carries the path, the record written, the well-formed
record found before (or null), `replaced` (an `opened` over an earlier
record) and `fresh` (the sentence a fresh `second-desk` record puts in
`record_error`). `InflightError` carries `found`, the record read before
the write failed, so the verb can still name its tarball. The read and the
replace run under the one `flock`, so two desks recording at once lose
neither entry. `list_inflight` (session `twine-status-inflight`) reads
without that lock and writes nothing: an `InflightListing` of `sids` (those
whose records `read_inflight` accepts, sorted) and `faults` (one sentence per
other entry in `inflight/`, by name — §4 lists the kinds); an absent
`inflight/` is two empty tuples. Its tests sit with `read_inflight`'s in
`tests/test_carry_bundle.py`; its rendering in `status` is
`tests/test_status.py`'s `InflightRecords`.

The tests (`tests/test_carry_bundle.py`) replay the three recordings
through the fixture player — `opened` and `second-desk` with the test's
directory as the scratch repository, `rehearsed` with `--cwd` the
repository root — and run the verb end to end as a subprocess against
`StubBale` replaying `opened` into a temporary state directory. Every state
directory is a temporary one; the in-process runs carry an environment
with no state variables, so a verb without `--state-dir` refuses rather
than touch the real default.

## 16. Recording a version (raising the floor): the recorder and the lander

Since session `2026-10-12-twine-pin-051-001` a recording session is
mechanical: one probe records every bale surface twine reads, and one tool
lands what it printed. Neither is a twine verb — they are maintenance tools
under `bin/`, run by the operator and the worker of a recording session (a
pin bump, until session `2026-10-12-twine-pin-floor-002` made the gate a
floor; under the floor a recording session is needed only when an install
moves a listed key, a pinned schema or a vocabulary, §6, and it raises the
floor) — and neither changes what any verb does.

**`bin/twine-record-fixtures [SLUG]`** — the recorder: a bash probe (its
header `# PROBE twine-record-fixtures: …`, so `take` reads it as one), run
from `~/twine-src` with the bale to be recorded on PATH, whose paste-back is
one `=== PROBE BEGIN <slug> ===` … `=== PROBE END <slug> ===` block with
the integrity trailer. `SLUG` defaults to `twine-record-<installed
bin/VERSION>`; anything but lowercase letters, digits, `.` and `-` is
refused, exit 2. It is probe `twine-051-record` as the operator ran it on
2026-10-08, with the slug made an argument and nothing else changed. It is
read-only: everything it writes is under one `mktemp -d` directory — a
throwaway git repository where the verbs that write (pack, open, relay,
apply, unlock) are recorded, and the bundles and responses it crafts —
removed at the end, and stdout is its only output (its tail offers the
block to `bale clipboard`, as any probe built on the crafter's scaffold
does). Per recording it prints a `== recording: <label> (<annotation>)`
header — the annotation naming where it ran (`repo`, `scratch`, `anywhere`
or `crafter`) and, for a JSON line, the outcome expected — then `argv:`
(echoed, so unquoted), `stdin:`, `cwd:`, `exit:`, and for each of stdout
and stderr the byte count, the sha256, whether it ends with a newline, a
raw head (60 lines at most, for a reader) and a **gzip+base64 copy of the
whole stream** — the copy is what crosses a clipboard intact; the raw
heads do not (clip.exe reads UTF-8 as code page 437).

**`bin/twine-land-recordings PASTE [--version V] [--check] [--tree DIR]`**
— the lander: stdlib Python, run as `python3 -I -S -B`. It reads a
paste-back of the recorder's format (CRLF folded to LF first, nothing else
changed) and refuses — exit 1, one `NOT OK — …` line on stderr naming the
first thing that differs, the recording by number, label and annotation —
unless the trailer counts the block's inner lines, the `recordings:` line
counts the recordings, every stream copy decodes to the byte count, sha256
and newline fact printed beside it, each annotation names exactly one
place, a `repo` recording ran in the paste's `cwd` and a `scratch` one
under its scratch directory. It derives every recording's path by §7's
rule — imported from `tests/fixture_rule.py`, the module
`tests/helpers.py` re-exports, never re-derived: `<where>` from the
annotation, the argv from the echoed command (`pack`'s goal is everything
before its first flag), the outcome group from the collision rule over the
whole paste, using each line's `outcome` and `reason` (a collision the
lines cannot tell apart is a refusal: a tag is a README's to assign) — and
the `.stderr` sibling beside each. `V` defaults to the paste's `install
bin/VERSION:` line; `--tree` names the repository (default: the one the
script is in). Then:

- **without `--check`** it writes, under `fixtures/bale-<V>/`, every
  recording, every sibling and the paste itself as
  `carried/probe-output_<slug>.txt` — refusing, before writing anything,
  to replace a file that holds other bytes (landing twice is a no-op) —
  and prints on stdout the version section's eight-column rows (§7), the
  carried table's row, and, per verb, one inline table per recording in
  the consumption manifest's `also_recorded` shape (`argv` with each role
  as `<role>` and stdin as `-`, `cwd`, `outcome`, `reason` when the line
  has one, `fixture`), with the crafter emissions' paths last. It edits no
  other file: the rows and entries are the worker's to place, the prose
  around them the worker's to write.
- **with `--check`** it writes nothing and exits 0 exactly when every
  derived file is in the tree byte-exact, no other file sits under
  `fixtures/bale-<V>/` — its `schemas/` subdirectory aside (since session
  `2026-10-12-twine-pin-floor-002`: the installed schemas the gate hashes,
  §7, which no recording derives and `tests/test_fixtures.py` holds to
  their own rows) — `fixtures/README.md` carries each derived row
  exactly, and the carried row carries the paste's line endings, bytes and
  hashes (for the landed LF paste, the CRLF form it arrived in: every LF
  turned back into CRLF); otherwise exit 1, naming the first difference.
  Exit 2 is a usage error or a paste that cannot be read.

**The recording procedure**, the session that raises the floor (§6 says
when one is needed; until session `2026-10-12-twine-pin-floor-002`, the
session that moved the pin):

1. The operator runs the recorder from `~/twine-src` with the new bale on
   PATH — `bin/twine-record-fixtures > <slug>.txt` — and attaches the
   paste-back to the recording worker's chat, with the new version's
   eight `schemas/*.json` when their hashes moved.
2. The worker runs the lander on the attachment, which lands the
   recordings, the siblings and the paste under `fixtures/bale-<V>/` and
   prints the rows and the manifest lines.
3. The worker places them: a `## bale <V>` section in `fixtures/README.md`
   (the rows, the carried row, the recording's facts and outcome groups),
   and each surface's `fixture` and `also_recorded` in
   `share/bale-consumption.toml` — the surface's `fixture` the recording of
   twine's own argv.
4. The worker raises `[bale] floor` to `<V>` and every `written_against`,
   lands the version's schemas byte-exact under `fixtures/bale-<V>/schemas/`
   (with their README table) and sets `[bale.schemas]` to their hashes,
   re-reads the vocabularies (a probe, or bale-src's context tarball,
   `read_at` saying which) and moves `FLOOR` in `tests/helpers.py` and
   whatever the recordings' facts move in the tests and this contract.
5. The suite runs, and `bin/twine-land-recordings --check
   fixtures/bale-<V>/carried/probe-output_<slug>.txt` exits 0 from the tree
   root — the session's `validation.sh` runs it, and the checkpoint may.

Earlier versions' directories and README sections stay as history; nothing
under them is moved, re-landed or edited.

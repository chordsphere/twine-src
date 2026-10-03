# The `twine` CLI contract

> What the shell, the parity test, and Arc 1's later sessions build
> on. These are interface outcomes: each line here is asserted by a
> test under `tests/` and by the session's `validation.sh`. Landed by
> session `2026-10-01-twine-core-002`, extended by
> `2026-10-02-twine-take-read-001` (§9, and the lines naming `take` or
> the `format` kind), by `2026-10-02-twine-carry-probe-002` (§10, the
> run seam, and the lines naming `carry probe`) and by
> `2026-10-03-twine-carry-bale-002` (§11, and the lines naming `carry
> exchange`, `carry response`, per-run values or recorded exits); a later
> session that changes a line changes it here in the same response.

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
- Verbs today: `commands`, `status`, `bale check`, `take`, and the
  `carry` group — `carry probe` (`twine/commands/carry.py`), `carry
  exchange` and `carry response` (`twine/commands/carry_bale.py`). One
  group's verbs may live in several modules; the parser assembles the
  group from all of them.
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

## 4. `twine status [--json] [--bale-root DIR]`

Twine's own facts, no bale repo state (reading `bale status --json` is
session 3's):

| key | value |
|---|---|
| `version` | twine's version (`VERSION`) |
| `python` | the interpreter's version |
| `repo_root` | the repository root, located from the package |
| `consumption_manifest` | absolute path of `share/bale-consumption.toml` |
| `fixtures` | absolute path of `fixtures/`; `fixtures_present` says whether it exists |
| `pin` | the manifest's `[bale] pin`, or null when the manifest is unusable |
| `bale` | the `bale check` result object (§5), or null when the manifest is unusable |
| `ok_reason` | why `ok` is what it is |

`ok` is true when twine itself is intact — the manifest parses and its
pin resolves — regardless of whether a bale install is present; the
bale result rides inside, and a mismatch there leaves `status` at exit
0. An unusable manifest is `ok` false, exit 1.

## 5. `twine bale check [--json] [--bale-root DIR]` (D2)

- Resolves the install root, first rule that answers: `--bale-root`,
  else the environment variable `TWINE_BALE_ROOT`, else `command -v
  bale` followed to its real path and up to the directory holding
  `bin/` (`~/.local/bin/bale` → `~/bale/bin/bale` → `~/bale`).
- Reads `<root>/bin/VERSION`, strips it, compares it to the pin.
- JSON: `pin`, `installed` (null when unreadable), `root` (null when
  no install was found), `source` (`"--bale-root"`, `"TWINE_BALE_ROOT"`,
  `"PATH"`, or null), `ok`, `reason`.
- An install at the pinned version: exit 0, `ok` true. A different
  version, a root with no readable `bin/VERSION`, or no install found:
  exit 1, one JSON line, `ok` false, no traceback.

## 6. The consumption manifest (D3, D4)

`share/bale-consumption.toml`, parsed by `tomllib`: `[bale] pin`, a
`[bale.schemas]` table of the eight installed schema files to their
sha256, one `[[surface]]` per bale surface twine reads (the file
`bin/VERSION` and each recorded `--json` verb: `kind`, `verb`, `flags`,
`argv`, `cwd`, `stdout`, `keys` — the JSON keys twine reads, `[]`
where none yet — `key_owner`, `read_by`, `fixture`, `written_against`;
a per-run value in `argv` is written `<role>` (§7); a verb with no
recording has no `fixture` and names its `stand_in` and the `doubles`
standing in for it, until a recording replaces them;
and, `kind = "format"`, each text format `take` parses out of a paste:
`format`, `locator`, `home`, `emitted_by`, `fixtures`, `keys`, `read_by`,
`written_against`),
and `[[wanted]]` for a surface a later session needs that the pinned
bale lacks (`bale open --json`, `bale relay --json` in 0.4.45). The
verbs twine runs today: `bale apply --dry-run --json <tarball>` (read by
`carry response`: the key `outcome`) and `bale relay <sid> -` (read by
`carry exchange`: stdout as text, no key). The
file's header comment spells the entry shape;
`tests/test_consumption_manifest.py` walks it.

## 7. Fixtures

`fixtures/README.md` carries the rule and the per-file provenance.
The path of a recorded output is
`fixtures/bale-<version>/<where>/<verb>_<flag[-value…]>[_…].<ext>`;
`tests/helpers.py`'s `fixture_relpath(argv, cwd)` computes it, and each
manifest surface's `fixture` is asserted equal to it. Every `.json`
fixture is one object line with a trailing newline.

A **per-run value** — a session id read out of a block, a tarball's
path — never enters a name: `fixture_key(argv)` replaces it with its
role, and a role is a `_` group of its own. `bale relay <sid> -` names
`relay_sid_stdin.txt`; `bale apply --dry-run --json <tarball>` names
`apply_--dry-run_--json_tarball.json`. A row's **exit** column is the
exit code the fixture player answers; a row that did not capture it
says `unrecorded`, and the player answers it only when the test names
the code it assumes. No row records stderr; the player answers it
empty.

A fixture that is not a bale argv's stdout keeps the version directory:
a crafter emission is `fixtures/bale-<version>/crafter/<flag[-value…]>[_…].txt`
(`-` spelled `stdin`; `emission_relpath(tool, argv)`), and an
architect-carried paste of bale output is
`fixtures/bale-<version>/carried/<kind>_<identity>[_to-<addressee>].txt`
(`carried_relpath(kind, identity, to)`), landed CRLF→LF with both
hashes in the README.

## 8. Tests

`tests/` is a package; the suite is stdlib `unittest`:

```
python3 -B -m unittest discover -s tests -t .
```

from the repository root — no network, no bale install, no third-party
module, and no bale reached whatever is on `PATH`: a verb that runs bale
(§11) runs it through the seam, and the tests hand the seam the fixture
player, a double (`BaleDouble`), or a stub `bin/bale` they write into a
temp root (`tests/helpers.py` `StubBale`, passed as `--bale-root`). `bash` is required: `carry probe`'s tests run real probe scripts,
each derived from the crafter's recorded scaffold by filling its
placeholders mechanically (`tests/helpers.py` `filled_probe`). `bale check` is tested against temp roots the tests build
(`bin/VERSION` at the pin, at another version, and absent), never a
real install, and every CLI subprocess runs with `TWINE_BALE_ROOT`
pinned to a temp directory so a bale on `PATH` cannot leak into a
verdict.

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
    stdout_cap: int | None = None) -> RunResult

RunResult(argv, exit_code: int | None, stdout: bytes, stderr: bytes,
          timed_out: bool, stdout_capped: bool, stderr_truncated: bool,
          duration_seconds: float)
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
gives up). Tests inject a double with the same signature:
`tests/helpers.py` carries `RecordingRunner` and `FixturePlayer`, the
latter answering a `bale …` argv from `fixture_relpath(argv[1:], where)`
— the argv normalized, per-run values replaced by their roles — with
the exit code `fixtures/README.md` records for it (§7).

## 11. The bale hand-offs: `carry exchange` and `carry response`

The courier hands bale what it carried. Both verbs live in
`twine/commands/carry_bale.py`, run bale only through the seam (§10.6)
and build its argv only in `twine/bale.py` (`relay_argv`,
`dry_run_argv`). Neither writes a file.

### 11.1 Finding bale

The executable is `<root>/bin/bale`, the root resolved exactly as `bale
check` resolves it (§5): `--bale-root DIR`, else `TWINE_BALE_ROOT`, else
`command -v bale` followed to its real path and up. No root found is a
refusal; a root with no runnable `bin/bale` is learned by starting it,
also a refusal (`ran` false). The installed `bin/VERSION` is reported
beside the pin in `bale` (`executable`, `root`, `source`, `installed`,
`pin`, `pin_matches`); a version other than the pin is said on stderr,
never gated on. bale runs in `--cwd DIR` (default: the current
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
- **The call.** `bale relay <sid> -`, `<sid>` the block's sentinel sid,
  with stdin exactly the block's own lines — BEGIN through END, LF, one
  trailing newline (`shapes.block_text`). Nothing else from the input
  reaches bale.
- **ok** exactly when the relay call exits 0. Otherwise not ok, exit 1,
  the reason naming bale's exit status (or that it timed out or was
  capped), bale's stderr surfaced; no traceback.
- **Human mode**: on ok, stdout is exactly bale's stdout — the block the
  courier carries next (a final newline is supplied if bale's lacked
  one); otherwise one line, `carry exchange FILE: refused — …` or
  `… NOT OK — …`.

The JSON twin, `command` `"carry exchange"`. Fixed names:

| key | value |
|---|---|
| `sid` | the chosen block's sentinel sid; null when none was chosen |
| `block` | the number `take` prints for it; null when none was chosen |
| `ran` | whether bale was started |
| `exit_code` | bale's exit status; null when it did not run or was killed |
| `stdout` | bale's stdout as text; `""` when it did not run |
| `stderr` | bale's stderr as text |
| `reason` | every refusal and failure, `; `-joined; null when ok |
| `refusals` | the reasons bale was not called, in order |

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
  whose `outcome` is `"dry-run"`. Otherwise not ok, exit 1, the reason
  naming what bale said — its exit status, its outcome, or that its
  stdout was not one JSON object — bale's stderr surfaced; no traceback.
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

The clean dry run is recorded
(`fixtures/bale-0.4.45/twine-src/apply_--dry-run_--json_tarball.json`;
its exit is `unrecorded`, and the tests that replay it name the exit
they assume). No `bale relay` output is recorded: the crafter's
`--emit-block` emission stands in for it (TARBALL.md §5.9.2 pins the two
renderings byte-identical), and the manifest's relay surface says so.
Every refusal, HOLD, non-zero exit and timeout is a double in the tests,
named as one, never a file under `fixtures/`; a recording replaces it.

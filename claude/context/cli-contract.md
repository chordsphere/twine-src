# The `twine` CLI contract

> What the shell, the parity test, and Arc 1's later sessions build
> on. These are interface outcomes: each line here is asserted by a
> test under `tests/` and by the session's `validation.sh`. Landed by
> session `2026-10-01-twine-core-002`; a later session that changes a
> line changes it here in the same response.

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
- Verbs today: `commands`, `status`, `bale check`.
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
where none yet — `key_owner`, `read_by`, `fixture`, `written_against`),
and `[[wanted]]` for a surface a later session needs that the pinned
bale lacks (`bale open --json`, `bale relay --json` in 0.4.45). The
file's header comment spells the entry shape;
`tests/test_consumption_manifest.py` walks it.

## 7. Fixtures

`fixtures/README.md` carries the rule and the per-file provenance.
The path of a recorded output is
`fixtures/bale-<version>/<where>/<verb>_<flag[-value…]>[_…].<ext>`;
`tests/helpers.py`'s `fixture_relpath(argv, cwd)` computes it, and each
manifest surface's `fixture` is asserted equal to it. Every `.json`
fixture is one object line with a trailing newline.

## 8. Tests

`tests/` is a package; the suite is stdlib `unittest`:

```
python3 -B -m unittest discover -s tests -t .
```

from the repository root — no network, no bale install, no third-party
module. `bale check` is tested against temp roots the tests build
(`bin/VERSION` at the pin, at another version, and absent), never a
real install, and every CLI subprocess runs with `TWINE_BALE_ROOT`
pinned to a temp directory so a bale on `PATH` cannot leak into a
verdict.

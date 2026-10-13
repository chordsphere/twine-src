# Notes — 2026-10-13-twine-housekeeping-probe-008

Both fixes landed and the suite is green: 1047 tests, up from the 1033 the base ran. There are no forecast departures. All thirteen paths are inside `resolved_scope`.

## A. The probe helpers

**Module: `twine/probing.py`** (R3's suggestion; the brief left the name to me).

It holds more than the four named helpers. They need `Outcome`, `CarryOutcome`, `CARRIED_KINDS` and the limits (`DEFAULT_TIMEOUT_SECONDS`, `STDOUT_CAP_BYTES`, `BASH`). `probe.py` also builds an `Outcome` and reads the timeout. Leaving those in `carry.py` would have kept the edge, so they moved too.

`twine/commands/carry.py` now imports them from `twine.probing`. It still re-exports every name it used to define. The re-exports mean `carry_bale.py` (`from twine.commands.carry import choose_block, …`) and the tests (`from twine.commands.carry import STDOUT_CAP_BYTES`) are untouched. `tests/test_probing.py` pins that these are the same objects at both names.

**What the helpers take instead of a `Context`:**
- `choose_block`, `check_block_ready` and `verify_output` never touched a `Context`. They take an outcome, and a report or bytes.
- `run_probe(seam, outcome)` uses only four members: `run`, `which`, `env` and `info`.
- `probing.ProbeSeam` is a `Protocol` naming those four. `cli.Context` satisfies it as it is, so `carry probe` passes its own context and its output is unchanged.
- `probing.Seam` is a small concrete dataclass that collects the `info` lines.
- The tool builds a `Seam`, so `probe.py` no longer imports `twine.cli`. It also no longer fabricates a `Context` with dummy streams, and it no longer strips the `[twine] ` prefix before logging.
- `probe_context(sandbox, diagnostics)` became `probe_seam(sandbox)`. Nothing else referenced the old name.
- Behaviour is unchanged. The tool's tests in `tests/test_runtime_tools.py` and the `carry probe` tests pass without edits.

The import walk is `tests/test_probing.py`. It resolves relative imports and counts `from twine import cli` and `from twine.commands import x`, which a module-name check would miss. It ran against the old `probe.py` and found `twine.cli`, `twine.cli.Context`, `twine.commands` and `twine.commands.carry`. It finds nothing now, over 30 modules under `twine/runtime/`.

**`twine/` files touched (the four the brief allows):**
- `twine/commands/carry.py`
- `twine/runtime/tools/probe.py`
- `twine/__init__.py` (module map)
- `twine/probing.py` (new)

`validation.sh` proves every other base file byte-identical to `base_files`. It also checks that nothing new sits under `twine/` or `tests/`.

## B. The recorder and the lander

**`bin/twine-record-fixtures`:**
- `argv:` is printed with `printf 'argv:'; printf ' %q' "$@"; echo`. That is quoted, with one space before each token and none after the last.
- Pack's goal reads `twine-051-record:\ the\ read-only\ session`.
- The clipboard line is now `CLIP_LINES="$(grep -c 'clipboard' bale.toml 2>/dev/null || true)"` with `${CLIP_LINES:-0}`.
- The `== recording:` header is untouched. `validation.sh` compares the harness's 21 non-crafter headers byte for byte with the landed paste's (as it arrived, the em dash read as cp437).

**The doubled `0` only appeared when a `bale.toml` exists without the key.** With no file, grep prints nothing and `|| echo 0` supplies the only 0. A harness with no `bale.toml` would have passed on the broken recorder. My first harness did exactly that, and the base run showed it passing wrongly. Both the harness and `test_the_clipboard_key_line_prints_once_whatever_the_project_bale_toml_holds` therefore run three repositories: no `bale.toml`, one without the key, and one with it. The with-key repo has two lines mentioning the key, so it prints `2 line(s)`.

**`tests/fixture_rule.py`:**
- New `echoed_tokens(command)` is `shlex.split`, raising `ValueError` on an unbalanced quote (a `Refusal` in the lander), never a silent fallback to space-splitting.
- `echoed_argv` uses it and then applies the same pack rule as before. A quoted goal is already one token, so the rule leaves it alone. The old `$*` form and the quoted form give the same argv.
- `shlex` reads the old form safely because no landed argv token has a quote, a backslash, a `$`, a backtick or a `#`. `test_no_landed_argv_line_carries_a_character_shlex_would_change` pins that for every carried paste in the tree.

**`bin/twine-land-recordings`:**
- The crafter recordings now go through the same reader.
- `command_cell` is now `"bale " + " ".join(argv)` rather than the echoed text. For old pastes this is byte-identical to before. For a quoted paste it keeps the README cell in the unquoted form every landed row is in, which `--check` compares exactly.
- `diff` of the lander's stdout on the 0.4.51 paste, old lander against new, is empty.
- `--check fixtures/bale-0.4.51/carried/probe-output_twine-051-record.txt` exits 0. It is the only recorder paste in the tree.
- The other carried pastes (take specimens, a relay block, the provider's paste) are not recorder pastes. They refuse before and after exactly as they did.

**What the recorder harness printed** (stub bale, `validation.sh` §E, on the landed tree):
- 24 argv lines.
- `argv: bale --version` with no trailing space.
- `argv: bale pack twine-051-record:\ the\ read-only\ session --slug ro --read-only --no-readme --json`.
- `echoed_argv` on that line gives `['pack', 'twine-051-record: the read-only session', '--slug', 'ro', '--read-only', '--no-readme', '--json']`.
- One clipboard-key line, `...: 0 line(s) (the global one…`, in the no-file repo and in the no-key repo, and `...: 2 line(s)` in the with-key repo. No line of its own reads `0 line(s)`.
- 21 headers byte-identical.
- The same script on the unmodified base fails those checks. The recorder pack-argv check fails, and `a line of its own reads '0 line(s)'` fails in the no-key repo.

A second harness step takes the landed paste, re-echoes every `argv:` line in `printf %q` form, and lands it into a temp tree. It writes 48 files byte-identical to the repository's, and prints the same rows and manifest lines. The carried row is the one thing that moves, since the paste's own bytes changed. `test_a_paste_with_the_quoted_argv_form_lands_the_same_files_and_rows` does this for both `%q` and `shlex.quote` forms.

**Not run here:** the real recorder against a real bale. There is no bale on PATH and no `~/twine-src`. The stub reaches every `rec` call and the environment section, but not the crafter's three recordings. The first real recording after this lands is the true test.

**Limits of `%q`:** an argument containing a newline, or non-ASCII text under a non-UTF-8 locale, comes out in `$'…'` form, which `shlex` does not read. No argument the recorder passes has either.

## Validation

`validation.sh` ran on the landed tree and on the unmodified base (the request's `context/`). It runs the suite, which takes about 100 to 190 seconds depending on the load.
- **Landed tree:** every check `[PASS]`. The suite ran 1047 tests, OK with 5 skips, against 1033 on the base.
- **Unmodified base:** the import walk, VERSION, the recorder harness and the lander harness fail as they should. The suite passes at 1033, and the file-syntax step fails only because the two new files are absent.
- **Order of runs:** I ran the whole script on the base before I tightened the harness to three repositories. I re-ran everything up to the suite on the base afterwards, and the harness failed there as described above.
- **TMPDIR:** the script points `TMPDIR` under `.validation-logs/<ts>/`, so the harness and the suite's temp directories land there too.
- **`twine-seed.md`:** it is not in `context/`, so I could not hash it. `validation.sh` shows it untouched only through the staged manifest's `changes[]` (skipped outside bale staging).

## Test pins that moved

None moved or were renamed.
- `test_echoed_argv_rejoins_only_packs_goal` keeps its name and assertions, and its docstring now says "the old form".
- `test_the_slug_is_an_argument_defaulting_to_the_installed_version` keeps its name; its stub-bale setup became the shared helper `stub_world`.
- New tests are 9 in `tests/test_probing.py` and 5 in `tests/test_recordings.py`.

## Proposals

- **What:** touch up `twine/commands/carry_bale.py`'s docstring, which still says `choose_block` is `carry.py`'s. Its import line could also name `twine.probing` directly.
  **Why:** the name still resolves through `carry.py`'s re-export, so it works, but it is stale prose. I held to the brief's four files under `twine/`.
  **Scope hints:** `twine/commands/carry_bale.py` only.

- **What:** once a real recording has landed, consider dropping the `carry.py` re-exports that nothing calls (`BASH`, `CARRIED_KINDS`, `verify_output`) and repointing the tests that import `STDOUT_CAP_BYTES` from `carry`.
  **Why:** the re-exports are scaffolding for this move. `tests/test_probing.py` pins them, so removal is a deliberate step.
  **Scope hints:** `twine/commands/carry.py`, `tests/test_carry.py`, `tests/test_probing.py`.

- **What:** the next session that records a bale version should run the real recorder once and confirm the quoted `argv:` lines and the single clipboard-key line in its paste.
  **Why:** I could only run the recorder against a stub bale.
  **Scope hints:** none, an operator step.

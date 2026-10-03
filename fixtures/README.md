# fixtures/ — recorded bale outputs

**The rule.** A fixture is the bytes a named bale version emitted on the
architect's machine, recorded through a probe and landed byte-exact —
never hand-written, never edited, never regenerated from memory. Tests
read fixtures instead of a bale install (twine-seed.md T8): under
`bale.toml`'s sandbox the suite has no network and no bale, so the
recorded outputs are the only bale the tests ever see. A `.json`
fixture holds exactly the one line bale emitted on stdout under
`--json`, trailing newline included; `.txt` holds a non-JSON output the
same way. Since session `2026-10-02-twine-take-read-001`, a fixture may
also be an architect-carried paste of a bale emission — bytes bale
printed that no read-only probe can record, such as the relay block
`bale apply` prints — landed with its provenance and its hash both as
received and as landed (ruled at the sitting `2026-09-29-begin-harness-001`).
A carried paste is landed with every CRLF turned into LF and nothing
else changed; the tests prove it by turning the LFs back into CRLFs and
hashing to the received bytes.

**Layout and naming.**

```
fixtures/bale-<version>/<where>/<verb>_<flag[-value…]>[_<flag[-value…]>…].<ext>
```

- `<version>` is bale's `bin/VERSION` at recording time.
- `<where>` is the directory the command ran in: `twine-src/` for
  `~/twine-src` (the packing repo), `anywhere/` for a command whose
  output does not depend on the working directory.
- `<verb>` is the bale verb; each flag follows, joined to the values
  that follow it with `-`; groups are joined with `_`. A flag-only
  command (`bale --version`) has no verb and starts with the flag.
- `<ext>` is `.json` when `--json` was among the flags, else `.txt`.
- `tests/helpers.py`'s `fixture_relpath(argv, cwd)` computes the path
  from the argv after `bale`, and `share/bale-consumption.toml`'s
  `[[surface]]` entries point at these files by that path. A session
  recording a new fixture adds a surface entry, a row below, and nothing
  else.

**Per-run values** (since session `2026-10-03-twine-carry-bale-002`). A
value that differs on every run — a session id twine reads out of a
block, a tarball's path — never enters a name: the argv is normalized
first, the value replaced by its **role**, and a role is a `_` group of
its own (it is not the value of the flag before it).
`tests/helpers.py`'s `fixture_key(argv)` is the normalization, one rule
per verb:

| verb | argv after `bale` | normalized | name |
|---|---|---|---|
| `relay` | `relay <sid> -` | `relay`, role `sid`, role `stdin` (a file argument: role `file`) | `relay_sid_stdin.txt` |
| `apply` | `apply --dry-run --json <tarball>` | every positional after `apply` is role `tarball` | `apply_--dry-run_--json_tarball.json` |

A value that selects *what* bale reports — `stats --sid <sid>`'s
dossier — is not per-run and stays in the name. The fixture player
(`FixturePlayer`) looks a call up by the normalized name, so one
recording answers every run of its command.

**The exit column** is what the player answers as the exit code (stdout
is the file; stderr is not recorded for any row yet, and the player
answers it empty). A row whose exit was not captured says
`unrecorded`, never a guess, and the player refuses to answer for it
unless the test names the code it assumes.

What is not the stdout of a `bale` argv keeps the version directory and
names its own `<where>`; both kinds are text formats `twine take` reads,
pinned by the consumption manifest's `kind = "format"` entries:

```
fixtures/bale-<version>/crafter/<flag[-value…]>[_…].txt     a crafter emission
fixtures/bale-<version>/carried/<kind>_<identity>[_to-<addressee>].txt   a carried paste
```

- `crafter/` holds what bale's `tools/craft_response.py` printed on
  stdout, run in `~/twine-src` (the probe's clipboard tail depends on
  that directory's `bale.toml`). The argv after the tool groups as for
  a bale argv; a `-` value (stdin) is spelled `stdin`. The stdin fed in
  is printed in the recording probe. `tests/helpers.py`'s
  `emission_relpath(tool, argv)` computes the path.
- `carried/` holds a paste of bale output: `<kind>` is the block kind
  `twine take` reports, `<identity>` the slug or sid its sentinel names,
  and a relay block adds its addressee. `carried_relpath(kind,
  identity, to)` computes it.

How to verify a fixture is still the recorded bytes: `sha256sum` it and
compare with the row below; `wc -c` must match too (the trailing
newline counts).

## bale 0.4.45

Recorded 2026-10-01 by probe `twine-core-fixtures` (session
`2026-10-01-twine-core-002`), bale 0.4.45 at `/home/chordsphere/bale`
(`~/.local/bin/bale` → `~/bale/bin/bale`), WSL2, python 3.12.3. The
chat transport added CRLFs to the paste; the recorded bytes are the
LF form, verified against the sha256 and byte count the probe printed
beside each output before the paste.

| file | command | ran in | exit | bytes | sha256 |
|---|---|---|---|---|---|
| `bale-0.4.45/twine-src/status_--json.json` | `bale status --json` | `/home/chordsphere/twine-src` | 0 | 1488 | `081879d0def5abb61d2f48027103051d5fb1326dc97d10274c6287ad3b246f63` |
| `bale-0.4.45/twine-src/stats_--json.json` | `bale stats --json` | `/home/chordsphere/twine-src` | 0 | 8121 | `a9dc5c9bab89e00a3745da8235142f1fe69ad8f6dd1ef23838c605f48ff95add` |
| `bale-0.4.45/twine-src/stats_--sid-2026-10-01-twine-seed-001_--json.json` | `bale stats --sid 2026-10-01-twine-seed-001 --json` | `/home/chordsphere/twine-src` | 0 | 4026 | `c50f1c6661f291e1378c42e6599ed60f3127452e39c5ae2f5b12f8b20df73455` |
| `bale-0.4.45/anywhere/--version.txt` | `bale --version` | `/tmp` | 0 | 12 | `20a67ed843d2255f22d492ce3dc4c3bbe42498fe39a86c32e34bb815dd337f69` |
| `bale-0.4.45/twine-src/apply_--dry-run_--json_tarball.json` | `bale apply --dry-run --json <tarball: unrecorded>` | `/home/chordsphere/twine-src` | unrecorded | 315 | `f5bd7e5bbb92363b2993e2aaba5816dc3428dd7acdc0c51e8e194a49c43471ce` |

State of `~/twine-src` at that recording: head `0c01dcb` (2026-10-01T23:11:26Z),
branch `master`, sessions `2026-09-29-begin-harness-001` (the sitting,
forecast `[]`) and `2026-10-01-twine-core-002` (forecast `["."]`) open,
`2026-10-01-twine-seed-001` applied. The `status` fixture's `sid` is the
sitting's: bale's lock state names the earliest open session.

The `apply` row was not recorded by that probe. It is the architect's
`apply-dry-run-carry-probe.json`, found on 2026-10-02 by probe
`twine-2b-ii-fixture` (22 lines, trailer matched) at
`/mnt/c/Users/chord/Downloads/apply-dry-run-carry-probe.json`, and
landed by session `2026-10-03-twine-carry-bale-002` byte-exact: 315
bytes, one line with its trailing newline, the sha256 the probe
printed. What its own fields say: bale 0.4.45, run in
`/home/chordsphere/twine-src` (its `log`) for the open session
`2026-10-02-twine-carry-probe-002` (its `sid`), outcome `dry-run`.
What is **not** known: the tarball argument it was given (so the
argv's exact order too) and its exit status — both `unrecorded` in the
row, never guessed. Its name is the normalized one (per-run values,
above). Tests that rely on its exit code name the code they assume.

### Emissions and carried pastes (session `2026-10-02-twine-take-read-001`)

Recorded 2026-10-02 by probe `twine-take-specimens` (session
`2026-10-02-twine-take-read-001`): bale 0.4.45 at `/home/chordsphere/bale`,
its `tools/craft_response.py` identical to the request-carried copy
(sha256 `66d389865447aa445a517b1113f9f8cf32d7d2d059a631f1388e9f1b6541738c`),
WSL2, python 3.12.3, `~/twine-src` at head `8d7173a` (the pack's
per-session checkpoint commit), `bale.toml` with no `[probe]
clipboard_command` (so the probe scaffold ends in the remedy text). The
light and exchange blocks render the same clarification manifest, fed on
stdin by the probe: two specimen question rows for session
`2026-10-02-twine-take-read-001`, the first carrying an em dash (which
the exchange body escapes as `\u2014`), the second carrying `options`,
`recommendation`, `priority` and `origin`. The exchange block's
`created_at` is the emission instant, `2026-10-02T17:57:34+00:00`. Each
emission's bytes, rebuilt from the paste, hash to the sha256 the probe
printed beside it before the paste.

| file | command | ran in | exit | bytes | sha256 |
|---|---|---|---|---|---|
| `bale-0.4.45/crafter/--probe-twine-take-fixture.txt` | `craft_response.py --probe twine-take-fixture` | `/home/chordsphere/twine-src` | 0 | 1898 | `abb75f26b64728022aa71cfeb17dc4df9b2ac4ed1c23046b5c8299a55125386a` |
| `bale-0.4.45/crafter/--light-block-stdin.txt` | `craft_response.py --light-block -` | `/home/chordsphere/twine-src` | 0 | 722 | `55c53cfe057b2e5a5cee10b7f6eabbbcb5365e24cc481329b27f19c6f3cebdb8` |
| `bale-0.4.45/crafter/--emit-block-stdin.txt` | `craft_response.py --emit-block -` | `/home/chordsphere/twine-src` | 0 | 1618 | `9632439af6dd669e03e7a49d87a79639409e5d9b586f56586a20bccdf98e7d00` |

Carried pastes. Both arrived as chat attachments with a CRLF on every
line and no newline after the END sentinel (a selection copy); landed
LF-normalized, nothing else changed.

| file | emission | received (line endings, bytes, sha256) | bytes | sha256 |
|---|---|---|---|---|
| `bale-0.4.45/carried/probe-output_twine-take-specimens.txt` | the output of probe `twine-take-specimens` (the crafter's `emit_probe_block`), run 2026-10-02T17:57:36Z; its trailer counts 661 lines and the paste carries 661 | CRLF 38184 `7ebf956f484edc52a30e9f7c2be3998f123d8ffa0230ae0927e6399acc15e167` | 37521 | `263f464b4ad141c57cda1d6ef3d39ac2ca678deda7e5e8c7ffe9ce8b8b64097c` |
| `bale-0.4.45/carried/relay_2026-10-01-twine-seed-effort-003_to-planner.txt` | the ratification relay `bale apply` printed on applying session `2026-10-01-twine-seed-effort-003` (`format_apply_relay_planner`), carried by the architect as `relay-2026-10-01-twine-seed-effort-003.txt` | CRLF 9047 `15067e79f5bed5817efb7082c8c3ad02d74cb87231d2bad6495428743e254482` | 8874 | `58e046e26d8b9c27ea572e4dd89e2951ec1791a45275955c3de56634f51bb888` |

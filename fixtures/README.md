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

**Provider recordings** (since session
`2026-10-12-twine-runtime-registry-007`, Arc 2 R1). Everything above is
bale's: `fixtures/bale-<version>/` and its naming rule. A model provider's
recorded output sits in a sibling directory named for the provider,
`fixtures/anthropic/`, under a rule of its own — the last section of this
file, "Provider recordings". Since session
`2026-10-13-twine-runtime-anthropic-002` (Arc 2 R2) that directory also
holds the wire itself — fifteen request/response pairs the architect
recorded on 2026-10-13 — landed by their own lander,
`bin/twine-land-provider-recordings`, beside `bin/twine-land-recordings`.

**The floor, and what it means here** (since session
`2026-10-12-twine-pin-floor-002`, D2 as amended at the sitting
`2026-10-08-open-arc2-003`). twine no longer drives one exact bale: it
drives any bale **at or above the floor** — `share/bale-consumption.toml`'s
`[bale] floor`, `0.4.51` — whose installed `schemas/*.json` hash as the
manifest's `[bale.schemas]` pins them, and every verb that reads a bale
`--json` line checks that line for the keys the manifest lists for its
surface. The floor is the version **the recordings were made at**, so
`fixtures/bale-<floor>/` is the directory the tests replay, and it is
raised only by a recording session (contract §16). An install that moves
without touching a listed key or a pinned schema needs nothing here:
0.4.52 was the first, admitted with nothing re-recorded (probe
`twine-052-delta`, 2026-10-12, found its `bin/bale`, `bale_report.py`,
`bale_relay.py`, `bale_open.py` and all eight schemas byte-identical to
0.4.51's). Until that session the directory was named by the exact pin;
the sections below that say "the pin" are that history.

**The schemas** (same session). The eight files the gate hashes land
byte-exact under the floor's directory, `fixtures/bale-0.4.51/schemas/`,
named as installed. They are not recordings — no argv printed them, they
have no `.stderr` sibling, and `bin/twine-land-recordings` neither derives
nor checks them (`tests/fixture_rule.py` `SCHEMAS_WHERE`) — so they have a
table of their own, `| file | bytes | sha256 |`, in the 0.4.51 section,
and `tests/test_fixtures.py` holds them to it and to the manifest. The
tests' stub install roots copy them (`tests/helpers.py`
`install_schemas`), so the gate admits a stub as it admits the operator's
install.

**stderr, and where a version's recordings come from** (since session
`2026-10-12-twine-pin-051-001`, the pin at 0.4.51). Every recording of a
bale argv or a crafter emission also lands the **stderr** the command
printed beside it, byte-exact, as a **sibling file**: the same name with
the extension `.stderr` in place of `.json` or `.txt`
(`unlock_sid_--json+unlocked.json` beside `unlock_sid_--json+unlocked.stderr`),
present even when stderr was empty (zero bytes). A version's section
lists each recording in one **eight-column row** —

```
| file | command | ran in | exit | bytes | sha256 | stderr bytes | stderr sha256 |
```

— `file` the path under `fixtures/`, `command` the argv as the recorder
echoed it, `ran in` the directory, then the exit, the stdout's bytes and
sha256, and the sibling's bytes and sha256. The six-column rows of the
0.4.45 and 0.4.49 sections stay as history: rows without stderr.
A version's recordings come from **one paste-back**: the recorder,
`bin/twine-record-fixtures`, runs every surface once and prints each
stream's bytes, sha256 and a gzip+base64 copy of the whole stream; the
paste-back lands under the version's `carried/` as the recordings' source
(CRLF→LF, like any carried paste); and the lander,
`bin/twine-land-recordings`, derives every file, sibling and row from it
— `--check` proves the tree still holds exactly that. Nothing in a
version's directory is typed. Contract §16 is the bump procedure.

**Layout and naming.**

```
fixtures/bale-<version>/<where>/<verb>_<flag[-value…]>[_<flag[-value…]>…].<ext>
```

- `<version>` is bale's `bin/VERSION` at recording time.
- `<where>` is the directory the command ran in: `twine-src/` for
  `~/twine-src` (the packing repo), `anywhere/` for a command whose
  output does not depend on the working directory, and, since session
  `2026-10-07-twine-pin-049-001`, `scratch/` for a throwaway repository
  a probe created under `mktemp -d` and removed — where a verb that
  writes (pack, open, relay, unlock) can be recorded without touching
  `~/twine-src`. Each version's section states that repository's facts.
- `<verb>` is the bale verb; each flag follows, joined to the values
  that follow it with `-`; groups are joined with `_`. A flag-only
  command (`bale --version`) has no verb and starts with the flag.
- `<ext>` is `.json` when `--json` was among the flags, else `.txt`.
- `tests/helpers.py`'s `fixture_relpath(argv, cwd)` computes the path
  from the argv after `bale` (the rule itself is `tests/fixture_rule.py`,
  which the lander imports too, since session
  `2026-10-12-twine-pin-051-001`), and `share/bale-consumption.toml`'s
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
| `relay` | `relay <sid> - --json` | `relay`, role `sid`, role `stdin` (a file argument: role `file`) | `relay_sid_stdin_--json.json` — recorded since 0.4.51 (below) |
| `apply` | `apply --dry-run --json <tarball>` | every positional after `apply` is role `tarball` | `apply_--dry-run_--json_tarball.json` |
| `unlock` | `unlock <sid> --reason aborted --json` | a positional right after `unlock` is role `sid` (session 5b) | `unlock_sid_--reason-aborted_--json.json` |
| `open` | `open [--check] <bundle> --json` | every positional after `open` is role `bundle` (session `2026-10-07-twine-pin-049-001`) | `open_bundle_--json.json`, `open_--check_bundle_--json.json` |
| `pack` | `pack <goal> --slug ro … --json` | the positional right after `pack` is role `goal`; a flag's value (`--slug ro`) stays (same session) | `pack_goal_--slug-ro_--read-only_--no-readme_--json.json` |

The `relay` row is twine's own argv since session
`2026-10-08-twine-carry-exchange-json-001` (the flagless `relay <sid> -`,
which would have named `relay_sid_stdin.txt`, is retired, and was never
recorded). `relay_sid_stdin_--json.json` is recorded since 0.4.51 (probe
`twine-051-record`: the relayed round, and two refusals, each with the
paste block or a line that is not one on stdin). The 0.4.49 probe had
recorded `relay` with a file argument (`relay_sid_file_--json…`, and the
re-emission with none), and the tests replayed those recordings for
twine's argv on a named assumption — that bale reads `-` as it reads the
file (`_read_relay_input`); the 0.4.51 recording retired the assumption,
and the 0.4.49 files stay as history. (`RecordedUnlock` still replays the
unlock refusals, recorded without `--reason`, for twine's argv on its own
named assumption: below.)

A value that selects *what* bale reports — `stats --sid <sid>`'s
dossier, `--slug ro` — is not per-run and stays in the name. The fixture
player (`FixturePlayer`) looks a call up by the normalized name, so one
recording answers every run of its command.

**Outcome groups** (since session `2026-10-07-twine-pin-049-001`). One
normalized argv can be recorded more than once, each run ending in
another outcome — `unlock <sid> --json` refused for a HOLD branch, for a
sid not open, or closing a read-only session. When a version's directory
tree holds more than one recording of a normalized argv (across every
`<where>`), each of them carries an **outcome group** between the name
and the extension: `+<outcome>`, the line's own `outcome` value, and,
only where two of them share the outcome, `+<reason>` — the line's
`reason` value when it has one (`unlock-refused` lines do), else a short
tag the version's section assigns beside the row (relay's refusals carry
their reason as a `cause` sentence, not a code). A normalized argv
recorded once keeps the plain name. `tests/helpers.py`'s
`fixture_relpath(argv, cwd, group)` spells the path, and the player
answers a grouped name only when the test names the group it wants
(`FixturePlayer(select={...})`), so which outcome a test replays is
always visible where it is used.

**The exit column** is what the player answers as the exit code (stdout
is the file). A row whose exit was not captured says `unrecorded`, never
a guess, and the player refuses to answer for it unless the test names
the code it assumes; every row of the 0.4.49 and 0.4.51 sections has one.

**The stderr columns** (since 0.4.51) are what the player answers on
stderr: the sibling's bytes, held to the row's sha256 (`tests/helpers.py`
`recorded_stderr`). They are recorded byte-exact — the recorder prints a
gzip+base64 copy of each stream, which survives a clipboard that mangles
non-ASCII text — and nothing about a stderr is derived. Before 0.4.51 no
row recorded stderr (the probes printed its first lines only, and clip.exe
mangled their non-ASCII); the 0.4.49 session derived one refusal's stderr
from its line until session `2026-10-07-twine-kill-reason-002` retired the
derivation, and the 0.4.49 section's "stderr" paragraph is that history.
twine reads no decision from bale's stderr — it reports and passes it
through — and a test that needs a stderr bale never printed still names
its bytes as not bale's.

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
  identity, to)` computes it. A carried paste is bound to the version
  that printed it and stays under that version's directory across a pin
  bump (a copy would claim an emitting version it does not have); the
  consumption manifest's format entry names that version as
  `fixtures_version`, and `carried_relpath` reads it from there. A
  crafter emission is **re-recorded when the crafter's sha256 moves**
  (the recorder prints it), so its `fixtures_version` is the floor's — the
  version its last recording was made at. (Until session
  `2026-10-12-twine-pin-floor-002` the rule was "at each pin".) 0.4.52's
  crafter moved — sha256 `c167f5b5…` (probe `twine-052-delta`): its probe
  scaffold gained a bound line and a bounded capture, the sentinels,
  trailer and placeholders unchanged — and that scaffold is a `probe`
  specimen for a later session to record, not a gate: twine reads the
  sentinels, the trailer and the sections, none of which moved.

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

## bale 0.4.49

Recorded 2026-10-07 by three probes (session `2026-10-07-twine-pin-049-001`,
the pin bump from 0.4.45): bale 0.4.49 at `/home/chordsphere/bale`
(`~/.local/bin/bale`), its `tools/craft_response.py` sha256
`3d82833b7bc446207e1aeb2c970a78e455ae4b0e15d5cb78342b6badea487b08`,
WSL2, python 3.12.3. `twine-049-fixtures` (13:14Z) and
`twine-049-emissions` (16:21Z) ran in `~/twine-src` at head `4ccbbad`
on `master`, nothing open, 17 applied, latest
`2026-10-06-twine-seed-tidy5-004`; `twine-049-scratch` (16:03Z) ran
`stats` in `~/twine-src` and everything that writes in a **throwaway
repository** it created under `mktemp -d` and removed at the end —
`/tmp/tmp.Jrs0DzBe5Z/scratch-repo`, git head `9548cb7` on `main`, one
committed `hello.txt`, no `bale.toml` of its own (no `[validation]`
base, no clipboard command), the operator's global `bale.toml` in force
(clipboard `clip.exe`, sweep on). Its rows are the `scratch/` ones; the
`/tmp/tmp.…` paths in their commands are that run's, per-run values the
names carry by role. In it the probe packed a read-only session
(`2026-10-07-ro-001`, its goal `twine-049-scratch: the read-only
session` as the positional), opened a scoped one from a crafter bundle
(`2026-10-07-sc-002`, then a second desk of it), relayed a one-question
clarification manifest for it (round 1, from worker), re-emitted it,
fed `relay` a file that is not JSON and a sid not open, dry-ran a clean
response tarball and one that drifts out of scope (`other.txt` beside
the forecast's `hello.txt`), then closed: the HOLD-branch refusal
(after a response had been staged to `bale/2026-10-07-sc-002`), the
`aborted` close of the scoped session (the branch deleted first), the
`closed-read-only` close of the read-only one, and the no-op with
nothing open.

Every paste crossed `clip.exe`: CRLF on every line, and `—`, `§`, `…`
mangled outside the JSON lines (which escape them as `\uXXXX`). The
recorded bytes are each `--- raw: … ---` span with CRLF folded to LF,
verified against the sha256 and byte count the probe printed beside it;
the three crafter emissions carry em dashes in plain text, so for them
the probe's gzip+base64 copy (`base64 -d | gunzip`) is the recovered
bytes, and it hashes where the raw span does not. Nothing was repaired.
Rows 7 and 22 are byte-identical to their 0.4.45 recordings (`stats
--sid …` and the light block); the exchange block differs from 0.4.45's
only in `created_at` (`2026-10-07T16:21:30+00:00`) and its trailer; the
probe scaffold differs in its tail, which now pipes the block into
`bale clipboard --block "probe block"` through a `bale` on PATH, and
prints two `[clipboard]` notices on stderr when there is none (the
0.4.45 tail was remedy text in comments). Rows 22–23 were fed on stdin
the same specimen clarification manifest as the 2026-10-02 recording
(two question rows for session `2026-10-02-twine-take-read-001`).

| file | command | ran in | exit | bytes | sha256 |
|---|---|---|---|---|---|
| `bale-0.4.49/anywhere/--version.txt` | `bale --version` | `/home/chordsphere/twine-src` | 0 | 12 | `49f3d68760069239c4246ca6ab02a58d21ba64469a0fd4714ac3572f22b4791e` |
| `bale-0.4.49/twine-src/status_--json.json` | `bale status --json` | `/home/chordsphere/twine-src` | 0 | 2040 | `bf35950de9441ff620ce0e2b620a7809def46f01f33cce2c6d852a289516d26c` |
| `bale-0.4.49/twine-src/unlock_sid_--json+unlock-refused+not-open.json` | `bale unlock no-such-sid-twine-049 --json` | `/home/chordsphere/twine-src` | 1 | 344 | `a374a63ffd5027180c1b0833be6b590d778402b428b6f8be66590c96b6050c82` |
| `bale-0.4.49/twine-src/unlock_--integration_--json.json` | `bale unlock --integration --json` | `/home/chordsphere/twine-src` | 1 | 488 | `d6e6668700da2266cc8386494ea65b0a0bc6eb22406c750a541c97e0b828376e` |
| `bale-0.4.49/twine-src/open_--check_bundle_--json.json` | `bale open --check /tmp/tmp.yznFCVXdRo/2026-10-07-twine-049-probe.bale-bundle --json` | `/home/chordsphere/twine-src` | 0 | 708 | `2a87907131523e40d59a77175c8e20127dcf200196fcf692dda6a2d28cccc80e` |
| `bale-0.4.49/twine-src/stats_--json.json` | `bale stats --json` | `/home/chordsphere/twine-src` | 0 | 13592 | `cc2936b8a5f58fa4dbcd2dd3bc6455a286d4f27aa9178bc814b2ad62ac6df085` |
| `bale-0.4.49/twine-src/stats_--sid-2026-10-01-twine-seed-001_--json.json` | `bale stats --sid 2026-10-01-twine-seed-001 --json` | `/home/chordsphere/twine-src` | 0 | 4026 | `c50f1c6661f291e1378c42e6599ed60f3127452e39c5ae2f5b12f8b20df73455` |
| `bale-0.4.49/scratch/pack_goal_--slug-ro_--read-only_--no-readme_--json.json` | `bale pack twine-049-scratch: the read-only session --slug ro --read-only --no-readme --json` | `/tmp/tmp.Jrs0DzBe5Z/scratch-repo` | 0 | 2031 | `a45c382fc4800ccdda614fb0778d7f36f7981c2383e99b610a99bed1e56ea5c9` |
| `bale-0.4.49/scratch/open_bundle_--json+opened.json` | `bale open /tmp/tmp.Jrs0DzBe5Z/2026-10-07-twine-049-scoped.bale-bundle --json` | `/tmp/tmp.Jrs0DzBe5Z/scratch-repo` | 0 | 2308 | `75872c420f92ca9696de2944ce19c4f8c7fd4a3f246064223e1c697142244616` |
| `bale-0.4.49/scratch/open_bundle_--json+second-desk.json` | `bale open /tmp/tmp.Jrs0DzBe5Z/2026-10-07-twine-049-scoped.bale-bundle --json` | `/tmp/tmp.Jrs0DzBe5Z/scratch-repo` | 0 | 2225 | `9bc523becf733ef3cfa00db3f973bb141685882df640e08dcbaaedda34976020` |
| `bale-0.4.49/scratch/relay_sid_file_--json+relayed.json` | `bale relay 2026-10-07-sc-002 /tmp/tmp.Jrs0DzBe5Z/clar/manifest.json --json` | `/tmp/tmp.Jrs0DzBe5Z/scratch-repo` | 0 | 1373 | `40bd534932ddbe3098fc54af8560371b698d9eed8f719b63e708ab2ac7333b71` |
| `bale-0.4.49/scratch/relay_sid_--json.json` | `bale relay 2026-10-07-sc-002 --json` | `/tmp/tmp.Jrs0DzBe5Z/scratch-repo` | 0 | 1311 | `47849102980eaff464160a04a4b3f06ac4a58ebf05a559dc89518a3f03bed400` |
| `bale-0.4.49/scratch/relay_sid_file_--json+relay-refused+ingest.json` | `bale relay 2026-10-07-sc-002 /tmp/tmp.Jrs0DzBe5Z/bogus.json --json` | `/tmp/tmp.Jrs0DzBe5Z/scratch-repo` | 1 | 517 | `84f6bced9a6ef57d692ef2050b8cd5de6738f9c43e155090f93bf923adede61d` |
| `bale-0.4.49/scratch/relay_sid_file_--json+relay-refused+session-gate.json` | `bale relay no-such-sid-twine-049 /tmp/tmp.Jrs0DzBe5Z/clar/manifest.json --json` | `/tmp/tmp.Jrs0DzBe5Z/scratch-repo` | 1 | 473 | `e0cb6d390ae7edd333aa1ae9145be59cff556f02b674dfc61c820b83f856bbcf` |
| `bale-0.4.49/scratch/apply_--dry-run_--json_tarball+dry-run.json` | `bale apply --dry-run --json /tmp/tmp.Jrs0DzBe5Z/clean-response-2026-10-07-sc-002.tar.gz` | `/tmp/tmp.Jrs0DzBe5Z/scratch-repo` | 0 | 290 | `266fc2539c08511d1ee29cb29442eacad6d6ebdab738723c3c0bf440fac8b955` |
| `bale-0.4.49/scratch/apply_--dry-run_--json_tarball+scope-drift-refused.json` | `bale apply --dry-run --json /tmp/tmp.Jrs0DzBe5Z/drift-response-2026-10-07-sc-002.tar.gz` | `/tmp/tmp.Jrs0DzBe5Z/scratch-repo` | 1 | 521 | `9f17bd60b2820b9b442a80b1c30a556c22fcace67fb5803843e3181b4cf1fcd7` |
| `bale-0.4.49/scratch/unlock_sid_--json+unlock-refused+hold-branch.json` | `bale unlock 2026-10-07-sc-002 --json` | `/tmp/tmp.Jrs0DzBe5Z/scratch-repo` | 1 | 569 | `14669f1831af42e2c39c7f7e9ab1995ff21ab8c2307675ed5d9df56db88f90ce` |
| `bale-0.4.49/scratch/unlock_sid_--reason-aborted_--json.json` | `bale unlock 2026-10-07-sc-002 --reason aborted --json` | `/tmp/tmp.Jrs0DzBe5Z/scratch-repo` | 0 | 489 | `1f91385974a148652c5b95434061772e83e397f535b272fc0dcfd28018efe921` |
| `bale-0.4.49/scratch/unlock_sid_--json+unlocked.json` | `bale unlock 2026-10-07-ro-001 --json` | `/tmp/tmp.Jrs0DzBe5Z/scratch-repo` | 0 | 498 | `8af871da9c5d437a055a01154f0d34591821b9fc313324eeb1e5301aa0f5a397` |
| `bale-0.4.49/scratch/unlock_--json.json` | `bale unlock --json` | `/tmp/tmp.Jrs0DzBe5Z/scratch-repo` | 0 | 231 | `e7a675b90e559559496927b2de7baad3f31f7d62268991615c3beded8bbe501e` |
| `bale-0.4.49/crafter/--probe-twine-take-fixture.txt` | `craft_response.py --probe twine-take-fixture` | `/home/chordsphere/twine-src` | 0 | 2626 | `1f5e235fd0958b4e984b2b5fe7c1745466171c02eff9603b1eb09330ccdca00e` |
| `bale-0.4.49/crafter/--light-block-stdin.txt` | `craft_response.py --light-block -` | `/home/chordsphere/twine-src` | 0 | 722 | `55c53cfe057b2e5a5cee10b7f6eabbbcb5365e24cc481329b27f19c6f3cebdb8` |
| `bale-0.4.49/crafter/--emit-block-stdin.txt` | `craft_response.py --emit-block -` | `/home/chordsphere/twine-src` | 0 | 1618 | `fda8a4d0d12f930f9077068163098aec626583d59e73c9a8d916b6da21b410f8` |

Outcome groups in this section, by normalized argv (the rule is above):
`unlock_sid_--json` — `unlock-refused+not-open` (in `twine-src/`),
`unlock-refused+hold-branch` and `unlocked` (in `scratch/`): two
refusals share the outcome, so each carries its line's `reason`;
`open_bundle_--json` — `opened`, `second-desk`; `apply_--dry-run_--json_tarball`
— `dry-run`, `scope-drift-refused`; `relay_sid_file_--json` — `relayed`,
`relay-refused+ingest` (the input was neither a paste block nor JSON)
and `relay-refused+session-gate` (the sid was not open) — relay's
refusal lines carry no `reason` code, only a `cause` sentence, so the
two tags are this section's. `--version` ran in `~/twine-src` this
time; its output depends on no directory, so it stays `anywhere/`.

**stderr.** No row records stderr byte-exact, and no test replays one:
`tests/helpers.py`'s `unlock_recording` answers stderr empty for every
recording, refusals included, and derives nothing from a recording. (The
probes print each recording's first stderr lines — for the
`unlock-refused` rows 3, 4 and 17, bale's error text — but those lines are
not recorded byte-exact; recording them is a later probe's.) `twine
kill` reads a refusal by its line, not by stderr: the HOLD refusal (row
17) is the line whose `outcome` is `unlock-refused` and whose `reason` is
`hold-branch` (session `2026-10-07-twine-kill-reason-002` retired the
stderr text match and, with it, the one derivation the tests made). A
test that proves stderr passes through feeds bytes it names as not
bale's. The 0.4.49 unlock recordings are what
`tests/` replays for `twine kill`'s closure (contract §14.7): the
`aborted` close (row 18) is twine's own argv; the refusals were recorded
without `--reason aborted` (rows 3, 17: `unlock <sid> --json`) and the
tests replay them for twine's argv on the stated assumption that bale
refuses before the reason matters. Likewise the four relay recordings
(rows 11–14) are what `tests/` replays for `twine carry exchange` (contract
§11.4, since session `2026-10-08-twine-carry-exchange-json-001`): made with
a file argument, replayed for twine's `relay <sid> - --json` on the stated
assumption that bale reads `-` as it reads the file (`RecordedRelay`; the
naming rule's `relay` row above).

The 0.4.45 section above and every file under `bale-0.4.45/` stay as
recorded history; the tests read the pinned version's directory
(`tests/helpers.py` `PIN`) and, for a carried paste, the version the
manifest's format entry names.

## bale 0.4.51

Recorded 2026-10-08 by one probe, `twine-051-record` (13:35:24Z), landed
by session `2026-10-12-twine-pin-051-001` (the pin bump from 0.4.49)
through `bin/twine-land-recordings` from its paste-back, which lands here
too (the carried table below). bale 0.4.51 at `/home/chordsphere/bale`
(`~/.local/bin/bale`), its `bin/bale_report.py` sha256
`1f4f2c758fdc3b1f8f92e25dc1561dddbc4ffb11b335f86cdefab4a3e77b21e1`, its
`tools/craft_response.py` sha256
`3d82833b7bc446207e1aeb2c970a78e455ae4b0e15d5cb78342b6badea487b08` (0.4.49's),
its eight `schemas/*.json` hashed by the probe and every one unchanged since
0.4.45; WSL2, python 3.12.3. The probe is the recorder,
`bin/twine-record-fixtures`, as it now stands with its slug fixed: every
verb ran with stdin closed (or the named file on stdin), and each stream's
bytes, sha256, newline fact and gzip+base64 copy were printed. Every
recording below is a stream copy decoded, hashed to the values printed
beside it before the paste: the raw heads crossed `clip.exe` (em dashes
and section signs mangled), the copies are the bytes. Nothing was repaired.

`~/twine-src` was at head `c91dfda` on `master` (`VERSION` 0.10.0), the
sitting `2026-10-08-open-arc2-003` (read-only) open — `status --json`'s
`session` and the `--integration` refusal's `open_sessions` name it — and
latest applied `2026-10-08-twine-seed-tidy6-002`. The `--check` bundle was
crafted outside the repository (`/tmp/tmp.7us84LTOtN/check/`, nine pack
tokens, a brief, no checkpoint) and rehearsed in it. Everything that writes
ran in a **throwaway repository**, `/tmp/tmp.7us84LTOtN/scratch-repo`,
created under `mktemp -d` and removed at the end: `git init -b main`, one
committed `hello.txt` (head `6f5d5de`), no `bale.toml` of its own, the
operator's global one in force (clipboard `clip.exe`, a `post_pack` hook
offered and declined on closed stdin). In it the probe packed the
read-only session `2026-10-08-ro-001` (goal `twine-051-record: the
read-only session`, one positional), opened the scoped session
`2026-10-08-sc-002` from a crafter bundle (`--include hello.txt --write
hello.txt`, a brief, no checkpoint), opened it again as desk-2, asked for
a bundle that does not exist, relayed a one-question clarification
manifest as round 1 from worker through the paste block on stdin (964
bytes, sha256 `7921f0df07f8e2054238fb0466ec01ffef44fac49be0661025432f1699b77c9c`),
re-emitted it, fed relay a line that is not a paste block and the block
under a sid not open (`no-such-sid-twine-051`), dry-ran a clean response
(`hello.txt` modified) and a drifting one (`other.txt` created beside it),
made the branch `bale/2026-10-08-sc-002` by hand for the HOLD refusal and
deleted it, closed the scoped session `aborted`, the read-only one without
a reason, and ran the no-op. The two crafter block renderers were fed on
stdin the same specimen clarification manifest as 2026-10-02's (1001
bytes, sha256 `8a9fa99994237b94e1c9e5b2e3599a93eb232f6f0ba0f840ba0887a35e2f8c9b`).

| file | command | ran in | exit | bytes | sha256 | stderr bytes | stderr sha256 |
|---|---|---|---|---|---|---|---|
| `bale-0.4.51/anywhere/--version.txt` | `bale --version` | `/home/chordsphere/twine-src` | 0 | 12 | `de4bfb2eea95dc5102c052339fba0c576c839a7bb8de083373994b04c109bcb4` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `bale-0.4.51/twine-src/status_--json.json` | `bale status --json` | `/home/chordsphere/twine-src` | 0 | 2830 | `688c2a65b1d33342d3ef789c3cf3314001c747fd49c5802896a7c04dd709b572` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `bale-0.4.51/twine-src/stats_--json.json` | `bale stats --json` | `/home/chordsphere/twine-src` | 0 | 19063 | `22fd5448775a980c8db490079a51ab4d8ce63f5ba3a9312f52208585b35bd05b` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `bale-0.4.51/twine-src/stats_--sid-2026-10-01-twine-seed-001_--json.json` | `bale stats --sid 2026-10-01-twine-seed-001 --json` | `/home/chordsphere/twine-src` | 0 | 4026 | `c50f1c6661f291e1378c42e6599ed60f3127452e39c5ae2f5b12f8b20df73455` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `bale-0.4.51/twine-src/unlock_sid_--json+unlock-refused+not-open.json` | `bale unlock no-such-sid-twine-051 --json` | `/home/chordsphere/twine-src` | 1 | 391 | `a6da42625c53f2f18442bf0297400918e033f9091d16bbd3dadb324a1e54029a` | 119 | `2e8ec66238b6879a63d7667cad8a197d8853d75d7aacab55b5cab26066cc475e` |
| `bale-0.4.51/twine-src/unlock_--integration_--json.json` | `bale unlock --integration --json` | `/home/chordsphere/twine-src` | 1 | 514 | `f64fec6c21aa9f97c1ac5528a4fafea15a9538c1b02310858d0f0bc8f4254049` | 253 | `23b022935757f1b3999ef3354c3efc723f777c6652c280093ad4bad6f79439fc` |
| `bale-0.4.51/twine-src/open_--check_bundle_--json.json` | `bale open --check /tmp/tmp.7us84LTOtN/check/twine-051-probe.bale-bundle --json` | `/home/chordsphere/twine-src` | 0 | 723 | `b8cf0ef8e85cb6779c9e56d50b31baf876c5a27bb33300bf3ea9121e27371bf0` | 1802 | `95788022dd14dbb6302b3538fbf413fcec7911eb3d404048e59371eec1c8753d` |
| `bale-0.4.51/crafter/--probe-twine-take-fixture.txt` | `craft_response.py --probe twine-take-fixture` | `/home/chordsphere/twine-src` | 0 | 2626 | `1f5e235fd0958b4e984b2b5fe7c1745466171c02eff9603b1eb09330ccdca00e` | 594 | `9411fa4d519f03fef3f20e48e095b72e18f264adc18fe4b1d1fd3b989dd8c6cc` |
| `bale-0.4.51/crafter/--light-block-stdin.txt` | `craft_response.py --light-block -` | `/home/chordsphere/twine-src` | 0 | 722 | `55c53cfe057b2e5a5cee10b7f6eabbbcb5365e24cc481329b27f19c6f3cebdb8` | 632 | `643da8527bb2b45bb3db80aa07bbec63e0552d0786cdec1e63a549f261a45d17` |
| `bale-0.4.51/crafter/--emit-block-stdin.txt` | `craft_response.py --emit-block -` | `/home/chordsphere/twine-src` | 0 | 1618 | `b1730d1a40eb48bf3b60be5fb389c110ee4f0b843fe87e87fa192c6720e2a2d9` | 317 | `87c88a3de079ecc5c7fee937d2628a49ade99251fb1662b51afda70ebd63691a` |
| `bale-0.4.51/scratch/pack_goal_--slug-ro_--read-only_--no-readme_--json.json` | `bale pack twine-051-record: the read-only session --slug ro --read-only --no-readme --json` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 0 | 2030 | `0320baecb3f0e70913d3de98ecdfef6cc50e88133e0f55945add6152da9949ed` | 4287 | `b1c36a6b10417025f48c68c06c559f80a9d0ffc9bdd052d75f3c26151e7d07ef` |
| `bale-0.4.51/scratch/open_bundle_--json+opened.json` | `bale open /tmp/tmp.7us84LTOtN/scoped/twine-051-scoped.bale-bundle --json` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 0 | 2337 | `838012cf6c7c760f5ff5786c6c9fc0f4cfec4a7f4bf2217a35384464cca930c9` | 4562 | `e4b2a2b64409eca88d509ef1d7cce854bd0db91f961410bc766f54e17f643f2b` |
| `bale-0.4.51/scratch/open_bundle_--json+second-desk.json` | `bale open /tmp/tmp.7us84LTOtN/scoped/twine-051-scoped.bale-bundle --json` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 0 | 2316 | `7629b63b930a99f2e2888e3df7be93810d886d4bd65688578d03cd48f1b66bba` | 2730 | `93684b7d2d0463be5cd50f4a08452d7cdd315b0bd1de6d9f3bcce63888e64c20` |
| `bale-0.4.51/scratch/open_bundle_--json+open-refused.json` | `bale open /tmp/tmp.7us84LTOtN/no-such-twine-051.bale-bundle --json` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 1 | 536 | `31908963df7fa7919ffd37f634a9bbe8866e0346a845894f5845fa7646a30fcf` | 82 | `8b84698f329ec410e64a5612c8494524c01f15e955a4d31dce5cf04cd331670c` |
| `bale-0.4.51/scratch/relay_sid_stdin_--json+relayed.json` | `bale relay 2026-10-08-sc-002 - --json` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 0 | 1384 | `b98fc9c13e4851701c2b1ee55f558c45319c8ed237a3a50ea8885c5329c9d5d0` | 872 | `c9219a9b0b296867ee1e986f1f9413d19e4931459cc8509d5caec64def80c27c` |
| `bale-0.4.51/scratch/relay_sid_--json.json` | `bale relay 2026-10-08-sc-002 --json` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 0 | 1329 | `600559d6927583dde5c8bcc7111d1707d13f8567d3197e15c489f3ef886d5f1c` | 857 | `30d6b99c5db67b52b98014b16439e8ebc51ab9360de689c389622ab7b4a0d6c6` |
| `bale-0.4.51/scratch/relay_sid_stdin_--json+relay-refused+not-an-object.json` | `bale relay 2026-10-08-sc-002 - --json` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 1 | 544 | `2151ca6880480456eb8bae15ec9dcba57fef01e23192714811185f34d45671da` | 356 | `07dbaa4a3f2e04929a705c3c2dd4275bd9430c3915c313543c7369fcdfb9836f` |
| `bale-0.4.51/scratch/relay_sid_stdin_--json+relay-refused+not-open.json` | `bale relay no-such-sid-twine-051 - --json` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 1 | 495 | `7af4cac97afab2acea2020c989b197324a9b497a8e699409f0f40661a8a7c764` | 264 | `4dd50c0efb1d5dde0c26bbbdf9803b456fa45144d02dec8c9e953ea46d700993` |
| `bale-0.4.51/scratch/apply_--dry-run_--json_tarball+dry-run.json` | `bale apply --dry-run --json /tmp/tmp.7us84LTOtN/clean/clean-response-2026-10-08-sc-002.tar.gz` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 0 | 290 | `7e7fd743b142148a90b145032709297c8ade1493595a5ba5a2ad8e5933d3cea8` | 747 | `24da1657bfc9cf300c8d1109aae85052916932dbddbf47072210a74da777fd82` |
| `bale-0.4.51/scratch/apply_--dry-run_--json_tarball+scope-drift-refused.json` | `bale apply --dry-run --json /tmp/tmp.7us84LTOtN/drift/drift-response-2026-10-08-sc-002.tar.gz` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 1 | 521 | `226625c1bfd08134df342813795fdd9dc03664787723525867674a787c068ca0` | 1363 | `deb16ba9bd89454784f85cc3011ac3f27365f58f45888f84b06d3bf4615eea7c` |
| `bale-0.4.51/scratch/unlock_sid_--json+unlock-refused+hold-branch.json` | `bale unlock 2026-10-08-sc-002 --json` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 1 | 569 | `b6bd5de4407d3f378daea09b3a9883c4394da7bdd24f805846d0ba1337934cda` | 314 | `98198a9917db84acc4d8b901bc57fcaf99a819b58cfd27ea41050a9d41f47e8a` |
| `bale-0.4.51/scratch/unlock_sid_--reason-aborted_--json.json` | `bale unlock 2026-10-08-sc-002 --reason aborted --json` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 0 | 489 | `319fb276ca1f3b5ab1801a680210ea5d2a7bc31ab60ed7251bb15e9b60501b6e` | 499 | `c20c85866f6403dbd89c209f52431866198036589654012eb630744ee154855f` |
| `bale-0.4.51/scratch/unlock_sid_--json+unlocked.json` | `bale unlock 2026-10-08-ro-001 --json` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 0 | 498 | `be6651120e7e7c06f4b00feb722adb9f5a110adc846a0481cd4af1e53ae6a4ec` | 413 | `3a67defb0070a978697aed381171ab07764d44bdaf025987cd1920ad6d398ecb` |
| `bale-0.4.51/scratch/unlock_--json.json` | `bale unlock --json` | `/tmp/tmp.7us84LTOtN/scratch-repo` | 0 | 231 | `e7a675b90e559559496927b2de7baad3f31f7d62268991615c3beded8bbe501e` | 39 | `73e52366af85bc078cf566c3a5551e2f920c17a41bec616e956e290ad8cfe0fc` |

Outcome groups in this section, by normalized argv (the rule is above):
`unlock_sid_--json` — `unlock-refused+not-open` (in `twine-src/`),
`unlock-refused+hold-branch` and `unlocked` (in `scratch/`), the two
refusals sharing the outcome and so each carrying its line's `reason`;
`open_bundle_--json` — `opened`, `second-desk` and `open-refused`, three
outcomes, so no reason (the refusal's line has one, `not-found`);
`relay_sid_stdin_--json` — `relayed`, `relay-refused+not-an-object` and
`relay-refused+not-open`, each refusal carrying its line's `reason`, which
relay lines have had since bale 0.4.50 (no tag is this section's);
`apply_--dry-run_--json_tarball` — `dry-run`, `scope-drift-refused`.
`relay <sid> --json`, the re-emission, is recorded once and keeps its plain
name.

What the recordings say, beside 0.4.49's: `stats --sid …`, the no-op
unlock, the probe scaffold and the light block are byte-identical to their
0.4.49 recordings, and the exchange block differs only in `created_at` and
its trailer. `open --json`'s line has 23 keys, `reason` and `cause` after
0.4.49's 21; a refusal prints one (`open-refused`, exit 1, its `reason`
from `OPEN_REFUSAL_REASONS`), and `second-desk`'s `tarball` is the outbox
path (0.4.49's was null). `relay --json`'s line has 13 keys, `reason`
last. `unlock`, `apply`, `pack`, `status` (13 keys) and `stats` lines are
unchanged in shape; the two `~/twine-src` unlock refusals differ from
0.4.49's only in the sid and in `open_sessions`. **stderr**, recorded for
every row: each unlock refusal's stderr ends with `[bale] error: <message>`
and a newline, the line's own `message` (the HOLD refusal's is preceded by
bale's `[bale] unlock: <sid>` line); each relay and open refusal's carries
the line `[bale] error: <cause>`, the line's own `cause` (the
`not-an-object` relay refusal's between two `[bale] relay:` lines, the
second saying the refusal was recorded as a `relay-refused` attempt); the
relayed and re-emitted rounds', pack's and the two opens' carry the
operator's clipboard notice (`[bale] clipboard: copied … (`clip.exe`,
global bale.toml)`); `status`, both `stats` and `--version` printed
nothing on stderr. The crafter emissions' stderr is
the crafter's `[craft]` commentary. The tests replay all of it: the
player answers each row's sibling, and `unlock_recording`,
`open_recording` and `relay_recording` return it.

Carried paste: the recordings' source. It is not a format entry's fixture
(the `probe-output` entry keeps the 0.4.45 paste as its specimen); it is
what `bin/twine-land-recordings --check` reads.

| file | emission | received (line endings, bytes, sha256) | bytes | sha256 |
|---|---|---|---|---|
| `bale-0.4.51/carried/probe-output_twine-051-record.txt` | the output of probe `twine-051-record` (`bin/twine-record-fixtures`), run 2026-10-08T13:35:24Z; its trailer counts 1444 lines and the paste carries 1444 | CRLF 135428 `b1bb27d1d54b40dc75a086c36c719742e6170b647c93de94d5a86b2662063e01` | 133981 | `dec7a229a8e108c2e2dd43a499e80ce473603201882f7422c1ef98dc7908a238` |

### The installed schemas (session `2026-10-12-twine-pin-floor-002`)

The eight `schemas/*.json` files the gate's second half hashes, landed
byte-exact under the floor's directory. They came from the operator's
`bale-src` context tarball of 2026-10-07 at 0.4.51, carried into the
session as `bale-0.4.51-schemas.tar.gz` (sha256
`b6e6217244fdb81e0e5cab71230f1db9ead6fc632d1414494832779499e614e1`,
117,394 bytes of JSON in eight files). Every hash below is the one
`share/bale-consumption.toml` pins in `[bale.schemas]` — unchanged since
0.4.45 — and equals what probe `twine-052-delta` (2026-10-12) hashed in the
operator's 0.4.52 install's `schemas/` and in the `bale-src` tree at head
`3c85138`; probe `twine-floor-schemas` (2026-10-12T14:10:33Z) hashed the
install's eight again and carried their bytes, which equal the tarball's
file for file. No argv printed them, so the table has no command, exit or
stderr: file, bytes, sha256.

| file | bytes | sha256 |
|---|---|---|
| `bale-0.4.51/schemas/bundle-manifest.schema.json` | 6915 | `3384ebcd52a08044356f30f1031f4389e9b4427d81602173b0c59f4f9f9cea23` |
| `bale-0.4.51/schemas/changelog-record.schema.json` | 5077 | `7b6d351c052dad8588b05e7592da78f9e9052a671ad6dae9395bfd6d531c5b5c` |
| `bale-0.4.51/schemas/diagnostics.schema.json` | 2992 | `bfeef3cc0a6b91b47b1c1c9084ca47349b23a6661b10c848da3b4ef28b413521` |
| `bale-0.4.51/schemas/escalation-record.schema.json` | 5547 | `16729aae82e20425f91b9fb343de6a74d00fa417ce3cd718767413deee550c41` |
| `bale-0.4.51/schemas/exchange-record.schema.json` | 6457 | `c9c291899103c4a73768ef930697722b89c5c3ef8f5b388c78c36741316cddc8` |
| `bale-0.4.51/schemas/request-manifest.schema.json` | 15000 | `70a0c2bd3b6b0d4cf17bc97010c2b7d58931527b7b3100aa984ca3576c075e3d` |
| `bale-0.4.51/schemas/response-manifest.schema.json` | 26227 | `02d2b6413d078e031641c99e09a9fea909555bdfcb9b2a8a110dbdce63f5817e` |
| `bale-0.4.51/schemas/telemetry-record.schema.json` | 49179 | `b79d7bf75c10f5799484f906954461e7379ef6d4a870bb7df8c08ce050b38825` |

## Provider recordings

**The rule.** A provider recording is what a named model of a named
provider returned on a named day, under `fixtures/<provider>/`, never
hand-written and never edited; a recording of a new model or a new day is
a new file beside the old ones. It comes in two kinds:

- **A carried emission** (R1's): the `usage` object of one response,
  landed as one JSON object on one line with its trailing newline, named
  `<api>-<what>-<YYYY-MM-DD>.json`.
- **A wire capture** (since Arc 2 R2): the bytes of one HTTP exchange as
  the provider sent them — no newline added, nothing re-serialized, the
  SSE streams' `data:` payloads with the padding spaces inside them —
  landed by `bin/twine-land-provider-recordings` from a provider-recording
  probe's paste-back, which lands under `fixtures/<provider>/carried/` as
  their source (every CRLF turned into LF, nothing else changed). Per
  recording `<name>`: `<name>.request.json` (the body sent, when one
  was), `<name>.response.json` or `<name>.response.sse` (by the recorded
  `content-type`), and `<name>.meta.json` — one JSON object on one line
  with its newline: `method`, `path`, `status`, `headers` (as the probe
  printed them, in order), `request_sha256`, `response_sha256`,
  `recorded_at` (the paste's `date-utc`), and beside them `name`,
  `seconds`, `note`, `request_bytes`, `response_bytes`, `request_file`,
  `response_file` and `probe`.

The bale naming rule (`fixtures/bale-<version>/…`, argvs named by role,
outcome groups, `.stderr` siblings) is bale's and does not apply here: no
bale argv printed these, and `tests/fixture_rule.py`,
`tests/test_fixtures.py` and `bin/twine-land-recordings` walk
`fixtures/bale-*/` only, so they neither derive nor check this directory.
`tests/test_runtime.py` holds each file here to its row below — bytes and
sha256 — and the carried emission and the meta files to being one JSON
object line; `tests/test_anthropic.py` holds the wire captures to the
hashes their session's brief pinned and replays them through the
Anthropic adapter's readers; `tests/test_provider_lander.py` runs the
lander. Twine's tests never reach the provider (T8): these files are the
only provider output the suite ever sees, and no key is in any of them.

**The lander**, `bin/twine-land-provider-recordings PASTE [--check] [--tree
DIR]`: reads a provider-recording paste-back (`=== PROBE BEGIN <slug> ===`,
an `environment` section with `date-utc:`, per recording a `== rec <name>:
<METHOD> <path> status <N> seconds <S>[ note …]` header, its `header` lines,
`request-sha256`/`request-b64gz` when a body was sent, and
`response-sha256`/`response-b64gz`; the `--- integrity: N lines ---`
trailer), refuses — exit 1, naming the recording — unless the trailer
counts the block and every gzip+base64 copy decodes to the byte count and
sha256 printed beside it, and derives the files above plus the paste at
`carried/<slug>-<YYYY-MM-DD>.txt`. Without `--check` it writes them
(never replacing a file that holds other bytes) and prints this section's
rows for the worker to place; with `--check` it writes nothing and exits 0
exactly when every derived file is in the tree byte-exact and this file
carries each one's row exactly (the carried paste's received cells too).
Files the paste does not derive — the 2026-10-08 usage object, a later
probe's — are left alone. Exit 2 on a usage error or an unreadable paste.
stdlib only; runs under `python3 -I -S -B`.

**`anthropic/messages-usage-2026-10-08.json`** — the `usage` object of
one Anthropic Messages API response, from the architect's own `curl` to
`POST https://api.anthropic.com/v1/messages` on 2026-10-08: model
`claude-haiku-5-5`, `max_tokens` 16, one user turn. It is a
**carried emission, not a byte capture of the wire**: the architect printed the
parsed `usage` object through Python's `repr`, and the desk of the sitting
`2026-10-08-open-arc2-003` re-serialized it as JSON (`json.dumps` spacing,
keys in the order the API returned them), as the rule for carried pastes
above allows. It reached this repository in the request brief of session
`2026-10-12-twine-runtime-registry-007` (its §3), inside a fence, and was
landed by slicing the fence's one line in code and appending the newline —
nothing retyped — to the bytes and hash the brief pins. What it holds
beyond what `from_anthropic` reads (`cache_creation`'s 5m/1h split,
`service_tier`, `inference_geo`) is kept as recorded and ignored by the
mapping (claude/context/runtime-contract.md §4).

| file | bytes | sha256 |
|---|---|---|
| `anthropic/messages-usage-2026-10-08.json` | 293 | `98137f648aa03f5c73628db77527df11b7f0d3222067f499e6b7573521f2b094` |

**The wire of 2026-10-13** (session `2026-10-13-twine-runtime-anthropic-002`,
Arc 2 R2). Probe `twine-anthropic-record`, run by the architect at
2026-10-13T00:43:12Z with his own key against `claude-haiku-5-5` (Python
3.12.3; every call `max_tokens` ≤ 2048), fifteen recordings:
`models` (`GET /v1/models`: per model `max_input_tokens`, `max_tokens`,
`capabilities.thinking.types` — `enabled` refused by every 5.x model,
`disabled` by Sonnet 5.5, Opus 5.5 and the Fable models); `text` and
`text_stream` (`end_turn`, one text block); `max_tokens` and
`max_tokens_stream`; `tool_use` and `tool_use_stream` (a `tool_use` block
with `caller`; streamed, four `input_json_delta` pieces); `tool_result` and
`tool_result_error` (the round trip, the second with `is_error: true`);
`thinking_stream` (adaptive thinking: an empty `thinking_delta`, a
`signature_delta`, usage `output_tokens` 33 with `thinking_tokens` 30);
`cache_write` and `cache_read` (`cache_control` on the system block: 2556
tokens written, then read); and three refusals, `error_401` (a bogus key,
`sk-ant-not-a-key`, sent in a header the probe did not print), `error_404_model`
and `error_400`. The paste reached this repository in that session's
request brief (its appendix), inside a fence, and was landed by slicing
the fence's 201 lines in code — nothing retyped — to the bytes and hash the
brief pins (received as CRLF, as the row says), then landed from it by the
lander; the brief's §3 table pins every recording's hash, and
`tests/test_anthropic.py` holds them to it.

| file | bytes | sha256 |
|---|---|---|
| `anthropic/models.response.json` | 14233 | `d744304435f479b8350556098dbf9cc5c3a4d94814351dfdcc073623d4afce13` |
| `anthropic/models.meta.json` | 505 | `d5344bbe5f2c73e63111e6c909044082f01d4ca68129e1e29635f73cf383309f` |
| `anthropic/text.request.json` | 192 | `f874bb9125f432e6a5aa5ebd4964125d6792872d100c919fc775e1c10828f1a1` |
| `anthropic/text.response.json` | 527 | `b9330f4527da18c36006c76905134be6ead1bd61980a17d02dcf117c823c11a3` |
| `anthropic/text.meta.json` | 895 | `004df2ef01b21e5d2fbcad502e5693bd5ae3b67e3ac50cd21996b2b2c3e4b8a3` |
| `anthropic/text_stream.request.json` | 208 | `7364a117e4583cff95db45733fc2a7ac9fec66e9b9355f66cfb8ec61a7b14467` |
| `anthropic/text_stream.response.sse` | 1258 | `ff21be177393814ab673b742cb0ea22ad80d22f9ee6ac68d84c681a49fd141b5` |
| `anthropic/text_stream.meta.json` | 932 | `561a5ef16c9cfd93f7f0b0f47ff5eec66becf250caff65aba8b6ffc1e5081b15` |
| `anthropic/max_tokens.request.json` | 191 | `4a8c485ec97d5179a2a481ed4cdc4f3e1b5e3da0c7db11bdde1b6c8160c35029` |
| `anthropic/max_tokens.response.json` | 536 | `258f687adf36abbd828b39bc886ab360f1677fbb957eb378f0ec3f28e7de25fd` |
| `anthropic/max_tokens.meta.json` | 941 | `79824d306bd63b0a640f60a3bd76b103ce9ca9bd038ce46a335181882e056361` |
| `anthropic/max_tokens_stream.request.json` | 207 | `3b828585dec98edf6c557a8f72ca8f0736339de31aca71e6753ab5c6cd15e5e0` |
| `anthropic/max_tokens_stream.response.sse` | 1266 | `5b74e39103d928b54390010db3f80b5643fc19326987d4861be9d1a213b659bc` |
| `anthropic/max_tokens_stream.meta.json` | 950 | `6c731348d5a0a6a1f44030900f7b101f3b917b4c981327bb7743503a39b7d678` |
| `anthropic/tool_use.request.json` | 526 | `e35be61c7d9347e59825ddb4267a5f4cd7bf213272ae4f48dd20d201cf0f1a36` |
| `anthropic/tool_use.response.json` | 631 | `712d0ac17cd9439f426b00300a68e8c8eef10834c7fecbc1607c09b8830e89ee` |
| `anthropic/tool_use.meta.json` | 933 | `1ac6ba57d21e1934b710018be0bfd72172684d1ed6aa003066ed40dea0797c8e` |
| `anthropic/tool_use_stream.request.json` | 542 | `45665e3e977936e29f4e51e9e5a2a6efc7ee559eba3d757b1aa4939107b0a5bd` |
| `anthropic/tool_use_stream.response.sse` | 1795 | `9a0ee0617a853e634650710792baef74c067e0566ee666b1e1cf5cd945d396d7` |
| `anthropic/tool_use_stream.meta.json` | 944 | `be6507a1dadfd8ae4d7f2cb9ac0e02133d9b9bd914de19562a3ac478ec87f10f` |
| `anthropic/tool_result.request.json` | 855 | `d5d067e11a7eee68deb08a87242adbbdd59b9ba58e346a82fe1def0deff0d8a0` |
| `anthropic/tool_result.response.json` | 552 | `3090a163575dedb1158041ef1507946ee8777f8e9e141996bf2ddc4515905785` |
| `anthropic/tool_result.meta.json` | 946 | `452708d1eb2a972d27ca432f83c681a8cabfe5cfc0c0794ffabe2b7696de8486` |
| `anthropic/tool_result_error.request.json` | 878 | `ebc86720085f5a219382d1a1c56d49c609376b8c1e0b6bc48488245433ae7e21` |
| `anthropic/tool_result_error.response.json` | 642 | `248e6b96cd39b32725d7de3dad99cd737ba120382b2901edbc0463efc0eb5137` |
| `anthropic/tool_result_error.meta.json` | 965 | `d75676984fce1d8bc6975e330a7d8a5d2a77fdc070da3b3511e36352df78e488` |
| `anthropic/thinking_stream.request.json` | 279 | `1b46a648951e2c91bdb2d3cde8f00e3c6381a2f647f56cdfeba9c31ed4a02606` |
| `anthropic/thinking_stream.response.sse` | 2566 | `2c159fc05ba61367ab9c0f52346a7d75787783bc22f5c25d35e1af27bb831988` |
| `anthropic/thinking_stream.meta.json` | 1003 | `978946deeea8d6bb56d22c7dc20640e18f943f9fa563ebe91bf4a5bfd34a87ae` |
| `anthropic/cache_write.request.json` | 6772 | `eef65b5ead7166b24c483142a365762133a3d5c551d7c1e4af355f73cbf1a6d0` |
| `anthropic/cache_write.response.json` | 530 | `b857ef93e7081d52231d0d7e2bd51b9d715d0aa25a35d3deb5d306a904469f51` |
| `anthropic/cache_write.meta.json` | 954 | `5d7637a28ab40eeca8ee9dcfd94db96ca0554d177a5940dddeee76755d153bd0` |
| `anthropic/cache_read.request.json` | 6772 | `9b0521f6aea591eb5436d770cfcf0329bc92807a74ac9167d60c5bb9b8fbe460` |
| `anthropic/cache_read.response.json` | 527 | `ad4dafd70c4656126f0d2416e880ecef05add216f508e718615e6d0e883b7ff0` |
| `anthropic/cache_read.meta.json` | 947 | `5a4f858358814f404a9ec30f62a139d0544b43089e3409e1cfcb4a995e0283e9` |
| `anthropic/error_401.request.json` | 95 | `088074b66073201ecd0f9b33719bbe75d12a7e902cd4a7f63a5968ccae7ed15f` |
| `anthropic/error_401.response.json` | 130 | `822bfc574d1a7489ef21c556d4dcd30c4aaa7ab4be7b00d275a1fbd74800b661` |
| `anthropic/error_401.meta.json` | 620 | `9f898cfb54c18b358d753ae578ad7b67f2ec38b8fb36c51ae593bc9dd219092d` |
| `anthropic/error_404_model.request.json` | 97 | `cce91afb6514cbc46fcb0b44dcd346dd8f4422a951b331ae7d455835d2acf801` |
| `anthropic/error_404_model.response.json` | 133 | `ed007a184db21677ff8ee6621308461008e960182b70f75313e48ef9cf3bf174` |
| `anthropic/error_404_model.meta.json` | 633 | `6f4f8bdd88e267023f86da7942c15f348ab2b21f847000a9f5fac47cbd3a6863` |
| `anthropic/error_400.request.json` | 46 | `2050f12e5179384323c5c6304369a047c9e4b9932002b706a3c89b7876f1a5c3` |
| `anthropic/error_400.response.json` | 138 | `5c8bd802a47e72312fddd1dd662e8258e30edeb0dd3d7d630d07bfbf71313dc7` |
| `anthropic/error_400.meta.json` | 634 | `007d22f88f64466d90582252d639c9dca313d69b196412560ba287d5eb568d5f` |

| file | bytes | sha256 | as received |
|---|---|---|---|
| `anthropic/carried/twine-anthropic-record-2026-10-13.txt` | 29039 | `4d1bfd63ef6746546c13962aad08f3ee726e4d81284b69cb21ea4a1bbd5da92d` | CRLF 29240 `41e8fe662769eb260af3e43d0615ba97dfdae3a58727d1a978dcc40273903d02` |

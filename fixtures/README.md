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
| `unlock` | `unlock <sid> --reason aborted --json` | a positional right after `unlock` is role `sid` (session 5b) | `unlock_sid_--reason-aborted_--json.json` |
| `open` | `open [--check] <bundle> --json` | every positional after `open` is role `bundle` (session `2026-10-07-twine-pin-049-001`) | `open_bundle_--json.json`, `open_--check_bundle_--json.json` |
| `pack` | `pack <goal> --slug ro … --json` | the positional right after `pack` is role `goal`; a flag's value (`--slug ro`) stays (same session) | `pack_goal_--slug-ro_--read-only_--no-readme_--json.json` |

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
is the file; stderr is not recorded byte-exact for any row — the probes
print its first lines only, and clip.exe mangled their non-ASCII — so the
player answers it empty, and no test replays a stderr from a recording or
derives one; see "stderr" under bale 0.4.49 below). A row whose exit was
not captured says `unrecorded`, never a guess, and the player refuses to
answer for it unless the test names the code it assumes; every row of
the 0.4.49 section has one.

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
  crafter emission is re-recorded at each pin, so its `fixtures_version`
  is the pin.

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
refuses before the reason matters.

The 0.4.45 section above and every file under `bale-0.4.45/` stay as
recorded history; the tests read the pinned version's directory
(`tests/helpers.py` `PIN`) and, for a carried paste, the version the
manifest's format entry names.

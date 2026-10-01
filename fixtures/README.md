# fixtures/ — recorded bale outputs

**The rule.** A fixture is the bytes a named bale version emitted on the
architect's machine, recorded through a probe and landed byte-exact —
never hand-written, never edited, never regenerated from memory. Tests
read fixtures instead of a bale install (twine-seed.md T8): under
`bale.toml`'s sandbox the suite has no network and no bale, so the
recorded outputs are the only bale the tests ever see. A `.json`
fixture holds exactly the one line bale emitted on stdout under
`--json`, trailing newline included; `.txt` holds a non-JSON output the
same way.

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

State of `~/twine-src` at recording: head `0c01dcb` (2026-10-01T23:11:26Z),
branch `master`, sessions `2026-09-29-begin-harness-001` (the sitting,
forecast `[]`) and `2026-10-01-twine-core-002` (forecast `["."]`) open,
`2026-10-01-twine-seed-001` applied. The `status` fixture's `sid` is the
sitting's: bale's lock state names the earliest open session.

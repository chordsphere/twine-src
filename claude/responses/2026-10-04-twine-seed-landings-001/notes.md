# notes — 2026-10-04-twine-seed-landings-001 (the second seed tidy)

Six texts landed in `twine-seed.md`, and nothing else changed. I started from the seed the request
shipped, sha256 `70637c290117bcbb774f1e8a4cf61f3a084263cbf6eb41f0c6a5a3f1ac188c64`, 1273 lines, LF,
UTF-8. That is the brief's hash, so the anchors in its table are the bytes I placed by. The landed
file is 1332 lines.

## Where each text landed

| text | beneath | landed lines |
|---|---|---|
| B | D2 | 434–438 |
| C | D15 | 651–657 |
| A | D17 | 723–733 |
| F | the §5.1 road table (rows 4 and 5) | 1029–1047 |
| D | Q-6 (now marked ratified) | 1122–1128 |
| E | Q-8 | 1139–1140 |

These match the brief's computed lines. Before inserting, I checked each "follows" line and each end
anchor against the shipped file: both match the table, and every end anchor is unique. I sliced the
texts out of the brief's fenced blocks mechanically and did not retype them. In text F, the two
`<this-sid>` openers became `2026-10-04-twine-seed-landings-001` and nothing else changed, so those two
first lines run longer than their neighbours. I left them unwrapped, because the constraint says
byte-exact.

## The texts against their sources

I removed the `> ` prefixes from the two notes' Proposals blocks and compared word sequences with
whitespace normalised. A, B, C and E are identical to their sources. D differs only by the sitting's
edit: `proposed` became `ratified at sitting 2026-10-03-continue-twine-003 (light block 5 [2], "as
assumed")`, and the closing `; the architect ratifies.` was dropped.

**No factual flags on the six texts.** I checked these facts against the notes:

- **Text A.** 13 + 9 + 9 = 31 bale keys, and the stop set is ten plus two, so 31 + 12 = 43 rows. The
  25 moves are 10 twine, 5 operator and 10 planner.
- **Text F, row 4.** `VERSION` 0.4.0 matches transitions-004's notes.
- **Text F, row 5.** `VERSION` 0.5.0, the HOLD's two faults (the whole-tree test, and the timeout
  race in 2b-i's tests), and the retry under the same session all match cost-spine-005's "Re-attempt
  after the HOLD". So do the `cap-unchecked` proposal and the runner's open question about reaping.
- **Text D.** It matches cost-spine-005's "Q-6: the hard cap's scope, proposed".

The ratification references (light block 2 [1], 4, and 5 [2]) are checked only against the
brief's quoted carry-forward, because the carry-forward itself did not ship.

**One discrepancy, not in any text.** cost-spine-005's Proposal calls `cap-unchecked` "a twelfth key
to the `stop` axis". transitions-004 already made the stop set twelve keys, which text A's 43 rows
depend on, so `cap-unchecked` would be the thirteenth. Text F names the key without counting it,
so nothing landed is wrong. Whoever writes 5b's brief should count from twelve.

## Places to look

- **Q-6's own lines are unchanged.** It still reads "*Arc 1 session 5 must decide.* … the architect
  ratifies." Text D beneath it carries the ratification, the same way TQ-1's annotation records its
  answer. The brief scoped out every existing line, so I took "Q-6 marked ratified" to mean the
  annotation. If you want the italic status tag itself updated, that is a one-line tidy for a
  later session.

## Validation

`validation.sh` reads only `twine-seed.md` and `.bale-manifest.json`, and walks nothing. It writes
only `.validation-logs/<timestamp>/`, which it announces first. Every byte outcome is checked
with `cmp` of files or a sha256, never by comparing captured strings. Each placement check compares
the landed span from one line before the text to one line after it against blank + text + blank,
so the blank-line framing is asserted along with the text. The reversal deletes the six insertions
with their added blanks and requires the shipped hash at 1273 lines.

One edit to a crafted fragment: the claims-reconciliation epilogue from
`tools/craft_response.py --validation-epilogue` runs `python3 -`. I changed that to
`python3 -B -`, because the brief says any Python runs under `-B`. The encoding check also runs
under `-B`, and the script exports `PYTHONDONTWRITEBYTECODE=1`.

I ran it twice, per TARBALL.md §7.2:

- **On a staged tree.** This was the shipped seed with `files/` overlaid, `apply.sh` run, the manifest
  at `.bale-manifest.json`, and a stand-in checkpoint under `claude/checkpoints/`. Exit 0. All 11
  checks `[PASS]` and all 10 claims reconcile `[agree]`. Afterwards the seed's hash was unchanged,
  and there were no new files beyond `.validation-logs/` and no `__pycache__`.
- **On the unmodified base.** Exit 1. All six placements, the reversal, the line count and the
  session-id check `[FAIL]`, each by name with a diff. The encoding and placeholder-count checks pass
  on both trees, as invariants should.

There are no project-level checks, because the repository's suite does not read the seed. So the
claims cover the session assertions, `pass` and observed. The encoding check is file syntax and
stays unclaimed.

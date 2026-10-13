# Notes — 2026-10-13-twine-seed-tidy9-005

Base seed checked first: 1603 lines, sha256 afbc1bee…cb45, as the brief
requires. The eight blocks were sliced from the brief's fences by script
(line counts 18/23/22/7/3/4/6/4 = 87, as stated) and inserted after the
six anchors, one blank line before each; every anchor was unique in the
base and already followed by a blank. The result is 1698 lines, sha256
337722a561b2776a0a80d48fe8a1ad96a37235b6945a38669eb9af77d1be0f35 — the
brief's hash. `VERSION` is untouched; no path outside `twine-seed.md`
changes.

`validation.sh` pins each fence's sha256 and checks the blocks by
unique anchor text on the landed tree, the blank before each block, the
anchor's own blank after the run, 1698 lines, the landed hash, and the
reversal to the base. I ran it on the landed tree (all pass), on the
unmodified base (fails), and against four mutations — a character
changed inside block A, blocks A and B swapped, a stray space elsewhere,
and block D placed before the existing T8 annotation instead of after
it — each of which fails it.

Suite claim is `predicted`: `tests/` is not shipped, and per the brief's
tidy6 fact only `test_spend.py`'s no-prices scan reads the seed and no
block carries a `[model."…"]` table. The base hash through `HEAD:` skips
when staging is not a repo; the reversal proves the base either way.

No forecast departures; no proposals.

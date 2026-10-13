# notes — 2026-10-13-twine-seed-tidy8-001

The placement went exactly as the brief describes. The base seed matched
its pin (1540 lines, `32f418e6…`), every anchor was on the line the table
names, and the landed seed reproduces the brief's pinned sha256
`afbc1bee…` at 1603 lines. The blocks were sliced in code from the
brief's ```` ```text ```` fences, never retyped. `validation.sh` carries
the same slices as Python literals, generated from the fences, and
re-checks each one against its pinned sha256 before using it. A
mismatch there exits 2, because it means the script is corrupt, not
the work.

## What I ran before shipping

I ran `validation.sh` in six mock staging trees, each holding the seed,
`VERSION` and `.bale-manifest.json`:

- **Landed.** Every seed check passes: nine blocks found once each, six
  runs at their anchors, the reversal back to the base, and no `TODO`.
  `VERSION`'s `cmp` passes. Exit 0.
- **Unmodified base.** Exit 1. Every block check, every run check and
  the landed-hash check fail.
- **tidy7's mutations.** Each exits 1, and each names its fault:
  - One character changed inside C: C is not found, the 5.2 run fails,
    and so do the hash and the reversal.
  - D and E swapped: the Q-3 run fails, along with the hash and the
    reversal.
  - A stray trailing space on line 10: the hash fails, and the reversal
    gives `a02dd236…` instead of the base.
  - G placed before Q-8's existing annotation: the Q-8 run fails,
    along with the hash and the reversal.

## Two calls to check

- **"The base hash before placement."** In staging the base no longer
  exists as a file, so I check it two ways. First, the reversal must
  reproduce `32f418e6…` exactly. Second, when staging is a git checkout,
  the script also hashes `HEAD:twine-seed.md` against the pin. That
  check SKIPs with its reason when there is no `.git`. I tested it both
  ways: it SKIPs in a plain tree and PASSes in a repo committed at the
  base.
- **The suite.** It isn't in the request, so it is claimed
  `pass`/`predicted` on tidy6's fact. The only test that reads the seed
  is `test_spend.py`'s no-prices scan, and none of the nine blocks
  carries a `[model."…"]` table. Neither does the base: I grepped it and
  found zero.
  The command, `python3 -B -m pytest -q -p no:cacheprovider` from the
  staged root, is my assumption about how twine runs its tests. If
  pytest isn't importable, the check SKIPs with that reason and the
  claim reconciles `[n/a]`. If twine uses a different runner, the label
  is the one line to change. Pytest wasn't available where I built
  this, so the suite has never actually run against this change.

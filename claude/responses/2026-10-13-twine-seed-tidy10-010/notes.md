# Notes — 2026-10-13-twine-seed-tidy10-010

A small, fully pinned session; it landed on the first pass.

## The base, as received

`twine-seed.md`: 1698 lines, sha256
`337722a561b2776a0a80d48fe8a1ad96a37235b6945a38669eb9af77d1be0f35`,
which matches the brief and the request's `provenance.base_files`.
`VERSION` reads `0.22.0` and is not shipped. The brief's own sha256
matched the manifest's `readme` pin, and every fence hashed to its pin
before I used it.

## Anchors (base line numbers, found by text)

Each anchor occurs exactly once in the base, and again after the landing.

| Block | Where | Base line | Landed line |
|-------|-------|-----------|-------------|
| A | §5.2, after R4's bracket | 1386 | 1411 |
| B | D23, after its 2026-10-01 bracket | 931 | 931 |
| C | TQ-1, after R4's bracket | 1507 | 1555 |
| D | §4.3 "Window management" bullet | 1004 | 1010 |
| E | §4.3 "Suspension and cold resume" bullet | 1015 | 1027 |
| F | §4.4, after R4's bracket | 1036 | 1054 |

Every base number matches the brief. A, B, C and F already had a blank
line after the anchor, so each block went after that blank and is
followed by one new blank. D and E had none, so each became blank,
block, blank before the next bullet. I inserted from the bottom of the
file up, using lines sliced from the fences. I typed none of the block
text myself.

## Landed

1751 lines, 98,503 bytes, sha256
`6e90e506e9aa2e61121dde7907cd3cfa07830d29f1e611e44217e9805e854dfa`,
which is the brief's pinned value. No other line changed and no other
file changed.

## Runs made

I ran `validation.sh` from a tree holding `twine-seed.md` and `VERSION`:

- **Landed tree, with the finished manifest staged as
  `.bale-manifest.json`:** exit 0. Every seed assertion, the reversal,
  `VERSION` and the manifest check passed. The suite reported `[SKIP]`
  because no `tests/` directory was there.
- **Base tree:** exit 1. All six presence checks and all six placement
  checks failed, and so did the landed check (1698 lines, the base hash).
  The reversal reported "skipped by failure". `VERSION` passed.
- **Mutation 1, one character changed in block D**
  (`window-exhausted` → `window-exhaustid`): exit 1. The presence and
  placement checks for D failed, and the landed hash came out as
  `f47aa935…`. The other five blocks passed.
- **Mutation 2, block A placed before R3's bracket instead of after
  R4's (still 1751 lines):** exit 1. A's placement check failed and the
  landed hash came out as `c9bba6ad…`. Presence and the reversal both
  passed, which is correct: the bytes are all there, just in the wrong
  place.

I also ran two checks on the script itself. A copy with one character
changed inside its carried block F exited 2 and named F. A copy of the
landed tree with a one-test `tests/` package ran the suite branch:
`[PASS]`, the reconcile line read `[agree]`, and no `__pycache__` was
left behind.

## Claims

The only claim is the project suite (`python3 -I -B -m unittest
discover -s tests -t .`): `pass`, `predicted`, on tidy6's fact as the
brief gives it. Only `test_spend.py`'s no-prices scan reads the seed,
and none of the six blocks contains a `[model."…"]` table. The suite
was not shipped, so I could not observe it. The session assertions are
observed (above) but not claimed, following TARBALL.md §5.3: claims
cover project-level checks when the project has any.

## Smaller things

- `validation.sh` carries the six blocks as Python string literals
  generated from the brief's fences, and re-hashes each against its pin
  before using it. The placement check reads the brief's rule
  literally: anchor, blank, block, blank, and then the line the brief
  says follows (`### 5.3 Arc 3`, `**D24 — Stack lean`, `- **TQ-2`,
  `- **Turn-end detection`, `- **The transition table grows`,
  `### 4.5 Effort (T11, directed)`).
- The only thing the script writes is
  `.validation-logs/<timestamp>/suite.log`, and only when `tests/`
  exists. It announces that location at the top.
- I did not read DOCS.md, although this is a doc edit. The brief pins
  every landed byte, so nothing in the doc-inventory contract could
  have changed what ships.
- `model_identity` is `anthropic:claude-opus-5-5`, the configured model
  string this surface shows me. The surface also says the model actually
  serving a turn can differ from it.

# notes — 2026-10-12-twine-seed-tidy7-006

The seed checked out before anything was touched: 1454 lines, sha256
`128671eab865722d3e97b5826b135d17c91902383415dcae9b6cd6a3ff0cb2e8`,
the brief's value. The three anchor lines were where the brief said
(274, 449, 1169), and the D2 anchor text does appear exactly twice
(449 and 1156); the D2 run went after the first.

## How the blocks were cut

The seven blocks were sliced in code from the brief's ```` ```text ````
fences (lines strictly between the opening and closing fence, each with
its newline) and inserted by line number into the base bytes; nothing
was retyped. Their line counts matched the brief's headers
(13, 9, 13, 13, 5, 23, 3 = 79). The landed seed is 1540 lines,
sha256 `32f418e637ef4ac75318c6ed4cf68e70cffea23d1a41c58bfec11a80fd793c7a`.

Fixture pins carried in `validation.sh` (sha256 of each block's bytes):

| block | lines | sha256 |
|---|---|---|
| A carry-exchange-json-001 | 13 | `cc5a84feed7a508fe817f6516723c96dd03d25eec7f4e5a3ebba2e2925dd93a9` |
| B status-inflight-004 | 9 | `efd6b8e44aaeb1b8eba61267ea9b133c2d5f4dc7030cbb996ea7a731b31a4e38` |
| C exchange-vouch-005 | 13 | `4850466078861f344a9081c0ddaeeebbdaba271316065f7a13a56e548ed01b34` |
| D pin-051-001, D2 | 13 | `d08c6f5820cb584bc0b6b8eab9e4ae691ecc9f171407b03f672ce2e0775c5551` |
| E pin-051-001, road | 5 | `3abd63714877709930e8df2b6efa78e41db035dd1363179eb469042b3fc75974` |
| F pin-floor-002, D2 | 23 | `dd14e8f10b5d5dcde84b60f2c9ffe5ba002fe4448f05f74f439b717b5f925665` |
| G pin-floor-002, T8 | 3 | `e104d99731333d84a0bc53e3fb9f05f06a9a00292f9d0e8d38f74e1598f627d7` |

If the checkpoint compares against the archived `notes.md` files and
disagrees with these, the fault is upstream of this session: these are
the brief's fence bytes exactly.

## validation.sh

The blocks ride inside the script as base64, each with its sha256 and
line count; a drifted fixture exits 2 before anything is graded. The
script reads only `twine-seed.md`, `VERSION`, `.bale-manifest.json`, and
`tests/` for the suite. It never walks the tree and never touches
`claude/checkpoints/`. It writes only under `.validation-logs/<ts>/`,
with `PYTHONDONTWRITEBYTECODE=1`, `python3 -I -B`, and pytest's cache
provider off. The anchor check is structural, not by line number: each
block must sit exactly where the brief's table puts it (anchor, blank,
block, blank, next block or next heading), and D's anchor must be the
first of the two copies. The reversal drops each block plus the blank
before it, requires exactly 86 lines removed and a blank before each
block, and compares the result to the base sha256 and its 1454 lines.

Runs I made before shipping, each in a staged copy (seed plus VERSION
plus `.bale-manifest.json`):

- **Landed tree:** exit 0, every assertion passes, and every claim agrees.
  The suite `[SKIP]`s there because I have no `tests/`.
- **Unmodified base:** exit 1. Verbatim, anchors, reversal, and line count
  all fail. The three guard checks (no TODO, no price table, VERSION)
  pass on the base by design; they guard constraints rather than test
  the change, so the mutations below are what prove them.
- **Mutations**, each exit 1 on the check meant to catch it:
  - M1, one character altered in block C, is caught by the verbatim check.
  - M2, the D2 run landed at the base-1156 copy, is caught by the anchors check ("first copy", "F then D3").
  - M3, F before D, is caught by the anchors check.
  - M4, no blank before E, is caught by the anchors check, the reversal (85 lines removed, not 86), and the line count (1539).
  - M5, one stray byte outside the blocks, is caught by the reversal sha256.
  - M6, a TODO inside the T8 run, is caught by the TODO check (and the verbatim check).
  - M7, VERSION moved, is caught by the VERSION check.
- **Suite branch** with a stand-in `tests/`, using unittest and pytest
  (pytest from a throwaway venv), each with a passing and a failing
  stub. Every case printed the right verdict, and no `__pycache__` or
  `.pytest_cache` appeared.

The brief asks for "the four mutations tidy6 ran." tidy6's list isn't
in this request, so I couldn't reproduce it exactly. M1–M7 above are my
replacement: a superset of anything I'd expect four to have covered.
Swap in tidy6's own if they differ.

## The suite claim

The suite claim is `pass`, `predicted`, resting on the brief's one fact:
the only test that reads the seed is `test_spend.py`'s no-prices scan,
and no block carries a `[model."…"]` table. That second half is also
asserted directly ("seed: no [model.] price table added"). I don't know
whether twine runs its suite under pytest or unittest, so the script
picks at run time: pytest if importable, otherwise `unittest discover -s
tests`. If twine needs a different invocation, the `[FAIL]` line names
the command it ran, which should make that obvious.

## Smaller things

- `VERSION` reads `0.14.0`, which matches block F's own `VERSION` 0.14.0.
  It is pinned by sha256 and stays untouched.
- `model_identity` is `anthropic:claude-opus-5-5`, the configured model
  string this session is shown. The serving model could in principle
  differ.
- The fixtures check is listed in `validation_will_run` but left
  unclaimed, because it tests the script's own bytes and not the change.

# Notes — 2026-10-08-twine-seed-tidy6-002

A small session. Nothing surprised me. Three things are worth having in
front of you at review.

## 1. How the annotations were copied

None of the three was typed, and none came from the brief. A script read
each archived `notes.md` under `claude/responses/<sid>/`. It found the
`## 5. The seed annotation` heading, took the run of `> ` lines starting
at `> [<sid>: `, and stripped the two-character prefix. The wrapping is
the notes' wrapping. The script checked the brief's line counts (10, 9
and 12) and that each block closes on `]` before it inserted anything.
All three sources are clean UTF-8 with LF line endings. The only
characters outside ASCII are em dashes, plus one en dash in the
carry-bundle annotation's "rows 0–5". So the archive copies did not have
the mangling the brief warned the pasted copy might have.

The placements are as the brief's §1 lays them out. Each annotation has
one blank line before it, and the following heading or annotation keeps
its blank line:

- D2: lines 440–449, after transitions-004's "carried, and now enforced"
  annotation, before `**D3 —`.
- D15: lines 712–720, after clear-group-003's "landed —" annotation,
  before `**D16 —`.
- End of §5.1: pin-049 again at lines 1147–1156, then carry-bundle at
  1158–1169. Both come after clear-group-003's "`clear_group` landed"
  annotation and before `### 5.2 Arc 2 — the runtime`.

That is 1454 lines. The clauses the brief says to keep as history are
untouched: pin-049's "still reads the HOLD refusal by its stderr prefix",
the 2026-10-01 row-3 sketch, and T8's 0.4.45 parenthesis.

## 2. What validation.sh proves, and what it can't

There are seven checks, all run with `python3 -I -B`. The script writes
only under `.validation-logs/<ts>/`, and it never lists or reads
`claude/checkpoints/`.

1. The three archived notes match the sha256s the request carried. If
   the archive changed, that fails here; it does not quietly become a
   new source.
2. Each annotation is re-extracted from its notes at run time and found
   verbatim. pin-049 appears exactly twice, and the other two once each.
   Each occurrence is checked for its section, the annotation it follows
   and what follows it, so a swapped landing order fails.
3. With the four insertions removed (each block plus the blank line
   before it), the seed hashes to the base `abb55c02…`. So nothing else
   moved.
4. The seed is 1454 lines.
5. `VERSION` passes `cmp` against `0.9.0\n`. (Bale's reconciliation
   would catch a change too; this check states the brief's constraint
   outright.)
6. The suite, using the project's own discover command.
7. There is no `__pycache__` in the tree.

I ran it twice, as §7.2 asks, on a mock tree built from the request's
`context/`. On the changed tree, checks 1–5 and 7 passed. On the base
tree, checks 2–4 failed, as they should. Checks 1, 5 and 7 pass on both
trees by design, because they guard things that must stay unchanged. I
also ran four mutations: an em dash turned into a hyphen in the second
pin copy, the two §5.1 annotations swapped, a stray space added in §7,
and a planted `__pycache__`. Each one failed at the check it should
have.

**The suite claim is `predicted`, not observed.** The request doesn't
carry the `twine` package, so locally the suite stops at
`ModuleNotFoundError`. The prediction rests on one fact: the only test
that reads `twine-seed.md` is the no-prices scan in `test_spend.py`, and
none of the new text contains a `[model."…"]` table.

## 3. Nothing outside the forecast

`changes[]` is `twine-seed.md` alone, which is the whole forecast.
`apply.sh` is the no-op. There are no proposals: the next annotation,
from the `carry exchange` session, is already queued for tidy 7 in the
brief's §3.

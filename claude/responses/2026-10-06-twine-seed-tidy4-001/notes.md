# notes — 2026-10-06-twine-seed-tidy4-001 (seed tidy, the fourth)

## What landed

Three insertions in `twine-seed.md`. No other line of the file changed, and no other path changed.
`diff` against the base shows exactly two hunks, both pure additions (`671a672,689` and
`1073a1092,1107`).

- **Text J** (kill-followups-003's D15 annotation) sits beneath D15, after the kill-switch-002
  annotation, at landed lines **672–688**. Lines 671 and 689 are blank, and D16 is at 690.
- **Text K** (kill-followups-003's road marker) sits beneath the §5.1 road table, after the row5-001
  annotation (text H), at landed lines **1093–1098**. Lines 1092 and 1099 are blank.
- **Text I** (the row-2 marker) comes straight after K, at **1100–1107**. Line 1108 is blank, and
  `### 5.2 Arc 2 — the runtime` is at 1109. Its `<this-sid>` became `2026-10-06-twine-seed-tidy4-001`,
  read from the request manifest's `session_id`. That was the only substitution. The relay
  template's `<sid>` stays, and the long first line stays unwrapped.

A script sliced all three texts out of the brief's fenced blocks and inserted them by line index,
so none was retyped. The same slicing generated `validation.sh`'s copies of the texts. Status lines
and tags are untouched, Q-6's "*Arc 1 session 5 must decide.*" among them.

## The base

`twine-seed.md` hashed to `491f71545b21f58074b5e2a95f29b1f1eb5bc74712f951507e5f3a029d4c0444`. It had
1358 lines, LF endings, UTF-8 and a final newline, all as the brief and `base_files` give it. The
lines the texts follow (670, 1073) and the end anchors (672, 1075) were where the brief's table
puts them. The script asserted them before it inserted anything.

The landed file has 1392 lines and hashes to `a8147460…48ab38`. Removing landed 672–689, 1093–1099
and 1100–1108 gives back `491f7154…` at 1358 lines. `<sid>` occurs 11 times on 10 lines, and
`<this-sid>` does not occur.

## J and K against the notes of record

A script compared each block with its source: the two blockquotes under "### Seed annotations for
this session, for the next seed tidy" in kill-followups-003's `notes.md`, with the `> ` prefixes
stripped. It folded whitespace and counted every other byte, `—` and `§` included. J has 187 words
and K has 50, as the brief expected, and both word sequences are identical. The desk's
reconstruction is right, so there was nothing to open a clarification over. Only the line breaks
differ, because the blocks are the seed-width reflow.

## Text I's facts, checked against the bytes I hold

The wording is the sitting's and out of scope, so none of this changed anything. What I could
check agrees:

- **2b-ii is `2026-10-03-twine-carry-bale-002`.** Its notes' title line reads "Arc 1 session
  2b-ii".
- **The claims in its first paragraph:** it landed `carry exchange` and `carry response`, the
  dry-run fixture, the normalized-argv fixture player, contract §11, and the `confined` switch
  point (prepared). It took `VERSION` to 0.3.0.
- **`bale relay <sid> -`:** `relay_argv`, in its notes' "Building bale argvs" section.
- **`bale apply --dry-run --json`:** `dry_run_argv`, in the same section.
- **"An intact exchange block's own lines":** "intact block" appears in its notes' item 3. The
  seed's row-2 annotation (shipped 1013–1026) says "an exchange block's own lines".
- **"The one `bale apply` line handed to the operator, T12":** `carry response`'s JSON carries an
  `apply_line` key, and T12 ("twine never merges at rung 1") is among its validation assertions.
  "Handed to the operator" is the seed's own reading at row 2 ("then the apply line, T12"). The
  notes I hold don't word it that way, but nothing in them contradicts it.
- **"Rows 0, 1, 4 and 5 landed above":** row 0 is the sitting's correction ("Session 0 landed this
  seed…"), row 1 is effort-003's "row 1 landed as", row 4 is landings-001's, and row 5 is
  row5-001's "row 5 done". All of them sit above I.
- **"Arc 1 waits only on row 3":** row 6 became Arc 2, row 3 still waits on `bale open --json`
  (shipped 1006–1011 and the slip at 1028–1033), and row 2 is now closed by I. That is the gap
  row5-001's Proposal asked a tidy to record.

## Validation

`validation.sh` has ten checks. Nine session assertions are claimed `pass` (observed): three
placements, the end anchors, text I's session id, placeholder counts, line count, the reversal, and
J and K's words against the notes. The encoding invariant runs and is not claimed (TARBALL.md §5.3),
because it passes on both trees and so guards the file rather than testing the change. There is no
project-level check, since the suite does not read the seed.

How it is built:

- **Reads:** only `twine-seed.md`, `.bale-manifest.json` and kill-followups-003's `notes.md`. It
  walks nothing and never reads `claude/checkpoints/`, other responses, or itself.
- **Writes:** it announces `.validation-logs/<stamp>/` first and writes only there. Every Python
  runs as `python3 -I -B`.
- **The crafted epilogue:** its `python3 -` is now `python3 -B -`. That is the one edit to a crafted
  fragment, as in the third tidy.
- **Byte comparisons:** each placement writes the landed span, from one line before the text to
  one line after it, to a file. It compares that file byte for byte with blank + text + blank built
  from the heredoc. The reversal compares a sha256. No captured shell string is compared anywhere.
- **Text I:** its expected bytes are built by substituting the manifest's `session_id` into the
  template, so the placement and the session-id check test the substitution from two sides.
- **The word check:** it reads the landed lines rather than the script's own copy of J and K, so it
  fails on the unmodified seed instead of passing on both trees.

It ran twice (TARBALL.md §7.2):

- **On a staged copy.** This was the base plus `files/`, with `apply.sh` run, the manifest at
  `.bale-manifest.json`, the notes at their archive path, and a stand-in checkpoint that nothing
  read. Exit 0, ten `[PASS]` and nine `[agree]`.
- **On the unmodified seed.** Exit 1. All nine session assertions `[FAIL]` by name: the three
  placements, the anchors, the session id, the counts (10 on 9), the line count (1358), the
  reversal and the words. The encoding invariant passes.

Neither run wrote outside `.validation-logs/`, and neither left any bytecode. A file listing before
and after each run confirmed it.

## Smaller things

- **Tools.** I read both tools' headers, checked their imports (stdlib only: no subprocess, socket
  or URL libraries) and read each write site before running them. The crafter writes only into
  the response directory under `--write`; its bundle writer exists but I did not use it. The lint
  writes nothing.
- **`model_identity`** is `anthropic:claude-opus-5-5`, the session's configured model. The serving
  model can differ, and this session sees no model picker.
- **Dates.** Everything here is dated from the session id (2026-10-06, UTC).

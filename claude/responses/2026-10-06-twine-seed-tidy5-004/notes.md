# notes — 2026-10-06-twine-seed-tidy5-004 (seed tidy, the fifth)

## What landed

Two insertions in `twine-seed.md`. No other line of the file changed, and no other path changed.
`diff` against the base shows two hunks, both pure additions (`689a690,700` and `1107a1119,1124`;
the second hunk reads as blank + M because diff anchors the shared blank differently, and the
bytes are the same).

- **Text L** (clear-group-003's D15 annotation) sits beneath D15, after kill-followups-003's text J,
  at landed lines **690–699**. Line 689 is the blank after J, line 700 is blank, and D16 is at 701.
- **Text M** (clear-group-003's road marker) sits on the §5.1 (Arc 1) road, after tidy4-001's
  row-2 marker (text I), at **1120–1124**. Line 1119 is the blank after I, line 1125 is blank, and
  `### 5.2 Arc 2 — the runtime` is at 1126.

The file grows from 1392 lines to 1409 and hashes to `abb55c02…05d9ed`. Removing landed 690–700
and 1120–1125 gives back `a8147460…48ab38`, the shipped hash.

A script sliced both texts out of the brief's fenced blocks and inserted them by line index, later
index first, so none was retyped. Before inserting, it asserted the shipped hash, the 1392 lines,
LF and the final newline, and the four anchors in the brief's table: 688 ends `then.]`, 689 is
blank, 690 begins `**D16 — Effort is envelope × policy.**`, 1107 ends `on row 3.]`, 1108 is blank,
and 1109 is the `### 5.2` heading. All of them were where the table says. The same slicing
generated `validation.sh`'s copies of the texts.

## L and M against the notes of record

I ran this check before touching the seed. A script compared each fenced block with its source:
the two blockquotes under "### Seed annotations for this session, for the next seed tidy" in
clear-group-003's archived `notes.md`, with the `> ` prefixes stripped and whitespace folded. L has
96 words and M has 34, as the brief says, and both word sequences are identical. The non-ASCII
characters are the same in both copies: `—` (U+2014) and `§` (U+00A7) in L, none in M. Backticks
and `0.7.1` agree too. So the desk's de-mangling was right, and there was nothing to open a
clarification over.

Only the line breaks differ. The blocks are 72 columns at most, and no code span is broken across
a line. In the notes, M's `clear_group(state_dir, sid, pid)` wraps mid-span; in the reflow it does
not.

## Validation

`validation.sh` has seven checks. Six session assertions are claimed `pass` (observed): the two
byte-compared placements, the anchors, the line count, the reversal, and the words against the
notes. The encoding invariant runs and is not claimed, because it passes on both trees. There is
no project-level check, since the suite does not read the seed.

How it is built, as tidy4 built it:

- **Reads:** only `twine-seed.md`, `.bale-manifest.json` (through the reconciliation) and
  clear-group-003's archived `notes.md`. It walks nothing.
- **Writes:** it announces `.validation-logs/<stamp>/` first and writes only there. Every Python
  runs as `python3 -I -B`.
- **The crafted epilogue:** its `python3 -` became `python3 -I -B -`. That is the one edit to a
  crafted fragment.
- **Byte comparisons:** each placement writes the landed span, from one line before the text to
  one line after it, to a file. It `cmp`s that file with blank + text + blank built from the
  heredoc. The reversal writes the reversed file and checks it with `sha256sum -c` against the
  shipped hash. No captured shell string is compared anywhere.
- **The word check:** it reads the landed lines (690–699, 1120–1124), not the script's own copy of
  L and M, so it fails on the unmodified seed.

It ran twice (TARBALL.md §7.2):

- **On a staged copy.** The base plus `files/`, with `apply.sh` run, the manifest at
  `.bale-manifest.json`, the notes at their archive path, and a stand-in checkpoint that nothing
  read. Exit 0: seven `[PASS]` and six `[agree]`.
- **On the unmodified seed.** Exit 1. All six session assertions `[FAIL]` by name:
  - `session: text L lands beneath D15 at lines 690-699 (byte compare)`
  - `session: text M lands on the Arc 1 road at lines 1120-1124 (byte compare)`
  - `session: anchors hold (J ends 688, D16 at 701, I ends 1118, 5.2 heading at 1126)`
  - `session: twine-seed.md has 1409 lines` (1392)
  - `session: removing lines 690-700 and 1120-1125 gives back the shipped seed (sha256)`
  - `session: landed L and M match clear-group-003's notes word for word` (84 and 22 words of D16
    and road text)

  The encoding invariant passes.

Neither run wrote outside `.validation-logs/`, and neither left any bytecode. A file listing before
and after each run confirmed this.

## Smaller things

- **Tools.** I read both tools' headers, checked their imports (stdlib only: no subprocess, socket
  or URL libraries) and read the crafter's write sites before running either. The crafter wrote
  only `manifest.json` and `apply.sh` under `--write`, and I did not use its bundle writer. The
  lint writes nothing.
- **`model_identity`** is `anthropic:claude-opus-5-5`, the session's configured model. The model
  actually serving the session can differ, and this session sees no model picker.
- **Dates.** Everything here is dated from the session id (2026-10-06, UTC).

# notes — 2026-10-05-twine-seed-row5-001 (seed tidy, the third)

## What landed

Two insertions in `twine-seed.md`. Nothing else in the file and no other path changed.

- **Text G** (kill-switch-002's annotation) is beneath D15, after the second tidy's cost-spine
  annotation. It sits at landed lines **659–670**, and line 672 is the D16 anchor.
- **Text H** (the row-5 marker) is beneath the §5.1 road table, after the second tidy's row-5 split
  annotation. It sits at landed lines **1062–1073**, and line 1075 is `### 5.2 Arc 2 — the runtime`.
  Its `<this-sid>` became `2026-10-05-twine-seed-row5-001`, and nothing else was substituted.

I sliced both texts mechanically out of the brief's fenced blocks and inserted them by line index.
Neither was retyped.

## The base I started from

`twine-seed.md` hashed to `12e87314ab46b053d90952856b80c4b9419d07e1f38416dac08f7f478e3f011c`, as the
brief and the manifest's `base_files` say. It has 1332 lines, LF endings, UTF-8 and a final newline.
Both anchors are whole lines that occur once each, at 659 and 1049, and the lines the texts follow
are at 657 and 1047, as the brief's table gives them. The brief's own sha256 matched the manifest's
`readme` stamp.

The landed file is 1358 lines and hashes to `491f7154…`. Remove G with its blank line (659–671) and
H with its blank line (1062–1074), and the result hashes to `12e87314…` again at 1332 lines.
`<sid>` occurs 10 times on 9 lines, and `<this-sid>` does not occur.

## Text G against its source

I compared text G with the Proposal in
`claude/responses/2026-10-04-twine-kill-switch-002/notes.md` (lines 239–247, the blockquote under
"Seed annotation for D15…") word by word, by script. Both have 107 words and they are identical,
including the real `—` and `§`. Only the line breaks differ, because the notes wrap wider inside a
blockquote, and the brief's block is the seed-width reflow. So there was nothing to open a
clarification over.

## Facts in text H, checked against the bytes I hold

The wording is out of scope, so none of this is an edit. These are the checks I could make, and two
I could not.

- **Agree with the bytes:**
  - `VERSION` 0.6.0 (notes, line 40).
  - The worker's single liveness check where polling was asked for (notes, lines 6–8).
  - The running record's `sid` key, ratified at the desk (notes, lines 24–26). This is consistent
    with a checkpoint fixture that lacked it.
  - `RunResult.group_survivors` and the whole-group wait (notes, lines 141–146).
  - "plausibly also explains cost-spine-005's HOLD sleep" (notes, lines 152–153).
  - The pin-gate question the sitting ruled on (notes, the first "Decisions to ratify" item,
    lines 85–91).
  - Row 3 waiting on `bale open --json` (seed, lines 993–998).
- **Not checkable here:**
  - "both judges", the checkpoint's amendment "to v2", and "the retry applied with the change
    accepted". The brief says these come from the relay and notes "which you hold", but only the
    notes shipped. The notes predate the retry's apply and say nothing about the checkpoint's
    version.
  - The pin-gate *ruling* itself. That is the sitting's, and I have no reason to doubt it.
- **"Of Arc 1, row 3 remains". Consistent, with one gap in the seed's own record.** Row 6 became
  Arc 2 (seed, lines 958–959), and rows 0, 1, 4 and 5 are marked landed. Row 2 is the odd one. The
  road table's annotations last describe 2b-ii as "not yet authored" (line 1005), and the sitting's
  close queues it (line 1328). The seed nowhere records 2b-ii landing at the table. Elsewhere,
  though, the bytes say it did:
  - line 435–437's transitions-004 annotation has `carry exchange` and `carry response` enforcing
    the pin, and names "carry-bale-002";
  - kill-switch-002's notes (line 135) edit those carry verbs in `twine/commands/carry_bale.py`.

  So H is right, but a reader of §5.1 alone sees row 2 still half open. See the Proposal.

## Smaller things

- **Claims.** I claimed the five session assertions as `pass` (observed). No project-level check
  runs, because the suite does not read the seed, so these are the claimable checks (TARBALL.md
  §5.3). The encoding check is listed, not claimed. It passes on both trees, so it guards the file
  rather than testing the change.
- **Validation runs, both trees (TARBALL.md §7.2):**
  - On a staged copy (landed seed plus `.bale-manifest.json`): exit 0, six `[PASS]`, and five
    `[agree]`.
  - On the unmodified seed: exit 1. G placement, H placement, reversal, placeholder counts and line
    count each `[FAIL]` by name, and the encoding invariant passes.
  - Both runs wrote only `.validation-logs/<stamp>/`, and no bytecode appeared.
- **One edit to a crafted fragment.** The claims epilogue from `craft_response.py
  --validation-epilogue` calls `python3 -`. I made it `python3 -B` to honour the brief's -B rule.
  It writes no bytecode either way, because a stdin script imports nothing local. You may want the
  crafter to emit `-B` by default.
- **Tools.** I read both tools' headers and usage, checked their imports (stdlib only, with no
  subprocess, socket or URL libraries) and read each write site before running them. The crafter
  writes only into the response directory under `--write`. Its bundle writer exists but I did not
  use it. The lint writes nothing.
- **`model_identity`** is `anthropic:claude-opus-5-5`, the session's configured model. The serving
  model can differ, and no picker is visible to this session.

## Proposals

### Record row 2's close at the §5.1 road table

**What.** A road-marker annotation for row 2 in the seed's landing form, naming the 2b-ii session
that landed `carry exchange` and `carry response`, so the table's annotations say every Arc 1 row
except 3 is done.

**Why.** The table's last word on 2b-ii is "not yet authored" (line 1005). Its landing shows only
indirectly, in D2's transitions-004 annotation (lines 435–437, "carry-bale-002") and in the code.
Text H's "row 3 remains" is true, but the table does not show it. I don't hold the 2b-ii session's
full id or its relay, so I can't write the line.

**Scope hints.** `twine-seed.md` only, beneath the §5.1 road table. It is the next seed tidy's, and
the sitting supplies the sid and facts.

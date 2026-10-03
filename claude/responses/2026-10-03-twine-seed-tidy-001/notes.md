# notes.md — 2026-10-03-twine-seed-tidy-001

I modified two files, both in the forecast: `twine-seed.md` (insertions
only) and `claude/INDEX.md` (one token). Nothing was created or deleted,
and no other path was touched. There was no probe, light block or
clarification. The budget was comfortable and nothing was compacted.
Both context files hashed to the brief's values (`74c454fb…`,
`2f2a73c9…`), and every end anchor sat on the line the placement table
names, with the shipped blank line before it.

**Substituted id:** `2026-10-03-twine-seed-tidy-001`, taken from the
manifest. It replaces `<this-sid>` in the five openers only.

## Where each text landed (line numbers in the landed file)

The shipped seed has 1225 lines and the landed one has 1273. The 48
added lines are the five texts' 43 lines plus one blank after each.
Each text was sliced from its fenced block in README.md by a script,
not retyped.

| text | lines | follows | directly before |
|---|---|---|---|
| A | 125–131 | I2a (now 115–123) | I2b's first line, now 133 |
| B | 142–151 | I2b (now 133–140) | `**T4 — …`, now 153 |
| C | 193–198 | I3 (now 184–191) | `**T5 — …`, now 200 |
| D | 996–1001 | the bale-src slip annotation (now 989–994) | `### 5.2 Arc 2 — the runtime`, now 1003 |
| E | 1027–1040 | §5.3's paragraph (now 1019–1025) | the `---` closing §5, now 1042 |

`claude/INDEX.md`: line 17's `T1–T10` is now `T1–T14`, en dash as
shipped. Same byte length; nothing else changed.

## One reading worth your eye: the `<sid>` count

The brief says the landed seed's "literal `<sid>` count is the shipped
three plus text B's." Text B carries **three** literal `<sid>`, not
one: "replace each `<sid>`", then "`bale relay <sid> -`, where `<sid>`
is…", with the second and third on the same line. So the landed seed
has **six occurrences on five lines**: 146 and 147 from B, plus the
shipped 336, 446 and 980 (formerly 310, 420 and 954). `validation.sh`
asserts both numbers. I think that is what the brief meant, since
"plus text B's" doesn't say one. But if the blind checkpoint counts
`<sid>` as 4, it will hold correct work on that count alone. The texts
are byte-verbatim, so no other count is reachable without editing B.

## The five texts against the bytes I hold (flags, not edits)

I checked each text's factual claims against what is in the request.
None of them is wrong against those bytes.

- **A.** The `bale.toml` in context still carries seed-001's
  explanatory header ("landed by session 2026-10-01-twine-seed-001…"),
  so "does hold its rationale today" is true. The re-attempt fact comes
  from seed-close-003's notes, which say the same.
- **B.** This matches seed-close-003's notes: I5 held three `<sid>` (two
  openers and the relay template), the held attempt replaced all
  three, and the checkpoint held it.
- **C.** AGENT.md §3 does say "five response shapes are possible", and
  the bailout is listed fifth. §11.4 gives `response_kind: "bailout"`.
  Accurate.
- **D.** Row 2 contains "a response to `bale apply --no-interact
  --json`" verbatim. T12 (now line 362) quotes the help text's "merge
  on PASS". The 2b-ii annotation spells `carry response` as
  `bale apply --dry-run --json` plus the apply line. All consistent.
- **E.** §5.3 reads "Over office 0.5.0's drafting-table", which is what
  E quotes as "above". One adjacent thing I left alone: **T2's ratified
  quote** (line 104) also says "the scheduler reads office 0.5.0's
  drafting-table in Arc 2". It is a verbatim quotation of the
  architect, and T5 already refines its arc, so annotating it would be
  re-litigating a quote. E corrects the claim where §5 makes it in the
  seed's own voice. Separately, the seed never uses the literal phrase
  "nisaba office", so message 12's point lands on §5.3 alone. E's
  probe facts were placed as given, as the brief allows.

## Validation

There are nine checks. `file syntax (md: utf-8, LF)` is mechanical and
unclaimed. The other eight are claimed `pass`, `claim_basis: observed`:

- **Reversal.** Deleting the five texts, each with its one blank line,
  hashes back to `74c454fb…` at 1225 lines.
- **Five placements.** Each check covers the previous paragraph's last
  line, one blank, the text byte-exact, one blank, and the end anchor,
  all present exactly once. For E, the anchor is `---` followed by
  `## 6. Open questions register`, so landing after the rule fails.
- **One id.** Five openers name this session, there is no
  `<this-sid>`, `<sid>` appears six times on five lines, and the three
  shipped command lines still carry theirs.
- **INDEX.** `T1–T14` appears once and `T1–T10` not at all. Reverting
  the token restores `2f2a73c9…`. The seed's bold-led rulings run
  T1..T14 contiguously, and the INDEX states exactly that range.

The expected texts are embedded as the brief's raw bytes, with
`<this-sid>` still literal, so you can diff them against README.md.

I ran the script on a staging copy with `apply.sh` run and
`.bale-manifest.json` in place: 9 PASS, and every claim was `[agree]`.
On the unmodified tree, all eight claimed checks failed by name, and
only file syntax passed on both. I also ran four mutations, each caught
by name:
- one byte changed in D
- an extra blank after C
- B's template `<sid>` substituted
- E moved below the `---`

I left the crafter's `--doc-assertions --index` block out. This session
adds, moves and removes no doc, and the block passes on the unmodified
tree too, so it would not test the change (TARBALL.md §7.2). Following
I2b's rule in spirit, the script asserts nothing about paths outside
the forecast. Its only write is `.validation-logs/<stamp>/`, announced
at the top. Python runs under `-B` with `PYTHONDONTWRITEBYTECODE=1`.

`model_identity` is `anthropic:claude-opus-5-5`, the model this surface
is configured with. The surface says the serving model may differ, so
read it as a self-report.

## Proposals

### Have briefs state placeholder counts as occurrences and lines

**What.** When a brief pins a count of a literal token in the landed
file, it should give the number and say whether it counts occurrences
or lines. For example: "six `<sid>` on five lines".

**Why.** This brief's "the shipped three plus text B's" resolves only
once you count B's three. If the checkpoint author counted one, the
checkpoint holds correct work. That would be the same failure as
seed-close-003's HOLD, one level up.

**Scope hints.** The planner's brief and checkpoint authoring
(PLANNER.md). No file in this repository.

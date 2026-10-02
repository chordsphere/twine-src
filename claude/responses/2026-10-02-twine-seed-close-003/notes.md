# notes.md — 2026-10-02-twine-seed-close-003

One file modified, `twine-seed.md`, inside the one-file forecast;
nothing created, nothing deleted, no other path touched. No probe, no
light block, no clarification. The budget was comfortable and nothing
was compacted. The seed I received hashed to `cabf7615…` as the brief
said, so every anchor was found by its exact line and the reversal in
`validation.sh` is anchored on the file you have.

**The session id is `-003`, not `-001`.** The brief expected
`2026-10-02-twine-seed-close-001`; the manifest says
`2026-10-02-twine-seed-close-003`, presumably because take-read-001
and carry-probe-002 took the day's first two counters. The brief says
to take the id from the manifest, so all eight annotation openers
carry `-003`. If the blind checkpoint hard-codes `-001` rather than
reading `{sid}`, it will hold correct work on that alone.

## Re-attempt after the HOLD: I5's relay template kept as a placeholder

The held attempt failed on one checkpoint probe, "the two Arc 1
annotations in 5.1 landed byte-exact in its place", while my own
validation passed. I diagnosed it from that label alone. Everything
else passed, including I1, I2a, I2b, I3, I6 and I8, which share I5's
`[<sid>: …]` openers, and the one-id outcome. So the session id and
the opener substitution are what the checkpoint expects, and I5's
placement is the same anchor logic as the others. The one thing only
I5 has is its third `<sid>`, inside a command template: "`carry
exchange` (an exchange block's own lines to `bale relay <sid> -`)".
The held attempt replaced it, as the brief's "replace each `<sid>`"
said, and its notes flagged that the result was wrong as a spec of
the verb.

**The fix.** I take the relay block reaching me as the planner's
ruling that the HOLD is a work defect (its WAIT line). On that ruling,
`<sid>` is now substituted only in the eight `[<sid>: …]` annotation
openers. I5's template keeps `<sid>` literal, so line 954 reads
"`bale relay <sid> -`", meaning the exchange's session, as the seed
already writes "`twine ask <sid> …`" and "`supersede <sid>`". This
deviates from the brief's wording, not its intent, and the
checkpoint's verdict is the evidence. Line 954 is the only change from
the held response; every line range below is unchanged. `"corrects"`
names the held response.

**Literal `<sid>` in the landed seed** is now exactly three lines, all
command placeholders: 310 and 420, which were shipped and which
insertions-only keeps, and 954 from I5. `validation.sh` asserts
exactly those three, eight openers all naming this session, and I5
byte-exact under the opener-only rule. The check that held the first
attempt would now pass and the old one would fail, so the change is
tested.

If this HOLDs again on the same label, the evidence points at the
checkpoint, not the I5 text, and the next step is to ask for that
probe's spec (PLANNER.md §5), not a third guess.

## Where each insertion landed (line numbers in the landed file)

The shipped seed is 1090 lines; the landed one is 1225, 135 lines
added: the nine texts' 126 lines plus one blank separator each. Every
text was sliced from the brief by its code block, never retyped, with
each annotation opener's `<sid>` replaced.

| text | lines | between |
|---|---|---|
| I1 | 88–92 | §2's preamble paragraph and **T1** |
| I2a | 115–123 | T3's paragraph and I2b |
| I2b | 125–132 | I2a and **T4** |
| I3 | 165–172 | T4's last paragraph ("…not in this repository.") and **T5** |
| I4 — T12, T13, T14 | 336–365 | T11's last paragraph and the `---` closing §2 (line 367) |
| I5, two annotations | 948–968 | the fourth effort-003 Arc 1 annotation and `### 5.2` |
| I6 | 1110–1115 | §8's intro paragraph and "Message 1" |
| I7 — messages 7 to 11 | 1168–1190 | Message 6's blockquote and `### How the sitting ended` |
| I8 | 1210–1225 | after effort-003's closing annotation; the file's last paragraph |

Each sits directly before its end anchor's separator, so where a
region already held annotations (T3, the Arc 1 table, the closing
paragraph) the new text follows them. I4's three rulings are bold-led
and unbracketed as the brief's text has them; I2a/I2b, I5 and I7 keep
the brief's internal blank lines.

## Other text worth your eye (flags, not edits)

- **I2a's "the rationale lives in this annotation, not in the file."**
  The event is right: the accidental `bale config init` replaced session
  0's header (take-read-001's notes, the HOLD section). But
  take-read-001's re-attempt shipped `bale.toml` back as the pinned
  bytes, and the `bale.toml` in this request still carries seed-001's
  explanatory header. So the file does hold the rationale today. A
  reader of I2a alone would think the header is gone. The annotation's
  real point, that the next wizard run will drop it again, stands.
- **I3's list of four.** "AGENT.md §3: a response tarball, a probe
  block, a light question block, a clarification response." AGENT.md
  §3 also names a bailout among tarball mode's five response shapes.
  The four is defensible, since a bailout is a response tarball with
  `response_kind: "bailout"`, but the parenthetical reads as a full
  quote of §3 and isn't one.
- **The Arc 1 table's row 2** still says a response is handed "to
  `bale apply --no-interact --json`", which T12 now rules out. I5's
  2b-ii annotation gives the replacement (dry-run, then the apply
  line), but nothing beneath the table says row 2's wording is
  superseded.

What I could check against the shipped code, I checked, and it
agrees: T13's three `--run` refusals and `confined: false`
(`twine/commands/carry.py`); T14's per-relay `to`
(`twine/shapes.py`); I3's "the kind of the last one" as `shape`
(`shapes.py`); `VERSION` at 0.2.0; and I5's TARBALL.md §5.9.2
property, that the crafter's emission and `bale relay`'s are
byte-identical. Some things are not in the request and I did not
verify them: T12's two quotes from `bale help`, the
`apply-dry-run-carry-probe.json` fixture, `_inline_lines` in bale-src,
and the verbatim wording of messages 9 and 10. I am not claiming they
are wrong.

## Validation

There are twelve checks. `file syntax (md: utf-8, LF)` is mechanical
and unclaimed. The other eleven are claimed `pass`, `claim_basis:
observed`:

- **Reversal.** It deletes the nine blocks plus the one blank each
  brought and hashes back to `cabf7615…`.
- **Nine placements.** Each text is byte-exact, present exactly once,
  after its start anchor, and directly followed by one blank line and
  its end anchor: I2b's first line for I2a, the `---` for I4, the end
  of file for I8.
- **One id.** Eight openers, all `[2026-10-02-twine-seed-close-003:`;
  literal `<sid>` only in the three command placeholders; no `TODO`.

The expected texts are embedded as the brief's raw bytes with `<sid>`
still literal, so you can diff them against README.md. The checker
substitutes only `[<sid>:`.

I ran the re-attempt on a staging copy with `apply.sh` run and
`.bale-manifest.json` in place: 12 PASS, every claim `[agree]`. On the
unmodified tree all eleven claimed checks fail by name, and only file
syntax passes on both. I also ran it on the held attempt's seed: I5,
the one-id check and the reversal fail there by name, and the other
eight placements pass, so the script now
distinguishes the held bytes from the fixed ones. Two mutations from
the first attempt were each caught by name: I2a and I2b swapped, and
one byte changed in T13.

Following I2b's own rule, the script asserts nothing about any other
file. It writes `.validation-logs/<stamp>/` plus a `mktemp -d` scratch
directory removed at exit, both announced at the top. Python runs
under `-B` and `PYTHONDONTWRITEBYTECODE=1`.

`model_identity` is `anthropic:claude-opus-5-5`, the model this
surface is configured with. The surface says the serving model may
differ, so read it as a self-report.

## Proposals

### Spell substitution targets differently from command placeholders

**What.** Future briefs that land seed text with a session-id
substitution should spell the target distinctly, e.g. `<this-sid>`
or "the `[<sid>:` opener", so a "replace every `<sid>`" rule can't
reach a command template's `<sid>`.

**Why.** This session's HOLD was exactly that collision. The brief's
rule and the template's meaning disagreed on one token, and it cost a
retry.

**Scope hints.** The planner's brief-authoring habit (PLANNER.md §2);
no file in this repo.

### Bring `claude/INDEX.md`'s seed entry up to date

**What.** The seed's INDEX entry still says "the sitting's rulings
T1–T10"; after effort-003 and this session it is T1–T14.

**Why.** The entry is how a session finds the rulings by drill-down,
and it now undercounts by four. It is out of this session's forecast,
so I did not touch it.

**Scope hints.** `claude/INDEX.md`, one line; any session whose
forecast holds it.

### Mark the Arc 1 table's row 2 as superseded by T12

**What.** One annotation beneath the table: row 2's "hand … a
response to `bale apply --no-interact --json`" is replaced by T12's
dry-run plus the apply line, which 2b-ii builds.

**Why.** Row 2 is the table a 2b-ii brief author reads first, and as
written it describes the auto-merging path T12 forbids.

**Scope hints.** `twine-seed.md` §5.1; the next seed session, with
the INDEX line if one session's forecast holds both.

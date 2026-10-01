# notes.md — 2026-10-01-twine-seed-001

Four files created, one deleted, all inside the whole-tree forecast.
No code. One probe (`twine-seed-sources`, pre-read), no clarification,
no light block. Budget comfortable throughout; no compaction.

## The probe, and what it established

The request's `context/` carried `.gitignore`, `SEED.md` and the
sitting's telemetry record, but not the two context tarballs the
brief's §5 said I would receive. Since the seed must be *derived* and
D1–D24 carried byte-for-byte, I could not write a line of it from
memory, so the first turn ended on a probe. You ran it; the paste was
complete (integrity trailer 672 lines, matched) once I stripped the
CRLFs the chat added. What it established, the part this response
relies on:

- `~/tedder-src/harness-seed.md`: sha256
  `9528a8411fd30253729adc4b614fb9eb68401d8c0dfb70648caaa731197e3a55`,
  23,898 bytes — **equal to the brief's §3 values**, and equal to the
  blob at `HEAD:harness-seed.md` on `fb10bd3` (2026-09-28). Working
  tree clean except the untracked `.gitignore` and `bale.toml` the
  brief already names.
- `~/nisaba-src/nisaba-seed.md`: sha256
  `16dd24473aadf69d9e0b12ce3ef5ca3d0eea73c59f092007cc29f55fb4c63d0e`,
  44,488 bytes — **equal to the brief's value**, head `f0dee6f`
  (2026-09-29), clean tree.
- Both context tarballs do exist, in `/mnt/c/Users/chord/Downloads/`
  (`context-tedder-src.tar.gz` 15,671 bytes, `context-nisaba-src.tar.gz`
  81,424 bytes, both dated 2026-09-29); they were not attached to the
  chat. The seed's header cites `context-tedder-src.tar.gz` as the
  brief asked, since the bytes I derived from are provably the same.
- `blueprints/drafting-table.md` exists (77,164 bytes); I read only
  its headings and cite it by name, per the brief.
- tedder-src's seed-reconcile `notes.md` and its checkpoint's shape
  (an embedded base64 original plus a per-entry extractor) — I
  mirrored the per-entry sha256 approach, embedding the 33 paragraph
  hashes rather than the whole file.

The decoded copies are what `validation.sh`'s baselines were computed
from. The probe output itself is chat-ephemeral; this section is its
durable record (TARBALL.md §4.5).

## Where to look at review

- **The D-entries.** `validation.sh` proves all 24 entries and the 9
  pre-existing `[2026-09-24-harness-plan-002: …]` annotations
  byte-identical to the shipped `harness-seed.md`, in order, by
  sha256 per paragraph, and that exactly one
  `[2026-10-01-twine-seed-001: …]` annotation sits last beneath each
  entry, opening with one of the five status words. I ran it on the
  staging copy with the change (all pass, every claim `[agree]`), on
  the unmodified tree (every change-testing check fails), and on a
  copy with one byte changed in D7 (the entry check fails by
  paragraph number). The annotations are wrapped at 70 columns like
  the carried ones.
- **The statuses I chose**, one line each:
  - D1 carried — own repo; the boundary makes T10 structural.
  - D2 carried — session 1's `twine bale check`.
  - D3 carried — the annotation's surface list is what session 1's
    consumption manifest pins.
  - D4 carried — the consumption manifest file is session 1's.
  - D5 **answered** — bale-side, landed in 0.4.35; nothing for twine
    to build (N1).
  - D6 carried — the §11.7 surface row travels by it.
  - D7 carried — not autonomous yet.
  - D8 **superseded** — by `twine-seed.md`, as the brief says.
  - D9 **retired** — by N4 and N6, as the brief says.
  - D10 carried — the cage is T6's canonical surface.
  - D11 carried — the include-set-on-disk runtime concern.
  - D12 carried — window management and the caching capability.
  - D13 carried — `probe` / `escalate` / `deliver` wrap bale's shapes.
  - D14 **answered** — by the exchange arc, already annotated.
  - D15 carried — session 5.
  - D16 carried — no arc claims it yet; first bites in Arc 3's cap
    and dispatch policy. The one I was least sure of: it could be
    read as "superseded by the office's house rules" (nisaba Q-6),
    but the effort *mechanisms* it names (cross-checks, retries,
    model-v-model) are twine's to run, so I kept it an input.
  - D17 carried — session 4.
  - D18 **answered** — by bale's exchange records, already annotated.
  - D19 **superseded** — by N6, as the brief says.
  - D20 carried — accounting half is twine's; rendering is the
    shell's. A one-word status can't split an entry; "carried" with
    the split in the sentence seemed more honest than "superseded".
  - D21 **answered** — Q-3 by T6, as the brief says.
  - D22 **re-read** — as the brief says.
  - D23 carried — suspension and cold resume.
  - D24 carried — as T9's lean.
- **The verbatim blocks.** The T4 and T6 blocks and the four
  messages are carried as blockquotes byte-identical to the brief.
  The six runtime concerns and the Arc 1 table are carried with the
  brief's `> ` framing stripped — the brief allows reformatting, and
  a blockquoted table in a spec reads badly. `validation.sh` asserts
  each in the form the seed carries it, computed from the brief's
  bytes. The N4 sentence and the architect's T7 sentence are
  inline and wrapped at the file's width, so they are asserted
  whitespace-collapsed (tedder's Q-7 precedent).
- **Section order** is mine: identity, rulings (T1–T10), carried
  inputs (D1–D24), the runtime, the road, open questions, what this
  is not, the sitting's words. I put the carried entries *after*
  the rulings so a reader meets twine's own decisions before the
  inputs they were made against; the brief fixed outcomes, not order.
- **Row 0's "see Q below"** in the Arc 1 table pointed at a question
  the sitting's own text raised. I left the table byte-exact and
  resolved the pointer in a sentence beneath the corrections list
  (T3 answers it).
- **`bale.toml`** carries a four-line comment above the two keys
  saying why there are only two. `tomllib` sees exactly
  `{validation: {base}, sandbox: {enabled}}` and `validation.sh`
  asserts that equality. If you want the file comment-free, that is
  a four-line deletion.
- **`claude/INDEX.md`** lists two root-level docs with `../` paths,
  since DOCS.md §2.3 makes entries relative to the INDEX's own
  directory and the seed lives at the root as the brief placed it.
  README.md sits under "Charter & product" for want of an inventory
  row — not a new category, just the nearest existing one; say so if
  you'd rather it had its own heading. The telemetry record under
  `claude/telemetry/` is bale's, not a doc, and is not listed. The
  INDEX-coherence block's coverage half reports "0 doc(s) under the
  INDEX tree" because both docs are outside `claude/`; the
  entries-resolve half is the live check.
- **`SEED.md`** is a delete, not an archive; its one line is in the
  seed's §8 (the brief's own words recorded it as the placeholder
  for the sitting), so nothing is lost.

## Brief §4, checked

Nothing in §4 was wrong as far as the probe could see: WSL2 kernel
string, `/bin/bash`, home, the presence of `git`, `sha256sum`,
`gzip`, `base64`; tedder-src head and its untracked pair; nisaba-src
head and clean tree — all as stated. I did not re-verify the
office-src or bale-install facts (the probe did not need them) and
the seed cites them as the brief gave them.

## Claims

Every session-specific assertion is claimed `pass` with
`claim_basis: observed`: `validation.sh` ran on a staging copy with
the change applied and `.bale-manifest.json` in place (all pass,
every claim `[agree]`), and on the unmodified tree (every
change-testing check fails; "no TODO" passes on both, as a constraint
assertion should). The utf-8 decode is listed in
`validation_will_run` and not claimed — mechanical, per §5.3.

`model_identity` is `anthropic:claude-fable-5.1` — the string this
surface shows as its configured model. The surface says the serving
model may differ from that line; recorded as the self-report it is.

## Proposals

### Arc 1's table: session 1 should also land the fixture pattern

**What.** When session 1's brief is written, add to its "lands"
column the fixtures directory and the fake-transport seam that T8
depends on — a `fixtures/` of recorded `bale … --json` outputs for
the surfaces the consumption manifest pins — so sessions 2 and 3
(which run `bale apply --no-interact --json` and `bale open --json`)
have something to test against without a bale install in the
sandbox.

**Why.** The table gives sessions 2 and 3 verbs to drive and says
"tests" only for session 1. Under `bale.toml`'s `[sandbox] enabled =
true` with network off, and with bale's `bin/` out of bounds by T10,
the only way those sessions' `validation.sh` can exercise the courier
is against recorded outputs — office-src's pattern, which T8 already
names. If session 1 doesn't lay that down, sessions 2 and 3 will each
invent a fixture shape, and they may run beside each other (the
brief says they are file-disjoint), so they can't agree after the
fact.

**Scope hints.** Session 1's brief, "lands" column; a `fixtures/`
layout decision is CODE.md territory and session 1 owns the layout
anyway.

### Session 3's "in-flight record" needs a home decision before it is built

**What.** Decide at the sitting that authors session 3 where twine's
in-flight session record lives (under `.bale/`-like dot state in the
packing repo? in twine's own state dir?) and whether it survives N4's
deletion test.

**Why.** The table calls it "twine's one piece of state besides
spend", but N4's test says deleting twine's state loses *spend history
and nothing else*. An in-flight record that, deleted, loses the fact
that a session is open would fail that test — unless it is derivable
from bale's registry (which already knows open sessions), in which
case it is a cache and should say so. The seed carries the row
verbatim and does not resolve this; it is a half-day decision that
should be made before session 3's worker guesses.

**Scope hints.** `twine-seed.md` §5.1 (an annotation beneath the
table), session 3's brief; nisaba-seed N4 is the constraint.

### Nisaba-seed §3.3 annotation, queued for a nisaba-src session

**What.** A nisaba-src session lands the dated annotation on
`nisaba-seed.md` §3.3 that T4 implies: the three faces, and that the
"courier and scheduler, and nothing else" sentence is read with the
runtime hosting the loop its later sentence already describes.

**Why.** The brief put it out of scope here and the seed's §4.4
records the debt; without a queued session it will be rediscovered
the next time someone reads §3.3 cold. Cheap, and it keeps the
standing rule ("the Nisaba seed wins") honest — right now the two
seeds disagree on a sentence and only this repo says so.

**Scope hints.** nisaba-src, `nisaba-seed.md` §3.3 only; one
bracketed paragraph dated by the session that lands it.

# notes.md — 2026-10-01-twine-seed-effort-003

One file modified, `twine-seed.md`, inside the one-file forecast;
nothing created, nothing deleted. No probe, no clarification, no light
block. Budget comfortable; no compaction. The seed I received hashed
to `55de078e…` as the brief said, so the reversal in `validation.sh`
is anchored on the file you have.

## Where each insertion landed (line numbers in the landed file)

The shipped seed is 934 lines; the landed one is 1090. Every shipped
line is present in order — I diffed the two and the diff has no `<`
lines, and `validation.sh` proves the same thing by deleting the ten
inserted ranges and hashing back to `55de078e…`.

| insertion | lines | anchor |
|---|---|---|
| T8 annotation | 210–214 | after T8's paragraph, before T9 |
| T9 annotation | 224–227 | after T9's paragraph, before T10 |
| **T11** (heading, the architect's words, the catalog, the closing sentence) | 240–300 | after T10, before section 2's `---` |
| D16 second annotation | 567–571 | after the seed-001 annotation, before D17 |
| **§4.5 Effort (T11, directed)** | 794–803 | after 4.4's paragraph, before section 4's `---` |
| Arc 1 table annotations, four | 848–881 | after the "Row 0's "see Q below"" paragraph, before `### 5.2` |
| TQ-1 answer | 955–959 | indented two spaces under TQ-1's bullet, before TQ-2 |
| TQ-4 | 971–978 | after TQ-3, before section 6's `---` |
| Messages 5 and 6 | 1064–1072 | after message 4's blockquote, before `### How the sitting ended` |
| closing annotation | 1086–1090 | after the "How the sitting ended" paragraph; the file's last paragraph |

T11's blockquote (lines 253–296) is the brief's §2.1 blockquote
byte-for-byte, sliced from the brief by line range rather than
retyped, so the five catalog rows and the two numbered consequences
are the sitting's bytes. The same goes for messages 5 and 6. The
opening of T11 — the bold heading through the end of the architect's
quote — is also sliced from the brief; the one sentence after the
quote is mine, in T6/T7's voice ("The shape the agent supplied and the
architect ratified, verbatim from the sitting:"), because the brief's
"Then the shape the agent supplied … (you may reformat the table's
framing, not reword a cell)" reads as an instruction to me, not as
seed text. If you wanted that sentence in the seed as written, say so
and I will re-ship.

## Wording in the brief's §2 against the seed as it stands

Nothing contradicted, two things worth your eye:

- **The seed's §2 preamble and §8 intro are now stale by accretion.**
  §2 says the rulings' sources are "two light question blocks … and
  the architect's four messages"; §8 says "Every message the architect
  typed, in order" and describes two blocks. After this session there
  are three blocks and six messages. The brief did not ask for an
  annotation beneath either paragraph and I added none — the closing
  annotation under "How the sitting ended" carries the counts. If you
  want the preamble annotated too, it is one more bracketed paragraph
  for the next seed session.
- **§5's opening sentence** ("Sessions 2, 3 and 4 of Arc 1 are
  file-disjoint and may run beside each other once session 1 has
  landed") is now qualified by the second Arc 1 annotation (rows 2 and
  3 serialize, 2 first). The annotation sits beneath the table, where
  the brief put it, not beneath that sentence; a reader of §5's first
  paragraph has to read on to find the correction. Same remedy as
  above if it bothers you.

Two placements I chose where the brief left room:

- **TQ-1's answer is indented two spaces** under its bullet, as a
  list-item paragraph with a blank line on each side. The brief points
  at `nisaba-seed.md` §8 for the form; that file was not in the
  request, so this is my reading of "indented under it". It renders as
  part of TQ-1's item and greps by the session id like every other
  annotation.
- **T11's closing sentence** says "D16 below (section 3)" rather than
  just "D16 below", since section 3 is three hundred lines on.

## Claims

Seven session-specific assertions, each claimed `pass` with
`claim_basis: observed`: I ran `validation.sh` on a staging copy with
the change applied and `.bale-manifest.json` in place (8 PASS, every
claim `[agree]`) and on the unmodified shipped tree (the six
change-testing checks fail by name; `file syntax` and `tree: every
other shipped file unchanged` pass on both, as constraint assertions
should). `file syntax (md: utf-8, no TODO)` is mechanical and
unclaimed. The script writes `.validation-logs/<stamp>/` and a
`mktemp -d` scratch directory removed at exit, both announced at the
top; python runs with `-B` and `PYTHONDONTWRITEBYTECODE=1`.

Two notes on what the script can and cannot see. "Nothing else in the
tree changed" is asserted over the files the request shipped
(`context/` minus the seed, 33 files by sha256); `claude/checkpoints/`
is tracked but not shipped, so it is outside the assertion. The
byte-exact checks on the T11 heading and the architect's words unwrap
paragraphs first (a wrapped heading is not one line), while the
catalog rows, message 5 and message 6 are compared as whole lines —
rows with the `> ` framing stripped on both sides, so the check is
framing-blind as the brief asked.

`model_identity` is `anthropic:claude-fable-5-1`, the model string
this surface is configured with; the surface says the serving model
may differ, so read it as the self-report it is.

## Proposals

### `cli-contract.md` should name the effort surface before Arc 2 cuts

**What.** When the Arc 2 sitting cuts the runtime, `cli-contract.md`
gains two verbs T11 now implies — `twine ask <sid> …` (re-warm a
finished transcript, read-only tools at most) and the `delegate`
capability's listing under `twine runtime list` with its experimental
marker — and the consumption manifest gains nothing, since neither
touches bale. The contract page should also say where the dial's
setting is read from (the office profile, TQ-4) so no adapter session
invents a `--effort` flag on twine.

**Why.** T11 makes `ask` the first twine verb whose argument is
another session's id and whose side effect is a model call; the
contract page is where sessions 2 and 3 will look for verb shapes, and
it currently knows only `commands`, `status`, `bale check`.

**Scope hints.** `claude/context/cli-contract.md`; after the Arc 2
sitting, not before — the page is session 2's to own until then
(the second Arc 1 annotation).

### Arc 2's cut should give `delegate` its own session, after the loop

**What.** When Arc 2 is cut, `delegate` is a session of its own,
sequenced after the loop and the sandbox: a child window billed to
the parent sid, a digest returned as a tool result, the same contract
on native tool use and on the text protocol.

**Why.** It is the one T11 mechanism that lives inside a worker's
turn, so it needs the loop, the sandbox and both adapters to exist
first; and it is the first capability to carry §4.1's experimental
marker, which the registry (TQ-2) must be able to express before it
lands.

**Scope hints.** The Arc 2 sitting's decomposition; §4.1, §4.5, TQ-2.

### Session 5 should reserve the effort row in the cost stream now

**What.** Row 5 (cost spine) records per-call usage by token class
per session; T11 says every effort spend is a row attributed to the
session it served. Session 5's record shape should carry a nullable
`served_sid` (or equivalent) from the start, so an `ask`, a `delegate`
child or a `compare` session can bill to the sid it served without a
schema change in Arc 2 or 3.

**Why.** T11's envelope half is the cost spine's; adding the
attribution field later means re-recording fixtures and a record
version bump.

**Scope hints.** Session 5's brief; the usage record shape; Q-6's cap
shape should read the same field.

### The seed's §2 and §8 preambles want a counting annotation

**What.** One dated annotation beneath §2's preamble and one beneath
§8's intro, each saying the counts have grown (three blocks, six
messages as of this session) and that the closing annotation under
"How the sitting ended" carries the running tally.

**Why.** Said above: both paragraphs state counts that accretion
outgrows, and the seed's convention forbids editing them.

**Scope hints.** `twine-seed.md` §2, §8; a later seed session.

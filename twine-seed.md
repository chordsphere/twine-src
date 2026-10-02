# twine — Project Seed Document

> The seed document for twine, the process layer of the Nisaba suite:
> the spec doc the project is born from, and the `amendment_target`
> for every later answer about twine — answers accrete here, as dated
> annotations and register entries, never as edits inside a ruling.
>
> Provenance: authored at twine-src session
> `2026-10-01-twine-seed-001` (session 0 of Arc 1, "the courier"),
> from the read-only sitting `2026-09-29-begin-harness-001`, twine's
> first. Derived — never rewritten from memory — from two files:
> tedder-src's `harness-seed.md` as shipped in
> `context-tedder-src.tar.gz` (sha256
> `9528a8411fd30253729adc4b614fb9eb68401d8c0dfb70648caaa731197e3a55`,
> 23,898 bytes, tedder-src head `fb10bd3`, 2026-09-28), and
> nisaba-src's `nisaba-seed.md` (sha256
> `16dd24473aadf69d9e0b12ce3ef5ca3d0eea73c59f092007cc29f55fb4c63d0e`,
> 44,488 bytes, nisaba-src head `f0dee6f`, 2026-09-29). Both hashes
> were verified against the copies this session received; section 3
> carries `harness-seed.md`'s D1–D24 byte-for-byte, and this
> session's `validation.sh` proves it with a per-entry sha256.
>
> Standing rule: `nisaba-seed.md` is the later ruling over
> `harness-seed.md`, and this seed is the later ruling over both *for
> twine*. Where this seed and the Nisaba seed disagree on the suite,
> the Nisaba seed wins and this seed is the defect.
>
> Annotation convention: a ruling or a carried entry is never edited
> in place. Status, later answers and corrections are dated,
> bracketed paragraphs beneath the entry — `[<session id>: …]` —
> wholly bracketed so each one is unambiguous where it ends, and
> greppable by the session that wrote it.

---

## 1. Identity and premise

**twine** is the process layer of Nisaba: the component that carries
what a person carries by hand today between a planner and a worker,
hosts the sessions a model runs, and — later — spawns sessions from
what the office declares. It uses bale and is never part of it (D1,
N1); it is rendered by the shell and has no face of its own (N6); it
holds no intent (N4).

**Three faces, one core** (T4): the **courier**, the **runtime**, and
the **scheduler**. One core, one command registry, one CLI (`twine`),
a JSON twin for every command, and the shell as the only renderer.
Section 2's T4 carries the framing the architect ratified, verbatim.

**The test twine is held to**, in the Nisaba seed's words (N4): "if
twine's local state were deleted, what is lost? Spend history and
nothing else." Twine's durable state is its mechanical streams —
per-call usage and cost, the in-flight state of its transition table,
its consumption manifest of the surfaces it reads, and (from Arc 2)
transcripts kept as logs. Plans, words, decisions and answers land in
the office or in the project through bale. The runtime face does not
move that line: it *hosts* intent-bearing conversations, it does not
own them.

**The layer cake** — bale carries sessions, office declares what a
session carries and holds the job's progression, twine carries and
schedules, the shell renders all three, dependencies pointing
strictly downward — is `nisaba-seed.md` §1's, and this seed points at
it rather than copying it. Twine depends on bale and on office, both
through their declared surfaces only (T10).

Doctrine this project is built under, by pointer, one home each:
the five global docs bale ships (`AGENT.md`, `TARBALL.md`, `DOCS.md`,
`CODE.md`, `PLANNER.md`) — this repo adopts them in full;
`nisaba-seed.md` §2 (N1–N10) for the suite's rulings and §5 for the
session kinds twine will host or spawn; `blueprints/drafting-table.md`
in nisaba-src for what the scheduler reads (Arc 3).

---

## 2. Rulings from the sitting

Each entry carries its status and its source. **Ratified** means the
architect said so at the sitting; **directed** means the architect
named the direction and the agent supplied the shape; **proposed**
means the agent's design, not yet ratified. Sources are the sitting's
two light question blocks (block 1 and block 2, each three questions,
each answered "as assumed") and the architect's four messages,
transported verbatim in section 8. Re-litigation goes through a
sitting, never a drive-by edit; the outcome lands here as a dated
annotation beneath the entry.

[2026-10-02-twine-seed-close-003: the sitting ran past this paragraph's counts. By its close it
had emitted five light question blocks, all answered "as assumed",
and the architect had typed eleven messages, all in section 8. T12,
T13 and T14 below come from block 4. The closing annotation under
section 8's "How the sitting ended" carries the full tally.]

**T1 — twine-src is a fresh repository; its seed is derived from
`harness-seed.md`; tedder-src is archive.** Ratified (block 1,
question [1], "as assumed"). The default as assumed, verbatim: "yes:
derive, never rewrite; tedder-src is not renamed or touched".
`~/tedder-src` stays as it is; `~/tedder-src-v0` is an earlier,
unrelated attempt (harness-seed Q-1). The Nisaba seed's Q-8 ("the
rename") is answered by this ruling: there is no rename — the seed is
derived into this repository and the old one stands as archive.

**T2 — Arc 1 is the courier.** Ratified (block 1 [2], "as assumed"):
"yes, courier first; the scheduler reads office 0.5.0's drafting-table
in Arc 2" — refined by T5, which moves the scheduler to Arc 3 and puts
the runtime in Arc 2.

**T3 — A blind checkpoint is pinned from session 1 onward.** Ratified
(block 1 [3], "as assumed"): "yes, tedder-src's pin; session 0 itself
packs before bale.toml exists, so it carries none". This session is
session 0: it lands the pin (`bale.toml`'s `[validation] base =
"claude/checkpoints/{sid}.sh"`) and is not graded by one. Every
session from 1 onward is.

[2026-10-02-twine-seed-close-003: why `bale.toml` holds exactly two keys, recorded here because
the file cannot keep it: `[validation] base` is this ruling's pin, and
`[sandbox] enabled = true` confines every `validation.sh` and blind
checkpoint; `network` is left unset because absent means off, the
floor T8 keeps twine's own tests under; packer identity is the global
`user/bale.toml`'s. `bale config init` rewrites the file from its
walked surface and drops comments — an accidental run on 2026-10-02
replaced session 0's explanatory header — so the rationale lives in
this annotation, not in the file.]

[2026-10-02-twine-seed-close-003: checkpoint authoring, learned at session
`2026-10-02-twine-take-read-001`'s HOLD: a blind checkpoint pins bytes
only inside the session's write forecast. Paths outside it are
guarded by bale's own forecast gate, which refuses any change there
that the operator does not admit; a pinned hash on such a path adds
no protection and turns operator drift into a HOLD of correct work —
that HOLD was the accidental `bale config init` above, not the
worker. Checkpoints authored after it follow this rule.]

**T4 — twine has three faces, one core: courier, runtime,
scheduler.** Ratified (block 2 [1], "as assumed"): "yes; the runtime
hosts both worker sessions and sittings, and N4 stands unchanged".
The agent's framing the architect ratified, verbatim from the
sitting:

> **Courier** — moves bale's four shapes between planner and worker,
> and applies/relays/runs them. Model-agnostic by construction,
> because the shapes are text and TARBALL §4.6 already says "same
> contract, whoever carries it."
> **Runtime** — *hosts* a session: the model-call loop, the tool
> surface, the per-sid sandbox, window accounting, the cost spine
> and kill-switch, and the adapter that makes a given model able to
> do all of that. It hosts worker sessions (unattended, end in a
> shape) and — per D22-as-re-read and Q-1 — sittings (attended,
> conversational, emit bundles).
> **Scheduler** — reads the drafting-table, opens bundles, dispatches
> to the runtime or to a person, enforces the cap.
> N4 survives untouched: the runtime hosts intent-bearing
> conversations, it doesn't own them. Delete twine's state and you
> lose spend history and transcripts-as-logs; every word that
> mattered landed through bale or in the office.

This departs from `nisaba-seed.md` §3.3's opening sentence ("The
courier and the scheduler, and nothing else.") and agrees with its
later sentence ("It holds every bale verb and executes the agent loop
as operator"): the runtime face is where that loop lives. The dated
annotation that records this departure on `nisaba-seed.md` §3.3 is a
nisaba-src session's to land, not this one's — that repository is not
in this session's forecast and not in this repository.

[2026-10-02-twine-seed-close-003: the courier's "four shapes" are the shapes a worker's turn
ends in (AGENT.md §3: a response tarball, a probe block, a light
question block, a clarification response). The courier carries more
than turn endings, so `twine take` reads five kinds of block — probe,
probe output, light, exchange, relay — and reports as the turn's
`shape` the kind of the last one. The dated annotation on
`nisaba-seed.md` §3.3 recording the three faces was authored at this
sitting's close as a nisaba-src session.]

**T5 — The arcs run courier, then runtime, then scheduler.** Ratified
(block 2 [2], "as assumed"): "yes; the scheduler moves from nisaba's
step 6 to Arc 3". The departure from `nisaba-seed.md` §10 step 6's
order ("the courier first … then the scheduler over the
drafting-table") is deliberate, and the reason is recorded: "a
scheduler before a runtime would only have a person to dispatch to."

**T6 — Tool calling: one small canonical tool surface, an adapter
boundary that abstracts it two ways (native tool use, or a strict
text tool protocol), Anthropic then OpenAI-compatible as the two Arc 2
adapters.** Ratified (block 2 [3], "as assumed"): "yes, as described
above". The description, verbatim from the sitting:

> 1. **One small canonical tool surface, twine's own.** The worker's
>    cage tools — `shell`, `read_file`, `write_file`, `list_dir` —
>    plus the bale-native wrappers D13 demands: `probe` (runs the
>    block against the real repo read-only and returns the paste,
>    closing the hop), `escalate` (emits a clarification response or
>    a light block and suspends the worker), `deliver` (hands the
>    response tarball to the courier). Seven-ish tools, deliberately.
>    A big tool set is exactly what weaker models mangle.
> 2. **An adapter boundary that abstracts tool calling two ways.**
>    Where the provider has native tool use (Anthropic `tool_use`;
>    OpenAI-style function calling, which covers vLLM, Ollama,
>    llama.cpp and most open servers), the adapter translates the
>    canonical schema and the result blocks. Where it doesn't, the
>    adapter falls back to a **text tool protocol**: the model emits
>    one sentinel-bracketed block per call (bale's probe-block style
>    — sentinels, one call, an integrity trailer), twine parses it
>    strictly, and returns the result as the next user turn. Same
>    loop, same tools, same transition table; only the adapter knows
>    which path it's on. A strict parser plus D17's
>    `malformed_response` move is what makes a weak model safe rather
>    than merely possible.
> 3. **Two adapters in Arc 2, not one.** Anthropic first (it's where
>    everything is proven), OpenAI-compatible second — that one
>    adapter is the whole open-source story at rung 1. Q-3's contract
>    gets designed once, against two implementations, which is the
>    only way to know the boundary is real.

The text tool protocol is twine's wire *inside* a worker session; it
never crosses the courier boundary and is not a bale shape (N1: bale
is unchanged).

**T7 — Runtime capabilities are a managed, editable registry; the
runtime is also the architect's research surface.** Directed (message
4, section 8). The architect's words, verbatim: "tool calls aren't the
only thing that an open weight api model would be missing, and I want
the ability to add or customize new runtime operations. Honestly, I'm
interested in developing my own runtime anyway for research reasons,
and would like this to be the place I do that. So when we're
developing the runtime phase, let's keep that in mind that I'd like
the ability to manage and easily edit the different run time
capabilities". The shape the agent supplies — directed, not ratified
— is section 4's: the runtime applies N5's registry rule to itself,
every runtime operation is a named capability with a declared
contract, and the Anthropic path stays the ground truth the research
path is measured against.

**T8 — twine's own tests never reach a model API.** Proposed by the
agent at the sitting, not yet ratified; the architect did not object.
The reason: twine's sessions run through bale, and `bale apply` runs
`validation.sh` confined with the network off (this repo's
`bale.toml` leaves `[sandbox] network` unset, which is off), so the
online adapter gets a fake transport from day one and the cost spine
is tested against recorded usage fixtures. office-src already works
this way (`claude/fixtures/bale-0.4.45/*.json` are recorded `--json`
outputs; probe-verified 2026-10-01). Twine mirrors the pattern, not
the code.

[2026-10-01-twine-seed-effort-003: the fixtures layout landed in
session 1 (`2026-10-01-twine-core-002`) as the ruling the sitting
accepted from session 0's Proposals, and the fake-transport seam was
deferred to Arc 2 and to session 5, where the first API-shaped call
exists to fake.]

**T9 — Stack lean.** Proposed: Python 3.10+, stdlib for the core
(courier, registry, transition table, cost spine); the `anthropic`
SDK as an optional extra used only inside the Anthropic adapter,
installed in a project venv (the machine's `python3` is the Ubuntu
system 3.12.3 with pip 24 — a system install is not the path). D24
held the same lean loosely; it stays mechanism territory, and session
1 may deviate with a flag in its `notes.md`.

[2026-10-01-twine-seed-effort-003: the Python floor is **3.11**, not
3.10 — the consumption manifest's parser is `tomllib` (3.11+), and
`bin/twine` refuses an older interpreter with one stderr line and
exit 2; ratified at the sitting from session 1's `notes.md`.]

**T10 — twine imports nothing from bale, office or tedder.** Carried
from D1 and from the Nisaba seed's layer cake, not new; stated once
here so no session improvises an import. Twine drives bale through
its non-interactive paths (`--json`, `--no-interact`, bundles,
pre-answered intents, the admission flags — the surface Arc 1 session
1's consumption manifest pins; semantics are `bale help`'s, not this
seed's) and reads office's *declarations* (`share/verbs.toml`'s
`lands` / `attended` / `trigger` columns, the drafting-table pages) —
never `lib/office_bale.py`, never bale's `bin/`, never anything under
`~/tedder-src`.

**T11 — Effort is envelope × policy × mechanisms; twine owns the
envelope and the mechanisms, the office holds the policy.** Directed
(message 5, section 8; ratified as assumed at light block 3 [1],
message 6). The architect's words, verbatim: "In my original draft
for the harness, I said that an "effort dial" would be really useful.
Not like claude's effort toggle, but what it would do is things like
run workers twice and compare, spawn reflection sessions to refine
context, ask old workers questions after the fact, sessions spawned
for subtasks like reading or tools to preserve main context etc.
Things that would just increase time and compute but would produce
refined answers." The shape the agent supplied and the architect
ratified, verbatim from the sitting:

> **Envelope** — a budget: how much more than the baseline a session
> may cost. That's the cost spine's (Arc 1 session 5): every effort
> spend is a row in the cost stream attributed to the session it
> served, so you can always answer "what did turning the dial up cost
> me" from twine's own stream.
>
> **Policy** — which mechanisms to spend on, for which work class, at
> which dial setting. Under N4 twine holds no intent, so the dial's
> *setting* is a declaration twine reads, not a knob twine owns: a
> house rule in the office (nisaba Q-6 already puts trust grants
> there, and effort is the same kind of policy — "code work in
> project X runs at effort 3"). The trust ledger later moves it per
> class; at rung 1 you set it.
>
> **Mechanisms** — the things that actually spend the budget. Each
> one is either a session kind (nisaba §5's table, which already
> demands a declared landing per kind) or a runtime capability (T7).
> None of them needs a change to bale:
>
> | mechanism | what it is | face / arc | the durable artifact it must leave (§9: or it's wasted) |
> |---|---|---|---|
> | **run twice and compare** | the same request tarball dispatched to k workers; each candidate response gets `bale apply --dry-run` (the read-only validation half) for a mechanical verdict; a **compare** session reads the k diffs + notes and picks or merges; twine applies the winner. Bale already allows k candidates for one sid — only one ever merges | scheduler, Arc 3; the compare session is nisaba's `check` kind generalised | the verdict as a claims block, plus the losers' dry-run verdicts in twine's stream (calibration data bale never sees) |
> | **reflection to refine context** | before a build: a read-only session that reads the brief and includes and returns a revised brief and include set — PLANNER.md §2's "worker-authored brief on request", scheduled rather than asked for. After a build: reading notes + telemetry for the next session's brief — which is what office's `cleanup`/`digest` already are | scheduler, Arc 3 (`reflect`, a new kind: lands a brief revision) | the revised brief, versioned (derive-don't-rewrite applies) |
> | **ask an old worker** | re-warm a finished worker's transcript (D12's append-only prefix makes this cheap), append a question, get an answer with read-only tools at most | runtime, Arc 2 (`twine ask <sid> …`) | the Q/A in twine's log, and in the asker's record (a sitting's notepad) — this is the manual path's "go back to the old chat tab" |
> | **subtask sessions to preserve context** | a `delegate` tool on the canonical surface: the worker hands a bounded task (read this 12k-line file and answer X; run this tool-heavy exploration) to a child with its own window, gets a digest back; children are runtime-internal, not bale sessions — they land nothing and bill to the parent sid | runtime, Arc 2 (a capability, and the first one that earns T7's "experimental" marker) | the digest in the parent's transcript; nothing else by design — it's context hygiene |
> | **retry**, **model-v-model** | D16's own: a second attempt, or two models debating a design question in a read-only session | scheduler, Arc 3 | the `corrects:` lineage / the sitting's record |
>
> Two consequences worth naming now rather than in Arc 2:
>
> 1. **"Ask an old worker" changes TQ-1.** I recommended transcripts
>    as disposable logs. If re-asking a worker is an effort mechanism,
>    a transcript is worth keeping durably, append-only, for as long
>    as the project wants the option. N4 still holds in its own words
>    — deleting twine's state loses *the ability to re-ask*, not
>    anything of record, because everything that mattered landed
>    through bale — but the recommendation flips to "durable, with
>    retention a house rule."
> 2. **`delegate` is where your research runtime starts paying.** It's
>    the one mechanism that lives inside a worker's turn, so it's a
>    capability with the same contract across adapters: a weak model
>    that can't do tool calls natively still gets delegation through
>    the text protocol. It also doesn't bend AGENT.md §11's
>    single-window premise — the parent still finishes in one window;
>    children spend their own.

§4.5 is the runtime's pointer to this ruling; the policy's home and
the dial's scale are TQ-4; and D16 below (section 3) carries this
placement as its annotation.

**T12 — twine never merges at rung 1.** Ratified (light block 4 [1],
"as assumed"): "yes; merging through twine waits for a PLANNER.md 18
trust grant you make deliberately". bale's own help text is why:
`bale apply --no-interact` makes "the walkthrough take its default
action (merge on PASS; …)". So the courier's response hand-off runs
`bale apply --dry-run --json` — which "Requires an open session …
no branch is created, nothing is staged into the worktree, nothing
is committed" — and hands the operator the exact `bale apply` line
to run. Final-merge review stays the architect's (PLANNER.md §10,
control 3).

**T13 — A probe runs only on the operator's explicit consent, and
unconfined until Arc 2.** Ratified (light block 4 [2], "as
assumed"): "yes; take shows the script and runs it only on --run,
exactly like you reading and pasting today". Landed as `twine carry
probe` (session `2026-10-02-twine-carry-probe-002`): without `--run`
nothing executes; `--run` refuses an unfilled crafter scaffold, a
header without a `# Read-only:` line and an ambiguous block choice;
every result reports `confined: false` until Arc 2's sandbox makes it
true.

**T14 — A relay block addressed to the planner never reaches a
worker.** Ratified (light block 4 [3], "as assumed"): "yes; the
to-planner block carries checkpoint output, and fixtures ship to every
future worker". On a HOLD, bale's relay block to planner inlines the
blind checkpoint's output; delivered to a worker, or landed as a
fixture (fixtures ship in every request), it would teach workers their
grader (TARBALL.md §7). `twine take` reports each relay block's
addressee as `to`; every router twine grows enforces this rule, and
only to-worker blocks may become fixtures.

---

## 3. Carried inputs — harness-seed.md D1–D24

The twenty-four ratified decisions of tedder-src's `harness-seed.md`
§2 are carried below byte-for-byte, each entry paragraph and every
dated `[2026-09-24-harness-plan-002: …]` annotation already beneath
it, in order and unchanged. They are **inputs** to this seed, not
contracts over it (the Nisaba seed's standing rule). Beneath each
entry, after its existing annotations, this session adds exactly one
dated status annotation in the same bracketed form, opening with one
of five words: **carried** (still an input twine builds to),
**retired** (no longer applies, with the ruling that retired it),
**re-read** (the words stand, the reading changed), **superseded**
(replaced by a named successor), or **answered** (the question the
entry posed has an answer, and where). Where the entry says "the
harness" or "tedder", read "twine".

**D1 — Separate repository.** The harness lives in its own repo,
not in bale-src. Grounds: dependency-profile divergence (SDK,
async runtime, frontend vs. bale's zero-dependency posture),
release-cadence divergence, and — decisive — the repo boundary
makes ADR-0012's "separate runner that uses bale" structural
rather than disciplinary: importing bale internals as a library
becomes physically unavailable, so the harness path can never
silently diverge from the manual path it must mirror.

[2026-10-01-twine-seed-001: carried — twine-src is its own repository
(T1), and the repo boundary is what makes T10's no-import rule
structural rather than disciplinary.]

**D2 — Bale-version pinning.** The harness pins a bale version and
refuses to drive a bale whose `bin/VERSION` mismatches the pin.
Upgrades are deliberate events at arc boundaries — bump the pin,
run the replay suite, fix, ratify — never ambient. Pre-1.0 bale is
allowed to break its machine-readable surfaces; the pin is what
contains that churn.

[2026-10-01-twine-seed-001: carried — Arc 1 session 1 lands `twine
bale check`, the pin against the installed `bin/VERSION`.]

**D3 — Narrowest consumption surface.** Rung 1 consumes the
minimum bale surface that works: exit codes, the
one-stdout-JSON-line discipline, an allowlisted key set, the
bundle format, the landed schemas. Every key the harness doesn't
read is a key bale can change for free.

[2026-09-24-harness-plan-002: the surface has grown since the seed;
what rung 1 can consume, all of it in bale 0.4.45 and all of it
exercised on the manual path: the planner **bundle**
(`schemas/bundle-manifest.schema.json`, shipped with every install)
and **`bale open`**, which consumes one; open's rehearsal modes
**`--check`** and **`--dry-run`**; **pre-answered intents** carried
in a bundle (today one prompt: `supersede <sid>`); one-line
**`--json`** reports; and **`--no-interact`** on apply. One rule
from that surface shapes Arc 2: every non-TTY path declines the
apply-time admission prompts — bale's own words, "an orchestrator
never admits" — so when a worker ships an out-of-forecast path,
tedder surfaces the refusal's remedy line to the architect (the
rung-1 master, D22) rather than admitting on its own.]

[2026-10-01-twine-seed-001: carried — the surface the annotation
enumerates is what Arc 1 session 1's consumption manifest pins; flag
semantics stay `bale help`'s.]

**D4 — Consumption manifest, harness-side.** The harness maintains
a manifest of exactly which bale surfaces it reads, beside its
pin. The upgrade briefing at pin-bump is mechanical: diff the
manifest against bale's changelog since the pinned version. The
manifest plus the pin-bump friction record is the 1.0 evidence
corpus, hosted where it belongs.

[2026-10-01-twine-seed-001: carried — the consumption manifest file is
Arc 1 session 1's, beside the pin.]

**D5 — Changelog in bale-src, loose schema.** Bale gains a
changelog record family for surface-affecting changes:
schema'd loosely per the existing record conventions
(`record_version`, additive/legacy-tolerant), written by the same
response that lands the surface change, with a validator row
making omission loud. Ratified over a prose-only alternative on
the architect's grounds: prose sprawls, especially from weaker
models, and the consumer is a Claude session whichever project it
serves. Bale-first justification stands independently: a tool
walking a version ladder toward contracts-become-promises needs
its breaking changes durable and travel-ready. Architect's
standing constraint, verbatim: "Anything we add for bale needs to
be primarily for bale's benefit."

[2026-09-24-harness-plan-002: landed. The changelog record family
shipped in bale 0.4.35 (session
`2026-09-17-board-56-57-changelog-aborted-002`): schema
`changelog-record`, one record per version under bale-src's
`claude/changelog/<version>.json`; records 0.4.35 through 0.4.45
exist. D4's pin-bump diff has its source.]

[2026-10-01-twine-seed-001: answered — the changelog family landed in
bale 0.4.35 (its annotation), so D4's pin-bump diff has its source and
twine owes bale nothing here (N1).]

**D6 — Cross-repo procedure is board 9 Level 1.** Coordinated
bale↔harness changes run as linked sessions: shared link id, one
interface-contract brief into both requests, the seam named.
Level 2 (cross-repo `depends_on`) as needed; Level 3 stays
deferred. The pin removes same-window races: the harness never
sees bale changes until a deliberate pin-bump, so the registry's
inability to span repos costs nothing at rung 1.

[2026-10-01-twine-seed-001: carried — the one bale-side obligation
this seed records, the `AGENT.md` §11.7 surface row (§4.4), travels by
this procedure.]

**D7 — Autonomy sequencing unchanged.** Board 45 (the
hostile-foreign-repo arc) remains sequenced before any harness
**autonomy**. It does not gate harness existence or the supervised
rungs. Recursion depth is earned last, per the S6 charter.

[2026-10-01-twine-seed-001: carried — autonomy stays sequenced behind
board 45; twine is not autonomous yet (§7).]

**D8 — This seed doc is the project spec's home.** MASTER.md stays
bale's; the board-10 row points here. The escalation contract's
`amendment_target` for harness-era questions is this file: answers
accrete here, mechanically, per PLANNER.md §15.

[2026-10-01-twine-seed-001: superseded — the project spec's home and
`amendment_target` for twine is `twine-seed.md`, this file;
`harness-seed.md` stands as tedder-src's archive (T1).]

**D9 — Component shape.** A locally run web application (local
first; hosting is a later question). Chat mode is the default
face: a custom UI for conversing with Claude, model selection, and
every API-tweakable parameter surfaced as a control or options
panel. Orchestrated mode is opt-in ("agentic spawning"),
activating the bale-tree dashboard.

[2026-10-01-twine-seed-001: retired — by N4 (twine holds no intent and
has no chat of its own; the chat is a hosted office session) and N6
(the face is the shell's).]

**D10 — Worker execution model: tool-access only.** Text-only
workers are dropped entirely, ratified. Workers run as sandboxed
tool-access sessions — the shape of today's proven-by-hand worker,
which is the parity the ground-truth doctrine requires. The cage
is the landed substrate: `run_confined`, the network-grant config,
ADR-0016's network-off / FS-confined-to-staging doctrine. Minimal
tool surface: shell plus file I/O in a per-sid sandbox home. The
worker never holds tools that touch bale verbs or oracles — the
division of labor enforced by tool absence. The harness holds
every bale verb and executes the agent loop as operator.

[2026-10-01-twine-seed-001: carried — the cage is T6's canonical tool
surface (`shell`, `read_file`, `write_file`, `list_dir`) in a per-sid
sandbox home, with the runtime holding every bale verb (§4.2, §4.3).]

**D11 — Injection model: lazy reading.** The include set sits on
disk in the worker's sandbox; AGENT.md's INDEX drives partial
reads — today's economics preserved, improved by prompt caching.
This resolves board 10's injection-model decision on the side its
own annotation predicted; the board annotation rides the deltas
session.

[2026-10-01-twine-seed-001: carried — the include set on disk and a
model-agnostic system prompt holding only the tool definitions and the
surface note is the third runtime concern (§4.3).]

**D12 — Caching discipline as a design constraint.** Append-only,
stable conversation prefixes; docs and tool definitions pinned at
spawn; per-worker model and thinking settings are spawn-time
constants, never mid-session knobs (changing thinking settings
invalidates message cache). Cache-read/write token classes are
first-class rows in the cost accounting.

[2026-10-01-twine-seed-001: carried — append-only prefixes are why
twine never compacts silently and counts instead (§4.3, window
management); prompt caching is a capability (§4.1).]

**D13 — Bale-native tools wrap, never fork.** Harness-defined
worker tools that touch protocol flows emit bale's ratified wire
shapes: an `escalate` tool emits a schema-valid escalation record
and suspends the worker rather than ending the session; a `probe`
tool closes the paste-back hop the board already annotates as the
first flow the transport replaces. The shapes stay bale's and stay
manual-path-exercisable. This is the session-interaction
mechanization mandate and the clarification-relay subsumption
item, discharged by construction.

[2026-09-24-harness-plan-002: the worker↔planner question channel
was mechanized inside bale after this seed was written (ADR-0017,
bale 0.4.18–0.4.19), and the architect ruled at the 2026-08-29
sitting that this leg belongs to bale, not the harness. Bale's
shapes, per TARBALL.md §5.9–§5.10 and PLANNER.md §15: a worker's
blocking question is a **clarification response**; each round of
the thread travels as an **exchange record**, recorded and rendered
by **`bale relay`**; a short non-blocking set (at most three) is a
**light question block** in chat. So the `escalate` tool here emits
the worker's clarification response — or a light block, admitted by
count — and tedder carries it through `bale relay`; the tool wraps
bale's shapes, as this entry already demands. The **escalation
record** is the master→architect leg only: a planner that is itself
a session escalating upward.]

[2026-10-01-twine-seed-001: carried — `probe`, `escalate` and
`deliver` are the wrappers T6 names, and per the annotation `escalate`
emits bale's clarification response or light block, never a fork.]

**D14 — The escalation producer.** The harness is the producer the
S4 schemas landed ahead of. Real-time questions surface on a
dedicated tab; priority classes per PLANNER.md §15 (only blockers
interrupt; the rest batch); every question arrives
options-plus-recommendation so "your recommendation is correct" is
the cheapest answer; dedup with fan-out via `subsumes`; answers
accrete to this file via `amendment_target`. Email delivery of the
batched class is a later-rung notification transport (open
question Q-5).

[2026-09-24-harness-plan-002: at rung 1 the architect is the master
(D22), so there is no master→architect leg yet and nothing produces
an escalation record. The questions tab renders what bale emits —
exchange records (the clarification thread's rounds) and light
question blocks; the escalation-record producer arrives with the
first agent master. See D13's annotation for the shapes.]

[2026-10-01-twine-seed-001: answered — by bale's exchange arc, as the
annotation already records: at rung 1 nothing produces an escalation
record, and the questions surface is the shell's inbox (N6) rendering
what bale emits.]

**D15 — Cost spine and kill-switch are arc-1 foundations** (the
architect's caveat, ratified last): full spend visibility — a
running total aggregated from per-call usage, split by token class
including cache reads/writes and thinking — and a reliable
kill-switch ship in chat mode, before any orchestration exists.
The hard cap refuses loudly, never degrades silently; a mid-arc
cap breach has bailout semantics (stop spawning, in-flight workers
hand off, validated work commits, resumption plan delivered). The
kill-switch is process-level — it must work when the harness
itself is wedged — and a kill leaves a durable `aborted`-class
closure record, never a mystery. Architect's words, verbatim:
"every session spawn should come with a foolproof kill-switch and
running total of the money used through the api, including a hard
cap for budget reasons."

[2026-09-24-harness-plan-002: the `aborted` closure reason landed
in bale 0.4.35, in the same session as D5's changelog family
(`2026-09-17-board-56-57-changelog-aborted-002`). The kill's
durable closure record has its vocabulary.]

[2026-10-01-twine-seed-001: carried — Arc 1 session 5 lands the cost
spine and the two-layer kill-switch against fixtures, before any
online call exists (T8).]

**D16 — Effort is envelope × policy.** The effort slider sets the
budget envelope; ledger-driven policy allocates within it, per
work class (PLANNER.md §17: effort is not uniform, and not a
vibe). Named effort mechanisms the policy can spend on:
cross-checking sessions (an independent session grading work it
didn't build — the blind-stream shape at a new altitude), retries,
model-v-model discussion sessions.

[2026-10-01-twine-seed-001: carried — still an input with no arc
claiming it yet; the first place it bites is the scheduler's cap and
dispatch policy (Arc 3), and the Nisaba seed's Q-6 puts the policy in
the office's house rules.]

[2026-10-01-twine-seed-effort-003: carried — T11 places it: the
envelope is the cost spine's (Arc 1 session 5), the policy is an
office house rule twine reads (TQ-4), and the mechanisms are the
runtime's (`ask`, `delegate`, Arc 2) and the scheduler's (`compare`,
`reflect`, retry, model-v-model, Arc 3).]

**D17 — Total transition function.** Every worker outcome in the
closed, fixture-pinned vocabulary (applied, HOLD, drift-refused,
rejected, clarification, bailout, crash, silence/timeout,
aborted, …) has a defined harness move; no default case. The two
non-obvious edges, ratified: a well-formed HOLD gets revert and
repack with the failure context shipped and `corrects:` lineage; a
**malformed** response gets respawn from the original request with
a master-authored failure note — never the failed worker's
self-account (the self-oracle constraint one level up). Silence
gets timeouts and a `no_response` closure record. Architect's
requirement, verbatim: "there shouldn't be any surprises, and
every path taken should have a defined response."

[2026-09-24-harness-plan-002: the silence and malformed edges have
their closure reasons in bale — `no_response` and
`malformed_response`, landed in bale 0.4.6.]

[2026-09-24-harness-plan-002: the transition table keys on what
bale actually emits, plus tedder's own third set. Verbatim from
bale 0.4.45's telemetry schema — outcomes (13): `opened`,
`applied`, `held`, `reverted`, `rejected`, `bailout`,
`scope-drift-refused`, `required-check-refused`,
`base-drift-refused`, `unlocked`, `rolled-back`, `re-applied`,
`relay-refused`; closure reasons (9): `abandoned`,
`superseded-by-split`, `reframed-after-clarification`,
`master-closeout`, `crash-debris`, `closed-read-only`,
`no_response`, `malformed_response`, `aborted`. Beside those,
tedder owns the API-side ways a worker turn stops. Two the list
above misses, each needing a defined move: a **model refusal** —
live specimen: the 45 arc's seed session sat 1 h 41 min from pack
to abandon because the worker surface's safety classifier refused
the brief's wording (reworded, it landed in 46 min); and
**context-window exhaustion** — API calls do not auto-compact, and
D12's append-only prefixes mean nothing compacts unless tedder
builds it, so reaching the window's edge is an outcome, not a
background event (AGENT.md §11's bail-before-the-wall discipline
is the doctrine it maps to). The exact API stop-reason names are
to be verified against the SDK when the loop is built; none are
named here from memory.]

[2026-10-01-twine-seed-001: carried — Arc 1 session 4 lands the table
as data over bale 0.4.45's 13 outcomes and 9 closure reasons plus
twine's API-side stop set, with the provider axis §4.3 names; a test
fails by name on any outcome without a move.]

**D18 — Discussion paths are artifact rounds.** Master↔child
clarification is structured records out and answer records in —
durable, accreting — rendered as fluidly as chat in the UI without
ever being raw chat. "An answer that lives only in a chat is not
accreted."

[2026-09-24-harness-plan-002: the "artifact rounds" here are now
exactly bale's exchange records (TARBALL.md §5.9.2) — one schema
for both directions, each round recorded by `bale relay`. See D13's
annotation.]

[2026-10-01-twine-seed-001: answered — by bale's exchange records, as
the annotation already records; twine relays rounds through `bale
relay` (Arc 1 session 2) and adds no record of its own.]

**D19 — Dashboard renders, never owns.** The bale-tree, the cost
ticker, and every visibility surface render bale's own records
(registry, lineage, telemetry, stats) and the harness's mechanical
streams; everything on screen stays derivable by hand.

[2026-10-01-twine-seed-001: superseded — by N6: the bale-tree, the
cost ticker and every visibility surface are the shell's, rendering
twine's mechanical streams and bale's records; twine keeps a JSON
surface and no rendering.]

**D20 — Thinking visibility.** Extended thinking enabled
per-worker with a spawn-time budget; thinking blocks streamed and
rendered expandably, per worker, on the dashboard and in chat
mode. Thinking tokens bill as output and cached thinking reads
count as input — both accounted in the cost spine.

[2026-10-01-twine-seed-001: carried — the accounting half (thinking
bills as output, cached thinking reads as input) is the cost spine's
and streaming-with-thinking is a runtime capability (§4.1); the
rendering half is the shell's (N6).]

**D21 — Models.** Anthropic-catered, per-spawn model selection.
Open-source models are supported through an adapter boundary
designed at rung 1 even though only the Anthropic adapter ships
behind it initially.

[2026-09-24-harness-plan-002: tedder's API workers are a new
surface for AGENT.md §11.7's surface table, which today has one
row, claude.ai. On this surface the model string is exact from the
API, so a worker's `model_identity` needs no picker-name guesswork;
the window-edge behavior is whatever tedder defines (D17's second
annotation: exhaustion is an outcome with a move, not a background
event). The row itself is a bale-src doc change: tedder owes
bale-src that row via D6 once Arc 1's loop exists.]

[2026-10-01-twine-seed-001: answered — Q-3's adapter boundary is T6's:
one canonical tool surface, native tool use or the text tool protocol
behind it, Anthropic then OpenAI-compatible in Arc 2; the surface row
the annotation names is §4.4's obligation.]

**D22 — Rung-1 master is the architect.** The harness chat is the
planning desk; the harness executes the mechanics the architect
would otherwise hand-run. The first agent master is a deliberate
§18 trust grant with a ledger behind it, not a launch feature.

[2026-10-01-twine-seed-001: re-read — "a sitting is an office session
twine hosts": the runtime hosts the planning desk and holds none of
its intent (N4, the Nisaba seed's Q-1), and the rung-1 master is still
the architect.]

**D23 — Suspended workers go cold at rung 1.** A worker blocked on
an escalation lets its cache expire and re-warms on resume; the
re-warm cost is a named telemetry field. Holding hot on the
extended-cache tier is a later policy knob for blocking-priority
questions, owned by the effort machinery — measure before
optimizing.

[2026-10-01-twine-seed-001: carried — suspension and cold resume is
the fourth runtime concern (§4.3): a worker blocked on a clarification
has its transcript persisted append-only and re-warms on the answer.]

**D24 — Stack lean: Python backend, thin web frontend.** Held
loosely as mechanism-authority territory: same language as bale,
official SDK, bale internals readable by harness sessions without
a language hop. The first worker session may flag a reasoned
deviation per the standing flagged-deviation-plus-ratification
loop.

[2026-10-01-twine-seed-001: carried — as T9's lean, held loosely:
Python 3.10+ and stdlib for the core, the `anthropic` SDK as an
optional extra inside its adapter; session 1 may deviate with a flag
in its `notes.md`.]

---

## 4. The runtime

The runtime is the face that *hosts* a session: the model-call loop,
the tool surface, the per-sid sandbox, window accounting, the cost
spine and kill-switch, and the adapter that makes a given model able
to do all of that (T4). It hosts worker sessions — unattended, ending
in one of bale's four shapes — and, per D22-as-re-read and the Nisaba
seed's Q-1, sittings — attended, conversational, emitting bundles.
Arc 2 builds it; what follows is what Arc 2 builds to, so that no Arc
2 session improvises it.

### 4.1 Capabilities (T7, directed)

The runtime applies N5's rule to itself. Every runtime operation —
tool calling (native or text protocol), thinking, prompt caching,
window accounting, streaming, sandboxing, suspension and resume, usage
accounting — is a **capability**: a named unit with a declared
contract, a default implementation, and per-adapter overrides, living
one-per-file in one directory so it can be read, replaced or added
without touching the loop. The loop composes capabilities; an adapter
is a chosen set of them. `twine runtime list` and `twine runtime show
<capability>` render the registry (CLI first, JSON twin, the shell
renders it later). The same rule as the command registry: no
capability without its declaration; a capability marked experimental
is listed, never silently absent. Where the architect's own runtime
work diverges from the Anthropic path, the Anthropic path stays the
ground truth the research path is measured against — the manual-path
doctrine, one level down. The registry's file shape is TQ-2.

### 4.2 Tool calling (T6, ratified)

One small canonical tool surface, twine's own: the worker's cage
tools — `shell`, `read_file`, `write_file`, `list_dir` — plus the
bale-native wrappers D13 demands: `probe`, `escalate`, `deliver`.
Seven-ish tools, deliberately. An adapter boundary abstracts tool
calling two ways: native tool use where the provider has it
(Anthropic `tool_use`; OpenAI-style function calling, which covers
vLLM, Ollama, llama.cpp and most open servers), and otherwise a
strict **text tool protocol** — one sentinel-bracketed block per call
in bale's probe-block style, parsed strictly, its result returned as
the next user turn — so that a weak model is safe rather than merely
possible (a strict parser plus D17's `malformed_response` move). Two
adapters in Arc 2: Anthropic first, OpenAI-compatible second; Q-3's
contract is designed once against both. T6 in section 2 carries the
sitting's description verbatim; the protocol's exact wire is TQ-3.

### 4.3 Concerns the sitting named

Verbatim from the sitting, reformatted as this seed's list and not
reworded:

- **Window management.** API calls don't compact (D17's
  annotation). D12's append-only prefixes mean twine never compacts
  silently either; instead it counts (usage from the API, estimates
  for open models), warns the worker as a tool result when the
  window runs thin so AGENT.md §11's bail-to-handoff fires, and
  treats exhaustion as an outcome with a move. Twine also owes
  bale-src an AGENT.md §11.7 surface row (D21's annotation).
- **Turn-end detection and shape classification.** On claude.ai a
  human reads the turn; in twine, `end_turn` with no tool call ends
  it, and the courier classifies the final text as one of the four
  shapes, or as prose (a sitting's answer). A response tarball
  can't travel as text, hence `deliver`.
- **The include set on disk, the opener as first user turn, a
  model-agnostic system prompt** holding only the tool definitions
  and the surface note (D11; prompt-cache-stable).
- **Suspension and cold resume** (D23): a worker blocked on a
  clarification has its transcript persisted append-only and
  re-warms on the answer.
- **The transition table grows a provider axis**: rate limit and
  overload (retry with backoff), network failure, `max_tokens`,
  model refusal (the 45-arc specimen), tool error (returned as a
  result, never a crash), timeout, malformed shape.
- **Sandbox**: twine builds the cage its workers' tools run in
  (per-sid home, network off, `unshare` where available);
  confinement of validation and checkpoints stays bale's.

### 4.4 What the runtime owes outside this repo

Two obligations fall out of the above and are recorded so they are
not lost. To **bale-src**: an `AGENT.md` §11.7 surface row for
twine-hosted API workers (D21's annotation), via D6's linked-session
procedure, once Arc 2's loop exists. To **nisaba-src**: the dated
annotation on `nisaba-seed.md` §3.3 recording T4's three faces (T4
above). Neither is this session's or this repository's to land.

### 4.5 Effort (T11, directed)

The runtime owns two of T11's mechanisms: `ask` re-warms a finished
worker's transcript, appends a question and answers it with read-only
tools at most; `delegate` is a capability on the canonical surface —
the same contract across adapters, native tool use or the text
protocol — and the first to carry §4.1's experimental marker. Both
bill to the sid they serve through the cost spine (Arc 1 session 5).
The dial's setting is read from the office and never held by twine
(N4). T11's table in section 2 is the catalog.

---

## 5. The road

Three arcs, in order (T5): the courier, the runtime, the scheduler.
Every session is a bundle authored at a sitting (`PLANNER.md` §2) and
opened with `bale open`; from session 1 onward each carries a blind
checkpoint (T3). Sessions 2, 3 and 4 of Arc 1 are file-disjoint and
may run beside each other once session 1 has landed; the rest
serialize on the dependencies the table names.

### 5.1 Arc 1 — the courier

As the sitting tabled it, verbatim:

| # | session | lands | depends on |
|---|---|---|---|
| 0 | **seed** | `twine-seed.md` (derived), `README.md`, `bale.toml` (packer identity; checkpoint pin — see Q below), repo layout as an ADR | probe facts |
| 1 | **core + registry + bale pin** | `bin/twine`, the command registry with JSON twins, `twine bale check` (pin vs installed `bin/VERSION`, D2) and the consumption manifest file (D4), `twine status`; stdlib only; tests | 0 |
| 2 | **offline courier — take** | classify a pasted worker turn into one of the four shapes; run a probe block read-only in the repo and produce the paste-back (integrity trailer verified); render a light block to the inbox and take the reply; hand a clarification to `bale relay` and a response to `bale apply --no-interact --json`, surfacing refusal remedies rather than admitting | 1 |
| 3 | **offline courier — emit** | `bale open --json` on a bundle → the request tarball path and opener; the session's in-flight record (twine's one piece of state besides spend) | 1 |
| 4 | **transition table (D17)** | outcomes × moves as data, keyed on bale 0.4.45's 13 outcomes and 9 closure reasons plus twine's API-side stop set; a test that fails by name on any outcome without a move | 1 |
| 5 | **cost spine + kill-switch (D15)** | per-call usage records by token class (input, output, thinking, cache read/write), running totals per session, hard cap checked *before* each call, between-calls abort and a process-level kill leaving an `aborted` closure — all against fixtures, no API | 1, 4 |
| 6 | **the loop (online)** | the Anthropic adapter behind an adapter boundary (D21), tool-use loop with shell + file I/O confined to a per-sid sandbox home (D10), streaming with thinking, prompt caching (D12); fake transport in tests | 2–5 |

Two corrections the sitting made after the table, recorded here
rather than edited into it:

- Row 0's "repo layout as an ADR" and "packer identity" did **not**
  land. The layout is session 1's to decide under `CODE.md` (no
  directory decision is made before the code that lives in it), and
  packer identity is already in the global `user/bale.toml`
  (`[identity] packer = "chordsphere"`), so `bale.toml` here carries
  only the checkpoint pin and the sandbox flag. Session 0 landed this
  seed, `README.md`, `bale.toml` and `claude/INDEX.md`, and removed
  the `SEED.md` placeholder.
- Row 6, the online loop, became Arc 2: it is the runtime, not a
  courier session.

Row 0's "see Q below" pointed at the sitting's own question about the
checkpoint pin; T3 answers it, and nothing below the table remains to
look for.

[2026-10-01-twine-seed-effort-003: row 1 landed as
`2026-10-01-twine-core-002` — `bin/twine` over a package `twine/`
whose command registry is discovered from `twine/commands/` (each
module's `COMMANDS`); the three verbs `commands`, `status` and `bale
check`; the `--json` discipline in one dispatcher;
`share/bale-consumption.toml` with the pin and the eight schema
hashes; four recorded fixtures under `fixtures/bale-0.4.45/`; and the
contract page `claude/context/cli-contract.md`. Its layout and the
decisions it asks the sitting to ratify are in
`claude/responses/2026-10-01-twine-core-002/notes.md`.]

[2026-10-01-twine-seed-effort-003: rows 2 and 3 serialize, 2 first.
Session 2 adds the `run` seam to `Context` (subprocess by default, a
fixture player in tests) and owns the three shared data files —
`share/bale-consumption.toml`, `fixtures/README.md`,
`claude/context/cli-contract.md` — which session 3 then extends; the
code and tests stay one module and one test file each, disjoint by
construction. Ratified at the sitting from session 1's Proposals.]

[2026-10-01-twine-seed-effort-003: row 3's "in-flight record" is a
**cache**: derived from `bale status --json` plus twine's own dispatch
facts (adapter, sandbox home, transcript), re-derivable, so deleting
it loses nothing bale does not know and N4's test holds; twine's
durable state is spend and transcripts. Beside it, the fact session
1's worker found: `bale status --json`'s `sid` names the *earliest*
open session, not necessarily the one twine is working on. Decided at
the sitting after session 0's Proposals; not objected to.]

[2026-10-01-twine-seed-effort-003: row 3 needs `bale open --json`,
which bale 0.4.45 does not have (nor does `relay`); both are
`[[wanted]]` entries in the consumption manifest, and the sitting
carries them as a slip for a bale-src session, after which twine bumps
its pin and re-records fixtures. Session 3 waits on it; session 2
does not.]

[2026-10-02-twine-seed-close-003: row 2 split twice, along what could be tested when. **2a —
read**: `twine take`, landed as `2026-10-02-twine-take-read-001`
(one HOLD — T3's second annotation — then PASS on retry). **2b-i —
the probe hand-off**: the `run` seam and `twine carry probe`, landed
as `2026-10-02-twine-carry-probe-002`, which also took `VERSION` to
0.2.0. **2b-ii — the bale hand-offs**, not yet authored: `carry
exchange` (an exchange block's own lines to `bale relay <sid> -`) and
`carry response` (`bale apply --dry-run --json`, then the apply line,
T12). Its first fixture is recorded: the architect's
`apply-dry-run-carry-probe.json`, one line, `"outcome": "dry-run"`,
for session `2026-10-02-twine-carry-probe-002`. Its relay-side fixture
rests on TARBALL.md §5.9.2's pinned property that the crafter's
`--emit-block` and `bale relay` render the same record
byte-identically.]

[2026-10-02-twine-seed-close-003: bale-src owes twine three changes, carried as one slip for a
bale-src sitting: `--json` on `bale open` (row 3 waits on it) and on
`bale relay`; and `_inline_lines` in `bin/bale_report.py` indenting
every sentinel prefix (`=== PROBE `, `=== LIGHT `, `BALE EXCHANGE`),
not only `=== RELAY `, so that text inlined into a relay block can
never read as another shape to a reader that is not span-aware.]

### 5.2 Arc 2 — the runtime

Not yet cut into sessions; its parts, each a session or a few: the
adapter boundary and the capability registry (T7, §4.1); the
canonical tool surface and the text tool protocol (T6, §4.2); the
sandbox the workers' tools run in (§4.3); the Anthropic adapter; the
OpenAI-compatible adapter; window accounting; hosted sittings (D22
as re-read). The Arc 1 loop row's content — the Anthropic adapter
behind the boundary, the tool-use loop with shell and file I/O
confined to a per-sid sandbox home, streaming with thinking, prompt
caching, a fake transport in tests — is the first of these sessions'
material. Arc 2 is cut at the sitting that opens it, after Arc 1
closes.

### 5.3 Arc 3 — the scheduler

Over office 0.5.0's drafting-table: it reads a ratified
decomposition, opens the bundles the sitting authored, dispatches
each to the runtime or to a person, runs children in parallel where
forecasts are disjoint and serialized where they are not, and
enforces the spend cap with bailout semantics. What it reads is
`blueprints/drafting-table.md` in nisaba-src — cited by name, not
copied here. Arc 3 is cut at the sitting that opens it.

---

## 6. Open questions register

Each entry carries a recommended default, who answers it, and in
which arc. An answer accretes beneath its entry as a dated bracketed
paragraph and ships verbatim into the request it affects. Q-numbers
are `harness-seed.md` §5's, carried with their disposition; TQ-numbers
are twine's own.

- **Q-2 — Frontend specifics.** *Moved.* The frontend is the shell's
  (N6); twine has no rendering of its own. Nothing for twine to
  answer; nisaba-src owns the question.
- **Q-3 — Open-source adapter contract.** *Answered in principle by
  T6:* the boundary abstracts tool calling (native or text protocol),
  thinking, usage accounting and the stop set, and is designed once
  against two adapters. The contract's text is Arc 2's; the agent
  authoring Arc 2's first runtime session writes it, the architect
  ratifies.
- **Q-4 — Chat-mode persistence.** *Still open.* Answered if the
  Nisaba seed's Q-1 (the planning chat is a hosted office session) is
  answered yes: the sitting's words land in the notepad, its plans on
  the drafting-table, and twine keeps only mechanical streams.
  Recommend yes. The architect answers, at the Arc 2 sitting.
- **Q-5 — Email transport.** *Later rung.* The batched-digest
  delivery mechanism; nothing in Arcs 1–3 depends on it. The
  architect answers when the scheduler has something to batch.
- **Q-6 — Hard-cap scope shape.** *Arc 1 session 5 must decide.*
  Recommend both per-session and per-arc caps, checked before each
  call, with the configuration living in the office's house rules
  (the Nisaba seed's Q-6: office holds the policy, twine reads it,
  bale's telemetry is the evidence). Session 5's worker proposes the
  shape in its `notes.md`; the architect ratifies.
- **Q-7 — The suite seams.** *Answered by the Nisaba seed* (its §1
  and §3); this seed's §1 points there.
- **Q-8 — Where spend lands.** *Still open bale-side.* The Nisaba
  seed's Q-5 recommends twine owns the stream and bale's
  `attempts[].cost` block mirrors it. Twine-side the answer is taken:
  the cost spine (Arc 1 session 5) is the owner. Whether bale grows
  an input for the mirror is a bale-src decision (D6 linked pair);
  the architect, at the Arc 2 sitting.
- **TQ-1 — Where a worker's transcript lands.** Twine's log, or the
  office's folder (the Nisaba seed's Q-3 is the neighbour).
  Recommend twine's log, kept as a log and not as a record of intent,
  with the office receiving only what bale's response carries; a
  transcript is diagnostic, and N4 says deleting it loses nothing
  that mattered. The architect answers, at the Arc 2 sitting.

  [2026-10-01-twine-seed-effort-003: answered — transcripts are kept
  **durably, append-only**, as logs and not as records of intent, with
  retention a house rule of the office; N4 holds because deleting them
  loses an effort option (T11's "ask an old worker"), never anything
  of record. Ratified as assumed at light block 3 [2].]

- **TQ-2 — The capability registry's file shape.** Recommend one
  Python module per capability carrying a declared contract object,
  and a `capabilities.toml` that lists them — a declaration, so the
  parity test has something to walk and an undeclared capability
  fails by name. Arc 2's first runtime session proposes; the
  architect ratifies.
- **TQ-3 — The text tool protocol's exact wire.** Sentinels, one call
  per block, an integrity trailer, in bale's probe-block style; the
  bytes are Arc 2's. The agent authoring the OpenAI-compatible adapter
  session proposes; the architect ratifies.
- **TQ-4 — The effort policy's home and the dial's scale.** Recommend
  a house rule in the office's profile, per project and work class: an
  integer dial `0`–`3` where each step names the mechanism set it
  enables (0: none; 1: retry; 2: plus compare and reflect; 3: plus ask
  and delegate by default); twine reads it and never writes it, and
  the trust ledger (`PLANNER.md` §18) later moves it per class. Arc 3's
  first scheduler session proposes the exact mapping; the architect
  ratifies.

---

## 7. What this is not

Not part of bale (N1, D1): the five global docs, the wire format and
the verbs are untouched, and nothing here is a bale-side obligation
except the surface row §4.4 names, which goes through D6.

Not a UI (N6): the shell renders twine — the session pane, the cost
ticker, the four inboxes — and twine keeps a CLI and a JSON surface
and no rendering.

Not the office (N2): twine reads what the office declares and lands
nothing in it except what bale's response carries; the queue, the
rulings, the evidence and the words are the office's.

Not autonomous, yet (`PLANNER.md` §18, D7): every rung is proven
under the architect's hand before twine inherits it, and autonomy
grants wait on the sequencing D7 keeps.

Not a replacement for the manual path, which remains fallback and
ground truth at every rung: a worker behaves identically whether a
person or twine packed its request, carried its shapes, and applied
its response.

---

## 8. The sitting's words, verbatim

Session `2026-09-29-begin-harness-001`, packed read-only from
`~/twine-src` on chordsphere. Every message the architect typed, in
order. The probe's output (496 lines, probe `begin-harness-001`,
2026-10-01T21:44Z) was attached as a file and is elided here; it
read the machine, bale's install and the four sibling repos, and its
facts are cited where this seed uses them. The two light question
blocks the sitting emitted are described, not quoted: block 1 asked
three questions — a fresh repository with a derived seed; Arc 1 is
the courier; the checkpoint pinned from session 1 — and was answered
"as assumed" (message 3); block 2 asked three — three faces, one
core; courier then runtime then scheduler; the tool-calling design —
and was answered "as assumed" with the T7 direction added (message
4).

[2026-10-02-twine-seed-close-003: this section continued after session 0 and holds every
message the architect typed, eleven in all. Light blocks 3, 4 and 5
are described beside the messages that answered them. Messages that
carried only attachments — ratification relays, probe outputs,
context tarballs, a recorded fixture — typed nothing and are not
listed.]

Message 1 (the session opener; the goal is the manifest's, verbatim):

> I'm using "bale", a CLI that packaged the attached request tarball.
> This message opens read-only bale session 2026-09-29-begin-harness-001
> (empty write forecast: an orchestration/discussion session — no changes land from it).
> Goal, verbatim from the request manifest: let's begin work on our harness 'twine' meant for 'bale'
> The docs and tools in the tarball are mine, written for this workflow;
> AGENT.md and the four docs beside it are my instructions for this
> session. Read manifest.json first, then AGENT.md; AGENT.md says when
> the other four docs are needed. tools/craft_response.py and
> tools/response_lint.py are stdlib-only formatters with no network
> access — conveniences over the docs, which are the contract; read them
> before you run them, and a response assembled by hand is just as
> valid.
> Packed at 2026-09-29T22:25:01+00:00 (UTC).
> bale's dates are UTC and can run a day ahead of this chat's date (a timezone gap, not an error); date what you write from the session id.
> If you need something from me, a fact from my machine or a decision,
> end that turn with the matching block from TARBALL.md (a probe, a
> light question block, or a clarification response) rather than a
> question in prose, which tends to get lost. This is a planner session:
> nothing lands from it, so don't build a response tarball, even an
> empty one. What I need back is your answer in chat and, for each
> session I ask you to author, a crafter bundle with its bale open line,
> as PLANNER.md describes.

Message 2 (with the probe's output attached, 2026-10-01):

> I just finished work on office-src, hopefully that brings us to the point we can develop twine-src:

Message 3 (answering light block 1 — [1] fresh repo with a derived
seed; [2] Arc 1 is the courier; [3] checkpoint pinned from session 1):

> Before we go further, I want to discuss twine's purpose and ultimate form. We've designed bale so that each turn from an llm API ends in a type of response, which should fit right into twine, but I always envisioned the harness doing more than just being a courier. For example, claude uses "tool calls", and if we don't build this into twine, then any model except for claude will not be able to use tool calls. I'm sure there's other concerns like this as well.
>
> otherwise, as assumed

Message 4 (answering light block 2 — [1] three faces; [2] courier,
runtime, scheduler; [3] the tool-calling design):

> as assumed. i like the runtime face addition because tool calls aren't the only thing that an open weight api model would be missing, and I want the ability to add or customize new runtime operations. Honestly, I'm interested in developing my own runtime anyway for research reasons, and would like this to be the place I do that. So when we're developing the runtime phase, let's keep that in mind that I'd like the ability to manage and easily edit the different run time capabilities

Message 5 (asked while session 1 ran):

> while that's running, I want to ask about another feature of twine that I wanted but don't think we accounted for. In my original draft for the harness, I said that an "effort dial" would be really useful. Not like claude's effort toggle, but what it would do is things like run workers twice and compare, spawn reflection sessions to refine context, ask old workers questions after the fact, sessions spawned for subtasks like reading or tools to preserve main context etc. Things that would just increase time and compute but would produce refined answers.

Message 6 (with session 1's ratification relay attached; answering
light block 3 — [1] effort as T11; [2] TQ-1 flips to durable
transcripts; [3] author this session now):

> applied, and as assumed

Message 7 (with a `bale pack --context` tarball of twine-src
attached, after session `2026-10-01-twine-seed-effort-003` applied):

> no problem

Message 8 (with a fresh context tarball attached; answering light
block 4 — [1] twine never merges; [2] a probe runs only on `--run`;
[3] only a to-worker HOLD relay block may become a fixture):

> as assumed

Message 9 (while session `2026-10-02-twine-carry-probe-002` ran):

> I'm a bit confused, I just ran the bale open line and its running, but what do I need to do before apply? and I don't apply directly? just give me the step by step

Message 10:

> looks like the file I downloaded is 002 not 001

Message 11 (answering light block 5 — close the sitting with the seed
accretion and the nisaba §3.3 annotation as its last two bundles):

> as assumed

### How the sitting ended

Twine has three faces and one core; the arcs run courier, runtime,
scheduler; the runtime hosts both worker sessions and sittings and
is the architect's research surface, with its capabilities as a
managed registry; tool calling is one canonical surface behind an
adapter boundary, with a text protocol for models that have none;
twine-src is founded fresh with this seed derived from
`harness-seed.md`, and tedder-src stands as archive. Probes emitted:
one, answered. Light blocks emitted: two, both answered "as assumed".
Sessions authored at the sitting: this one, session 0.

[2026-10-01-twine-seed-effort-003: the sitting continued past session
0 — session 1 (`2026-10-01-twine-core-002`) applied with checkpoint
PASS and worker PASS; light block 3 was emitted and answered "as
assumed"; sessions authored so far: 0, 1, and this one; probes
emitted: two, both answered.]

[2026-10-02-twine-seed-close-003: the sitting closed on 2026-10-02 after session
`2026-10-02-twine-carry-probe-002` applied. Sessions authored: seven
— `2026-10-01-twine-seed-001`, `2026-10-01-twine-core-002`,
`2026-10-01-twine-seed-effort-003`,
`2026-10-02-twine-take-read-001`, `2026-10-02-twine-carry-probe-002`,
this one, and a nisaba-src session annotating `nisaba-seed.md`
§3.3. The first five applied, all with checkpoint and worker PASS
from session 1 on, one after a HOLD and a retry. Probes emitted by
the sitting: two, both answered. Light blocks emitted: five,
dispositions — block 1 as-assumed, block 2 as-assumed with the T7
direction added, block 3 as-assumed, block 4 as-assumed, block 5
as-assumed. Queued for the next sittings: session 2b-ii; Arc 1
session 4 (the transition table); session 3, after bale-src's
`open --json`; the bale-src slip of section 5.1's last annotation;
then session 5, whose usage record reserves a `served_sid` field
from the start (T11's envelope).]

# INDEX.md

> Drill-down map for this project's documentation.
> Updated whenever the inventory changes.

Paths are relative to this file's directory (`claude/`); the docs
that live at the repository root or beside the code carry `../`.
The global docs bale ships (`AGENT.md`, `TARBALL.md`, `DOCS.md`,
`CODE.md`, `PLANNER.md`) are not listed — they are not part of this
project's inventory.

## Project state
- `INDEX.md` — this file.

## Charter & product
- `../twine-seed.md` — twine's seed document and the project spec's
  home: identity, the sitting's rulings T1–T14, harness-seed.md's
  D1–D24 carried with a status each, the runtime's design, the road
  (three arcs), the open questions register, and the sitting's words.
  The `amendment_target` for every later answer about twine. Default
  inclusion.
- `../README.md` — the repository's front page: what twine is in a
  paragraph, what exists now and how to run it and its tests, where
  the seed is, and the Nisaba layer cake by pointer. Pull when a
  reader needs the one-paragraph picture; the seed wins on any detail.

## Schemas & data contracts
- `../share/bale-consumption.toml` — the floor (D2 as amended: twine
  drives any bale at or above it whose installed schemas hash as pinned)
  and the consumption manifest (D3, D4): the installed schema hashes (the
  gate's second half), one
  `[[surface]]` per bale surface twine reads — files, verbs (with every
  further recorded outcome of a verb as `also_recorded`), and the text
  formats `take` parses, each naming the version that emitted its
  fixtures — `[[wanted]]`, a shape kept in the header for a surface a
  later session needs and the bale at the floor lacks (none at 0.4.51: the three the
  0.4.45 manifest carried are surfaces now), and `[[vocabulary]]` for
  bale's three closed vocabularies the transition table keys on
  (telemetry outcomes, closure reasons, `bale apply --json` outcomes).
  `[bale] floor = "0.4.51"` since session `2026-10-12-twine-pin-floor-002`
  (an exact `pin` before); each surface's `keys` are checked present on
  the line its reader reads. Pull when a session reads a new bale surface
  or raises the floor; the header comment spells the entry shapes.
- `../share/transitions.toml` — the transition table (D17): four axes
  (the three bale vocabularies and twine's stop set), one row per key,
  each naming a declared move with its actor (twine, operator or
  planner); no default case. Pull when a session dispatches on an
  outcome or a stop, adds a stop, or raises the floor; the header comment
  spells the shape and `twine transitions` checks it is total. Its `stop`
  axis is the runtime boundary's stop set, read through
  `twine.transitions.stop_keys` (`context/runtime-contract.md` §1.5).
- `../twine/runtime/capabilities.toml` — the runtime's capability
  declaration (T7, §4.1; TQ-2's shape, proposed at Arc 2 R1): one
  `[[capability]]` per capability — `name`, `module`, `status`
  (`declared`, `implemented`, `experimental`), `summary` — held to the
  modules under `twine/runtime/capabilities/` by name. Pull when a session
  adds, implements or changes a runtime capability; the header comment
  spells the entry shape and `twine runtime list` checks parity.

- `<state-dir>/spend.jsonl`, `<state-dir>/prices.toml`,
  `<state-dir>/abort/<sid>.json`, `<state-dir>/running/<sid>.json` and
  `<state-dir>/inflight/<sid>.json` — not in this repository: twine's state directory (`--state-dir`, else
  `$TWINE_STATE_DIR`, else `${XDG_STATE_HOME:-$HOME/.local/state}/twine`).
  The spend stream is twine's durable usage record (D15, N4): append-only,
  one JSON line per model call, tokens by class and a nullable
  `served_sid`. The price file is the operator's — twine ships no prices —
  one `[model."<id>"]` table per model in US dollars per million tokens.
  Both shapes, and that no provider usage has been recorded yet, are
  `context/cli-contract.md` §13. The abort request is the kill-switch's
  durable between-calls abort — its presence is the signal the loop checks
  before every model call, written by `twine kill` and never removed — and
  the running record is the process groups a session's runtime runs in, a
  cache of exactly six keys (`sid`, `pgid`, `pid`, `started_at`,
  `leader_start_ticks`, and `groups` — one entry per further group the
  runtime registered through the run seam's spawn hook, session 5c) the
  runtime writes before it works, grows as it starts tools and shrinks as
  they return with nothing left alive (`clear_group`), and `twine kill`
  reads, signals every group of, re-reads once and clears; both are
  `context/cli-contract.md` §14, and `twine status` reports which state
  directory twine resolves and what of it exists (§4). The in-flight record
  (Arc 1 session 3) is the session `twine carry bundle` opened: a cache of
  exactly four keys (`sid`, `cwd`, `tarball`, and `opens` — one entry per
  desk, `outcome`, `desk`, `bundle_sha256`, `opener_sha256`, `recorded_at`),
  written on an `opened` or `second-desk` only, never removed in Arc 1, and
  where a second desk finds the request tarball when bale's `second-desk`
  line does not name one (bale 0.4.49's did not; 0.4.50 on names it); `context/cli-contract.md` §15.4. Pull when a session
  reads or writes spend, prices a model, maps a provider's usage onto the
  record (Arc 2), starts, stops or kills a session's runtime, or opens,
  tracks or closes a session twine carried in.

## Explainers
- `context/cli-contract.md` — the `twine` CLI's interface outcomes:
  the entrypoint, the registry and its discovery, the `--json`
  discipline and exit codes, `status` (its keys, and since session 5c
  the state directory it resolves), `bale check` and `take`'s keys,
  the five block kinds and the no-nest rule, the relay routing rule
  (a `to: planner` block never reaches a worker), `carry probe` (its
  refusals, `--run`, the output cap, `confined: false`, its keys) and
  the run seam (`Context.run`, the signature later carry verbs build
  on, its group wait and its spawn hook), §11 — the bale hand-offs
  (`carry exchange`, `carry response`),
  how bale is found and the gate (a floor plus schema hashes, and the
  key check on each line), T12's one `apply` argv —
  §12, `transitions` (the table's axes, its ok rule and the problems
  that name a fault), and §13, `spend totals` and `spend check` (the cost
  spine: the usage record, the state directory, prices as operator data,
  the hard cap's pre-call check and its refusals, `stop` `cap-reached` and
  `cap-unchecked`), §14, `kill` (the kill-switch: the between-calls abort,
  the running record with its `groups` and the process-level kill of every
  one of them, the gate gating the closure alone, the one `unlock` argv and
  the `aborted` closure, the recorded unlock lines the tests replay since
  the pin at 0.4.49, their stderr since 0.4.51), §15, `carry bundle` (the
  courier opens a bundle with the one `open` argv, never retried; the
  opener on stdout; the in-flight record and the tarball a second desk
  needs; the four recorded open lines the tests replay, a refusal among
  them), §16, recording a version (the recorder, the lander and the
  procedure that raises the floor), the manifest and fixture shapes (§5
  the gate, §6 the floor, the key check and when a moved install needs a
  recording) (per-run fixture names, by
  role; outcome groups; stderr siblings), how the tests run. Default inclusion for any session
  that adds a verb, runs a subprocess, routes a courier's block, or
  touches spend, the kill-switch or the in-flight record. Since Arc 2 R1
  also §17, `runtime list` and `runtime show` (the registry rendered, ok
  on parity by name; one capability's contract).
- `context/runtime-contract.md` — the runtime's contract, the sibling of
  `cli-contract.md` (Arc 2 R1; §1 and §2 proposed, awaiting ratification):
  §1 the adapter boundary (Q-3 — what an adapter implements: tool calling,
  thinking fixed at spawn, usage as the five token classes, the stop set
  read from the transition table's `stop` axis and spelled nowhere else;
  what the boundary refuses), §2 the capability registry (TQ-2 — the
  declaration's entry shape, the contract object, the three statuses,
  parity by name, adapters declaring what they implement, the eight at
  R1), §3 the fake adapter (the script format, what it cannot do), §4
  provider usage mappings (`from_anthropic`'s table, thinking counted
  once). Default inclusion for any Arc 2 runtime session: an adapter, a
  capability, the loop, the sandbox, window accounting.
- `../fixtures/README.md` — the fixtures rule (recorded bytes from a
  named bale version, or an architect-carried paste of bale output;
  never hand-written), the path naming rules (bale argvs, crafter
  emissions, carried pastes; the three `<where>` directories, per-run
  values named by role, and the outcome group an argv recorded with more
  than one outcome carries), and per file the command, directory, date,
  probe, byte count and sha256 — exit codes, `unrecorded` where not
  captured (no 0.4.49 or 0.4.51 row) — and, since 0.4.51, the stderr each
  recording printed: a `.stderr` sibling per file and two more columns
  per row; a version's recordings come from one carried paste-back, the
  recorder's, which lands under its `carried/` as their source. Since
  session `2026-10-12-twine-pin-floor-002` the floor names the directory
  the tests replay, and the eight installed schemas the gate hashes sit
  under it in `schemas/`, byte-exact, with a `| file | bytes | sha256 |`
  table of their own (not recordings: the lander leaves them alone). One
  section per bale version, earlier sections kept as history. Since Arc 2
  R1 a last section, "Provider recordings": `fixtures/anthropic/`, a
  provider's recorded `usage` object (one JSON object line per model per
  day) under its own rule, beside bale's, with its provenance and a
  `| file | bytes | sha256 |` row. Pull when recording or reading a
  fixture, or mapping a provider's usage.

## Tools
- `../bin/twine-record-fixtures` — the recorder: the probe a recording session
  runs in `~/twine-src` with the new bale on PATH, recording every bale
  surface twine reads, stdout and stderr, with a gzip+base64 copy of
  each stream; `[SLUG]`, default `twine-record-<installed version>`.
  `context/cli-contract.md` §16.
- `../bin/twine-land-recordings` — the lander: lands a recorder
  paste-back under `fixtures/bale-<version>/` (recordings, `.stderr`
  siblings, the paste) and prints the README rows and manifest lines, or
  with `--check` writes nothing and exits 0 exactly when the tree holds
  what the paste derives. Its naming rule is `../tests/fixture_rule.py`,
  shared with the tests; `--check` leaves the floor's `schemas/` alone.
  Pull both when raising the floor.

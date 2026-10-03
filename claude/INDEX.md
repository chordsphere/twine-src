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
- `../share/bale-consumption.toml` — the bale version pin and the
  consumption manifest (D3, D4): the installed schema hashes, one
  `[[surface]]` per bale surface twine reads — files, verbs, and the
  text formats `take` parses — `[[wanted]]` for the surfaces a later
  session needs and the pin lacks, and `[[vocabulary]]` for bale's three
  closed vocabularies the transition table keys on (telemetry outcomes,
  closure reasons, `bale apply --json` outcomes). Pull when a session
  reads a new bale surface or bumps the pin; the header comment spells
  the entry shapes.
- `../share/transitions.toml` — the transition table (D17): four axes
  (the three bale vocabularies and twine's stop set), one row per key,
  each naming a declared move with its actor (twine, operator or
  planner); no default case. Pull when a session dispatches on an
  outcome or a stop, adds a stop, or bumps the pin; the header comment
  spells the shape and `twine transitions` checks it is total.

## Explainers
- `context/cli-contract.md` — the `twine` CLI's interface outcomes:
  the entrypoint, the registry and its discovery, the `--json`
  discipline and exit codes, `status`, `bale check` and `take`'s keys,
  the five block kinds and the no-nest rule, the relay routing rule
  (a `to: planner` block never reaches a worker), `carry probe` (its
  refusals, `--run`, the output cap, `confined: false`, its keys) and
  the run seam (`Context.run`, the signature later carry verbs build
  on), §11 — the bale hand-offs (`carry exchange`, `carry response`),
  how bale is found and the pin gate, T12's one `apply` argv — and
  §12, `transitions` (the table's axes, its ok rule and the problems
  that name a fault), the manifest and fixture shapes (per-run fixture
  names, by role), how the tests run. Default inclusion for any session
  that adds a verb, runs a subprocess, or routes a courier's block.
- `../fixtures/README.md` — the fixtures rule (recorded bytes from a
  named bale version, or an architect-carried paste of bale output;
  never hand-written), the path naming rules (bale argvs, crafter
  emissions, carried pastes), and per file the command, directory,
  date, probe, byte count and sha256 —
  per-run values named by role; exit codes, `unrecorded` where not captured.
  Pull when recording or reading a fixture.

# notes.md — 2026-10-08-twine-carry-exchange-json-001 (`carry exchange` reads `bale relay --json`)

The change does what the brief asked, and nothing past the forecast.
`twine.bale.relay_argv` builds exactly `relay <sid> - --json`. Stdin is
still `shapes.block_text`. `carry_bale.read_relay_line` reads bale's one
line. Human stdout on ok is the line's `block`. The twin gains `relay`
and `outcome`. The flagless surface, its stand-in and the `BaleDouble`
relay answers are gone. The suite went from 521 to 536. Every path I
changed is inside `resolved_scope`, and `claude/INDEX.md` is not shipped
because none of its sentences became false.

## 1. The three decisions brief §5 left to me

**The not-ok reasons.** Every check runs on its own and appends its own
failure, so the reason lists every difference at once, `; `-joined, after
`call_bale`'s `bale exited N` / timeout / cap lines:

- `bale's stdout was not one JSON object (it was empty)` or
  `… (it began '<first 60 chars>')`. This is the wording `carry
  response` already uses for the same fault.
- `bale refused the relay (outcome 'relay-refused'): "<cause>"`. The cause
  is in double quotes, whole and unescaped. If the cause is null or empty,
  the reason says `its line names no cause`.
- `bale reported outcome 're-emitted': it recorded nothing (a re-emission
  answers a relay given no input; twine always passes the block)`.
- `bale reported outcome '<x>', which twine does not know (not 'relayed')`.
- `bale's line names sid '<x>', not the block's '<sid>'`.
- `bale's line carries no block (block is null)`, or `(block is int)`
  and so on for a non-string, or `bale's line carries an empty block`.

One consequence to ratify. On `relay-refused` the line's `block` is null,
so the reason also ends with `bale's line carries no block (block is
null)`. I read §2.2's "naming each thing that differs" literally rather
than special-casing the refusal. It is redundant beside the quoted cause.
If you'd rather the block check only fire on `relayed`, it is one `if`
in `read_relay_line`.

**The double.** I called it `RecordedRelay` and put it in
`tests/helpers.py`, directly after the open recordings. Beside it are
`relay_recording(name)`, `RELAY_RECORDINGS`, `RELAY_KEYS` (the twelve
keys in order, checked against every recorded line),
`relayed_block()` and `block_for_sid()`. It has `RecordedUnlock`'s shape.
Its docstring names the `_read_relay_input` assumption. It adds one
guard: it refuses to replay a recording for a sid its line does not
name, unless the test overrides `stdout` with bytes it names as not
bale's. bale's `sid` is "the argument as given", so replaying a line for
another sid would claim something bale never said. That guard is how
"each recorded line answers for its own sid" is enforced rather than
just intended.

**`keys` for the `--json` relay surface: four, without `round` and
`awaiting`.** twine reads `outcome`, `sid`, `block` and `cause`, and
carries the rest whole in the twin's `relay`. At first I had the ok log
line print `round` and `awaiting`. I took that out so the manifest's
"every key not listed is free for bale to change" stays exactly true.
The log line now names only the sid and the outcome.

## 2. Other choices worth a look

- **The session-gate refusal is replayed for an edited block.** That
  recording names `no-such-sid-twine-049`. The test carries the relayed
  block with its BEGIN sentinel changed to that sid (`block_for_sid`).
  The trailer hashes the body only, so `take` still reads the block as
  intact, and a test asserts this. twine's argv then names the sid the
  recording answered for.
- **What the ingest and re-emitted replays mean.** The ingest refusal was
  bale's answer to a file that was not JSON. Replayed for a block twine
  has vouched for, it stands for any refusal of ingested input. The
  re-emission answered `relay <sid> --json` with no input, which is an
  argv twine never builds, so replaying it proves only that twine never
  accepts one. `RecordedRelay`'s docstring says both.
- **Contract sections beyond §11.2 and §11.4.** §6 named the flagless
  relay as the one stand-in and said `bale relay --json` was read by
  nothing. §7's naming example gave `relay <sid> -` →
  `relay_sid_stdin.txt`. §8's test paragraph named only `BaleDouble`
  and said no test runs a real `bale unlock`/`open`. All of these became
  false, and they are in the same forecast file, so I corrected them. I
  also added one sentence to §11's opening. The original opening
  sentence, "Neither writes a file", is unchanged.
- **Two small edits in the consumption manifest.** The header's
  `stand_in` shape comment now says no surface carries one since this
  session. The shape itself stays. The `exchange` format's
  `emitted_by` now reads `bale relay <sid> <file|-> (on stdout; under
  --json, as the line's `block`)`. No test reads either.
- **Never-called runners swapped.** The refused-before-bale exchange
  tests used `BaleDouble()` as a runner that is never called. They now
  use `RecordedRelay()`, so the exchange tests no longer reference
  `BaleDouble` at all. Each one still asserts `calls == []`.
  `BaleDouble` is now `carry response`'s only, and its docstring says so.
- **The vouching tests still edit the crafter's emission.** Its body
  carries a `—` escape, which `test_unescaped_in_transit` needs and
  the relayed block's body does not have. Nothing in those tests reaches
  bale, so they keep using it, and the file stays the `exchange` format's
  fixture.
- **The relay-argv-built-once test** looks for list and tuple displays
  holding `"relay"`. It cannot just count string constants, because
  `"relay"` is also `shapes.RELAY`, the block kind, and the twin's
  `relay` key. It also asserts `relay_argv` is called only from
  `carry_bale.py`. Like the `apply` test it is modelled on, it passes on
  the old tree too: it is an invariant, not a change detector.

## 3. Every test that moved, by name

The eleven the brief named, rewritten:

- `test_one_exchange_block_is_chosen_and_its_sid_reported` now carries
  the relayed block. It asserts sid `2026-10-07-sc-002`, `[1]`, ok, every
  fixed name present, `relay` equal to the recorded line and `outcome`
  `relayed`.
- `test_block_number_picks_by_takes_numbering` builds the turn from a
  light block, the crafter's exchange block and the relayed block.
  `--block 3` relays exactly the relayed block's bytes for its sid.
- `test_bale_relay_sid_dash_with_exactly_the_blocks_lines_on_stdin`
  asserts argv `[…/bin/bale, relay, 2026-10-07-sc-002, -, --json]`, one
  call, and stdin exactly the block's bytes through CRLF and surrounding
  prose. Timeout, cap, env and cwd are as before.
- `test_stdin_dash_reads_the_turn_from_stdin` covers the same flow with
  the turn read from stdin. It is ok, and bale's stdin is the block.
- `test_ok_json_carries_bales_stdout_and_stderr` asserts that the twin's
  `stdout` is the recorded line byte for byte, `relay` the parsed line
  with the twelve keys in order, and `outcome` `relayed`. Stderr is
  bytes named as not bale's, and they pass through.
- `test_human_stdout_is_exactly_bales_stdout` is renamed
  `test_human_stdout_is_exactly_the_lines_block`. It asserts human
  stdout is byte for byte the line's `block` and that the JSON line is
  not printed.
- `test_the_pinned_version_is_driven` now has its exchange case answered
  by `RecordedRelay()` with the relayed block carried. The response case
  is unchanged.
- `test_carry_exchange_through_the_real_seam` uses `StubBale` replaying
  the relayed recording. It asserts the stub saw `relay
  2026-10-07-sc-002 - --json` and the block's bytes, and that the twin's
  `stdout`, `relay` and `outcome` are the line's.
- `test_carry_exchange_human_stdout_is_the_relayed_block` asserts,
  through the same stub, that stdout is byte for byte the line's `block`.
- `test_the_carry_hand_offs_bale_surfaces` (manifest) checks that the
  relay surface is `--json` only, with keys `outcome, sid, block, cause`
  and read_by `carry exchange`. It checks that no verb surface has a
  `stand_in` and that the exchange format keeps the crafter fixture and
  its `read_by`.
- `test_relay_json_is_a_surface_now` is renamed
  `test_relay_json_is_read_by_carry_exchange`. It asserts read_by, keys
  ⊆ `RELAY_KEYS`, every recording's key order, the `fixture` and
  `also_recorded` files being exactly `RELAY_RECORDINGS`, that the
  flagless surface is gone, and that the note names `relay <sid> -
  --json`, `_read_relay_input`, "with a file" and
  `relay_sid_stdin_--json.json`.

The four that described the flagless relay through `BaleDouble`:

- `test_bale_exiting_non_zero_is_not_ok_naming_the_status` is now a
  named double: exit 1 with empty stdout. The reason names
  `bale exited 1` and the missing line. `relay` and `outcome` are null.
- `test_human_mode_not_ok_is_one_line_and_never_bales_stdout` uses the
  recorded ingest refusal, and the relayed line beside exit 1. Each is
  one `NOT OK` line with no block and no JSON line.
- `test_a_bale_that_times_out_is_not_ok` uses `RecordedRelay(timed_out=True)`.
- `test_the_fixture_player_has_no_relay_recording` is renamed
  `test_the_fixture_player_has_no_recording_of_twines_relay_argv`. The
  player refuses twine's argv, naming `relay_sid_stdin_--json.json`. It
  answers the recorded file argv with the same bytes and exit that
  `RecordedRelay` replays.

Also moved: `test_json_discipline.py`'s setUp. Its stub replayed the
crafter's block as relay stdout, and its carry-exchange input was the
crafter's block. It now replays the relayed recording and carries that
line's block.

New (15): `test_the_relay_argv_is_fixed`,
`test_relay_is_built_in_one_place_only`,
`test_a_block_without_a_final_newline_gains_one`,
`test_each_recorded_refusal_is_not_ok_quoting_its_cause` (ingest and
session-gate), `test_a_re_emission_recorded_nothing_and_is_not_ok`,
`test_a_relayed_line_beside_exit_1_is_not_ok`,
`test_a_relayed_line_naming_another_sid_is_not_ok`,
`test_a_relayed_line_with_a_null_or_empty_block_is_not_ok` (null, `""`,
int), `test_an_outcome_bale_never_emits_is_named` (exchange's),
`test_stdout_that_is_not_one_json_object` (exchange's: the flagless
answer, a usage line, two lines, an array), `test_a_capped_stdout_is_not_ok`,
`test_the_twins_fixed_names_on_every_path`,
`test_the_double_refuses_to_answer_for_another_sid`,
`test_the_relayed_block_is_an_intact_exchange_block_of_its_sid`,
`test_a_recorded_refusal_through_the_real_seam` (StubBale replaying the
ingest refusal, exit 1).

The integrity and sid refusals that start nothing are unchanged, and
still assert `calls == []`.

## 4. validation.sh

It runs `python3 -I -B` throughout, from the staged root. It checks:

- file syntax (`ast.parse` on the six changed .py files, `tomllib` on
  the manifest);
- the suite, which must report OK and run ≥ 521 tests;
- `bin/twine carry exchange` end to end against a stub root it writes,
  which replays the relayed recording. Human stdout must equal the
  line's `block` by `cmp`. The stub's recorded argv must be exactly
  `relay 2026-10-07-sc-002 - --json`, and its stdin `cmp`-equal to the
  block. The `--json` run must be the ok `relayed` twin;
- the same against a stub replaying the ingest refusal, exit 1: one
  `NOT OK` line quoting the cause, with no block and no traceback;
- the untouched set by sha256. That is 38 files hashed from the tree I
  was given: `bin/twine`, `share/transitions.toml`, `carry_bundle.py`,
  `inflight.py`, `kill.py`, and every file under `fixtures/` except
  README.md, plus a check that nothing was added there;
- `VERSION` `cmp`-equal to `0.10.0\n`.

One limit: `twine-seed.md` is not in the request's tree, so I cannot
hash it. The script checks only that this response's `changes[]` does
not name it, read from `.bale-manifest.json`. Outside bale staging it
says it skipped that part.

I ran it on a staged copy (all checks pass, 39 s) and on the unmodified
tree. On the unmodified tree both end-to-end checks and the VERSION
check fail; the suite and the untouched check pass, as they should. The
claim is the suite only (observed pass), per §5.3's project-level rule.

## 5. The seed annotation (out of scope here; for tidy7)

At the end of §5.1's annotations, where carry-bundle-003's went, after
whatever tidy6 leaves last there. Verbatim:

> [2026-10-08-twine-carry-exchange-json-001: `twine carry exchange` reads
> `bale relay <sid> - --json`'s one line instead of passing the flagless
> relay's stdout through — ok exactly when bale exits 0 and the line says
> `relayed` for the block's sid with a non-empty `block`, which is then
> human stdout, byte for byte what the flagless relay printed; a refusal's
> reason quotes bale's `cause` whole and never dispatches on it. The JSON
> twin gains `relay` and `outcome`, and its `stdout` is now the line. The
> flagless relay surface, its stand-in (the crafter's `--emit-block`
> emission, still the `exchange` format's fixture) and the `BaleDouble`
> relay answers are retired: the tests replay the four 0.4.49
> `relay --json` recordings, made with a file, for twine's `-` on a named
> assumption (bale's `_read_relay_input`) that a recording of
> `relay <sid> - --json` replaces. `VERSION` 0.10.0.]

## Proposals

**What.** Record `bale relay <sid> - --json` (relayed, and one refusal)
on the next recording probe, then drop the assumption from
`RecordedRelay`, the manifest note, contract §11.4 and fixtures/README.md.
**Why.** Every exchange test now rests on the claim that bale reads `-`
as it reads a file. The brief verified this from `_read_relay_input`,
but it is still a reading of source, not bytes. The brief already rides
it on the next probe. I'm listing it so the four places to update are
named.
**Scope hints.** `tests/helpers.py` `RELAY_RECORDINGS`, then the
manifest's `fixture`/`also_recorded`. `fixture_key` already names it
`relay_sid_stdin_--json.json`.

**What.** Vouch for the block bale hands back: run `take`'s exchange
integrity check on the line's `block` before printing it, and fail if it
does not hold.
**Why.** twine refuses to relay a block it cannot vouch for, but it
prints whatever `block` bale returns. The reply block is exactly what the
courier carries next, so a garbled one is only caught a hop later, by
whoever relays it. It is cheap, since `shapes.find_blocks` already
exists. The brief ruled it out of this session.
**Scope hints.** `carry_bale.read_relay_line`, after the `block` checks.
The relayed recording's block is intact, so the existing ok tests would
not move. Doubles would cover a broken trailer and two blocks in one.

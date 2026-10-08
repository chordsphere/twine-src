# notes.md — 2026-10-08-twine-exchange-vouch-005 (`carry exchange` vouches for the block bale hands back)

The change does what the brief asked, and every path it touches is
inside the forecast. `read_relay_line` keeps all its checks. When the
line's `block` is a non-empty string, it now also hands that string to
the new `vouch_for_relayed_block`, which reads it as `take` reads text:
CRLF to LF first, then `shapes.find_blocks`. The verb is ok only when
the string is exactly one block, of kind `exchange`, intact by `take`'s
rule, and of the carried block's sid. When the vouch fails, the verb is
NOT OK with exit 1, and each failure is appended after the line's own.
`outcome` stays `relayed` and `relay` still carries the line, since
what failed is the vouch, not the reading. `relayed_block` was already
ok-only, so nothing changed there for "never printed".

The tree I was given was 0.11.0 with 556 tests, so
`twine-status-inflight` had landed first. `VERSION` is now 0.12.0, and
the suite is 568: 12 new tests, and no existing test moved.

## 1. The three decisions brief §5 left to me

**Exactness: yes, with one tolerated difference.** The string must be
the one block's own lines (`shapes.block_text` of it), with nothing
before or after, including a blank line. There is one exception. A
string that lacks only its final newline still passes, because
`test_a_block_without_a_final_newline_gains_one` is an existing ok test
and the brief says the existing ok tests stay unmoved. Contract §11.2's
human mode has also always supplied that newline. So "exactly" here
means "exactly, modulo the final LF that human mode supplies anyway".
If you want the final LF to be required too, that is one line in
`vouch_for_relayed_block` (drop the `whole = …` tolerance), and that
test would move to NOT OK.

The brief's "CRLF→LF first" means a CRLF block passes the vouch. Human
stdout is still the line's `block` byte for byte, CRs included, because
twine never rewrites what it hands on. A test pins this. I'm noting it
because a CRLF block is not what bale prints, and you might prefer to
refuse it. I followed the brief.

**The wording.** Every vouch failure opens with one fixed phrase,
`twine cannot vouch for the block bale handed back:` (the constant
`VOUCH_FAILURE`), so a reader can see that bale's line was fine and the
block is what twine refused. After that phrase:

- `it holds no block at all (`take` finds none in it)`
- `it holds N blocks, not exactly one ([1] exchange <sid>, [2] light <sid>, …)`.
  With more than one block, it names them and stops there.
- `it carries text around its one block (the block is lines a–b of n); twine hands on exactly a block's own lines`
- `it is a light block (light <sid>), not an exchange block`
- `it fails integrity (<fault>): <take's own error text> — twine never prints a block it cannot vouch for, and never repairs one`.
  This mirrors `check_vouchable`'s refusal for the block going in.
- `it is an exchange block of session '<x>', not of the carried block's '<sid>'`

With exactly one block, exactness, kind, integrity and sid are checked
independently, so prose around a corrupted block names both problems.
The sid check is skipped when the sentinel has no sid, because `no-sid`
already says so.

**Where it lives: `twine/commands/carry_bale.py`, beside
`read_relay_line`.** "Exactly one block, of this kind and this sid" is
the courier's rule about one hand-off. It is not a parse fact, and
`take` has no use for it. `shapes.py` stays the pure parser, and the
vouch is about thirty lines that call it. Nothing was shipped outside
the forecast.

## 2. Other choices worth a look

- **The vouch runs whatever the outcome**, whenever `block` is a
  non-empty string. That way an edited block next to `bale exited 1`
  and a wrong `sid` is named alongside them (§11.2: every difference at
  once). A test pins the order: the line's failures come first and the
  vouch's are appended after them. On the recorded `re-emitted` line it
  adds nothing, because that block is intact.
- **`share/bale-consumption.toml`: only the note's "ok exactly when"
  sentence moved**, as the brief said. The relay surface's separate
  `doubles` string already lists "edited lines (another sid, a null,
  empty or non-string block, …)". The new doubles are edited lines too,
  so that string is still true, but it doesn't name them. If you want
  them named there, it's one string, and `test_consumption_manifest`
  only checks that it is non-empty.
- **`claude/INDEX.md` is not shipped.** Its §11 sentence ("the bale
  hand-offs … how bale is found and the pin gate, T12's one `apply`
  argv") is still true, and nothing else in it describes the ok rule.
- **The verb's `--help` description** (`Command.description`) now says
  that ok needs "exactly one intact exchange block of that session" and
  that "a block twine cannot vouch for is never printed". The ok log
  line on stderr says the block handed back was intact.
- **The new tests' human-mode check is narrower than
  `assert_relay_not_ok`'s.** That helper asserts `# sha256 ` is absent
  from stdout, as a stand-in for "no trailer was printed". But `take`'s
  own text for the `no-trailer` fault, which the reason quotes, names
  the `` `# sha256 <hex>` `` trailer. So the new helper,
  `assert_not_vouched`, checks the things that would actually show a
  printed block instead: the relayed block's full trailer digest, its
  body's `"record_version"` and `BALE EXCHANGE END`. `assert_relay_not_ok`
  itself is unchanged.
- **Two blocks are built by hand, named as not bale's**
  (`hand_built_exchange`). A trailer that matches its body can't be
  produced by editing the recorded block, and `no-body` and
  `body-not-json` both need one. `unescaped-in-transit` uses the
  crafter's block, the only one with a `—` escape, with its
  sentinel renamed to the carried sid through `block_for_sid`, so that
  is the only fault it shows.

## 3. Every test that moved, by name

None moved. `tests/test_json_discipline.py`'s carry-exchange case
replays the recorded line whole, still passes the vouch, and pins no
reason, so it is not shipped. I added one paragraph to
`tests/test_carry_bale.py`'s module docstring, in its "what stands in"
list.

New (12). In section 3, the class `ExchangeVouchesForBalesBlock`, built
on relay lines that are not bale's (`relay_line_double(block=…)`):

- `test_a_block_edited_after_its_trailer_is_mismatch`
- `test_a_block_cut_short_is_no_trailer_or_unclosed`
- `test_every_integrity_fault_is_named_in_takes_words`
  (`unescaped-in-transit`, `no-sid`, `no-body`, `body-not-json`)
- `test_two_intact_blocks_in_one_string`
- `test_text_around_the_one_block_is_not_vouched_for` (prose around, a
  blank line before, a blank line after; this pins decision 1)
- `test_a_string_with_no_block_at_all`
- `test_a_light_block_in_place_of_the_exchange_block`
- `test_an_intact_block_of_another_session` (`block_for_sid`)
- `test_every_difference_is_named_at_once`
- `test_a_crlf_block_is_read_as_take_reads_it_and_printed_as_bale_sent_it`
- `test_the_recorded_block_is_vouched_for`

In section 6: `test_a_block_twine_cannot_vouch_for_through_the_real_seam`,
which runs `StubBale` replaying the edited line, as
`test_a_recorded_refusal_through_the_real_seam` does for a refusal.

To check the tests test the change, I ran the new file against the old
`carry_bale.py`, with no-op stubs for the two names it imports. 16
cases fail, counting subtests. The CRLF test and the recorded-block
test pass on both trees, which is what they are for: they pin ok
behaviour that must not move.

## 4. validation.sh

It runs from the staged root, with `python3 -I -B` throughout. It
writes only under `.validation-logs/<ts>/`, with `TMPDIR` pointed
there, and it never reads `claude/checkpoints/`. The one tree walk, the
`__pycache__` sweep, prunes that directory and the logs. It checks:

- file syntax: `ast.parse` on the two `.py` files, and `tomllib` on the
  manifest.
- the suite: it must report OK, with at least 568 tests. That is
  stricter than the brief's 536, because 568 is what this tree has.
- `bin/twine carry exchange` end to end, against a stub root it writes,
  with `bin/VERSION` set to the pin read from the manifest:
  - The recorded `relayed` line: exit 0, and human stdout `cmp`-equal to
    its `block`. The stub's argv is `relay <sid> - --json`, and its
    stdin is `cmp`-equal to the block.
  - The same line with the block's body edited (round 1 → 2): exit 1,
    one line, `NOT OK`, naming `(mismatch)`, with no `BALE EXCHANGE`
    on stdout and no traceback.
  - The same edited line under `--json`: one line, not ok, `outcome`
    `relayed`, `relay` and `stdout` equal to the line, and `refusals`
    empty.
- the untouched set by sha256: 40 files hashed from the tree I was
  given. These are `bin/twine`, `share/transitions.toml`,
  `carry_bundle.py`, `inflight.py`, `kill.py`, `commands/core.py`, and
  all 34 files under `fixtures/` (its README included), plus a check
  that nothing was added under `fixtures/`.
- `twine-seed.md` is not in the request's tree, so I can't hash it,
  the same limit carry-exchange-json-001 hit. The script checks
  instead that `changes[]` does not name it, read from
  `.bale-manifest.json`. Outside staging, it reports `[SKIP]` with that
  reason.
- `VERSION` is `cmp`-equal to `0.12.0\n`.
- there is no `__pycache__` in the tree.

I ran it twice, as §7.2 asks. On a staged copy with `files/` overlaid
and the manifest in place, every check passes (about 41 s, nearly all
of it the suite). On the unmodified tree, the suite floor, both
edited-block checks and `VERSION` fail. The recorded-line check, the
untouched set and the `__pycache__` check pass on both, because they
are invariants. I claim only the suite (`pass`, observed), per §5.3's
project-level rule. `tools/response_lint.py` reports the response
CLEAN.

## 5. The seed annotation (out of scope here; for tidy7)

This goes at the end of §5.1's road annotations, after the last one
there. Verbatim:

> [2026-10-08-twine-exchange-vouch-005: `twine carry exchange` vouches
> for the block bale hands back as it vouched for the block it carried
> in — the line's `block`, read as `take` reads text (CRLF→LF, then the
> §9.2 scanner), must be exactly one block (its own lines and nothing
> around them; a missing final newline, which human mode supplies, is
> tolerated) of kind `exchange`, intact by `take`'s rule, and naming the
> carried block's sid, or the verb is NOT OK, exit 1, each failure
> appended in `take`'s fault words or the session's own, `outcome` still
> `relayed` and the line still whole in `relay`; a block twine cannot
> vouch for is never printed and never repaired. Nothing before the line
> is read moved: the refusals, the one relay argv, stdin, timeout, cap
> and the pin gate. The new doubles are relayed lines whose `block` is
> named as not bale's (the recorded block is intact). `VERSION` 0.12.0.]

## Proposals

**What.** Give the relay surface's `doubles` string in
`share/bale-consumption.toml` a clause naming the new vouch doubles,
next to the "edited lines" it already lists.
**Why.** This session left the string alone because the brief said
"nothing else in the file". The string is still true, but a reader
looking for the vouch doubles finds them only in contract §11.4. The
pin bump, which already rewrites this surface, is a natural place to
add the clause.
**Scope hints.** That one string, during the pin-bump session.

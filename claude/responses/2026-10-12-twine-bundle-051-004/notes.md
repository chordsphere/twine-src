# Notes — 2026-10-12-twine-bundle-051-004

`carry bundle` now reads the two facts of bale 0.4.50's open line it used to
ignore. Every path is inside the forecast. `claude/INDEX.md` is the one
forecast file I left alone: no sentence in it became false. Its in-flight
paragraph still holds ("where a second desk finds the request tarball when
bale's `second-desk` line does not name one").

## 1. Decisions for you to ratify (brief §4)

**1. The refusal's wording, and the mismatch failure.** An `open-refused`
line fails with

    bale refused the open (outcome 'open-refused', reason 'not-found'): "<cause>"

This follows `bale exited 1`. It is modelled on `carry exchange`'s
relay-refused sentence, with the code added inside the parentheses. On
`open-refused` it **replaces** the "an open wants 'opened' or
'second-desk'" mismatch rather than standing beside it. That sentence would
only restate what the outcome already says, and under `--check` it would
read "--check wants 'rehearsed'", which misdescribes a refusal. Every other
outcome keeps the mismatch failure. The edge cases:

- A code or cause that is absent, null, empty or not a string reads
  `no reason code` / `its line names no cause`. You never see a quoted
  `"None"`.
- If the key itself is deleted, the key check names it as well.
- The reason never says "the session may be open", because a refusal
  opened nothing.
- The code is named and never validated against a list. The manifest
  doesn't carry OPEN_REFUSAL_REASONS; see Proposal 1.

**2. `tarball_source` stays `"bale"` / `"record"` / null.** The field says
where the *twin's* `tarball` came from. On the append-keeps-own path that
is bale's value, because the twin hands this desk what bale printed for it.
A third value would describe the record instead of the twin. So that the
difference isn't silent, `record()` writes one stderr line when the record
keeps a tarball that differs from bale's:
`the in-flight record keeps its own tarball X; bale's line names Y`.
`inflight._compose` logs the adopt and keep-own cases at info.

**Smaller calls:**

- The fresh-record sentence now ends `bale's tarball` or
  `tarball null (bale's line names none)` instead of a flat `tarball null`.
- I refreshed the `(~line N)` section pointers in `kill.py` and
  `carry_bundle.py`. They had drifted 4–37 lines before this session.
- `kill.py`'s two comments now cite the 0.4.51 recordings and keep "first
  recorded at 0.4.49".
- `inflight.py` keeps the history ("bale 0.4.49's `second-desk` line
  carried `tarball` null …") and says 0.4.50 names the tarball.

## 2. Where to look on review

- `twine/inflight.py` `_compose`: the three second-desk rules, about 20
  lines.
- `twine/commands/carry_bundle.py`: `read_line`'s early return on
  `open-refused`, which sits after the key check so a refused line lacking
  `cause` gets both failures, and `refusal_failure`.
- `share/bale-consumption.toml`: the open keys are eight now. That makes
  the key check demand `reason` and `cause` on *every* open line, `opened`
  and `rehearsed` included. All four 0.4.51 recordings carry both (null
  unless refused), and bale 0.4.50+ prints them on every outcome. The
  0.4.49 recordings lack them, but nothing replays those through the key
  check.

## 3. Tests: what moved, what is new (suite 639 → 658, OK, 3 skipped as before)

**Moved** (an assertion changed to the new rule):

- `test_carry_bundle.NotOk.test_the_recorded_refusal_is_not_ok_and_records_nothing`
  is now `test_the_recorded_refusal_names_bales_code_and_quotes_its_cause`.
  It asserts the exact reason and human line; it used to assert that
  neither the code nor the cause appeared.
- `test_carry_bundle.SecondDesk.test_second_desk_with_no_record_writes_a_fresh_one_and_says_so`
  is now `test_second_desk_with_no_record_writes_a_fresh_one_holding_bales_tarball`.
  This is the test whose docstring said "this test pins that it stands
  until then" (pin-051's "until twine-bundle-051"). The record's
  `tarball` is now bale's, where it was null.
- `test_carry_bundle.SecondDesk.test_second_desk_over_a_record_that_is_not_one_replaces_it_naming_why`
  keeps its name. The fresh record now holds bale's tarball instead of
  null, and the twin's tarball/source are asserted too.
- `test_carry_bundle.SecondDesk.test_bales_tarball_wins_when_its_second_desk_line_names_one`
  keeps its name. Its assertions already were the new rule's keep-own case.
  The docstring now cites the rule, and it gains the stderr line naming
  both tarballs.
- `test_carry_bundle.TheKeysOnTheLine.test_an_opened_line_lacking_a_listed_key_is_not_ok_and_not_recorded`:
  its loop gains `reason` and `cause`.
- `test_consumption_manifest.SurfacesAreWalkable.test_open_json_is_read_by_carry_bundle`:
  the open keys are eight, every open recording carries them, and the
  note's needles follow the rewritten sentence ("reads neither" must be
  gone).

**New (19):**

- In `NotOk`:
  - `test_a_refused_line_with_cause_null_says_no_cause` (null, "", 7)
  - `test_a_refused_line_with_no_reason_code_says_so`
  - `test_the_cause_is_quoted_never_dispatched_on` (the `unclassified`
    code, and a cause that reads like an open)
  - `test_a_refused_rehearsal_is_named_the_same` (`--check`)
  - `test_a_refused_line_lacking_reason_or_cause_fails_the_key_check`
- In `SecondDesk`:
  - `test_a_fresh_second_desk_record_is_null_only_when_bales_tarball_is`
  - `test_an_appended_record_with_no_tarball_adopts_bales`
  - `test_an_appended_record_is_handed_on_when_bales_line_names_none`
    (the `"record"` source, kept)
- In `TheRecordModule`, `_compose` through `record_open`, seven tests:
  - fresh keeps bale's
  - fresh is null only when bale's is
  - fresh over a non-record keeps bale's
  - appended adopts
  - appended keeps its own (against bale's differing, equal, and null)
  - appended with neither stays null
  - `opened` unchanged
- New class `EndToEndRefusalAndTarball`, a subprocess against `StubBale`,
  four tests:
  - the recorded refusal (exit 1): NOT OK in the twin and the human line,
    nothing under the state dir
  - second-desk into an empty state dir
  - appended adopting
  - appended keeping its own

Every double is built from a recording's bytes and named as one.
`tests/helpers.py` changed in its docstring only.

## 4. Validation

`validation.sh` runs from the staged root under `python3 -I -B`. It writes
only under `.validation-logs/<ts>/`, and its one tree walk prunes
`claude/checkpoints/`.

I ran it twice on base + `files/` + this manifest as `.bale-manifest.json`:
all eight checks passed both times, and all seven claims agreed. Hence
`claim_basis: observed`. On the unmodified tree, every change-specific
check fails: suite count 639, both e2e runs, the session assertions, and
VERSION. The guards pass on both trees, as guards should: syntax, the
untouched files, no `__pycache__`.

One gap: `twine-seed.md` wasn't in the request, so I couldn't pin its
sha256. The script checks it with `git diff --quiet HEAD` when staging is a
work tree, and through the staged manifest's paths otherwise. In my
simulation it took the manifest path. The fixtures are checked per file
against the 91 sha256s the request carried, and by git when it is
available.

The suite count: the brief says "≥ the count you were given", but no count
was given. I measured 639 on the base tree and assert ≥ 658, the count this
response ships.

## 5. Seed annotation (for tidy8)

For `twine-seed.md` §5.1, at the end of its road annotations, verbatim and
complete:

> `carry bundle` reads 0.4.50's open line: the refusal named with its code and cause, the second-desk tarball kept, `VERSION` 0.15.0.

The brief's wording ends "the `VERSION`"; I read that as "name the
version" and filled it in. If tidy8 wants the brief's words unfilled,
they're the same sentence ending "the `VERSION`."

## Proposals

**1. Record the open refusal's closed set on the surface.**

- **What:** add `reasons` and `reasons_home` (OPEN_REFUSAL_REASONS,
  bin/bale_report.py) to the open surface in `share/bale-consumption.toml`,
  as the relay surface carries RELAY_REFUSAL_REASONS.
- **Why:** the note says "15 codes with the fallback unclassified", but
  only `not-found` is written down. With the list, a test could pin that
  the recorded code is one of bale's, and a later courier axis could key on
  it. I couldn't add it: the request doesn't carry bale-src's list, and
  guessing at it is exactly the drift the manifest exists to prevent.
- **Scope hints:** `share/bale-consumption.toml`,
  `tests/test_consumption_manifest.py`; needs the list from bale-src (a
  read, not a recording).

**2. One refusal sentence for the courier verbs.**

- **What:** when `carry exchange` starts reading relay's `reason` (out of
  scope here), shape its sentence as `carry bundle`'s now is, with the code
  inside the parentheses. Consider one helper in `carry_bale.py` that both
  verbs call.
- **Why:** the two sentences now differ only by the code. A shared helper
  keeps the "never dispatch on the cause" rule in one place.
- **Scope hints:** `twine/commands/carry_bale.py` `read_relay_line`,
  `twine/commands/carry_bundle.py` `refusal_failure`; after the
  relay-reason session.

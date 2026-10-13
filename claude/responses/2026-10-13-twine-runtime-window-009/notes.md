# Notes — 2026-10-13-twine-runtime-window-009 (Arc 2 R5)

Built on the 0.21.0 base the brief names (the two predecessor sessions
applied): every "what exists" fact in the brief held there, though the brief
says it verified them at 0.19.0. The base suite was **1047** tests (the brief
expected ≥ 1027); the landed tree runs **1113**, all OK (5 skipped, as on the
base), under `python3 -I -B -m unittest discover -s tests -t .`.

No probe, no light block, no clarification this session.

## The four decisions the brief left me

- **Module names.** `twine/runtime/window.py` (`IMPLEMENTS =
  ("window-accounting",)`) and `twine/runtime/resume.py` (`IMPLEMENTS =
  ("suspend-resume",)`), both directly under `twine.runtime`, the
  `sandboxing` form.
- **The `/v1/models` read: one call per spawn**, held on the adapter
  instance (`AnthropicAdapter.context_window()` memoizes; `window_calls`
  counts). Not a per-process cache: a spawn is the unit D12 fixes constants
  on, and a process that spawned two adapters for two models should ask
  twice. The verb asks only when `--window` is absent.
- **The clarification tarball's name in the home:**
  `escalations/<k>/response-<sid>.tar.gz`, built from
  `escalations/<k>/response-NNN/`, `k` the first free integer — so a session
  that escalates in several rounds keeps every round, and a later normal
  `response-<sid>.tar.gz` the worker builds at the home's top cannot collide
  with one.
- **`resume` in its own module**, `twine/commands/resume.py`, reusing
  `run.py`'s `RunReport`, `build_adapter`, `deliver`, `finish_running`,
  `lines` and the new `spawn_window`/`window_refusal`/`WINDOW_ARGUMENT`.
  `RunReport` grew `command`, `window`, `resumed_from`, `resume_sid` and a
  `rewarm` property; it is the one twin for both verbs.

## Where I went past or against the brief — please ratify or correct

1. **The `sent: false` line is generalized (an R4 gap the resume exposed).**
   R4 wrote it only after a tool-calling turn that ended the run. The final
   assistant turn of an `end-turn` ending — prose, or **a light block in the
   final text, which is a suspension** — was appended to the loop's messages
   but never to any `request` line, so a rebuild from request lines would
   have resumed a conversation missing the model's own question. `Loop.run()`
   now writes one last `request` line, `sent: false`, whenever the run ends
   with messages no line holds (this also covers the tool results a window
   stop leaves unsent). The visible change: an end-turn ending's transcript
   gains a `request` line before `run-end`; `tests/test_run.py`'s order test
   says so. Look here first.
2. **The rebuild takes the last conversation, not literally "every request
   line".** A `run-start` without `resumed_from` (a second desk's `twine
   run`, which starts over from the opener) resets the join; a resumed one
   continues it. Joining across a fresh restart would hand the model two
   openers. Each line's `messages_total` is checked against the join so far,
   so a missing or reordered line refuses rather than re-warms garbage.
3. **A call whose input side is 0 keeps `used`.** A retry stop the provider
   answered with no usage (a 429, a socket timeout) reports zeros; taking
   that as "0 tokens in use" would un-warn a warned run. Every prompt carries
   the system note, so a zero is an uncounted call. The `window` line carries
   `call_input` (the call's own count) beside the brief's five keys so the
   difference is visible.
4. **One `window` line per call that returned a turn.** An adapter-defect
   call has no turn and no usage, so it gets none (its transcript tail is
   R4's `adapter-error`, `move`, unchanged).
5. **`twine resume`'s `--cap` and `--answer` are not argparse-required**: the
   brief lists both among the refusals named "every reason at once", which
   argparse's exit 2 would pre-empt. `run`'s `--cap` stays argparse's (R4).
   I also added **`--model`** to `resume`'s flags: the brief's synopsis omits
   it, but its refusal list names it (given and differing → refused; given
   and equal → accepted).
6. **The twin's three new fixed names follow `open`**, so R4's order (and
   `tests/test_run.py`'s positional `TWIN_KEYS` check) holds: `…, open,
   window, resumed_from, rewarm`, then the names beside, which gain
   `window_reason` (why the size is unknown). `window` is null only when the
   run refused before the adapter was spawned.
7. **Extra transcript keys:** `run-start` carries `window` (`size`,
   `source`, `reason`, `warn_fraction`) and `resumed_from` (null on `run`);
   a resume's adds `answer` (source, sha256, length — the text itself is in
   the next `request` line) and `rebuilt`. `check` carries `input_basis`
   (`counted`/`estimated`).
8. **Resume refuses a few things the brief did not list**, each because the
   alternative is silently wrong: the record's transcript not this state
   directory's; the sandbox home missing, not this state directory's, or
   holding no `request/` (a resume does not unpack again); a torn last
   transcript line (the tail may be gone).
9. **escalate's clarification form, the details:** rows may span lines (the
   one-line rule is the light tier's); `summary` is generated — the request
   manifest's `goal` plus that the worker is blocked; **the request's lint is
   run in the cage too** after filling (a finding is an error result naming
   each; a request without the lint is tolerated, logged and said in the
   result); the crafter and lint run on `sys.executable` (the interpreter
   twine runs on, known ≥ 3.11) rather than whatever `python3` the cage's
   PATH holds; the input schema lost `maxItems: 3` (the light count moved
   into the executor, and its error now names `blocking: true`). The
   suspended twin's `move` is the `apply-outcome` row's for `dry-run`
   (`operator-applies`, the operator's) — the brief pinned `tarball`,
   `apply_line`, `dry_run` and `block` but not the move; this is what
   `delivered` reports for the same dry run.
10. **Each run counts its own window.** A resumed run's `used` is 0 until its
    first call reports (that call is also the `rewarm`), and its first
    pre-call cap check prices the whole-request estimate.
11. **The warned-window log line is INFO**, not WARNING: the operator's view
    is the default stderr progress line (`call N: the window runs thin — …`),
    and a WARNING would print on every in-process test that warns.

## Something the brief got slightly wrong

The bale fact: "a double built from the recorded dry-run line with
`verdict`/`merge` nulled stands in". The recorded `dry-run` line
(`fixtures/bale-0.4.51/scratch/apply_--dry-run_--json_tarball+dry-run.json`)
already carries `verdict: null` and `merge: null`, so the stand-in is the
recording unchanged. `tests/test_resume.py`'s docstring and cli-contract
§19.6 name it as standing in for the clarification fork, not a recording of
it.

## A judgment call you may not want: bale's tools vendored into tests/

The clarification form runs the **request's** crafter and lint, so a test
needs them in its request tarball, and nothing in this repo carried them
(`fixtures/` holds recordings and was off-limits anyway). I copied the two
request-carried tools verbatim from this request (bale 0.4.52) to
`tests/bale_tools/craft_response.py` and `tests/bale_tools/response_lint.py`
(~5,900 lines of bale's code), pinned by sha256 in `tests/helpers.py`
(`BALE_TOOLS_SHA256`) and held by `tests/test_resume.py`
(`ThePinnedBaleTools`). Nothing under `twine/` reads them. The alternative —
a crafter double named as such — would test the wiring but not the shape
bale actually emits, which is the point of D13. If you'd rather not carry
them, the tests that use them are `EscalateClarification` (test_runtime_tools)
and `TheClarificationForm` (test_resume); everything else stands without.

## Validation

`validation.sh` ran on the landed tree (staged copy, `bash validation.sh`
from its root): every check PASS, 2 min 06 s, the claims reconciliation
`[SKIP]` outside bale's staging; nothing written outside
`.validation-logs/<ts>/` (diffed against the tree afterwards) — `TMPDIR`
points into it, so the suite's temporary state directories land there too.

On the unmodified base: the session-specific checks FAIL as they should
(syntax of the new files, both registries, the four end-to-end outcomes,
VERSION, the docs). Three PASS on both, by design — they are the invariants
the brief asks to hold, not tests of the change (TARBALL.md §7.2's "passes on
both" rule read accordingly): no stop key spelled under `twine/runtime/`, the
untouched paths, and the suite at ≥ 1047.

Two things about the script you may trip on: the stop-key sweep exempts a
tool module's declared argument names, as `tests/test_runtime_tools.py`'s own
guard does (`shell`'s `timeout` argument is not the stop key); and the
untouched-paths check pins the sha256 of every file under `fixtures/` and
`share/` **that this request carried** (141 files with `twine-seed.md` and
`bin/twine`) — a file your tree has there that the request did not ship is
not checked. The suite is ~2 minutes and runs unconditionally, because the
brief requires it.

## Seed annotation text for tidy10 (verbatim, complete)

Under §5.2, after R4's bracket:

> [2026-10-13-twine-runtime-window-009: R5 landed — window accounting and
> cold resume (D23). The window: `twine run --window N` fixes its size, or the
> adapter states it at spawn (`Adapter.context_window()`, a
> `WindowStatement`; the Anthropic adapter's one `GET /v1/models`, its
> model's `max_input_tokens`; the fake's unknown — counted, never warned or
> stopped on); after each call `used` = the call's `input + cache_read +
> cache_write`, one `window` transcript line per call; at 80% the run is
> warned and every tool result the model reads ends with the warning line,
> never the transcript's `tool-result` line; at 100% the next call is not
> made — `stopped`, `window-exhausted`, `split-goal`, before the cap check;
> the cap check prices the count plus what was appended since. Cold resume:
> `twine resume SID --cap USD --answer FILE|-` rebuilds the conversation from
> the transcript's `request` lines, appends the answer as one user message
> and runs the loop again under the same sid in the same sandbox home with
> the transcript's spawn-time constants, no `bale open`; the twin's `rewarm`
> is the first call's usage. `escalate` gained its clarification form
> (`blocking: true`): bale's request-carried crafter and lint in the cage,
> the response tarball in the home, `carry response` on it, the run
> `suspended` on its apply line. `window-accounting` and `suspend-resume`
> `implemented`, by the runtime (`twine/runtime/window.py`,
> `twine/runtime/resume.py`). `VERSION` 0.22.0.]

Under D23 (after its 2026-10-01 bracket):

> [2026-10-13-twine-runtime-window-009: landed — a suspended session goes
> cold and `twine resume` re-warms it from its transcript with the planner's
> answer appended; the re-warm cost is the twin's `rewarm`, the resumed run's
> first call's usage in the five classes; holding hot stays the effort
> machinery's later knob.]

Under TQ-1 (after R4's bracket), one sentence:

> [2026-10-13-twine-runtime-window-009: the transcript gained the line kind
> `window` (each call's counted window) and is now what `twine resume`
> rebuilds a conversation from, its last `request` line `sent: false`
> whenever a run ends with messages never sent.]

Under §4.3, after "Window management", one sentence:

> [2026-10-13-twine-runtime-window-009: landed — counted from each call's
> usage, warned as the last line of every tool result at 80%, and exhausted
> as `window-exhausted` → `split-goal` before the call past it
> (runtime-contract.md §7.4).]

Under §4.3, after "Suspension and cold resume", one sentence:

> [2026-10-13-twine-runtime-window-009: landed — `escalate`'s clarification
> form suspends a run on a response tarball, and `twine resume` re-warms the
> transcript on the answer (runtime-contract.md §6.6, §7.9).]

## Proposals

- **What:** Record bale's `apply --dry-run --json` line for a clarification
  tarball and swap the stand-in. **Why:** the clarification fork prints its
  own stderr and may differ from a normal dry run in ways the tests cannot
  see; the brief already names it the architect's, by probe. **Scope:**
  fixtures/bale-0.4.5x/, `tests/test_resume.py`'s `DRY_RUN` use.
- **What:** Have escalate's clarification form also render the paste-block
  courier (`craft_response.py --emit-block` on the filled manifest) beside
  the tarball, and carry it. **Why:** TARBALL.md §5.9.2 says a formal ask
  ships both transports so the operator picks the courier at carry time; the
  brief pinned the tarball and `block: null`, so I built only that.
  **Scope:** `twine/runtime/tools/escalate.py`, the twin's `block`.
- **What:** Update AGENT.md §11.7's `twine run` surface row. **Why:** it
  says "until twine's window accounting warns the worker as a tool result, no
  warning reaches it before the edge" — no longer true; and the row should
  name `twine resume` for both a light block and a clarification. It is
  bale-src's doc (D21's annotation: twine owes bale-src the row), so a
  bale-src session.
- **What:** Mention the window line and `blocking: true` in the surface
  note. **Why:** the model learns both only from tool descriptions and the
  first warned result; the note is the one place twine tells a worker how the
  session works. **Scope:** `twine/runtime/loop.py` `SURFACE_NOTE` — a
  prompt-cache-stable constant, so a deliberate, ratified change; I left it.
- **What:** Refresh the repository README's "What exists". **Why:** it
  predates R5 (it was outside this forecast, so I did not touch it).

# Notes — twine-run-ergonomics (session 2026-10-15-twine-run-ergonomics-002)

All eight outcomes landed; `VERSION` is 0.24.0. The suite is 1209 tests under
`python3 -I -B -m unittest discover -s tests -t .` (the base in the request was
1154), green, five skipped as before. `validation.sh` ran clean in a staging
copy of my tree. `fixtures/`, `share/`, `twine-seed.md`, `bin/twine` and
`twine/probing.py` are byte-identical to the request's (checked by digest in
`validation.sh`); `carry probe`'s 256 KiB and `read_file`'s refusal are untouched.

## Step one: the reader's fault text (call 93)

I probed for the line first. The paste-back failed the integrity check (my
block printed no trailer, my mistake), but the candidate block it quoted held the
line, and I read it as text, not as verified output. The turn line for call 93
of `2026-10-13-twine-runtime-window-009`:

```
{"at": "2026-10-13T19:02:38Z", "seq": 569, "kind": "turn", "call": 93, "turn": {"text": "", "thinking": null, "tool_calls": [], "stop": "malformed-shape", "usage": {"input": 2, "output": 15764, "thinking": 236, "cache_read": 368782, "cache_write": 1801}, "provider_stop": null, "content": [], "retry_after": null, "request_id": "req_011Cfzkcb4wLkVZw9hCHZK7P", "reason": "message_stop with block(s) [1] still open: a 200 whose body is not JSON or SSE, or not the documented shape: a message without content, stop_reason or usage, a content block of an unknown type, a usage the mapping refuses"}}
```

It agrees with the diagnosis: block 0 closed, block 1 open, `output + thinking` =
15764 + 236 = 16000 exactly the old ceiling, and `provider_stop` is null because the
reader raised before `_finish` ever read `message_delta`'s `stop_reason`.

## What changed, and the decisions that were mine

1. **Reader** (`adapters/anthropic.py`, `_cut_blocks`). At `message_stop`, an open
   block with `stop_reason` `max_tokens` is a `max-tokens` turn. Open `text` and
   `thinking` blocks are carried as far as they got; an open `tool_use` block is
   carried only if its joined input parses as an object (a ceiling that fell
   between the last piece and the stop), else it is left out and its
   `{"id", "name", "partial_json"}` goes on the `Turn` as `cut_tool_call`. An
   opened-but-empty tool_use is not carried either (an empty join is "nothing
   arrived", not `{}`). Any other `stop_reason` keeps `malformed-body`. The key
   I named in the transcript's `turn` line: **`cut_tool_input`**. Both new keys
   sit at the line's top level beside `turn`, not inside it (`Turn.as_json()` is
   unchanged and pinned).
2. **Continuation text** (`loop.py`): `CONTINUE_TEXT`, then, when a call was cut,
   `CUT_CALL_TEXT`: "The <name> call you were writing was cut off before its input
   was complete, so it was not run. Make it again in smaller pieces: write a large
   file in parts, never all in one call." Same text block, so the window line (when
   warned) still ends it. A test sends the continued conversation through the
   real adapter's `build_request` and the boundary and compares the body to
   `build_request`'s own output.
3. **Raw stream.** The adapter hands the bytes over (a `_Drawn` tee on the stream's
   chunks, or the joined body) only when the Outcome is the `malformed-body`
   condition, on `Outcome.raw` → `Turn.raw`; the loop writes
   `<state-dir>/transcripts/<sid>.call-<N>.raw` (0600) through
   `transcript.write_raw` and the `turn` line carries `"raw": "<path>"`. I chose
   "loop writes what it got through the Turn" over "adapter writes and names it",
   so the adapter needs no state directory. A write failure is named (`raw: null`,
   `raw_error`), never silent. I also taught `transcript.list_transcripts` to skip
   `<sid>.call-<N>.raw`, otherwise `twine status` would report every kept file as a
   fault of the state directory.
4. **`--max-tokens` 32000**: `run.DEFAULT_MAX_TOKENS`, help text, cli-contract
   §18.1. `resume` needed no change (default `None`, refuses only a differing
   value); `tests/test_resume.py` expected 16000 in two places and now says 32000.
5. **Surface note**: one new paragraph and an extended escalate sentence; all
   seven stems are held by `TheSurfaceNoteSaysWhatItMust`, and nothing about the
   model, provider, task or sid. It is the one edit; I changed nothing else in it.
6. **`shell`**: `SHELL_CONTENT_CAP_BYTES = 32768`; `cut_stream` cuts on a character
   boundary and writes the marker on its own line, so when the cut falls mid-line
   the stdout part of `content` is 32768 bytes plus one separating `\n`. The
   seam's kill at 256 KiB is still `SHELL_STDOUT_CAP_BYTES`, its exit line reworded
   from "above is cut there" to "is cut there" (the output above is no longer
   "the cut"). Stderr is cut the same way under its own marker. Result fields are
   whole, as before.
7. **Progress lines** (stderr, both verbs):
   - a returned turn: `call N: asks for X — $2.00, 33s, window 1000000 of 2000000`
     (window only when its size is known; `$?` unpriced; four decimals under a
     cent so a cheap first call is not `$0.00`);
   - tool lines come in two: `call N: tool shell: running — <cmd>` and
     `call N: tool shell: ok — <cmd>`, the argument cut after 80 *characters* with
     `...` after the cut and whitespace folded to one line;
   - heartbeat: `call N: tool shell: still running, 30s — <cmd>`, from a daemon
     thread started per tool and joined before the tool's end line, interval
     `HEARTBEAT_SECONDS = 30` (an argument of `Loop` so tests shorten it). Verified
     once for real with a 33-second `sleep`: one heartbeat at 30 s;
   - summary: `summary: delivered, move operator-applies, 4 calls, 4 tool calls,
     0 retries, $2.00, 0s` as the last line. It is printed from the verbs, after
     their closing line, **also on a refusal** (`summary: refused, 0 calls, …`):
     the brief says "every run", and a refused run is an outcome in the twin. Say
     if you want that dropped.
   The window-runs-thin and retry lines carry the same figures in brackets.
8. **Clarification form**: `escalate` runs `craft_response.py --emit-block
   <dir>/manifest.json` in the cage after the tarball is built, reads the output
   back with `twine.shapes` (one intact `exchange` block for the sid), and returns
   it as the new `block` result key and as the twin's `block`; `content` is the old
   sentence plus the block. `lines()` now prefers the apply line over `block` for
   a suspended run, so stdout stays the apply line alone. I leave `--round` at the
   crafter's default 1; I do not know how bale numbers a second escalation's round.
9. **Docs**: runtime-contract §1.1, §5.4, §6.2, §6.6, §7.2, §7.4, §7.6; cli-contract
   §18.1, §18.4, §18.5, §18.7, §18.8. The table's `continue-turn` description is
   unchanged.

## Paths outside the write forecast (each also in `forecast_departures`)

- `twine/runtime/boundary.py` — `Turn` gained `raw` and `cut_tool_call` (both
  default `None`, absent from `as_json()`, type-checked in `turn_faults`). The
  raw bytes and the cut call have no other way to reach the loop than through the
  Turn; the brief's own allowance ("the loop writes nothing it did not get
  through the boundary's `Turn`") needs the field.
- `README.md` — one sentence said `shell` has "a 256 KiB stdout cap"; it is now
  the 32 KiB cut and the seam's 256 KiB kill. A stale statement of the behaviour
  this session changes.

`tests/test_window.py` is in the forecast and I did not need to touch it.

## Judgment calls to ratify

- **An open `thinking` block is carried as far as it got**, per the brief, with
  `signature: ""` when none arrived (the signature is the last delta). The API
  may refuse an unsigned thinking block on the next call. I followed the brief and
  did not guess; if it proves refused, dropping an unsigned open thinking block in
  `_cut_blocks` is a three-line change. No recorded stream shows it.
- `adapters/anthropic.py`'s own `DEFAULT_MAX_TOKENS` (the adapter's default when a
  caller gives none) stays 16000: only `run`'s default was asked, and a test ties
  the adapter's to the models listing.
- I wrote no recording of the ceiling-inside-a-block stream (the architect's, by
  probe). Every specimen in `tests/test_anthropic.py` is built in the test and
  named DERIVED: `max_tokens_stream` with its last `content_block_stop` removed,
  plus streams assembled from that recording's head and tail.
- A weak spot: `TheHeartbeat.test_the_heartbeat_counts_the_clock_it_is_given`
  only shows that an injected clock feeds the elapsed figure; the cadence itself is
  held by the shortened-interval test and the one real 33 s run.

## Proposals

- **What**: number the raw file and the transcript's `call` lines so a resumed run
  cannot overwrite an earlier run's `<sid>.call-<N>.raw`. **Why**: a resumed loop
  restarts `n` at 1, so a malformed call 3 in the resume replaces the file of
  call 3 from the first run; I documented it (§7.6) rather than change the
  pinned name. **Scope**: `twine-run-recovery` forecasts the same files; the
  resume rule is its to settle.
- **What**: have the architect record the ceiling-inside-a-block stream (and an
  unsigned open thinking block, if the model will produce one). **Why**: the reader's
  open-block rule stands on a derived stream, and the thinking case is a guess
  about the API's refusal.

## Seed annotation for the next tidy (twine-seed.md §5.2, after gate-contract's bracket, or R5's if that is not there yet)

[2026-10-15-twine-run-ergonomics-002: the hardening wave's first session — eight
outcomes. (1) The stream reader takes `message_delta`'s `stop_reason` before it
judges an open block: a stream that ends at the output ceiling inside a block is a
`max-tokens` turn (the table's `continue-turn`), its closed blocks and an open text
or thinking block kept, an open `tool_use` block whose input does not parse left
out and its partial input put in the transcript's `turn` line under
`cut_tool_input`, and the continuation turn says a tool call was cut off, so the
model writes the file in parts; with any other `stop_reason` an open block stays
`malformed-shape`. (2) On any `malformed-shape` the response body the transport
drew is kept at `<state-dir>/transcripts/<sid>.call-<N>.raw` (0600) and named in
the `turn` line's `raw` key. (3) `--max-tokens` defaults to 32000. (4) `SURFACE_NOTE`
gained its six things — list the home first, read ranges never whole files, write
large files in parts, never background a command and poll it, the lint judges the
manifest, the window line and `escalate`'s `blocking: true` form exist — the one
deliberate edit of the cache-stable constant. (5) `shell`'s content cap is 32 KiB
(stdout and stderr each), the cut marked `[stdout cut at 32768 bytes of <total>;
read it in parts]`, the command not stopped there; `read_file`'s and `carry
probe`'s 256 KiB stand. (6) The progress lines carry the run's cost and elapsed
time on each returned turn, the window once counted, what each tool runs (80
characters), a 30-second heartbeat while a tool runs, and a last `summary:` line.
(7) The clarification form also renders its exchange paste block, the twin's
`block`. (8) The contracts (runtime-contract §1.1, §5.4, §6.2, §6.6, §7.2, §7.4,
§7.6; cli-contract §18) say all of it. `VERSION` 0.24.0.]

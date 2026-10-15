# notes — 2026-10-15-twine-run-telemetry-004

Everything in the brief landed. The suite is 1309 tests (base 1249) green
under `python3 -I -B -m unittest discover -s tests -t .`; `VERSION` is 0.26.0.
Every changed path is inside the write forecast (`twine/`, `tests/`, the two
contract docs, `claude/INDEX.md`, `README.md`, `VERSION`), so there is no
`forecast_departures`. `fixtures/`, `share/`, `twine-seed.md` and `bin/twine`
are untouched — `validation.sh` compares every file of the request's by sha256.

## What is where

- `twine/runs.py` — the `runs.jsonl` writer (one `O_APPEND` write and an fsync
  per line, 0600, a torn tail ended with an LF rather than glued onto), the
  validator that pins the thirty-two keys and their order, the reader (a bad line
  is a `line N: …` fault and the reading goes on) and the aggregation `twine
  stats` renders.
- `twine/cost.py` — the cost file (`<state-dir>/cost/<sid>.json`, dir 0700, file
  0600, temp file + fsync + `os.replace`), and `costed_apply_line`.
- `twine/transcript_view.py` — reads a transcript with line numbers and renders
  the per-kind summaries. `twine/commands/telemetry.py` — the two verbs.
- `twine/bale.py` — `apply_cost_line` beside `apply_line`.
- `twine/runtime/loop.py` — `LoopResult` gains `tools`, `continuations` and
  `heartbeats`; the tool time is measured around `run_tool` in
  `run_tool_beating` (so a probe hop in the final text counts too).
- `twine/commands/run.py`, `resume.py` — `RunReport.run_record`,
  `write_run_line`, `deliver(…, report)` writing the cost file before the line,
  `name_next` writing it before bale's admit line. `twine/recovery.py` —
  `admit_line` and `next_commands` take the cost file; the clarification form's
  `next` is now `[apply line, resume line]`. `twine/commands/core.py` — the
  eighth boolean.
- Docs: cli-contract §18.7a (the cost file), §20 (`runs.jsonl`, `twine stats`),
  §21 (`twine transcript`), and the lines of §2, §4, §18.5–§18.7, §19.4–§19.5;
  runtime-contract §7.7; INDEX's state-directory bullet and explainer; README.

## Choices I made that you should ratify

1. **Module placement.** `twine/runs.py` for the record, `twine/cost.py` for the
   cost file, `twine/transcript_view.py` for the story, one `commands/telemetry.py`
   for both verbs. Not `durable.py`, not inside `transcript.py` (the story
   reader needs `twine.runtime.loop`'s `tool_argument`, and `loop` imports
   `transcript`, so the reading could not live there without a cycle).
2. **`desk`.** The brief says integer or null; bale spells a desk `desk-N` (the
   second-desk recording has `"desk": "desk-2"`) and the first desk null. The
   record carries `N`, and null for the first desk — so a first-desk `run` and a
   `resume` both read null (`command` tells them apart). If you meant the first
   desk to be 1, it is one line in `desk_number`.
3. **The twin gained `cost_file` and `cost_file_error`**, placed *before* `next`
   so recovery's pinned "`next` is the last name" holds (a test pins it). The
   brief says the twin says why a cost file failed; these are the names.
4. **`cost_usd`/sums are over records whose `sid` is the session's**, not over
   records that merely *serve* it (`served_sid`). `twine spend totals --sid`
   keeps those apart as `served_*`; no code writes `served_sid` yet. Counting
   both would be a one-line change in `twine/cost.py` (`session_cost`).
5. **`stats`: `runs` counts members**, after `--since`/`--sid` (not every line
   read); `faults` always names every non-record line of the file, since a bad
   line has no sid to filter by. Unfiltered the two readings agree. `--since` that
   is not a date is `ok` false with every key present.
6. **`transcript`'s human line** is `<seq> <kind> [call <n>] <summary>` with the
   brackets literal, and the part absent on a line with no call. `faults` there
   (and in `stats`) are strings, `line N: why`.
7. **A resume asked of a state directory that does not exist writes no line**
   (it would create a directory to record a refusal); a `run` refused after the
   open does, since `bale open` and the in-flight record have used the directory.
   A run that dies of an internal error (exit 2) writes no line — it has no
   outcome among the eight; the transcript's `run-end` says `internal_error`.
8. **`twine carry response` still prints the plain `bale apply <tarball>`.** It
   is given a tarball, no session and no state directory; a cost file made from
   an empty spend stream would stamp zeros into bale's telemetry, which is worse
   than no file. Every apply line of a *hosted* session carries the flag. Say if
   you want `carry response` to take a `--state-dir` and write the file.
9. **`resume --plan` names `--cost-file` on an admit line only when the file is
   already there** (it writes nothing, and bale refuses a `--cost-file` that does
   not exist). The run that printed the line wrote it, so in practice it is.
10. **The `"apply"` key** (reserved, null) is spelled `runs.APPLY = KEYS[-1]` in
    code, because `tests/test_carry_bale.py` guards the bare token `"apply"` to
    `twine.bale.dry_run_argv` alone. That guard is about argv, and I left it
    standing rather than loosen it.
11. **`validation.sh` runs the suite by default** (about two and a half minutes,
    over TARBALL §7.6's two-minute target) because the brief names it first;
    `--skip-suite` leaves it out and says so.

## Tests I changed (each moved with a pinned thing)

`test_status.py` (the eighth boolean, five assertions), `test_registry.py` (the
two verbs), `test_json_discipline.py` (argv for `stats` and `transcript`, and a
transcript in its state double), `test_run.py` (`test_the_delivered_path`: the
apply line with `--cost-file`, the file's six keys and sums, its modes),
`test_resume.py` (the apply line with the flag in four places, the clarification
form's second `next` line, the admit line with the flag, `VERSION`).
`tests/test_telemetry.py` is new: 60 tests over the cost file, the record, the
aggregation, the story, every outcome leaving one line, the resume's line, the
cost file across a suspend and a resume, a cost file that cannot be written (the
plain line, the twin's reason, a warning), the admit line, the verbs through the
shell, and the write-nothing diff.

## Where to look closely

- `deliver()` in `twine/commands/run.py`: the cost file is written *inside* the
  courier's `deliver` callable, after the dry run is clean and before the line
  goes back to the loop, so the loop, the transcript's `move` line
  (`carry_response`), the twin and `next` all carry the same line.
- `name_next`: the clarification form now needs a suggested cap (it names a
  resume line), so a `suspended`-with-apply-line run reads its transcript and
  prices as any resumable ending does; with no cap to suggest the second line is
  `twine resume SID --plan`.
- I did not run the blind checkpoint (I cannot see it). The brief's description
  of it — two `runs.jsonl` lines' key order and values, the delivered run's apply
  line and file, `stats` with and without `--sid`, `transcript --json`, `status`
  — is what the tests above assert against the same fake-adapter beds.

## The seed annotation for the next tidy (verbatim, complete)

Under §5.2, after recovery's bracket:

```
[2026-10-15-twine-run-telemetry-004: landed — telemetry that matches bale's.
`<state-dir>/runs.jsonl`: one append-only line per run that has a sid, on every
outcome (`delivered`, `suspended`, `ended`, `stopped`, `killed`, `cap-reached`,
`cap-unchecked`, and `refused` after the open), thirty-two keys pinned whole — the
run twin plus the desk, the times, durations by tool and the events the stderr
warnings name (`twine/runs.py`). It is read by `twine stats [--since DATE] [--sid
SID]` (read-only; an absent file an honest empty report, as `bale stats`' is) and
`twine transcript SID [--from SEQ]` (a run's story, a line per transcript line),
both in `twine/commands/telemetry.py`; `twine status` names the file as the
eighth of `state_present`. Every `bale apply` line twine prints — `delivered`'s,
escalate's clarification form's, bale's admit line on a scope-drift refusal, and
the same lines in `next` — now carries `--cost-file
<state-dir>/cost/<sid>.json` (bale 0.4.54's flag; Q-8's mirror built), the file
written first by `twine/cost.py`: bale's six keys summed over every spend record
of the sid, `usd` null when any is unpriced, `model_tier` always null; the dry
run's argv and `twine kill`'s unlock never carry it. escalate's clarification
form also names the resume that follows the planner's answer. `twine/durable.py`
for the record writers (now six: spend, kill, inflight, transcript, runs, cost)
stays a proposal. The contract is `cli-contract.md` §18.7a, §20 and §21, and
`VERSION` 0.26.0.]
```

Under TQ-1, after the `twine-runtime-window-009` bracket:

```
[2026-10-15-twine-run-telemetry-004: beside the transcript, `<state-dir>/runs.jsonl`
is the durable per-run record — the same append-only, never-rewritten kind of
log, one line per run that has a sid, read by `twine stats`; the transcript stays
the story, and `twine transcript` reads it (cli-contract.md §20, §21).]
```

## Proposals

- **What** — Make `twine/durable.py` real now: six record writers share one
  shape (`spend.py`, `kill.py`, `inflight.py`, `transcript.py`, `runs.py`,
  `cost.py`): create 0700/0600, one `O_APPEND` write plus fsync, or temp + fsync +
  rename. **Why** — this session wrote the fifth and sixth, and the two new ones
  each re-implement the torn-tail and permission handling `spend.py` and
  `transcript.py` already have; the carry-forward's "now five" is now six.
  **Scope hints** — `twine/{spend,transcript,runs,cost,kill,inflight}.py`;
  after this lands, before any seventh writer.
- **What** — A `--state-dir` on `twine carry response` that, given it, writes the
  session's cost file (the sid is in bale's dry-run line) and prints the flagged
  line. **Why** — it is the one apply line twine prints that cannot carry
  `--cost-file` today (choice 8), and the chat-worker path ends there. **Scope
  hints** — `twine/commands/carry_bale.py`, `check_response`; wants a decision on
  what a session with no spend stream should stamp (nothing, I think).
- **What** — `--cost-file` on `twine kill`'s `bale unlock` argv, queued as the
  brief says for the session that next re-records unlock. **Why** — an `aborted`
  close is the one attempt of a hosted session that records cost-less.
- **What** — A line in `runs.jsonl` for a run that dies of an internal error.
  **Why** — "every run that had a sid writes a line" is held for the eight
  outcomes; a defect in twine is not one, so the rate over runs omits exactly the
  runs a defect killed. It needs a ninth outcome (a contract change), so I left it.

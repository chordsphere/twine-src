#!/usr/bin/env bash
# Blind checkpoint — session twine-seed-tidy9 (v1), authored at the desk of
# sitting 2026-10-08-open-arc2-003.
#
# What it grades (outcomes only): twine-seed.md is the base (1603 lines,
# sha256 afbc1bee…) plus exactly eight annotation blocks — R2's, R3's and
# R4's under §5.2 after R1's; one line each under T8, D13, D11, TQ-1 and
# §4.4 — each preceded by one blank line; the landed file is one exact byte
# string, pinned by hash, and removing the insertions gives the base back.
# The blocks are carried here verbatim (the ratified sessions' words).
#
# Writes only under ./.checkpoint-tidy9.<pid>/ (removed at exit); reads
# nothing of its own. Exit 0 all probes passed; 1 a probe failed; 2 the
# oracle is broken.
set -u
WORK="$(pwd)/.checkpoint-tidy9.$$"
mkdir -p "$WORK" || exit 2
trap 'rm -rf "$WORK"' EXIT
echo "[checkpoint] writes only under $WORK (removed at exit)"
PYTHONDONTWRITEBYTECODE=1 python3 -I -B - "$WORK" <<'PY'
import hashlib, sys
from pathlib import Path

def broken(msg):
    print(f"[checkpoint] ORACLE BROKEN: {msg}")
    sys.exit(2)
sys.excepthook = lambda t, v, tb: broken(f"unplanned {t.__name__}: {v}")

TREE = Path.cwd()
BASE_SHA = "afbc1bee9ac96435dfc0f36c4baeb406064c23f80c5eda9185291ec5a7d8cb45"
BASE_LINES = 1603
LANDED_SHA = "337722a561b2776a0a80d48fe8a1ad96a37235b6945a38669eb9af77d1be0f35"
LANDED_LINES = 1698
BLOCKS = {
 "A": [
  "[2026-10-13-twine-runtime-anthropic-002: R2 landed — the Anthropic",
  "adapter (`twine/runtime/adapters/anthropic.py`, registered `anthropic`,",
  "implementing `tool-calling`, `thinking` and `usage-accounting` and, now",
  "`implemented`, `prompt-caching` and `streaming`) over a stdlib transport",
  "seam (`twine/runtime/transport.py`, the only place twine opens a socket;",
  "the `anthropic` SDK is not used), its key read from `ANTHROPIC_API_KEY`",
  "in the environment it is given and sent in `x-api-key` and nowhere else;",
  "the readers (`read_response`, `read_stream`, the `Outcome` whose",
  "`as_json()` is pinned) and `build_request` with three prompt-cache",
  "breakpoints; the stop and error mapping as `[[mapping]]` rows of",
  "`share/transitions.toml`, whose `stop` axis gained `request-refused`",
  "(move `fix-request`, the operator's) and `provider-error`",
  "(`retry-with-backoff`) and declares `loop_keys` (`cap-reached`,",
  "`cap-unchecked`, `killed`), which the boundary now refuses from an",
  "adapter, with `written_against` at the floor, 0.4.51; the fifteen",
  "recordings of 2026-10-13 under `fixtures/anthropic/` and their lander,",
  "`bin/twine-land-provider-recordings`; the gated live smoke test,",
  "`tests/test_anthropic_live.py`; and `VERSION` 0.17.0.]"
 ],
 "B": [
  "[2026-10-13-twine-runtime-tools-003: R3 landed — the seven canonical",
  "tools (`shell`, `read_file`, `write_file`, `list_dir`, `probe`,",
  "`escalate`, `deliver`) declared in `twine/runtime/tools.toml` (`name`,",
  "`module`, `leaves_cage`), one module each under `twine/runtime/tools/`,",
  "parity by name, rendered by the verb `twine runtime tools [--json]`;",
  "each a `ToolSpec` and an executor whose every failure is a result, never",
  "an exception (`run_tool`). The cage and its rules: one sandbox per sid",
  "(`twine/runtime/sandbox.py`), its home",
  "`<state-dir>/sandbox/<sid>/home/`, every file tool's path resolved",
  "inside it — an absolute path, a `..` or a symlink out refused, naming",
  "the cage — and `shell` run there with a minimal environment (`PATH`,",
  "`HOME`, `TMPDIR`, `LANG`; never `ANTHROPIC_API_KEY`), a timeout capped",
  "by the sandbox's maximum and a 256 KiB stdout cap. The network rule and",
  "`confines`: `unshare -rn` detected at creation, every `shell` argv",
  "wrapped in it where it works (`network: \"off\"`), `network: \"unconfined\"`",
  "and the reason where it does not; `confines` declared by the sandbox's",
  "runner exactly when the network is off — cli-contract §10.5's switch",
  "made. The hook: every spawn registered with the kill-switch's running",
  "record through the run seam's `on_spawn` when a record exists, and",
  "cleared after a run with no survivor. What leaves the cage: `probe`",
  "alone — `carry probe`'s machinery run read-only against the real",
  "repository, with the cage's environment. `sandboxing` implemented by the",
  "runtime itself (`implemented_by`). `VERSION` 0.18.0.]"
 ],
 "C": [
  "[2026-10-13-twine-runtime-run-004: R4 landed — `twine run BUNDLE`",
  "(`twine/commands/run.py` over `twine/runtime/loop.py`). The sequence:",
  "`carry bundle` opens the session; the runtime leads its own process",
  "group and registers it in the running record before it spawns anything;",
  "the sandbox is made and the request unpacked at `request/` with",
  "tarfile's `data` filter; the adapter (`anthropic`, or `fake` with",
  "`--script`) is spawned behind the boundary, the key handed to it and to",
  "nothing else; the transcript and the in-flight record's `runtime` fields",
  "are written; and the loop runs — the opener as the first turn under a",
  "model-agnostic system prompt, the abort file and the pre-call cap check",
  "before every call, each call's usage appended to `spend.jsonl`, and the",
  "transition table's moves performed from its rows (`classify-final-text`;",
  "`continue-turn`, at most three times; `retry-with-backoff`, at most five",
  "retries; `return-tool-error` for a failed tool; every other move named",
  "and the run stopped). The outcomes: `delivered` (the dry run clean, the",
  "apply line printed — twine applies nothing), `suspended`, `ended`,",
  "`stopped`, `killed`, `cap-reached`, `cap-unchecked`, `refused`. Every",
  "step is a line of `<state-dir>/transcripts/<sid>.jsonl`. On any end the",
  "running record is cleared; on `delivered` the in-flight record is",
  "removed and the sandbox home kept; otherwise both are kept. `VERSION`",
  "0.19.0. With R1–R4 landed, the first milestone of the Arc 2 cut is",
  "reached: the worker side of the courier is twine's.]"
 ],
 "D": [
  "[2026-10-13-twine-runtime-anthropic-002: the first provider recordings",
  "of the wire — fifteen Messages API exchanges the architect made on",
  "2026-10-13 with his own key through probe `twine-anthropic-record`,",
  "carried as its paste-back and landed byte-exact by",
  "`bin/twine-land-provider-recordings` — live under `fixtures/anthropic/`",
  "(beside R1's 2026-10-08 usage object), and the Anthropic adapter's tests",
  "replay them through its transport seam.]"
 ],
 "E": [
  "[2026-10-13-twine-runtime-tools-003: `probe`, `escalate` (light form)",
  "and `deliver` exist as the wrappers it demanded, in",
  "`twine/runtime/tools/`.]"
 ],
 "F": [
  "[2026-10-13-twine-runtime-run-004: landed — the include set sits on disk",
  "at `request/` in the worker's sandbox home, the opener is the first user",
  "turn, and the system prompt holds only the tool definitions and the",
  "surface note (runtime-contract.md §7.1–§7.2).]"
 ],
 "G": [
  "  [2026-10-13-twine-runtime-run-004: landed — a hosted session's",
  "  transcript lives at `<state-dir>/transcripts/<sid>.jsonl`, one",
  "  append-only JSON line per step (`run-start`, `check`, `request`,",
  "  `turn`, `tool-call`, `tool-result`, `move`, `retry`, `abort`,",
  "  `adapter-error`, `run-end`), its `seq` continuing across runs",
  "  (runtime-contract.md §7.6).]"
 ],
 "H": [
  "[2026-10-13-twine-runtime-run-004: the loop exists, so both obligations",
  "are now due — the bale-src `AGENT.md` §11.7 surface row for twine-hosted",
  "API workers, and nisaba-src's `nisaba-seed.md` §3.3 annotation; the",
  "desk's to send.]"
 ]
}
# (before line, after line, blocks in order, whether the base had a blank after the before line)
RUNS = [
 ("`twine runtime list` and `twine runtime show`, and `VERSION` 0.16.0.]", "### 5.3 Arc 3 — the scheduler", ["A", "B", "C"], True),
 ("at.]", "**T9 — Stack lean.** Proposed: Python 3.10+, stdlib for the core", ["D"], True),
 ("emits bale's clarification response or light block, never a fork.]", "**D14 — The escalation producer.** The harness is the producer the", ["E"], True),
 ("surface note is the third runtime concern (§4.3).]", "**D12 — Caching discipline as a design constraint.** Append-only,", ["F"], True),
 ("  of record. Ratified as assumed at light block 3 [2].]", "- **TQ-2 — The capability registry's file shape.** Recommend one", ["G"], True),
 ("above). Neither is this session's or this repository's to land.", "### 4.5 Effort (T11, directed)", ["H"], True),
]
NAMES = {"A": "R2's annotation (§5.2)", "B": "R3's annotation (§5.2)", "C": "R4's annotation (§5.2)", "D": "R2's T8 line",
         "E": "R3's D13 line", "F": "R4's D11 line", "G": "R4's TQ-1 line", "H": "R4's §4.4 line"}

failures = []
def probe(label, ok):
    print(f"{'[PASS]' if ok else '[FAIL]'} {label}")
    if not ok: failures.append(label)

def find_run(lines, block):
    n = len(block)
    return [i for i in range(len(lines) - n + 1) if lines[i:i + n] == block]

def sequence_at(lines, before, blocks, after):
    """`after` occurs once; walking back from it: a blank, then the blocks
    (each preceded by a blank) in order, then `before`."""
    hits = [i for i, l in enumerate(lines) if l == after]
    if len(hits) != 1: return False
    end = hits[0]
    start = end - 2 - sum(len(b) + 1 for b in blocks)
    if start < 0 or lines[start] != before: return False
    i = start + 1
    for b in blocks:
        if lines[i] != "": return False
        i += 1
        if lines[i:i + len(b)] != b: return False
        i += len(b)
    return lines[i] == "" and i + 1 == end

seed_bytes = (TREE / "twine-seed.md").read_bytes()
seed = seed_bytes.decode("utf-8").split("\n")
if seed and seed[-1] == "": seed.pop()

probe(f"the landed seed is byte-exact ({LANDED_LINES} lines, {LANDED_SHA[:12]})",
      hashlib.sha256(seed_bytes).hexdigest() == LANDED_SHA and len(seed) == LANDED_LINES)
for k in "ABCDEFGH":
    probe(f"block {k}, {NAMES[k]} ({len(BLOCKS[k])} lines), lands exactly once, byte-verbatim", len(find_run(seed, BLOCKS[k])) == 1)
for before, after, ks, _ in RUNS:
    probe(f"run {'+'.join(ks)} sits after {before.strip()[:28]!r}, blank-separated, before {after[:28]!r}",
          sequence_at(seed, before, [BLOCKS[k] for k in ks], after))

# the reversal: remove each block with the blank before it, then the blank each
# no-blank run added before its `after` line; the base must come back
kept = list(seed)
for before, after, ks, had_blank in RUNS:
    for k in ks:
        runs = find_run(kept, BLOCKS[k])
        if len(runs) == 1 and runs[0] >= 1 and kept[runs[0] - 1] == "":
            del kept[runs[0] - 1: runs[0] + len(BLOCKS[k])]
    if not had_blank:
        hits = [i for i, l in enumerate(kept) if l == after]
        if len(hits) == 1 and hits[0] >= 2 and kept[hits[0] - 1] == "" and kept[hits[0] - 2] == before:
            del kept[hits[0] - 1]
base = ("\n".join(kept) + "\n").encode("utf-8")
probe(f"with the eight insertions removed the seed is the base ({BASE_LINES} lines, {BASE_SHA[:12]})",
      len(kept) == BASE_LINES and hashlib.sha256(base).hexdigest() == BASE_SHA)
probe("no TODO entered the seed", "TODO" not in seed_bytes.decode("utf-8"))

# --- controls ---
if find_run(["a", "b", "c"], ["b", "c"]) != [1] or find_run(["a", "b"], ["b", "a"]) != []: broken("find_run is wrong")
if not sequence_at(["x", "", "p", "q", "", "r", "", "y"], "x", [["p", "q"], ["r"]], "y"): broken("sequence_at refuses a good sequence")
if sequence_at(["x", "p", "q", "", "y"], "x", [["p", "q"]], "y"): broken("sequence_at accepts a missing blank")
if sequence_at(["x", "", "p", "q", "", "r", "", "y"], "x", [["r"], ["p", "q"]], "y"): broken("sequence_at accepts the wrong order")
if sequence_at(["x", "", "p", "", "y", "y"], "x", [["p"]], "y"): broken("sequence_at accepts an ambiguous after-anchor")
if sequence_at(["x", "", "p", "q", "z", "y"], "x", [["p", "q"]], "y"): broken("sequence_at accepts text where the trailing blank must be")
# the pinned landed bytes must equal base + the insertions as RUNS describes them (the oracle agrees with itself)
import json as _j
if len(BLOCKS) != 8 or any(not isinstance(b, list) or not b for b in BLOCKS.values()): broken("the blocks table is malformed")
if sum(len(b) for b in BLOCKS.values()) + 8 + sum(1 for r in RUNS if not r[3]) + BASE_LINES != LANDED_LINES: broken("the line arithmetic does not add up")
for h in (BASE_SHA, LANDED_SHA):
    if len(h) != 64 or any(c not in "0123456789abcdef" for c in h) or hashlib.sha256(b"x").hexdigest() == h: broken("a pinned hash is not a hash")

print(f"[checkpoint] {len(failures)} failing probe(s)")
sys.exit(1 if failures else 0)
PY

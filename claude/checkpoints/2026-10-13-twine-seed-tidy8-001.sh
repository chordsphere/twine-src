#!/usr/bin/env bash
# Blind checkpoint — session twine-seed-tidy8 (v1), authored at the desk of
# sitting 2026-10-08-open-arc2-003.
#
# What it grades (outcomes only): twine-seed.md is the base (1540 lines,
# sha256 32f418e6…) plus exactly nine annotation blocks — bundle-051's road
# line at the end of §5.1; the Arc 2 cut's and R1's under §5.2; in the §6
# register, Q-3's proposal and ratification, Q-4's answer, Q-8's answer,
# TQ-2's proposal and ratification — each preceded by one blank line, the
# three runs whose anchor had no blank after it followed by one; the landed
# file is therefore one exact byte string, pinned by hash, and removing the
# insertions gives the base back. The blocks are carried here verbatim
# (they are the sitting's rulings and the ratified notes' words, which no
# file in the tree holds).
#
# Writes only under ./.checkpoint-tidy8.<pid>/ (removed at exit); reads
# nothing of its own. Exit 0 all probes passed; 1 a probe failed; 2 the
# oracle is broken.
set -u
WORK="$(pwd)/.checkpoint-tidy8.$$"
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
BASE_SHA = "32f418e637ef4ac75318c6ed4cf68e70cffea23d1a41c58bfec11a80fd793c7a"
BASE_LINES = 1540
LANDED_SHA = "afbc1bee9ac96435dfc0f36c4baeb406064c23f80c5eda9185291ec5a7d8cb45"
LANDED_LINES = 1603
BLOCKS = {
 "A": [
  "[2026-10-12-twine-bundle-051-004: `carry bundle` reads 0.4.50's open",
  "line: the refusal named with its code and cause, the second-desk tarball",
  "kept, `VERSION` 0.15.0.]"
 ],
 "B": [
  "[2026-10-08-open-arc2-003: Arc 2 cut at the sitting, ratified \"as",
  "assumed\" on 2026-10-12 — R1 the adapter boundary and the capability",
  "registry (T7, §4.1, Q-3, TQ-2); R2 the Anthropic adapter and the",
  "transition table's provider axis; R3 the canonical tools and the sandbox",
  "(T6, §4.2, §4.3); R4 the loop, `twine run <bundle>`; R5 window",
  "accounting and cold resume (D23); R6 the OpenAI-compatible adapter and",
  "the text tool protocol (TQ-3); R7 hosted sittings (D22 as re-read, Q-4);",
  "R8 `ask` and `delegate` (T11). Serialized R1→R2→R3→R4, the first",
  "milestone; each a code session with a blind checkpoint. Q-4 answered yes",
  "and Q-8 sent to bale-src at the same sitting (§6).]"
 ],
 "C": [
  "[2026-10-12-twine-runtime-registry-007: R1 landed — the capability",
  "registry (`twine/runtime/capabilities.toml` declaring the eight",
  "capabilities §4.1 names, one module each under",
  "`twine/runtime/capabilities/` with its contract, three `implemented` —",
  "`tool-calling`, `thinking`, `usage-accounting`, by the fake adapter —",
  "and five `declared`, parity by name), the adapter boundary",
  "(`twine/runtime/boundary.py`) with its one stop spelling — the",
  "transition table's `stop` axis, read through",
  "`twine.transitions.stop_keys` and spelled nowhere in code — the fake",
  "transport adapter `fake` the tests drive, `from_anthropic` held to the",
  "architect's 2026-10-08 recording",
  "(`fixtures/anthropic/messages-usage-2026-10-08.json`), the two verbs",
  "`twine runtime list` and `twine runtime show`, and `VERSION` 0.16.0.]"
 ],
 "D": [
  "  [2026-10-12-twine-runtime-registry-007: proposed, awaiting",
  "  ratification — the contract text is",
  "  `claude/context/runtime-contract.md` §1, the four things the boundary",
  "  abstracts each with what an adapter must do and what the boundary",
  "  promises, implemented by `twine/runtime/boundary.py`.]"
 ],
 "E": [
  "  [2026-10-08-open-arc2-003: ratified at the sitting, 2026-10-12, with",
  "  three calls accepted — a turn asks for tools or stops, never both; the",
  "  boundary accepts every key of the `stop` axis, the loop-only three a",
  "  recorded defect for R2's table; an unknown tool name is the loop's",
  "  tool error, not the boundary's refusal.]"
 ],
 "F": [
  "  [2026-10-08-open-arc2-003: answered yes at the Arc 2 sitting,",
  "  2026-10-12 (\"as assumed\") — the planning chat becomes a hosted office",
  "  session, R7 of the cut (§5.2); twine keeps only mechanical streams.]"
 ],
 "G": [
  "  [2026-10-08-open-arc2-003: answered at the Arc 2 sitting, 2026-10-12",
  "  (\"as assumed\") — a bale-src decision, queued for bale-src's desk",
  "  beside `bale contract --json`; nothing in R1–R8 waits on it.]"
 ],
 "H": [
  "  [2026-10-12-twine-runtime-registry-007: proposed, awaiting",
  "  ratification — the shape is written in",
  "  `claude/context/runtime-contract.md` §2: the declaration",
  "  `twine/runtime/capabilities.toml` (name, dotted module, status,",
  "  summary), one module per capability exposing a `Contract`, three",
  "  statuses held to the adapters, and each adapter declaring the",
  "  capabilities it implements.]"
 ],
 "I": [
  "  [2026-10-08-open-arc2-003: ratified at the sitting, 2026-10-12, as",
  "  proposed.]"
 ]
}
# (before line, after line, blocks in order, whether the base had a blank after the before line)
RUNS = [
 ("`twine-pin-floor`.]", "### 5.2 Arc 2 — the runtime", ["A"], True),
 ("closes.", "### 5.3 Arc 3 — the scheduler", ["B", "C"], True),
 ("  ratifies.", "- **Q-4 — Chat-mode persistence.** *Still open.* Answered if the", ["D", "E"], False),
 ("  Recommend yes. The architect answers, at the Arc 2 sitting.", "- **Q-5 — Email transport.** *Later rung.* The batched-digest", ["F"], False),
 ("  exists and is the owner; bale's mirror remains bale-src's.]", "- **TQ-1 — Where a worker's transcript lands.** Twine's log, or the", ["G"], True),
 ("  architect ratifies.", "- **TQ-3 — The text tool protocol's exact wire.** Sentinels, one call", ["H", "I"], False),
]
NAMES = {"A": "bundle-051's road line (§5.1)", "B": "the Arc 2 cut (§5.2)", "C": "R1's annotation (§5.2)",
         "D": "R1's Q-3 proposal", "E": "the Q-3 ratification", "F": "Q-4's answer", "G": "Q-8's answer",
         "H": "R1's TQ-2 proposal", "I": "the TQ-2 ratification"}

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
for k in "ABCDEFGHI":
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
probe(f"with the nine insertions removed the seed is the base ({BASE_LINES} lines, {BASE_SHA[:12]})",
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
if len(BLOCKS) != 9 or any(not isinstance(b, list) or not b for b in BLOCKS.values()): broken("the blocks table is malformed")
if sum(len(b) for b in BLOCKS.values()) + 9 + sum(1 for r in RUNS if not r[3]) + BASE_LINES != LANDED_LINES: broken("the line arithmetic does not add up")
for h in (BASE_SHA, LANDED_SHA):
    if len(h) != 64 or any(c not in "0123456789abcdef" for c in h) or hashlib.sha256(b"x").hexdigest() == h: broken("a pinned hash is not a hash")

print(f"[checkpoint] {len(failures)} failing probe(s)")
sys.exit(1 if failures else 0)
PY

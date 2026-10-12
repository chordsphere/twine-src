#!/usr/bin/env bash
# Blind checkpoint — session twine-seed-tidy7 (v1), authored at the desk of
# sitting 2026-10-08-open-arc2-003 from the request alone.
#
# What it grades (outcomes only): twine-seed.md is the base (1454 lines,
# sha256 128671ea…) plus exactly seven annotation blocks, each the run of
# `> `-quoted lines under "## 5." of its session's archived notes.md,
# un-quoted and otherwise byte-verbatim, each preceded by one blank line
# and landed at its anchor: pin-floor's T8 line after T8's last annotation;
# pin-051's and pin-floor's D2 annotations, in that order, after pin-049's
# D2 annotation; carry-exchange-json-001's, status-inflight-004's,
# exchange-vouch-005's and pin-051's road annotations, in that order, at
# the end of §5.1. Removing the seven insertions gives the base back,
# byte for byte. The blocks are read from the tree at grade time, never
# from this file.
#
# Writes only under ./.checkpoint-tidy7.<pid>/ (removed at exit); reads
# nothing of its own. Exit 0 all probes passed; 1 a probe failed; 2 the
# oracle is broken.
set -u
WORK="$(pwd)/.checkpoint-tidy7.$$"
mkdir -p "$WORK" || exit 2
trap 'rm -rf "$WORK"' EXIT
echo "[checkpoint] writes only under $WORK (removed at exit)"
PYTHONDONTWRITEBYTECODE=1 python3 -I -B - "$WORK" <<'PY'
import hashlib, re, sys
from pathlib import Path

def broken(msg):
    print(f"[checkpoint] ORACLE BROKEN: {msg}")
    sys.exit(2)
sys.excepthook = lambda t, v, tb: broken(f"unplanned {t.__name__}: {v}")

TREE = Path.cwd()
BASE_SHA = "128671eab865722d3e97b5826b135d17c91902383415dcae9b6cd6a3ff0cb2e8"
BASE_LINES = 1454
# (sid, which block of its notes' §5 — 0 the first, 1 the second), in landing order per anchor
T8 = [("2026-10-12-twine-pin-floor-002", 1)]
D2 = [("2026-10-12-twine-pin-051-001", 0), ("2026-10-12-twine-pin-floor-002", 0)]
ROAD = [("2026-10-08-twine-carry-exchange-json-001", 0), ("2026-10-08-twine-status-inflight-004", 0),
        ("2026-10-08-twine-exchange-vouch-005", 0), ("2026-10-12-twine-pin-051-001", 1)]
# the preserved lines each run of insertions sits between (byte-stable anchors in the base)
T8_BEFORE, T8_AFTER = "exists to fake.]", "**T9 — Stack lean.** Proposed: Python 3.10+, stdlib for the core"
D2_BEFORE, D2_AFTER = "`twine-kill-reason` keys it on the recorded `reason` code.]", "**D3 — Narrowest consumption surface.** Rung 1 consumes the"
ROAD_BEFORE, ROAD_AFTER = "With rows 0–5 landed, Arc 1 is complete.]", "### 5.2 Arc 2 — the runtime"

failures = []
def probe(label, ok):
    print(f"{'[PASS]' if ok else '[FAIL]'} {label}")
    if not ok: failures.append(label)

def notes_blocks(sid):
    """The `> `-quoted runs under the notes' `## 5.` heading that open with
    `> [<sid>:` and close on a line ending `]`, un-quoted (one `> ` or `>`
    stripped per line), in order."""
    p = TREE / "claude" / "responses" / sid / "notes.md"
    if not p.is_file(): return None
    text = p.read_text(encoding="utf-8")
    if "\n## 5." not in text: return []
    sec = text.split("\n## 5.", 1)[1].split("\n## ", 1)[0]
    lines = sec.split("\n"); out = []; i = 0
    while i < len(lines):
        if lines[i].startswith(f"> [{sid}:"):
            j = i
            while j < len(lines) and not lines[j].rstrip().endswith("]"): j += 1
            if j >= len(lines): return out
            out.append([re.sub(r"^> ?", "", l) for l in lines[i:j + 1]]); i = j + 1
        else: i += 1
    return out

def find_run(lines, block):
    """Indices where `block` (a list of lines) occurs as a contiguous run."""
    n = len(block)
    return [i for i in range(len(lines) - n + 1) if lines[i:i + n] == block]

def sequence_at(lines, before, blocks, after):
    """True when `before` is followed by: blank, block, blank, block, …, blank,
    then `after`. Anchored on whichever of `before`/`after` occurs exactly
    once (pin-049's D2 annotation also sits in §5.1, so its last line is
    not unique; `**D3 —` is)."""
    before_hits = [i for i, l in enumerate(lines) if l == before]
    after_hits = [i for i, l in enumerate(lines) if l == after]
    if len(after_hits) == 1:
        end = after_hits[0]
        start = end - 2 - sum(len(b) + 1 for b in blocks)
        if start < 0 or lines[start] != before: return False
    elif len(before_hits) == 1:
        start = before_hits[0]
        end = start + 2 + sum(len(b) + 1 for b in blocks)
        if end >= len(lines) or lines[end] != after: return False
    else:
        return False
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

got = {}
for sid in {s for s, _ in T8 + D2 + ROAD}:
    bl = notes_blocks(sid)
    probe(f"claude/responses/{sid}/notes.md is archived and its §5 carries its annotation block(s)", bl is not None and len(bl) >= 1)
    got[sid] = bl or []
def block(sid, k):
    return got[sid][k] if k < len(got[sid]) else None
blocks = {(s, k): block(s, k) for s, k in T8 + D2 + ROAD}
probe("the seven blocks are all present in the archived notes (pin-051 and pin-floor carry two each)", all(b is not None for b in blocks.values()))

for (s, k), b in blocks.items():
    if b is None: continue
    probe(f"{s} block {k} ({len(b)} lines) lands exactly once, byte-verbatim", len(find_run(seed, b)) == 1)
probe("T8: pin-floor's line sits after T8's last annotation, before T9", all(blocks[x] for x in T8) and sequence_at(seed, T8_BEFORE, [blocks[x] for x in T8], T8_AFTER))
probe("D2: pin-051's then pin-floor's annotations after pin-049's, before D3", all(blocks[x] for x in D2) and sequence_at(seed, D2_BEFORE, [blocks[x] for x in D2], D2_AFTER))
probe("§5.1: carry-exchange-json, status-inflight, exchange-vouch, pin-051 after carry-bundle-003's, before §5.2", all(blocks[x] for x in ROAD) and sequence_at(seed, ROAD_BEFORE, [blocks[x] for x in ROAD], ROAD_AFTER))

# the reversal: remove each landed block and the blank before it; the base must come back
if all(b is not None for b in blocks.values()):
    kept = list(seed)
    for b in blocks.values():
        runs = find_run(kept, b)
        if len(runs) == 1 and runs[0] >= 1 and kept[runs[0] - 1] == "":
            del kept[runs[0] - 1: runs[0] + len(b)]
    base = ("\n".join(kept) + "\n").encode("utf-8")
    probe(f"with the seven insertions removed the seed is the base ({BASE_LINES} lines, {BASE_SHA[:12]})", len(kept) == BASE_LINES and hashlib.sha256(base).hexdigest() == BASE_SHA)
    expected_lines = BASE_LINES + sum(len(b) + 1 for b in blocks.values())
    probe(f"the landed seed is {expected_lines} lines", len(seed) == expected_lines)
probe("no TODO entered the seed", "TODO" not in seed_bytes.decode("utf-8"))

# --- controls ---
if find_run(["a", "b", "c"], ["b", "c"]) != [1] or find_run(["a", "b"], ["b", "a"]) != [] or find_run(["a", "b", "x"], ["b", "c"]) != []: broken("find_run is wrong")
if sequence_at(["x", "z", "p", "q", "", "y"], "x", [["p", "q"]], "y"): broken("sequence_at accepts text where the blank before a block must be")
if sequence_at(["x", "", "p", "q", "z", "y"], "x", [["p", "q"]], "y"): broken("sequence_at accepts text where the blank after the last block must be")
if not sequence_at(["x", "", "p", "q", "", "r", "", "y"], "x", [["p", "q"], ["r"]], "y"): broken("sequence_at refuses a good sequence")
if sequence_at(["x", "p", "q", "", "y"], "x", [["p", "q"]], "y"): broken("sequence_at accepts a missing blank")
if sequence_at(["x", "", "p", "q", "", "r", "", "y"], "x", [["r"], ["p", "q"]], "y"): broken("sequence_at accepts the wrong order")
if sequence_at(["x", "", "p", "", "y", "x", "y"], "x", [["p"]], "y"): broken("sequence_at accepts anchors that are both ambiguous")
if not sequence_at(["x", "", "p", "", "y", "x"], "x", [["p"]], "y"): broken("sequence_at refuses a unique after-anchor beside a repeated before")
if sequence_at(["x", "", "q", "", "y", "x"], "x", [["p"]], "y"): broken("sequence_at accepts the wrong block under the after-anchor")
if hashlib.sha256(b"x").hexdigest() == BASE_SHA: broken("the base hash is not a hash")
fake = TREE / ".checkpoint-tidy7-fake-notes"  # notes_blocks reads the tree only; test its parser on a string instead
sample = "# n\n\n## 5. The seed annotation\n\nText.\n\n> [sid-x: one —\n> two]\n\nand\n\n> [sid-x: three\n>\n> > quoted\n> four.]\n\n## Proposals\n> [sid-x: not in §5]\n"
sec = sample.split("\n## 5.", 1)[1].split("\n## ", 1)[0]
lines = sec.split("\n"); out = []; i = 0
while i < len(lines):
    if lines[i].startswith("> [sid-x:"):
        j = i
        while not lines[j].rstrip().endswith("]"): j += 1
        out.append([re.sub(r"^> ?", "", l) for l in lines[i:j + 1]]); i = j + 1
    else: i += 1
if out != [["[sid-x: one —", "two]"], ["[sid-x: three", "", "> quoted", "four.]"]]: broken(f"the block parser is wrong: {out}")

print(f"[checkpoint] {len(failures)} failing probe(s)")
sys.exit(1 if failures else 0)
PY

#!/usr/bin/env bash
# Blind checkpoint, v1 — twine-src session `twine-seed-tidy6` (slug), authored
# by the twine desk on 2026-10-07 from the brief, before the landing exists.
# Outcome contracts only: three dated annotations, each read from its
# session's archived notes.md in the tree (graded against that source, never
# against the brief's copy), inserted beneath the named entries of
# twine-seed.md; and nothing else in the seed changed — with the inserted
# blocks removed, the seed hashes to the base. The suite stays green.
# Pins no VERSION and no code: a session beside this one may change them.
#
# Runs in the staging tree's root (cwd). Exit 0 / 1 / 2: passed / a probe
# failed by name / the oracle is broken (a source notes.md missing, or no
# annotation in it, is the oracle's, not the landing's). Writes nothing but
# the suite's own temporary directories. Python under -I -B.
set -u
exec python3 -I -B - "$@" <<'PY'
import hashlib, os, subprocess, sys
from pathlib import Path


def _excepthook(kind, value, tb):
    import traceback
    print("[ORACLE ERROR] the checkpoint itself raised; exit 2 (not a verdict):", file=sys.stderr)
    traceback.print_exception(kind, value, tb)
    sys.stdout.flush()
    os._exit(2)


sys.excepthook = _excepthook
TREE = Path.cwd()
SEED = TREE / "twine-seed.md"
BASE_SHA = "abb55c02c0fb3abdeb2b8b155c6160448ce14330dacabe27b18568aae905d9ed"
SOURCES = {
    "pin": ("claude/responses/2026-10-07-twine-pin-049-001/notes.md", "2026-10-07-twine-pin-049-001"),
    "kill": ("claude/responses/2026-10-07-twine-kill-reason-002/notes.md", "2026-10-07-twine-kill-reason-002"),
    "bundle": ("claude/responses/2026-10-07-twine-carry-bundle-003/notes.md", "2026-10-07-twine-carry-bundle-003"),
}
# (label, the anchor annotation's first-line prefix, the blocks in order, the line that follows them)
PLACES = [
    ("pin-049-under-D2", "[2026-10-03-twine-transitions-004: carried, and now enforced", ["pin"], "**D3 "),
    ("kill-reason-under-D15", "[2026-10-06-twine-clear-group-003: landed", ["kill"], "**D16 "),
    ("pin-049-and-carry-bundle-ending-5.1", "[2026-10-06-twine-clear-group-003: `clear_group` landed",
     ["pin", "bundle"], "### 5.2 "),
]
for needed in [SEED, TREE / "tests"] + [TREE / p for p, _ in SOURCES.values()]:
    if not needed.exists():
        print(f"[ORACLE ERROR] {needed} is missing; the checkpoint grades against the archived notes in the "
              "staging tree and must run in its root; exit 2", file=sys.stderr)
        sys.exit(2)
print("[checkpoint] writes: nothing but the test suite's own temporary directories")
results = []


def probe(label, failures):
    results.append((label, list(failures)))
    print((f"[FAIL] {label}: " + "; ".join(failures)) if failures else f"[PASS] {label}")


def control(label, failures):
    if not failures:
        print(f"[ORACLE ERROR] control {label!r} did not fire; exit 2", file=sys.stderr)
        os._exit(2)
    print(f"[CONTROL] {label}: fires")


def annotation(text, sid):
    """The `> [<sid>: …]` blockquote of a notes.md, its `> ` stripped, one string per line;
    None when there is none."""
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith(f"> [{sid}:")), None)
    if start is None:
        return None
    out = []
    for l in lines[start:]:
        if not l.startswith(">"):
            break
        out.append(l[2:] if l.startswith("> ") else l[1:])
    return out if out and out[-1].endswith("]") else None


BLOCKS = {}
for key, (rel, sid) in SOURCES.items():
    block = annotation((TREE / rel).read_text(encoding="utf-8"), sid)
    if block is None:
        print(f"[ORACLE ERROR] {rel} carries no `> [{sid}: …]` annotation; exit 2", file=sys.stderr)
        sys.exit(2)
    BLOCKS[key] = block


# --- detectors -----------------------------------------------------------------

def anchor_end(lines, prefix):
    """The index of the anchor annotation's closing line (the first line from its start
    ending in `]`), or None."""
    start = next((i for i, l in enumerate(lines) if l.startswith(prefix)), None)
    if start is None:
        return None
    return next((j for j in range(start, len(lines)) if lines[j].endswith("]")), None)


def det_placed(lines, prefix, keys, follows, blocks):
    """Beneath the anchor: a blank line and each block in order, blank-separated, then a blank
    line and the line that followed the anchor in the base."""
    end = anchor_end(lines, prefix)
    if end is None:
        return [f"the anchor {prefix[:48]!r}… is not in the seed"]
    want = []
    for key in keys:
        want += [""] + blocks[key]
    want += ["", None]
    got = lines[end + 1:end + 1 + len(want)]
    f = []
    if got[:-1] != want[:-1]:
        f.append(f"the lines beneath the anchor are not {' then '.join(keys)}'s annotation, verbatim from the "
                 "archived notes")
    if len(got) < len(want) or not got[-1].startswith(follows):
        f.append(f"the annotations are not followed by {follows.strip()!r}")
    return f


def det_rest_is_base(lines, blocks):
    """Remove every inserted block (with the blank line before it) beneath its anchor; what is
    left must hash to the base seed."""
    rest = list(lines)
    for _, prefix, keys, _ in reversed(PLACES):
        end = anchor_end(rest, prefix)
        if end is None:
            return ["an anchor is missing, so the rest cannot be compared"]
        n = sum(1 + len(blocks[k]) for k in keys)
        rest[end + 1:end + 1 + n] = []
    digest = hashlib.sha256("\n".join(rest).encode("utf-8")).hexdigest()
    return [] if digest == BASE_SHA else [f"with the three insertions removed the seed hashes to {digest[:12]}…, "
                                          f"not the base {BASE_SHA[:12]}…: something else changed"]


def det_suite(code, tail):
    return [] if code == 0 else [f"the suite exited {code}: {tail}"]


# --- controls ------------------------------------------------------------------

_toy = ["x", PLACES[0][1] + " y]", "", PLACES[0][3] + "z"]
control("placed (absent)", det_placed(_toy, PLACES[0][1], ["pin"], PLACES[0][3], BLOCKS))
control("placed (no anchor)", det_placed(["nothing"], PLACES[0][1], ["pin"], PLACES[0][3], BLOCKS))
control("rest is base", det_rest_is_base(_toy, BLOCKS))
control("suite", det_suite(1, "boom"))

# --- probes --------------------------------------------------------------------

text = SEED.read_text(encoding="utf-8")
lines = text.split("\n")
for label, prefix, keys, follows in PLACES:
    probe(label, det_placed(lines, prefix, keys, follows, BLOCKS))
probe("nothing-else-in-the-seed-changed", det_rest_is_base(lines, BLOCKS))
suite = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                       cwd=str(TREE), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900)
probe("suite-green", det_suite(suite.returncode, suite.stderr.strip()[-400:]))

failed = [label for label, f in results if f]
print(f"[checkpoint] {len(results)} probes, {len(failed)} failed" + (": " + ", ".join(failed) if failed else ""))
sys.exit(1 if failed else 0)
PY

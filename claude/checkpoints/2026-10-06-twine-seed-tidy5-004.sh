#!/usr/bin/env bash
# Blind checkpoint, v1 — twine-src session `twine-seed-tidy5` (slug), authored
# at sitting 2026-10-06-continue-twine-002 from the brief, before the
# landing exists. Outcome contracts only: the landed seed's bytes, its two
# placements, the reversal to the shipped file, the texts' words against
# the archived notes of record, and the rest of the tree untouched.
#
# Runs in the staging tree's root (cwd). Exit 0: every probe passed. Exit 1:
# a probe failed, by name. Exit 2: the oracle is broken (a control did not
# fire, or an unexpected exception) — never a verdict on the work.
#
# Writes nothing: reads twine-seed.md, the archived notes, VERSION and the
# pinned untouched files, and prints. Every Python runs with -I -B.
set -u
exec python3 -I -B - "$@" <<'PY'
import hashlib, re, sys
from pathlib import Path


def _excepthook(kind, value, tb):
    import traceback
    print("[ORACLE ERROR] the checkpoint itself raised; exit 2 (not a verdict):", file=sys.stderr)
    traceback.print_exception(kind, value, tb)
    sys.stdout.flush()
    sys.exit(2)


sys.excepthook = _excepthook
TREE = Path.cwd()
SEED = TREE / "twine-seed.md"
NOTES = TREE / "claude/responses/2026-10-06-twine-clear-group-003/notes.md"
if not SEED.exists() or not (TREE / "bin/twine").exists():
    print(f"[ORACLE ERROR] twine-seed.md and bin/twine are not under the cwd {TREE}; the "
          "checkpoint must run in the staging tree's root; exit 2", file=sys.stderr)
    sys.exit(2)
print("[checkpoint] writes: nothing")

SHIPPED_SHA = "a814746039e5106e12d4aece1edc0bcaa79d2b7194b8a5d3417e3f2fe948ab38"
LANDED_SHA = "abb55c02c0fb3abdeb2b8b155c6160448ce14330dacabe27b18568aae905d9ed"
LANDED_LINES = 1409
# Landed placements (1-based, inclusive), from the brief §3.
L_SPAN, L_BLANK, L_NEXT = (690, 699), 700, "**D16 — Effort is envelope × policy.**"
M_SPAN, M_BLANK, M_NEXT = (1120, 1124), 1125, "### 5.2 Arc 2 — the runtime"
TEXT_L = """[2026-10-06-twine-clear-group-003: landed —
`twine.kill.clear_group(state_dir, sid, pgid)` forgets a group once its
run has returned with no survivor, so the running record holds what is
alive rather than one entry per tool. It runs under `register_group`'s
lock on `running/`, and `clear_running` takes that lock too (bounded, so
a wedged writer cannot hang the kill), so a record `twine kill` removed
never comes back. The loop calls it itself after `run` returns with
`group_survivors` empty; an entry whose run returned survivors stays for
the kill (contract §14.4). `twine kill` is unchanged and does not signal
a cleared group.]"""
TEXT_M = """[2026-10-06-twine-clear-group-003: `clear_group` landed (`VERSION`
0.7.1): the record's registered groups can now be forgotten as their
runs return. Arc 2's loop composes
`on_spawn=lambda pid: register_group(state_dir, sid, pid)` with
`clear_group(state_dir, sid, pid)` after a survivor-free return.]"""
NOTES_HEADING = "### Seed annotations for this session, for the next seed tidy"
UNTOUCHED = {
    "VERSION": "0.7.1\n",
}
UNTOUCHED_SHA = {
    "bale.toml": "b09e9b065594c48b2eb6c1754dd19a0700a5415b14b67ac80d629294b03cfbff",
    "share/transitions.toml": "b98ecd04bc0beeea08eab9e1ba4b47d3ea3d12e9e9fc8aa10fd37e66f42a2610",
    "share/bale-consumption.toml": "25365e193cc74598b5dadb0dbca0ec697367622afcffd372f72def2a8f5203dc",
    "bin/twine": "d5388349e4559df3f93f74a48f4740a512466a1224f84c98f655f3f3b4d4669e",
}

results = []


def probe(label, failures):
    results.append((label, list(failures)))
    print((f"[FAIL] {label}: " + "; ".join(failures)) if failures else f"[PASS] {label}")


def control(label, failures):
    if not failures:
        print(f"[ORACLE ERROR] control {label!r} did not fire; exit 2", file=sys.stderr)
        sys.exit(2)
    print(f"[CONTROL] {label}: fires")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def words(text):
    return text.replace("> ", " ").split()


# --- detectors: pure functions of observations --------------------------------

def det_landed(raw):
    f = []
    if sha(raw) != LANDED_SHA:
        f.append(f"twine-seed.md hashes to {sha(raw)[:16]}…, not the landing derived from the brief")
    n = raw.count(b"\n")
    if n != LANDED_LINES or not raw.endswith(b"\n"):
        f.append(f"{n} lines, expected {LANDED_LINES} with a final newline")
    return f


def det_placement(lines, span, blank, nxt, text, label):
    """lines: the file's lines (1-based via index-1). The span holds the
    text's lines exactly, the blank is empty, and the next line is nxt."""
    f = []
    want = text.split("\n")
    if len(lines) < blank + 1:
        return [f"{label}: the file is too short to hold the placement"]
    got = lines[span[0] - 1: span[1]]
    if got != want:
        f.append(f"{label}: lines {span[0]}-{span[1]} are not the text")
    if lines[blank - 1] != "":
        f.append(f"{label}: line {blank} is not blank")
    if not lines[blank].startswith(nxt):
        f.append(f"{label}: line {blank + 1} does not begin {nxt!r}")
    return f


def det_reversal(lines):
    kept = lines[: L_SPAN[0] - 1] + lines[L_BLANK: M_SPAN[0] - 1] + lines[M_BLANK:]
    back = ("\n".join(kept) + "\n").encode("utf-8")
    if sha(back) != SHIPPED_SHA:
        return ["removing the two landed spans does not give back the shipped seed"]
    return []


def det_words(landed_l, landed_m, notes_text):
    """The landed texts' words equal the archived notes' two blockquotes."""
    if notes_text is None:
        return [f"the notes of record are not archived at {NOTES.relative_to(TREE)}"]
    head = notes_text.find(NOTES_HEADING)
    if head < 0:
        return ["the archived notes have no seed-annotations heading"]
    section = notes_text[head:]
    end = section.find("\n### ", 1)
    section = section if end < 0 else section[:end]
    quotes = re.findall(r"((?:^> .*\n?)+)", section, re.M)
    if len(quotes) != 2:
        return [f"the archived notes hold {len(quotes)} blockquotes under the heading, not two"]
    f = []
    for name, landed, quote in (("L", landed_l, quotes[0]), ("M", landed_m, quotes[1])):
        if words(landed) != words(quote):
            f.append(f"text {name}'s landed words differ from the archived notes' blockquote")
    return f


def det_untouched(observed_text, observed_sha):
    f = [f"{p} is {observed_text.get(p)!r}, not {v!r}" for p, v in UNTOUCHED.items()
         if observed_text.get(p) != v]
    f += [f"{p} changed" for p, v in UNTOUCHED_SHA.items() if observed_sha.get(p) != v]
    return f


# --- controls ------------------------------------------------------------------

control("landed", det_landed(b"x\n"))
_short = ["a"] * 10
control("placement", det_placement(_short, (1, 2), 3, "zzz", "a\nb", "L"))
control("placement (short file)", det_placement(["a"], L_SPAN, L_BLANK, L_NEXT, TEXT_L, "L"))
control("reversal", det_reversal(["a"] * LANDED_LINES))
control("words (absent notes)", det_words(TEXT_L, TEXT_M, None))
control("words (differ)", det_words(TEXT_L, TEXT_M, NOTES_HEADING + "\n\n> one\n\n> two\n"))
control("untouched", det_untouched({"VERSION": "0.7.0\n"}, {p: "0" * 64 for p in UNTOUCHED_SHA}))

# --- probes --------------------------------------------------------------------

raw = SEED.read_bytes()
lines = raw.decode("utf-8").split("\n")
if lines and lines[-1] == "":
    lines = lines[:-1]
probe("seed-landed-bytes", det_landed(raw))
probe("text-L-placement", det_placement(lines, L_SPAN, L_BLANK, L_NEXT, TEXT_L, "L"))
probe("text-M-placement", det_placement(lines, M_SPAN, M_BLANK, M_NEXT, TEXT_M, "M"))
probe("reversal-to-shipped-seed",
      det_reversal(lines) if len(lines) == LANDED_LINES
      else [f"{len(lines)} lines; the reversal needs the landed {LANDED_LINES}"])
landed_l = "\n".join(lines[L_SPAN[0] - 1: L_SPAN[1]])
landed_m = "\n".join(lines[M_SPAN[0] - 1: M_SPAN[1]])
probe("texts-words-match-archived-notes",
      det_words(landed_l, landed_m,
                NOTES.read_text(encoding="utf-8") if NOTES.exists() else None))
probe("untouched-files",
      det_untouched({p: (TREE / p).read_text(encoding="utf-8") if (TREE / p).exists() else None
                     for p in UNTOUCHED},
                    {p: sha((TREE / p).read_bytes()) if (TREE / p).exists() else None
                     for p in UNTOUCHED_SHA}))

failed = [label for label, f in results if f]
print(f"[checkpoint] {len(results)} probes, {len(failed)} failed"
      + (": " + ", ".join(failed) if failed else ""))
sys.exit(1 if failed else 0)
PY

#!/usr/bin/env bash
# Blind checkpoint — twine-src, the fourth seed tidy (slug twine-seed-tidy4), v1.
# Authored at sitting 2026-10-05-continue-twine-002 from the brief alone, before
# the session existed. It grades the landed twine-seed.md: three texts at their
# anchors, the session id substituted, the counts, the reversal to the base, and
# texts J and K word for word against the archived notes of
# 2026-10-05-twine-kill-followups-003 (TARBALL.md §7). It needs no session id of
# its own — it reads the id from the landed text and cross-checks
# .bale-manifest.json only when one is present — and not its own filename:
# `bale open`'s dry-run runs it before any session exists.
#
# Exit 0: every probe passed. Exit 1: a probe failed, named on its own [FAIL]
# line. Exit 2: this oracle is broken (its control failed, or an error of its
# own) — a verdict on the checkpoint, never on the work.
#
# Reads twine-seed.md, claude/responses/2026-10-05-twine-kill-followups-003/notes.md
# and .bale-manifest.json (when present). Writes nothing. No bytecode, no
# network, no process started. Never reads claude/checkpoints/ or itself.

set -u
export PYTHONDONTWRITEBYTECODE=1
export LC_ALL=C.UTF-8

if [ -f twine-seed.md ] && [ -d claude ]; then
  ROOT="$(pwd)"
else
  ROOT="$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)"
  if [ -z "$ROOT" ] || [ ! -f "$ROOT/twine-seed.md" ]; then
    echo "[checkpoint] cannot find the twine-src tree from $(pwd) or from $0" >&2
    exit 2
  fi
fi
cd "$ROOT" || exit 2
echo "[checkpoint] writes: nothing"
echo "[checkpoint] tree: $ROOT"

python3 -B - "$ROOT" <<'PY'
import hashlib, json, re, sys
from pathlib import Path

ROOT = Path(sys.argv[1])
SEED = ROOT / "twine-seed.md"
NOTES = ROOT / "claude" / "responses" / "2026-10-05-twine-kill-followups-003" / "notes.md"
MANIFEST = ROOT / ".bale-manifest.json"

BASE_SHA = "491f71545b21f58074b5e2a95f29b1f1eb5bc74712f951507e5f3a029d4c0444"
BASE_LINES = 1358
LANDED_LINES = 1392

# The texts as the brief's fenced blocks carry them (byte-exact; text I's
# first line with the session id in place of <this-sid>).
J = """[2026-10-05-twine-kill-followups-003: landed — the kill's follow-ups.
The pin gates the closure alone (the sitting's correction to 5b, on the
worker's reading of D15): the abort and the process kill run with any
bale or none, and an unpinned bale stops the kill at the closure with
the unlock line. The running record carries `groups` — exactly six keys,
one entry per group the runtime registers through the run seam's
`on_spawn` hook (`twine.kill.register_group`, the moment a tool exists,
under a lock) — and `twine kill` signals every one of them, the
runtime's first, re-reads the record once for a group registered
meanwhile, and is done only when no member of any is alive; `dead` is
the record's whole. Two residuals, named in contract §14.4: pid reuse
past a full wrap, and the window between a child's `Popen` and its
hook's write in a runtime that is itself SIGKILLed. `twine status`
reports which state directory twine resolves and what of it exists. The
`[[wanted]]` entry asks bale-src for a JSON unlock refusal with a reason
code; twine keys the `bale revert` hand line on the stderr text until
then.]
"""
K = """[2026-10-05-twine-kill-followups-003: the kill follow-ups landed
(`VERSION` 0.7.0): the pin gate moved to the closure, the running
record's `groups` and the seam's spawn hook, `twine status`'s state
directory, the unlock `[[wanted]]`. Arc 2's loop composes the hook with
the record (`on_spawn=lambda pid: register_group(state_dir, sid, pid)`)
and may now run a tool.]
"""
I_TEMPLATE = """[<this-sid>: row 2 done — 2b-ii landed as
`2026-10-03-twine-carry-bale-002`: `carry exchange` (an intact exchange
block's own lines to `bale relay <sid> -`) and `carry response` (`bale
apply --dry-run --json`, then the one `bale apply` line handed to the
operator, T12), the recorded dry-run fixture, the fixture player on
normalized argvs, contract §11 and the `confined` switch point;
`VERSION` 0.3.0. With rows 0, 1, 4 and 5 landed above, Arc 1 waits only
on row 3.]
"""
SID_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*-\d{3}): row 2 done — 2b-ii landed as$")

# landed line numbers (1-based), from the brief's table
J_FIRST, J_LAST = 672, 688          # blanks at 671 and 689; D16 at 690
K_FIRST, K_LAST = 1093, 1098        # blanks at 1092 and 1099
I_FIRST, I_LAST = 1100, 1107        # blanks at 1099 and 1108; ### 5.2 at 1109
D16_LINE, S52_LINE = 690, 1109
D16_PREFIX = "**D16 — Effort is envelope × policy.**"
S52 = "### 5.2 Arc 2 — the runtime"

def _hook(exc_type, exc, tb):
    sys.stderr.write(f"[checkpoint] ORACLE ERROR {exc_type.__name__}: {exc}\n")
    import traceback; traceback.print_tb(tb, file=sys.stderr)
    sys.exit(2)
sys.excepthook = _hook

failures: list[str] = []
def result(name: str, problems: list[str]) -> None:
    if problems:
        failures.append(name); print(f"[FAIL] {name}")
        for p in problems: print(f"       - {p}")
    else:
        print(f"[PASS] {name}")

def words(text: str) -> list[str]:
    return text.split()

def framed_equal(got: str, expected: str) -> bool:
    """The one byte comparison every placement uses: the landed span from
    one line before the text to one line after it is blank + text + blank."""
    return got == "\n" + expected + "\n"

def blockquotes(notes_text: str) -> list[str]:
    """Each run of `> ` lines in the notes, prefixes stripped, joined by spaces."""
    out = []
    for run in re.findall(r"((?:^> ?.*\n)+)", notes_text, flags=re.M):
        out.append(" ".join(line[2:] if line.startswith("> ") else line[1:]
                            for line in run.splitlines()))
    return out

# --- the graded surface, read once ------------------------------------------
raw = SEED.read_bytes()
text = raw.decode("utf-8", errors="replace")
lines = text.split("\n")[:-1] if text.endswith("\n") else text.split("\n")

def span(first: int, last: int) -> str:
    """Lines first..last (1-based, inclusive) with their newlines."""
    return "".join(l + "\n" for l in lines[first - 1:last])

def line(n: int) -> str | None:
    return lines[n - 1] if 1 <= n <= len(lines) else None

# --- the detectors' control: a mutated copy must be caught (else exit 2) ----
def control() -> None:
    # placement detector: the framed block is seen, and a one-byte change is not
    bad = J.replace("every one of them", "every one of  them")
    if not framed_equal("\n" + J + "\n", J) or framed_equal("\n" + bad + "\n", J) \
            or framed_equal(J + "\n", J):
        raise RuntimeError("placement control: the byte comparison does not discriminate")
    # word detector: the notes' blockquote words differ from a mutated block
    fake_notes = "x\n\n" + "".join("> " + l + "\n" for l in J.splitlines()) + "\ny\n"
    if words(blockquotes(fake_notes)[0]) != words(J):
        raise RuntimeError("word control: a blockquote of J does not read back as J's words")
    if words(blockquotes(fake_notes)[0]) == words(J.replace("§14.4", "14.4")):
        raise RuntimeError("word control: a dropped § is not seen")
    if SID_RE.match("[2026-10-06-twine-seed-tidy4-001: row 2 done — 2b-ii landed as") is None:
        raise RuntimeError("sid control: a well-formed first line is not matched")
    if SID_RE.match("[<this-sid>: row 2 done — 2b-ii landed as") is not None:
        raise RuntimeError("sid control: the unsubstituted placeholder is matched")
    print("[checkpoint] control: detectors work (bytes, words, sid)")
control()

# --- encoding invariant -------------------------------------------------------
def probe_encoding() -> None:
    probs: list[str] = []
    if b"\r" in raw: probs.append("a CR byte is present")
    if not raw.endswith(b"\n"): probs.append("no final newline")
    try: raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc: probs.append(f"not UTF-8 at byte {exc.start}")
    result("encoding-utf8-lf-final-newline", probs)
probe_encoding()

# --- line count ---------------------------------------------------------------
def probe_line_count() -> None:
    probs: list[str] = []
    if len(lines) != LANDED_LINES:
        probs.append(f"{len(lines)} lines, expected {LANDED_LINES}")
    result("line-count-1392", probs)
probe_line_count()

# --- placements by strict line anchors ----------------------------------------
def probe_placement(name: str, expected: str, first: int, last: int,
                    after_line: int, after_text: str, by_prefix: bool = False) -> None:
    probs: list[str] = []
    got = span(first - 1, last + 1)
    if not framed_equal(got, expected):
        probs.append(f"lines {first - 1}–{last + 1} are not blank + the text + blank")
        exp_lines = expected.splitlines()
        for i, (a, b) in enumerate(zip(got.splitlines()[1:], exp_lines)):
            if a != b:
                probs.append(f"first difference at landed line {first + i}: {a!r} vs expected {b!r}")
                break
    anchor = line(after_line)
    ok = anchor is not None and (anchor.startswith(after_text) if by_prefix else anchor == after_text)
    if not ok:
        probs.append(f"line {after_line} is {anchor!r}, expected {'to start with ' if by_prefix else ''}{after_text!r}")
    result(name, probs)

probe_placement("placement-J-beneath-D15", J, J_FIRST, J_LAST, D16_LINE, D16_PREFIX, by_prefix=True)
probe_placement("placement-K-after-row5-annotation", K, K_FIRST, K_LAST, K_LAST + 1, "", by_prefix=False)

# --- text I: the sid read from the landed text, the manifest a cross-check ----
def probe_I() -> None:
    probs: list[str] = []
    first = line(I_FIRST) or ""
    m = SID_RE.match(first)
    sid = m.group(1) if m else None
    if sid is None:
        probs.append(f"line {I_FIRST} is {first!r}: not text I's first line with a session id in place of <this-sid>")
    else:
        expected = I_TEMPLATE.replace("<this-sid>", sid, 1)
        got = span(I_FIRST - 1, I_LAST + 1)
        if not framed_equal(got, expected):
            probs.append(f"lines {I_FIRST - 1}–{I_LAST + 1} are not blank + text I (sid {sid}) + blank")
        if MANIFEST.is_file():
            try:
                man = json.loads(MANIFEST.read_text("utf-8"))
                man_sid = man.get("session_id") if isinstance(man, dict) else None
            except ValueError:
                man_sid = None
            if man_sid != sid:
                probs.append(f"the manifest's session_id is {man_sid!r}, text I names {sid!r}")
        else:
            print("[checkpoint] no .bale-manifest.json beside the tree (a dry-run before any session): the sid cross-check is skipped")
    anchor = line(S52_LINE)
    if anchor != S52:
        probs.append(f"line {S52_LINE} is {anchor!r}, expected {S52!r}")
    result("placement-I-row2-marker-with-sid", probs)
probe_I()

# --- counts --------------------------------------------------------------------
def probe_counts() -> None:
    probs: list[str] = []
    n_this = text.count("<this-sid>")
    if n_this != 0: probs.append(f"<this-sid> occurs {n_this} time(s), expected 0")
    n_sid = text.count("<sid>"); l_sid = sum(1 for l in lines if "<sid>" in l)
    if (n_sid, l_sid) != (11, 10):
        probs.append(f"<sid> occurs {n_sid} time(s) on {l_sid} line(s), expected 11 on 10")
    result("placeholder-counts", probs)
probe_counts()

# --- reversal: remove the three insertions, recover the base -------------------
def probe_reversal() -> None:
    probs: list[str] = []
    if len(lines) != LANDED_LINES:
        probs.append("line count differs; the reversal is by index and cannot run")
    else:
        keep = [l for i, l in enumerate(lines, 1)
                if not (J_FIRST <= i <= J_LAST + 1 or K_FIRST <= i <= K_LAST + 1 or I_FIRST <= i <= I_LAST + 1)]
        back = "".join(l + "\n" for l in keep).encode("utf-8")
        digest = hashlib.sha256(back).hexdigest()
        if len(keep) != BASE_LINES or digest != BASE_SHA:
            probs.append(f"removing the insertions gives {len(keep)} lines, sha256 {digest[:12]}…; expected {BASE_LINES} lines, {BASE_SHA[:12]}…")
    result("reversal-to-base", probs)
probe_reversal()

# --- J and K word for word against the archived notes -------------------------
def probe_against_notes() -> None:
    probs: list[str] = []
    if not NOTES.is_file():
        probs.append(f"{NOTES.relative_to(ROOT)} is missing; the texts' source is not in the tree")
    else:
        bqs = blockquotes(NOTES.read_text("utf-8"))
        wanted = [b for b in bqs if b.startswith("[2026-10-05-twine-kill-followups-003:")]
        if len(wanted) != 2:
            probs.append(f"expected two blockquotes opening with the session's id in the notes, found {len(wanted)}")
        else:
            for name, landed_text, source in (("J", span(J_FIRST, J_LAST), wanted[0]),
                                              ("K", span(K_FIRST, K_LAST), wanted[1])):
                if words(landed_text) != words(source):
                    a, b = words(landed_text), words(source)
                    at = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
                    probs.append(f"text {name} differs from the notes at word {at + 1}: landed {a[at:at + 3]!r}, notes {b[at:at + 3]!r} ({len(a)} vs {len(b)} words)")
    result("J-and-K-match-the-archived-notes", probs)
probe_against_notes()

if failures:
    print(f"[checkpoint] {len(failures)} probe(s) failed: {', '.join(failures)}")
    sys.exit(1)
print("[checkpoint] all probes passed")
sys.exit(0)
PY

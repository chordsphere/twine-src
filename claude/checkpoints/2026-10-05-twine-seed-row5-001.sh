#!/usr/bin/env bash
# Blind checkpoint — twine-src seed tidy, the third (slug twine-seed-row5), v1.
# Authored at sitting 2026-10-03-continue-twine-006 from the request alone,
# before the work existed. It grades outcomes of the applied tree only:
#   - twine-seed.md carries the brief's two texts, byte-exact, each at its
#     placement (preceded by a blank line, followed by a blank line and its
#     end anchor), exactly once;
#   - the <this-sid> placeholder is gone and the <sid> templates stand (ten on
#     nine lines: the shipped six plus text G's four);
#   - deleting the two insertions restores the shipped seed byte-for-byte.
# It reads twine-seed.md in the current directory (the staging root; failing
# that, the root two levels above this script). The session id is read out of
# text H's opener; when .bale-manifest.json is present its session_id is
# cross-checked, and when it is absent (bale open's dry-run, before any session
# exists) that one check skips with its reason. It writes nothing. Exit 0: all
# probes pass. Exit 1: a probe failed (the work). Exit 2: the oracle itself is
# broken or cannot run. Derived from the second tidy's checkpoint v2.
set -u
echo "[checkpoint] twine-seed-row5 v1"
echo "[checkpoint] writes: none (reads twine-seed.md, and .bale-manifest.json when present)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[checkpoint] ERROR: python3 not found; the oracle cannot run"
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname -- "$0")" 2>/dev/null && pwd)"
export CHECKPOINT_SCRIPT_DIR="${SCRIPT_DIR:-}"

python3 -I -B - <<'PY'
import hashlib, json, os, re, sys, traceback

def _unexpected(exc_type, exc, tb):
    # An exception the oracle did not anticipate is the oracle breaking, not a
    # verdict on the work: TARBALL.md 7.5 gives that exit 2, never 1.
    traceback.print_exception(exc_type, exc, tb)
    print("[checkpoint] ERROR: the oracle raised an unexpected exception (exit 2)")
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(2)
sys.excepthook = _unexpected

SHIPPED_SHA = "12e87314ab46b053d90952856b80c4b9419d07e1f38416dac08f7f478e3f011c"
SHIPPED_LINES = 1332
LANDED_LINES = 1358
PLACEHOLDER = "<this-sid>"

# The six texts, byte-exact from the brief's fenced blocks (F with the
# placeholder still literal), each with the whole line that follows it.
TEXTS = {
"G": ("""[2026-10-04-twine-kill-switch-002: landed — the kill-switch's three
layers: the between-calls abort (`<state-dir>/abort/<sid>.json`, checked
by `twine.kill.abort_requested` before every call; observed, the loop
stops `killed` and closes), the process-level kill (the runtime's
running record `<state-dir>/running/<sid>.json`; SIGTERM, SIGCONT, a
grace, SIGKILL, finished only when no member of the group is alive, else
the survivors named), and the `aborted` closure (exactly `bale unlock
<sid> --reason aborted --json`, pinned bale, once, never while a member
lives). The operator's line is `twine kill <sid>`. The cost spine's
uncheckable cap stops `cap-unchecked` (move `fix-and-resume`, the
operator's). The record covers one process group; the runtime's tools in
groups of their own are Arc 2's (contract §14.4).]
""", "**D16 — Effort is envelope × policy.** The effort slider sets the", False),
"H": ("""[<this-sid>: row 5 done — 5b landed as
`2026-10-04-twine-kill-switch-002` (one HOLD, both judges: a worker test
checked a killed process once instead of polling, and the blind
checkpoint's running-record fixture lacked the `sid` key the worker's
reader requires, so the checkpoint was amended to v2 at the desk and the
retry applied with the change accepted; `VERSION` 0.6.0). The runner now
waits for the whole killed group (`RunResult.group_survivors`), which
plausibly explains cost-spine-005's HOLD sleep. Ratified at sitting
2026-10-03-continue-twine-006 from the session's notes, with one
correction queued: the pin gate moves to the closure alone, so the abort
and the signal need no bale. Of Arc 1, row 3 remains, waiting on `bale
open --json`.]
""", "### 5.2 Arc 2 — the runtime", False),
}

failures = []

def probe(label, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)

def oracle_error(msg):
    print(f"[checkpoint] ERROR: {msg}")
    sys.exit(2)

def needle(text, anchor):
    # The insertion as it sits in the landed file: the end of the paragraph
    # above, one blank line, the text, one blank line, the anchor line.
    return "\n\n" + text + "\n" + anchor + "\n"

def reversed_form(anchor, in_list):
    # What the same span was in the shipped file: list items ran straight
    # into the next; paragraphs already had their blank line.
    return ("\n" if in_list else "\n\n") + anchor + "\n"

SID_PATTERN = r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+-\d{3}"

def pattern_for(fragment):
    """A regex for `fragment` with every PLACEHOLDER standing for one and
    the same well-formed session id (the first is captured, the rest
    must repeat it). A fragment without the placeholder matches itself."""
    parts = fragment.split(PLACEHOLDER)
    out = re.escape(parts[0])
    for i, part in enumerate(parts[1:]):
        out += ("(" + SID_PATTERN + ")" if i == 0 else r"\1") + re.escape(part)
    return re.compile(out)

def detect(doc, text, anchor):
    """(placements, bare occurrences, sids): how often `text` sits at its
    placement, how often its bytes occur at all, and the session ids the
    placed copies carry (empty when the text has no placeholder)."""
    placed = list(pattern_for(needle(text, anchor)).finditer(doc))
    bare = len(list(pattern_for(text).finditer(doc)))
    sids = [m.group(1) for m in placed if m.groups()]
    return len(placed), bare, sids

# --- control: the detectors work on a synthetic document (exit 2 if not) ---
tA, aA, _ = TEXTS["G"]
synthetic = "x\n\n" + tA + "\n" + aA + "\nrest\n"
if detect(synthetic, tA, aA) != (1, 1, []):
    oracle_error("control: placement detector misses a correct landing")
mutant = synthetic.replace("SIGCONT", "SIGCONT.", 1)
if detect(mutant, tA, aA) != (0, 0, []):
    oracle_error("control: placement detector accepts a mutated text")
undone = synthetic.replace(needle(tA, aA), reversed_form(aA, False), 1)
if undone != "x\n\n" + aA + "\nrest\n":
    oracle_error("control: reversal does not restore the pre-insertion span")
tF, aF, _ = TEXTS["H"]
ctrl_sid = "2000-01-01-control-only-000"
placedF = tF.replace(PLACEHOLDER, ctrl_sid)
synthF = "x\n\n" + placedF + "\n" + aF + "\nrest\n"
if detect(synthF, tF, aF) != (1, 1, [ctrl_sid]):
    oracle_error("control: the placeholder-aware detector misses a correct landing or misreads its sid")
# (text H has one opener, so the two-different-sids control of the second tidy's
# oracle has nothing to check here and is omitted)
if detect(synthF.replace(ctrl_sid, PLACEHOLDER, 1), tF, aF) != (0, 0, []):
    oracle_error("control: the detector accepts a literal placeholder as a sid")
print("[checkpoint] control: detectors and reversal verified on synthetic documents")

# --- the manifest's session id, when a manifest is present (a cross-check) ---
manifest_sid = None
manifest_state = "absent"
if os.path.isfile(".bale-manifest.json"):
    try:
        with open(".bale-manifest.json", encoding="utf-8") as fh:
            manifest_sid = json.load(fh).get("session_id")
        manifest_state = "present"
    except (OSError, ValueError) as e:
        manifest_state = f"unreadable ({e})"
print(f"[checkpoint] .bale-manifest.json: {manifest_state}"
      + (f", session_id {manifest_sid}" if manifest_sid else ""))

# --- read the subject ---
if not os.path.isfile("twine-seed.md"):
    here = os.environ.get("CHECKPOINT_SCRIPT_DIR", "")
    root = os.path.dirname(os.path.dirname(here)) if here else ""
    if root and os.path.isfile(os.path.join(root, "twine-seed.md")):
        os.chdir(root)
        print(f"[checkpoint] subject not in the current directory; using the tree root above this script: {root}")
    else:
        oracle_error("twine-seed.md not found in the current directory nor two levels above this script")
raw = open("twine-seed.md", "rb").read()
try:
    doc = raw.decode("utf-8")
except UnicodeDecodeError as e:
    probe("seed-utf8-lf", False, f"not UTF-8: {e}")
    doc = raw.decode("utf-8", "replace")
else:
    probe("seed-utf8-lf", "\r" not in doc and doc.endswith("\n"),
          "CR present or no final newline")

# --- the six placements ---
work = doc
landed_sid = None
for key in "GH":
    text, anchor, in_list = TEXTS[key]
    n_place, n_text, sids = detect(doc, text, anchor)
    probe(f"placement-{key}", n_place == 1 and n_text == 1,
          f"text occurs {n_text}x, at its placement {n_place}x (want 1 and 1)")
    if n_place == 1:
        if sids:
            landed_sid = sids[0]
            text = text.replace(PLACEHOLDER, landed_sid)
        work = work.replace(needle(text, anchor), reversed_form(anchor, in_list), 1)
if landed_sid:
    print(f"[checkpoint] text H's opener carry the session id {landed_sid}")
if landed_sid is None:
    print("[SKIP] sid-matches-manifest: text H not found at its placement, so no landed sid to compare")
elif manifest_sid is None:
    print(f"[SKIP] sid-matches-manifest: .bale-manifest.json {manifest_state}; "
          "nothing to compare the landed sid against (bale open's dry-run runs before a session exists)")
else:
    probe("sid-matches-manifest", landed_sid == manifest_sid,
          f"text H names {landed_sid}, the manifest names {manifest_sid}")

# --- placeholders ---
probe("placeholder-gone", PLACEHOLDER not in doc,
      f"'{PLACEHOLDER}' still present")
sid_lines = [ln for ln in doc.split("\n") if "<sid>" in ln]
probe("sid-templates-unchanged",
      doc.count("<sid>") == 10 and len(sid_lines) == 9,
      f"<sid> occurs {doc.count('<sid>')}x on {len(sid_lines)} lines (want 10 on 9)")

# --- whole-file outcomes ---
probe("landed-line-count", doc.count("\n") == LANDED_LINES,
      f"{doc.count(chr(10))} lines (want {LANDED_LINES})")
rev_sha = hashlib.sha256(work.encode("utf-8")).hexdigest()
probe("reversal-restores-shipped-seed",
      rev_sha == SHIPPED_SHA and work.count("\n") == SHIPPED_LINES,
      f"after deleting the insertions: sha256 {rev_sha[:12]}…, "
      f"{work.count(chr(10))} lines (want {SHIPPED_SHA[:12]}…, {SHIPPED_LINES})")

if failures:
    print(f"[checkpoint] {len(failures)} probe(s) failed: {', '.join(failures)}")
    sys.exit(1)
print("[checkpoint] all probes passed")
sys.exit(0)
PY

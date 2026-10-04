#!/usr/bin/env bash
# Blind checkpoint — twine-src seed tidy, the second (slug twine-seed-landings), v2.
# Authored at sitting 2026-10-03-continue-twine-006 from the request alone,
# before the work existed. It grades outcomes of the applied tree only:
#   - twine-seed.md carries the brief's six texts, byte-exact, each at its
#     placement (preceded by a blank line, followed by a blank line and its
#     end anchor), exactly once;
#   - the <this-sid> placeholder is gone and the shipped <sid> templates stand;
#   - deleting the six insertions restores the shipped seed byte-for-byte.
# It reads twine-seed.md in the current directory (the staging root; failing
# that, the root two levels above this script, its committed home). The
# session id is read out of text F's two openers, which must agree; when
# .bale-manifest.json is present its session_id is cross-checked, and when it
# is absent (bale open's dry-run, before any session exists) that one check
# skips with its reason. It writes nothing. Exit 0: all probes pass. Exit 1: a
# probe failed (the work). Exit 2: the oracle itself is broken or cannot run.
# v2 (2026-10-04): v1 exited 2 at bale open's dry-run because it demanded a
# session id from a manifest or its own filename, neither of which exists
# before the session does. The probes and expected bytes are unchanged.
set -u
echo "[checkpoint] twine-seed-landings v2"
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

SHIPPED_SHA = "70637c290117bcbb774f1e8a4cf61f3a084263cbf6eb41f0c6a5a3f1ac188c64"
SHIPPED_LINES = 1273
LANDED_LINES = 1332
PLACEHOLDER = "<this-sid>"

# The six texts, byte-exact from the brief's fenced blocks (F with the
# placeholder still literal), each with the whole line that follows it.
TEXTS = {
"A": ("""[2026-10-03-twine-transitions-004: landed — `share/transitions.toml`,
rendered by `twine transitions`: bale 0.4.45's 13 telemetry outcomes, 9
closure reasons and the 9 outcomes `bale apply --json` prints (a third
vocabulary the seed did not name, read by probe at sitting
2026-10-03-continue-twine-003), keyed on the consumption manifest's
`[[vocabulary]]` data, plus twine's stop set — the sitting's ten and
`cap-reached` and `killed` from D15 — 43 rows over 25 declared moves,
each with one actor (twine, operator or planner), no default case. The
ratified edges hold: `held` gets `revert-and-repack`,
`malformed_response` and `malformed-shape` get `respawn-from-request`.
`tests/test_transitions.py` fails by name on any key without a move.]
""", "**D18 — Discussion paths are artifact rounds.** Master↔child", False),
"B": ("""[2026-10-03-twine-transitions-004: carried, and now enforced on the
courier — `carry exchange` and `carry response` refuse a bale whose
`bin/VERSION` is not the pin, or cannot be read, before starting it;
carry-bale-002's provisional report-only reading ended when the
transition table keyed on the pinned version's whole vocabulary.]
""", "**D3 — Narrowest consumption surface.** Rung 1 consumes the", False),
"C": ("""[2026-10-03-twine-cost-spine-005: landed in part — the spine:
`twine/spend.py` and `twine spend totals|check`; the usage record
(`<state-dir>/spend.jsonl`, five disjoint token classes, a nullable
`served_sid`), prices as operator data (twine ships none; an unpriced
model is a refusal), and the hard cap's pre-call check (own + served
spend plus the worst case, at most the cap, else `cap-reached`, never
shrunk). The kill-switch is session 5b's.]
""", "**D16 — Effort is envelope × policy.** The effort slider sets the", False),
"D": ("""  [2026-10-03-twine-cost-spine-005: ratified at sitting
  2026-10-03-continue-twine-003 (light block 5 [2], "as assumed") —
  per-session and per-arc envelopes, both checked before each call, the
  tighter binds; an arc keyed on the office's arc id with membership the
  office's declaration, arc spend counting each record once; no `arc`
  key in the record; an absent cap refuses. Shape in the session's
  notes.md.]
""", "- **Q-7 — The suite seams.** *Answered by the Nisaba seed* (its §1", True),
"E": ("""  [2026-10-03-twine-cost-spine-005: twine-side landed — the stream
  exists and is the owner; bale's mirror remains bale-src's.]
""", "- **TQ-1 — Where a worker's transcript lands.** Twine's log, or the", True),
"F": ("""[<this-sid>: row 4 landed as `2026-10-03-twine-transitions-004` —
`share/transitions.toml` and `twine transitions`, the stop set grown by
`cap-reached` and `killed` from D15, and the pin gate on the two carry
verbs (D2); `VERSION` 0.4.0. Ratified at sitting
2026-10-03-continue-twine-003 (light block 2 [1], "as assumed"); the
decisions it asks to have read are in
`claude/responses/2026-10-03-twine-transitions-004/notes.md`.]

[<this-sid>: row 5 split at sitting 2026-10-03-continue-twine-003 (light
block 4, "as assumed"). **5a — the cost spine**, landed as
`2026-10-03-twine-cost-spine-005` (one HOLD — a worker-test defect and a
pre-existing race in 2b-i's timeout tests — then applied on retry under
the same session, the checkpoint unamended; `VERSION` 0.5.0; its
decisions are in
`claude/responses/2026-10-03-twine-cost-spine-005/notes.md`). **5b — the
kill-switch**, queued: the between-calls abort, the process-level kill
and the `aborted` closure, carrying cost-spine-005's proposed
`cap-unchecked` stop key and the runner's open question, whether a run
returns only after every member of the killed group is reaped.]
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
tA, aA, _ = TEXTS["A"]
synthetic = "x\n\n" + tA + "\n" + aA + "\nrest\n"
if detect(synthetic, tA, aA) != (1, 1, []):
    oracle_error("control: placement detector misses a correct landing")
mutant = synthetic.replace("43 rows", "44 rows", 1)
if detect(mutant, tA, aA) != (0, 0, []):
    oracle_error("control: placement detector accepts a mutated text")
undone = synthetic.replace(needle(tA, aA), reversed_form(aA, False), 1)
if undone != "x\n\n" + aA + "\nrest\n":
    oracle_error("control: reversal does not restore the pre-insertion span")
tF, aF, _ = TEXTS["F"]
ctrl_sid = "2000-01-01-control-only-000"
placedF = tF.replace(PLACEHOLDER, ctrl_sid)
synthF = "x\n\n" + placedF + "\n" + aF + "\nrest\n"
if detect(synthF, tF, aF) != (1, 1, [ctrl_sid]):
    oracle_error("control: the placeholder-aware detector misses a correct landing or misreads its sid")
twoSids = synthF.replace("[" + ctrl_sid + ": row 5", "[2000-01-02-control-only-001: row 5", 1)
if detect(twoSids, tF, aF) != (0, 0, []):
    oracle_error("control: the detector accepts two different sids in text F's openers")
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
for key in "ABCDEF":
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
    print(f"[checkpoint] text F's openers carry the session id {landed_sid}")
if landed_sid is None:
    print("[SKIP] sid-matches-manifest: text F not found at its placement, so no landed sid to compare")
elif manifest_sid is None:
    print(f"[SKIP] sid-matches-manifest: .bale-manifest.json {manifest_state}; "
          "nothing to compare the landed sid against (bale open's dry-run runs before a session exists)")
else:
    probe("sid-matches-manifest", landed_sid == manifest_sid,
          f"text F names {landed_sid}, the manifest names {manifest_sid}")

# --- placeholders ---
probe("placeholder-gone", PLACEHOLDER not in doc,
      f"'{PLACEHOLDER}' still present")
sid_lines = [ln for ln in doc.split("\n") if "<sid>" in ln]
probe("sid-templates-unchanged",
      doc.count("<sid>") == 6 and len(sid_lines) == 5,
      f"<sid> occurs {doc.count('<sid>')}x on {len(sid_lines)} lines (want 6 on 5)")

# --- whole-file outcomes ---
probe("landed-line-count", doc.count("\n") == LANDED_LINES,
      f"{doc.count(chr(10))} lines (want {LANDED_LINES})")
rev_sha = hashlib.sha256(work.encode("utf-8")).hexdigest()
probe("reversal-restores-shipped-seed",
      rev_sha == SHIPPED_SHA and work.count("\n") == SHIPPED_LINES,
      f"after deleting the six insertions: sha256 {rev_sha[:12]}…, "
      f"{work.count(chr(10))} lines (want {SHIPPED_SHA[:12]}…, {SHIPPED_LINES})")

if failures:
    print(f"[checkpoint] {len(failures)} probe(s) failed: {', '.join(failures)}")
    sys.exit(1)
print("[checkpoint] all probes passed")
sys.exit(0)
PY

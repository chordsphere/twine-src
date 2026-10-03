#!/usr/bin/env bash
# Blind checkpoint — twine-src "seed and INDEX tidy" (slug twine-seed-tidy).
# Authored at sitting 2026-10-02-continue-twine-004 from the session's brief,
# before any implementation existed, by a desk that does not build against it.
#
# Outcomes graded (never mechanisms):
#   - the five openers carry one session id of this slug; no <this-sid> left;
#   - texts A-E sit byte-exact, once each, between their brief anchors;
#   - removing them gives back the shipped seed (sha256 74c454fb...);
#   - claude/INDEX.md is the shipped file with T1–T10 -> T1–T14, nothing else.
# Nothing outside the write forecast is asserted (twine-seed.md T3's second
# annotation): bale's forecast gate guards those paths.
#
# Read-only: writes nothing; Python runs with -B and PYTHONDONTWRITEBYTECODE.
# Exit codes (TARBALL.md 7.5): 0 all pass, 1 a probe failed, 2 the oracle
# itself is broken (failed control, missing interpreter, unlocatable root).
set -u
export PYTHONDONTWRITEBYTECODE=1

echo "checkpoint twine-seed-tidy v1: read-only, writes nothing"

root=""
if [ -f "./bale.toml" ]; then
  root="$(pwd)"
else
  here="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
  if [ -n "$here" ] && [ -f "$here/../../bale.toml" ]; then
    root="$(cd "$here/../.." && pwd)"
  fi
fi
if [ -z "$root" ]; then
  echo "[FAIL] control: repository root not found (no bale.toml at cwd or two levels above the script)"
  exit 2
fi
echo "root: $root"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[FAIL] control: python3 not found"
  exit 2
fi

python3 -B - "$root" <<'PY'
import hashlib, os, re, sys, traceback
from pathlib import Path

def _oracle_crashed(kind, value, tb):
    # An uncaught error is the oracle breaking, never a verdict: exit 2.
    print("[FAIL] control: the checkpoint itself raised an error")
    traceback.print_exception(kind, value, tb, file=sys.stdout)
    sys.stdout.flush()
    os._exit(2)
sys.excepthook = _oracle_crashed

root = Path(sys.argv[1])
SLUG = "twine-seed-tidy"
PLACEHOLDER = "<this-sid>"
SHIPPED_SEED_SHA = "74c454fbdfa9436125fde9faa9af32caf95694e3088ecfcbf04a566e6612a6b6"
EXPECTED_INDEX_SHA = "eb642699048512f201d538959a5fc2e175dd33dbbb0b00ee96d0983816fb9a5a"
TEXT_SHAS = {  # sha256 of each embedded text, placeholder unsubstituted, + "\n"
    "A": "fd229f223ddf01840fb769ebb99fe90d73ab7f8c866bf76f9387f3d63e917148", "B": "98aa5b68099cb189eed8e6e6959d87bea932d69eca13e8c11f66195e72ba98e5", "C": "199d917ffcbb23779247e98747d9ad238ea072dea79af5e592b95c31cf6bff19",
    "D": "c9645bdffdeb39170107cbb1b13ffb17e3991cbe693809c658630a9a72ddc1c8", "E": "48748636f1424e9375cf9a0de99a095d80f444642893aff4be01e1c6ced4bf58",
}

TEXTS = {
"A": r'''[<this-sid>: a correction to the annotation above. `bale.toml` does
hold its rationale today: the re-attempt of
`2026-10-02-twine-take-read-001` shipped the file back as its pinned
bytes, seed-001's explanatory header included, so the accidental
`bale config init` cost nothing that stayed lost. The annotation's
point stands: the next run of the wizard drops the header again, and
this annotation is the copy that survives it.]''',
"B": r'''[<this-sid>: brief authoring, learned at session
`2026-10-02-twine-seed-close-003`'s HOLD: a brief that hands over
text for substitution spells its target so that it cannot collide
with a placeholder in a command the text itself quotes. That brief
said to replace each `<sid>`, and one of its texts quoted
`bale relay <sid> -`, where `<sid>` is the exchange's session, not
the brief's; the worker replaced all three in that text, the
template's included, and the checkpoint held the result. Briefs
after it name a target no command uses, and substitute it only in
the annotation openers.]''',
"C": r'''[<this-sid>: a note on the parenthetical above. It summarizes
AGENT.md §3 rather than quoting it: §3 names five shapes within
tarball mode, the fifth being the bailout response, which is a
response tarball by kind (`response_kind: "bailout"`). A courier
that carries response tarballs carries bailouts with them, so the
count of four holds.]''',
"D": r'''[<this-sid>: row 2 of the table above is superseded in one clause.
Its "a response to `bale apply --no-interact --json`" describes the
path T12 rules out: with `--no-interact` the walkthrough merges on
PASS, and twine never merges at rung 1. The response hand-off is
2b-ii's `carry response`: `bale apply --dry-run --json`, then the
exact `bale apply` line handed to the operator.]''',
"E": r'''[<this-sid>: the drafting-table this arc reads is the home
office's. After the sitting closed, the architect wrote (message 12,
2026-10-02, verbatim): "one last thing, I developed offce to the
point where "nisaba office" is out of date language. I just have one
home office, probe if you need facts to update the plan". Probe
`home-office` (2026-10-02) found the office at `~/home-office`,
founded 2026-09-30 by `office init` from office-src 0.4.0, the
install now at 0.5.0, and no drafting-table in it: that is a
renovation space, and office-src's `renovate` verb is not built in
0.5.0. So "office 0.5.0's drafting-table" above names a space that
does not exist yet, and Arc 3 waits on two things: `renovate`
landing in office-src, and the home office's renovation with it.
`blueprints/drafting-table.md` in nisaba-src stays the spec of what
the scheduler reads.]''',
}

# (label, last line of the shipped paragraph before, end anchor after)
PLACES = {
"A": ("text A byte-exact beneath I2a, directly before I2b",
      "this annotation, not in the file.]",
      "[2026-10-02-twine-seed-close-003: checkpoint authoring, learned at session"),
"B": ("text B byte-exact beneath I2b, directly before T4",
      "worker. Checkpoints authored after it follow this rule.]",
      "**T4 — twine has three faces, one core: courier, runtime,"),
"C": ("text C byte-exact beneath I3, directly before T5",
      "sitting's close as a nisaba-src session.]",
      "**T5 — The arcs run courier, then runtime, then scheduler.** Ratified"),
"D": ("text D byte-exact at the end of the Arc 1 annotations, directly before 5.2",
      "never read as another shape to a reader that is not span-aware.]",
      "### 5.2 Arc 2 — the runtime"),
"E": ("text E byte-exact beneath 5.3, directly before the --- closing section 5",
      "copied here. Arc 3 is cut at the sitting that opens it.",
      "---\n\n## 6. Open questions register"),
}

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

# --- control: the oracle's own inputs are intact --------------------------
control_bad = []
for k, t in TEXTS.items():
    if not t.startswith("[" + PLACEHOLDER + ": ") or t.count(PLACEHOLDER) != 1:
        control_bad.append(f"text {k}: placeholder not exactly once at the opener")
    if sha((t + "\n").encode("utf-8")) != TEXT_SHAS[k]:
        control_bad.append(f"text {k}: embedded bytes differ from the published hash")
if set(TEXTS) != set(PLACES):
    control_bad.append("texts and placements disagree")
if control_bad:
    print("[FAIL] control: the checkpoint's embedded texts are not intact")
    for line in control_bad:
        print("  " + line)
    sys.exit(2)
print("[PASS] control: embedded texts intact")

failed = []
def verdict(ok: bool, label: str, detail: str = "") -> None:
    print(("[PASS] " if ok else "[FAIL] ") + label)
    if not ok:
        failed.append(label)
        if detail:
            print("  " + detail)

seed_path = root / "twine-seed.md"
index_path = root / "claude" / "INDEX.md"
try:
    seed = seed_path.read_bytes().decode("utf-8")
except (OSError, UnicodeDecodeError) as e:
    seed = None
    verdict(False, "seed: twine-seed.md readable as UTF-8", str(e))

if seed is not None:
    # One session id across the five openers, none left unsubstituted.
    opener_re = re.compile(r"^\[(\d{4}-\d{2}-\d{2}-" + re.escape(SLUG) + r"-\d{3}): ",
                           re.M)
    ids = opener_re.findall(seed)
    # The id most openers carry; a stray opener then fails alone.
    sid = max(sorted(set(ids)), key=ids.count) if ids else None
    verdict(len(ids) == 5 and len(set(ids)) == 1 and PLACEHOLDER not in seed,
            "seed: five openers, one session id of this slug, no <this-sid> left",
            f"openers found: {len(ids)}; distinct ids: {len(set(ids))}; "
            f"<this-sid> present: {PLACEHOLDER in seed}")

    landed = {k: (t.replace("[" + PLACEHOLDER + ": ", "[" + sid + ": ", 1)
                  if sid else None)
              for k, t in TEXTS.items()}
    for k, (label, before, anchor) in PLACES.items():
        body = landed[k]
        ok = body is not None and seed.count(body) == 1 and \
            seed.count(before + "\n\n" + body + "\n\n" + anchor) == 1
        verdict(ok, "seed: " + label)

    # Reversal: take each text and its one blank line back out.
    reverted = seed
    for k, (label, before, anchor) in PLACES.items():
        body = landed[k]
        if body is not None:
            reverted = reverted.replace(body + "\n\n" + anchor, anchor, 1)
    verdict(sha(reverted.encode("utf-8")) == SHIPPED_SEED_SHA,
            "seed: shipped lines intact (reversal to 74c454fb)")

try:
    index_sha = sha(index_path.read_bytes())
    verdict(index_sha == EXPECTED_INDEX_SHA,
            "INDEX: the seed entry reads T1–T14 and nothing else changed")
except OSError as e:
    verdict(False, "INDEX: the seed entry reads T1–T14 and nothing else changed",
            str(e))

print(f"checkpoint twine-seed-tidy v1: {len(failed)} probe(s) failed")
sys.exit(1 if failed else 0)
PY
rc=$?
case "$rc" in
  0|1|2) exit "$rc" ;;
  *) echo "[FAIL] control: python exited $rc"; exit 2 ;;
esac

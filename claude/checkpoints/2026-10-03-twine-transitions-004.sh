#!/usr/bin/env bash
# Blind checkpoint — twine-src Arc 1 session 4, the transition table (slug twine-transitions).
# Authored at sitting 2026-10-03-continue-twine-003 from the session's brief,
# before any implementation existed, by a desk that does not build against it.
#
# Outcomes graded (never mechanisms):
#   - `twine transitions --json` (python3 -I -S, no bale reachable) exits 0,
#     ok true, and its rows cover exactly bale 0.4.45's 13 telemetry
#     outcomes, 9 closure reasons and 9 apply outcomes, plus at least the
#     brief's ten stop keys; one row per (axis, key); every move declared,
#     with an actor of twine/operator/planner and a description;
#   - the ratified edges: held -> revert-and-repack, malformed_response and
#     malformed-shape -> respawn-from-request;
#   - the verb is registered with a --json twin; the suite passes;
#   - no test double spells the invented outcomes "refused" or "hold";
#   - the consumption manifest keeps pin 0.4.45 and its eight schema hashes
#     and carries every value of the three bale vocabularies as data;
#   - VERSION 0.4.0; the contract has a section headed for the verb; the
#     INDEX entries carry the Proposal's tokens and its verbatim phrase;
#     README no longer says the table is missing.
# Nothing outside the write forecast is asserted (twine-seed.md T3's second
# annotation): bale's forecast gate guards those paths.
#
# Read-only: writes nothing in the tree; Python runs with -B and
# PYTHONDONTWRITEBYTECODE; the suite runs as the session's own tests do.
# Exit codes (TARBALL.md 7.5): 0 all pass, 1 a probe failed, 2 the oracle
# itself is broken (failed control, missing interpreter, unlocatable root).
set -u
export PYTHONDONTWRITEBYTECODE=1

echo "checkpoint twine-transitions v1: read-only, writes nothing"

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
import hashlib, json, os, re, subprocess, sys, traceback
from pathlib import Path

def _oracle_crashed(kind, value, tb):
    # An uncaught error is the oracle breaking, never a verdict: exit 2.
    print("[FAIL] control: the checkpoint itself raised an error")
    traceback.print_exception(kind, value, tb, file=sys.stdout)
    sys.stdout.flush()
    os._exit(2)
sys.excepthook = _oracle_crashed

root = Path(sys.argv[1])

# The brief's vocabularies (§2.1-§2.3, read from bale 0.4.45 by probe) and
# its pinned stop keys (§3 item 2), with the sha256 of json.dumps(list).
TELEMETRY = ["opened", "applied", "held", "reverted", "rejected", "bailout",
             "scope-drift-refused", "required-check-refused", "base-drift-refused",
             "unlocked", "rolled-back", "re-applied", "relay-refused"]
CLOSURE = ["abandoned", "superseded-by-split", "reframed-after-clarification",
           "master-closeout", "crash-debris", "closed-read-only", "no_response",
           "malformed_response", "aborted"]
APPLY = ["applied", "held", "reverted", "bailout", "clarification", "dry-run",
         "scope-drift-refused", "required-check-refused", "base-drift-refused"]
STOP = ["end-turn", "max-tokens", "model-refusal", "window-exhausted", "rate-limited",
        "overloaded", "network-failure", "timeout", "tool-error", "malformed-shape"]
VOCAB = {"telemetry-outcome": (TELEMETRY, 13, "4c87353df1d0d1cab691624e3f537eeae60b7cccb2eeb52e7e1e1de3c108a86c"),
         "closure-reason": (CLOSURE, 9, "9f6794fd9013fd1da889843a26e5836ac8f0f24f8f2295a928cdbe1d960a877e"),
         "apply-outcome": (APPLY, 9, "f6555ddd35e81cbb3569a87eb3371294eb4a9e683c0408bfc6de2a43a794c467"),
         "stop": (STOP, 10, "25bc35203c4193fd1daccf01a6ab3cc7c0109be0f9ee18cbc70501394e404204")}
EXACT_AXES = ("telemetry-outcome", "closure-reason", "apply-outcome")
ACTORS = {"twine", "operator", "planner"}
PINNED_EDGES = [("telemetry-outcome", "held", "revert-and-repack"),
                ("apply-outcome", "held", "revert-and-repack"),
                ("closure-reason", "malformed_response", "respawn-from-request"),
                ("stop", "malformed-shape", "respawn-from-request")]
WILDCARDS = {"*", "", "default", "any", "else", "fallback"}
SCHEMA_PINS = {
    "bundle-manifest.schema.json": "3384ebcd52a08044356f30f1031f4389e9b4427d81602173b0c59f4f9f9cea23",
    "changelog-record.schema.json": "7b6d351c052dad8588b05e7592da78f9e9052a671ad6dae9395bfd6d531c5b5c",
    "diagnostics.schema.json": "bfeef3cc0a6b91b47b1c1c9084ca47349b23a6661b10c848da3b4ef28b413521",
    "escalation-record.schema.json": "16729aae82e20425f91b9fb343de6a74d00fa417ce3cd718767413deee550c41",
    "exchange-record.schema.json": "c9c291899103c4a73768ef930697722b89c5c3ef8f5b388c78c36741316cddc8",
    "request-manifest.schema.json": "70a0c2bd3b6b0d4cf17bc97010c2b7d58931527b7b3100aa984ca3576c075e3d",
    "response-manifest.schema.json": "02d2b6413d078e031641c99e09a9fea909555bdfcb9b2a8a110dbdce63f5817e",
    "telemetry-record.schema.json": "b79d7bf75c10f5799484f906954461e7379ef6d4a870bb7df8c08ce050b38825",
}
FIXTURES_PHRASE = "per-run values named by role; exit codes, `unrecorded` where not captured"
INVENTED = re.compile(r"""['"]outcome['"]\s*:\s*['"](refused|hold)['"]""")

# --- control: the oracle's own inputs are intact --------------------------
control_bad = []
for axis, (values, count, digest) in VOCAB.items():
    if len(values) != count or len(set(values)) != count:
        control_bad.append(f"{axis}: expected {count} distinct values")
    if hashlib.sha256(json.dumps(values).encode()).hexdigest() != digest:
        control_bad.append(f"{axis}: embedded list differs from its published hash")
for axis, key, _ in PINNED_EDGES:
    if key not in VOCAB[axis][0]:
        control_bad.append(f"pinned edge {axis}/{key} is not in its vocabulary")
if not INVENTED.search('{"outcome": "refused"}') or INVENTED.search('{"outcome": "held"}'):
    control_bad.append("the invented-spelling detector does not discriminate")
if control_bad:
    print("[FAIL] control: the checkpoint's embedded inputs are not intact")
    for line in control_bad:
        print("  " + line)
    sys.exit(2)
print("[PASS] control: embedded vocabularies and detectors intact")

failed = []
def verdict(ok, label, detail=""):
    print(("[PASS] " if ok else "[FAIL] ") + label)
    if not ok:
        failed.append(label)
        if detail:
            for line in str(detail).splitlines()[:12]:
                print("  " + line)

def norm(text):
    return " ".join(text.split())

def read(rel):
    try:
        return (root / rel).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return None

# A bale that cannot be reached: the verb must not need one.
env = dict(os.environ)
env["TWINE_BALE_ROOT"] = "/nonexistent/twine-checkpoint-no-bale"
env["PYTHONDONTWRITEBYTECODE"] = "1"

def twine(*argv, timeout=120):
    try:
        p = subprocess.run([sys.executable, "-I", "-S", str(root / "bin" / "twine"), *argv],
                           cwd=root, env=env, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return None, "", "timed out"

# --- VERSION ---------------------------------------------------------------
v = read("VERSION")
verdict(v is not None and v.strip() == "0.4.0", "VERSION is 0.4.0", f"VERSION reads {v!r}")

# --- the verb's JSON twin ----------------------------------------------------
rc, out, err = twine("transitions", "--json")
obj = None
lines = [l for l in out.splitlines() if l.strip()]
try:
    obj = json.loads(out) if len(lines) == 1 else None
except ValueError:
    obj = None
verdict(rc == 0 and isinstance(obj, dict) and obj.get("command") == "transitions"
        and obj.get("ok") is True,
        "transitions --json: exit 0, one JSON object, command 'transitions', ok true",
        f"exit {rc}; stdout lines {len(lines)}; stderr tail: {err[-600:]}")

rows = obj.get("rows") if isinstance(obj, dict) else None
moves = obj.get("moves") if isinstance(obj, dict) else None
rows_ok = isinstance(rows, list) and all(
    isinstance(r, dict) and all(isinstance(r.get(k), str) for k in ("axis", "key", "move"))
    for r in rows)
verdict(rows_ok, "rows: a list of objects with string axis, key and move")
moves_ok = isinstance(moves, dict) and all(
    isinstance(m, dict) and isinstance(m.get("actor"), str) and isinstance(m.get("description"), str)
    for m in moves.values())
verdict(moves_ok, "moves: an object of moves, each with string actor and description")

if rows_ok:
    pairs = [(r["axis"], r["key"]) for r in rows]
    dupes = sorted({p for p in pairs if pairs.count(p) > 1})
    verdict(not dupes, "one row per (axis, key)", f"duplicated: {dupes}")
    by_axis = {}
    for a, k in pairs:
        by_axis.setdefault(a, set()).add(k)
    for axis in EXACT_AXES:
        want = set(VOCAB[axis][0]); got = by_axis.get(axis, set())
        verdict(got == want, f"axis {axis}: keys are exactly bale 0.4.45's {len(want)}",
                f"missing: {sorted(want - got)}; not bale's: {sorted(got - want)}")
    got = by_axis.get("stop", set())
    verdict(set(STOP) <= got, "axis stop: carries the brief's ten keys",
            f"missing: {sorted(set(STOP) - got)}")
    wild = sorted(p for p in pairs if p[1].strip().lower() in WILDCARDS)
    verdict(not wild, "no default case: no wildcard or catch-all key", f"found: {wild}")
    if moves_ok:
        unresolved = sorted({r["move"] for r in rows if r["move"] not in moves})
        verdict(not unresolved, "every row's move is declared", f"undeclared: {unresolved}")
        bad_actor = sorted(n for n, m in moves.items()
                           if m["actor"] not in ACTORS or not m["description"].strip())
        verdict(not bad_actor, "every move's actor is twine, operator or planner, with a description",
                f"offending moves: {bad_actor}")
    table = {(r["axis"], r["key"]): r["move"] for r in rows}
    for axis, key, move in PINNED_EDGES:
        verdict(table.get((axis, key)) == move, f"ratified edge: {axis} {key} -> {move}",
                f"found: {table.get((axis, key))!r}")

# --- registered with a JSON twin ---------------------------------------------
rc2, out2, _ = twine("commands", "--json")
try:
    listing = json.loads(out2).get("commands", [])
except (ValueError, AttributeError):
    listing = []
row = next((c for c in listing if isinstance(c, dict) and c.get("name") == "transitions"), None)
verdict(rc2 == 0 and row is not None and row.get("json") is True,
        "twine commands lists transitions with a --json twin")

# --- the suite -----------------------------------------------------------------
try:
    p = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                       cwd=root, env=env, capture_output=True, timeout=900)
    verdict(p.returncode == 0, "the suite passes (python3 -B -m unittest discover -s tests -t .)",
            p.stderr.decode("utf-8", "replace")[-1500:])
except subprocess.TimeoutExpired:
    verdict(False, "the suite passes (python3 -B -m unittest discover -s tests -t .)", "timed out after 900 s")

# --- doubles speak bale's spellings ---------------------------------------------
hits = []
for path in sorted((root / "tests").rglob("*.py")):
    text = path.read_text(encoding="utf-8", errors="replace")
    for n, line in enumerate(text.splitlines(), 1):
        if INVENTED.search(line):
            hits.append(f"{path.relative_to(root)}:{n}: {line.strip()[:100]}")
verdict(not hits, "tests/: no double spells the invented outcomes 'refused' or 'hold'", "\n".join(hits))

# --- the consumption manifest ---------------------------------------------------
manifest_text = read("share/bale-consumption.toml")
try:
    import tomllib
    manifest = tomllib.loads(manifest_text) if manifest_text is not None else None
except Exception as e:
    manifest = None
    print(f"  (manifest does not parse: {e})")
if manifest is None:
    verdict(False, "share/bale-consumption.toml parses")
else:
    bale = manifest.get("bale", {})
    verdict(bale.get("pin") == "0.4.45" and bale.get("schemas") == SCHEMA_PINS,
            "consumption manifest: pin 0.4.45 and the eight schema hashes unchanged")
    strings = set()
    def walk(node):
        if isinstance(node, str): strings.add(node)
        elif isinstance(node, dict): [walk(v) for v in node.values()]
        elif isinstance(node, list): [walk(v) for v in node]
    walk(manifest)
    for axis in EXACT_AXES:
        missing = [v for v in VOCAB[axis][0] if v not in strings]
        verdict(not missing, f"consumption manifest: every {axis} value present as data",
                f"missing: {missing}")

# --- docs ---------------------------------------------------------------------------
contract = read("claude/context/cli-contract.md") or ""
verdict(any(l.startswith("## ") and "twine transitions" in l for l in contract.splitlines()),
        "contract: a ## section headed for twine transitions")

index = read("claude/INDEX.md") or ""
def entry(anchor):
    out, on = [], False
    for line in index.splitlines():
        if line.startswith(anchor):
            on = True; out.append(line); continue
        if on:
            if line.startswith("  ") and line.strip():
                out.append(line)
            else:
                break
    return norm("\n".join(out))
c_entry = entry("- `context/cli-contract.md`")
need = ["§11", "carry exchange", "carry response", "transitions"]
verdict(bool(c_entry) and all(t in c_entry for t in need),
        "INDEX: the cli-contract entry names §11, carry exchange, carry response and transitions",
        f"missing: {[t for t in need if t not in c_entry]}" if c_entry else "entry not found")
f_entry = entry("- `../fixtures/README.md`")
verdict(FIXTURES_PHRASE in f_entry,
        "INDEX: the fixtures entry carries the Proposal's phrase verbatim",
        "entry not found" if not f_entry else "phrase absent")

readme = read("README.md") or ""
verdict(readme != "" and "no transition table" not in norm(readme),
        "README: no longer says the transition table is missing")

print(f"checkpoint twine-transitions v1: {len(failed)} probe(s) failed")
sys.exit(1 if failed else 0)
PY
rc=$?
case "$rc" in
  0|1|2) exit "$rc" ;;
  *) echo "[FAIL] control: python exited $rc"; exit 2 ;;
esac

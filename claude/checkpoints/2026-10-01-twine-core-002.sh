#!/usr/bin/env bash
# Blind checkpoint — twine-src session twine-core (Arc 1, session 1), v1.
# Authored at sitting 2026-09-29-begin-harness-001 from the request alone,
# before any implementation exists (TARBALL.md 7; PLANNER.md 4). Outcome
# contracts only: what must be true of the applied tree, never how the
# worker got there. Runs with cwd = the staged tree, confined, network off.
# Exit 0 = every probe passed; 1 = a probe failed (HOLD); 2 = this script
# itself is broken (a failed control, or python3 missing).
#
# Writes: a private temp directory (mktemp -d, under the sandbox's /tmp),
# removed on exit. Nothing in the tree.

set -u
export PYTHONDONTWRITEBYTECODE=1
fails=0
pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; fails=$((fails + 1)); }
self_error() { echo "[ERROR] checkpoint: $1"; exit 2; }

command -v python3 >/dev/null 2>&1 || self_error "python3 not found on PATH"

TMP="$(mktemp -d 2>/dev/null || true)"
if [ -z "$TMP" ] || [ ! -d "$TMP" ]; then
  TMP="./.checkpoint-tmp.$$"; mkdir -p "$TMP" || self_error "cannot create a temp dir"
fi
trap 'rm -rf "$TMP"' EXIT
echo "checkpoint twine-core v1: temp dir $TMP (removed on exit); tree writes: none"

# ---- helpers -------------------------------------------------------------

# json_line FILE: 0 when FILE holds exactly one line and it parses as a JSON
# object; prints nothing. Used by the control and by the probes.
json_line() {
  python3 - "$1" <<'PY'
import json, sys
data = open(sys.argv[1], "rb").read()
lines = data.split(b"\n")
if data.endswith(b"\n"):
    lines = lines[:-1]
if len(lines) != 1:
    sys.exit(3)
try:
    obj = json.loads(lines[0].decode("utf-8"))
except (ValueError, UnicodeDecodeError):
    sys.exit(4)
sys.exit(0 if isinstance(obj, dict) else 5)
PY
}

# json_get FILE EXPR: evaluate a python expression over the parsed object `o`
# and print its repr; nonzero when the file is not one JSON line.
json_get() {
  python3 - "$1" "$2" <<'PY'
import json, sys
o = json.loads(open(sys.argv[1], "rb").read().decode("utf-8").strip())
print(repr(eval(sys.argv[2], {"o": o})))
PY
}

# run_twine OUT ERR ARGS...: run ./bin/twine, capture stdout/stderr, return code.
run_twine() {
  local out="$1" err="$2"; shift 2
  ./bin/twine "$@" >"$out" 2>"$err"
}

sha256_of() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }

# ---- control: the detectors detect ---------------------------------------
printf '{"a": 1}\n{"b": 2}\n' > "$TMP/two.json"
printf '{bad json\n' > "$TMP/bad.json"
printf '{"ok": true, "command": "x"}\n' > "$TMP/good.json"
if json_line "$TMP/two.json"; then self_error "control: json_line accepted two lines"; fi
if json_line "$TMP/bad.json"; then self_error "control: json_line accepted malformed JSON"; fi
json_line "$TMP/good.json" || self_error "control: json_line rejected a valid line"
[ "$(json_get "$TMP/good.json" 'o["ok"]')" = "True" ] || self_error "control: json_get misread a value"
echo "[control] detectors verified"

# ---- 1. the entrypoint ---------------------------------------------------
if [ -f bin/twine ] && [ -x bin/twine ]; then pass "bin/twine exists and is executable"
else fail "bin/twine exists and is executable"; fi

if [ -x bin/twine ]; then
  if run_twine "$TMP/h.out" "$TMP/h.err" --help; then pass "twine --help exits 0"
  else fail "twine --help exits 0"; fi

  if run_twine "$TMP/v.out" "$TMP/v.err" --version && [ "$(wc -l < "$TMP/v.out" | tr -d ' ')" = "1" ] \
     && grep -Eq '^twine [0-9]' "$TMP/v.out"; then pass "twine --version prints one line 'twine <version>'"
  else fail "twine --version prints one line 'twine <version>'"; fi

  # stdlib only (T9): the CLI loads and answers with site-packages disabled.
  if python3 -I -S bin/twine --version >"$TMP/s.out" 2>"$TMP/s.err" \
     && python3 -I -S bin/twine commands --json >"$TMP/s2.out" 2>"$TMP/s2.err"; then
    pass "twine runs under python3 -I -S (no third-party import at load)"
  else fail "twine runs under python3 -I -S (no third-party import at load)"; fi
else
  fail "twine --help exits 0"
  fail "twine --version prints one line 'twine <version>'"
  fail "twine runs under python3 -I -S (no third-party import at load)"
fi

# ---- 2. the command registry --------------------------------------------
if [ -x bin/twine ] && run_twine "$TMP/c.out" "$TMP/c.err" commands --json && json_line "$TMP/c.out" \
   && [ "$(json_get "$TMP/c.out" 'o["command"]')" = "'commands'" ] \
   && [ "$(json_get "$TMP/c.out" 'o["ok"]')" = "True" ]; then
  pass "twine commands --json: one JSON line with command=commands, ok=true"
  names="$(json_get "$TMP/c.out" 'sorted(c["name"] for c in o["commands"])' 2>/dev/null || echo "")"
  if printf '%s' "$names" | grep -q "'status'" && printf '%s' "$names" | grep -q "'bale check'" \
     && printf '%s' "$names" | grep -q "'commands'"; then
    pass "registry lists status, bale check and commands by name"
  else fail "registry lists status, bale check and commands by name"; fi
else
  fail "twine commands --json: one JSON line with command=commands, ok=true"
  fail "registry lists status, bale check and commands by name"
fi

# ---- 3. status -----------------------------------------------------------
if [ -x bin/twine ] && run_twine "$TMP/st.out" "$TMP/st.err" status --json && json_line "$TMP/st.out" \
   && [ "$(json_get "$TMP/st.out" 'o["command"]')" = "'status'" ] \
   && [ "$(json_get "$TMP/st.out" 'o["ok"]')" = "True" ]; then
  pass "twine status --json: one JSON line with command=status, ok=true"
else fail "twine status --json: one JSON line with command=status, ok=true"; fi

# ---- 4. the bale pin -----------------------------------------------------
mkdir -p "$TMP/bale-ok/bin" "$TMP/bale-old/bin" "$TMP/bale-none"
printf '0.4.45\n' > "$TMP/bale-ok/bin/VERSION"
printf '0.0.1\n'  > "$TMP/bale-old/bin/VERSION"

if [ -x bin/twine ] && run_twine "$TMP/p1.out" "$TMP/p1.err" bale check --bale-root "$TMP/bale-ok" --json \
   && json_line "$TMP/p1.out" \
   && [ "$(json_get "$TMP/p1.out" 'o["command"]')" = "'bale check'" ] \
   && [ "$(json_get "$TMP/p1.out" 'o["ok"]')" = "True" ]; then
  pass "bale check against an install at the pinned version: exit 0, ok=true"
else fail "bale check against an install at the pinned version: exit 0, ok=true"; fi

if [ -x bin/twine ]; then
  run_twine "$TMP/p2.out" "$TMP/p2.err" bale check --bale-root "$TMP/bale-old" --json; rc=$?
  if [ "$rc" -ne 0 ] && json_line "$TMP/p2.out" \
     && [ "$(json_get "$TMP/p2.out" 'o["ok"]')" = "False" ] \
     && ! grep -q "Traceback" "$TMP/p2.err"; then
    pass "bale check against a mismatched version: nonzero exit, one JSON line, ok=false, no traceback"
  else fail "bale check against a mismatched version: nonzero exit, one JSON line, ok=false, no traceback"; fi

  run_twine "$TMP/p3.out" "$TMP/p3.err" bale check --bale-root "$TMP/bale-none" --json; rc=$?
  if [ "$rc" -ne 0 ] && json_line "$TMP/p3.out" \
     && [ "$(json_get "$TMP/p3.out" 'o["ok"]')" = "False" ] \
     && ! grep -q "Traceback" "$TMP/p3.err"; then
    pass "bale check against a root with no bin/VERSION: nonzero exit, one JSON line, ok=false, no traceback"
  else fail "bale check against a root with no bin/VERSION: nonzero exit, one JSON line, ok=false, no traceback"; fi
else
  fail "bale check against a mismatched version: nonzero exit, one JSON line, ok=false, no traceback"
  fail "bale check against a root with no bin/VERSION: nonzero exit, one JSON line, ok=false, no traceback"
fi

# ---- 5. the consumption manifest ----------------------------------------
if [ -f share/bale-consumption.toml ] && python3 - <<'PY'
import tomllib, sys
d = tomllib.load(open("share/bale-consumption.toml", "rb"))
sys.exit(0 if d.get("bale", {}).get("pin") == "0.4.45" else 1)
PY
then pass "share/bale-consumption.toml parses and pins bale 0.4.45"
else fail "share/bale-consumption.toml parses and pins bale 0.4.45"; fi

# ---- 6. fixtures ---------------------------------------------------------
if [ -d fixtures/bale-0.4.45 ] && python3 - <<'PY'
import json, pathlib, sys
files = sorted(pathlib.Path("fixtures/bale-0.4.45").rglob("*.json"))
if len(files) < 2:
    sys.exit(1)
for f in files:
    json.loads(f.read_text(encoding="utf-8"))
sys.exit(0)
PY
then pass "fixtures/bale-0.4.45/ holds at least two recorded JSON fixtures, all parseable"
else fail "fixtures/bale-0.4.45/ holds at least two recorded JSON fixtures, all parseable"; fi

if [ -f fixtures/README.md ]; then pass "fixtures/README.md records how fixtures are made"
else fail "fixtures/README.md records how fixtures are made"; fi

# ---- 7. the test suite ---------------------------------------------------
if [ -d tests ] && python3 -B -m unittest discover -s tests -t . >"$TMP/t.out" 2>&1; then
  ran="$(grep -Eo 'Ran [0-9]+ tests?' "$TMP/t.out" | grep -Eo '[0-9]+' | head -n1)"
  if [ -n "${ran:-}" ] && [ "$ran" -ge 5 ]; then pass "python3 -B -m unittest discover -s tests -t . passes with at least 5 tests (ran $ran)"
  else fail "python3 -B -m unittest discover -s tests -t . passes with at least 5 tests (ran ${ran:-0})"; fi
else fail "python3 -B -m unittest discover -s tests -t . passes with at least 5 tests"; fi

# ---- 8. what must not have moved ----------------------------------------
if [ "$(sha256_of twine-seed.md)" = "55de078ea9f027e32fae28f0f35f23c95f3b67d28b3505eaee22e7ae465d6ecb" ]; then
  pass "twine-seed.md untouched (sha256 55de078e…)"
else fail "twine-seed.md untouched (sha256 55de078e…)"; fi

if [ "$(sha256_of bale.toml)" = "b09e9b065594c48b2eb6c1754dd19a0700a5415b14b67ac80d629294b03cfbff" ]; then
  pass "bale.toml untouched (sha256 b09e9b06…)"
else fail "bale.toml untouched (sha256 b09e9b06…)"; fi

# ---- 9. docs caught up ---------------------------------------------------
if [ -f README.md ] && ! grep -q "No code exists yet" README.md; then
  pass "README.md no longer says no code exists"
else fail "README.md no longer says no code exists"; fi

if [ -f claude/INDEX.md ] && python3 - <<'PY'
import pathlib, re, sys
base = pathlib.Path("claude")
bad = []
for line in pathlib.Path("claude/INDEX.md").read_text(encoding="utf-8").splitlines():
    m = re.match(r"^\s*-\s+`([^`]+)`", line)
    if m and not (base / m.group(1)).exists():
        bad.append(m.group(1))
sys.exit(1 if bad else 0)
PY
then pass "every path claude/INDEX.md lists exists"
else fail "every path claude/INDEX.md lists exists"; fi

if [ -z "$(find . -path ./.git -prune -o \( -name '*.pyc' -o -name '__pycache__' \) -print 2>/dev/null | head -n1)" ]; then
  pass "no bytecode or __pycache__ in the tree"
else fail "no bytecode or __pycache__ in the tree"; fi

# ---- verdict -------------------------------------------------------------
echo "checkpoint twine-core v1: $fails probe(s) failed"
[ "$fails" -eq 0 ] && exit 0 || exit 1

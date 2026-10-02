#!/usr/bin/env bash
# Blind checkpoint — twine-src session twine-carry-probe (Arc 1, session 2b-i), v1.
# Authored at sitting 2026-09-29-begin-harness-001 from the request alone,
# before any implementation exists (TARBALL.md 7; PLANNER.md 4). Outcome
# contracts only. cwd = the staged tree, confined, network off.
# Exit 0 pass; 1 a probe failed (HOLD); 2 this script is broken.
#
# Specimens: probe scaffolds emitted by bale 0.4.45's crafter
# (tools/craft_response.py --probe, sha256 66d38986…), filled
# mechanically (header lines and the probe() body replaced; one variant
# keeps the crafter's TODO(worker) placeholders, one drops the
# Read-only header line, one prints a wrong integrity count, one
# sleeps). Out-of-forecast files are not pinned here: bale's own
# forecast gate guards them (the sitting's 2026-10-02 authoring rule).
# Writes: one private temp directory (mktemp -d), removed on exit.

set -u
export PYTHONDONTWRITEBYTECODE=1
fails=0
pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; fails=$((fails + 1)); }
self_error() { echo "[ERROR] checkpoint: $1"; exit 2; }
command -v python3 >/dev/null 2>&1 || self_error "python3 not found on PATH"
command -v bash >/dev/null 2>&1 || self_error "bash not found on PATH"
TMP="$(mktemp -d 2>/dev/null || true)"
[ -n "$TMP" ] && [ -d "$TMP" ] || { TMP="./.checkpoint-tmp.$$"; mkdir -p "$TMP" || self_error "cannot create a temp dir"; }
trap 'rm -rf "$TMP"' EXIT
echo "checkpoint twine-carry-probe v1: temp dir $TMP (removed on exit); tree writes: none"

SPEC_B64='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'
mkdir -p "$TMP/s"
printf '%s' "$SPEC_B64" | base64 -d | tar -xzf - -C "$TMP/s" 2>/dev/null || self_error "could not unpack the embedded specimens"
[ -f "$TMP/s/t-one.txt" ] || self_error "specimens incomplete"
sed -i "s|@CANARY@|$TMP/canary.touched|" "$TMP/s/t-canary.txt"

cat > "$TMP/judge.py" <<'PYEOF'
import json, sys
out, err, rc, expr, label, cmd = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5], sys.argv[6]
def verdict(ok): print(("[PASS] " if ok else "[FAIL] ") + label)
try:
    data = open(out, "rb").read().decode("utf-8")
    errtext = open(err, "rb").read().decode("utf-8", "replace")
    lines = data.split("\n")
    if len(lines) != 2 or lines[1] != "": verdict(False); sys.exit(0)
    o = json.loads(lines[0])
    if not isinstance(o, dict) or o.get("command") != cmd or not isinstance(o.get("ok"), bool): verdict(False); sys.exit(0)
    if "Traceback" in errtext: verdict(False); sys.exit(0)
    if rc != (0 if o["ok"] else 1): verdict(False); sys.exit(0)
    verdict(bool(eval(expr, {"o": o, "rc": rc})))
except Exception:
    verdict(False)
PYEOF

printf '{"command": "carry probe", "ok": true, "ran": false}\n' > "$TMP/c1.out"; : > "$TMP/c.err"
printf '{"command": "carry probe", "ok": false}\n' > "$TMP/c2.out"
python3 "$TMP/judge.py" "$TMP/c1.out" "$TMP/c.err" 0 'o["ran"] is False' c1 "carry probe" | grep -q '^\[PASS\]' || self_error "control: judge rejected a good line"
python3 "$TMP/judge.py" "$TMP/c2.out" "$TMP/c.err" 0 'True' c2 "carry probe" | grep -q '^\[FAIL\]' || self_error "control: judge accepted ok false with exit 0"
python3 "$TMP/judge.py" "$TMP/c1.out" "$TMP/c.err" 0 'True' c3 "take" | grep -q '^\[FAIL\]' || self_error "control: judge accepted the wrong command"
echo "[control] judge verified"

carry() {  # carry NAME ARGS...: twine carry probe ARGS --json, captured; echoes rc
  local name="$1"; shift
  if [ -x bin/twine ]; then ./bin/twine carry probe "$@" --json >"$TMP/$name.out" 2>"$TMP/$name.err"; echo $?
  else : >"$TMP/$name.out"; : >"$TMP/$name.err"; echo 127; fi
}
judge() {  # judge NAME RC EXPR LABEL
  local line
  line="$(python3 "$TMP/judge.py" "$TMP/$1.out" "$TMP/$1.err" "$2" "$3" "$4" "carry probe")"
  echo "$line"
  case "$line" in "[FAIL]"*) fails=$((fails + 1));; "[PASS]"*) ;; *) self_error "judge printed no verdict for $4";; esac
}

# ---- 1. the verb ----------------------------------------------------------
if [ -x bin/twine ] && ./bin/twine commands --json >"$TMP/cmds.out" 2>/dev/null \
   && python3 -c 'import json,sys; o=json.loads(open(sys.argv[1]).read()); sys.exit(0 if any(c["name"]=="carry probe" and c["json"] for c in o["commands"]) else 1)' "$TMP/cmds.out"; then
  pass "twine commands lists carry probe with a --json twin"
else fail "twine commands lists carry probe with a --json twin"; fi

# ---- 2. without --run: shown, never run -------------------------------------
rc=$(carry show "$TMP/s/t-one.txt")
judge show "$rc" 'o["ok"] and o["ran"] is False and o["slug"] == "oracle-one" and o["confined"] is False' \
  "without --run: ok, ran false, slug oracle-one, confined false"
rc=$(carry canary "$TMP/s/t-canary.txt")
judge canary "$rc" 'o["ran"] is False' "a probe that would touch a file, without --run: ran false"
[ ! -e "$TMP/canary.touched" ] && pass "without --run nothing executes" || fail "without --run nothing executes"

# ---- 3. with --run: the paste-back -----------------------------------------
rc=$(carry run "$TMP/s/t-one.txt" --run --cwd "$TMP")
judge run "$rc" 'o["ok"] and o["ran"] is True and o["slug"] == "oracle-one" and o["exit_code"] == 0 and o["timed_out"] is False and o["integrity"]["ok"] is True and "=== PROBE BEGIN oracle-one ===" in o["output"] and "=== PROBE END oracle-one ===" in o["output"] and "hello from oracle-one" in o["output"]' \
  "--run: ran, exit 0, integrity verified, output is the paste-back block"
if [ -s "$TMP/run.out" ] && python3 -c 'import json,sys; sys.stdout.write(json.loads(open(sys.argv[1]).read())["output"])' "$TMP/run.out" > "$TMP/paste.txt" 2>/dev/null \
   && ./bin/twine take "$TMP/paste.txt" --json > "$TMP/retake.out" 2>/dev/null \
   && python3 -c 'import json,sys; o=json.loads(open(sys.argv[1]).read()); sys.exit(0 if o["ok"] and o["shape"]=="probe-output" and len(o["blocks"])==1 and o["blocks"][0]["slug"]=="oracle-one" else 1)' "$TMP/retake.out"; then
  pass "the reported output reads back through twine take as one intact probe-output block"
else fail "the reported output reads back through twine take as one intact probe-output block"; fi

rc=$(carry canaryrun "$TMP/s/t-canary.txt" --run --cwd "$TMP")
judge canaryrun "$rc" 'o["ok"] and o["ran"] is True' "--run runs the block it was given, in --cwd"

# ---- 4. refusals before running --------------------------------------------
rc=$(carry unfilled "$TMP/s/t-unfilled.txt" --run --cwd "$TMP")
judge unfilled "$rc" 'o["ok"] is False and o["ran"] is False' "--run refuses a crafter scaffold still carrying TODO(worker): ran false, exit 1"
rc=$(carry noro "$TMP/s/t-noreadonly.txt" --run --cwd "$TMP")
judge noro "$rc" 'o["ok"] is False and o["ran"] is False' "--run refuses a probe whose header declares no Read-only line: ran false, exit 1"
rc=$(carry none "$TMP/s/t-none.txt" --run --cwd "$TMP")
judge none "$rc" 'o["ok"] is False and o["ran"] is False' "no probe block in the input: ok false, ran false, exit 1"
rc=$(carry two "$TMP/s/t-two.txt" --run --cwd "$TMP")
judge two "$rc" 'o["ok"] is False and o["ran"] is False' "two probe blocks and no --block: refused, never guessed"
rc=$(carry twoB "$TMP/s/t-two.txt" --block 2 --run --cwd "$TMP")
judge twoB "$rc" 'o["ok"] and o["ran"] is True and o["slug"] == "oracle-two" and "hello from oracle-two" in o["output"]' \
  "--block 2 selects the second block (the numbering twine take prints) and runs it"

# ---- 5. failures after running ---------------------------------------------
rc=$(carry bad "$TMP/s/t-badtrailer.txt" --run --cwd "$TMP")
judge bad "$rc" 'o["ok"] is False and o["ran"] is True and o["integrity"]["ok"] is False' \
  "a probe whose own trailer is wrong: ran, integrity not ok, exit 1"
start=$(date +%s)
rc=$(carry slow "$TMP/s/t-slow.txt" --run --cwd "$TMP" --timeout 2)
elapsed=$(( $(date +%s) - start ))
judge slow "$rc" 'o["ok"] is False and o["ran"] is True and o["timed_out"] is True' "--timeout 2 on a probe that sleeps 30s: timed out, ok false, exit 1"
[ "$elapsed" -lt 20 ] && pass "the timeout returns promptly (${elapsed}s)" || fail "the timeout returns promptly (${elapsed}s)"

# ---- 6. --out -------------------------------------------------------------
rc=$(carry outw "$TMP/s/t-one.txt" --run --cwd "$TMP" --out "$TMP/paste-out.txt")
judge outw "$rc" 'o["ok"] and o["ran"] is True' "--out: ok"
if [ -f "$TMP/paste-out.txt" ] && grep -qx "=== PROBE BEGIN oracle-one ===" "$TMP/paste-out.txt" && grep -qx "=== PROBE END oracle-one ===" "$TMP/paste-out.txt"; then
  pass "--out writes the paste-back block to the named file"; else fail "--out writes the paste-back block to the named file"; fi
cp "$TMP/paste-out.txt" "$TMP/paste-out.before" 2>/dev/null || : > "$TMP/paste-out.before"
rc=$(carry outx "$TMP/s/t-one.txt" --run --cwd "$TMP" --out "$TMP/paste-out.txt")
judge outx "$rc" 'o["ok"] is False' "--out onto an existing file: refused, exit 1"
cmp -s "$TMP/paste-out.txt" "$TMP/paste-out.before" && pass "--out never overwrites" || fail "--out never overwrites"

# ---- 7. the tree ------------------------------------------------------------
if [ -x bin/twine ] && [ "$(./bin/twine --version 2>/dev/null)" = "twine 0.2.0" ]; then pass "twine --version prints twine 0.2.0"
else fail "twine --version prints twine 0.2.0"; fi
if [ -x bin/twine ] && python3 -I -S -B bin/twine carry probe "$TMP/s/t-one.txt" --json >"$TMP/iso.out" 2>"$TMP/iso.err"; then
  judge iso 0 'o["ran"] is False' "carry probe runs under python3 -I -S (stdlib only)"
else fail "carry probe runs under python3 -I -S (stdlib only)"; fi
if [ -d tests ] && python3 -B -m unittest discover -s tests -t . >"$TMP/t.out" 2>&1; then pass "the suite passes: python3 -B -m unittest discover -s tests -t ."
else fail "the suite passes: python3 -B -m unittest discover -s tests -t ."; fi
[ "$(sha256sum twine-seed.md 2>/dev/null | cut -d' ' -f1)" = "cabf76158430bdcb84366afc52cbea6c5662e2870e069f8375f69642cd3e164e" ] \
  && pass "twine-seed.md untouched (sha256 cabf7615…)" || fail "twine-seed.md untouched (sha256 cabf7615…)"
if [ -z "$(find . -path ./.git -prune -o \( -name '*.pyc' -o -name '__pycache__' \) -print 2>/dev/null | head -n1)" ]; then
  pass "no bytecode or __pycache__ in the tree"; else fail "no bytecode or __pycache__ in the tree"; fi
grep -q "carry probe" claude/context/cli-contract.md 2>/dev/null && pass "cli-contract.md names carry probe" || fail "cli-contract.md names carry probe"

echo "checkpoint twine-carry-probe v1: $fails probe(s) failed"
[ "$fails" -eq 0 ] && exit 0 || exit 1

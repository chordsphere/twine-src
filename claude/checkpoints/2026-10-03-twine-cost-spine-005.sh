#!/usr/bin/env bash
# Blind checkpoint — twine-src Arc 1 session 5a, the cost spine (slug twine-cost-spine).
# Authored at sitting 2026-10-03-continue-twine-003 from the session's brief,
# before any implementation existed, by a desk that does not build against it.
#
# Outcomes graded (never mechanisms), through the CLI only:
#   - `spend totals` reads <state-dir>/spend.jsonl (the brief's record shape)
#     and a price file of USD per million tokens, and reports per-session
#     calls, token totals by class, own and served cost, and the stream total;
#     --sid filters; the state dir resolves --state-dir > $TWINE_STATE_DIR >
#     $XDG_STATE_HOME/twine; an empty stream is ok; a malformed line or an
#     unpriced model is not-ok, exit 1;
#   - `spend check` admits exactly when spend so far (own + served) plus the
#     worst case (input at the dearest input-side price, max output at the
#     output price) is at most the cap; a refusal is exit 1 with
#     stop "cap-reached"; an unpriced model is never admitted;
#   - both verbs are registered with --json twins; the suite passes;
#   - VERSION 0.5.0; the contract has a section headed for twine spend and
#     names the probe twine-usage-record; INDEX mentions spend and prices;
#     README no longer says there is no cost spine; no spend stream lands in
#     the tree.
# Nothing outside the write forecast is asserted (twine-seed.md T3's second
# annotation): bale's forecast gate guards those paths.
#
# Writes nothing in the tree. It builds its test streams and price files in
# temporary directories outside the tree (python tempfile) and removes them.
# Python runs with -B and PYTHONDONTWRITEBYTECODE.
# Exit codes (TARBALL.md 7.5): 0 all pass, 1 a probe failed, 2 the oracle
# itself is broken (failed control, missing interpreter, unlocatable root).
set -u
export PYTHONDONTWRITEBYTECODE=1

echo "checkpoint twine-cost-spine v1: writes nothing in the tree"

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
import json, os, shutil, subprocess, sys, tempfile, traceback
from pathlib import Path

def _oracle_crashed(kind, value, tb):
    # An uncaught error is the oracle breaking, never a verdict: exit 2.
    print("[FAIL] control: the checkpoint itself raised an error")
    traceback.print_exception(kind, value, tb, file=sys.stdout)
    sys.stdout.flush()
    os._exit(2)
sys.excepthook = _oracle_crashed

root = Path(sys.argv[1])
TOL = 1e-9
CLASSES = ("input", "output", "thinking", "cache_read", "cache_write")

# Test data — invented prices and usage, doubles for the oracle's own use.
PRICES_TOML = '''# checkpoint test data: invented prices, USD per million tokens
[model."ckpt-model"]
input = 3
output = 15
cache_read = 0.3
cache_write = 3.75
'''
PRICES = {"input": 3, "output": 15, "cache_read": 0.3, "cache_write": 3.75}
RECORDS = [
    {"sid": "ckpt-a", "served_sid": None, "model": "ckpt-model",
     "tokens": {"input": 1000, "output": 200, "thinking": 300, "cache_read": 5000, "cache_write": 0},
     "ckpt_unknown_key": "kept, never fatal"},
    {"sid": "ckpt-a", "served_sid": None, "model": "ckpt-model",
     "tokens": {"input": 2000, "output": 100, "thinking": None, "cache_read": 0, "cache_write": 4000}},
    {"sid": "ckpt-b", "served_sid": "ckpt-a", "model": "ckpt-model",
     "tokens": {"input": 500, "output": 50, "thinking": None, "cache_read": 0, "cache_write": 0}},
]
# Worked by hand from the brief's rules (published; the control recomputes them).
EXPECT = {
    "ckpt-a": {"calls": 2, "tokens": {"input": 3000, "output": 300, "thinking": 300,
                                      "cache_read": 5000, "cache_write": 4000},
               "cost_usd": 0.0345, "served_cost_usd": 0.00225},
    "ckpt-b": {"calls": 1, "tokens": {"input": 500, "output": 50, "thinking": None,
                                      "cache_read": 0, "cache_write": 0},
               "cost_usd": 0.00225, "served_cost_usd": 0.0},
}
EXPECT_TOTAL = 0.03675
# spend check for ckpt-a, --input 10000 --max-output 1000:
#   so far 0.0345 + 0.00225 = 0.03675; worst 10000*3.75/1e6 + 1000*15/1e6 = 0.0525; sum 0.08925
CHECKS = [("1.0", True), ("0.0890", False), ("0.0893", True)]
CHECK_SUM = 0.08925

def cost(t):
    c = sum(t[k] * PRICES[k] for k in ("input", "output", "cache_read", "cache_write"))
    if t["thinking"] is not None:
        c += t["thinking"] * PRICES["output"]
    return c / 1e6

# --- control: the oracle's own expectations agree with its data ------------
bad = []
for sid, exp in EXPECT.items():
    own = [r for r in RECORDS if r["sid"] == sid]
    served = [r for r in RECORDS if r["served_sid"] == sid]
    if len(own) != exp["calls"]: bad.append(f"{sid}: calls")
    if abs(sum(cost(r["tokens"]) for r in own) - exp["cost_usd"]) > TOL: bad.append(f"{sid}: cost")
    if abs(sum(cost(r["tokens"]) for r in served) - exp["served_cost_usd"]) > TOL: bad.append(f"{sid}: served")
    for k in CLASSES:
        vals = [r["tokens"][k] for r in own]
        want = None if all(v is None for v in vals) else sum(v for v in vals if v is not None)
        if want != exp["tokens"][k]: bad.append(f"{sid}: tokens.{k}")
if abs(sum(cost(r["tokens"]) for r in RECORDS) - EXPECT_TOTAL) > TOL: bad.append("total")
worst = 10000 * max(PRICES["input"], PRICES["cache_read"], PRICES["cache_write"]) / 1e6 + 1000 * PRICES["output"] / 1e6
if abs(EXPECT["ckpt-a"]["cost_usd"] + EXPECT["ckpt-a"]["served_cost_usd"] + worst - CHECK_SUM) > TOL: bad.append("check sum")
for cap, admitted in CHECKS:
    if (CHECK_SUM <= float(cap) + TOL) != admitted: bad.append(f"check cap {cap}")
if bad:
    print("[FAIL] control: the checkpoint's expectations disagree with its own data")
    for b in bad: print("  " + b)
    sys.exit(2)
print("[PASS] control: expectations recomputed from the oracle's data")

failed = []
def verdict(ok, label, detail=""):
    print(("[PASS] " if ok else "[FAIL] ") + label)
    if not ok:
        failed.append(label)
        if detail:
            for line in str(detail).splitlines()[:12]:
                print("  " + line)

scratch = Path(tempfile.mkdtemp(prefix="twine-ckpt-spend-"))
try:
    base_env = {k: v for k, v in os.environ.items()
                if k not in ("TWINE_STATE_DIR", "XDG_STATE_HOME")}
    base_env["TWINE_BALE_ROOT"] = str(scratch / "no-bale-here")
    base_env["PYTHONDONTWRITEBYTECODE"] = "1"
    base_env["HOME"] = str(scratch / "home")   # the real default is never touched
    (scratch / "home").mkdir()

    def twine(*argv, env=None):
        try:
            p = subprocess.run([sys.executable, "-I", "-S", str(root / "bin" / "twine"), *argv],
                               cwd=root, env=env or base_env, capture_output=True, timeout=120)
            return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            return None, "", "timed out"

    def as_json(out):
        lines = [l for l in out.splitlines() if l.strip()]
        if len(lines) != 1:
            return None
        try:
            obj = json.loads(lines[0])
        except ValueError:
            return None
        return obj if isinstance(obj, dict) else None

    def num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    def state(name, lines):
        d = scratch / name
        d.mkdir()
        (d / "spend.jsonl").write_text("".join(l + "\n" for l in lines), encoding="utf-8")
        (d / "prices.toml").write_text(PRICES_TOML, encoding="utf-8")
        return d

    good = state("good", [json.dumps(r) for r in RECORDS])
    empty = scratch / "empty"; empty.mkdir()
    (empty / "prices.toml").write_text(PRICES_TOML, encoding="utf-8")

    # --- VERSION ------------------------------------------------------------
    try:
        v = (root / "VERSION").read_text(encoding="utf-8")
    except OSError as e:
        v = None
    verdict(v is not None and v.strip() == "0.5.0", "VERSION is 0.5.0", f"VERSION reads {v!r}")

    # --- registered ---------------------------------------------------------
    rc, out, _ = twine("commands", "--json")
    obj = as_json(out) or {}
    listing = {c.get("name"): c for c in obj.get("commands", []) if isinstance(c, dict)}
    for name in ("spend totals", "spend check"):
        verdict(rc == 0 and name in listing and listing[name].get("json") is True,
                f"twine commands lists {name} with a --json twin")

    # --- totals -------------------------------------------------------------
    rc, out, err = twine("spend", "totals", "--state-dir", str(empty), "--json")
    obj = as_json(out)
    verdict(rc == 0 and obj is not None and obj.get("command") == "spend totals"
            and obj.get("ok") is True and obj.get("sessions") == [],
            "spend totals on an empty state dir: exit 0, ok true, sessions []",
            f"exit {rc}; stdout {out[:300]!r}; stderr {err[-300:]!r}")

    def check_totals(label, argv, env=None, only=None):
        rc, out, err = twine("spend", "totals", *argv, "--json", env=env)
        obj = as_json(out)
        if not (rc == 0 and obj is not None and obj.get("ok") is True
                and isinstance(obj.get("sessions"), list)):
            verdict(False, label, f"exit {rc}; stdout {out[:400]!r}; stderr {err[-400:]!r}")
            return
        by = {s.get("sid"): s for s in obj["sessions"] if isinstance(s, dict)}
        want = {k: EXPECT[k] for k in (only or EXPECT)}
        problems = []
        if set(by) != set(want):
            problems.append(f"sessions {sorted(map(str, by))}, want {sorted(want)}")
        for sid, exp in want.items():
            s = by.get(sid, {})
            if s.get("calls") != exp["calls"]: problems.append(f"{sid}.calls {s.get('calls')!r}")
            if s.get("tokens") is None or any(s["tokens"].get(k) != exp["tokens"][k] for k in CLASSES):
                problems.append(f"{sid}.tokens {s.get('tokens')!r}")
            for k in ("cost_usd", "served_cost_usd"):
                if not num(s.get(k)) or abs(s[k] - exp[k]) > TOL:
                    problems.append(f"{sid}.{k} {s.get(k)!r}, want {exp[k]}")
        if only is None and (not num(obj.get("total_cost_usd")) or abs(obj["total_cost_usd"] - EXPECT_TOTAL) > TOL):
            problems.append(f"total_cost_usd {obj.get('total_cost_usd')!r}, want {EXPECT_TOTAL}")
        verdict(not problems, label, "\n".join(problems))

    check_totals("spend totals: calls, tokens by class, own and served cost, stream total",
                 ["--state-dir", str(good)])
    check_totals("spend totals --sid: only the named session", ["--state-dir", str(good), "--sid", "ckpt-b"],
                 only=["ckpt-b"])
    env_t = dict(base_env); env_t["TWINE_STATE_DIR"] = str(good)
    check_totals("state dir from $TWINE_STATE_DIR", [], env=env_t)
    xdg = scratch / "xdg"; shutil.copytree(good, xdg / "twine")
    env_x = dict(base_env); env_x["XDG_STATE_HOME"] = str(xdg)
    check_totals("state dir from $XDG_STATE_HOME/twine", [], env=env_x)
    other_prices = scratch / "prices-elsewhere.toml"
    other_prices.write_text(PRICES_TOML, encoding="utf-8")
    noprice = state("noprice-file", [json.dumps(r) for r in RECORDS]); (noprice / "prices.toml").unlink()
    check_totals("--prices PATH overrides <state-dir>/prices.toml",
                 ["--state-dir", str(noprice), "--prices", str(other_prices)])

    malformed = state("malformed", [json.dumps(RECORDS[0]), "this line is not json", json.dumps(RECORDS[1])])
    rc, out, _ = twine("spend", "totals", "--state-dir", str(malformed), "--json")
    obj = as_json(out)
    verdict(rc == 1 and obj is not None and obj.get("ok") is False,
            "spend totals: a malformed line is not-ok, exit 1", f"exit {rc}; stdout {out[:300]!r}")

    unpriced_rec = dict(RECORDS[0]); unpriced_rec["model"] = "ckpt-unpriced-model"
    unpriced = state("unpriced", [json.dumps(unpriced_rec)])
    rc, out, _ = twine("spend", "totals", "--state-dir", str(unpriced), "--json")
    obj = as_json(out)
    verdict(rc == 1 and obj is not None and obj.get("ok") is False,
            "spend totals: an unpriced model is not-ok, exit 1", f"exit {rc}; stdout {out[:300]!r}")

    # --- check --------------------------------------------------------------
    def check(cap, model="ckpt-model", state_dir=good):
        rc, out, err = twine("spend", "check", "--sid", "ckpt-a", "--cap", cap, "--model", model,
                             "--input", "10000", "--max-output", "1000",
                             "--state-dir", str(state_dir), "--json")
        return rc, as_json(out), out, err

    for cap, admitted in CHECKS:
        rc, obj, out, err = check(cap)
        if admitted:
            ok = rc == 0 and obj is not None and obj.get("command") == "spend check" and obj.get("ok") is True
            verdict(ok, f"spend check --cap {cap}: admitted (so far + worst case = {CHECK_SUM})",
                    f"exit {rc}; stdout {out[:400]!r}; stderr {err[-300:]!r}")
        else:
            ok = rc == 1 and obj is not None and obj.get("ok") is False and obj.get("stop") == "cap-reached"
            verdict(ok, f"spend check --cap {cap}: refused, exit 1, stop cap-reached",
                    f"exit {rc}; stdout {out[:400]!r}; stderr {err[-300:]!r}")

    rc, obj, out, _ = check("1000", model="ckpt-unpriced-model")
    verdict(rc == 1 and obj is not None and obj.get("ok") is False,
            "spend check: an unpriced model is never admitted (exit 1)", f"exit {rc}; stdout {out[:300]!r}")

    # --- the suite ------------------------------------------------------------
    try:
        p = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                           cwd=root, env=base_env, capture_output=True, timeout=900)
        verdict(p.returncode == 0, "the suite passes (python3 -B -m unittest discover -s tests -t .)",
                p.stderr.decode("utf-8", "replace")[-1500:])
    except subprocess.TimeoutExpired:
        verdict(False, "the suite passes (python3 -B -m unittest discover -s tests -t .)", "timed out after 900 s")

    # --- nothing landed in the tree, nothing at the scratch HOME's default ----
    strays = [str(p.relative_to(root)) for p in root.rglob("spend.jsonl")]
    verdict(not strays, "no spend stream in the tree", f"found: {strays}")
    default = scratch / "home" / ".local" / "state" / "twine" / "spend.jsonl"
    verdict(not default.exists(), "no run with an explicit state dir wrote to the default")

    # --- docs -------------------------------------------------------------------
    def read(rel):
        try:
            return (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""
    norm = lambda s: " ".join(s.split())
    contract = read("claude/context/cli-contract.md")
    verdict(any(l.startswith("## ") and "twine spend" in l for l in contract.splitlines()),
            "contract: a ## section headed for twine spend")
    verdict("twine-usage-record" in contract, "contract: names the probe twine-usage-record")
    index = read("claude/INDEX.md").lower()
    verdict("spend" in index and "price" in index, "INDEX: mentions the spend stream and the price file")
    readme = norm(read("README.md"))
    verdict(readme != "" and "no cost spine" not in readme, "README: no longer says there is no cost spine")
finally:
    shutil.rmtree(scratch, ignore_errors=True)

print(f"checkpoint twine-cost-spine v1: {len(failed)} probe(s) failed")
sys.exit(1 if failed else 0)
PY
rc=$?
case "$rc" in
  0|1|2) exit "$rc" ;;
  *) echo "[FAIL] control: python exited $rc"; exit 2 ;;
esac

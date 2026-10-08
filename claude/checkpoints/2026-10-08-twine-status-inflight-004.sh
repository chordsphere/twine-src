#!/usr/bin/env bash
# Blind checkpoint — session twine-status-inflight (v1), authored at the
# desk of sitting 2026-10-08-open-arc2-003 from the request alone.
#
# What it grades (outcomes only, never how): `twine status` reads
# twine's in-flight records. `state_present` gains a fifth member,
# `inflight` (whether <state-dir>/inflight/ exists as a directory), after
# the four it has; two keys join the twin on every path — `inflight_sids`
# (the sids whose <state-dir>/inflight/<sid>.json reads as an in-flight
# record, sorted; [] when the directory is absent) and `inflight_faults`
# (one string per file there that does not read as one, naming the file;
# [] when none) — both null when no state directory resolves; `status`
# stays exit 0 and ok through all of it and still creates nothing; human
# mode names each in-flight sid; the contract's §4 table names the keys.
#
# Writes only under ./.checkpoint-status-inflight.<pid>/ in the tree it
# grades (removed at exit); it reads nothing of its own: no sid, no
# manifest, no own path. Exit 0: every probe passed. Exit 1: a probe
# failed (named). Exit 2: the oracle itself is broken (a control did not
# fire, or an unplanned exception).
set -u
WORK="$(pwd)/.checkpoint-status-inflight.$$"
mkdir -p "$WORK" || exit 2
trap 'rm -rf "$WORK"' EXIT
echo "[checkpoint] writes only under $WORK (removed at exit)"
export TMPDIR="$WORK"
PYTHONDONTWRITEBYTECODE=1 python3 -I -B - "$WORK" <<'PY'
import json, os, re, subprocess, sys
from pathlib import Path

def broken(msg):
    print(f"[checkpoint] ORACLE BROKEN: {msg}")
    sys.exit(2)
sys.excepthook = lambda t, v, tb: broken(f"unplanned {t.__name__}: {v}")

WORK = Path(sys.argv[1]); TREE = Path.cwd()
TWINE = TREE / "bin" / "twine"
SID = "2026-10-08-inflight-oracle-001"
PRESENT_KEYS = ["spend_jsonl", "prices_toml", "abort", "running", "inflight"]

# The in-flight record, exactly as cli-contract.md §15.4 pins it (four keys,
# one open entry of five keys) — written by hand here, byte-pinned in the brief.
RECORD = {"sid": SID, "cwd": str(WORK),
          "tarball": None,
          "opens": [{"outcome": "opened", "desk": None,
                     "bundle_sha256": "0" * 64,
                     "opener_sha256": "1" * 64,
                     "recorded_at": "2026-10-08T00:00:00Z"}]}

def state_dir(name, *, inflight=True, record=True, junk=False):
    d = WORK / name; d.mkdir()
    if inflight:
        (d / "inflight").mkdir()
        if record:
            (d / "inflight" / f"{SID}.json").write_text(json.dumps(RECORD) + "\n", encoding="utf-8")
        if junk:
            (d / "inflight" / "not-a-record.json").write_text("{}\n", encoding="utf-8")
            (d / "inflight" / "junk.txt").write_text("not even json\n", encoding="utf-8")
    return d

def run(*argv, env=None):
    base = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8",
            "TWINE_BALE_ROOT": str(WORK / "no-bale-here")}
    if env: base.update(env)
    proc = subprocess.run([sys.executable, "-I", "-S", "-B", str(TWINE), "status", *argv],
                          capture_output=True, env=base, cwd=str(TREE), timeout=120)
    return proc

def twin(*argv, env=None):
    proc = run("--json", *argv, env=env)
    if proc.returncode != 0 or not proc.stdout.strip():
        return proc.returncode, None
    return proc.returncode, json.loads(proc.stdout)

failures = []
def probe(label, ok):
    print(f"{'[PASS]' if ok else '[FAIL]'} {label}")
    if not ok: failures.append(label)

# --- detectors (named; the controls call these, never copies) ---
def present_has_five_in_order(obj):
    sp = obj.get("state_present")
    return isinstance(sp, dict) and list(sp) == PRESENT_KEYS and all(isinstance(v, bool) for v in sp.values())
def inflight_reads(obj, flag, sids, faults_named):
    sp = obj.get("state_present")
    if not isinstance(sp, dict) or sp.get("inflight") is not flag: return False
    if obj.get("inflight_sids") != sids: return False
    faults = obj.get("inflight_faults")
    if not isinstance(faults, list) or len(faults) != len(faults_named): return False
    return all(isinstance(f, str) and name in f for f, name in zip(sorted(faults), sorted(faults_named)))
def inflight_nulls(obj):
    return (obj.get("state_present") is None and "inflight_sids" in obj and obj["inflight_sids"] is None
            and "inflight_faults" in obj and obj["inflight_faults"] is None)
def ok_exit0(code, obj):
    return code == 0 and isinstance(obj, dict) and obj.get("ok") is True

# --- probes ---
with_record = state_dir("with-record")
code, obj = twin("--state-dir", str(with_record))
probe("a record in inflight/: status ok, exit 0", ok_exit0(code, obj))
probe("state_present has exactly five booleans, inflight fifth", bool(obj) and present_has_five_in_order(obj))
probe("inflight true, inflight_sids is [the sid], inflight_faults []",
      bool(obj) and inflight_reads(obj, True, [SID], []))
human = run("--state-dir", str(with_record))
probe("human mode names the in-flight sid", human.returncode == 0 and SID.encode() in human.stdout)

no_dir = state_dir("no-inflight", inflight=False)
code, obj = twin("--state-dir", str(no_dir))
probe("no inflight/: inflight false, inflight_sids [], inflight_faults []",
      ok_exit0(code, obj) and inflight_reads(obj, False, [], []))

code, obj = twin()
probe("no state directory resolves: state_present null and both inflight keys present and null",
      ok_exit0(code, obj) and inflight_nulls(obj))

mixed = state_dir("mixed", junk=True)
code, obj = twin("--state-dir", str(mixed))
probe("a record beside two files that are not records: the sid listed, each bad file named in inflight_faults, still ok",
      ok_exit0(code, obj) and inflight_reads(obj, True, [SID], ["not-a-record.json", "junk.txt"]))

missing = WORK / "not-yet"
code, obj = twin("--state-dir", str(missing))
probe("a state directory that does not exist: inflight false, [] and [], and the directory is still not created",
      ok_exit0(code, obj) and inflight_reads(obj, False, [], []) and not missing.exists())

# the shipped surfaces that must not move
code, obj = twin("--state-dir", str(with_record))
probe("the pre-existing state keys still ride (state_dir, source, exists)",
      bool(obj) and obj.get("state_dir") == str(with_record) and obj.get("state_dir_source") == "--state-dir"
      and obj.get("state_dir_exists") is True and obj.get("state_dir_reason") is None)

contract = (TREE / "claude" / "context" / "cli-contract.md").read_text(encoding="utf-8")
sec4 = contract.split("\n## 4. ", 1)[1].split("\n## 5. ", 1)[0] if "\n## 4. " in contract else ""
probe("cli-contract.md §4's key table has rows for inflight_sids and inflight_faults, and names inflight under state_present",
      bool(re.search(r"^\| `inflight_sids` \|", sec4, re.M)) and bool(re.search(r"^\| `inflight_faults` \|", sec4, re.M))
      and "`inflight`" in sec4)

# --- controls: every detector fires on the input it must refuse ---
good = {"ok": True, "state_present": dict.fromkeys(PRESENT_KEYS, False) | {"inflight": True},
        "inflight_sids": [SID], "inflight_faults": []}
if not present_has_five_in_order(good): broken("present_has_five_in_order refuses the pinned shape")
if present_has_five_in_order(good | {"state_present": dict.fromkeys(PRESENT_KEYS[:4], False)}): broken("present_has_five_in_order accepts four members")
if present_has_five_in_order(good | {"state_present": dict(reversed(list(good["state_present"].items())))}): broken("present_has_five_in_order accepts another order")
if not inflight_reads(good, True, [SID], []): broken("inflight_reads refuses the good twin")
if inflight_reads(good | {"inflight_sids": []}, True, [SID], []): broken("inflight_reads accepts a missing sid")
if inflight_reads(good | {"inflight_faults": ["x"]}, True, [SID], []): broken("inflight_reads accepts an unexpected fault")
if inflight_reads(good | {"inflight_faults": ["some other file"]}, True, [SID], ["junk.txt"]): broken("inflight_reads accepts a fault that does not name the file")
if inflight_reads(good, False, [SID], []): broken("inflight_reads accepts the wrong flag")
if inflight_reads({"state_present": None, "inflight_sids": None, "inflight_faults": None}, False, [], []): broken("inflight_reads accepts nulls for a resolved directory")
if not inflight_nulls({"state_present": None, "inflight_sids": None, "inflight_faults": None}): broken("inflight_nulls refuses the null triple")
if inflight_nulls({"state_present": None}): broken("inflight_nulls accepts absent keys")
if inflight_nulls({"state_present": None, "inflight_sids": [], "inflight_faults": None}): broken("inflight_nulls accepts [] for null sids")
if inflight_nulls({"state_present": None, "inflight_sids": None, "inflight_faults": []}): broken("inflight_nulls accepts [] for null faults")
if inflight_nulls({"state_present": None, "inflight_sids": None}): broken("inflight_nulls accepts an absent faults key")
if ok_exit0(1, {"ok": True}) or ok_exit0(0, {"ok": False}) or ok_exit0(0, None): broken("ok_exit0 accepts a failure")
if not re.search(r"^\| `inflight_sids` \|", "| `inflight_sids` | the sids |\n", re.M): broken("the contract row pattern does not match its own example")

print(f"[checkpoint] {len(failures)} failing probe(s)")
sys.exit(1 if failures else 0)
PY

#!/usr/bin/env bash
# Blind checkpoint — session twine-bundle-051 (v1), authored at the desk of
# sitting 2026-10-08-open-arc2-003 from the request alone.
#
# What it grades (outcomes only): `twine carry bundle` reads bale 0.4.50+'s
# open line. An `open-refused` line is NOT OK (exit 1), its reason naming
# bale's `reason` code and quoting its `cause` whole, nothing recorded; a
# `second-desk` line that names a tarball lands that tarball in a fresh
# record (no prior record) and in a record whose own tarball was null,
# while a record whose own tarball is set keeps it; the manifest's open
# surface lists `reason` and `cause` among the keys twine reads; the
# in-flight module no longer describes bale 0.4.49's second-desk line as
# current.
#
# Writes only under ./.checkpoint-bundle-051.<pid>/ (removed at exit);
# reads nothing of its own. Exit 0 all probes passed; 1 a probe failed; 2
# the oracle is broken.
set -u
WORK="$(pwd)/.checkpoint-bundle-051.$$"
mkdir -p "$WORK" || exit 2
trap 'rm -rf "$WORK"' EXIT
echo "[checkpoint] writes only under $WORK (removed at exit)"
export TMPDIR="$WORK"
PYTHONDONTWRITEBYTECODE=1 python3 -I -B - "$WORK" <<'PY'
import hashlib, json, os, re, shutil, stat, subprocess, sys, tomllib
from pathlib import Path

def broken(msg):
    print(f"[checkpoint] ORACLE BROKEN: {msg}")
    sys.exit(2)
sys.excepthook = lambda t, v, tb: broken(f"unplanned {t.__name__}: {v}")

WORK = Path(sys.argv[1]); TREE = Path.cwd()
TWINE = TREE / "bin" / "twine"
SID = "2026-10-12-bundle-oracle-001"
CAUSE = "bundle not found: /nowhere/oracle.bale-bundle"
OPEN_KEYS = ["outcome", "sid", "tarball", "log", "session_dir", "context_files", "readme_path", "readme_heading",
             "readme_sha256", "checkpoint_file_path", "checkpoint_file_sha256", "branch", "applied_latest", "sweep",
             "include_group", "opener", "bundle", "members", "rehearsal", "checkpoint_dry_run", "desk", "reason", "cause"]
STALE = "bale 0.4.49's `second-desk` line carries `tarball` null"

failures = []
def probe(label, ok):
    print(f"{'[PASS]' if ok else '[FAIL]'} {label}")
    if not ok: failures.append(label)

manifest = tomllib.load(open(TREE / "share/bale-consumption.toml", "rb"))
floor = manifest["bale"].get("floor") or manifest["bale"].get("pin")
schema_dir = TREE / f"fixtures/bale-{floor}/schemas"

def line(outcome, **over):
    d = {k: None for k in OPEN_KEYS}
    d.update({"outcome": outcome, "bundle": {"path": "/x/b.bale-bundle", "sha256": "a" * 64, "stem": "b"},
              "members": {"brief": None, "checkpoint": None}})
    d.update(over)
    return json.dumps(d) + "\n"

def root(name, text):
    r = WORK / f"root-{name}"; (r / "bin").mkdir(parents=True)
    (r / "bin" / "VERSION").write_text(floor + "\n")
    if schema_dir.is_dir():
        shutil.copytree(schema_dir, r / "schemas")
    (r / "line.json").write_text(text, encoding="utf-8")
    s = r / "bin" / "bale"
    s.write_text(f"#!/usr/bin/env bash\n# oracle stub, not bale\ncat >/dev/null\ncat {json.dumps(str(r / 'line.json'))}\nexit 0\n")
    s.chmod(s.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return r

bundle = WORK / "oracle.bale-bundle"; bundle.write_bytes(b"stub\n")
def run(root_, state, *extra):
    env = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8", "TMPDIR": str(WORK)}
    return subprocess.run([sys.executable, "-I", "-S", "-B", str(TWINE), "carry", "bundle", str(bundle),
                           "--cwd", str(WORK), "--bale-root", str(root_), "--state-dir", str(state), "--json", *extra],
                          capture_output=True, env=env, cwd=str(TREE), timeout=300)
def twin(p): return json.loads(p.stdout) if p.stdout.strip() else None
def record_of(state):
    p = state / "inflight" / f"{SID}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

# --- detectors ---
def refused_named(p):
    o = twin(p)
    return (o is not None and p.returncode == 1 and o.get("ok") is False and o.get("ran") is True
            and isinstance(o.get("reason"), str) and "not-found" in o["reason"] and CAUSE in o["reason"]
            and b"Traceback" not in p.stderr)
def nothing_recorded(state): return not (state / "inflight").exists() or not any((state / "inflight").iterdir())
def record_tarball_is(rec, want): return isinstance(rec, dict) and rec.get("tarball") == want and rec.get("sid") == SID
def keys_listed(m):
    s = [x for x in m["surface"] if x.get("kind") == "verb" and x.get("verb") == "open"]
    return len(s) == 1 and {"outcome", "sid", "tarball", "opener", "desk", "bundle", "reason", "cause"} <= set(s[0]["keys"])

# --- probes ---
st1 = WORK / "state-refused"; st1.mkdir()
p = run(root("refused", line("open-refused", reason="not-found", cause=CAUSE)), st1)
probe("an open-refused line: NOT OK, exit 1, the reason names bale's reason code and quotes its cause whole", refused_named(p))
probe("an open-refused line records nothing", nothing_recorded(st1))

TB = "/nowhere/.bale/outbox/request-" + SID + ".tar.gz"
st2 = WORK / "state-fresh"; st2.mkdir()
p = run(root("second-fresh", line("second-desk", sid=SID, opener="opener text\n", desk="desk-2", tarball=TB)), st2)
o = twin(p)
probe("second-desk with a tarball and no prior record: ok, the fresh record keeps bale's tarball",
      o is not None and o.get("ok") is True and record_tarball_is(record_of(st2), TB))
probe("…and the twin says tarball_source bale", o is not None and o.get("tarball") == TB and o.get("tarball_source") == "bale")

st3 = WORK / "state-null-own"; (st3 / "inflight").mkdir(parents=True)
(st3 / "inflight" / f"{SID}.json").write_text(json.dumps({"sid": SID, "cwd": str(WORK), "tarball": None,
    "opens": [{"outcome": "opened", "desk": None, "bundle_sha256": "a" * 64, "opener_sha256": "b" * 64, "recorded_at": "2026-10-12T00:00:00Z"}]}) + "\n")
p = run(root("second-adopt", line("second-desk", sid=SID, opener="opener text\n", desk="desk-2", tarball=TB)), st3)
rec = record_of(st3)
probe("second-desk appended to a record whose tarball was null: the record adopts bale's tarball, both opens kept",
      twin(p) is not None and twin(p).get("ok") is True and record_tarball_is(rec, TB) and len(rec.get("opens", [])) == 2)

st4 = WORK / "state-own-kept"; (st4 / "inflight").mkdir(parents=True)
OWN = "/elsewhere/request-" + SID + ".tar.gz"
(st4 / "inflight" / f"{SID}.json").write_text(json.dumps({"sid": SID, "cwd": str(WORK), "tarball": OWN,
    "opens": [{"outcome": "opened", "desk": None, "bundle_sha256": "a" * 64, "opener_sha256": "b" * 64, "recorded_at": "2026-10-12T00:00:00Z"}]}) + "\n")
p = run(root("second-keep", line("second-desk", sid=SID, opener="opener text\n", desk="desk-2", tarball=TB)), st4)
probe("second-desk appended to a record whose tarball is set: the record keeps its own", twin(p) is not None and twin(p).get("ok") is True and record_tarball_is(record_of(st4), OWN))

probe("the consumption manifest's open surface lists reason and cause among the keys twine reads", keys_listed(manifest))
inflight_text = re.sub(r"\s+", " ", (TREE / "twine/inflight.py").read_text(encoding="utf-8"))
probe("twine/inflight.py no longer describes bale 0.4.49's second-desk line as carrying tarball null", STALE not in inflight_text)

# --- controls ---
class Fake:
    def __init__(self, rc, out, err=b""): self.returncode, self.stdout, self.stderr = rc, out, err
good = json.dumps({"ok": False, "ran": True, "reason": f"bale refused the open (reason 'not-found'): \"{CAUSE}\""}).encode()
if not refused_named(Fake(1, good)): broken("refused_named refuses a good refusal")
if refused_named(Fake(1, good.replace(b"not-found", b"not-fund"))): broken("refused_named accepts a reason without the code")
if refused_named(Fake(1, good.replace(CAUSE.encode(), b"other cause"))): broken("refused_named accepts a reason without the cause")
if refused_named(Fake(0, good)): broken("refused_named accepts exit 0")
if refused_named(Fake(1, good, b"Traceback (most recent call last)")): broken("refused_named accepts a traceback")
if not record_tarball_is({"sid": SID, "tarball": TB}, TB) or record_tarball_is({"sid": SID, "tarball": None}, TB) or record_tarball_is({"sid": "x", "tarball": TB}, TB): broken("record_tarball_is is wrong")
if not keys_listed({"surface": [{"kind": "verb", "verb": "open", "keys": ["outcome", "sid", "tarball", "opener", "desk", "bundle", "reason", "cause"]}]}): broken("keys_listed refuses the pinned set")
if keys_listed({"surface": [{"kind": "verb", "verb": "open", "keys": ["outcome", "sid", "tarball", "opener", "desk", "bundle"]}]}): broken("keys_listed accepts the six")
tmp = WORK / "ctl"; tmp.mkdir(); (tmp / "inflight").mkdir(); (tmp / "inflight" / "x.json").write_text("{}")
if nothing_recorded(tmp) or not nothing_recorded(WORK / "ctl-empty"): broken("nothing_recorded is wrong")
if STALE not in re.sub(r"\s+", " ", "bale 0.4.49's `second-desk` line carries\n`tarball` null, so"): broken("the stale clause cannot see its own text")

print(f"[checkpoint] {len(failures)} failing probe(s)")
sys.exit(1 if failures else 0)
PY

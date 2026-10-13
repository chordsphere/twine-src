#!/usr/bin/env bash
# Blind checkpoint — session twine-runtime-run (Arc 2 R4, v1), authored at the
# desk of sitting 2026-10-08-open-arc2-003 from the request alone.
#
# What it grades (outcomes only), all through `bin/twine run --adapter fake`
# against a stub bale root (recorded open and dry-run lines), a request
# tarball and scripts in the fake adapter's format, under a temp state dir:
# the delivered path end to end (file written in the cage, tarred, delivered,
# `bale apply --dry-run --json` asked of the stub, the apply line printed, the
# in-flight record removed, the running record cleared); `ended` on prose;
# `suspended` on escalate with the light block; `killed` from the abort file
# with no call made; `cap-reached` and `cap-unchecked` with no call made;
# `stopped` on a scripted request-refused with the table's move; one retry
# on a scripted overload; max-turns; a refused anthropic run without a key
# that never reaches bale; the transcript's first and last lines; one spend
# record per call; the key sentinel absent from every file under the state
# dir; `twine status` listing the new directories; VERSION moved.
#
# Writes only under ./.checkpoint-r4.<pid>/ (removed at exit); reads nothing
# of its own. Exit 0 all probes passed; 1 a probe failed; 2 the oracle is
# broken.
set -u
WORK="$(pwd)/.checkpoint-r4.$$"
mkdir -p "$WORK" || exit 2
trap 'rm -rf "$WORK"' EXIT
export TMPDIR="$WORK"
echo "[checkpoint] writes only under $WORK (removed at exit)"
PYTHONDONTWRITEBYTECODE=1 python3 -I -B - "$WORK" <<'PY'
import hashlib, io, json, os, re, shutil, stat, subprocess, sys, tarfile, time, tomllib
from pathlib import Path

def broken(msg):
    print(f"[checkpoint] ORACLE BROKEN: {msg}")
    sys.exit(2)
sys.excepthook = lambda t, v, tb: broken(f"unplanned {t.__name__}: {v}")

WORK = Path(sys.argv[1]); TREE = Path.cwd()
TWINE = TREE / "bin" / "twine"
SID = "2026-10-13-oracle-r4-001"
SECRET = "sk-ant-ORACLE-SENTINEL-9e2b"
OPEN_KEYS = ["outcome", "sid", "tarball", "log", "session_dir", "context_files", "readme_path", "readme_heading",
             "readme_sha256", "checkpoint_file_path", "checkpoint_file_sha256", "branch", "applied_latest", "sweep",
             "include_group", "opener", "bundle", "members", "rehearsal", "checkpoint_dry_run", "desk", "reason", "cause"]
OPENER = ("I'm using \"bale\", a CLI that packaged the attached request tarball.\nThis message opens bale session "
          + SID + ".\nGoal, verbatim from the request manifest: oracle-r4: the loop's rehearsal\nRead manifest.json first, then AGENT.md, then README.md.\n")

failures = []
def probe(label, ok):
    print(f"{'[PASS]' if ok else '[FAIL]'} {label}")
    if not ok: failures.append(label)

manifest = tomllib.load(open(TREE / "share/bale-consumption.toml", "rb"))
floor = manifest["bale"].get("floor") or manifest["bale"].get("pin")
schema_dir = TREE / f"fixtures/bale-{floor}/schemas"

# --- the fixtures the run needs ---
def make_request_tarball(path, escaping=False):
    with tarfile.open(path, "w:gz") as t:
        def add(name, data):
            ti = tarfile.TarInfo(name); ti.size = len(data); ti.mtime = 0; t.addfile(ti, io.BytesIO(data))
        add("manifest.json", (json.dumps({"sid": SID, "goal": "oracle-r4: the loop's rehearsal", "kind": "work"}) + "\n").encode())
        add("AGENT.md", b"# AGENT\n\nYou are a worker. Read README.md.\n")
        add("README.md", b"# Brief \xe2\x80\x94 oracle-r4\n\nWrite notes.md, tar it to out/response.tar.gz, deliver it.\n")
        add("context/seed.md", b"# seed (oracle)\n\nnothing here\n")
        if escaping: add("../escape.txt", b"no\n")
    return path

def open_line(tarball, outcome="opened"):
    d = {k: None for k in OPEN_KEYS}
    d.update({"outcome": outcome, "sid": SID, "tarball": str(tarball), "log": str(WORK / "bale.log"), "session_dir": str(WORK / "sessions" / SID),
              "context_files": 1, "readme_path": str(WORK / "brief.md"), "readme_heading": "# Brief — oracle-r4", "readme_sha256": "a" * 64,
              "branch": "main", "sweep": [], "opener": OPENER,
              "bundle": {"path": str(WORK / "oracle.bale-bundle"), "sha256": hashlib.sha256(b"stub\n").hexdigest(), "stem": "oracle"},
              "members": {"brief": "a" * 64, "checkpoint": None}})
    return json.dumps(d) + "\n"

def dry_run_line():
    return json.dumps({"outcome": "dry-run", "sid": SID, "log": str(WORK / "bale.log"), "verdict": None, "merge": None, "telemetry": None,
                       "drift": None, "checkpoint": None, "required_checks": None, "base_drift": None, "archive": None, "sweep": None}) + "\n"

def stub_root(name, tarball):
    r = WORK / f"root-{name}"; (r / "bin").mkdir(parents=True); rec = WORK / f"record-{name}"; rec.mkdir()
    (r / "bin" / "VERSION").write_text(floor + "\n")
    if schema_dir.is_dir(): shutil.copytree(schema_dir, r / "schemas")
    (r / "open.json").write_text(open_line(tarball)); (r / "apply.json").write_text(dry_run_line())
    s = r / "bin" / "bale"
    s.write_text("#!/usr/bin/env bash\n# oracle stub, not bale: records argv, replays a recorded line by verb\n"
                 f"printf '%s\\n' \"$*\" >> {json.dumps(str(rec / 'argv.txt'))}\ncat >/dev/null\n"
                 f"case \"$1\" in open) cat {json.dumps(str(r / 'open.json'))};; apply) cat {json.dumps(str(r / 'apply.json'))};; *) echo 'stub: unknown verb' >&2; exit 2;; esac\nexit 0\n")
    s.chmod(s.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return r, rec

PRICES = '[model."fake"]\ninput = 1.0\noutput = 2.0\ncache_read = 0.5\ncache_write = 1.5\n'
def usage(i=10, o=5): return {"input": i, "output": o, "thinking": None, "cache_read": 0, "cache_write": 0}
def tc(id_, name, args): return {"id": id_, "name": name, "arguments": args}
SCRIPTS = {
 "deliver": [{"tool_calls": [tc("t1", "write_file", {"path": "notes.md", "content": "hello from the oracle\n"}),
                             tc("t2", "shell", {"command": "mkdir -p out && tar czf out/response.tar.gz notes.md && ls -la out"})], "stop": None, "usage": usage()},
             {"tool_calls": [tc("t3", "deliver", {"tarball": "out/response.tar.gz"})], "stop": None, "usage": usage(20, 7)}],
 "prose": [{"text": "All done; nothing to deliver.", "stop": "end-turn", "usage": usage()}],
 "escalate": [{"tool_calls": [tc("t1", "escalate", {"questions": [{"question": "Which base?", "while_doing": "starting", "would_assume": "HEAD", "why_blocked": "the brief does not say"}]})], "stop": None, "usage": usage()}],
 "refused": [{"text": "", "stop": "request-refused", "usage": usage()}],
 "overload": [{"text": "", "stop": "overloaded", "usage": usage()}, {"text": "ok after the retry", "stop": "end-turn", "usage": usage()}],
 "two": [{"tool_calls": [tc("t1", "write_file", {"path": "a.txt", "content": "a\n"})], "stop": None, "usage": usage()}, {"text": "done", "stop": "end-turn", "usage": usage()}],
}

def run(name, script, *extra, env_extra=None, prices=True, cap="5.00", adapter="fake", abort=False, tar_escaping=False):
    base = WORK / name; base.mkdir(); state = base / "state"; state.mkdir(); cwd = base / "cwd"; cwd.mkdir()
    tarball = make_request_tarball(base / f"request-{SID}.tar.gz", escaping=tar_escaping)
    root, rec = stub_root(name, tarball)
    (WORK / "oracle.bale-bundle").write_bytes(b"stub\n")
    if prices: (state / "prices.toml").write_text(PRICES)
    if abort:
        (state / "abort").mkdir(); (state / "abort" / f"{SID}.json").write_text(json.dumps({"sid": SID, "requested_at": "2026-10-13T00:00:00Z", "by": "oracle"}) + "\n")
    if script is not None: (base / "script.json").write_text(json.dumps(script))
    env = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8", "TMPDIR": str(WORK), "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(base)}
    env.update(env_extra or {})
    argv = [sys.executable, "-I", "-B", str(TWINE), "run", str(WORK / "oracle.bale-bundle"), "--adapter", adapter, "--cap", cap,
            "--state-dir", str(state), "--bale-root", str(root), "--cwd", str(cwd), "--json", *extra]
    if script is not None: argv += ["--script", str(base / "script.json")]
    t0 = time.monotonic()
    p = subprocess.run(argv, capture_output=True, env=env, cwd=str(base), timeout=600)
    try: o = json.loads(p.stdout) if p.stdout.strip() else None
    except ValueError: o = None
    return {"twin": o, "rc": p.returncode, "stderr": p.stderr.decode(errors="replace"), "stdout": p.stdout.decode(errors="replace"),
            "state": state, "record": rec, "tarball": tarball, "seconds": time.monotonic() - t0, "lines": p.stdout.count(b"\n")}

def bale_argv(r):
    f = r["record"] / "argv.txt"
    return f.read_text().splitlines() if f.is_file() else []
def jsonl(path):
    try: return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError): return None
def files_under(root): return [p for p in root.rglob("*") if p.is_file()]

# --- detectors ---
def outcome_is(r, outcome, ok):
    o = r["twin"]
    return (isinstance(o, dict) and o.get("command") == "run" and o.get("outcome") == outcome and o.get("ok") is ok
            and r["rc"] == (0 if ok else 1) and r["lines"] == 1 and "Traceback" not in r["stderr"])

# ===== the delivered path =====
d = run("deliver", SCRIPTS["deliver"], env_extra={"ANTHROPIC_API_KEY": SECRET})
if d["twin"] is None: print("  [detail] deliver run printed no JSON; stderr tail: " + d["stderr"][-600:].replace("\n", " | "))
o = d["twin"] or {}
probe("delivered: the fake script writes, tars and delivers; outcome delivered, ok, exit 0", outcome_is(d, "delivered", True) and o.get("sid") == SID)
home = Path(o.get("sandbox") or (d["state"] / "nowhere"))
probe("the request was unpacked at <home>/request/ and the file the model wrote is in the cage",
      (home / "request" / "README.md").is_file() and (home / "request" / "context" / "seed.md").is_file() and (home / "notes.md").is_file())
tb = o.get("tarball") or ""
probe("the response tarball is inside the cage and the apply line names it",
      tb.startswith(str(home)) and Path(tb).is_file() and isinstance(o.get("apply_line"), str) and o["apply_line"].startswith("bale apply ") and tb.split("/")[-1] in o["apply_line"])
av = bale_argv(d)
probe("bale was asked exactly: open <bundle> --json, then apply --dry-run --json <absolute tarball>",
      len(av) == 2 and av[0].startswith("open ") and "--json" in av[0] and av[1].startswith("apply ") and "--dry-run" in av[1] and "--json" in av[1] and tb in av[1])
probe("delivered: turns 2, tool_calls 3, usage summed (input 30, output 12), cost priced, dry_run outcome dry-run",
      o.get("turns") == 2 and o.get("tool_calls") == 3 and (o.get("usage") or {}).get("input") == 30 and (o.get("usage") or {}).get("output") == 12
      and isinstance(o.get("cost_usd"), (int, float)) and (o.get("dry_run") or {}).get("outcome") == "dry-run" and o.get("stop") is None)
probe("delivered: the in-flight record is removed and the running record is cleared",
      o.get("inflight") == "removed" and not (d["state"] / "inflight" / f"{SID}.json").exists() and not (d["state"] / "running" / f"{SID}.json").exists())
tr = jsonl(d["state"] / "transcripts" / f"{SID}.jsonl")
probe("the transcript exists at <state-dir>/transcripts/<sid>.jsonl: JSON lines, seq 1.., run-start first, run-end last, a turn and a tool-result inside",
      isinstance(tr, list) and len(tr) >= 6 and tr[0].get("kind") == "run-start" and tr[-1].get("kind") == "run-end" and [l.get("seq") for l in tr] == list(range(1, len(tr) + 1))
      and any(l.get("kind") == "turn" for l in tr) and any(l.get("kind") == "tool-result" for l in tr) and o.get("transcript") == str(d["state"] / "transcripts" / f"{SID}.jsonl"))
sp = jsonl(d["state"] / "spend.jsonl")
probe("spend.jsonl gained one record per call for the sid, model fake, served_sid null",
      isinstance(sp, list) and len(sp) == 2 and all(l.get("sid") == SID and l.get("model") == "fake" and l.get("served_sid") is None for l in sp))
leak = [str(p.relative_to(d["state"])) for p in files_under(d["state"]) if SECRET.encode() in p.read_bytes()]
probe("the key sentinel appears in no file under the state directory and not in the twin" + (f" (found in {leak})" if leak else ""), not leak and SECRET not in d["stdout"] and SECRET not in d["stderr"])
st = subprocess.run([sys.executable, "-I", "-B", str(TWINE), "status", "--state-dir", str(d["state"]), "--bale-root", str(WORK / "root-deliver"), "--json"],
                    capture_output=True, env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8", "HOME": str(WORK)}, cwd=str(WORK), timeout=120)
try: so = json.loads(st.stdout)
except ValueError: so = {}
def present(name):
    sp_ = so.get("state_present")
    return (sp_.get(name) is True) if isinstance(sp_, dict) else (name in (sp_ or []))
probe("twine status lists transcripts/ and sandbox/ beside running/ and inflight/, naming the sid",
      present("transcripts") and present("sandbox") and SID in (so.get("transcript_sids") or []) and SID in (so.get("sandbox_sids") or []))

# ===== ended on prose =====
e = run("prose", SCRIPTS["prose"]); o = e["twin"] or {}
probe("ended: a final text with no block is outcome ended, shape prose, stop end-turn, move classify-final-text, record kept",
      outcome_is(e, "ended", False) and o.get("shape") == "prose" and o.get("stop") == "end-turn" and o.get("move") == "classify-final-text"
      and o.get("inflight") == "kept" and (e["state"] / "inflight" / f"{SID}.json").is_file())

# ===== suspended on escalate =====
s = run("escalate", SCRIPTS["escalate"]); o = s["twin"] or {}
probe("suspended: escalate stops the run with the light block in the twin, record and transcript kept",
      outcome_is(s, "suspended", False) and isinstance(o.get("block"), str) and f"=== LIGHT BEGIN {SID} ===" in o["block"] and o.get("inflight") == "kept"
      and (s["state"] / "transcripts" / f"{SID}.jsonl").is_file())

# ===== killed before the first call =====
k = run("killed", SCRIPTS["prose"], abort=True); o = k["twin"] or {}
probe("killed: an abort file set before the run stops it with no call made", outcome_is(k, "killed", False) and o.get("stop") == "killed" and o.get("turns") == 0 and not (k["state"] / "spend.jsonl").exists())

# ===== the cap =====
c = run("cap", SCRIPTS["prose"], cap="0.000001"); o = c["twin"] or {}
probe("cap-reached: a tiny cap refuses before the first call; turns 0; stop cap-reached, move stop-at-cap",
      outcome_is(c, "cap-reached", False) and o.get("turns") == 0 and o.get("stop") == "cap-reached" and o.get("move") == "stop-at-cap")
u = run("unchecked", SCRIPTS["prose"], prices=False); o = u["twin"] or {}
probe("cap-unchecked: no prices file refuses before the first call; stop cap-unchecked, move fix-and-resume", outcome_is(u, "cap-unchecked", False) and o.get("turns") == 0 and o.get("stop") == "cap-unchecked" and o.get("move") == "fix-and-resume")

# ===== stopped on a provider refusal, retried on overload =====
f = run("refused", SCRIPTS["refused"]); o = f["twin"] or {}
probe("stopped: a scripted request-refused stops with the table's move fix-request and a reason", outcome_is(f, "stopped", False) and o.get("stop") == "request-refused" and o.get("move") == "fix-request" and isinstance(o.get("reason"), str))
v = run("overload", SCRIPTS["overload"]); o = v["twin"] or {}
probe("retry: a scripted overload is retried once with backoff (≥ 2 s) and the run then ends on the next turn's prose",
      outcome_is(v, "ended", False) and o.get("retries") == 1 and o.get("turns") == 2 and v["seconds"] >= 2.0)

# ===== max-turns =====
m = run("maxturns", SCRIPTS["two"], "--max-turns", "1"); o = m["twin"] or {}
probe("max-turns 1: ended with shape max-turns after exactly one call", outcome_is(m, "ended", False) and o.get("shape") == "max-turns" and o.get("turns") == 1)

# ===== refused before bale =====
a = run("nokey", None, adapter="anthropic", env_extra={}, cap="1.00"); o = a["twin"] or {}
argv_a = [x for x in bale_argv(a)]
probe("refused: --adapter anthropic without ANTHROPIC_API_KEY (and without --model) is refused before bale open is called",
      outcome_is(a, "refused", False) and not argv_a and isinstance(o.get("reason"), str) and o.get("turns") == 0)
x = run("escape", SCRIPTS["prose"], tar_escaping=True); o = x["twin"] or {}
probe("refused: a request tarball with an escaping member is refused", outcome_is(x, "refused", False) and o.get("turns") == 0)

# ===== hygiene =====
hits = []
for pth in list((TREE / "twine" / "runtime").rglob("*.py")) + [TREE / "twine" / "commands" / "run.py"]:
    if pth.is_file() and re.search(r"^\s*(import|from)\s+subprocess(\s|$|\.)", pth.read_text(encoding="utf-8"), re.M): hits.append(str(pth.relative_to(TREE)))
probe("no subprocess import under twine/runtime/ or in twine/commands/run.py" + (f" ({', '.join(hits)})" if hits else ""), not hits and (TREE / "twine" / "commands" / "run.py").is_file())
cmds = subprocess.run([sys.executable, "-I", "-B", str(TWINE), "commands", "--json"], capture_output=True, env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8"}, cwd=str(WORK), timeout=120)
try: names = {c.get("name") for c in json.loads(cmds.stdout).get("commands", [])}
except ValueError: names = set()
probe("twine commands lists run", "run" in names)
ver = (TREE / "VERSION").read_text(encoding="utf-8").strip()
try: tup = tuple(int(x) for x in ver.split("."))
except ValueError: tup = ()
probe(f"VERSION ({ver}) is at least 0.19.0", len(tup) == 3 and tup >= (0, 19, 0))
probe("no __pycache__ in the tree", not any(".checkpoint-r4" not in str(q) for q in TREE.rglob("__pycache__")))

# --- controls ---
good = {"twin": {"command": "run", "outcome": "delivered", "ok": True}, "rc": 0, "lines": 1, "stderr": ""}
if not outcome_is(good, "delivered", True): broken("outcome_is refuses a good twin")
if outcome_is(dict(good, rc=1), "delivered", True) or outcome_is(dict(good, lines=2), "delivered", True) or outcome_is(dict(good, stderr="Traceback (most recent"), "delivered", True): broken("outcome_is accepts a bad run")
if outcome_is(good, "ended", False): broken("outcome_is accepts the wrong outcome")
tb_ctl = make_request_tarball(WORK / "ctl.tar.gz", escaping=True)
with tarfile.open(tb_ctl) as t:
    if "../escape.txt" not in t.getnames() or "README.md" not in t.getnames(): broken("the request tarball fixture is wrong")
ol = json.loads(open_line("/x"))
if set(ol) != set(OPEN_KEYS) or ol["outcome"] != "opened": broken("the open line fixture is wrong")
if json.loads(dry_run_line())["outcome"] != "dry-run": broken("the dry-run line fixture is wrong")
if jsonl(WORK / "no-such-file") is not None: broken("jsonl is wrong")
(WORK / "ctl.jsonl").write_text('{"a": 1}\n{"a": 2}\n')
if jsonl(WORK / "ctl.jsonl") != [{"a": 1}, {"a": 2}]: broken("jsonl is wrong")
for name, sc in SCRIPTS.items():
    for turn in sc:
        if "stop" not in turn or "usage" not in turn or set(turn["usage"]) != {"input", "output", "thinking", "cache_read", "cache_write"}: broken(f"script {name} is malformed")

print(f"[checkpoint] {len(failures)} failing probe(s)")
sys.exit(1 if failures else 0)
PY

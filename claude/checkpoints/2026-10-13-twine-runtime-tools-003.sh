#!/usr/bin/env bash
# Blind checkpoint — session twine-runtime-tools (Arc 2 R3, v2), authored at
# the desk of sitting 2026-10-08-open-arc2-003 from the request alone.
# v2 (2026-10-13, after the HOLD of -003): inside bale's apply sandbox the
# grading interpreter's process group reads as 0 (a PID namespace whose group
# leader is outside it), so registering the runtime with its own pgid crashed
# the interpreter and every probe after it. The interpreter now makes itself
# a session leader before registering, and the registration is a step of its
# own so a failure there names itself instead of taking the others down. No
# probe's expectation changed.
#
# What it grades (outcomes only): `twine runtime tools` lists the seven
# canonical tools with schemas and parity by name; a sandbox created under a
# temp state dir has its home where the brief says and reports its network
# honestly (checked against this machine's own `unshare -rn true`); the file
# tools work inside the cage and are refused outside it (.., absolute,
# symlink escape) as error results, never exceptions; `shell` runs real
# processes in the home with a minimal environment (a sentinel key in the
# parent never reaches the cage), reports exit code/stdout/stderr, and a
# timeout kills the group; with a running record registered, a shell run
# registers its group through the seam's hook and clears it after; `probe`
# runs a read-only block against the repo and returns a verifiable
# probe-output block; `escalate` emits a light block shapes finds intact;
# `deliver` hashes a file in the cage; `sandboxing` is implemented; nothing
# under twine/runtime/ imports subprocess; VERSION moved.
#
# Writes only under ./.checkpoint-r3.<pid>/ (removed at exit); reads nothing
# of its own. Exit 0 all probes passed; 1 a probe failed; 2 the oracle is
# broken.
set -u
WORK="$(pwd)/.checkpoint-r3.$$"
mkdir -p "$WORK" || exit 2
trap 'rm -rf "$WORK"' EXIT
echo "[checkpoint] writes only under $WORK (removed at exit)"
export TMPDIR="$WORK"
PYTHONDONTWRITEBYTECODE=1 python3 -I -B - "$WORK" <<'PY'
import hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

def broken(msg):
    print(f"[checkpoint] ORACLE BROKEN: {msg}")
    sys.exit(2)
sys.excepthook = lambda t, v, tb: broken(f"unplanned {t.__name__}: {v}")

WORK = Path(sys.argv[1]); TREE = Path.cwd()
SEVEN = {"shell", "read_file", "write_file", "list_dir", "probe", "escalate", "deliver"}
SECRET = "sk-ant-ORACLE-SENTINEL-c41d"
SID = "2026-10-13-oracle-r3-001"

failures = []
def probe(label, ok):
    print(f"{'[PASS]' if ok else '[FAIL]'} {label}")
    if not ok: failures.append(label)

def env(extra=None):
    e = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8", "TMPDIR": str(WORK), "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(WORK)}
    e.update(extra or {}); return e
def twine(root, *argv):
    return subprocess.run([sys.executable, "-I", "-B", str(root / "bin" / "twine"), *argv, "--json"], capture_output=True, env=env(), cwd=str(WORK), timeout=120)
def twin(p):
    try: return json.loads(p.stdout) if p.stdout.strip() else None
    except ValueError: return None
def copy_tree(name):
    dst = WORK / name
    shutil.copytree(TREE, dst, symlinks=True, ignore=shutil.ignore_patterns(".git", ".checkpoint-*", ".validation-logs", "__pycache__", "fixtures"))
    return dst

PRE = ("import sys, json, os, hashlib\n" "sys.path.insert(0, " + json.dumps(str(TREE)) + ")\n"
       "def J(x):\n    return json.loads(json.dumps(x, default=str))\n" "out = {}\n"
       "def step(name, fn):\n    try:\n        out[name] = {'ok': True, 'value': J(fn())}\n"
       "    except BaseException as e:\n        out[name] = {'ok': False, 'error': type(e).__name__ + ': ' + str(e)}\n")
def run_py(code, extra_env=None):
    p = subprocess.run([sys.executable, "-I", "-B", "-c", PRE + code + "\nprint(json.dumps(out))\n"], capture_output=True, env=env(extra_env), cwd=str(WORK), timeout=600)
    err = p.stderr.decode(errors="replace")
    try: return json.loads(p.stdout.decode()), err
    except ValueError: return {"__crash__": err[-800:]}, err
def value(res, name): return res.get(name, {}).get("value")
def okv(res, name): return res.get(name, {}).get("ok") is True

# this machine's own answer to "can unprivileged user+net namespaces be made?"
def host_unshare_works():
    try:
        return subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False

# --- detectors ---
def is_error(v): return isinstance(v, dict) and v.get("is_error") is True and isinstance(v.get("content"), str) and bool(v["content"].strip())
def is_ok(v): return isinstance(v, dict) and v.get("is_error") is False
def names_cage(v): return is_error(v) and re.search(r"cage|sandbox|outside|home", v["content"], re.I) is not None

# --- the verb ---
p = twine(TREE, "runtime", "tools"); o = twin(p) or {}
tools = {t.get("name"): t for t in o.get("tools", []) if isinstance(t, dict)}
probe("runtime tools --json: ok, the seven, each with a description, an object input_schema and leaves_cage (probe alone true)",
      p.returncode == 0 and o.get("ok") is True and set(tools) >= SEVEN
      and all(isinstance(tools[n].get("description"), str) and tools[n]["description"].strip()
              and isinstance(tools[n].get("input_schema"), dict) and tools[n]["input_schema"].get("type") == "object"
              and tools[n].get("leaves_cage") is (n == "probe") for n in SEVEN))
lst = twin(twine(TREE, "runtime", "list")) or {}
caps = {c.get("name"): c for c in lst.get("capabilities", []) if isinstance(c, dict)}
probe("runtime list: sandboxing is implemented, tool-calling still implemented", caps.get("sandboxing", {}).get("status") == "implemented" and caps.get("tool-calling", {}).get("status") == "implemented")
planted = copy_tree("planted")
tdir = planted / "twine" / "runtime" / "tools"
if tdir.is_dir():
    (tdir / "zz_oracle_planted.py").write_text('"""planted by the checkpoint"""\n')
    pp = twine(planted, "runtime", "tools"); po = twin(pp) or {}
    probe("parity: a module under tools/ the declaration does not list makes `runtime tools` NOT OK naming it",
          pp.returncode == 1 and po.get("ok") is False and "zz_oracle_planted" in json.dumps(po))
else:
    probe("twine/runtime/tools/ is a directory", False)

# --- the sandbox and the tools, in one interpreter with the sentinel in its environment ---
STATE = WORK / "state"; REPO = WORK / "repo"; REPO.mkdir(); (REPO / "README.md").write_text("oracle repo\n")
OUTSIDE = WORK / "outside"; OUTSIDE.mkdir(); (OUTSIDE / "secret.txt").write_text("outside the cage\n")
PROBE_BLOCK = ("```bash\n#!/usr/bin/env bash\n# PROBE oracle-r3: list the repo's files and count them.\n"
               "# Why: the checkpoint checks the probe tool closes the paste-back hop.\n"
               "# Read-only: writes nothing anywhere; stdout is the only output.\n"
               "probe() { echo \"--- section: files ---\"; ls -1 | sort; echo \"count: $(ls -1 | wc -l | tr -d ' ')\"; }\n"
               "out=\"$(probe 2>&1 </dev/null)\"\n"
               "echo \"=== PROBE BEGIN oracle-r3 ===\"; printf '%s\\n' \"$out\"; printf -- '--- integrity: %s lines ---\\n' \"$(printf '%s\\n' \"$out\" | wc -l | tr -d ' ')\"; echo \"=== PROBE END oracle-r3 ===\"\n```\n")
code = ("from pathlib import Path\nimport twine.process as P\nfrom twine.runtime.sandbox import Sandbox\nfrom twine.runtime.tools import run_tool\nfrom twine import shapes, kill\n"
        + f"STATE = Path({json.dumps(str(STATE))}); REPO = Path({json.dumps(str(REPO))}); OUTSIDE = Path({json.dumps(str(OUTSIDE))}); SID = {json.dumps(SID)}\nPROBE_BLOCK = {json.dumps(PROBE_BLOCK)}\n" + r'''
seen = {"argv": [], "hooks": 0, "groups_during": None}
def recording_runner(argv, **kw):
    seen["argv"].append([str(a) for a in argv])
    hook = kw.get("on_spawn")
    if hook is not None:
        def wrapped(pid):
            seen["hooks"] += 1
            hook(pid)
            rec = kill.read_running(STATE, SID)
            seen["groups_during"] = len(rec.groups) if rec is not None else None
        kw["on_spawn"] = wrapped
    return P.run_process(argv, **kw)
sb = Sandbox.create(STATE, SID, repo=REPO, run=recording_runner, max_timeout=20)
def R(name, args): return run_tool(sb, name, args).as_json()
step("sandbox", lambda: sb.as_json())
step("home", lambda: {"home": str(sb.home), "under": str(sb.home).startswith(str(STATE / "sandbox" / SID)), "exists": sb.home.is_dir()})
step("write", lambda: R("write_file", {"path": "notes/a.txt", "content": "hello\n"}))
step("write_bytes", lambda: (sb.home / "notes" / "a.txt").read_bytes().decode())
step("read", lambda: R("read_file", {"path": "notes/a.txt"}))
step("list", lambda: R("list_dir", {"path": "notes"}))
step("read_dotdot", lambda: R("read_file", {"path": "../../../outside/secret.txt"}))
step("read_abs", lambda: R("read_file", {"path": str(OUTSIDE / "secret.txt")}))
os.symlink(OUTSIDE, sb.home / "escape")
step("write_symlink", lambda: R("write_file", {"path": "escape/x.txt", "content": "leak"}))
step("leak_check", lambda: (OUTSIDE / "x.txt").exists())
step("read_missing", lambda: R("read_file", {"path": "notes/none.txt"}))
step("shell", lambda: R("shell", {"command": "printf hi; printf err 1>&2; exit 3"}))
step("shell_env", lambda: R("shell", {"command": "echo KEY=${ANTHROPIC_API_KEY:-unset}; echo HOME=$HOME; pwd"}))
step("shell_timeout", lambda: R("shell", {"command": "sleep 30", "timeout": 1}))
step("unknown", lambda: R("no_such_tool", {}))
step("bad_args", lambda: R("read_file", {"nope": 1}))
step("probe", lambda: R("probe", {"block": PROBE_BLOCK}))
step("probe_no_ro", lambda: R("probe", {"block": PROBE_BLOCK.replace("# Read-only: writes nothing anywhere; stdout is the only output.\n", "")}))
qs = [{"question": "Which runner?", "while_doing": "grading R3", "would_assume": "the real one", "why_blocked": "only the desk knows"}]
step("escalate", lambda: R("escalate", {"questions": qs}))
step("escalate_parsed", lambda: [(b.kind, b.integrity.get("ok")) for b in shapes.find_blocks(R("escalate", {"questions": qs})["content"]).blocks])
step("escalate_four", lambda: R("escalate", {"questions": qs * 4}))
(sb.home / "out").mkdir(exist_ok=True); (sb.home / "out" / "r.tar.gz").write_bytes(b"not really a tarball\n")
step("deliver", lambda: R("deliver", {"tarball": "out/r.tar.gz"}))
step("deliver_missing", lambda: R("deliver", {"tarball": "out/none.tar.gz"}))
step("deliver_outside", lambda: R("deliver", {"tarball": str(OUTSIDE / "secret.txt")}))
# the kill-switch hook: a running record for the sid, then a shell run. This
# interpreter becomes its own session (and so its own group, pgid == pid > 1)
# first: under a PID namespace the inherited group's leader is invisible and
# the pgid reads as 0.
def register():
    try: os.setsid()
    except OSError: pass
    rec = kill.register_running(STATE, SID, os.getpgid(0), os.getpid())
    return {"pgid": rec.pgid, "pid": rec.pid}
step("register", register)
seen["hooks"] = 0; seen["groups_during"] = None
step("hooked", lambda: R("shell", {"command": "sleep 0.3; echo done"}))
step("hook_seen", lambda: dict(seen, argv=None))
step("groups_after", lambda: len(kill.read_running(STATE, SID).groups) if kill.read_running(STATE, SID) is not None else None)
step("argv_shell", lambda: [a for a in seen["argv"] if any("printf hi" in x for x in a)][:1])
''')
r, err = run_py(code, {"ANTHROPIC_API_KEY": SECRET, "ORACLE_PARENT_ONLY": "1"})
if "__crash__" in r: print("  [detail] the tools interpreter crashed: " + r["__crash__"].replace("\n", " | ")[-500:])
sbj = value(r, "sandbox") or {}
host_ns = host_unshare_works()
probe("Sandbox.create: home under <state-dir>/sandbox/<sid>/, created", (value(r, "home") or {}).get("under") is True and (value(r, "home") or {}).get("exists") is True)
probe(f"Sandbox.as_json: network/confines agree with this machine (unshare -rn works here: {host_ns})",
      sbj.get("network") in ("off", "unconfined") and sbj.get("confines") is (sbj.get("network") == "off") and (sbj.get("network") == "off") is host_ns and sbj.get("sid") == SID)
v = value(r, "write")
probe("write_file inside the cage: ok, parents created, bytes as given", is_ok(v) and value(r, "write_bytes") == "hello\n" and v.get("size") == 6)
v = value(r, "read")
probe("read_file inside the cage: content 'hello\\n'", is_ok(v) and v.get("content") == "hello\n")
v = value(r, "list")
probe("list_dir: entries sorted with name/kind/size, a.txt a file of 6 bytes",
      is_ok(v) and any(e.get("name") == "a.txt" and e.get("kind") == "file" and e.get("size") == 6 for e in (v.get("entries") or [])))
probe("read_file with .. and with an absolute path outside: error results naming the cage, no exception", names_cage(value(r, "read_dotdot")) and names_cage(value(r, "read_abs")))
probe("write_file through a symlink pointing out of the cage: error result and nothing written outside", names_cage(value(r, "write_symlink")) and value(r, "leak_check") is False)
probe("read_file of a missing file: an error result", is_error(value(r, "read_missing")))
v = value(r, "shell") or {}
probe("shell: exit 3 is not a tool error; exit_code 3, stdout 'hi', stderr 'err', content carries all three",
      is_ok(v) and v.get("exit_code") == 3 and v.get("stdout") == "hi" and v.get("stderr") == "err" and "hi" in v.get("content", "") and "err" in v.get("content", "") and "3" in v.get("content", ""))
v = value(r, "shell_env") or {}
home = str((value(r, "home") or {}).get("home"))
probe("shell: the cage's environment is minimal — the parent's ANTHROPIC_API_KEY is unset inside, HOME and cwd are the home",
      is_ok(v) and "KEY=unset" in v.get("stdout", "") and SECRET not in json.dumps(v) and f"HOME={home}" in v.get("stdout", "") and os.path.realpath(home) in [os.path.realpath(l) for l in v.get("stdout", "").splitlines() if l.startswith("/")])
v = value(r, "shell_timeout") or {}
probe("shell with timeout 1 on `sleep 30`: an error result, timed_out, exit_code null, back well before 30 s", is_error(v) and v.get("timed_out") is True and v.get("exit_code") is None and float(v.get("duration_seconds") or 99) < 15)
probe("run_tool with an unknown tool, and with arguments the schema refuses: error results, never exceptions", is_error(value(r, "unknown")) and is_error(value(r, "bad_args")) and okv(r, "unknown") and okv(r, "bad_args"))
v = value(r, "probe") or {}
probe("probe: runs the read-only block against the repo and returns a probe-output block (sentinels, integrity trailer, README.md listed), leaves_cage true",
      is_ok(v) and v.get("leaves_cage") is True and "=== PROBE BEGIN oracle-r3 ===" in v.get("content", "") and "=== PROBE END oracle-r3 ===" in v.get("content", "")
      and "README.md" in v.get("content", "") and re.search(r"--- integrity: \d+ lines ---", v.get("content", "")) is not None and v.get("slug") == "oracle-r3")
probe("probe: a block without the read-only declaration is an error result", is_error(value(r, "probe_no_ro")))
v = value(r, "escalate") or {}
probe("escalate: a light block for the sid, suspend true, kind light, shapes finds exactly one light block",
      is_ok(v) and v.get("suspend") is True and v.get("kind") == "light" and f"=== LIGHT BEGIN {SID} ===" in v.get("content", "") and f"=== LIGHT END {SID} ===" in v.get("content", "")
      and value(r, "escalate_parsed") == [["light", True]])
probe("escalate with four questions: an error result", is_error(value(r, "escalate_four")))
v = value(r, "deliver") or {}
probe("deliver: delivered true with the file's sha256 and size", is_ok(v) and v.get("delivered") is True and v.get("sha256") == hashlib.sha256(b"not really a tarball\n").hexdigest() and v.get("size") == 21)
probe("deliver of a missing file and of a path outside the cage: error results", is_error(value(r, "deliver_missing")) and is_error(value(r, "deliver_outside")))
hs = value(r, "hook_seen") or {}
probe("the kill-switch hook: with a running record (this interpreter registered as its own session), shell passes on_spawn, the group is in the record during the run and cleared after",
      okv(r, "register") and is_ok(value(r, "hooked")) and hs.get("hooks") == 1 and hs.get("groups_during") == 1 and value(r, "groups_after") == 0)
argv = (value(r, "argv_shell") or [[]])[0]
probe("shell runs through the seam as bash -c (wrapped in unshare -rn when the network is off)",
      isinstance(argv, list) and "bash" in argv and "-c" in argv and ((sbj.get("network") == "off") == (len(argv) > 0 and argv[0] == "unshare" and "-rn" in argv)))

# --- hygiene ---
hits = []
for pth in (TREE / "twine" / "runtime").rglob("*.py"):
    if re.search(r"^\s*(import|from)\s+subprocess(\s|$|\.)", pth.read_text(encoding="utf-8"), re.M): hits.append(str(pth.relative_to(TREE)))
probe("no module under twine/runtime/ imports subprocess (tools run through the seam)" + (f" ({', '.join(hits)})" if hits else ""), not hits)
def no_proposed(m):
    f = TREE / f"twine/runtime/{m}.py"
    return f.is_file() and "proposed" not in f.read_text(encoding="utf-8").lower()
probe("twine/runtime/contract.py and registry.py exist and no longer say 'proposed'", no_proposed("contract") and no_proposed("registry"))
ver = (TREE / "VERSION").read_text(encoding="utf-8").strip()
try: tup = tuple(int(x) for x in ver.split("."))
except ValueError: tup = ()
probe(f"VERSION ({ver}) is at least 0.18.0", len(tup) == 3 and tup >= (0, 18, 0))
probe("no __pycache__ in the tree", not any(".checkpoint-r3" not in str(q) for q in TREE.rglob("__pycache__")))

# --- controls ---
if not is_error({"is_error": True, "content": "x"}) or is_error({"is_error": False, "content": "x"}) or is_error({"is_error": True, "content": " "}): broken("is_error is wrong")
if not names_cage({"is_error": True, "content": "outside the cage"}) or names_cage({"is_error": True, "content": "nope"}) or names_cage({"is_error": False, "content": "cage"}): broken("names_cage is wrong")
if not is_ok({"is_error": False}) or is_ok({"is_error": True}) or is_ok(None): broken("is_ok is wrong")
ctl, _ = run_py("step('x', lambda: os.environ.get('ORACLE_PARENT_ONLY'))\nstep('y', lambda: 1/0)\n", {"ORACLE_PARENT_ONLY": "1"})
if not (value(ctl, "x") == "1" and not okv(ctl, "y")): broken("run_py is wrong")
if "# Read-only: writes nothing" not in PROBE_BLOCK or "=== PROBE BEGIN oracle-r3 ===" not in PROBE_BLOCK: broken("the oracle's probe block is malformed")
if len(b"not really a tarball\n") != 21: broken("the deliver fixture is wrong")

print(f"[checkpoint] {len(failures)} failing probe(s)")
sys.exit(1 if failures else 0)
PY

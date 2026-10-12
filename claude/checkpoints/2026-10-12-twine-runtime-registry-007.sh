#!/usr/bin/env bash
# Blind checkpoint — session twine-runtime-registry (Arc 2 R1, v1), authored
# at the desk of sitting 2026-10-08-open-arc2-003 from the request alone.
#
# What it grades (outcomes only): `twine runtime list --json` reports the
# eight capabilities of twine-seed.md §4.1 under their pinned names, each
# with a status from the closed set, the three the fake adapter implements
# marked implemented, and an adapter named `fake` registered against them;
# `twine runtime show NAME --json` renders one capability with a contract
# and refuses an unknown name by name; parity by name — a module planted
# under twine/runtime/capabilities/ that the declaration does not list, and
# a listed module removed, each make `list` NOT OK naming it; the
# usage-accounting module's `from_anthropic` maps the recorded Messages
# API usage onto the five token classes and refuses a usage without counts;
# the recording is in place byte for byte; the runtime contract doc exists
# and names the boundary's four things; nothing under twine/runtime/
# imports a network module; VERSION moved; no __pycache__.
#
# Writes only under ./.checkpoint-r1.<pid>/ (removed at exit); reads nothing
# of its own. Exit 0 all probes passed; 1 a probe failed; 2 the oracle is
# broken.
set -u
WORK="$(pwd)/.checkpoint-r1.$$"
mkdir -p "$WORK" || exit 2
trap 'rm -rf "$WORK"' EXIT
echo "[checkpoint] writes only under $WORK (removed at exit)"
export TMPDIR="$WORK"
PYTHONDONTWRITEBYTECODE=1 python3 -I -B - "$WORK" <<'PY'
import hashlib, json, os, re, shutil, subprocess, sys, tomllib
from pathlib import Path

def broken(msg):
    print(f"[checkpoint] ORACLE BROKEN: {msg}")
    sys.exit(2)
sys.excepthook = lambda t, v, tb: broken(f"unplanned {t.__name__}: {v}")

WORK = Path(sys.argv[1]); TREE = Path.cwd()
EIGHT = {"tool-calling", "thinking", "prompt-caching", "window-accounting", "streaming",
         "sandboxing", "suspend-resume", "usage-accounting"}
IMPLEMENTED = {"tool-calling", "thinking", "usage-accounting"}
STATUSES = {"declared", "implemented", "experimental"}
REC_PATH = "fixtures/anthropic/messages-usage-2026-10-08.json"
REC_SHA = "98137f648aa03f5c73628db77527df11b7f0d3222067f499e6b7573521f2b094"
NET = ("anthropic", "urllib.request", "http.client", "socket", "ssl")

failures = []
def probe(label, ok):
    print(f"{'[PASS]' if ok else '[FAIL]'} {label}")
    if not ok: failures.append(label)

def copy_tree(name):
    dst = WORK / name
    shutil.copytree(TREE, dst, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", ".checkpoint-*", ".validation-logs", "__pycache__"))
    return dst

def twine(root, *argv, json_mode=True):
    env = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8", "TMPDIR": str(WORK),
           "PYTHONDONTWRITEBYTECODE": "1"}
    args = [sys.executable, "-I", "-B", str(root / "bin" / "twine"), *argv] + (["--json"] if json_mode else [])
    return subprocess.run(args, capture_output=True, env=env, cwd=str(WORK), timeout=120)
def twin(p):
    try: return json.loads(p.stdout) if p.stdout.strip() else None
    except ValueError: return None
def one_line(p): return p.stdout.count(b"\n") == 1 and not p.stdout.strip().startswith(b"Traceback")

# --- detectors ---
def listing_ok(p):
    o = twin(p)
    if not (o and p.returncode == 0 and o.get("ok") is True and o.get("command") == "runtime list" and one_line(p)): return False
    caps = o.get("capabilities"); ads = o.get("adapters")
    if not (isinstance(caps, list) and isinstance(ads, list)): return False
    by = {}
    for c in caps:
        if not (isinstance(c, dict) and isinstance(c.get("name"), str)): return False
        if not (c.get("status") in STATUSES and isinstance(c.get("summary"), str) and c["summary"].strip()
                and isinstance(c.get("module"), str) and c["module"].startswith("twine.runtime.")
                and isinstance(c.get("adapters"), list)): return False
        by[c["name"]] = c
    if not EIGHT <= set(by): return False
    if {n for n, c in by.items() if c["status"] == "implemented"} != IMPLEMENTED: return False
    fake = [a for a in ads if isinstance(a, dict) and a.get("name") == "fake"]
    if len(fake) != 1 or not IMPLEMENTED <= set(fake[0].get("capabilities") or []): return False
    return all("fake" in by[n]["adapters"] for n in IMPLEMENTED)
def not_ok_naming(p, name):
    o = twin(p)
    return (o is not None and p.returncode == 1 and o.get("ok") is False and one_line(p)
            and name in json.dumps(o, ensure_ascii=False) and b"Traceback" not in p.stderr)
def show_ok(p, name):
    o = twin(p)
    return (o is not None and p.returncode == 0 and o.get("ok") is True and o.get("command") == "runtime show"
            and o.get("name") == name and o.get("status") in STATUSES and isinstance(o.get("module"), str)
            and "fake" in (o.get("adapters") or []) and bool(o.get("contract")) and one_line(p))
def module_path(root, dotted):
    p = root / Path(*dotted.split("."))
    return p.with_suffix(".py") if p.with_suffix(".py").is_file() else (p / "__init__.py" if (p / "__init__.py").is_file() else None)

def call_from_anthropic(root, dotted, usage):
    code = ("import sys, json, importlib\n"
            f"sys.path.insert(0, {json.dumps(str(root))})\n"
            f"m = importlib.import_module({json.dumps(dotted)})\n"
            f"u = json.loads({json.dumps(json.dumps(usage))})\n"
            "try:\n    t = m.from_anthropic(u)\n"
            "except Exception as e:\n    print(json.dumps({'raised': type(e).__name__})); sys.exit(0)\n"
            "from twine.spend import Tokens\n"
            "print(json.dumps({'tokens': t.as_json(), 'is_tokens': isinstance(t, Tokens)}))\n")
    env = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, env=env, cwd=str(WORK), timeout=120)
    try: return json.loads(p.stdout)
    except ValueError: return {"error": p.stderr.decode(errors="replace")[-400:]}
def mapped(r, want): return r.get("is_tokens") is True and r.get("tokens") == want
def refused(r): return isinstance(r.get("raised"), str)

def imports_net(root):
    hits = []
    for p in (root / "twine" / "runtime").rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        for mod in NET:
            if re.search(rf"^\s*(import|from)\s+{re.escape(mod)}(\s|$|\.)", text, re.M):
                hits.append(f"{p.relative_to(root)}:{mod}")
    return hits

# --- probes ---
base = copy_tree("base")
p = twine(base, "runtime", "list")
probe("runtime list --json: ok, the eight capabilities with closed statuses, tool-calling/thinking/usage-accounting implemented, adapter `fake` registered against them", listing_ok(p))
listing = twin(p) or {}
caps = {c.get("name"): c for c in listing.get("capabilities", []) if isinstance(c, dict)}
h = twine(base, "runtime", "list", json_mode=False)
probe("runtime list (human): exit 0 and every one of the eight named on stdout",
      h.returncode == 0 and all(n.encode() in h.stdout for n in EIGHT))

p = twine(base, "runtime", "show", "usage-accounting")
probe("runtime show usage-accounting --json: ok, status, module, adapters include fake, a non-empty contract", show_ok(p, "usage-accounting"))
p = twine(base, "runtime", "show", "no-such-capability")
probe("runtime show of an unknown name: NOT OK, exit 1, the name in the reason", not_ok_naming(p, "no-such-capability"))

c = twine(base, "commands")
cmds = {r.get("name") for r in ((twin(c) or {}).get("commands") or []) if isinstance(r, dict)}
probe("twine commands lists runtime list and runtime show", {"runtime list", "runtime show"} <= cmds)

planted = copy_tree("planted")
capdir = planted / "twine" / "runtime" / "capabilities"
probe("twine/runtime/capabilities/ is a directory and twine/runtime/capabilities.toml parses",
      capdir.is_dir() and isinstance(tomllib.loads((planted / "twine/runtime/capabilities.toml").read_text(encoding="utf-8")) if (planted / "twine/runtime/capabilities.toml").is_file() else None, dict))
if capdir.is_dir():
    (capdir / "zz_oracle_planted.py").write_text('"""planted by the checkpoint: not in the declaration."""\n')
    p = twine(planted, "runtime", "list")
    probe("parity: a module under capabilities/ the declaration does not list makes `list` NOT OK naming it", not_ok_naming(p, "zz_oracle_planted"))
    hp = twine(planted, "runtime", "list", json_mode=False)
    probe("…and the human rendering names it too, exit 1", hp.returncode == 1 and b"zz_oracle_planted" in hp.stdout)
else:
    probe("parity (planted): skipped — no capabilities directory", False)

removed = copy_tree("removed")
th = caps.get("thinking") or {}
mp = module_path(removed, th.get("module", "")) if isinstance(th.get("module"), str) else None
if mp and mp.is_file() and mp.name != "__init__.py":
    mp.unlink()
    p = twine(removed, "runtime", "list")
    probe("parity: a listed capability whose module is missing makes `list` NOT OK naming it", not_ok_naming(p, "thinking"))
else:
    probe("parity (removed): the module `list` names for `thinking` is a file under the tree", False)

rec = TREE / REC_PATH
probe(f"{REC_PATH} is in place byte for byte", rec.is_file() and hashlib.sha256(rec.read_bytes()).hexdigest() == REC_SHA)
ua = caps.get("usage-accounting") or {}
dotted = ua.get("module") if isinstance(ua.get("module"), str) else None
if dotted and rec.is_file():
    usage = json.loads(rec.read_bytes())
    r = call_from_anthropic(base, dotted, usage)
    probe("from_anthropic on the recording: input 18, output 4, thinking 0, cache_read 0, cache_write 0",
          mapped(r, {"input": 18, "output": 4, "thinking": 0, "cache_read": 0, "cache_write": 0}))
    u2 = dict(usage); u2.update({"cache_creation_input_tokens": 7, "cache_read_input_tokens": 11, "output_tokens": 40,
                                 "output_tokens_details": {"thinking_tokens": 3}})
    probe("from_anthropic maps cache_creation→cache_write, cache_read→cache_read, thinking_tokens→thinking",
          mapped(call_from_anthropic(base, dotted, u2), {"input": 18, "output": 40, "thinking": 3, "cache_read": 11, "cache_write": 7}))
    u3 = {"input_tokens": 5, "output_tokens": 2}
    probe("from_anthropic without output_tokens_details or cache keys: thinking None, caches 0",
          mapped(call_from_anthropic(base, dotted, u3), {"input": 5, "output": 2, "thinking": None, "cache_read": 0, "cache_write": 0}))
    probe("from_anthropic without input_tokens raises", refused(call_from_anthropic(base, dotted, {"output_tokens": 2})))
    probe("from_anthropic with a negative count raises", refused(call_from_anthropic(base, dotted, {"input_tokens": -1, "output_tokens": 2})))
    probe("from_anthropic with a non-integer count raises", refused(call_from_anthropic(base, dotted, {"input_tokens": "18", "output_tokens": 2})))
else:
    probe("from_anthropic: the usage-accounting module is named by `list` and the recording exists", False)

doc = TREE / "claude/context/runtime-contract.md"
text = doc.read_text(encoding="utf-8").lower() if doc.is_file() else ""
probe("claude/context/runtime-contract.md exists and names tool calling, thinking, usage accounting, the stop set and the fake adapter",
      bool(text) and all(w in text for w in ("tool calling", "thinking", "usage accounting", "stop", "fake")))
cli = (TREE / "claude/context/cli-contract.md").read_text(encoding="utf-8")
probe("cli-contract.md documents `twine runtime list` and `twine runtime show`", "twine runtime list" in cli and "twine runtime show" in cli)
hits = imports_net(TREE)
probe("nothing under twine/runtime/ imports anthropic, urllib.request, http.client, socket or ssl" + (f" ({', '.join(hits)})" if hits else ""), not hits)
ver = (TREE / "VERSION").read_text(encoding="utf-8").strip()
try: tup = tuple(int(x) for x in ver.split("."))
except ValueError: tup = ()
probe(f"VERSION ({ver}) is at least 0.16.0", len(tup) == 3 and tup >= (0, 16, 0))
probe("no __pycache__ in the tree", not any(p.name == "__pycache__" for p in TREE.rglob("__pycache__") if ".checkpoint-r1" not in str(p)))

# --- controls ---
class Fake:
    def __init__(self, rc, out, err=b""): self.returncode, self.stdout, self.stderr = rc, out, err
def good_listing():
    caps = [{"name": n, "status": "implemented" if n in IMPLEMENTED else "declared", "summary": "s",
             "module": f"twine.runtime.capabilities.{n.replace('-', '_')}", "adapters": ["fake"] if n in IMPLEMENTED else []} for n in sorted(EIGHT)]
    return {"command": "runtime list", "ok": True, "capabilities": caps, "adapters": [{"name": "fake", "capabilities": sorted(IMPLEMENTED)}]}
g = good_listing()
if not listing_ok(Fake(0, (json.dumps(g) + "\n").encode())): broken("listing_ok refuses a good listing")
bad = good_listing(); bad["capabilities"][0]["status"] = "ready"
if listing_ok(Fake(0, (json.dumps(bad) + "\n").encode())): broken("listing_ok accepts a status outside the set")
bad = good_listing(); bad["capabilities"] = [c for c in bad["capabilities"] if c["name"] != "streaming"]
if listing_ok(Fake(0, (json.dumps(bad) + "\n").encode())): broken("listing_ok accepts seven")
bad = good_listing(); bad["adapters"] = []
if listing_ok(Fake(0, (json.dumps(bad) + "\n").encode())): broken("listing_ok accepts no fake adapter")
bad = good_listing(); [c for c in bad["capabilities"] if c["name"] == "thinking"][0]["status"] = "declared"
if listing_ok(Fake(0, (json.dumps(bad) + "\n").encode())): broken("listing_ok accepts thinking unimplemented")
if listing_ok(Fake(1, (json.dumps(g) + "\n").encode())): broken("listing_ok accepts exit 1")
if listing_ok(Fake(0, (json.dumps(g) + "\n" + json.dumps(g) + "\n").encode())): broken("listing_ok accepts two lines")
r = {"command": "runtime list", "ok": False, "problems": ["undeclared module zz_oracle_planted"]}
if not not_ok_naming(Fake(1, (json.dumps(r) + "\n").encode()), "zz_oracle_planted"): broken("not_ok_naming refuses a good refusal")
if not_ok_naming(Fake(1, (json.dumps(r) + "\n").encode()), "thinking"): broken("not_ok_naming accepts a refusal that does not name the fault")
if not_ok_naming(Fake(0, (json.dumps(r) + "\n").encode()), "zz_oracle_planted"): broken("not_ok_naming accepts exit 0")
if not_ok_naming(Fake(1, (json.dumps(r) + "\n").encode(), b"Traceback (most recent call last)"), "zz_oracle_planted"): broken("not_ok_naming accepts a traceback")
s = {"command": "runtime show", "ok": True, "name": "usage-accounting", "status": "implemented", "module": "twine.runtime.capabilities.usage_accounting", "adapters": ["fake"], "contract": {"maps": "usage"}}
if not show_ok(Fake(0, (json.dumps(s) + "\n").encode()), "usage-accounting"): broken("show_ok refuses a good show")
s2 = dict(s); s2["contract"] = ""
if show_ok(Fake(0, (json.dumps(s2) + "\n").encode()), "usage-accounting"): broken("show_ok accepts an empty contract")
s3 = dict(s); s3["adapters"] = []
if show_ok(Fake(0, (json.dumps(s3) + "\n").encode()), "usage-accounting"): broken("show_ok accepts no adapter")
if not mapped({"is_tokens": True, "tokens": {"input": 1}}, {"input": 1}) or mapped({"is_tokens": False, "tokens": {"input": 1}}, {"input": 1}) or mapped({"raised": "ValueError"}, {"input": 1}): broken("mapped is wrong")
if not refused({"raised": "ValueError"}) or refused({"is_tokens": True, "tokens": {}}): broken("refused is wrong")
ctl = WORK / "ctl-net"; (ctl / "twine" / "runtime").mkdir(parents=True)
(ctl / "twine" / "runtime" / "x.py").write_text("import json\nfrom urllib.request import urlopen\n")
(ctl / "twine" / "runtime" / "y.py").write_text("# urllib.request mentioned in a comment only\nimport socketserver_not\n")
if imports_net(ctl) != ["twine/runtime/x.py:urllib.request"]: broken(f"imports_net is wrong: {imports_net(ctl)}")
if module_path(base, "twine.spend") != base / "twine" / "spend.py" or module_path(base, "twine.commands") != base / "twine" / "commands" / "__init__.py" or module_path(base, "twine.nope") is not None: broken("module_path is wrong")
if not re.fullmatch(r"[0-9a-f]{64}", REC_SHA) or hashlib.sha256(b"x").hexdigest() == REC_SHA: broken("the recording hash is not a hash")

print(f"[checkpoint] {len(failures)} failing probe(s)")
sys.exit(1 if failures else 0)
PY

#!/usr/bin/env bash
# Blind checkpoint — session twine-pin-floor (v1), authored at the desk of
# sitting 2026-10-08-open-arc2-003 from the request alone.
#
# What it grades (outcomes only): D2's gate is a floor plus the manifest's
# contract. The consumption manifest's [bale] table carries `floor`, not
# `pin`; the eight schema files twine was read against land as fixtures;
# `twine bale check` (and `status`'s `bale` object) is ok exactly for an
# install whose bin/VERSION is at or above the floor AND whose schemas/
# hash as the manifest pins them — below the floor, a schema that differs,
# a schemas/ directory missing, or an unparsable version is not ok, naming
# which; the carry verbs and the kill's closure drive an install above the
# floor and refuse one below it; a --json line that lacks a key the
# manifest lists for that surface is not ok, naming the key; the contract
# no longer says a version other than the pin is refused; the transition
# table is still total.
#
# Writes only under ./.checkpoint-pin-floor.<pid>/ in the tree it grades
# (removed at exit); reads nothing of its own. Exit 0 all probes passed;
# 1 a probe failed (named); 2 the oracle is broken.
set -u
WORK="$(pwd)/.checkpoint-pin-floor.$$"
mkdir -p "$WORK" || exit 2
trap 'rm -rf "$WORK"' EXIT
echo "[checkpoint] writes only under $WORK (removed at exit)"
export TMPDIR="$WORK"
PYTHONDONTWRITEBYTECODE=1 python3 -I -B - "$WORK" <<'PY'
import hashlib, json, os, shutil, stat, subprocess, sys, tomllib
from pathlib import Path

def broken(msg):
    print(f"[checkpoint] ORACLE BROKEN: {msg}")
    sys.exit(2)
sys.excepthook = lambda t, v, tb: broken(f"unplanned {t.__name__}: {v}")

WORK = Path(sys.argv[1]); TREE = Path.cwd()
TWINE = TREE / "bin" / "twine"
FLOOR = "0.4.51"
SCHEMAS = {
 "bundle-manifest.schema.json": "3384ebcd52a08044356f30f1031f4389e9b4427d81602173b0c59f4f9f9cea23",
 "changelog-record.schema.json": "7b6d351c052dad8588b05e7592da78f9e9052a671ad6dae9395bfd6d531c5b5c",
 "diagnostics.schema.json": "bfeef3cc0a6b91b47b1c1c9084ca47349b23a6661b10c848da3b4ef28b413521",
 "escalation-record.schema.json": "16729aae82e20425f91b9fb343de6a74d00fa417ce3cd718767413deee550c41",
 "exchange-record.schema.json": "c9c291899103c4a73768ef930697722b89c5c3ef8f5b388c78c36741316cddc8",
 "request-manifest.schema.json": "70a0c2bd3b6b0d4cf17bc97010c2b7d58931527b7b3100aa984ca3576c075e3d",
 "response-manifest.schema.json": "02d2b6413d078e031641c99e09a9fea909555bdfcb9b2a8a110dbdce63f5817e",
 "telemetry-record.schema.json": "b79d7bf75c10f5799484f906954461e7379ef6d4a870bb7df8c08ce050b38825"}
FIXTURE_SCHEMAS = TREE / f"fixtures/bale-{FLOOR}/schemas"
SID = "2026-10-12-floor-oracle-001"
STALE_SENTENCE = ("Both verbs refuse, before bale is started, a bale\nwhose `bin/VERSION` is not the pin, one whose `bin/VERSION` cannot be\nread, and any bale when the pin itself is unknown")

failures = []
def probe(label, ok):
    print(f"{'[PASS]' if ok else '[FAIL]'} {label}")
    if not ok: failures.append(label)

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

# --- stub install roots: bin/VERSION, bin/bale (a stub printing one line), schemas/ ---
def root(name, version, *, schemas=True, alter=None, line=None, exit_code=0):
    r = WORK / f"root-{name}"; (r / "bin").mkdir(parents=True)
    if version is not None: (r / "bin" / "VERSION").write_text(version + "\n")
    if schemas and FIXTURE_SCHEMAS.is_dir():
        (r / "schemas").mkdir()
        for f in SCHEMAS:
            src = FIXTURE_SCHEMAS / f
            if src.is_file():
                data = src.read_bytes()
                if alter == f: data = data + b"\n"
                (r / "schemas" / f).write_bytes(data)
    stub = r / "bin" / "bale"
    body = f"cat {json.dumps(str(r / 'line.json'))}\n" if line is not None else ""
    if line is not None: (r / "line.json").write_text(line, encoding="utf-8")
    stub.write_text(f"#!/usr/bin/env bash\n# oracle stub, not bale\ncat >/dev/null\n{body}exit {exit_code}\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return r

def run(*argv, env=None):
    base = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8", "TMPDIR": str(WORK)}
    if env: base.update(env)
    return subprocess.run([sys.executable, "-I", "-S", "-B", str(TWINE), *argv],
                          capture_output=True, env=base, cwd=str(TREE), timeout=300)
def twin(proc):
    return json.loads(proc.stdout) if proc.stdout.strip() else None

# --- detectors ---
def check_is(proc, want_ok):
    obj = twin(proc)
    return (obj is not None and obj.get("ok") is want_ok and proc.returncode == (0 if want_ok else 1)
            and obj.get("floor") == FLOOR and "pin" not in obj and isinstance(obj.get("reason"), str))
def reason_names(proc, word):
    obj = twin(proc); return obj is not None and isinstance(obj.get("reason"), str) and word in obj["reason"]
def verb_ran(proc, want):
    obj = twin(proc); return obj is not None and obj.get("ran") is want
def not_ok_naming_key(proc, key):
    obj = twin(proc)
    return (obj is not None and obj.get("ok") is False and proc.returncode == 1 and obj.get("ran") is True
            and isinstance(obj.get("reason"), str) and key in obj["reason"])

# --- probes: the schema fixtures and the manifest ---
for f, h in SCHEMAS.items():
    p = FIXTURE_SCHEMAS / f
    probe(f"fixtures/bale-{FLOOR}/schemas/{f} landed with sha256 {h[:12]}", p.is_file() and sha(p) == h)
m = tomllib.load(open(TREE / "share/bale-consumption.toml", "rb"))
probe("consumption manifest: [bale] carries floor = 0.4.51 and no pin", m["bale"].get("floor") == FLOOR and "pin" not in m["bale"])
probe("consumption manifest: [bale.schemas] unchanged", m["bale"].get("schemas") == SCHEMAS)

# --- probes: bale check ---
r_floor = root("at-floor", FLOOR); r_above = root("above", "0.4.52"); r_far = root("far", "0.5.0")
r_below = root("below", "0.4.49"); r_bad = root("bad-schema", "0.4.52", alter="telemetry-record.schema.json")
r_none = root("no-schemas", "0.4.52", schemas=False); r_junk = root("junk-version", "zero.four")
probe("bale check: an install at the floor with matching schemas is ok", check_is(run("bale", "check", "--json", "--bale-root", str(r_floor)), True))
probe("bale check: 0.4.52 with matching schemas is ok", check_is(run("bale", "check", "--json", "--bale-root", str(r_above)), True))
probe("bale check: 0.5.0 with matching schemas is ok", check_is(run("bale", "check", "--json", "--bale-root", str(r_far)), True))
p = run("bale", "check", "--json", "--bale-root", str(r_below))
probe("bale check: 0.4.49 is not ok and the reason names the floor", check_is(p, False) and reason_names(p, FLOOR))
p = run("bale", "check", "--json", "--bale-root", str(r_bad))
probe("bale check: a schema that differs is not ok and the reason names the file", check_is(p, False) and reason_names(p, "telemetry-record.schema.json"))
p = run("bale", "check", "--json", "--bale-root", str(r_none))
probe("bale check: no schemas/ under the install is not ok and the reason says so", check_is(p, False) and reason_names(p, "schemas"))
probe("bale check: a version that does not parse is not ok", check_is(run("bale", "check", "--json", "--bale-root", str(r_junk)), False))
p = run("bale", "check", "--json", "--bale-root", str(r_above))
probe("bale check --json: keys floor, installed, schemas, ok, reason present; pin absent",
      (lambda o: o is not None and all(k in o for k in ("floor", "installed", "schemas", "ok", "reason", "root", "source")) and "pin" not in o)(twin(p)))
p = run("status", "--json", "--bale-root", str(r_above))
probe("status --json: floor beside the bale object, no pin key, bale.ok true for 0.4.52",
      (lambda o: o is not None and o.get("floor") == FLOOR and "pin" not in o and isinstance(o.get("bale"), dict) and o["bale"].get("ok") is True)(twin(p)))

# --- probes: the verbs drive above the floor and refuse below it ---
def exchange_block(sid, record):
    body = json.dumps(record, indent=2) + "\n"
    return (f"BALE EXCHANGE BEGIN {sid}\n# oracle specimen\n{body}# sha256 {hashlib.sha256(body.encode()).hexdigest()}\nBALE EXCHANGE END\n")
worker = exchange_block(SID, {"record_version": 1, "session_id": SID, "round": 1, "from": "worker",
                              "created_at": "2026-10-12T00:00:00+00:00",
                              "questions": [{"question": "Which?", "context": "c", "default_assumption": "a", "why_blocked": "b"}]})
planner = exchange_block(SID, {"record_version": 1, "session_id": SID, "round": 2, "from": "planner",
                               "created_at": "2026-10-12T00:00:01+00:00",
                               "answers": [{"question_round": 1, "answer": "a", "disposition": "as-recommended"}]})
turn = WORK / "turn.txt"; turn.write_text(f"turn\n\n{worker}\n", encoding="utf-8")
def relay_line(**drop):
    d = {"outcome": "relayed", "sid": SID, "round": 2, "from": "planner", "awaiting": "worker",
         "kind": "exchange record", "preserved": f".bale/clarifications/{SID}/002.json", "block": planner,
         "log": f"/nowhere/{SID}.log", "clipboard": False, "cause": None, "telemetry": None, "reason": None}
    for k in drop: d.pop(k)
    return json.dumps(d) + "\n"
r_ex_above = root("exchange-above", "0.4.52", line=relay_line())
r_ex_below = root("exchange-below", "0.4.49", line=relay_line())
r_ex_nocause = root("exchange-no-cause", "0.4.52", line=relay_line(cause=None))
p = run("carry", "exchange", str(turn), "--cwd", str(WORK), "--bale-root", str(r_ex_above), "--json")
probe("carry exchange drives a 0.4.52 install (ran true, ok)", verb_ran(p, True) and twin(p).get("ok") is True)
p = run("carry", "exchange", str(turn), "--cwd", str(WORK), "--bale-root", str(r_ex_below), "--json")
probe("carry exchange refuses a 0.4.49 install before starting it (ran false, reason names the floor)", verb_ran(p, False) and reason_names(p, FLOOR))
p = run("carry", "exchange", str(turn), "--cwd", str(WORK), "--bale-root", str(r_ex_nocause), "--json")
probe("carry exchange: a relayed line without the `cause` key the manifest lists is not ok, naming cause", not_ok_naming_key(p, "cause"))
dry = json.dumps({"outcome": "dry-run", "sid": SID, "log": f"/nowhere/{SID}.log", "verdict": None, "merge": None,
                  "telemetry": None, "drift": None, "checkpoint": None, "required_checks": None, "archive": None, "sweep": None}) + "\n"
tarball = WORK / f"response-{SID}.tar.gz"; tarball.write_bytes(b"not a real tarball; the stub never reads it\n")
p = run("carry", "response", str(tarball), "--cwd", str(WORK), "--bale-root", str(root("response-above", "0.4.52", line=dry)), "--json")
probe("carry response drives a 0.4.52 install (ran true, ok)", verb_ran(p, True) and twin(p).get("ok") is True)
p = run("carry", "response", str(tarball), "--cwd", str(WORK), "--bale-root", str(root("response-below", "0.4.49", line=dry)), "--json")
probe("carry response refuses a 0.4.49 install (ran false)", verb_ran(p, False) and reason_names(p, FLOOR))
open_keys = ["outcome", "sid", "tarball", "log", "session_dir", "context_files", "readme_path", "readme_heading",
             "readme_sha256", "checkpoint_file_path", "checkpoint_file_sha256", "branch", "applied_latest", "sweep",
             "include_group", "opener", "bundle", "members", "rehearsal", "checkpoint_dry_run", "desk", "reason", "cause"]
def open_line(**drop):
    d = {k: None for k in open_keys}; d.update({"outcome": "rehearsed", "bundle": {"path": "/x/b.bale-bundle", "sha256": "0" * 64, "stem": "b"},
                                                 "members": {"brief": None, "checkpoint": None}, "rehearsal": "check"})
    for k in drop: d.pop(k)
    return json.dumps(d) + "\n"
bundle = WORK / "oracle-stub.bale-bundle"; bundle.write_bytes(b"stub\n")
p = run("carry", "bundle", str(bundle), "--check", "--cwd", str(WORK), "--bale-root", str(root("bundle-above", "0.4.52", line=open_line())), "--json")
probe("carry bundle --check drives a 0.4.52 install (ran true, ok)", verb_ran(p, True) and twin(p).get("ok") is True)
p = run("carry", "bundle", str(bundle), "--check", "--cwd", str(WORK), "--bale-root", str(root("bundle-below", "0.4.49", line=open_line())), "--json")
probe("carry bundle refuses a 0.4.49 install (ran false)", verb_ran(p, False) and reason_names(p, FLOOR))
p = run("carry", "bundle", str(bundle), "--check", "--cwd", str(WORK), "--bale-root", str(root("bundle-no-desk", "0.4.52", line=open_line(desk=None))), "--json")
probe("carry bundle: a rehearsed line without the `desk` key the manifest lists is not ok, naming desk", not_ok_naming_key(p, "desk"))
probe("twine transitions --json is still total (ok)", (lambda o: o is not None and o.get("ok") is True)(twin(run("transitions", "--json"))))

# --- probes: the contract no longer says the pin is exact ---
contract = (TREE / "claude/context/cli-contract.md").read_text(encoding="utf-8")
probe("cli-contract.md §11.1's exact-pin sentence is gone", STALE_SENTENCE not in contract)
probe("cli-contract.md names the floor in §5 and §11.1", "floor" in contract.split("\n## 5. ", 1)[1].split("\n## 6. ", 1)[0] and "floor" in contract.split("\n### 11.1 ", 1)[1].split("\n### 11.2 ", 1)[0])

# --- controls ---
class Fake:
    def __init__(self, rc, out): self.returncode, self.stdout = rc, out
good = json.dumps({"ok": True, "floor": FLOOR, "reason": "x", "installed": "0.4.52", "schemas": {}, "root": "/r", "source": "--bale-root"}).encode()
if not check_is(Fake(0, good), True): broken("check_is refuses a good check line")
if check_is(Fake(0, good.replace(b'"ok": true', b'"ok": false')), True): broken("check_is accepts ok false for want True")
if check_is(Fake(0, good.replace(b'"floor": "0.4.51"', b'"pin": "0.4.51", "floor": "0.4.51"')), True): broken("check_is accepts a pin key")
if check_is(Fake(1, good), True): broken("check_is accepts exit 1 for ok")
if not reason_names(Fake(0, good), "x") or reason_names(Fake(0, good), "zzz"): broken("reason_names is wrong")
if verb_ran(Fake(0, b'{"ran": false}'), True) or not verb_ran(Fake(0, b'{"ran": true}'), True): broken("verb_ran is wrong")
nk = json.dumps({"ok": False, "ran": True, "reason": "bale's line lacks keys the manifest lists: cause"}).encode()
if not not_ok_naming_key(Fake(1, nk), "cause") or not_ok_naming_key(Fake(1, nk), "desk") or not_ok_naming_key(Fake(0, nk), "cause"): broken("not_ok_naming_key is wrong")
if not_ok_naming_key(Fake(1, nk.replace(b'"ok": false', b'"ok": true')), "cause"): broken("not_ok_naming_key accepts ok true")
if STALE_SENTENCE not in "x " + STALE_SENTENCE + " y": broken("the stale-sentence probe cannot see its own sentence")
if len(SCHEMAS) != 8: broken("eight schemas expected")
# the altered root really differs from the floor root
if FIXTURE_SCHEMAS.is_dir() and (r_bad / "schemas" / "telemetry-record.schema.json").is_file() and sha(r_bad / "schemas" / "telemetry-record.schema.json") == SCHEMAS["telemetry-record.schema.json"]: broken("the altered schema root is not altered")

print(f"[checkpoint] {len(failures)} failing probe(s)")
sys.exit(1 if failures else 0)
PY

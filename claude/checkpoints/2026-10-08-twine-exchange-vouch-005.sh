#!/usr/bin/env bash
# Blind checkpoint — session twine-exchange-vouch (v1), authored at the
# desk of sitting 2026-10-08-open-arc2-003 from the request alone.
#
# What it grades (outcomes only, never how): `twine carry exchange`
# vouches for the block bale hands back. Against a stub bale whose
# `relay --json` line is `relayed` for the block's sid, the verb is ok and
# prints the block only when that block is one intact exchange block of
# the session; a block whose sha256 trailer does not hold, two blocks in
# one, prose with no block, or a block whose sentinel names another sid,
# is NOT OK (exit 1), its reason non-empty, and no `BALE EXCHANGE` line
# reaches stdout.
#
# Writes only under ./.checkpoint-exchange-vouch.<pid>/ in the tree it
# grades (removed at exit); it reads nothing of its own: no sid, no
# manifest, no own path. Exit 0: every probe passed. Exit 1: a probe
# failed (named). Exit 2: the oracle itself is broken (a control did not
# fire, or an unplanned exception).
set -u
WORK="$(pwd)/.checkpoint-exchange-vouch.$$"
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
PIN = tomllib.load(open(TREE / "share" / "bale-consumption.toml", "rb"))["bale"]["pin"]
SID = "2026-10-08-vouch-oracle-001"
OTHER_SID = "2026-10-08-vouch-other-002"

def exchange_block(sid, record):
    """An exchange paste block as bale and the crafter emit it: BEGIN with
    the sid, `#` header lines, the record pretty-printed (ASCII-escaped,
    indent 2) plus LF as the body, `# sha256 <hex>` of the body bytes, END."""
    body = json.dumps(record, indent=2) + "\n"
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return (f"BALE EXCHANGE BEGIN {sid}\n# bale exchange record — oracle specimen\n"
            f"{body}# sha256 {digest}\nBALE EXCHANGE END\n")

worker_record = {"record_version": 1, "session_id": SID, "round": 1, "from": "worker",
                 "created_at": "2026-10-08T00:00:00+00:00",
                 "questions": [{"question": "Which of the two?", "context": "the oracle's specimen",
                                "default_assumption": "the first", "why_blocked": "both named"}]}
planner_record = {"record_version": 1, "session_id": SID, "round": 2, "from": "planner",
                  "created_at": "2026-10-08T00:00:01+00:00",
                  "answers": [{"question_round": 1, "answer": "the first", "disposition": "as-recommended"}]}
turn_block = exchange_block(SID, worker_record)
intact = exchange_block(SID, planner_record)
# the returned-block variants the stub bale hands back
body_start = intact.index("{")
broken_trailer = intact[:body_start] + intact[body_start:].replace('"planner"', '"PLANNER"', 1)  # body edited, trailer stale
two_blocks = intact + intact
prose = "Nothing here is a block.\nJust two lines of prose.\n"
other_sid = intact.replace(f"BALE EXCHANGE BEGIN {SID}", f"BALE EXCHANGE BEGIN {OTHER_SID}", 1)

def relay_line(block):
    return json.dumps({"outcome": "relayed", "sid": SID, "round": 2, "from": "planner",
                       "awaiting": "worker", "kind": "exchange record",
                       "preserved": f".bale/clarifications/{SID}/002.json", "block": block,
                       "log": f"/nowhere/.bale/logs/{SID}.log", "clipboard": False,
                       "cause": None, "telemetry": None, "reason": None}) + "\n"

def stub_bale(name, block):
    """A stub install root whose bin/bale prints one relay line and exits 0,
    bin/VERSION at the manifest's pin (so the pin gate admits it)."""
    root = WORK / f"stub-{name}"; (root / "bin").mkdir(parents=True)
    (root / "bin" / "VERSION").write_text(PIN + "\n")
    line = root / "line.json"; line.write_text(relay_line(block), encoding="utf-8")
    script = root / "bin" / "bale"
    script.write_text("#!/usr/bin/env bash\n# oracle stub, not bale\ncat >/dev/null\n"
                      f"cat {json.dumps(str(line))}\nexit 0\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return root

turn = WORK / "turn.txt"
turn.write_text(f"The worker asks:\n\n{turn_block}\nEnd of turn.\n", encoding="utf-8")

def run(root, *extra):
    env = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8", "TMPDIR": str(WORK)}
    proc = subprocess.run([sys.executable, "-I", "-S", "-B", str(TWINE), "carry", "exchange",
                           str(turn), "--cwd", str(WORK), "--bale-root", str(root), *extra],
                          capture_output=True, env=env, cwd=str(TREE), timeout=120)
    return proc

failures = []
def probe(label, ok):
    print(f"{'[PASS]' if ok else '[FAIL]'} {label}")
    if not ok: failures.append(label)

# --- detectors (named functions; the controls below call these, never copies) ---
def is_ok_and_prints_block(proc, block):
    return proc.returncode == 0 and proc.stdout == block.encode("utf-8")
def is_not_ok_and_prints_no_block(proc):
    return (proc.returncode == 1 and b"BALE EXCHANGE" not in proc.stdout
            and b"Traceback" not in proc.stderr and proc.stdout.strip() != b"")
def twin_not_ok_with_reason(proc_json):
    obj = json.loads(proc_json.stdout)
    return (proc_json.returncode == 1 and obj["ok"] is False and isinstance(obj["reason"], str)
            and obj["reason"] and obj["ran"] is True and obj["outcome"] == "relayed"
            and isinstance(obj["relay"], dict))
def reason_names_mismatch(proc_json):
    reason = json.loads(proc_json.stdout).get("reason")
    return isinstance(reason, str) and "mismatch" in reason

# --- probes ---
roots = {name: stub_bale(name, block) for name, block in
         [("intact", intact), ("broken-trailer", broken_trailer), ("two-blocks", two_blocks),
          ("prose", prose), ("other-sid", other_sid)]}
p_intact = run(roots["intact"])
probe("intact block from bale: ok, stdout is exactly the block", is_ok_and_prints_block(p_intact, intact))
for name in ("broken-trailer", "two-blocks", "prose", "other-sid"):
    human = run(roots[name]); twin = run(roots[name], "--json")
    probe(f"{name}: NOT OK (exit 1), one line, no BALE EXCHANGE on stdout, no traceback",
          is_not_ok_and_prints_no_block(human))
    probe(f"{name}: --json twin not ok, reason non-empty, bale's line still carried (relay, outcome relayed)",
          twin_not_ok_with_reason(twin) if twin.stdout.strip() else False)
twin_bt = run(roots["broken-trailer"], "--json")
probe("broken-trailer: the reason names the fault as take names it (mismatch)",
      bool(twin_bt.stdout.strip()) and reason_names_mismatch(twin_bt))
# the shipped surfaces that must not move
probe("intact block: --json twin ok with sid, outcome relayed, reason null",
      (lambda o: o["ok"] is True and o["sid"] == SID and o["outcome"] == "relayed" and o["reason"] is None)
      (json.loads(run(roots["intact"], "--json").stdout)))

# --- controls: every detector fires on the input it must refuse (else the oracle is broken) ---
class Fake:  # a subprocess-shaped stand-in for the controls
    def __init__(self, rc, out, err=b""): self.returncode, self.stdout, self.stderr = rc, out, err
if is_ok_and_prints_block(Fake(0, broken_trailer.encode()), intact): broken("is_ok_and_prints_block accepts another block")
if is_ok_and_prints_block(Fake(1, intact.encode()), intact): broken("is_ok_and_prints_block accepts exit 1")
if is_not_ok_and_prints_no_block(Fake(1, intact.encode())): broken("is_not_ok_and_prints_no_block accepts a printed block")
if is_not_ok_and_prints_no_block(Fake(0, b"carry exchange: NOT OK\n")): broken("is_not_ok_and_prints_no_block accepts exit 0")
if is_not_ok_and_prints_no_block(Fake(1, b"x\n", b"Traceback (most recent call last)")): broken("…accepts a traceback")
good_twin = json.dumps({"ok": False, "reason": "bale's block fails integrity (mismatch)", "ran": True,
                        "outcome": "relayed", "relay": {"outcome": "relayed"}}).encode()
if not twin_not_ok_with_reason(Fake(1, good_twin)): broken("twin_not_ok_with_reason refuses a valid not-ok twin")
if twin_not_ok_with_reason(Fake(1, good_twin.replace(b'"reason": "bale', b'"reason": null, "x": "bale'))): broken("twin_not_ok_with_reason accepts a null reason")
if twin_not_ok_with_reason(Fake(0, good_twin)): broken("twin_not_ok_with_reason accepts exit 0")
if twin_not_ok_with_reason(Fake(1, good_twin.replace(b'"reason": "bale\'s block fails integrity (mismatch)"', b'"reason": ""'))): broken("twin_not_ok_with_reason accepts an empty reason")
if reason_names_mismatch(Fake(1, good_twin.replace(b"mismatch", b"other"))): broken("reason_names_mismatch accepts a reason without the fault")
if reason_names_mismatch(Fake(1, b'{"reason": null}')): broken("reason_names_mismatch accepts a null reason")
if not reason_names_mismatch(Fake(1, good_twin)): broken("reason_names_mismatch refuses the fault name")
# the specimens themselves must be what the probes assume
if not hashlib.sha256((intact.split("\n",2)[2].rsplit("# sha256",1)[0]).encode()).hexdigest() in intact: broken("the intact specimen's trailer does not hold")
if broken_trailer == intact or two_blocks.count("BALE EXCHANGE BEGIN") != 2 or OTHER_SID not in other_sid: broken("a specimen is not the variant it claims to be")

print(f"[checkpoint] {len(failures)} failing probe(s)")
sys.exit(1 if failures else 0)
PY

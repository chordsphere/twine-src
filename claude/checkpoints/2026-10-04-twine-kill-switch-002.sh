#!/usr/bin/env bash
# Blind checkpoint — twine-src road 5b, the kill-switch (slug twine-kill-switch), v2.
# v2 (2026-10-04, after the HOLD of 2026-10-04-twine-kill-switch-002): the running
# record the kill fixture writes now carries the session's `sid` beside pgid, pid
# and started_at — the desk ratified the worker's reading that a record names its
# session. Only that fixture line changed; every probe is as in v1.
# Authored at sitting 2026-10-03-continue-twine-006 from the request alone,
# before the work existed. Outcomes graded, never mechanisms:
#   - the suite passes; VERSION moved off 0.5.0 and --version agrees;
#   - a `kill` verb is registered with a --json twin;
#   - the stop axis has `cap-unchecked` with an operator move that is not
#     stop-at-cap, and the table is still ok;
#   - `spend check` reports stop cap-unchecked when the cap cannot be checked
#     and still cap-reached when the cap refuses;
#   - `twine kill <sid>` against a temp state dir, a real setsid process group
#     and a stub bale: the group dies, the abort request lands durably, bale
#     is asked exactly `unlock <sid> --reason aborted --json` and nothing
#     else, the closure is reported; when the stub refuses (exit 1, empty
#     stdout) the kill is not ok, shows the refusal and hands back the line.
# Writes: one temp directory under the current directory (the staging root),
# announced below and removed at exit; python runs with bytecode writing off.
# Exit 0: all probes pass. Exit 1: a probe failed (the work). Exit 2: the
# oracle itself is broken or cannot run.
set -u
export PYTHONDONTWRITEBYTECODE=1
echo "[checkpoint] twine-kill-switch v2"
TMP="$PWD/.checkpoint-twine-kill-switch.tmp"
echo "[checkpoint] writes: $TMP (created now, removed at exit); nothing else"
for tool in python3 setsid sleep; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "[checkpoint] ERROR: $tool not found; the oracle cannot run"; exit 2
  fi
done
if [ ! -f bin/twine ] || [ ! -f VERSION ] || [ ! -d tests ]; then
  echo "[checkpoint] ERROR: not at the twine-src tree root (bin/twine, VERSION, tests/ expected)"; exit 2
fi
rm -rf "$TMP"; mkdir -p "$TMP" || { echo "[checkpoint] ERROR: cannot create $TMP"; exit 2; }
cleanup() {
  if [ -n "${SLEEP_PID:-}" ]; then kill -KILL -- "-$SLEEP_PID" 2>/dev/null; kill -KILL "$SLEEP_PID" 2>/dev/null; fi
  rm -rf "$TMP"
}
trap cleanup EXIT

# --- fixtures: a real process group the kill must end ---------------------
setsid sleep 300 >/dev/null 2>&1 < /dev/null &
SLEEP_PID=$!
sleep 0.2
if ! kill -0 "$SLEEP_PID" 2>/dev/null; then echo "[checkpoint] ERROR: control: the setsid sleep did not start"; exit 2; fi
export CHECKPOINT_TMP="$TMP" CHECKPOINT_SLEEP_PID="$SLEEP_PID"

python3 -I -B - <<'PY'
import hashlib, json, os, re, signal, stat, subprocess, sys, time, traceback

def _unexpected(exc_type, exc, tb):
    traceback.print_exception(exc_type, exc, tb)
    print("[checkpoint] ERROR: the oracle raised an unexpected exception (exit 2)")
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(2)
sys.excepthook = _unexpected

TMP = os.environ["CHECKPOINT_TMP"]
SLEEP_PID = int(os.environ["CHECKPOINT_SLEEP_PID"])
SID = "2026-01-01-checkpoint-kill-001"
TWINE = [sys.executable, "-I", "-S", "bin/twine"]
ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONDONTWRITEBYTECODE": "1",
       "LC_ALL": "C.UTF-8"}
failures = []

def probe(label, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f": {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)

def oracle_error(msg):
    print(f"[checkpoint] ERROR: {msg}"); sys.stdout.flush(); sys.exit(2)

def run(argv, cwd=None, env=None, timeout=120):
    try:
        r = subprocess.run(argv, cwd=cwd, env=env or ENV, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "", f"timed out after {timeout}s"
    return r.returncode, r.stdout, r.stderr

def one_json_line(stdout):
    lines = [l for l in stdout.splitlines() if l.strip()]
    if len(lines) != 1:
        return None
    try:
        obj = json.loads(lines[0])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None

def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True

def dies_within(pid, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if not alive(pid):
            return True
        time.sleep(0.05)
    return not alive(pid)

# --- fixtures: a stub bale root, answering exactly one argv -----------------
UNLOCK_LINE = json.dumps({"outcome": "unlocked", "sid": SID,
                          "log": f"{TMP}/repo/.bale/logs/{SID}.log",
                          "closure_reason": "aborted", "session_dir_wiped": True,
                          "branch_preserved": False,
                          "telemetry": f"claude/telemetry/{SID}.json",
                          "debris": None, "sweep": None})
REFUSAL_TEXT = f"[bale] error: session {SID} is not open; nothing to unlock. No sessions are open."

def make_stub(root, mode):
    """mode 'close': the one expected argv prints UNLOCK_LINE, exit 0; anything
    else exits 1 with a refusal on stderr. mode 'refuse': every argv exits 1
    with REFUSAL_TEXT on stderr and nothing on stdout. Every argv is logged."""
    os.makedirs(os.path.join(root, "bin"), exist_ok=True)
    with open(os.path.join(root, "bin", "VERSION"), "w") as fh:
        fh.write("0.4.45\n")
    log_path = os.path.join(root, "argv.log")
    expected = f"unlock {SID} --reason aborted --json"
    script = f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> {json.dumps(log_path)}
if [ {json.dumps(mode)} = close ] && [ "$*" = {json.dumps(expected)} ]; then
  printf '%s\\n' {json.dumps(UNLOCK_LINE)}
  exit 0
fi
printf '%s\\n' {json.dumps(REFUSAL_TEXT)} >&2
exit 1
"""
    path = os.path.join(root, "bin", "bale")
    with open(path, "w") as fh:
        fh.write(script)
    os.chmod(path, 0o755)
    return log_path

def argv_log(path):
    try:
        with open(path) as fh:
            return [l.rstrip("\n") for l in fh if l.strip()]
    except OSError:
        return []

# --- control: the fixtures behave (exit 2 if not) ----------------------------
ctrl_root = os.path.join(TMP, "ctrl-bale")
ctrl_log = make_stub(ctrl_root, "close")
code, out, err = run([os.path.join(ctrl_root, "bin", "bale"), "unlock", SID, "--reason", "aborted", "--json"])
if code != 0 or one_json_line(out) is None or one_json_line(out).get("closure_reason") != "aborted":
    oracle_error(f"control: the stub bale does not answer its one argv (exit {code}, stdout {out!r})")
code, out, err = run([os.path.join(ctrl_root, "bin", "bale"), "unlock", SID, "--force", "--json"])
if code != 1 or out.strip() or "not open" not in err:
    oracle_error("control: the stub bale does not refuse an unexpected argv")
if argv_log(ctrl_log) != [f"unlock {SID} --reason aborted --json", f"unlock {SID} --force --json"]:
    oracle_error("control: the stub bale does not log its argv")
if not alive(SLEEP_PID):
    oracle_error("control: the setsid sleep is not alive before the kill")
if one_json_line("not json\n") is not None or one_json_line("{}\n{}\n") is not None:
    oracle_error("control: the one-JSON-line reader accepts what it should not")
print("[checkpoint] control: stub bale, argv log, process fixture and JSON reader verified")

# --- 1. the suite -----------------------------------------------------------
code, out, err = run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."], timeout=600)
tail = "\n".join((out + err).splitlines()[-3:])
probe("suite-passes", code == 0, f"unittest exited {code}: {tail}")

# --- 2. version ---------------------------------------------------------------
version = open("VERSION", encoding="utf-8").read().strip()
code, out, err = run(TWINE + ["--version"])
probe("version-bumped", version != "0.5.0" and code == 0 and out.strip() == f"twine {version}",
      f"VERSION {version!r}, --version printed {out.strip()!r} (exit {code})")

# --- 3. the verb is registered ----------------------------------------------------
code, out, err = run(TWINE + ["commands", "--json"])
cmds = one_json_line(out) or {}
names = {c.get("name"): c for c in cmds.get("commands", []) if isinstance(c, dict)}
probe("kill-verb-registered", code == 0 and "kill" in names and names["kill"].get("json") is True,
      f"registered verbs: {sorted(names)}")

# --- 4. the transition table ----------------------------------------------------
code, out, err = run(TWINE + ["transitions", "--json"])
table = one_json_line(out) or {}
stop_axis = next((a for a in table.get("axes", []) if isinstance(a, dict) and a.get("name") == "stop"), {})
rows = [r for r in table.get("rows", []) if isinstance(r, dict) and r.get("axis") == "stop" and r.get("key") == "cap-unchecked"]
row = rows[0] if len(rows) == 1 else {}
move = (table.get("moves") or {}).get(row.get("move") or "", {}) if row else {}
probe("transitions-cap-unchecked",
      code == 0 and table.get("ok") is True and "cap-unchecked" in (stop_axis.get("keys") or [])
      and len(rows) == 1 and row.get("actor") == "operator" and row.get("move") != "stop-at-cap"
      and move.get("actor") == "operator",
      f"exit {code}, ok {table.get('ok')}, stop keys {stop_axis.get('keys')}, rows {rows}")
probe("transitions-still-total", code == 0 and table.get("ok") is True and not table.get("problems"),
      f"exit {code}, problems {table.get('problems')}")

# --- 5. spend check's stop keys ----------------------------------------------------
state_a = os.path.join(TMP, "state-a"); os.makedirs(state_a)
code, out, err = run(TWINE + ["spend", "check", "--sid", SID, "--cap", "1", "--model", "checkpoint-model",
                      "--input", "1", "--max-output", "1", "--state-dir", state_a, "--json"])
chk = one_json_line(out) or {}
probe("spend-check-stop-cap-unchecked",
      code == 1 and chk.get("admitted") is False and chk.get("refusal") == "no-prices"
      and chk.get("stop") == "cap-unchecked",
      f"exit {code}, refusal {chk.get('refusal')!r}, stop {chk.get('stop')!r}")
state_b = os.path.join(TMP, "state-b"); os.makedirs(state_b)
with open(os.path.join(state_b, "prices.toml"), "w") as fh:   # a price DOUBLE for an invented model
    fh.write('[model."checkpoint-model"]\ninput = 1.0\noutput = 1.0\ncache_read = 1.0\ncache_write = 1.0\n')
code, out, err = run(TWINE + ["spend", "check", "--sid", SID, "--cap", "0", "--model", "checkpoint-model",
                      "--input", "1000000", "--max-output", "1", "--state-dir", state_b, "--json"])
chk = one_json_line(out) or {}
probe("spend-check-stop-cap-reached-unchanged",
      code == 1 and chk.get("refusal") == "cap-reached" and chk.get("stop") == "cap-reached",
      f"exit {code}, refusal {chk.get('refusal')!r}, stop {chk.get('stop')!r}")

# --- 6. twine kill, end to end -------------------------------------------------------
state_k = os.path.join(TMP, "state-k"); os.makedirs(os.path.join(state_k, "running"))
repo_k = os.path.join(TMP, "repo"); os.makedirs(repo_k)
with open(os.path.join(state_k, "running", f"{SID}.json"), "w") as fh:
    json.dump({"sid": SID, "pgid": SLEEP_PID, "pid": SLEEP_PID,
               "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, fh)
close_root = os.path.join(TMP, "bale-close"); close_log = make_stub(close_root, "close")
code, out, err = run(TWINE + ["kill", SID, "--state-dir", state_k, "--cwd", repo_k,
                      "--bale-root", close_root, "--grace", "0.5", "--json"], timeout=60)
kill = one_json_line(out) or {}
proc = kill.get("process") if isinstance(kill.get("process"), dict) else {}
closure = kill.get("closure") if isinstance(kill.get("closure"), dict) else {}
asked = argv_log(close_log)
probe("kill-ok", code == 0 and kill.get("ok") is True and kill.get("command") == "kill",
      f"exit {code}, ok {kill.get('ok')}, reason {kill.get('reason')!r}, stderr tail {err.strip()[-300:]!r}")
probe("kill-group-dead", dies_within(SLEEP_PID, 5.0) and proc.get("dead") is True and not proc.get("survivors"),
      f"sleep {SLEEP_PID} alive={alive(SLEEP_PID)}, process {proc}")
probe("kill-closure-aborted",
      kill.get("closed") is True and closure.get("outcome") == "unlocked" and closure.get("sid") == SID
      and closure.get("closure_reason") == "aborted",
      f"closed {kill.get('closed')}, closure {closure}")
probe("kill-asks-bale-exactly-once",
      asked == [f"unlock {SID} --reason aborted --json"],
      f"the stub bale saw {asked}")
mentions = []
for base, _, files in os.walk(state_k):
    for name in files:
        p = os.path.join(base, name)
        if "running" in os.path.relpath(p, state_k).split(os.sep):
            continue
        try:
            with open(p, "rb") as fh:
                if SID.encode() in fh.read() or SID in name:
                    mentions.append(os.path.relpath(p, state_k))
        except OSError:
            pass
probe("kill-abort-request-durable", kill.get("abort_requested") is True and len(mentions) >= 1,
      f"abort_requested {kill.get('abort_requested')}, state files naming the sid outside running/: {mentions}")

# --- 7. twine kill when bale refuses --------------------------------------------------
state_r = os.path.join(TMP, "state-r"); os.makedirs(state_r)      # no running record: nothing to kill
refuse_root = os.path.join(TMP, "bale-refuse"); refuse_log = make_stub(refuse_root, "refuse")
code, out, err = run(TWINE + ["kill", SID, "--state-dir", state_r, "--cwd", repo_k,
                      "--bale-root", refuse_root, "--json"], timeout=60)
kill_r = one_json_line(out) or {}
asked_r = argv_log(refuse_log)
probe("kill-refusal-surfaced",
      code == 1 and kill_r.get("ok") is False and kill_r.get("closed") is False
      and kill_r.get("closure") is None and "not open" in (kill_r.get("reason") or ""),
      f"exit {code}, ok {kill_r.get('ok')}, closed {kill_r.get('closed')}, reason {kill_r.get('reason')!r}")
probe("kill-refusal-hands-back-the-line",
      f"bale unlock {SID} --reason aborted" in (kill_r.get("operator_line") or ""),
      f"operator_line {kill_r.get('operator_line')!r}")
probe("kill-never-forces",
      asked_r == [f"unlock {SID} --reason aborted --json"] and not any("--force" in a for a in asked + asked_r),
      f"the refusing stub saw {asked_r}")
probe("kill-abort-still-requested-on-refusal", kill_r.get("abort_requested") is True,
      f"abort_requested {kill_r.get('abort_requested')}")

if failures:
    print(f"[checkpoint] {len(failures)} probe(s) failed: {', '.join(failures)}")
    sys.exit(1)
print("[checkpoint] all probes passed")
sys.exit(0)
PY
rc=$?
exit $rc

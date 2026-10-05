#!/usr/bin/env bash
# Blind checkpoint — twine-src, the kill follow-ups (slug twine-kill-followups), v1.
# Authored at sitting 2026-10-05-continue-twine-002 from the brief alone, before
# the session existed. It grades outcomes of the applied tree (TARBALL.md §7):
# what `twine status`, `twine kill`, the running-record format, the consumption
# manifest and the contract text must do or say — never how the worker got
# there. It needs no session id, no .bale-manifest.json and not its own
# filename: `bale open`'s dry-run runs it before any session exists.
#
# Exit 0: every probe passed. Exit 1: a probe failed, named on its own
# [FAIL] line. Exit 2: this oracle is broken (its control failed, or it hit an
# error of its own) — a verdict on the checkpoint, never on the work.
#
# Writes exactly one location, printed below, and removes it at exit:
#   <repo>/.checkpoint-scratch-<pid>/   (temp state directories, stub bale, a repo dir)
# No bytecode (PYTHONDONTWRITEBYTECODE=1 and -B throughout). No network. The
# only `bale` it runs is a stub it writes itself, which prints a double built
# from format_unlock_json's key contract (cli-contract.md §14.7). It never
# reads claude/checkpoints/, claude/responses/ or itself.

set -u
export PYTHONDONTWRITEBYTECODE=1
export LC_ALL=C.UTF-8

# The repo root: the working directory when it is the tree (bale runs the
# checkpoint in staging), else derived from this file's committed path
# claude/checkpoints/<sid>.sh. Neither answering is the oracle's fault (2).
if [ -f bin/twine ] && [ -f twine/kill.py ] && [ -f share/bale-consumption.toml ]; then
  ROOT="$(pwd)"
else
  ROOT="$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)"
  if [ -z "$ROOT" ] || [ ! -f "$ROOT/bin/twine" ] || [ ! -f "$ROOT/twine/kill.py" ]; then
    echo "[checkpoint] cannot find the twine-src tree from $(pwd) or from $0" >&2
    exit 2
  fi
fi
cd "$ROOT" || exit 2
SCRATCH="$ROOT/.checkpoint-scratch-$$"
echo "[checkpoint] writes: $SCRATCH (removed at exit)"
echo "[checkpoint] tree: $ROOT"

python3 -B - "$ROOT" "$SCRATCH" <<'PY'
import json, os, signal, subprocess, sys, time, tomllib
from pathlib import Path

ROOT = Path(sys.argv[1])
SCRATCH = Path(sys.argv[2])
SID = "2026-10-05-checkpoint-probe-001"
TWINE = [sys.executable, "-I", "-S", "-B", str(ROOT / "bin" / "twine")]
BASE_ENV = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            # never a bale on the developer's PATH (tests/helpers.py's rule)
            "TWINE_BALE_ROOT": str(SCRATCH / "no-bale-here")}
UNLOCK_LINE = f"bale unlock {SID} --reason aborted"
DEAD = {"Z", "X", "x"}

# --- the oracle's own failure is exit 2, never 1 ---------------------------
def _hook(exc_type, exc, tb):
    sys.stderr.write(f"[checkpoint] ORACLE ERROR {exc_type.__name__}: {exc}\n")
    import traceback; traceback.print_tb(tb, file=sys.stderr)
    cleanup()
    os._exit(2)
sys.excepthook = _hook

failures: list[str] = []
groups: list[subprocess.Popen] = []

def result(name: str, problems: list[str]) -> None:
    if problems:
        failures.append(name)
        print(f"[FAIL] {name}")
        for p in problems:
            print(f"       - {p}")
    else:
        print(f"[PASS] {name}")

# --- helpers that are the detectors (the control below proves them) --------
def proc_state(pid: int):
    try:
        text = (Path("/proc") / str(pid) / "stat").read_text("ascii", "replace")
        fields = text.rsplit(")", 1)[1].split()
        return fields[0], int(fields[2])
    except (OSError, IndexError, ValueError):
        return None

def alive(pid: int) -> bool:
    st = proc_state(pid)
    return st is not None and st[0] not in DEAD

def members(pgid: int) -> list[int]:
    out = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            st = proc_state(int(entry.name))
            if st is not None and st[1] == pgid and st[0] not in DEAD:
                out.append(int(entry.name))
    return sorted(out)

def wait_gone(pids: list[int], timeout: float) -> list[int]:
    deadline = time.monotonic() + timeout
    while True:
        left = [p for p in pids if alive(p)]
        if not left or time.monotonic() >= deadline:
            return left
        time.sleep(0.05)

def start_group() -> tuple[int, list[int]]:
    """A real session-led group: bash with two sleeps; returns (pgid, member pids)."""
    proc = subprocess.Popen(["bash", "-c", "sleep 300 & echo $!; sleep 300 & echo $!; wait"],
                            start_new_session=True, stdout=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    groups.append(proc)
    kids = [int(proc.stdout.readline()) for _ in range(2)]
    return proc.pid, [proc.pid] + kids

def cleanup() -> None:
    for proc in groups:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
    import shutil
    shutil.rmtree(SCRATCH, ignore_errors=True)

def run_twine(*args: str, env_extra: dict | None = None, timeout: float = 120):
    env = dict(BASE_ENV, **(env_extra or {}))
    cp = subprocess.run(TWINE + list(args), env=env, cwd=str(ROOT),
                        stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    return cp.returncode, cp.stdout.decode("utf-8", "replace"), cp.stderr.decode("utf-8", "replace")

def one_json_line(stdout: str):
    lines = stdout.splitlines()
    if len(lines) != 1 or not stdout.endswith("\n"):
        return None
    try:
        obj = json.loads(lines[0])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None

def expect_keys(obj, want: dict, problems: list[str], prefix: str = "") -> None:
    """Each key of `want` must be present in `obj` and equal; absent is a
    named failure, never an exception (a missing key is the work's, not ours)."""
    if not isinstance(obj, dict):
        problems.append(f"{prefix or 'payload'} is not a JSON object: {obj!r}")
        return
    for key, value in want.items():
        if key not in obj:
            problems.append(f"{prefix}{key}: missing")
        elif obj[key] != value:
            problems.append(f"{prefix}{key}: {obj[key]!r}, expected {value!r}")

def make_state(name: str) -> Path:
    d = SCRATCH / name
    d.mkdir(parents=True)
    return d

def write_record(state: Path, body: dict) -> Path:
    (state / "running").mkdir(exist_ok=True)
    p = state / "running" / f"{SID}.json"
    p.write_text(json.dumps(body) + "\n", encoding="ascii")
    return p

def record(pgid: int, extra_groups: list[int] | None, with_groups: bool = True) -> dict:
    body = {"sid": SID, "pgid": pgid, "pid": pgid,
            "started_at": "2026-10-05T00:00:00Z", "leader_start_ticks": None}
    if with_groups:
        body["groups"] = [{"pgid": g, "leader_start_ticks": None,
                           "registered_at": "2026-10-05T00:00:01Z"}
                          for g in (extra_groups or [])]
    return body

def pin() -> str:
    data = tomllib.loads((ROOT / "share" / "bale-consumption.toml").read_text("utf-8"))
    return data["bale"]["pin"]

def stub_bale(name: str, version: str) -> tuple[Path, Path]:
    """A stub install root: bin/VERSION at `version`, bin/bale a bash script
    that records its argv and answers `unlock` with the double (nine keys of
    format_unlock_json's contract), anything else with a refusal."""
    root = SCRATCH / name
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "VERSION").write_text(version + "\n")
    rec = root / "argv.log"
    double = {"outcome": "unlocked", "sid": SID, "log": f"/stub/.bale/logs/{SID}.log",
              "closure_reason": "aborted", "session_dir_wiped": True,
              "branch_preserved": False, "telemetry": f"claude/telemetry/{SID}.json",
              "debris": None, "sweep": None}
    line = root / "unlock.json"
    line.write_text(json.dumps(double) + "\n", encoding="ascii")
    script = f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> {str(rec)!r}
if [ "${{1:-}}" = unlock ]; then cat {str(line)!r}; exit 0; fi
echo "[bale] error: stub bale: unexpected verb ${{1:-}}" >&2; exit 1
"""
    (root / "bin" / "bale").write_text(script)
    (root / "bin" / "bale").chmod(0o755)
    return root, rec

SCRATCH.mkdir(parents=True)
REPO = SCRATCH / "repo"; REPO.mkdir()

# --- control: the detectors detect (a failing control is exit 2) -----------
def control() -> None:
    probs: list[str] = []
    expect_keys({"a": 1, "b": None}, {"a": 2, "b": None, "c": 3}, probs)
    if sorted(probs) != sorted(["a: 1, expected 2", "c: missing"]):
        raise RuntimeError(f"expect_keys control: {probs}")
    if one_json_line("not json\n") is not None or one_json_line('{"a":1}\n{"b":2}\n') is not None:
        raise RuntimeError("one_json_line control: accepted a non-line")
    if one_json_line('{"a": 1}\n') != {"a": 1}:
        raise RuntimeError("one_json_line control: refused a line")
    pgid, pids = start_group()
    if not all(alive(p) for p in pids) or members(pgid) != sorted(pids):
        raise RuntimeError(f"liveness control: a fresh group is not seen alive: {pids} vs {members(pgid)}")
    os.killpg(pgid, signal.SIGKILL)
    if wait_gone(pids, 5.0):
        raise RuntimeError("liveness control: a SIGKILLed group is still seen alive after 5s")
    # the prose normalizer folds wraps and bold markers
    if " ".join("a **b\n   c** d".replace("**", "").split()) != "a b c d":
        raise RuntimeError("normalizer control: wrapped bold text is not folded")
    # exit codes are read: a known failing command is not 0
    code, _, _ = run_twine("no-such-verb-for-the-control", "--json")
    if code == 0:
        raise RuntimeError("exit-code control: an unknown verb exited 0")
    print("[checkpoint] control: detectors work (JSON, keys, liveness, exit codes)")
control()

# --- probe: VERSION ---------------------------------------------------------
def probe_version() -> None:
    probs: list[str] = []
    text = (ROOT / "VERSION").read_text("utf-8")
    if text != "0.7.0\n":
        probs.append(f"VERSION is {text!r}, expected '0.7.0\\n'")
    code, out, _ = run_twine("--version")
    if (code, out) != (0, "twine 0.7.0\n"):
        probs.append(f"twine --version: exit {code}, stdout {out!r}")
    result("version-0.7.0", probs)
probe_version()

# --- probe: twine status reports where state lives --------------------------
def probe_status() -> None:
    probs: list[str] = []
    # (a) resolved from $TWINE_STATE_DIR, with spend.jsonl and abort/ present
    state = make_state("status-state")
    (state / "spend.jsonl").write_text("")
    (state / "abort").mkdir()
    code, out, err = run_twine("status", "--json", env_extra={"TWINE_STATE_DIR": str(state)})
    obj = one_json_line(out)
    if code != 0 or obj is None:
        probs.append(f"(a) status --json with TWINE_STATE_DIR: exit {code}, stdout {out[:200]!r}")
    else:
        expect_keys(obj, {"ok": True, "state_dir_source": "TWINE_STATE_DIR",
                          "state_dir_reason": None, "state_dir_exists": True,
                          "state_present": {"spend_jsonl": True, "prices_toml": False,
                                            "abort": True, "running": False}},
                    probs, "(a) ")
        sd = obj.get("state_dir")
        if not isinstance(sd, str) or Path(sd).resolve() != state.resolve():
            probs.append(f"(a) state_dir: {sd!r}, expected {str(state)!r}")
    # (b) none resolves: no flag, no $TWINE_STATE_DIR, no $XDG_STATE_HOME, no $HOME — still ok
    code, out, err = run_twine("status", "--json")
    obj = one_json_line(out)
    if code != 0 or obj is None:
        probs.append(f"(b) status --json with no state directory resolvable: exit {code}, stdout {out[:200]!r}")
    else:
        expect_keys(obj, {"ok": True, "state_dir": None, "state_dir_source": None,
                          "state_dir_exists": None, "state_present": None}, probs, "(b) ")
        if not (isinstance(obj.get("state_dir_reason"), str) and obj.get("state_dir_reason")):
            probs.append(f"(b) state_dir_reason: {obj.get('state_dir_reason')!r}, expected a non-empty reason")
    # (c) --state-dir naming a directory that does not exist: reported, not created, still ok
    missing = SCRATCH / "status-missing-dir"
    code, out, err = run_twine("status", "--state-dir", str(missing), "--json")
    obj = one_json_line(out)
    if code != 0 or obj is None:
        probs.append(f"(c) status --state-dir <missing> --json: exit {code}, stdout {out[:200]!r}")
    else:
        expect_keys(obj, {"ok": True, "state_dir_source": "--state-dir", "state_dir_reason": None,
                          "state_dir_exists": False,
                          "state_present": {"spend_jsonl": False, "prices_toml": False,
                                            "abort": False, "running": False}}, probs, "(c) ")
        sd = obj.get("state_dir")
        if not isinstance(sd, str) or Path(sd).resolve() != missing.resolve():
            probs.append(f"(c) state_dir: {sd!r}, expected {str(missing)!r}")
    if missing.exists():
        probs.append("(c) status created the state directory it was asked about")
    # (d) human mode still exits 0 and names the state directory
    code, out, err = run_twine("status", env_extra={"TWINE_STATE_DIR": str(state)})
    if code != 0 or str(state) not in out:
        probs.append(f"(d) human status: exit {code}; the state directory path is {'' if str(state) in out else 'not '}in stdout")
    result("status-state-dir-keys", probs)
probe_status()

# --- probe: an unpinned or absent bale gates only the closure ---------------
def probe_pin_gate_closure_only() -> None:
    probs: list[str] = []
    cases = [("unpinned", stub_bale("bale-unpinned", "0.0.1")[0]),
             ("absent", SCRATCH / "bale-absent")]
    (SCRATCH / "bale-absent").mkdir()
    for label, root in cases:
        state = make_state(f"pin-{label}")
        pgid, pids = start_group()
        write_record(state, record(pgid, []))
        code, out, err = run_twine("kill", SID, "--state-dir", str(state), "--cwd", str(REPO),
                                   "--bale-root", str(root), "--grace", "1", "--json")
        obj = one_json_line(out)
        if obj is None:
            probs.append(f"[{label}] kill --json: not one JSON line (exit {code}): {out[:200]!r}")
            continue
        if code != 1:
            probs.append(f"[{label}] exit {code}, expected 1 (not ok: the closure needs the pin)")
        expect_keys(obj, {"ok": False, "abort_requested": True, "closed": False,
                          "stopped_at": "closure", "refusals": [], "operator_line": UNLOCK_LINE},
                    probs, f"[{label}] ")
        if not (state / "abort" / f"{SID}.json").is_file():
            probs.append(f"[{label}] the abort request was not written")
        left = wait_gone(pids, 10.0)
        if left:
            probs.append(f"[{label}] the recorded group was not killed; alive: {left}")
        proc = obj.get("process")
        if not isinstance(proc, dict) or proc.get("dead") is not True:
            probs.append(f"[{label}] process.dead: {None if not isinstance(proc, dict) else proc.get('dead')!r}, expected True")
        if (state / "running" / f"{SID}.json").exists() and not left:
            probs.append(f"[{label}] the running record was not removed although the group is gone")
        if label == "unpinned" and (cases[0][1] / "argv.log").exists():
            probs.append("[unpinned] the unpinned bale was run")
        reason = obj.get("reason")
        if not (isinstance(reason, str) and reason):
            probs.append(f"[{label}] reason: {reason!r}, expected the drive refusal named")
    result("kill-unpinned-bale-still-aborts-and-kills-stops-at-closure", probs)
probe_pin_gate_closure_only()

# --- probe: every recorded group is signalled and waited for ----------------
def probe_every_group() -> None:
    probs: list[str] = []
    root, rec = stub_bale("bale-pinned", pin())
    state = make_state("groups")
    pg0, pids0 = start_group()
    pg1, pids1 = start_group()
    pg2, pids2 = start_group()
    write_record(state, record(pg0, [pg1, pg2]))
    code, out, err = run_twine("kill", SID, "--state-dir", str(state), "--cwd", str(REPO),
                               "--bale-root", str(root), "--grace", "1", "--json")
    obj = one_json_line(out)
    if obj is None:
        probs.append(f"kill --json: not one JSON line (exit {code}): {out[:200]!r}")
    else:
        if code != 0:
            probs.append(f"exit {code}, expected 0; reason: {obj.get('reason')!r}")
        expect_keys(obj, {"ok": True, "abort_requested": True, "closed": True,
                          "stopped_at": None, "operator_line": None, "refusals": []}, probs)
        proc = obj.get("process")
        if not isinstance(proc, dict):
            probs.append(f"process: {proc!r}, expected an object")
        else:
            expect_keys(proc, {"pgid": pg0, "dead": True, "survivors": [], "record_cleared": True},
                        probs, "process.")
            gs = proc.get("groups")
            if not isinstance(gs, list) or [g.get("pgid") if isinstance(g, dict) else g for g in gs] != [pg1, pg2]:
                probs.append(f"process.groups: {gs!r}, expected two objects with pgid {pg1} then {pg2}")
            else:
                for g in gs:
                    expect_keys(g, {"dead": True, "survivors": []}, probs, f"process.groups[{g.get('pgid')}].")
                    for k in ("signalled", "signals", "stale"):
                        if k not in g:
                            probs.append(f"process.groups[{g.get('pgid')}].{k}: missing")
    left = wait_gone(pids0 + pids1 + pids2, 10.0)
    if left:
        probs.append(f"members still alive after the kill reported: {left} (groups {pg0}, {pg1}, {pg2})")
    if (state / "running" / f"{SID}.json").exists():
        probs.append("the running record was not removed")
    if not (state / "abort" / f"{SID}.json").is_file():
        probs.append("the abort request was not written")
    calls = rec.read_text().splitlines() if rec.exists() else []
    if calls != [f"unlock {SID} --reason aborted --json"]:
        probs.append(f"the stub bale saw {calls!r}, expected exactly ['unlock {SID} --reason aborted --json']")
    result("kill-every-recorded-group", probs)
probe_every_group()

# --- probe: a record without `groups` is malformed, nothing is signalled ----
def probe_record_without_groups() -> None:
    probs: list[str] = []
    root, rec = stub_bale("bale-pinned-2", pin())
    state = make_state("no-groups-key")
    pgid, pids = start_group()
    path = write_record(state, record(pgid, None, with_groups=False))
    code, out, err = run_twine("kill", SID, "--state-dir", str(state), "--cwd", str(REPO),
                               "--bale-root", str(root), "--grace", "1", "--json")
    obj = one_json_line(out)
    if obj is None:
        probs.append(f"kill --json: not one JSON line (exit {code}): {out[:200]!r}")
    else:
        if code != 1:
            probs.append(f"exit {code}, expected 1")
        expect_keys(obj, {"ok": False, "abort_requested": True, "closed": False,
                          "stopped_at": "process", "operator_line": None, "refusals": []}, probs)
        proc = obj.get("process")
        if not isinstance(proc, dict) or not proc.get("error"):
            probs.append("process.error: expected the malformed record named")
    time.sleep(0.5)
    if not all(alive(p) for p in pids):
        probs.append("the group was signalled although the record named no group to trust")
    if not path.exists():
        probs.append("the malformed record was removed; it is left for the operator")
    if rec.exists():
        probs.append(f"bale was reached: {rec.read_text().splitlines()!r}")
    os.killpg(pgid, signal.SIGKILL)
    result("kill-record-without-groups-is-malformed", probs)
probe_record_without_groups()

# --- probe: the consumption manifest wants a JSON unlock refusal ------------
def probe_wanted() -> None:
    probs: list[str] = []
    data = tomllib.loads((ROOT / "share" / "bale-consumption.toml").read_text("utf-8"))
    wanted = [w for w in data.get("wanted", []) if w.get("verb") == "unlock"]
    if not wanted:
        probs.append("no [[wanted]] entry with verb = \"unlock\"")
    else:
        w = wanted[0]
        if "--json" not in w.get("flags", []):
            probs.append(f"wanted unlock flags: {w.get('flags')!r}, expected to contain '--json'")
        for key in ("needed_by", "status"):
            if not (isinstance(w.get(key), str) and w.get(key).strip()):
                probs.append(f"wanted unlock {key}: empty or missing")
        if "2026-10-04-twine-kill-switch-002" not in w.get("needed_by", ""):
            probs.append("wanted unlock needed_by does not name session 2026-10-04-twine-kill-switch-002")
    # the three existing kinds of entry still parse and the pin is unchanged
    if data.get("bale", {}).get("pin") != "0.4.45":
        probs.append(f"the pin moved: {data.get('bale', {}).get('pin')!r}")
    result("wanted-unlock-json-refusal", probs)
probe_wanted()

# --- probe: the contract no longer says the pin is checked before the abort --
def probe_contract() -> None:
    probs: list[str] = []
    # Markdown prose wraps, so compare with every run of whitespace (newlines
    # included) folded to one space; the markers around the bold text are
    # dropped too, so the sentence is found however it is emphasized or wrapped.
    raw = (ROOT / "claude" / "context" / "cli-contract.md").read_text("utf-8")
    text = " ".join(raw.replace("**", "").split())
    gone = "The pin is checked before the abort is requested"
    if gone in text:
        probs.append(f"cli-contract.md still carries {gone!r}")
    gone2 = "`dead` means the recorded group is gone, not every process the session started"
    if gone2 in text:
        probs.append(f"cli-contract.md still carries {gone2!r}")
    result("contract-pin-and-one-group-sentences-gone", probs)
probe_contract()

# --- invariant: the suite is green --------------------------------------------
def probe_suite() -> None:
    probs: list[str] = []
    cp = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                        cwd=str(ROOT), env=dict(BASE_ENV, HOME=str(SCRATCH / "home")),
                        stdin=subprocess.DEVNULL, capture_output=True, timeout=900)
    if cp.returncode != 0:
        tail = cp.stderr.decode("utf-8", "replace").strip().splitlines()[-25:]
        probs.append("unittest exit %d; last lines:\n         " % cp.returncode + "\n         ".join(tail))
    result("suite", probs)
probe_suite()

cleanup()
if failures:
    print(f"[checkpoint] {len(failures)} probe(s) failed: {', '.join(failures)}")
    sys.exit(1)
print("[checkpoint] all probes passed")
sys.exit(0)
PY
code=$?
rm -rf "$SCRATCH"
exit $code

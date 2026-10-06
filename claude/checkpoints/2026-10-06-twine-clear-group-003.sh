#!/usr/bin/env bash
# Blind checkpoint, v1 — twine-src session `twine-clear-group` (slug), authored
# at sitting 2026-10-06-continue-twine-002 from the brief, before any
# implementation exists. Outcome contracts only (PLANNER.md §4): what must be
# true of the applied tree, never how the worker got there.
#
# Runs in the staging tree's root (cwd). Exit 0: every probe passed. Exit 1:
# at least one probe failed, by name. Exit 2: the oracle itself is broken — a
# control did not fire, or an unexpected exception — never a verdict on the
# work (TARBALL.md §7.5).
#
# Writes: one temporary directory (tempfile.mkdtemp under $TMPDIR, announced,
# removed at exit) for state directories and real process groups the probes
# start themselves; the kill and process test modules write only their own
# temporary directories. Nothing under the tree. Every Python runs with -B.
set -u
exec python3 -I -B - "$@" <<'PY'
import hashlib, inspect, json, os, shutil, signal, subprocess, sys, tempfile, threading, time
from pathlib import Path

# ---------------------------------------------------------------------------
# 0. Harness: the oracle's own failures exit 2, never 1
# ---------------------------------------------------------------------------

def _excepthook(kind, value, tb):
    import traceback
    print("[ORACLE ERROR] the checkpoint itself raised; exit 2 (not a verdict):", file=sys.stderr)
    traceback.print_exception(kind, value, tb)
    sys.stdout.flush()
    os._exit(2)

sys.excepthook = _excepthook

TREE = Path.cwd()
for needed in ("bin/twine", "twine/kill.py", "twine/process.py",
               "claude/context/cli-contract.md", "VERSION"):
    if not (TREE / needed).exists():
        print(f"[ORACLE ERROR] {needed} is not under the cwd {TREE}; the checkpoint "
              "must run in the staging tree's root; exit 2", file=sys.stderr)
        sys.exit(2)

SCRATCH = Path(tempfile.mkdtemp(prefix="twine-clear-group-checkpoint-"))
print(f"[checkpoint] writes: {SCRATCH} (temporary, removed at exit) and the test "
      "modules' own temporary directories; nothing under the tree")

SID = "checkpoint-clear-group-001"   # any sid; the dry-run has no session yet
RUNTIME, GROUP_A, GROUP_B = 40001, 40002, 40003   # fake ids: registered, never signalled
SIX_KEYS = ("sid", "pgid", "pid", "started_at", "leader_start_ticks", "groups")
ENTRY_KEYS = ("pgid", "leader_start_ticks", "registered_at")

# The bytes the brief pins untouched (§6), verified at the desk on the shipped tree.
UNTOUCHED = {
    "twine-seed.md": "a814746039e5106e12d4aece1edc0bcaa79d2b7194b8a5d3417e3f2fe948ab38",
    "bale.toml": "b09e9b065594c48b2eb6c1754dd19a0700a5415b14b67ac80d629294b03cfbff",
    "share/transitions.toml": "b98ecd04bc0beeea08eab9e1ba4b47d3ea3d12e9e9fc8aa10fd37e66f42a2610",
    "share/bale-consumption.toml": "25365e193cc74598b5dadb0dbca0ec697367622afcffd372f72def2a8f5203dc",
    "bin/twine": "d5388349e4559df3f93f74a48f4740a512466a1224f84c98f655f3f3b4d4669e",
}
SIGNATURE_LINE = "clear_group(state_dir: Path, sid: str, pgid: int) -> bool"

sys.path.insert(0, str(TREE))
from twine import kill  # noqa: E402  (the shipped module; clear_group may be absent)

results: list[tuple[str, list[str]]] = []
started_groups: list[subprocess.Popen] = []


def probe(label, failures):
    results.append((label, list(failures)))
    if failures:
        print(f"[FAIL] {label}: " + "; ".join(failures))
    else:
        print(f"[PASS] {label}")


def control(label, failures):
    """A detector fed a known-bad observation must fail; if it does not, the
    oracle is broken: exit 2 (PLANNER.md §4)."""
    if not failures:
        print(f"[ORACLE ERROR] control {label!r} did not fire; exit 2", file=sys.stderr)
        cleanup()
        os._exit(2)
    print(f"[CONTROL] {label}: fires")


def cleanup():
    for proc in started_groups:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
    shutil.rmtree(SCRATCH, ignore_errors=True)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fresh_state(name):
    d = SCRATCH / name
    d.mkdir()
    return d


def record_bytes(state, sid=SID):
    p = Path(state) / "running" / f"{sid}.json"
    return p.read_bytes() if p.exists() else None


def have_clear():
    return callable(getattr(kill, "clear_group", None))


def call_clear(state, sid, pgid):
    """Call clear_group and report (outcome, value): outcome is 'returned',
    or the raised exception's class name. Missing function → ('absent', None)."""
    if not have_clear():
        return "absent", None
    try:
        return "returned", kill.clear_group(state, sid, pgid)
    except Exception as exc:  # the probes decide what is a refusal
        return type(exc).__name__, exc


# ---------------------------------------------------------------------------
# 1. Detectors — pure functions of observations
# ---------------------------------------------------------------------------

def det_callable(module):
    fn = getattr(module, "clear_group", None)
    if fn is None:
        return ["twine.kill has no clear_group"]
    if not callable(fn):
        return ["twine.kill.clear_group is not callable"]
    try:
        inspect.signature(fn).bind(Path("/x"), "sid", 2)
    except TypeError as exc:
        return [f"clear_group does not take (state_dir, sid, pgid) positionally: {exc}"]
    return []


def det_record(outcome, value, raw, expected_groups, sid=SID, runtime=RUNTIME):
    """After a clear that must remove: True returned, the file one JSON object
    with exactly the six keys, the runtime's values intact, groups exactly
    expected_groups (pgids, in order), each entry exactly three keys."""
    f = []
    if outcome != "returned":
        f.append(f"clear_group did not return: {outcome}")
    elif value is not True:
        f.append(f"clear_group returned {value!r}, not True")
    if raw is None:
        f.append("the running record is gone")
        return f
    try:
        obj = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        return f + [f"the record is not JSON: {exc}"]
    if not isinstance(obj, dict) or tuple(obj.keys()) != SIX_KEYS:
        f.append(f"the record's keys are {list(obj) if isinstance(obj, dict) else type(obj).__name__}, "
                 f"not exactly {list(SIX_KEYS)}")
        return f
    if obj["sid"] != sid or obj["pgid"] != runtime or obj["pid"] != runtime:
        f.append("the runtime's sid/pgid/pid changed")
    groups = obj["groups"]
    if not isinstance(groups, list):
        return f + ["groups is not an array"]
    for i, e in enumerate(groups):
        if not isinstance(e, dict) or tuple(e.keys()) != ENTRY_KEYS:
            f.append(f"groups[{i}] keys are not exactly {list(ENTRY_KEYS)}")
    got = [e.get("pgid") for e in groups if isinstance(e, dict)]
    if got != list(expected_groups):
        f.append(f"groups names {got}, expected {list(expected_groups)}")
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        f.append("the record is not one line ending in a newline")
    return f


def det_unchanged(outcome, value, expected_value, before, after):
    """A clear that must not write: the expected return, bytes identical."""
    f = []
    if outcome != "returned":
        f.append(f"clear_group did not return: {outcome}")
    elif value is not expected_value:
        f.append(f"clear_group returned {value!r}, not {expected_value!r}")
    if before != after:
        f.append("the record's bytes changed")
    return f


def det_nothing_created(outcome, value, running_dir_exists):
    f = []
    if outcome != "returned":
        f.append(f"clear_group did not return: {outcome}")
    elif value is not False:
        f.append(f"clear_group returned {value!r}, not False")
    if running_dir_exists:
        f.append("a running/ directory was created where there was none")
    return f


def det_refused(outcome, before, after):
    f = []
    if outcome != "RunningRecordError":
        f.append(f"expected RunningRecordError, got {outcome}")
    if before != after:
        f.append("the record's bytes changed on a refusal")
    return f


def det_concurrent(final_pgids, standing):
    if final_pgids != list(standing):
        return [f"after concurrent registrations and clears the record names {final_pgids}, "
                f"expected exactly {list(standing)}"]
    return []


def det_kill_twin(stdout, runtime_pgid, kept_pgid, cleared_alive, others_dead):
    """twine kill after a clear: one JSON line; process.pgid the runtime's;
    process.groups exactly the kept group; the cleared group's process alive
    afterwards; every other recorded group dead."""
    f = []
    lines = [l for l in stdout.decode("utf-8", "replace").splitlines() if l.strip()]
    if len(lines) != 1:
        return [f"twine kill --json printed {len(lines)} non-empty lines, not one"]
    try:
        twin = json.loads(lines[0])
    except ValueError as exc:
        return [f"twine kill's line is not JSON: {exc}"]
    proc = twin.get("process")
    if not isinstance(proc, dict):
        return [f"process is {proc!r}, not an object"]
    if proc.get("pgid") != runtime_pgid:
        f.append(f"process.pgid is {proc.get('pgid')}, not the runtime's {runtime_pgid}")
    got = [g.get("pgid") for g in proc.get("groups", []) if isinstance(g, dict)]
    if got != [kept_pgid]:
        f.append(f"process.groups names {got}, expected exactly [{kept_pgid}]")
    if proc.get("dead") is not True:
        f.append("process.dead is not true")
    if proc.get("record_cleared") is not True:
        f.append("the record was not cleared by the kill")
    if twin.get("stopped_at") != "closure":
        f.append(f"stopped_at is {twin.get('stopped_at')!r}, expected 'closure' (no bale)")
    if not cleared_alive:
        f.append("the cleared group was signalled: its process is not alive after the kill")
    if not others_dead:
        f.append("a recorded group is still alive after the kill")
    return f


def det_contract(text):
    f = []
    head = text.find("\n### 14.8 ")
    if head < 0:
        return ["cli-contract.md has no '### 14.8' heading"]
    tail = text.find("\n## ", head + 1)
    block_14_8 = text[head: tail if tail > 0 else len(text)]
    if not any(l.strip().startswith(SIGNATURE_LINE) for l in block_14_8.splitlines()):
        f.append(f"§14.8 has no line beginning {SIGNATURE_LINE!r}")
    h4 = text.find("\n### 14.4 ")
    h5 = text.find("\n### 14.5 ", h4 + 1)
    if h4 < 0 or h5 < 0:
        return f + ["cli-contract.md lacks the §14.4/§14.5 headings"]
    if "clear_group" not in text[h4:h5]:
        f.append("§14.4 does not mention clear_group")
    return f


def det_version(raw):
    return [] if raw == b"0.7.1\n" else [f"VERSION is {raw!r}, not b'0.7.1\\n'"]


def det_hashes(observed, expected=UNTOUCHED):
    return [f"{p} changed (sha256 {observed.get(p)})" for p in expected
            if observed.get(p) != expected[p]]


def det_suite(exit_code, tail):
    return [] if exit_code == 0 else [f"the kill/process test modules exited {exit_code}: {tail}"]


# ---------------------------------------------------------------------------
# 2. Controls — every detector fed an observation that must fail
# ---------------------------------------------------------------------------

class _Empty:
    pass

control("callable", det_callable(_Empty()))
_good = json.dumps({"sid": SID, "pgid": RUNTIME, "pid": RUNTIME, "started_at": "t",
                    "leader_start_ticks": None,
                    "groups": [{"pgid": GROUP_B, "leader_start_ticks": None,
                                "registered_at": "t"}]}).encode() + b"\n"
control("record (not removed)", det_record("returned", True, _good, [GROUP_A]))
control("record (five keys)", det_record("returned", True, b'{"sid": "x"}\n', []))
control("unchanged", det_unchanged("returned", False, False, b"a\n", b"b\n"))
control("nothing created", det_nothing_created("returned", False, True))
control("refused", det_refused("returned", b"a\n", b"a\n"))
control("concurrent", det_concurrent([1, 2], [1, 2, 3]))
control("kill twin", det_kill_twin(b'{"process": {"pgid": 1, "groups": []}, "stopped_at": "closure"}\n',
                                   1, 2, True, True))
control("contract", det_contract("\n### 14.4 x\n\n### 14.5 y\n\n### 14.8 z\nnothing\n"))
control("version", det_version(b"0.7.0\n"))
control("hashes", det_hashes({p: "0" * 64 for p in UNTOUCHED}))
control("suite", det_suite(1, "boom"))

# ---------------------------------------------------------------------------
# 3. Probes
# ---------------------------------------------------------------------------

probe("clear-group-callable", det_callable(kill))


def registered_state(name, groups=(GROUP_A, GROUP_B)):
    state = fresh_state(name)
    kill.register_running(state, SID, RUNTIME, RUNTIME)
    for g in groups:
        kill.register_group(state, SID, g)
    return state


# removes one entry, the rest intact, six keys, three keys per entry
state = registered_state("remove")
outcome, value = call_clear(state, SID, GROUP_A)
probe("clear-group-removes-entry", det_record(outcome, value, record_bytes(state), [GROUP_B]))

# False, bytes unchanged, when no entry names the pgid
state = registered_state("absent")
before = record_bytes(state)
outcome, value = call_clear(state, SID, 40009)
probe("clear-group-absent-group-is-false",
      det_unchanged(outcome, value, False, before, record_bytes(state)))

# False and nothing created when there is no record at all
state = fresh_state("no-record")
outcome, value = call_clear(state, SID, GROUP_A)
probe("clear-group-no-record-is-false",
      det_nothing_created(outcome, value, (state / "running").exists()))

# refused: the runtime's own group
state = registered_state("own")
before = record_bytes(state)
outcome, _ = call_clear(state, SID, RUNTIME)
probe("clear-group-own-group-refused", det_refused(outcome, before, record_bytes(state)))

# refused: a pgid that could not be a group (0, 1, a bool)
state = registered_state("bad-id")
before = record_bytes(state)
bad = [call_clear(state, SID, v)[0] for v in (0, 1, True)]
probe("clear-group-bad-pgid-refused",
      sum((det_refused(o, before, record_bytes(state)) for o in bad), []))

# refused: a malformed record (five-key format), left untouched
state = fresh_state("malformed")
(state / "running").mkdir()
malformed = json.dumps({"sid": SID, "pgid": RUNTIME, "pid": RUNTIME,
                        "started_at": "2026-10-06T00:00:00Z",
                        "leader_start_ticks": None}).encode() + b"\n"
(state / "running" / f"{SID}.json").write_bytes(malformed)
outcome, _ = call_clear(state, SID, GROUP_A)
probe("clear-group-malformed-record-refused", det_refused(outcome, malformed, record_bytes(state)))

# a pgid the record names twice is forgotten whole (record written by hand in the
# six-key format of contract §14.4, as the brief pins it)
state = fresh_state("duplicate")
(state / "running").mkdir()
entry = lambda pgid: {"pgid": pgid, "leader_start_ticks": None,
                      "registered_at": "2026-10-06T00:00:00Z"}
doubled = json.dumps({"sid": SID, "pgid": RUNTIME, "pid": RUNTIME,
                      "started_at": "2026-10-06T00:00:00Z", "leader_start_ticks": None,
                      "groups": [entry(40005), entry(GROUP_B), entry(40005)]}).encode() + b"\n"
(state / "running" / f"{SID}.json").write_bytes(doubled)
outcome, value = call_clear(state, SID, 40005)
probe("clear-group-duplicate-forgotten-whole",
      det_record(outcome, value, record_bytes(state), [GROUP_B]))

# concurrent registrations and clears lose nothing of each other
state = fresh_state("concurrent")
standing = [41001, 41002, 41003, 41004]
kill.register_running(state, SID, RUNTIME, RUNTIME)
for g in standing:
    kill.register_group(state, SID, g)
errors: list[str] = []


def churn(pgid):
    try:
        kill.register_group(state, SID, pgid)
        if have_clear():
            kill.clear_group(state, SID, pgid)
    except Exception as exc:
        errors.append(f"{pgid}: {type(exc).__name__}: {exc}")


threads = [threading.Thread(target=churn, args=(42000 + i,)) for i in range(16)]
for t in threads:
    t.start()
for t in threads:
    t.join()
final = kill.read_running(state, SID)
probe("clear-group-concurrent-churn",
      det_concurrent([] if final is None else [g.pgid for g in final.groups], standing)
      + ([f"a thread raised: {errors[0]}"] if errors else []))

# twine kill after a clear reaches only what the record still names (real groups)
state = fresh_state("kill")
if have_clear():
    procs = [subprocess.Popen(["sleep", "300"], start_new_session=True,
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL) for _ in range(3)]
    started_groups.extend(procs)
    runtime_p, cleared_p, kept_p = procs
    kill.register_running(state, SID, runtime_p.pid, runtime_p.pid)
    kill.register_group(state, SID, cleared_p.pid)
    kill.register_group(state, SID, kept_p.pid)
    kill.clear_group(state, SID, cleared_p.pid)
    run = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(TREE / "bin" / "twine"), "kill", SID,
         "--state-dir", str(state), "--bale-root", str(SCRATCH / "no-bale-here"),
         "--grace", "1", "--json"],
        cwd=str(TREE), env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        stdin=subprocess.DEVNULL, capture_output=True, timeout=120)

    def alive(p):
        return p.poll() is None

    time.sleep(0.2)
    cleared_alive = alive(cleared_p)
    others_dead = not alive(runtime_p) and not alive(kept_p)
    probe("kill-after-clear-reaches-only-recorded-groups",
          det_kill_twin(run.stdout, runtime_p.pid, kept_p.pid, cleared_alive, others_dead))
else:
    probe("kill-after-clear-reaches-only-recorded-groups",
          ["twine.kill has no clear_group; the kill was not run"])

probe("contract-14-4-and-14-8-name-clear-group",
      det_contract((TREE / "claude/context/cli-contract.md").read_text(encoding="utf-8")))
probe("version-is-0.7.1", det_version((TREE / "VERSION").read_bytes()))
probe("untouched-files-by-hash", det_hashes({p: sha256(TREE / p) for p in UNTOUCHED}))

suite = subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_kill", "tests.test_process"],
                       cwd=str(TREE), stdin=subprocess.DEVNULL, capture_output=True, timeout=600)
probe("kill-and-process-suites-green",
      det_suite(suite.returncode, suite.stderr.decode("utf-8", "replace").strip()[-400:]))

# ---------------------------------------------------------------------------
# 4. Verdict
# ---------------------------------------------------------------------------

cleanup()
failed = [label for label, f in results if f]
print(f"[checkpoint] {len(results)} probes, {len(failed)} failed"
      + (": " + ", ".join(failed) if failed else ""))
sys.exit(1 if failed else 0)
PY

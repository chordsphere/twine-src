#!/usr/bin/env bash
# Blind checkpoint, v1 — twine-src session `twine-kill-reason` (slug), authored
# by the twine desk on 2026-10-07 from the brief, before the landing exists.
# Outcome contracts only: the hand line keys on the recorded `reason` code
# (the HOLD line with empty stderr hands back `bale revert`; a non-HOLD line
# with the old stderr text does not), the code is named, the twin's keys are
# unchanged, no text-match constant, the tests replay no derived stderr, the
# stale sentences are gone, VERSION, the untouched set, the suite.
#
# Runs in the staging tree's root (cwd). Exit 0 / 1 / 2: passed / a probe
# failed by name / the oracle is broken. Writes: one temporary directory for
# the stub bale roots and kill state (announced, removed at exit) and the
# suite's own temporary directories. Nothing under the tree. Python -I -B.
set -u
exec python3 -I -B - "$@" <<'PY'
import hashlib, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path


def _excepthook(kind, value, tb):
    import traceback
    print("[ORACLE ERROR] the checkpoint itself raised; exit 2 (not a verdict):", file=sys.stderr)
    traceback.print_exception(kind, value, tb)
    sys.stdout.flush()
    cleanup()
    os._exit(2)


sys.excepthook = _excepthook
TREE = Path.cwd()
HOLD_FIXTURE = "fixtures/bale-0.4.49/scratch/unlock_sid_--json+unlock-refused+hold-branch.json"
NOT_OPEN_FIXTURE = "fixtures/bale-0.4.49/twine-src/unlock_sid_--json+unlock-refused+not-open.json"
for needed in ("bin/twine", "twine/kill.py", "tests/helpers.py", "tests/test_kill.py", "VERSION",
               "claude/context/cli-contract.md", "fixtures/README.md", "share/bale-consumption.toml",
               HOLD_FIXTURE, NOT_OPEN_FIXTURE):
    if not (TREE / needed).exists():
        print(f"[ORACLE ERROR] {needed} is not under the cwd {TREE}; exit 2", file=sys.stderr)
        sys.exit(2)
SCRATCH = Path(tempfile.mkdtemp(prefix="twine-kill-reason-checkpoint-"))
print(f"[checkpoint] writes: {SCRATCH} (temporary, removed at exit) and the suite's own temporary "
      "directories; nothing under the tree")

SID = "2026-10-07-sc-002"
VERSION = b"0.8.1\n"
TWIN_KEYS = ["command", "ok", "sid", "abort_requested", "process", "closed", "closure", "telemetry",
             "operator_line", "stopped_at", "reason", "refusals", "abort", "argv", "ran", "exit_code",
             "stdout", "stderr", "stderr_truncated", "timed_out", "capped", "duration_seconds",
             "state_dir", "state_dir_source", "cwd", "grace_seconds", "bale"]
UNTOUCHED = {
    "twine-seed.md": "abb55c02c0fb3abdeb2b8b155c6160448ce14330dacabe27b18568aae905d9ed",
    "bin/twine": "d5388349e4559df3f93f74a48f4740a512466a1224f84c98f655f3f3b4d4669e",
    "twine/bale.py": "b3aede25158bea8f84426ea731f7e3c12b5d4a461abb1312faedcd35e360a43e",
    "share/transitions.toml": "707e94f9af6ea82457109c193d71141e774a97f40a90dec6b485ea65acb94f3e",
}
# (file, phrase) that must be gone: each stated the text match or the derivation as the mechanism.
STALE = [
    ("twine/kill.py", "HOLD_BRANCH_REFUSAL"),
    ("twine/kill.py", "keying on it instead of the text is the next session's"),
    ("twine/kill.py", "nothing on stdout, the reason on stderr"),
    ("twine/kill.py", "On a refusal stdout is empty"),
    ("tests/helpers.py", "[bale] error: "),
    ("tests/test_kill.py", "still reads by its prefix"),
    ("tests/test_kill.py", "keying on it is the next session's"),
    ("claude/context/cli-contract.md", "named as a derivation"),
    ("claude/context/cli-contract.md", "its stderr names the branch"),
    ("claude/context/cli-contract.md", "the one stderr text twine reads"),
    ("claude/context/cli-contract.md", "keying the hand line on the code instead of the text is the next session's"),
    ("fixtures/README.md", "the one derivation"),
    ("share/bale-consumption.toml", "keys its one hand-line decision on the stderr prefix"),
    ("share/bale-consumption.toml", "keying on `reason` instead is the next session's"),
]
results = []


def cleanup():
    shutil.rmtree(SCRATCH, ignore_errors=True)


def probe(label, failures):
    results.append((label, list(failures)))
    print((f"[FAIL] {label}: " + "; ".join(failures)) if failures else f"[PASS] {label}")


def control(label, failures):
    if not failures:
        print(f"[ORACLE ERROR] control {label!r} did not fire; exit 2", file=sys.stderr)
        cleanup()
        os._exit(2)
    print(f"[CONTROL] {label}: fires")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fold(text):
    return re.sub(r"\s+", " ", text.replace("*", "").replace("`", ""))


# --- detectors -----------------------------------------------------------------

def det_hold_line_keys(obs):
    """obs: {"json": twin dict or None, "human": stdout text, "exit": code} from
    `twine kill` against a stub printing the recorded HOLD line, exit 1,
    nothing on stderr."""
    f, j = [], obs.get("json")
    if not isinstance(j, dict):
        return ["twine kill --json printed no JSON object"]
    if j.get("operator_line") != f"bale revert {SID}":
        f.append(f"operator_line is {j.get('operator_line')!r}, not 'bale revert {SID}' on the HOLD line with empty stderr")
    if "hold-branch" not in (j.get("reason") or ""):
        f.append("the twin's reason does not name hold-branch")
    if (j.get("ok"), j.get("closed"), j.get("stopped_at"), obs.get("exit")) != (False, False, "closure", 1):
        f.append(f"ok/closed/stopped_at/exit are {(j.get('ok'), j.get('closed'), j.get('stopped_at'), obs.get('exit'))}")
    human = obs.get("human") or ""
    if f"finish by hand: bale revert {SID}" not in human:
        f.append("human mode does not hand back bale revert")
    if "hold-branch" not in human:
        f.append("human mode does not name hold-branch")
    return f


def det_text_no_longer_keys(obs):
    """obs: {"json": twin dict} from a stub printing the recorded NOT-OPEN line, exit 1,
    with the old HOLD text on stderr."""
    f, j = [], obs.get("json")
    if not isinstance(j, dict):
        return ["twine kill --json printed no JSON object"]
    if j.get("operator_line") != f"bale unlock {SID} --reason aborted":
        f.append(f"operator_line is {j.get('operator_line')!r} on a not-open line whose stderr carries the HOLD text")
    if "not-open" not in (j.get("reason") or ""):
        f.append("the twin's reason does not name not-open")
    if "branch bale/" not in (j.get("stderr") or ""):
        f.append("bale's stderr was not reported (it is evidence, not a key)")
    return f


def det_twin_keys(keys):
    return [] if list(keys) == TWIN_KEYS else [f"the twin's keys changed: {list(keys)}"]


def det_no_derived_stderr(hold_stderr, not_open_stderr):
    f = []
    if hold_stderr != b"":
        f.append(f"unlock_recording('hold-branch').stderr is {hold_stderr!r}, not b''")
    if not_open_stderr != b"":
        f.append(f"unlock_recording('not-open').stderr is {not_open_stderr!r}, not b''")
    return f


def det_stale(texts):
    """texts: {path: folded text}."""
    return [f"{p} still says {fold(s)!r}" for p, s in STALE if fold(s) in texts[p]]


def det_untouched(observed):
    return [f"{p} changed" for p, h in UNTOUCHED.items() if observed.get(p) != h]


def det_version(raw):
    return [] if raw == VERSION else [f"VERSION is {raw!r}, not {VERSION!r}"]


def det_suite(code, tail, count):
    f = [] if code == 0 else [f"the suite exited {code}: {tail}"]
    if count is None or count < 449:
        f.append(f"the suite ran {count} tests, fewer than the 449 at 0.8.0")
    return f


# --- controls ------------------------------------------------------------------

control("hold line", det_hold_line_keys({"json": {"operator_line": f"bale unlock {SID} --reason aborted", "reason": "x",
                                                   "ok": False, "closed": False, "stopped_at": "closure"},
                                         "human": "", "exit": 1}))
control("text no longer keys", det_text_no_longer_keys({"json": {"operator_line": f"bale revert {SID}", "reason": "", "stderr": ""}}))
control("twin keys", det_twin_keys(TWIN_KEYS + ["refusal_reason"]))
control("derived stderr", det_no_derived_stderr(b"[bale] error: x\n", b""))
control("stale", det_stale({p: fold(s) for p, s in STALE}))
control("untouched", det_untouched({p: "0" * 64 for p in UNTOUCHED}))
control("version", det_version(b"0.8.0\n"))
control("suite", det_suite(1, "boom", 449))
control("suite count", det_suite(0, "", 448))

# --- probes --------------------------------------------------------------------

BASH = shutil.which("bash") or "/bin/bash"


def kill_against(label, stdout_file, stderr_text, json_mode=True):
    """Run bin/twine kill SID against a stub bale root that replays stdout_file,
    prints stderr_text, exits 1. Returns (exit, stdout)."""
    root = SCRATCH / f"root-{label}"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "VERSION").write_text("0.4.49\n", encoding="utf-8")
    script = f"#!{BASH}\n# stub written by the checkpoint — not bale\ncat {json.dumps(str(stdout_file))}\n"
    if stderr_text:
        script += f"printf '%s' {json.dumps(stderr_text)} >&2\n"
    script += "exit 1\n"
    (root / "bin" / "bale").write_text(script, encoding="utf-8")
    (root / "bin" / "bale").chmod(0o755)
    state, repo = SCRATCH / f"state-{label}", SCRATCH / f"repo-{label}"
    state.mkdir(); repo.mkdir()
    argv = [sys.executable, "-I", "-S", "-B", str(TREE / "bin/twine"), "kill", SID, "--state-dir", str(state),
            "--cwd", str(repo)] + (["--json"] if json_mode else [])
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C.UTF-8", "TWINE_BALE_ROOT": str(root)}
    r = subprocess.run(argv, cwd=str(TREE), env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                       timeout=120)
    return r.returncode, r.stdout


def last_json(text):
    try:
        return json.loads(text.strip().splitlines()[-1])
    except Exception:
        return None


code, out = kill_against("hold-json", TREE / HOLD_FIXTURE, "")
hold_json = last_json(out)
_, human = kill_against("hold-human", TREE / HOLD_FIXTURE, "", json_mode=False)
probe("hand-line-keys-on-the-recorded-reason", det_hold_line_keys({"json": hold_json, "human": human, "exit": code}))
_, out = kill_against("not-open-text", TREE / NOT_OPEN_FIXTURE,
                      f"[bale] error: branch bale/{SID} exists — this session reached HOLD.\n")
probe("stderr-text-no-longer-keys-the-hand-line", det_text_no_longer_keys({"json": last_json(out)}))
probe("kill-twin-keys-unchanged", det_twin_keys(list(hold_json) if isinstance(hold_json, dict) else []))

reader = ("import sys, json; sys.path.insert(0, sys.argv[1]); from tests.helpers import unlock_recording as u; "
          "print(json.dumps([u('hold-branch').stderr.decode('utf-8'), u('not-open').stderr.decode('utf-8')]))")
r = subprocess.run([sys.executable, "-I", "-B", "-c", reader, str(TREE)], cwd=str(TREE), stdin=subprocess.DEVNULL,
                   capture_output=True, text=True, timeout=120)
if r.returncode != 0:
    probe("tests-replay-no-derived-stderr", [f"tests.helpers could not answer: {r.stderr.strip()[-300:]}"])
else:
    h, n = json.loads(r.stdout.strip().splitlines()[-1])
    probe("tests-replay-no-derived-stderr", det_no_derived_stderr(h.encode(), n.encode()))

texts = {p: fold((TREE / p).read_text(encoding="utf-8")) for p in {p for p, _ in STALE}}
probe("stale-sentences-gone", det_stale(texts))
probe("seed-bin-bale-transitions-untouched",
      det_untouched({p: sha((TREE / p).read_bytes()) for p in UNTOUCHED}))
probe("version-is-0.8.1", det_version((TREE / "VERSION").read_bytes()))

suite = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                       cwd=str(TREE), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900)
m = re.search(r"^Ran (\d+) tests", suite.stderr, re.M)
probe("suite-green-and-not-smaller", det_suite(suite.returncode, suite.stderr.strip()[-400:], int(m.group(1)) if m else None))

cleanup()
failed = [label for label, f in results if f]
print(f"[checkpoint] {len(results)} probes, {len(failed)} failed" + (": " + ", ".join(failed) if failed else ""))
sys.exit(1 if failed else 0)
PY

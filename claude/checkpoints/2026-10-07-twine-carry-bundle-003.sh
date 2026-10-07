#!/usr/bin/env bash
# Blind checkpoint, v1 — twine-src session `twine-carry-bundle` (slug; Arc 1
# row 3), authored by the twine desk on 2026-10-07 from the brief, before the
# landing exists. Outcome contracts only, driven through bin/twine against
# stub bale roots that replay the three recorded `bale open --json` lines:
# the opened open and its record, a second desk finding the tarball in the
# record (and without one), --check rehearsing with no state directory and
# writing nothing, a mode mismatch and a bale refusal recording nothing, the
# refusals that never start bale, the argv in each mode, the twin's fixed
# keys, the contract section and the manifest's open surface, the untouched
# set, VERSION, the suite.
#
# Runs in the staging tree's root (cwd). Exit 0 / 1 / 2: passed / a probe
# failed by name / the oracle is broken. Writes: one temporary directory for
# the stub bale roots, repos and state directories (announced, removed at
# exit) and the suite's own temporary directories. Nothing under the tree.
# Python under -I -B.
set -u
exec python3 -I -B - "$@" <<'PY'
import hashlib, json, os, re, shutil, stat, subprocess, sys, tempfile, tomllib
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
FX = "fixtures/bale-0.4.49/"
OPENED = FX + "scratch/open_bundle_--json+opened.json"
SECOND = FX + "scratch/open_bundle_--json+second-desk.json"
REHEARSED = FX + "twine-src/open_--check_bundle_--json.json"
for needed in ("bin/twine", "VERSION", "twine-seed.md", "share/bale-consumption.toml",
               "claude/context/cli-contract.md", OPENED, SECOND, REHEARSED):
    if not (TREE / needed).exists():
        print(f"[ORACLE ERROR] {needed} is not under the cwd {TREE}; exit 2", file=sys.stderr)
        sys.exit(2)
SCRATCH = Path(tempfile.mkdtemp(prefix="twine-carry-bundle-checkpoint-"))
print(f"[checkpoint] writes: {SCRATCH} (temporary, removed at exit) and the suite's own temporary "
      "directories; nothing under the tree")

PIN = "0.4.49"
VERSION = b"0.9.0\n"
SID = "2026-10-07-sc-002"
FIXED = ["command", "ok", "bundle", "check", "ran", "exit_code", "open", "outcome", "sid", "desk", "tarball",
         "tarball_source", "opener", "record", "record_error", "stderr", "reason", "refusals"]
BESIDE = ["stdout", "argv", "stderr_truncated", "timed_out", "capped", "duration_seconds", "cwd", "state_dir",
          "state_dir_source", "bale"]
RECORD_KEYS = ["sid", "cwd", "tarball", "opens"]
OPEN_KEYS = ["outcome", "desk", "bundle_sha256", "opener_sha256", "recorded_at"]
UNTOUCHED = {
    "twine-seed.md": "abb55c02c0fb3abdeb2b8b155c6160448ce14330dacabe27b18568aae905d9ed",
    "bin/twine": "d5388349e4559df3f93f74a48f4740a512466a1224f84c98f655f3f3b4d4669e",
    "share/transitions.toml": "707e94f9af6ea82457109c193d71141e774a97f40a90dec6b485ea65acb94f3e",
    "fixtures/": "1dacb8355d8c0af0e7c417026f3da9b1681f2a306896e1bf8c72a5128a1dcc3e",
}
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


def tree_sha(root):
    """One hash over every file under root: relative path, NUL, bytes, NUL."""
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


OPENED_LINE = json.loads((TREE / OPENED).read_text(encoding="utf-8"))
SECOND_LINE = json.loads((TREE / SECOND).read_text(encoding="utf-8"))

# --- detectors -----------------------------------------------------------------


def det_twin_keys(twins):
    """twins: {label: twin dict or None}. Every twin carries the fixed names and those beside them."""
    f = []
    for label, t in twins.items():
        if not isinstance(t, dict):
            f.append(f"{label}: no JSON object on stdout")
            continue
        missing = [k for k in FIXED + BESIDE if k not in t]
        if missing:
            f.append(f"{label}: missing {missing}")
        if t.get("command") != "carry bundle":
            f.append(f"{label}: command is {t.get('command')!r}")
    return f


def det_opened(o):
    """o: exit, twin, argv (what the stub saw), bundle_abs, record (parsed or None), record_path,
    record_mode, cwd, human_stdout."""
    f, t = [], o.get("twin") or {}
    if (o.get("exit"), t.get("ok"), t.get("outcome"), t.get("sid")) != (0, True, "opened", SID):
        f.append(f"exit/ok/outcome/sid are {(o.get('exit'), t.get('ok'), t.get('outcome'), t.get('sid'))}")
    if o.get("argv") != ["open", o.get("bundle_abs"), "--json"]:
        f.append(f"bale saw argv {o.get('argv')!r}, not open <absolute bundle> --json")
    if (t.get("tarball"), t.get("tarball_source")) != (OPENED_LINE["tarball"], "bale"):
        f.append(f"tarball/tarball_source are {(t.get('tarball'), t.get('tarball_source'))}")
    if t.get("opener") != OPENED_LINE["opener"]:
        f.append("the twin's opener is not the recording's")
    if t.get("record") != o.get("record_path") or t.get("record_error") is not None:
        f.append(f"record/record_error are {(t.get('record'), t.get('record_error'))}, wanted "
                 f"{(o.get('record_path'), None)}")
    r = o.get("record")
    if not isinstance(r, dict):
        f.append(f"no record at {o.get('record_path')}")
    else:
        if list(r) != RECORD_KEYS:
            f.append(f"the record's keys are {list(r)}, not {RECORD_KEYS}")
        if (r.get("sid"), r.get("cwd"), r.get("tarball")) != (SID, o.get("cwd"), OPENED_LINE["tarball"]):
            f.append(f"the record's sid/cwd/tarball are {(r.get('sid'), r.get('cwd'), r.get('tarball'))}")
        opens = r.get("opens")
        if not (isinstance(opens, list) and len(opens) == 1 and isinstance(opens[0], dict)):
            f.append(f"the record's opens is {opens!r}, not one entry")
        else:
            e = opens[0]
            if list(e) != OPEN_KEYS:
                f.append(f"the entry's keys are {list(e)}, not {OPEN_KEYS}")
            want = ("opened", None, OPENED_LINE["bundle"]["sha256"], sha(OPENED_LINE["opener"].encode("utf-8")))
            got = (e.get("outcome"), e.get("desk"), e.get("bundle_sha256"), e.get("opener_sha256"))
            if got != want:
                f.append(f"the entry's outcome/desk/bundle_sha256/opener_sha256 are {got}")
            if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z", str(e.get("recorded_at"))):
                f.append(f"recorded_at is {e.get('recorded_at')!r}, not UTC ISO 8601 with Z")
    if o.get("record_mode") != 0o600:
        f.append(f"the record's mode is {o.get('record_mode')!r}, not 0o600")
    if o.get("human_stdout") != OPENED_LINE["opener"]:
        f.append("human stdout is not exactly the recording's opener")
    return f


def det_second_desk(o):
    """o: twin, record after the second open (on top of an opened one)."""
    f, t = [], o.get("twin") or {}
    if (t.get("ok"), t.get("outcome"), t.get("desk")) != (True, "second-desk", "desk-2"):
        f.append(f"ok/outcome/desk are {(t.get('ok'), t.get('outcome'), t.get('desk'))}")
    if (t.get("tarball"), t.get("tarball_source")) != (OPENED_LINE["tarball"], "record"):
        f.append(f"tarball/tarball_source are {(t.get('tarball'), t.get('tarball_source'))}, not the first "
                 "open's from the record")
    r = o.get("record") or {}
    opens = r.get("opens") if isinstance(r, dict) else None
    if r.get("tarball") != OPENED_LINE["tarball"]:
        f.append("the record lost the first open's tarball")
    if not (isinstance(opens, list) and len(opens) == 2):
        f.append(f"the record holds {opens!r}, not two opens")
    elif (opens[1].get("outcome"), opens[1].get("desk")) != ("second-desk", "desk-2"):
        f.append(f"the second entry is {opens[1]!r}")
    return f


def det_second_desk_fresh(o):
    f, t = [], o.get("twin") or {}
    if (o.get("exit"), t.get("ok"), t.get("tarball"), t.get("tarball_source")) != (0, True, None, None):
        f.append(f"exit/ok/tarball/tarball_source are "
                 f"{(o.get('exit'), t.get('ok'), t.get('tarball'), t.get('tarball_source'))}")
    if not t.get("record_error"):
        f.append("record_error does not say the record was written fresh")
    r = o.get("record") or {}
    if (r.get("tarball"), len(r.get("opens") or [])) != (None, 1):
        f.append(f"the fresh record is {r!r}")
    return f


def det_check(o):
    """o: twin (no state dir resolvable), argv, bundle_abs, twin2 + state_dir_listing (with --state-dir)."""
    f, t = [], o.get("twin") or {}
    if (o.get("exit"), t.get("ok"), t.get("outcome"), t.get("check")) != (0, True, "rehearsed", True):
        f.append(f"exit/ok/outcome/check are {(o.get('exit'), t.get('ok'), t.get('outcome'), t.get('check'))}")
    if o.get("argv") != ["open", "--check", o.get("bundle_abs"), "--json"]:
        f.append(f"bale saw argv {o.get('argv')!r}, not open --check <absolute bundle> --json")
    if (t.get("state_dir"), t.get("record")) != (None, None):
        f.append(f"state_dir/record are {(t.get('state_dir'), t.get('record'))} under --check")
    t2 = o.get("twin2") or {}
    if t2.get("ok") is not True:
        f.append("--check with --state-dir given is not ok")
    if o.get("state_dir_listing"):
        f.append(f"--check wrote under the state directory: {o.get('state_dir_listing')}")
    return f


def det_not_ok_records_nothing(cases):
    """cases: {label: {"exit", "twin", "listing"}} — each must be not ok, exit 1, ran, nothing recorded."""
    f = []
    for label, c in cases.items():
        t = c.get("twin") or {}
        if (c.get("exit"), t.get("ok"), t.get("ran")) != (1, False, True):
            f.append(f"{label}: exit/ok/ran are {(c.get('exit'), t.get('ok'), t.get('ran'))}")
        if not t.get("reason"):
            f.append(f"{label}: no reason")
        if t.get("record") is not None or c.get("listing"):
            f.append(f"{label}: something was recorded: {c.get('listing')}")
    return f


def det_refused_unstarted(cases):
    """cases: {label: {"exit", "twin", "started"}} — refused, exit 1, bale never started."""
    f = []
    for label, c in cases.items():
        t = c.get("twin") or {}
        if (c.get("exit"), t.get("ok"), t.get("ran"), c.get("started")) != (1, False, False, False):
            f.append(f"{label}: exit/ok/ran/started are {(c.get('exit'), t.get('ok'), t.get('ran'), c.get('started'))}")
        if not t.get("refusals"):
            f.append(f"{label}: no refusal named")
    return f


def det_bare_name(argv, name):
    return [] if argv == ["open", name, "--json"] else [f"bale saw {argv!r} for a bare name, not open {name} --json"]


def det_docs(contract, manifest):
    f = []
    if not re.search(r"^## 15\. `twine carry bundle", contract, re.M):
        f.append("the contract has no '## 15. `twine carry bundle' section")
    opens = [s for s in manifest.get("surface") or [] if s.get("verb") == "open"]
    if len(opens) != 1:
        f.append(f"{len(opens)} open surfaces in the manifest")
    else:
        s = opens[0]
        if "carry bundle" not in (s.get("read_by") or []):
            f.append("the open surface's read_by lacks 'carry bundle'")
        if not {"outcome", "sid", "tarball", "opener", "desk", "bundle"} <= set(s.get("keys") or []):
            f.append(f"the open surface's keys are {s.get('keys')!r}")
    if (manifest.get("bale") or {}).get("pin") != PIN:
        f.append("the pin moved")
    return f


def det_untouched(observed):
    return [f"{p} changed" for p, h in UNTOUCHED.items() if observed.get(p) != h]


def det_version(raw):
    return [] if raw == VERSION else [f"VERSION is {raw!r}, not {VERSION!r}"]


def det_suite(code, tail, count):
    f = [] if code == 0 else [f"the suite exited {code}: {tail}"]
    if count is None or count < 455:
        f.append(f"the suite ran {count} tests, fewer than the 455 at 0.8.1")
    return f


# --- controls ------------------------------------------------------------------

control("twin keys", det_twin_keys({"x": {"command": "carry bundle"}}))
control("opened", det_opened({"exit": 0, "twin": {"ok": True, "outcome": "opened", "sid": SID}, "argv": ["open", "b"],
                              "bundle_abs": "b", "record": None, "record_mode": 0o644, "human_stdout": ""}))
control("second desk", det_second_desk({"twin": {"ok": True, "outcome": "second-desk", "desk": "desk-2",
                                                 "tarball": None, "tarball_source": None}, "record": {}}))
control("second desk fresh", det_second_desk_fresh({"exit": 0, "twin": {"ok": True, "tarball": None,
                                                                        "tarball_source": None}, "record": {}}))
control("check", det_check({"exit": 0, "twin": {"ok": True, "outcome": "rehearsed", "check": True, "state_dir": "/s"},
                            "argv": ["open", "b", "--json"], "bundle_abs": "b", "twin2": {"ok": True},
                            "state_dir_listing": ["inflight"]}))
control("not ok records nothing", det_not_ok_records_nothing({"x": {"exit": 0, "twin": {"ok": True, "ran": True},
                                                                    "listing": []}}))
control("refused unstarted", det_refused_unstarted({"x": {"exit": 1, "twin": {"ok": False, "ran": False,
                                                                             "refusals": ["r"]}, "started": True}}))
control("bare name", det_bare_name(["open", "/abs/n", "--json"], "n"))
control("docs", det_docs("## 14. kill\n", {"bale": {"pin": PIN}, "surface": [{"verb": "open", "read_by": [], "keys": []}]}))
control("untouched", det_untouched({p: "0" * 64 for p in UNTOUCHED}))
control("version", det_version(b"0.8.1\n"))
control("suite", det_suite(1, "boom", 455))
control("suite count", det_suite(0, "", 454))

# --- the harness ---------------------------------------------------------------

BASH = shutil.which("bash") or "/bin/bash"
_n = [0]


def stub_root(stdout_file=None, stderr_text="", exit_code=0, version=PIN):
    """A temp bale install root whose bin/bale is a bash stub (not bale): it records its argv,
    one per line, replays stdout_file's bytes on stdout, prints stderr_text, exits exit_code."""
    _n[0] += 1
    root = SCRATCH / f"root-{_n[0]}"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "VERSION").write_text(version + "\n", encoding="utf-8")
    rec = root / "argv"
    lines = [f"#!{BASH}", "# a stub written by the checkpoint — not bale",
             f"printf '%s\\n' \"$@\" > {json.dumps(str(rec))}"]
    if stdout_file is not None:
        lines.append(f"cat {json.dumps(str(stdout_file))}")
    if stderr_text:
        lines.append(f"printf '%s' {json.dumps(stderr_text)} >&2")
    lines.append(f"exit {int(exit_code)}")
    exe = root / "bin" / "bale"
    exe.write_text("\n".join(lines) + "\n", encoding="utf-8")
    exe.chmod(0o755)
    return root


def seen_argv(root):
    p = root / "argv"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else None


def fresh_dir(name):
    _n[0] += 1
    d = SCRATCH / f"{name}-{_n[0]}"
    d.mkdir()
    return d


BUNDLE = SCRATCH / "2026-10-07-checkpoint-specimen.bale-bundle"
BUNDLE.write_bytes(b"not a bundle: a stub bale never reads it\n")
BUNDLE_ABS = str(BUNDLE)


def twine(root, *args, state_dir=None, json_mode=True, cwd=None, tail=()):
    """bin/twine carry bundle under -I -S -B, with only PATH, LC_ALL and TWINE_BALE_ROOT in the
    environment (no HOME, no TWINE_STATE_DIR, no XDG_STATE_HOME), so no state directory resolves
    unless --state-dir is given. `tail` goes last, after every option (a `--` and a name that
    begins with `-`, as an operator must type it). Returns (exit, stdout, twin-or-None)."""
    argv = [sys.executable, "-I", "-S", "-B", str(TREE / "bin/twine"), "carry", "bundle", *args]
    if cwd is not None:
        argv += ["--cwd", str(cwd)]
    if state_dir is not None:
        argv += ["--state-dir", str(state_dir)]
    if json_mode:
        argv.append("--json")
    argv += list(tail)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C.UTF-8", "TWINE_BALE_ROOT": str(root)}
    r = subprocess.run(argv, cwd=str(SCRATCH), env=env, stdin=subprocess.DEVNULL, capture_output=True,
                       timeout=300)
    out = r.stdout.decode("utf-8", errors="replace")
    twin = None
    if json_mode:
        try:
            twin = json.loads(out.strip().splitlines()[-1])
        except Exception:
            twin = None
    return r.returncode, out, twin


def read_record(state):
    p = state / "inflight" / f"{SID}.json"
    if not p.is_file():
        return None, None, str(p)
    try:
        return json.loads(p.read_text(encoding="utf-8")), stat.S_IMODE(p.stat().st_mode), str(p)
    except Exception:
        return "unreadable", stat.S_IMODE(p.stat().st_mode), str(p)


def listing(state):
    return sorted(str(p.relative_to(state)) for p in Path(state).rglob("*")) if Path(state).exists() else []


twins = {}

# opened, then a second desk into the same state directory
repo, state = fresh_dir("repo"), fresh_dir("state")
root = stub_root(TREE / OPENED)
code, _, twin = twine(root, BUNDLE_ABS, state_dir=state, cwd=repo)
twins["opened"] = twin
record, mode, record_path = read_record(state)
h_root, h_state = stub_root(TREE / OPENED), fresh_dir("state")
_, human, _ = twine(h_root, BUNDLE_ABS, state_dir=h_state, cwd=repo, json_mode=False)
probe("opened-opens-records-and-prints-the-opener",
      det_opened({"exit": code, "twin": twin, "argv": seen_argv(root), "bundle_abs": BUNDLE_ABS,
                  "record": record, "record_mode": mode, "record_path": record_path,
                  "cwd": str(repo.resolve()), "human_stdout": human}))

root2 = stub_root(TREE / SECOND)
_, _, twin = twine(root2, BUNDLE_ABS, state_dir=state, cwd=repo)
twins["second-desk"] = twin
record, _, _ = read_record(state)
probe("second-desk-finds-the-tarball-in-the-record", det_second_desk({"twin": twin, "record": record}))

state3 = fresh_dir("state")
code, _, twin = twine(stub_root(TREE / SECOND), BUNDLE_ABS, state_dir=state3, cwd=repo)
twins["second-desk-fresh"] = twin
record, _, _ = read_record(state3)
probe("second-desk-without-a-record-is-ok-and-says-so",
      det_second_desk_fresh({"exit": code, "twin": twin, "record": record}))

# --check: no state directory resolvable; then with one given, nothing written
root4 = stub_root(TREE / REHEARSED)
code, _, twin = twine(root4, "--check", BUNDLE_ABS, cwd=repo)
twins["rehearsed"] = twin
state5 = fresh_dir("state")
_, _, twin2 = twine(stub_root(TREE / REHEARSED), "--check", BUNDLE_ABS, state_dir=state5, cwd=repo)
probe("check-rehearses-needs-no-state-and-writes-nothing",
      det_check({"exit": code, "twin": twin, "argv": seen_argv(root4), "bundle_abs": BUNDLE_ABS,
                 "twin2": twin2, "state_dir_listing": listing(state5)}))

# not ok, nothing recorded: a mode mismatch either way, and a bale refusal (a double: exit 1, nothing on stdout)
cases = {}
for label, src, args, err, ex in (
        ("rehearsed-without-check", REHEARSED, [BUNDLE_ABS], "", 0),
        ("opened-under-check", OPENED, ["--check", BUNDLE_ABS], "", 0),
        ("bale-refused", None, [BUNDLE_ABS], "[bale] error: a refusal double written by the checkpoint\n", 1)):
    st = fresh_dir("state")
    c, _, t = twine(stub_root(TREE / src if src else None, err, ex), *args, state_dir=st, cwd=repo)
    twins[label] = t
    cases[label] = {"exit": c, "twin": t, "listing": listing(st)}
probe("not-ok-records-nothing", det_not_ok_records_nothing(cases))

# refused before bale starts
cases = {}
r = stub_root(TREE / OPENED)
c, _, t = twine(r, BUNDLE_ABS, cwd=repo)
cases["no-state-dir"] = {"exit": c, "twin": t, "started": seen_argv(r) is not None}
r = stub_root(TREE / OPENED)
c, _, t = twine(r, state_dir=fresh_dir("state"), cwd=repo, tail=("--", "-x-not-a-file.bale-bundle"))
cases["leading-dash-name"] = {"exit": c, "twin": t, "started": seen_argv(r) is not None}
r = stub_root(TREE / OPENED, version="0.4.45")
c, _, t = twine(r, BUNDLE_ABS, state_dir=fresh_dir("state"), cwd=repo)
cases["unpinned-bale"] = {"exit": c, "twin": t, "started": seen_argv(r) is not None}
twins.update({k: v["twin"] for k, v in cases.items()})
probe("refusals-never-start-bale", det_refused_unstarted(cases))

bare = "2026-10-07-not-in-the-scratch-dir.bale-bundle"
r = stub_root(TREE / OPENED)
twine(r, bare, state_dir=fresh_dir("state"), cwd=repo)
probe("a-bare-name-reaches-bale-as-given", det_bare_name(seen_argv(r), bare))

probe("twin-fixed-keys-on-every-path", det_twin_keys(twins))

probe("contract-section-and-open-surface",
      det_docs((TREE / "claude/context/cli-contract.md").read_text(encoding="utf-8"),
               tomllib.loads((TREE / "share/bale-consumption.toml").read_text(encoding="utf-8"))))

observed = {p: sha((TREE / p).read_bytes()) for p in UNTOUCHED if not p.endswith("/")}
observed["fixtures/"] = tree_sha(TREE / "fixtures")
probe("seed-bin-transitions-fixtures-untouched", det_untouched(observed))
probe("version-is-0.9.0", det_version((TREE / "VERSION").read_bytes()))

suite = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                       cwd=str(TREE), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900)
m = re.search(r"^Ran (\d+) tests", suite.stderr, re.M)
probe("suite-green-and-not-smaller",
      det_suite(suite.returncode, suite.stderr.strip()[-400:], int(m.group(1)) if m else None))

cleanup()
failed = [label for label, f in results if f]
print(f"[checkpoint] {len(results)} probes, {len(failed)} failed" + (": " + ", ".join(failed) if failed else ""))
sys.exit(1 if failed else 0)
PY

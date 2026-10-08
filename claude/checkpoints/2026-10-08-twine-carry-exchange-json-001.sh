#!/usr/bin/env bash
# Blind checkpoint, v1 — twine-src session `twine-carry-exchange-json` (slug),
# authored by the twine desk on 2026-10-07 from the brief, before the landing
# exists. Outcome contracts only, driven through bin/twine against stub bale
# roots that replay the four recorded `bale relay --json` lines, carrying the
# relayed line's own block: the argv and stdin; ok on `relayed` with human
# stdout exactly the line's block; each refusal not ok naming its cause; the
# lines twine must not take for a relay not ok; integrity still refused
# before bale; the twin's fixed names; the flagless relay surface retired and
# the --json one read; the untouched set; VERSION; the suite. Pins no seed:
# tidy6 may land beside it.
#
# Runs in the staging tree's root (cwd). Exit 0 / 1 / 2: passed / a probe
# failed by name / the oracle is broken. Writes: one temporary directory for
# the stub bale roots and turn files (announced, removed at exit) and the
# suite's own temporary directories. Nothing under the tree. Python -I -B.
set -u
exec python3 -I -B - "$@" <<'PY'
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, tomllib
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
FX = "fixtures/bale-0.4.49/scratch/"
RELAYED = FX + "relay_sid_file_--json+relayed.json"
REEMITTED = FX + "relay_sid_--json.json"
INGEST = FX + "relay_sid_file_--json+relay-refused+ingest.json"
GATE = FX + "relay_sid_file_--json+relay-refused+session-gate.json"
for needed in ("bin/twine", "VERSION", "share/bale-consumption.toml", RELAYED, REEMITTED, INGEST, GATE):
    if not (TREE / needed).exists():
        print(f"[ORACLE ERROR] {needed} is not under the cwd {TREE}; exit 2", file=sys.stderr)
        sys.exit(2)
SCRATCH = Path(tempfile.mkdtemp(prefix="twine-carry-exchange-json-checkpoint-"))
print(f"[checkpoint] writes: {SCRATCH} (temporary, removed at exit) and the suite's own temporary "
      "directories; nothing under the tree")

PIN = "0.4.49"
VERSION = b"0.10.0\n"
SID = "2026-10-07-sc-002"
FIXED = ["command", "ok", "sid", "block", "ran", "exit_code", "stdout", "stderr", "reason", "refusals",
         "relay", "outcome", "integrity", "argv", "cwd", "bale", "input"]
UNTOUCHED = {
    "bin/twine": "d5388349e4559df3f93f74a48f4740a512466a1224f84c98f655f3f3b4d4669e",
    "share/transitions.toml": "707e94f9af6ea82457109c193d71141e774a97f40a90dec6b485ea65acb94f3e",
    "twine/kill.py": "1e960b1433e3b1041ca1503bc3c192206190be74af0785ed8a4159890a2f18b5",
    "twine/inflight.py": "ff516ae2bcb3aae91276230bc2d786b7fe3cf8547b0e9772dcd464d9f425fa99",
    "twine/commands/carry_bundle.py": "a5317910ce7fef12934330d6e01ed68167a73f053ba2c78493b30675c969a2be",
    "fixtures/ but README.md": "4bafb7359dcd114315b9418b53910ca2f3a43a969d89fed63ad978120ef4ca15",
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


def fixtures_sha(root):
    h = hashlib.sha256()
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and p.relative_to(root).as_posix() != "README.md":
            h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


LINE = {k: json.loads((TREE / p).read_text(encoding="utf-8")) for k, p in
        (("relayed", RELAYED), ("re-emitted", REEMITTED), ("ingest", INGEST), ("gate", GATE))}
BLOCK = LINE["relayed"]["block"]

# --- detectors -----------------------------------------------------------------


def det_relayed(o):
    """o: exit, twin, argv and stdin the stub saw, human stdout, calls (how many times the stub ran)."""
    f, t = [], o.get("twin") or {}
    if (o.get("exit"), t.get("ok"), t.get("outcome")) != (0, True, "relayed"):
        f.append(f"exit/ok/outcome are {(o.get('exit'), t.get('ok'), t.get('outcome'))}")
    if t.get("relay") != LINE["relayed"]:
        f.append("the twin's relay is not bale's line")
    if o.get("argv") != ["relay", SID, "-", "--json"]:
        f.append(f"bale saw argv {o.get('argv')!r}, not relay {SID} - --json")
    if o.get("stdin") != BLOCK.encode("utf-8"):
        f.append("bale's stdin was not exactly the block's own lines")
    if o.get("calls") != 1:
        f.append(f"bale ran {o.get('calls')} times")
    if o.get("human") != BLOCK:
        f.append("human stdout is not exactly the line's block")
    return f


def det_refused_names_cause(cases):
    """cases: {label: {"exit", "twin", "human", "cause"}}."""
    f = []
    for label, c in cases.items():
        t = c.get("twin") or {}
        if (c.get("exit"), t.get("ok"), t.get("ran"), t.get("outcome")) != (1, False, True, "relay-refused"):
            f.append(f"{label}: exit/ok/ran/outcome are {(c.get('exit'), t.get('ok'), t.get('ran'), t.get('outcome'))}")
        if c.get("cause") not in (t.get("reason") or ""):
            f.append(f"{label}: the reason does not carry bale's cause whole")
        human = c.get("human") or ""
        if len(human.splitlines()) != 1 or not human.startswith("carry exchange ") or "BALE EXCHANGE BEGIN" in human:
            f.append(f"{label}: human stdout is not one 'carry exchange …' line")
    return f


def det_not_a_relay(cases):
    """cases: {label: {"exit", "twin"}} — each not ok, exit 1, bale ran, a reason."""
    f = []
    for label, c in cases.items():
        t = c.get("twin") or {}
        if (c.get("exit"), t.get("ok"), t.get("ran")) != (1, False, True) or not t.get("reason"):
            f.append(f"{label}: exit/ok/ran/reason are {(c.get('exit'), t.get('ok'), t.get('ran'), t.get('reason'))}")
    return f


def det_unstarted(o):
    t = o.get("twin") or {}
    f = []
    if (o.get("exit"), t.get("ok"), t.get("ran"), o.get("started")) != (1, False, False, False):
        f.append(f"a tampered block: exit/ok/ran/started are {(o.get('exit'), t.get('ok'), t.get('ran'), o.get('started'))}")
    return f


def det_twin_keys(twins):
    f = []
    for label, t in twins.items():
        if not isinstance(t, dict):
            f.append(f"{label}: no JSON object on stdout")
            continue
        missing = [k for k in FIXED if k not in t]
        if missing:
            f.append(f"{label}: missing {missing}")
        if t.get("command") != "carry exchange":
            f.append(f"{label}: command is {t.get('command')!r}")
    return f


def det_manifest(m):
    f = []
    relays = [s for s in m.get("surface") or [] if s.get("verb") == "relay"]
    if any(list(s.get("flags") or []) == [] for s in relays):
        f.append("the flagless relay surface is still in the manifest")
    js = [s for s in relays if list(s.get("flags") or []) == ["--json"]]
    if len(js) != 1:
        f.append(f"{len(js)} relay --json surfaces")
    else:
        if "carry exchange" not in (js[0].get("read_by") or []):
            f.append("the relay --json surface's read_by lacks 'carry exchange'")
        if not {"outcome", "sid", "block", "cause"} <= set(js[0].get("keys") or []):
            f.append(f"the relay --json surface's keys are {js[0].get('keys')!r}")
    if (m.get("bale") or {}).get("pin") != PIN:
        f.append("the pin moved")
    return f


def det_untouched(observed):
    return [f"{p} changed" for p, h in UNTOUCHED.items() if observed.get(p) != h]


def det_version(raw):
    return [] if raw == VERSION else [f"VERSION is {raw!r}, not {VERSION!r}"]


def det_suite(code, tail, count):
    f = [] if code == 0 else [f"the suite exited {code}: {tail}"]
    if count is None or count < 521:
        f.append(f"the suite ran {count} tests, fewer than the 521 at 0.9.0")
    return f


# --- controls ------------------------------------------------------------------

control("relayed", det_relayed({"exit": 0, "twin": {"ok": True, "outcome": "relayed"}, "argv": ["relay", SID, "-"],
                                "stdin": b"", "calls": 1, "human": ""}))
control("refused names cause", det_refused_names_cause({"x": {"exit": 1, "twin": {"ok": False, "ran": True,
                                                                                 "outcome": "relay-refused",
                                                                                 "reason": "bale exited 1"},
                                                            "human": "carry exchange t: NOT OK", "cause": "why"}}))
control("not a relay", det_not_a_relay({"x": {"exit": 0, "twin": {"ok": True, "ran": True}}}))
control("unstarted", det_unstarted({"exit": 1, "twin": {"ok": False, "ran": False}, "started": True}))
control("twin keys", det_twin_keys({"x": {"command": "carry exchange", "sid": None}}))
control("manifest", det_manifest({"bale": {"pin": PIN}, "surface": [{"verb": "relay", "flags": []},
                                                                    {"verb": "relay", "flags": ["--json"],
                                                                     "read_by": [], "keys": []}]}))
control("untouched", det_untouched({p: "0" * 64 for p in UNTOUCHED}))
control("version", det_version(b"0.9.0\n"))
control("suite", det_suite(1, "boom", 521))
control("suite count", det_suite(0, "", 520))

# --- the harness ---------------------------------------------------------------

BASH = shutil.which("bash") or "/bin/bash"
_n = [0]


def stub_root(stdout_file=None, exit_code=0, stderr_text=""):
    """A temp bale install root whose bin/bale is a bash stub (not bale): it counts its runs,
    records its argv and its stdin, replays stdout_file's bytes, prints stderr_text, exits."""
    _n[0] += 1
    root = SCRATCH / f"root-{_n[0]}"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "VERSION").write_text(PIN + "\n", encoding="utf-8")
    q = json.dumps
    lines = [f"#!{BASH}", "# a stub written by the checkpoint — not bale",
             f"printf 'x' >> {q(str(root / 'calls'))}",
             f"printf '%s\\n' \"$@\" > {q(str(root / 'argv'))}",
             f"cat > {q(str(root / 'stdin'))}"]
    if stdout_file is not None:
        lines.append(f"cat {q(str(stdout_file))}")
    if stderr_text:
        lines.append(f"printf '%s' {q(stderr_text)} >&2")
    lines.append(f"exit {int(exit_code)}")
    exe = root / "bin" / "bale"
    exe.write_text("\n".join(lines) + "\n", encoding="utf-8")
    exe.chmod(0o755)
    return root


def seen(root):
    a, s, c = root / "argv", root / "stdin", root / "calls"
    return (a.read_text(encoding="utf-8").splitlines() if a.exists() else None,
            s.read_bytes() if s.exists() else None,
            len(c.read_bytes()) if c.exists() else 0)


def write(name, data):
    p = SCRATCH / name
    p.write_text(data, encoding="utf-8")
    return p


TURN = write("turn.txt", "The worker's turn, as pasted.\n\n" + BLOCK + "\nAfter the block.\n")


def twine(root, turn, json_mode=True):
    argv = [sys.executable, "-I", "-S", "-B", str(TREE / "bin/twine"), "carry", "exchange", str(turn),
            "--cwd", str(SCRATCH)] + (["--json"] if json_mode else [])
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C.UTF-8", "TWINE_BALE_ROOT": str(root)}
    r = subprocess.run(argv, cwd=str(SCRATCH), env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=300)
    out = r.stdout.decode("utf-8", errors="replace")
    twin = None
    if json_mode:
        try:
            twin = json.loads(out.strip().splitlines()[-1])
        except Exception:
            twin = None
    return r.returncode, out, twin


twins = {}

root = stub_root(TREE / RELAYED, 0, "[bale] a stub's stderr line\n")
code, _, twin = twine(root, TURN)
twins["relayed"] = twin
argv, stdin, calls = seen(root)
_, human, _ = twine(stub_root(TREE / RELAYED, 0), TURN, json_mode=False)
probe("relayed-is-ok-and-prints-the-block",
      det_relayed({"exit": code, "twin": twin, "argv": argv, "stdin": stdin, "calls": calls, "human": human}))

cases = {}
for label, path, key in (("ingest", INGEST, "ingest"), ("session-gate", GATE, "gate")):
    code, _, twin = twine(stub_root(TREE / path, 1, "[bale] error: " + LINE[key]["cause"] + "\n"), TURN)
    _, human, _ = twine(stub_root(TREE / path, 1), TURN, json_mode=False)
    twins[label] = twin
    cases[label] = {"exit": code, "twin": twin, "human": human, "cause": LINE[key]["cause"]}
probe("each-refusal-is-not-ok-and-names-its-cause", det_refused_names_cause(cases))

other = dict(LINE["relayed"], sid="2026-10-07-not-this-session")
nullblock = dict(LINE["relayed"], block=None)
doubles = {"another-sid": write("double-other-sid.json", json.dumps(other) + "\n"),
           "null-block": write("double-null-block.json", json.dumps(nullblock) + "\n"),
           "not-json": write("double-not-json.txt", "not a line bale prints\n"),
           "empty": write("double-empty.txt", "")}
cases = {}
for label, src, ex in (("re-emitted", TREE / REEMITTED, 0), ("relayed-beside-exit-1", TREE / RELAYED, 1),
                       ("another-sid", doubles["another-sid"], 0), ("null-block", doubles["null-block"], 0),
                       ("not-json", doubles["not-json"], 0), ("empty-exit-1", doubles["empty"], 1)):
    code, _, twin = twine(stub_root(src, ex), TURN)
    twins[label] = twin
    cases[label] = {"exit": code, "twin": twin}
probe("lines-that-are-not-this-relay-are-not-ok", det_not_a_relay(cases))

tampered = write("tampered.txt", BLOCK.replace('"the first"', '"the second"', 1))
r = stub_root(TREE / RELAYED, 0)
code, _, twin = twine(r, tampered)
twins["tampered"] = twin
probe("a-block-that-fails-integrity-never-starts-bale",
      det_unstarted({"exit": code, "twin": twin, "started": seen(r)[2] > 0}))

probe("twin-fixed-names-on-every-path", det_twin_keys(twins))
probe("flagless-relay-surface-retired-and-json-surface-read",
      det_manifest(tomllib.loads((TREE / "share/bale-consumption.toml").read_text(encoding="utf-8"))))

observed = {p: sha((TREE / p).read_bytes()) for p in UNTOUCHED if not p.startswith("fixtures/")}
observed["fixtures/ but README.md"] = fixtures_sha(TREE / "fixtures")
probe("bin-transitions-kill-inflight-carry-bundle-fixtures-untouched", det_untouched(observed))
probe("version-is-0.10.0", det_version((TREE / "VERSION").read_bytes()))

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

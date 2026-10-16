#!/usr/bin/env bash
# Blind checkpoint — twine-src session `twine-run-many` (the hardening wave,
# 5 of 6), authored at sitting 2026-10-13-open-hardening-011, v1.
#
# Outcome contracts only (PLANNER.md §4), graded through `twine run` over
# several bundles with the fake adapter against a stub bale this oracle
# writes itself: it replays the tree's recorded `opened` and dry-run lines
# re-keyed to one session per bundle (the second at desk-2), answers
# `contract --json` from the tree's carried line, holds each open a second
# and logs when each began and ended. Runs from the staged tree's root; reads
# nothing of its own path, sid or manifest. Exit 0: every probe holds. Exit
# 1: a probe fails, named. Exit 2: this oracle is broken (a control failed,
# or an unplanned exception) — the planner's artifact.
set -u
export PYTHONDONTWRITEBYTECODE=1
python3 -I -B - <<'ORACLE'
import io, json, re, shutil, stat, subprocess, sys, tarfile, tempfile, tomllib
from pathlib import Path


def broken(exc_type, exc, tb):
    sys.stderr.write(f"[checkpoint] BROKEN: {exc_type.__name__}: {exc}\n")
    sys.exit(2)


sys.excepthook = broken
ROOT = Path.cwd()
failures: list[str] = []

# --- the pins the brief carries ---------------------------------------------
VERSION = "0.28.0"
MANY_KEYS = ("bundles", "runs", "apply_lines", "reason", "next")
BUNDLES = ("oracle-left.bale-bundle", "oracle-right.bale-bundle")
SIDS = ("2026-10-15-oracle-left-001", "2026-10-15-oracle-right-002")
DESKS = (None, "desk-2")
SLEEP_SECONDS = 4
PRICES = '[model."fake"]\ninput = 1\noutput = 2\ncache_read = 0.1\ncache_write = 1.25\n'
MANIFEST = tomllib.loads((ROOT / "share" / "bale-consumption.toml").read_text(encoding="utf-8"))
RECORDINGS = MANIFEST["bale"]["recordings"]
CONTRACT_LINE = ROOT / MANIFEST["bale"]["contract"]
OPEN_LINE = ROOT / "fixtures" / f"bale-{RECORDINGS}" / "scratch" / "open_bundle_--json+opened.json"
DRY_RUN_LINE = ROOT / "fixtures" / f"bale-{RECORDINGS}" / "scratch" / \
    "apply_--dry-run_--json_tarball+dry-run.json"
TWINE = ROOT / "bin" / "twine"


def usage(input_tokens: int) -> dict:
    return {"input": input_tokens, "output": 1, "thinking": None, "cache_read": 0,
            "cache_write": 0}


def tool_turn(name: str, arguments: dict, input_tokens: int, tag: str = "") -> dict:
    return {"stop": None, "tool_calls": [{"id": f"t-{name}{tag}", "name": name,
                                          "arguments": arguments}],
            "usage": usage(input_tokens)}


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("`", "").replace("*", "")).strip().lower()


# --- detectors ------------------------------------------------------------------

def many_problems(twin: dict, exit_code: int) -> list[str]:
    """Two bundles, both delivered: the one twin, each run's own twin inside
    it, and each run's own apply line."""
    if list(twin)[:2] != ["command", "ok"] or tuple(list(twin)[2:]) != MANY_KEYS:
        return [f"the twin's names are {list(twin)}, want command, ok, then exactly {list(MANY_KEYS)}"]
    out = []
    runs = twin["runs"]
    if not isinstance(runs, list) or len(runs) != len(BUNDLES):
        return [f"runs is {runs if not isinstance(runs, list) else f'{len(runs)} entries'}, "
                f"want one twin per bundle ({len(BUNDLES)})"]
    if twin["bundles"] != list(BUNDLES):
        out.append(f"bundles is {twin['bundles']!r}, want {list(BUNDLES)}")
    for i, (run, sid) in enumerate(zip(runs, SIDS)):
        if not isinstance(run, dict) or list(run)[:2] != ["command", "ok"] or run.get("command") != "run":
            out.append(f"runs[{i}] is not a single run's twin (names {list(run)[:4] if isinstance(run, dict) else run!r})")
            continue
        if run.get("sid") != sid:
            out.append(f"runs[{i}] is session {run.get('sid')!r}, want {sid!r} (the bundles' order)")
        if run.get("outcome") != "delivered" or run.get("ok") is not True:
            out.append(f"runs[{i}] ended {run.get('outcome')!r} ({str(run.get('reason'))[:160]!r}), "
                       "want delivered")
        if list(run)[-1:] != ["next"]:
            out.append(f"runs[{i}]'s last name is {list(run)[-1:]!r}, want next (the single twin, unchanged)")
        line = str(run.get("apply_line") or "")
        m = re.search(r"--cost-file\s+(\S+)", line)
        if m is None or f"{sid}.json" not in m.group(1):
            out.append(f"runs[{i}]'s apply line {line!r} does not carry its own session's cost file")
    if twin["apply_lines"] != [r.get("apply_line") for r in runs if isinstance(r, dict)]:
        out.append(f"apply_lines is {twin['apply_lines']!r}, want each delivered run's own line in order")
    if twin["ok"] is not True or exit_code != 0:
        out.append(f"ok {twin['ok']!r}, exit {exit_code}, with every run delivered; want true and 0")
    if twin["reason"] is not None:
        out.append(f"reason is {twin['reason']!r}, want null")
    return out


def overlap_problems(records: list[dict]) -> list[str]:
    """The two runs' runs.jsonl lines: one per session, their times overlapping."""
    by_sid = {r.get("sid"): r for r in records if isinstance(r, dict)}
    if sorted(by_sid) != sorted(SIDS) or len(records) != len(SIDS):
        return [f"runs.jsonl holds {len(records)} line(s) for {sorted(by_sid)}, want one for each of {list(SIDS)}"]
    a, b = (by_sid[s] for s in SIDS)
    try:
        concurrent = a["started_at"] < b["ended_at"] and b["started_at"] < a["ended_at"]
    except (KeyError, TypeError) as exc:
        return [f"a runs.jsonl line carries no comparable times: {exc}"]
    if not concurrent:
        return [f"the runs did not overlap: {SIDS[0]} {a['started_at']}–{a['ended_at']}, "
                f"{SIDS[1]} {b['started_at']}–{b['ended_at']}"]
    return []


def open_problems(calls: list[dict]) -> list[str]:
    """bale open ran once per bundle, in the order given, one after the other."""
    opens = [c for c in calls if c.get("verb") == "open"]
    if [c.get("bundle") for c in opens] != list(BUNDLES):
        return [f"bale open saw {[c.get('bundle') for c in opens]}, want {list(BUNDLES)} in that order"]
    for first, second in zip(opens, opens[1:]):
        if second["began"] < first["ended"]:
            return [f"the opens overlapped: {second['bundle']} began {first['ended'] - second['began']:.2f}s "
                    f"before {first['bundle']}'s open returned"]
    return []


def refusal_problems(twin: dict, exit_code: int, calls: list[dict]) -> list[str]:
    """Two bundles, one --script: refused before anything is passed to bale."""
    out = []
    if exit_code == 0:
        out.append("two bundles with one --script exited 0")
    if twin and twin.get("ok") is not False:
        out.append(f"two bundles with one --script: ok {twin.get('ok')!r}, want false")
    if any(c.get("verb") == "open" for c in calls):
        out.append("two bundles with one --script still opened a session")
    return out


def single_problems(twin: dict) -> list[str]:
    """One bundle: today's twin, unwrapped."""
    if not twin:
        return ["one bundle printed no twin"]
    out = []
    wrapped = [k for k in ("bundles", "runs", "apply_lines") if k in twin]
    if wrapped:
        out.append(f"one bundle's twin carries {wrapped} — wrapped; want today's single twin")
    if twin.get("sid") != SIDS[0] or twin.get("outcome") != "delivered":
        out.append(f"one bundle ended {twin.get('outcome')!r} as {twin.get('sid')!r}, want delivered as {SIDS[0]!r}")
    return out


def version_problems(text: str) -> list[str]:
    return [] if text.strip() == VERSION else [f"VERSION is {text.strip()!r}, want {VERSION!r}"]


def docs_problems(cli_doc: str, readme: str) -> list[str]:
    out = []
    if "apply_lines" not in fold(cli_doc):
        out.append("cli-contract.md never names apply_lines")
    if "disjoint" not in fold(cli_doc):
        out.append("cli-contract.md never names the forecast disjointness")
    if "disjoint" not in fold(readme):
        out.append("README.md never says the bundles run together must be disjoint")
    return out


# --- controls (exit 2 when a detector does not fire) ------------------------------

def control(name: str, ok: bool) -> None:
    if not ok:
        sys.stderr.write(f"[checkpoint] BROKEN: control {name} did not fire\n")
        sys.exit(2)


def _run_twin(i: int) -> dict:
    line = f"bale apply /h{i}/response.tar.gz --cost-file /s/cost/{SIDS[i]}.json"
    return {"command": "run", "ok": True, "sid": SIDS[i], "outcome": "delivered", "reason": None,
            "apply_line": line, "next": [line]}


_good = {"command": "run", "ok": True, "bundles": list(BUNDLES), "runs": [_run_twin(0), _run_twin(1)],
         "apply_lines": [_run_twin(0)["apply_line"], _run_twin(1)["apply_line"]], "reason": None,
         "next": []}
control("many ok", many_problems(_good, 0) == [])
control("many keys", bool(many_problems({k: v for k, v in _good.items() if k != "apply_lines"}, 0)))
control("many order", bool(many_problems({**_good, "runs": [_run_twin(1), _run_twin(0)]}, 0)))
control("many exit", bool(many_problems(_good, 1)))
control("many cost", bool(many_problems({**_good, "runs": [_run_twin(0), {**_run_twin(1), "apply_line":
                                          _run_twin(0)["apply_line"]}]}, 0)))
_r = [{"sid": SIDS[0], "started_at": "2026-10-15T10:00:00Z", "ended_at": "2026-10-15T10:00:05Z"},
      {"sid": SIDS[1], "started_at": "2026-10-15T10:00:01Z", "ended_at": "2026-10-15T10:00:06Z"}]
control("overlap ok", overlap_problems(_r) == [])
control("overlap sequential", bool(overlap_problems([_r[0], {**_r[1], "started_at": "2026-10-15T10:00:05Z",
                                                             "ended_at": "2026-10-15T10:00:10Z"}])))
control("overlap count", bool(overlap_problems(_r[:1])))
_c = [{"verb": "open", "bundle": BUNDLES[0], "began": 1.0, "ended": 2.0},
      {"verb": "open", "bundle": BUNDLES[1], "began": 2.1, "ended": 3.1}]
control("open ok", open_problems(_c) == [])
control("open overlap", bool(open_problems([_c[0], {**_c[1], "began": 1.5}])))
control("open order", bool(open_problems([_c[1], _c[0]])))
control("refusal ok", refusal_problems({"ok": False}, 1, []) == [])
control("refusal opened", bool(refusal_problems({"ok": False}, 1, _c[:1])))
control("single ok", single_problems({"command": "run", "ok": True, "sid": SIDS[0], "outcome": "delivered"}) == [])
control("single wrapped", bool(single_problems(_good)))
control("version", version_problems(VERSION + "\n") == [] and bool(version_problems("0.27.0\n")))
control("docs", docs_problems("apply_lines disjoint", "disjoint") == [] and bool(docs_problems("", "")))

# --- the stub bale, the requests, and twine ------------------------------------------


def write_request(base: Path, sid: str) -> Path:
    tarball = base / f"request-{sid}.tar.gz"
    manifest = json.dumps({"session_id": sid, "goal": "the oracle's request"})
    members = [("request-001/manifest.json", manifest.encode("utf-8"))]
    for name in ("craft_response.py", "response_lint.py"):
        found = sorted(p for p in (ROOT / "tests").rglob(name) if p.is_file())
        if found:
            members.append((f"request-001/tools/{name}", found[0].read_bytes()))
    with tarfile.open(tarball, "w:gz") as tf:
        for name, data in members:
            info = tarfile.TarInfo(name); info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return tarball


STUB = r'''
import json, sys, time
from pathlib import Path
CONF = json.loads(Path(__file__).with_name("stub.json").read_text())
args = sys.argv[1:]
began = time.time()
def log(**kw):
    with open(CONF["calls"], "a") as f:
        f.write(json.dumps(kw) + "\n")
if args[:1] == ["contract"]:
    sys.stdout.write(Path(CONF["contract"]).read_text()); sys.exit(0)
if args[:1] == ["open"]:
    names = [a for a in args[1:] if a.endswith(".bale-bundle")]
    name = Path(names[0]).name if names else None
    time.sleep(1.0)
    entry = CONF["bundles"].get(name)
    log(verb="open", bundle=name, began=began, ended=time.time())
    if entry is None:
        sys.exit(1)
    text = Path(CONF["open"]).read_text().splitlines()[0].replace(CONF["old_sid"], entry["sid"])
    line = json.loads(text)
    line["sid"], line["tarball"], line["desk"] = entry["sid"], entry["tarball"], entry["desk"]
    print(json.dumps(line)); sys.exit(0)
if args[:1] == ["apply"]:
    sid = next((e["sid"] for e in CONF["bundles"].values() if any(e["sid"] in a for a in args)), None)
    log(verb="apply", sid=sid, began=began, ended=time.time())
    text = Path(CONF["dry_run"]).read_text()
    if sid:
        line = json.loads(text.splitlines()[0].replace(CONF["old_sid"], sid)); line["sid"] = sid
        text = json.dumps(line) + "\n"
    sys.stdout.write(text); sys.exit(0)
log(verb=args[0] if args else None, began=began, ended=time.time())
sys.exit(1)
'''


def bed(label: str) -> dict:
    base = Path(tempfile.mkdtemp(prefix=f"twine-oracle-{label}-")).resolve()
    state = base / "state"; state.mkdir()
    (state / "prices.toml").write_text(PRICES, encoding="utf-8")
    repo = base / "repo"; repo.mkdir()
    root = base / "root"; (root / "bin").mkdir(parents=True)
    (root / "bin" / "VERSION").write_text(
        json.loads(CONTRACT_LINE.read_text(encoding="utf-8"))["bale_version"] + "\n", encoding="utf-8")
    old_sid = json.loads(OPEN_LINE.read_text(encoding="utf-8").splitlines()[0])["sid"]
    conf = {"calls": str(base / "calls.jsonl"), "contract": str(CONTRACT_LINE), "open": str(OPEN_LINE),
            "dry_run": str(DRY_RUN_LINE), "old_sid": old_sid,
            "bundles": {b: {"sid": s, "desk": d, "tarball": str(write_request(base, s))}
                        for b, s, d in zip(BUNDLES, SIDS, DESKS)}}
    (root / "bin" / "stub.json").write_text(json.dumps(conf), encoding="utf-8")
    exe = root / "bin" / "bale"
    exe.write_text(f"#!{sys.executable} -I\n# A double written by the run-many checkpoint — not bale.\n"
                   + STUB, encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    scripts = []
    for i, sid in enumerate(SIDS):
        make = (f"sleep {SLEEP_SECONDS}; printf '{sid}\\n' > out.txt && "
                "tar czf response-oracle.tar.gz out.txt")
        script = [tool_turn("shell", {"command": make}, 20 + i, tag=f"-{i}"),
                  tool_turn("deliver", {"tarball": "response-oracle.tar.gz"}, 30 + i, tag=f"-{i}")]
        path = base / f"script-{i}.json"; path.write_text(json.dumps(script), encoding="utf-8")
        scripts.append(str(path))
    return {"base": base, "state": state, "repo": repo, "root": root, "scripts": scripts,
            "calls": base / "calls.jsonl"}


def twine_run(b: dict, bundles: list[str], scripts: list[str]) -> tuple[dict, int, str]:
    argv = [sys.executable, "-I", "-B", str(TWINE), "run", *bundles, "--adapter", "fake",
            "--model", "fake", "--cap", "5", "--state-dir", str(b["state"]), "--bale-root",
            str(b["root"]), "--cwd", str(b["repo"]), "--json"]
    for s in scripts:
        argv += ["--script", s]
    proc = subprocess.run(argv, cwd=b["repo"], capture_output=True, text=True, timeout=600)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    twin = None
    try:
        twin = json.loads(lines[0]) if len(lines) == 1 else None
    except ValueError:
        pass
    return (twin if isinstance(twin, dict) else {}), proc.returncode, proc.stderr


def calls_of(b: dict) -> list[dict]:
    path = b["calls"]
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.is_file() else []


def jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(raw))
        except ValueError:
            out.append({"unparsed": raw})
    return out


# (a) two disjoint bundles, at once
b = bed("many")
twin, code, err = twine_run(b, list(BUNDLES), b["scripts"])
if not twin:
    failures.append(f"two bundles: no single JSON twin on stdout (exit {code}; stderr ends {err[-300:]!r})")
else:
    for p in many_problems(twin, code):
        failures.append(f"two bundles: {p}")
for p in overlap_problems(jsonl(b["state"] / "runs.jsonl")):
    failures.append(f"concurrency: {p}")
for p in open_problems(calls_of(b)):
    failures.append(f"opens: {p}")
for sid in SIDS:
    if not (b["state"] / "transcripts" / f"{sid}.jsonl").is_file():
        failures.append(f"isolation: no transcript for {sid}")
    if not (b["state"] / "sandbox" / sid / "home").is_dir():
        failures.append(f"isolation: no sandbox home for {sid}")

# (b) two bundles, one script: refused before anything opens
b2 = bed("refuse")
twin, code, err = twine_run(b2, list(BUNDLES), b2["scripts"][:1])
for p in refusal_problems(twin, code, calls_of(b2)):
    failures.append(f"refusal: {p}")

# (c) one bundle: today's twin
b3 = bed("single")
twin, code, err = twine_run(b3, [BUNDLES[0]], b3["scripts"][:1])
for p in single_problems(twin):
    failures.append(f"one bundle: {p}")

# (d) docs and VERSION
for p in docs_problems((ROOT / "claude" / "context" / "cli-contract.md").read_text(encoding="utf-8"),
                       (ROOT / "README.md").read_text(encoding="utf-8")):
    failures.append(f"docs: {p}")
for p in version_problems((ROOT / "VERSION").read_text(encoding="utf-8")):
    failures.append(f"version: {p}")

for bb in (b, b2, b3):
    shutil.rmtree(bb["base"], ignore_errors=True)
if failures:
    for f in failures:
        print(f"[checkpoint] FAIL {f}")
    sys.exit(1)
print("[checkpoint] PASS: two disjoint bundles opened one after the other and ran at once, each "
      f"in its own cage and transcript, one twin carrying both; VERSION {VERSION}")
sys.exit(0)
ORACLE
exit $?

#!/usr/bin/env bash
# Blind checkpoint — twine-src session `twine-run-telemetry` (the hardening
# wave, 3 of 6), authored at sitting 2026-10-13-open-hardening-011, v1.
#
# Outcome contracts only (PLANNER.md §4), graded through `twine run`,
# `twine resume`, `twine stats`, `twine transcript` and `twine status` with
# the fake adapter and a stub bale this oracle writes itself (replaying the
# tree's recorded `open` and `apply --dry-run` lines under an install root
# carrying the floor's schemas). Runs from the staged tree's root; reads
# nothing of its own path, sid or manifest. Exit 0: every probe holds. Exit
# 1: a probe fails, named. Exit 2: this oracle is broken (a control failed,
# or an unplanned exception) — the planner's artifact. Re-derived on
# 2026-10-15 for the contract gate (the stub bale answers `contract --json`
# from the tree's carried line) and bale's --cost-file, before first issue.
set -u
export PYTHONDONTWRITEBYTECODE=1
python3 -I -B - <<'ORACLE'
import io, json, os, re, shutil, stat, subprocess, sys, tarfile, tempfile, tomllib
from pathlib import Path


def broken(exc_type, exc, tb):
    sys.stderr.write(f"[checkpoint] BROKEN: {exc_type.__name__}: {exc}\n")
    sys.exit(2)


sys.excepthook = broken
ROOT = Path.cwd()
failures: list[str] = []

# --- the pins the brief carries ---------------------------------------------
VERSION = "0.26.0"
RUN_KEYS = ("record_version", "sid", "command", "desk", "started_at", "ended_at", "wall_seconds",
            "outcome", "stop", "move", "actor", "shape", "reason", "turns", "tool_calls",
            "retries", "continuations", "usage", "cost_usd", "cap_usd", "adapter", "model",
            "window", "resumed_from", "rewarm", "tools", "events", "transcript", "sandbox",
            "inflight", "cost_file", "apply")
EVENT_KEYS = ("window_warned", "continuations", "retries", "heartbeats", "transcript_faults",
              "inflight_error", "group_survivors")
STATS_KEYS = ("path", "runs", "faults", "sessions", "by_outcome", "by_command", "turns",
              "tool_calls", "retries", "cost_usd", "unpriced_runs", "wall_seconds", "by_tool",
              "delivered", "since", "sid", "reason")
OUTCOMES = ("delivered", "suspended", "ended", "stopped", "killed", "cap-reached",
            "cap-unchecked", "refused")
COST_KEYS = {"tokens_in", "tokens_out", "usd", "model_tier", "calls", "models"}
TRANSCRIPT_KEYS = ("sid", "path", "lines", "runs", "faults", "story", "reason")
PRICES = '[model."fake"]\ninput = 1\noutput = 2\ncache_read = 0.1\ncache_write = 1.25\n'
QUESTION = {"question": "Which seam?", "while_doing": "the oracle's rehearsal",
            "would_assume": "the first", "why_blocked": "the brief names two"}
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


def prose_turn(input_tokens: int) -> dict:
    return {"text": "done; nothing to deliver", "stop": "end-turn", "usage": usage(input_tokens)}


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("`", "").replace("*", "")).strip().lower()


# --- detectors ------------------------------------------------------------------

def record_problems(line: dict, *, sid: str, command: str, outcome: str, turns: int,
                    tool_calls: int, tool: str | None) -> list[str]:
    out = []
    if tuple(line.keys()) != RUN_KEYS:
        return [f"a runs.jsonl line's keys are {list(line.keys())}, want exactly {list(RUN_KEYS)} in order"]
    if line["record_version"] != 1:
        out.append(f"record_version {line['record_version']!r}, want 1")
    for key, want in (("sid", sid), ("command", command), ("outcome", outcome),
                      ("turns", turns), ("tool_calls", tool_calls)):
        if line[key] != want:
            out.append(f"{key} is {line[key]!r}, want {want!r}")
    if not (isinstance(line["wall_seconds"], (int, float)) and line["wall_seconds"] >= 0):
        out.append(f"wall_seconds {line['wall_seconds']!r} is not a non-negative number")
    if not isinstance(line["usage"], dict) or set(line["usage"]) != {"input", "output", "thinking",
                                                                       "cache_read", "cache_write"}:
        out.append("usage is not the five classes")
    if not isinstance(line["events"], dict) or tuple(line["events"].keys()) != EVENT_KEYS:
        out.append(f"events keys are {list(line['events']) if isinstance(line['events'], dict) else line['events']!r}, want {list(EVENT_KEYS)}")
    tools = line["tools"]
    if not isinstance(tools, dict):
        out.append("tools is not an object")
    elif tool is not None:
        entry = tools.get(tool)
        if not (isinstance(entry, dict) and tuple(entry.keys()) == ("calls", "errors", "seconds")
                and entry["calls"] >= 1):
            out.append(f"tools[{tool!r}] is {entry!r}, want {{calls >= 1, errors, seconds}}")
    if line["apply"] is not None:
        out.append("apply is not null (reserved for the T12 session)")
    if command == "resume" and not isinstance(line["resumed_from"], int):
        out.append("a resume's line carries no integer resumed_from")
    if command == "run" and not isinstance(line["desk"], int):
        out.append(f"a run's desk is {line['desk']!r}, want the open's desk number")
    return out


def stats_problems(twin: dict, *, runs: int, by_outcome: dict, by_command: dict,
                   tool: str | None) -> list[str]:
    out = []
    if twin.get("ok") is not True:
        return [f"stats not ok: {twin.get('reason')}"]
    keys = [k for k in twin.keys() if k not in ("command", "ok")]
    if tuple(keys) != STATS_KEYS:
        return [f"stats keys are {keys}, want exactly {list(STATS_KEYS)} in order after command, ok"]
    if twin["runs"] != runs:
        out.append(f"stats runs {twin['runs']!r}, want {runs}")
    bo = twin["by_outcome"]
    if not isinstance(bo, dict) or set(bo) != set(OUTCOMES):
        out.append("by_outcome does not carry every one of the eight outcomes")
    else:
        for k, v in by_outcome.items():
            if bo.get(k) != v:
                out.append(f"by_outcome[{k!r}] {bo.get(k)!r}, want {v}")
    for k, v in by_command.items():
        if (twin["by_command"] or {}).get(k) != v:
            out.append(f"by_command[{k!r}] {(twin['by_command'] or {}).get(k)!r}, want {v}")
    if tool is not None and not isinstance((twin["by_tool"] or {}).get(tool), dict):
        out.append(f"by_tool lacks {tool!r}")
    if not isinstance(twin["cost_usd"], (int, float)) or twin["cost_usd"] <= 0:
        out.append(f"cost_usd {twin['cost_usd']!r}, want the priced runs' positive sum")
    return out


def transcript_problems(twin: dict, lines: list[dict]) -> list[str]:
    out = []
    if twin.get("ok") is not True:
        return [f"transcript not ok: {twin.get('reason')}"]
    keys = [k for k in twin.keys() if k not in ("command", "ok")]
    if tuple(keys) != TRANSCRIPT_KEYS:
        return [f"transcript keys are {keys}, want exactly {list(TRANSCRIPT_KEYS)} after command, ok"]
    story = twin["story"]
    if not isinstance(story, list) or len(story) != len(lines):
        return out + [f"story has {len(story) if isinstance(story, list) else story!r} entries, "
                      f"want one per transcript line ({len(lines)})"]
    for entry, line in zip(story, lines):
        if not isinstance(entry, dict) or tuple(entry.keys()) != ("seq", "kind", "call", "summary"):
            out.append(f"a story entry is {entry!r}, want {{seq, kind, call, summary}}")
            break
        if entry["seq"] != line.get("seq") or entry["kind"] != line.get("kind"):
            out.append(f"story entry {entry['seq']} ({entry['kind']}) does not match the line "
                       f"{line.get('seq')} ({line.get('kind')})")
            break
        if not isinstance(entry["summary"], str) or not entry["summary"]:
            out.append(f"story entry {entry['seq']} has no summary")
            break
    if twin["runs"] != sum(1 for l in lines if l.get("kind") == "run-start"):
        out.append(f"transcript runs {twin['runs']!r}, want the run-start count")
    return out


def status_problems(twin: dict, present: bool) -> list[str]:
    sp = twin.get("state_present") or {}
    if tuple(sp.keys())[-1:] != ("runs_jsonl",) or len(sp) != 8:
        return [f"status state_present keys are {list(sp)}, want eight ending in runs_jsonl"]
    return [] if sp["runs_jsonl"] is present else [f"state_present.runs_jsonl {sp['runs_jsonl']!r}, want {present}"]


def version_problems(text: str) -> list[str]:
    return [] if text.strip() == VERSION else [f"VERSION is {text.strip()!r}, want {VERSION!r}"]


def docs_problems(cli_doc: str, index: str, readme: str) -> list[str]:
    out = []
    f = fold(cli_doc)
    for name in ("runs.jsonl", "twine stats", "twine transcript"):
        if name not in f:
            out.append(f"cli-contract.md never names {name}")
    if "runs.jsonl" not in fold(index):
        out.append("claude/INDEX.md never names runs.jsonl")
    if "twine stats" not in fold(readme) or "twine transcript" not in fold(readme):
        out.append("README.md does not name both verbs")
    return out


def cost_problems(twin: dict, sums: dict) -> list[str]:
    """A delivered run: the apply line names a cost file whose six keys sum
    the sid's spend.jsonl records by bale's definitions."""
    out = []
    if twin.get("outcome") != "delivered":
        return [f"the oracle's delivered run ends {twin.get('outcome')!r} "
                f"({str(twin.get('reason'))[:160]!r})"]
    line = str(twin.get("apply_line") or "")
    m = re.search(r"--cost-file\s+(\S+)", line)
    if not line.startswith("bale apply ") or m is None:
        return [f"the apply line {line!r} carries no --cost-file"]
    path = Path(m.group(1).strip("'\""))
    if not path.is_file():
        return [f"the cost file {path} the apply line names does not exist"]
    try:
        cost = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"the cost file is not JSON: {exc}"]
    if not isinstance(cost, dict) or set(cost) != COST_KEYS:
        return [f"the cost file's keys are {sorted(cost) if isinstance(cost, dict) else cost!r}, "
                f"want exactly {sorted(COST_KEYS)}"]
    for key in ("tokens_in", "tokens_out", "calls"):
        if cost[key] != sums[key]:
            out.append(f"cost {key} is {cost[key]!r}, want {sums[key]!r}")
    if cost["models"] != sums["models"]:
        out.append(f"cost models is {cost['models']!r}, want {sums['models']!r}")
    if cost["model_tier"] is not None:
        out.append(f"cost model_tier is {cost['model_tier']!r}, want null")
    if not isinstance(cost["usd"], (int, float)) or cost["usd"] <= 0:
        out.append(f"cost usd is {cost['usd']!r}, want the priced spend")
    return out


# --- controls (exit 2 when a detector does not fire) ------------------------------

def control(name: str, ok: bool) -> None:
    if not ok:
        sys.stderr.write(f"[checkpoint] BROKEN: control {name} did not fire\n")
        sys.exit(2)


def good_record(**over) -> dict:
    base = {k: None for k in RUN_KEYS}
    base.update({"record_version": 1, "sid": "s", "command": "run", "desk": 1, "started_at": "t",
                 "ended_at": "t", "wall_seconds": 1.5, "outcome": "ended", "turns": 2,
                 "tool_calls": 1, "retries": 0, "continuations": 0,
                 "usage": usage(1), "cost_usd": 0.1, "tools": {"shell": {"calls": 1, "errors": 0, "seconds": 0.2}},
                 "events": {k: 0 for k in EVENT_KEYS}, "apply": None})
    base.update(over)
    return base


control("record ok", record_problems(good_record(), sid="s", command="run", outcome="ended", turns=2,
                                     tool_calls=1, tool="shell") == [])
bad = good_record(); bad["extra"] = 1
control("record keys", bool(record_problems(bad, sid="s", command="run", outcome="ended", turns=2,
                                            tool_calls=1, tool="shell")))
control("record values", bool(record_problems(good_record(turns=9), sid="s", command="run",
                                              outcome="ended", turns=2, tool_calls=1, tool="shell")))
control("record tools", bool(record_problems(good_record(tools={}), sid="s", command="run",
                                             outcome="ended", turns=2, tool_calls=1, tool="shell")))
good_stats = {"command": "stats", "ok": True, **{k: None for k in STATS_KEYS}}
good_stats.update({"runs": 2, "by_outcome": {o: 0 for o in OUTCOMES} | {"ended": 2},
                   "by_command": {"run": 1, "resume": 1}, "by_tool": {"shell": {}}, "cost_usd": 0.3})
control("stats ok", stats_problems(good_stats, runs=2, by_outcome={"ended": 2},
                                   by_command={"run": 1, "resume": 1}, tool="shell") == [])
control("stats runs", bool(stats_problems(good_stats, runs=3, by_outcome={"ended": 2},
                                          by_command={"run": 1}, tool="shell")))
bad_stats = dict(good_stats); del bad_stats["unpriced_runs"]
control("stats keys", bool(stats_problems(bad_stats, runs=2, by_outcome={}, by_command={}, tool=None)))
good_lines = [{"seq": 1, "kind": "run-start"}, {"seq": 2, "kind": "run-end"}]
good_tr = {"command": "transcript", "ok": True, "sid": "s", "path": "p", "lines": 2, "runs": 1,
           "faults": [], "story": [{"seq": 1, "kind": "run-start", "call": None, "summary": "x"},
                                   {"seq": 2, "kind": "run-end", "call": None, "summary": "y"}], "reason": None}
control("transcript ok", transcript_problems(good_tr, good_lines) == [])
bad_tr = json.loads(json.dumps(good_tr)); bad_tr["story"] = bad_tr["story"][:1]
control("transcript story", bool(transcript_problems(bad_tr, good_lines)))
control("status", status_problems({"state_present": {k: False for k in ("spend_jsonl", "prices_toml", "abort", "running", "inflight", "transcripts", "sandbox")} | {"runs_jsonl": True}}, True) == []
        and bool(status_problems({"state_present": {"spend_jsonl": True}}, True)))
control("version", version_problems(VERSION + "\n") == [] and bool(version_problems("0.25.0\n")))
with tempfile.TemporaryDirectory(prefix="twine-oracle-ctl-") as _td:
    _cf = Path(_td) / "c.json"
    _cf.write_text(json.dumps({"tokens_in": 3, "tokens_out": 2, "usd": 0.1, "model_tier": None,
                               "calls": 2, "models": ["fake"]}), encoding="utf-8")
    _good = {"outcome": "delivered", "apply_line": f"bale apply /t.tar.gz --cost-file {_cf}"}
    _sums = {"tokens_in": 3, "tokens_out": 2, "calls": 2, "models": ["fake"]}
    control("cost ok", cost_problems(_good, _sums) == [])
    control("cost flag", bool(cost_problems({**_good, "apply_line": "bale apply /t.tar.gz"}, _sums)))
    control("cost sums", bool(cost_problems(_good, {**_sums, "tokens_in": 4})))
control("docs", docs_problems("runs.jsonl twine stats twine transcript", "runs.jsonl", "twine stats twine transcript") == []
        and bool(docs_problems("", "", "")))

# --- the stub bale, the request tarball, and the runs -------------------------------


def write_stub_bale(base: Path, request_tarball: Path) -> tuple[Path, Path]:
    root = base / "root"; (root / "bin").mkdir(parents=True)
    contract_version = json.loads(CONTRACT_LINE.read_text(encoding="utf-8"))["bale_version"]
    (root / "bin" / "VERSION").write_text(contract_version + "\n", encoding="utf-8")
    opened = json.loads(OPEN_LINE.read_text(encoding="utf-8").splitlines()[0])
    opened["tarball"] = str(request_tarball)
    open_file = base / "open.json"; open_file.write_text(json.dumps(opened) + "\n", encoding="utf-8")
    calls = base / "calls"
    bash = shutil.which("bash") or "/bin/bash"
    script = "\n".join([
        f"#!{bash}",
        "# A double written by the telemetry checkpoint — not bale.",
        f"(IFS=$'\\t'; printf '%s\\n' \"$*\") >> '{calls}'",
        f"if [ \"$1\" = open ]; then cat '{open_file}'; exit 0; fi",
        f"if [ \"$1\" = apply ]; then cat '{DRY_RUN_LINE}'; exit 0; fi",
        f"if [ \"$1\" = contract ]; then cat '{CONTRACT_LINE}'; exit 0; fi",
        "exit 1", ""])
    exe = root / "bin" / "bale"; exe.write_text(script, encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return root, calls


def crafter_copies() -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for name in ("craft_response.py", "response_lint.py"):
        found = sorted(p for p in (ROOT / "tests").rglob(name) if p.is_file())
        if found:
            out[name] = found[0].read_bytes()
    return out


def write_request(base: Path) -> Path:
    tarball = base / "request-oracle.tar.gz"
    manifest = json.dumps({"session_id": "2026-10-08-sc-002", "goal": "the oracle's request"})
    members = [("request-001/manifest.json", manifest.encode("utf-8"))]
    members += [(f"request-001/tools/{name}", data) for name, data in crafter_copies().items()]
    with tarfile.open(tarball, "w:gz") as tf:
        for name, data in members:
            info = tarfile.TarInfo(name); info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return tarball


def twine(args: list[str], cwd: Path) -> tuple[dict, str]:
    proc = subprocess.run([sys.executable, "-I", "-B", str(TWINE), *args], cwd=cwd,
                          capture_output=True, text=True, timeout=600)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    try:
        twin = json.loads(lines[0]) if len(lines) == 1 else None
    except ValueError:
        twin = None
    if not isinstance(twin, dict):
        failures.append(f"twine {' '.join(args[:2])}: no JSON twin on stdout (exit "
                        f"{proc.returncode}; stderr ends {proc.stderr[-300:]!r})")
        return {}, proc.stderr
    return twin, proc.stderr


def run_case(label: str, script: list, extra: list[str] = ()) -> tuple[dict, str, Path]:
    base = Path(tempfile.mkdtemp(prefix=f"twine-oracle-{label}-"))
    state = base / "state"; state.mkdir()
    (state / "prices.toml").write_text(PRICES, encoding="utf-8")
    repo = base / "repo"; repo.mkdir()
    tarball = write_request(base)
    root, calls = write_stub_bale(base, tarball)
    script_file = base / "script.json"; script_file.write_text(json.dumps(script), encoding="utf-8")
    twin, err = twine(["run", "oracle.bale-bundle", "--adapter", "fake", "--script",
                       str(script_file), "--model", "fake", "--cap", "5", "--state-dir",
                       str(state), "--bale-root", str(root), "--cwd", str(repo), "--json",
                       *extra], cwd=repo)
    return twin, err, state


def transcript_lines(state: Path, sid: str) -> list[dict]:
    path = state / "transcripts" / f"{sid}.jsonl"
    if not sid or not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def sent_tool_results(lines: list[dict]) -> list[tuple[str, bool]]:
    out = []
    for line in lines:
        if line.get("kind") != "request":
            continue
        for message in line.get("appended") or []:
            content = message.get("content") if isinstance(message, dict) else None
            if message.get("role") != "user" or not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    inner = block.get("content")
                    text = inner if isinstance(inner, str) else \
                        "".join(b.get("text", "") for b in inner if isinstance(b, dict)) \
                        if isinstance(inner, list) else ""
                    out.append((text, bool(block.get("is_error"))))
    return out




def read_runs(state: Path) -> list[dict]:
    path = state / "runs.jsonl"
    if not path.is_file():
        failures.append("runs: <state-dir>/runs.jsonl was not written")
        return []
    out = []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            out.append(json.loads(raw))
        except ValueError as exc:
            failures.append(f"runs: line {n} is not JSON: {exc}")
    return out


# (a) a run with one shell call, then a resume of it (a light block suspends it first)
twin, err, state = run_case("tele", [tool_turn("shell", {"command": "echo tele"}, 10),
                                     tool_turn("escalate", {"questions": [QUESTION]}, 12)])
sid = twin.get("sid") or ""
base = state.parent
answer = base / "answer.txt"; answer.write_text("as assumed\n", encoding="utf-8")
script2 = base / "script2.json"; script2.write_text(json.dumps([prose_turn(14)]), encoding="utf-8")
twin2, err2 = twine(["resume", sid, "--answer", str(answer), "--script", str(script2), "--cap", "5",
                     "--state-dir", str(state), "--bale-root", str(base / "root"), "--cwd",
                     str(base / "repo"), "--json"], cwd=base / "repo")
records = read_runs(state)
if len(records) != 2:
    failures.append(f"runs: {len(records)} line(s) in runs.jsonl after a run and a resume, want 2")
else:
    for p in record_problems(records[0], sid=sid, command="run", outcome="suspended", turns=2,
                             tool_calls=2, tool="shell"):
        failures.append(f"runs[0]: {p}")
    for p in record_problems(records[1], sid=sid, command="resume", outcome="ended", turns=1,
                             tool_calls=0, tool=None):
        failures.append(f"runs[1]: {p}")

# (b) stats over them, whole and by sid
common = ["--state-dir", str(state), "--json"]
stats, _ = twine(["stats", *common], ROOT)
for p in stats_problems(stats, runs=2, by_outcome={"suspended": 1, "ended": 1},
                        by_command={"run": 1, "resume": 1}, tool="shell"):
    failures.append(f"stats: {p}")
by_sid, _ = twine(["stats", "--sid", sid, *common], ROOT)
for p in stats_problems(by_sid, runs=2, by_outcome={"suspended": 1, "ended": 1},
                        by_command={"run": 1, "resume": 1}, tool="shell"):
    failures.append(f"stats --sid: {p}")
other, _ = twine(["stats", "--sid", "2026-01-01-no-such-sid-001", *common], ROOT)
if other.get("ok") is True and other.get("runs") != 0:
    failures.append(f"stats --sid on an unknown sid reports {other.get('runs')!r} runs, want 0")
# an empty report is honest: a fresh state directory
with tempfile.TemporaryDirectory(prefix="twine-oracle-empty-") as td:
    empty, _ = twine(["stats", "--state-dir", td, "--json"], ROOT)
    if empty.get("ok") is not True or empty.get("runs") != 0:
        failures.append(f"stats on an empty state directory: ok {empty.get('ok')!r}, runs "
                        f"{empty.get('runs')!r}; want ok true and 0")

# (c) the transcript's story
lines = transcript_lines(state, sid)
story, _ = twine(["transcript", sid, *common], ROOT)
for p in transcript_problems(story, lines):
    failures.append(f"transcript: {p}")
proc = subprocess.run([sys.executable, "-I", "-B", str(TWINE), "transcript", sid, "--state-dir",
                       str(state)], cwd=ROOT, capture_output=True, text=True, timeout=120)
human = [l for l in proc.stdout.splitlines() if l.strip()]
if proc.returncode != 0 or len(human) != len(lines):
    failures.append(f"transcript (human): exit {proc.returncode}, {len(human)} line(s) on stdout, "
                    f"want one per transcript line ({len(lines)})")

# (d) status knows the file
status, _ = twine(["status", "--state-dir", str(state), "--json"], ROOT)
for p in status_problems(status, True):
    failures.append(f"status: {p}")

# (e) a delivered run: the apply line carries --cost-file, the file sums the spend
make = "printf 'x\\n' > out.txt && tar czf response-oracle.tar.gz out.txt"
twin, err, state = run_case("cost", [tool_turn("shell", {"command": make}, 20),
                                     tool_turn("deliver", {"tarball": "response-oracle.tar.gz"}, 30)])
records = []
spend = state / "spend.jsonl"
if spend.is_file():
    records = [json.loads(l) for l in spend.read_text(encoding="utf-8").splitlines() if l.strip()]
toks = [r.get("tokens") or {} for r in records]
sums = {"tokens_in": sum((t.get("input") or 0) + (t.get("cache_read") or 0) + (t.get("cache_write") or 0) for t in toks),
        "tokens_out": sum((t.get("output") or 0) + (t.get("thinking") or 0) for t in toks),
        "calls": len(records), "models": sorted({r.get("model") for r in records if r.get("model")})}
for p in cost_problems(twin, sums):
    failures.append(f"cost: {p}")

# (f) docs and VERSION
for p in docs_problems((ROOT / "claude" / "context" / "cli-contract.md").read_text(encoding="utf-8"),
                       (ROOT / "claude" / "INDEX.md").read_text(encoding="utf-8"),
                       (ROOT / "README.md").read_text(encoding="utf-8")):
    failures.append(f"docs: {p}")
for p in version_problems((ROOT / "VERSION").read_text(encoding="utf-8")):
    failures.append(f"version: {p}")

if failures:
    for f in failures:
        print(f"[checkpoint] FAIL {f}")
    sys.exit(1)
print("[checkpoint] PASS: every run writes its runs.jsonl line, twine stats aggregates them, "
      "twine transcript tells the story, status lists the file, the apply line carries the "
      f"session's cost file; VERSION {VERSION}")
sys.exit(0)
ORACLE
exit $?

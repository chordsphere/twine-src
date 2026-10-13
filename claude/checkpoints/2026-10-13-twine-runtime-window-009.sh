#!/usr/bin/env bash
# Blind checkpoint — twine-src session `twine-runtime-window` (Arc 2 R5:
# window accounting and cold resume), authored at sitting
# 2026-10-13-open-milestone-2-006, v1.
#
# Outcome contracts only (PLANNER.md §4), graded through the verbs'
# surfaces — `twine run`, `twine resume`, `twine runtime list` — with
# the fake adapter and a stub bale this oracle writes itself (a bash
# script that replays the tree's own recorded `open` and `apply --dry-run`
# lines, under an install root carrying the floor's schemas, so twine's
# gate admits it). Runs from the staged tree's root; reads nothing of
# its own path, sid or manifest. Exit 0: every probe holds. Exit 1: a
# probe fails, named. Exit 2: this oracle is broken (a control failed,
# or an unplanned exception) — the planner's artifact, not the worker's.
set -u
export PYTHONDONTWRITEBYTECODE=1
python3 -I -B - <<'ORACLE'
import io, json, os, re, shutil, stat, subprocess, sys, tarfile, tempfile
from pathlib import Path


def broken(exc_type, exc, tb):
    sys.stderr.write(f"[checkpoint] BROKEN: {exc_type.__name__}: {exc}\n")
    sys.exit(2)


sys.excepthook = broken
ROOT = Path.cwd()
failures: list[str] = []

# --- the pins the brief carries ---------------------------------------------
VERSION = "0.22.0"
FLOOR = "0.4.51"
OPEN_LINE = ROOT / "fixtures" / f"bale-{FLOOR}" / "scratch" / "open_bundle_--json+opened.json"
DRY_RUN_LINE = ROOT / "fixtures" / f"bale-{FLOOR}" / "scratch" / \
    "apply_--dry-run_--json_tarball+dry-run.json"
SCHEMAS = ROOT / "fixtures" / f"bale-{FLOOR}" / "schemas"
TWINE = ROOT / "bin" / "twine"
WINDOW = 1000
WARN_FRACTION = 0.8
PRICES = '[model."fake"]\ninput = 1\noutput = 2\ncache_read = 0.1\ncache_write = 1.25\n'
ANSWER = "as assumed — the oracle's answer to the light block"
QUESTION = {"question": "Which seam?", "while_doing": "the oracle's rehearsal",
            "would_assume": "the first", "why_blocked": "the brief names two"}


def usage(input_tokens: int) -> dict:
    return {"input": input_tokens, "output": 1, "thinking": None, "cache_read": 0,
            "cache_write": 0}


def tool_turn(name: str, arguments: dict, input_tokens: int) -> dict:
    return {"stop": None, "tool_calls": [{"id": f"t-{name}", "name": name,
                                          "arguments": arguments}],
            "usage": usage(input_tokens)}


def prose_turn(input_tokens: int) -> dict:
    return {"text": "done; nothing to deliver", "stop": "end-turn", "usage": usage(input_tokens)}


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("`", "").replace("*", "")).strip()


# --- detectors ------------------------------------------------------------------

def registry_problems(twin: dict) -> list[str]:
    out = []
    if twin.get("ok") is not True:
        out.append(f"runtime list not ok: {twin.get('reason')}")
    rows = {c.get("name"): c for c in twin.get("capabilities", [])}
    for name in ("window-accounting", "suspend-resume"):
        row = rows.get(name)
        if row is None:
            out.append(f"no capability {name!r}")
            continue
        if row.get("status") != "implemented":
            out.append(f"{name} status {row.get('status')!r}, want 'implemented'")
        by = row.get("implemented_by")
        if not (isinstance(by, str) and by.startswith("twine.runtime.")):
            out.append(f"{name} implemented_by {by!r}: want a module under twine.runtime")
    return out


def sent_tool_results(lines: list[dict]) -> list[str]:
    """Every tool_result content the loop sent the model, read from the
    transcript's `request` lines (their `appended` joined is the conversation
    as sent) — what the model read, not what the tool returned."""
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
                    if isinstance(inner, str):
                        out.append(inner)
                    elif isinstance(inner, list):
                        out.append("".join(b.get("text", "") for b in inner if isinstance(b, dict)))
    return out


def warning_problems(twin: dict, tool_results: list[str]) -> list[str]:
    """Run (a): the window reported in the twin, and the warning in the
    tool result the model read after the call that crossed the line."""
    out = []
    w = twin.get("window")
    if not isinstance(w, dict):
        return [f"twin carries no window object (got {w!r})"]
    if w.get("size") != WINDOW:
        out.append(f"window.size {w.get('size')!r}, want {WINDOW}")
    if not (isinstance(w.get("used"), int) and w["used"] >= 850):
        out.append(f"window.used {w.get('used')!r}, want the last call's input side (>= 850)")
    if w.get("warned") is not True:
        out.append(f"window.warned {w.get('warned')!r}, want true")
    contents = list(tool_results)
    if not any(f"[window: 850 of {WINDOW} input tokens in use (85%)" in c for c in contents):
        out.append("no tool result carries the warning line for 850 of 1000")
    return out


def exhaustion_problems(twin: dict) -> list[str]:
    out = []
    if twin.get("outcome") != "stopped":
        out.append(f"outcome {twin.get('outcome')!r}, want 'stopped'")
    if twin.get("stop") != "window-exhausted":
        out.append(f"stop {twin.get('stop')!r}, want 'window-exhausted'")
    if twin.get("move") != "split-goal":
        out.append(f"move {twin.get('move')!r}, want 'split-goal'")
    if twin.get("turns") != 1:
        out.append(f"turns {twin.get('turns')!r}, want 1 (the second call is not made)")
    return out


def resume_problems(twin1: dict, twin2: dict, lines: list[dict]) -> list[str]:
    """Run (c): suspended, then resumed cold with the answer as the next
    user turn, the conversation rebuilt from the transcript."""
    out = []
    if twin1.get("outcome") != "suspended":
        out.append(f"first run outcome {twin1.get('outcome')!r}, want 'suspended'")
    if twin2.get("command") != "resume":
        out.append(f"second twin's command {twin2.get('command')!r}, want 'resume'")
    if twin2.get("outcome") != "ended":
        out.append(f"resumed run outcome {twin2.get('outcome')!r}, want 'ended'")
    starts = [i for i, l in enumerate(lines) if l.get("kind") == "run-start"]
    if len(starts) != 2:
        return out + [f"{len(starts)} run-start line(s) in the transcript, want 2"]
    first_run = lines[starts[0]:starts[1]]
    second_run = lines[starts[1]:]
    totals = [l["messages_total"] for l in first_run if l.get("kind") == "request"]
    req2 = [l for l in second_run if l.get("kind") == "request"]
    if not totals or not req2:
        return out + ["request lines missing in one of the runs"]
    first = req2[0]
    if first.get("messages_total") != totals[-1] + 1:
        out.append(f"the resumed run's first request carries messages_total "
                   f"{first.get('messages_total')!r}, want {totals[-1] + 1} (the whole "
                   "conversation plus the answer)")
    appended = first.get("appended") or []
    last = appended[-1] if appended else {}
    content = last.get("content")
    text = content if isinstance(content, str) else \
        "".join(b.get("text", "") for b in content if isinstance(b, dict)) \
        if isinstance(content, list) else ""
    if last.get("role") != "user" or ANSWER not in text:
        out.append("the resumed run's first request does not end with the answer as a user turn")
    seqs = [l.get("seq") for l in lines]
    if seqs != list(range(1, len(lines) + 1)):
        out.append("transcript seq does not continue 1..n across the two runs")
    if not isinstance(second_run[0].get("resumed_from"), int):
        out.append("the second run-start line carries no integer resumed_from")
    return out


def clarification_problems(twin: dict, manifest: dict | None, calls: list[list[str]]) -> list[str]:
    out = []
    if twin.get("outcome") != "suspended":
        out.append(f"outcome {twin.get('outcome')!r}, want 'suspended'")
    if not twin.get("tarball"):
        out.append("twin names no tarball for the clarification response")
    if not twin.get("apply_line"):
        out.append("twin carries no apply_line for the clarification response")
    if manifest is None:
        out.append("the clarification tarball has no readable manifest.json")
    else:
        if manifest.get("response_kind") != "clarification":
            out.append(f"response_kind {manifest.get('response_kind')!r}, want 'clarification'")
        qs = manifest.get("questions") or []
        if not qs or qs[0].get("question") != QUESTION["question"]:
            out.append("the manifest's questions[] does not carry the escalated question")
    if not any(c[:3] == ["apply", "--dry-run", "--json"] for c in calls):
        out.append("bale was not asked for the dry run of the clarification tarball")
    return out


def version_problems(text: str) -> list[str]:
    return [] if text.strip() == VERSION else [f"VERSION is {text.strip()!r}, want {VERSION!r}"]


def docs_problems(cli_doc: str, runtime_doc: str) -> list[str]:
    out = []
    if "twine resume" not in fold(cli_doc):
        out.append("cli-contract.md never names `twine resume`")
    if "--window" not in fold(cli_doc):
        out.append("cli-contract.md never names --window")
    if "window-exhausted" not in fold(runtime_doc) or "resume" not in fold(runtime_doc):
        out.append("runtime-contract.md does not describe the window or the resume")
    return out


# --- controls (exit 2 when a detector does not fire) ------------------------------

def control(name: str, ok: bool) -> None:
    if not ok:
        sys.stderr.write(f"[checkpoint] BROKEN: control {name} did not fire\n")
        sys.exit(2)


good_reg = {"ok": True, "capabilities": [
    {"name": "window-accounting", "status": "implemented", "implemented_by": "twine.runtime.x"},
    {"name": "suspend-resume", "status": "implemented", "implemented_by": "twine.runtime.y"}]}
control("registry ok", registry_problems(good_reg) == [])
bad = json.loads(json.dumps(good_reg)); bad["capabilities"][0]["status"] = "declared"
control("registry status", bool(registry_problems(bad)))
bad = json.loads(json.dumps(good_reg)); bad["capabilities"][1]["implemented_by"] = None
control("registry implemented_by", bool(registry_problems(bad)))
good_w = {"window": {"size": WINDOW, "used": 850, "warned": True}}
good_r = [f"x\n[window: 850 of {WINDOW} input tokens in use (85%); y"]
control("warning ok", warning_problems(good_w, good_r) == [])
control("warning absent", bool(warning_problems(good_w, ["x"])))
control("sent results", sent_tool_results([{"kind": "request", "appended": [
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "r1"}]}]}]) == ["r1"]
        and sent_tool_results([{"kind": "turn"}]) == [])
control("warning twin", bool(warning_problems({"window": None}, good_r)))
control("exhaustion ok", exhaustion_problems({"outcome": "stopped", "stop": "window-exhausted",
                                              "move": "split-goal", "turns": 1}) == [])
control("exhaustion stop", bool(exhaustion_problems({"outcome": "stopped", "stop": None,
                                                     "move": None, "turns": 2})))
good_lines = [{"kind": "run-start", "seq": 1}, {"kind": "request", "seq": 2, "messages_total": 1},
              {"kind": "request", "seq": 3, "messages_total": 3, "sent": False},
              {"kind": "run-start", "seq": 4, "resumed_from": 3},
              {"kind": "request", "seq": 5, "messages_total": 4,
               "appended": [{"role": "user", "content": ANSWER}]}]
control("resume ok", resume_problems({"outcome": "suspended"},
                                     {"command": "resume", "outcome": "ended"}, good_lines) == [])
bad_lines = json.loads(json.dumps(good_lines)); bad_lines[-1]["messages_total"] = 9
control("resume total", bool(resume_problems({"outcome": "suspended"},
                                             {"command": "resume", "outcome": "ended"}, bad_lines)))
bad_lines = json.loads(json.dumps(good_lines)); bad_lines[-1]["appended"][-1]["content"] = "no"
control("resume answer", bool(resume_problems({"outcome": "suspended"},
                                              {"command": "resume", "outcome": "ended"}, bad_lines)))
good_c = ({"outcome": "suspended", "tarball": "/t", "apply_line": "bale apply /t"},
          {"response_kind": "clarification", "questions": [QUESTION]},
          [["apply", "--dry-run", "--json", "/t"]])
control("clarification ok", clarification_problems(*good_c) == [])
control("clarification kind", bool(clarification_problems(good_c[0], {"response_kind": "normal"},
                                                          good_c[2])))
control("clarification dry run", bool(clarification_problems(good_c[0], good_c[1], [])))
control("version", bool(version_problems("0.21.0\n")) and version_problems(VERSION + "\n") == [])
control("docs", bool(docs_problems("", "")) and
        docs_problems("twine resume --window", "window-exhausted resume") == [])

# --- the stub bale, the request tarball, and the runs -------------------------------


def write_stub_bale(base: Path, request_tarball: Path) -> tuple[Path, Path]:
    """An install root twine's gate admits (bin/VERSION at the floor, the
    floor's schemas byte-exact), whose bin/bale replays the recorded lines:
    `open` with its tarball rewritten to ours, `apply --dry-run` as recorded.
    Every call's argv is appended to a calls file."""
    root = base / "root"; (root / "bin").mkdir(parents=True)
    (root / "bin" / "VERSION").write_text(FLOOR + "\n", encoding="utf-8")
    shutil.copytree(SCHEMAS, root / "schemas")
    opened = json.loads(OPEN_LINE.read_text(encoding="utf-8").splitlines()[0])
    opened["tarball"] = str(request_tarball)
    open_file = base / "open.json"; open_file.write_text(json.dumps(opened) + "\n", encoding="utf-8")
    calls = base / "calls"
    bash = shutil.which("bash") or "/bin/bash"
    script = "\n".join([
        f"#!{bash}",
        "# A double written by the R5 checkpoint — not bale.",
        f"(IFS=$'\\t'; printf '%s\\n' \"$*\") >> '{calls}'",
        f"if [ \"$1\" = open ]; then cat '{open_file}'; exit 0; fi",
        f"if [ \"$1\" = apply ]; then cat '{DRY_RUN_LINE}'; exit 0; fi",
        "exit 1", ""])
    exe = root / "bin" / "bale"; exe.write_text(script, encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return root, calls


def write_request(base: Path) -> Path:
    tarball = base / "request-oracle.tar.gz"
    manifest = json.dumps({"session_id": "2026-10-08-sc-002", "goal": "the oracle's request"})
    with tarfile.open(tarball, "w:gz") as tf:
        data = manifest.encode("utf-8")
        info = tarfile.TarInfo("request-001/manifest.json"); info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    return tarball


def twine(args: list[str], cwd: Path) -> dict:
    proc = subprocess.run([sys.executable, "-I", "-B", str(TWINE), *args], cwd=cwd,
                          capture_output=True, text=True, timeout=600)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    try:
        twin = json.loads(lines[0]) if len(lines) == 1 else None
    except ValueError:
        twin = None
    if not isinstance(twin, dict):
        # A verb that printed no twin (an unknown flag, a refusal with no
        # line) is a failed probe, never a broken oracle: name it.
        failures.append(f"twine {' '.join(args[:2])}: no JSON twin on stdout (exit "
                        f"{proc.returncode}; stderr ends {proc.stderr[-300:]!r})")
        return {}
    return twin


def run_case(label: str, script: list, extra: list[str] = ()) -> tuple[dict, Path, Path, Path]:
    """One `twine run` of the fake over `script` in a fresh everything;
    returns the twin, the state dir, the repo and the calls file."""
    base = Path(tempfile.mkdtemp(prefix=f"twine-oracle-{label}-"))
    state = base / "state"; state.mkdir()
    (state / "prices.toml").write_text(PRICES, encoding="utf-8")
    repo = base / "repo"; repo.mkdir()
    tarball = write_request(base)
    root, calls = write_stub_bale(base, tarball)
    script_file = base / "script.json"; script_file.write_text(json.dumps(script), encoding="utf-8")
    twin = twine(["run", "oracle.bale-bundle", "--adapter", "fake", "--script", str(script_file),
                  "--model", "fake", "--cap", "5", "--window", str(WINDOW), "--state-dir",
                  str(state), "--bale-root", str(root), "--cwd", str(repo), "--json", *extra],
                 cwd=repo)
    return twin, state, repo, calls


def transcript_lines(state: Path, sid: str) -> list[dict]:
    path = state / "transcripts" / f"{sid}.jsonl"
    if not sid or not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# (0) the registry
for p in registry_problems(twine(["runtime", "list", "--json"], ROOT)):
    failures.append(f"registry: {p}")

# (a) the warning: the first call's prompt is 850 of 1000; the tool result the
# model reads next carries the line; the second call ends the turn in prose.
# (850 of 1000: the R4 estimate of the appended tool result stays under the rest.)
twin, state, repo, calls = run_case("warn", [tool_turn("list_dir", {}, 850), prose_turn(860)])
results = sent_tool_results(transcript_lines(state, twin.get("sid") or ""))
for p in warning_problems(twin, results):
    failures.append(f"warning: {p}")

# (b) exhaustion: the first call's prompt is the whole window; the second
# call is not made.
twin, state, repo, calls = run_case("exhaust", [tool_turn("list_dir", {}, 1000), prose_turn(1001)])
for p in exhaustion_problems(twin):
    failures.append(f"exhaustion: {p}")

# (c) suspend on escalate, then resume cold with the answer.
twin1, state, repo, calls = run_case(
    "resume", [tool_turn("escalate", {"questions": [QUESTION]}, 10)])
sid = twin1.get("sid") or ""
base = state.parent
script2 = base / "script2.json"; script2.write_text(json.dumps([prose_turn(12)]), encoding="utf-8")
answer = base / "answer.txt"; answer.write_text(ANSWER + "\n", encoding="utf-8")
twin2 = twine(["resume", sid, "--answer", str(answer), "--script", str(script2), "--cap", "5",
               "--state-dir", str(state), "--bale-root", str(base / "root"), "--cwd", str(repo),
               "--json"], cwd=repo)
for p in resume_problems(twin1, twin2, transcript_lines(state, sid)):
    failures.append(f"resume: {p}")

# (d) the clarification form of escalate: a tarball the courier dry-runs.
twin, state, repo, calls = run_case(
    "clarify", [tool_turn("escalate", {"questions": [QUESTION], "blocking": True}, 10)])
manifest = None
tarball = twin.get("tarball")
if tarball and Path(tarball).is_file():
    with tarfile.open(tarball, "r:gz") as tf:
        for member in tf.getmembers():
            if member.name.split("/")[-1] == "manifest.json":
                manifest = json.loads(tf.extractfile(member).read().decode("utf-8"))
                break
bale_calls = [l.split("\t") for l in calls.read_text(encoding="utf-8").splitlines()] \
    if calls.exists() else []
for p in clarification_problems(twin, manifest, bale_calls):
    failures.append(f"clarification: {p}")

# (e) docs and VERSION
cli_doc = (ROOT / "claude" / "context" / "cli-contract.md").read_text(encoding="utf-8")
runtime_doc = (ROOT / "claude" / "context" / "runtime-contract.md").read_text(encoding="utf-8")
for p in docs_problems(cli_doc, runtime_doc):
    failures.append(f"docs: {p}")
for p in version_problems((ROOT / "VERSION").read_text(encoding="utf-8")):
    failures.append(f"version: {p}")

if failures:
    for f in failures:
        print(f"[checkpoint] FAIL {f}")
    sys.exit(1)
print("[checkpoint] PASS: the window is counted, warned and exhausted; a suspended run "
      "resumes cold; escalate's clarification form is a tarball the courier dry-runs; "
      "VERSION " + VERSION)
sys.exit(0)
ORACLE
exit $?

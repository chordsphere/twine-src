#!/usr/bin/env bash
# Blind checkpoint — twine-src session `twine-run-recovery` (the hardening
# wave, 2 of 6), authored at sitting 2026-10-13-open-hardening-011, v3 (2026-10-15: v2's
# probes byte-identical; added the mechanized recovery the architect asked
# for — `twine resume --plan`, `--cap +USD`, and the twin's `next` lines,
# a scope-drift refusal among them; the stub bale's dry run is now chosen per
# case).
#
# Outcome contracts only (PLANNER.md §4), graded through `twine run` and
# `twine resume` with the fake adapter and a stub bale this oracle writes
# itself (replaying the tree's recorded `open` and `apply --dry-run` lines
# under an install root carrying the floor's schemas). Runs from the staged
# tree's root; reads nothing of its own path, sid or manifest. Exit 0: every
# probe holds. Exit 1: a probe fails, named. Exit 2: this oracle is broken
# (a control failed, or an unplanned exception) — the planner's artifact.
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
VERSION = "0.25.0"
RESUME_TEXT = "This session was stopped and has been resumed; continue from where you left off."
MOVES_NAMING_RESUME = ("fix-adapter", "stop-at-cap", "respawn-from-request")
PRICES = '[model."fake"]\ninput = 1\noutput = 2\ncache_read = 0.1\ncache_write = 1.25\n'
QUESTION = {"question": "Which seam?", "while_doing": "the oracle's rehearsal",
            "would_assume": "the first", "why_blocked": "the brief names two"}
MANIFEST = tomllib.loads((ROOT / "share" / "bale-consumption.toml").read_text(encoding="utf-8"))
RECORDINGS = MANIFEST["bale"]["recordings"]
CONTRACT_LINE = ROOT / MANIFEST["bale"]["contract"]
OPEN_LINE = ROOT / "fixtures" / f"bale-{RECORDINGS}" / "scratch" / "open_bundle_--json+opened.json"
DRY_RUN_LINE = ROOT / "fixtures" / f"bale-{RECORDINGS}" / "scratch" / \
    "apply_--dry-run_--json_tarball+dry-run.json"
DRIFT_LINE = ROOT / "fixtures" / f"bale-{RECORDINGS}" / "scratch" / \
    "apply_--dry-run_--json_tarball+scope-drift-refused.json"
PLAN_KEYS = ("plan", "sid", "outcome", "stop", "move", "actor", "resumable", "why", "window",
             "calls", "spend_usd", "per_call_usd", "next_call_worst_usd", "suggested_cap_usd",
             "last_tools", "home", "next", "reason")
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


def stop_turn(stop: str, input_tokens: int) -> dict:
    return {"stop": stop, "usage": usage(input_tokens), "reason": "the oracle's scripted stop"}


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("`", "").replace("*", "")).strip().lower()


# --- detectors ------------------------------------------------------------------

def spent_cap_problems(twin: dict, spend_before: int, spend_after: int) -> list[str]:
    out = []
    if twin.get("outcome") != "cap-reached":
        out.append(f"a cap-reached run resumed under the same cap ends {twin.get('outcome')!r}, "
                   "want 'cap-reached'")
    if twin.get("turns") != 0:
        out.append(f"… with turns {twin.get('turns')!r}, want 0")
    if spend_after != spend_before:
        out.append(f"… and spend.jsonl grew from {spend_before} to {spend_after} lines")
    return out


def raised_cap_problems(twin: dict) -> list[str]:
    out = []
    if twin.get("outcome") != "ended":
        out.append(f"a cap-reached run resumed under a raised cap ends {twin.get('outcome')!r}, "
                   "want 'ended' (its next call made)")
    if twin.get("turns") != 1:
        out.append(f"… with turns {twin.get('turns')!r}, want 1")
    return out


def resume_text_problems(twin: dict, lines: list[dict]) -> list[str]:
    out = []
    if twin.get("outcome") != "ended":
        out.append(f"a stopped run resumed with no --answer ends {twin.get('outcome')!r}, "
                   "want 'ended'")
    starts = [i for i, l in enumerate(lines) if l.get("kind") == "run-start"]
    if len(starts) != 2:
        return out + [f"{len(starts)} run-start line(s), want 2"]
    req = [l for l in lines[starts[1]:] if l.get("kind") == "request"]
    if not req:
        return out + ["the resumed run wrote no request line"]
    appended = req[0].get("appended") or []
    last = appended[-1] if appended else {}
    content = last.get("content")
    text = content if isinstance(content, str) else \
        "".join(b.get("text", "") for b in content if isinstance(b, dict)) \
        if isinstance(content, list) else ""
    if last.get("role") != "user" or text != RESUME_TEXT:
        out.append("the resumed run's first request does not end with RESUME_TEXT, byte for "
                   f"byte, as a user turn (got {text[:80]!r})")
    return out


def suspended_refusal_problems(twin: dict) -> list[str]:
    return [] if twin.get("outcome") == "refused" else \
        [f"a suspended run resumed with no --answer is {twin.get('outcome')!r}, want 'refused'"]


def move_problems(table: dict) -> list[str]:
    out = []
    moves = table.get("move") or {}
    for name in MOVES_NAMING_RESUME:
        text = fold(str((moves.get(name) or {}).get("description", "")))
        if "twine resume" not in text:
            out.append(f"[move.{name}]'s description does not name `twine resume`")
    return out


def readme_problems(text: str) -> list[str]:
    out = []
    folded = fold(text)
    if "twine resume" not in folded:
        out.append("README.md never names `twine resume`")
    if "sixteen" not in folded:
        out.append("README.md does not say the stop set has sixteen keys")
    return out


def version_problems(text: str) -> list[str]:
    return [] if text.strip() == VERSION else [f"VERSION is {text.strip()!r}, want {VERSION!r}"]


def plan_problems(plan: dict, sid: str) -> list[str]:
    out = []
    if plan.get("ok") is not True:
        return [f"--plan is not ok: {plan.get('reason')!r}"]
    keys = [k for k in plan if k not in ("command", "ok")]
    if tuple(keys) != PLAN_KEYS:
        return [f"--plan's keys are {keys}, want exactly {list(PLAN_KEYS)} after command, ok"]
    if plan["plan"] is not True or plan["resumable"] is not True:
        out.append(f"--plan says plan {plan['plan']!r}, resumable {plan['resumable']!r}; want true, true")
    spend, worst, cap = plan["spend_usd"], plan["next_call_worst_usd"], plan["suggested_cap_usd"]
    if not all(isinstance(v, (int, float)) for v in (spend, worst, cap)):
        return out + [f"--plan's spend {spend!r}, next-call worst {worst!r}, cap {cap!r} are not all numbers"]
    if spend <= 0:
        out.append(f"--plan's spend_usd {spend!r}, want the session's positive spend")
    if not cap > spend + worst:
        out.append(f"suggested_cap_usd {cap} is not above spend {spend} + next call's worst {worst}")
    nxt = plan["next"]
    if not (isinstance(nxt, list) and nxt and str(nxt[0]).startswith(f"twine resume {sid}")
            and "--cap" in str(nxt[0])):
        out.append(f"--plan's next is {nxt!r}, want first a `twine resume {sid} … --cap …` line")
    return out


def plus_cap_problems(twin: dict, spend_before: float) -> list[str]:
    out = []
    if twin.get("outcome") != "ended" or twin.get("turns") != 1:
        out.append(f"`--cap +5` resumes to {twin.get('outcome')!r} with turns {twin.get('turns')!r}; "
                   "want 'ended', 1")
    cap = twin.get("cap_usd")
    if not isinstance(cap, (int, float)) or abs(cap - (spend_before + 5)) > 0.01:
        out.append(f"`--cap +5`'s cap_usd is {cap!r}, want the spend so far ({spend_before}) + 5")
    return out


def drift_next_problems(twin: dict) -> list[str]:
    if twin.get("outcome") != "stopped":
        return [f"a delivery refused scope-drift ends {twin.get('outcome')!r}, want 'stopped'"]
    nxt = twin.get("next")
    if not isinstance(nxt, list):
        return [f"the twin's next is {nxt!r}, want a list of commands"]
    if not any(str(c).startswith("bale apply ") and "--allow-out-of-scope" in str(c) for c in nxt):
        return [f"next names no `bale apply … --allow-out-of-scope …` line: {nxt!r}"]
    return []


# --- controls (exit 2 when a detector does not fire) ------------------------------

def control(name: str, ok: bool) -> None:
    if not ok:
        sys.stderr.write(f"[checkpoint] BROKEN: control {name} did not fire\n")
        sys.exit(2)


control("spent cap", spent_cap_problems({"outcome": "cap-reached", "turns": 0}, 2, 2) == []
        and bool(spent_cap_problems({"outcome": "ended", "turns": 1}, 2, 3)))
control("raised cap", raised_cap_problems({"outcome": "ended", "turns": 1}) == []
        and bool(raised_cap_problems({"outcome": "cap-reached", "turns": 0})))
good_lines = [{"kind": "run-start"}, {"kind": "request", "appended": [{"role": "user", "content": "x"}]},
              {"kind": "run-start"}, {"kind": "request", "appended": [{"role": "user", "content": RESUME_TEXT}]}]
control("resume text ok", resume_text_problems({"outcome": "ended"}, good_lines) == [])
bad_lines = json.loads(json.dumps(good_lines)); bad_lines[-1]["appended"][-1]["content"] = RESUME_TEXT + " "
control("resume text bytes", bool(resume_text_problems({"outcome": "ended"}, bad_lines)))
control("suspended refusal", suspended_refusal_problems({"outcome": "refused"}) == []
        and bool(suspended_refusal_problems({"outcome": "ended"})))
good_table = {"move": {n: {"description": "the operator resumes it with `twine resume`"} for n in MOVES_NAMING_RESUME}}
control("moves ok", move_problems(good_table) == [])
bad_table = json.loads(json.dumps(good_table)); bad_table["move"]["stop-at-cap"]["description"] = "rerun"
control("moves missing", bool(move_problems(bad_table)))
control("readme", readme_problems("twine resume; sixteen keys") == [] and bool(readme_problems("")))
control("version", version_problems(VERSION + "\n") == [] and bool(version_problems("0.24.0\n")))
good_plan = {"command": "resume", "ok": True, **{k: None for k in PLAN_KEYS}}
good_plan.update({"plan": True, "resumable": True, "spend_usd": 0.05, "next_call_worst_usd": 0.07,
                  "suggested_cap_usd": 0.5, "next": ["twine resume s1 --cap 0.50"]})
control("plan ok", plan_problems(good_plan, "s1") == [])
control("plan cap", bool(plan_problems({**good_plan, "suggested_cap_usd": 0.1}, "s1")))
control("plan next", bool(plan_problems({**good_plan, "next": []}, "s1")))
control("plan keys", bool(plan_problems({k: v for k, v in good_plan.items() if k != "why"}, "s1")))
control("plus cap", plus_cap_problems({"outcome": "ended", "turns": 1, "cap_usd": 5.05}, 0.05) == []
        and bool(plus_cap_problems({"outcome": "ended", "turns": 1, "cap_usd": 5.0}, 0.05)))
control("drift next", drift_next_problems({"outcome": "stopped", "next": [
    "bale apply /t.tar.gz --allow-out-of-scope README.md", "twine resume s1 --cap 1"]}) == []
        and bool(drift_next_problems({"outcome": "stopped", "next": ["twine resume s1"]})))

# --- the stub bale, the request tarball, and the runs -------------------------------


def write_stub_bale(base: Path, request_tarball: Path, dry_run: Path = DRY_RUN_LINE,
                    dry_exit: int = 0) -> tuple[Path, Path]:
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
        "# A double written by the recovery checkpoint — not bale.",
        f"(IFS=$'\\t'; printf '%s\\n' \"$*\") >> '{calls}'",
        f"if [ \"$1\" = open ]; then cat '{open_file}'; exit 0; fi",
        f"if [ \"$1\" = apply ]; then cat '{dry_run}'; exit {dry_exit}; fi",
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


def run_case(label: str, script: list, extra: list[str] = (), dry_run: Path = DRY_RUN_LINE,
             dry_exit: int = 0) -> tuple[dict, str, Path]:
    base = Path(tempfile.mkdtemp(prefix=f"twine-oracle-{label}-"))
    state = base / "state"; state.mkdir()
    (state / "prices.toml").write_text(PRICES, encoding="utf-8")
    repo = base / "repo"; repo.mkdir()
    tarball = write_request(base)
    root, calls = write_stub_bale(base, tarball, dry_run, dry_exit)
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




def spend_lines(state: Path) -> int:
    path = state / "spend.jsonl"
    return len([l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]) \
        if path.is_file() else 0


def resume(sid: str, state: Path, script: list, extra: list[str]) -> tuple[dict, str]:
    base = state.parent
    script_file = base / f"script-{len(list(base.glob('script-*.json')))}.json"
    script_file.write_text(json.dumps(script), encoding="utf-8")
    return twine(["resume", sid, "--script", str(script_file), "--state-dir", str(state),
                  "--bale-root", str(base / "root"), "--cwd", str(base / "repo"), "--json",
                  *extra], cwd=base / "repo")


# (a) a cap-reached run: resumed under the same cap, then under a raised one
twin, err, state = run_case("cap", [prose_turn(10)], ["--cap", "0.000001"])
sid = twin.get("sid") or ""
if twin.get("outcome") != "cap-reached":
    failures.append(f"cap: the oracle's tiny-cap run ends {twin.get('outcome')!r}, not "
                    "'cap-reached' (its ground is the R4 loop; see the run's reason: "
                    f"{str(twin.get('reason'))[:200]!r})")
else:
    answer = state.parent / "answer.txt"; answer.write_text("go on\n", encoding="utf-8")
    before = spend_lines(state)
    same, _ = resume(sid, state, [prose_turn(12)], ["--cap", "0.000001", "--answer", str(answer)])
    for p in spent_cap_problems(same, before, spend_lines(state)):
        failures.append(f"spent cap: {p}")
    raised, _ = resume(sid, state, [prose_turn(12)], ["--cap", "5", "--answer", str(answer)])
    for p in raised_cap_problems(raised):
        failures.append(f"raised cap: {p}")

# (b) a stopped run resumed with no --answer: RESUME_TEXT is the next user turn
twin, err, state = run_case("stopped", [stop_turn("malformed-shape", 10)])
sid = twin.get("sid") or ""
if twin.get("outcome") != "stopped":
    failures.append(f"stopped: the oracle's scripted malformed-shape run ends "
                    f"{twin.get('outcome')!r}, not 'stopped'")
else:
    resumed, _ = resume(sid, state, [prose_turn(12)], ["--cap", "5"])
    for p in resume_text_problems(resumed, transcript_lines(state, sid)):
        failures.append(f"resume text: {p}")

# (c) a suspended run resumed with no --answer refuses
twin, err, state = run_case("susp", [tool_turn("escalate", {"questions": [QUESTION]}, 10)])
sid = twin.get("sid") or ""
if twin.get("outcome") != "suspended":
    failures.append(f"suspended: the oracle's escalate run ends {twin.get('outcome')!r}, not "
                    "'suspended'")
else:
    refused, _ = resume(sid, state, [prose_turn(12)], ["--cap", "5"])
    for p in suspended_refusal_problems(refused):
        failures.append(f"suspended refusal: {p}")

# (e) --plan on a run the cap stopped after one costly call, then its own next line's cap
twin, err, state = run_case("plan", [tool_turn("list_dir", {}, 50000), prose_turn(12)], ["--cap", "0.10"])
sid = twin.get("sid") or ""
if twin.get("outcome") != "cap-reached" or twin.get("turns") != 1:
    failures.append(f"plan: the oracle's 0.10-cap run ends {twin.get('outcome')!r} after "
                    f"{twin.get('turns')!r} call(s), not cap-reached after 1 (its ground is the "
                    "pre-call check)")
else:
    plan, _ = twine(["resume", sid, "--plan", "--state-dir", str(state), "--json"],
                    cwd=state.parent / "repo")
    problems = plan_problems(plan, sid)
    for p in problems:
        failures.append(f"plan: {p}")
    if not problems:
        cap = str(plan["suggested_cap_usd"])
        resumed, _ = resume(sid, state, [prose_turn(12)], ["--cap", cap])
        if resumed.get("outcome") != "ended" or resumed.get("turns") != 1:
            failures.append(f"plan: resumed under its suggested cap {cap}, the run ends "
                            f"{resumed.get('outcome')!r} with turns {resumed.get('turns')!r}; "
                            "want 'ended', 1 (the next call admitted)")

# (f) --cap +5 on another such run
twin, err, state = run_case("plus", [tool_turn("list_dir", {}, 50000), prose_turn(12)], ["--cap", "0.10"])
sid = twin.get("sid") or ""
if twin.get("outcome") == "cap-reached":
    spent = 0.0
    for raw in (state / "spend.jsonl").read_text(encoding="utf-8").splitlines():
        t = (json.loads(raw).get("tokens") or {})
        spent += ((t.get("input") or 0) * 1 + (t.get("output") or 0) * 2
                  + (t.get("thinking") or 0) * 2 + (t.get("cache_read") or 0) * 0.1
                  + (t.get("cache_write") or 0) * 1.25) / 1_000_000
    plus, _ = resume(sid, state, [prose_turn(12)], ["--cap", "+5"])
    for p in plus_cap_problems(plus, spent):
        failures.append(f"cap +: {p}")

# (g) a delivery the dry run refuses scope-drift: next names bale's admit line
if not DRIFT_LINE.is_file():
    failures.append(f"drift: {DRIFT_LINE.relative_to(ROOT)} (the tree's recording) is missing")
else:
    make = "printf 'x\\n' > out.txt && tar czf response-oracle.tar.gz out.txt"
    twin, err, state = run_case("drift", [tool_turn("shell", {"command": make}, 20),
                                          tool_turn("deliver", {"tarball": "response-oracle.tar.gz"}, 30)],
                                dry_run=DRIFT_LINE, dry_exit=1)
    for p in drift_next_problems(twin):
        failures.append(f"drift: {p}")

# (d) the table's descriptions, the README, VERSION
table = tomllib.loads((ROOT / "share" / "transitions.toml").read_text(encoding="utf-8"))
for p in move_problems(table):
    failures.append(f"table: {p}")
for p in readme_problems((ROOT / "README.md").read_text(encoding="utf-8")):
    failures.append(f"readme: {p}")
for p in version_problems((ROOT / "VERSION").read_text(encoding="utf-8")):
    failures.append(f"version: {p}")

if failures:
    for f in failures:
        print(f"[checkpoint] FAIL {f}")
    sys.exit(1)
print("[checkpoint] PASS: a capped run resumes under a raised cap and not under a spent one, a "
      "stopped run resumes on RESUME_TEXT, a suspended one still needs its answer, --plan reads "
      "the session and suggests a cap that admits the next call, --cap +USD adds to the spend, a "
      f"drift refusal names bale's admit line, the table and the README say resume; VERSION {VERSION}")
sys.exit(0)
ORACLE
exit $?

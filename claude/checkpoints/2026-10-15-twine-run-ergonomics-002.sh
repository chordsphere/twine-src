#!/usr/bin/env bash
# Blind checkpoint — twine-src session `twine-run-ergonomics` (the hardening
# wave, 1 of 6), authored at sitting 2026-10-13-open-hardening-011, v2 (2026-10-15: the
# stub bale answers `contract --json` from the tree's carried line, and the
# recordings are found through the manifest's `recordings`, for the contract
# gate twine-gate-contract lands first; nothing else changed).
#
# Outcome contracts only (PLANNER.md §4), graded through the verbs' surfaces
# — `twine run` with the fake adapter and a stub bale this oracle writes
# itself (a bash script that replays the tree's own recorded `open` and
# `apply --dry-run` lines, under an install root carrying the floor's
# schemas, so twine's gate admits it) — and the Anthropic reader read
# directly with a specimen derived from the tree's recorded max_tokens
# stream. Runs from the staged tree's root; reads nothing of its own path,
# sid or manifest; the floor it uses is the tree's own. Exit 0: every probe
# holds. Exit 1: a probe fails, named. Exit 2: this oracle is broken (a
# control failed, or an unplanned exception) — the planner's artifact.
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
sys.path.insert(0, str(ROOT))
failures: list[str] = []

# --- the pins the brief carries ---------------------------------------------
VERSION = "0.24.0"
MAX_TOKENS_DEFAULT = 32000
CONTENT_CAP = 32768
CUT_MARK = f"cut at {CONTENT_CAP} bytes"
WINDOW = 1000
MARKER = "rig-marker-xyz"
HEARTBEAT_WORDS = "still running"
NOTE_STEMS = (("list", "first"), ("range",), ("in parts",), ("background",),
              ("lint", "judge"), ("window",), ("blocking",))
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
STREAM = ROOT / "fixtures" / "anthropic" / "max_tokens_stream.response.sse"


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


def derived_stream() -> bytes:
    """The recorded max_tokens stream with its content_block_stop event
    removed: the block is still open at message_stop. A derived specimen,
    not a recording."""
    text = STREAM.read_text(encoding="utf-8")
    events = text.split("\n\n")
    kept = [e for e in events if '"type":"content_block_stop"' not in e]
    if len(kept) != len(events) - 1:
        raise RuntimeError("the recorded stream has no single content_block_stop to remove")
    return "\n\n".join(kept).encode("utf-8")


# --- detectors ------------------------------------------------------------------

def reader_problems(stop, text: str) -> list[str]:
    out = []
    if stop != "max-tokens":
        out.append(f"a stream ending inside a block with stop_reason max_tokens reads as "
                   f"{stop!r}, want 'max-tokens'")
    if "Rope is made" not in (text or ""):
        out.append("the open text block was not carried as far as it got")
    return out


def max_tokens_problems(run_start: dict) -> list[str]:
    got = run_start.get("max_tokens")
    return [] if got == MAX_TOKENS_DEFAULT else \
        [f"run-start max_tokens is {got!r} with no --max-tokens given, want {MAX_TOKENS_DEFAULT}"]


def cap_problems(sent: list[tuple[str, bool]]) -> list[str]:
    """`sent`: (content, is_error) of every tool_result the model read."""
    big = [(c, e) for c, e in sent if "x" * 1000 in c]
    if not big:
        return ["no tool result carrying the 40 KB stdout reached the model"]
    content, is_error = big[0]
    out = []
    if len(content.encode("utf-8")) > CONTENT_CAP + 400:
        out.append(f"the shell result the model read is {len(content)} chars; want at most "
                   f"{CONTENT_CAP} plus a marker")
    if CUT_MARK not in content:
        out.append(f"the cut shell result does not carry the marker {CUT_MARK!r}")
    if is_error:
        out.append("a completed command whose stdout was cut is marked is_error")
    return out


def progress_problems(stderr: str, *, want_window: bool) -> list[str]:
    out = []
    lines = [l for l in stderr.splitlines() if l.startswith("[twine] ")]
    call_lines = [l for l in lines if re.search(r"\bcall \d+:", l)]
    if not any(re.search(r"\$\d+\.\d{2,}", l) and re.search(r"\b\d+s\b", l) for l in call_lines):
        out.append("no `call N:` line carries the cost so far ($n.nn) and the elapsed time (ns)")
    if want_window and not any(re.search(rf"window \d+ of {WINDOW}\b", l) for l in call_lines):
        out.append(f"no `call N:` line carries `window <used> of {WINDOW}`")
    if not any(MARKER in l for l in lines if "tool" in l):
        out.append("no tool line carries what the tool ran (the shell command)")
    summary = [l for l in lines if re.search(r"\bsummary:", l)]
    if not summary:
        out.append("no `summary:` line")
    else:
        s = summary[-1]
        if lines[-1] != s:
            out.append("the summary is not the last progress line")
        for word in ("call", "tool", "retr", "$"):
            if word not in s:
                out.append(f"the summary line lacks {word!r}")
        if not re.search(r"\b\d+s\b", s):
            out.append("the summary line lacks the wall time (ns)")
    return out


def heartbeat_problems(stderr: str) -> list[str]:
    beats = [l for l in stderr.splitlines() if HEARTBEAT_WORDS in l]
    return [] if beats else [f"no heartbeat line ({HEARTBEAT_WORDS!r}) while a tool ran 33 s"]


def note_problems(note: str) -> list[str]:
    folded = fold(note)
    missing = [stems for stems in NOTE_STEMS if not all(s in folded for s in stems)]
    return [f"the surface note lacks {' and '.join(repr(s) for s in stems)}" for stems in missing]


def block_problems(twin: dict, sid: str) -> list[str]:
    out = []
    if twin.get("outcome") != "suspended":
        out.append(f"clarification form: outcome {twin.get('outcome')!r}, want 'suspended'")
    block = twin.get("block")
    if not isinstance(block, str) or "BALE EXCHANGE BEGIN" not in block:
        return out + ["the clarification form's twin carries no exchange paste block in `block`"]
    if sid and sid not in block:
        out.append("the exchange block does not name the session")
    if not twin.get("tarball"):
        out.append("the clarification form's twin names no tarball")
    return out


def version_problems(text: str) -> list[str]:
    return [] if text.strip() == VERSION else [f"VERSION is {text.strip()!r}, want {VERSION!r}"]


def docs_problems(cli_doc: str, runtime_doc: str) -> list[str]:
    out = []
    if "32000" not in fold(cli_doc):
        out.append("cli-contract.md never names the 32000 default")
    if ".raw" not in runtime_doc:
        out.append("runtime-contract.md never names the kept raw stream (.raw)")
    if "32" not in fold(runtime_doc) or "kib" not in fold(runtime_doc):
        out.append("runtime-contract.md does not state shell's 32 KiB content cap")
    return out


# --- controls (exit 2 when a detector does not fire) ------------------------------

def control(name: str, ok: bool) -> None:
    if not ok:
        sys.stderr.write(f"[checkpoint] BROKEN: control {name} did not fire\n")
        sys.exit(2)


control("reader", reader_problems("max-tokens", "Rope is made") == []
        and bool(reader_problems("malformed-shape", "Rope is made")))
control("max_tokens", max_tokens_problems({"max_tokens": 32000}) == []
        and bool(max_tokens_problems({"max_tokens": 16000})))
good_cut = "x" * 32768 + f"\n[stdout {CUT_MARK} of 40000; read it in parts]\n[exit 0]"
control("cap ok", cap_problems([("hi", False), (good_cut, False)]) == [])
control("cap uncut", bool(cap_problems([("x" * 40000 + "\n[exit 0]", False)])))
control("cap error", bool(cap_problems([(good_cut, True)])))
good_err = "\n".join(["[twine] run: call 1: asks for shell — $0.0012 so far, 3s elapsed, window 850 of 1000",
                      f"[twine] run: call 1: tool shell: ok — echo {MARKER}",
                      "[twine] run: summary: ended, 2 calls, 1 tool call, 0 retries, $0.0020, 4s"])
control("progress ok", progress_problems(good_err, want_window=True) == [])
control("progress cost", bool(progress_problems(good_err.replace("$0.0012 so far, 3s elapsed", ""),
                                                 want_window=True)))
control("progress window", bool(progress_problems(good_err.replace("window 850 of 1000", ""),
                                                   want_window=True)))
control("progress tool", bool(progress_problems(good_err.replace(MARKER, ""), want_window=True)))
control("progress summary", bool(progress_problems(good_err.rsplit("\n", 1)[0], want_window=True)))
control("heartbeat", heartbeat_problems("[twine] run: call 1: tool shell still running (30s)") == []
        and bool(heartbeat_problems("[twine] run: call 1: tool shell: ok")))
good_note = ("List your home first. Read ranges, never whole files. Write large files in parts. "
             "Never background a command. The lint judges the manifest. The window line; "
             "escalate's blocking form.")
control("note stems", bool(note_problems("list_dir reads request/manifest.json; response_lint.py")))
control("note ok", note_problems(good_note) == [])
control("note missing", bool(note_problems(good_note.replace("in parts", "whole"))))
control("block ok", block_problems({"outcome": "suspended", "block": "BALE EXCHANGE BEGIN s1\n…",
                                    "tarball": "/t"}, "s1") == [])
control("block null", bool(block_problems({"outcome": "suspended", "block": None, "tarball": "/t"}, "s1")))
control("version", version_problems(VERSION + "\n") == [] and bool(version_problems("0.23.0\n")))
control("docs", docs_problems("--max-tokens 32000", "the .raw file; 32 KiB") == []
        and bool(docs_problems("", "")))

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
        "# A double written by the ergonomics checkpoint — not bale.",
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


# (a) the reader, with the derived specimen
try:
    from twine.runtime.adapters.anthropic import read_stream
    outcome = read_stream(200, {}, [derived_stream()])
    for p in reader_problems(getattr(outcome, "stop", None), getattr(outcome, "text", "")):
        failures.append(f"reader: {p}")
except Exception as exc:   # the code under test crashed: the work's failure
    failures.append(f"reader: read_stream raised {type(exc).__name__}: {exc}")

# (b) one run: the big stdout, the marker, the default ceiling, the progress lines
big = f"echo {MARKER}; head -c 40000 /dev/zero | tr '\\0' x"
twin, err, state = run_case("ergo", [tool_turn("shell", {"command": big}, 850), prose_turn(860)],
                            ["--window", str(WINDOW)])
lines = transcript_lines(state, twin.get("sid") or "")
starts = [l for l in lines if l.get("kind") == "run-start"]
for p in max_tokens_problems(starts[0] if starts else {}):
    failures.append(f"max-tokens: {p}")
for p in cap_problems(sent_tool_results(lines)):
    failures.append(f"shell cap: {p}")
for p in progress_problems(err, want_window=True):
    failures.append(f"progress: {p}")
note = ((starts[0].get("system") or {}).get("note") if starts else None) or ""
for p in note_problems(note):
    failures.append(f"note: {p}")

# (c) the heartbeat: a tool that runs 33 seconds
twin, err, state = run_case("beat", [tool_turn("shell", {"command": "sleep 33"}, 10), prose_turn(12)])
for p in heartbeat_problems(err):
    failures.append(f"heartbeat: {p}")

# (d) the clarification form carries its paste block
if "craft_response.py" not in crafter_copies():
    failures.append("block: the tree holds no craft_response.py under tests/ for the oracle's "
                    "request to carry")
twin, err, state = run_case("clarify",
                            [tool_turn("escalate", {"questions": [QUESTION], "blocking": True}, 10)])
for p in block_problems(twin, twin.get("sid") or ""):
    failures.append(f"block: {p}")

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
print("[checkpoint] PASS: the reader continues a cut turn, the model reads 32 KiB of a shell's "
      "stdout, the operator reads cost, time, tools, heartbeats and a summary, the note says "
      f"what it must, the clarification form carries its block; VERSION {VERSION}")
sys.exit(0)
ORACLE
exit $?

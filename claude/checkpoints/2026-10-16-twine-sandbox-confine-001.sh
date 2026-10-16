#!/usr/bin/env bash
# Blind checkpoint — twine-src session `twine-sandbox-confine` (the hardening
# wave, 4 of 6), authored at sitting 2026-10-13-open-hardening-011, v1.
#
# Outcome contracts only (PLANNER.md §4), graded through `twine run` with the
# fake adapter against a stub bale this oracle writes itself (replaying the
# tree's recorded `open` and `apply --dry-run` lines and its carried contract
# line), and through `twine sandbox prune`. Runs from the staged tree's root;
# reads nothing of its own path, sid or manifest. The cage's outcomes are
# graded on the branch this environment takes: where `unshare -rnmpf
# --mount-proc true` succeeds the cage must confine; where it fails the
# sandbox must say so. Exit 0: every probe holds. Exit 1: a probe fails,
# named. Exit 2: this oracle is broken (a control failed, or an unplanned
# exception) — the planner's artifact.
set -u
export PYTHONDONTWRITEBYTECODE=1
python3 -I -B - <<'ORACLE'
import io, json, os, re, secrets, shlex, shutil, signal, stat, subprocess, sys, tarfile, \
    tempfile, time, tomllib
from pathlib import Path


def broken(exc_type, exc, tb):
    sys.stderr.write(f"[checkpoint] BROKEN: {exc_type.__name__}: {exc}\n")
    sys.exit(2)


sys.excepthook = broken
ROOT = Path.cwd()
failures: list[str] = []

# --- the pins the brief carries ---------------------------------------------
VERSION = "0.27.0"
PRUNE_KEYS = ("dry_run", "state_dir", "cwd", "pruned", "kept", "freed_bytes", "reason")
PROBES = ("read_outside", "read_repo", "write_outside", "write_home", "procs", "python",
          "background")
NAMESPACES = ("unshare", "-rnmpf", "--mount-proc", "true")
SLEEP_ARGV = b"sleep\x003017\x00"
PRICES = '[model."fake"]\ninput = 1\noutput = 2\ncache_read = 0.1\ncache_write = 1.25\n'
PRICES_MARK = "cache_write = 1.25"
MANIFEST = tomllib.loads((ROOT / "share" / "bale-consumption.toml").read_text(encoding="utf-8"))
RECORDINGS = MANIFEST["bale"]["recordings"]
CONTRACT_LINE = ROOT / MANIFEST["bale"]["contract"]
OPEN_LINE = ROOT / "fixtures" / f"bale-{RECORDINGS}" / "scratch" / "open_bundle_--json+opened.json"
DRY_RUN_LINE = ROOT / "fixtures" / f"bale-{RECORDINGS}" / "scratch" / \
    "apply_--dry-run_--json_tarball+dry-run.json"
TWINE = ROOT / "bin" / "twine"
# The prune bed: five homes; bale records for four, under an agent_dir of the repo's own.
AGENT_DIR = "oracle-agent"
P_APPLIED, P_HELD, P_NONE, P_INFLIGHT, P_ROLLED = (
    "2026-10-15-oracle-applied-001", "2026-10-15-oracle-held-002", "2026-10-15-oracle-none-003",
    "2026-10-15-oracle-inflight-004", "2026-10-15-oracle-rolled-005")
PRUNE_ATTEMPTS = {P_APPLIED: ["opened", "applied"], P_HELD: ["opened", "held"],
                  P_INFLIGHT: ["opened", "applied"], P_ROLLED: ["opened", "applied", "rolled-back"]}
WANT_PRUNED = [P_APPLIED]
WANT_KEPT = sorted([P_HELD, P_NONE, P_INFLIGHT, P_ROLLED])
HOME_BYTES = 4096


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

def sandbox_problems(sb, twin: dict, can: bool) -> list[str]:
    """The run-start line's sandbox and the run twin report the filesystem
    rule honestly, on the branch this environment takes."""
    if not isinstance(sb, dict):
        return [f"the transcript's run-start line carries no sandbox object ({sb!r})"]
    if "filesystem" not in sb:
        return [f"the sandbox reports no filesystem (keys {sorted(sb)})"]
    out = []
    if can:
        if sb["filesystem"] != "confined":
            out.append(f"filesystem is {sb['filesystem']!r} (reason "
                       f"{str(sb.get('filesystem_reason'))[:200]!r}) where `{' '.join(NAMESPACES)}` "
                       "succeeds here; want \"confined\"")
        if sb.get("confines") is not True:
            out.append(f"confines is {sb.get('confines')!r} where the namespaces can be made; want true")
        if "filesystem_reason" in sb:
            out.append("a confined sandbox carries filesystem_reason (absent when confined)")
        if sb.get("network") != "off":
            out.append(f"network is {sb.get('network')!r}; want \"off\"")
    else:
        if sb["filesystem"] != "unconfined":
            out.append(f"filesystem is {sb['filesystem']!r} where `{' '.join(NAMESPACES)}` fails here; "
                       "want \"unconfined\"")
        if not (isinstance(sb.get("filesystem_reason"), str) and sb["filesystem_reason"].strip()):
            out.append("an unconfined filesystem carries no filesystem_reason")
        if sb.get("confines") is not False:
            out.append(f"confines is {sb.get('confines')!r} with the filesystem unconfined; want false")
    if twin.get("filesystem") != sb["filesystem"]:
        out.append(f"the run twin's filesystem is {twin.get('filesystem', '<absent>')!r}, want the "
                   f"sandbox's {sb['filesystem']!r}")
    if list(twin)[-1:] != ["next"]:
        out.append(f"the run twin's last name is {list(twin)[-1:]!r}, want next")
    return out


def cage_problems(results: dict, host: dict, can: bool) -> list[str]:
    """What the `shell` calls saw from inside, and what the host saw after."""
    missing = [p for p in PROBES if p not in results]
    if missing:
        return [f"no tool result came back for the {', '.join(missing)} call(s)"]
    out = []
    if host["home_files"] != [True, True]:
        out.append(f"writes to $HOME/inside.txt and (from /) $HOME/inside2.txt landed "
                   f"{host['home_files']} in the sandbox home; want both")
    if "py-ok" not in results["python"]:
        out.append(f"python3 did not run in the cage: {results['python'][-200:]!r}")
    if not can:
        return out
    if host["secret"] in results["read_outside"]:
        out.append("a file outside the home (beside the state directory) was readable from the cage")
    if PRICES_MARK in results["read_outside"]:
        out.append("the state directory's prices.toml was readable from the cage")
    if host["repo_mark"] in results["read_repo"]:
        out.append("the repository the run was opened in was listable from the cage")
    for path in host["escaped"]:
        out.append(f"a write from the cage reached the host at {path}")
    if host["marker"] in results["procs"]:
        out.append("a host process was visible in the cage's /proc")
    m = re.search(r"count=(\d+)", results["procs"])
    if m is None or int(m.group(1)) < 1:
        out.append(f"the cage's /proc lists no process at all: {results['procs'][-200:]!r}")
    if host["survivors"]:
        out.append(f"{host['survivors']} process(es) a shell call backgrounded (setsid sleep 3017) "
                   "outlived the call")
    return out


def prune_problems(twin: dict, exists: dict, *, dry_run: bool) -> list[str]:
    """`twine sandbox prune`: the twin's keys and verdicts, and what is on disk after."""
    label = "--dry-run" if dry_run else "prune"
    if twin.get("ok") is not True:
        return [f"{label}: ok {twin.get('ok')!r} ({str(twin.get('reason'))[:200]!r})"]
    keys = [k for k in twin if k not in ("command", "ok")]
    if tuple(keys) != PRUNE_KEYS or list(twin)[:2] != ["command", "ok"]:
        return [f"{label}: keys are {list(twin)}, want command, ok, then exactly {list(PRUNE_KEYS)}"]
    out = []
    if twin["command"] != "sandbox prune":
        out.append(f"{label}: command is {twin['command']!r}, want 'sandbox prune'")
    if twin["dry_run"] is not dry_run:
        out.append(f"{label}: dry_run is {twin['dry_run']!r}, want {dry_run}")
    if twin["pruned"] != WANT_PRUNED:
        out.append(f"{label}: pruned is {twin['pruned']!r}, want {WANT_PRUNED}")
    kept = twin["kept"]
    if not isinstance(kept, list) or [k.get("sid") if isinstance(k, dict) else k for k in kept] != WANT_KEPT:
        out.append(f"{label}: kept is {kept!r}, want the sids {WANT_KEPT} in order")
    elif any(not (isinstance(k, dict) and list(k) == ["sid", "why"] and isinstance(k["why"], str)
                  and k["why"].strip()) for k in kept):
        out.append(f"{label}: a kept entry is not {{sid, why}} with a reason: {kept!r}")
    if isinstance(twin["freed_bytes"], bool) or not isinstance(twin["freed_bytes"], int) \
            or twin["freed_bytes"] < HOME_BYTES:
        out.append(f"{label}: freed_bytes is {twin['freed_bytes']!r}, want at least {HOME_BYTES}")
    if twin["reason"] is not None:
        out.append(f"{label}: reason is {twin['reason']!r}, want null")
    for sid, present in exists.items():
        want = dry_run or sid not in WANT_PRUNED
        if sid == "<outside>":
            want = True
        if present is not want:
            out.append(f"{label}: {sid}'s {'home' if sid != '<outside>' else 'state file'} is "
                       f"{'there' if present else 'gone'} afterwards; want it {'there' if want else 'gone'}")
    return out


def version_problems(text: str) -> list[str]:
    return [] if text.strip() == VERSION else [f"VERSION is {text.strip()!r}, want {VERSION!r}"]


def docs_problems(runtime_doc: str, cli_doc: str, readme: str) -> list[str]:
    out = []
    if "filesystem_reason" not in fold(runtime_doc):
        out.append("runtime-contract.md never names filesystem_reason")
    if "twine sandbox prune" not in fold(cli_doc):
        out.append("cli-contract.md never names twine sandbox prune")
    if "twine sandbox prune" not in fold(readme):
        out.append("README.md never names twine sandbox prune")
    return out


# --- controls (exit 2 when a detector does not fire) ------------------------------

def control(name: str, ok: bool) -> None:
    if not ok:
        sys.stderr.write(f"[checkpoint] BROKEN: control {name} did not fire\n")
        sys.exit(2)


_sb = {"sid": "s", "home": "/h", "repo": "/r", "network": "off", "filesystem": "confined",
       "confines": True, "max_timeout": 600.0}
_tw = {"outcome": "ended", "network": "off", "filesystem": "confined", "next": []}
control("sandbox ok", sandbox_problems(_sb, _tw, True) == [])
control("sandbox absent", bool(sandbox_problems({k: v for k, v in _sb.items() if k != "filesystem"}, _tw, True)))
control("sandbox confined", bool(sandbox_problems({**_sb, "filesystem": "unconfined", "confines": False,
                                                   "filesystem_reason": "x"}, _tw, True)))
control("sandbox honest", sandbox_problems({**_sb, "filesystem": "unconfined", "confines": False,
                                            "filesystem_reason": "no unshare"},
                                           {**_tw, "filesystem": "unconfined"}, False) == []
        and bool(sandbox_problems({**_sb, "filesystem": "unconfined", "confines": False},
                                  {**_tw, "filesystem": "unconfined"}, False)))
control("sandbox twin", bool(sandbox_problems(_sb, {"outcome": "ended", "next": []}, True)))
_res = {"read_outside": "@@read_outside@@\ncat: no such file", "read_repo": "@@read_repo@@\nls: no",
        "write_outside": "@@write_outside@@\ndone", "write_home": "@@write_home@@\nT",
        "procs": "@@procs@@\nbash -c x\ncount=2", "python": "@@python@@\npy-ok",
        "background": "@@background@@\nstarted"}
_host = {"secret": "S3", "repo_mark": "R3", "marker": "M3", "escaped": [], "survivors": 0,
         "home_files": [True, True]}
control("cage ok", cage_problems(_res, _host, True) == [])
for _k, _bad in (("read_outside", "S3"), ("read_outside", PRICES_MARK), ("read_repo", "R3"),
                 ("procs", "M3"), ("python", "Traceback")):
    _r = dict(_res); _r[_k] = _r[_k] + "\n" + _bad if _bad != "Traceback" else "@@python@@\nTraceback"
    control(f"cage {_k} {_bad}", bool(cage_problems(_r, _host, True)))
control("cage escaped", bool(cage_problems(_res, {**_host, "escaped": ["/tmp/x"]}, True)))
control("cage survivors", bool(cage_problems(_res, {**_host, "survivors": 1}, True)))
control("cage home", bool(cage_problems(_res, {**_host, "home_files": [True, False]}, False)))
control("cage missing", bool(cage_problems({k: v for k, v in _res.items() if k != "procs"}, _host, True)))
control("cage proc empty", bool(cage_problems({**_res, "procs": "@@procs@@\ncount=0"}, _host, True)))
_pt = {"command": "sandbox prune", "ok": True, "dry_run": True, "state_dir": "/s", "cwd": "/r",
       "pruned": list(WANT_PRUNED), "kept": [{"sid": s, "why": "w"} for s in WANT_KEPT],
       "freed_bytes": HOME_BYTES, "reason": None}
_ex = {s: True for s in [P_APPLIED, *WANT_KEPT, "<outside>"]}
control("prune ok", prune_problems(_pt, _ex, dry_run=True) == []
        and prune_problems({**_pt, "dry_run": False}, {**_ex, P_APPLIED: False}, dry_run=False) == [])
control("prune removed on dry run", bool(prune_problems(_pt, {**_ex, P_APPLIED: False}, dry_run=True)))
control("prune not removed", bool(prune_problems({**_pt, "dry_run": False}, _ex, dry_run=False)))
control("prune kept removed", bool(prune_problems({**_pt, "dry_run": False},
                                                  {**_ex, P_APPLIED: False, P_HELD: False}, dry_run=False)))
control("prune verdict", bool(prune_problems({**_pt, "pruned": [P_APPLIED, P_ROLLED]}, _ex, dry_run=True)))
control("prune keys", bool(prune_problems({k: v for k, v in _pt.items() if k != "freed_bytes"}, _ex,
                                          dry_run=True)))
control("prune why", bool(prune_problems({**_pt, "kept": [{"sid": s, "why": ""} for s in WANT_KEPT]}, _ex,
                                         dry_run=True)))
control("version", version_problems(VERSION + "\n") == [] and bool(version_problems("0.26.0\n")))
control("docs", docs_problems("filesystem_reason", "twine sandbox prune", "twine sandbox prune") == []
        and bool(docs_problems("", "twine sandbox prune", "twine sandbox prune")))

# --- the stub bale, the request tarball, and twine ---------------------------------


def write_stub_bale(base: Path, request_tarball: Path) -> Path:
    root = base / "root"; (root / "bin").mkdir(parents=True)
    contract_version = json.loads(CONTRACT_LINE.read_text(encoding="utf-8"))["bale_version"]
    (root / "bin" / "VERSION").write_text(contract_version + "\n", encoding="utf-8")
    opened = json.loads(OPEN_LINE.read_text(encoding="utf-8").splitlines()[0])
    opened["tarball"] = str(request_tarball)
    open_file = base / "open.json"; open_file.write_text(json.dumps(opened) + "\n", encoding="utf-8")
    bash = shutil.which("bash") or "/bin/bash"
    script = "\n".join([
        f"#!{bash}",
        "# A double written by the sandbox-confine checkpoint — not bale.",
        f"if [ \"$1\" = open ]; then cat '{open_file}'; exit 0; fi",
        f"if [ \"$1\" = apply ]; then cat '{DRY_RUN_LINE}'; exit 0; fi",
        f"if [ \"$1\" = contract ]; then cat '{CONTRACT_LINE}'; exit 0; fi",
        "exit 1", ""])
    exe = root / "bin" / "bale"; exe.write_text(script, encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return root


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


def transcript_lines(state: Path, sid: str) -> list[dict]:
    path = state / "transcripts" / f"{sid}.jsonl"
    if not sid or not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def sent_tool_results(lines: list[dict]) -> list[str]:
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
                    out.append(inner if isinstance(inner, str) else
                               "".join(b.get("text", "") for b in inner if isinstance(b, dict))
                               if isinstance(inner, list) else "")
    return out


def processes_with(needle: bytes) -> list[int]:
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if needle in (entry / "cmdline").read_bytes():
                found.append(int(entry.name))
        except OSError:
            continue
    return found


def can_confine() -> bool:
    try:
        return subprocess.run(list(NAMESPACES), capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# --- (a) the cage, through twine run ---------------------------------------------------

CAN = can_confine()
tok = secrets.token_hex(6)
base = Path(tempfile.mkdtemp(prefix="twine-oracle-cage-")).resolve()
state = base / "state"; state.mkdir()
(state / "prices.toml").write_text(PRICES, encoding="utf-8")
outside = base / "outside"; outside.mkdir()
secret = f"twine-oracle-secret-{tok}"
(outside / "secret.txt").write_text(secret + "\n", encoding="utf-8")
repo = base / "repo"; repo.mkdir()
repo_mark = f"repo-marker-{tok}"
(repo / repo_mark).write_text("x\n", encoding="utf-8")
tmp_escape = Path(f"/tmp/twine-oracle-escape-{tok}")
marker = f"twine-oracle-marker-{tok}"
marker_proc = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(900)", marker],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
q = shlex.quote
commands = {
    "read_outside": f"echo @@read_outside@@; cat {q(str(outside / 'secret.txt'))} "
                    f"{q(str(state / 'prices.toml'))} 2>&1 | head -c 4000",
    "read_repo": f"echo @@read_repo@@; ls -a {q(str(repo))} 2>&1 | head -c 4000",
    "write_outside": f"echo @@write_outside@@; echo x > {q(str(outside / 'escape.txt'))}; "
                     f"echo x > {q(str(tmp_escape))}; echo done",
    "write_home": f"echo @@write_home@@; echo {tok} > \"$HOME/inside.txt\"; "
                  f"cd / && echo {tok} > \"$HOME/inside2.txt\"; cat \"$HOME/inside.txt\"",
    "procs": "echo @@procs@@; n=0; for f in /proc/[0-9]*/cmdline; do n=$((n+1)); "
             "tr '\\0' ' ' < \"$f\" 2>/dev/null; echo; done; echo count=$n",
    "python": "echo @@python@@; python3 -c 'print(\"py\" + \"-ok\")' 2>&1",
    "background": "echo @@background@@; setsid sleep 3017 >/dev/null 2>&1 < /dev/null & sleep 0.5; echo started",
}
try:
    control("host marker visible", bool(processes_with(marker.encode())))
    tarball = write_request(base)
    root = write_stub_bale(base, tarball)
    script = [tool_turn("shell", {"command": commands[p]}, 10 + i, tag=f"-{p}")
              for i, p in enumerate(PROBES)] + [prose_turn(30)]
    script_file = base / "script.json"; script_file.write_text(json.dumps(script), encoding="utf-8")
    twin, err = twine(["run", "oracle.bale-bundle", "--adapter", "fake", "--script",
                       str(script_file), "--model", "fake", "--cap", "5", "--state-dir",
                       str(state), "--bale-root", str(root), "--cwd", str(repo), "--json"],
                      cwd=repo)
    time.sleep(0.5)
    survivors = processes_with(SLEEP_ARGV)
    sid = twin.get("sid") or ""
    lines = transcript_lines(state, sid)
    if twin and not lines:
        failures.append(f"run: no transcript for {sid!r} (outcome {twin.get('outcome')!r}, reason "
                        f"{str(twin.get('reason'))[:200]!r})")
    starts = [l for l in lines if l.get("kind") == "run-start"]
    if twin and lines:
        for p in sandbox_problems(starts[0].get("sandbox") if starts else None, twin, CAN):
            failures.append(f"sandbox: {p}")
        results = {}
        for text in sent_tool_results(lines):
            m = re.search(r"@@([a-z_]+)@@", text)
            if m:
                results[m.group(1)] = text
        home = state / "sandbox" / sid / "home"
        host = {"secret": secret, "repo_mark": repo_mark, "marker": marker, "survivors": len(survivors),
                "escaped": [str(p) for p in (outside / "escape.txt", tmp_escape) if p.exists()],
                "home_files": [(home / n).is_file() and (home / n).read_text(errors="replace").strip() == tok
                               for n in ("inside.txt", "inside2.txt")]}
        branch = "confining" if CAN else "unconfined (the namespaces cannot be made here)"
        for p in cage_problems(results, host, CAN):
            failures.append(f"cage [{branch}]: {p}")
finally:
    marker_proc.kill(); marker_proc.wait()
    for pid in processes_with(SLEEP_ARGV):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    tmp_escape.unlink(missing_ok=True)

# --- (b) twine sandbox prune ------------------------------------------------------------

pbase = Path(tempfile.mkdtemp(prefix="twine-oracle-prune-")).resolve()
pstate = pbase / "state"; prepo = pbase / "repo"
for sid in (P_APPLIED, *WANT_KEPT):
    h = pstate / "sandbox" / sid / "home"; (h / "tmp").mkdir(parents=True)
    (h / "work.bin").write_bytes(b"\0" * HOME_BYTES)
(pstate / "keep-me.txt").write_text("not a home\n", encoding="utf-8")
(pstate / "inflight").mkdir()
(pstate / "inflight" / f"{P_INFLIGHT}.json").write_text(json.dumps({"sid": P_INFLIGHT}) + "\n",
                                                         encoding="utf-8")
(prepo / AGENT_DIR / "telemetry").mkdir(parents=True)
(prepo / "bale.toml").write_text(f'[layout]\nagent_dir = "{AGENT_DIR}"\n', encoding="utf-8")
for sid, outcomes in PRUNE_ATTEMPTS.items():
    record = {"sid": sid, "outcome": outcomes[-1],
              "attempts": [{"attempt": n, "outcome": o} for n, o in enumerate(outcomes, 1)]}
    (prepo / AGENT_DIR / "telemetry" / f"{sid}.json").write_text(json.dumps(record) + "\n",
                                                                 encoding="utf-8")


def on_disk() -> dict:
    out = {sid: (pstate / "sandbox" / sid).exists() for sid in (P_APPLIED, *WANT_KEPT)}
    out["<outside>"] = (pstate / "keep-me.txt").is_file()
    return out


for dry in (True, False):
    args = ["sandbox", "prune", "--state-dir", str(pstate), "--cwd", str(prepo), "--json"]
    twin, _ = twine(args + (["--dry-run"] if dry else []), pbase)
    if twin:
        for p in prune_problems(twin, on_disk(), dry_run=dry):
            failures.append(f"prune: {p}")

# --- (c) docs and VERSION ----------------------------------------------------------------

for p in docs_problems((ROOT / "claude" / "context" / "runtime-contract.md").read_text(encoding="utf-8"),
                       (ROOT / "claude" / "context" / "cli-contract.md").read_text(encoding="utf-8"),
                       (ROOT / "README.md").read_text(encoding="utf-8")):
    failures.append(f"docs: {p}")
for p in version_problems((ROOT / "VERSION").read_text(encoding="utf-8")):
    failures.append(f"version: {p}")

shutil.rmtree(base, ignore_errors=True)
shutil.rmtree(pbase, ignore_errors=True)
if failures:
    for f in failures:
        print(f"[checkpoint] FAIL {f}")
    sys.exit(1)
print(f"[checkpoint] PASS: the cage {'confines' if CAN else 'reports honestly that it cannot confine'} "
      "here, the home stays writable, twine sandbox prune removes exactly the applied home; "
      f"VERSION {VERSION}")
sys.exit(0)
ORACLE
exit $?

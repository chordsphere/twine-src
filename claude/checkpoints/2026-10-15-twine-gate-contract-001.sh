#!/usr/bin/env bash
# Blind checkpoint — twine-src session `twine-gate-contract` (the gate on
# bale's contract), authored at sitting 2026-10-13-open-hardening-011 on
# 2026-10-15, v1.
#
# Outcome contracts only (PLANNER.md §4), graded through `twine bale check
# --json`, `twine status --json` and `twine transitions --json` against
# install roots this oracle builds itself: a `bin/VERSION` and a `bin/bale`
# bash script that prints the tree's carried contract line, or an edited
# copy of it (the edits are this oracle's, named as not bale's). Runs from
# the staged tree's root; reads nothing of its own path, sid or manifest.
# Exit 0: every probe holds. Exit 1: a probe fails, named. Exit 2: this
# oracle is broken (a control failed, or an unplanned exception).
set -u
export PYTHONDONTWRITEBYTECODE=1
python3 -I -B - <<'ORACLE'
import json, re, shutil, stat, subprocess, sys, tempfile, tomllib
from pathlib import Path


def broken(exc_type, exc, tb):
    sys.stderr.write(f"[checkpoint] BROKEN: {exc_type.__name__}: {exc}\n")
    sys.exit(2)


sys.excepthook = broken
ROOT = Path.cwd()
failures: list[str] = []

# --- the pins the brief carries ---------------------------------------------
VERSION = "0.23.0"
FLOOR = "0.4.54"
RECORDINGS = "0.4.51"
CONTRACT_REL = "fixtures/contract/bale-0.4.55.json"
CONTRACT_VERSION = "0.4.55"
CHECK_KEYS = {"floor", "installed", "root", "source", "contract", "ok", "reason"}
CONTRACT_OBJECT_KEYS = ("ok", "bale_version", "sha256", "problems", "notes")
ADDED_OUTCOME = "twine-oracle-added-outcome"
ADDED_RELAY = "twine-oracle-added-relay-outcome"
TWINE = ROOT / "bin" / "twine"
BASH = shutil.which("bash") or "/bin/bash"


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("`", "").replace("*", "")).strip().lower()


# --- detectors --------------------------------------------------------------

def manifest_problems(bale: dict) -> list[str]:
    out = []
    for key, want in (("floor", FLOOR), ("recordings", RECORDINGS), ("contract", CONTRACT_REL)):
        if bale.get(key) != want:
            out.append(f"[bale] {key} is {bale.get(key)!r}, want {want!r}")
    return out


def carried_problems(text: str | None) -> list[str]:
    if text is None:
        return [f"{CONTRACT_REL} is not in the tree"]
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) != 1:
        return [f"{CONTRACT_REL} holds {len(lines)} non-empty lines, want one JSON line"]
    try:
        obj = json.loads(lines[0])
    except ValueError as exc:
        return [f"{CONTRACT_REL} is not JSON: {exc}"]
    if not isinstance(obj, dict) or obj.get("outcome") != "contract" \
            or obj.get("bale_version") != CONTRACT_VERSION:
        return [f"{CONTRACT_REL} is not bale {CONTRACT_VERSION}'s contract line"]
    return []


def admitted_problems(twin: dict, label: str) -> list[str]:
    out = []
    if twin.get("ok") is not True:
        return [f"{label}: the gate refuses ({twin.get('reason')!r}), want ok"]
    keys = set(twin) - {"command"}
    if keys != CHECK_KEYS:
        out.append(f"{label}: bale check's keys are {sorted(keys)}, want {sorted(CHECK_KEYS)} "
                   "(no `schemas`)")
    c = twin.get("contract")
    if not isinstance(c, dict) or tuple(c.keys()) != CONTRACT_OBJECT_KEYS:
        out.append(f"{label}: `contract` is {c!r}, want an object with exactly "
                   f"{list(CONTRACT_OBJECT_KEYS)}")
    elif c.get("ok") is not True or c.get("bale_version") != CONTRACT_VERSION:
        out.append(f"{label}: contract.ok {c.get('ok')!r}, bale_version {c.get('bale_version')!r}")
    return out


def refused_problems(twin: dict, label: str, names: tuple[str, ...]) -> list[str]:
    if twin.get("ok") is not False:
        return [f"{label}: the gate admits it (ok {twin.get('ok')!r}), want it refused"]
    reason = str(twin.get("reason") or "")
    missing = [n for n in names if n not in reason]
    return [f"{label}: the refusal does not name {', '.join(map(repr, missing))} "
            f"(reason {reason[:240]!r})"] if missing else []


def noted_problems(twin: dict) -> list[str]:
    out = admitted_problems(twin, "an added relay outcome")
    c = twin.get("contract") if isinstance(twin.get("contract"), dict) else {}
    if not any(ADDED_RELAY in str(n) for n in (c.get("notes") or [])):
        out.append("an added relay outcome is not reported in contract.notes")
    return out


def status_problems(twin: dict) -> list[str]:
    b = twin.get("bale")
    return [] if isinstance(b, dict) and b.get("ok") is True else \
        [f"twine status's bale object is {str(b)[:200]!r}, want ok true for the same root"]


def version_problems(text: str) -> list[str]:
    return [] if text.strip() == VERSION else [f"VERSION is {text.strip()!r}, want {VERSION!r}"]


def docs_problems(cli_doc: str) -> list[str]:
    return [] if "bale contract --json" in fold(cli_doc) else \
        ["cli-contract.md never names `bale contract --json`"]


# --- controls (exit 2 when a detector does not fire) -------------------------

def control(name: str, ok: bool) -> None:
    if not ok:
        sys.stderr.write(f"[checkpoint] BROKEN: control {name} did not fire\n")
        sys.exit(2)


control("manifest", manifest_problems({"floor": FLOOR, "recordings": RECORDINGS,
                                       "contract": CONTRACT_REL}) == []
        and bool(manifest_problems({"floor": "0.4.51"})))
good_line = json.dumps({"outcome": "contract", "bale_version": CONTRACT_VERSION}) + "\n"
control("carried", carried_problems(good_line) == [] and bool(carried_problems(None))
        and bool(carried_problems(good_line + good_line)))
good_twin = {"command": "bale check", "ok": True, "floor": FLOOR, "installed": CONTRACT_VERSION,
             "root": "/r", "source": "--bale-root", "contract": {"ok": True, "bale_version": CONTRACT_VERSION,
             "sha256": "x", "problems": [], "notes": []}, "reason": "ok"}
control("admitted", admitted_problems(good_twin, "c") == [])
control("admitted schemas key", bool(admitted_problems({**good_twin, "schemas": {}}, "c")))
control("admitted refused", bool(admitted_problems({**good_twin, "ok": False}, "c")))
control("refused", refused_problems({"ok": False, "reason": "lacks 'opener'"}, "c", ("opener",)) == []
        and bool(refused_problems({"ok": True}, "c", ("opener",)))
        and bool(refused_problems({"ok": False, "reason": "x"}, "c", ("opener",))))
noted = json.loads(json.dumps(good_twin)); noted["contract"]["notes"] = [f"added {ADDED_RELAY}"]
control("noted", noted_problems(noted) == [] and bool(noted_problems(good_twin)))
control("status", status_problems({"bale": {"ok": True}}) == [] and bool(status_problems({"bale": None})))
control("version", version_problems(VERSION + "\n") == [] and bool(version_problems("0.22.0\n")))
control("docs", docs_problems("the gate runs `bale contract --json`") == [] and bool(docs_problems("")))

# --- roots and runs ------------------------------------------------------------


def twine(args: list[str], label: str) -> dict:
    proc = subprocess.run([sys.executable, "-I", "-B", str(TWINE), *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=180)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    try:
        twin = json.loads(lines[0]) if len(lines) == 1 else None
    except ValueError:
        twin = None
    if not isinstance(twin, dict):
        failures.append(f"{label}: no JSON twin on stdout (exit {proc.returncode}; stderr ends "
                        f"{proc.stderr[-300:]!r})")
        return {}
    return twin


def make_root(base: Path, name: str, version: str, line: str | None, *, exit_code: int = 0,
              schemas: str | None = None) -> Path:
    """An install root of this oracle's: bin/VERSION, and a bin/bale (a double,
    not bale) that prints `line` for `contract --json` and exits `exit_code`."""
    root = base / name
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "VERSION").write_text(version + "\n", encoding="utf-8")
    payload = base / f"{name}.contract.json"
    payload.write_text(line or "", encoding="utf-8")
    script = "\n".join([f"#!{BASH}", "# A double written by the gate-contract checkpoint — not bale.",
                        f"if [ \"$1\" = contract ]; then cat '{payload}'; exit {exit_code}; fi",
                        "exit 1", ""])
    exe = root / "bin" / "bale"
    exe.write_text(script, encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    if schemas == "altered":
        (root / "schemas").mkdir()
        (root / "schemas" / "telemetry-record.schema.json").write_text(
            '{"$comment": "altered by the gate-contract checkpoint"}\n', encoding="utf-8")
    return root


def edited(obj: dict, edit) -> str:
    copy = json.loads(json.dumps(obj))
    edit(copy)
    return json.dumps(copy) + "\n"


# (a) the manifest and the carried line
try:
    bale_table = tomllib.loads((ROOT / "share" / "bale-consumption.toml").read_text(encoding="utf-8")).get("bale") or {}
except (OSError, tomllib.TOMLDecodeError) as exc:
    bale_table = {}
    failures.append(f"manifest: share/bale-consumption.toml cannot be parsed: {exc}")
for p in manifest_problems(bale_table):
    failures.append(f"manifest: {p}")
carried_path = ROOT / CONTRACT_REL
carried_text = carried_path.read_text(encoding="utf-8") if carried_path.is_file() else None
problems = carried_problems(carried_text)
for p in problems:
    failures.append(f"carried line: {p}")

# (b) the gate against roots built from the carried line
if not problems:
    line = [l for l in carried_text.splitlines() if l.strip()][0] + "\n"
    obj = json.loads(line)
    with tempfile.TemporaryDirectory(prefix="twine-oracle-gate-") as td:
        base = Path(td)

        def check(root: Path, label: str) -> dict:
            return twine(["bale", "check", "--json", "--bale-root", str(root)], label)

        good = make_root(base, "good", CONTRACT_VERSION, line)
        twin = check(good, "no schemas/")
        for p in admitted_problems(twin, "a 0.4.55 root with no schemas/"):
            failures.append(f"gate: {p}")
        twin = check(make_root(base, "altered", CONTRACT_VERSION, line, schemas="altered"), "altered")
        for p in admitted_problems(twin, "a 0.4.55 root with an altered schema"):
            failures.append(f"gate: {p}")

        def drop_opener(o):
            o["json_keys"]["open"] = [k for k in o["json_keys"]["open"] if k != "opener"]
        twin = check(make_root(base, "nokey", CONTRACT_VERSION, edited(obj, drop_opener)), "no opener")
        for p in refused_problems(twin, "an open line without `opener`", ("opener",)):
            failures.append(f"gate: {p}")

        def add_outcome(o):
            o["vocabularies"]["telemetry-outcome"]["values"].append(ADDED_OUTCOME)
        twin = check(make_root(base, "vocab", CONTRACT_VERSION, edited(obj, add_outcome)), "vocab")
        for p in refused_problems(twin, "an added telemetry outcome", (ADDED_OUTCOME,)):
            failures.append(f"gate: {p}")

        def drop_hold(o):
            o["refusal_reasons"]["unlock"]["values"] = [
                v for v in o["refusal_reasons"]["unlock"]["values"] if v != "hold-branch"]
        twin = check(make_root(base, "hold", CONTRACT_VERSION, edited(obj, drop_hold)), "hold")
        for p in refused_problems(twin, "an unlock contract without hold-branch", ("hold-branch",)):
            failures.append(f"gate: {p}")

        twin = check(make_root(base, "mismatch", "0.4.56", line), "mismatch")
        for p in refused_problems(twin, "a contract whose bale_version is not bin/VERSION", ()):
            failures.append(f"gate: {p}")

        twin = check(make_root(base, "below", "0.4.53", line), "below")
        for p in refused_problems(twin, "a root below 0.4.54", ()):
            failures.append(f"gate: {p}")

        twin = check(make_root(base, "noverb", CONTRACT_VERSION, "", exit_code=1), "noverb")
        for p in refused_problems(twin, "a bale whose contract --json fails", ()):
            failures.append(f"gate: {p}")

        def add_relay(o):
            o["vocabularies"]["relay-outcome"]["values"].append(ADDED_RELAY)
        twin = check(make_root(base, "relay", CONTRACT_VERSION, edited(obj, add_relay)), "relay")
        for p in noted_problems(twin):
            failures.append(f"gate: {p}")

        for p in status_problems(twine(["status", "--json", "--bale-root", str(good)], "status")):
            failures.append(f"status: {p}")

# (c) the table, VERSION, the docs
table = twine(["transitions", "--json"], "transitions")
if table.get("ok") is not True:
    failures.append(f"table: twine transitions --json is not ok: {table.get('reason')}")
for p in version_problems((ROOT / "VERSION").read_text(encoding="utf-8")):
    failures.append(f"version: {p}")
for p in docs_problems((ROOT / "claude" / "context" / "cli-contract.md").read_text(encoding="utf-8")):
    failures.append(f"docs: {p}")

if failures:
    for f in failures:
        print(f"[checkpoint] FAIL {f}")
    sys.exit(1)
print(f"[checkpoint] PASS: the gate is the floor {FLOOR} plus bale's contract, admitting what "
      "twine reads unmoved and refusing, by name, what moved; no schema is hashed; "
      f"VERSION {VERSION}")
sys.exit(0)
ORACLE
exit $?

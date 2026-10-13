#!/usr/bin/env bash
# Blind checkpoint — twine-src session `twine-table-adapter-defect`
# (authored at sitting 2026-10-13-open-milestone-2-006, v1).
#
# Outcome contracts only (PLANNER.md §4): what must be true of the
# applied tree, never how the worker got there. Runs from the staged
# tree's root; reads nothing of its own path, sid or manifest. Exit 0:
# every probe holds. Exit 1: a probe fails, named. Exit 2: this oracle
# is broken (a control failed, or an unplanned exception) — the
# planner's fault, not the work's (TARBALL.md §7.5).
set -u
cd "$(pwd)" || exit 2
export PYTHONDONTWRITEBYTECODE=1
python3 -I -B - <<'ORACLE'
import json, os, re, subprocess, sys, tempfile, tomllib
from pathlib import Path


def broken(exc_type, exc, tb):
    # An unplanned exception is the oracle's fault: exit 2, never 1.
    sys.stderr.write(f"[checkpoint] BROKEN: {exc_type.__name__}: {exc}\n")
    sys.exit(2)


sys.excepthook = broken
ROOT = Path.cwd()
failures: list[str] = []

# --- the pins the brief carries, verbatim ---------------------------------
KEY = "adapter-defect"
MOVE = "fix-adapter"
ACTOR = "operator"
CONTINUE_DESCRIPTION = (
    "Twine continues the cut-off turn in a further call that carries what was "
    "written so far, counted against the window and the cap; at most three "
    "continuations in a row, past which the run stops with the stop the turn "
    "carried, max-tokens, for the planner to read."
)
VERSION = "0.20.0"
STALE_SENTENCE = ("The continue-turn move's description in the table says that past "
                  "the bound \"the turn stops as malformed-shape\"")


def fold(text: str) -> str:
    """Whitespace folded and emphasis markers stripped, so a wrapped or
    emphasised sentence still matches (PLANNER.md §4)."""
    return re.sub(r"\s+", " ", text.replace("`", "").replace("*", "")).strip()


# --- detectors (each a function; the controls call these, never a copy) ---

def table_problems(table: dict) -> list[str]:
    out = []
    stop = table.get("axis", {}).get("stop", {})
    keys = stop.get("keys", [])
    loop = stop.get("loop_keys", [])
    if KEY not in keys:
        out.append(f"stop axis keys lack {KEY!r}")
    if KEY not in loop:
        out.append(f"stop axis loop_keys lack {KEY!r}")
    rows = [r for r in table.get("row", []) if r.get("axis") == "stop" and r.get("key") == KEY]
    if len(rows) != 1:
        out.append(f"{len(rows)} [[row]] entries for (stop, {KEY}); want 1")
    elif rows[0].get("move") != MOVE:
        out.append(f"the (stop, {KEY}) row's move is {rows[0].get('move')!r}, not {MOVE!r}")
    move = table.get("move", {}).get(MOVE)
    if move is None:
        out.append(f"no [move.{MOVE}]")
    elif move.get("actor") != ACTOR:
        out.append(f"[move.{MOVE}] actor is {move.get('actor')!r}, not {ACTOR!r}")
    cont = table.get("move", {}).get("continue-turn", {})
    if fold(cont.get("description", "")) != fold(CONTINUE_DESCRIPTION):
        out.append("[move.continue-turn] description is not the brief's sentence")
    return out


def transitions_verb_problems(argv_root: Path) -> list[str]:
    proc = subprocess.run([sys.executable, "-I", "-B", str(argv_root / "bin" / "twine"),
                           "transitions", "--json"], capture_output=True, text=True,
                          cwd=argv_root, timeout=300)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    if proc.returncode != 0 or len(lines) != 1:
        return [f"twine transitions --json: exit {proc.returncode}, {len(lines)} stdout line(s)"]
    return twin_problems(json.loads(lines[0]))


def twin_problems(twin: dict) -> list[str]:
    out = []
    if twin.get("ok") is not True:
        out.append(f"twine transitions --json not ok: {twin.get('reason')}")
    axes = {a.get("name"): a for a in twin.get("axes", [])}
    if KEY not in axes.get("stop", {}).get("loop_keys", []):
        out.append(f"the twin's stop axis loop_keys lack {KEY!r}")
    return out


def loop_outcome_problems(result) -> list[str]:
    out = []
    if result.outcome != "stopped":
        out.append(f"outcome {result.outcome!r}, want 'stopped'")
    if result.stop != KEY:
        out.append(f"stop {result.stop!r}, want {KEY!r}")
    if result.move != MOVE:
        out.append(f"move {result.move!r}, want {MOVE!r}")
    if result.actor != ACTOR:
        out.append(f"actor {result.actor!r}, want {ACTOR!r}")
    return out


def docs_problems(runtime_doc: str, cli_doc: str) -> list[str]:
    out = []
    for name, text in (("runtime-contract.md", runtime_doc), ("cli-contract.md", cli_doc)):
        f = fold(text)
        if KEY not in f:
            out.append(f"{name} never names {KEY!r}")
        if MOVE not in f:
            out.append(f"{name} never names {MOVE!r}")
    if fold(STALE_SENTENCE) in fold(runtime_doc):
        out.append("runtime-contract.md still carries R4's stale continue-turn sentence")
    return out


def version_problems(text: str) -> list[str]:
    return [] if text.strip() == VERSION else [f"VERSION is {text.strip()!r}, want {VERSION!r}"]


# --- controls: prove each detector fires on a known-bad input (exit 2) ---

def control(name: str, ok: bool) -> None:
    if not ok:
        sys.stderr.write(f"[checkpoint] BROKEN: control {name} did not fire\n")
        sys.exit(2)


good_table = {"axis": {"stop": {"keys": [KEY], "loop_keys": [KEY]}},
              "row": [{"axis": "stop", "key": KEY, "move": MOVE}],
              "move": {MOVE: {"actor": ACTOR},
                       "continue-turn": {"description": CONTINUE_DESCRIPTION}}}
control("table ok", table_problems(good_table) == [])
bad = json.loads(json.dumps(good_table)); bad["axis"]["stop"]["loop_keys"] = []
control("table loop_keys", bool(table_problems(bad)))
bad = json.loads(json.dumps(good_table)); bad["row"][0]["move"] = "respawn-from-request"
control("table row move", bool(table_problems(bad)))
bad = json.loads(json.dumps(good_table)); bad["move"][MOVE]["actor"] = "planner"
control("table actor", bool(table_problems(bad)))
bad = json.loads(json.dumps(good_table))
bad["move"]["continue-turn"]["description"] = "past the bound the turn stops as malformed-shape"
control("table continue-turn", bool(table_problems(bad)))


good_twin = {"ok": True, "axes": [{"name": "stop", "loop_keys": [KEY]}]}
control("twin ok", twin_problems(good_twin) == [])
control("twin not ok", bool(twin_problems({"ok": False, "reason": "x", "axes": good_twin["axes"]})))
control("twin loop_keys", bool(twin_problems({"ok": True, "axes": [{"name": "stop", "loop_keys": []}]})))


class _R:
    def __init__(self, **kw): self.__dict__.update(kw)


control("loop ok", loop_outcome_problems(_R(outcome="stopped", stop=KEY, move=MOVE, actor=ACTOR)) == [])
control("loop stop", bool(loop_outcome_problems(_R(outcome="stopped", stop=None, move=None, actor=None))))
control("docs ok", docs_problems(f"x {KEY} y {MOVE}", f"{KEY} {MOVE}") == [])
control("docs key", bool(docs_problems(f"{MOVE} only", f"{KEY} {MOVE}")))
control("docs stale", bool(docs_problems(f"{KEY} {MOVE} " + STALE_SENTENCE, f"{KEY} {MOVE}")))
control("version", bool(version_problems("0.19.0\n")) and version_problems(VERSION + "\n") == [])

# --- probes, on the tree ---------------------------------------------------

with open(ROOT / "share" / "transitions.toml", "rb") as fh:
    table = tomllib.load(fh)
for p in table_problems(table):
    failures.append(f"table: {p}")

for p in transitions_verb_problems(ROOT):
    failures.append(f"verb: {p}")

# The loop, in-process, over the fake adapter: an adapter that raises
# (a one-turn script runs out on call 2) and one the boundary refuses (a
# provider's word where twine's stop belongs) both end the run on the
# new key and its move. Nothing is registered with the kill-switch; a
# temporary state directory holds the sandbox, the transcript and the
# prices double the fake's model is priced by.
sys.path.insert(0, str(ROOT))
from decimal import Decimal
from twine import CONSUMPTION_MANIFEST, TRANSITIONS_TABLE, transcript as transcripts
from twine.bale import load_manifest
from twine.runtime import loop as runloop
from twine.runtime.boundary import Boundary, SpawnSettings
from twine.runtime.sandbox import Sandbox
from twine.runtime.terms import ThinkingSettings
from twine.runtime.tooling import load_tool_registry
from twine.transitions import load_table

PRICES = '[model."fake"]\ninput = 1\noutput = 2\ncache_read = 0.1\ncache_write = 1.25\n'
SID = "2026-10-13-oracle-loop-001"
TOOLS = load_tool_registry()
BOOK = runloop.MoveBook(load_table(TRANSITIONS_TABLE, load_manifest(CONSUMPTION_MANIFEST)))


def run_loop(script: list) -> object:
    with tempfile.TemporaryDirectory(prefix="twine-oracle-") as d:
        state = Path(d) / "state"; state.mkdir()
        (state / "prices.toml").write_text(PRICES, encoding="utf-8")
        repo = Path(d) / "repo"; repo.mkdir()
        sandbox = Sandbox.create(state, SID, repo=repo)
        prompt = runloop.system_prompt(TOOLS)
        fake = runloop.adapter_class("fake")
        adapter = fake(SpawnSettings("fake", 16000, ThinkingSettings(enabled=True, adaptive=True)),
                       script)
        loop = runloop.Loop(
            boundary=Boundary(adapter), sandbox=sandbox,
            transcript=transcripts.Transcript.open(state, SID),
            settings=runloop.LoopSettings(sid=SID, state_dir=state, cap_usd=Decimal("5"),
                                          model="fake", max_tokens=16000, max_turns=10),
            prompt=prompt, moves=BOOK, tools=TOOLS,
            deliver=lambda path: runloop.Delivery(ok=False, tarball=str(path), apply_line=None,
                                                  dry_run=None, outcome="dry-run",
                                                  reason="oracle", twin={}),
            messages=[runloop.user_message("the opener")],
            sleep=lambda s: None, abort=lambda state_dir, sid: False)
        return loop.run()


USAGE = {"input": 1, "output": 1, "thinking": None, "cache_read": 0, "cache_write": 0}
cases = {
    "an adapter that raises (the script exhausted on call 2)":
        [{"stop": None, "tool_calls": [{"id": "t1", "name": "list_dir", "arguments": {}}],
          "usage": USAGE}],
    "a turn the boundary refuses (provider word 'end_turn')":
        [{"text": "", "stop": "end_turn", "usage": USAGE}],
}
for label, script in cases.items():
    result = run_loop(script)
    for p in loop_outcome_problems(result):
        failures.append(f"loop, {label}: {p}")

runtime_doc = (ROOT / "claude" / "context" / "runtime-contract.md").read_text(encoding="utf-8")
cli_doc = (ROOT / "claude" / "context" / "cli-contract.md").read_text(encoding="utf-8")
for p in docs_problems(runtime_doc, cli_doc):
    failures.append(f"docs: {p}")

for p in version_problems((ROOT / "VERSION").read_text(encoding="utf-8")):
    failures.append(f"version: {p}")

if failures:
    for f in failures:
        print(f"[checkpoint] FAIL {f}")
    sys.exit(1)
print("[checkpoint] PASS: adapter-defect on the stop axis and in the loop; continue-turn "
      "reconciled; docs name both; VERSION " + VERSION)
sys.exit(0)
ORACLE
exit $?

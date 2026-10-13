#!/usr/bin/env bash
# Blind checkpoint — twine-src session `twine-housekeeping-probe`
# (authored at sitting 2026-10-13-open-milestone-2-006, v1).
#
# Outcome contracts only (PLANNER.md §4). Runs from the staged tree's
# root; reads nothing of its own path, sid or manifest. Exit 0: every
# probe holds. Exit 1: a probe fails, named. Exit 2: this oracle is
# broken (a control failed, or an unplanned exception) — the planner's
# artifact, not the worker's (TARBALL.md §7.5).
set -u
export PYTHONDONTWRITEBYTECODE=1
python3 -I -B - <<'ORACLE'
import ast, sys, tempfile
from pathlib import Path


def broken(exc_type, exc, tb):
    sys.stderr.write(f"[checkpoint] BROKEN: {exc_type.__name__}: {exc}\n")
    sys.exit(2)


sys.excepthook = broken
ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
failures: list[str] = []
VERSION = "0.21.0"
FORBIDDEN = ("twine.commands", "twine.cli")
# The crafter's recorded probe scaffold, a fixtures/README.md row at the floor.
SCAFFOLD = ROOT / "fixtures" / "bale-0.4.51" / "crafter" / "--probe-twine-take-fixture.txt"
WHAT = "TODO(worker) — what this asks, in one line."
WHY = "TODO(worker) — the gap this fills, in one line."
TAIL = "\n# Clipboard copy (TARBALL.md 4.3)"


# --- detectors ---------------------------------------------------------------

def import_edges(source: str, forbidden=FORBIDDEN) -> list[str]:
    """Every import in `source` of a forbidden module (or a submodule of
    one), by its dotted name — [] when the module imports none."""
    tree = ast.parse(source)
    hits = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        for name in names:
            if any(name == f or name.startswith(f + ".") for f in forbidden):
                hits.append(name)
    return hits


def runtime_edge_problems(runtime_dir: Path) -> list[str]:
    out = []
    for path in sorted(runtime_dir.rglob("*.py")):
        for name in import_edges(path.read_text(encoding="utf-8")):
            out.append(f"{path.relative_to(ROOT)} imports {name} — a runtime→commands edge")
    return out


def probe_result_problems(result, slug: str) -> list[str]:
    """The probe tool's result for a read-only block: ok, and its
    content one intact probe-output block of the slug."""
    from twine import shapes
    out = []
    if result.is_error:
        out.append(f"probe tool is_error: {result.content[:300]!r}")
        return out
    report = shapes.find_blocks(result.content)
    blocks = [b for b in report.blocks if b.kind == shapes.PROBE_OUTPUT]
    if len(blocks) != 1 or not blocks[0].ok:
        out.append(f"probe tool content is not one intact probe-output block "
                   f"(shape {report.shape!r}, {len(blocks)} output block(s))")
    elif blocks[0].fields.get("slug") != slug:
        out.append(f"probe-output block names slug {blocks[0].fields.get('slug')!r}, not {slug!r}")
    if result.fields.get("leaves_cage") is not True:
        out.append("probe result does not say leaves_cage: true")
    return out


def version_problems(text: str) -> list[str]:
    return [] if text.strip() == VERSION else [f"VERSION is {text.strip()!r}, want {VERSION!r}"]


# --- controls (exit 2 when a detector does not fire) ------------------------

def control(name: str, ok: bool) -> None:
    if not ok:
        sys.stderr.write(f"[checkpoint] BROKEN: control {name} did not fire\n")
        sys.exit(2)


control("edges clean", import_edges("import os\nfrom twine import shapes\n") == [])
control("edges import", import_edges("from twine.commands import carry\n") == ["twine.commands"])
control("edges cli", import_edges("from twine.cli import Context\n") == ["twine.cli"])
control("edges dotted", import_edges("import twine.commands.carry\n") == ["twine.commands.carry"])


class _R:
    def __init__(self, **kw): self.__dict__.update(kw)


control("probe is_error", bool(probe_result_problems(_R(is_error=True, content="x", fields={}), "s")))
control("probe shape", bool(probe_result_problems(_R(is_error=False, content="prose only", fields={}), "s")))
control("version", bool(version_problems("0.20.0\n")) and version_problems(VERSION + "\n") == [])

# --- probes -----------------------------------------------------------------

for p in runtime_edge_problems(ROOT / "twine" / "runtime"):
    failures.append(f"edge: {p}")

# The probe tool, in a sandbox, on a filled read-only probe block built from
# the tree's own recorded scaffold: the paste-back must come back intact.
from twine.runtime.sandbox import Sandbox
from twine.runtime.tooling import run_tool

text = SCAFFOLD.read_bytes().decode("utf-8")
if text.count(WHAT) != 1 or text.count(WHY) != 1 or text.count(TAIL) != 1:
    raise AssertionError("the recorded scaffold is not the one this oracle fills")
text = text.replace(WHAT, "what the oracle asks.").replace(WHY, "the oracle's rehearsal.")
start = text.index("probe() {\n") + len("probe() {\n")
end = text.index("\n}\n", start)
text = text[:start] + '  echo "--- section: oracle ---"\n  echo "oracle ok"' + text[end:]
text = text[:text.index(TAIL)]
assert "TODO(worker)" not in text
block = "```bash\n" + text + "```\n"

with tempfile.TemporaryDirectory(prefix="twine-oracle-") as d:
    state = Path(d) / "state"; state.mkdir()
    repo = Path(d) / "repo"; repo.mkdir()
    sandbox = Sandbox.create(state, "2026-10-13-oracle-probe-001", repo=repo)
    result = run_tool(sandbox, "probe", {"block": block})
    for p in probe_result_problems(result, "twine-take-fixture"):
        failures.append(f"probe tool: {p}")

for p in version_problems((ROOT / "VERSION").read_text(encoding="utf-8")):
    failures.append(f"version: {p}")

if failures:
    for f in failures:
        print(f"[checkpoint] FAIL {f}")
    sys.exit(1)
print("[checkpoint] PASS: no runtime→commands edge; the probe tool still closes the hop; "
      "VERSION " + VERSION)
sys.exit(0)
ORACLE
exit $?

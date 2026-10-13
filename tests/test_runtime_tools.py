"""The canonical tools, the sandbox they run in, and the kill-switch hook
(Arc 2 R3; claude/context/runtime-contract.md §6, cli-contract.md §17.6).

Real processes throughout — bash, sleep, unshare where this machine has it —
and no model, no network (T8): nothing here calls an adapter or opens a
socket. Doubles of the run seam appear only where a failure must be forced
(an `unshare` that is absent or refused, a hook that cannot register, a
group that survives); each is named as one. The sandbox's detection of the
network rule runs for real on this machine and is asserted whichever way it
goes: `network` and `confines` agree, and the argv the runner saw is the one
the rule implies.

Sections:
  1. Helpers
  2. The declaration and the registry
  3. The verb, `twine runtime tools`
  4. The sandbox: creation, the environment, the network rule
  5. The file tools and the cage
  6. shell
  7. The kill-switch hook
  8. probe
  9. escalate and deliver
 10. run_tool, results, and the import rule
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from twine import REPO_ROOT, kill, process, shapes
from twine.cli import Context, main
from twine.process import RunError, RunResult, run_process, runner_confines
from twine.runtime import TOOLS_DECLARATION, TOOLS_DIR, RUNTIME_DIR
from twine.runtime.adapters import anthropic
from twine.runtime.registry import DeclarationError, load_runtime_registry
from twine.runtime.sandbox import (FALLBACK_LANG, FALLBACK_PATH, NETWORK_OFF,
                                   NETWORK_UNCONFINED, CageError, Sandbox, SandboxError,
                                   SandboxRunner)
from twine.runtime.terms import ToolSpec
from twine.runtime.tooling import (Tool, ToolRegistry, ToolResult, argument_faults,
                                   load_tool_declaration, load_tool_registry,
                                   schema_faults)
from twine.runtime.tools import run_tool
from twine.runtime.tools.shell import SHELL_STDOUT_CAP_BYTES
from twine.runtime.tools.read_file import READ_FILE_CAP_BYTES

from tests.helpers import (RealGroup, RecordingRunner, dies_within, fenced_probe,
                           filled_probe, run_cli, run_inprocess)

SID = "2026-10-13-twine-runtime-tools-003"
SENTINEL_KEY = "sk-ant-sentinel-r3-never-in-the-cage"

# The seven T6 names, in the declaration's order, and the result keys the
# brief pins for each beyond `name`, `content`, `is_error` (§2).
THE_SEVEN = ["shell", "read_file", "write_file", "list_dir", "probe", "escalate",
             "deliver"]
RESULT_KEYS = {
    "shell": ["exit_code", "stdout", "stderr", "timed_out", "stdout_capped",
              "duration_seconds"],
    "read_file": ["path", "size"],
    "write_file": ["path", "size"],
    "list_dir": ["path", "entries"],
    "probe": ["slug", "leaves_cage", "exit_code", "lines"],
    "escalate": ["kind", "suspend", "questions"],
    "deliver": ["delivered", "path", "size", "sha256"],
}
BASE = ["name", "content", "is_error"]

# ---------------------------------------------------------------------------
# 1. Helpers
# ---------------------------------------------------------------------------


class Wrapping:
    """A wrapping runner (a double around the real one): passes every call
    to `inner` (run_process by default), records what it was handed — the
    argv, the timeout, the environment — the pid its hook saw, the RunResult
    it got back and, through `during(pid)`, whatever a test reads while the
    child is alive (the hook runs before the child does anything)."""

    def __init__(self, inner=run_process, during=None) -> None:
        self.inner = inner
        self.during = during
        self.calls: list[dict] = []

    def __call__(self, argv, *, cwd=None, stdin=None, timeout=None, env=None,
                 stdout_cap=None, on_spawn=None):
        seen = {"argv": tuple(argv), "cwd": cwd, "timeout": timeout, "env": env,
                "stdout_cap": stdout_cap, "hooked": on_spawn is not None, "pids": [],
                "during": None, "result": None}
        self.calls.append(seen)

        def hook(pid: int) -> None:
            seen["pids"].append(pid)
            if on_spawn is not None:
                on_spawn(pid)
            if self.during is not None:
                seen["during"] = self.during(pid)

        seen["result"] = self.inner(argv, cwd=cwd, stdin=stdin, timeout=timeout, env=env,
                                    stdout_cap=stdout_cap, on_spawn=hook)
        return seen["result"]

    def tool_calls(self) -> list[dict]:
        """The calls after the creation-time detection."""
        return [c for c in self.calls if c["argv"][-1] != "true"]


def no_unshare(argv, *, cwd=None, stdin=None, timeout=None, env=None, stdout_cap=None,
               on_spawn=None):
    """A run-seam double for a machine without `unshare`: that argv cannot
    start (RunError, as run_process raises for a missing executable); every
    other argv runs for real."""
    if argv[0] == "unshare":
        raise RunError(2, "cannot start unshare: No such file or directory")
    return run_process(argv, cwd=cwd, stdin=stdin, timeout=timeout, env=env,
                       stdout_cap=stdout_cap, on_spawn=on_spawn)


def stand_in_runtime(test: unittest.TestCase) -> int:
    """A process that leads its own group, to register as the runtime: a
    `sleep` started as a session leader (RealGroup), killed and reaped at
    cleanup. Never the test process itself — under bale's apply sandbox the
    suite runs in a PID namespace whose group leader is outside it, so
    os.getpgrp() is 0, and where the runner is the namespace's init its pid
    is 1; register_running refuses both (the HOLD of 2026-10-13). Returns
    the stand-in's pid, which is its pgid."""
    group = RealGroup(body="exec sleep 300", children=0)
    test.addCleanup(group.cleanup)
    return group.pgid


def register_stand_in(test: unittest.TestCase, state: Path) -> int:
    """register_running for SID with a stand-in runtime; its pgid."""
    pgid = stand_in_runtime(test)
    kill.register_running(state, SID, pgid, pgid)
    return pgid


class TempSandbox:
    """A state directory and a repo under one temp dir, and the sandbox."""

    def __init__(self, test: unittest.TestCase, *, run=run_process, env=None,
                 max_timeout: float = 600.0) -> None:
        self.test = test
        self.runtime_pgid: int | None = None
        tmp = tempfile.TemporaryDirectory(prefix="twine-tools-")
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.state = self.root / "state"
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / "README.txt").write_text("the real repository\n", encoding="utf-8")
        self.outside = self.root / "outside"
        self.outside.mkdir()
        (self.outside / "secret.txt").write_text("outside the cage\n", encoding="utf-8")
        self.sandbox = Sandbox.create(self.state, SID, repo=self.repo, run=run, env=env,
                                      max_timeout=max_timeout)
        self.home = self.sandbox.home

    def tool(self, name: str, **arguments) -> ToolResult:
        return run_tool(self.sandbox, name, arguments)

    def register_runtime(self) -> int:
        """The loop registers itself first (R4); here a stand-in process
        that leads its own group (stand_in_runtime). Its pgid."""
        self.runtime_pgid = register_stand_in(self.test, self.state)
        return self.runtime_pgid

    def record(self):
        return kill.read_running(self.state, SID)


def assert_shape(test: unittest.TestCase, result: ToolResult, name: str) -> dict:
    """The result's JSON twin carries exactly the base keys and the tool's
    pinned keys, in that order."""
    obj = result.as_json()
    test.assertEqual(list(obj), BASE + RESULT_KEYS[name], obj)
    test.assertEqual(obj["name"], name)
    test.assertIsInstance(obj["content"], str)
    test.assertIsInstance(obj["is_error"], bool)
    json.dumps(obj)   # plain JSON data
    return obj


def one_line(test: unittest.TestCase, stdout: str, command: str) -> dict:
    lines = stdout.split("\n")
    test.assertEqual(len(lines), 2, f"stdout must be exactly one line: {stdout!r}")
    obj = json.loads(lines[0])
    test.assertEqual(obj["command"], command)
    return obj


# ---------------------------------------------------------------------------
# 2. The declaration and the registry
# ---------------------------------------------------------------------------


def toml_tools(path: Path = TOOLS_DECLARATION) -> list[dict]:
    import tomllib
    with path.open("rb") as fh:
        return tomllib.load(fh)["tool"]


class TheToolDeclaration(unittest.TestCase):

    def test_the_seven_in_order_with_exactly_three_keys(self):
        entries = toml_tools()
        self.assertEqual([e["name"] for e in entries], THE_SEVEN)
        for entry in entries:
            with self.subTest(tool=entry["name"]):
                self.assertEqual(set(entry), {"name", "module", "leaves_cage"})
                self.assertEqual(entry["module"], f"twine.runtime.tools.{entry['name']}")
        self.assertEqual([d.name for d in load_tool_declaration()], THE_SEVEN)

    def test_only_probe_leaves_the_cage(self):
        self.assertEqual([e["name"] for e in toml_tools() if e["leaves_cage"]], ["probe"])

    def test_parity_by_name_walked_with_the_test_s_own_logic(self):
        on_disk = sorted(p.stem for p in TOOLS_DIR.glob("*.py") if p.stem != "__init__")
        self.assertEqual(on_disk, sorted(THE_SEVEN))
        self.assertEqual([p for p in TOOLS_DIR.iterdir()
                          if p.is_dir() and p.name != "__pycache__"], [])

    def test_the_registry_loads_every_tool_whole(self):
        registry = load_tool_registry()
        self.assertTrue(registry.ok, [p.message for p in registry.problems])
        self.assertEqual(registry.names, THE_SEVEN)
        for entry in registry.tools:
            with self.subTest(tool=entry.name):
                tool = entry.tool
                self.assertIsInstance(tool, Tool)
                self.assertIsInstance(tool.spec, ToolSpec)
                self.assertEqual(tool.spec.name, entry.name)
                self.assertTrue(tool.spec.description.strip())
                self.assertEqual(tool.spec.input_schema["type"], "object")
                self.assertIs(tool.spec.input_schema["additionalProperties"], False)
                self.assertEqual(schema_faults(tool.spec.input_schema), [])
                self.assertEqual(list(tool.result_keys), RESULT_KEYS[entry.name])
        self.assertEqual([s.name for s in registry.specs()], THE_SEVEN)

    def test_the_pinned_inputs(self):
        """The brief's table: each tool's arguments and which are required."""
        registry = load_tool_registry()
        wanted = {"shell": (["command", "timeout"], ["command"]),
                  "read_file": (["path"], ["path"]),
                  "write_file": (["path", "content"], ["path", "content"]),
                  "list_dir": (["path"], []),
                  "probe": (["block"], ["block"]),
                  "escalate": (["questions"], ["questions"]),
                  "deliver": (["tarball"], ["tarball"])}
        for name, (props, required) in wanted.items():
            with self.subTest(tool=name):
                schema = registry.get(name).tool.spec.input_schema
                self.assertEqual(list(schema["properties"]), props)
                self.assertEqual(list(schema["required"]), required)
        question = registry.get("escalate").tool.spec.input_schema["properties"]["questions"]
        self.assertEqual((question["minItems"], question["maxItems"]), (1, 3))
        self.assertEqual(list(question["items"]["properties"]),
                         ["question", "while_doing", "would_assume", "why_blocked"])

    def test_every_spec_is_one_the_anthropic_adapter_sends(self):
        """R2's adapter turns a ToolSpec into the API's tool object; every
        canonical tool goes through it and into a request body unchanged."""
        specs = load_tool_registry().specs()
        tools = [anthropic.tool_dict(s) for s in specs]
        body = anthropic.build_request(model="claude-haiku-5-5", max_tokens=1024,
                                       system=None,
                                       messages=[{"role": "user", "content": "hi"}],
                                       tools=tools, thinking=None, stream=False)
        self.assertEqual([t["name"] for t in body["tools"]], THE_SEVEN)
        for spec, sent in zip(specs, body["tools"]):
            self.assertEqual(sent["input_schema"], json.loads(json.dumps(
                dict(spec.input_schema))))

    def test_sandboxing_is_implemented_by_the_runtime(self):
        registry = load_runtime_registry()
        self.assertTrue(registry.ok, [p.message for p in registry.problems])
        entry = registry.get("sandboxing")
        self.assertEqual(entry.declared.status, "implemented")
        self.assertEqual(entry.declared.implemented_by, "twine.runtime.sandbox")
        self.assertEqual(entry.adapters, [])
        from twine.runtime import sandbox
        self.assertEqual(sandbox.IMPLEMENTS, ("sandboxing",))
        self.assertEqual(registry.get("tool-calling").declared.implemented_by, None)
        self.assertEqual(registry.get("tool-calling").declared.status, "implemented")


class TheToolDeclarationRefusesLoudly(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="twine-tools-decl-")
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "tools.toml"
        self.text = TOOLS_DECLARATION.read_text(encoding="utf-8")

    def refused(self, text: str, *needles: str) -> None:
        self.path.write_text(text, encoding="utf-8")
        with self.assertRaises(DeclarationError) as caught:
            load_tool_declaration(self.path)
        for needle in needles:
            self.assertIn(needle, str(caught.exception))

    def test_each_malformation(self):
        cases = {
            "missing key": (self.text.replace('leaves_cage = false\n', '', 1),
                            "'shell'", "lacks 'leaves_cage'"),
            "unknown key": (self.text.replace('name = "shell"\n',
                                              'name = "shell"\nsummary = "x"\n', 1),
                            "unknown key(s) 'summary'"),
            "bad name": (self.text.replace('name = "read_file"', 'name = "Read-File"', 1),
                         "'Read-File'"),
            "bad module": (self.text.replace('module = "twine.runtime.tools.shell"',
                                             'module = "twine.commands.shell"', 1),
                           "'twine.commands.shell'"),
            "leaves_cage not a bool": (self.text.replace('leaves_cage = true',
                                                         'leaves_cage = "yes"', 1),
                                       "'yes'"),
            "duplicate name": (self.text + '\n[[tool]]\nname = "shell"\nmodule = '
                               '"twine.runtime.tools.shell2"\nleaves_cage = false\n',
                               "declared twice"),
            "duplicate module": (self.text + '\n[[tool]]\nname = "shell2"\nmodule = '
                                 '"twine.runtime.tools.shell"\nleaves_cage = false\n',
                                 "declared for two tools"),
            "not TOML": ("[[tool]\n", "not valid TOML"),
            "no entries": ("[other]\nx = 1\n", "no [[tool]] entries", "'other'"),
        }
        for label, (text, *needles) in cases.items():
            with self.subTest(case=label):
                self.refused(text, *needles)

    def test_an_absent_declaration(self):
        with self.assertRaises(DeclarationError):
            load_tool_declaration(self.path)


class ToolParityDetectors(unittest.TestCase):
    """Each detector fires, by name, on a copy edited to be wrong."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="twine-tools-copy-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.directory = root / "tools"
        shutil.copytree(TOOLS_DIR, self.directory,
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.declaration = root / "tools.toml"
        shutil.copyfile(TOOLS_DECLARATION, self.declaration)

    def kinds(self) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        for p in load_tool_registry(self.declaration, self.directory).problems:
            found.setdefault(p.kind, []).append(p.name)
        return found

    def edit(self, name: str, old: str, new: str) -> None:
        path = self.directory / f"{name}.py"
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_the_copy_is_ok(self):
        self.assertEqual(self.kinds(), {})

    def test_a_planted_module(self):
        (self.directory / "teleport.py").write_text("TOOL = None\n", encoding="utf-8")
        self.assertEqual(self.kinds(), {"stray-module": ["teleport"]})

    def test_a_removed_module(self):
        (self.directory / "list_dir.py").unlink()
        self.assertEqual(self.kinds(), {"missing-module": ["list_dir"]})

    def test_a_module_without_a_tool(self):
        self.edit("deliver", "\nTOOL = Tool(", "\nNOT_A_TOOL = Tool(")
        self.assertEqual(self.kinds(), {"no-tool": ["deliver"]})

    def test_a_tool_for_another_name(self):
        self.edit("deliver", 'name="deliver"', 'name="hand_over"')
        self.assertEqual(self.kinds(), {"tool-mismatch": ["deliver"]})

    def test_a_schema_outside_the_subset(self):
        self.edit("read_file", '"minLength": 1,', '"pattern": "x",')
        self.assertEqual(self.kinds(), {"malformed-tool": ["read_file"]})

    def test_a_cage_mismatch(self):
        text = self.declaration.read_text(encoding="utf-8")
        self.declaration.write_text(text.replace(
            'module = "twine.runtime.tools.probe"\nleaves_cage = true',
            'module = "twine.runtime.tools.probe"\nleaves_cage = false', 1),
            encoding="utf-8")
        self.assertEqual(self.kinds(), {"cage-mismatch": ["probe"]})

    def test_a_module_that_does_not_import(self):
        (self.directory / "escalate.py").write_text("raise RuntimeError('broken')\n",
                                                    encoding="utf-8")
        self.assertEqual(self.kinds(), {"unloadable-module": ["escalate"]})


class TheRuntimeImplementer(unittest.TestCase):
    """runtime-contract.md §2.3 since R3: `implemented_by` is held as an
    adapter set is — a declared capability beside it, an implementer that
    does not stand behind it, and an adapter claiming a runtime capability
    are each named."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="twine-implementer-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        from twine.runtime import CAPABILITIES_DECLARATION, CAPABILITIES_DIR
        self.directory = root / "capabilities"
        shutil.copytree(CAPABILITIES_DIR, self.directory,
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.declaration = root / "capabilities.toml"
        shutil.copyfile(CAPABILITIES_DECLARATION, self.declaration)

    def kinds(self, old: str, new: str) -> dict[str, list[str]]:
        text = self.declaration.read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.declaration.write_text(text.replace(old, new, 1), encoding="utf-8")
        found: dict[str, list[str]] = {}
        for p in load_runtime_registry(self.declaration, self.directory).problems:
            found.setdefault(p.kind, []).append(p.name)
        return found

    def test_declared_beside_an_implementer(self):
        self.assertEqual(self.kinds('module = "twine.runtime.capabilities.sandboxing"\n'
                                    'status = "implemented"',
                                    'module = "twine.runtime.capabilities.sandboxing"\n'
                                    'status = "declared"'),
                         {"status-mismatch": ["sandboxing"]})

    def test_an_implementer_that_does_not_import(self):
        self.assertEqual(self.kinds('implemented_by = "twine.runtime.sandbox"',
                                    'implemented_by = "twine.runtime.cage"'),
                         {"missing-implementer": ["sandboxing"],
                          "status-mismatch": ["sandboxing"]})

    def test_an_implementer_that_does_not_list_it(self):
        self.assertEqual(self.kinds('implemented_by = "twine.runtime.sandbox"',
                                    'implemented_by = "twine.runtime.usage"'),
                         {"missing-implementer": ["sandboxing"],
                          "status-mismatch": ["sandboxing"]})

    def test_an_adapter_claiming_a_runtime_capability(self):
        from twine.runtime.registry import CapabilityEntry, Declared, RuntimeRegistry, \
            hold_status
        registry = RuntimeRegistry(self.declaration, self.directory)
        entry = CapabilityEntry(Declared("sandboxing", "twine.runtime.capabilities."
                                         "sandboxing", "implemented", "s",
                                         "twine.runtime.sandbox"), adapters=["fake"])
        hold_status(registry, entry)
        self.assertEqual([(p.kind, p.name) for p in registry.problems],
                         [("status-mismatch", "sandboxing")])
        self.assertIn("never implements a runtime capability", registry.problems[0].message)

    def test_a_bad_implemented_by_refuses_the_declaration(self):
        from twine.runtime.registry import load_declaration
        text = self.declaration.read_text(encoding="utf-8")
        for bad in ('"twine.runtime.capabilities"', '"twine.runtime.adapters"',
                    '"os.path"', '"twine.runtime.sandbox.Sandbox"', "42"):
            with self.subTest(implemented_by=bad):
                self.declaration.write_text(text.replace(
                    'implemented_by = "twine.runtime.sandbox"', f"implemented_by = {bad}",
                    1), encoding="utf-8")
                with self.assertRaises(DeclarationError) as caught:
                    load_declaration(self.declaration)
                self.assertIn("implemented_by", str(caught.exception))


# ---------------------------------------------------------------------------
# 3. The verb, `twine runtime tools`
# ---------------------------------------------------------------------------


class RuntimeToolsVerb(unittest.TestCase):

    def test_json_twin(self):
        run = run_cli("runtime", "tools", "--json")
        obj = one_line(self, run.stdout, "runtime tools")
        self.assertEqual((run.code, obj["ok"]), (0, True))
        self.assertEqual([t["name"] for t in obj["tools"]], THE_SEVEN)
        registry = load_tool_registry()
        for row in obj["tools"]:
            with self.subTest(tool=row["name"]):
                self.assertEqual(list(row), ["name", "description", "input_schema",
                                             "leaves_cage"])
                spec = registry.get(row["name"]).tool.spec
                self.assertEqual(row["description"], spec.description)
                self.assertEqual(row["input_schema"], json.loads(json.dumps(
                    dict(spec.input_schema))))
                self.assertIs(row["leaves_cage"], row["name"] == "probe")
        self.assertEqual(obj["counts"], {"tools": 7, "leaves_cage": 1})
        self.assertEqual((obj["problems"], obj["reason"]), ([], None))
        self.assertEqual(obj["declaration"], "twine/runtime/tools.toml")
        self.assertNotIn("Traceback", run.stderr)

    def test_human_lines(self):
        run = run_inprocess("runtime", "tools")
        self.assertEqual(run.code, 0)
        self.assertTrue(run.stdout.startswith("tool registry twine/runtime/tools.toml: ok"))
        for name in THE_SEVEN:
            self.assertIn(f"  {name} ", run.stdout)
        self.assertIn("leaves the cage  twine.runtime.tools.probe", run.stdout)

    def test_the_verb_never_touches_the_run_seam(self):
        def refuse(*args, **kwargs):
            raise AssertionError("runtime tools reached ctx.run")
        out = io.StringIO()
        ctx = Context(env={}, stdout=out, stderr=io.StringIO(), which=lambda n: None,
                      stdin=io.BytesIO(b""), run=refuse)
        self.assertEqual(main(["runtime", "tools", "--json"], ctx=ctx), 0)
        self.assertTrue(json.loads(out.getvalue())["ok"])


class RuntimeToolsOnABrokenTree(unittest.TestCase):
    """End to end on a copy of the tree, as a reviewer would: a module
    planted, one removed, the declaration broken — each NOT OK, exit 1, the
    fault named, no traceback."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="twine-tools-tree-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in ("twine", "bin", "share"):
            shutil.copytree(REPO_ROOT / name, self.root / name,
                            ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(REPO_ROOT / "VERSION", self.root / "VERSION")
        self.tools = self.root / "twine" / "runtime" / "tools"

    def run_copy(self, *argv: str):
        import subprocess
        import sys
        proc = subprocess.run([sys.executable, "-I", "-S", "-B",
                               str(self.root / "bin" / "twine"), *argv],
                              cwd=str(self.root), capture_output=True,
                              env={"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"})
        return proc.returncode, proc.stdout.decode(), proc.stderr.decode()

    def test_the_copy_is_ok(self):
        code, out, _ = self.run_copy("runtime", "tools", "--json")
        self.assertEqual((code, json.loads(out)["ok"]), (0, True))

    def test_a_planted_module(self):
        (self.tools / "teleport.py").write_text("", encoding="utf-8")
        code, out, err = self.run_copy("runtime", "tools", "--json")
        obj = one_line(self, out, "runtime tools")
        self.assertEqual((code, obj["ok"]), (1, False))
        self.assertEqual([(p["kind"], p["name"]) for p in obj["problems"]],
                         [("stray-module", "teleport")])
        self.assertIn("teleport", obj["reason"])
        self.assertNotIn("Traceback", err)
        code, out, _ = self.run_copy("runtime", "tools")
        self.assertEqual(code, 1)
        self.assertIn("NOT OK", out)
        self.assertIn("stray-module", out)

    def test_a_removed_module(self):
        (self.tools / "deliver.py").unlink()
        code, out, err = self.run_copy("runtime", "tools", "--json")
        obj = one_line(self, out, "runtime tools")
        self.assertEqual((code, obj["ok"]), (1, False))
        self.assertEqual([(p["kind"], p["name"]) for p in obj["problems"]],
                         [("missing-module", "deliver")])
        self.assertEqual(obj["tools"][-1], {"name": "deliver", "description": None,
                                            "input_schema": None, "leaves_cage": False})
        self.assertNotIn("Traceback", err)
        code, out, _ = self.run_copy("commands", "--json")
        self.assertEqual(code, 0, "every verb still loads")

    def test_a_malformed_declaration(self):
        path = self.root / "twine" / "runtime" / "tools.toml"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "leaves_cage = true", 'leaves_cage = "maybe"', 1), encoding="utf-8")
        code, out, err = self.run_copy("runtime", "tools", "--json")
        obj = one_line(self, out, "runtime tools")
        self.assertEqual((code, obj["ok"]), (1, False))
        self.assertIn("malformed", obj["reason"])
        self.assertIn("'maybe'", obj["reason"])
        self.assertEqual(obj["tools"], [])
        self.assertNotIn("Traceback", err)


# ---------------------------------------------------------------------------
# 4. The sandbox: creation, the environment, the network rule
# ---------------------------------------------------------------------------


class SandboxCreation(unittest.TestCase):

    def test_the_home_under_the_state_directory(self):
        t = TempSandbox(self)
        self.assertEqual(t.home, (t.state / "sandbox" / SID / "home").resolve())
        self.assertTrue(t.home.is_dir())
        self.assertTrue((t.home / "tmp").is_dir())
        self.assertEqual(t.sandbox.repo, t.repo.resolve())
        self.assertEqual(stat.S_IMODE(t.home.stat().st_mode), 0o700)

    def test_as_json(self):
        t = TempSandbox(self)
        obj = t.sandbox.as_json()
        base = ["sid", "home", "repo", "network", "confines", "max_timeout"]
        self.assertEqual(list(obj), base + (["reason"] if obj["network"] != "off" else []))
        self.assertEqual((obj["sid"], obj["home"], obj["repo"], obj["max_timeout"]),
                         (SID, str(t.home), str(t.repo), 600.0))
        self.assertIs(obj["confines"], obj["network"] == "off")
        json.dumps(obj)

    def test_created_twice_reuses_the_home(self):
        t = TempSandbox(self)
        (t.home / "kept.txt").write_text("x", encoding="utf-8")
        again = Sandbox.create(t.state, SID, repo=t.repo)
        self.assertEqual(again.home, t.home)
        self.assertTrue((again.home / "kept.txt").is_file())

    def test_refused_at_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for kwargs, needle in (({"sid": "../escape"}, "session id"),
                                   ({"sid": "-flag"}, "session id"),
                                   ({"repo": root / "absent"}, "not a directory"),
                                   ({"max_timeout": 0}, "max_timeout"),
                                   ({"max_timeout": -1}, "max_timeout"),
                                   ({"max_timeout": float("inf")}, "max_timeout"),
                                   ({"max_timeout": True}, "max_timeout"),
                                   ({"env": {"PATH": 7}}, "refused")):
                with self.subTest(kwargs=kwargs):
                    args = {"sid": SID, "repo": root, **kwargs}
                    with self.assertRaises(SandboxError) as caught:
                        Sandbox.create(root / "state", args.pop("sid"), **args)
                    self.assertIn(needle, str(caught.exception))
            self.assertFalse((root / "state" / "sandbox" / "..").exists()
                             and (root / "escape").exists())


class TheEnvironment(unittest.TestCase):

    def test_minimal_by_default_and_the_key_never_inherited(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": SENTINEL_KEY,
                                          "TWINE_R3_OTHER": "not passed",
                                          "PATH": "/usr/bin:/bin",
                                          "LANG": "C.UTF-8"}):
            t = TempSandbox(self)
        self.assertEqual(dict(t.sandbox.env), {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                                               "HOME": str(t.home),
                                               "TMPDIR": str(t.home / "tmp")})

    def test_fallbacks_when_the_parent_has_neither(self):
        saved = {k: os.environ.pop(k) for k in ("PATH", "LANG") if k in os.environ}
        try:
            env = dict(TempSandbox(self, run=RecordingRunner()).sandbox.env)
        finally:
            os.environ.update(saved)
        self.assertEqual((env["PATH"], env["LANG"]), (FALLBACK_PATH, FALLBACK_LANG))

    def test_what_it_is_told_to_pass_and_never_the_key(self):
        with self.assertLogs("twine.runtime.sandbox", "WARNING") as logs:
            t = TempSandbox(self, env={"PATH": "/usr/bin:/bin", "EXTRA": "passed",
                                       "HOME": "/elsewhere",
                                       "ANTHROPIC_API_KEY": SENTINEL_KEY})
        self.assertEqual(dict(t.sandbox.env), {"PATH": "/usr/bin:/bin", "EXTRA": "passed",
                                               "LANG": FALLBACK_LANG, "HOME": str(t.home),
                                               "TMPDIR": str(t.home / "tmp")})
        self.assertIn("ANTHROPIC_API_KEY", "\n".join(logs.output))
        self.assertNotIn(SENTINEL_KEY, "\n".join(logs.output))
        self.assertNotIn(SENTINEL_KEY, json.dumps(t.sandbox.as_json()))


class TheNetworkRule(unittest.TestCase):
    """Whichever way this machine goes, the sandbox reports it honestly:
    `network` and `confines` agree, and the argv the runner saw is the one
    the rule implies."""

    def test_detection_on_this_machine(self):
        wrap = Wrapping()
        t = TempSandbox(self, run=wrap)
        detect = wrap.calls[0]
        self.assertEqual(detect["argv"], ("unshare", "-rn", "true"))
        self.assertEqual(detect["cwd"], t.home)
        sb = t.sandbox
        self.assertIn(sb.network, (NETWORK_OFF, NETWORK_UNCONFINED))
        self.assertIs(sb.confines, sb.network == NETWORK_OFF)
        self.assertIs(runner_confines(sb.runner), sb.confines)
        self.assertIs(sb.runner.inner, wrap)
        result = t.tool("shell", command="echo hello")
        self.assertFalse(result.is_error, result.content)
        seen = wrap.tool_calls()[-1]["argv"]
        if sb.network == NETWORK_OFF:
            self.assertEqual(seen, ("unshare", "-rn", "--", "bash", "-c", "echo hello"))
            self.assertIsNone(sb.network_reason)
            self.assertNotIn("reason", sb.as_json())
        else:
            self.assertEqual(seen, ("bash", "-c", "echo hello"))
            self.assertTrue(sb.network_reason)
            self.assertEqual(sb.as_json()["reason"], sb.network_reason)

    def test_with_the_network_off_the_cage_has_no_interface_but_loopback(self):
        t = TempSandbox(self)
        if t.sandbox.network != NETWORK_OFF:
            self.skipTest(f"unshare is unavailable here: {t.sandbox.network_reason}")
        result = t.tool("shell", command="tail -n +3 /proc/net/dev | cut -d: -f1")
        self.assertEqual(result.as_json()["stdout"].split(), ["lo"])

    def test_no_unshare_is_unconfined_and_says_why(self):
        wrap = Wrapping(inner=no_unshare)
        sb = TempSandbox(self, run=wrap).sandbox
        self.assertEqual((sb.network, sb.confines), (NETWORK_UNCONFINED, False))
        self.assertIn("could not start", sb.network_reason)
        self.assertEqual(sb.as_json()["reason"], sb.network_reason)
        run_tool(sb, "shell", {"command": "true"})
        self.assertEqual(wrap.calls[-1]["argv"], ("bash", "-c", "true"))

    def test_a_refused_unshare_is_unconfined_and_says_why(self):
        refused = RecordingRunner(RunResult(argv=("unshare",), exit_code=1, stdout=b"",
                                            stderr=b"unshare: unshare failed: Operation "
                                                   b"not permitted\n"))
        sb = TempSandbox(self, run=refused).sandbox
        self.assertEqual((sb.network, sb.confines), (NETWORK_UNCONFINED, False))
        self.assertIn("exited 1", sb.network_reason)
        self.assertIn("Operation not permitted", sb.network_reason)

    def test_a_working_unshare_wraps_every_shell_argv(self):
        rec = RecordingRunner()
        sb = TempSandbox(self, run=rec).sandbox
        self.assertEqual((sb.network, sb.confines), (NETWORK_OFF, True))
        run_tool(sb, "shell", {"command": "id -u"})
        self.assertEqual(rec.calls[-1]["argv"],
                         ["unshare", "-rn", "--", "bash", "-c", "id -u"])

    def test_the_sandbox_runner_is_the_one_switch_point(self):
        rec = RecordingRunner()
        on, off = SandboxRunner(rec, network_off=True), SandboxRunner(rec, network_off=False)
        self.assertIs(runner_confines(on), True)
        self.assertIs(runner_confines(off), False)
        self.assertIs(runner_confines(run_process), False)
        on(["x", "y"], cwd="/", timeout=3, env={}, stdout_cap=9, on_spawn=None)
        off(["x", "y"])
        self.assertEqual([c["argv"] for c in rec.calls],
                         [["unshare", "-rn", "--", "x", "y"], ["x", "y"]])
        self.assertEqual((rec.calls[0]["cwd"], rec.calls[0]["timeout"],
                          rec.calls[0]["stdout_cap"]), ("/", 3, 9))


# ---------------------------------------------------------------------------
# 5. The file tools and the cage
# ---------------------------------------------------------------------------


class TheCage(unittest.TestCase):

    def setUp(self):
        self.t = TempSandbox(self)
        self.home = self.t.home
        os.symlink(self.t.outside / "secret.txt", self.home / "out-link")
        os.symlink(self.t.outside, self.home / "out-dir")
        (self.home / "inner").mkdir()
        (self.home / "inner" / "a.txt").write_text("inside\n", encoding="utf-8")
        os.symlink(self.home / "inner", self.home / "in-dir")

    def test_resolve_refuses_each_way_out(self):
        sb = self.t.sandbox
        for path, needle in (("../outside/secret.txt", "`..`"),
                             ("inner/../../x", "`..`"),
                             (str(self.t.outside / "secret.txt"), "absolute"),
                             (str(self.home / "inner" / "a.txt"), "absolute"),
                             ("out-link", "outside the sandbox home"),
                             ("out-dir/secret.txt", "outside the sandbox home"),
                             ("", "non-empty"), ("a\0b", "NUL")):
            with self.subTest(path=path):
                with self.assertRaises(CageError) as caught:
                    sb.resolve(path)
                self.assertIn(needle, str(caught.exception))
        self.assertEqual(sb.resolve("in-dir/a.txt"), self.home / "inner" / "a.txt")
        self.assertEqual(sb.resolve("."), self.home)
        self.assertEqual(sb.resolve("new/deeper/file"), self.home / "new/deeper/file")

    def test_every_file_tool_refuses_outside_the_cage_naming_it(self):
        attempts = [("read_file", {"path": "../outside/secret.txt"}),
                    ("read_file", {"path": "out-link"}),
                    ("read_file", {"path": str(self.t.outside / "secret.txt")}),
                    ("write_file", {"path": "out-dir/planted.txt", "content": "x"}),
                    ("write_file", {"path": "../planted.txt", "content": "x"}),
                    ("write_file", {"path": "/tmp/planted-by-twine-test", "content": "x"}),
                    ("list_dir", {"path": "out-dir"}),
                    ("list_dir", {"path": ".."}),
                    ("deliver", {"tarball": "out-link"}),
                    ("deliver", {"tarball": "../outside/secret.txt"})]
        for name, arguments in attempts:
            with self.subTest(tool=name, arguments=arguments):
                result = run_tool(self.t.sandbox, name, arguments)
                obj = assert_shape(self, result, name)
                self.assertTrue(obj["is_error"])
                self.assertIn("sandbox home", obj["content"])
                self.assertIn(str(self.home), obj["content"])
                self.assertNotIn("outside the cage\n", obj["content"])
        self.assertEqual(sorted(p.name for p in self.t.outside.iterdir()), ["secret.txt"])
        self.assertFalse(Path("/tmp/planted-by-twine-test").exists())
        self.assertFalse((self.t.root / "planted.txt").exists())

    def test_write_then_read_parents_created(self):
        written = self.t.tool("write_file", path="new/deeper/note.md", content="héllo\n")
        obj = assert_shape(self, written, "write_file")
        self.assertEqual((obj["is_error"], obj["path"], obj["size"]),
                         (False, "new/deeper/note.md", len("héllo\n".encode())))
        self.assertEqual((self.home / "new/deeper/note.md").read_bytes(),
                         "héllo\n".encode())
        read = assert_shape(self, self.t.tool("read_file", path="new/deeper/note.md"),
                            "read_file")
        self.assertEqual((read["is_error"], read["content"], read["path"], read["size"]),
                         (False, "héllo\n", "new/deeper/note.md", 7))
        again = self.t.tool("write_file", path="new/deeper/note.md", content="")
        self.assertEqual(again.as_json()["size"], 0)
        self.assertEqual((self.home / "new/deeper/note.md").read_bytes(), b"")

    def test_a_symlink_inside_the_cage_is_followed_and_reported_resolved(self):
        read = self.t.tool("read_file", path="in-dir/a.txt").as_json()
        self.assertEqual((read["is_error"], read["content"], read["path"]),
                         (False, "inside\n", "inner/a.txt"))

    def test_read_file_faults(self):
        (self.home / "latin1.txt").write_bytes(b"caf\xe9\n")
        (self.home / "big.txt").write_bytes(b"x" * (READ_FILE_CAP_BYTES + 1))
        for path, needle in (("missing.txt", "does not exist"),
                             ("inner", "is a directory"),
                             ("latin1.txt", "not UTF-8 text (byte 3"),
                             ("big.txt", "over the")):
            with self.subTest(path=path):
                obj = assert_shape(self, self.t.tool("read_file", path=path), "read_file")
                self.assertTrue(obj["is_error"])
                self.assertIn(needle, obj["content"])

    def test_write_file_onto_a_directory_or_through_a_file(self):
        for path in ("inner", ".", "inner/a.txt/below"):
            with self.subTest(path=path):
                obj = assert_shape(self, self.t.tool("write_file", path=path, content="x"),
                                   "write_file")
                self.assertTrue(obj["is_error"])
        self.assertEqual((self.home / "inner" / "a.txt").read_text(), "inside\n")

    def test_list_dir_kinds_and_order(self):
        (self.home / "inner" / "b.bin").write_bytes(b"12345")
        os.mkfifo(self.home / "inner" / "fifo")
        os.symlink("a.txt", self.home / "inner" / "c-link")
        (self.home / "inner" / "Z-dir").mkdir()
        obj = assert_shape(self, self.t.tool("list_dir", path="inner"), "list_dir")
        self.assertFalse(obj["is_error"])
        self.assertEqual(obj["path"], "inner")
        self.assertEqual(obj["entries"], [
            {"name": "Z-dir", "kind": "dir", "size": None},
            {"name": "a.txt", "kind": "file", "size": 7},
            {"name": "b.bin", "kind": "file", "size": 5},
            {"name": "c-link", "kind": "link", "size": None},
            {"name": "fifo", "kind": "other", "size": None}])
        for entry in obj["entries"]:
            self.assertIn(entry["name"], obj["content"])

    def test_list_dir_defaults_to_the_home(self):
        obj = self.t.tool("list_dir").as_json()
        self.assertEqual(obj["path"], ".")
        names = [e["name"] for e in obj["entries"]]
        self.assertEqual(names, sorted(names))
        self.assertIn("tmp", names)
        self.assertEqual({e["name"]: e["kind"] for e in obj["entries"]}["out-dir"], "link")

    def test_list_dir_faults(self):
        for path, needle in (("inner/a.txt", "not a directory"),
                             ("nowhere", "does not exist")):
            with self.subTest(path=path):
                obj = self.t.tool("list_dir", path=path).as_json()
                self.assertTrue(obj["is_error"])
                self.assertIn(needle, obj["content"])
                self.assertEqual(obj["entries"], [])


# ---------------------------------------------------------------------------
# 6. shell
# ---------------------------------------------------------------------------


class Shell(unittest.TestCase):

    def test_stdout_stderr_and_the_exit_code(self):
        t = TempSandbox(self)
        obj = assert_shape(self, t.tool("shell", command="echo out; echo err >&2; exit 3"),
                           "shell")
        self.assertEqual((obj["is_error"], obj["exit_code"], obj["stdout"], obj["stderr"],
                          obj["timed_out"], obj["stdout_capped"]),
                         (False, 3, "out\n", "err\n", False, False))
        self.assertEqual(obj["content"], "out\n[stderr]\nerr\n[exit 3]")
        self.assertIsInstance(obj["duration_seconds"], float)
        ok = t.tool("shell", command="true").as_json()
        self.assertEqual((ok["is_error"], ok["exit_code"], ok["content"]),
                         (False, 0, "[exit 0]"))

    def test_the_working_directory_is_the_home(self):
        t = TempSandbox(self)
        obj = t.tool("shell", command="pwd; touch made-here").as_json()
        self.assertEqual(obj["stdout"], f"{t.home}\n")
        self.assertTrue((t.home / "made-here").is_file())

    def test_the_environment_is_minimal_and_never_carries_the_key(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": SENTINEL_KEY,
                                          "TWINE_R3_OTHER": "not passed"}):
            t = TempSandbox(self)
            obj = t.tool("shell", command="env").as_json()
        self.assertNotIn(SENTINEL_KEY, obj["stdout"] + obj["content"])
        names = {line.split("=", 1)[0] for line in obj["stdout"].splitlines()}
        # bash itself adds PWD, SHLVL and `_`; nothing else comes from the parent.
        self.assertEqual(names - {"PWD", "SHLVL", "_"}, {"PATH", "HOME", "TMPDIR", "LANG"})
        env = dict(line.split("=", 1) for line in obj["stdout"].splitlines())
        self.assertEqual((env["HOME"], env["TMPDIR"]), (str(t.home), str(t.home / "tmp")))

    def test_a_timeout_kills_the_command_and_its_group(self):
        wrap = Wrapping()
        t = TempSandbox(self, run=wrap)
        obj = assert_shape(self, t.tool("shell", command="sleep 30 & echo $!; wait",
                                        timeout=1), "shell")
        self.assertTrue(obj["is_error"])
        self.assertEqual((obj["timed_out"], obj["exit_code"]), (True, None))
        self.assertIn("timed out after 1s", obj["content"])
        sleeper = int(obj["stdout"].split()[0])
        self.assertTrue(dies_within(sleeper), f"the backgrounded sleep {sleeper} lives on")
        result = wrap.tool_calls()[-1]["result"]
        self.assertEqual(result.group_survivors, ())
        self.assertEqual(wrap.tool_calls()[-1]["timeout"], 1.0)

    def test_the_timeout_is_capped_by_the_sandbox_and_defaults_to_it(self):
        rec = RecordingRunner()
        t = TempSandbox(self, run=rec, max_timeout=2)
        t.tool("shell", command="true", timeout=100)
        t.tool("shell", command="true")
        t.tool("shell", command="true", timeout=0.5)
        self.assertEqual([c["timeout"] for c in rec.calls[1:]], [2.0, 2.0, 0.5])
        for bad in (0, -1, "5", True):
            with self.subTest(timeout=bad):
                self.assertTrue(t.tool("shell", command="true", timeout=bad).is_error)
        self.assertEqual(len(rec.calls), 4, "a refused call runs nothing")

    def test_the_stdout_cap(self):
        t = TempSandbox(self)
        obj = t.tool("shell", command=f"head -c {SHELL_STDOUT_CAP_BYTES * 2} /dev/zero "
                                      "| tr '\\0' a").as_json()
        self.assertTrue(obj["is_error"])
        self.assertEqual((obj["stdout_capped"], obj["exit_code"]), (True, None))
        self.assertEqual(len(obj["stdout"]), SHELL_STDOUT_CAP_BYTES)
        self.assertIn(f"stdout passed {SHELL_STDOUT_CAP_BYTES} bytes", obj["content"])

    def test_output_that_is_not_utf8_is_a_result_not_an_error(self):
        t = TempSandbox(self)
        obj = t.tool("shell", command="printf 'caf\\351\\n'").as_json()
        self.assertEqual((obj["is_error"], obj["stdout"]), (False, "caf�\n"))

    def test_bash_that_cannot_start_is_an_error_result(self):
        def no_bash(argv, **kwargs):
            if "bash" in argv:
                raise RunError(2, "cannot start bash: No such file or directory")
            return run_process(argv, **kwargs)
        t = TempSandbox(self, run=no_bash)
        obj = assert_shape(self, t.tool("shell", command="true"), "shell")
        self.assertTrue(obj["is_error"])
        self.assertIn("bash could not be started", obj["content"])


# ---------------------------------------------------------------------------
# 7. The kill-switch hook
# ---------------------------------------------------------------------------


class TheKillSwitchHook(unittest.TestCase):

    def test_registered_during_the_run_and_cleared_after(self):
        state: dict = {}

        def during(pid: int):
            if "dir" not in state:   # the detection at creation, before the record
                return None
            return [g.pgid for g in kill.read_running(state["dir"], SID).groups]

        wrap = Wrapping(during=during)
        t = TempSandbox(self, run=wrap)
        state["dir"] = t.state
        t.register_runtime()
        obj = t.tool("shell", command="echo $$").as_json()
        self.assertFalse(obj["is_error"], obj["content"])
        call = wrap.tool_calls()[-1]
        self.assertTrue(call["hooked"])
        [pid] = call["pids"]
        self.assertEqual(int(obj["stdout"]), pid, "the hook is handed the child's pid")
        self.assertEqual(call["during"], [pid], "the record names the group while it runs")
        self.assertEqual(call["result"].group_survivors, ())
        self.assertEqual(t.record().groups, (), "cleared once the run returned")
        self.assertEqual(t.record().pgid, t.runtime_pgid, "the runtime's own is untouched")
        self.assertEqual(t.sandbox.last_spawn, {"argv": ["bash", "-c", "echo $$"],
                                                "registered": [pid], "cleared": True})

    def test_the_detection_at_creation_is_registered_too(self):
        """Whatever this machine's `unshare` does, the detection is a spawn
        like any other: a double runs `true` in its place (a real child,
        so the hook has a pid) and the record shows it registered and
        cleared."""
        def detect_with_true(argv, **kwargs):
            if tuple(argv) == ("unshare", "-rn", "true"):
                argv = ("true",)
            return run_process(argv, **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            register_stand_in(self, state)
            wrap = Wrapping(inner=detect_with_true)
            sb = Sandbox.create(state, SID, repo=Path(tmp), run=wrap)
            self.assertTrue(wrap.calls[0]["hooked"])
            self.assertEqual(len(wrap.calls[0]["pids"]), 1)
            self.assertEqual(sb.last_spawn, {"argv": ["unshare", "-rn", "true"],
                                             "registered": wrap.calls[0]["pids"],
                                             "cleared": True})
            self.assertEqual(kill.read_running(state, SID).groups, ())
            self.assertEqual(sb.network, NETWORK_OFF)

    def test_a_record_that_cannot_be_read_refuses_the_sandbox_at_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            (state / "running").mkdir(parents=True)
            (state / "running" / f"{SID}.json").write_text("[]", encoding="utf-8")
            rec = RecordingRunner()
            with self.assertRaises(SandboxError) as caught:
                Sandbox.create(state, SID, repo=Path(tmp), run=rec)
            self.assertIn("running record", str(caught.exception))
            self.assertEqual(rec.calls, [], "nothing was started")

    def test_without_a_record_the_run_proceeds_unregistered_and_says_so(self):
        wrap = Wrapping()
        t = TempSandbox(self, run=wrap)
        with self.assertLogs("twine.runtime.sandbox", "INFO") as logs:
            obj = t.tool("shell", command="echo ran").as_json()
        self.assertEqual((obj["is_error"], obj["stdout"]), (False, "ran\n"))
        self.assertFalse(wrap.tool_calls()[-1]["hooked"])
        self.assertIn("no running record", "\n".join(logs.output))
        self.assertIsNone(t.record())
        self.assertFalse((t.state / "running").exists(), "nothing written")

    def test_a_record_that_cannot_be_read_refuses_the_spawn(self):
        rec = RecordingRunner()
        t = TempSandbox(self, run=rec)
        (t.state / "running").mkdir()
        (t.state / "running" / f"{SID}.json").write_text("{not json", encoding="utf-8")
        before = len(rec.calls)
        for name, arguments in (("shell", {"command": "echo never"}),
                                ("probe", {"block": fenced_probe(filled_probe())})):
            with self.subTest(tool=name):
                obj = assert_shape(self, run_tool(t.sandbox, name, arguments), name)
                self.assertTrue(obj["is_error"])
                self.assertIn("running record", obj["content"])
        self.assertEqual(len(rec.calls), before, "nothing was started")

    def test_a_hook_that_cannot_register_is_an_error_and_the_child_never_ran(self):
        """The seam kills the child when its hook raises (cli-contract.md
        §10.6); a double stands in for it here, handing the hook the runtime's
        own group, which register_group refuses."""
        runtime: dict[str, int] = {}

        def hands_back_the_runtime_s_group(argv, *, on_spawn=None, **kwargs):
            if argv[-1] == "true":
                return RunResult(argv=tuple(argv), exit_code=1, stdout=b"", stderr=b"")
            on_spawn(runtime["pgid"])
            raise AssertionError("the hook should have raised")
        t = TempSandbox(self, run=hands_back_the_runtime_s_group)
        runtime["pgid"] = t.register_runtime()
        obj = assert_shape(self, t.tool("shell", command="echo never"), "shell")
        self.assertTrue(obj["is_error"])
        self.assertIn("could not register", obj["content"])
        self.assertIn("runtime's own", obj["content"])

    def test_a_group_with_survivors_stays_recorded(self):
        stray = 2 ** 22 + 11   # a pgid no process holds: register_group takes it

        def leaves_a_survivor(argv, *, on_spawn=None, **kwargs):
            if argv[-1] != "true":
                on_spawn(stray)
            return RunResult(argv=tuple(argv), exit_code=0, stdout=b"", stderr=b"",
                             group_survivors=(stray + 1,))
        t = TempSandbox(self, run=leaves_a_survivor)
        t.register_runtime()
        with self.assertLogs("twine.runtime.sandbox", "WARNING") as logs:
            t.tool("shell", command="echo hi")
        self.assertEqual([g.pgid for g in t.record().groups], [stray])
        self.assertEqual(t.sandbox.last_spawn["cleared"], False)
        self.assertIn("stays in the running record", "\n".join(logs.output))


# ---------------------------------------------------------------------------
# 8. probe
# ---------------------------------------------------------------------------


class Probe(unittest.TestCase):

    BODY = 'echo "--- section: repo ---"\nls\necho "--- section: env ---"\nenv | sort'

    def probe(self, t: TempSandbox, script: str) -> dict:
        return assert_shape(self, t.tool("probe", block=fenced_probe(script)), "probe")

    def test_a_read_only_block_runs_against_the_repo_and_returns_the_paste(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": SENTINEL_KEY}):
            t = TempSandbox(self)
            obj = self.probe(t, filled_probe(self.BODY))
        self.assertFalse(obj["is_error"], obj["content"])
        self.assertEqual((obj["slug"], obj["leaves_cage"], obj["exit_code"]),
                         ("twine-take-fixture", True, 0))
        report = shapes.find_blocks(obj["content"])
        [block] = report.blocks
        self.assertEqual((block.kind, block.ok, block.fields["slug"]),
                         (shapes.PROBE_OUTPUT, True, "twine-take-fixture"))
        self.assertEqual(obj["lines"], block.integrity["expected_lines"])
        self.assertEqual(shapes.block_text(obj["content"], block), obj["content"])
        self.assertIn("README.txt", obj["content"], "it ran in the real repository")
        self.assertNotIn(SENTINEL_KEY, obj["content"])
        self.assertIn(f"HOME={t.home}", obj["content"])

    def test_it_registers_with_the_kill_switch_and_clears(self):
        wrap = Wrapping()
        t = TempSandbox(self, run=wrap)
        t.register_runtime()
        obj = self.probe(t, filled_probe())
        self.assertFalse(obj["is_error"], obj["content"])
        call = wrap.tool_calls()[-1]
        self.assertEqual((Path(call["argv"][0]).name, call["argv"][1]), ("bash", "-c"),
                         "the probe runs unwrapped: it leaves the cage")
        self.assertEqual(call["env"], dict(t.sandbox.env))
        self.assertEqual(call["cwd"], str(t.repo.resolve()))
        self.assertTrue(call["hooked"])
        self.assertEqual(t.sandbox.last_spawn["registered"], call["pids"])
        self.assertEqual(t.record().groups, ())

    def test_refused_before_running(self):
        rec = RecordingRunner()
        t = TempSandbox(self, run=rec)
        good = filled_probe()
        no_read_only = "\n".join(line for line in good.split("\n")
                                 if not line.startswith("# Read-only:")) + "\n"
        cases = {"no read-only line": (fenced_probe(no_read_only), "Read-only"),
                 "malformed (unclosed fence)": ("```bash\n" + good, "malformed"),
                 "no probe block": ("just prose, no block\n", "no probe block"),
                 "two probe blocks": (fenced_probe(good) + "\n" + fenced_probe(good),
                                      "2 probe blocks"),
                 "the unfilled scaffold": (fenced_probe(
                     (REPO_ROOT / "fixtures/bale-0.4.51/crafter/"
                      "--probe-twine-take-fixture.txt").read_text()), "TODO(worker)")}
        before = len(rec.calls)
        for label, (text, needle) in cases.items():
            with self.subTest(case=label):
                obj = assert_shape(self, t.tool("probe", block=text), "probe")
                self.assertTrue(obj["is_error"])
                self.assertTrue(obj["leaves_cage"])
                self.assertIn(needle, obj["content"])
        self.assertEqual(len(rec.calls), before, "nothing ran")

    def test_a_probe_that_fails_or_prints_no_block(self):
        t = TempSandbox(self)
        script = filled_probe().replace("emit_probe_block\n", "exit 4\n")
        obj = self.probe(t, script)
        self.assertTrue(obj["is_error"])
        self.assertEqual(obj["exit_code"], 4)
        self.assertIn("exited 4", obj["content"])
        self.assertIn("no `=== PROBE BEGIN twine-take-fixture ===` block", obj["content"])


# ---------------------------------------------------------------------------
# 9. escalate and deliver
# ---------------------------------------------------------------------------


def question(n: int) -> dict:
    return {"question": f"Question {n}: keep the default?",
            "while_doing": f"step {n} of the build",
            "would_assume": "yes", "why_blocked": "the brief names both"}


class Escalate(unittest.TestCase):

    def setUp(self):
        self.t = TempSandbox(self, run=RecordingRunner())

    def test_one_and_three_questions_read_back_intact(self):
        for count in (1, 3):
            with self.subTest(questions=count):
                rows = [question(n) for n in range(1, count + 1)]
                obj = assert_shape(self, self.t.tool("escalate", questions=rows),
                                   "escalate")
                self.assertEqual((obj["is_error"], obj["kind"], obj["suspend"],
                                  obj["questions"]), (False, "light", True, count))
                [block] = shapes.find_blocks(obj["content"]).blocks
                self.assertEqual((block.kind, block.ok, block.fields["sid"]),
                                 (shapes.LIGHT, True, SID))
                self.assertEqual(block.fields["questions"], [
                    {"question": r["question"], "context": r["while_doing"],
                     "default_assumption": r["would_assume"],
                     "why_blocked": r["why_blocked"]} for r in rows])
                self.assertEqual(shapes.block_text(obj["content"], block), obj["content"])
                self.assertIn('Reply: answer inline, "as assumed", or "formal".',
                              obj["content"])

    def test_the_layout_is_tarball_md_s(self):
        obj = self.t.tool("escalate", questions=[question(1)]).as_json()
        self.assertEqual(obj["content"].split("\n")[:5], [
            f"=== LIGHT BEGIN {SID} ===",
            "[1] question:     Question 1: keep the default?",
            "    while doing:  step 1 of the build",
            "    would assume: yes",
            "    why blocked:  the brief names both"])

    def test_four_questions_or_none_is_an_error(self):
        for rows in ([question(n) for n in range(1, 5)], []):
            with self.subTest(count=len(rows)):
                obj = assert_shape(self, self.t.tool("escalate", questions=rows),
                                   "escalate")
                self.assertTrue(obj["is_error"])
                self.assertIs(obj["suspend"], False)

    def test_a_field_empty_or_not_one_line_is_an_error(self):
        for key, value in (("would_assume", "   "), ("question", "two\nlines"),
                           ("why_blocked", "carriage\rreturn")):
            with self.subTest(key=key):
                row = dict(question(1), **{key: value})
                obj = self.t.tool("escalate", questions=[row]).as_json()
                self.assertTrue(obj["is_error"])
                self.assertIn(key, obj["content"])
                self.assertIs(obj["suspend"], False)

    def test_a_question_missing_a_field_is_refused_by_the_schema(self):
        row = question(1)
        del row["why_blocked"]
        obj = self.t.tool("escalate", questions=[row]).as_json()
        self.assertTrue(obj["is_error"])
        self.assertIn("why_blocked", obj["content"])


class Deliver(unittest.TestCase):

    def test_a_file_in_the_cage(self):
        t = TempSandbox(self, run=RecordingRunner())
        data = os.urandom(3000)
        (t.home / "out").mkdir()
        (t.home / "out" / f"response-{SID}.tar.gz").write_bytes(data)
        obj = assert_shape(self, t.tool("deliver", tarball=f"out/response-{SID}.tar.gz"),
                           "deliver")
        self.assertEqual((obj["is_error"], obj["delivered"], obj["path"], obj["size"],
                          obj["sha256"]),
                         (False, True, f"out/response-{SID}.tar.gz", 3000,
                          hashlib.sha256(data).hexdigest()))
        self.assertIn(obj["sha256"], obj["content"])

    def test_faults(self):
        t = TempSandbox(self, run=RecordingRunner())
        (t.home / "a-dir").mkdir()
        for path, needle in (("missing.tar.gz", "does not exist"),
                             ("a-dir", "not a regular file"),
                             ("../outside/secret.txt", "`..`"),
                             (str(t.outside / "secret.txt"), "absolute")):
            with self.subTest(path=path):
                obj = assert_shape(self, t.tool("deliver", tarball=path), "deliver")
                self.assertEqual((obj["is_error"], obj["delivered"]), (True, False))
                self.assertIn(needle, obj["content"])


# ---------------------------------------------------------------------------
# 10. run_tool, results, and the import rule
# ---------------------------------------------------------------------------


class RunTool(unittest.TestCase):

    def setUp(self):
        self.t = TempSandbox(self, run=RecordingRunner())

    def test_an_unknown_tool_is_an_error_result(self):
        with self.assertLogs("twine.runtime.tooling", "WARNING"):
            result = run_tool(self.t.sandbox, "teleport", {})
        self.assertEqual(result.as_json(), {
            "name": "teleport", "is_error": True,
            "content": "no tool is named 'teleport'; the tools are " + ", ".join(THE_SEVEN)})
        self.assertEqual(list(result.as_json()), BASE)
        with self.assertLogs("twine.runtime.tooling", "WARNING"):
            self.assertTrue(run_tool(self.t.sandbox, None, {}).is_error)

    def test_arguments_the_schema_refuses(self):
        cases = [("shell", {}, "lacks the required 'command'"),
                 ("shell", {"command": 5}, "'command' must be a string"),
                 ("shell", {"command": "x", "cwd": "/"}, "carries 'cwd'"),
                 ("read_file", {"path": ""}, "shorter than 1"),
                 ("write_file", {"path": "a"}, "lacks the required 'content'"),
                 ("list_dir", {"path": ["."]}, "must be a string"),
                 ("escalate", {"questions": "one"}, "must be an array"),
                 ("escalate", {"questions": [{"question": 1}]}, "questions'[1].question"),
                 ("deliver", {"tarball": None}, "not null")]
        for name, arguments, needle in cases:
            with self.subTest(tool=name, arguments=arguments):
                obj = assert_shape(self, run_tool(self.t.sandbox, name, arguments), name)
                self.assertTrue(obj["is_error"])
                self.assertIn("input schema", obj["content"])
                self.assertIn(needle.replace("not null", "null"), obj["content"])
        self.assertTrue(run_tool(self.t.sandbox, "shell", ["command"]).is_error)

    def test_a_tool_that_raises_is_still_a_result(self):
        def explode(sandbox, arguments):
            raise KeyError("boom")
        tool = Tool(spec=ToolSpec("boom", "explodes", {
                        "type": "object", "properties": {}, "additionalProperties": False}),
                    leaves_cage=False, result_keys=("k",), error_defaults={"k": None},
                    execute=explode)
        from twine.runtime.tooling import DeclaredTool, ToolEntry
        registry = ToolRegistry(TOOLS_DECLARATION, TOOLS_DIR,
                                tools=[ToolEntry(DeclaredTool("boom", "twine.runtime.tools."
                                                              "boom", False), tool)])
        with self.assertLogs("twine.runtime.tooling", "ERROR"):
            result = run_tool(self.t.sandbox, "boom", {}, registry=registry)
        self.assertEqual(result.as_json(), {"name": "boom", "is_error": True, "k": None,
                                            "content": "boom failed inside twine: "
                                                       "KeyError: 'boom'"})

    def test_a_result_feeds_the_adapter_s_tool_result_block(self):
        result = run_tool(self.t.sandbox, "read_file", {"path": "nope"})
        message = anthropic.tool_result_message([("toolu_1", result.content,
                                                  result.is_error)])
        self.assertEqual(message["content"][0], {"type": "tool_result",
                                                 "tool_use_id": "toolu_1",
                                                 "content": result.content,
                                                 "is_error": True})

    def test_the_schema_subset_checker(self):
        self.assertEqual(argument_faults({"type": "object", "properties": {
            "n": {"type": "integer"}}, "additionalProperties": False}, {"n": True}),
            ["'n' must be an integer, not a boolean"])
        self.assertIn("outside the checked subset",
                      " ".join(schema_faults({"type": "object", "properties": {},
                                              "additionalProperties": False,
                                              "oneOf": []})))
        self.assertTrue(schema_faults({"type": "object", "properties": {}}))


class TheImportRule(unittest.TestCase):
    """The brief: no module under twine/runtime/ imports subprocess, socket
    or anthropic (R2's transport keeps its exception for http.client and
    ssl, and imports none of the three either), and none reads the process
    environment; processes go through the run seam, PATH and LANG through
    twine.process.inherited_environment."""

    def roots(self, path: Path) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module.split(".")[0])
        return found

    def test_no_runtime_module_imports_subprocess_socket_or_anthropic(self):
        files = sorted(RUNTIME_DIR.rglob("*.py"))
        self.assertIn(RUNTIME_DIR / "sandbox.py", files)
        self.assertIn(RUNTIME_DIR / "tools" / "shell.py", files)
        for path in files:
            with self.subTest(file=path.relative_to(REPO_ROOT).as_posix()):
                self.assertEqual(self.roots(path) & {"subprocess", "socket", "anthropic",
                                                     "multiprocessing", "pty", "os"}, set())

    def test_the_sandbox_reads_the_environment_through_the_seam_s_module_only(self):
        source = (RUNTIME_DIR / "sandbox.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        touched = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                   and n.attr in ("environ", "getenv", "environb")}
        touched |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
                    and n.id in ("environ", "getenv")}
        self.assertEqual(touched, set())
        self.assertIn("process.inherited_environment(INHERITED)", source)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": SENTINEL_KEY,
                                          "PATH": "/p", "LANG": "L"}):
            self.assertEqual(process.inherited_environment(("PATH", "LANG", "ABSENT")),
                             {"PATH": "/p", "LANG": "L"})

    def test_nothing_else_spawns_in_r3(self):
        """Every spawn of the sandbox and the tools goes through
        Sandbox.spawn: no tool module calls a runner itself."""
        for path in sorted((RUNTIME_DIR / "tools").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotIn("run_process", text)
                self.assertIsNone(re.search(r"sandbox\.runner\(|sandbox\.run\(", text))


if __name__ == "__main__":
    unittest.main()

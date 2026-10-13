"""The runtime (Arc 2 R1): the capability registry and its parity by name,
the adapter boundary and its one stop spelling, the fake transport adapter
driven through it, the Anthropic usage mapping onto the five token classes,
and the two verbs, `twine runtime list` and `twine runtime show`.

Arc 2 R2 (session 2026-10-13-twine-runtime-anthropic-002) moved what R1's
facts became: `anthropic` registered beside `fake`, prompt-caching and
streaming implemented, the boundary refusing the loop's keys, from_anthropic
living in twine.runtime.usage (re-exported), null cache counts read as 0,
and the provider directory holding the wire recordings of 2026-10-13. The
Anthropic adapter's own tests are tests/test_anthropic.py.

No test here reaches a network, reads a key or imports a provider SDK
(T8): the model is the fake adapter, and the provider's usage is the
architect's recording under fixtures/anthropic/.

Sections:
  1. The declaration: the eight, the statuses, refusals
  2. Parity by name, and its detectors
  3. from_anthropic
  4. The boundary and the fake adapter
  5. The verbs
  6. No network, no key
  7. The recording and its README row
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import importlib
import inspect
import io
import json
import re
import shutil
import tempfile
import tomllib
import unittest
from decimal import Decimal
from pathlib import Path

from twine import FIXTURES_DIR, REPO_ROOT, TRANSITIONS_TABLE, transitions
from twine.cli import Context, main
from twine.runtime import CAPABILITIES_DECLARATION, CAPABILITIES_DIR, RUNTIME_DIR
from twine.runtime.adapters.fake import (FakeAdapter, FakeScript, FakeScriptError,
                                         FakeScriptExhausted)
from twine.runtime.boundary import (BOUNDARY_CAPABILITIES, Adapter, Boundary, BoundaryError,
                                    Request, SpawnSettings, Turn)
from twine.runtime.capabilities.usage_accounting import UsageMappingError, from_anthropic
from twine.runtime.contract import Contract
from twine.runtime.terms import (TEXT, THINKING_OFF, ThinkingSettings, ThinkingSettingsError,
                                 ToolCall, ToolSpec)
from twine.runtime.registry import (STATUSES, DeclarationError, load_declaration,
                                    load_runtime_registry, module_names)
from twine.spend import ModelPrice, Tokens, UsageRecord, record_cost

from tests.helpers import run_cli, run_inprocess

# The eight capabilities §4.1 names, in its order, under the brief's names.
THE_EIGHT = ["tool-calling", "thinking", "prompt-caching", "window-accounting",
             "streaming", "sandboxing", "suspend-resume", "usage-accounting"]
# The three the fake adapter implements — the `implemented` ones at R1.
THE_THREE = {"tool-calling", "thinking", "usage-accounting"}
# What the Anthropic adapter implements (R2): the three, prompt caching and
# streaming — the `implemented` ones at R2.
ANTHROPIC_FIVE = THE_THREE | {"prompt-caching", "streaming"}
# What the runtime implements itself (R3): sandboxing, by
# twine/runtime/sandbox.py — the declaration's `implemented_by`.
RUNTIME_OWN = {"sandboxing": "twine.runtime.sandbox"}
IMPLEMENTED = ANTHROPIC_FIVE | set(RUNTIME_OWN)

RECORDING = FIXTURES_DIR / "anthropic" / "messages-usage-2026-10-08.json"
RECORDING_BYTES = 293
RECORDING_SHA = "98137f648aa03f5c73628db77527df11b7f0d3222067f499e6b7573521f2b094"

SETTINGS = SpawnSettings(model="fake-model", max_tokens=1024, thinking=THINKING_OFF)
THINKING_ON = SpawnSettings(model="fake-model", max_tokens=1024,
                            thinking=ThinkingSettings(enabled=True, budget_tokens=512))


def usage(**counts) -> dict:
    """A scripted usage in twine's five classes (a double: not a provider's)."""
    base = {"input": 10, "output": 5, "thinking": None, "cache_read": 0, "cache_write": 0}
    base.update(counts)
    return base


def recorded_usage() -> dict:
    return json.loads(RECORDING.read_bytes())


def one_line(test: unittest.TestCase, stdout: str, command: str) -> dict:
    lines = stdout.split("\n")
    test.assertEqual(len(lines), 2, f"stdout must be exactly one line: {stdout!r}")
    test.assertEqual(lines[1], "")
    obj = json.loads(lines[0])
    test.assertEqual(obj["command"], command)
    test.assertIsInstance(obj["ok"], bool)
    return obj


def toml_entries(path: Path = CAPABILITIES_DECLARATION) -> list[dict]:
    """The declaration read with tomllib directly — logic of the test's own,
    not the registry's."""
    with path.open("rb") as fh:
        return tomllib.load(fh)["capability"]


class TempCopy:
    """A temp copy of the capabilities directory and the declaration, for
    the detectors: the registry pointed at it loads modules by file path,
    leaving the real package alone."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="twine-runtime-")
        self.root = Path(self._tmp.name)
        self.directory = self.root / "capabilities"
        shutil.copytree(CAPABILITIES_DIR, self.directory,
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.declaration = self.root / "capabilities.toml"
        shutil.copyfile(CAPABILITIES_DECLARATION, self.declaration)

    def load(self):
        return load_runtime_registry(self.declaration, self.directory)

    def edit_declaration(self, old: str, new: str) -> None:
        text = self.declaration.read_text(encoding="utf-8")
        assert old in text, old
        self.declaration.write_text(text.replace(old, new, 1), encoding="utf-8")

    def cleanup(self) -> None:
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# 1. The declaration: the eight, the statuses, refusals
# ---------------------------------------------------------------------------


class TheDeclaration(unittest.TestCase):

    def test_the_eight_in_section_4_1_order(self):
        self.assertEqual([e["name"] for e in toml_entries()], THE_EIGHT)
        self.assertEqual([d.name for d in load_declaration()], THE_EIGHT)

    def test_every_entry_has_exactly_the_four_keys(self):
        """Four keys, and since R3 `implemented_by` beside them exactly where
        the runtime implements the capability itself."""
        for entry in toml_entries():
            with self.subTest(capability=entry.get("name")):
                extra = {"implemented_by"} if entry["name"] in RUNTIME_OWN else set()
                self.assertEqual(set(entry), {"name", "module", "status", "summary"} | extra)
                if extra:
                    self.assertEqual(entry["implemented_by"], RUNTIME_OWN[entry["name"]])

    def test_every_entry_loads(self):
        registry = load_runtime_registry()
        self.assertTrue(registry.ok, [p.message for p in registry.problems])
        for entry in registry.capabilities:
            with self.subTest(capability=entry.name):
                self.assertIsInstance(entry.contract, Contract)
                self.assertEqual(entry.contract.capability, entry.name)
                self.assertEqual(entry.contract.faults(), [])

    def test_the_status_set_is_closed_and_three(self):
        self.assertEqual(STATUSES, ("declared", "implemented", "experimental"))
        for entry in toml_entries():
            with self.subTest(capability=entry["name"]):
                self.assertIn(entry["status"], STATUSES)

    def test_six_implemented_two_declared(self):
        """R1 had three implemented (the fake's) and five declared; R2's
        adapter implements prompt-caching and streaming too; R3's sandbox is
        the runtime's own implementation of sandboxing."""
        statuses = {e["name"]: e["status"] for e in toml_entries()}
        self.assertEqual({n for n, s in statuses.items() if s == "implemented"},
                         IMPLEMENTED)
        self.assertEqual({n for n, s in statuses.items() if s == "declared"},
                         set(THE_EIGHT) - IMPLEMENTED)

    def test_the_declared_two_have_their_contracts_written(self):
        registry = load_runtime_registry()
        for name in set(THE_EIGHT) - IMPLEMENTED:
            with self.subTest(capability=name):
                contract = registry.get(name).contract
                self.assertTrue(contract.purpose.strip())
                self.assertTrue(contract.adapter_must)
                self.assertTrue(contract.runtime_promises)
                self.assertIn("declared", contract.lands)

    def test_delegate_is_not_r1s(self):
        """§4.5's first experimental capability is R8's."""
        self.assertNotIn("delegate", [e["name"] for e in toml_entries()])

    def test_the_boundary_capabilities_are_declared(self):
        names = {e["name"] for e in toml_entries()}
        self.assertLessEqual(set(BOUNDARY_CAPABILITIES), names)
        self.assertEqual(set(BOUNDARY_CAPABILITIES), THE_THREE)


class MalformedDeclarationRefusesLoudly(unittest.TestCase):

    def setUp(self):
        self.copy = TempCopy()
        self.addCleanup(self.copy.cleanup)

    def assertRefused(self, *fragments: str) -> None:
        with self.assertRaises(DeclarationError) as caught:
            load_declaration(self.copy.declaration)
        for fragment in fragments:
            self.assertIn(fragment, str(caught.exception))

    def test_a_status_outside_the_three(self):
        # window-accounting: still declared at R2 (streaming, R1's example,
        # is implemented now).
        self.copy.edit_declaration('name = "window-accounting"\nmodule = "twine.runtime.capabilities.window_accounting"\nstatus = "declared"',
                                   'name = "window-accounting"\nmodule = "twine.runtime.capabilities.window_accounting"\nstatus = "beta"')
        self.assertRefused("'window-accounting'", "'beta'", "declared, implemented, experimental")

    def test_a_missing_key(self):
        self.copy.edit_declaration('module = "twine.runtime.capabilities.thinking"\n', "")
        self.assertRefused("'thinking'", "lacks 'module'")

    def test_an_unknown_key(self):
        self.copy.edit_declaration('module = "twine.runtime.capabilities.thinking"\n',
                                   'module = "twine.runtime.capabilities.thinking"\nadapters = ["fake"]\n')
        self.assertRefused("'thinking'", "unknown key(s) 'adapters'")

    def test_a_bad_name(self):
        self.copy.edit_declaration('name = "thinking"', 'name = "Thinking_Mode"')
        self.assertRefused("'Thinking_Mode'", "lowercase words joined by hyphens")

    def test_a_bad_module(self):
        for bad in ("thinking", "twine.runtime.capabilities.thinking.py",
                    "twine.runtime.thinking", "twine.runtime.capabilities._thinking",
                    "twine.runtime.capabilities.a.b"):
            with self.subTest(module=bad):
                self.copy.declaration.write_text(
                    CAPABILITIES_DECLARATION.read_text(encoding="utf-8").replace(
                        'module = "twine.runtime.capabilities.thinking"',
                        f'module = "{bad}"'), encoding="utf-8")
                self.assertRefused(f"{bad!r}", "directly under twine.runtime.capabilities")

    def test_a_duplicate_name(self):
        self.copy.edit_declaration('name = "thinking"', 'name = "tool-calling"')
        self.assertRefused("'tool-calling' is declared twice")

    def test_a_duplicate_module(self):
        self.copy.edit_declaration('module = "twine.runtime.capabilities.thinking"', 'module = "twine.runtime.capabilities.tool_calling"')
        self.assertRefused("'twine.runtime.capabilities.tool_calling' is declared for two capabilities")

    def test_not_toml(self):
        self.copy.declaration.write_text("[[capability]\nname =", encoding="utf-8")
        self.assertRefused("not valid TOML")

    def test_no_entries_and_a_stray_table(self):
        self.copy.declaration.write_text("[other]\nx = 1\n", encoding="utf-8")
        self.assertRefused("no [[capability]] entries", "unknown top-level key(s) 'other'")

    def test_an_absent_file(self):
        self.copy.declaration.unlink()
        self.assertRefused("capabilities.toml")

    def test_the_registry_refuses_it_too(self):
        self.copy.edit_declaration('status = "implemented"', 'status = "done"')
        with self.assertRaises(DeclarationError):
            self.copy.load()


# ---------------------------------------------------------------------------
# 2. Parity by name, and its detectors
# ---------------------------------------------------------------------------


class ParityByName(unittest.TestCase):
    """The parity pair, each failing by name — walked with logic of the
    test's own (a directory listing and tomllib), not the registry's."""

    def on_disk(self) -> set[str]:
        stems = {p.stem for p in CAPABILITIES_DIR.glob("*.py") if p.name != "__init__.py"}
        packages = {p.name for p in CAPABILITIES_DIR.iterdir()
                    if p.is_dir() and (p / "__init__.py").is_file()}
        return stems | packages

    def test_every_module_is_listed(self):
        listed = {e["module"].rsplit(".", 1)[1] for e in toml_entries()}
        for name in sorted(self.on_disk()):
            with self.subTest(module=name):
                self.assertIn(name, listed, f"twine/runtime/capabilities/{name} is not "
                              "declared in twine/runtime/capabilities.toml")

    def test_every_listed_capability_has_its_module(self):
        present = self.on_disk()
        for entry in toml_entries():
            with self.subTest(capability=entry["name"]):
                self.assertIn(entry["module"].rsplit(".", 1)[1], present,
                              f"capability {entry['name']!r}: its module "
                              f"{entry['module']} is missing")

    def test_the_registry_walks_the_same_directory(self):
        self.assertEqual(set(module_names()), self.on_disk())


class ParityDetectors(unittest.TestCase):
    """Each detector fires, by name, on a copy edited to be wrong."""

    def setUp(self):
        self.copy = TempCopy()
        self.addCleanup(self.copy.cleanup)

    def kinds(self, registry) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        for p in registry.problems:
            found.setdefault(p.kind, []).append(p.name)
        return found

    def test_the_copy_is_ok(self):
        self.assertTrue(self.copy.load().ok)

    def test_a_planted_module_is_named(self):
        (self.copy.directory / "teleport.py").write_text(
            "CONTRACT = None\n", encoding="utf-8")
        registry = self.copy.load()
        self.assertFalse(registry.ok)
        self.assertEqual(self.kinds(registry), {"stray-module": ["teleport"]})
        self.assertIn("teleport", registry.problems[0].message)

    def test_a_planted_package_is_named(self):
        (self.copy.directory / "warp").mkdir()
        (self.copy.directory / "warp" / "__init__.py").write_text("", encoding="utf-8")
        self.assertEqual(self.kinds(self.copy.load()), {"stray-module": ["warp"]})

    def test_a_removed_module_is_named_by_its_capability(self):
        (self.copy.directory / "streaming.py").unlink()
        registry = self.copy.load()
        self.assertFalse(registry.ok)
        self.assertEqual(self.kinds(registry), {"missing-module": ["streaming"]})
        self.assertIn("'streaming'", registry.problems[0].message)

    def test_a_module_without_a_contract(self):
        (self.copy.directory / "sandboxing.py").write_text('"""no contract"""\n',
                                                           encoding="utf-8")
        self.assertEqual(self.kinds(self.copy.load()), {"no-contract": ["sandboxing"]})

    def test_a_contract_for_another_capability(self):
        path = self.copy.directory / "streaming.py"
        path.write_text(path.read_text(encoding="utf-8").replace(
            'capability="streaming"', 'capability="sandboxing"'), encoding="utf-8")
        self.assertEqual(self.kinds(self.copy.load()), {"contract-mismatch": ["streaming"]})

    def test_a_contract_that_is_not_whole(self):
        path = self.copy.directory / "streaming.py"
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"runtime_promises=\(.*?\),\n    lands",
                      "runtime_promises=(),\n    lands", text, flags=re.S)
        path.write_text(text, encoding="utf-8")
        self.assertEqual(self.kinds(self.copy.load()), {"malformed-contract": ["streaming"]})

    def test_a_module_that_does_not_import(self):
        (self.copy.directory / "suspend_resume.py").write_text(
            "raise RuntimeError('broken on purpose')\n", encoding="utf-8")
        registry = self.copy.load()
        self.assertEqual(self.kinds(registry), {"unloadable-module": ["suspend-resume"]})
        self.assertIn("broken on purpose", registry.problems[0].message)

    def test_a_declared_capability_an_adapter_implements(self):
        """`declared` means no adapter implements it; thinking has fake."""
        self.copy.edit_declaration('module = "twine.runtime.capabilities.thinking"\nstatus = "implemented"',
                                   'module = "twine.runtime.capabilities.thinking"\nstatus = "declared"')
        self.assertEqual(self.kinds(self.copy.load()), {"status-mismatch": ["thinking"]})

    def test_an_implemented_capability_no_adapter_implements(self):
        self.copy.edit_declaration('module = "twine.runtime.capabilities.window_accounting"\nstatus = "declared"',
                                   'module = "twine.runtime.capabilities.window_accounting"\nstatus = "implemented"')
        self.assertEqual(self.kinds(self.copy.load()),
                         {"status-mismatch": ["window-accounting"]})

    def test_a_declared_capability_only_anthropic_implements(self):
        """R2: streaming is the Anthropic adapter's alone; declared, it is
        a mismatch naming it."""
        self.copy.edit_declaration('module = "twine.runtime.capabilities.streaming"\nstatus = "implemented"',
                                   'module = "twine.runtime.capabilities.streaming"\nstatus = "declared"')
        self.assertEqual(self.kinds(self.copy.load()), {"status-mismatch": ["streaming"]})

    def test_experimental_is_listed_with_or_without_an_adapter(self):
        self.copy.edit_declaration('module = "twine.runtime.capabilities.streaming"\nstatus = "implemented"',
                                   'module = "twine.runtime.capabilities.streaming"\nstatus = "experimental"')
        self.copy.edit_declaration('module = "twine.runtime.capabilities.thinking"\nstatus = "implemented"',
                                   'module = "twine.runtime.capabilities.thinking"\nstatus = "experimental"')
        registry = self.copy.load()
        self.assertTrue(registry.ok, [p.message for p in registry.problems])
        self.assertEqual(registry.get("streaming").declared.status, "experimental")

    def test_an_adapter_implementing_an_undeclared_capability(self):
        """Removing a declared capability the fake implements leaves the
        fake naming one nobody declares — and the module a stray. Since R2
        the Anthropic adapter implements it too, and is named beside."""
        text = self.copy.declaration.read_text(encoding="utf-8")
        head, rest = text.split('[[capability]]\nname = "thinking"', 1)
        rest = rest.split("[[capability]]", 1)[1]
        self.copy.declaration.write_text(head + "[[capability]]" + rest, encoding="utf-8")
        kinds = self.kinds(self.copy.load())
        self.assertEqual(kinds, {"stray-module": ["thinking"],
                                 "unknown-capability": ["anthropic", "fake"]})


# ---------------------------------------------------------------------------
# 3. from_anthropic
# ---------------------------------------------------------------------------


class FromAnthropic(unittest.TestCase):

    def test_the_recording_is_the_one_the_brief_carries(self):
        data = RECORDING.read_bytes()
        self.assertEqual((len(data), hashlib.sha256(data).hexdigest()),
                         (RECORDING_BYTES, RECORDING_SHA))
        self.assertTrue(data.endswith(b"\n"))
        self.assertEqual(data.count(b"\n"), 1)

    def test_the_recording_maps(self):
        self.assertEqual(from_anthropic(recorded_usage()),
                         Tokens(input=18, output=4, thinking=0, cache_read=0, cache_write=0))

    def test_absent_output_tokens_details_is_thinking_none(self):
        u = recorded_usage()
        del u["output_tokens_details"]
        t = from_anthropic(u)
        self.assertIsNone(t.thinking)
        self.assertEqual(t.output, 4)

    def test_details_without_a_thinking_count_is_thinking_none(self):
        u = recorded_usage()
        u["output_tokens_details"] = {}
        self.assertIsNone(from_anthropic(u).thinking)

    def test_reported_thinking_is_taken_out_of_output_once(self):
        """The provider counts thinking inside output_tokens; the spine's
        classes are disjoint and record_cost bills thinking on top of
        output, so output is output_tokens less thinking — and the cost is
        output_tokens at the output price, never more."""
        u = recorded_usage()
        u["output_tokens"] = 40
        u["output_tokens_details"] = {"thinking_tokens": 25}
        t = from_anthropic(u)
        self.assertEqual((t.output, t.thinking), (15, 25))
        price = ModelPrice("m", input=Decimal(3), output=Decimal(15),
                           cache_read=Decimal("0.3"), cache_write=Decimal("3.75"))
        cost = record_cost(UsageRecord("s", None, "m", t), price)
        self.assertEqual(cost, (18 * Decimal(3) + 40 * Decimal(15)) / Decimal(1_000_000))

    def test_thinking_above_output_is_refused(self):
        u = recorded_usage()
        u["output_tokens_details"] = {"thinking_tokens": 5}
        with self.assertRaisesRegex(UsageMappingError, "exceeds output_tokens"):
            from_anthropic(u)

    def test_absent_cache_keys_are_zero(self):
        u = recorded_usage()
        u["cache_read_input_tokens"] = 7
        u["cache_creation_input_tokens"] = 9
        self.assertEqual((from_anthropic(u).cache_read, from_anthropic(u).cache_write), (7, 9))
        del u["cache_read_input_tokens"], u["cache_creation_input_tokens"]
        t = from_anthropic(u)
        self.assertEqual((t.cache_read, t.cache_write), (0, 0))

    def test_a_missing_required_count_raises(self):
        for key in ("input_tokens", "output_tokens"):
            with self.subTest(missing=key):
                u = recorded_usage()
                del u[key]
                with self.assertRaisesRegex(UsageMappingError, f"{key} is missing"):
                    from_anthropic(u)

    def test_a_negative_or_non_integer_count_raises(self):
        paths = [("input_tokens",), ("output_tokens",), ("cache_read_input_tokens",),
                 ("cache_creation_input_tokens",), ("output_tokens_details", "thinking_tokens")]
        nullable = {("cache_read_input_tokens",), ("cache_creation_input_tokens",)}
        for path in paths:
            # Null cache counts read as absent since R2 (the next test).
            for bad in (-1, 1.0, "4", True, [4]) + (() if path in nullable else (None,)):
                with self.subTest(path=path, value=bad):
                    u = recorded_usage()
                    target = u
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = bad
                    with self.assertRaises(UsageMappingError) as caught:
                        from_anthropic(u)
                    self.assertIn(path[-1], str(caught.exception))

    def test_null_cache_counts_read_as_absent(self):
        """Arc 2 R2, brief §5 item 4: the SDK (anthropic 1.13.0,
        types/usage.py and types/message_delta_usage.py) types both cache
        counts Optional[int] = None, so null is a value the provider may send
        and reads as absent — 0. The other counts stay refused when null."""
        u = recorded_usage()
        u["cache_read_input_tokens"] = None
        u["cache_creation_input_tokens"] = None
        t = from_anthropic(u)
        self.assertEqual((t.cache_read, t.cache_write), (0, 0))
        self.assertEqual((t.input, t.output), (18, 4))
        for key in ("input_tokens", "output_tokens"):
            with self.subTest(null=key):
                u = recorded_usage()
                u[key] = None
                with self.assertRaises(UsageMappingError):
                    from_anthropic(u)

    def test_a_raise_is_a_value_error(self):
        self.assertTrue(issubclass(UsageMappingError, ValueError))

    def test_not_an_object_raises(self):
        for bad in (None, [], "usage", 18):
            with self.subTest(value=bad):
                with self.assertRaises(UsageMappingError):
                    from_anthropic(bad)  # type: ignore[arg-type]

    def test_details_not_an_object_raises(self):
        u = recorded_usage()
        u["output_tokens_details"] = 0
        with self.assertRaisesRegex(UsageMappingError, "output_tokens_details must be"):
            from_anthropic(u)

    def test_extra_keys_are_ignored(self):
        u = recorded_usage()
        u["service_tier"] = "priority"
        u["inference_geo"] = "elsewhere"
        u["cache_creation"] = {"ephemeral_5m_input_tokens": 99}
        u["something_new"] = {"nested": True}
        self.assertEqual(from_anthropic(u), from_anthropic(recorded_usage()))

    def test_pure(self):
        u = recorded_usage()
        before = copy.deepcopy(u)
        from_anthropic(u)
        self.assertEqual(u, before)

    def test_exported_by_the_module_the_declaration_names(self):
        """The declaration's module exports it; since R2 the code lives in
        twine.runtime.usage — not a capability module, so the Anthropic
        adapter can import it — and the export is the same object."""
        module = {e["name"]: e["module"] for e in toml_entries()}["usage-accounting"]
        self.assertEqual(module, "twine.runtime.capabilities.usage_accounting")
        self.assertIs(importlib.import_module(module).from_anthropic, from_anthropic)
        self.assertIs(importlib.import_module(module).UsageMappingError, UsageMappingError)
        self.assertEqual(from_anthropic.__module__, "twine.runtime.usage")
        self.assertIs(importlib.import_module("twine.runtime.usage").from_anthropic,
                      from_anthropic)


# ---------------------------------------------------------------------------
# 4. The boundary and the fake adapter
# ---------------------------------------------------------------------------

TOOL_TURN = {"text": "Let me look.", "tool_calls": [
    {"id": "call-1", "name": "read_file", "arguments": {"path": "README.md"}}],
    "stop": None, "usage": usage(input=120, output=30, cache_write=100)}
FINAL_TURN = {"text": "Done.", "stop": "end-turn",
              "usage": usage(input=180, output=12, cache_read=100)}
READ_FILE = ToolSpec("read_file", "read a file in the sandbox home",
                     {"type": "object", "properties": {"path": {"type": "string"}}})


def boundary(script, settings: SpawnSettings = SETTINGS, **kwargs) -> Boundary:
    return Boundary(FakeAdapter(settings, script), **kwargs)


def request(*messages: str) -> Request:
    return Request(tuple({"role": "user", "content": m} for m in messages) or
                   ({"role": "user", "content": "go"},), (READ_FILE,))


class TheStopSet(unittest.TestCase):

    def test_the_boundary_s_stop_set_is_the_table_s_stop_axis(self):
        """Three readings agree: the boundary's, twine.transitions' (through
        load_table, as `twine transitions` reads it) and the file's own."""
        with TRANSITIONS_TABLE.open("rb") as fh:
            raw = tomllib.load(fh)["axis"]["stop"]["keys"]
        table = transitions.load_table(TRANSITIONS_TABLE, None, "not needed")
        self.assertEqual(boundary([FINAL_TURN]).stop_set, tuple(raw))
        self.assertEqual(transitions.stop_keys(), table.axis("stop").keys)
        self.assertIn("end-turn", raw)

    def test_no_runtime_module_spells_a_stop_key(self):
        """The one spelling is the table's: no string constant in any module
        under twine/runtime/ is a stop key (a docstring naming one in prose
        is not a constant equal to it)."""
        keys = set(transitions.stop_keys())
        # Arc 2 R3: a canonical tool's argument names are the tool surface's
        # spelling, pinned by its brief — `shell` takes `timeout`, which the
        # stop axis also spells. In a tool's own module, and only there, a
        # constant naming one of that tool's declared arguments is exempt;
        # any other stop key spelled there still fails.
        from twine.runtime.tooling import load_tool_registry
        arguments = {f"twine/runtime/tools/{t.declared.stem}.py":
                     set(t.tool.spec.input_schema.get("properties", {}))
                     for t in load_tool_registry().tools if t.tool is not None}
        self.assertEqual(arguments["twine/runtime/tools/shell.py"] & keys, {"timeout"})
        for path in sorted(RUNTIME_DIR.rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            with self.subTest(file=rel):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                spelled = {n.value for n in ast.walk(tree)
                           if isinstance(n, ast.Constant) and n.value in keys}
                self.assertEqual(spelled - arguments.get(rel, set()), set())

    def test_stop_keys_refuses_a_table_without_a_usable_stop_axis(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = TRANSITIONS_TABLE.read_text(encoding="utf-8")
            cases = {
                "no-axis": text.replace("[axis.stop]", "[axis.halt]"),
                "bale-source": re.sub(r'(\[axis\.stop\]\norder = 4\nsource = )"twine"',
                                      r'\1"bale"', text),
                "catch-all": text.replace('"cap-unchecked"]', '"cap-unchecked", "other"]'),
                "not-toml": "[axis.stop\n",
            }
            for name, body in cases.items():
                with self.subTest(case=name):
                    self.assertNotEqual(body, text)
                    path = Path(tmp) / f"{name}.toml"
                    path.write_text(body, encoding="utf-8")
                    with self.assertRaises(transitions.TableError):
                        transitions.stop_keys(path)
                    with self.assertRaises(BoundaryError):
                        boundary([FINAL_TURN], table=path)


class FakeThroughTheBoundary(unittest.TestCase):

    def test_a_scripted_exchange_with_a_tool_call_and_an_end_turn(self):
        b = boundary([TOOL_TURN, FINAL_TURN])
        first = b.call(request("read the README"))
        self.assertTrue(first.continues)
        self.assertIsNone(first.stop)
        self.assertEqual(first.tool_calls, (ToolCall("call-1", "read_file",
                                                     {"path": "README.md"}),))
        self.assertEqual(dict(first.tool_calls[0].arguments), {"path": "README.md"})
        self.assertEqual(first.usage, Tokens(120, 30, None, 0, 100))
        second = b.call(request("read the README", "(tool result)"))
        self.assertFalse(second.continues)
        self.assertEqual(second.stop, "end-turn")
        self.assertIn(second.stop, transitions.stop_keys())
        self.assertEqual(second.text, "Done.")
        self.assertIsInstance(second.usage, Tokens)
        self.assertEqual(second.usage, Tokens(180, 12, None, 100, 0))
        self.assertEqual(b.calls, 2)
        self.assertEqual(len(b.adapter.requests), 2)
        self.assertEqual(b.adapter.requests[0].tools, (READ_FILE,))
        self.assertEqual(b.adapter.remaining, 0)

    def test_every_stop_on_the_axis_passes_but_the_loops(self):
        """Every key of the axis passes from an adapter — except the axis's
        loop_keys (Arc 2 R2): the loop produces those, and the boundary
        refuses an adapter whose mapping produces one, naming it."""
        loop = transitions.loop_keys()
        self.assertEqual(set(loop), {"cap-reached", "cap-unchecked", "killed"})
        for key in transitions.stop_keys():
            with self.subTest(stop=key):
                if key in loop:
                    with self.assertRaises(BoundaryError) as caught:
                        boundary([dict(FINAL_TURN, stop=key)]).call(request())
                    self.assertIn(repr(key), str(caught.exception))
                    self.assertIn("loop key", str(caught.exception))
                else:
                    turn = boundary([dict(FINAL_TURN, stop=key)]).call(request())
                    self.assertEqual(turn.stop, key)

    def test_the_boundary_reads_the_loop_keys_from_the_table(self):
        b = boundary([FINAL_TURN])
        self.assertEqual(b.loop_set, transitions.loop_keys())
        with tempfile.TemporaryDirectory() as tmp:
            text = TRANSITIONS_TABLE.read_text(encoding="utf-8")
            body = re.sub(r"\nloop_keys = \[[^\]]*\]\n", "\n", text)
            self.assertNotEqual(body, text)
            path = Path(tmp) / "no-loop-keys.toml"
            path.write_text(body, encoding="utf-8")
            with self.assertRaises(transitions.TableError):
                transitions.loop_keys(path)
            with self.assertRaises(BoundaryError) as caught:
                boundary([FINAL_TURN], table=path)
            self.assertIn("loop_keys", str(caught.exception))

    def test_the_new_turn_fields_default_and_are_checked(self):
        """R2 added content, retry_after, request_id and reason to Turn,
        each defaulting so the fake is unchanged; the boundary checks their
        types."""
        turn = boundary([FINAL_TURN]).call(request())
        self.assertEqual((turn.content, turn.retry_after, turn.request_id, turn.reason),
                         ((), None, None, None))
        self.assertEqual(set(turn.as_json()),
                         {"text", "thinking", "tool_calls", "stop", "usage", "provider_stop",
                          "content", "retry_after", "request_id", "reason"})
        b = boundary([FINAL_TURN])
        good = Turn("ok", None, (), "end-turn", Tokens(1, 1, None, 0, 0))
        self.assertEqual(b.turn_faults(good), [])
        for bad, needle in ((dataclasses.replace(good, content=[{"type": "text"}]), "content"),
                            (dataclasses.replace(good, content=("x",)), "content"),
                            (dataclasses.replace(good, retry_after=-1), "retry_after"),
                            (dataclasses.replace(good, retry_after=True), "retry_after"),
                            (dataclasses.replace(good, request_id=7), "request_id"),
                            (dataclasses.replace(good, reason=b"x"), "reason")):
            with self.subTest(needle=needle, value=bad):
                faults = b.turn_faults(bad)
                self.assertTrue(any(needle in f for f in faults), faults)

    def test_a_stop_not_on_the_axis_is_refused(self):
        """A provider's word scripted where twine's belongs: the fake maps
        nothing and the boundary translates nothing, so it is refused."""
        for word in ("end_turn", "tool_use", "max_tokens", "stop_sequence", "refusal",
                     "End-Turn", ""):
            with self.subTest(stop=word):
                with self.assertRaises(BoundaryError) as caught:
                    boundary([dict(FINAL_TURN, stop=word)]).call(request())
                self.assertIn(f"stop {word!r} is not a key of the stop axis",
                              str(caught.exception))
                self.assertEqual(caught.exception.adapter, "fake")
                self.assertEqual(caught.exception.call, 1)

    def test_a_turn_does_tools_or_stops_not_both_not_neither(self):
        both = dict(TOOL_TURN, stop="end-turn")
        neither = dict(FINAL_TURN, stop=None)
        with self.assertRaisesRegex(BoundaryError, "a turn does one or the other"):
            boundary([both]).call(request())
        with self.assertRaisesRegex(BoundaryError, "neither asks for a tool nor stops"):
            boundary([neither]).call(request())

    def test_usage_that_is_not_tokens_the_spine_accepts_is_refused(self):
        for counts, fault in (({"input": -1}, "tokens.input is negative"),
                              ({"output": 1.5}, "tokens.output must be"),
                              ({"cache_read": "0"}, "tokens.cache_read must be"),
                              ({"thinking": -3}, "tokens.thinking is negative"),
                              ({"input": True}, "tokens.input must be")):
            with self.subTest(counts=counts):
                with self.assertRaisesRegex(BoundaryError, re.escape(fault)):
                    boundary([dict(FINAL_TURN, usage=usage(**counts))]).call(request())

    def test_thinking_text_needs_thinking_on_at_spawn(self):
        turn = dict(FINAL_TURN, thinking="considering…", usage=usage(thinking=40))
        with self.assertRaisesRegex(BoundaryError, "spawned with thinking off"):
            boundary([turn]).call(request())
        self.assertEqual(boundary([turn], THINKING_ON).call(request()).thinking,
                         "considering…")

    def test_tool_calls_need_ids_unique_within_the_turn(self):
        calls = [{"id": "c", "name": "read_file", "arguments": {}},
                 {"id": "c", "name": "list_dir", "arguments": {}}]
        with self.assertRaisesRegex(BoundaryError, "'c' is used twice"):
            boundary([dict(TOOL_TURN, tool_calls=calls)]).call(request())
        with self.assertRaisesRegex(BoundaryError, "has no id"):
            boundary([dict(TOOL_TURN, tool_calls=[dict(calls[0], id="")])]).call(request())

    def test_an_unknown_tool_name_is_not_the_boundary_s_to_refuse(self):
        """§4.3: a call to a tool that does not exist is a tool error the
        loop returns as a result, never a crash."""
        calls = [{"id": "c", "name": "teleport", "arguments": {}}]
        turn = boundary([dict(TOOL_TURN, tool_calls=calls)]).call(request())
        self.assertEqual(turn.tool_calls[0].name, "teleport")

    def test_a_call_past_the_script_raises(self):
        b = boundary([FINAL_TURN])
        b.call(request())
        with self.assertRaises(FakeScriptExhausted):
            b.call(request())

    def test_a_request_must_be_a_request(self):
        with self.assertRaises(BoundaryError):
            boundary([FINAL_TURN]).call({"messages": []})  # type: ignore[arg-type]

    def test_the_arguments_are_read_only(self):
        turn = boundary([TOOL_TURN]).call(request())
        with self.assertRaises(TypeError):
            turn.tool_calls[0].arguments["path"] = "/etc/passwd"  # type: ignore[index]


class SpawnTimeConstants(unittest.TestCase):
    """D12: model and thinking are set at spawn and never mid-session."""

    def test_settings_are_frozen(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            SETTINGS.model = "other"  # type: ignore[misc]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            THINKING_ON.thinking.budget_tokens = 1  # type: ignore[misc]
        adapter = FakeAdapter(SETTINGS, [FINAL_TURN])
        with self.assertRaises(AttributeError):
            adapter.settings = THINKING_ON  # type: ignore[misc]

    def test_no_call_takes_a_model_or_thinking(self):
        for fn in (Adapter.call, FakeAdapter.call, Boundary.call):
            with self.subTest(fn=fn.__qualname__):
                self.assertEqual(list(inspect.signature(fn).parameters), ["self", "request"])
        for cls in (Adapter, Boundary, FakeAdapter):
            names = {n for n, _ in inspect.getmembers(cls, callable) if not n.startswith("_")}
            with self.subTest(cls=cls.__name__):
                self.assertFalse({n for n in names if n.startswith("set")}, names)

    def test_the_thinking_settings_refuse_incoherence(self):
        for kwargs in ({"enabled": True}, {"enabled": True, "budget_tokens": 0},
                       {"enabled": False, "budget_tokens": 100}, {"enabled": 1},
                       {"enabled": False, "adaptive": True},
                       {"enabled": True, "budget_tokens": 100, "adaptive": True},
                       {"enabled": True, "adaptive": 1}):
            with self.subTest(**kwargs):
                with self.assertRaises(ThinkingSettingsError):
                    ThinkingSettings(**kwargs)

    def test_adaptive_thinking_is_on_without_a_budget(self):
        """R2: Anthropic's `{"type": "adaptive"}` — thinking on, no budget."""
        adaptive = ThinkingSettings(enabled=True, adaptive=True)
        self.assertEqual(adaptive.as_json(),
                         {"enabled": True, "budget_tokens": None, "adaptive": True})
        settings = SpawnSettings(model="m", max_tokens=10, thinking=adaptive)
        self.assertTrue(settings.thinking.enabled)
        self.assertEqual(THINKING_OFF.as_json(),
                         {"enabled": False, "budget_tokens": None, "adaptive": False})

    def test_the_spawn_settings_refuse_incoherence(self):
        for kwargs in ({"model": "", "max_tokens": 10, "thinking": THINKING_OFF},
                       {"model": "m", "max_tokens": 0, "thinking": THINKING_OFF},
                       {"model": "m", "max_tokens": 100,
                        "thinking": ThinkingSettings(True, 100)}):
            with self.subTest(**{k: str(v) for k, v in kwargs.items()}):
                with self.assertRaises(ValueError):
                    SpawnSettings(**kwargs)


class TheBoundaryRefusesAnAdapterItCannotHost(unittest.TestCase):

    def test_an_adapter_short_of_the_three(self):
        class Partial(FakeAdapter):
            name = "partial"
            implements = frozenset({"tool-calling", "usage-accounting"})

        with self.assertRaisesRegex(BoundaryError, "does not implement thinking"):
            Boundary(Partial(SETTINGS, [FINAL_TURN]))

    def test_an_adapter_on_the_text_protocol_has_no_parser_yet(self):
        class Texty(FakeAdapter):
            name = "texty"
            tool_protocol = TEXT

        with self.assertRaisesRegex(BoundaryError, "TQ-3"):
            Boundary(Texty(SETTINGS, [FINAL_TURN]))

    def test_an_adapter_returning_something_else(self):
        class Wrong(FakeAdapter):
            name = "wrong"

            def call(self, request):
                return {"text": "hi", "stop": "end-turn"}

        with self.assertRaisesRegex(BoundaryError, "not a Turn"):
            Boundary(Wrong(SETTINGS, [FINAL_TURN])).call(request())

    def test_not_an_adapter(self):
        with self.assertRaises(BoundaryError):
            Boundary(object())  # type: ignore[arg-type]

    def test_an_adapter_needs_spawn_settings(self):
        with self.assertRaises(TypeError):
            FakeAdapter({"model": "m"}, [FINAL_TURN])  # type: ignore[arg-type]


class FakeScripts(unittest.TestCase):

    def test_a_script_refuses_what_it_cannot_play(self):
        cases = {
            "not a list": "end-turn",
            "empty": [],
            "unknown key": [dict(FINAL_TURN, colour="blue")],
            "no usage": [{"text": "x", "stop": "end-turn"}],
            "no stop": [{"text": "x", "usage": usage()}],
            "usage short a class": [dict(FINAL_TURN, usage={"input": 1, "output": 1})],
            "usage in the provider's shape": [dict(FINAL_TURN, usage=recorded_usage())],
            "text not a string": [dict(FINAL_TURN, text=3)],
            "a tool call short a key": [dict(TOOL_TURN, tool_calls=[{"id": "a",
                                                                    "name": "x"}])],
            "a turn not an object": ["end-turn"],
        }
        for name, script in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(FakeScriptError):
                    FakeScript.from_data(script)

    def test_the_fault_names_the_turn(self):
        with self.assertRaisesRegex(FakeScriptError, "turn 2 has unknown key"):
            FakeScript.from_data([FINAL_TURN, dict(FINAL_TURN, colour="blue")])

    def test_the_fake_is_registered_and_implements_the_three(self):
        """And, since R2, `anthropic` beside it, implementing five."""
        self.assertEqual(FakeAdapter.name, "fake")
        self.assertEqual(FakeAdapter.implements, frozenset(THE_THREE))
        registry = load_runtime_registry()
        self.assertEqual([a.name for a in registry.adapters], ["anthropic", "fake"])
        for name in THE_EIGHT:
            with self.subTest(capability=name):
                want = (["anthropic"] if name in ANTHROPIC_FIVE else []) + (
                    ["fake"] if name in THE_THREE else [])
                self.assertEqual(registry.get(name).adapters, want)

    def test_nothing_in_twine_drives_the_fake(self):
        """T8: the tests drive it — and since Arc 2 R4 `twine run --adapter
        fake --script FILE`, which reaches it by name through the adapter
        registry (twine.runtime.loop.adapter_class) — so no module under
        twine/ but its own names its class."""
        for path in sorted((REPO_ROOT / "twine").rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel == "twine/runtime/adapters/fake.py":
                continue
            with self.subTest(file=rel):
                self.assertNotIn("FakeAdapter", path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 5. The verbs
# ---------------------------------------------------------------------------


class RuntimeList(unittest.TestCase):

    def test_json_twin(self):
        run = run_cli("runtime", "list", "--json")
        obj = one_line(self, run.stdout, "runtime list")
        self.assertEqual((run.code, obj["ok"]), (0, True))
        self.assertEqual([c["name"] for c in obj["capabilities"]], THE_EIGHT)
        for row in obj["capabilities"]:
            with self.subTest(capability=row["name"]):
                self.assertEqual(set(row), {"name", "status", "summary", "module", "adapters",
                                            "implemented_by"})
                self.assertTrue(row["module"].startswith("twine.runtime.capabilities."))
                self.assertTrue(row["summary"])
                self.assertEqual(row["status"],
                                 "implemented" if row["name"] in IMPLEMENTED else "declared")
                self.assertEqual(row["implemented_by"], RUNTIME_OWN.get(row["name"]))
        self.assertEqual(obj["adapters"], [{
            "name": "anthropic",
            "implements": ["tool-calling", "thinking", "prompt-caching", "streaming",
                           "usage-accounting"],
            "tool_protocol": "native", "module": "twine.runtime.adapters.anthropic"}, {
            "name": "fake", "implements": ["tool-calling", "thinking", "usage-accounting"],
            "tool_protocol": "native", "module": "twine.runtime.adapters.fake"}])
        self.assertEqual(obj["counts"], {"capabilities": 8, "declared": 2, "implemented": 6,
                                         "experimental": 0, "adapters": 2})
        self.assertEqual(obj["statuses"], list(STATUSES))
        self.assertEqual((obj["problems"], obj["reason"]), ([], None))
        self.assertNotIn("Traceback", run.stderr)

    def test_human_lines_carry_the_same_facts(self):
        run = run_inprocess("runtime", "list")
        self.assertEqual(run.code, 0)
        self.assertTrue(run.stdout.startswith("runtime registry "))
        self.assertIn(": ok\n", run.stdout)
        obj = json.loads(run_inprocess("runtime", "list", "--json").stdout)
        for row in obj["capabilities"]:
            line = next(l for l in run.stdout.splitlines()
                        if l.split() and l.split()[0] == row["name"])
            for fact in (row["status"], row["module"]):
                self.assertIn(fact, line)
            self.assertIn(row["summary"], run.stdout)
        self.assertIn("fake  implements tool-calling, thinking, usage-accounting",
                      run.stdout)

    def test_the_verbs_never_touch_the_run_seam(self):
        def refuse(*args, **kwargs):
            raise AssertionError("a runtime verb reached ctx.run")
        for argv in (["runtime", "list"], ["runtime", "show", "thinking"],
                     ["runtime", "show", "nope"]):
            with self.subTest(argv=argv):
                out = io.StringIO()
                ctx = Context(env={}, stdout=out, stderr=io.StringIO(),
                              which=lambda n: None, stdin=io.BytesIO(b""), run=refuse)
                code = main([*argv, "--json"], ctx=ctx)
                self.assertIn(code, (0, 1))
                self.assertNotIn("error", json.loads(out.getvalue()))


class RuntimeShow(unittest.TestCase):

    def test_json_twin(self):
        run = run_cli("runtime", "show", "usage-accounting", "--json")
        obj = one_line(self, run.stdout, "runtime show")
        self.assertEqual((run.code, obj["ok"]), (0, True))
        listed = next(r for r in json.loads(run_cli("runtime", "list", "--json").stdout)
                      ["capabilities"] if r["name"] == "usage-accounting")
        for key, value in listed.items():
            self.assertEqual(obj[key], value)
        self.assertTrue(obj["contract"])
        self.assertEqual(set(obj["contract"]),
                         {"purpose", "adapter_must", "runtime_promises", "lands", "grounds"})
        self.assertTrue(obj["contract"]["purpose"])
        self.assertIsNone(obj["reason"])

    def test_every_capability_shows_with_a_contract(self):
        for name in THE_EIGHT:
            with self.subTest(capability=name):
                run = run_inprocess("runtime", "show", name, "--json")
                obj = one_line(self, run.stdout, "runtime show")
                self.assertEqual((run.code, obj["ok"], obj["name"]), (0, True, name))
                self.assertTrue(obj["contract"]["adapter_must"])

    def test_human_lines(self):
        run = run_inprocess("runtime", "show", "thinking")
        self.assertEqual(run.code, 0)
        self.assertIn("capability thinking: ok", run.stdout)
        self.assertIn("status: implemented", run.stdout)
        self.assertIn("an adapter that implements it must:", run.stdout)

    def test_an_unknown_name_is_not_ok_naming_it_and_the_known(self):
        run = run_cli("runtime", "show", "teleport", "--json")
        obj = one_line(self, run.stdout, "runtime show")
        self.assertEqual((run.code, obj["ok"]), (1, False))
        self.assertIn("'teleport'", obj["reason"])
        for name in THE_EIGHT:
            self.assertIn(name, obj["reason"])
        self.assertEqual(obj["known"], THE_EIGHT)
        self.assertNotIn("Traceback", run.stderr)
        human = run_cli("runtime", "show", "teleport")
        self.assertEqual(human.code, 1)
        self.assertIn("NOT OK", human.stdout)


class TheVerbsOnABrokenTree(unittest.TestCase):
    """End to end, as a reviewer would: a copy of the tree with a module
    planted, one removed, and the declaration broken — each NOT OK, exit 1,
    the fault named, no traceback."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="twine-runtime-tree-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for name in ("twine", "bin", "share"):
            shutil.copytree(REPO_ROOT / name, self.root / name,
                            ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(REPO_ROOT / "VERSION", self.root / "VERSION")
        self.capabilities = self.root / "twine" / "runtime" / "capabilities"

    def run_copy(self, *argv: str):
        import subprocess
        import sys
        proc = subprocess.run([sys.executable, "-I", "-S", "-B",
                               str(self.root / "bin" / "twine"), *argv],
                              cwd=str(self.root), capture_output=True,
                              env={"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"})
        return proc.returncode, proc.stdout.decode(), proc.stderr.decode()

    def test_the_copy_is_ok(self):
        code, out, _ = self.run_copy("runtime", "list", "--json")
        self.assertEqual((code, json.loads(out)["ok"]), (0, True))

    def test_a_planted_module(self):
        (self.capabilities / "teleport.py").write_text("", encoding="utf-8")
        code, out, err = self.run_copy("runtime", "list", "--json")
        obj = one_line(self, out, "runtime list")
        self.assertEqual((code, obj["ok"]), (1, False))
        self.assertEqual([(p["kind"], p["name"]) for p in obj["problems"]],
                         [("stray-module", "teleport")])
        self.assertIn("teleport", obj["reason"])
        self.assertNotIn("Traceback", err)
        code, out, _ = self.run_copy("runtime", "list")
        self.assertEqual(code, 1)
        self.assertIn("NOT OK", out)
        self.assertIn("stray-module", out)

    def test_a_listed_module_removed(self):
        (self.capabilities / "window_accounting.py").unlink()
        code, out, err = self.run_copy("runtime", "list", "--json")
        obj = one_line(self, out, "runtime list")
        self.assertEqual((code, obj["ok"]), (1, False))
        self.assertEqual([(p["kind"], p["name"]) for p in obj["problems"]],
                         [("missing-module", "window-accounting")])
        self.assertIn("'window-accounting'", obj["reason"])
        code, out, _ = self.run_copy("runtime", "show", "window-accounting", "--json")
        obj = one_line(self, out, "runtime show")
        self.assertEqual((code, obj["ok"]), (1, False))
        self.assertIsNone(obj["contract"])
        self.assertIn("window-accounting", obj["reason"])
        self.assertNotIn("Traceback", err)

    def test_show_of_a_sound_capability_on_a_broken_registry(self):
        (self.capabilities / "teleport.py").write_text("", encoding="utf-8")
        code, out, _ = self.run_copy("runtime", "show", "thinking", "--json")
        obj = one_line(self, out, "runtime show")
        self.assertEqual((code, obj["ok"], obj["registry_ok"]), (0, True, False))

    def test_a_malformed_declaration(self):
        path = self.root / "twine" / "runtime" / "capabilities.toml"
        path.write_text(path.read_text(encoding="utf-8").replace(
            'status = "declared"', 'status = "maybe"', 1), encoding="utf-8")
        for argv in (("runtime", "list"), ("runtime", "show", "thinking")):
            with self.subTest(argv=argv):
                code, out, err = self.run_copy(*argv, "--json")
                obj = one_line(self, out, " ".join(argv[:2]))
                self.assertEqual((code, obj["ok"]), (1, False))
                self.assertIn("malformed", obj["reason"])
                self.assertIn("'maybe'", obj["reason"])
                self.assertNotIn("Traceback", err)


class RemovingAnyListedModule(unittest.TestCase):
    """The HOLD of 2026-10-12 (probe 2): with any one listed capability
    module removed, `twine runtime list` is NOT OK, exit 1, naming that
    capability — and every twine verb still loads. Each module in turn, on
    its own copy of the tree, in fresh interpreters."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="twine-runtime-each-")
        cls.root = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def copy_without(self, module: str) -> Path:
        dest = self.root / module.rsplit(".", 1)[1]
        for name in ("twine", "bin", "share"):
            shutil.copytree(REPO_ROOT / name, dest / name,
                            ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(REPO_ROOT / "VERSION", dest / "VERSION")
        path = dest / (module.replace(".", "/") + ".py")
        self.assertTrue(path.is_file(), path)
        path.unlink()
        return dest

    def run_in(self, tree: Path, *argv: str):
        import subprocess
        import sys
        return subprocess.run([sys.executable, "-I", "-S", "-B", *argv], cwd=str(tree),
                              capture_output=True, text=True,
                              env={"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8"})

    def test_each_listed_module_removed_in_turn(self):
        verbs_script = (
            "import sys, io\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from twine.cli import Context, main\n"
            "from twine.registry import load_registry\n"
            "bad = []\n"
            "names = list(load_registry())\n"
            "for name in names:\n"
            "    out, err = io.StringIO(), io.StringIO()\n"
            "    code = main([*name.split(' '), '--help'],\n"
            "                ctx=Context(env={}, stdout=out, stderr=err, which=lambda n: None,\n"
            "                            stdin=io.BytesIO(b'')))\n"
            "    if code != 0 or 'Traceback' in err.getvalue():\n"
            "        bad.append(name)\n"
            "print(len(names), 'verbs', 'bad:', bad)\n"
            "sys.exit(1 if bad or len(names) < 14 else 0)\n")
        for entry in toml_entries():
            name, module = entry["name"], entry["module"]
            with self.subTest(removed=module):
                tree = self.copy_without(module)
                twine = str(tree / "bin" / "twine")
                run = self.run_in(tree, twine, "runtime", "list", "--json")
                obj = one_line(self, run.stdout, "runtime list")
                self.assertEqual((run.returncode, obj["ok"]), (1, False), run.stderr)
                self.assertEqual([(p["kind"], p["name"]) for p in obj["problems"]],
                                 [("missing-module", name)])
                self.assertIn(repr(name), obj["reason"])
                self.assertNotIn("Traceback", run.stderr)
                show = self.run_in(tree, twine, "runtime", "show", name, "--json")
                shown = one_line(self, show.stdout, "runtime show")
                self.assertEqual((show.returncode, shown["ok"]), (1, False))
                self.assertIn(name, shown["reason"])
                commands = self.run_in(tree, twine, "commands", "--json")
                listed = one_line(self, commands.stdout, "commands")
                self.assertEqual((commands.returncode, listed["ok"]), (0, True),
                                 commands.stderr)
                self.assertIn("runtime list", [c["name"] for c in listed["commands"]])
                verbs = self.run_in(tree, "-c", verbs_script, str(tree))
                self.assertEqual(verbs.returncode, 0, verbs.stdout + verbs.stderr)
                self.assertNotIn("Traceback", commands.stderr + verbs.stderr)


class NothingImportsACapabilityModule(unittest.TestCase):
    """Why the above holds, structurally: no module under twine/ outside
    twine/runtime/capabilities/ imports a capability module — the registry
    reaches them alone, by its guarded import — so a missing one cannot
    take an import chain (and every verb) down with it."""

    PACKAGE = "twine.runtime.capabilities"

    def imports_a_capability(self, node: ast.AST) -> list[str]:
        found = []
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names
                      if a.name == self.PACKAGE or a.name.startswith(self.PACKAGE + ".")]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.startswith(self.PACKAGE + "."):
                found.append(node.module)
            elif node.module == self.PACKAGE:
                found += [f"{self.PACKAGE}.{a.name}" for a in node.names]
            elif node.module == "twine.runtime":
                found += [f"twine.runtime.{a.name}" for a in node.names
                          if a.name == "capabilities"]
        return found

    def test_no_module_outside_the_directory_imports_one(self):
        inside = REPO_ROOT / "twine" / "runtime" / "capabilities"
        for path in sorted((REPO_ROOT / "twine").rglob("*.py")):
            if inside in path.parents:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            found = [m for node in ast.walk(tree) for m in self.imports_a_capability(node)]
            with self.subTest(file=path.relative_to(REPO_ROOT).as_posix()):
                self.assertEqual(found, [])

    def test_no_capability_module_imports_another(self):
        for path in sorted(CAPABILITIES_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            found = [m for node in ast.walk(tree) for m in self.imports_a_capability(node)]
            with self.subTest(file=path.name):
                self.assertEqual(found, [])


# ---------------------------------------------------------------------------
# 6. No network, no key
# ---------------------------------------------------------------------------


def imported_names(path: Path) -> set[str]:
    """Every module an import statement in `path` names, and each root."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.add(node.module.split(".")[0])
    return names


def runtime_sources() -> list[Path]:
    return sorted(RUNTIME_DIR.rglob("*.py")) + [REPO_ROOT / "twine/commands/runtime.py"]


class NoNetworkNoKey(unittest.TestCase):
    """Since Arc 2 R2 one module under twine/runtime/ reaches a network:
    twine/runtime/transport.py, the real transport, the only place twine
    opens a socket — and it reaches it through http.client and ssl alone.
    Every other module is held to R1's line; no module imports a provider
    SDK, a process-spawning module or `os`, and none reads the process
    environment (the Anthropic adapter reads its key from the mapping it is
    given)."""

    FORBIDDEN = {"anthropic", "openai", "urllib", "urllib.request", "http", "http.client",
                 "socket", "ssl", "requests", "httpx", "aiohttp", "asyncio", "subprocess",
                 "multiprocessing", "os"}
    TRANSPORT = "twine/runtime/transport.py"
    # What the transport may import to open its socket: http.client and ssl,
    # and urllib.parse to split the URL (it parses; it opens nothing).
    TRANSPORT_REACHES = {"http", "http.client", "ssl", "urllib", "urllib.parse"}

    def test_no_runtime_module_imports_anything_that_reaches_out(self):
        for path in runtime_sources():
            rel = path.relative_to(REPO_ROOT).as_posix()
            allowed = self.TRANSPORT_REACHES if rel == self.TRANSPORT else set()
            with self.subTest(file=rel):
                found = imported_names(path) & self.FORBIDDEN
                self.assertEqual(found - allowed, set())

    def test_the_transport_is_the_one_module_that_reaches_out(self):
        reaching = sorted(p.relative_to(REPO_ROOT).as_posix()
                          for p in (REPO_ROOT / "twine").rglob("*.py")
                          if imported_names(p) & {"socket", "ssl", "http", "http.client",
                                                  "urllib.request", "anthropic", "requests",
                                                  "httpx", "aiohttp"})
        self.assertEqual(reaching, [self.TRANSPORT])
        self.assertEqual(imported_names(REPO_ROOT / self.TRANSPORT) & self.FORBIDDEN,
                         self.TRANSPORT_REACHES & self.FORBIDDEN)

    def test_no_runtime_module_reads_the_environment(self):
        """No key is read: nothing under twine/runtime/ touches the
        environment at all (no `environ`, no `getenv`)."""
        for path in runtime_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            touched = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                       and n.attr in ("environ", "getenv", "environb")}
            touched |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
                        and n.id in ("environ", "getenv")}
            with self.subTest(file=path.relative_to(REPO_ROOT).as_posix()):
                self.assertEqual(touched, set())

    def test_no_test_imports_a_provider_sdk_or_a_socket(self):
        for path in sorted((REPO_ROOT / "tests").glob("*.py")):
            with self.subTest(file=path.name):
                self.assertFalse(imported_names(path) & {"anthropic", "openai", "socket",
                                                          "ssl", "http", "urllib"})


# ---------------------------------------------------------------------------
# 7. The recording and its README row
# ---------------------------------------------------------------------------


class ProviderRecordings(unittest.TestCase):

    ROW = re.compile(r"^\| `(?P<file>anthropic/[^`]+)` \| (?P<bytes>\d+) "
                     r"\| `(?P<sha>[0-9a-f]{64})` \|", re.M)

    def setUp(self):
        self.text = (FIXTURES_DIR / "README.md").read_text(encoding="utf-8")

    def test_the_section_exists_after_the_bale_sections(self):
        self.assertIn("\n## Provider recordings\n", self.text)
        provider = self.text.index("\n## Provider recordings\n")
        self.assertGreater(provider, self.text.rindex("\n## bale "))

    def test_every_provider_recording_has_its_row(self):
        rows = {m["file"]: m for m in self.ROW.finditer(self.text)}
        on_disk = sorted(p.relative_to(FIXTURES_DIR).as_posix()
                         for p in (FIXTURES_DIR / "anthropic").rglob("*") if p.is_file())
        self.assertEqual(sorted(rows), on_disk)
        for name in on_disk:
            with self.subTest(fixture=name):
                data = (FIXTURES_DIR / name).read_bytes()
                self.assertEqual(int(rows[name]["bytes"]), len(data))
                self.assertEqual(rows[name]["sha"], hashlib.sha256(data).hexdigest())

    def test_every_provider_recording_is_one_json_object(self):
        """R1's rule for a carried emission (the usage object) and the
        lander's meta files: one JSON object, one line, its newline. The wire
        captures of 2026-10-13 (`*.request.json`, `*.response.json`) are the
        provider's bytes, no newline added — tests/test_anthropic.py holds
        them to the brief's hashes and to being JSON."""
        for path in sorted((FIXTURES_DIR / "anthropic").rglob("*.json")):
            if path.name.endswith((".request.json", ".response.json")):
                continue
            with self.subTest(fixture=path.name):
                data = path.read_bytes()
                self.assertEqual(data.count(b"\n"), 1)
                self.assertTrue(data.endswith(b"\n"))
                self.assertIsInstance(json.loads(data), dict)

    def test_the_provenance_is_stated(self):
        section = self.text.split("\n## Provider recordings\n", 1)[1]
        for fact in ("2026-10-08", "claude-haiku-5-5", "max_tokens", "repr",
                     "carried emission", "not a byte capture"):
            self.assertIn(fact, section)


if __name__ == "__main__":
    unittest.main()

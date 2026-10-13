"""The canonical tools' machinery (twine-seed.md T6, §4.2; Arc 2 R3 —
claude/context/runtime-contract.md §6): what a tool is, what it returns,
how the declaration of the seven is held to their modules, how a call's
arguments are checked, and `run_tool`, the one way a tool runs.

The tools are declared the way capabilities are (§2 of the contract): a
declaration, twine/runtime/tools.toml, lists every tool — `name`, `module`,
`leaves_cage` — in the order every renderer lists them and the model is
offered them; a directory, twine/runtime/tools/, holds one module per tool,
each exposing a module-level `TOOL`; and the two are held to each other by
name. A stray module, a missing one, a module that does not import, a
module whose TOOL is absent, names another tool, is malformed (its input
schema outside the subset below), or disagrees with the declaration about
leaving the cage — each is a problem `twine runtime tools` names (NOT OK,
exit 1). A malformed declaration is refused loudly (DeclarationError), as
the capability declaration is.

**A tool error is a result, never an exception** (§4.3 of the seed: "tool
error (returned as a result, never a crash)"). `run_tool` never raises: an
unknown tool, arguments the schema refuses, a tool that cannot load, and a
tool that raised are each a ToolResult with `is_error` true and a sentence
naming the fault. The loop (R4) hands `content` and `is_error` to the
adapter's tool_result block (contract §5.6) as they are.

**The schema subset.** A tool's `input_schema` is JSON Schema with `type:
object` (R1's ToolSpec), written in a subset this module can check without a
dependency (T9): `type` (object, string, integer, number, boolean, array),
`properties`, `required`, `additionalProperties: false`, `items`,
`minItems`, `maxItems`, `minLength`, `exclusiveMinimum`, and `description`
for the model. A schema using anything else is a malformed tool, so a call
is never waved through a keyword nobody checks.

Reads twine's own files and imports twine's own modules; spawns nothing
itself (the tools spawn through the sandbox, twine/runtime/sandbox.py).

Sections:
  1. Tools and results              (~line 60)
  2. The schema subset              (~line 170)
  3. The declaration and the registry (~line 290)
  4. run_tool                       (~line 470)
  5. Rendering                      (~line 530)
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import math
import pkgutil
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Callable, Mapping

from twine.runtime import TOOLS_DECLARATION, TOOLS_DIR, TOOLS_PACKAGE
from twine.runtime.registry import DeclarationError, Problem, shown
from twine.runtime.terms import ToolSpec

log = logging.getLogger("twine.runtime.tooling")

# ---------------------------------------------------------------------------
# 1. Tools and results
# ---------------------------------------------------------------------------

# Every result's own three keys; a tool's pinned keys follow them.
RESULT_BASE_KEYS = ("name", "content", "is_error")


class ToolDefinitionError(ValueError):
    """A tool built a result outside its pinned keys — a defect in the tool,
    which run_tool turns into an error result naming it."""


@dataclass(frozen=True)
class ToolResult:
    """What a tool returns, error or not.

    name      the tool's name
    content   what the model reads back — a string
    is_error  whether the tool failed (a path outside the cage, a missing
              file, a timeout, bad arguments, …); a command that exits
              non-zero is not a failure of `shell`
    fields    the tool's pinned keys beyond the three (contract §6.2), in
              its declared order
    """

    name: str
    content: str
    is_error: bool
    fields: Mapping[str, Any] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        """`name`, `content`, `is_error`, then the tool's own keys."""
        out: dict[str, Any] = {"name": self.name, "content": self.content,
                               "is_error": self.is_error}
        for key, value in self.fields.items():
            out[key] = list(value) if isinstance(value, tuple) else value
        return out


Executor = Callable[[Any, Mapping[str, Any]], ToolResult]


@dataclass(frozen=True)
class Tool:
    """One canonical tool: its spec (what the model is offered), whether it
    leaves the cage, the keys its results carry beyond the base three, the
    values an error result carries for them unless the tool knows better,
    and its executor — `execute(sandbox, arguments) -> ToolResult`, called
    only by run_tool with arguments the schema has passed."""

    spec: ToolSpec
    leaves_cage: bool
    result_keys: tuple[str, ...]
    error_defaults: Mapping[str, Any]
    execute: Executor

    @property
    def name(self) -> str:
        return self.spec.name

    def ok(self, content: str, **fields: Any) -> ToolResult:
        """A successful result carrying exactly the tool's keys."""
        return self._make(content, False, fields)

    def error(self, content: str, **fields: Any) -> ToolResult:
        """An error result: the tool's keys, those not given taken from
        error_defaults."""
        return self._make(content, True, {**self.error_defaults, **fields})

    def _make(self, content: str, is_error: bool, fields: dict[str, Any]) -> ToolResult:
        if set(fields) != set(self.result_keys):
            missing = sorted(set(self.result_keys) - set(fields))
            extra = sorted(set(fields) - set(self.result_keys))
            raise ToolDefinitionError(f"tool {self.name!r} built a result with keys "
                                      f"missing {missing} and extra {extra}")
        if not isinstance(content, str):
            raise ToolDefinitionError(f"tool {self.name!r} built a result whose content "
                                      f"is a {type(content).__name__}, not a string")
        ordered = {key: fields[key] for key in self.result_keys}
        return ToolResult(self.name, content, is_error, MappingProxyType(ordered))

    def as_json(self) -> dict[str, Any]:
        """The row `twine runtime tools --json` prints."""
        return {"name": self.name, "description": self.spec.description,
                "input_schema": plain(self.spec.input_schema),
                "leaves_cage": self.leaves_cage}


def plain(value: Any) -> Any:
    """A schema as plain JSON data (mappings to dicts, tuples to lists)."""
    if isinstance(value, Mapping):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def bare_error(name: str, content: str) -> ToolResult:
    """An error result for a call that reached no tool (an unknown name, a
    tool that cannot load): the three base keys alone."""
    return ToolResult(str(name), content, True, MappingProxyType({}))


# ---------------------------------------------------------------------------
# 2. The schema subset
# ---------------------------------------------------------------------------

SCHEMA_TYPES = ("object", "string", "integer", "number", "boolean", "array")
SCHEMA_KEYWORDS = frozenset({"type", "properties", "required", "additionalProperties",
                             "items", "minItems", "maxItems", "minLength",
                             "exclusiveMinimum", "description"})


def schema_faults(schema: Any, where: str = "input_schema") -> list[str]:
    """Every reason `schema` is outside the subset this module checks; []
    when it is inside. The top level must be `type: object` with
    `properties` and `additionalProperties: false`."""
    found: list[str] = []
    if where == "input_schema":
        if not isinstance(schema, Mapping) or schema.get("type") != "object":
            return [f"{where} must be a JSON Schema object with type `object`"]
        if schema.get("additionalProperties") is not False:
            found.append(f"{where} must set additionalProperties false: a canonical "
                         "tool takes exactly the arguments it names")
    if not isinstance(schema, Mapping):
        return [f"{where} is not an object"]
    unknown = sorted(set(schema) - SCHEMA_KEYWORDS)
    if unknown:
        found.append(f"{where} uses {', '.join(unknown)}, outside the checked subset")
    kind = schema.get("type")
    if kind not in SCHEMA_TYPES:
        found.append(f"{where}.type {kind!r} is not one of {', '.join(SCHEMA_TYPES)}")
    if "description" in schema and (not isinstance(schema["description"], str)
                                    or not schema["description"].strip()):
        found.append(f"{where}.description must be a non-empty string")
    if kind == "object":
        props = schema.get("properties", {})
        if not isinstance(props, Mapping):
            found.append(f"{where}.properties is not an object")
            props = {}
        for name, sub in props.items():
            found += schema_faults(sub, f"{where}.properties.{name}")
        required = schema.get("required", [])
        if not isinstance(required, (list, tuple)) or not all(
                isinstance(r, str) for r in required):
            found.append(f"{where}.required is not a list of names")
        else:
            found += [f"{where}.required names {r!r}, which it does not define"
                      for r in required if r not in props]
        extra = schema.get("additionalProperties", False)
        if extra is not False:
            found.append(f"{where}.additionalProperties may only be false")
    if kind == "array":
        if "items" not in schema:
            found.append(f"{where} is an array with no items schema")
        else:
            found += schema_faults(schema["items"], f"{where}.items")
    for key in ("minItems", "maxItems", "minLength"):
        if key in schema and (type(schema[key]) is not int or schema[key] < 0):
            found.append(f"{where}.{key} must be a non-negative integer")
    if "exclusiveMinimum" in schema and (isinstance(schema["exclusiveMinimum"], bool)
                                         or not isinstance(schema["exclusiveMinimum"],
                                                           (int, float))):
        found.append(f"{where}.exclusiveMinimum must be a number")
    return found


def _type_ok(kind: str, value: Any) -> bool:
    if kind == "object":
        return isinstance(value, Mapping)
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return type(value) is int
    if kind == "number":
        return (type(value) in (int, float)) and math.isfinite(value)
    if kind == "boolean":
        return type(value) is bool
    if kind == "array":
        return isinstance(value, (list, tuple))
    return False


JSON_TYPE_NAMES = {dict: "an object", list: "an array", tuple: "an array", str: "a string",
                   int: "an integer", float: "a number", bool: "a boolean",
                   type(None): "null"}


def _named(value: Any) -> str:
    return JSON_TYPE_NAMES.get(type(value), type(value).__name__)


def argument_faults(schema: Mapping[str, Any], value: Any, where: str = "the call"
                    ) -> list[str]:
    """Every reason `value` does not fit `schema` (a schema inside the
    subset); [] when it fits. Each fault names the argument."""
    kind = schema.get("type")
    if not _type_ok(kind, value):
        article = "an" if kind[0] in "aeiou" else "a"
        return [f"{where} must be {article} {kind}, not {_named(value)}"]
    found: list[str] = []
    if kind == "object":
        props = schema.get("properties", {})
        for name in schema.get("required", ()):
            if name not in value:
                found.append(f"{where} lacks the required {name!r}")
        for name in value:
            if name not in props:
                found.append(f"{where} carries {name!r}, which the tool does not take "
                             f"(it takes {', '.join(props) or 'nothing'})")
        for name, sub in props.items():
            if name in value:
                found += argument_faults(sub, value[name], f"{name!r}"
                                         if where == "the call" else f"{where}.{name}")
    elif kind == "array":
        if "minItems" in schema and len(value) < schema["minItems"]:
            found.append(f"{where} holds {len(value)} item(s); at least "
                         f"{schema['minItems']} wanted")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            found.append(f"{where} holds {len(value)} items; at most "
                         f"{schema['maxItems']}")
        for n, item in enumerate(value, 1):
            found += argument_faults(schema["items"], item, f"{where}[{n}]")
    elif kind == "string":
        if "minLength" in schema and len(value) < schema["minLength"]:
            found.append(f"{where} is shorter than {schema['minLength']} "
                         f"character(s)")
    elif kind in ("integer", "number"):
        if "exclusiveMinimum" in schema and not value > schema["exclusiveMinimum"]:
            found.append(f"{where} must be greater than {schema['exclusiveMinimum']:g} "
                         f"(got {value!r})")
    return found


# ---------------------------------------------------------------------------
# 3. The declaration and the registry
# ---------------------------------------------------------------------------

ENTRY_KEYS = ("name", "module", "leaves_cage")
# A tool's name, as the model spells it: lowercase words joined by `_`.
TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
TOOL_MODULE_PATTERN = re.compile(r"^" + re.escape(TOOLS_PACKAGE) + r"\.[a-z][a-z0-9_]*$")

# Why the tool registry is not ok — each names what is at fault.
TOOL_PROBLEM_KINDS = (
    "stray-module",       # a module under tools/ the declaration does not list
    "missing-module",     # a declared tool whose module is absent
    "unloadable-module",  # a declared module that raises on import
    "no-tool",            # a module without a TOOL, or whose TOOL is not a Tool
    "tool-mismatch",      # TOOL names another tool than its entry
    "malformed-tool",     # TOOL's spec or result keys are not whole, or its schema
                          # is outside the checked subset
    "cage-mismatch",      # TOOL.leaves_cage disagrees with the declaration
)


@dataclass(frozen=True)
class DeclaredTool:
    """One [[tool]] entry of the declaration."""

    name: str
    module: str
    leaves_cage: bool

    @property
    def stem(self) -> str:
        return self.module.rsplit(".", 1)[1]


@dataclass
class ToolEntry:
    """A declared tool as the registry found it."""

    declared: DeclaredTool
    tool: Tool | None = None

    @property
    def name(self) -> str:
        return self.declared.name

    def as_json(self) -> dict[str, Any]:
        if self.tool is not None:
            return self.tool.as_json()
        return {"name": self.name, "description": None, "input_schema": None,
                "leaves_cage": self.declared.leaves_cage}


@dataclass
class ToolRegistry:
    """The loaded tool registry and every problem found loading it."""

    declaration: Path
    directory: Path
    tools: list[ToolEntry] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def names(self) -> list[str]:
        return [t.name for t in self.tools]

    def get(self, name: str) -> ToolEntry | None:
        return next((t for t in self.tools if t.name == name), None)

    def problems_for(self, name: str) -> list[Problem]:
        entry = self.get(name)
        names = {name} | ({entry.declared.stem} if entry else set())
        return [p for p in self.problems if p.name in names]

    def specs(self) -> tuple[ToolSpec, ...]:
        """What the loop offers the model: every loaded tool's spec, in the
        declaration's order."""
        return tuple(t.tool.spec for t in self.tools if t.tool is not None)

    def problem(self, kind: str, name: str, message: str) -> None:
        assert kind in TOOL_PROBLEM_KINDS, kind
        log.info("tool registry: %s: %s", kind, message)
        self.problems.append(Problem(kind, name, message))


def load_tool_declaration(path: Path = TOOLS_DECLARATION) -> list[DeclaredTool]:
    """The declaration's entries, in order, or DeclarationError naming every
    malformed entry: unreadable, not TOML, no [[tool]] entries, a top-level
    key other than `tool`, an entry with a missing or unknown key, a bad
    name, a module not directly under twine.runtime.tools, a `leaves_cage`
    that is not a boolean, a name or module declared twice."""
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        raise DeclarationError(f"{shown(path)}: {exc.strerror or exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise DeclarationError(f"{shown(path)}: not valid TOML: {exc}") from exc
    faults: list[str] = []
    extra = sorted(set(data) - {"tool"})
    if extra:
        faults.append(f"unknown top-level key(s) {', '.join(map(repr, extra))}; the "
                      "declaration holds [[tool]] entries only")
    raw = data.get("tool")
    if not isinstance(raw, list) or not raw:
        faults.append("no [[tool]] entries")
        raw = []
    entries: list[DeclaredTool] = []
    seen_names: set[str] = set()
    seen_modules: set[str] = set()
    for n, spec in enumerate(raw, 1):
        label = f"entry {n}"
        if not isinstance(spec, dict):
            faults.append(f"{label} is not a table")
            continue
        if isinstance(spec.get("name"), str):
            label = f"entry {n} ({spec['name']!r})"
        before = len(faults)
        missing = [k for k in ENTRY_KEYS if k not in spec]
        if missing:
            faults.append(f"{label} lacks {', '.join(map(repr, missing))}")
        unknown = sorted(set(spec) - set(ENTRY_KEYS))
        if unknown:
            faults.append(f"{label} has unknown key(s) {', '.join(map(repr, unknown))}")
        name, module, leaves = spec.get("name"), spec.get("module"), spec.get("leaves_cage")
        if "name" in spec and (not isinstance(name, str)
                               or not TOOL_NAME_PATTERN.match(name)):
            faults.append(f"{label}: name {name!r} is not lowercase words joined by `_`")
        if "module" in spec and (not isinstance(module, str)
                                 or not TOOL_MODULE_PATTERN.match(module)):
            faults.append(f"{label}: module {module!r} is not a module directly under "
                          f"{TOOLS_PACKAGE}")
        if "leaves_cage" in spec and type(leaves) is not bool:
            faults.append(f"{label}: leaves_cage {leaves!r} is not true or false")
        if len(faults) > before:
            continue
        if name in seen_names:
            faults.append(f"{label}: tool {name!r} is declared twice")
            continue
        if module in seen_modules:
            faults.append(f"{label}: module {module!r} is declared for two tools")
            continue
        seen_names.add(name)
        seen_modules.add(module)
        entries.append(DeclaredTool(name, module, leaves))
    if faults:
        log.error("tool declaration %s refused: %s", shown(path), "; ".join(faults))
        raise DeclarationError(f"{shown(path)}: " + "; ".join(faults))
    return entries


def tool_module_names(directory: Path = TOOLS_DIR) -> list[str]:
    """Every module (file or package) in `directory`, by name, sorted."""
    return sorted(m.name for m in pkgutil.iter_modules([str(directory)]))


def import_tool_module(name: str, directory: Path = TOOLS_DIR) -> ModuleType:
    """Import one tool module — through the package for the real directory,
    by file path under a private name for a test's copy (sys.modules is left
    as it was), as the capability registry does."""
    if directory.resolve() == TOOLS_DIR.resolve():
        return importlib.import_module(f"{TOOLS_PACKAGE}.{name}")
    path = directory / f"{name}.py"
    if not path.is_file():
        path = directory / name / "__init__.py"
    modname = f"_twine_tool_copy_{name}"
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(modname, None)
    return module


def tool_faults(tool: Tool) -> list[str]:
    """Every reason a TOOL is not whole; [] when it is."""
    found: list[str] = []
    spec = tool.spec
    if not isinstance(spec, ToolSpec):
        return [f"its spec is a {type(spec).__name__}, not a ToolSpec"]
    if not isinstance(spec.description, str) or not spec.description.strip():
        found.append("its description is empty")
    found += schema_faults(spec.input_schema)
    if type(tool.leaves_cage) is not bool:
        found.append(f"leaves_cage {tool.leaves_cage!r} is not a boolean")
    if not isinstance(tool.result_keys, tuple) or not all(
            isinstance(k, str) and k for k in tool.result_keys):
        found.append("result_keys is not a tuple of names")
    elif set(tool.result_keys) & set(RESULT_BASE_KEYS):
        found.append(f"result_keys repeats a base key ({', '.join(RESULT_BASE_KEYS)})")
    elif not isinstance(tool.error_defaults, Mapping) or \
            set(tool.error_defaults) != set(tool.result_keys):
        found.append("error_defaults must give a value for exactly the result keys")
    if not callable(tool.execute):
        found.append("its executor is not callable")
    return found


def load_tool(registry: ToolRegistry, entry: ToolEntry) -> None:
    """Import the entry's module and take its TOOL, naming each fault."""
    declared = entry.declared
    try:
        module = import_tool_module(declared.stem, registry.directory)
    except Exception as exc:   # any import failure is a named problem, never a crash
        registry.problem("unloadable-module", declared.name,
                         f"tool {declared.name!r}: module {declared.module} does not "
                         f"import: {type(exc).__name__}: {exc}")
        return
    tool = getattr(module, "TOOL", None)
    if not isinstance(tool, Tool):
        registry.problem("no-tool", declared.name,
                         f"tool {declared.name!r}: module {declared.module} has no TOOL"
                         if tool is None else
                         f"tool {declared.name!r}: {declared.module}.TOOL is a "
                         f"{type(tool).__name__}, not a Tool")
        return
    if tool.name != declared.name:
        registry.problem("tool-mismatch", declared.name,
                         f"tool {declared.name!r}: {declared.module}.TOOL is the tool "
                         f"{tool.name!r}")
        return
    faults = tool_faults(tool)
    if faults:
        registry.problem("malformed-tool", declared.name,
                         f"tool {declared.name!r}: " + "; ".join(faults))
        return
    if tool.leaves_cage != declared.leaves_cage:
        registry.problem("cage-mismatch", declared.name,
                         f"tool {declared.name!r}: the declaration says leaves_cage "
                         f"{str(declared.leaves_cage).lower()}, {declared.module}.TOOL "
                         f"says {str(tool.leaves_cage).lower()}")
        return
    entry.tool = tool


def load_tool_registry(declaration: Path = TOOLS_DECLARATION,
                       directory: Path = TOOLS_DIR) -> ToolRegistry:
    """Load the declaration (DeclarationError if it is malformed), check
    parity by name against `directory`, and load every TOOL. Every other
    fault is a Problem on the result; `tools` is in the declaration's order."""
    entries = load_tool_declaration(declaration)
    registry = ToolRegistry(declaration=declaration, directory=directory,
                            tools=[ToolEntry(d) for d in entries])
    present = set(tool_module_names(directory))
    listed = {e.stem for e in entries}
    for name in sorted(present - listed):
        registry.problem("stray-module", name,
                         f"module {TOOLS_PACKAGE}.{name} is under {shown(directory)}/ "
                         f"and {shown(declaration)} does not declare it")
    for entry in registry.tools:
        if entry.declared.stem not in present:
            registry.problem("missing-module", entry.name,
                             f"tool {entry.name!r} is declared with module "
                             f"{entry.declared.module}, and {shown(directory)}/ has no "
                             f"{entry.declared.stem}.py")
            continue
        load_tool(registry, entry)
    log.info("tool registry: %d tools, %d problems", len(registry.tools),
             len(registry.problems))
    return registry


# ---------------------------------------------------------------------------
# 4. run_tool
# ---------------------------------------------------------------------------


def run_tool(sandbox: Any, name: str, arguments: Mapping[str, Any], *,
             registry: ToolRegistry | None = None) -> ToolResult:
    """Run one tool call in `sandbox`. Never raises: an unknown tool, a tool
    that cannot load, arguments the schema refuses and a tool that raised are
    each an error result naming the fault."""
    if registry is None:
        try:
            registry = load_tool_registry()
        except DeclarationError as exc:
            log.error("run_tool %r: the tool declaration is malformed: %s", name, exc)
            return bare_error(name, f"no tool can run: the tool declaration is "
                                    f"malformed: {exc}")
    entry = registry.get(name) if isinstance(name, str) else None
    if entry is None:
        log.warning("run_tool: no tool is named %r", name)
        return bare_error(name, f"no tool is named {name!r}; the tools are "
                                f"{', '.join(registry.names)}")
    tool = entry.tool
    own = registry.problems_for(name)
    if tool is None or own:
        reason = "; ".join(p.message for p in own) or "it did not load"
        log.error("run_tool %r: the tool cannot run: %s", name, reason)
        return bare_error(name, f"tool {name!r} cannot run: {reason}")
    faults = argument_faults(tool.spec.input_schema, arguments)
    if faults:
        log.info("run_tool %r: arguments refused: %s", name, "; ".join(faults))
        return tool.error(f"{name}: the arguments do not fit the tool's input schema: "
                          + "; ".join(faults))
    frozen = MappingProxyType(dict(arguments))
    try:
        result = tool.execute(sandbox, frozen)
    except Exception as exc:   # a tool's defect is still a result, never a crash
        log.exception("run_tool %r: the tool raised", name)
        return tool.error(f"{name} failed inside twine: {type(exc).__name__}: {exc}")
    if not isinstance(result, ToolResult) or result.name != name:
        log.error("run_tool %r: the tool returned %r, not its ToolResult", name, result)
        return tool.error(f"{name} failed inside twine: it returned "
                          f"{type(result).__name__}, not its result")
    log.info("run_tool %r: %s", name, "error" if result.is_error else "ok")
    return result


# ---------------------------------------------------------------------------
# 5. Rendering
# ---------------------------------------------------------------------------


def tools_json(registry: ToolRegistry) -> dict[str, Any]:
    """`twine runtime tools --json`'s payload (cli-contract.md §17.6)."""
    return {
        "declaration": shown(registry.declaration),
        "directory": shown(registry.directory),
        "tools": [t.as_json() for t in registry.tools],
        "counts": {"tools": len(registry.tools),
                   "leaves_cage": sum(1 for t in registry.tools
                                      if t.declared.leaves_cage)},
        "problems": [p.as_json() for p in registry.problems],
        "reason": None if registry.ok else "; ".join(p.message for p in registry.problems),
    }


def _leaving(count: int) -> str:
    return f"{count} {'leaves' if count == 1 else 'leave'} the cage"


def tools_lines(registry: ToolRegistry) -> list[str]:
    """The same facts as readable lines."""
    lines = [f"tool registry {shown(registry.declaration)}: "
             f"{'ok' if registry.ok else 'NOT OK'}",
             f"  {len(registry.tools)} tools; "
             + _leaving(sum(1 for t in registry.tools if t.declared.leaves_cage)),
             ""]
    width = max((len(t.name) for t in registry.tools), default=0)
    for t in registry.tools:
        where = "leaves the cage" if t.declared.leaves_cage else "in the cage"
        args = ", ".join(t.tool.spec.input_schema.get("properties", {})) \
            if t.tool is not None else "-"
        lines.append(f"  {t.name:<{width}}  {where:<15}  {t.declared.module}  "
                     f"arguments: {args or '-'}")
        if t.tool is not None:
            lines.append(f"  {'':<{width}}  {t.tool.spec.description.splitlines()[0]}")
    if registry.problems:
        lines.append("")
        lines.append(f"{len(registry.problems)} problem(s):")
        lines.extend(f"  {p.kind}: {p.message}" for p in registry.problems)
    return lines

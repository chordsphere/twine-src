"""The runtime's capability registry (twine-seed.md T7, §4.1; TQ-2's file
shape, ratified 2026-10-12 — claude/context/runtime-contract.md §2).

The runtime applies N5's rule to itself, as twine/registry.py applies it
to the verbs: a declaration (twine/runtime/capabilities.toml) lists every
capability, a directory (twine/runtime/capabilities/) holds one module per
capability, and the two are held to each other **by name**:

  - a module in the directory that the declaration does not list is a
    `stray-module`, named by its module name;
  - a declared capability whose module is absent is a `missing-module`,
    named by the capability;
  - a module that does not import, has no CONTRACT, or whose CONTRACT is
    not whole or names another capability is named too.

Adapters are discovered by listing twine/runtime/adapters/ (each module's
ADAPTERS); each declares the capabilities it implements, and the registry
derives every capability's `adapters` from those sets and holds the
declared statuses to them (`declared`: none; `implemented`: at least one).

Since Arc 2 R3 a capability may be the runtime's own rather than an
adapter's — `sandboxing`: the cage is the runtime's, and an adapter must
never run a tool. Its entry says so with a fifth, optional key,
`implemented_by`, naming the runtime module that implements it (directly
under twine.runtime, not a package); that module declares the capabilities
it implements in an `IMPLEMENTS` tuple, as an adapter declares its set. The
status check is held, not loosened: `implemented` needs an implementer — a
registered adapter, or a sound `implemented_by` (the module imports and its
IMPLEMENTS lists the capability; otherwise `missing-implementer`); an entry
with `implemented_by` that is `declared` is a status-mismatch; and an adapter
claiming a runtime capability is a status-mismatch too.

`load_runtime_registry` never raises for any of those faults: each is a
Problem on the result, which `twine runtime list` reports by name (NOT OK,
exit 1). A declaration that is itself malformed — unreadable, not TOML, an
entry with a missing or unknown key, a bad name or status, a duplicate —
is different: `load_declaration` refuses it loudly with DeclarationError
naming every bad entry, as twine.registry.validate_command refuses a bad
Command, and the verbs report that refusal as NOT OK with its reason.

The registry is the only way into a capability module: nothing outside
twine/runtime/capabilities/ imports one (the shapes the boundary needs are
twine.runtime.terms), so `import_capability` failing — the module absent,
or raising — is a named problem here and never an import failure that
stops twine's verbs from loading (the HOLD of 2026-10-12; a test holds
it).

Reads twine's own files and imports twine's own modules; no bale, no
subprocess, no network.

Sections:
  1. Shapes                         (~line 60)
  2. The declaration                (~line 150)
  3. Capability modules             (~line 240)
  4. Adapters                       (~line 300)
  5. Assembling the registry        (~line 360)
  6. Rendering                      (~line 450)
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from twine import REPO_ROOT
from twine.runtime import (ADAPTERS_PACKAGE, CAPABILITIES_DECLARATION, CAPABILITIES_DIR,
                           CAPABILITIES_PACKAGE)
from twine.runtime.boundary import adapter_class_faults
from twine.runtime.contract import NAME_PATTERN, Contract

log = logging.getLogger("twine.runtime.registry")

# ---------------------------------------------------------------------------
# 1. Shapes
# ---------------------------------------------------------------------------

DECLARED = "declared"
IMPLEMENTED = "implemented"
EXPERIMENTAL = "experimental"
# A capability's status: a closed set of three.
STATUSES = (DECLARED, IMPLEMENTED, EXPERIMENTAL)
# A declaration entry's keys: these four, always ...
ENTRY_KEYS = ("name", "module", "status", "summary")
# ... and these, only when they apply (Arc 2 R3).
OPTIONAL_KEYS = ("implemented_by",)
# A runtime module that implements a capability itself: directly under
# twine.runtime, never one of its packages (the capabilities, the adapters,
# the tools) — an adapter's capability is declared by the adapter.
RUNTIME_PACKAGE = "twine.runtime"
IMPLEMENTER_PATTERN = re.compile(r"^" + re.escape(RUNTIME_PACKAGE) + r"\.[a-z][a-z0-9_]*$")
NOT_IMPLEMENTERS = frozenset({f"{RUNTIME_PACKAGE}.{name}"
                              for name in ("capabilities", "adapters", "tools")})
# A declared module: dotted, directly under the capabilities package, its
# last part a plain identifier (no leading underscore).
MODULE_PATTERN = re.compile(r"^" + re.escape(CAPABILITIES_PACKAGE) + r"\.[a-z][a-z0-9_]*$")

# Why the registry is not ok — each names what is at fault.
PROBLEM_KINDS = (
    "stray-module",        # a module under capabilities/ the declaration does not list
    "missing-module",      # a declared capability whose module is absent
    "unloadable-module",   # a declared module that raises on import
    "no-contract",         # a module without a CONTRACT
    "contract-mismatch",   # CONTRACT names another capability than its entry
    "malformed-contract",  # CONTRACT is not whole
    "status-mismatch",     # the declared status disagrees with the adapters
    "unloadable-adapter",  # an adapters module that raises on import, or has no ADAPTERS
    "malformed-adapter",   # an ADAPTERS entry the boundary cannot host
    "duplicate-adapter",   # two adapters registered under one name
    "unknown-capability",  # an adapter implements a capability nobody declared
    "missing-implementer", # an implemented_by module that is absent, does not import,
                           # or does not list the capability in its IMPLEMENTS
)


@dataclass(frozen=True)
class Declared:
    """One [[capability]] entry of the declaration."""

    name: str
    module: str      # dotted: twine.runtime.capabilities.<stem>
    status: str
    summary: str
    implemented_by: str | None = None   # a runtime module, when the runtime implements it

    @property
    def stem(self) -> str:
        """The module's file stem under twine/runtime/capabilities/."""
        return self.module.rsplit(".", 1)[1]


@dataclass(frozen=True)
class Problem:
    """One fault, naming the capability, module or adapter at fault."""

    kind: str
    name: str
    message: str

    def as_json(self) -> dict[str, str]:
        return {"kind": self.kind, "name": self.name, "message": self.message}


@dataclass
class CapabilityEntry:
    """A declared capability as the registry found it."""

    declared: Declared
    contract: Contract | None = None
    adapters: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.declared.name

    def as_json(self, *, with_contract: bool = False) -> dict[str, Any]:
        """The row `twine runtime list --json` prints; with the contract,
        the object `twine runtime show --json` prints."""
        row: dict[str, Any] = {"name": self.declared.name, "status": self.declared.status,
                               "summary": self.declared.summary,
                               "module": self.declared.module,
                               "adapters": list(self.adapters),
                               "implemented_by": self.declared.implemented_by}
        if with_contract:
            row["contract"] = None if self.contract is None else self.contract.as_json()
        return row


@dataclass(frozen=True)
class AdapterEntry:
    """A registered adapter: its name, what it implements, its tool
    protocol and the module that registers it."""

    name: str
    implements: tuple[str, ...]
    tool_protocol: str
    module: str

    def as_json(self) -> dict[str, Any]:
        return {"name": self.name, "implements": list(self.implements),
                "tool_protocol": self.tool_protocol, "module": self.module}


@dataclass
class RuntimeRegistry:
    """The loaded registry and every problem found loading it."""

    declaration: Path
    directory: Path
    capabilities: list[CapabilityEntry] = field(default_factory=list)
    adapters: list[AdapterEntry] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.capabilities]

    def get(self, name: str) -> CapabilityEntry | None:
        return next((c for c in self.capabilities if c.name == name), None)

    def problems_for(self, name: str) -> list[Problem]:
        """The problems naming this capability (or its module)."""
        entry = self.get(name)
        names = {name} | ({entry.declared.stem} if entry else set())
        return [p for p in self.problems if p.name in names]

    def problem(self, kind: str, name: str, message: str) -> None:
        assert kind in PROBLEM_KINDS, kind
        log.info("runtime registry: %s: %s", kind, message)
        self.problems.append(Problem(kind, name, message))


class DeclarationError(Exception):
    """The declaration cannot be read, is not TOML, or holds a malformed
    entry; the message names every fault."""


# ---------------------------------------------------------------------------
# 2. The declaration
# ---------------------------------------------------------------------------


def shown(path: Path) -> str:
    """A path as the verbs print it: repo-relative when it is under the
    repository, absolute otherwise."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def load_declaration(path: Path = CAPABILITIES_DECLARATION) -> list[Declared]:
    """The declaration's entries, in order, or DeclarationError naming every
    malformed entry. Refuses loudly; never drops or defaults an entry."""
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        raise DeclarationError(f"{shown(path)}: {exc.strerror or exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise DeclarationError(f"{shown(path)}: not valid TOML: {exc}") from exc
    extra = sorted(set(data) - {"capability"})
    raw = data.get("capability")
    faults: list[str] = []
    if extra:
        faults.append(f"unknown top-level key(s) {', '.join(map(repr, extra))}; the "
                      "declaration holds [[capability]] entries only")
    if not isinstance(raw, list) or not raw:
        faults.append("no [[capability]] entries")
        raw = []
    entries: list[Declared] = []
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
        unknown = sorted(set(spec) - set(ENTRY_KEYS) - set(OPTIONAL_KEYS))
        if unknown:
            faults.append(f"{label} has unknown key(s) {', '.join(map(repr, unknown))}")
        name, module = spec.get("name"), spec.get("module")
        status, summary = spec.get("status"), spec.get("summary")
        if "name" in spec and (not isinstance(name, str) or not NAME_PATTERN.match(name)):
            faults.append(f"{label}: name {name!r} is not lowercase words joined by hyphens")
        if "module" in spec and (not isinstance(module, str)
                                 or not MODULE_PATTERN.match(module)):
            faults.append(f"{label}: module {module!r} is not a module directly under "
                          f"{CAPABILITIES_PACKAGE} (`{CAPABILITIES_PACKAGE}.<name>`, the "
                          "name a plain identifier)")
        if "status" in spec and status not in STATUSES:
            faults.append(f"{label}: status {status!r} is not one of {', '.join(STATUSES)}")
        if "summary" in spec and (not isinstance(summary, str) or not summary.strip()
                                  or "\n" in summary):
            faults.append(f"{label}: summary must be one non-empty line")
        implementer = spec.get("implemented_by")
        if "implemented_by" in spec and (not isinstance(implementer, str)
                                         or not IMPLEMENTER_PATTERN.match(implementer)
                                         or implementer in NOT_IMPLEMENTERS):
            faults.append(f"{label}: implemented_by {implementer!r} is not a module "
                          f"directly under {RUNTIME_PACKAGE} (the runtime's own code — "
                          "an adapter's capability is declared by the adapter)")
        if len(faults) > before:
            continue
        if name in seen_names:
            faults.append(f"{label}: capability {name!r} is declared twice")
            continue
        if module in seen_modules:
            faults.append(f"{label}: module {module!r} is declared for two capabilities")
            continue
        seen_names.add(name)
        seen_modules.add(module)
        entries.append(Declared(name, module, status, summary.strip(), implementer))
    if faults:
        log.error("capability declaration %s refused: %s", shown(path), "; ".join(faults))
        raise DeclarationError(f"{shown(path)}: " + "; ".join(faults))
    log.debug("capability declaration %s: %d entries", shown(path), len(entries))
    return entries


# ---------------------------------------------------------------------------
# 3. Capability modules
# ---------------------------------------------------------------------------


def module_names(directory: Path = CAPABILITIES_DIR) -> list[str]:
    """Every module (file or package) in `directory`, by name, sorted —
    what the parity check walks. `__init__` is the package, not a module
    of it."""
    names = sorted(m.name for m in pkgutil.iter_modules([str(directory)]))
    log.debug("capability modules under %s: %s", shown(directory), names)
    return names


def import_capability(name: str, directory: Path = CAPABILITIES_DIR) -> ModuleType:
    """Import one capability module. The real directory imports through
    the package (so `twine.runtime.capabilities.usage_accounting` is one
    module object everywhere); another directory — a test's copy — loads
    by file path under a private name, leaving sys.modules alone."""
    if directory.resolve() == CAPABILITIES_DIR.resolve():
        return importlib.import_module(f"{CAPABILITIES_PACKAGE}.{name}")
    path = directory / f"{name}.py"
    if not path.is_file():
        path = directory / name / "__init__.py"
    modname = f"_twine_capability_copy_{name}"
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    # A dataclass resolves its module through sys.modules while the class
    # body runs, so the copy is registered for exactly the import and
    # removed after: the real package's modules are never shadowed.
    sys.modules[modname] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(modname, None)
    return module


def load_contract(registry: RuntimeRegistry, entry: CapabilityEntry) -> None:
    """Import the entry's module and take its CONTRACT, naming each fault."""
    declared = entry.declared
    try:
        module = import_capability(declared.stem, registry.directory)
    except Exception as exc:   # any import failure is a named problem, never a crash
        registry.problem("unloadable-module", declared.name,
                         f"capability {declared.name!r}: module {declared.module} does not "
                         f"import: {type(exc).__name__}: {exc}")
        return
    contract = getattr(module, "CONTRACT", None)
    if contract is None:
        registry.problem("no-contract", declared.name,
                         f"capability {declared.name!r}: module {declared.module} has no "
                         "CONTRACT")
        return
    if not isinstance(contract, Contract):
        registry.problem("no-contract", declared.name,
                         f"capability {declared.name!r}: {declared.module}.CONTRACT is a "
                         f"{type(contract).__name__}, not a Contract")
        return
    if contract.capability != declared.name:
        registry.problem("contract-mismatch", declared.name,
                         f"capability {declared.name!r}: {declared.module}.CONTRACT is the "
                         f"contract for {contract.capability!r}")
        return
    faults = contract.faults()
    if faults:
        registry.problem("malformed-contract", declared.name,
                         f"capability {declared.name!r}: its contract is not whole: "
                         + "; ".join(faults))
        return
    entry.contract = contract


# ---------------------------------------------------------------------------
# 4. Adapters
# ---------------------------------------------------------------------------


def load_adapters(registry: RuntimeRegistry, package: str = ADAPTERS_PACKAGE) -> None:
    """Discover every adapters module, register each ADAPTERS class, and
    name every fault: an unloadable module, a class the boundary cannot
    host, a duplicate name, a capability nobody declared."""
    pkg = importlib.import_module(package)
    declared = {c.name for c in registry.capabilities}
    for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        modname = f"{package}.{info.name}"
        try:
            module = importlib.import_module(modname)
        except Exception as exc:   # named, never a crash
            registry.problem("unloadable-adapter", info.name,
                             f"adapters module {modname} does not import: "
                             f"{type(exc).__name__}: {exc}")
            continue
        classes = getattr(module, "ADAPTERS", None)
        if not isinstance(classes, tuple):
            registry.problem("unloadable-adapter", info.name,
                             f"adapters module {modname} has no ADAPTERS tuple")
            continue
        for cls in classes:
            faults = adapter_class_faults(cls)
            label = getattr(cls, "name", getattr(cls, "__name__", repr(cls)))
            if faults:
                registry.problem("malformed-adapter", str(label),
                                 f"adapter {label!r} in {modname}: " + "; ".join(faults))
                continue
            if any(a.name == cls.name for a in registry.adapters):
                registry.problem("duplicate-adapter", cls.name,
                                 f"adapter {cls.name!r} is registered twice ({modname})")
                continue
            for capability in sorted(cls.implements - declared):
                registry.problem("unknown-capability", cls.name,
                                 f"adapter {cls.name!r} implements {capability!r}, which "
                                 "the declaration does not list")
            # In the declaration's order, so every renderer lists one order.
            implements = tuple(c.name for c in registry.capabilities
                               if c.name in cls.implements)
            registry.adapters.append(AdapterEntry(cls.name, implements, cls.tool_protocol,
                                                  modname))
            log.debug("registered adapter %r from %s", cls.name, modname)
    registry.adapters.sort(key=lambda a: a.name)


# ---------------------------------------------------------------------------
# 5. Assembling the registry
# ---------------------------------------------------------------------------


def load_runtime_registry(declaration: Path = CAPABILITIES_DECLARATION,
                          directory: Path = CAPABILITIES_DIR,
                          adapters_package: str = ADAPTERS_PACKAGE) -> RuntimeRegistry:
    """Load the declaration (DeclarationError if it is malformed), check
    parity by name against `directory`, load every contract and adapter,
    and hold the statuses to the adapters. Every other fault is a Problem
    on the result; the order of `capabilities` is the declaration's."""
    entries = load_declaration(declaration)
    registry = RuntimeRegistry(declaration=declaration, directory=directory,
                               capabilities=[CapabilityEntry(d) for d in entries])
    present = set(module_names(directory))
    listed = {e.stem for e in entries}
    for name in sorted(present - listed):
        registry.problem("stray-module", name,
                         f"module {CAPABILITIES_PACKAGE}.{name} is under "
                         f"{shown(directory)}/ and {shown(declaration)} does not "
                         "declare it")
    for entry in registry.capabilities:
        if entry.declared.stem not in present:
            registry.problem("missing-module", entry.name,
                             f"capability {entry.name!r} is declared with module "
                             f"{entry.declared.module}, and {shown(directory)}/ has no "
                             f"{entry.declared.stem}.py")
            continue
        load_contract(registry, entry)
    load_adapters(registry, adapters_package)
    for entry in registry.capabilities:
        entry.adapters = [a.name for a in registry.adapters if entry.name in a.implements]
        hold_status(registry, entry)
    log.info("runtime registry: %d capabilities, %d adapters, %d problems",
             len(registry.capabilities), len(registry.adapters), len(registry.problems))
    return registry


def runtime_implements(registry: RuntimeRegistry, entry: CapabilityEntry) -> bool:
    """Whether the entry's `implemented_by` module stands behind it: it
    imports, and its IMPLEMENTS lists the capability. Each failure is a
    `missing-implementer` problem naming the module."""
    module_name = entry.declared.implemented_by
    assert module_name is not None
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:   # named, never a crash
        registry.problem("missing-implementer", entry.name,
                         f"capability {entry.name!r} is implemented_by {module_name}, which "
                         f"does not import: {type(exc).__name__}: {exc}")
        return False
    implements = getattr(module, "IMPLEMENTS", None)
    if not isinstance(implements, tuple) or entry.name not in implements:
        registry.problem("missing-implementer", entry.name,
                         f"capability {entry.name!r} is implemented_by {module_name}, whose "
                         f"IMPLEMENTS does not list it ({implements!r})")
        return False
    return True


def hold_status(registry: RuntimeRegistry, entry: CapabilityEntry) -> None:
    """Hold the declared status to what implements the capability: the
    registered adapters, or — for a runtime capability — its implemented_by
    module (runtime-contract.md §2.3)."""
    status, implementer = entry.declared.status, entry.declared.implemented_by
    if implementer is not None:
        if entry.adapters:
            registry.problem("status-mismatch", entry.name,
                             f"capability {entry.name!r} is the runtime's (implemented_by "
                             f"{implementer}), and adapter(s) {', '.join(entry.adapters)} "
                             "claim it: an adapter never implements a runtime capability")
        sound = runtime_implements(registry, entry)
        if status == DECLARED:
            registry.problem("status-mismatch", entry.name,
                             f"capability {entry.name!r} is declared `{DECLARED}` and "
                             f"implemented_by {implementer}: it is `{IMPLEMENTED}`")
        elif status == IMPLEMENTED and not sound:
            registry.problem("status-mismatch", entry.name,
                             f"capability {entry.name!r} is declared `{IMPLEMENTED}` and "
                             f"its implemented_by module {implementer} does not stand "
                             "behind it")
        return
    if status == DECLARED and entry.adapters:
        registry.problem("status-mismatch", entry.name,
                         f"capability {entry.name!r} is declared `{DECLARED}` and "
                         f"adapter(s) {', '.join(entry.adapters)} implement it: it is "
                         f"`{IMPLEMENTED}`")
    elif status == IMPLEMENTED and not entry.adapters:
        registry.problem("status-mismatch", entry.name,
                         f"capability {entry.name!r} is declared `{IMPLEMENTED}` and no "
                         "registered adapter implements it")


# ---------------------------------------------------------------------------
# 6. Rendering
# ---------------------------------------------------------------------------


def status_counts(registry: RuntimeRegistry) -> dict[str, int]:
    counts = {s: 0 for s in STATUSES}
    for entry in registry.capabilities:
        counts[entry.declared.status] += 1
    return counts


def list_json(registry: RuntimeRegistry) -> dict[str, Any]:
    """`twine runtime list --json`'s payload (cli-contract.md §17)."""
    return {
        "declaration": shown(registry.declaration),
        "directory": shown(registry.directory),
        "statuses": list(STATUSES),
        "capabilities": [c.as_json() for c in registry.capabilities],
        "adapters": [a.as_json() for a in registry.adapters],
        "counts": {"capabilities": len(registry.capabilities), **status_counts(registry),
                   "adapters": len(registry.adapters)},
        "problems": [p.as_json() for p in registry.problems],
        "reason": None if registry.ok else "; ".join(p.message for p in registry.problems),
    }


def list_lines(registry: RuntimeRegistry) -> list[str]:
    """The same facts as readable lines."""
    counts = status_counts(registry)
    lines = [f"runtime registry {shown(registry.declaration)}: "
             f"{'ok' if registry.ok else 'NOT OK'}",
             f"  {len(registry.capabilities)} capabilities ("
             + ", ".join(f"{counts[s]} {s}" for s in STATUSES)
             + f"); {len(registry.adapters)} adapter(s)", ""]
    nwidth = max((len(c.name) for c in registry.capabilities), default=0)
    swidth = max(len(s) for s in STATUSES)
    for c in registry.capabilities:
        adapters = ", ".join(c.adapters) or "-"
        by = f"  implemented by {c.declared.implemented_by}" \
            if c.declared.implemented_by else ""
        lines.append(f"  {c.name:<{nwidth}}  {c.declared.status:<{swidth}}  "
                     f"{c.declared.module}  adapters: {adapters}{by}")
        lines.append(f"  {'':<{nwidth}}  {c.declared.summary}")
    lines.append("")
    lines.append("adapters")
    for a in registry.adapters:
        lines.append(f"  {a.name}  implements {', '.join(a.implements) or '-'}  "
                     f"(tool protocol {a.tool_protocol}; {a.module})")
    if not registry.adapters:
        lines.append("  (none registered)")
    if registry.problems:
        lines.append("")
        lines.append(f"{len(registry.problems)} problem(s):")
        lines.extend(f"  {p.kind}: {p.message}" for p in registry.problems)
    lines.append("")
    lines.append("contracts: `twine runtime show NAME`")
    return lines

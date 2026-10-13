"""`twine runtime list [--json]` and `twine runtime show NAME [--json]` —
render the runtime's capability registry (twine-seed.md T7, §4.1; Arc 2
R1) — and `twine runtime tools [--json]`, the canonical tool surface's
declaration (T6, §4.2; Arc 2 R3).

The registry is twine/runtime/registry.py over the declaration
(twine/runtime/capabilities.toml), the capability modules
(twine/runtime/capabilities/) and the registered adapters
(twine/runtime/adapters/). Both verbs read twine's own files and import
twine's own modules — no bale, no subprocess (neither touches `ctx.run`),
no network.

`list` is ok exactly when the declaration and the directory agree (parity
by name) and every entry loads — its contract whole, its status held to
the adapters; otherwise NOT OK, exit 1, each fault named. Contracts are
rendered by `show` only, so the list stays one screen. `show NAME` is ok
when NAME is a declared capability whose own entry loads; an unknown NAME
is NOT OK, the reason naming it and listing the known names. A malformed
declaration is NOT OK on both, the reason naming every bad entry.

`tools` renders twine/runtime/tools.toml held to twine/runtime/tools/ the
same way (twine.runtime.tooling): every tool with its name, description,
input schema and whether it leaves the cage; ok exactly when the declaration
and the directory agree by name and every TOOL loads whole; otherwise NOT OK,
exit 1, naming each stray or missing module. It too reads twine's own files
only and never touches the run seam. The contract is
claude/context/cli-contract.md §17.
"""

from __future__ import annotations

import argparse

from twine.cli import Context
from twine.registry import Argument, Command, Result
from twine.runtime import TOOLS_DECLARATION, tooling
from twine.runtime import registry as runtime_registry
from twine.runtime.registry import DeclarationError, RuntimeRegistry


def _load(ctx: Context) -> tuple[RuntimeRegistry | None, str | None]:
    """The registry, or None and the declaration's refusal."""
    try:
        return runtime_registry.load_runtime_registry(), None
    except DeclarationError as exc:
        reason = f"the capability declaration is malformed: {exc}"
        ctx.info(reason)
        return None, reason


def cmd_runtime_list(ctx: Context, args: argparse.Namespace) -> Result:
    """Every capability with its status, summary, module and adapters, and
    every registered adapter; ok when parity holds and every entry loads."""
    registry, refusal = _load(ctx)
    if registry is None:
        payload = {"declaration": runtime_registry.shown(
                       runtime_registry.CAPABILITIES_DECLARATION),
                   "capabilities": [], "adapters": [], "problems": [],
                   "reason": refusal}
        return Result(False, payload, [f"runtime registry: NOT OK — {refusal}"])
    for problem in registry.problems:
        ctx.info(f"{problem.kind}: {problem.message}")
    counts = runtime_registry.status_counts(registry)
    if registry.ok:
        ctx.info(f"runtime registry ok: {len(registry.capabilities)} capabilities ("
                 + ", ".join(f"{counts[s]} {s}" for s in runtime_registry.STATUSES)
                 + f"), {len(registry.adapters)} adapter(s)")
    return Result(registry.ok, runtime_registry.list_json(registry),
                  runtime_registry.list_lines(registry))


def cmd_runtime_show(ctx: Context, args: argparse.Namespace) -> Result:
    """One capability: the list's fields plus its contract."""
    name = args.name
    registry, refusal = _load(ctx)
    if registry is None:
        payload = {"name": name, "reason": refusal}
        return Result(False, payload, [f"runtime show {name}: NOT OK — {refusal}"])
    entry = registry.get(name)
    if entry is None:
        reason = (f"no capability is named {name!r}; the declared capabilities are "
                  f"{', '.join(registry.names)}")
        ctx.info(reason)
        payload = {"name": name, "known": registry.names, "reason": reason}
        return Result(False, payload, [f"runtime show {name}: NOT OK — {reason}"])
    own = registry.problems_for(name)
    for problem in own:
        ctx.info(f"{problem.kind}: {problem.message}")
    others = len(registry.problems) - len(own)
    if others:
        ctx.info(f"{others} other registry problem(s); `twine runtime list` names them")
    ok = not own and entry.contract is not None
    payload = entry.as_json(with_contract=True)
    payload.update({"problems": [p.as_json() for p in own],
                    "registry_ok": registry.ok,
                    "reason": None if ok else "; ".join(p.message for p in own)})
    lines = [f"capability {entry.name}: {'ok' if ok else 'NOT OK'}",
             f"  status: {entry.declared.status}",
             f"  summary: {entry.declared.summary}",
             f"  module: {entry.declared.module}",
             f"  adapters: {', '.join(entry.adapters) or '-'}",
             f"  registry: {'ok' if registry.ok else 'NOT OK (see twine runtime list)'}",
             "", "contract"]
    if entry.contract is not None:
        lines += [f"  {line}" for line in entry.contract.as_lines()]
    else:
        lines.append("  (not loaded)")
    if own:
        lines.append("")
        lines.append(f"{len(own)} problem(s):")
        lines.extend(f"  {p.kind}: {p.message}" for p in own)
    return Result(ok, payload, lines)


def cmd_runtime_tools(ctx: Context, args: argparse.Namespace) -> Result:
    """Every canonical tool with its name, description, input schema and
    whether it leaves the cage; ok when the declaration and the directory
    agree by name and every TOOL loads whole."""
    try:
        registry = tooling.load_tool_registry()
    except DeclarationError as exc:
        reason = f"the tool declaration is malformed: {exc}"
        ctx.info(reason)
        payload = {"declaration": runtime_registry.shown(TOOLS_DECLARATION),
                   "tools": [], "problems": [], "reason": reason}
        return Result(False, payload, [f"tool registry: NOT OK — {reason}"])
    for problem in registry.problems:
        ctx.info(f"{problem.kind}: {problem.message}")
    if registry.ok:
        ctx.info(f"tool registry ok: {len(registry.tools)} tools, "
                 f"{sum(1 for t in registry.tools if t.declared.leaves_cage)} leaving "
                 "the cage")
    return Result(registry.ok, tooling.tools_json(registry), tooling.tools_lines(registry))


COMMANDS = (
    Command(
        name="runtime list",
        summary="list the runtime's capabilities (status, module, adapters) and its "
                "adapters; ok when the declaration and the directory agree",
        handler=cmd_runtime_list,
        description="Render the runtime's capability registry: every capability "
                    "twine/runtime/capabilities.toml declares — its name, status "
                    "(declared, implemented or experimental), one-line summary, "
                    "module and the registered adapters that implement it — and "
                    "every registered adapter with what it implements. ok when "
                    "every declared capability has its module under "
                    "twine/runtime/capabilities/ and every module there is "
                    "declared (parity by name), every contract loads whole, and "
                    "every status agrees with the adapters; otherwise exit 1, "
                    "naming each fault. Contracts: `twine runtime show NAME`. "
                    "Reads twine's own files; runs nothing, reaches no network."),
    Command(
        name="runtime show",
        summary="show one runtime capability with its declared contract",
        handler=cmd_runtime_show,
        arguments=(
            Argument(("name",), {"metavar": "NAME",
                                 "help": "a capability's name, as `twine runtime "
                                         "list` prints it"}),
        ),
        description="Render one capability: the fields `twine runtime list` "
                    "prints, plus its declared contract — its purpose, what an "
                    "adapter that implements it must do, what the runtime "
                    "promises, where it lands and on what grounds. ok when NAME "
                    "is declared and its own entry loads; an unknown NAME is "
                    "exit 1, naming it and the known names."),
    Command(
        name="runtime tools",
        summary="list the canonical tools (name, description, input schema, whether "
                "it leaves the cage); ok when the declaration and the directory agree",
        handler=cmd_runtime_tools,
        description="Render the canonical tool surface: every tool "
                    "twine/runtime/tools.toml declares — its name, the description "
                    "and input schema the model is offered, and whether it leaves "
                    "the sandbox (only probe does). ok when every declared tool has "
                    "its module under twine/runtime/tools/ and every module there is "
                    "declared (parity by name), and every module's TOOL loads whole "
                    "and agrees with the declaration; otherwise exit 1, naming each "
                    "fault. Reads twine's own files; runs nothing, reaches no "
                    "network."),
)

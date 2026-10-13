"""The canonical tools — one module per tool (twine-seed.md T6, §4.2; Arc 2
R3; claude/context/runtime-contract.md §6).

Each module here is listed by twine/runtime/tools.toml under its dotted name
and exposes a module-level `TOOL` (twine.runtime.tooling.Tool): its ToolSpec
(name, description, input schema — what the model is offered), whether it
leaves the cage, its pinned result keys and its executor. A module the
declaration does not list, or a listed module that is absent, is a fault
`twine runtime tools` names; the registry reaches the modules by its own
guarded import (twine.runtime.tooling), so nothing imports a tool module
directly and a missing one never takes a verb down.

  shell       bash -c in the sandbox home, through the sandbox's runner
  read_file   a UTF-8 file inside the home
  write_file  UTF-8 text to a file inside the home, parents created
  list_dir    a directory inside the home, sorted by name
  probe       a read-only probe block run against the real repository (D13)
              — the one tool that leaves the cage
  escalate    a light question block (TARBALL.md §5.10) and a request to
              suspend
  deliver     names the response tarball the courier will carry

The pinned surface, re-exported here: `run_tool(sandbox, name, arguments)
-> ToolResult` (never raises) and `ToolResult.as_json()`.
"""

from __future__ import annotations

from twine.runtime.tooling import (Tool, ToolRegistry, ToolResult, load_tool_registry,
                                   run_tool)

__all__ = ["Tool", "ToolRegistry", "ToolResult", "load_tool_registry", "run_tool"]

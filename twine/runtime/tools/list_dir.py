"""`list_dir` — a directory inside the sandbox home, sorted by name (T6;
Arc 2 R3, runtime-contract.md §6.2).

The path (default `.`, the home) resolves against the home
(Sandbox.resolve); a symlinked directory leading out of the cage is refused
like any path. Each entry is `{name, kind, size}`: `kind` from the entry
itself, never followed — `file`, `dir`, `link` (a symlink, wherever it
points) or `other` — and `size` the bytes of a file, null for the rest.
"""

from __future__ import annotations

import stat
from typing import Any, Mapping

from twine.runtime.sandbox import CageError, Sandbox
from twine.runtime.terms import ToolSpec
from twine.runtime.tooling import Tool, ToolResult

KINDS = ("file", "dir", "link", "other")


def entry_of(path: Any) -> dict[str, Any]:
    """One entry, read with lstat: a symlink is a `link`, never followed."""
    st = path.lstat()
    if stat.S_ISLNK(st.st_mode):
        kind = "link"
    elif stat.S_ISDIR(st.st_mode):
        kind = "dir"
    elif stat.S_ISREG(st.st_mode):
        kind = "file"
    else:
        kind = "other"
    return {"name": path.name, "kind": kind, "size": st.st_size if kind == "file" else None}


def line_of(entry: dict[str, Any]) -> str:
    if entry["kind"] == "dir":
        return f"{entry['name']}/"
    if entry["kind"] == "file":
        return f"{entry['name']}  ({entry['size']} bytes)"
    return f"{entry['name']}  [{entry['kind']}]"


def execute(sandbox: Sandbox, arguments: Mapping[str, Any]) -> ToolResult:
    asked = arguments.get("path", ".")
    try:
        target = sandbox.resolve(asked)
    except CageError as exc:
        return TOOL.error(f"list_dir: refused: {exc}")
    rel = sandbox.relative(target)
    if not target.exists():
        return TOOL.error(f"list_dir: {rel} does not exist in the sandbox home", path=rel)
    if not target.is_dir():
        return TOOL.error(f"list_dir: {rel} is not a directory; read_file reads a file",
                          path=rel)
    try:
        entries = sorted((entry_of(child) for child in target.iterdir()),
                         key=lambda e: e["name"])
    except OSError as exc:
        return TOOL.error(f"list_dir: {rel} cannot be listed: {exc.strerror or exc}",
                          path=rel)
    lines = [f"{rel}: {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}"]
    lines += [f"  {line_of(e)}" for e in entries]
    return TOOL.ok("\n".join(lines) + "\n", path=rel, entries=entries)


TOOL = Tool(
    spec=ToolSpec(
        name="list_dir",
        description=("List a directory in your sandbox home, sorted by name: each "
                     "entry's name, kind (file, dir, link or other) and, for a file, "
                     "its size in bytes. The path is relative to the home and defaults "
                     "to the home itself."),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1,
                         "description": "the directory, relative to the sandbox home "
                                        "(default `.`)"},
            },
            "required": [],
            "additionalProperties": False,
        }),
    leaves_cage=False,
    result_keys=("path", "entries"),
    error_defaults={"path": None, "entries": ()},
    execute=execute,
)

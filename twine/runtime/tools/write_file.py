"""`write_file` — UTF-8 text to a file inside the sandbox home, its parent
directories created (T6; Arc 2 R3, runtime-contract.md §6.2).

The path resolves against the home (Sandbox.resolve), so the file and every
parent created are inside it; an existing file is replaced, an existing
directory is refused. `size` is the bytes written.
"""

from __future__ import annotations

from typing import Any, Mapping

from twine.runtime.sandbox import DIR_MODE, CageError, Sandbox
from twine.runtime.terms import ToolSpec
from twine.runtime.tooling import Tool, ToolResult


def execute(sandbox: Sandbox, arguments: Mapping[str, Any]) -> ToolResult:
    asked, content = arguments["path"], arguments["content"]
    try:
        target = sandbox.resolve(asked)
    except CageError as exc:
        return TOOL.error(f"write_file: refused: {exc}")
    rel = sandbox.relative(target)
    if target == sandbox.home or target.is_dir():
        return TOOL.error(f"write_file: {rel} is a directory; name a file inside it",
                          path=rel)
    try:
        data = content.encode("utf-8")
    except UnicodeEncodeError as exc:   # a lone surrogate cannot be UTF-8
        return TOOL.error(f"write_file: the content is not encodable as UTF-8 "
                          f"(character {exc.start}: {exc.reason})", path=rel)
    try:
        target.parent.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        target.write_bytes(data)
    except OSError as exc:
        return TOOL.error(f"write_file: {rel} cannot be written: {exc.strerror or exc}",
                          path=rel)
    return TOOL.ok(f"wrote {len(data)} bytes to {rel}", path=rel, size=len(data))


TOOL = Tool(
    spec=ToolSpec(
        name="write_file",
        description=("Write UTF-8 text to a file in your sandbox home, creating its "
                     "parent directories and replacing the file if it exists. The path "
                     "is relative to the home; absolute paths, `..` and symlinks that "
                     "lead out of it are refused."),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1,
                         "description": "the file, relative to the sandbox home"},
                "content": {"type": "string",
                            "description": "the file's whole text"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        }),
    leaves_cage=False,
    result_keys=("path", "size"),
    error_defaults={"path": None, "size": None},
    execute=execute,
)

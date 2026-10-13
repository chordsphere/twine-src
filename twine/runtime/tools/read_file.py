"""`read_file` — a UTF-8 file inside the sandbox home (T6; Arc 2 R3,
runtime-contract.md §6.2).

The path resolves against the home (Sandbox.resolve: absolute paths, `..`
and symlinks out are refused, naming the cage). A missing path, a directory,
anything but a regular file, a file over READ_FILE_CAP_BYTES and bytes that
are not UTF-8 are error results naming the fault. The content is the file's
text exactly, a leading byte-order mark included.
"""

from __future__ import annotations

from typing import Any, Mapping

from twine.runtime.sandbox import CageError, Sandbox
from twine.runtime.terms import ToolSpec
from twine.runtime.tooling import Tool, ToolResult

# The most a single read hands the model — shell's stdout cap. A bigger file
# is read in parts with `shell` (head, sed -n, …), as a person would.
READ_FILE_CAP_BYTES = 256 * 1024


def execute(sandbox: Sandbox, arguments: Mapping[str, Any]) -> ToolResult:
    asked = arguments["path"]
    try:
        target = sandbox.resolve(asked)
    except CageError as exc:
        return TOOL.error(f"read_file: refused: {exc}")
    rel = sandbox.relative(target)
    if not target.exists():
        return TOOL.error(f"read_file: {rel} does not exist in the sandbox home", path=rel)
    if not target.is_file():
        kind = "a directory" if target.is_dir() else "not a regular file"
        return TOOL.error(f"read_file: {rel} is {kind}; list_dir lists a directory",
                          path=rel)
    try:
        size = target.stat().st_size
        if size > READ_FILE_CAP_BYTES:
            return TOOL.error(f"read_file: {rel} is {size} bytes, over the "
                              f"{READ_FILE_CAP_BYTES}-byte cap of one read; read it in "
                              "parts with shell (head, sed -n)", path=rel, size=size)
        data = target.read_bytes()
    except OSError as exc:
        return TOOL.error(f"read_file: {rel} cannot be read: {exc.strerror or exc}",
                          path=rel)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return TOOL.error(f"read_file: {rel} is not UTF-8 text (byte {exc.start}: "
                          f"{exc.reason}); inspect it with shell (od, file)",
                          path=rel, size=len(data))
    return TOOL.ok(text, path=rel, size=len(data))


TOOL = Tool(
    spec=ToolSpec(
        name="read_file",
        description=("Read a UTF-8 text file in your sandbox home. The path is "
                     "relative to the home; absolute paths, `..` and symlinks that "
                     "lead out of it are refused. Returns the file's text."),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1,
                         "description": "the file, relative to the sandbox home"},
            },
            "required": ["path"],
            "additionalProperties": False,
        }),
    leaves_cage=False,
    result_keys=("path", "size"),
    error_defaults={"path": None, "size": None},
    execute=execute,
)

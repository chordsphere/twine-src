"""`deliver` — names the response tarball the courier will carry (T6, D13;
§4.3 of the seed: "a response tarball can't travel as text, hence
`deliver`"; Arc 2 R3, runtime-contract.md §6.2).

The path resolves against the sandbox home (Sandbox.resolve); it must be a
regular file there, and readable. The result names it — `path` (inside the
home), `size`, `sha256` — with `delivered: true`. Handing it to bale
(`twine carry response`) is the loop's, R4's: this tool reads the file and
moves nothing.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from twine.runtime.sandbox import CageError, Sandbox
from twine.runtime.terms import ToolSpec
from twine.runtime.tooling import Tool, ToolResult

CHUNK = 1024 * 1024


def execute(sandbox: Sandbox, arguments: Mapping[str, Any]) -> ToolResult:
    asked = arguments["tarball"]
    try:
        target = sandbox.resolve(asked)
    except CageError as exc:
        return TOOL.error(f"deliver: refused: {exc}")
    rel = sandbox.relative(target)
    if not target.exists():
        return TOOL.error(f"deliver: {rel} does not exist in the sandbox home", path=rel)
    if not target.is_file():
        return TOOL.error(f"deliver: {rel} is not a regular file; deliver the response "
                          "tarball itself", path=rel)
    digest = hashlib.sha256()
    size = 0
    try:
        with target.open("rb") as fh:
            while chunk := fh.read(CHUNK):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        return TOOL.error(f"deliver: {rel} cannot be read: {exc.strerror or exc}",
                          path=rel)
    sha = digest.hexdigest()
    return TOOL.ok(f"delivered {rel} ({size} bytes, sha256 {sha}); the courier carries "
                   "it when your turn ends", delivered=True, path=rel, size=size,
                   sha256=sha)


TOOL = Tool(
    spec=ToolSpec(
        name="deliver",
        description=("Hand over your finished work: name the response tarball, a file "
                     "in your sandbox home, that the courier will carry to bale. "
                     "Returns its size and sha256."),
        input_schema={
            "type": "object",
            "properties": {
                "tarball": {"type": "string", "minLength": 1,
                            "description": "the response tarball, relative to the "
                                           "sandbox home"},
            },
            "required": ["tarball"],
            "additionalProperties": False,
        }),
    leaves_cage=False,
    result_keys=("delivered", "path", "size", "sha256"),
    error_defaults={"delivered": False, "path": None, "size": None, "sha256": None},
    execute=execute,
)

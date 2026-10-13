"""`shell` — a command run by `bash -c` in the sandbox home (T6; Arc 2 R3,
runtime-contract.md §6.2).

The command runs through the sandbox's runner — wrapped `unshare -rn --`
when the network is off — with the home as its working directory, the cage's
minimal environment, stdin /dev/null, stdout capped (SHELL_STDOUT_CAP_BYTES),
a timeout (the call's, at most the sandbox's maximum; the maximum when the
call names none), and the process group killed however the run ends (the
seam's promise). Its group is registered with the kill-switch while it runs
(Sandbox.spawn).

A command that exits non-zero is **not** a tool error: the result carries the
exit code, stdout and stderr, and `is_error` is false. A timeout is (the
command did not finish), and so is the stdout cap (it was stopped, its output
incomplete); so are a spawn the kill-switch could not stand behind and a bash
that could not start.
"""

from __future__ import annotations

import signal
from typing import Any, Mapping

from twine import process
from twine.runtime.sandbox import Sandbox, SpawnRefused
from twine.runtime.terms import ToolSpec
from twine.runtime.tooling import Tool, ToolResult

BASH = "bash"
# What a model reads back is bounded: 256 KiB of stdout, carry probe's cap
# (cli-contract.md §10.3). Past it the group is killed and the result says so.
SHELL_STDOUT_CAP_BYTES = 256 * 1024


def render(stdout: str, stderr: str, exit_line: str) -> str:
    """What the model reads: stdout as it was, then stderr under a
    `[stderr]` line, then one bracketed line saying how the command ended —
    nothing dropped up to the cap, nothing added but those two markers."""
    parts: list[str] = []
    if stdout:
        parts.append(stdout if stdout.endswith("\n") else stdout + "\n")
    if stderr:
        parts.append("[stderr]\n" + (stderr if stderr.endswith("\n") else stderr + "\n"))
    parts.append(exit_line)
    return "".join(parts)


def exit_line(result: process.RunResult, timeout: float) -> str:
    if result.timed_out:
        line = f"[killed: timed out after {timeout:g}s; the command and its children were stopped]"
    elif result.stdout_capped:
        line = (f"[killed: stdout passed {SHELL_STDOUT_CAP_BYTES} bytes; the command was "
                "stopped and its output above is cut there]")
    elif result.exit_code is not None and result.exit_code < 0:
        try:
            name = signal.Signals(-result.exit_code).name
        except ValueError:
            name = f"signal {-result.exit_code}"
        line = f"[exit {result.exit_code}: killed by {name}]"
    else:
        line = f"[exit {result.exit_code}]"
    if result.stderr_truncated:
        line += f"\n[stderr cut at {process.DEFAULT_STDERR_CAP} bytes]"
    return line


def execute(sandbox: Sandbox, arguments: Mapping[str, Any]) -> ToolResult:
    command = arguments["command"]
    timeout = sandbox.tool_timeout(arguments.get("timeout"))
    try:
        result = sandbox.spawn([BASH, "-c", command], cwd=sandbox.home, timeout=timeout,
                               stdout_cap=SHELL_STDOUT_CAP_BYTES)
    except SpawnRefused as exc:
        return TOOL.error(f"shell: nothing ran: {exc}")
    except process.RunError as exc:
        return TOOL.error(f"shell: bash could not be started in the sandbox: "
                          f"{exc.strerror or exc}")
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    fields = {"exit_code": result.exit_code, "stdout": stdout, "stderr": stderr,
              "timed_out": result.timed_out, "stdout_capped": result.stdout_capped,
              "duration_seconds": result.duration_seconds}
    content = render(stdout, stderr, exit_line(result, timeout))
    if result.killed:
        return TOOL.error(content, **fields)
    return TOOL.ok(content, **fields)


TOOL = Tool(
    spec=ToolSpec(
        name="shell",
        description=("Run a command with `bash -c` in your sandbox home (the working "
                     "directory), with a minimal environment and no network. Returns "
                     "stdout, then stderr, then the exit code; a non-zero exit is a "
                     "result, not a failure. Stdout is capped at 256 KiB, and the "
                     "command and everything it started are stopped at the timeout."),
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "minLength": 1,
                            "description": "the command line, run by bash -c"},
                "timeout": {"type": "number", "exclusiveMinimum": 0,
                            "description": "seconds before the command is stopped; "
                                           "capped by the sandbox's maximum, which is "
                                           "also the default"},
            },
            "required": ["command"],
            "additionalProperties": False,
        }),
    leaves_cage=False,
    result_keys=("exit_code", "stdout", "stderr", "timed_out", "stdout_capped",
                 "duration_seconds"),
    error_defaults={"exit_code": None, "stdout": "", "stderr": "", "timed_out": False,
                    "stdout_capped": False, "duration_seconds": None},
    execute=execute,
)

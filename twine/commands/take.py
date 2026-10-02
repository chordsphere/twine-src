"""`twine take` — the courier's read of a worker turn (Arc 1 session 2a).

Reads text (a file, or stdin for `-`), finds every bale shape in it
with twine.shapes, verifies each integrity trailer, and reports. Text
in, one JSON line out: it executes nothing it reads, writes nothing,
calls no bale verb and reaches no network. Acting on what it found —
running a probe, handing a block to `bale relay`, a response to `bale
apply` — is session 2b's.

The keys (claude/context/cli-contract.md §9): `shape`, `blocks`, `ok`,
and `input` (what was read and how it was normalized). A block that
fails integrity or is malformed makes `ok` false and the exit 1 — a
truncated paste is a reported fact, never a traceback.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from twine import shapes
from twine.cli import Context
from twine.registry import Argument, Command, Result

STDIN = "-"


def read_input(ctx: Context, source: str) -> bytes:
    """The raw bytes of FILE, or of stdin for `-`. OSError propagates to
    the handler, which reports it."""
    if source == STDIN:
        return ctx.stdin.read()
    return Path(source).expanduser().read_bytes()


def block_line(n: int, block: shapes.Block) -> str:
    """One human line per block: kind, identity, where, integrity."""
    f = block.fields
    if block.kind == shapes.RELAY:
        ident = f"sid={f.get('sid')} to={f.get('to')}"
    elif block.kind in (shapes.LIGHT, shapes.EXCHANGE):
        ident = f"sid={f.get('sid')}"
        if block.kind == shapes.EXCHANGE and f.get("round") is not None:
            ident += f" round={f.get('round')} from={f.get('from')}"
        if block.kind == shapes.LIGHT:
            ident += f" questions={len(f.get('questions') or [])}"
    else:
        ident = f"slug={f.get('slug')}"
    integ = block.integrity
    if block.ok:
        if integ.get("basis") == "line-count":
            verdict = f"integrity ok ({integ['found_lines']} lines)"
        elif integ.get("basis") == "sha256":
            verdict = f"integrity ok (sha256 {integ['found_sha256'][:12]}…)"
        else:
            verdict = "integrity ok (structural)"
    else:
        verdict = f"NOT OK — {block.error}"
    return (f"[{n}] {block.kind:<12} {ident}  "
            f"lines {block.start_line}-{block.end_line}  {verdict}")


def cmd_take(ctx: Context, args: argparse.Namespace) -> Result:
    """Read, normalize, scan, report. Every failure — unreadable input,
    bytes that are not UTF-8, a block whose integrity fails — is a
    not-ok Result (exit 1) with the reason, never an exception."""
    source = args.file
    label = "<stdin>" if source == STDIN else source
    try:
        data = read_input(ctx, source)
    except OSError as exc:
        reason = f"cannot read {label}: {exc.strerror or exc}"
        ctx.info(reason)
        return Result(False, {"shape": None, "blocks": [],
                              "input": {"source": label}, "input_error": reason},
                      [f"take: {reason}"])
    try:
        norm = shapes.normalize(data)
    except ValueError as exc:
        reason = f"{label}: {exc}"
        ctx.info(reason)
        return Result(False, {"shape": None, "blocks": [],
                              "input": {"source": label, "bytes": len(data)},
                              "input_error": reason},
                      [f"take: {reason}"])
    report = shapes.find_blocks(norm.text)
    payload: dict[str, Any] = report.as_json()
    payload["input"] = {"source": label, "bytes": norm.bytes_read,
                        "lines": len(shapes.split_lines(norm.text)),
                        "crlf_normalized": norm.crlf_replaced,
                        "bom_stripped": norm.bom_stripped}
    for block in report.blocks:
        if not block.ok:
            ctx.info(f"{block.kind} at line {block.start_line}: {block.error}")
    n = len(report.blocks)
    lines = [f"take {label}: {n} block{'' if n == 1 else 's'}, shape {report.shape}, "
             + ("ok" if report.ok else "NOT OK")]
    lines += [block_line(k, b) for k, b in enumerate(report.blocks, 1)]
    return Result(report.ok, payload, lines)


COMMANDS = (
    Command(
        name="take",
        summary="read a pasted turn: find each bale shape, parse it, verify "
                "its integrity trailer — executes nothing",
        handler=cmd_take,
        arguments=(Argument(("file",), {
            "metavar": "FILE",
            "help": "the text to read (a worker's turn, a probe's output, a "
                    "relay block); `-` reads stdin"}),),
        description="Find every bale shape in FILE (probe, probe-output, "
                    "light, exchange, relay), parse each, verify the ones "
                    "that carry an integrity trailer, and report. CRLF is "
                    "read as LF. Nothing read is ever executed. Exit 0 when "
                    "every block is intact (prose included); 1 when any "
                    "block fails integrity or is malformed, or the input "
                    "cannot be read."),
)

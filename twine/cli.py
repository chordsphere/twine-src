"""The `twine` CLI: the parser rendered from the registry, dispatch, and
the --json discipline every verb obeys.

The discipline (claude/context/cli-contract.md carries it as the
interface the shell relies on):
  - with --json, exactly one line on stdout: a JSON object with at least
    "command" (the verb's space-joined path) and "ok" (a boolean);
    everything informational goes to stderr;
  - exit 0 when ok is true, 1 when the verb ran and reports not-ok, 2
    only on an internal error — and even then the one JSON line is
    emitted (ok false, an "error" object) before the traceback goes to
    stderr, so a consumer never reads an empty stdout;
  - a handled failure never prints a traceback;
  - without --json, the same facts as readable lines on stdout.

Sections:
  1. Context + logging           (~line 35)
  2. Parser from the registry    (~line 75)
  3. Dispatch                    (~line 150)
  4. main                        (~line 215)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Callable, Mapping, TextIO

from twine import __version__
from twine.process import Runner, run_process
from twine.registry import Command, Result, load_registry

log = logging.getLogger("twine.cli")

PROG = "twine"
EXIT_OK = 0
EXIT_NOT_OK = 1
EXIT_INTERNAL = 2

# ---------------------------------------------------------------------------
# 1. Context + logging
# ---------------------------------------------------------------------------


@dataclass
class Context:
    """What a handler may touch besides its parsed arguments.

    Every environmental dependency is a field so tests inject their own:
    `env` instead of os.environ, `which` instead of shutil.which, the
    two output streams, and `stdin` — bytes, read by `twine take -`, so
    the verb decodes it itself rather than trusting the locale. Handlers
    write informational text to `stderr` only; stdout is the dispatcher's.

    `run` is the seam through which a handler runs a subprocess — the
    only one (twine/process.py; cli-contract.md §10.6). Its default
    spawns a real process group; tests inject a double with the same
    signature, and session 2b-ii's fixture player answers bale argvs
    from fixtures/ through it.
    """

    env: Mapping[str, str] = field(default_factory=lambda: os.environ)
    stdout: TextIO = field(default_factory=lambda: sys.stdout)
    stderr: TextIO = field(default_factory=lambda: sys.stderr)
    which: Callable[[str], str | None] = shutil.which
    stdin: BinaryIO = field(default_factory=lambda: sys.stdin.buffer)
    run: Runner = run_process

    def info(self, message: str) -> None:
        """An informational line for a human: stderr, never stdout."""
        self.stderr.write(f"[twine] {message}\n")


def configure_logging(verbose: bool, stream: TextIO) -> None:
    """Structured, leveled, stderr-only. --verbose shows INFO and DEBUG;
    the default shows WARNING and up. Re-entrant for in-process tests."""
    root = logging.getLogger("twine")
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("[twine %(levelname)s] %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if verbose else logging.WARNING)
    root.propagate = False


# ---------------------------------------------------------------------------
# 2. Parser from the registry
# ---------------------------------------------------------------------------

# argparse Namespace attribute carrying the matched verb's full name.
DEST_COMMAND = "_twine_command"


def build_parser(registry: Mapping[str, Command]) -> argparse.ArgumentParser:
    """Render argparse from the registry — nested subparsers for
    multi-word verbs ("bale check" -> `bale` group, `check` leaf) —
    so --help, the parser, and `twine commands` cannot disagree.
    """
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="twine — the process layer of the Nisaba suite: the "
                    "courier, the runtime and the scheduler, one CLI, a "
                    "JSON twin for every command.",
        epilog="`twine commands` lists every verb; `twine <verb> --json` "
               "emits one JSON line on stdout.")
    parser.add_argument("--version", action="version",
                        version=f"{PROG} {__version__}")
    parser.add_argument("--verbose", action="store_true",
                        help="log INFO and DEBUG lines to stderr")
    parser.set_defaults(**{DEST_COMMAND: None})

    # Groups are created on first use, keyed by their path prefix.
    groups: dict[tuple[str, ...], argparse._SubParsersAction] = {}

    def subparsers_for(prefix: tuple[str, ...]) -> argparse._SubParsersAction:
        if prefix in groups:
            return groups[prefix]
        if not prefix:
            action = parser.add_subparsers(title="commands", metavar="<command>",
                                           required=True)
        else:
            parent = subparsers_for(prefix[:-1])
            group = parent.add_parser(
                prefix[-1], help=f"{' '.join(prefix)} verbs",
                description=f"{' '.join(prefix)} — a group; pick a sub-command.")
            action = group.add_subparsers(title="sub-commands",
                                          metavar="<sub-command>", required=True)
        groups[prefix] = action
        return action

    for cmd in registry.values():
        leaf = subparsers_for(cmd.path[:-1]).add_parser(
            cmd.path[-1], help=cmd.summary,
            description=cmd.description or cmd.summary)
        for arg in cmd.arguments:
            leaf.add_argument(*arg.flags, **arg.kwargs)
        if cmd.json:
            leaf.add_argument("--json", action="store_true",
                              help="emit one JSON object line on stdout "
                                   "(informational lines go to stderr)")
        else:
            leaf.set_defaults(json=False)
        leaf.set_defaults(**{DEST_COMMAND: cmd.name})
    return parser


def parser_leaf_names(parser: argparse.ArgumentParser) -> set[str]:
    """Every leaf verb the parser accepts, as space-joined paths — walked
    from the parser itself, so the parity test compares two independent
    renderings of the registry."""
    names: set[str] = set()

    def walk(p: argparse.ArgumentParser, prefix: tuple[str, ...]) -> None:
        subs = [a for a in p._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            if prefix:
                names.add(" ".join(prefix))
            return
        for action in subs:
            for word, child in action.choices.items():
                walk(child, prefix + (word,))

    walk(parser, ())
    return names


# ---------------------------------------------------------------------------
# 3. Dispatch
# ---------------------------------------------------------------------------


def emit_json(stream: TextIO, command: str, ok: bool,
              payload: Mapping[str, Any]) -> None:
    """The one line. json.dumps never emits a newline inside an object,
    so `line` is one physical line by construction; the check below is
    the assertion that keeps it that way if a payload ever carries a
    raw newline through a non-string."""
    obj: dict[str, Any] = {"command": command, "ok": ok}
    for key, value in payload.items():
        if key in obj:
            # The two contract keys are the dispatcher's; a handler that
            # tries to set them is a bug worth hearing about, not a
            # silent override of the exit code's own basis.
            log.warning("payload key %r ignored: it is the dispatcher's", key)
            continue
        obj[key] = value
    line = json.dumps(obj, ensure_ascii=False)
    if "\n" in line:
        raise RuntimeError("JSON twin rendered more than one line")
    stream.write(line + "\n")
    stream.flush()


def run_command(cmd: Command, args: argparse.Namespace, ctx: Context) -> int:
    """Run one verb under the --json discipline and return the exit code."""
    json_mode = bool(getattr(args, "json", False))
    try:
        result: Result = cmd.handler(ctx, args)
    except Exception as exc:   # internal error: report, then exit 2
        log.error("internal error in %r: %s: %s", cmd.name, type(exc).__name__, exc)
        if json_mode:
            emit_json(ctx.stdout, cmd.name, False,
                      {"error": {"type": type(exc).__name__, "message": str(exc)}})
        else:
            ctx.stdout.write(f"{PROG} {cmd.name}: internal error: "
                             f"{type(exc).__name__}: {exc}\n")
        ctx.stderr.write(traceback.format_exc())
        return EXIT_INTERNAL
    if json_mode:
        emit_json(ctx.stdout, cmd.name, result.ok, result.payload)
    else:
        for line in result.lines:
            ctx.stdout.write(line + "\n")
        ctx.stdout.flush()
    code = EXIT_OK if result.ok else EXIT_NOT_OK
    log.info("%s: ok=%s exit=%d", cmd.name, result.ok, code)
    return code


# ---------------------------------------------------------------------------
# 4. main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None, *, ctx: Context | None = None) -> int:
    """Parse, dispatch, return the exit code (bin/twine passes it to
    sys.exit). argparse's own exits — --help and --version (0), a usage
    error (2, usage on stderr, nothing on stdout) — are returned as
    codes rather than raised, so in-process callers see one contract."""
    ctx = ctx or Context()
    argv = sys.argv[1:] if argv is None else list(argv)
    registry = load_registry()
    parser = build_parser(registry)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    configure_logging(args.verbose, ctx.stderr)
    name = getattr(args, DEST_COMMAND)
    cmd = registry[name]
    log.debug("dispatching %r with %s", name, vars(args))
    return run_command(cmd, args, ctx)

"""The command registry — the single source for twine's verbs (N5, T4).

Every verb is a Command. The argparse wiring, `--help`, and the
`twine commands` listing are all rendered from the registry, and
tests/test_registry.py asserts the parser and the registry agree (the
parity test's seed).

Commands are declared by the modules under twine/commands/: each module
exposes a COMMANDS tuple, and load_registry() discovers the modules by
listing that package (sorted, so the order is deterministic). The point
of discovery over a hand-maintained list is concurrency: Arc 1's
sessions 2 and 3 each add one module and never edit a shared file.

Verb names are the full space-joined path ("bale check"), which is how
the registry, the JSON `command` key, and the parser's nested
subcommands all spell the same verb.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("twine.registry")

COMMANDS_PACKAGE = "twine.commands"


@dataclass(frozen=True)
class Argument:
    """One argparse argument a command takes, declared as data.

    `flags` is the positional name or the option strings; `kwargs` goes
    to add_argument unchanged. Declared as data rather than a callback
    so `twine commands` and future renderers can list a verb's flags
    without building a parser.
    """

    flags: tuple[str, ...]
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    """What a handler returns.

    `ok` decides the exit code (0 when true, 1 when false). `payload` is
    merged into the --json object beside `command` and `ok`; `lines` is
    the human rendering printed without --json. Both carry the same
    facts — the JSON twin is never richer or poorer than the lines.
    """

    ok: bool
    payload: dict[str, Any] = field(default_factory=dict)
    lines: list[str] = field(default_factory=list)


Handler = Callable[[Any, Any], Result]   # (Context, argparse.Namespace) -> Result


@dataclass(frozen=True)
class Command:
    """One registered verb.

    name     the full space-joined path, e.g. "bale check"
    summary  one line, shown by --help and `twine commands`
    handler  the function that runs it
    json     whether the verb has a --json twin; a verb without one is
             listed by `twine commands` with cli_only: true, never
             omitted (cli_only is derived from this field so the two
             can never disagree)
    arguments  the verb's own argparse arguments, as data
    description  the long help; the summary when None
    """

    name: str
    summary: str
    handler: Handler
    json: bool = True
    arguments: tuple[Argument, ...] = ()
    description: str | None = None

    @property
    def path(self) -> tuple[str, ...]:
        return tuple(self.name.split(" "))

    @property
    def cli_only(self) -> bool:
        return not self.json

    def listing(self) -> dict[str, Any]:
        """The `twine commands --json` row for this verb."""
        return {"name": self.name, "summary": self.summary,
                "json": self.json, "cli_only": self.cli_only}


class RegistryError(Exception):
    """A commands module declared something the registry cannot host."""


def validate_command(cmd: Command, origin: str) -> None:
    """Refuse a malformed declaration loudly, naming the module."""
    if not isinstance(cmd, Command):
        raise RegistryError(f"{origin}: COMMANDS holds a non-Command: {cmd!r}")
    if not cmd.name or cmd.name != " ".join(cmd.name.split()):
        raise RegistryError(
            f"{origin}: command name {cmd.name!r} must be words joined by "
            "single spaces")
    for word in cmd.path:
        if not word.replace("-", "").isalnum() or word != word.lower():
            raise RegistryError(
                f"{origin}: command path word {word!r} in {cmd.name!r} must "
                "be lowercase alphanumeric with hyphens")
    if not cmd.summary.strip():
        raise RegistryError(f"{origin}: command {cmd.name!r} has no summary")
    if not callable(cmd.handler):
        raise RegistryError(f"{origin}: command {cmd.name!r} handler is not "
                            "callable")


def discover_modules(package: str = COMMANDS_PACKAGE) -> list[str]:
    """The dotted names of every module under twine/commands/, sorted."""
    pkg = importlib.import_module(package)
    names = sorted(m.name for m in pkgutil.iter_modules(pkg.__path__))
    log.debug("discovered command modules under %s: %s", package, names)
    return [f"{package}.{n}" for n in names]


def load_registry(package: str = COMMANDS_PACKAGE) -> dict[str, Command]:
    """Import every commands module and collect its COMMANDS.

    Returns an insertion-ordered dict keyed by verb name, sorted by name
    so every renderer lists verbs in one stable order. A duplicate name,
    a module without COMMANDS, or a malformed Command refuses.
    """
    found: dict[str, Command] = {}
    for modname in discover_modules(package):
        module = importlib.import_module(modname)
        commands = getattr(module, "COMMANDS", None)
        if commands is None:
            raise RegistryError(f"{modname}: no COMMANDS tuple")
        for cmd in commands:
            validate_command(cmd, modname)
            if cmd.name in found:
                raise RegistryError(
                    f"{modname}: duplicate command name {cmd.name!r}")
            found[cmd.name] = cmd
            log.debug("registered %r from %s", cmd.name, modname)
    # A prefix of one verb's path cannot be another verb: "bale" would be
    # both a group and a leaf, and argparse cannot express that.
    names = set(found)
    for name in names:
        words = name.split(" ")
        for i in range(1, len(words)):
            prefix = " ".join(words[:i])
            if prefix in names:
                raise RegistryError(
                    f"command {prefix!r} is also a group prefix of {name!r}")
    return dict(sorted(found.items()))

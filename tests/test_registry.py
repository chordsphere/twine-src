"""The command registry and its parity with the parser (N5, T4)."""

from __future__ import annotations

import json
import unittest

from twine.cli import build_parser, parser_leaf_names
from twine.registry import (Command, RegistryError, Result, discover_modules,
                            load_registry, validate_command)

from tests.helpers import run_inprocess


def _noop(ctx, args):
    return Result(True)


class RegistryParity(unittest.TestCase):
    """The parity test's seed: the parser and the registry agree."""

    def test_parser_leaves_equal_registry_names(self):
        registry = load_registry()
        parser = build_parser(registry)
        self.assertEqual(parser_leaf_names(parser), set(registry))

    def test_commands_listing_equals_registry(self):
        """`twine commands --json` lists every verb, no omissions, with
        the four keys the brief fixes, in the registry's order."""
        registry = load_registry()
        run = run_inprocess("commands", "--json")
        self.assertEqual(run.code, 0)
        obj = json.loads(run.stdout)
        self.assertEqual([r["name"] for r in obj["commands"]], list(registry))
        for row in obj["commands"]:
            self.assertEqual(set(row), {"name", "summary", "json", "cli_only"})
            self.assertIsInstance(row["json"], bool)
            self.assertEqual(row["cli_only"], not row["json"])

    def test_this_sessions_verbs_are_registered(self):
        self.assertEqual(set(load_registry()),
                         {"commands", "status", "bale check", "take", "carry probe"})

    def test_verb_names_are_space_joined_paths(self):
        for name, cmd in load_registry().items():
            self.assertEqual(cmd.name, name)
            self.assertEqual(" ".join(cmd.path), name)


class RegistryDiscovery(unittest.TestCase):

    def test_discovers_core_module(self):
        self.assertIn("twine.commands.core", discover_modules())

    def test_discovers_take_module(self):
        self.assertIn("twine.commands.take", discover_modules())

    def test_discovers_carry_module_as_a_group(self):
        """`carry` is a verb family: its verbs share the group prefix, and
        the parser renders `carry` as a group with a `probe` leaf."""
        self.assertIn("twine.commands.carry", discover_modules())
        carry = [n for n in load_registry() if n.split(" ")[0] == "carry"]
        self.assertEqual(carry, ["carry probe"])

    def test_registry_is_sorted_by_name(self):
        names = list(load_registry())
        self.assertEqual(names, sorted(names))

    def test_cli_only_is_derived_from_json(self):
        cmd = Command(name="x", summary="s", handler=_noop, json=False)
        self.assertTrue(cmd.cli_only)
        self.assertEqual(cmd.listing(), {"name": "x", "summary": "s",
                                         "json": False, "cli_only": True})


class RegistryValidation(unittest.TestCase):

    def test_refuses_bad_names(self):
        for bad in ("", "Bale check", "bale  check", " bale", "bale_check"):
            with self.subTest(name=bad):
                with self.assertRaises(RegistryError):
                    validate_command(Command(name=bad, summary="s", handler=_noop),
                                     "test")

    def test_refuses_empty_summary_and_bad_handler(self):
        with self.assertRaises(RegistryError):
            validate_command(Command(name="x", summary=" ", handler=_noop), "test")
        with self.assertRaises(RegistryError):
            validate_command(Command(name="x", summary="s", handler="nope"), "test")  # type: ignore[arg-type]

    def test_refuses_non_command(self):
        with self.assertRaises(RegistryError):
            validate_command("not a command", "test")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

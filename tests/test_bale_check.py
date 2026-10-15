"""`twine bale check` (D2): install-root resolution and the gate, against
temp roots the tests build — never a real install.

Since session 2026-10-15-twine-gate-contract-001 the gate is the floor plus
bale's contract, where it was the floor plus the manifest's schema hashes
(session 2026-10-12-twine-pin-floor-002) and before that an exact pin: ok
exactly when `<root>/bin/VERSION` parses as three dotted integers at or
above the floor (0.4.54), compared as a tuple, and `<root>/bin/bale contract
--json`, run through the seam, prints one contract line for that version
stating the transition table's three vocabularies exactly, every key each
line twine reads carries, and every outcome and the one unlock reason twine
dispatches on. No file under `<root>/schemas/` is read.

Every root's `bin/bale` here is a double (tests/helpers.py make_root): the
carried line, fixtures/contract/bale-0.4.55.json, replayed byte-exact at
0.4.55, and every other line built from it and named as a double. The
matrix is the brief's: at the floor, above, far above, below, unparsable,
schemas absent or altered (admitted), a key removed, a vocabulary value
added or removed, hold-branch removed, a bale_version that disagrees, a
non-zero exit, two lines, not JSON — each reason named, every failing fact
at once, and no `pin` or `schemas` key anywhere."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from twine import CONSUMPTION_MANIFEST, bale, inflight, kill
from twine.bale import (CONTRACT_STDOUT_CAP_BYTES, CONTRACT_TIMEOUT_SECONDS,
                        DISPATCHED_OUTCOMES, DISPATCHED_REASONS, ENV_ROOT, ManifestError,
                        check, contract_argv, contract_findings, load_manifest,
                        parse_contract_stdout, parse_version, read_installed_version,
                        resolve_root)
from twine.commands import carry_bale, carry_bundle
from twine.process import RunResult, run_process

from tests.helpers import (ABOVE, BALE_VOCABULARIES, CONTRACT_BYTES, CONTRACT_RELPATH,
                           CONTRACT_SHA256, CONTRACT_VERSION, FLOOR, NOT_A_BALE_OUTCOME,
                           RECORDINGS, RecordingRunner, TempRoots, add_refusal_reason,
                           add_vocabulary_value, carried_contract, contract_line,
                           drop_contract_key, drop_refusal_reason, drop_vocabulary_value,
                           edited_contract, make_root, run_cli, run_inprocess,
                           set_bale_version)

# The lines twine reads, by the reader's surface, as the brief names them.
READ_LINES = {"open": ("open", "open-refused"), "relay": ("relay", "relay-refused"),
              "unlock": ("unlock", "unlock-refused"), "apply": ("apply",)}


class RootResolution(unittest.TestCase):

    def test_explicit_wins_over_env_and_path(self):
        root = resolve_root("/explicit", {ENV_ROOT: "/env"}, lambda n: "/path/bin/bale")
        self.assertEqual((root.path, root.source), (Path("/explicit"), "--bale-root"))

    def test_env_wins_over_path(self):
        root = resolve_root(None, {ENV_ROOT: "/env"}, lambda n: "/path/bin/bale")
        self.assertEqual((root.path, root.source), (Path("/env"), ENV_ROOT))

    def test_path_is_followed_to_its_real_bin_parent(self):
        roots = TempRoots()
        self.addCleanup(roots.cleanup)
        exe = roots.ok / "bin" / "bale"
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        link_dir = roots.ok.parent / "local-bin"
        link_dir.mkdir()
        link = link_dir / "bale"
        link.symlink_to(exe)
        root = resolve_root(None, {}, lambda n: str(link))
        self.assertEqual((root.path, root.source), (roots.ok, "PATH"))

    def test_nothing_found(self):
        root = resolve_root(None, {}, lambda n: None)
        self.assertFalse(root.found)
        self.assertIsNone(root.source)
        self.assertIn("no bale on PATH", root.detail)


class InstalledVersion(unittest.TestCase):

    def setUp(self):
        self.roots = TempRoots()
        self.addCleanup(self.roots.cleanup)

    def test_reads_and_strips(self):
        self.assertEqual(read_installed_version(self.roots.ok)[0], CONTRACT_VERSION)
        self.assertEqual(read_installed_version(self.roots.at_floor)[0], FLOOR)

    def test_absent_is_none_with_reason(self):
        version, detail = read_installed_version(self.roots.absent)
        self.assertIsNone(version)
        self.assertIn("unreadable", detail)

    def test_empty_is_none(self):
        (self.roots.absent / "bin").mkdir()
        (self.roots.absent / "bin" / "VERSION").write_text("\n", encoding="utf-8")
        self.assertIsNone(read_installed_version(self.roots.absent)[0])


class VersionParsing(unittest.TestCase):

    def test_three_dotted_integers_and_nothing_else(self):
        """The gate compares tuples, so a version must be exactly three
        dotted integers: a suffix, a leading zero, two parts or whitespace
        inside is not one."""
        self.assertEqual(parse_version("0.4.51"), (0, 4, 51))
        self.assertEqual(parse_version("10.0.0"), (10, 0, 0))
        for text in ("0.4", "0.4.51.1", "0.4.51-rc1", "v0.4.51", "00.4.51", " 0.4.51",
                     "0.4.51\n", "", "0.4.x", None):
            with self.subTest(text=text):
                self.assertIsNone(parse_version(text))

    def test_compared_as_tuples_never_as_strings(self):
        """0.4.100 is above the floor (0.4.54) and 0.4.9 below it, though a
        string comparison says the opposite of both."""
        self.assertGreater(parse_version("0.4.100"), parse_version(FLOOR))
        self.assertLess(parse_version("0.4.9"), parse_version(FLOOR))
        self.assertLess("0.4.100", FLOOR, "the string comparison the gate must not make")


def gate(manifest, root, run=run_process):
    """`twine bale check`'s verdict on `root`, through `run` (the real seam
    by default: the root's own bin/bale double answers)."""
    return check(manifest, resolve_root(str(root), {}, lambda n: None), run)


class TheManifestsBaleTable(unittest.TestCase):
    """`[bale]` is exactly floor, recordings and contract (session
    2026-10-15-twine-gate-contract-001); [bale.schemas] and `pin` are
    refused by name."""

    def setUp(self):
        self.manifest = load_manifest(CONSUMPTION_MANIFEST)
        self.text = CONSUMPTION_MANIFEST.read_text(encoding="utf-8")

    def test_the_three_keys_exactly(self):
        self.assertEqual(self.manifest.data["bale"],
                         {"floor": FLOOR, "recordings": RECORDINGS,
                          "contract": CONTRACT_RELPATH})
        self.assertEqual((self.manifest.floor, self.manifest.recordings,
                          self.manifest.contract), ("0.4.54", "0.4.51",
                                                    "fixtures/contract/bale-0.4.55.json"))
        self.assertFalse(hasattr(self.manifest, "pin"))
        self.assertFalse(hasattr(self.manifest, "schemas"))
        self.assertNotIn("[bale.schemas]\n", self.text)

    def test_the_contract_key_names_the_carried_line(self):
        data = (CONSUMPTION_MANIFEST.parent.parent / self.manifest.contract).read_bytes()
        self.assertEqual((len(data), hashlib.sha256(data).hexdigest()),
                         (CONTRACT_BYTES, CONTRACT_SHA256))
        self.assertEqual((CONTRACT_BYTES, CONTRACT_SHA256),
                         (8549, "bab19c6d19f31f56eba6b4e808e9e4950b15b8b4fbc8781295f1df93111e0334"))
        self.assertEqual(json.loads(data)["bale_version"], CONTRACT_VERSION)

    def refused(self, edited: str, says: str) -> None:
        self.assertNotEqual(edited, self.text)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.toml"
            path.write_text(edited, encoding="utf-8")
            with self.assertRaises(ManifestError) as caught:
                load_manifest(path)
        self.assertIn(says, str(caught.exception))

    def test_retired_and_unknown_keys_and_bad_values_refuse(self):
        """The retired keys are refused by name, never read: `pin` (the exact
        pin) and [bale.schemas] (the hashes); any other key is unknown; a
        floor or recordings that is not three dotted integers, or a contract
        that is not a .json path under fixtures/, refuses too."""
        floor = f'floor = "{FLOOR}"\n'
        cases = [
            (self.text.replace(floor, f'pin = "{FLOOR}"\n'), "[bale] `pin` retired"),
            (self.text.replace(floor, floor + 'pin = "0.4.51"\n'), "[bale] `pin` retired"),
            (self.text.replace(floor, f'floor = "0.4"\n'), "three dotted integers"),
            (self.text.replace(floor, ""), "floor must be"),
            (self.text.replace('recordings = "0.4.51"\n', ""), "recordings must be"),
            (self.text.replace('recordings = "0.4.51"', 'recordings = "0.4.51-rc1"'),
             "recordings must be"),
            (self.text.replace(f'contract = "{CONTRACT_RELPATH}"', 'contract = "/tmp/x.json"'),
             "contract must be"),
            (self.text.replace(f'contract = "{CONTRACT_RELPATH}"',
                               'contract = "fixtures/../share/x.json"'), "contract must be"),
            (self.text.replace(f'contract = "{CONTRACT_RELPATH}"\n', ""), "contract must be"),
            (self.text.replace(floor, floor + 'extra = "x"\n'), "its keys are exactly"),
            (self.text.replace(f'contract = "{CONTRACT_RELPATH}"\n',
                               f'contract = "{CONTRACT_RELPATH}"\n\n[bale.schemas]\n'
                               '"telemetry-record.schema.json" = "00"\n'),
             "[bale.schemas] retired when the gate became the floor plus bale's contract"),
        ]
        for edited, says in cases:
            with self.subTest(says=says, edited=edited[:0]):
                self.refused(edited, says)

    def test_a_reading_surface_without_contract_lines_refuses(self):
        """A verb surface that lists keys and names a reader must say which
        contract lines carry them, or the gate could not check them."""
        self.refused(self.text.replace('contract_lines = ["apply"]\n', ""),
                     "lists keys twine reads but no contract_lines")
        self.refused(self.text.replace('outcomes = ["opened", "second-desk", "rehearsed", '
                                       '"open-refused"]\n', ""),
                     "outcome_vocabulary and outcomes come together")
        self.refused(self.text.replace('contract_lines = ["apply"]', 'contract_lines = []'),
                     "contract_lines must be a non-empty list")

    def test_the_surfaces_name_the_lines_and_outcomes_the_brief_names(self):
        by_verb = {s["verb"]: s for s in self.manifest.surfaces if s.get("kind") == "verb"
                   and s.get("read_by") and s["verb"] != "contract"}
        self.assertEqual({v: tuple(s["contract_lines"]) for v, s in by_verb.items()},
                         READ_LINES)
        self.assertEqual({v: s.get("outcome_vocabulary") for v, s in by_verb.items()},
                         {"open": "open-outcome", "relay": "relay-outcome",
                          "unlock": "unlock-outcome", "apply": None})
        self.assertIn("cost-file", by_verb["unlock"]["reasons"])
        for vocabulary, dispatched in DISPATCHED_OUTCOMES.items():
            recorded = [s for s in by_verb.values()
                        if s.get("outcome_vocabulary") == vocabulary]
            self.assertEqual(len(recorded), 1, vocabulary)
            self.assertLessEqual(set(dispatched), set(recorded[0]["outcomes"]), vocabulary)


class TheCarriedLine(unittest.TestCase):
    """The carried line is what the brief says bale 0.4.55 prints, and states
    everything twine reads as the manifest records it — so the gate admits
    it with no note."""

    def setUp(self):
        self.manifest = load_manifest(CONSUMPTION_MANIFEST)
        self.line = json.loads(carried_contract())

    def test_six_top_level_keys_in_order(self):
        self.assertEqual(list(self.line), ["outcome", "bale_version", "vocabularies",
                                           "refusal_reasons", "json_keys", "json_key_homes"])
        self.assertEqual((self.line["outcome"], self.line["bale_version"]),
                         ("contract", CONTRACT_VERSION))
        self.assertEqual((len(self.line["vocabularies"]), len(self.line["json_keys"])),
                         (18, 18))
        self.assertTrue(carried_contract().endswith(b"}}\n"))
        self.assertEqual(carried_contract().count(b"\n"), 1)

    def test_its_three_table_vocabularies_are_the_oracle_s(self):
        for axis, values in BALE_VOCABULARIES.items():
            with self.subTest(axis=axis):
                self.assertEqual(self.line["vocabularies"][axis]["values"], values)
                self.assertEqual(self.manifest.vocabularies[axis]["values"], values)

    def test_the_findings_on_it_are_empty(self):
        self.assertEqual(contract_findings(self.manifest, self.line, CONTRACT_VERSION),
                         ([], [], []))

    def test_what_the_manifest_records_is_what_it_states(self):
        """Each recorded outcome set and reason set equals the line's, so a
        note means bale moved since 0.4.55, never a stale manifest."""
        for s in self.manifest.surfaces:
            if s.get("outcome_vocabulary"):
                self.assertEqual(s["outcomes"],
                                 self.line["vocabularies"][s["outcome_vocabulary"]]["values"])
            if s.get("reasons"):
                self.assertEqual(s["reasons"],
                                 self.line["refusal_reasons"][s["verb"]]["values"])

    def test_the_keys_twine_reads_are_on_every_line_it_reads(self):
        for s in self.manifest.surfaces:
            for name in s.get("contract_lines") or []:
                with self.subTest(line=name):
                    self.assertLessEqual(set(s["keys"]), set(self.line["json_keys"][name]))


class WhatTwineDispatchesOn(unittest.TestCase):
    """DISPATCHED_OUTCOMES and DISPATCHED_REASONS are the readers' own
    spellings, value for value: a reader cannot start dispatching on a
    spelling the gate does not hold an install to."""

    def test_the_open_outcomes_are_carry_bundles_and_inflights(self):
        self.assertEqual(set(DISPATCHED_OUTCOMES["open-outcome"]),
                         {*inflight.RECORDED_OUTCOMES, carry_bundle.REHEARSED,
                          carry_bundle.OPEN_REFUSED})

    def test_the_relay_outcomes_are_carry_exchanges(self):
        self.assertEqual(set(DISPATCHED_OUTCOMES["relay-outcome"]),
                         {carry_bale.RELAYED_OUTCOME, carry_bale.RE_EMITTED_OUTCOME,
                          carry_bale.RELAY_REFUSED_OUTCOME})

    def test_the_unlock_outcomes_and_the_one_reason_are_kills(self):
        self.assertEqual(set(DISPATCHED_OUTCOMES["unlock-outcome"]),
                         {kill.UNLOCKED_OUTCOME, kill.UNLOCK_REFUSED_OUTCOME})
        self.assertEqual(DISPATCHED_REASONS, {kill.READER: (kill.HOLD_BRANCH_REASON,)})
        self.assertEqual(kill.HOLD_BRANCH_REASON, "hold-branch")

    def test_the_gates_argv(self):
        self.assertEqual(contract_argv(Path("/r/bin/bale")),
                         ["/r/bin/bale", "contract", "--json"])


class TheGate(unittest.TestCase):

    def setUp(self):
        self.roots = TempRoots()
        self.addCleanup(self.roots.cleanup)
        self.manifest = load_manifest(CONSUMPTION_MANIFEST)
        self.tmp = tempfile.TemporaryDirectory(prefix="twine-gate-")
        self.addCleanup(self.tmp.cleanup)

    def result(self, root, run=run_process):
        return gate(self.manifest, root, run)

    def root_with(self, contract: bytes, *, version: str = CONTRACT_VERSION,
                  exit_code: int = 0, stderr: bytes = b"") -> Path:
        """A fresh root at `version` whose bin/bale double answers `contract`."""
        root = Path(tempfile.mkdtemp(dir=self.tmp.name))
        return make_root(root, version, contract=contract, contract_exit=exit_code,
                         contract_stderr=stderr)

    def test_the_manifest_carries_a_floor_and_no_pin(self):
        self.assertEqual(self.manifest.floor, FLOOR)
        self.assertNotIn("pin", self.manifest.data["bale"])
        self.assertNotIn("schemas", self.manifest.data["bale"])

    def test_at_the_floor_above_and_far_above_are_admitted(self):
        for root, installed in ((self.roots.ok, CONTRACT_VERSION),
                                (self.roots.at_floor, FLOOR), (self.roots.above, ABOVE),
                                (self.roots.far_above, TempRoots.FAR_ABOVE)):
            with self.subTest(installed=installed):
                result = self.result(root)
                self.assertEqual((result.ok, result.installed, result.root, result.floor),
                                 (True, installed, root, FLOOR))
                self.assertTrue(result.floor_admits)
                self.assertTrue(result.contract.ok)
                self.assertEqual((result.contract.bale_version, result.contract.problems,
                                  result.contract.notes), (installed, (), ()))
                self.assertEqual(result.contract.sha256,
                                 hashlib.sha256(contract_line(installed)).hexdigest())
                self.assertEqual(result.reason,
                                 f"installed {installed} is at or above the floor {FLOOR}, "
                                 "and its contract (bale contract --json) states "
                                 "everything twine reads")

    def test_the_carried_line_is_replayed_byte_exact_at_its_version(self):
        result = self.result(self.roots.ok)
        self.assertEqual(result.contract.sha256, CONTRACT_SHA256)

    def test_the_contract_runs_through_the_seam_once(self):
        """`<root>/bin/bale contract --json`, the resolved root's own
        executable, through `run`, stdin closed, with the timeout and cap."""
        seen = []

        def run(argv, **kwargs):
            seen.append((list(argv), kwargs))
            return run_process(argv, **kwargs)
        self.assertTrue(self.result(self.roots.ok, run).ok)
        self.assertEqual(len(seen), 1)
        argv, kwargs = seen[0]
        self.assertEqual(argv, [str(self.roots.ok / "bin" / "bale"), "contract", "--json"])
        self.assertEqual((kwargs["stdin"], kwargs["timeout"], kwargs["stdout_cap"]),
                         (None, CONTRACT_TIMEOUT_SECONDS, CONTRACT_STDOUT_CAP_BYTES))
        runner = RecordingRunner()
        self.assertTrue(self.result(self.roots.ok, runner).ok)
        self.assertEqual((runner.calls, len(runner.gate_calls)), ([], 1))

    def test_schemas_absent_or_altered_are_admitted(self):
        """The gate reads no file under <root>/schemas/: an install with none,
        with one altered, with a ninth, or with `schemas` not a directory at
        all is admitted on its contract."""
        stray = make_root(Path(self.tmp.name) / "stray", CONTRACT_VERSION)
        (stray / "schemas").write_text("not a directory\n", encoding="utf-8")
        ninth = make_root(Path(self.tmp.name) / "ninth", CONTRACT_VERSION, schemas=True)
        (ninth / "schemas" / "new-record.schema.json").write_text("{}\n")
        for root in (self.roots.no_schemas, self.roots.bad_schema, stray, ninth):
            with self.subTest(root=root.name):
                self.assertFalse((root / "schemas").is_dir() and root.name == "no-schemas")
                result = self.result(root)
                self.assertTrue(result.ok, result.reason)
                self.assertNotIn("schema", result.reason)
        self.assertTrue((self.roots.bad_schema / "schemas" / TempRoots.ALTERED_SCHEMA).is_file())

    def test_below_the_floor_is_refused_naming_the_floor_and_never_asked(self):
        for root, installed in ((self.roots.below, TempRoots.BELOW),
                                (self.roots.other, self.roots.other_version)):
            with self.subTest(installed=installed):
                runner = RecordingRunner()
                result = self.result(root, runner)
                self.assertFalse(result.ok)
                self.assertIs(result.floor_admits, False)
                self.assertEqual((runner.calls, runner.gate_calls), ([], []))
                self.assertFalse(result.contract.ok)
                self.assertFalse(result.contract.asked)
                self.assertEqual(result.reason,
                                 f"installed {installed} is below the floor {FLOOR}; bale "
                                 f"contract --json was not run (no bale below the floor "
                                 f"{FLOOR} has it)")
                self.assertEqual(result.as_json()["contract"]["bale_version"], None)

    def test_an_unparsable_or_unreadable_version_is_refused(self):
        result = self.result(self.roots.unparsable)
        self.assertFalse(result.ok)
        self.assertIsNone(result.floor_admits)
        self.assertEqual(result.installed, TempRoots.UNPARSABLE)
        self.assertIn("not a version of three dotted integers", result.reason)
        self.assertIn(repr(TempRoots.UNPARSABLE), result.reason)
        self.assertIn(f"bale_version {CONTRACT_VERSION} disagrees with bin/VERSION",
                      result.reason)
        (self.roots.ok / "bin" / "VERSION").unlink()
        result = self.result(self.roots.ok)
        self.assertFalse(result.ok)
        self.assertIsNone(result.installed)
        self.assertIn("unreadable", result.reason)
        self.assertIn("cannot be held to bin/VERSION, which did not read", result.reason)

    def refused(self, root: Path, *says: str, moved: bool = True):
        result = self.result(root)
        self.assertFalse(result.ok)
        self.assertTrue(result.floor_admits)
        for needle in says:
            self.assertIn(needle, result.reason)
        self.assertEqual(bool(result.contract.moved), moved, result.contract)
        self.assertEqual(result.reason, "; ".join(result.contract.problems))
        return result

    def test_a_key_twine_reads_missing_from_a_line_it_reads_refuses_naming_both(self):
        manifest_keys = {s["verb"]: s["keys"] for s in self.manifest.surfaces
                         if s.get("contract_lines")}
        for verb, lines in READ_LINES.items():
            for line in lines:
                for key in manifest_keys[verb]:
                    with self.subTest(line=line, key=key):
                        root = self.root_with(edited_contract(drop_contract_key(line, key)))
                        self.refused(root, f"the contract's {line} line lacks the key "
                                           f"{key!r}, which twine reads (the {verb} surface)")

    def test_a_key_twine_does_not_read_is_free(self):
        root = self.root_with(edited_contract(drop_contract_key("open", "log")))
        self.assertTrue(self.result(root).ok)
        root = self.root_with(edited_contract(drop_contract_key("status", "clipboard")))
        self.assertTrue(self.result(root).ok)

    def test_a_line_twine_reads_missing_from_json_keys_refuses(self):
        def edit(obj):
            del obj["json_keys"]["relay-refused"]
        root = self.root_with(edited_contract(edit))
        self.refused(root, "the contract states no keys for bale's relay-refused line, "
                           "which twine reads (the relay surface)")

    def test_a_table_vocabulary_value_added_or_removed_refuses_naming_axis_and_value(self):
        for axis, values in BALE_VOCABULARIES.items():
            with self.subTest(axis=axis, change="added"):
                root = self.root_with(edited_contract(add_vocabulary_value(
                    axis, NOT_A_BALE_OUTCOME)))
                self.refused(root, f"the contract's {axis} vocabulary adds "
                                   f"{NOT_A_BALE_OUTCOME!r}", "(D17)")
            with self.subTest(axis=axis, change="removed"):
                root = self.root_with(edited_contract(drop_vocabulary_value(axis, values[-1])))
                self.refused(root, f"the contract's {axis} vocabulary no longer lists "
                                   f"{values[-1]!r}")
        self.refused(self.roots.adds_outcome, "telemetry-outcome vocabulary adds")

    def test_a_table_vocabulary_missing_refuses(self):
        def edit(obj):
            del obj["vocabularies"]["closure-reason"]
        self.refused(self.root_with(edited_contract(edit)),
                     "the contract states no closure-reason vocabulary, which the "
                     "transition table keys on")

    def test_an_empty_section_states_nothing_and_every_reading_refuses(self):
        """An empty `vocabularies`, `json_keys` or `refusal_reasons` object is
        read, not skipped: everything twine reads from it is named missing.
        A section that is not an object at all is one shape problem."""
        def emptied(section):
            def edit(obj):
                obj[section] = {}
            return edit
        result = self.refused(self.root_with(edited_contract(emptied("vocabularies"))),
                              "the contract states no telemetry-outcome vocabulary",
                              "the contract states no open-outcome vocabulary")
        self.assertEqual(len(result.contract.problems), 6)
        result = self.refused(self.root_with(edited_contract(emptied("json_keys"))),
                              "the contract states no keys for bale's apply line")
        self.assertEqual(len(result.contract.problems), 8)
        self.refused(self.root_with(edited_contract(emptied("refusal_reasons"))),
                     "the contract states no unlock refusal reasons, and twine dispatches "
                     "on 'hold-branch'")

        def dropped(obj):
            obj["json_keys"] = ["not", "an", "object"]
        result = self.refused(self.root_with(edited_contract(dropped)),
                              "bale contract --json's line has no `json_keys` object",
                              moved=False)
        self.assertEqual(len(result.contract.problems), 1)

    def test_a_dispatched_outcome_missing_refuses_naming_it(self):
        for vocabulary, dispatched in DISPATCHED_OUTCOMES.items():
            for value in dispatched:
                with self.subTest(vocabulary=vocabulary, value=value):
                    root = self.root_with(edited_contract(drop_vocabulary_value(
                        vocabulary, value)))
                    self.refused(root, f"the contract's {vocabulary} vocabulary lacks "
                                       f"{value!r}, an outcome twine dispatches on")

    def test_an_outcome_vocabulary_twine_dispatches_on_missing_refuses(self):
        def edit(obj):
            del obj["vocabularies"]["unlock-outcome"]
        self.refused(self.root_with(edited_contract(edit)),
                     "the contract states no unlock-outcome vocabulary, which twine "
                     "dispatches on (the unlock surface)")

    def test_hold_branch_missing_refuses_naming_it(self):
        self.refused(self.roots.lacks_hold_branch,
                     "the contract's unlock refusal reasons lack 'hold-branch', a reason "
                     "twine dispatches on")

        def edit(obj):
            del obj["refusal_reasons"]["unlock"]
        self.refused(self.root_with(edited_contract(edit)),
                     "the contract states no unlock refusal reasons, and twine dispatches "
                     "on 'hold-branch'")

    def test_additions_twine_does_not_dispatch_on_are_reported_never_refused(self):
        """A value added to open-outcome, relay-outcome, unlock-outcome or a
        refusal-reason set twine records is a note; so is a recorded value
        twine does not dispatch on that the contract dropped."""
        cases = [
            (add_vocabulary_value("open-outcome", "opened-twice"),
             "the contract's open-outcome vocabulary adds 'opened-twice', which the "
             "consumption manifest does not record (reported, not refused: twine does "
             "not dispatch on it)"),
            (add_vocabulary_value("relay-outcome", "relayed-later"),
             "the contract's relay-outcome vocabulary adds 'relayed-later'"),
            (add_vocabulary_value("unlock-outcome", "unlocked-twice"),
             "the contract's unlock-outcome vocabulary adds 'unlocked-twice'"),
            (add_refusal_reason("unlock", "lock-busy"),
             "the contract's unlock refusal reasons add 'lock-busy'"),
            (add_refusal_reason("relay", "relay-busy"),
             "the contract's relay refusal reasons add 'relay-busy'"),
            (drop_vocabulary_value("unlock-outcome", "no-op"),
             "the contract's unlock-outcome vocabulary no longer lists 'no-op', which the "
             "consumption manifest records (reported, not refused: twine does not "
             "dispatch on it)"),
            (drop_refusal_reason("relay", "no-git"),
             "the contract's relay refusal reasons no longer list 'no-git'"),
            (add_vocabulary_value("revert-outcome", "reverted-twice"), None),
            (add_refusal_reason("open", "open-busy"), None),
        ]
        for edit, note in cases:
            with self.subTest(note=note):
                result = self.result(self.root_with(edited_contract(edit)))
                self.assertTrue(result.ok, result.reason)
                if note is None:
                    self.assertEqual(result.contract.notes, ())
                    continue
                self.assertEqual(len(result.contract.notes), 1)
                self.assertIn(note, result.contract.notes[0])
                self.assertIn("1 addition reported, none refused", result.reason)
                self.assertEqual(result.as_json()["contract"]["notes"],
                                 list(result.contract.notes))

    def test_a_bale_version_that_disagrees_refuses(self):
        result = self.refused(self.roots.disagrees,
                              f"the contract's bale_version {ABOVE} disagrees with "
                              f"bin/VERSION, which reads {CONTRACT_VERSION}", moved=False)
        self.assertEqual(result.contract.bale_version, ABOVE)

    def test_an_outcome_that_is_not_contract_refuses(self):
        def edit(obj):
            obj["outcome"] = "status"
        self.refused(self.root_with(edited_contract(edit)),
                     "bale contract --json's line has outcome 'status', not 'contract'",
                     moved=False)

    def test_a_line_that_cannot_be_read_refuses_naming_why(self):
        carried = carried_contract()
        cases = [
            (dict(contract=carried, exit_code=2, stderr=b"usage: bale ...\nunknown verb\n"),
             "bale contract --json exited 2 (stderr: 'usage: bale ...\\nunknown verb')",
             CONTRACT_SHA256),
            (dict(contract=b"", exit_code=1), "bale contract --json exited 1 with nothing on "
                                              "stderr", None),
            (dict(contract=carried + carried), "bale contract --json printed 2 lines, not one",
             hashlib.sha256(carried + carried).hexdigest()),
            (dict(contract=carried + b"\n"), "printed 2 lines, not one", None),
            (dict(contract=b"not json\n"), "bale contract --json's line is not JSON", None),
            (dict(contract=b"[1, 2]\n"), "is JSON but not an object (a list)", None),
            (dict(contract=b""), "bale contract --json printed nothing", None),
            (dict(contract=b"\xff\xfe\n"), "printed bytes that are not UTF-8", None),
        ]
        for kwargs, says, digest in cases:
            with self.subTest(says=says):
                result = self.refused(self.root_with(**kwargs), says, moved=False)
                obj = result.as_json()["contract"]
                self.assertEqual((obj["ok"], obj["bale_version"]), (False, None))
                stdout = kwargs["contract"]
                self.assertEqual(obj["sha256"],
                                 hashlib.sha256(stdout).hexdigest() if stdout else None)
                if digest is not None:
                    self.assertEqual(obj["sha256"], digest)

    def test_a_line_without_its_final_newline_is_still_one_line(self):
        root = self.root_with(carried_contract()[:-1])
        self.assertTrue(self.result(root).ok)

    def test_a_killed_or_unstartable_run_refuses(self):
        def killed(**flags):
            def run(argv, **kwargs):
                return RunResult(argv=tuple(argv), exit_code=None, stdout=b"",
                                 stderr=b"", **flags)
            return run
        result = self.result(self.roots.ok, killed(timed_out=True))
        self.assertIn(f"killed after {CONTRACT_TIMEOUT_SECONDS:g}s", result.reason)
        result = self.result(self.roots.ok, killed(stdout_capped=True))
        self.assertIn(f"more than {CONTRACT_STDOUT_CAP_BYTES} bytes", result.reason)
        root = make_root(Path(self.tmp.name) / "no-exe", CONTRACT_VERSION, executable=False)
        result = self.result(root)
        self.assertFalse(result.ok)
        self.assertTrue(result.floor_admits)
        self.assertIn("bale contract --json could not be started", result.reason)
        self.assertIsNone(result.as_json()["contract"]["sha256"])

    def test_every_failing_fact_is_named_at_once(self):
        """An unparsable version, a key gone from a line twine reads, a
        telemetry outcome added and hold-branch removed: one reason, every
        sentence, none hiding the others."""
        def edit(obj):
            drop_contract_key("unlock", "closure_reason")(obj)
            add_vocabulary_value("telemetry-outcome", NOT_A_BALE_OUTCOME)(obj)
            drop_refusal_reason("unlock", "hold-branch")(obj)
        root = self.root_with(edited_contract(edit), version=TempRoots.UNPARSABLE)
        result = self.result(root)
        self.assertFalse(result.ok)
        parts = result.reason.split("; ")
        self.assertEqual(len(parts), 5, parts)
        self.assertIn("which is not a version of three dotted integers", parts[0])
        self.assertIn("disagrees with bin/VERSION", parts[1])
        self.assertIn("telemetry-outcome vocabulary adds", parts[2])
        self.assertIn("unlock line lacks the key 'closure_reason'", parts[3])
        self.assertIn("lack 'hold-branch'", parts[4])
        self.assertEqual(len(result.contract.moved), 3)

    def test_no_install(self):
        result = check(self.manifest, resolve_root(None, {}, lambda n: None), run_process)
        self.assertEqual((result.ok, result.installed, result.root, result.contract),
                         (False, None, None, None))
        absent = self.result(self.roots.absent)
        self.assertFalse(absent.ok)
        self.assertIn("unreadable", absent.reason)
        self.assertIn("bale contract --json could not be started", absent.reason)

    def test_json_shape(self):
        """The keys, in order: floor, installed, root, source, contract, ok,
        reason — no `pin`, no `schemas`. `contract` is exactly ok,
        bale_version, sha256, problems, notes; null only when no install was
        found."""
        obj = self.result(self.roots.ok).as_json()
        self.assertEqual(list(obj), ["floor", "installed", "root", "source", "contract",
                                     "ok", "reason"])
        self.assertEqual(obj["contract"], {"ok": True, "bale_version": CONTRACT_VERSION,
                                           "sha256": CONTRACT_SHA256, "problems": [],
                                           "notes": []})
        self.assertEqual(list(obj["contract"]),
                         ["ok", "bale_version", "sha256", "problems", "notes"])
        bad = self.result(self.roots.lacks_key).as_json()["contract"]
        self.assertEqual((bad["ok"], bad["bale_version"], len(bad["problems"])),
                         (False, CONTRACT_VERSION, 1))
        none = check(self.manifest, resolve_root(None, {}, lambda n: None),
                     run_process).as_json()
        self.assertIsNone(none["contract"])

    def test_parse_contract_stdout(self):
        self.assertEqual(parse_contract_stdout(b'{"a": 1}\n'), ({"a": 1}, None))
        self.assertEqual(parse_contract_stdout(b'{"a": 1}'), ({"a": 1}, None))
        self.assertIsNone(parse_contract_stdout(b'{"a": 1}\n{"a": 1}\n')[0])
        self.assertIsNone(parse_contract_stdout(b"")[0])


class TheRefusalText(unittest.TestCase):
    """drive_refusal: a contract that read cleanly with something twine reads
    moved says bale changed it and a recording session lands the new
    spelling; any other failure says which bale twine drives. Neither says
    to raise the floor."""

    def setUp(self):
        self.roots = TempRoots()
        self.addCleanup(self.roots.cleanup)

    def refusal(self, root) -> str:
        exe = bale.locate_executable(str(root), {}, lambda n: None, run_process)
        return exe.drive_refusal

    def test_something_moved(self):
        text = self.refusal(self.roots.lacks_key)
        self.assertIn("the contract's open-refused line lacks the key 'desk'", text)
        self.assertIn("bale changed something twine reads", text)
        self.assertIn("a recording session lands the new spelling", text)
        self.assertNotIn("raise the floor", text)
        self.assertNotIn("twine drives only a bale at or above", text)

    def test_below_the_floor_or_a_line_that_is_not_this_installs(self):
        for root in (self.roots.below, self.roots.disagrees, self.roots.absent):
            with self.subTest(root=root.name):
                text = self.refusal(root)
                self.assertIn(f"twine drives only a bale at or above the floor {FLOOR} "
                              "whose contract (bale contract --json) states everything "
                              "twine reads", text)
                self.assertNotIn("bale changed something", text)
                self.assertNotIn("raise the floor", text)

    def test_admitted_is_none_and_the_twin_carries_contract_ok(self):
        exe = bale.locate_executable(str(self.roots.ok), {}, lambda n: None, run_process)
        self.assertIsNone(exe.drive_refusal)
        self.assertEqual(exe.as_json()["contract_ok"], True)
        self.assertNotIn("schemas_match", exe.as_json())
        exe = bale.locate_executable(str(self.roots.lacks_key), {}, lambda n: None,
                                     run_process)
        self.assertEqual((exe.as_json()["contract_ok"], exe.as_json()["floor_admits"]),
                         (False, True))


class CheckViaCli(unittest.TestCase):
    """`bin/twine bale check --json` end to end against the roots."""

    def setUp(self):
        self.roots = TempRoots()
        self.addCleanup(self.roots.cleanup)

    def test_subprocess_the_matrix(self):
        expect = {"ok": (0, True, CONTRACT_VERSION, None),
                  "at_floor": (0, True, FLOOR, None), "above": (0, True, ABOVE, None),
                  "far_above": (0, True, TempRoots.FAR_ABOVE, None),
                  "bad_schema": (0, True, CONTRACT_VERSION, None),
                  "no_schemas": (0, True, CONTRACT_VERSION, None),
                  "below": (1, False, TempRoots.BELOW, f"below the floor {FLOOR}"),
                  "other": (1, False, self.roots.other_version, f"below the floor {FLOOR}"),
                  "unparsable": (1, False, TempRoots.UNPARSABLE, "three dotted integers"),
                  "absent": (1, False, None, "unreadable"),
                  "lacks_key": (1, False, CONTRACT_VERSION, "lacks the key 'desk'"),
                  "adds_outcome": (1, False, CONTRACT_VERSION, NOT_A_BALE_OUTCOME),
                  "lacks_hold_branch": (1, False, CONTRACT_VERSION, "'hold-branch'"),
                  "disagrees": (1, False, CONTRACT_VERSION, "disagrees with bin/VERSION")}
        for name, (code, ok, installed, says) in expect.items():
            with self.subTest(root=name):
                run = run_cli("bale", "check", "--json", "--bale-root",
                              str(getattr(self.roots, name)))
                obj = json.loads(run.stdout)
                self.assertEqual((run.code, obj["ok"], obj["installed"], obj["floor"]),
                                 (code, ok, installed, FLOOR))
                # The dispatcher's two keys, then the check's, in its order.
                self.assertEqual(list(obj), ["command", "ok", "floor", "installed", "root",
                                             "source", "contract", "reason"])
                self.assertNotIn("pin", obj)
                self.assertNotIn("schemas", obj)
                self.assertEqual(obj["root"], str(getattr(self.roots, name)))
                self.assertEqual(obj["contract"]["ok"], ok if name not in (
                    "below", "other", "unparsable", "absent") else False)
                if says is not None:
                    self.assertIn(says, obj["reason"])
                self.assertNotIn("Traceback", run.stderr)

    def test_env_variable_resolves(self):
        run = run_cli("bale", "check", "--json", bale_root=self.roots.ok)
        obj = json.loads(run.stdout)
        self.assertEqual((run.code, obj["ok"], obj["source"]), (0, True, ENV_ROOT))

    def test_human_rendering_names_the_floor_and_the_contract_verdict(self):
        run = run_inprocess("bale", "check", "--bale-root", str(self.roots.other))
        self.assertEqual(run.code, 1)
        self.assertIn(f"floor:     {FLOOR}", run.stdout)
        self.assertIn(self.roots.other_version, run.stdout)
        self.assertIn("contract:  NOT OK — bale contract --json was not run", run.stdout)
        self.assertIn("FAIL", run.stdout)
        self.assertNotIn("pin:", run.stdout)
        self.assertNotIn("schemas:", run.stdout)
        bad = run_inprocess("bale", "check", "--bale-root", str(self.roots.lacks_key))
        self.assertEqual(bad.code, 1)
        self.assertIn("contract:  NOT OK — the contract's open-refused line lacks the key "
                      "'desk'", bad.stdout)
        good = run_inprocess("bale", "check", "--bale-root", str(self.roots.ok))
        self.assertEqual(good.code, 0)
        self.assertIn(f"contract:  ok — bale {CONTRACT_VERSION}'s line (sha256 "
                      f"{CONTRACT_SHA256}) states everything twine reads", good.stdout)
        self.assertIn("check:     ok", good.stdout)

    def test_a_reported_addition_is_a_note_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp) / "r", CONTRACT_VERSION, contract=edited_contract(
                add_refusal_reason("unlock", "lock-busy")))
            run = run_inprocess("bale", "check", "--bale-root", str(root))
        self.assertEqual(run.code, 0)
        self.assertIn("note:      the contract's unlock refusal reasons add 'lock-busy'",
                      run.stdout)


if __name__ == "__main__":
    unittest.main()

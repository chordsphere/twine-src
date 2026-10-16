"""`twine sandbox prune` and twine/prune.py (twine-sandbox-confine;
claude/context/cli-contract.md §22, runtime-contract.md §7.7): the homes of
sessions bale records as applied are removed, every other home is kept with
why, and nothing outside `<state-dir>/sandbox/<sid>/` is touched.

The records are written by the test, in the shape bale's telemetry record has
(`attempts[].outcome` is the only key twine reads, so it is the only one the
records carry beyond what makes them records). No bale, no process, no network.

Sections:
  1. The bed
  2. The rule
  3. The verb: what is removed, what is kept
  4. The JSON twin and human mode
  5. Refusals and failures
  6. Safety
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from twine import prune
from twine.cli import Context, main
from twine.registry import load_registry

from tests.helpers import run_cli, run_inprocess

# ---------------------------------------------------------------------------
# 1. The bed
# ---------------------------------------------------------------------------

APPLIED = "2026-10-10-twine-applied-001"
HELD = "2026-10-10-twine-held-002"
ROLLED_BACK = "2026-10-10-twine-rolled-back-003"
IN_FLIGHT = "2026-10-10-twine-inflight-004"
NO_RECORD = "2026-10-10-twine-norecord-005"
RUNNING = "2026-10-10-twine-running-006"
RE_APPLIED = "2026-10-10-twine-reapplied-007"
REVERTED = "2026-10-10-twine-reverted-008"
CLOSED_AFTER = "2026-10-10-twine-closed-009"

TWIN_KEYS = ["command", "ok", "dry_run", "state_dir", "cwd", "pruned", "kept",
             "freed_bytes", "reason"]


class Bed:
    """A state directory with homes, and a repository whose bale.toml names an
    `agent_dir` of its own, holding bale's records for some of them."""

    AGENT_DIR = "agentdir"

    def __init__(self, test: unittest.TestCase, agent_dir: str | None = AGENT_DIR) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="twine-prune-")
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.state = self.root / "state"
        self.repo = self.root / "repo"
        self.state.mkdir()
        self.repo.mkdir()
        self.agent_dir = agent_dir
        if agent_dir is not None:
            (self.repo / "bale.toml").write_text(
                f'[validation]\nbase = "x"\n\n[layout]\nagent_dir = "{agent_dir}"\n',
                encoding="utf-8")
        self.sizes: dict[str, int] = {}

    def home(self, sid: str, size: int = 100) -> Path:
        """A kept home: `<state>/sandbox/<sid>/home/` with `size` bytes in a
        file and one in a nested directory, and the cage's empty `root/`."""
        base = self.state / "sandbox" / sid
        (base / "home" / "sub").mkdir(parents=True)
        (base / "root").mkdir()
        (base / "home" / "work.bin").write_bytes(b"x" * size)
        (base / "home" / "sub" / "more.txt").write_bytes(b"y" * 7)
        self.sizes[sid] = size + 7
        return base

    def record(self, sid: str, *outcomes: str) -> Path:
        """bale's record for `sid`: attempts with these outcomes in order, and
        the other keys a record has (twine reads none of them)."""
        path = (self.repo / (self.agent_dir or "claude") / "telemetry" / f"{sid}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "record_version": 1, "session_id": sid, "outcome": outcomes[-1],
            "attempts": [{"at": "2026-10-10T00:00:00+00:00", "command": "apply",
                          "outcome": o, "tarball": "not-read.tar.gz"} for o in outcomes]}),
            encoding="utf-8")
        return path

    def inflight(self, sid: str) -> None:
        (self.state / "inflight").mkdir(exist_ok=True)
        (self.state / "inflight" / f"{sid}.json").write_text("{}\n", encoding="utf-8")

    def running(self, sid: str) -> None:
        (self.state / "running").mkdir(exist_ok=True)
        (self.state / "running" / f"{sid}.json").write_text("{}\n", encoding="utf-8")

    def sids(self) -> list[str]:
        return sorted(p.name for p in (self.state / "sandbox").iterdir())

    def argv(self, *extra: str) -> list[str]:
        return ["sandbox", "prune", "--state-dir", str(self.state), "--cwd", str(self.repo),
                *extra]

    def twin(self, *extra: str) -> dict:
        run = run_cli(*self.argv(*extra, "--json"))
        lines = run.stdout.split("\n")
        assert len(lines) == 2 and lines[1] == "", run.stdout + run.stderr
        obj = json.loads(lines[0])
        assert run.code == (0 if obj["ok"] else 1), (run.code, run.stderr)
        assert "Traceback" not in run.stderr, run.stderr
        return obj

    def full(self) -> "Bed":
        """The five homes of the brief — applied, held, applied then rolled
        back, applied but still in flight, no record — and the rest."""
        for sid in (APPLIED, HELD, ROLLED_BACK, IN_FLIGHT, NO_RECORD):
            self.home(sid)
        self.record(APPLIED, "opened", "applied")
        self.record(HELD, "opened", "held")
        self.record(ROLLED_BACK, "opened", "applied", "rolled-back")
        self.record(IN_FLIGHT, "opened", "applied")
        self.inflight(IN_FLIGHT)
        return self


# ---------------------------------------------------------------------------
# 2. The rule
# ---------------------------------------------------------------------------


class TheRule(unittest.TestCase):

    def verdict(self, *outcomes: str) -> tuple[bool, str]:
        return prune.applied_verdict(list(outcomes))

    def test_applied_exactly_when_the_last_merge_outcome_is_applied_or_re_applied(self):
        self.assertEqual(self.verdict("opened", "applied"), (True, "applied"))
        self.assertEqual(self.verdict("applied", "re-applied"), (True, "re-applied"))
        self.assertEqual(self.verdict("applied", "rolled-back", "re-applied"),
                         (True, "re-applied"))
        self.assertEqual(self.verdict("applied", "rolled-back"), (False, "rolled-back"))
        self.assertEqual(self.verdict("applied", "reverted"), (False, "reverted"))
        self.assertEqual(self.verdict("applied", "rolled-back", "re-applied", "reverted"),
                         (False, "reverted"))

    def test_a_close_after_the_apply_does_not_hide_it(self):
        for later in ("unlocked", "relay-refused", "rejected", "bailout", "held"):
            with self.subTest(later=later):
                self.assertEqual(self.verdict("opened", "applied", later), (True, "applied"))

    def test_without_a_merge_outcome_the_last_outcome_of_any_kind_is_named(self):
        self.assertEqual(self.verdict("opened", "held"), (False, "held"))
        self.assertEqual(self.verdict("opened"), (False, "opened"))
        self.assertEqual(self.verdict("held", "scope-drift-refused"),
                         (False, "scope-drift-refused"))
        self.assertEqual(self.verdict(), (False, "none"))

    def test_the_agent_dir_is_the_repositorys_or_claude(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            self.assertEqual(prune.agent_dir(cwd), "claude", "no bale.toml")
            (cwd / "bale.toml").write_text("[sandbox]\nenabled = true\n")
            self.assertEqual(prune.agent_dir(cwd), "claude", "no [layout]")
            (cwd / "bale.toml").write_text("[layout]\nsomething = 1\n")
            self.assertEqual(prune.agent_dir(cwd), "claude", "no agent_dir")
            (cwd / "bale.toml").write_text('[layout]\nagent_dir = ".agent"\n')
            self.assertEqual(prune.agent_dir(cwd), ".agent")
            for bad in ("[layout\n", "layout = 3\n", "[layout]\nagent_dir = 3\n",
                        '[layout]\nagent_dir = " "\n'):
                with self.subTest(bad=bad):
                    (cwd / "bale.toml").write_text(bad)
                    with self.assertRaises(prune.RecordError):
                        prune.agent_dir(cwd)

    def test_only_attempt_outcomes_are_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text(json.dumps({"outcome": "held", "closure": {"category": "x"},
                                        "attempts": [{"outcome": "applied", "junk": [1]}]}))
            self.assertEqual(prune.attempt_outcomes(path), ["applied"],
                             "the envelope's own `outcome` is not read")
            self.assertIsNone(prune.attempt_outcomes(Path(tmp) / "absent.json"))
            for bad in ("{", "[]", '{"attempts": 3}', '{"attempts": [3]}',
                        '{"attempts": [{"outcome": 3}]}', '{"attempts": [{}]}'):
                with self.subTest(bad=bad):
                    path.write_text(bad)
                    with self.assertRaises(prune.RecordError):
                        prune.attempt_outcomes(path)


# ---------------------------------------------------------------------------
# 3. The verb: what is removed, what is kept
# ---------------------------------------------------------------------------


class TheVerb(unittest.TestCase):

    def test_the_brief_s_five_homes(self):
        bed = Bed(self).full()
        before = bed.sids()
        dry = bed.twin("--dry-run")
        self.assertEqual(bed.sids(), before, "--dry-run removes nothing")
        self.assertEqual(dry["pruned"], [APPLIED])
        whys = {row["sid"]: row["why"] for row in dry["kept"]}
        self.assertEqual(whys, {HELD: "not applied (last: held)",
                                ROLLED_BACK: "not applied (last: rolled-back)",
                                IN_FLIGHT: "in flight",
                                NO_RECORD: "no bale record"})
        self.assertEqual([row["sid"] for row in dry["kept"]], sorted(whys), "sorted by sid")
        self.assertEqual(dry["freed_bytes"], bed.sizes[APPLIED])
        real = bed.twin()
        self.assertEqual(bed.sids(), sorted({HELD, ROLLED_BACK, IN_FLIGHT, NO_RECORD}))
        self.assertEqual({k: v for k, v in real.items() if k != "dry_run"},
                         {k: v for k, v in dry.items() if k != "dry_run"})
        self.assertEqual((dry["dry_run"], real["dry_run"]), (True, False))
        self.assertFalse((bed.state / "sandbox" / APPLIED).exists(), "root/ went with it")
        again = bed.twin()
        self.assertEqual((again["pruned"], again["freed_bytes"]), ([], 0))

    def test_every_way_a_session_ends_in_the_merge_standing_or_not(self):
        bed = Bed(self)
        cases = {RE_APPLIED: ("opened", "applied", "rolled-back", "re-applied"),
                 REVERTED: ("opened", "applied", "reverted"),
                 CLOSED_AFTER: ("opened", "applied", "unlocked")}
        for sid, outcomes in cases.items():
            bed.home(sid)
            bed.record(sid, *outcomes)
        twin = bed.twin()
        self.assertEqual(twin["pruned"], sorted([RE_APPLIED, CLOSED_AFTER]))
        self.assertEqual(twin["kept"], [{"sid": REVERTED,
                                         "why": "not applied (last: reverted)"}])

    def test_a_running_record_keeps_the_home_whatever_bale_says(self):
        bed = Bed(self)
        bed.home(RUNNING)
        bed.record(RUNNING, "opened", "applied")
        bed.running(RUNNING)
        twin = bed.twin()
        self.assertEqual((twin["pruned"], twin["kept"]),
                         ([], [{"sid": RUNNING, "why": "running"}]))
        self.assertTrue((bed.state / "sandbox" / RUNNING / "home").is_dir())

    def test_an_in_flight_record_that_is_not_json_still_keeps_it(self):
        bed = Bed(self)
        bed.home(IN_FLIGHT)
        bed.record(IN_FLIGHT, "applied")
        (bed.state / "inflight").mkdir()
        (bed.state / "inflight" / f"{IN_FLIGHT}.json").write_text("{not json")
        self.assertEqual(bed.twin()["kept"], [{"sid": IN_FLIGHT, "why": "in flight"}])

    def test_a_record_that_cannot_be_read_keeps_the_home_and_says_why(self):
        bed = Bed(self)
        bed.home(APPLIED)
        bed.home(HELD)
        bed.record(APPLIED, "applied").write_text("{broken", encoding="utf-8")
        bed.record(HELD, "applied").write_text('{"attempts": "no"}', encoding="utf-8")
        twin = bed.twin()
        self.assertEqual(twin["pruned"], [])
        for row in twin["kept"]:
            self.assertTrue(row["why"].startswith("the record cannot be read: "), row)
        self.assertIn("is not JSON", twin["kept"][0]["why"])
        self.assertIn("no attempts[] list", twin["kept"][1]["why"])
        self.assertTrue(twin["ok"])

    def test_a_bale_toml_that_cannot_be_read_keeps_every_home(self):
        bed = Bed(self)
        bed.home(APPLIED)
        bed.record(APPLIED, "applied")
        (bed.repo / "bale.toml").write_text("[layout\n", encoding="utf-8")
        twin = bed.twin()
        self.assertEqual(twin["pruned"], [])
        self.assertIn("the record cannot be read: ", twin["kept"][0]["why"])
        self.assertIn("bale.toml", twin["kept"][0]["why"])

    def test_the_default_agent_dir_is_claude(self):
        bed = Bed(self, agent_dir=None)
        bed.home(APPLIED)
        bed.record(APPLIED, "applied")
        self.assertTrue((bed.repo / "claude" / "telemetry" / f"{APPLIED}.json").is_file())
        self.assertEqual(bed.twin()["pruned"], [APPLIED])

    def test_a_record_in_the_wrong_agent_dir_is_no_record(self):
        bed = Bed(self)
        bed.home(APPLIED)
        bed.record(APPLIED, "applied")
        (bed.repo / "bale.toml").write_text('[layout]\nagent_dir = "elsewhere"\n')
        self.assertEqual(bed.twin()["kept"], [{"sid": APPLIED, "why": "no bale record"}])

    def test_sid_limits_it_to_one_session(self):
        bed = Bed(self)
        for sid in (APPLIED, RE_APPLIED):
            bed.home(sid)
            bed.record(sid, "applied")
        twin = bed.twin("--sid", APPLIED)
        self.assertEqual((twin["pruned"], twin["kept"]), ([APPLIED], []))
        self.assertEqual(bed.sids(), [RE_APPLIED])
        gone = bed.twin("--sid", APPLIED)
        self.assertEqual(gone["pruned"], [])
        self.assertEqual([r["sid"] for r in gone["kept"]], [APPLIED])
        self.assertIn("no sandbox home", gone["kept"][0]["why"])
        self.assertTrue(gone["ok"])
        odd = bed.twin("--sid", "../x")
        self.assertEqual((odd["pruned"], odd["ok"]), ([], True))
        self.assertIn("not a session id", odd["kept"][0]["why"])
        self.assertEqual(bed.sids(), [RE_APPLIED])

    def test_a_read_only_tree_in_a_home_is_removed_too(self):
        bed = Bed(self)
        base = bed.home(APPLIED)
        cache = base / "home" / "cache" / "deep"
        cache.mkdir(parents=True)
        (cache / "obj").write_text("read-only, as a module cache is")
        for path in (cache, cache.parent):
            path.chmod(0o500)
        bed.record(APPLIED, "applied")
        twin = bed.twin()
        self.assertEqual((twin["ok"], twin["pruned"]), (True, [APPLIED]), twin)
        self.assertFalse(base.exists())

    def test_freed_bytes_are_the_files_not_followed_symlinks(self):
        bed = Bed(self)
        base = bed.home(APPLIED, size=1000)
        outside = bed.root / "big.bin"
        outside.write_bytes(b"z" * 5000)
        (base / "home" / "link").symlink_to(outside)
        (base / "home" / "dirlink").symlink_to(bed.repo)
        bed.record(APPLIED, "applied")
        twin = bed.twin()
        self.assertEqual(twin["pruned"], [APPLIED])
        self.assertLess(twin["freed_bytes"], 1007 + 1000,
                        "a symlink counts as its own length, not what it points at")
        self.assertGreaterEqual(twin["freed_bytes"], 1007)
        self.assertEqual(outside.read_bytes(), b"z" * 5000, "what a link pointed at stays")
        self.assertTrue((bed.repo / "bale.toml").is_file())


# ---------------------------------------------------------------------------
# 4. The JSON twin and human mode
# ---------------------------------------------------------------------------


class TheTwinAndHumanMode(unittest.TestCase):

    def test_the_twin_names_in_order(self):
        bed = Bed(self).full()
        twin = bed.twin("--dry-run")
        self.assertEqual(list(twin), TWIN_KEYS)
        self.assertEqual(twin["command"], "sandbox prune")
        self.assertEqual((twin["state_dir"], twin["cwd"]), (str(bed.state), str(bed.repo)))
        self.assertIsNone(twin["reason"])
        self.assertIsInstance(twin["freed_bytes"], int)
        for row in twin["kept"]:
            self.assertEqual(list(row), ["sid", "why"])

    def test_human_mode_a_line_per_sid_then_a_total(self):
        bed = Bed(self).full()
        dry = run_cli(*bed.argv("--dry-run"))
        self.assertEqual(dry.code, 0, dry.stderr)
        lines = dry.stdout.splitlines()
        self.assertEqual(lines[0], f"would prune {APPLIED}  ({bed.sizes[APPLIED]} bytes)")
        self.assertEqual(lines[1:5], [f"kept {HELD}: not applied (last: held)",
                                      f"kept {IN_FLIGHT}: in flight",
                                      f"kept {NO_RECORD}: no bale record",
                                      f"kept {ROLLED_BACK}: not applied (last: rolled-back)"])
        self.assertEqual(lines[-1], f"dry run: would prune 1 home, freeing "
                                    f"{bed.sizes[APPLIED]} bytes; 4 kept")
        real = run_cli(*bed.argv())
        self.assertEqual(real.stdout.splitlines()[0],
                         f"pruned {APPLIED}  ({bed.sizes[APPLIED]} bytes)")
        self.assertEqual(real.stdout.splitlines()[-1],
                         f"pruned 1 home, freed {bed.sizes[APPLIED]} bytes; 4 kept")
        self.assertIn("removed the home of", real.stderr)

    def test_nothing_to_prune_is_a_total_line_and_ok(self):
        bed = Bed(self)
        (bed.state / "sandbox").mkdir()
        run = run_cli(*bed.argv())
        self.assertEqual((run.code, run.stdout), (0, "pruned 0 homes, freed 0 bytes; 0 kept\n"))
        bare = Bed(self)
        twin = bare.twin()
        self.assertEqual((twin["ok"], twin["pruned"], twin["kept"]), (True, [], []),
                         "no sandbox/ at all: nothing to do")

    def test_it_is_a_registered_verb(self):
        self.assertIn("sandbox prune", load_registry())
        run = run_cli("commands", "--json")
        names = [row["name"] for row in json.loads(run.stdout)["commands"]]
        self.assertIn("sandbox prune", names)
        self.assertEqual(names, sorted(names))


# ---------------------------------------------------------------------------
# 5. Refusals and failures
# ---------------------------------------------------------------------------


class RefusalsAndFailures(unittest.TestCase):

    def test_a_state_directory_that_cannot_be_read_is_not_ok_and_removes_nothing(self):
        bed = Bed(self).full()
        run = run_cli("sandbox", "prune", "--state-dir", str(bed.root / "absent"),
                      "--cwd", str(bed.repo), "--json")
        twin = json.loads(run.stdout)
        self.assertEqual(run.code, 1)
        self.assertEqual((twin["ok"], twin["pruned"], twin["kept"], twin["freed_bytes"]),
                         (False, [], [], 0))
        self.assertIn("does not exist", twin["reason"])
        self.assertEqual(list(twin), TWIN_KEYS)
        (bed.root / "afile").write_text("x")
        twin = json.loads(run_cli("sandbox", "prune", "--state-dir", str(bed.root / "afile"),
                                  "--cwd", str(bed.repo), "--json").stdout)
        self.assertIn("is not a directory", twin["reason"])
        self.assertEqual(len(bed.sids()), 5)

    def test_no_state_directory_resolves(self):
        run = run_inprocess("sandbox", "prune", "--json", env={})
        twin = json.loads(run.stdout)
        self.assertEqual((run.code, twin["ok"], twin["state_dir"]), (1, False, None))
        self.assertIn("cannot resolve twine's state directory", twin["reason"])

    def test_a_cwd_that_is_not_a_directory_is_not_ok_and_removes_nothing(self):
        bed = Bed(self).full()
        run = run_cli("sandbox", "prune", "--state-dir", str(bed.state), "--cwd",
                      str(bed.root / "nope"), "--json")
        twin = json.loads(run.stdout)
        self.assertEqual((run.code, twin["ok"], twin["pruned"]), (1, False, []))
        self.assertIn("--cwd", twin["reason"])
        self.assertEqual(len(bed.sids()), 5)

    def test_the_default_cwd_is_the_current_directory(self):
        bed = Bed(self)
        bed.home(APPLIED)
        bed.record(APPLIED, "applied")
        run = run_cli("sandbox", "prune", "--state-dir", str(bed.state), "--json",
                      cwd=bed.repo)
        twin = json.loads(run.stdout)
        self.assertEqual((twin["pruned"], twin["cwd"]), ([APPLIED], str(bed.repo)))

    def test_state_dir_from_the_environment(self):
        bed = Bed(self)
        bed.home(APPLIED)
        bed.record(APPLIED, "applied")
        run = run_cli("sandbox", "prune", "--cwd", str(bed.repo), "--json",
                      extra_env={"TWINE_STATE_DIR": str(bed.state)})
        self.assertEqual(json.loads(run.stdout)["pruned"], [APPLIED])

    def test_a_removal_that_fails_is_named_not_ok_and_the_rest_go_on(self):
        bed = Bed(self)
        for sid in (APPLIED, RE_APPLIED):
            bed.home(sid)
            bed.record(sid, "applied")
        real = prune.remove_home

        def fails_for_the_first(state_dir, sid):
            if sid == APPLIED:
                raise PermissionError(13, "Permission denied")
            return real(state_dir, sid)

        import io
        out, err = io.StringIO(), io.StringIO()
        ctx = Context(env={}, stdout=out, stderr=err, which=lambda name: None)
        with mock.patch.object(prune, "remove_home", fails_for_the_first):
            code = main(bed.argv("--json"), ctx=ctx)
        twin = json.loads(out.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(twin["ok"])
        self.assertEqual(twin["pruned"], [RE_APPLIED])
        self.assertEqual(twin["kept"], [{"sid": APPLIED,
                                         "why": "removal failed: Permission denied"}])
        self.assertIn(f"could not remove {APPLIED}: Permission denied", twin["reason"])
        self.assertTrue((bed.state / "sandbox" / APPLIED).is_dir())
        self.assertFalse((bed.state / "sandbox" / RE_APPLIED).exists())
        self.assertEqual(twin["freed_bytes"], bed.sizes[RE_APPLIED])

    def test_a_sandbox_directory_that_cannot_be_listed_is_not_ok(self):
        if os.geteuid() == 0:
            self.skipTest("root lists any directory")
        bed = Bed(self).full()
        (bed.state / "sandbox").chmod(0o000)
        self.addCleanup((bed.state / "sandbox").chmod, 0o700)
        twin = bed.twin()
        self.assertFalse(twin["ok"])
        self.assertIn("cannot be listed", twin["reason"])


# ---------------------------------------------------------------------------
# 6. Safety
# ---------------------------------------------------------------------------


class Safety(unittest.TestCase):

    def test_nothing_outside_a_home_is_removed(self):
        bed = Bed(self).full()
        sentinels = [bed.state / "spend.jsonl", bed.state / "runs.jsonl",
                     bed.root / "outside.txt", bed.repo / "keep.txt"]
        for path in sentinels:
            path.write_text("keep\n")
        (bed.state / "transcripts").mkdir()
        (bed.state / "transcripts" / f"{APPLIED}.jsonl").write_text("{}\n")
        bed.twin()
        for path in sentinels + [bed.state / "transcripts" / f"{APPLIED}.jsonl",
                                 bed.state / "inflight" / f"{IN_FLIGHT}.json",
                                 bed.repo / bed.AGENT_DIR / "telemetry" / f"{APPLIED}.json"]:
            self.assertTrue(path.is_file(), f"{path} was removed")

    def test_entries_that_are_not_homes_are_never_touched(self):
        bed = Bed(self)
        sandbox = bed.state / "sandbox"
        bed.home(APPLIED)
        bed.record(APPLIED, "applied")
        (sandbox / "not a sid").mkdir()
        (sandbox / "stray.txt").write_text("x")
        (sandbox / "-flag").mkdir()
        target = bed.root / "target"
        (target / "home").mkdir(parents=True)
        (target / "home" / "precious").write_text("do not remove")
        (sandbox / "2026-10-10-twine-link-011").symlink_to(target)
        bed.record("2026-10-10-twine-link-011", "applied")
        run = run_cli(*bed.argv("--json"))
        twin = json.loads(run.stdout)
        self.assertEqual((twin["pruned"], twin["kept"]), ([APPLIED], []))
        self.assertTrue((target / "home" / "precious").is_file())
        for name in ("not a sid", "stray.txt", "-flag", "2026-10-10-twine-link-011"):
            self.assertTrue(os.path.lexists(sandbox / name), name)
        self.assertIn("ignoring", run.stderr)

    def test_a_sid_named_directory_without_a_home_is_still_a_kept_home(self):
        """What is under sandbox/ named like a sid is twine's: a directory a
        run made and something removed the `home/` of is pruned like any
        other, by the same rule."""
        bed = Bed(self)
        odd = bed.state / "sandbox" / APPLIED
        odd.mkdir(parents=True)
        (odd / "left-over.txt").write_text("x")
        bed.record(APPLIED, "applied")
        twin = bed.twin()
        self.assertEqual(twin["pruned"], [APPLIED])
        self.assertFalse(odd.exists())

    def test_remove_home_refuses_what_is_not_a_home_path(self):
        bed = Bed(self)
        bed.home(APPLIED)
        for bad in ("../state", "", ".", "-x", "a/b", "x" * 300):
            with self.subTest(sid=bad):
                with self.assertRaises(ValueError):
                    prune.remove_home(bed.state, bad)
        link = bed.state / "sandbox" / "2026-10-10-twine-link-011"
        link.symlink_to(bed.repo)
        with self.assertRaises(ValueError):
            prune.remove_home(bed.state, "2026-10-10-twine-link-011")
        self.assertTrue(bed.repo.is_dir())
        self.assertTrue((bed.state / "sandbox" / APPLIED / "home").is_dir())

    def test_the_module_runs_nothing(self):
        text = (Path(prune.__file__)).read_text(encoding="utf-8")
        for word in ("subprocess", "ctx.run", "socket", "urllib", "ANTHROPIC"):
            self.assertNotIn(word, text)
        run = run_cli("sandbox", "prune", "--help")
        self.assertEqual(run.code, 0)
        self.assertIn("--dry-run", run.stdout)


if __name__ == "__main__":      # pragma: no cover
    unittest.main()

"""The sandbox's cage (twine-sandbox-confine; claude/context/runtime-contract.md
§6.3, §6.4, §6.7): a user, network, mount and PID namespace around `shell` and
the clarification form's crafter, the home the only writable tree.

Real processes throughout — `unshare`, the cage's setup script, bash, python3,
`sleep` — and no model, no network. **Every test asserts either the confined
outcome or an honest unconfined report**, so the suite passes on a machine
where the namespaces cannot be made: `Sandbox.as_json()` says
`filesystem: "unconfined"` with a `filesystem_reason` there, and the tests that
need the cage return after asserting that report rather than pretending. Which
branch this machine took is the first line of `test_this_machine`'s output
under `-v`, and `can_make_the_namespaces` is the test suite's own, independent
probe (`unshare -rnmpf --mount-proc true`, the checkpoint's): where it
succeeds the sandbox must be confined, where it fails the sandbox must say so.

Sections:
  1. Helpers
  2. What is reported
  3. What the cage confines
  4. The processes: nothing outlives a call
  5. The pieces: the script, the read-only trees, the fallback
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from twine.process import run_process
from twine.runtime import sandbox as sandbox_module
from twine.runtime.sandbox import (CAGE_SCRIPT, FILESYSTEM_CONFINED, FILESYSTEM_UNCONFINED,
                                   NETWORK_OFF, Sandbox, SandboxRunner)
from twine.runtime.tools import escalate, run_tool

from tests.helpers import processes_running
from tests.test_runtime_tools import SID, TempSandbox

# ---------------------------------------------------------------------------
# 1. Helpers
# ---------------------------------------------------------------------------


def can_make_the_namespaces() -> tuple[bool, str]:
    """Whether this machine makes the user, network, mount and PID namespaces
    at all — independent of twine's code: the checkpoint's own probe."""
    try:
        done = subprocess.run(["unshare", "-rnmpf", "--mount-proc", "true"],
                              capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return done.returncode == 0, done.stderr.decode("utf-8", "replace").strip()


NAMESPACES, WHY_NOT = can_make_the_namespaces()


class CageCase(unittest.TestCase):
    """A TempSandbox and the shell, with the confined/unconfined split made
    once: `confined()` asserts the report is honest for this machine and says
    whether the cage is there."""

    def setUp(self) -> None:
        self.t = TempSandbox(self)
        self.sb = self.t.sandbox

    def sh(self, command: str, **kwargs) -> dict:
        obj = self.t.tool("shell", command=command, **kwargs).as_json()
        return obj

    def confined(self) -> bool:
        """The report agrees with itself and with this machine; True when the
        filesystem is confined."""
        obj = self.sb.as_json()
        if self.sb.filesystem == FILESYSTEM_CONFINED:
            self.assertNotIn("filesystem_reason", obj)
            self.assertIs(self.sb.confines, self.sb.network == NETWORK_OFF)
            return True
        self.assertEqual(self.sb.filesystem, FILESYSTEM_UNCONFINED)
        self.assertTrue(obj["filesystem_reason"], "unconfined says why")
        self.assertIs(self.sb.confines, False)
        return False


# ---------------------------------------------------------------------------
# 2. What is reported
# ---------------------------------------------------------------------------


class WhatIsReported(CageCase):

    def test_this_machine(self):
        confined = self.confined()
        print(f"\n[cage] namespaces here: {NAMESPACES}; filesystem "
              f"{self.sb.filesystem}"
              + ("" if confined else f" ({self.sb.filesystem_reason})"), flush=True)
        if NAMESPACES:
            self.assertTrue(confined, "the namespaces can be made here, so the cage must "
                                      f"be: {self.sb.filesystem_reason}")
            self.assertEqual(self.sb.network, NETWORK_OFF)
            self.assertIs(self.sb.confines, True)
        else:
            self.assertFalse(confined, "the namespaces cannot be made here: " + WHY_NOT)

    def test_the_twin_names_the_filesystem_beside_the_network(self):
        obj = self.sb.as_json()
        self.assertEqual(list(obj)[:5], ["sid", "home", "repo", "network", "filesystem"])
        self.assertIn(obj["filesystem"], ("confined", "unconfined"))
        json.dumps(obj)

    def test_the_shell_runs_in_the_home_whichever_way_the_machine_went(self):
        out = self.sh("pwd; python3 -c 'print(6 * 7)'; echo hi > made; cat made")
        self.assertEqual(out["stdout"], f"{self.t.home}\n42\nhi\n")
        self.assertTrue((self.t.home / "made").is_file())


# ---------------------------------------------------------------------------
# 3. What the cage confines
# ---------------------------------------------------------------------------


class WhatTheCageConfines(CageCase):

    def test_the_home_is_writable_at_its_own_path(self):
        out = self.sh('echo "$HOME" "$TMPDIR"; pwd; echo kept > "$HOME/note"; '
                      'echo temp > "$TMPDIR/scratch"; ls "$HOME"')
        self.assertEqual(out["exit_code"], 0, out["stderr"])
        lines = out["stdout"].splitlines()
        self.assertEqual(lines[0], f"{self.t.home} {self.t.home / 'tmp'}")
        self.assertEqual(lines[1], str(self.t.home))
        self.assertEqual((self.t.home / "note").read_text(), "kept\n")
        self.assertEqual((self.t.home / "tmp" / "scratch").read_text(), "temp\n")

    def test_a_file_outside_the_home_cannot_be_read(self):
        secret = self.t.outside / "secret.txt"
        out = self.sh(f"cat {secret}; echo rc=$?")
        if not self.confined():
            return
        self.assertNotIn("outside the cage", out["stdout"])
        self.assertIn("rc=1", out["stdout"])
        self.assertIn("No such file", out["stderr"])

    def test_nothing_outside_the_home_can_be_written(self):
        if not self.confined():
            return
        tag = f"{os.getpid()}-{time.time_ns()}"
        host_marker = self.t.outside / f"marker-{tag}"
        out = self.sh(f"touch /zz /etc/zz /usr/zz /dev/zz; echo $?; "
                      f"touch {host_marker}; echo $?; touch /tmp/inside-{tag}; echo $?; "
                      f"echo ok > /dev/null; echo $?; touch /dev/shm/x; echo $?")
        self.assertEqual(out["stdout"].split(), ["1", "1", "0", "0", "0"], out["stderr"])
        for name in ("/zz", "/etc/zz", "/usr/zz", "/dev/zz"):
            self.assertIn(name, out["stderr"])
        self.assertFalse(host_marker.exists(), "a place of the host's is not writable")
        self.assertFalse(Path(f"/tmp/inside-{tag}").exists())

    def test_the_hosts_other_trees_are_not_there(self):
        t = self.t
        out = self.sh(f"ls /mnt 2>&1; ls /media 2>&1; ls {t.repo} 2>&1; ls {t.root} 2>&1; "
                      f"ls {t.state} 2>&1; ls {t.state / 'sandbox'} 2>&1; "
                      f"ls {t.state / 'sandbox' / SID} 2>&1")
        if not self.confined():
            return
        lines = out["stdout"].splitlines()
        self.assertEqual(sum("No such file or directory" in line for line in lines), 3,
                         "/mnt, /media and the repository are not there")
        shown = [line for line in lines if "No such file" not in line]
        # the directories on the way to the home are there, empty but for that way:
        # not `repo/` and `outside/` beside `state/`, not the state directory's
        # other files, not the other sessions' homes
        self.assertEqual(shown, ["state", "sandbox", SID, "home"])

    def test_the_state_directorys_own_files_are_unreachable(self):
        (self.t.state / "spend.jsonl").write_text("not for the cage\n", encoding="utf-8")
        (self.t.state / "abort").mkdir(exist_ok=True)
        out = self.sh(f"cat {self.t.state}/spend.jsonl; ls {self.t.state}/abort; "
                      f"mkdir -p {self.t.state}/abort && touch {self.t.state}/abort/{SID}.json; "
                      f"echo rc=$?")
        if not self.confined():
            return
        self.assertNotIn("not for the cage", out["stdout"])
        self.assertEqual(out["stdout"].count("rc=1"), 1, out)
        self.assertFalse((self.t.state / "abort" / f"{SID}.json").exists())

    def test_the_way_to_the_home_is_read_only_under_the_hosts_tmp_too(self):
        """A state directory under the host's `/tmp` (a temp dir, bale's
        staging) puts the way to the home inside the cage's own writable
        `/tmp`; the cage gives that way a read-only tmpfs of its own, so the
        home stays the only writable tree on it and the private `/tmp` beside
        it stays writable. The test above covers wherever TMPDIR points; this
        one pins `/tmp` itself, the case the operator's apply ran."""
        try:
            tmp = tempfile.TemporaryDirectory(prefix="twine-under-tmp-", dir="/tmp")
        except OSError as exc:
            self.skipTest(f"no writable /tmp here: {exc}")
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        if not str(base).startswith("/tmp/"):
            self.skipTest(f"/tmp resolves elsewhere here ({base}); the case does not arise")
        repo = base / "repo"
        repo.mkdir()
        state = base / "state"
        sb = Sandbox.create(state, SID, repo=repo)
        tag = f"{os.getpid()}-{time.time_ns()}"
        out = run_tool(sb, "shell", {"command": (
            f"mkdir {state}/abort; echo rc=$?; touch {sb.home.parent}/beside; echo rc=$?; "
            f"touch {base}/top; echo rc=$?; touch /tmp/free-{tag}; echo rc=$?; "
            f"echo kept > {sb.home}/note; echo rc=$?")}).as_json()
        if sb.filesystem != FILESYSTEM_CONFINED:
            self.assertEqual(sb.filesystem, FILESYSTEM_UNCONFINED)
            self.assertTrue(sb.filesystem_reason, "unconfined says why")
            return
        self.assertEqual(out["stdout"].split(), ["rc=1", "rc=1", "rc=1", "rc=0", "rc=0"], out)
        self.assertIn("Read-only file system", out["stderr"])
        self.assertFalse((state / "abort").exists(), "nothing reaches the host's state")
        self.assertFalse((sb.home.parent / "beside").exists())
        self.assertFalse(Path(f"/tmp/free-{tag}").exists(), "the cage's /tmp is its own")
        self.assertEqual((sb.home / "note").read_text(), "kept\n")

    def test_proc_is_the_cages_own(self):
        out = self.sh("ls /proc | grep -E '^[0-9]+$' | wc -l; "
                      "tr '\\0' ' ' < /proc/1/cmdline | cut -d' ' -f1-2")
        if not self.confined():
            return
        count, init = out["stdout"].split("\n")[:2]
        self.assertLessEqual(int(count), 5, "the shell, ls, grep, wc, tr — no host process")
        self.assertEqual(init, "bash -c", "pid 1 is the command, not the host's init")

    def test_python3_git_tar_and_coreutils_run(self):
        out = self.sh("python3 -c 'import sys, json, ssl, sqlite3; print(sys.version_info[0])'; "
                      "git init -q repo && cd repo && git -c user.email=a@b -c user.name=n "
                      "commit -q --allow-empty -m x && git log --oneline | wc -l; "
                      "cd .. && echo data > f && tar cf f.tar f && tar tf f.tar; "
                      "sort /dev/null; id -u > /dev/null; echo done")
        self.assertEqual(out["exit_code"], 0, out["stderr"])
        self.assertEqual(out["stdout"].split(), ["3", "1", "f", "done"])

    def test_the_network_is_still_off(self):
        out = self.sh("tail -n +3 /proc/net/dev | cut -d: -f1")
        if self.sb.network != NETWORK_OFF:
            self.assertTrue(self.sb.network_reason)
            return
        self.assertEqual(out["stdout"].split(), ["lo"])

    def test_the_cage_cannot_undo_itself(self):
        if not self.confined():
            return
        out = self.sh("mount -t tmpfs none /tmp > /dev/null 2>&1; echo mount=$?; "
                      "python3 -c \"import os; os.chroot('/tmp')\" 2>&1 | tail -1")
        lines = out["stdout"].splitlines()
        self.assertNotEqual(lines[0], "mount=0", "mount is refused: no CAP_SYS_ADMIN")
        self.assertIn("PermissionError", lines[-1], "chroot is refused: no CAP_SYS_CHROOT")

    def test_the_cage_has_the_ordinary_devices(self):
        out = self.sh("echo x > /dev/null; head -c 4 /dev/zero | wc -c; "
                      "head -c 4 /dev/urandom | wc -c; cat <(echo substituted)")
        self.assertEqual(out["exit_code"], 0, out["stderr"])
        self.assertEqual(out["stdout"].split(), ["4", "4", "substituted"])

    def test_an_environment_variable_never_carries_the_hosts_paths_in(self):
        out = self.sh("env")
        names = {line.split("=", 1)[0] for line in out["stdout"].splitlines()}
        self.assertEqual(names - {"PWD", "SHLVL", "_"}, {"PATH", "HOME", "TMPDIR", "LANG"})


# ---------------------------------------------------------------------------
# 4. The processes: nothing outlives a call
# ---------------------------------------------------------------------------


class NothingOutlivesACall(CageCase):

    def test_a_backgrounded_child_does_not_survive_the_call(self):
        marker = "41411"
        out = self.sh(f"sleep {marker} & echo started")
        self.assertEqual(out["stdout"], "started\n")
        self.assertEqual(processes_running(marker), [])

    def test_a_child_in_a_session_of_its_own_does_not_survive_the_call(self):
        marker = "41412"
        out = self.sh(f"setsid sleep {marker} < /dev/null > /dev/null 2>&1 & "
                      f"sleep 0.3; echo started")
        self.assertEqual(out["stdout"], "started\n")
        time.sleep(0.2)
        if self.sb.filesystem != FILESYSTEM_CONFINED:
            # without the PID namespace the seam can only kill the group; a
            # `setsid` child leaves it — what the report's `unconfined` says
            for pid in processes_running(marker):
                os.kill(pid, 9)
            self.assertTrue(self.sb.filesystem_reason)
            return
        self.assertEqual(processes_running(marker), [])

    def test_a_timeout_kills_the_command_and_everything_it_started(self):
        marker = "41413"
        out = self.sh(f"setsid sleep {marker} & sleep {marker}; wait", timeout=1)
        self.assertTrue(out["timed_out"])
        deadline = time.monotonic() + 5
        while processes_running(marker) and time.monotonic() < deadline:
            time.sleep(0.05)
        left = processes_running(marker)
        if left and self.sb.filesystem != FILESYSTEM_CONFINED:
            for pid in left:           # the escaped `setsid` child, unconfined
                os.kill(pid, 9)
            self.assertTrue(self.sb.filesystem_reason)
            return
        self.assertEqual(left, [])

    def test_the_command_is_the_namespaces_init(self):
        out = self.sh("echo $$")
        if not self.confined():
            return
        self.assertEqual(out["stdout"], "1\n")


# ---------------------------------------------------------------------------
# 5. The pieces: the script, the read-only trees, the fallback
# ---------------------------------------------------------------------------


class ThePieces(CageCase):

    def test_a_tree_a_call_names_is_shown_read_only_at_its_own_path(self):
        with tempfile.TemporaryDirectory(prefix="twine-ro-") as tmp:
            tree = Path(tmp).resolve() / "toolchain"
            (tree / "bin").mkdir(parents=True)
            (tree / "bin" / "tool").write_text("#!/bin/sh\necho the tool ran\n")
            (tree / "bin" / "tool").chmod(0o755)
            result = self.sb.spawn(["sh", "-c", f"{tree}/bin/tool; touch {tree}/new; echo $?"],
                                   cwd=self.t.home, readonly=[tree])
            out = result.stdout.decode()
            if not self.confined():
                return
            self.assertEqual(out.split("\n")[0], "the tool ran", result.stderr)
            self.assertEqual(out.split("\n")[1], "1")
            self.assertFalse((tree / "new").exists())
            plain = self.sb.spawn(["sh", "-c", f"ls {tree}; echo $?"], cwd=self.t.home)
            self.assertEqual(plain.stdout.decode(), "2\n", "without naming it, it is not there")

    def test_the_interpreter_escalate_runs_is_visible(self):
        trees = escalate.interpreter_trees()
        self.assertTrue(trees)
        runner = self.sb.runner
        if not isinstance(runner, SandboxRunner):
            self.fail("the sandbox's runner is a SandboxRunner")
        shown = runner.with_readonly(trees).readonly
        if shown:
            self.assertEqual(sorted(shown), list(shown), "sorted, so the argv is stable")
        result = self.sb.spawn([sys.executable, "-I", "-B", "-c", "print('ran')"],
                               cwd=self.t.home, readonly=trees)
        self.assertEqual((result.exit_code, result.stdout), (0, b"ran\n"), result.stderr)

    def test_the_script_without_pivot_root_falls_back_to_chroot(self):
        """Where `pivot_root` is refused (a chrooted bale, an unusual root),
        the script confines with `chroot` instead, the capabilities dropped
        — the same outcomes: the home writable, a host file not there."""
        if not NAMESPACES:
            self.assertFalse(self.confined())
            return
        script = CAGE_SCRIPT.replace("pivot_root . .", "false")
        self.assertNotEqual(script, CAGE_SCRIPT)
        secret = self.t.outside / "secret.txt"
        argv = ("unshare", "-rnmpf", "--kill-child", "--", "sh", "-c", script, "twine-cage",
                str(self.sb.home), str(self.sb.home), str(self.sb.root), "0", "bash", "-c",
                f"cat {secret}; echo rc=$?; pwd; echo ok > in-home; touch /zz; echo rc=$?; "
                f"echo $$; ls /proc | grep -cE '^[0-9]+$'")
        result = run_process(argv, cwd=self.sb.home, env=dict(self.sb.env), timeout=60)
        text = result.stdout.decode()
        self.assertNotIn("outside the cage", text)
        lines = text.split("\n")
        self.assertEqual(lines[:2], ["rc=1", str(self.sb.home)], result.stderr)
        self.assertEqual(lines[2:4], ["rc=1", "1"], "a read-only root; the command is init")
        self.assertEqual((self.sb.home / "in-home").read_text(), "ok\n")

    def test_a_cage_that_cannot_be_built_stops_at_the_step_that_failed(self):
        if not NAMESPACES:
            self.assertFalse(self.confined())
            return
        bad_root = self.t.root / "no-such-dir"
        argv = ("unshare", "-rnmpf", "--kill-child", "--", "sh", "-c", CAGE_SCRIPT,
                "twine-cage", str(self.sb.home), str(self.sb.home), str(bad_root), "0",
                "true")
        result = run_process(argv, cwd=self.sb.home, env=dict(self.sb.env), timeout=60)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("twine cage: stopped while making the private root",
                      result.stderr.decode())

    def test_the_mount_point_is_kept_empty_in_the_sid_directory(self):
        self.sh("true")
        root = self.t.home.parent / "root"
        self.assertTrue(root.is_dir())
        self.assertEqual(list(root.iterdir()), [], "the cage's mounts are not the host's")


class TheDocsName(unittest.TestCase):
    """The docs say what the code does (a line changed here changes there)."""

    def read(self, rel: str) -> str:
        from twine import REPO_ROOT
        return " ".join((REPO_ROOT / rel).read_text(encoding="utf-8").split())

    def test_the_contracts_the_readme_and_the_index(self):
        runtime = self.read("claude/context/runtime-contract.md")
        for needle in ("filesystem_reason", "`filesystem: \"unconfined\"`", "unshare -rnmpf",
                       "no process it started is alive", "the outer `unshare`",
                       "twine sandbox prune", "CAGE_SCRIPT", "--kill-child"):
            self.assertIn(needle, runtime, needle)
        self.assertNotIn("there is no mount namespace", runtime)
        cli = self.read("claude/context/cli-contract.md")
        for needle in ("## 22. `twine sandbox prune", "`filesystem`", "attempts[].outcome",
                       "never removed", "freed_bytes"):
            self.assertIn(needle, cli, needle)
        readme = self.read("README.md")
        for needle in ("twine sandbox prune", "filesystem_reason", "0.27.0"):
            self.assertIn(needle, readme, needle)
        index = self.read("claude/INDEX.md")
        for needle in ("sandbox prune", "filesystem_reason"):
            self.assertIn(needle, index, needle)
        from twine import REPO_ROOT
        self.assertEqual((REPO_ROOT / "VERSION").read_text().strip(), "0.27.0")


class TheMountPoint(unittest.TestCase):

    def test_the_sandbox_made_twice_reuses_the_mount_point(self):
        t = TempSandbox(self)
        again = Sandbox.create(t.state, SID, repo=t.repo)
        self.assertEqual(again.root, t.sandbox.root)
        self.assertEqual((again.filesystem, again.network),
                         (t.sandbox.filesystem, t.sandbox.network))


if __name__ == "__main__":      # pragma: no cover
    unittest.main()

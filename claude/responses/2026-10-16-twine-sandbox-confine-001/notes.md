# notes — 2026-10-16-twine-sandbox-confine-001

Twine's sandbox is a cage now, and `twine sandbox prune` exists. Everything
below is what I'd want to know before ratifying. Nothing is outside the write
forecast: every path is under `README.md`, `VERSION`, `claude/`, `tests/` or
`twine/`, so there is no `forecast_departures`.

## This is a re-attempt (corrects the held first response)

The first response was held on one suite failure,
`WhatTheCageConfines.test_the_state_directorys_own_files_are_unreachable`:
`mkdir -p <state>/abort && touch <state>/abort/<sid>.json` printed `rc=0` in the
cage where the test expected `rc=1`. The checkpoint passed and nothing reached
the host (the `cat` and `ls` of the state directory's real files both said "No
such file"), so this was not a hole to the host. It was a case the first
attempt never exercised.

**What happened.** The cage script made the directories on the way to the home
with `mkdir -p "$root$home"` on whatever mount they fell in. When the state
directory lives under the host's `/tmp` (the suite's temp dirs in bale's
staging, and on this desk), that way falls inside the cage's own **writable**
`/tmp` tmpfs. So `<state>/abort` could be made there: a throwaway directory in
the cage's private `/tmp`, but a writable place on the way to the home all the
same. The first worker's desk had its temp root outside `/tmp`, where the way
falls on the read-only root, so the test passed there. I reproduced both: the
test fails with the old script when `TMPDIR` is under `/tmp` and passes when it
is elsewhere.

**The fix, in the code rather than the test.** The brief says the home is "the
only writable place the cage sees besides an empty private `/tmp`", and that
should not depend on where the state directory lives. So the setup now finds
the shallowest directory on the way to the home that the private root does not
have yet, mounts a 1 MB tmpfs there, makes the rest of the way inside it, binds
the home, and remounts that tmpfs read-only (`CAGE_SCRIPT`, the "mounting the
home" step). Under `/tmp`, that leaves `/tmp/<temp-root>/…` read-only and the
rest of the cage's `/tmp` writable. When every directory on the way already
exists (inside a read-only tree a call named), nothing is added, as before. A
failed step still fails closed into an honest `unconfined`. The original test
is unchanged and now passes wherever `TMPDIR` points.

**What changed in this attempt:** `twine/runtime/sandbox.py` (the script),
`tests/test_sandbox_cage.py` (one new test,
`test_the_way_to_the_home_is_read_only_under_the_hosts_tmp_too`, which builds its
state directory under `/tmp` itself so the case is always exercised: the way is
read-only, the cage's `/tmp` is still writable and still its own, the home is
writable; it fails against the old script), `claude/context/runtime-contract.md`
§6.3 (the way to the home is read-only, and how; the setup order names the new
step), `validation.sh` (a new line in the cage check: "the way to the home is
read-only"), and the seed annotation below (one clause). Everything else is the
first attempt's bytes.

**Run here, on the finished tree:** the full suite, 1374 tests, green under
the runner with the temp root under `/tmp`; `tests/test_sandbox_*.py` green
with `TMPDIR` outside `/tmp`; `tests/test_sandbox_cage.py` green with `unshare`
hidden from `PATH` (the honest-unconfined branch). This desk makes the
namespaces (`unshare -rnmpf --mount-proc true` succeeds). I could not run the
checkpoint or bale's PID-namespace sandbox. The new mount is the same kind the
script already makes (a tmpfs, then a bind-remount read-only, as for `/` and
`/dev`), so I expect nothing new there.

## What I ran, and on what (the first attempt)

This desk is itself a user namespace (everything under `/` reads as `nobody`,
I am uid 0 inside it), so every confined run below is a cage nested inside a
namespace — the same shape as bale's apply sandbox, which is the one place I
could not run the blind checkpoint.

- The suite: 1373 tests (1309 + 64; 1374 with this attempt's), green, twice: normally (the cage is
  made, `filesystem: "confined"`), and with a `PATH` that has no `unshare`
  (`/tmp/fakebin`: every `/usr/bin` entry but that one), where the cage tests
  take their honest-`unconfined` branch and pass. The one failure of the
  second run before I fixed the tests was my own kill test, which in the
  unconfined branch leaves a `setsid` sleeper behind by design — it now kills
  it and says so.
- `validation.sh` on the finished tree, both branches of its cage check.
- By hand: `find /` in the cage ends in about 2.6 s here — 136 000 entries,
  134 000 of them under `/usr` on this machine (the brief hoped for "a
  second"; what it crawled before was `/mnt/c` for 600 s, and that cannot be
  reached now); `/mnt`, `/media`, the repository, the state directory's files are
  not there; `touch /zz` is "Read-only file system"; `mount` and
  `chroot(2)` are refused; `python3`, `git`, `tar`, `sort` run; a command
  that backgrounds a child and returns, and one that `setsid`s one, leave
  nothing; a SIGTERM to the registered group, and a SIGKILL of it, leave
  nothing; a call costs about 50 ms in all (the setup is ~40 ms); `kill -9 $$` in a call is ignored, as the init note below says.

## The mechanism (the worker's, flagged for ratification)

`unshare -rnmpf --kill-child -- sh -c CAGE_SCRIPT twine-cage HOME CWD ROOT N
RO… COMMAND…` (`SandboxRunner.wrap`, `CAGE_SCRIPT` in
`twine/runtime/sandbox.py`). The script, as the PID namespace's first
process: mounts a tmpfs at `<state>/sandbox/<sid>/root/`; `/tmp`, a fresh
`/proc`, `/dev` (null, zero, full, random, urandom, tty, the `fd` links,
`/dev/shm`); `--rbind`s `/usr /bin /sbin /lib*` and remounts the mount **and
every submount under it** read-only; copies a short list of `/etc` files;
`--rbind`s the home at its own path; remounts `/` and `/dev` read-only;
`pivot_root . .` and `umount -l .`; `cd`s to the cwd; and `exec`s `setpriv
--no-new-privs --bounding-set=-sys_admin,-sys_chroot -- COMMAND`. Where
`pivot_root` is refused it `chroot`s instead, with the same capabilities
dropped. Worth looking at:

- **No `--mount-proc`.** I mount `/proc` myself inside the PID namespace;
  `--mount-proc` would mount it over the *old* root's `/proc`, which the
  pivot then discards.
- **`rbind` and the recursive read-only remount.** A plain bind of `/usr` is
  `EINVAL` here (WSL mounts three filesystems under `/usr/lib`, locked in a
  user namespace), and an `rbind` alone leaves those submounts writable, so
  `readonly_tree` remounts each one it finds in `/proc/self/mountinfo`. A
  failed remount stops the script — fail closed, reported as unconfined.
- **The command is init.** `$$` is 1; signals with no handler sent *inside*
  the namespace to it are ignored (so `kill -9 $$` in a `shell` call does not
  end the call); its exit status and death-by-signal come back through
  `unshare` as before. I chose this over a tiny init so the command's status
  is not re-encoded. Say if you'd rather have an init between.
- **`--kill-child`** is belt and braces. In my experiment the group's
  SIGKILL already kills init (it is a member of the group), and the namespace
  takes everything else with it; `--kill-child` covers a SIGTERM that only the
  outer `unshare` sees, and a bare kill of its pid.
- **`/etc` is copies, not a bind**, and `/etc/python3*` is left out on
  purpose: on Debian the `sitecustomize` it carries imports apport and apt,
  which warn on stderr when `/etc/apt` is not there. Python runs without it.
- **`root/`** is a new empty directory beside `home/`, made by
  `Sandbox.create` (0700), so nothing is mounted over a host path. `twine
  status` still lists homes by `home/`; prune removes `root/` with the rest.
- **`readonly=`.** `escalate` runs the request's crafter and lint on
  `sys.executable`. When that lives under the system directories (the usual
  case) nothing is added; when it is a pyenv or a venv under the operator's
  home, `interpreter_trees()` names `sys.prefix`, `sys.base_prefix` and the
  executable's directory and those — and only those — are shown read-only at
  their own paths. `readonly_trees` drops what is already visible.

## Behavior changes you should know about

- `confines` is now true only when the network is off **and** the filesystem
  confined. A machine that can make `-rn` but not the mount/PID namespaces is
  `network: "off"`, `filesystem: "unconfined"`, `confines: false` — it used to
  say `confines: true`. §10.5 and the capability's promises say so.
- `as_json()` key order: `sid, home, repo, network, filesystem, confines,
  max_timeout`, then `reason` (network unconfined), then `filesystem_reason`.
  The run twin has `filesystem` immediately after `network`; `next` is last.
- Detection runs the whole cage on `true`; only when that fails does it try
  `unshare -rn true` and `unshare -rmpf … true` separately (so a machine
  that can do half keeps the half). A failing step prints `twine cage: stopped
  while <step>` and that line is in `filesystem_reason`.
- Four existing tests assumed a `shell` that reached outside the home and were
  rewritten, not weakened: two wrote the abort request from the cage (now a
  marker in the home and the operator's side — `AbortWhenSeen` — writes it);
  one's double crafter `runpy`'d the repository's `tests/bale_tools` (now a
  copy in the home); one looked for a sleeper by its in-cage pid (now by
  command line, `processes_running`). The two "record exists before the first
  spawn" tests now accept the extra detection spawns of a half-working machine.
  `VERSION` pins moved to 0.27.0 in `test_resume` and `test_telemetry`.
- Prune choices where the brief left room: a state directory that does not
  exist is not ok (as `twine kill`), one without `sandbox/` is nothing to do;
  `--sid` naming no home or no sid is a `kept` row, ok true; a record whose
  `attempts` has an entry without a string `outcome` is "cannot be read";
  without any of the four merge outcomes, `not applied (last: X)` names the
  last outcome of any kind (`held`, `opened`, … or `none`); `freed_bytes` is
  the sum of file and symlink sizes (nothing followed, directories not
  counted); an in-flight or running record that exists but cannot be `lstat`ed
  keeps the home and says so.

## Residuals and unknowns

- I could not run the blind checkpoint, and the nested-namespace shape I did
  run is the only nested shape I know. The two spots I'd watch in bale's
  sandbox: `mount -t proc` (it needs the existing `/proc` to be fully visible,
  as `--mount-proc` does) and the read-only remount of submounts under `/usr`.
  Both fail closed into an honest `unconfined`, not a crash.
- `shell`'s `python3` is whatever the cage's `PATH` finds under the system
  directories. A `python3` that only a `PATH` entry under the operator's home
  provides is not there — by design, that is the home the brief says must be
  unreachable — and the sandbox does not say so beyond `command not found`.
- `/proc` is the namespace's own, but its `sys` and kernel files are as
  readable to a user-namespace root as to any user.
- The `/etc` copies are snapshots taken at each call.
- `probe` is untouched and still leaves the cage.

## Proposals

### Tell the worker about the cage

**What** — the loop's system prompt (runtime-contract §7.2) and the `shell`
description say "no network" and nothing of the filesystem. A worker that
knows its `/tmp` is private, `/mnt` is absent and the system directories are
read-only will stop trying `find /` and `cd /tmp/stage`.
**Why** — finding 7 of the hosted run was exactly that behavior.
**Scope hints** — `twine/runtime/loop.py`'s prompt, `tools.toml`'s `shell`
description (parity by name only), and the tests that pin the prompt's required
content; the sandbox could hand `filesystem` to the prompt builder so an
unconfined run says the opposite.

### An init between unshare and the command

**What** — if `kill -9 $$` or a command that expects to be killable by its own
`kill $$` matters, a 20-line reaper as the namespace's init, the command its
child, would restore ordinary signal behavior at the cost of re-encoding the
exit status.
**Why** — init ignores unhandled signals sent from inside its namespace; nothing
in the suite or the brief needs it.

### A `--prune` hint on `twine run`'s `delivered` line

**What** — `twine status` could count homes and say how many `sandbox prune
--dry-run` would remove.
**Why** — the homes accumulate silently until the operator thinks of the verb.
**Scope hints** — `twine/commands/core.py`'s `list_sandboxes` and §4's twin;
a read of bale's record from `status` would be new, so only after a ruling.

## The seed annotation, for the next tidy

Verbatim and complete, to go under §5.2 after telemetry's bracket:

```
[2026-10-16-twine-sandbox-confine-001: the sandbox confined (the hardening
wave, 4 of 6). `shell`, and escalate's clarification form — the request's
crafter and lint — now run in a user, network, mount and PID namespace,
`unshare -rnmpf --kill-child` around a setup script
(`CAGE_SCRIPT`, `twine/runtime/sandbox.py`) that builds a private tmpfs root
and pivots into it: the sandbox home is the only writable tree, at its own
absolute path, beside an empty private `/tmp`, the directories on the way to
it read-only wherever the state directory lives; `/usr`, `/bin`, `/sbin`,
`/lib*` and a few copied `/etc` files are read-only; nothing else of the host
is visible — not the operator's home outside the sandbox home, not `/mnt`,
not the repository the session was opened in, not the state directory beyond
the home — and `/proc` is the cage's own; no process a call started is alive
when it returns, a `setsid` child included, because the command is the
namespace's init; `CAP_SYS_ADMIN` and `CAP_SYS_CHROOT` are dropped. Where the
namespaces cannot be made the sandbox runs as before and says so, never
silently: `Sandbox.as_json()` and the run twin gain `filesystem`
(`"confined"` or `"unconfined"`) and, when unconfined, `filesystem_reason`;
`confines` is true exactly when the network is off and the filesystem
confined, detected at creation by running the whole cage on `true`, each half
alone when that fails. The kill-switch still reaches the cage: the pid the
hook registers is the outer `unshare`'s, the command is the namespace's init,
and the namespace dies with the outer process. `probe` still leaves the cage.
The lifecycle: `twine sandbox prune [--sid SID] [--dry-run] [--state-dir DIR]
[--cwd DIR] [--json]` removes `<state-dir>/sandbox/<sid>/` for each kept home
whose session bale records as applied — read from bale's own record,
`<cwd>/<agent_dir>/telemetry/<sid>.json`, only `attempts[].outcome`: applied
exactly when, of the attempts whose outcome is `applied`, `re-applied`,
`rolled-back` or `reverted`, the last is `applied` or `re-applied` — keeps
every other home with why (`no bale record`, `not applied (last: …)`, `the
record cannot be read: …`, `in flight`, `running`), and never removes a home
whose session has an in-flight or a running record, nor anything outside
`<state-dir>/sandbox/<sid>/` (runtime-contract §6.3, §6.4, §6.7, §7.7;
cli-contract §22, §18.5, §18.6). `VERSION` 0.27.0.]
```

# Notes — 2026-10-13-twine-runtime-tools-003 (Arc 2 R3)

## 0. The HOLD of 2026-10-13, corrected (this re-attempt: `corrects` set)

Both judges held for one environmental reason, as the desk ruled. Under
bale's apply sandbox, the test process runs in a PID namespace whose
group leader is outside it. So `os.getpgrp()` is 0, and
`register_running` refuses it. Five tests registered the test process
itself as the runtime, and so did `validation.sh`'s hook check.

I reproduced it here with `unshare -rpf --mount-proc`. It gave exactly
the same five errors. There the runner is also the namespace's init, so
`os.getpid()` is 1, which `register_running` refuses too. That rules out
the "make the test process a group leader" option on such a runner.

So I took the ruling's other option: register a child process spawned
for the purpose.

- **Tests:** a new helper, `stand_in_runtime`, is `helpers.RealGroup`
  running `exec sleep 300`. It's started as a session leader, so its
  pid is its pgid. It's registered with `register_running(state, SID,
  pgid, pgid)`, then killed and reaped at cleanup. The five tests use
  it, and the "hook cannot register" double hands back the stand-in's
  group instead of `os.getpgrp()`.
- **`validation.sh`'s hook check:** it uses a `sleep` started with
  `start_new_session=True` the same way.

Nothing in `twine/` changed: the `files/` mirror differs from the held
response only in `tests/test_runtime_tools.py`, and `validation.sh` is
new. Results under `unshare -rpf --mount-proc`:

- The suite: 958 tests, OK, the same 5 skips as before.
- `validation.sh`: all checks pass.

Section 4 below describes the first response's rehearsal. The
re-attempt's runs are in this section.

Everything the brief pinned is built and the suite is 958 (873 + 85),
green. Every changed path is inside the forecast, so there are no
forecast departures. Below: the four decisions §7 left to me, the other
places where I chose or deviated, what to look at closely, what surprised
me, and the seed annotation for tidy9.

## 1. Decisions (brief §7) and other flagged calls

**§7.1: how the declaration marks `sandboxing` as implemented by the runtime.**
I added an optional fifth key, `implemented_by`, which names a module
directly under `twine.runtime` (`twine.runtime.sandbox`). That module
declares `IMPLEMENTS = ("sandboxing",)`, the same way an adapter declares
its set. The status check got stricter, not looser:

- `implemented` now needs an implementer: either an adapter, or an
  `implemented_by` module that imports and lists the capability.
  Otherwise the registry reports a new problem kind,
  `missing-implementer`, plus the status-mismatch.
- `declared` next to an `implemented_by` is a status-mismatch.
- An adapter that claims a runtime capability is a status-mismatch.

I rejected the loop-as-pseudo-adapter option. The boundary requires
every adapter to implement tool-calling, thinking and usage-accounting
and to answer `call`, which a sandbox can't do. It would also print
next to `anthropic` and `fake` in `runtime list` as if it were an
adapter.

Consequence: `runtime list`'s rows gained a key, `implemented_by`
(`null` for the other seven). `runtime show` carries it too. The R1
test that pinned the row's five keys now pins six; see §2 below.

**§7.2: the tools' declaration shape.**
I mirrored `capabilities.toml`: `twine/runtime/tools.toml` has
`[[tool]]` entries with exactly `name`, `module` and `leaves_cage`, and
each module exposes a `TOOL`. I didn't use a `TOOLS` tuple per module,
for two reasons:

- A discovered tuple is its own declaration, so parity would have only
  one side and a missing tool could never be reported.
- `leaves_cage` is the one security fact a reviewer should be able to
  read without opening code, so it lives in the declaration. The
  registry checks the module's `TOOL.leaves_cage` against it and
  reports any disagreement as `cage-mismatch`.

**§7.3: `shell`'s `content`.**
It's stdout as it was. If there was stderr, it follows under a
`[stderr]` line. Then comes one bracketed exit line: `[exit N]`,
`[exit -N: killed by SIGKILL]`, `[killed: timed out after Ts; …]` or
`[killed: stdout passed 262144 bytes; …]`. When the seam truncated
stderr there's also `[stderr cut at 65536 bytes]`. Nothing is dropped
up to the caps.

**§7.4: `-m`/`-p`.**
I used `-rn` alone.

- `-m` without bind mounts confines nothing.
- `-p` needs `--fork` and a `/proc` remount. It would also hand the
  hook the outer `unshare`'s pid instead of the command's.
- Without `--fork`, `unshare` execs the command in place, so the pid
  registered is the command's own. A test reads `$$` back to check it.

runtime-contract §6.3 states plainly that `shell` is cwd'd in the home
but **not** filesystem-confined. Only the file tools are
path-confined. I added a proposal for this below.

Other calls you should be able to find without reading the diff:

- **PATH and LANG come from `twine.process.inherited_environment`, not
  from `os.environ` in the sandbox.** The brief says the default env is
  "built from os.environ for PATH and LANG only". But R2's
  `NoNetworkNoKey` test forbids any `environ`/`getenv` (and any `os`
  import) under `twine/runtime/`, and I kept that rule intact. The seam's
  module reads the two variables by name. The effect is what the brief
  asked for.
- **`probe` gets the cage's minimal environment, not the operator's.**
  `carry probe --run` inherits the operator's environment. A
  model-authored probe script would then hold `ANTHROPIC_API_KEY` and
  could print it into the paste-back the model reads. So the tool
  deviates from carry probe here; everything else about the run is
  carry probe's (it leaves the cage, runs unwrapped, network on,
  `cwd` is the repo).
- **`probe` reuses `carry.py`'s functions rather than copying them.**
  That's `choose_block`, `run_probe` and `verify_output`, plus
  `check_block_ready`, which I split out of `check_ready` (behaviour
  unchanged; `check_ready` calls it). So `twine/runtime/tools/probe.py`
  imports `twine.commands.carry` and `twine.cli.Context`. That's a
  runtime→commands dependency. I think reuse is worth it, but it's
  yours to rule on. The alternative is moving those four functions into
  a non-command module.
- **The network detection at creation goes through the kill-switch hook
  too.** The brief says "nothing else in R3 spawns", but the detection
  is a spawn, so it goes through the same `Sandbox.spawn`.
- **A record that can't be read refuses the spawn.** That's an error
  result for a tool, and `SandboxError` at creation. "No record" runs
  unregistered and logs it, as pinned. A malformed record is different:
  it means `twine kill` can't find the group, so I fail closed.
- **The stdout cap makes `shell` an error result.** The brief lists
  timeout among tool errors and says non-zero exit isn't one; it doesn't
  mention the cap. A capped command was stopped by the runner and its
  output is cut, so I treat it like the timeout. The exit code is still
  `null`, and stdout and stderr are kept.
- **Two caps that aren't in the brief:**
  - `shell` stdout is capped at 256 KiB, carry probe's number. The
    seam's 16 MiB default is far too much to hand a model.
  - `read_file` refuses a file over the same 256 KiB and says to read
    it in parts with `shell`.
- **The cage rules are strict on purpose:**
  - Every absolute path is refused, including one that points inside
    the home.
  - Every `..` component is refused, including one that would stay
    inside.
  - Symlinks are resolved, and the result must stay inside the home.
  - A symlink that stays inside is followed, and the result reports the
    resolved path.
- **`Sandbox.as_json()` carries `reason` only when the network is
  unconfined.** That's the brief's literal wording. When the network is
  off the six pinned keys appear and nothing else.
- **`env=` semantics.** A given `env` replaces the inherited PATH/LANG
  pair. Any other variables it carries do pass, since that's the
  sandbox being "told to pass" them. HOME and TMPDIR are always the
  sandbox's. `ANTHROPIC_API_KEY` is dropped even when passed, and the
  drop is logged by name only.
- **Error results keep the tool's pinned keys.** Values the tool
  couldn't know are `null` (`entries` is `[]`, `delivered` is `false`,
  `suspend` is `false`). A call that reached no tool, such as an
  unknown name or a tool that can't load, carries only `name`,
  `content` and `is_error`.
- **Input schemas use a checked subset of JSON Schema, with
  `additionalProperties: false` everywhere.** A schema using any other
  keyword is a `malformed-tool`, so no argument passes through
  unchecked. All seven specs go through R2's `tool_dict` and
  `build_request` unchanged (a test does this).
- **`probe`'s `block` must be the fenced probe block,** as `carry probe`
  finds it. A bare script with no fence is "no probe block". It's
  strict rather than guessing.
- **`shell`'s default timeout is the sandbox maximum (600 s).** That's
  how I read "at most the sandbox's maximum, default 600 s". R4 may want
  a shorter default per call.
- **Test amendment.** `TheStopSet.test_no_runtime_module_spells_a_stop_key`
  (R1) failed because `shell`'s pinned argument `timeout` is also a stop
  key. I didn't hide the string. Instead I added a narrow exemption: in a
  tool's own module, and only there, a constant equal to one of that
  tool's declared argument names is exempt. The test asserts the
  exemption covers exactly `{"timeout"}` today.

## 2. Look closely at

- `twine/runtime/sandbox.py`: `resolve` (the cage) and `spawn` (the
  hook composition, clear-after-no-survivors, fail-closed on an
  unreadable record).
- `twine/runtime/registry.py`: `hold_status` and `runtime_implements`.
  This is where §2.3's check stays strict.
- `twine/commands/carry.py`: the `check_block_ready` split. It's a pure
  move with no behaviour change, and `tests/test_carry.py` is green.
- Existing tests I changed (all expected by the brief's changes):
  - `tests/test_runtime.py`: sandboxing is implemented, so the counts
    move (6/2) and the row now has an `implemented_by` key. Two test
    names changed: `…five_implemented_three_declared` is now
    `…six_implemented_two_declared`, and
    `…declared_three_have_their_contracts_written` is now
    `…declared_two_…`. Plus the stop-key exemption above.
  - `tests/test_registry.py`: the verb set includes `runtime tools`.

## 3. What surprised me

- **This machine runs the work as root, and `unshare -rn` works.** So
  the tests and validation here took the `network: "off"` branch.
  Bale's validation sandbox may refuse nested namespaces. Every
  assertion accepts either branch, as long as `network`, `confines` and
  the argv the runner saw agree. I also ran the new tests, the whole
  suite and `validation.sh` with `unshare` removed from PATH, and
  everything was green on the `unconfined` branch.
- **`Path.mkdir(mode=…, parents=True)` applies the mode only to the
  last directory.** The home is now created 0700 explicitly, and so is
  its `tmp/`.

## 4. Validation

`validation.sh` runs from the staged root under `python3 -I -B`. It
writes `.validation-logs/<ts>/` and one temp dir, which it removes, and
prunes `claude/checkpoints/` from its one tree walk. It took about 80 s
here. Every claim is `observed`. I ran it four times on a rehearsed
staging copy (the base tree plus `files/`, with the manifest at
`.bale-manifest.json`):

- Twice on the final mirror: 19 PASS, 17 claims agree.
- Once on the final mirror with `unshare` off PATH: all PASS on the
  unconfined branch.
- Once on the unmodified tree: the change assertions all FAIL.

Three guard assertions pass on the unmodified tree as well, by nature:
`fixtures/` untouched, seed/`bin/twine`/`share/` untouched, and no
`__pycache__`. The brief pins them as invariants, not as tests of the
change.

## 5. Seed annotation, for tidy9 (verbatim and complete)

Under §5.2, after R2's annotation:

[2026-10-13-twine-runtime-tools-003: R3 landed — the seven canonical
tools (`shell`, `read_file`, `write_file`, `list_dir`, `probe`,
`escalate`, `deliver`) declared in `twine/runtime/tools.toml` (`name`,
`module`, `leaves_cage`), one module each under `twine/runtime/tools/`,
parity by name, rendered by the verb `twine runtime tools [--json]`; each
a `ToolSpec` and an executor whose every failure is a result, never an
exception (`run_tool`). The cage and its rules: one sandbox per sid
(`twine/runtime/sandbox.py`), its home `<state-dir>/sandbox/<sid>/home/`,
every file tool's path resolved inside it — an absolute path, a `..` or a
symlink out refused, naming the cage — and `shell` run there with a
minimal environment (`PATH`, `HOME`, `TMPDIR`, `LANG`; never
`ANTHROPIC_API_KEY`), a timeout capped by the sandbox's maximum and a
256 KiB stdout cap. The network rule and `confines`: `unshare -rn`
detected at creation, every `shell` argv wrapped in it where it works
(`network: "off"`), `network: "unconfined"` and the reason where it does
not; `confines` declared by the sandbox's runner exactly when the network
is off — cli-contract §10.5's switch made. The hook: every spawn
registered with the kill-switch's running record through the run seam's
`on_spawn` when a record exists, and cleared after a run with no
survivor. What leaves the cage: `probe` alone — `carry probe`'s machinery
run read-only against the real repository, with the cage's environment.
`sandboxing` implemented by the runtime itself (`implemented_by`).
`VERSION` 0.18.0.]

Under D13, one sentence:

[2026-10-13-twine-runtime-tools-003: `probe`, `escalate` (light form) and
`deliver` exist as the wrappers it demanded, in `twine/runtime/tools/`.]

## Proposals

- **What:** a mount namespace for `shell`: `unshare -rnm` with the home
  bind-mounted as the only writable tree, and probably `-p --fork` with
  a private `/proc`.
  **Why:** R3's cage confines `shell`'s network and environment, not its
  filesystem. A command can `cd /` and write anywhere the operator's
  user can (runtime-contract §6.3 says so). That's the real gap between
  "cwd'd in the home" and D10's "FS-confined to staging".
  **Scope hints:** `twine/runtime/sandbox.py` (`SandboxRunner.wrap`, the
  detection). Under `-p` the hook's pid becomes the outer `unshare`, so
  §6.7's "the pid is the command's own" changes. Best after R4, once the
  loop exercises the cage.
- **What:** R4's loop should call `register_running` *before*
  `Sandbox.create`.
  **Why:** the detection at creation is a spawn. With the record already
  in place, it's registered like every tool (a test covers that
  ordering).
  **Scope hints:** R4's spawn sequence.
- **What:** a lifecycle for sandbox homes: who removes
  `<state-dir>/sandbox/<sid>/`, and whether `twine status` lists
  `sandbox/` beside `running/` and `inflight/`.
  **Why:** R3 creates homes and never removes one. They'll accumulate
  under the state directory, one per session.
  **Scope hints:** `twine/commands/core.py` (status),
  `twine/runtime/sandbox.py`. Probably tied to the `aborted` and normal
  closures.
- **What:** decide whether the `probe` tool's helpers (`choose_block`,
  `check_block_ready`, `run_probe`, `verify_output`) move out of
  `twine/commands/carry.py` into a non-command module, say
  `twine/probing.py`.
  **Why:** the runtime now imports a command module to reuse them. It
  works and there's no cycle, but it's the first runtime→commands edge.
  **Scope hints:** `twine/commands/carry.py`,
  `twine/runtime/tools/probe.py`.

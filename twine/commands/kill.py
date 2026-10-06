"""`twine kill SID` — the operator's one line for the kill-switch (D15; Arc 1
session 5b).

    twine kill SID [--state-dir DIR] [--cwd DIR] [--bale-root DIR]
                   [--grace SECONDS] [--json]

Thin over twine/kill.py's `kill_session`, the same functions the Arc 2 loop
will call: it requests the between-calls abort, kills every process group
the session's runtime recorded — its own, then each it registered — and
waits until none of them is alive, then closes the session in bale with the
closure reason `aborted` — `bale unlock <sid> --reason aborted --json`,
through the run seam (ctx.run) and only with the pinned bale. When it
cannot finish, the report says where it stopped and gives the one line that
finishes by hand.

Refused before anything is done, every reason named at once: SID is not a
session id (relay_argv's rule); no state directory (resolved as the spend
verbs resolve it, cli-contract.md §13.2), or one that does not exist — a
kill never creates the directory it reports to, since an abort written
where the runtime does not look stops nothing; `--cwd` is not a directory;
`--grace` is not a non-negative number of at most 600 seconds.

The bale is located first, so the report says what was found, but a bale
that is absent, unreadable or not the pin is **not a refusal** (session 5c,
the sitting's correction to 5b): the abort request and the process kill run
with any bale or none — D15's kill must work when the harness itself is
wedged, and an install drifted off the pin is one way it can be. The pin
gates the closure alone, which `close_aborted` checks itself: such a kill
ends `stopped_at: "closure"`, not ok, with the drive refusal in `reason`
and the unlock line to finish by hand (D2, D17: the pin exists for the
closure's vocabulary, not for the signal).

No module here spawns a process: bale runs through ctx.run, and signals go
through twine.process's group helpers. The contract is
claude/context/cli-contract.md §14.
"""

from __future__ import annotations

import argparse
import math
import os
import stat

from twine import bale, kill, spend
from twine.cli import Context
from twine.commands.carry_bale import BALE_ROOT_ARGUMENT, resolve_cwd
from twine.registry import Argument, Command, Result


def parse_grace(text: str) -> float:
    """--grace: a finite, non-negative number of seconds, at most
    kill.MAX_GRACE_SECONDS (a kill that waits for days is not one)."""
    try:
        value = float(text.strip())
    except (ValueError, AttributeError):
        raise ValueError(f"--grace {text!r} is not a number of seconds") from None
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"--grace {text!r} is not a finite, non-negative number "
                         "of seconds")
    if value > kill.MAX_GRACE_SECONDS:
        raise ValueError(f"--grace {text!r} is more than "
                         f"{kill.MAX_GRACE_SECONDS:g} seconds")
    return value


def state_dir_fault(path) -> str | None:
    """Why `path` is not a state directory to kill in, or None when it is
    one: it does not exist, is not a directory, or cannot be looked at (no
    search permission on a parent, say) — a named refusal, never a
    traceback (session 5c, found by its review)."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return "does not exist"
    except OSError as exc:
        return f"cannot be read ({exc.strerror or exc})"
    return None if stat.S_ISDIR(st.st_mode) else "is not a directory"


def cmd_kill(ctx: Context, args: argparse.Namespace) -> Result:
    """Collect every refusal first; do nothing unless there is none; then the
    three steps, each reported on stderr as it happens."""
    report = kill.KillReport(sid=args.sid)
    if not kill.is_sid(args.sid):
        report.refusals.append(
            f"{args.sid!r} is not a session id twine passes to bale (a letter or "
            "digit, then letters, digits, `.`, `_`, `-`; at most "
            f"{kill.MAX_SID_LENGTH} characters)")
    try:
        where = spend.resolve_state_dir(args.state_dir, ctx.env)
        report.state_dir, report.state_dir_source = where.path, where.source
        fault = state_dir_fault(where.path)
        if fault is not None:
            report.refusals.append(
                f"the state directory {where.path} (from {where.source}) {fault}"
                " — the runtime writes its running record there and the loop reads "
                "its abort request there, so a kill reported anywhere else stops "
                "nothing; name the runtime's with --state-dir or $TWINE_STATE_DIR "
                "(a session that never ran under twine has nothing to kill: "
                "close it with `bale unlock <sid> --reason aborted`)")
    except spend.SpendError as exc:
        report.refusals.append(exc.message)
    report.cwd = resolve_cwd(args.cwd, report.refusals)
    try:
        report.grace_seconds = parse_grace(args.grace)
    except ValueError as exc:
        report.refusals.append(str(exc))
    # The bale is located first so the report says what was found, but its
    # drive refusal does not join `refusals`: the pin gates the closure
    # alone (close_aborted checks it), never the abort or the signal.
    executable = bale.locate_executable(args.bale_root, ctx.env, ctx.which)
    report.bale = executable.as_json()
    if report.refusals:
        for problem in report.refusals:
            ctx.info(problem)
        ctx.info(f"kill {args.sid}: refused; nothing was done")
        return Result(False, report.as_json(), report.lines())
    assert report.state_dir is not None and report.grace_seconds is not None
    if executable.drive_refusal is not None:
        ctx.info(f"kill {args.sid}: {executable.drive_refusal} — the abort and the "
                 "process kill go ahead; the closure will not")
    ctx.info(f"kill {args.sid}: requesting the abort in {report.state_dir}, then "
             f"killing every recorded process group (grace {report.grace_seconds:g}s), "
             f"then closing it in bale (in {report.cwd})")
    kill.kill_session(report.state_dir, args.sid, run=ctx.run,
                      executable=executable, cwd=report.cwd, env=ctx.env,
                      grace=report.grace_seconds, report=report)
    for line in report.lines()[1:]:
        ctx.info(line.strip())
    closure = report.closure
    if closure is not None and closure.stderr:
        ctx.info("bale's stderr follows")
        ctx.stderr.write(closure.stderr if closure.stderr.endswith("\n")
                         else closure.stderr + "\n")
    return Result(report.ok, report.as_json(), report.lines())


COMMANDS = (
    Command(
        name="kill",
        summary="the kill-switch: request the between-calls abort, kill every "
                "process group the session's runtime recorded, and close it in "
                "bale as `aborted`",
        handler=cmd_kill,
        arguments=(
            Argument(("sid",), {
                "metavar": "SID",
                "help": "the session to kill (its bale session id)"}),
            Argument(("--state-dir",), {
                "metavar": "DIR", "default": None,
                "help": "twine's state directory, holding abort/ and running/ "
                        "(it must exist: the runtime's); else $TWINE_STATE_DIR, "
                        "else ${XDG_STATE_HOME:-$HOME/.local/state}/twine"}),
            Argument(("--cwd",), {
                "metavar": "DIR", "default": None,
                "help": "the repo whose session SID is, where bale runs (default: "
                        "the current directory)"}),
            BALE_ROOT_ARGUMENT,
            Argument(("--grace",), {
                "metavar": "SECONDS", "default": str(kill.DEFAULT_GRACE_SECONDS),
                "help": "how long the group has between SIGTERM and SIGKILL "
                        f"(default {kill.DEFAULT_GRACE_SECONDS:g}, at most "
                        f"{kill.MAX_GRACE_SECONDS:g})"}),
        ),
        description="Request the between-calls abort for SID in twine's state "
                    "directory (durable, idempotent); if the session's runtime "
                    "recorded its process groups, SIGTERM each — the runtime's "
                    "own first, then every group it registered — SIGKILL it after "
                    "--grace seconds, and wait until no member of any is alive — "
                    "or name the survivors and stop; then, only when nothing of "
                    "them is alive, close the session in bale with `bale unlock "
                    "SID --reason aborted --json`, run in --cwd with the pinned "
                    "bale, once. The abort and the kill run with any bale or "
                    "none; only the closure needs the pin. ok when all three "
                    "landed. Otherwise the report says where it stopped and gives "
                    "the one line that finishes by hand. twine never reverts, "
                    "merges or applies anything."),
)

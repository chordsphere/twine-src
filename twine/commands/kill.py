"""`twine kill SID` — the operator's one line for the kill-switch (D15; Arc 1
session 5b).

    twine kill SID [--state-dir DIR] [--cwd DIR] [--bale-root DIR]
                   [--grace SECONDS] [--json]

Thin over twine/kill.py's `kill_session`, the same functions the Arc 2 loop
will call: it requests the between-calls abort, kills the process group the
session's runtime recorded and waits until none of it is alive, then closes
the session in bale with the closure reason `aborted` — `bale unlock <sid>
--reason aborted --json`, through the run seam (ctx.run) and only with the
pinned bale. When it cannot finish, the report says where it stopped and
gives the one line that finishes by hand.

Refused before anything is done, every reason named at once: SID is not a
session id (relay_argv's rule); no state directory (resolved as the spend
verbs resolve it, cli-contract.md §13.2), or one that does not exist — a
kill never creates the directory it reports to, since an abort written
where the runtime does not look stops nothing; `--cwd` is not a directory;
`--grace` is not a non-negative number of at most 600 seconds; no bale, or
not the pinned one (D2).
The pin is checked before the abort is requested, so an unpinned bale
refuses the whole kill rather than leaving a half-done one (brief item 1).

No module here spawns a process: bale runs through ctx.run, and signals go
through twine.process's group helpers. The contract is
claude/context/cli-contract.md §14.
"""

from __future__ import annotations

import argparse
import math

from twine import kill, spend
from twine.cli import Context
from twine.commands.carry_bale import BALE_ROOT_ARGUMENT, locate, resolve_cwd
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
        if not where.path.is_dir():
            report.refusals.append(
                f"the state directory {where.path} (from {where.source}) "
                f"{'is not a directory' if where.path.exists() else 'does not exist'}"
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
    executable = locate(ctx, args, report.refusals)
    report.bale = executable.as_json()
    if report.refusals:
        for problem in report.refusals:
            ctx.info(problem)
        ctx.info(f"kill {args.sid}: refused; nothing was done")
        return Result(False, report.as_json(), report.lines())
    assert report.state_dir is not None and executable.path is not None
    assert report.grace_seconds is not None
    ctx.info(f"kill {args.sid}: requesting the abort in {report.state_dir}, then "
             f"killing any recorded process group (grace {report.grace_seconds:g}s), "
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
        summary="the kill-switch: request the between-calls abort, kill the "
                "session's recorded process group, and close it in bale as "
                "`aborted`",
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
                    "recorded a process group, SIGTERM it, SIGKILL it after "
                    "--grace seconds, and wait until no member is alive — or name "
                    "the survivors and stop; then, only when nothing of it is "
                    "alive, close the session in bale with `bale unlock SID "
                    "--reason aborted --json`, run in --cwd with the pinned bale, "
                    "once. ok when all three landed. Otherwise the report says "
                    "where it stopped and gives the one line that finishes by "
                    "hand. twine never reverts, merges or applies anything."),
)

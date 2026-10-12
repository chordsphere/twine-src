"""`twine carry bundle` — the courier carries a planner's bundle into bale
and hands back what opens the worker's chat (Arc 1 session 3, row 3,
"offline courier — emit"; twine-seed.md §5.1).

    twine carry bundle BUNDLE [--check] [--cwd DIR] [--bale-root DIR]
                              [--state-dir DIR] [--json]

twine runs `bale open` itself (brief ruling 1): an open merges nothing — it
packs a session, and an unwanted one is closed with `bale unlock` — so,
unlike `carry response`, the plain invocation acts and `--check` rehearses.
The argv is exactly `bale open <bundle> --json`, or with `--check` exactly
`bale open --check <bundle> --json` (twine.bale.open_argv, the only place an
`open` argv is built), run once through the seam (ctx.run) in `--cwd` with a
1800-second timeout — an open runs the bundle's checkpoint dry-run, which
may run a whole suite — and **never retried**: an open that timed out may or
may not have opened a session, and `bale status` is how to tell.

ok exactly when bale exits 0 and prints one JSON object whose `outcome` is
`opened` or `second-desk` (without `--check`) or `rehearsed` (with it) and,
for the first two, whose `sid` is one twine accepts (twine.kill.is_sid) and
whose `opener` is a non-empty string. Then, for `opened` and `second-desk`
only, the open is recorded in twine's state directory —
`<state-dir>/inflight/<sid>.json` (twine/inflight.py) — and human stdout is
exactly bale's `opener`: what the operator pastes into the new chat, beside
the request tarball the diagnostics name. A record that cannot be written
after a successful open does not make the verb not ok (the session is open
in bale; a failure that invited a retry would open another desk): `record`
is null and `record_error` says why.

A refusal bale prints (since bale 0.4.50: outcome `open-refused`, exit 1, a
`reason` code and a `cause`) is NOT OK, the reason naming bale's code and
quoting its cause whole, never dispatching on the cause's wording; nothing
is recorded (session 2026-10-12-twine-bundle-051-004). Under --check the
same.

Refused before bale starts, every reason named at once: BUNDLE empty, or —
when it names no existing file — beginning with `-`; `--cwd` not a
directory (or the current directory gone); no bale found or startable, or
one the gate does not admit (D2: below the floor, or schemas that do not
hash as pinned — the floor since session 2026-10-12-twine-pin-floor-002);
and, without `--check` only, no state directory resolving
(as `twine spend` and `twine kill` resolve it) or one that exists and is not
a directory — an open that could not be recorded is refused before it
happens. `--check` needs no state directory and never reads or writes one.

Since session 2026-10-12-twine-pin-floor-002 the line must also carry every
key the consumption manifest lists for the open surface
(twine.bale.missing_keys_failure); a line lacking one is not ok, its reason
naming the key and the surface — and, after an open, saying the session may
be open, since no record is written for a line twine did not accept.

The contract is claude/context/cli-contract.md §15.

Sections:
  1. Limits and names            (~line 85)
  2. What the verb learned       (~line 110)
  3. The verb                    (~line 200)
  4. Refusals before bale        (~line 240)
  5. Reading bale's line         (~line 305)
  6. The record                  (~line 390)
  7. Rendering                   (~line 445)
  8. The registry entry          (~line 485)
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from twine import bale, inflight, kill, spend
from twine.cli import Context
from twine.commands.carry_bale import (BALE_ROOT_ARGUMENT, CWD_ARGUMENT, BaleCall,
                                       call_bale, locate, passthrough_lines, resolve_cwd)
from twine.commands.kill import state_dir_fault
from twine.registry import Argument, Command, Result

log = logging.getLogger("twine.carry_bundle")

# ---------------------------------------------------------------------------
# 1. Limits and names
# ---------------------------------------------------------------------------

# The verb's registered name, which is also how the consumption manifest's
# open surface names its reader (`read_by`): bale.missing_keys_failure finds
# the keys the line owes by it (session 2026-10-12-twine-pin-floor-002).
READER = "carry bundle"
# An open runs the bundle's checkpoint dry-run, which may run a whole suite:
# 300 seconds (the other bale calls' limit) is too short (brief §2.3).
BUNDLE_TIMEOUT_SECONDS = 1800.0
# The outcome --check wants (format_open_json; recorded at bale 0.4.51):
# nothing written.
REHEARSED = "rehearsed"
# bale's refusal line (bale 0.4.50 on; recorded at 0.4.51 as
# open_bundle_--json+open-refused.json, exit 1): `reason` one code of bale's
# OPEN_REFUSAL_REASONS, `cause` bale's sentence — the `[bale] error:` text on
# stderr. carry bundle names the code and quotes the cause whole, and
# dispatches on neither: the cause's wording is bale's and may change
# (session 2026-10-12-twine-bundle-051-004).
OPEN_REFUSED = "open-refused"
# What state_dir_fault says of a path that is simply absent: the one fault
# carry bundle does not refuse — the record's writer creates the directory.
STATE_DIR_ABSENT = "does not exist"


# ---------------------------------------------------------------------------
# 2. What the verb learned
# ---------------------------------------------------------------------------


@dataclass
class BundleOutcome:
    """Everything `carry bundle` learned; rendered once as the JSON twin
    (cli-contract.md §15.5) and once as human lines."""

    name: str
    check: bool
    bundle: str | None = None
    refusals: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    call: BaleCall = field(default_factory=BaleCall)
    open: dict[str, Any] | None = None
    cwd: str | None = None
    state_dir: Path | None = None
    state_dir_source: str | None = None
    bale: dict[str, Any] | None = None
    tarball: str | None = None
    tarball_source: str | None = None
    record: str | None = None
    record_error: str | None = None

    def _field(self, key: str) -> Any:
        return None if self.open is None else self.open.get(key)

    @property
    def outcome(self) -> Any:
        return self._field("outcome")

    @property
    def sid(self) -> Any:
        return self._field("sid")

    @property
    def desk(self) -> Any:
        return self._field("desk")

    @property
    def opener(self) -> Any:
        return self._field("opener")

    @property
    def ok(self) -> bool:
        return not self.refusals and self.call.ran and not self.failures

    @property
    def opened(self) -> bool:
        """ok, and bale opened a session at a desk (not a rehearsal)."""
        return self.ok and self.outcome in inflight.RECORDED_OUTCOMES

    @property
    def reason(self) -> str | None:
        problems = self.refusals + self.failures
        return "; ".join(problems) if problems else None

    def payload(self) -> dict[str, Any]:
        """The JSON twin beside `command` and `ok` (cli-contract.md §15.5).
        Every key is present on every path — refused, not ok, ok — the
        uncomputed values null."""
        call = self.call.report()
        return {
            "bundle": self.bundle,
            "check": self.check,
            "ran": call.pop("ran"),
            "exit_code": call.pop("exit_code"),
            "open": self.open,
            "outcome": self.outcome,
            "sid": self.sid,
            "desk": self.desk,
            "tarball": self.tarball,
            "tarball_source": self.tarball_source,
            "opener": self.opener,
            "record": self.record,
            "record_error": self.record_error,
            "stderr": call.pop("stderr"),
            "reason": self.reason,
            "refusals": self.refusals,
            **call,
            "cwd": self.cwd,
            "state_dir": None if self.state_dir is None else str(self.state_dir),
            "state_dir_source": self.state_dir_source,
            "bale": self.bale,
        }


# ---------------------------------------------------------------------------
# 3. The verb
# ---------------------------------------------------------------------------


def cmd_carry_bundle(ctx: Context, args: argparse.Namespace) -> Result:
    """Collect every refusal first; start bale only when there is none; run
    the one open argv once; read its line; record an open; hand back the
    opener."""
    outcome = BundleOutcome(name=args.bundle, check=bool(args.check))
    argument = resolve_bundle(ctx, outcome)
    outcome.cwd = resolve_cwd(args.cwd, outcome.refusals)
    executable = locate(ctx, args, outcome.refusals)
    outcome.bale = executable.as_json()
    if outcome.check:
        if args.state_dir is not None:
            ctx.info("--check needs no state directory; --state-dir is not read")
    else:
        resolve_state(outcome, args.state_dir, ctx.env)
    if not outcome.refusals:
        assert argument is not None and executable.path is not None
        argv = bale.open_argv(executable.path, argument, check=outcome.check)
        outcome.bundle = argument
        outcome.call = call_bale(ctx, argv, outcome.cwd or ".", None, outcome.refusals,
                                 outcome.failures, timeout=BUNDLE_TIMEOUT_SECONDS)
        if outcome.call.timed_out or outcome.call.capped:
            outcome.failures.append(
                "bale was stopped before it finished, so the session may or may not "
                f"be open: `bale status` in {outcome.cwd} says which — twine never "
                "retries an open")
        if outcome.call.ran:
            read_line(outcome, executable.manifest)
        if outcome.opened:
            record(ctx, outcome)
    for problem in outcome.refusals + outcome.failures:
        ctx.info(problem)
    diagnose(ctx, outcome)
    return Result(outcome.ok, outcome.payload(), lines(outcome))


# ---------------------------------------------------------------------------
# 4. Refusals before bale
# ---------------------------------------------------------------------------


def resolve_bundle(ctx: Context, outcome: BundleOutcome) -> str | None:
    """The argument bale gets: an existing file's absolute path (relative to
    twine's current directory, `~` expanded), else the name exactly as
    given, for bale to resolve by its own rules (its current directory, then
    `apply.search_paths` — the bare file name the crafter prints works from
    Downloads). None, with the refusal named, for an empty name or — when it
    names no existing file — one beginning with `-`, which bale could read
    as a flag."""
    name = outcome.name
    if not name:
        outcome.refusals.append("BUNDLE is empty; it names no bundle")
        return None
    try:
        path = bale.absolute_path(name)
    except OSError as exc:   # a relative name, and the current directory is gone
        ctx.info(f"BUNDLE {name!r} cannot be made absolute ({exc.strerror or exc}); "
                 "it is passed as given")
        path = None
    is_file = False
    if path is not None:
        try:
            is_file = Path(path).is_file()
        except OSError as exc:   # a name too long to stat, a directory twine cannot search
            ctx.info(f"cannot tell whether BUNDLE {name!r} is a file here "
                     f"({exc.strerror or exc}); it is passed as given")
    if is_file:
        ctx.info(f"BUNDLE {name} is the file {path}")
        return path
    if name.startswith("-"):
        outcome.refusals.append(
            f"BUNDLE {name!r} names no existing file and begins with `-`, so bale "
            f"could read it as a flag; name the file by a path (./{name})")
        return None
    ctx.info(f"BUNDLE {name} names no file here; it is passed as given, for bale "
             "to resolve (its current directory, then apply.search_paths)")
    return name


def resolve_state(outcome: BundleOutcome, flag: str | None, env) -> None:
    """Without --check: the state directory the record goes in, resolved as
    `twine spend` and `twine kill` resolve it (cli-contract.md §13.2). None
    resolving, or one that exists and is not a directory (or cannot be
    looked at), is a refusal: an open that could not be recorded is refused
    before it happens. One that does not exist yet is fine — the record's
    writer creates it, as spend's writer does."""
    why = ("carry bundle records each open in twine's state directory "
           "(inflight/<sid>.json), and an open that could not be recorded is "
           "refused before it happens; rehearse with --check, which needs none")
    try:
        where = spend.resolve_state_dir(flag, env)
    except spend.SpendError as exc:
        outcome.refusals.append(f"{exc.message} — {why}")
        return
    outcome.state_dir, outcome.state_dir_source = where.path, where.source
    fault = state_dir_fault(where.path)
    if fault is not None and fault != STATE_DIR_ABSENT:
        outcome.refusals.append(f"the state directory {where.path} (from "
                                f"{where.source}) {fault} — {why}")


# ---------------------------------------------------------------------------
# 5. Reading bale's line
# ---------------------------------------------------------------------------


def read_line(outcome: BundleOutcome, manifest: bale.Manifest | None) -> None:
    """bale's stdout must be one JSON object carrying every key the manifest
    lists for the open surface (bale.missing_keys_failure, since session
    2026-10-12-twine-pin-floor-002) whose `outcome` is the mode's —
    `opened` or `second-desk` without --check, `rehearsed` with it — and,
    when it opened, whose `sid` twine accepts and whose `opener` is a
    non-empty string. Whatever it said instead is named; a non-zero exit is
    already a failure (call_bale), and the line is still read and reported.
    A line lacking a listed key after an open says the session may be open
    (it is not recorded: the verb is not ok), as the other unaccepted-open
    failures do.

    A refusal line (`open-refused`, with or without --check — a refused
    rehearsal prints the same line) is named by refusal_failure in place
    of the outcome mismatch: bale's `reason` code and its `cause`, quoted
    whole."""
    try:
        obj = json.loads(outcome.call.stdout)
    except (ValueError, RecursionError):
        obj = None
    if not isinstance(obj, dict):
        shown = outcome.call.stdout.strip()
        outcome.failures.append(
            "bale's stdout was not one JSON object"
            + (f" (it began {shown[:60]!r})" if shown else " (it was empty)"))
        return
    try:
        json.dumps(obj, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError:
        # A lone-surrogate escape (\udcXX: bale wrote a path whose bytes
        # are not UTF-8). Such text can be neither printed nor recorded as
        # bale's, so the line is reported with `?` in its place and the
        # open is not ok; the raw line stays in the twin's `stdout`.
        outcome.open = json.loads(json.dumps(obj, ensure_ascii=False)
                                  .encode("utf-8", "replace").decode("utf-8"))
        outcome.failures.append(
            "bale's line carries text that is not UTF-8 (a lone surrogate escape, "
            "as a path with non-UTF-8 bytes prints), which twine can neither print "
            "nor record as bale's; the session may be open: `bale status` in "
            f"{outcome.cwd} says which — twine never retries an open")
        return
    outcome.open = obj
    lacking = bale.missing_keys_failure(manifest, READER, obj)
    if lacking is not None:
        if not outcome.check and obj.get("outcome") in inflight.RECORDED_OUTCOMES:
            lacking += (f"; the session may be open: `bale status` in {outcome.cwd} "
                        "says which — twine never retries an open, and records none "
                        "from a line it did not accept")
        outcome.failures.append(lacking)
    if obj.get("outcome") == OPEN_REFUSED:
        outcome.failures.append(refusal_failure(obj))
        return
    wanted = (REHEARSED,) if outcome.check else inflight.RECORDED_OUTCOMES
    if obj.get("outcome") not in wanted:
        mode = "--check wants" if outcome.check else "an open wants"
        outcome.failures.append(f"bale reported outcome {obj.get('outcome')!r}; "
                                f"{mode} {' or '.join(map(repr, wanted))}")
        return
    if outcome.check:
        return
    if not kill.is_sid(obj.get("sid")):
        outcome.failures.append(f"bale's {obj['outcome']} line has no sid twine "
                                f"accepts (sid {obj.get('sid')!r})")
    opener = obj.get("opener")
    if not isinstance(opener, str) or not opener:
        outcome.failures.append(f"bale's {obj['outcome']} line has no opener "
                                f"(opener {opener!r})")


def refusal_failure(line: dict[str, Any]) -> str:
    """The failure an `open-refused` line makes: bale's `reason` code named
    and its `cause` quoted whole — bale's only account of why — as `carry
    exchange` names a `relay-refused` line. Neither is dispatched on; a code
    or cause that is absent, null, empty or not a string is said to be
    missing rather than guessed at."""
    code = line.get("reason")
    cause = line.get("cause")
    named = f"reason {code!r}" if isinstance(code, str) and code else "no reason code"
    quoted = (f'"{cause}"' if isinstance(cause, str) and cause
              else "its line names no cause")
    return f"bale refused the open (outcome {OPEN_REFUSED!r}, {named}): {quoted}"


# ---------------------------------------------------------------------------
# 6. The record
# ---------------------------------------------------------------------------


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def record(ctx: Context, outcome: BundleOutcome) -> None:
    """Record the open (twine/inflight.py) and settle the tarball the desk
    needs: bale's when its line gives one, else — for a second desk — the
    record's. (What the record itself keeps is inflight._compose's: on an
    appended second desk its own tarball when set, else bale's.) A record
    that cannot be written leaves the verb ok: `record` null, `record_error`
    naming why, a warning on stderr."""
    assert outcome.open is not None and outcome.state_dir is not None
    line = outcome.open
    bundle = line.get("bundle")
    bundle_sha256 = _text_or_none(bundle.get("sha256")) if isinstance(bundle, dict) else None
    bales = _text_or_none(line.get("tarball"))
    recorded_tarball: str | None = None
    try:
        written = inflight.record_open(
            outcome.state_dir, outcome.sid, outcome=outcome.outcome,
            cwd=outcome.cwd or "", tarball=bales, desk=_text_or_none(line.get("desk")),
            bundle_sha256=bundle_sha256, opener=outcome.opener)
    except inflight.InflightError as exc:
        outcome.record_error = (f"{exc.message} — the session is open in bale, so "
                                "this is not a failure and nothing is retried (a retry "
                                "would open another desk)")
        ctx.info(f"warning: the open was not recorded: {outcome.record_error}")
        if exc.found is not None:
            recorded_tarball = exc.found["tarball"]
    else:
        outcome.record = str(written.path)
        outcome.record_error = written.fresh
        recorded_tarball = written.record["tarball"]
        if written.replaced:
            ctx.info(f"an earlier in-flight record of {outcome.sid} was replaced by this "
                     f"open ({written.path})")
        if written.fresh:
            ctx.info(f"warning: {written.fresh}")
        if bales is not None and recorded_tarball not in (None, bales):
            ctx.info(f"the in-flight record keeps its own tarball {recorded_tarball}; "
                     f"bale's line names {bales}")
    if bales is not None:
        outcome.tarball, outcome.tarball_source = bales, "bale"
    elif outcome.outcome == inflight.SECOND_DESK and recorded_tarball is not None:
        outcome.tarball, outcome.tarball_source = recorded_tarball, "record"


# ---------------------------------------------------------------------------
# 7. Rendering
# ---------------------------------------------------------------------------


def diagnose(ctx: Context, outcome: BundleOutcome) -> None:
    """stderr, on an open: the sid, the desk, the tarball to attach (or
    that none is known), and where the record is (or why it is not)."""
    if outcome.ok and not outcome.opened:
        ctx.info(f"rehearsed: bale would open {outcome.bundle}; nothing was written")
        return
    if not outcome.opened:
        return
    desk = outcome.desk if outcome.desk is not None else "the first desk"
    ctx.info(f"{outcome.outcome}: session {outcome.sid}, {desk}")
    if outcome.tarball is not None:
        ctx.info(f"attach the request tarball: {outcome.tarball} (from "
                 f"{outcome.tarball_source})")
    else:
        ctx.info(f"no request tarball is known for {outcome.sid}: bale's line names "
                 "none and no in-flight record holds one")
    if outcome.record is not None:
        ctx.info(f"in-flight record: {outcome.record}")
    else:
        ctx.info(f"in-flight record not written: {outcome.record_error}")
    ctx.info("stdout is bale's opener: paste it into the new chat")


def lines(outcome: BundleOutcome) -> list[str]:
    """stdout without --json: on an open exactly bale's opener (a final LF
    supplied if it lacked one); on a rehearsal one line; otherwise one line
    naming why."""
    if outcome.opened:
        return passthrough_lines(outcome.opener)
    if outcome.ok:
        return [f"carry bundle {outcome.name}: {REHEARSED} — bale would open it "
                "(nothing written)"]
    state = "NOT OK" if outcome.call.ran else "refused"
    return [f"carry bundle {outcome.name}: {state} — {outcome.reason}"]


# ---------------------------------------------------------------------------
# 8. The registry entry
# ---------------------------------------------------------------------------

COMMANDS = (
    Command(
        name=READER,
        summary="open a planner's bundle with `bale open --json`; print the opener "
                "to paste, name the request tarball, and record the open",
        handler=cmd_carry_bundle,
        arguments=(
            Argument(("bundle",), {
                "metavar": "BUNDLE",
                "help": "the bundle file (made absolute when it exists here), or the "
                        "name bale resolves from its search paths; a name beginning "
                        "with `-` goes after `--`"}),
            Argument(("--check",), {
                "action": "store_true",
                "help": "rehearse: `bale open --check`, nothing written anywhere — "
                        "no session, no record, no state directory needed"}),
            CWD_ARGUMENT,
            BALE_ROOT_ARGUMENT,
            Argument(("--state-dir",), {
                "metavar": "DIR", "default": None,
                "help": "twine's state directory, where the open is recorded "
                        "(inflight/<sid>.json; created if absent); else "
                        "$TWINE_STATE_DIR, else ${XDG_STATE_HOME:-$HOME/.local/state}"
                        "/twine. Not read under --check"}),
        ),
        description="Run `bale open BUNDLE --json` (with --check, `bale open --check "
                    "BUNDLE --json`) once, in --cwd, with a bale the gate admits. ok when "
                    "bale exits 0 and prints one JSON object whose outcome is "
                    "\"opened\" or \"second-desk\" (\"rehearsed\" under --check) with "
                    "a sid and an opener. On an open, stdout is exactly bale's opener "
                    "— paste it into the new chat and attach the request tarball "
                    "stderr names — and the open is recorded in twine's state "
                    "directory, inflight/<sid>.json. A refusal bale prints "
                    "(\"open-refused\") is NOT OK, naming bale's reason code and "
                    "quoting its cause. Never retried: an open that "
                    "timed out may or may not have opened a session (`bale status` "
                    "says which)."),
)

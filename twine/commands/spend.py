"""The `spend` verbs (Arc 1 session 5a, D15's cost spine without the
kill-switch): `twine spend totals` renders the spend stream, and `twine
spend check` is the hard cap's pre-call check, run by hand.

Both are thin over twine/spend.py — the same `spend_totals` and
`check_call` the Arc 2 loop will call — so the loop never re-implements
the check (brief item 7). This module only resolves where things are,
parses the command line exactly (a cap is a Decimal, a count an int) and
renders.

Neither verb writes anything: the stream is appended to by the loop
(`twine.spend.append_record`), and the price file is the operator's. No
network, no subprocess, no provider SDK; `ctx.run` is never called. The
contract is claude/context/cli-contract.md §13.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from twine import spend
from twine.cli import Context
from twine.registry import Argument, Command, Result


def _state_dir_argument() -> Argument:
    return Argument(("--state-dir",), {
        "metavar": "DIR", "default": None,
        "help": "twine's state directory, holding spend.jsonl (and prices.toml "
                "unless --prices); else $TWINE_STATE_DIR, else "
                "${XDG_STATE_HOME:-$HOME/.local/state}/twine"})


def _prices_argument() -> Argument:
    return Argument(("--prices",), {
        "metavar": "PATH", "default": None,
        "help": "the operator's price file (US dollars per million tokens, one "
                "[model.\"<id>\"] table per model); else <state-dir>/prices.toml. "
                "twine ships no prices"})


def _where(ctx: Context, args: argparse.Namespace) -> tuple[spend.StateDir | None,
                                                            spend.SpendError | None]:
    try:
        where = spend.resolve_state_dir(args.state_dir, ctx.env)
        spend.resolve_prices_path(args.prices, where.path)   # refuses an empty --prices
        return where, None
    except spend.SpendError as exc:
        ctx.info(exc.message)
        return None, exc


def _paths(where: spend.StateDir | None, prices_flag: str | None) -> dict[str, Any]:
    """The location keys every spend payload carries: resolved, or null
    where the state directory itself could not be resolved."""
    if where is None:
        prices = None
        if prices_flag and prices_flag.strip():
            prices = str(spend.resolve_prices_path(prices_flag, Path())[0])
        return {"state_dir": None, "state_dir_source": None, "stream": None,
                "prices": prices, "prices_source": "--prices" if prices else None}
    prices_path, prices_source = spend.resolve_prices_path(prices_flag, where.path)
    return {"state_dir": str(where.path), "state_dir_source": where.source,
            "stream": str(where.stream), "prices": str(prices_path),
            "prices_source": prices_source}


# ---------------------------------------------------------------------------
# twine spend totals
# ---------------------------------------------------------------------------


def cmd_spend_totals(ctx: Context, args: argparse.Namespace) -> Result:
    """Render the running totals per session. Not ok, naming why, on a
    malformed or unreadable stream, a missing or malformed price file, or
    an unpriced model; an empty or absent stream is ok with no sessions."""
    where, error = _where(ctx, args)
    if where is None:
        # The same keys as any report, the locations null: built from an
        # empty report so the twin's key set never depends on the path taken.
        report = spend.TotalsReport(state_dir=Path(), stream=Path(), sid=args.sid)
        report.refuse(error)
        payload = {**report.as_json(), "total_cost_usd": None, "stream_present": False,
                   **_paths(None, args.prices)}
        return Result(False, payload, [f"spend totals: refused ({error.kind}) — "
                                       f"{error.message}"])
    prices_path, _ = spend.resolve_prices_path(args.prices, where.path)
    report = spend.spend_totals(where.path, prices_path, args.sid)
    payload = {**report.as_json(), **_paths(where, args.prices)}
    for problem in report.problems[:spend.MAX_REPORTED_PROBLEMS]:
        ctx.info(f"{report.stream}: {problem}")
    if not report.ok:
        ctx.info(f"spend totals: {report.refusal}: {report.reason}")
    return Result(report.ok, payload, totals_lines(report))


def totals_lines(report: spend.TotalsReport) -> list[str]:
    """The human rendering: a verdict line, then one block per session."""
    scope = f" for {report.sid}" if report.sid else ""
    if not report.stream_present:
        head = f"spend totals{scope}: no spend recorded ({report.stream} is absent)"
    elif report.ok:
        calls = sum(s.calls for s in report.sessions)
        head = (f"spend totals{scope}: {calls} call(s) over {len(report.sessions)} "
                f"session(s); the whole stream {spend.dollars(report.total_cost_usd)} "
                f"({report.records} record(s) in {report.stream})")
    else:
        head = f"spend totals{scope}: NOT OK ({report.refusal}) — {report.reason}"
    lines = [head]
    if report.ok and report.stream_present and not report.sessions:
        lines.append(f"  no records for {report.sid}" if report.sid
                     else "  no records")
    for s in report.sessions:
        t = s.tokens
        lines.append(f"  {s.sid}: {s.calls} call(s), {spend.dollars(s.cost_usd)} own, "
                     f"{spend.dollars(s.served_cost_usd)} served by "
                     f"{s.served_calls} call(s) of other sessions")
        lines.append("    tokens: " + ", ".join(
            f"{name} {'null' if t[name] is None else t[name]}"
            for name in spend.TOKEN_CLASSES))
    for problem in report.problems[:spend.MAX_REPORTED_PROBLEMS]:
        lines.append(f"  {problem}")
    if len(report.problems) > spend.MAX_REPORTED_PROBLEMS:
        lines.append(f"  … and {len(report.problems) - spend.MAX_REPORTED_PROBLEMS} "
                     "more line problem(s)")
    return lines


# ---------------------------------------------------------------------------
# twine spend check
# ---------------------------------------------------------------------------


def cmd_spend_check(ctx: Context, args: argparse.Namespace) -> Result:
    """The hard cap's pre-call check, by hand. ok (exit 0) exactly when the
    call is admitted; refused by the cap, `stop` is "cap-reached"; any
    other refusal names its own reason, and is never an admission."""
    faults, values = [], {}
    for name, flag, parse in (("cap_usd", "--cap", spend.parse_usd),
                              ("input_tokens", "--input", spend.parse_count),
                              ("max_output_tokens", "--max-output", spend.parse_count)):
        try:
            values[name] = parse(getattr(args, name))
        except ValueError as exc:
            faults.append(f"{flag}: {exc}")
            values[name] = None
    where, error = _where(ctx, args)
    if where is None or faults:
        if faults:
            error = spend.SpendError("bad-argument", "; ".join(faults))
            ctx.info(error.message)
        # The same keys as any check, the uncomputed ones null.
        check = spend.CallCheck(sid=args.sid, model=args.model, cap_usd=values["cap_usd"],
                                input_tokens=values["input_tokens"],
                                max_output_tokens=values["max_output_tokens"],
                                state_dir=Path(), stream=Path(), prices=Path())
        check.refuse(error)
        payload = {**check.as_json(), **_paths(where, args.prices)}
        return Result(False, payload, check_lines(check))
    prices_path, _ = spend.resolve_prices_path(args.prices, where.path)
    check = spend.check_call(where.path, sid=args.sid, cap_usd=values["cap_usd"],
                             model=args.model, input_tokens=values["input_tokens"],
                             max_output_tokens=values["max_output_tokens"],
                             prices_path=prices_path)
    payload = {**check.as_json(), **_paths(where, args.prices)}
    if not check.admitted:
        ctx.info(f"spend check {check.sid}: {check.refusal}: {check.reason}")
    return Result(check.admitted, payload, check_lines(check))


def check_lines(check: spend.CallCheck) -> list[str]:
    """The human rendering: one verdict line, then the numbers."""
    if check.admitted:
        head = f"spend check {check.sid}: admitted"
    elif check.refusal == "cap-reached":
        head = (f"spend check {check.sid}: REFUSED (cap-reached) — the call is not made, "
                "and it is not shrunk to fit")
    else:
        head = (f"spend check {check.sid}: NOT CHECKED ({check.refusal}; stop "
                f"{check.stop}) — {check.reason}; the call is not made")
    lines = [head]
    if check.projected_usd is not None:
        relation = "<=" if check.admitted else ">"
        lines.append(f"  spend so far {spend.dollars(check.spend_so_far_usd)} "
                     f"(own {spend.dollars(check.own_cost_usd)} over "
                     f"{check.calls_so_far} call(s), served "
                     f"{spend.dollars(check.served_cost_usd)}) + worst case "
                     f"{spend.dollars(check.worst_case_usd)} = "
                     f"{spend.dollars(check.projected_usd)} {relation} cap "
                     f"{spend.dollars(check.cap_usd)}")
        lines.append(f"  worst case: {check.input_tokens} input token(s) at "
                     f"{check.input_price_class} {spend.dollars(check.input_price)}/MTok "
                     f"+ {check.max_output_tokens} output token(s) at "
                     f"{spend.dollars(check.output_price)}/MTok on {check.model}")
    for problem in check.problems[:spend.MAX_REPORTED_PROBLEMS]:
        lines.append(f"  {problem}")
    return lines


COMMANDS = (
    Command(
        name="spend totals",
        summary="the spend stream's running totals: per session, calls, tokens by "
                "class, and cost at the operator's prices",
        handler=cmd_spend_totals,
        arguments=(
            Argument(("--sid",), {"metavar": "SID", "default": None,
                                  "help": "only this session's row (the stream's "
                                          "total stays the whole stream's)"}),
            _state_dir_argument(),
            _prices_argument(),
        ),
        description="Read <state-dir>/spend.jsonl, twine's append-only usage record "
                    "(one line per model call), and render per session: the call "
                    "count, the five token classes summed (input, output, thinking, "
                    "cache_read, cache_write), the cost of its own calls and the cost "
                    "of calls that served it, at the prices in the operator's price "
                    "file. twine ships no prices: an unpriced model, a malformed "
                    "line (named by number) or a malformed price file is not ok, "
                    "exit 1, never an estimate or a skip. An empty or absent stream "
                    "is ok with no sessions. Writes nothing."),
    Command(
        name="spend check",
        summary="the hard cap's pre-call check: admit a call only if spend so far "
                "plus its worst-case cost is at most the cap",
        handler=cmd_spend_check,
        arguments=(
            Argument(("--sid",), {"metavar": "SID", "required": True,
                                  "help": "the session the call would run in"}),
            Argument(("--cap",), {"metavar": "USD", "required": True,
                                  "dest": "cap_usd",
                                  "help": "the session's hard cap, in US dollars"}),
            Argument(("--model",), {"metavar": "MODEL", "required": True,
                                    "help": "the model id the call would run on"}),
            Argument(("--input",), {"metavar": "N", "required": True,
                                    "dest": "input_tokens",
                                    "help": "the call's input tokens (all priced at "
                                            "the model's dearest input-side price)"}),
            Argument(("--max-output",), {"metavar": "N", "required": True,
                                         "dest": "max_output_tokens",
                                         "help": "the call's output bound, thinking "
                                                 "included (priced at output)"}),
            _state_dir_argument(),
            _prices_argument(),
        ),
        description="Admit the call (exit 0) exactly when the session's spend so far "
                    "— its own calls' cost plus the cost of calls that served it — "
                    "plus the call's worst-case cost is at most --cap. Refused by "
                    "the cap: exit 1, `stop` \"cap-reached\", the numbers that "
                    "decided it; the call is never shrunk to fit. An unpriced "
                    "model, an unreadable or malformed stream, a missing or "
                    "malformed price file or a bad argument is also exit 1, with "
                    "its own refusal and `stop` \"cap-unchecked\", and never an "
                    "admission. Writes nothing."),
)

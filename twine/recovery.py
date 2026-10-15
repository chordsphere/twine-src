"""Recovery: what a kept session says about how to go on (twine-run-recovery;
cli-contract.md §18.5, §18.7, §19; runtime-contract.md §7.9).

`twine run` and `twine resume` end on a transcript, a spend stream and a
sandbox home that stay. This module reads them — it writes nothing, starts no
bale and calls no model — and answers the questions the operator used to
answer by hand when a session was cut short:

  read_story(path) -> Story
      the transcript's last `run-end` twin (its outcome, stop, move, actor,
      reason, and for a refused delivery the tarball and the dry run's
      line), the last `window` line and the last ten tool calls. A `run-start`
      after a `run-end` means a run began and did not end: the last outcome
      is then unknown (None), as it is for a run that died of an internal
      error. Lines are read as `transcript.read_lines` reads them — a log,
      never trusted as a record.

  advise(state_dir, sid, conversation, window, prices_path) -> Advice
      the session's spend, priced as `twine spend totals --sid` prices it
      (the session's own cost and what served it, each record at its
      model's row — the sum the cap check compares); the mean of the last
      ten calls; the pre-call check's worst case for the next call, priced
      as the check prices it (the input estimate of the rebuilt conversation
      plus `RESUME_TEXT`, at the dearest input-side price, and the whole
      `max_tokens` at the output price); and a **suggested cap** (below).
      Every figure that cannot be priced is None, with `problem` saying why:
      a number is never estimated from prices twine does not have.

  next_commands(...) -> list[str]
      the command each ending names (cli-contract.md §18.7): the apply line
      on `delivered`; for a refused delivery (`scope-drift-refused`) bale's
      own admit line built from the dry run's `drift` — never run by twine
      (T12) — and the resume line that returns the work to the worker; the
      resume line, carrying a suggested cap, for the endings a resume
      continues; nothing for `killed` (a kill stays a close: the respawn
      path is said in words) and for `window-exhausted` (the planner's
      split).

  parse_cap(text) -> CapSpec, resolve_cap(...)
      `--cap`: dollars, or `+<dollars>` — the session's spend so far plus
      that amount.

**The suggested cap** is a number of dollars at two decimals, strictly above
the session's spend plus the next call's worst case — so the resumed run's
first call is admitted — and, above that floor, this rule (the desk's hand
rule for twine-run-ergonomics' recovery):

    spend so far
    + a re-warm of the window at the cache-write price   (the first call of
      a resumed run re-writes the conversation: window tokens in use, or
      the input estimate when no call counted a window)
    + 40 calls at the mean of the last ten calls
    + the next call's worst case
    rounded up to the cent, and one cent more when that is not above the floor.

With no calls yet the forty-call term is 0 (there is no mean to price it
with). Nothing here spells a stop key: the loop's constants are read from
`twine.runtime.loop`.
"""

from __future__ import annotations

import dataclasses
import logging
import shlex
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from twine import bale, spend, transcript as transcripts
from twine.runtime import loop as runloop
from twine.runtime.registry import DeclarationError
from twine.runtime.resume import RESUME_TEXT, Conversation
from twine.runtime.tooling import load_tool_registry

log = logging.getLogger("twine.recovery")

# How many of the transcript's last tool calls a plan shows, and the width
# of each one's `what` (runtime.loop.tool_argument's cut).
LAST_TOOLS = 10
WHAT_CHARS = 110
# The mean cost per call is taken over this many of the session's last
# records, and a resumed run is given this many calls of headroom.
MEAN_OVER = 10
HEADROOM_CALLS = 40
CENT = Decimal("0.01")
PLUS = "+"

# The outcomes a resume continues, and the two it does not (a delivered
# session's record is removed; a killed one is closed in bale).
DELIVERED = runloop.DELIVERED
KILLED = runloop.KILLED
SUSPENDED = runloop.SUSPENDED
# `--answer` may be absent on every outcome except this one: a suspended
# worker waits for an answer, and the others only need to be told to go on.
ANSWER_REQUIRED_ON = (SUSPENDED,)
# bale's dry-run outcome that names the admit line (consumption manifest's
# apply surface note).
SCOPE_DRIFT = "scope-drift-refused"
ADMIT_FLAG = "--allow-out-of-scope"


# ---------------------------------------------------------------------------
# 1. The transcript's story
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Story:
    """What recovery reads off a transcript: the last run's end (its twin;
    None when the last run did not end, or ended on an internal error), the
    last `window` line's `used`, `size` and `fraction` (None before any),
    and the last tool calls."""

    end: Mapping[str, Any] | None
    window: Mapping[str, Any] | None
    tools: tuple[dict[str, Any], ...]

    @property
    def outcome(self) -> str | None:
        value = None if self.end is None else self.end.get("outcome")
        return value if isinstance(value, str) else None

    def field(self, name: str) -> Any:
        return None if self.end is None else self.end.get(name)


def read_story(path: Path) -> Story:
    end: Mapping[str, Any] | None = None
    window: Mapping[str, Any] | None = None
    tools: list[dict[str, Any]] = []
    for line in transcripts.read_lines(path):
        kind = line.get("kind")
        if kind == "run-start":
            end = None
        elif kind == "run-end":
            twin = line.get("twin")
            end = twin if isinstance(twin, dict) else None
        elif kind == "window":
            window = {"used": line.get("used"), "size": line.get("size"),
                      "fraction": line.get("fraction")}
        elif kind == "tool-call":
            arguments = line.get("arguments")
            name = line.get("name")
            what = (runloop.tool_argument(name, arguments, WHAT_CHARS)
                    if isinstance(name, str) and isinstance(arguments, dict) else "")
            tools.append({"call": line.get("call"), "name": name, "what": what})
    return Story(end=end, window=window, tools=tuple(tools[-LAST_TOOLS:]))


# ---------------------------------------------------------------------------
# 2. The cap, as given
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CapSpec:
    """`--cap` as typed: `given` the text, `amount` its dollars, `relative`
    when it was `+<dollars>` (the session's spend so far plus the amount)."""

    given: str
    amount: Decimal
    relative: bool

    def absolute(self, spent: Decimal | None) -> Decimal | None:
        """The cap in dollars: the amount, or the spend so far plus it —
        None when a relative cap has no priced spend to add to."""
        if not self.relative:
            return self.amount
        return None if spent is None else spent + self.amount


def parse_cap(text: str) -> CapSpec:
    """`5`, `0.25` or `+2.50`. Raises ValueError (naming the text) for
    anything that is not a finite, non-negative number of dollars after an
    optional leading `+`."""
    stripped = text.strip() if isinstance(text, str) else text
    relative = isinstance(stripped, str) and stripped.startswith(PLUS)
    body = stripped[len(PLUS):] if relative else stripped
    try:
        if relative and body[:1] in ("+", "-", " ", "\t"):
            raise ValueError("a sign or a space after the +")
        amount = spend.parse_usd(body)
    except ValueError:
        raise ValueError(f"{text!r} is not a number of US dollars, or +<dollars> (the "
                         "session's spend so far plus that amount)") from None
    return CapSpec(given=stripped, amount=amount, relative=relative)


# ---------------------------------------------------------------------------
# 3. The money
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Advice:
    """The session's money and what a resume should be given: each figure
    None when it cannot be priced (`problem` says why — the first thing that
    could not be read or priced)."""

    calls: int | None = None
    spent: Decimal | None = None
    per_call: Decimal | None = None
    worst: Decimal | None = None
    rewarm: Decimal | None = None
    suggested: Decimal | None = None
    problem: str | None = None

    def arithmetic(self) -> str | None:
        """The suggestion's sum, in words, for the human rendering; None
        when there is no suggestion."""
        if self.suggested is None:
            return None
        headroom = (self.per_call or Decimal(0)) * HEADROOM_CALLS
        mean = ("no mean yet, so 0" if self.per_call is None
                else f"{HEADROOM_CALLS} calls at {spend.dollars(self.per_call)}")
        return (f"spend so far {spend.dollars(self.spent)} + re-warm of the window at the "
                f"cache-write price {spend.dollars(self.rewarm)} + {mean} "
                f"({spend.dollars(headroom)}) + the next call's worst case "
                f"{spend.dollars(self.worst)}, rounded up to the cent")


def round_up_to_cent(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_CEILING)


def read_spend(state_dir: Path, sid: str, prices_path: Path | None
               ) -> tuple[int | None, Decimal | None, Decimal | None,
                          spend.PriceTable | None, str | None]:
    """(calls, spend so far, mean of the last ten calls, the price table,
    problem). `calls` counts the sid's own records; the spend is the cap
    check's — own cost plus what served the session — and is 0 with no
    record of the sid (nothing to price, so no price file needed). A
    record whose model has no row, an unreadable stream or an unreadable
    price file leaves the figures it touches None, never a partial sum."""
    path = Path(prices_path) if prices_path else Path(state_dir) / spend.PRICES_NAME
    stream = spend.read_stream(Path(state_dir) / spend.STREAM_NAME)
    fault = stream.refusal()
    if fault is not None:
        return None, None, None, None, fault.message
    relevant = [r for r in stream.records if sid in (r.sid, r.served_sid)]
    own = [r for r in relevant if r.sid == sid]
    try:
        prices = spend.load_prices(path)
    except spend.SpendError as exc:
        return len(own), (None if relevant else Decimal(0)), None, None, exc.message
    unpriced = prices.unpriced(r.model for r in relevant)
    if unpriced:
        return (len(own), None, None, prices,
                f"no price row for {', '.join(repr(m) for m in unpriced)} in {path}")
    sessions, _ = spend.accumulate(relevant, prices)
    total = sessions.get(sid, spend.SessionTotals(sid)).spend_so_far_usd
    tail = own[-MEAN_OVER:]
    per_call = (sum((spend.record_cost(r, prices.models[r.model]) for r in tail),
                    Decimal(0)) / len(tail)) if tail else None
    return len(own), total, per_call, prices, None


def spend_so_far(state_dir: Path, sid: str, prices_path: Path | None
                 ) -> tuple[Decimal | None, str | None]:
    """The session's spend as the cap check counts it, and why not when it
    cannot be priced — what a `+<dollars>` cap adds to."""
    _, total, _, _, problem = read_spend(state_dir, sid, prices_path)
    if total is None and problem is None:
        problem = "the session's spend could not be priced"
    return total, problem


def advise(state_dir: Path, sid: str, conversation: Conversation,
           window: Mapping[str, Any] | None, prices_path: Path | None) -> Advice:
    """The session's money and the suggested cap (module docstring)."""
    advice = Advice()
    calls, total, per_call, prices, problem = read_spend(state_dir, sid, prices_path)
    advice.calls, advice.spent, advice.per_call, advice.problem = calls, total, per_call, problem
    start = conversation.run_start
    price = None if prices is None else prices.models.get(start.model)
    if price is None:
        advice.problem = advice.problem or (
            f"no price row for {start.model!r}: the next call cannot be priced")
        return advice
    try:
        prompt = runloop.system_prompt(load_tool_registry())
    except (DeclarationError, OSError, ValueError) as exc:
        advice.problem = advice.problem or f"the tool registry cannot be read: {exc}"
        return advice
    estimate = runloop.estimate_input_tokens(
        prompt, [*conversation.messages, runloop.user_message(RESUME_TEXT)])
    advice.worst = spend.worst_case_cost(price, estimate, start.max_tokens)
    used = None if window is None else window.get("used")
    in_window = used if type(used) is int and used > 0 else estimate
    advice.rewarm = in_window * price.cache_write / spend.PER_MILLION
    if total is None:
        return advice
    floor = total + advice.worst
    headroom = (per_call or Decimal(0)) * HEADROOM_CALLS
    suggested = round_up_to_cent(total + advice.rewarm + headroom + advice.worst)
    advice.suggested = suggested if suggested > floor else suggested + CENT
    return advice


# ---------------------------------------------------------------------------
# 4. The commands an ending names
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Carried:
    """The flags a run was given that its resume line carries: the state
    directory, bale's root, the repo, and the price file (the suggested cap
    was priced from it). Each only when it was given."""

    state_dir: str | None = None
    bale_root: str | None = None
    cwd: str | None = None
    prices: str | None = None

    @classmethod
    def of(cls, args: Any) -> "Carried":
        return cls(state_dir=getattr(args, "state_dir", None),
                   bale_root=getattr(args, "bale_root", None),
                   cwd=getattr(args, "cwd", None), prices=getattr(args, "prices", None))

    def tokens(self) -> list[str]:
        flags = (("--state-dir", self.state_dir), ("--bale-root", self.bale_root),
                 ("--cwd", self.cwd), ("--prices", self.prices))
        return [token for flag, value in flags if value
                for token in (flag, shlex.quote(value))]


def resume_line(sid: str, cap: str | None, carried: Carried, *,
                answer_stdin: bool = False) -> str:
    """`twine resume SID --cap CAP` with the carried flags, and `--answer -`
    for the light block's answer; without a cap, `--plan` instead — the
    command that reads the session and suggests one."""
    parts = ["twine", "resume", shlex.quote(sid)]
    parts += ["--plan"] if cap is None else ["--cap", cap]
    if answer_stdin and cap is not None:
        parts += ["--answer", "-"]
    parts += carried.tokens()
    return " ".join(parts)


def admit_line(tarball: str, dry_run: Mapping[str, Any] | None) -> str | None:
    """bale's own admit line for a delivery its dry run refused as
    `scope-drift-refused`: `bale apply <tarball> --allow-out-of-scope <path>`
    once per path of the line's `drift.out_of_scope_paths` (bale's refusal
    prints the same line, one flag per drifted path) — the `bale apply
    <tarball>` part is `twine.bale.apply_line`'s, the one place an apply line
    is spelled. None for any other outcome, or when the line names no path.
    Twine never runs it (T12)."""
    if not isinstance(dry_run, Mapping) or dry_run.get("outcome") != SCOPE_DRIFT:
        return None
    drift = dry_run.get("drift")
    paths = drift.get("out_of_scope_paths") if isinstance(drift, Mapping) else None
    if not tarball or not isinstance(paths, list) or not paths:
        return None
    if not all(isinstance(p, str) and p for p in paths):
        return None
    return " ".join([bale.apply_line(tarball),
                     *(f"{ADMIT_FLAG} {shlex.quote(p)}" for p in paths)])


def next_commands(sid: str, *, outcome: str | None, stop: str | None, move: str | None = None,
                  apply_line: str | None = None, light_block: bool = False,
                  tarball: str | None = None, dry_run: Mapping[str, Any] | None = None,
                  suggested: Decimal | None, carried: Carried,
                  plannable: bool = True) -> list[str]:
    """The `next` list of an ending (cli-contract.md §18.7, §19.4). With no
    suggested cap the resume line is `twine resume SID --plan` — the command
    that says why — unless `plannable` is False (the plan itself is asking:
    a plan whose next line is a plan names nothing)."""
    if outcome == DELIVERED:
        return [apply_line] if apply_line else []
    if outcome == SUSPENDED:
        if apply_line:
            return [apply_line]
        cap = None if suggested is None else f"{suggested:.2f}"
        if cap is None and not plannable:
            return []
        return [resume_line(sid, cap, carried, answer_stdin=True)] if light_block else []
    if outcome in (KILLED, runloop.REFUSED) or stop in (KILLED, runloop.WINDOW_EXHAUSTED):
        return []
    cap = None if suggested is None else f"{suggested:.2f}"
    if cap is None and not plannable:
        return []
    again = resume_line(sid, cap, carried)
    admit = admit_line(tarball or "", dry_run)
    return [admit, again] if admit else [again]


# What a kill is, and the way on: said in the refusal and in the human end.
KILLED_WAY = ("`twine kill` closes the session in bale as `aborted` (`bale unlock --reason "
              "aborted`), so a resumed worker could rebuild the conversation but no response "
              "it delivered could be dry-run or applied under that sid — a kill stays a "
              "close. The way on is the planner's respawn from the original request with a "
              "failure note (the table's move respawn-from-request)")


def killed_refusal(sid: str) -> str:
    """Why `twine resume` refuses a session whose last run ended `killed`: a
    kill is a close (cli-contract.md §14.5), and the way on is a respawn."""
    return f"{sid} was killed: {KILLED_WAY}"


def no_command_words(sid: str | None, outcome: str | None, stop: str | None) -> str | None:
    """The way on, in words, for the endings that name no command: `killed`
    (a respawn) and `window-exhausted` (the planner's split). None for any
    other."""
    who = sid or "the session"
    if outcome == KILLED:
        return f"killed: no resume line — {KILLED_WAY}"
    if stop == runloop.WINDOW_EXHAUSTED:
        return (f"window-exhausted: no resume line — {who}'s window is used up, and a resume "
                "would re-warm the same conversation; the way on is the planner's split "
                "(the table's move split-goal)")
    return None


def departures_note(tarball: str | None) -> str:
    """The human line that goes with an admit line: bale's own reminder that
    the response's notes.md enumerates the departures, and that the line is
    the operator's to run."""
    return ("the departures from the write forecast are enumerated in the response's "
            "notes.md"
            + (f" ({tarball})" if tarball else "")
            + "; the `bale apply` line below admits them deliberately — twine never runs it")


__all__ = ["ADMIT_FLAG", "Advice", "CapSpec", "Carried", "HEADROOM_CALLS", "Story",
           "admit_line", "advise", "departures_note", "killed_refusal", "next_commands",
           "no_command_words", "parse_cap",
           "read_spend", "read_story", "resume_line", "round_up_to_cent", "spend_so_far"]

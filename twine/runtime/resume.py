"""Cold resume: a kept session's conversation rebuilt from its transcript
(Arc 2 R5; D23, TQ-1, twine-seed.md §4.3 "Suspension and cold resume";
claude/context/runtime-contract.md §7.9).

D23: a worker blocked on an escalation goes cold — its cache expires, and it
re-warms on the answer. Nothing of it is held hot: what a resume needs is the
transcript `twine run` wrote, append-only (TQ-1), whose `request` lines each
carry `appended`, the messages added since the line before — so the lines'
`appended` lists, joined, are the conversation as sent, the `sent: false`
line after the turn that ended a run carrying what was never sent. This
module reads that back:

  read_conversation(path) -> Conversation
      every complete line read as JSON, in order; a line that is not JSON, a
      torn last line, a `request` line whose `appended` is not a list of
      messages, or whose `messages_total` disagrees with the conversation
      joined so far, refuses (ResumeError, every fault named) — a resume
      never re-warms a conversation it cannot vouch for. A `run-start` line
      without `resumed_from` begins a new conversation (a second desk's
      `twine run` starts over from the opener); one with it continues the
      last. The conversation is the last one: its messages, the constants
      of its last `run-start` (adapter, model, max_tokens, thinking — D12's
      spawn-time constants a resume is held to), and the `seq` of the
      transcript's last line, which the resumed run's `run-start` names as
      `resumed_from`.

The verb is `twine resume` (twine/commands/resume.py, cli-contract.md §19):
it appends one user message — the answer — and runs the loop again with
`Loop(messages=…, logged=…)`, so its first `request` line carries only that
message and the cached prefix is the conversation unchanged (the
capability's promise: a resume appends and never edits an earlier turn).

The runtime implements suspend-resume itself, not an adapter: the
declaration's `implemented_by` names this module (runtime-contract.md
§2.1). An adapter's part is to accept the rebuilt conversation as a prefix
with the settings it was spawned with — which every adapter does, since
each call already carries the whole conversation. Nothing here spawns,
reaches a network, reads the environment or spells a stop key.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("twine.runtime.resume")

# The runtime implements this capability itself: twine/runtime/
# capabilities.toml's `implemented_by` names this module, and the registry
# holds the declaration to this tuple (runtime-contract.md §2.3).
IMPLEMENTS = ("suspend-resume",)

# The user message `twine resume` appends when no answer is given, byte for
# byte (twine-run-recovery): a run that was stopped needs telling to go on,
# not answering. Spelled once; `validation.sh` of the session that landed it
# holds it to these bytes, and the transcript's `run-start` `answer` object
# says `source: "twine"` when it was sent.
RESUME_TEXT = "This session was stopped and has been resumed; continue from where you left off."
# The `source` a `run-start`'s `answer` carries for it.
RESUME_SOURCE = "twine"

# The transcript's line kinds a rebuild reads (twine/runtime/loop.py and
# twine/commands/run.py write them; runtime-contract.md §7.6).
RUN_START = "run-start"
REQUEST = "request"
ROLES = ("user", "assistant")
# The run-start constants a resume is held to (D12) and spawns with.
CONSTANTS = ("adapter", "model", "max_tokens", "thinking")


class ResumeError(ValueError):
    """A transcript a resume cannot rebuild a conversation from. `faults`
    lists every reason."""

    def __init__(self, path: Path, faults: list[str]) -> None:
        super().__init__(f"the transcript {path} cannot be resumed from: " + "; ".join(faults))
        self.path = path
        self.faults = list(faults)


@dataclass(frozen=True)
class RunStart:
    """A `run-start` line's spawn-time constants, as `twine run` wrote them:
    the adapter's name, the model, the output ceiling and the thinking
    choice (`adaptive` or `off`), and the line's `seq`."""

    seq: int
    adapter: str
    model: str
    max_tokens: int
    thinking: str

    def as_json(self) -> dict[str, Any]:
        return {"seq": self.seq, "adapter": self.adapter, "model": self.model,
                "max_tokens": self.max_tokens, "thinking": self.thinking}


@dataclass(frozen=True)
class Conversation:
    """What a resume re-warms: the last conversation's messages, joined from
    its `request` lines in order (`sent: false` included); the constants of
    its last `run-start`; the `seq` of the transcript's last line; how many
    `request` lines and runs it spans; and the last line's `messages_total`."""

    messages: tuple[dict[str, Any], ...]
    run_start: RunStart
    last_seq: int
    request_lines: int
    runs: int

    @property
    def messages_total(self) -> int:
        return len(self.messages)


def message_fault(n: int, message: Any) -> str | None:
    """Why `message` is not one the loop wrote (runtime-contract.md §7.3);
    None when it is."""
    if not isinstance(message, dict):
        return f"message {n} is not an object"
    if message.get("role") not in ROLES:
        return f"message {n} has role {message.get('role')!r}, not user or assistant"
    content = message.get("content")
    if not isinstance(content, (str, list)):
        return f"message {n}'s content is neither a string nor a list of blocks"
    if isinstance(content, list) and not all(isinstance(b, dict) for b in content):
        return f"message {n}'s content holds a block that is not an object"
    return None


def _run_start(line: dict[str, Any], faults: list[str]) -> RunStart | None:
    seq = line.get("seq")
    found = []
    for key, kind in (("adapter", str), ("model", str), ("thinking", str)):
        if not isinstance(line.get(key), kind) or not line.get(key):
            found.append(f"its {key} is {line.get(key)!r}, not a non-empty string")
    max_tokens = line.get("max_tokens")
    if type(max_tokens) is not int or max_tokens <= 0:
        found.append(f"its max_tokens is {max_tokens!r}, not a positive integer")
    if found:
        faults.append(f"the run-start line (seq {seq}) cannot be read: " + "; ".join(found))
        return None
    return RunStart(seq=seq, adapter=line["adapter"], model=line["model"],
                    max_tokens=max_tokens, thinking=line["thinking"])


def read_conversation(path: Path) -> Conversation:
    """The last conversation in the transcript at `path`, rebuilt (module
    docstring). Raises ResumeError naming every fault: no such file, a file
    that cannot be read, a line that is not a JSON object, a torn last line,
    no `run-start`, no `request` line since the last fresh one, a `request`
    line that cannot be read or whose `messages_total` disagrees."""
    path = Path(path)
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise ResumeError(path, ["it does not exist"]) from None
    except OSError as exc:
        raise ResumeError(path, [f"it cannot be read: {exc.strerror or exc}"]) from exc
    faults: list[str] = []
    raw_lines = data.split(b"\n")
    if raw_lines and raw_lines[-1]:
        faults.append("its last line is torn (no LF: a run was killed mid-write), so the "
                      "conversation may be missing its tail")
    messages: list[dict[str, Any]] = []
    run_start: RunStart | None = None
    request_lines = runs = 0
    last_seq = 0
    for number, raw in enumerate(raw_lines[:-1], 1):
        if not raw:
            continue
        try:
            line = json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError) as exc:
            faults.append(f"line {number} is not JSON ({exc})")
            continue
        if not isinstance(line, dict):
            faults.append(f"line {number} is not a JSON object")
            continue
        if type(line.get("seq")) is int:
            last_seq = line["seq"]
        kind = line.get("kind")
        if kind == RUN_START:
            if line.get("resumed_from") is None:
                # A fresh run: a new conversation from its opener.
                messages, request_lines, runs = [], 0, 0
            runs += 1
            run_start = _run_start(line, faults) or run_start
        elif kind == REQUEST:
            request_lines += 1
            appended = line.get("appended")
            if not isinstance(appended, list):
                faults.append(f"the request line at line {number} (seq {line.get('seq')}) "
                              "has no `appended` list")
                continue
            bad = [f for i, m in enumerate(appended, 1)
                   if (f := message_fault(i, m)) is not None]
            if bad:
                faults.append(f"the request line at line {number} (seq {line.get('seq')}) "
                              "carries a message the loop never wrote: " + "; ".join(bad))
                continue
            messages.extend(appended)
            total = line.get("messages_total")
            if total != len(messages):
                faults.append(f"the request line at line {number} (seq {line.get('seq')}) "
                              f"says messages_total {total!r}, and the conversation joined "
                              f"so far holds {len(messages)}: a request line is missing or "
                              "out of order")
    if run_start is None:
        faults.append("it has no run-start line twine run wrote")
    elif request_lines == 0:
        faults.append(f"it has no request line after the run-start at seq {run_start.seq}: "
                      "nothing was ever sent, so there is no conversation to re-warm")
    if faults:
        raise ResumeError(path, faults)
    assert run_start is not None
    log.info("transcript %s: %d message(s) from %d request line(s) over %d run(s); last "
             "seq %d", path, len(messages), request_lines, runs, last_seq)
    return Conversation(messages=tuple(messages), run_start=run_start, last_seq=last_seq,
                        request_lines=request_lines, runs=runs)


__all__ = ["CONSTANTS", "Conversation", "IMPLEMENTS", "RESUME_SOURCE", "RESUME_TEXT",
           "ResumeError", "RunStart", "message_fault", "read_conversation"]

"""Bale shapes in text: find every block a courier carries, parse it,
verify its integrity, and report — executing nothing (twine-seed.md
§4.3 "turn-end detection and shape classification"; Arc 1 session 2a).

Pure: text in, `Report` out. Nothing here runs, writes, imports bale,
or reaches a network; `twine take` (twine/commands/take.py) is the verb
over it, and `twine carry probe` (twine/commands/carry.py, session 2b-i)
reads both the pasted turn and the probe's stdout through the same
Report — one parser for every courier verb.

The five kinds, each a *span* between whole-line sentinels:

  probe         a fenced code block whose first lines carry the
                crafter's header `# PROBE <slug>: …` (TARBALL.md §4.2)
  probe-output  `=== PROBE BEGIN <slug> ===` … `=== PROBE END <slug> ===`
                with `--- integrity: N lines ---` as its last inner line
  light         `=== LIGHT BEGIN <sid> ===` … `=== LIGHT END <sid> ===`
                (TARBALL.md §5.10)
  exchange      `BALE EXCHANGE BEGIN <sid>` … `BALE EXCHANGE END`, sha256
                trailer (TARBALL.md §5.9.2; bale's parse_exchange_input)
  relay         `=== RELAY BEGIN <sid> to <planner|worker> ===` …
                `=== RELAY END <sid> to <same> ===` (bale's relay_sentinels)

Spans do not nest: once one opens, every line until its own END is its
content, whatever it looks like. A relay block routinely quotes notes
that would otherwise read as other shapes, and a probe's output
routinely carries the blocks it recorded. Sentinels are whole lines:
the `===` ones match from column 0 (bale's _inline_lines defuses an
inlined sentinel by indenting it two spaces, so indentation must mean
"not a sentinel"); the exchange ones tolerate surrounding whitespace,
as bale's parser does. Trailing whitespace is tolerated everywhere.

A fenced code block that is not a probe is transparent: the shapes
inside it are found (bale's own parser ignores "a chat's fence lines").

Sections:
  1. Sentinels and constants       (~line 55)
  2. The report model              (~line 115)
  3. Input normalization           (~line 180)
  4. The scanner                   (~line 220)
  5. Per-kind parsers              (~line 355)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("twine.shapes")

# ---------------------------------------------------------------------------
# 1. Sentinels and constants
# ---------------------------------------------------------------------------

PROBE = "probe"
PROBE_OUTPUT = "probe-output"
LIGHT = "light"
EXCHANGE = "exchange"
RELAY = "relay"
KINDS = (PROBE, PROBE_OUTPUT, LIGHT, EXCHANGE, RELAY)
PROSE = "prose"   # the shape of a turn that carries no block

# `===` sentinels, matched against a line with trailing whitespace removed.
PROBE_BEGIN = re.compile(r"=== PROBE BEGIN (\S+) ===")
PROBE_END = re.compile(r"=== PROBE END (\S+) ===")
LIGHT_BEGIN = re.compile(r"=== LIGHT BEGIN (\S+) ===")
LIGHT_END = re.compile(r"=== LIGHT END (\S+) ===")
RELAY_BEGIN = re.compile(r"=== RELAY BEGIN (\S+) to (planner|worker) ===")
RELAY_END = re.compile(r"=== RELAY END (\S+) to (planner|worker) ===")

# Exchange sentinels, matched against a stripped line (bale_relay.py's
# parse_exchange_input strips; the BEGIN's remainder is the sid).
EXCHANGE_BEGIN = "BALE EXCHANGE BEGIN"
EXCHANGE_BEGIN_LINE = re.compile(r"BALE EXCHANGE BEGIN(?:\s+(.*))?")
EXCHANGE_END = "BALE EXCHANGE END"
# bale_relay.py's _EXCHANGE_TRAILER_RE, verbatim, matched on a stripped line.
EXCHANGE_TRAILER = re.compile(r"^#\s*sha256:?\s+([0-9a-fA-F]{64})\s*$")
# The body serialization bale renders (_exchange_body_bytes): two-space
# indent, ASCII escaping, one trailing newline.
EXCHANGE_BODY_INDENT = 2

# The probe-output trailer the crafter's emit_probe_block prints.
INTEGRITY_TRAILER = re.compile(r"--- integrity: (\d+) lines ---")

# A fence: up to three spaces, three or more backticks, an info string
# without backticks (CommonMark). A closing fence has at least as many
# backticks and nothing after them.
FENCE_OPEN = re.compile(r" {0,3}(`{3,})([^`]*)")
FENCE_CLOSE = re.compile(r" {0,3}(`{3,})\s*")
# The crafter's probe header line; "first lines" is this many lines in.
PROBE_HEADER = re.compile(r"#\s*PROBE\s+(\S+?):(?:\s.*)?")
PROBE_HEADER_WINDOW = 5
# The purpose header's read-only declaration (TARBALL.md §4.2: the header
# "confirming the script is read-only"; the crafter's third header line is
# `# Read-only: writes nothing anywhere; stdout is the only output.`). A
# declaration with nothing after the colon declares nothing.
PROBE_READ_ONLY = re.compile(r"#\s*Read-only:\s*\S.*")
# The crafter's unfilled-placeholder sentinel: an unfilled scaffold carries
# it on four lines ("unfilled probe placeholder — not ready to paste").
UNFILLED_SENTINEL = "TODO(worker)"

# TARBALL.md §5.10's four labels, in order, onto the question-row fields
# of a clarification manifest (the same fields --emit-block carries).
LIGHT_LABELS = (("question", "question"), ("while doing", "context"),
                ("would assume", "default_assumption"),
                ("why blocked", "why_blocked"))
LIGHT_ENTRY = re.compile(r"\[(\d+)\]\s+question:\s*(.*)")
LIGHT_CONTINUATION = re.compile(r"\s+(while doing|would assume|why blocked):\s*(.*)")
LIGHT_REPLY_PREFIX = "Reply:"

# ---------------------------------------------------------------------------
# 2. The report model
# ---------------------------------------------------------------------------


@dataclass
class Block:
    """One block found in the input.

    `start_line`/`end_line` are 1-based and inclusive, counted in the
    normalized input (the END sentinel's line, or the last input line
    when the span never closed). `fields` carries the per-kind identity
    and parse results; `integrity` always has `ok` and `basis`;
    `error` is set exactly when `integrity["ok"]` is false.
    """

    kind: str
    start_line: int
    end_line: int
    fields: dict[str, Any] = field(default_factory=dict)
    integrity: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.integrity.get("ok"))

    def fail(self, error: str, **integrity: Any) -> "Block":
        """Mark this block not-ok with the reason, in both places."""
        self.integrity.update(integrity)
        self.integrity["ok"] = False
        self.error = error
        return self

    def as_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        out.update(self.fields)
        out["start_line"] = self.start_line
        out["end_line"] = self.end_line
        out["integrity"] = self.integrity
        if self.error is not None:
            out["error"] = self.error
        return out


@dataclass
class Report:
    """Every block in input order, and the turn's shape: the kind of the
    last block (the shape the turn ended in, AGENT.md §3), or "prose"."""

    blocks: list[Block]

    @property
    def shape(self) -> str:
        return self.blocks[-1].kind if self.blocks else PROSE

    @property
    def ok(self) -> bool:
        return all(b.ok for b in self.blocks)

    def as_json(self) -> dict[str, Any]:
        return {"shape": self.shape,
                "blocks": [b.as_json() for b in self.blocks]}


# ---------------------------------------------------------------------------
# 3. Input normalization
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Normalized:
    """The input as the scanner reads it, and what normalization did."""

    text: str
    bytes_read: int
    crlf_replaced: int
    bom_stripped: bool


def normalize(data: bytes) -> Normalized:
    """Decode UTF-8 (strict; a leading BOM is dropped) and turn every CRLF
    into LF before anything is matched — chat transports add them. A lone
    CR is left alone. Raises ValueError, naming the offset, on bytes that
    are not UTF-8: a courier must not guess at a damaged paste."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"input is not UTF-8 (byte {exc.start}: {exc.reason})") from exc
    bom = text.startswith("﻿")
    if bom:
        text = text[1:]
    crlf = text.count("\r\n")
    return Normalized(text.replace("\r\n", "\n"), len(data), crlf, bom)


def split_lines(text: str) -> list[str]:
    """Lines without their LF; a final LF does not make an empty last line."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


# ---------------------------------------------------------------------------
# 4. The scanner
# ---------------------------------------------------------------------------


def find_blocks(text: str) -> Report:
    """Scan normalized text for every block, in order (no nesting)."""
    return Report(scan(split_lines(text)))


def scan(lines: list[str]) -> list[Block]:
    """Walk the lines once. Outside a span, each line is tried as a BEGIN
    sentinel, a probe fence, a fence of any other kind (transparent), or
    a stray END sentinel (reported: a paste cut at the top). A span's
    parser returns the block and the index after its END."""
    blocks: list[Block] = []
    open_fence: int | None = None   # backtick count of a transparent fence
    i = 0
    while i < len(lines):
        line = lines[i]
        bare = line.rstrip()
        if open_fence is not None and _closes_fence(line, open_fence):
            open_fence = None
            i += 1
            continue
        m = PROBE_BEGIN.fullmatch(bare)
        if m:
            block, i = parse_probe_output(lines, i, m.group(1))
            blocks.append(block)
            continue
        m = LIGHT_BEGIN.fullmatch(bare)
        if m:
            block, i = parse_light(lines, i, m.group(1))
            blocks.append(block)
            continue
        m = RELAY_BEGIN.fullmatch(bare)
        if m:
            block, i = parse_relay(lines, i, m.group(1), m.group(2))
            blocks.append(block)
            continue
        m = EXCHANGE_BEGIN_LINE.fullmatch(line.strip())
        if m:
            block, i = parse_exchange(lines, i, (m.group(1) or "").strip() or None)
            blocks.append(block)
            continue
        if open_fence is None:
            m = FENCE_OPEN.fullmatch(bare)
            if m:
                ticks = len(m.group(1))
                slug = _probe_header_slug(lines, i, ticks)
                if slug is not None:
                    block, i = parse_probe(lines, i, slug, ticks, m.group(2).strip())
                    blocks.append(block)
                else:
                    log.debug("line %d: fence without a probe header; transparent", i + 1)
                    open_fence = ticks
                    i += 1
                continue
        orphan = _orphan_end(line)
        if orphan is not None:
            blocks.append(orphan_block(i, *orphan))
        i += 1
    log.debug("scanned %d lines: %d block(s)", len(lines), len(blocks))
    return blocks


def block_text(text: str, block: Block) -> str:
    """The block's own lines — start_line through end_line of the
    normalized `text` it was found in — LF-joined with one trailing LF:
    exactly the bytes a courier carries for it, and nothing around it."""
    lines = split_lines(text)
    return "\n".join(lines[block.start_line - 1:block.end_line]) + "\n"


def _closes_fence(line: str, ticks: int) -> bool:
    m = FENCE_CLOSE.fullmatch(line)
    return m is not None and len(m.group(1)) >= ticks


def _probe_header_slug(lines: list[str], i: int, ticks: int) -> str | None:
    """The slug from a `# PROBE <slug>:` line among the fence's first
    PROBE_HEADER_WINDOW lines (stopping at its closing fence), or None."""
    for j in range(i + 1, min(i + 1 + PROBE_HEADER_WINDOW, len(lines))):
        if _closes_fence(lines[j], ticks):
            return None
        m = PROBE_HEADER.fullmatch(lines[j].strip())
        if m:
            return m.group(1)
    return None


def _find_end(lines: list[str], start: int, is_end) -> int | None:
    for j in range(start + 1, len(lines)):
        if is_end(lines[j]):
            return j
    return None


def _orphan_end(line: str) -> tuple[str, dict[str, Any]] | None:
    """(kind, identity) when `line` is an END sentinel outside any span."""
    bare = line.rstrip()
    m = PROBE_END.fullmatch(bare)
    if m:
        return PROBE_OUTPUT, {"slug": m.group(1)}
    m = LIGHT_END.fullmatch(bare)
    if m:
        return LIGHT, {"sid": m.group(1)}
    m = RELAY_END.fullmatch(bare)
    if m:
        return RELAY, {"sid": m.group(1), "to": m.group(2)}
    if line.strip() == EXCHANGE_END:
        return EXCHANGE, {"sid": None}
    return None


def orphan_block(i: int, kind: str, identity: dict[str, Any]) -> Block:
    """An END sentinel with no BEGIN: the paste lost its top."""
    block = Block(kind, i + 1, i + 1, dict(identity),
                  {"ok": False, "basis": _basis(kind)})
    return block.fail(f"line {i + 1}: END sentinel with no BEGIN before it — "
                      "the paste is cut at the top; re-request the block")


def _basis(kind: str) -> str:
    return {PROBE_OUTPUT: "line-count", EXCHANGE: "sha256"}.get(kind, "structural")


def _unclosed(block: Block, lines: list[str], what: str) -> tuple[Block, int]:
    """Close an unterminated span at end of input and fail it."""
    block.end_line = len(lines)
    block.fail(f"line {block.start_line}: {what} never closes — the paste is "
               "truncated or its END sentinel was cut; re-request the block")
    return block, len(lines)


# ---------------------------------------------------------------------------
# 5. Per-kind parsers
# ---------------------------------------------------------------------------


def parse_probe(lines: list[str], i: int, slug: str, ticks: int,
                info: str) -> tuple[Block, int]:
    """A fenced probe block: the script is the fence's content, verbatim.
    No trailer (TARBALL.md §4.2's trailer is on the output, not the
    script); an unclosed fence is malformed."""
    block = Block(PROBE, i + 1, i + 1, {"slug": slug, "fence_info": info},
                  {"ok": False, "basis": "structural"})
    end = _find_end(lines, i, lambda ln: _closes_fence(ln, ticks))
    if end is None:
        return _unclosed(block, lines, f"probe {slug}'s code fence")
    block.end_line = end + 1
    body = lines[i + 1:end]
    block.fields["script"] = "\n".join(body) + ("\n" if body else "")
    block.integrity["ok"] = True
    return block, end + 1


def probe_header(script: str) -> list[str]:
    """A probe script's purpose header: its leading run of `#` lines
    (the shebang included), after any leading blank lines — where the
    crafter puts `# PROBE`, `# Why` and `# Read-only`."""
    header: list[str] = []
    for line in split_lines(script):
        if not header and not line.strip():
            continue
        if not line.lstrip().startswith("#"):
            break
        header.append(line)
    return header


def probe_read_only_line(header: list[str]) -> str | None:
    """The header's `# Read-only: …` declaration, or None."""
    for line in header:
        if PROBE_READ_ONLY.fullmatch(line.strip()):
            return line
    return None


def parse_probe_output(lines: list[str], i: int, slug: str) -> tuple[Block, int]:
    """A probe's pasted output. N in the trailer is the number of lines
    between BEGIN and the trailer (the crafter prints `$out` with one
    trailing newline and counts it with `wc -l`); a paste missing or
    gaining a line fails."""
    block = Block(PROBE_OUTPUT, i + 1, i + 1, {"slug": slug},
                  {"ok": False, "basis": "line-count"})
    end_line = f"=== PROBE END {slug} ==="
    end = _find_end(lines, i, lambda ln: ln.rstrip() == end_line)
    if end is None:
        block.integrity.update(expected_lines=None, found_lines=None)
        return _unclosed(block, lines, f"probe output {slug}")
    block.end_line = end + 1
    inner = lines[i + 1:end]
    t = len(inner) - 1
    while t >= 0 and not inner[t].strip():
        t -= 1
    m = INTEGRITY_TRAILER.fullmatch(inner[t].strip()) if t >= 0 else None
    if m is None:
        block.fail(f"probe output {slug} has no `--- integrity: N lines ---` "
                   "trailer as its last inner line — truncated or edited",
                   expected_lines=None, found_lines=len(inner))
        return block, end + 1
    expected, found = int(m.group(1)), t
    block.integrity.update(expected_lines=expected, found_lines=found)
    if expected != found:
        block.fail(f"probe output {slug}: the trailer counts {expected} lines, "
                   f"the paste carries {found} — a line was lost or added in "
                   "transit; re-request the output")
    else:
        block.integrity["ok"] = True
    return block, end + 1


def parse_light(lines: list[str], i: int, sid: str) -> tuple[Block, int]:
    """A light question block (TARBALL.md §5.10). Each entry is four
    labeled lines; the block ends with the packer's reply line. Any other
    line, a missing or out-of-order label, an empty value, or a
    misnumbered entry makes it malformed."""
    block = Block(LIGHT, i + 1, i + 1, {"sid": sid},
                  {"ok": False, "basis": "structural"})
    end_line = f"=== LIGHT END {sid} ==="
    end = _find_end(lines, i, lambda ln: ln.rstrip() == end_line)
    if end is None:
        return _unclosed(block, lines, f"light block {sid}")
    block.end_line = end + 1
    questions, problem = _light_rows(lines, i + 1, end)
    block.fields["questions"] = questions
    if problem:
        block.fail(f"light block {sid}: {problem}")
    else:
        block.integrity["ok"] = True
    return block, end + 1


def _light_rows(lines: list[str], start: int, end: int
                ) -> tuple[list[dict[str, Any]], str | None]:
    """Parse lines[start:end] into question rows keyed by manifest field."""
    rows: list[dict[str, Any]] = []
    expect = 0          # index into LIGHT_LABELS of the next label wanted
    reply_seen = False
    for j in range(start, end):
        raw = lines[j]
        if not raw.strip():
            continue
        where = f"line {j + 1}"
        if reply_seen:
            return rows, f"{where}: content after the reply line"
        entry = LIGHT_ENTRY.fullmatch(raw.strip())
        cont = LIGHT_CONTINUATION.fullmatch(raw.rstrip())
        if entry:
            if expect != 0:
                return rows, f"{where}: entry [{entry.group(1)}] starts before " \
                             f"the previous one's `{LIGHT_LABELS[expect][0]}` line"
            if int(entry.group(1)) != len(rows) + 1:
                return rows, f"{where}: entry numbered [{entry.group(1)}], " \
                             f"expected [{len(rows) + 1}]"
            value = entry.group(2).strip()
            if not value:
                return rows, f"{where}: empty `question`"
            rows.append({"question": value})
            expect = 1
        elif cont:
            label, value = cont.group(1), cont.group(2).strip()
            if expect == 0 or label != LIGHT_LABELS[expect][0]:
                wanted = LIGHT_LABELS[expect][0] if expect else "[n] question"
                return rows, f"{where}: `{label}` where `{wanted}` was expected"
            if not value:
                return rows, f"{where}: empty `{label}`"
            rows[-1][LIGHT_LABELS[expect][1]] = value
            expect = (expect + 1) % len(LIGHT_LABELS)
        elif raw.startswith(LIGHT_REPLY_PREFIX):
            if expect != 0:
                return rows, f"{where}: reply line before entry [{len(rows)}]'s " \
                             f"`{LIGHT_LABELS[expect][0]}` line"
            reply_seen = True
        else:
            return rows, f"{where}: not a labeled row or the reply line: {raw.strip()[:60]!r}"
    if not rows:
        return rows, "no question entries"
    if expect != 0:
        return rows, f"entry [{len(rows)}] has no `{LIGHT_LABELS[expect][0]}` line"
    if not reply_seen:
        return rows, "no `Reply:` line — TARBALL.md §5.10 ends every block with it"
    return rows, None


def parse_relay(lines: list[str], i: int, sid: str, to: str) -> tuple[Block, int]:
    """A relay block bale apply printed. No trailer (relay blocks carry
    none); its integrity is that the END naming the same sid and
    addressee arrives. The content is not parsed: `to` is the routing
    fact (claude/context/cli-contract.md §9.4)."""
    block = Block(RELAY, i + 1, i + 1, {"sid": sid, "to": to},
                  {"ok": False, "basis": "structural"})
    end_line = f"=== RELAY END {sid} to {to} ==="
    end = _find_end(lines, i, lambda ln: ln.rstrip() == end_line)
    if end is None:
        return _unclosed(block, lines, f"relay block {sid} to {to}")
    block.end_line = end + 1
    block.integrity["ok"] = True
    return block, end + 1


def exchange_body_bytes(record: Any) -> bytes:
    """bale's _exchange_body_bytes, re-declared (twine imports no bale)."""
    return (json.dumps(record, indent=EXCHANGE_BODY_INDENT) + "\n").encode("utf-8")


def parse_exchange(lines: list[str], i: int, sid: str | None) -> tuple[Block, int]:
    """An exchange paste block, verified exactly as bale_relay.py's
    parse_exchange_input does: the header is the leading `#` lines, the
    trailer is the last non-blank inner line `# sha256 <hex>`, the body is
    everything between joined with LF plus one trailing LF, and its
    sha256 must equal the trailer's. When it does not but the body
    re-serialized with ASCII escaping does, the fault is named: a carrier
    unescaped the body's \\uXXXX escapes in transit."""
    block = Block(EXCHANGE, i + 1, i + 1,
                  {"sid": sid, "round": None, "from": None},
                  {"ok": False, "basis": "sha256",
                   "expected_sha256": None, "found_sha256": None})
    end = _find_end(lines, i, lambda ln: ln.strip() == EXCHANGE_END)
    if end is None:
        block.integrity["fault"] = "unclosed"
        return _unclosed(block, lines, f"exchange block {sid}")
    block.end_line = end + 1
    nxt = end + 1
    if sid is None:
        block.fail(f"line {i + 1}: `{EXCHANGE_BEGIN}` carries no session id",
                   fault="no-sid")
        return block, nxt
    inner = lines[i + 1:end]
    k = 0
    while k < len(inner) and inner[k].lstrip().startswith("#"):
        k += 1
    if k >= len(inner):
        block.fail(f"exchange block {sid} has a header but no body — truncated",
                   fault="no-body")
        return block, nxt
    t = len(inner) - 1
    while t > k and not inner[t].strip():
        t -= 1
    m = EXCHANGE_TRAILER.match(inner[t].strip())
    body = "\n".join(inner[k:t]) + "\n"
    record = _json_or_none(body)
    if isinstance(record, dict):
        block.fields["round"] = record.get("round")
        block.fields["from"] = record.get("from")
    if m is None:
        block.fail(f"exchange block {sid}: the last inner line is not the "
                   "`# sha256 <hex>` trailer — truncated or edited",
                   fault="no-trailer")
        return block, nxt
    expected = m.group(1).lower()
    found = hashlib.sha256(body.encode("utf-8")).hexdigest()
    block.integrity.update(expected_sha256=expected, found_sha256=found)
    if found != expected:
        if record is not None and hashlib.sha256(
                exchange_body_bytes(record)).hexdigest() == expected:
            block.fail(f"exchange block {sid}: the body's bytes miss the trailer "
                       "but its ASCII-escaped re-serialization matches — a carrier "
                       "unescaped \\uXXXX escapes in transit; re-carry the block "
                       "byte-for-byte (a file, not a rendered message)",
                       fault="unescaped-in-transit")
        else:
            block.fail(f"exchange block {sid}: body sha256 {found[:12]}… does "
                       f"not match the trailer's {expected[:12]}… — truncated "
                       "or edited in transit; re-request the block",
                       fault="mismatch")
        return block, nxt
    if not isinstance(record, dict):
        block.fail(f"exchange block {sid}: the body matches its trailer but is "
                   "not a JSON object", fault="body-not-json")
        return block, nxt
    block.integrity["ok"] = True
    block.fields["record"] = record
    return block, nxt


def _json_or_none(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None

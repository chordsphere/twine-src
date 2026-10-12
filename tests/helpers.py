"""Shared test helpers: run the real entrypoint as a subprocess the way
the brief specifies (`python3 -I -S bin/twine …`, plus -B so no
bytecode lands), build temp bale roots, and run the CLI in-process with
injected streams and environment.

Since session 2b-i: probes for `carry probe` derived from the crafter's
recorded scaffold (filled_probe — the placeholders filled mechanically,
never a script typed from scratch), and two doubles for the run seam
(Context.run): RecordingRunner, which records calls and answers a canned
result, and FixturePlayer, which answers a `bale …` argv from its
recorded fixture (laid down for session 2b-ii).

Since session 2b-ii: fixture names key on a *normalized* argv — a
per-run value (a session id, a tarball's temp path) is replaced by its
role (`fixture_key`), so `bale relay <sid> -` names `relay_sid_stdin` and
`bale apply --dry-run --json <path>` names
`apply_--dry-run_--json_tarball`; FixturePlayer answers the exit code
fixtures/README.md records for the file (refusing to guess one the row
calls `unrecorded`); and StubBale, a double named as one: a generated
`bin/bale` script in a temp root that replays given bytes and records
how it was called, so the CLI can be run end to end as a subprocess
without any bale.

Since session 5a: the spend doubles — PRICES_DOUBLE (invented prices for
invented model ids), usage_double (a twine usage record's tokens, never a
provider's response) and SpendStateDouble (a temp state directory).

Since session 5b: RealGroup, a real `setsid`-led process group for the
kill to kill. (5b also built the unlock doubles — unlock_json_double,
UnlockDouble, StubBale's double stdout — from format_unlock_json's
docstring, because no `bale unlock --json` output had been recorded.)

Since session 5c: the run-seam doubles accept the seam's `on_spawn` hook
(and record it, never call it).

Since session 2026-10-07-twine-pin-049-001 (the pin at 0.4.49): the unlock
doubles are gone, replaced by the recordings — six `bale unlock … --json`
lines recorded at 0.4.49 (the `aborted` close, the HOLD-branch refusal,
and four more outcomes; fixtures/README.md), read by `unlock_recording`
and replayed by RecordedUnlock (the run-seam double that took UnlockDouble's
place) and by StubBale. A recording replaces a double and never joins it
(contract §14.7). Fixture names gained a third `<where>`, `scratch` (a
throwaway repository), two roles (`bundle`, `goal`) and an outcome group
(`+<outcome>[+<reason>]`) for an argv recorded with more than one
outcome; FixturePlayer answers a grouped name only when the test selects
the group. `carried_relpath` reads the version a carried paste belongs
to from the manifest's format entry (`fixtures_version`), since a paste
stays under the version that printed it.

Since session 2026-10-07-twine-kill-reason-002: no recording carries a
stderr. twine's kill keys its hand line on the refusal line's `reason`
code, not on stderr text, so `unlock_recording` answers stderr empty for
every recording and derives none; a test that proves stderr passes through
feeds bytes it names as not bale's (RecordedUnlock's and StubBale's
`stderr=`). (History since the pin at 0.4.51, below: every recording now
carries the stderr bale printed beside it, recorded byte-exact, and the
recording answers it. twine's kill still keys on `reason`, never on stderr
text, and a test that needs bytes bale never printed still names them.)

Since Arc 1 session 3 (`twine carry bundle`): StubBale also replays an
`open` recording (`open_stdout=`), and `open_recording(name)` reads the
three recorded `bale open … --json` lines (OPEN_RECORDINGS) — opened and
second-desk in the scratch repository, rehearsed under --check in
~/twine-src — as `unlock_recording` reads the unlock lines.

Since session 2026-10-08-twine-carry-exchange-json-001 (`carry exchange`
reads `bale relay --json`'s line): `relay_recording(name)` reads the four
recorded `bale relay … --json` lines (RELAY_RECORDINGS) and RecordedRelay
replays one for twine's argv, `relay <sid> - --json`, on the named
assumption that bale reads `-` exactly as it reads the file the recordings
were made with. StubBale's `relay_stdout` is a recording's file now; the
crafter's `--emit-block` emission no longer stands in for relay's stdout
(it stays the `exchange` format's fixture, which `take` reads).

Since session 2026-10-12-twine-pin-051-001 (the pin at 0.4.51): the naming
rule and the README row shapes live in tests/fixture_rule.py, shared with
bin/twine-land-recordings (the lander) and re-exported here with PIN as the
version. Every recording of the pinned version has a `.stderr` sibling and
an eight-column README row (`recorded_rows`; `recorded_exits` is a view of
it), and `Recording.stderr` is the sibling's bytes: FixturePlayer answers
it, `unlock_recording`, `open_recording` and `relay_recording` return it,
and RecordedUnlock, RecordedRelay and StubBale replay it (`stderr=` still
overrides with bytes named as not bale's). The relay recordings are of
twine's own argv, `relay <sid> - --json`, so RecordedRelay's assumption is
gone; `open_recording` gains the recorded refusal, `open-refused`."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from twine import REPO_ROOT
from twine.bale import load_manifest
from twine.cli import Context, main

from tests import fixture_rule
from tests.fixture_rule import (EMISSION_TOOLS, GROUP_SEP, STDERR_EXT, UNRECORDED, WHERE,
                                WHERE_ANYWHERE, Role, Row, fixture_key, fixture_stem,
                                fixture_where, split_group, stderr_relpath)

TWINE = REPO_ROOT / "bin" / "twine"
PIN = "0.4.51"

# bale's three closed vocabularies — the oracle the consumption manifest's
# [[vocabulary]] entries and the transition table's bale axes are held to.
# Copied from the output of the probes twine-table-vocab and
# twine-apply-vocab (2026-10-03, bale 0.4.45, quoted in the session-4 brief
# §2); re-read at the pin bump to 0.4.49 by the desk of sitting
# 2026-10-06-continue-twine-002 from bale-src's context tarball (the two
# schema-homed axes under schema hashes unchanged since 0.4.45;
# format_apply_json's docstring at bin/bale_report.py line 3040 with the
# same nine outcomes) and found unchanged, value for value; re-read at the
# pin bump to 0.4.51 by the desk of sitting 2026-10-08-open-arc2-003 from
# bale-src's context tarball (format_apply_json's docstring at line 3426 of
# bin/bale_report.py, sha256 1f4f2c75…, the same nine outcomes) with the
# eight schemas hashed by probe twine-051-record, all unchanged — and found
# unchanged again. Never edited to match the manifest: a pin bump re-reads
# them and says where.
BALE_VOCABULARIES: dict[str, list[str]] = {
    # schemas/telemetry-record.schema.json /properties/outcome (13)
    "telemetry-outcome": ["opened", "applied", "held", "reverted", "rejected",
                          "bailout", "scope-drift-refused", "required-check-refused",
                          "base-drift-refused", "unlocked", "rolled-back",
                          "re-applied", "relay-refused"],
    # the same schema, /properties/attempts/items/properties/closure_reason —
    # ten members, the tenth null ("not closed"), which is not a key (9)
    "closure-reason": ["abandoned", "superseded-by-split",
                       "reframed-after-clarification", "master-closeout",
                       "crash-debris", "closed-read-only", "no_response",
                       "malformed_response", "aborted"],
    # bin/bale_report.py format_apply_json's docstring, the outcome block (9)
    "apply-outcome": ["applied", "held", "reverted", "bailout", "clarification",
                      "dry-run", "scope-drift-refused", "required-check-refused",
                      "base-drift-refused"],
}
# An outcome no bale emits, spelled so that no reader could take it for
# bale's: what a double prints when a test proves twine names an outcome
# it does not know. It is in none of BALE_VOCABULARIES' lists.
NOT_A_BALE_OUTCOME = "twine-test-not-a-bale-outcome"


@dataclass
class Run:
    code: int
    stdout: str
    stderr: str


def run_cli(*argv: str, cwd: Path | None = None,
            bale_root: Path | str | None = None,
            extra_env: dict[str, str] | None = None,
            stdin: bytes | None = None) -> Run:
    """Run bin/twine as a subprocess under `python3 -I -S -B`.

    TWINE_BALE_ROOT is always set — to `bale_root`, or to a directory
    that does not exist — so the resolution never falls through to a
    bale on the developer's PATH (the suite's no-install rule). `stdin`,
    when given, is fed as bytes (byte-exact, so a CRLF test means it) and
    the outputs are decoded as UTF-8; otherwise stdin is empty.
    """
    env = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8",
           "TWINE_BALE_ROOT": str(bale_root) if bale_root is not None
           else os.path.join(tempfile.gettempdir(), "twine-tests-no-bale-here")}
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(TWINE), *argv],
        cwd=str(cwd or REPO_ROOT), env=env, capture_output=True,
        input=stdin if stdin is not None else b"")
    return Run(proc.returncode, proc.stdout.decode("utf-8"),
               proc.stderr.decode("utf-8"))


def run_inprocess(*argv: str, env: dict[str, str] | None = None,
                  which=lambda name: None, stdin: bytes = b"") -> Run:
    """Run cli.main in-process with captured streams. `env` defaults to
    an empty mapping, `which` to "nothing on PATH" and `stdin` to empty
    bytes, so no test reaches the real environment unless it says so."""
    out, err = io.StringIO(), io.StringIO()
    ctx = Context(env=env if env is not None else {}, stdout=out, stderr=err,
                  which=which, stdin=io.BytesIO(stdin))
    code = main(list(argv), ctx=ctx)
    return Run(code, out.getvalue(), err.getvalue())


class TempRoots:
    """Three bale install roots under one temp dir: `ok` (bin/VERSION at
    the pin), `other` (another version), `absent` (no bin/VERSION)."""

    def __init__(self, pin: str = PIN, other: str = "0.4.46") -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="twine-roots-")
        base = Path(self._dir.name)
        self.ok = base / "ok"
        self.other = base / "other"
        self.absent = base / "absent"
        (self.ok / "bin").mkdir(parents=True)
        (self.other / "bin").mkdir(parents=True)
        self.absent.mkdir()
        (self.ok / "bin" / "VERSION").write_text(pin + "\n", encoding="utf-8")
        (self.other / "bin" / "VERSION").write_text(other + "\n", encoding="utf-8")
        self.other_version = other

    def cleanup(self) -> None:
        self._dir.cleanup()


# The naming rule (Role, fixture_key, fixture_stem, fixture_where,
# split_group, GROUP_SEP, WHERE) is tests/fixture_rule.py's, imported above;
# the functions below are its path functions at the pin.


def fixture_relpath(argv: list[str], cwd: str, group: str | None = None) -> str:
    """The fixtures/ path a recorded bale output lands at, from the argv
    after `bale`, where it ran and (for an argv recorded with more than one
    outcome) its outcome group — fixtures/README.md's naming rule, at the
    pin (fixture_rule.fixture_relpath_at):

      fixtures/bale-<pin>/<where>/<verb>_<flag[-value…]>[_…][+<group>].<ext>

    `where` is `twine-src` for cwd "repo", `scratch` for cwd "scratch"
    (the throwaway repository a probe recorded in) and `anywhere`
    otherwise. The argv is normalized first (fixture_key: a per-run value
    becomes its Role; fixture_stem spells the groups). `group` is the
    outcome group, `<outcome>` or `<outcome>+<reason>`, None for an argv
    recorded once.
    """
    return fixture_rule.fixture_relpath_at(PIN, argv, cwd, group)


def recorded_rows() -> dict[str, Row]:
    """Every recording row of fixtures/README.md, keyed by its fixtures/
    path: exit (an int, or "unrecorded"), bytes, sha256 and — on the
    eight-column rows of 0.4.51 on — the `.stderr` sibling's bytes and
    sha256 (None on the six-column rows of 0.4.45 and 0.4.49, which stay
    as history). fixture_rule.parse_rows is the parser the lander shares."""
    text = (REPO_ROOT / "fixtures" / "README.md").read_text(encoding="utf-8")
    return fixture_rule.parse_rows(text)


def recorded_exits() -> dict[str, int | str]:
    """Each recorded output's exit code as fixtures/README.md states it,
    keyed by its fixtures/ path: an int, or "unrecorded" — a view of
    recorded_rows(), kept so the player's callers do not move."""
    return {path: row.exit for path, row in recorded_rows().items()}


def recorded_stderr(relpath: str, row: Row | None = None) -> bytes:
    """The stderr bale printed beside the recording at `relpath`: its
    `.stderr` sibling's bytes, held to the README row's stderr bytes and
    sha256. Raises when the row records no stderr (a six-column row of
    0.4.45 or 0.4.49), the sibling is missing, or its bytes are not the
    row's — a stderr is never guessed and never derived."""
    row = recorded_rows().get(relpath) if row is None else row
    if row is None:
        raise AssertionError(f"{relpath} has no fixtures/README.md row")
    if not row.has_stderr:
        raise AssertionError(f"{relpath}'s row records no stderr (a recording older than "
                             "0.4.51); a test that needs one names bytes as not bale's")
    sibling = REPO_ROOT / stderr_relpath(relpath)
    if not sibling.is_file():
        raise AssertionError(f"{relpath}'s stderr sibling is missing at {sibling.name}")
    data = sibling.read_bytes()
    if (len(data), hashlib.sha256(data).hexdigest()) != (row.stderr_bytes, row.stderr_sha256):
        raise AssertionError(f"{sibling.name} is not the bytes its row records")
    return data


# Fixtures that are not the stdout of a `bale` argv (fixtures/README.md,
# "Emissions and carried pastes"): the crafter's emissions, and pastes of
# bale output the architect carried. Both land as .txt.


def emission_relpath(tool: str, argv: list[str]) -> str:
    """fixtures/bale-<pin>/<tool>/<flag[-value…]>[_…].txt for a bale tool
    run with `argv` — fixture_relpath's grouping, with a `-` value (stdin)
    spelled `stdin` so no name carries a bare dash."""
    return fixture_rule.emission_relpath_at(PIN, tool, argv)


def fixtures_version(kind: str) -> str:
    """The bale version that emitted a format's fixtures, as the
    consumption manifest's format entry for `kind` names it
    (`fixtures_version`): the pin for a crafter emission (re-recorded at
    every pin), and the version that printed a carried paste, which stays
    under that version's directory across a pin bump. Raises for a kind
    with no entry or no version: a paste's home is never guessed."""
    for s in load_manifest().surfaces:
        if s.get("kind") == "format" and s.get("format") == kind:
            version = s.get("fixtures_version")
            if not isinstance(version, str) or not version.strip():
                raise ValueError(f"format entry {kind!r} names no fixtures_version")
            return version
    raise ValueError(f"no format entry for {kind!r} in the consumption manifest")


def carried_relpath(kind: str, identity: str, to: str | None = None,
                    version: str | None = None) -> str:
    """fixtures/bale-<version>/carried/<kind>_<identity>[_to-<addressee>].txt
    for a carried paste: the block kind, the slug or sid its sentinel
    names, and for a relay block its addressee. `version` is the bale that
    printed the paste — by default the one the manifest's format entry for
    `kind` names (fixtures_version), never the pin by assumption."""
    version = fixtures_version(kind) if version is None else version
    return fixture_rule.carried_relpath_at(version, kind, identity, to)


# ---------------------------------------------------------------------------
# Probes for `carry probe` (session 2b-i): derived from the crafter's
# recorded scaffold by filling its placeholders mechanically — never a
# probe script typed from scratch.
# ---------------------------------------------------------------------------

PROBE_SCAFFOLD = REPO_ROOT / emission_relpath("crafter", ["--probe", "twine-take-fixture"])
PROBE_SLUG = "twine-take-fixture"
SCAFFOLD_WHAT = "TODO(worker) — what this asks, in one line."
SCAFFOLD_WHY = "TODO(worker) — the gap this fills, in one line."
SCAFFOLD_BODY_OPEN = "probe() {\n"
SCAFFOLD_BODY_CLOSE = "\n}\n"
# Where the scaffold's clipboard tail begins (0.4.49's, byte-identical at
# 0.4.51): after the
# `emit_probe_block` call, a comment block and the shell that pipes the
# block into `bale clipboard --block "probe block"` when a `bale` is on
# PATH (two `[clipboard]` notices on stderr when none is). The tail is a
# fact about the installed crafter (contract §10.3); a test's probe must
# never reach a bale (T8), so the filled specimen ends before it unless a
# test keeps it on purpose and controls PATH.
SCAFFOLD_TAIL_OPEN = "\n# Clipboard copy (TARBALL.md 4.3)"
SCAFFOLD_TAIL_NOTICE = "[clipboard] "


def scaffold() -> str:
    """The crafter's unfilled probe scaffold, as recorded."""
    return PROBE_SCAFFOLD.read_bytes().decode("utf-8")


def filled_probe(body: str = 'echo "--- section: shell ---"\necho "bash ok"',
                 what: str = "what bash reports about itself.",
                 why: str = "a carry-probe test needs a filled scaffold.",
                 clipboard_tail: bool = False) -> str:
    """The scaffold with its two header placeholders replaced and the
    probe() body replaced by `body` (indented two spaces) — the filling
    a worker does, done mechanically. Every TODO(worker) is gone. The
    scaffold's clipboard tail (SCAFFOLD_TAIL_OPEN) is cut unless
    `clipboard_tail` is True: it would hand the block to whatever `bale`
    is on PATH, which no test's probe may reach."""
    text = scaffold()
    for placeholder in (SCAFFOLD_WHAT, SCAFFOLD_WHY):
        if text.count(placeholder) != 1:
            raise AssertionError(f"scaffold drifted: {placeholder!r}")
    text = text.replace(SCAFFOLD_WHAT, what).replace(SCAFFOLD_WHY, why)
    start = text.index(SCAFFOLD_BODY_OPEN) + len(SCAFFOLD_BODY_OPEN)
    end = text.index(SCAFFOLD_BODY_CLOSE, start)
    indented = "\n".join("  " + ln if ln else ln for ln in body.split("\n"))
    text = text[:start] + indented + text[end:]
    if "TODO(worker)" in text:
        raise AssertionError("filled probe still carries TODO(worker)")
    if not clipboard_tail:
        if text.count(SCAFFOLD_TAIL_OPEN) != 1:
            raise AssertionError("scaffold drifted: the clipboard tail is not where "
                                 "the pinned recording has it")
        text = text[:text.index(SCAFFOLD_TAIL_OPEN)]   # ends at `emit_probe_block\n`
    return text


def fenced_probe(script: str, info: str = "bash") -> str:
    """A probe as a worker's turn carries it: the script in a fence."""
    return f"```{info}\n{script}```\n"


def turn(*parts: str) -> str:
    """A pasted turn: prose and blocks joined by blank lines."""
    return "\n".join(parts)


def process_alive(pid: int) -> bool:
    """Whether `pid` is a live process. A zombie (exited, not yet reaped
    — a container's PID 1 may never reap an orphan) counts as dead."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat = Path(f"/proc/{pid}/stat")
    try:
        state = stat.read_text().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return True
    return state not in ("Z", "X")


def dies_within(pid: int, seconds: float = 3.0) -> bool:
    """Whether `pid` is dead (process_alive false) within `seconds`.

    A SIGKILLed process closes its file descriptors before the kernel
    marks it a zombie, and the runner returns once the pipes close — so a
    single process_alive check right after a run can catch the killed
    sleep in that gap, wider on a loaded machine (session 5a's HOLD, in
    bale's sandbox). Polling briefly asserts what the contract says — the
    group is killed — without asserting a scheduler's timing."""
    deadline = time.monotonic() + seconds
    while process_alive(pid):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)
    return True


class RecordingRunner:
    """A run-seam double: records every call and answers with a canned
    RunResult (exit 0, empty output) unless given one. A test that must
    prove nothing executed asserts `calls == []`. Every run-seam double
    here takes the seam's whole signature, `on_spawn` included (session
    5c), and records it; none calls it — a double spawns nothing, so it
    has no pid to hand over."""

    def __init__(self, result=None) -> None:
        self.calls: list[dict] = []
        self.result = result

    def __call__(self, argv, *, cwd=None, stdin=None, timeout=None, env=None,
                 stdout_cap=None, on_spawn=None):
        from twine.process import RunResult
        self.calls.append({"argv": list(argv), "cwd": cwd, "stdin": stdin,
                           "timeout": timeout, "env": env,
                           "stdout_cap": stdout_cap, "on_spawn": on_spawn})
        return self.result or RunResult(argv=tuple(argv), exit_code=0,
                                        stdout=b"", stderr=b"")


class FixturePlayer:
    """A run-seam double that answers a `bale …` argv from its recorded
    fixture: the path is fixture_relpath(argv after `bale`, where, group)
    — the argv normalized, so a per-run sid or tarball path finds its one
    recording — with `where` "repo" when cwd is `repo_root`, "scratch"
    when cwd is `scratch_root` (the directory a test names as the
    throwaway repository the scratch recordings were made in), else
    "anywhere".

    An argv recorded with more than one outcome has no plain file, only
    grouped ones (`+<outcome>[+<reason>]`, fixtures/README.md): the player
    answers it only when `select` names the group for that normalized
    name (e.g. {"apply_--dry-run_--json_tarball": "dry-run"}), and
    otherwise refuses naming the candidates — which outcome a test
    replays is visible where it is used, never the player's pick.

    The answer is the fixture's bytes on stdout, the exit code its
    fixtures/README.md row records, and on stderr the bytes bale printed
    beside it — the recording's `.stderr` sibling, held to the row's stderr
    sha256 (since the pin at 0.4.51; recorded_stderr). A row whose exit is
    `unrecorded` is refused unless the test names the code it assumes in
    `assumed_exits` (fixtures/ path -> code), so an assumption is always
    visible where it is made (no pinned row lacks its exit; the rule
    stays). An argv with no fixture raises — a test must never reach a
    live bale."""

    def __init__(self, repo_root: Path,
                 assumed_exits: dict[str, int] | None = None,
                 scratch_root: Path | None = None,
                 select: dict[str, str] | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.scratch_root = None if scratch_root is None else Path(scratch_root).resolve()
        self.calls: list[list[str]] = []
        self.rows = recorded_rows()
        self.exits = {path: row.exit for path, row in self.rows.items()}
        self.assumed_exits = dict(assumed_exits or {})
        self.select = dict(select or {})

    def where(self, cwd) -> str:
        if cwd is not None:
            resolved = Path(cwd).resolve()
            if resolved == self.repo_root:
                return "repo"
            if self.scratch_root is not None and resolved == self.scratch_root:
                return "scratch"
        return "anywhere"

    def relpath(self, argv: list[str], where: str) -> str:
        """The fixture a bale argv (after `bale`) names in `where`: the
        plain name when recorded once, else the selected group's."""
        stem, ext = fixture_stem(argv)
        plain = fixture_relpath(argv, where)
        directory = (REPO_ROOT / plain).parent
        grouped = sorted(p.name for p in directory.glob(f"{stem}{GROUP_SEP}*{ext}")
                         ) if directory.is_dir() else []
        if (REPO_ROOT / plain).is_file():
            if grouped:
                raise AssertionError(f"{plain} exists beside grouped recordings "
                                     f"{grouped}: the naming rule allows one or the other")
            return plain
        if not grouped:
            raise AssertionError(f"no recorded fixture for bale {argv} at {plain}")
        group = self.select.get(stem)
        if group is None:
            raise AssertionError(
                f"bale {argv} is recorded with more than one outcome in {directory.name}/ "
                f"({', '.join(grouped)}); name the group in select={{{stem!r}: ...}}")
        rel = fixture_relpath(argv, where, group)
        if not (REPO_ROOT / rel).is_file():
            raise AssertionError(f"no recorded fixture for bale {argv} with group "
                                 f"{group!r} at {rel} (recorded: {', '.join(grouped)})")
        return rel

    def __call__(self, argv, *, cwd=None, stdin=None, timeout=None, env=None,
                 stdout_cap=None, on_spawn=None):
        from twine.process import RunResult
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        if not argv or Path(argv[0]).name != "bale":
            raise AssertionError(f"FixturePlayer answers bale argvs only: {argv}")
        rel = self.relpath(argv[1:], self.where(cwd))
        path = REPO_ROOT / rel
        code = self.exits.get(rel)
        if code is None:
            raise AssertionError(f"{rel} has no fixtures/README.md row")
        if code == UNRECORDED:
            if rel not in self.assumed_exits:
                raise AssertionError(
                    f"{rel}: its exit code is unrecorded; a test that relies on "
                    "one names it in assumed_exits")
            code = self.assumed_exits[rel]
        return RunResult(argv=tuple(argv), exit_code=code,
                         stdout=path.read_bytes(),
                         stderr=recorded_stderr(rel, self.rows[rel]))


class StubBale:
    """A double, not bale: a temp install root whose `bin/bale` is a
    bash script this class writes, and `bin/VERSION` at the pin. The
    script records its argv, cwd and (for `relay`) stdin under `record`,
    then replays the bytes of `relay_stdout` (since session
    2026-10-08-twine-carry-exchange-json-001, a `relay --json` recording's
    file — relay_recording(...).path), `apply_stdout`,
    `unlock_stdout` (since the pin at 0.4.49, a recording's file —
    unlock_recording(...).path) or `open_stdout` (since Arc 1 session 3, an
    `open` recording's file) on stdout, and exits `exit_code`. On stderr it
    replays, for the verb it answers, the recording's `.stderr` sibling
    when that file has one (since the pin at 0.4.51: bale's stderr,
    recorded byte-exact) — unless `stderr` is given, which replaces it with
    text the test names as not bale's ("" for none at all). It lets the
    CLI run end to end as a subprocess (`--bale-root`) with no bale
    anywhere; the bytes it replays are a recorded fixture, or bytes the
    test names as not bale's."""

    def __init__(self, relay_stdout: Path | None = None,
                 apply_stdout: Path | None = None, exit_code: int = 0,
                 stderr: str | None = None, unlock_stdout: Path | None = None,
                 open_stdout: Path | None = None) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="twine-stub-bale-")
        base = Path(self._dir.name)
        self.root = base / "root"
        self.record = base / "record"
        (self.root / "bin").mkdir(parents=True)
        self.record.mkdir()
        (self.root / "bin" / "VERSION").write_text(PIN + "\n", encoding="utf-8")
        q = shlex.quote
        replay = {"relay": relay_stdout, "apply": apply_stdout,
                  "unlock": unlock_stdout, "open": open_stdout}
        # bash by absolute path: a verb run in-process may hand the child an
        # empty environment, and the shebang must not depend on PATH.
        bash = shutil.which("bash") or "/bin/bash"
        lines = [f"#!{bash}",
                 "# A test double written by tests/helpers.py StubBale — not bale.",
                 f"printf '%s\\n' \"$@\" > {q(str(self.record / 'argv'))}",
                 f"pwd > {q(str(self.record / 'cwd'))}",
                 f"if [ \"$1\" = relay ]; then cat > {q(str(self.record / 'stdin'))}; fi"]
        for verb, source in replay.items():
            if source is not None:
                sibling = Path(source).with_suffix(STDERR_EXT)
                replay_stderr = (f"; cat {q(str(sibling))} >&2"
                                 if stderr is None and sibling.is_file() else "")
                lines.append(f"if [ \"$1\" = {verb} ]; then cat {q(str(source))}"
                             f"{replay_stderr}; fi")
        if stderr:
            lines.append(f"printf '%s' {q(stderr)} >&2")
        lines.append(f"exit {int(exit_code)}")
        self.executable = self.root / "bin" / "bale"
        self.executable.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.executable.chmod(self.executable.stat().st_mode | stat.S_IXUSR)

    def argv(self) -> list[str] | None:
        path = self.record / "argv"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else None

    def stdin(self) -> bytes | None:
        path = self.record / "stdin"
        return path.read_bytes() if path.exists() else None

    def cwd(self) -> str | None:
        path = self.record / "cwd"
        return path.read_text(encoding="utf-8").strip() if path.exists() else None

    def cleanup(self) -> None:
        self._dir.cleanup()


# ---------------------------------------------------------------------------
# Spend doubles (Arc 1 session 5a). No provider usage has ever been
# recorded and twine ships no prices, so every usage value and every price
# a spend test sees is a double, named as one: the model ids say so, and no
# price below is any provider's.
# ---------------------------------------------------------------------------

# Invented model ids: no reader could take one for a real model.
DOUBLE_MODEL = "double-model-a"
DOUBLE_MODEL_DEAR_CACHE = "double-model-dear-cache-read"
DOUBLE_MODEL_UNPRICED = "double-model-with-no-price-row"

# A price table double: invented prices, US dollars per million tokens.
# `double-model-a`'s dearest input-side price is cache_write; the second
# model's is cache_read, so the worst case's choice is tested both ways.
PRICES_DOUBLE = """\
# A test double written by tests/helpers.py: invented prices, not any
# provider's. twine ships no prices.
[model."double-model-a"]
input = 3
output = 15
cache_read = 0.3
cache_write = 3.75
source = "tests/helpers.py PRICES_DOUBLE (invented)"
as_of = "never"

[model."double-model-dear-cache-read"]
input = 1
output = 2
cache_read = 5
cache_write = 4
"""


def usage_double(input: int = 0, output: int = 0, thinking: int | None = None,
                 cache_read: int = 0, cache_write: int = 0) -> dict[str, int | None]:
    """A twine usage record's `tokens`, as a double: never a provider's
    response, which nobody has recorded yet (the gated probe
    `twine-usage-record` will)."""
    return {"input": input, "output": output, "thinking": thinking,
            "cache_read": cache_read, "cache_write": cache_write}


class SpendStateDouble:
    """A temp state directory: `path` (holding spend.jsonl, written through
    twine.spend.append_record — the writer the Arc 2 loop will call) and,
    unless `prices` is None, prices.toml holding `prices`. Never the real
    default state directory."""

    def __init__(self, prices: str | None = PRICES_DOUBLE) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="twine-spend-")
        self.path = Path(self._dir.name) / "state"
        self.path.mkdir()
        self.stream = self.path / "spend.jsonl"
        self.prices = self.path / "prices.toml"
        if prices is not None:
            self.prices.write_text(prices, encoding="utf-8")

    def call(self, sid: str, model: str = DOUBLE_MODEL, served_sid: str | None = None,
             **tokens: int | None):
        """Append one record — one model call, a double — and return it."""
        from twine import spend
        return spend.append_record(self.path, sid=sid, model=model,
                                   served_sid=served_sid, tokens=usage_double(**tokens),
                                   clock=lambda: "2026-10-03T00:00:00Z")

    def raw(self, text: str | bytes) -> None:
        """Append raw bytes to the stream, bypassing the writer: how a test
        lays down a line the writer would refuse."""
        data = text.encode("utf-8") if isinstance(text, str) else text
        with self.stream.open("ab") as fh:
            fh.write(data)

    def cleanup(self) -> None:
        self._dir.cleanup()


# ---------------------------------------------------------------------------
# The unlock recordings (session 2026-10-07-twine-pin-049-001, the pin at
# 0.4.49; re-recorded at 0.4.51 with their stderr by session
# 2026-10-12-twine-pin-051-001). Six `bale unlock … --json` lines — four in
# a throwaway repository, two in ~/twine-src (fixtures/README.md, "bale
# 0.4.51") — replace session 5b's doubles, which were built from
# format_unlock_json's docstring because nothing had been recorded. Every
# unlock answer a test sees now is one of these recordings' bytes (stdout,
# exit and, since 0.4.51, stderr), or bytes a test names as not bale's at
# all (contract §14.7).
# ---------------------------------------------------------------------------

# format_unlock_json's keys at 0.4.49 and 0.4.51, in the order the recorded
# lines carry them: the nine of 0.4.45 and the three bale 0.4.47 added for
# the refusal line (`reason`, `message`, `open_sessions`) — present on every
# outcome, null where they do not apply.
UNLOCK_KEYS = ("outcome", "sid", "log", "closure_reason", "session_dir_wiped",
               "branch_preserved", "telemetry", "debris", "sweep", "reason",
               "message", "open_sessions")
UNLOCK_REFUSED = "unlock-refused"
# The sids the recordings name: the scoped session the scratch probe closed
# `aborted` (and whose HOLD refusal it recorded first), the read-only one it
# closed without a reason, and the sid that was never open.
UNLOCK_RECORDED_SID = "2026-10-08-sc-002"
UNLOCK_RECORDED_READ_ONLY_SID = "2026-10-08-ro-001"
UNLOCK_RECORDED_ABSENT_SID = "no-such-sid-twine-051"

# Each recording by the name the tests call it: where it ran, the argv as
# recorded (per-run values as their roles) and its outcome group.
UNLOCK_RECORDINGS: dict[str, tuple[str, list[str], str | None]] = {
    "aborted": ("scratch", ["unlock", Role("sid"), "--reason", "aborted", "--json"], None),
    "hold-branch": ("scratch", ["unlock", Role("sid"), "--json"], "unlock-refused+hold-branch"),
    "closed-read-only": ("scratch", ["unlock", Role("sid"), "--json"], "unlocked"),
    "no-op": ("scratch", ["unlock", "--json"], None),
    "not-open": ("repo", ["unlock", Role("sid"), "--json"], "unlock-refused+not-open"),
    "integration-json": ("repo", ["unlock", "--integration", "--json"], None),
}


@dataclass(frozen=True)
class Recording:
    """One recorded bale output as a test replays it: its fixtures/ path,
    stdout (the file's bytes), the exit its README row records, stderr
    (since the pin at 0.4.51, the `.stderr` sibling's bytes, read eagerly
    when the recording is read and held to the row's stderr sha256 —
    recorded, never derived) and the line parsed."""

    relpath: str
    stdout: bytes
    exit_code: int
    stderr: bytes
    line: dict

    @property
    def path(self) -> Path:
        return REPO_ROOT / self.relpath

    @property
    def stderr_path(self) -> Path:
        return REPO_ROOT / stderr_relpath(self.relpath)


def read_recording(kind: str, name: str, where: str, argv: list[str],
                   group: str | None) -> Recording:
    """The pinned recording of `argv` run in `where` with outcome `group`:
    stdout from the file, the exit and the stderr its README row records
    (the stderr from the `.stderr` sibling, held to the row). `kind` and
    `name` only name it in a failure."""
    rel = fixture_relpath(argv, where, group)
    path = REPO_ROOT / rel
    if not path.is_file():
        raise AssertionError(f"{kind} recording {name!r} missing at {rel}")
    row = recorded_rows().get(rel)
    if row is None or row.exit == UNRECORDED:
        raise AssertionError(f"{rel} has no recorded exit in fixtures/README.md")
    stdout = path.read_bytes()
    return Recording(rel, stdout, int(row.exit), recorded_stderr(rel, row),
                     json.loads(stdout))


def unlock_recording(name: str) -> Recording:
    """The pinned recording of `bale unlock` named `name` (a key of
    UNLOCK_RECORDINGS), with its exit and the stderr bale printed beside it
    — recorded byte-exact since 0.4.51 (every refusal's ends with `[bale]
    error: <message>`). twine's kill reads the refusal by its line's
    `reason`, never by stderr; the stderr is what passes through."""
    where, argv, group = UNLOCK_RECORDINGS[name]
    return read_recording("unlock", name, where, argv, group)


class RecordedUnlock:
    """A run-seam double for the closure that answers twine's one unlock
    argv with a RECORDING's bytes: by default the `aborted` close
    (unlock_recording("aborted") — the session it names is
    UNLOCK_RECORDED_SID, so a test that wants the close to be ok kills that
    sid), else the recording named by `recording`. Records every call.

    The refusals were recorded under `unlock <sid> --json`, without
    `--reason aborted`; replaying one for twine's argv assumes bale refuses
    before the reason matters — the assumption is this double's, named
    here and in fixtures/README.md. The recording's stderr (recorded since
    0.4.51) is replayed with its stdout and exit. `stdout` replaces the
    recording's bytes with bytes that are NOT bale's (an empty stdout, a
    bare word) to prove what twine refuses; `stderr` likewise answers bytes
    that are NOT bale's in place of the recording's stderr, to prove that
    stderr passes through and decides nothing; `timed_out` answers as the
    seam does for a call it killed. It answers only the unlock argv shape
    and fails the test on anything else."""

    def __init__(self, recording: str | Recording = "aborted", *,
                 stdout: bytes | None = None, stderr: bytes | None = None,
                 timed_out: bool = False) -> None:
        self.calls: list[dict] = []
        self.recording = (unlock_recording(recording) if isinstance(recording, str)
                          else recording)
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out

    def __call__(self, argv, *, cwd=None, stdin=None, timeout=None, env=None,
                 stdout_cap=None, on_spawn=None):
        from twine.process import RunResult
        argv = [str(a) for a in argv]
        self.calls.append({"argv": argv, "cwd": cwd, "stdin": stdin,
                           "timeout": timeout, "env": env, "stdout_cap": stdout_cap,
                           "on_spawn": on_spawn})
        if Path(argv[0]).name != "bale" or argv[1:2] != ["unlock"]:
            raise AssertionError(f"RecordedUnlock answers the unlock argv only: {argv}")
        stderr = self.recording.stderr if self.stderr is None else self.stderr
        if self.timed_out:
            return RunResult(argv=tuple(argv), exit_code=None, stdout=b"",
                             stderr=stderr, timed_out=True)
        stdout = self.recording.stdout if self.stdout is None else self.stdout
        return RunResult(argv=tuple(argv), exit_code=self.recording.exit_code,
                         stdout=stdout, stderr=stderr)


class RealGroup:
    """A real process group to kill: bash started as a session leader
    (`setsid`, so it leads its own group), running `body` and printing the
    pid of each background child it starts. `pgid` is bash's pid. Cleanup
    SIGKILLs the group and reaps bash, whatever the test did."""

    def __init__(self, body: str = "sleep 60 & echo $!; sleep 60 & echo $!; wait",
                 children: int = 2) -> None:
        bash = shutil.which("bash") or "/bin/bash"
        self.proc = subprocess.Popen([bash, "-c", body], start_new_session=True,
                                     stdout=subprocess.PIPE, stdin=subprocess.DEVNULL)
        self.pgid = self.proc.pid
        self.children = [int(self.proc.stdout.readline()) for _ in range(children)]

    @property
    def pids(self) -> list[int]:
        return [self.pgid, *self.children]

    def cleanup(self) -> None:
        import signal as _signal
        try:
            os.killpg(self.pgid, _signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.proc.stdout.close()
        self.proc.wait(timeout=10)



# ---------------------------------------------------------------------------
# The open recordings (bale 0.4.49, re-recorded at 0.4.51; read since Arc 1
# session 3, `twine carry bundle`). Four `bale open … --json` lines are
# recorded at the pin: the scoped scratch session opened from a crafter
# bundle (`opened`), the same bundle opened again as desk-2 (`second-desk`,
# whose `tarball` is the outbox path since bale 0.4.50), a bundle file that
# does not exist (`open-refused`, exit 1, reason `not-found` — since 0.4.50
# a refusal prints a line too), all three in the scratch repository, and a
# throwaway bundle rehearsed with --check in ~/twine-src (`rehearsed`;
# fixtures/README.md, "bale 0.4.51"). A refusal that stops before printing
# a line (exit 1, nothing on stdout) is no longer what bale's refusal looks
# like; the tests keep it as a double named as such (OpenDouble), the case
# of a bale that stopped before writing its line.
# ---------------------------------------------------------------------------

# format_open_json's 23 keys at 0.4.51, in the order the recorded lines carry
# them: the 21 of 0.4.49 (the brief of session
# 2026-10-07-twine-carry-bundle-003, §1) and the two a refusal fills since
# bale 0.4.50, `reason` (a code from OPEN_REFUSAL_REASONS) and `cause`.
OPEN_KEYS = ("outcome", "sid", "tarball", "log", "session_dir", "context_files",
             "readme_path", "readme_heading", "readme_sha256", "checkpoint_file_path",
             "checkpoint_file_sha256", "branch", "applied_latest", "sweep",
             "include_group", "opener", "bundle", "members", "rehearsal",
             "checkpoint_dry_run", "desk", "reason", "cause")
OPEN_RECORDED_SID = "2026-10-08-sc-002"
# The normalized name the three open-without---check recordings share, and
# the group a test selects to replay one of them through FixturePlayer.
OPEN_KEY = "open_bundle_--json"
OPEN_RECORDINGS: dict[str, tuple[str, list[str], str | None]] = {
    "opened": ("scratch", ["open", Role("bundle"), "--json"], "opened"),
    "second-desk": ("scratch", ["open", Role("bundle"), "--json"], "second-desk"),
    "open-refused": ("scratch", ["open", Role("bundle"), "--json"], "open-refused"),
    "rehearsed": ("repo", ["open", "--check", Role("bundle"), "--json"], None),
}


def open_recording(name: str) -> Recording:
    """The pinned recording of `bale open` named `name` (a key of
    OPEN_RECORDINGS), with the exit its fixtures/README.md row records and
    the stderr bale printed beside it (recorded since 0.4.51)."""
    where, argv, group = OPEN_RECORDINGS[name]
    return read_recording("open", name, where, argv, group)


# ---------------------------------------------------------------------------
# The relay recordings (bale 0.4.49, re-recorded at 0.4.51; read since
# session 2026-10-08-twine-carry-exchange-json-001, when `carry exchange`
# moved onto `bale relay --json`). Four `bale relay … --json` lines are
# recorded at the pin in the scratch repository (fixtures/README.md, "bale
# 0.4.51"), three of them under twine's own argv, `relay <sid> - --json`,
# the paste block on stdin: a clarification manifest relayed as round 1
# (`relayed`), stdin that was neither a paste block nor JSON
# (`not-an-object`) and the block under a sid not open (`not-open`) — the
# two refusals named by the line's `reason`, which relay lines carry since
# bale 0.4.50 — and the round re-emitted with no input (`re-emitted`).
# They replaced the flagless relay's stand-in (the crafter's --emit-block
# emission) and the BaleDouble relay answers.
# ---------------------------------------------------------------------------

# format_relay_json's thirteen keys at 0.4.51, in the order every recorded
# line carries them: the twelve of 0.4.49 (the brief of session
# 2026-10-08-twine-carry-exchange-json-001, §1: BALE.md §5.8 and the
# function's docstring in bin/bale_report.py) and `reason`, a code from
# RELAY_REFUSAL_REASONS on a refusal (bale 0.4.50), null otherwise.
RELAY_KEYS = ("outcome", "sid", "round", "from", "awaiting", "kind", "preserved",
              "block", "log", "clipboard", "cause", "telemetry", "reason")
# The sid the relayed, re-emitted and not-an-object lines name (the scoped
# scratch session), and the one the not-open refusal names (never open).
RELAY_RECORDED_SID = "2026-10-08-sc-002"
RELAY_RECORDED_ABSENT_SID = "no-such-sid-twine-051"
# The normalized name of twine's argv, which the three stdin recordings
# share, and the group a test selects to replay one through FixturePlayer.
RELAY_STDIN_KEY = "relay_sid_stdin_--json"
RELAY_RECORDINGS: dict[str, tuple[str, list[str], str | None]] = {
    "relayed": ("scratch", ["relay", Role("sid"), Role("stdin"), "--json"], "relayed"),
    "re-emitted": ("scratch", ["relay", Role("sid"), "--json"], None),
    "not-an-object": ("scratch", ["relay", Role("sid"), Role("stdin"), "--json"],
                      "relay-refused+not-an-object"),
    "not-open": ("scratch", ["relay", Role("sid"), Role("stdin"), "--json"],
                 "relay-refused+not-open"),
}


def relay_recording(name: str) -> Recording:
    """The pinned recording of `bale relay … --json` named `name` (a key of
    RELAY_RECORDINGS), with the exit its fixtures/README.md row records and
    the stderr bale printed beside it (recorded since 0.4.51)."""
    where, argv, group = RELAY_RECORDINGS[name]
    return read_recording("relay", name, where, argv, group)


def relayed_block() -> str:
    """The relayed recording's own `block`: the exchange block of
    RELAY_RECORDED_SID that bale handed back (21 lines, LF, one trailing
    newline). It is intact — `take` reads one exchange block whose sha256
    trailer holds — so the tests carry it as twine's input, and the
    recording they replay answers for the sid the block names."""
    return relay_recording("relayed").line["block"]


def block_for_sid(sid: str, block: str | None = None) -> str:
    """`block` (default: relayed_block()) with its BEGIN sentinel naming
    `sid` instead. The sha256 trailer covers the body only, never the
    sentinel, so the block stays intact; a test uses it to carry a block
    whose sid is the one a recording names (the not-open refusal's)."""
    block = relayed_block() if block is None else block
    begin = block.split("\n", 1)[0]
    if not begin.startswith("BALE EXCHANGE BEGIN "):
        raise AssertionError(f"not an exchange block: {begin!r}")
    return f"BALE EXCHANGE BEGIN {sid}\n" + block.split("\n", 1)[1]


class RecordedRelay:
    """A run-seam double for `carry exchange` that answers twine's one relay
    argv, `bale relay <sid> - --json`, with a RECORDING's bytes, exit and
    stderr: by default the `relayed` line (relay_recording("relayed")),
    else the recording named by `recording`. Records every call.

    Since the pin at 0.4.51 the recordings are of twine's own argv: three
    were made as `relay <sid> - --json` with the paste block (or a line that
    is not one) on stdin, so nothing is assumed about how bale reads `-`.
    (The 0.4.49 recordings were made with a file and replayed for `-` on an
    assumption — `_read_relay_input` reads stdin for `-` and the file
    otherwise — that this double named; the recording retired it.) The
    `not-an-object` refusal was bale's answer to stdin that was neither a
    paste block nor JSON; replayed for a block twine vouched for, it stands
    for any refusal of what bale ingested. The `re-emitted` line answered
    `relay <sid> --json` with no input at all — an argv twine never builds —
    so replaying it for twine's proves only that twine never accepts a
    re-emission, not that bale would send one.

    Each recording answers for its own sid: a call whose sid is not the one
    the recording's line names fails the test, since bale's `sid` is the
    argument as given and the replay would claim what bale never said —
    unless `stdout` replaces the recording's bytes. `stdout`, `exit_code`
    and `stderr` answer bytes that are NOT bale's (an edited line, a
    `relayed` line beside exit 1, an empty stdout) to prove what twine
    refuses; `timed_out` and `capped` answer as the seam does for a call it
    killed. It answers only the relay argv shape and fails the test on
    anything else."""

    def __init__(self, recording: str | Recording = "relayed", *,
                 stdout: bytes | None = None, exit_code: int | None = None,
                 stderr: bytes | None = None, timed_out: bool = False,
                 capped: bool = False) -> None:
        self.calls: list[dict] = []
        self.recording = (relay_recording(recording) if isinstance(recording, str)
                          else recording)
        self.stdout = stdout
        self.exit_code = exit_code
        self.stderr = stderr
        self.timed_out = timed_out
        self.capped = capped

    def __call__(self, argv, *, cwd=None, stdin=None, timeout=None, env=None,
                 stdout_cap=None, on_spawn=None):
        from twine.process import RunResult
        argv = [str(a) for a in argv]
        self.calls.append({"argv": argv, "cwd": cwd, "stdin": stdin,
                           "timeout": timeout, "env": env, "stdout_cap": stdout_cap,
                           "on_spawn": on_spawn})
        if (len(argv) != 5 or Path(argv[0]).name != "bale" or argv[1] != "relay"
                or argv[3:] != ["-", "--json"]):
            raise AssertionError(f"RecordedRelay answers `relay <sid> - --json` only: "
                                 f"{argv}")
        if self.stdout is None and argv[2] != self.recording.line["sid"]:
            raise AssertionError(
                f"{self.recording.relpath} answers for sid "
                f"{self.recording.line['sid']!r}, not {argv[2]!r}: carry a block "
                "naming that sid, or name the stdout as not bale's")
        stderr = self.recording.stderr if self.stderr is None else self.stderr
        if self.timed_out or self.capped:
            return RunResult(argv=tuple(argv), exit_code=None,
                             stdout=b"" if self.stdout is None else self.stdout,
                             stderr=stderr, timed_out=self.timed_out,
                             stdout_capped=self.capped)
        stdout = self.recording.stdout if self.stdout is None else self.stdout
        code = self.recording.exit_code if self.exit_code is None else self.exit_code
        return RunResult(argv=tuple(argv), exit_code=code, stdout=stdout, stderr=stderr)

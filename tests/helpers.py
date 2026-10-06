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

Since session 5b: the unlock doubles. No `bale unlock --json` output has
been recorded for any outcome (a read-only probe cannot record one: unlock
mutates the registry), so every unlock answer a test sees is built here
from the key contract `format_unlock_json`'s docstring owns (quoted in the
session-5b brief §2.1) and named as a double: unlock_json_double (the one
line), UnlockDouble (a run-seam double answering the unlock argv) and
StubBale's `unlock_stdout`. A recording replaces them; it never joins them.
And RealGroup: a real `setsid`-led process group for the kill to kill.

Since session 5c: the run-seam doubles accept the seam's `on_spawn` hook
(and record it, never call it)."""

from __future__ import annotations

import io
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
from twine.cli import Context, main

TWINE = REPO_ROOT / "bin" / "twine"
PIN = "0.4.45"

# bale 0.4.45's three closed vocabularies, copied from the output of the
# probes twine-table-vocab and twine-apply-vocab (2026-10-03, quoted in the
# session-4 brief §2) — the oracle the consumption manifest's
# [[vocabulary]] entries and the transition table's bale axes are held to.
# Never edited to match the manifest: a pin bump re-records them by probe.
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


class Role(str):
    """A per-run argv value's role, standing in for the value in a fixture
    name (`sid`, `stdin`, `tarball`). A Role is its own `_` group: it is
    never joined to the flag before it, because it is not that flag's
    value."""


def fixture_key(argv: list[str]) -> list[str]:
    """The argv after `bale`, normalized for naming a fixture: the values
    that differ per run are replaced by their roles (fixtures/README.md,
    "Per-run values"). `relay <sid> -` keys as relay, sid, stdin (a file
    argument as `file`); every positional after `apply` is the tarball.
    Any other argv is its own key."""
    argv = [str(a) for a in argv]
    if argv[:1] == ["relay"] and len(argv) >= 2:
        key: list[str] = ["relay", Role("sid")]
        for token in argv[2:]:
            if token == "-":
                key.append(Role("stdin"))
            elif token.startswith("-"):
                key.append(token)
            else:
                key.append(Role("file"))
        return key
    if argv[:1] == ["apply"]:
        return ["apply"] + [t if t.startswith("-") else Role("tarball")
                            for t in argv[1:]]
    if argv[:1] == ["unlock"] and len(argv) >= 2 and not argv[1].startswith("-"):
        # `unlock <sid> --reason aborted --json` (session 5b): the sid is per run.
        return ["unlock", Role("sid"), *argv[2:]]
    return argv


def fixture_relpath(argv: list[str], cwd: str) -> str:
    """The fixtures/ path a recorded bale output lands at, from the argv
    after `bale` and where it ran — fixtures/README.md's naming rule:

      fixtures/bale-<pin>/<where>/<verb>_<flag[-value…]>[_…].<ext>

    `where` is `twine-src` for cwd "repo" and `anywhere` otherwise. The
    argv is normalized first (fixture_key: a per-run value becomes its
    Role); each flag is joined to the values that follow it with `-`, a
    Role is a group of its own, the groups are joined with `_`; `.json`
    when --json is among the flags, else `.txt`.
    """
    where = "twine-src" if cwd == "repo" else "anywhere"
    argv = list(argv)
    key = argv if any(isinstance(t, Role) for t in argv) else fixture_key(argv)
    groups: list[str] = []
    for token in key:
        if token.startswith("-") or not groups or isinstance(token, Role):
            groups.append(str(token))
        else:
            groups[-1] += "-" + token
    ext = ".json" if "--json" in key else ".txt"
    return f"fixtures/bale-{PIN}/{where}/{'_'.join(groups)}{ext}"


# A fixtures/README.md row for the stdout of a command: file, command, ran
# in, exit (a number, or `unrecorded`), bytes, sha256.
EXIT_ROW = re.compile(r"^\| `(?P<file>bale-[^`]+)` \| `[^`]+` \| `[^`]+` "
                      r"\| (?P<exit>\d+|unrecorded) \| \d+ \| `[0-9a-f]{64}` \|$", re.M)
UNRECORDED = "unrecorded"


def recorded_exits() -> dict[str, int | str]:
    """Each recorded output's exit code as fixtures/README.md states it,
    keyed by its fixtures/ path: an int, or "unrecorded"."""
    text = (REPO_ROOT / "fixtures" / "README.md").read_text(encoding="utf-8")
    return {f"fixtures/{m['file']}": (UNRECORDED if m["exit"] == UNRECORDED
                                      else int(m["exit"]))
            for m in EXIT_ROW.finditer(text)}


# Fixtures that are not the stdout of a `bale` argv (fixtures/README.md,
# "Emissions and carried pastes"): the crafter's emissions, and pastes of
# bale output the architect carried. Both land as .txt.
EMISSION_TOOLS = {"crafter": "tools/craft_response.py"}


def emission_relpath(tool: str, argv: list[str]) -> str:
    """fixtures/bale-<pin>/<tool>/<flag[-value…]>[_…].txt for a bale tool
    run with `argv` — fixture_relpath's grouping, with a `-` value (stdin)
    spelled `stdin` so no name carries a bare dash."""
    if tool not in EMISSION_TOOLS:
        raise ValueError(f"unknown emitting tool {tool!r}")
    spelled = ["stdin" if token == "-" else token for token in argv]
    groups: list[str] = []
    for token in spelled:
        if token.startswith("-") or not groups:
            groups.append(token)
        else:
            groups[-1] += "-" + token
    return f"fixtures/bale-{PIN}/{tool}/{'_'.join(groups)}.txt"


def carried_relpath(kind: str, identity: str, to: str | None = None) -> str:
    """fixtures/bale-<pin>/carried/<kind>_<identity>[_to-<addressee>].txt
    for a carried paste: the block kind, the slug or sid its sentinel
    names, and for a relay block its addressee."""
    tail = f"_to-{to}" if to else ""
    return f"fixtures/bale-{PIN}/carried/{kind}_{identity}{tail}.txt"


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


def scaffold() -> str:
    """The crafter's unfilled probe scaffold, as recorded."""
    return PROBE_SCAFFOLD.read_bytes().decode("utf-8")


def filled_probe(body: str = 'echo "--- section: shell ---"\necho "bash ok"',
                 what: str = "what bash reports about itself.",
                 why: str = "a carry-probe test needs a filled scaffold.") -> str:
    """The scaffold with its two header placeholders replaced and the
    probe() body replaced by `body` (indented two spaces) — the filling
    a worker does, done mechanically. Every TODO(worker) is gone."""
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
    fixture: the path is fixture_relpath(argv after `bale`, where) — the
    argv normalized, so a per-run sid or tarball path finds its one
    recording — with `where` "repo" when cwd is `repo_root`.

    The answer is the fixture's bytes on stdout, the exit code its
    fixtures/README.md row records, and empty stderr (no row records
    stderr yet, and twine only surfaces it). A row whose exit is
    `unrecorded` is refused unless the test names the code it assumes in
    `assumed_exits` (fixtures/ path -> code), so an assumption is always
    visible where it is made. An argv with no fixture raises — a test
    must never reach a live bale."""

    def __init__(self, repo_root: Path,
                 assumed_exits: dict[str, int] | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.calls: list[list[str]] = []
        self.exits = recorded_exits()
        self.assumed_exits = dict(assumed_exits or {})

    def __call__(self, argv, *, cwd=None, stdin=None, timeout=None, env=None,
                 stdout_cap=None, on_spawn=None):
        from twine.process import RunResult
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        if not argv or Path(argv[0]).name != "bale":
            raise AssertionError(f"FixturePlayer answers bale argvs only: {argv}")
        where = ("repo" if cwd is not None
                 and Path(cwd).resolve() == self.repo_root else "anywhere")
        rel = fixture_relpath(argv[1:], where)
        path = REPO_ROOT / rel
        if not path.is_file():
            raise AssertionError(f"no recorded fixture for {argv} at {rel}")
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
                         stdout=path.read_bytes(), stderr=b"")


class StubBale:
    """A double, not bale: a temp install root whose `bin/bale` is a
    bash script this class writes, and `bin/VERSION` at the pin. The
    script records its argv, cwd and (for `relay`) stdin under `record`,
    then replays the bytes of `relay_stdout`, `apply_stdout` or (session
    5b, a double built by unlock_json_double) `unlock_stdout` on stdout,
    `stderr` on stderr, and exits `exit_code`. It lets the CLI run end to
    end as a subprocess (`--bale-root`) with no bale anywhere; the bytes
    it replays are a recorded fixture or a double the test names."""

    def __init__(self, relay_stdout: Path | None = None,
                 apply_stdout: Path | None = None, exit_code: int = 0,
                 stderr: str = "", unlock_stdout: Path | None = None) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="twine-stub-bale-")
        base = Path(self._dir.name)
        self.root = base / "root"
        self.record = base / "record"
        (self.root / "bin").mkdir(parents=True)
        self.record.mkdir()
        (self.root / "bin" / "VERSION").write_text(PIN + "\n", encoding="utf-8")
        q = shlex.quote
        replay = {"relay": relay_stdout, "apply": apply_stdout,
                  "unlock": unlock_stdout}
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
                lines.append(f"if [ \"$1\" = {verb} ]; then cat {q(str(source))}; fi")
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
# Unlock doubles (Arc 1 session 5b). No `bale unlock --json` output has been
# recorded: every answer below is built from format_unlock_json's key
# contract (bale 0.4.45, bin/bale_report.py, quoted verbatim in the
# session-5b brief §2.1) and is a double, named as one. The two recordings
# queued at sitting continue-twine-006 replace them.
# ---------------------------------------------------------------------------

# format_unlock_json's nine keys, in the order its body builds them.
UNLOCK_KEYS = ("outcome", "sid", "log", "closure_reason", "session_dir_wiped",
               "branch_preserved", "telemetry", "debris", "sweep")


def unlock_json_double(sid: str, /, **overrides) -> bytes:
    """A `bale unlock <sid> --reason aborted --json` stdout line, as a double:
    the nine keys of the key contract in its order, `json.dumps` with
    default separators, one line, LF — the close of a session (`outcome`
    "unlocked", exit 0). `overrides` replaces values (a `no-op`, another
    sid, another reason) to prove what twine refuses."""
    import json as _json
    obj = {"outcome": "unlocked", "sid": sid,
           "log": f"/double/repo/.bale/logs/{sid}.log",
           "closure_reason": "aborted", "session_dir_wiped": True,
           "branch_preserved": False,
           "telemetry": f"claude/telemetry/{sid}.json", "debris": None,
           "sweep": None}
    for key, value in overrides.items():
        if key not in obj:
            raise KeyError(f"{key!r} is not in format_unlock_json's key contract")
        obj[key] = value
    assert tuple(obj) == UNLOCK_KEYS
    return (_json.dumps(obj) + "\n").encode("utf-8")


def unlock_refusal_double(message: str) -> bytes:
    """bale's fail() on stderr, as a double: `[bale] error: <msg>` (bin/bale
    lines 517-543); stdout is empty and the exit is 1."""
    return f"[bale] error: {message}\n".encode("utf-8")


class UnlockDouble:
    """A run-seam double for the closure: records every call and answers it
    with the given stdout, stderr and exit (default: the close of the sid
    the argv names, exit 0). `timed_out` answers as the seam does for a call
    it killed. Never bale: it answers only the one unlock argv shape and
    fails the test on anything else."""

    def __init__(self, stdout: bytes | None = None, stderr: bytes = b"",
                 exit_code: int | None = 0, timed_out: bool = False) -> None:
        self.calls: list[dict] = []
        self.stdout, self.stderr = stdout, stderr
        self.exit_code, self.timed_out = exit_code, timed_out

    def __call__(self, argv, *, cwd=None, stdin=None, timeout=None, env=None,
                 stdout_cap=None, on_spawn=None):
        from twine.process import RunResult
        argv = [str(a) for a in argv]
        self.calls.append({"argv": argv, "cwd": cwd, "stdin": stdin,
                           "timeout": timeout, "env": env, "stdout_cap": stdout_cap,
                           "on_spawn": on_spawn})
        if Path(argv[0]).name != "bale" or argv[1:2] != ["unlock"]:
            raise AssertionError(f"UnlockDouble answers the unlock argv only: {argv}")
        stdout = (unlock_json_double(argv[2]) if self.stdout is None
                  else self.stdout)
        if self.timed_out:
            return RunResult(argv=tuple(argv), exit_code=None, stdout=b"",
                             stderr=self.stderr, timed_out=True)
        return RunResult(argv=tuple(argv), exit_code=self.exit_code, stdout=stdout,
                         stderr=self.stderr)


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


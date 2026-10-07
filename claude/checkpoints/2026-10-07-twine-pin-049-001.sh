#!/usr/bin/env bash
# Blind checkpoint, v2 — twine-src session `twine-pin-049` (slug), authored by
# the twine desk on 2026-10-07 from the brief, before the landing exists.
# Outcome contracts only: the pin and schema hashes in the manifest, no
# [[wanted]] left, the vocabulary's home re-pinned, every one of the twenty
# verified recordings present byte-exact under fixtures/bale-0.4.49/ with a
# README row, three crafter emissions present and rowed, the doubles gone,
# the pin named nowhere as 0.4.45 under twine/ tests/ share/, bale check
# driving the pin, the seed and bin untouched, VERSION, the suite.
#
# Runs in the staging tree's root (cwd). Exit 0 / 1 / 2: passed / a probe
# failed by name / the oracle is broken. Writes: one temporary directory for
# the bale-root stand-ins (announced, removed at exit) and the suite's own
# temporary directories. Nothing under the tree. Python under -I -B.
set -u
exec python3 -I -B - "$@" <<'PY'
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, tomllib
from pathlib import Path


def _excepthook(kind, value, tb):
    import traceback
    print("[ORACLE ERROR] the checkpoint itself raised; exit 2 (not a verdict):", file=sys.stderr)
    traceback.print_exception(kind, value, tb)
    sys.stdout.flush()
    cleanup()
    os._exit(2)


sys.excepthook = _excepthook
TREE = Path.cwd()
for needed in ("bin/twine", "share/bale-consumption.toml", "fixtures/README.md", "tests/helpers.py", "VERSION",
               "twine-seed.md"):
    if not (TREE / needed).exists():
        print(f"[ORACLE ERROR] {needed} is not under the cwd {TREE}; exit 2", file=sys.stderr)
        sys.exit(2)
SCRATCH = Path(tempfile.mkdtemp(prefix="twine-pin-049-checkpoint-"))
print(f"[checkpoint] writes: {SCRATCH} (temporary, removed at exit) and the suite's own temporary "
      "directories; nothing under the tree")

PIN = "0.4.49"
VERSION = b"0.8.0\n"
SCHEMAS = {
    "bundle-manifest.schema.json": "3384ebcd52a08044356f30f1031f4389e9b4427d81602173b0c59f4f9f9cea23",
    "changelog-record.schema.json": "7b6d351c052dad8588b05e7592da78f9e9052a671ad6dae9395bfd6d531c5b5c",
    "diagnostics.schema.json": "bfeef3cc0a6b91b47b1c1c9084ca47349b23a6661b10c848da3b4ef28b413521",
    "escalation-record.schema.json": "16729aae82e20425f91b9fb343de6a74d00fa417ce3cd718767413deee550c41",
    "exchange-record.schema.json": "c9c291899103c4a73768ef930697722b89c5c3ef8f5b388c78c36741316cddc8",
    "request-manifest.schema.json": "70a0c2bd3b6b0d4cf17bc97010c2b7d58931527b7b3100aa984ca3576c075e3d",
    "response-manifest.schema.json": "02d2b6413d078e031641c99e09a9fea909555bdfcb9b2a8a110dbdce63f5817e",
    "telemetry-record.schema.json": "b79d7bf75c10f5799484f906954461e7379ef6d4a870bb7df8c08ce050b38825",
}
APPLY_HOME_SHA = "20871bc61408ef9a21a2d14789399463cf5ed9a92802b951f6a1438fe75b0c78"
APPLY_OUTCOMES = ["applied", "held", "reverted", "bailout", "clarification", "dry-run",
                  "scope-drift-refused", "required-check-refused", "base-drift-refused"]
# The twenty recordings the desk verified against the probes' printed hashes (brief §2, rows 1-20),
# plus rows 21-23, the three crafter emissions, verified through their gzip+base64 copies.
RECORDINGS = [("--version", 12, "49f3d68760069239c4246ca6ab02a58d21ba64469a0fd4714ac3572f22b4791e"), ("status_--json", 2040, "bf35950de9441ff620ce0e2b620a7809def46f01f33cce2c6d852a289516d26c"), ("unlock_sid_--json (not-open)", 344, "a374a63ffd5027180c1b0833be6b590d778402b428b6f8be66590c96b6050c82"), ("unlock_--integration_--json (integration-json)", 488, "d6e6668700da2266cc8386494ea65b0a0bc6eb22406c750a541c97e0b828376e"), ("open_--check_bundle_--json (rehearsed)", 708, "2a87907131523e40d59a77175c8e20127dcf200196fcf692dda6a2d28cccc80e"), ("stats_--json", 13592, "cc2936b8a5f58fa4dbcd2dd3bc6455a286d4f27aa9178bc814b2ad62ac6df085"), ("stats_--sid-2026-10-01-twine-seed-001_--json", 4026, "c50f1c6661f291e1378c42e6599ed60f3127452e39c5ae2f5b12f8b20df73455"), ("pack_goal_--slug-ro_--read-only_--no-readme_--json (packed; opener key)", 2031, "a45c382fc4800ccdda614fb0778d7f36f7981c2383e99b610a99bed1e56ea5c9"), ("open_bundle_--json (opened)", 2308, "75872c420f92ca9696de2944ce19c4f8c7fd4a3f246064223e1c697142244616"), ("open_bundle_--json (second-desk)", 2225, "9bc523becf733ef3cfa00db3f973bb141685882df640e08dcbaaedda34976020"), ("relay_sid_file_--json (relayed, round 1 from worker)", 1373, "40bd534932ddbe3098fc54af8560371b698d9eed8f719b63e708ab2ac7333b71"), ("relay_sid_--json (re-emitted)", 1311, "47849102980eaff464160a04a4b3f06ac4a58ebf05a559dc89518a3f03bed400"), ("relay_sid_file_--json (relay-refused: ingest)", 517, "84f6bced9a6ef57d692ef2050b8cd5de6738f9c43e155090f93bf923adede61d"), ("relay_sid_file_--json (relay-refused: session gate)", 473, "e0cb6d390ae7edd333aa1ae9145be59cff556f02b674dfc61c820b83f856bbcf"), ("apply_--dry-run_--json_tarball (dry-run)", 290, "266fc2539c08511d1ee29cb29442eacad6d6ebdab738723c3c0bf440fac8b955"), ("apply_--dry-run_--json_tarball (scope-drift-refused)", 521, "9f17bd60b2820b9b442a80b1c30a556c22fcace67fb5803843e3181b4cf1fcd7"), ("unlock_sid_--json (unlock-refused: hold-branch)", 569, "14669f1831af42e2c39c7f7e9ab1995ff21ab8c2307675ed5d9df56db88f90ce"), ("unlock_sid_--reason-aborted_--json (unlocked, aborted)", 489, "1f91385974a148652c5b95434061772e83e397f535b272fc0dcfd28018efe921"), ("unlock_sid_--json (unlocked, closed-read-only)", 498, "8af871da9c5d437a055a01154f0d34591821b9fc313324eeb1e5301aa0f5a397"), ("unlock_--json (no-op)", 231, "e7a675b90e559559496927b2de7baad3f31f7d62268991615c3beded8bbe501e"), ("--light-block-stdin (row 22)", 722, "55c53cfe057b2e5a5cee10b7f6eabbbcb5365e24cc481329b27f19c6f3cebdb8"), ("--probe-twine-take-fixture (row 21)", 2626, "1f5e235fd0958b4e984b2b5fe7c1745466171c02eff9603b1eb09330ccdca00e"), ("--emit-block-stdin (row 23)", 1618, "fda8a4d0d12f930f9077068163098aec626583d59e73c9a8d916b6da21b410f8")]
SEED_SHA = "abb55c02c0fb3abdeb2b8b155c6160448ce14330dacabe27b18568aae905d9ed"
DOUBLE_NAMES = ("unlock_json_double", "unlock_refusal_double", "UnlockDouble")
results = []


def cleanup():
    shutil.rmtree(SCRATCH, ignore_errors=True)


def probe(label, failures):
    results.append((label, list(failures)))
    print((f"[FAIL] {label}: " + "; ".join(failures)) if failures else f"[PASS] {label}")


def control(label, failures):
    if not failures:
        print(f"[ORACLE ERROR] control {label!r} did not fire; exit 2", file=sys.stderr)
        cleanup()
        os._exit(2)
    print(f"[CONTROL] {label}: fires")


def sha(data):
    return hashlib.sha256(data).hexdigest()


# --- detectors -----------------------------------------------------------------

def det_manifest(m):
    f = []
    if (m.get("bale") or {}).get("pin") != PIN:
        f.append(f"pin is {(m.get('bale') or {}).get('pin')!r}, not {PIN!r}")
    if (m.get("bale") or {}).get("schemas") != SCHEMAS:
        f.append("the eight schema hashes are not the pinned values")
    if m.get("wanted"):
        f.append(f"{len(m['wanted'])} [[wanted]] entries remain")
    surfaces = m.get("surface") or []
    verbs = {(s.get("verb"), tuple(s.get("flags") or [])) for s in surfaces if s.get("kind") == "verb"}
    for want in (("open", ("--json",)), ("relay", ("--json",)), ("pack", ("--json",))):
        if want not in verbs:
            f.append(f"no [[surface]] for {want[0]} {' '.join(want[1])}")
    unlock = [s for s in surfaces if s.get("verb") == "unlock"]
    if not unlock or not {"reason", "message", "open_sessions"} <= set(unlock[0].get("keys") or []):
        f.append("the unlock surface's keys lack reason/message/open_sessions")
    if any(s.get("written_against") != PIN for s in surfaces if "written_against" in s):
        f.append("a surface's written_against is not the pin")
    vocab = {v.get("axis"): v for v in (m.get("vocabulary") or [])}
    ap = vocab.get("apply-outcome") or {}
    if ap.get("values") != APPLY_OUTCOMES:
        f.append("apply-outcome values changed")
    if ap.get("home_sha256") != APPLY_HOME_SHA:
        f.append("apply-outcome home_sha256 is not bin/bale_report.py's at 0.4.49")
    if any(v.get("written_against") != PIN for v in vocab.values()):
        f.append("a vocabulary's written_against is not the pin")
    return f


def det_recordings(present):
    """present: {sha256: (path, size)} of every file under fixtures/bale-0.4.49/."""
    f = []
    for label, nbytes, h in RECORDINGS:
        if h not in present:
            f.append(f"recording missing: {label}")
        elif present[h][1] != nbytes:
            f.append(f"{label}: {present[h][1]} bytes, expected {nbytes}")
    return f


def det_readme_rows(readme_text, present):
    """Every file under bale-0.4.49/ has a row carrying its sha256 and byte count; a 0.4.49 section exists."""
    f = []
    if "## bale 0.4.49" not in readme_text:
        f.append("fixtures/README.md has no '## bale 0.4.49' section")
    for h, (path, size) in present.items():
        row = next((l for l in readme_text.splitlines() if h in l), None)
        if row is None:
            f.append(f"no README row carries {path}'s sha256")
        elif f"| {size} |" not in row.replace("  ", " "):
            f.append(f"the row for {path} does not carry its byte count {size}")
    return f


def det_emissions(crafter_files):
    f = []
    if len(crafter_files) < 3:
        f.append(f"{len(crafter_files)} crafter emission(s) under bale-0.4.49/, expected 3")
    names = " ".join(crafter_files)
    for want in ("probe", "light-block", "emit-block"):
        if want not in names:
            f.append(f"no crafter emission named for {want}")
    return f


def det_doubles_gone(helpers_text):
    return [f"tests/helpers.py still defines {n}" for n in DOUBLE_NAMES if re.search(r"\b" + n + r"\b", helpers_text)]


def det_no_old_pin(hits):
    return [f"0.4.45 still named in {p}" for p in hits]


def det_bale_check(ok_json, other_json):
    f = []
    if not (isinstance(ok_json, dict) and ok_json.get("ok") is True):
        f.append("twine bale check against a 0.4.49 root is not ok")
    if not (isinstance(other_json, dict) and other_json.get("ok") is False):
        f.append("twine bale check against a 0.4.45 root is not refused")
    return f


def det_untouched(seed_sha, bin_same, old_fixtures_same):
    f = []
    if seed_sha != SEED_SHA:
        f.append("twine-seed.md changed")
    if not bin_same:
        f.append("bin/twine changed")
    if not old_fixtures_same:
        f.append("fixtures/bale-0.4.45/ changed")
    return f


def det_version(raw):
    return [] if raw == VERSION else [f"VERSION is {raw!r}, not {VERSION!r}"]


def det_suite(code, tail):
    return [] if code == 0 else [f"the suite exited {code}: {tail}"]


# --- controls ------------------------------------------------------------------

control("manifest", det_manifest({"bale": {"pin": "0.4.45", "schemas": SCHEMAS}, "surface": [], "vocabulary": []}))
control("recordings", det_recordings({}))
control("readme rows", det_readme_rows("nothing", {"a" * 64: ("x", 1)}))
control("emissions", det_emissions([]))
control("doubles", det_doubles_gone("def unlock_json_double(sid):"))
control("old pin", det_no_old_pin(["tests/helpers.py"]))
control("bale check", det_bale_check({"ok": False}, {"ok": True}))
control("untouched", det_untouched("0" * 64, False, False))
control("version", det_version(b"0.7.1\n"))
control("suite", det_suite(1, "boom"))

# --- probes --------------------------------------------------------------------

manifest = tomllib.loads((TREE / "share/bale-consumption.toml").read_text(encoding="utf-8"))
probe("manifest-pinned-to-0.4.49", det_manifest(manifest))

fx = TREE / "fixtures" / f"bale-{PIN}"
present = {}
if fx.is_dir():
    for p in sorted(fx.rglob("*")):
        if p.is_file():
            data = p.read_bytes()
            present[sha(data)] = (str(p.relative_to(TREE)), len(data))
probe("twenty-three-recordings-byte-exact", det_recordings(present))
probe("readme-rows-for-every-0.4.49-fixture",
      det_readme_rows((TREE / "fixtures/README.md").read_text(encoding="utf-8"), present))
probe("three-crafter-emissions-at-0.4.49",
      det_emissions([p.name for p in (fx / "crafter").iterdir()] if (fx / "crafter").is_dir() else []))
probe("unlock-doubles-gone", det_doubles_gone((TREE / "tests/helpers.py").read_text(encoding="utf-8")))

hits = []
for sub in ("twine", "tests", "share"):
    for p in sorted((TREE / sub).rglob("*")):
        if p.is_file() and p.suffix in (".py", ".toml") and "0.4.45" in p.read_text(encoding="utf-8", errors="replace"):
            hits.append(str(p.relative_to(TREE)))
probe("no-0.4.45-under-twine-tests-share", det_no_old_pin(hits))


def bale_check(version):
    root = SCRATCH / f"root-{version}"
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "bin" / "bale").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (root / "bin" / "bale").chmod(0o755)
    r = subprocess.run([sys.executable, "-I", "-S", "-B", str(TREE / "bin/twine"), "bale", "check", "--json",
                        "--bale-root", str(root)], cwd=str(TREE), env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return None


probe("bale-check-drives-the-new-pin", det_bale_check(bale_check("0.4.49"), bale_check("0.4.45")))

old = TREE / "fixtures/bale-0.4.45"
old_ok = old.is_dir() and len(list(old.rglob("*"))) >= 10
probe("seed-bin-and-0.4.45-fixtures-untouched",
      det_untouched(sha((TREE / "twine-seed.md").read_bytes()),
                    sha((TREE / "bin/twine").read_bytes()) == "d5388349e4559df3f93f74a48f4740a512466a1224f84c98f655f3f3b4d4669e",
                    old_ok))
probe("version-is-0.8.0", det_version((TREE / "VERSION").read_bytes()))

suite = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                       cwd=str(TREE), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900)
probe("suite-green", det_suite(suite.returncode, suite.stderr.strip()[-400:]))

cleanup()
failed = [label for label, f in results if f]
print(f"[checkpoint] {len(results)} probes, {len(failed)} failed" + (": " + ", ".join(failed) if failed else ""))
sys.exit(1 if failed else 0)
PY

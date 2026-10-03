#!/usr/bin/env bash
# Blind checkpoint — twine-src Arc 1 session 2b-ii (slug twine-carry-bale):
# `twine carry exchange` and `twine carry response`.
# Authored at sitting 2026-10-02-continue-twine-004 from the session's brief,
# before any implementation existed, by a desk that does not build against it.
#
# Outcomes graded (never mechanisms): what each verb sends to bale (argv and
# stdin, as a stand-in `bale` records them), what it reports (exit code, the
# JSON twin's fixed keys, human-mode stdout), what it refuses without calling
# bale, that `bale apply` is never called without --dry-run, that the dry-run
# fixture is landed byte-exact, and that the unittest suite passes.
#
# The stand-in `bale` is installed in a temp directory, first on PATH and as
# TWINE_BALE_ROOT, so whichever way twine finds bale, it finds the stand-in.
# Calls other than `relay` and `apply` (a --version check, say) are answered
# and ignored.
#
# Writes: only under one `mktemp -d` directory, removed at exit. Python runs
# with -B and PYTHONDONTWRITEBYTECODE. Nothing in the tree is written.
# Exit codes (TARBALL.md 7.5): 0 all pass, 1 a probe failed, 2 the oracle
# itself is broken (failed control, missing interpreter, unlocatable root).
set -u
export PYTHONDONTWRITEBYTECODE=1

echo "checkpoint twine-carry-bale v1: writes only under a mktemp -d directory, removed at exit"

root=""
if [ -f "./bale.toml" ] && [ -f "./bin/twine" ]; then
  root="$(pwd)"
else
  here="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
  if [ -n "$here" ] && [ -f "$here/../../bale.toml" ] && [ -f "$here/../../bin/twine" ]; then
    root="$(cd "$here/../.." && pwd)"
  fi
fi
if [ -z "$root" ]; then
  echo "[FAIL] control: repository root not found (bale.toml and bin/twine at cwd or two levels above the script)"
  exit 2
fi
echo "root: $root"
if ! command -v python3 >/dev/null 2>&1; then
  echo "[FAIL] control: python3 not found"; exit 2
fi
if ! command -v bash >/dev/null 2>&1; then
  echo "[FAIL] control: bash not found"; exit 2
fi

python3 -B - "$root" <<'PY'
import base64, hashlib, json, os, shlex, shutil, subprocess, sys, tempfile, traceback
from pathlib import Path

def _oracle_crashed(kind, value, tb):
    print("[FAIL] control: the checkpoint itself raised an error")
    traceback.print_exception(kind, value, tb, file=sys.stdout)
    sys.stdout.flush()
    os._exit(2)
sys.excepthook = _oracle_crashed

ROOT = Path(sys.argv[1])
TWINE = ROOT / "bin" / "twine"
SID = "2026-10-02-twine-take-read-001"
EMIT = base64.b64decode("QkFMRSBFWENIQU5HRSBCRUdJTiAyMDI2LTEwLTAyLXR3aW5lLXRha2UtcmVhZC0wMDEKIyBiYWxlIGV4Y2hhbmdlIHJlY29yZCDigJQgc2Vzc2lvbiAyMDI2LTEwLTAyLXR3aW5lLXRha2UtcmVhZC0wMDEg4oCUIHJvdW5kIDEg4oCUIGZyb20gd29ya2VyIHRvIHBsYW5uZXIKIyAyIGJsb2NraW5nIHF1ZXN0aW9uKHMpLiBQbGFubmVyOiBhbnN3ZXIgYXMgYW4gZXhjaGFuZ2UgcmVjb3JkIChmcm9tOiBwbGFubmVyLCByb3VuZCAyLCBhbnN3ZXJzW10ga2V5ZWQgcXVlc3Rpb25fcm91bmQgMSkgYW5kIHJlY29yZCBpdCB3aXRoIGBiYWxlIHJlbGF5IDIwMjYtMTAtMDItdHdpbmUtdGFrZS1yZWFkLTAwMSA8YW5zd2VyLmpzb258LT5gLgojIEJvZHk6IHRoZSByZWNvcmQgKGV4Y2hhbmdlLXJlY29yZC5zY2hlbWEuanNvbikuIFRyYWlsZXI6IHNoYTI1NiBvZiB0aGUgYm9keSBieXRlcyDigJQgYSBtaXNtYXRjaCBvbiBpbmdlc3QgbWVhbnMgYSB0cnVuY2F0ZWQgcGFzdGU7IHJlLXJlcXVlc3QgdGhlIGJsb2NrIHJhdGhlciB0aGFuIHJlYXNvbiBmcm9tIGl0Lgp7CiAgInJlY29yZF92ZXJzaW9uIjogMSwKICAic2Vzc2lvbl9pZCI6ICIyMDI2LTEwLTAyLXR3aW5lLXRha2UtcmVhZC0wMDEiLAogICJyb3VuZCI6IDEsCiAgImZyb20iOiAid29ya2VyIiwKICAiY3JlYXRlZF9hdCI6ICIyMDI2LTEwLTAyVDE3OjU3OjM0KzAwOjAwIiwKICAicXVlc3Rpb25zIjogWwogICAgewogICAgICAicXVlc3Rpb24iOiAiU3BlY2ltZW4gcm93IDEgXHUyMDE0IGRvZXMgdHdpbmUgdGFrZSByZXBvcnQgYSBwcm9iZSBibG9jaydzIHNjcmlwdCB3aXRoIGl0cyBmZW5jZXMgc3RyaXBwZWQ/IiwKICAgICAgImNvbnRleHQiOiAiUmVjb3JkaW5nIGZpeHR1cmVzIGZvciB0d2luZSB0YWtlIChzcGVjaW1lbiBvbmx5OyBubyBhbnN3ZXIgd2FudGVkKSIsCiAgICAgICJkZWZhdWx0X2Fzc3VtcHRpb24iOiAic3RyaXBwZWQiLAogICAgICAid2h5X2Jsb2NrZWQiOiAibm90IGJsb2NrZWQ7IGEgcmVjb3JkZWQgc3BlY2ltZW4gZm9yIHRoZSBwYXJzZXIncyB0ZXN0cyIKICAgIH0sCiAgICB7CiAgICAgICJxdWVzdGlvbiI6ICJTcGVjaW1lbiByb3cgMjogaXMgYSByZWxheSBibG9jayB0byBwbGFubmVyIGV2ZXIgZGVsaXZlcmVkIHRvIGEgd29ya2VyPyIsCiAgICAgICJjb250ZXh0IjogIlJlY29yZGluZyB0aGUgcm91dGluZyBydWxlJ3MgZml4dHVyZSAoc3BlY2ltZW4gb25seTsgbm8gYW5zd2VyIHdhbnRlZCkiLAogICAgICAiZGVmYXVsdF9hc3N1bXB0aW9uIjogIm5ldmVyIiwKICAgICAgIndoeV9ibG9ja2VkIjogIm5vdCBibG9ja2VkOyBhIHJlY29yZGVkIHNwZWNpbWVuIGZvciB0aGUgcGFyc2VyJ3MgdGVzdHMiLAogICAgICAib3B0aW9ucyI6IFsKICAgICAgICAibmV2ZXIiLAogICAgICAgICJ3aXRoIGNvbnNlbnQiCiAgICAgIF0sCiAgICAgICJyZWNvbW1lbmRhdGlvbiI6ICJuZXZlciIsCiAgICAgICJwcmlvcml0eSI6ICJiYXRjaGVkIiwKICAgICAgIm9yaWdpbiI6ICJpbnRlbnQtZ2FwIgogICAgfQogIF0KfQojIHNoYTI1NiAyZWUzMDg0NzAzNjAwMWI4ZjU3Y2QxY2JmNGI4ZmQ3ZmNiZjMyMmFhZDkyN2EyZmYzOGQzZDlhMTE5NWU5YzQ3CkJBTEUgRVhDSEFOR0UgRU5ECg==")     # crafter --emit-block emission
LIGHT = base64.b64decode("PT09IExJR0hUIEJFR0lOIDIwMjYtMTAtMDItdHdpbmUtdGFrZS1yZWFkLTAwMSA9PT0KWzFdIHF1ZXN0aW9uOiAgICAgU3BlY2ltZW4gcm93IDEg4oCUIGRvZXMgdHdpbmUgdGFrZSByZXBvcnQgYSBwcm9iZSBibG9jaydzIHNjcmlwdCB3aXRoIGl0cyBmZW5jZXMgc3RyaXBwZWQ/CiAgICB3aGlsZSBkb2luZzogIFJlY29yZGluZyBmaXh0dXJlcyBmb3IgdHdpbmUgdGFrZSAoc3BlY2ltZW4gb25seTsgbm8gYW5zd2VyIHdhbnRlZCkKICAgIHdvdWxkIGFzc3VtZTogc3RyaXBwZWQKICAgIHdoeSBibG9ja2VkOiAgbm90IGJsb2NrZWQ7IGEgcmVjb3JkZWQgc3BlY2ltZW4gZm9yIHRoZSBwYXJzZXIncyB0ZXN0cwpbMl0gcXVlc3Rpb246ICAgICBTcGVjaW1lbiByb3cgMjogaXMgYSByZWxheSBibG9jayB0byBwbGFubmVyIGV2ZXIgZGVsaXZlcmVkIHRvIGEgd29ya2VyPwogICAgd2hpbGUgZG9pbmc6ICBSZWNvcmRpbmcgdGhlIHJvdXRpbmcgcnVsZSdzIGZpeHR1cmUgKHNwZWNpbWVuIG9ubHk7IG5vIGFuc3dlciB3YW50ZWQpCiAgICB3b3VsZCBhc3N1bWU6IG5ldmVyCiAgICB3aHkgYmxvY2tlZDogIG5vdCBibG9ja2VkOyBhIHJlY29yZGVkIHNwZWNpbWVuIGZvciB0aGUgcGFyc2VyJ3MgdGVzdHMKUmVwbHk6IGFuc3dlciBpbmxpbmUsICJhcyBhc3N1bWVkIiwgb3IgImZvcm1hbCIuCj09PSBMSUdIVCBFTkQgMjAyNi0xMC0wMi10d2luZS10YWtlLXJlYWQtMDAxID09PQo=")   # crafter --light-block emission
DRY = base64.b64decode("eyJvdXRjb21lIjogImRyeS1ydW4iLCAic2lkIjogIjIwMjYtMTAtMDItdHdpbmUtY2FycnktcHJvYmUtMDAyIiwgImxvZyI6ICIvaG9tZS9jaG9yZHNwaGVyZS90d2luZS1zcmMvLmJhbGUvbG9ncy8yMDI2LTEwLTAyLXR3aW5lLWNhcnJ5LXByb2JlLTAwMi5sb2ciLCAidmVyZGljdCI6IG51bGwsICJtZXJnZSI6IG51bGwsICJ0ZWxlbWV0cnkiOiBudWxsLCAiZHJpZnQiOiBudWxsLCAiY2hlY2twb2ludCI6IG51bGwsICJyZXF1aXJlZF9jaGVja3MiOiBudWxsLCAiYmFzZV9kcmlmdCI6IG51bGwsICJhcmNoaXZlIjogbnVsbCwgInN3ZWVwIjogbnVsbH0K")       # the architect's dry-run fixture
HASHES = {"EMIT": "9632439af6dd669e03e7a49d87a79639409e5d9b586f56586a20bccdf98e7d00",
          "LIGHT": "55c53cfe057b2e5a5cee10b7f6eabbbcb5365e24cc481329b27f19c6f3cebdb8",
          "DRY": "f5bd7e5bbb92363b2993e2aaba5816dc3428dd7acdc0c51e8e194a49c43471ce"}

def sha(b): return hashlib.sha256(b).hexdigest()

TMP = Path(tempfile.mkdtemp(prefix="ck-twine-carry-bale-"))
import atexit
atexit.register(shutil.rmtree, TMP, True)
FAKE = TMP / "fakebale"
(FAKE / "bin").mkdir(parents=True)
(FAKE / "calls").mkdir()
(FAKE / "mode").mkdir()
(FAKE / "bin" / "VERSION").write_text("0.4.45\n")
STUB = FAKE / "bin" / "bale"
STUB.write_text(r'''#!/usr/bin/env bash
d="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
case "${1:-}" in
  relay|apply) ;;
  --version) echo "bale 0.4.45"; exit 0 ;;
  *) cat >/dev/null; exit 0 ;;
esac
n=$(( $(ls "$d/calls" | wc -l) + 1 ))
mkdir "$d/calls/$n"
printf '%s\0' "$@" > "$d/calls/$n/argv"
pwd > "$d/calls/$n/cwd"
cat > "$d/calls/$n/stdin"
cat "$d/mode/stdout"
cat "$d/mode/stderr" >&2
exit "$(cat "$d/mode/exit")"
''')
STUB.chmod(0o755)

ALL_CALLS = []
GEN = 0
SEEN = set()
def calls():
    out = []
    for c in sorted((FAKE / "calls").iterdir(), key=lambda p: int(p.name)):
        argv = (c / "argv").read_bytes().split(b"\0")[:-1]
        out.append({"argv": [a.decode() for a in argv],
                    "stdin": (c / "stdin").read_bytes(),
                    "cwd": (c / "cwd").read_text().strip()})
        if (GEN, c.name) not in SEEN:
            SEEN.add((GEN, c.name))
            ALL_CALLS.append(out[-1])
    return out

def set_mode(stdout: bytes, exit_code: int = 0, stderr: bytes = b""):
    global GEN
    calls()  # harvest the previous scenario's calls into ALL_CALLS first
    GEN += 1
    (FAKE / "mode" / "stdout").write_bytes(stdout)
    (FAKE / "mode" / "stderr").write_bytes(stderr)
    (FAKE / "mode" / "exit").write_text(str(exit_code))
    for c in (FAKE / "calls").iterdir():
        shutil.rmtree(c)


ENV = dict(os.environ)
ENV["PATH"] = f"{FAKE / 'bin'}{os.pathsep}{ENV.get('PATH', '')}"
ENV["TWINE_BALE_ROOT"] = str(FAKE)
WORK = TMP / "work"
WORK.mkdir()

def twine(*args, stdin=None):
    r = subprocess.run([sys.executable, "-I", "-S", str(TWINE), *args], cwd=WORK,
                       env=ENV, input=stdin, capture_output=True, timeout=120)
    return r

# --- control: the embedded inputs and the stand-in work ----------------------
bad = [k for k, b in (("EMIT", EMIT), ("LIGHT", LIGHT), ("DRY", DRY)) if sha(b) != HASHES[k]]
set_mode(b"stand-in\n", 3, b"")
r = subprocess.run([str(STUB), "relay", "x", "-"], input=b"in", capture_output=True, env=ENV)
selfcheck = calls()
ALL_CALLS.clear()
if bad or r.returncode != 3 or r.stdout != b"stand-in\n" or len(selfcheck) != 1 \
        or selfcheck[0]["argv"] != ["relay", "x", "-"] or selfcheck[0]["stdin"] != b"in":
    print("[FAIL] control: the checkpoint's embedded inputs or its stand-in bale are broken")
    print(f"  bad hashes: {bad}; stand-in rc={r.returncode} calls={selfcheck}")
    sys.exit(2)
print("[PASS] control: embedded inputs intact, stand-in bale records its calls")

failed = []
def verdict(ok, label, detail=""):
    print(("[PASS] " if ok else "[FAIL] ") + label)
    if not ok:
        failed.append(label)
        if detail:
            for line in str(detail).splitlines()[:12]:
                print("  " + line)

json_runs = []   # (label, CompletedProcess, verb) for the JSON-discipline probe
def jrun(verb, *args, stdin=None):
    r = twine(*verb.split(), *args, "--json", stdin=stdin)
    json_runs.append((verb, r))
    try:
        lines = r.stdout.decode().splitlines()
        obj = json.loads(lines[0]) if len(lines) == 1 else None
    except (ValueError, UnicodeDecodeError, IndexError):
        obj = None
    return r, (obj if isinstance(obj, dict) else None)

def relevant(cs):
    return [c for c in cs if c["argv"] and c["argv"][0] in ("relay", "apply")]

def why(r, obj, cs=None):
    return (f"exit {r.returncode}; json {json.dumps(obj)[:600] if obj else None}; "
            f"stderr tail {r.stderr.decode(errors='replace')[-400:]!r}"
            + (f"; bale calls {[c['argv'] for c in cs]}" if cs is not None else ""))

def no_trace(r): return b"Traceback" not in r.stderr

# --- commands ------------------------------------------------------------------
r, obj = jrun("commands")
names = [c.get("name") for c in (obj or {}).get("commands", [])]
verdict(r.returncode == 0 and "carry exchange" in names and "carry response" in names,
        "commands lists carry exchange and carry response", why(r, obj))

# --- carry exchange --------------------------------------------------------------
turn = b"Here is my turn.\n\n" + EMIT + b"\nThat is all.\n"
(WORK / "turn.txt").write_bytes(turn)
set_mode(EMIT, 0)
r, obj = jrun("carry exchange", "turn.txt")
cs = relevant(calls())
ok = (r.returncode == 0 and obj is not None and obj.get("ok") is True
      and obj.get("command") == "carry exchange" and obj.get("sid") == SID
      and obj.get("ran") is True and len(cs) == 1
      and cs[0]["argv"] == ["relay", SID, "-"] and cs[0]["stdin"] == EMIT
      and Path(cs[0]["cwd"]).resolve() == WORK.resolve())
verdict(ok, "carry exchange relays an intact block: one bale relay <sid> - call in the "
            "current directory, stdin exactly the block's own lines", why(r, obj, cs))

set_mode(EMIT, 0)
r = twine("carry", "exchange", "-", stdin=turn)
cs = relevant(calls())
verdict(r.returncode == 0 and r.stdout == EMIT and len(cs) == 1 and cs[0]["stdin"] == EMIT,
        "carry exchange human mode, input on stdin: stdout is exactly bale relay's stdout",
        f"exit {r.returncode}; stdout {r.stdout[:200]!r}; calls {len(cs)}")

damaged = turn.replace(b"Specimen row 1", b"Specimen row 9", 1)
(WORK / "damaged.txt").write_bytes(damaged)
cut = turn.replace(b"BALE EXCHANGE END\n", b"", 1)
(WORK / "cut.txt").write_bytes(cut)
set_mode(EMIT, 0)
r1, o1 = jrun("carry exchange", "damaged.txt")
r2, o2 = jrun("carry exchange", "cut.txt")
cs = relevant(calls())
verdict(all(r.returncode == 1 and o and o.get("ok") is False and o.get("ran") is False
            for r, o in ((r1, o1), (r2, o2))) and not cs,
        "carry exchange refuses a damaged or cut-off block without calling bale",
        why(r1, o1) + "\n" + why(r2, o2, cs))

(WORK / "light.txt").write_bytes(LIGHT)
set_mode(EMIT, 0)
r, obj = jrun("carry exchange", "light.txt")
cs = relevant(calls())
verdict(r.returncode == 1 and obj and obj.get("ok") is False and not cs,
        "carry exchange refuses an input with no exchange block without calling bale",
        why(r, obj, cs))

three = EMIT + b"\n" + LIGHT + b"\n" + EMIT
(WORK / "three.txt").write_bytes(three)
set_mode(EMIT, 0)
ra, oa = jrun("carry exchange", "three.txt")
rb, ob = jrun("carry exchange", "three.txt", "--block", "2")
cs_refused = relevant(calls())
set_mode(EMIT, 0)
rc, oc = jrun("carry exchange", "three.txt", "--block", "3")
cs = relevant(calls())
verdict(ra.returncode == 1 and rb.returncode == 1 and not cs_refused
        and rc.returncode == 0 and oc and oc.get("ok") is True and oc.get("block") == 3
        and len(cs) == 1 and cs[0]["stdin"] == EMIT,
        "carry exchange refuses two exchange blocks without --block, refuses --block "
        "naming a light block, and relays the one --block names",
        why(ra, oa) + "\n" + why(rb, ob, cs_refused) + "\n" + why(rc, oc, cs))

set_mode(b"", 1, b"bale: relay refused (stand-in)\n")
r, obj = jrun("carry exchange", "turn.txt")
cs = relevant(calls())
verdict(r.returncode == 1 and obj and obj.get("ok") is False and obj.get("ran") is True
        and obj.get("exit_code") == 1 and len(cs) == 1 and no_trace(r),
        "carry exchange reports bale relay's non-zero exit as not ok, without a traceback",
        why(r, obj, cs))

# --- carry response --------------------------------------------------------------
tar = WORK / "response-x.tar.gz"
tar.write_bytes(b"\x1f\x8b stand-in tarball bytes")
real = str(tar.resolve())

def apply_ok(c, path):
    a = c["argv"]
    if not a or a[0] != "apply" or "--dry-run" not in a or "--json" not in a:
        return False
    rest = [t for t in a[1:] if not t.startswith("-")]
    return len(rest) == 1 and str((Path(c["cwd"]) / rest[0]).resolve()) == path

set_mode(DRY, 0)
r, obj = jrun("carry response", "response-x.tar.gz")
cs = relevant(calls())
expected_line = "bale apply " + shlex.quote(real)
verdict(r.returncode == 0 and obj and obj.get("ok") is True
        and obj.get("command") == "carry response" and obj.get("outcome") == "dry-run"
        and obj.get("apply_line") == expected_line and obj.get("ran") is True
        and len(cs) == 1 and apply_ok(cs[0], real),
        "carry response dry-runs the tarball and hands back the exact apply line",
        why(r, obj, cs) + f"\nexpected apply_line {expected_line!r}")

set_mode(DRY, 0)
r = twine("carry", "response", "response-x.tar.gz")
verdict(r.returncode == 0 and r.stdout == (expected_line + "\n").encode(),
        "carry response human mode prints exactly the apply line",
        f"exit {r.returncode}; stdout {r.stdout[:300]!r}")

spaced = WORK / "my response.tar.gz"
spaced.write_bytes(b"stand-in")
set_mode(DRY, 0)
r, obj = jrun("carry response", "my response.tar.gz")
cs = relevant(calls())
sline = "bale apply " + shlex.quote(str(spaced.resolve()))
verdict(r.returncode == 0 and obj and obj.get("apply_line") == sline
        and shlex.split(obj["apply_line"]) == ["bale", "apply", str(spaced.resolve())]
        and len(cs) == 1 and apply_ok(cs[0], str(spaced.resolve())),
        "carry response quotes a tarball path with a space in the apply line",
        why(r, obj, cs) + f"\nexpected {sline!r}")

set_mode(DRY, 0)
r, obj = jrun("carry response", "absent.tar.gz")
cs = relevant(calls())
verdict(r.returncode == 1 and obj and obj.get("ok") is False and obj.get("ran") is False
        and obj.get("apply_line") is None and not cs,
        "carry response refuses a missing tarball without calling bale", why(r, obj, cs))

set_mode(b"", 1, b"bale: apply refused (stand-in)\n")
r, obj = jrun("carry response", "response-x.tar.gz")
cs = relevant(calls())
verdict(r.returncode == 1 and obj and obj.get("ok") is False and obj.get("ran") is True
        and obj.get("exit_code") == 1 and obj.get("apply_line") is None
        and len(cs) == 1 and no_trace(r),
        "carry response is not ok when the dry-run exits non-zero, without a traceback",
        why(r, obj, cs))

set_mode(DRY.replace(b'"dry-run"', b'"applied"', 1), 0)
r1, o1 = jrun("carry response", "response-x.tar.gz")
set_mode(b"this is not json\n", 0)
r2, o2 = jrun("carry response", "response-x.tar.gz")
verdict(all(r.returncode == 1 and o and o.get("ok") is False and o.get("apply_line") is None
            and no_trace(r) for r, o in ((r1, o1), (r2, o2))),
        "carry response is not ok when the outcome is not dry-run or stdout is not one JSON object",
        why(r1, o1) + "\n" + why(r2, o2))

# --- across every run above --------------------------------------------------------
calls()  # collect any calls the last scenario left
bare = [c["argv"] for c in ALL_CALLS if c["argv"][0] == "apply" and "--dry-run" not in c["argv"]]
applies = [c for c in ALL_CALLS if c["argv"][0] == "apply"]
verdict(applies and not bare, "twine never calls bale apply without --dry-run",
        f"{len(applies)} apply call(s); without --dry-run: {bare}")
bad_json = []
for verb, r in json_runs:
    lines = r.stdout.decode(errors="replace").splitlines()
    try:
        o = json.loads(lines[0]) if len(lines) == 1 else None
    except ValueError:
        o = None
    if not isinstance(o, dict) or o.get("command") != verb or not isinstance(o.get("ok"), bool) \
            or (r.returncode == 0) != o.get("ok") or r.returncode not in (0, 1):
        bad_json.append(f"{verb}: exit {r.returncode}, stdout {r.stdout[:160]!r}")
verdict(not bad_json, "every --json run prints one JSON line whose ok matches its exit code",
        "\n".join(bad_json))

# --- the fixture and the suite -------------------------------------------------------
hits = [p.relative_to(ROOT).as_posix() for p in (ROOT / "fixtures").rglob("*")
        if p.is_file() and sha(p.read_bytes()) == HASHES["DRY"]] if (ROOT / "fixtures").is_dir() else []
verdict(len(hits) == 1, "the dry-run fixture is landed byte-exact under fixtures/ (sha256 f5bd7e5b)",
        f"files with that hash: {hits}")

suite_env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
try:
    s = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                       cwd=ROOT, env=suite_env, capture_output=True, timeout=600)
    verdict(s.returncode == 0, "the unittest suite passes",
            s.stderr.decode(errors="replace")[-1200:])
except subprocess.TimeoutExpired:
    verdict(False, "the unittest suite passes", "timed out after 600s")

print(f"checkpoint twine-carry-bale v1: {len(failed)} probe(s) failed")
sys.exit(1 if failed else 0)
PY
rc=$?
case "$rc" in
  0|1|2) exit "$rc" ;;
  *) echo "[FAIL] control: python exited $rc"; exit 2 ;;
esac

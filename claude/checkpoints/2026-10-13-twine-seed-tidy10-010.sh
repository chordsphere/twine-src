#!/usr/bin/env bash
# Blind checkpoint — twine-src session `twine-seed-tidy10` (authored at
# sitting 2026-10-13-open-milestone-2-006, v1). Outcome contracts only:
# the seed carries R5's five annotations and the §4.4 line, byte-exact
# from this oracle's own copy of the blocks (the brief's fences), each
# after its anchor, and nothing else moved — the reversal hashes to the
# base. Exit 0 pass; 1 a probe failed, named; 2 this oracle is broken.
set -u
export PYTHONDONTWRITEBYTECODE=1
python3 -I -B - <<'ORACLE'
import base64, hashlib, json, re, sys
from pathlib import Path


def broken(exc_type, exc, tb):
    sys.stderr.write(f"[checkpoint] BROKEN: {exc_type.__name__}: {exc}\n")
    sys.exit(2)


sys.excepthook = broken
ROOT = Path.cwd()
failures: list[str] = []
BASE_SHA = "337722a561b2776a0a80d48fe8a1ad96a37235b6945a38669eb9af77d1be0f35"
LANDED_SHA = "6e90e506e9aa2e61121dde7907cd3cfa07830d29f1e611e44217e9805e854dfa"
BASE_LINES, LANDED_LINES = 1698, 1751
VERSION = "0.22.0"
PAYLOAD = json.loads(r"""{"A": {"b64": "WzIwMjYtMTAtMTMtdHdpbmUtcnVudGltZS13aW5kb3ctMDA5OiBSNSBsYW5kZWQg4oCUIHdpbmRvdyBhY2NvdW50aW5nIGFuZApjb2xkIHJlc3VtZSAoRDIzKS4gVGhlIHdpbmRvdzogYHR3aW5lIHJ1biAtLXdpbmRvdyBOYCBmaXhlcyBpdHMgc2l6ZSwgb3IKdGhlIGFkYXB0ZXIgc3RhdGVzIGl0IGF0IHNwYXduIChgQWRhcHRlci5jb250ZXh0X3dpbmRvdygpYCwgYQpgV2luZG93U3RhdGVtZW50YDsgdGhlIEFudGhyb3BpYyBhZGFwdGVyJ3Mgb25lIGBHRVQgL3YxL21vZGVsc2AsIGl0cwptb2RlbCdzIGBtYXhfaW5wdXRfdG9rZW5zYDsgdGhlIGZha2UncyB1bmtub3duIOKAlCBjb3VudGVkLCBuZXZlciB3YXJuZWQKb3Igc3RvcHBlZCBvbik7IGFmdGVyIGVhY2ggY2FsbCBgdXNlZGAgPSB0aGUgY2FsbCdzIGBpbnB1dCArIGNhY2hlX3JlYWQKKyBjYWNoZV93cml0ZWAsIG9uZSBgd2luZG93YCB0cmFuc2NyaXB0IGxpbmUgcGVyIGNhbGw7IGF0IDgwJSB0aGUgcnVuIGlzCndhcm5lZCBhbmQgZXZlcnkgdG9vbCByZXN1bHQgdGhlIG1vZGVsIHJlYWRzIGVuZHMgd2l0aCB0aGUgd2FybmluZyBsaW5lLApuZXZlciB0aGUgdHJhbnNjcmlwdCdzIGB0b29sLXJlc3VsdGAgbGluZTsgYXQgMTAwJSB0aGUgbmV4dCBjYWxsIGlzIG5vdAptYWRlIOKAlCBgc3RvcHBlZGAsIGB3aW5kb3ctZXhoYXVzdGVkYCwgYHNwbGl0LWdvYWxgLCBiZWZvcmUgdGhlIGNhcApjaGVjazsgdGhlIGNhcCBjaGVjayBwcmljZXMgdGhlIGNvdW50IHBsdXMgd2hhdCB3YXMgYXBwZW5kZWQgc2luY2UuIENvbGQKcmVzdW1lOiBgdHdpbmUgcmVzdW1lIFNJRCAtLWNhcCBVU0QgLS1hbnN3ZXIgRklMRXwtYCByZWJ1aWxkcyB0aGUKY29udmVyc2F0aW9uIGZyb20gdGhlIHRyYW5zY3JpcHQncyBgcmVxdWVzdGAgbGluZXMsIGFwcGVuZHMgdGhlIGFuc3dlcgphcyBvbmUgdXNlciBtZXNzYWdlIGFuZCBydW5zIHRoZSBsb29wIGFnYWluIHVuZGVyIHRoZSBzYW1lIHNpZCBpbiB0aGUKc2FtZSBzYW5kYm94IGhvbWUgd2l0aCB0aGUgdHJhbnNjcmlwdCdzIHNwYXduLXRpbWUgY29uc3RhbnRzLCBubyBgYmFsZQpvcGVuYDsgdGhlIHR3aW4ncyBgcmV3YXJtYCBpcyB0aGUgZmlyc3QgY2FsbCdzIHVzYWdlLiBgZXNjYWxhdGVgIGdhaW5lZAppdHMgY2xhcmlmaWNhdGlvbiBmb3JtIChgYmxvY2tpbmc6IHRydWVgKTogYmFsZSdzIHJlcXVlc3QtY2FycmllZApjcmFmdGVyIGFuZCBsaW50IGluIHRoZSBjYWdlLCB0aGUgcmVzcG9uc2UgdGFyYmFsbCBpbiB0aGUgaG9tZSwgYGNhcnJ5CnJlc3BvbnNlYCBvbiBpdCwgdGhlIHJ1biBgc3VzcGVuZGVkYCBvbiBpdHMgYXBwbHkgbGluZS4KYHdpbmRvdy1hY2NvdW50aW5nYCBhbmQgYHN1c3BlbmQtcmVzdW1lYCBgaW1wbGVtZW50ZWRgLCBieSB0aGUgcnVudGltZQooYHR3aW5lL3J1bnRpbWUvd2luZG93LnB5YCwgYHR3aW5lL3J1bnRpbWUvcmVzdW1lLnB5YCkuIGBWRVJTSU9OYAowLjIyLjAuXQo=", "sha256": "558e75d5633086fab0017a0e05bfe43413c6b08171e24b8b51a6da41acf2167c", "anchor": "reached: the worker side of the courier is twine's.]"}, "B": {"b64": "WzIwMjYtMTAtMTMtdHdpbmUtcnVudGltZS13aW5kb3ctMDA5OiBsYW5kZWQg4oCUIGEgc3VzcGVuZGVkIHNlc3Npb24gZ29lcwpjb2xkIGFuZCBgdHdpbmUgcmVzdW1lYCByZS13YXJtcyBpdCBmcm9tIGl0cyB0cmFuc2NyaXB0IHdpdGggdGhlCnBsYW5uZXIncyBhbnN3ZXIgYXBwZW5kZWQ7IHRoZSByZS13YXJtIGNvc3QgaXMgdGhlIHR3aW4ncyBgcmV3YXJtYCwgdGhlCnJlc3VtZWQgcnVuJ3MgZmlyc3QgY2FsbCdzIHVzYWdlIGluIHRoZSBmaXZlIGNsYXNzZXM7IGhvbGRpbmcgaG90IHN0YXlzCnRoZSBlZmZvcnQgbWFjaGluZXJ5J3MgbGF0ZXIga25vYi5dCg==", "sha256": "cf217d25ce70078f77e3de562c4f7ecea1b799e890932a3889df3652c8e5d244", "anchor": "has its transcript persisted append-only and re-warms on the answer.]"}, "C": {"b64": "ICBbMjAyNi0xMC0xMy10d2luZS1ydW50aW1lLXdpbmRvdy0wMDk6IHRoZSB0cmFuc2NyaXB0IGdhaW5lZCB0aGUgbGluZQogIGtpbmQgYHdpbmRvd2AgKGVhY2ggY2FsbCdzIGNvdW50ZWQgd2luZG93KSBhbmQgaXMgbm93IHdoYXQgYHR3aW5lCiAgcmVzdW1lYCByZWJ1aWxkcyBhIGNvbnZlcnNhdGlvbiBmcm9tLCBpdHMgbGFzdCBgcmVxdWVzdGAgbGluZSBgc2VudDoKICBmYWxzZWAgd2hlbmV2ZXIgYSBydW4gZW5kcyB3aXRoIG1lc3NhZ2VzIG5ldmVyIHNlbnQuXQo=", "sha256": "55c5332020140590d65aad19a2153a2e4321866680d8d1c48cafc5dee4383564", "anchor": "  (runtime-contract.md \u00a77.6).]"}, "D": {"b64": "ICBbMjAyNi0xMC0xMy10d2luZS1ydW50aW1lLXdpbmRvdy0wMDk6IGxhbmRlZCDigJQgY291bnRlZCBmcm9tIGVhY2gKICBjYWxsJ3MgdXNhZ2UsIHdhcm5lZCBhcyB0aGUgbGFzdCBsaW5lIG9mIGV2ZXJ5IHRvb2wgcmVzdWx0IGF0IDgwJSwgYW5kCiAgZXhoYXVzdGVkIGFzIGB3aW5kb3ctZXhoYXVzdGVkYCDihpIgYHNwbGl0LWdvYWxgIGJlZm9yZSB0aGUgY2FsbCBwYXN0IGl0CiAgKHJ1bnRpbWUtY29udHJhY3QubWQgwqc3LjQpLl0K", "sha256": "80b2cae2fb616dc0397b0a03e0b571f9e2202d7060d46353a25ee415966b29f0", "anchor": "  bale-src an AGENT.md \u00a711.7 surface row (D21's annotation)."}, "E": {"b64": "ICBbMjAyNi0xMC0xMy10d2luZS1ydW50aW1lLXdpbmRvdy0wMDk6IGxhbmRlZCDigJQgYGVzY2FsYXRlYCdzCiAgY2xhcmlmaWNhdGlvbiBmb3JtIHN1c3BlbmRzIGEgcnVuIG9uIGEgcmVzcG9uc2UgdGFyYmFsbCwgYW5kIGB0d2luZQogIHJlc3VtZWAgcmUtd2FybXMgdGhlIHRyYW5zY3JpcHQgb24gdGhlIGFuc3dlciAocnVudGltZS1jb250cmFjdC5tZAogIMKnNi42LCDCpzcuOSkuXQo=", "sha256": "8cd4a0f232d649be88bc641f19bb7fff2b607abcf4ea418678e55902adc1d4e6", "anchor": "  re-warms on the answer."}, "F": {"b64": "WzIwMjYtMTAtMTMtb3Blbi1taWxlc3RvbmUtMi0wMDY6IGJvdGggc2VudCBvbiAyMDI2LTEwLTEzIOKAlCBuaXNhYmEtc3JjJ3MKYW5ub3RhdGlvbiBsYW5kZWQgYXMgc2Vzc2lvbiBgMjAyNi0xMC0xMy1uaXNhYmEtcnVudGltZS1mYWNlLTAwMWAKKGJlbmVhdGggaXRzIMKnMy4zLCByZWNvcmRpbmcgdGhlIHJ1bnRpbWUgZmFjZSBidWlsdCk7IGJhbGUtc3JjJ3MgwqcxMS43CnJvdyBpcyBpdGVtIDEgb2YgdGhlIHNpdHRpbmcgYnVuZGxlIGB0d2luZS1vYmxpZ2F0aW9ucy1kZXNrYCBhdXRob3JlZApmb3IgaXRzIGRlc2ssIHdpdGggUjUncyB3YXJuaW5nIGFuZCBgdHdpbmUgcmVzdW1lYCBpbiBpdHMgbWF0ZXJpYWwg4oCUCnRoYXQgZGVzaydzIHRvIGxhbmQuXQo=", "sha256": "4b2aefe4882ca70ebe1e8561b78ef25067a0f7231b29aa923bf63a53c6b44816", "anchor": "desk's to send.]"}}""")
ARCHIVE = ROOT / "claude" / "responses" / "2026-10-13-twine-runtime-window-009" / "notes.md"

BLOCKS = {}
for name, spec in PAYLOAD.items():
    data = base64.b64decode(spec["b64"])
    if hashlib.sha256(data).hexdigest() != spec["sha256"]:
        raise AssertionError(f"the oracle's carried block {name} drifted")   # exit 2
    BLOCKS[name] = data


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# --- detectors -----------------------------------------------------------------

def presence_problems(seed: bytes) -> list[str]:
    out = []
    for name, data in BLOCKS.items():
        n = seed.count(data)
        if n != 1:
            out.append(f"block {name} found {n} time(s) byte-exact; want 1")
    return out


def placement_problems(seed: bytes) -> list[str]:
    """Each block sits after its anchor line: anchor, one blank, the block,
    one blank, then whatever followed the anchor's paragraph in the base."""
    out = []
    text = seed.decode("utf-8")
    for name, spec in PAYLOAD.items():
        anchor = spec["anchor"]
        want = anchor + "\n\n" + BLOCKS[name].decode("utf-8") + "\n"
        if text.count(anchor + "\n") != 1:
            out.append(f"block {name}: anchor line found {text.count(anchor + chr(10))} time(s); want 1")
        elif want not in text:
            out.append(f"block {name} is not placed as anchor, blank, block, blank")
    return out


def whole_problems(seed: bytes) -> list[str]:
    out = []
    lines = seed.count(b"\n")
    if lines != LANDED_LINES:
        out.append(f"seed has {lines} lines; want {LANDED_LINES}")
    if hashlib.sha256(seed).hexdigest() != LANDED_SHA:
        out.append("seed does not hash to the landed pin")
    return out


def reversal_problems(seed: bytes) -> list[str]:
    text = seed
    for name, spec in PAYLOAD.items():
        # D and E were inserted with a blank before and after inside a
        # bullet; the others after an existing blank, with one blank after.
        if name in ("D", "E"):
            piece = b"\n" + BLOCKS[name] + b"\n"
        else:
            piece = BLOCKS[name] + b"\n"
        if text.count(piece) != 1:
            return [f"block {name}'s insertion is not found exactly once"]
        text = text.replace(piece, b"", 1)
    out = []
    lines = text.count(b"\n")
    if lines != BASE_LINES:
        out.append(f"reversal leaves {lines} lines; want {BASE_LINES}")
    if hashlib.sha256(text).hexdigest() != BASE_SHA:
        out.append("reversal does not reproduce the base's bytes")
    return out


def archive_problems(notes: str | None) -> list[str]:
    """The five R5 annotations, word for word, against the archived
    notes.md's blockquotes when the archive is in the tree (never against
    the brief's copy); skipped with a note when it is not."""
    if notes is None:
        return []
    quotes = [" ".join(l[2:].strip() for l in q.strip("\n").split("\n"))
              for q in re.findall(r"((?:^> .*\n)+)", notes, re.M)]
    out = []
    for name in "ABCDE":
        words = fold(BLOCKS[name].decode("utf-8"))
        if not any(fold(q) == words for q in quotes):
            out.append(f"block {name}'s words differ from every blockquote in the archived notes.md")
    return out


def version_problems(text: str) -> list[str]:
    return [] if text.strip() == VERSION else [f"VERSION is {text.strip()!r}, want {VERSION!r}"]


# --- controls (exit 2 when a detector does not fire) ------------------------------

def control(name: str, ok: bool) -> None:
    if not ok:
        sys.stderr.write(f"[checkpoint] BROKEN: control {name} did not fire\n")
        sys.exit(2)


good = b"x\n" + b"".join(PAYLOAD[n]["anchor"].encode() + b"\n\n" + BLOCKS[n] + b"\n" for n in "ABCDEF") + b"y\n"
control("presence ok", presence_problems(good) == [])
control("presence missing", bool(presence_problems(good.replace(BLOCKS["B"], b"gone\n"))))
control("placement ok", placement_problems(good) == [])
control("placement moved", bool(placement_problems(good.replace(PAYLOAD["A"]["anchor"].encode() + b"\n\n" + BLOCKS["A"], BLOCKS["A"] + PAYLOAD["A"]["anchor"].encode() + b"\n\n"))))
control("whole", bool(whole_problems(b"short\n")))
control("reversal", bool(reversal_problems(good)))
control("archive ok", archive_problems("> " + BLOCKS["A"].decode().replace("\n", "\n> ").rstrip("> ") + "\n\n" + "".join("> " + BLOCKS[n].decode().replace("\n", "\n> ").rstrip("> ") + "\n\n" for n in "BCDE")) == [])
control("archive differs", bool(archive_problems("> something else\n")))
control("version", bool(version_problems("0.21.0\n")) and version_problems(VERSION + "\n") == [])

# --- probes ---------------------------------------------------------------------
seed = (ROOT / "twine-seed.md").read_bytes()
for p in presence_problems(seed): failures.append(f"presence: {p}")
for p in placement_problems(seed): failures.append(f"placement: {p}")
for p in whole_problems(seed): failures.append(f"whole: {p}")
for p in reversal_problems(seed): failures.append(f"reversal: {p}")
notes = ARCHIVE.read_text(encoding="utf-8") if ARCHIVE.is_file() else None
if notes is None:
    print("[checkpoint] note: no archived notes.md for R5 in the tree; the words are held by the oracle's own copy")
for p in archive_problems(notes): failures.append(f"archive: {p}")
for p in version_problems((ROOT / "VERSION").read_text(encoding="utf-8")): failures.append(f"version: {p}")

if failures:
    for f in failures:
        print(f"[checkpoint] FAIL {f}")
    sys.exit(1)
print(f"[checkpoint] PASS: six blocks placed, {LANDED_LINES} lines, the reversal is the base; VERSION {VERSION}")
sys.exit(0)
ORACLE
exit $?

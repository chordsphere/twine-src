#!/usr/bin/env bash
# Blind checkpoint — session twine-pin-051 (v2: the assumption probe amended
# to the assumption's own sentence; every other probe byte-identical to v1), authored at the desk of
# sitting 2026-10-08-open-arc2-003 from the request and the paste-back of
# probe twine-051-record (2026-10-08T13:35Z, bale 0.4.51) alone.
#
# What it grades (outcomes only): the 24 recordings of bale 0.4.51 landed
# byte-exact at their rule-named paths under fixtures/bale-0.4.51/, each
# with its stderr beside it as a .stderr sibling and a README row carrying
# exit, bytes and both sha256s; the paste-back itself landed under
# carried/; the 0.4.49 recordings untouched; the consumption manifest at
# pin 0.4.51 pointing at the new files (relay's own stdin argv, its reason
# codes, open's refusal), the schema hashes and the apply vocabulary's home
# re-read; the _read_relay_input assumption gone from its four places;
# `bale check` admits 0.4.51 and refuses 0.4.49; the transition table still
# total; the recorder and the lander present, the lander's --check passing.
#
# Writes only under ./.checkpoint-pin-051.<pid>/ in the tree it grades
# (removed at exit); reads nothing of its own. Exit 0 all probes passed;
# 1 a probe failed (named); 2 the oracle is broken.
set -u
WORK="$(pwd)/.checkpoint-pin-051.$$"
mkdir -p "$WORK" || exit 2
trap 'rm -rf "$WORK"' EXIT
echo "[checkpoint] writes only under $WORK (removed at exit)"
export TMPDIR="$WORK"
PYTHONDONTWRITEBYTECODE=1 python3 -I -B - "$WORK" <<'PY'
import hashlib, json, os, re, subprocess, sys, tomllib
from pathlib import Path

def broken(msg):
    print(f"[checkpoint] ORACLE BROKEN: {msg}")
    sys.exit(2)
sys.excepthook = lambda t, v, tb: broken(f"unplanned {t.__name__}: {v}")

WORK = Path(sys.argv[1]); TREE = Path.cwd()
TWINE = TREE / "bin" / "twine"
VERSION = "0.4.51"
# path, exit, stdout bytes, stdout sha256, stderr bytes, stderr sha256 — from the paste-back
ROWS = [
    [
    "fixtures/bale-0.4.51/anywhere/--version.txt",
    0,
    12,
    "de4bfb2eea95dc5102c052339fba0c576c839a7bb8de083373994b04c109bcb4",
    0,
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ],
    [
    "fixtures/bale-0.4.51/twine-src/status_--json.json",
    0,
    2830,
    "688c2a65b1d33342d3ef789c3cf3314001c747fd49c5802896a7c04dd709b572",
    0,
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ],
    [
    "fixtures/bale-0.4.51/twine-src/stats_--json.json",
    0,
    19063,
    "22fd5448775a980c8db490079a51ab4d8ce63f5ba3a9312f52208585b35bd05b",
    0,
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ],
    [
    "fixtures/bale-0.4.51/twine-src/stats_--sid-2026-10-01-twine-seed-001_--json.json",
    0,
    4026,
    "c50f1c6661f291e1378c42e6599ed60f3127452e39c5ae2f5b12f8b20df73455",
    0,
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ],
    [
    "fixtures/bale-0.4.51/twine-src/unlock_sid_--json+unlock-refused+not-open.json",
    1,
    391,
    "a6da42625c53f2f18442bf0297400918e033f9091d16bbd3dadb324a1e54029a",
    119,
    "2e8ec66238b6879a63d7667cad8a197d8853d75d7aacab55b5cab26066cc475e"
    ],
    [
    "fixtures/bale-0.4.51/twine-src/unlock_--integration_--json.json",
    1,
    514,
    "f64fec6c21aa9f97c1ac5528a4fafea15a9538c1b02310858d0f0bc8f4254049",
    253,
    "23b022935757f1b3999ef3354c3efc723f777c6652c280093ad4bad6f79439fc"
    ],
    [
    "fixtures/bale-0.4.51/twine-src/open_--check_bundle_--json.json",
    0,
    723,
    "b8cf0ef8e85cb6779c9e56d50b31baf876c5a27bb33300bf3ea9121e27371bf0",
    1802,
    "95788022dd14dbb6302b3538fbf413fcec7911eb3d404048e59371eec1c8753d"
    ],
    [
    "fixtures/bale-0.4.51/crafter/--probe-twine-take-fixture.txt",
    0,
    2626,
    "1f5e235fd0958b4e984b2b5fe7c1745466171c02eff9603b1eb09330ccdca00e",
    594,
    "9411fa4d519f03fef3f20e48e095b72e18f264adc18fe4b1d1fd3b989dd8c6cc"
    ],
    [
    "fixtures/bale-0.4.51/crafter/--light-block-stdin.txt",
    0,
    722,
    "55c53cfe057b2e5a5cee10b7f6eabbbcb5365e24cc481329b27f19c6f3cebdb8",
    632,
    "643da8527bb2b45bb3db80aa07bbec63e0552d0786cdec1e63a549f261a45d17"
    ],
    [
    "fixtures/bale-0.4.51/crafter/--emit-block-stdin.txt",
    0,
    1618,
    "b1730d1a40eb48bf3b60be5fb389c110ee4f0b843fe87e87fa192c6720e2a2d9",
    317,
    "87c88a3de079ecc5c7fee937d2628a49ade99251fb1662b51afda70ebd63691a"
    ],
    [
    "fixtures/bale-0.4.51/scratch/pack_goal_--slug-ro_--read-only_--no-readme_--json.json",
    0,
    2030,
    "0320baecb3f0e70913d3de98ecdfef6cc50e88133e0f55945add6152da9949ed",
    4287,
    "b1c36a6b10417025f48c68c06c559f80a9d0ffc9bdd052d75f3c26151e7d07ef"
    ],
    [
    "fixtures/bale-0.4.51/scratch/open_bundle_--json+opened.json",
    0,
    2337,
    "838012cf6c7c760f5ff5786c6c9fc0f4cfec4a7f4bf2217a35384464cca930c9",
    4562,
    "e4b2a2b64409eca88d509ef1d7cce854bd0db91f961410bc766f54e17f643f2b"
    ],
    [
    "fixtures/bale-0.4.51/scratch/open_bundle_--json+second-desk.json",
    0,
    2316,
    "7629b63b930a99f2e2888e3df7be93810d886d4bd65688578d03cd48f1b66bba",
    2730,
    "93684b7d2d0463be5cd50f4a08452d7cdd315b0bd1de6d9f3bcce63888e64c20"
    ],
    [
    "fixtures/bale-0.4.51/scratch/open_bundle_--json+open-refused.json",
    1,
    536,
    "31908963df7fa7919ffd37f634a9bbe8866e0346a845894f5845fa7646a30fcf",
    82,
    "8b84698f329ec410e64a5612c8494524c01f15e955a4d31dce5cf04cd331670c"
    ],
    [
    "fixtures/bale-0.4.51/scratch/relay_sid_stdin_--json+relayed.json",
    0,
    1384,
    "b98fc9c13e4851701c2b1ee55f558c45319c8ed237a3a50ea8885c5329c9d5d0",
    872,
    "c9219a9b0b296867ee1e986f1f9413d19e4931459cc8509d5caec64def80c27c"
    ],
    [
    "fixtures/bale-0.4.51/scratch/relay_sid_--json.json",
    0,
    1329,
    "600559d6927583dde5c8bcc7111d1707d13f8567d3197e15c489f3ef886d5f1c",
    857,
    "30d6b99c5db67b52b98014b16439e8ebc51ab9360de689c389622ab7b4a0d6c6"
    ],
    [
    "fixtures/bale-0.4.51/scratch/relay_sid_stdin_--json+relay-refused+not-an-object.json",
    1,
    544,
    "2151ca6880480456eb8bae15ec9dcba57fef01e23192714811185f34d45671da",
    356,
    "07dbaa4a3f2e04929a705c3c2dd4275bd9430c3915c313543c7369fcdfb9836f"
    ],
    [
    "fixtures/bale-0.4.51/scratch/relay_sid_stdin_--json+relay-refused+not-open.json",
    1,
    495,
    "7af4cac97afab2acea2020c989b197324a9b497a8e699409f0f40661a8a7c764",
    264,
    "4dd50c0efb1d5dde0c26bbbdf9803b456fa45144d02dec8c9e953ea46d700993"
    ],
    [
    "fixtures/bale-0.4.51/scratch/apply_--dry-run_--json_tarball+dry-run.json",
    0,
    290,
    "7e7fd743b142148a90b145032709297c8ade1493595a5ba5a2ad8e5933d3cea8",
    747,
    "24da1657bfc9cf300c8d1109aae85052916932dbddbf47072210a74da777fd82"
    ],
    [
    "fixtures/bale-0.4.51/scratch/apply_--dry-run_--json_tarball+scope-drift-refused.json",
    1,
    521,
    "226625c1bfd08134df342813795fdd9dc03664787723525867674a787c068ca0",
    1363,
    "deb16ba9bd89454784f85cc3011ac3f27365f58f45888f84b06d3bf4615eea7c"
    ],
    [
    "fixtures/bale-0.4.51/scratch/unlock_sid_--json+unlock-refused+hold-branch.json",
    1,
    569,
    "b6bd5de4407d3f378daea09b3a9883c4394da7bdd24f805846d0ba1337934cda",
    314,
    "98198a9917db84acc4d8b901bc57fcaf99a819b58cfd27ea41050a9d41f47e8a"
    ],
    [
    "fixtures/bale-0.4.51/scratch/unlock_sid_--reason-aborted_--json.json",
    0,
    489,
    "319fb276ca1f3b5ab1801a680210ea5d2a7bc31ab60ed7251bb15e9b60501b6e",
    499,
    "c20c85866f6403dbd89c209f52431866198036589654012eb630744ee154855f"
    ],
    [
    "fixtures/bale-0.4.51/scratch/unlock_sid_--json+unlocked.json",
    0,
    498,
    "be6651120e7e7c06f4b00feb722adb9f5a110adc846a0481cd4af1e53ae6a4ec",
    413,
    "3a67defb0070a978697aed381171ab07764d44bdaf025987cd1920ad6d398ecb"
    ],
    [
    "fixtures/bale-0.4.51/scratch/unlock_--json.json",
    0,
    231,
    "e7a675b90e559559496927b2de7baad3f31f7d62268991615c3beded8bbe501e",
    39,
    "73e52366af85bc078cf566c3a5551e2f920c17a41bec616e956e290ad8cfe0fc"
    ]
    ]
OLD = [
    [
    "bale-0.4.49/anywhere/--version.txt",
    "49f3d68760069239c4246ca6ab02a58d21ba64469a0fd4714ac3572f22b4791e"
    ],
    [
    "bale-0.4.49/twine-src/status_--json.json",
    "bf35950de9441ff620ce0e2b620a7809def46f01f33cce2c6d852a289516d26c"
    ],
    [
    "bale-0.4.49/twine-src/unlock_sid_--json+unlock-refused+not-open.json",
    "a374a63ffd5027180c1b0833be6b590d778402b428b6f8be66590c96b6050c82"
    ],
    [
    "bale-0.4.49/twine-src/unlock_--integration_--json.json",
    "d6e6668700da2266cc8386494ea65b0a0bc6eb22406c750a541c97e0b828376e"
    ],
    [
    "bale-0.4.49/twine-src/open_--check_bundle_--json.json",
    "2a87907131523e40d59a77175c8e20127dcf200196fcf692dda6a2d28cccc80e"
    ],
    [
    "bale-0.4.49/twine-src/stats_--json.json",
    "cc2936b8a5f58fa4dbcd2dd3bc6455a286d4f27aa9178bc814b2ad62ac6df085"
    ],
    [
    "bale-0.4.49/twine-src/stats_--sid-2026-10-01-twine-seed-001_--json.json",
    "c50f1c6661f291e1378c42e6599ed60f3127452e39c5ae2f5b12f8b20df73455"
    ],
    [
    "bale-0.4.49/scratch/pack_goal_--slug-ro_--read-only_--no-readme_--json.json",
    "a45c382fc4800ccdda614fb0778d7f36f7981c2383e99b610a99bed1e56ea5c9"
    ],
    [
    "bale-0.4.49/scratch/open_bundle_--json+opened.json",
    "75872c420f92ca9696de2944ce19c4f8c7fd4a3f246064223e1c697142244616"
    ],
    [
    "bale-0.4.49/scratch/open_bundle_--json+second-desk.json",
    "9bc523becf733ef3cfa00db3f973bb141685882df640e08dcbaaedda34976020"
    ],
    [
    "bale-0.4.49/scratch/relay_sid_file_--json+relayed.json",
    "40bd534932ddbe3098fc54af8560371b698d9eed8f719b63e708ab2ac7333b71"
    ],
    [
    "bale-0.4.49/scratch/relay_sid_--json.json",
    "47849102980eaff464160a04a4b3f06ac4a58ebf05a559dc89518a3f03bed400"
    ],
    [
    "bale-0.4.49/scratch/relay_sid_file_--json+relay-refused+ingest.json",
    "84f6bced9a6ef57d692ef2050b8cd5de6738f9c43e155090f93bf923adede61d"
    ],
    [
    "bale-0.4.49/scratch/relay_sid_file_--json+relay-refused+session-gate.json",
    "e0cb6d390ae7edd333aa1ae9145be59cff556f02b674dfc61c820b83f856bbcf"
    ],
    [
    "bale-0.4.49/scratch/apply_--dry-run_--json_tarball+dry-run.json",
    "266fc2539c08511d1ee29cb29442eacad6d6ebdab738723c3c0bf440fac8b955"
    ],
    [
    "bale-0.4.49/scratch/apply_--dry-run_--json_tarball+scope-drift-refused.json",
    "9f17bd60b2820b9b442a80b1c30a556c22fcace67fb5803843e3181b4cf1fcd7"
    ],
    [
    "bale-0.4.49/scratch/unlock_sid_--json+unlock-refused+hold-branch.json",
    "14669f1831af42e2c39c7f7e9ab1995ff21ab8c2307675ed5d9df56db88f90ce"
    ],
    [
    "bale-0.4.49/scratch/unlock_sid_--reason-aborted_--json.json",
    "1f91385974a148652c5b95434061772e83e397f535b272fc0dcfd28018efe921"
    ],
    [
    "bale-0.4.49/scratch/unlock_sid_--json+unlocked.json",
    "8af871da9c5d437a055a01154f0d34591821b9fc313324eeb1e5301aa0f5a397"
    ],
    [
    "bale-0.4.49/scratch/unlock_--json.json",
    "e7a675b90e559559496927b2de7baad3f31f7d62268991615c3beded8bbe501e"
    ],
    [
    "bale-0.4.49/crafter/--probe-twine-take-fixture.txt",
    "1f5e235fd0958b4e984b2b5fe7c1745466171c02eff9603b1eb09330ccdca00e"
    ],
    [
    "bale-0.4.49/crafter/--light-block-stdin.txt",
    "55c53cfe057b2e5a5cee10b7f6eabbbcb5365e24cc481329b27f19c6f3cebdb8"
    ],
    [
    "bale-0.4.49/crafter/--emit-block-stdin.txt",
    "fda8a4d0d12f930f9077068163098aec626583d59e73c9a8d916b6da21b410f8"
    ]
    ]   # the 0.4.49 rows: path, sha256 (history; untouched)
SCHEMAS = {
    "bundle-manifest.schema.json": "3384ebcd52a08044356f30f1031f4389e9b4427d81602173b0c59f4f9f9cea23",
    "changelog-record.schema.json": "7b6d351c052dad8588b05e7592da78f9e9052a671ad6dae9395bfd6d531c5b5c",
    "diagnostics.schema.json": "bfeef3cc0a6b91b47b1c1c9084ca47349b23a6661b10c848da3b4ef28b413521",
    "escalation-record.schema.json": "16729aae82e20425f91b9fb343de6a74d00fa417ce3cd718767413deee550c41",
    "exchange-record.schema.json": "c9c291899103c4a73768ef930697722b89c5c3ef8f5b388c78c36741316cddc8",
    "request-manifest.schema.json": "70a0c2bd3b6b0d4cf17bc97010c2b7d58931527b7b3100aa984ca3576c075e3d",
    "response-manifest.schema.json": "02d2b6413d078e031641c99e09a9fea909555bdfcb9b2a8a110dbdce63f5817e",
    "telemetry-record.schema.json": "b79d7bf75c10f5799484f906954461e7379ef6d4a870bb7df8c08ce050b38825"
    }
RELAY_REASONS = ["not-open", "held-branch", "not-found", "not-an-object", "trailer-mismatch", "malformed-block", "wrong-session", "schema", "stale-round", "skipped-round", "planner-round-one", "unresolved-answer", "thread-changed", "no-rounds", "unreadable-record", "unreadable-input", "no-sid", "not-a-repo", "system-dir", "config-invalid", "no-git", "unclassified"]
CARRIED = f"fixtures/bale-{VERSION}/carried/probe-output_twine-051-record.txt"
CARRIED_SHA, CARRIED_BYTES = "dec7a229a8e108c2e2dd43a499e80ce473603201882f7422c1ef98dc7908a238", 133981
FOUR_PLACES = ["claude/context/cli-contract.md", "fixtures/README.md",
               "share/bale-consumption.toml", "tests/helpers.py"]

def sha(p): return hashlib.sha256((TREE / p).read_bytes()).hexdigest()
def size(p): return (TREE / p).stat().st_size
def stderr_path(p): return p.rsplit(".", 1)[0] + ".stderr"

failures = []
def probe(label, ok):
    print(f"{'[PASS]' if ok else '[FAIL]'} {label}")
    if not ok: failures.append(label)

# --- detectors ---
def file_is(p, n, h):
    return (TREE / p).is_file() and size(p) == n and sha(p) == h
ROW_RE = re.compile(r"^\| `(?P<file>bale-[^`]+)` \| `[^`]+` \| `[^`]+` \| (?P<exit>\d+|unrecorded) \| (?P<bytes>\d+) \| `(?P<sha>[0-9a-f]{64})` \| (?P<ebytes>\d+) \| `(?P<esha>[0-9a-f]{64})` \|$", re.M)
def readme_rows(text):
    return {f"fixtures/{m['file']}": (m['exit'], int(m['bytes']), m['sha'], int(m['ebytes']), m['esha']) for m in ROW_RE.finditer(text)}
def row_matches(rows, p, exit_, n, h, en, eh):
    r = rows.get(p)
    return r is not None and r == (str(exit_), n, h, en, eh)
def exact_file_set(found, expected):
    return set(found) == set(expected)
def manifest_facts(m):
    surf = {s.get("verb"): s for s in m["surface"] if s.get("kind") == "verb"}
    relay, opn, unlock, apply_, status = surf["relay"], surf["open"], surf["unlock"], surf["apply"], surf["status"]
    also = lambda s: [(tuple(r["argv"]), r.get("outcome"), r.get("reason"), r["fixture"]) for r in s.get("also_recorded", [])]
    checks = {
      "pin": m["bale"]["pin"] == VERSION,
      "schemas": m["bale"]["schemas"] == SCHEMAS,
      "relay argv": relay["argv"] == ["relay", "<sid>", "-", "--json"],
      "relay fixture": relay["fixture"] == f"fixtures/bale-{VERSION}/scratch/relay_sid_stdin_--json+relayed.json",
      "relay keys": relay["keys"] == ["outcome", "sid", "block", "cause"],
      "relay reasons": list(relay.get("reasons", [])) == RELAY_REASONS and isinstance(relay.get("reasons_home"), str),
      "relay also": {(a[1], a[2], a[3]) for a in also(relay)} == {
          ("re-emitted", None, f"fixtures/bale-{VERSION}/scratch/relay_sid_--json.json"),
          ("relay-refused", "not-an-object", f"fixtures/bale-{VERSION}/scratch/relay_sid_stdin_--json+relay-refused+not-an-object.json"),
          ("relay-refused", "not-open", f"fixtures/bale-{VERSION}/scratch/relay_sid_stdin_--json+relay-refused+not-open.json")},
      "open fixture": opn["fixture"] == f"fixtures/bale-{VERSION}/scratch/open_bundle_--json+opened.json",
      "open also": {(a[1], a[3]) for a in also(opn)} == {
          ("second-desk", f"fixtures/bale-{VERSION}/scratch/open_bundle_--json+second-desk.json"),
          ("open-refused", f"fixtures/bale-{VERSION}/scratch/open_bundle_--json+open-refused.json"),
          ("rehearsed", f"fixtures/bale-{VERSION}/twine-src/open_--check_bundle_--json.json")},
      "open keys": opn["keys"] == ["outcome", "sid", "tarball", "opener", "desk", "bundle"],
      "unlock fixture": unlock["fixture"] == f"fixtures/bale-{VERSION}/scratch/unlock_sid_--reason-aborted_--json.json",
      "unlock also": {(a[1], a[2], a[3]) for a in also(unlock)} == {
          ("unlock-refused", "hold-branch", f"fixtures/bale-{VERSION}/scratch/unlock_sid_--json+unlock-refused+hold-branch.json"),
          ("unlock-refused", "not-open", f"fixtures/bale-{VERSION}/twine-src/unlock_sid_--json+unlock-refused+not-open.json"),
          ("unlock-refused", "integration-json", f"fixtures/bale-{VERSION}/twine-src/unlock_--integration_--json.json"),
          ("unlocked", None, f"fixtures/bale-{VERSION}/scratch/unlock_sid_--json+unlocked.json"),
          ("no-op", None, f"fixtures/bale-{VERSION}/scratch/unlock_--json.json")},
      "apply fixtures": apply_["fixture"] == f"fixtures/bale-{VERSION}/scratch/apply_--dry-run_--json_tarball+dry-run.json"
          and {a[3] for a in also(apply_)} == {f"fixtures/bale-{VERSION}/scratch/apply_--dry-run_--json_tarball+scope-drift-refused.json"},
      "status fixture": status["fixture"] == f"fixtures/bale-{VERSION}/twine-src/status_--json.json",
      "every verb fixture exists": all((TREE / s["fixture"]).is_file() for s in surf.values() if "fixture" in s)
          and all((TREE / r["fixture"]).is_file() for s in surf.values() for r in s.get("also_recorded", [])),
      "no verb surface points at 0.4.49": not any("bale-0.4.49/" in str(s.get("fixture", "")) or any("bale-0.4.49/" in r["fixture"] for r in s.get("also_recorded", [])) for s in surf.values()),
      "written_against": all(s.get("written_against") == VERSION for s in m["surface"]) and all(v.get("written_against") == VERSION for v in m["vocabulary"]),
      "crafter formats at the pin": all(f.get("fixtures_version") == VERSION and all(x.startswith(f"fixtures/bale-{VERSION}/crafter/") for x in f["fixtures"])
                                      for f in m["surface"] if f.get("kind") == "format" and f.get("format") in ("probe", "light", "exchange")),
      "carried formats stay at 0.4.45": all(f.get("fixtures_version") == "0.4.45" for f in m["surface"] if f.get("kind") == "format" and f.get("format") in ("probe-output", "relay")),
      "apply vocabulary home re-read": next(v for v in m["vocabulary"] if v["axis"] == "apply-outcome")["home_sha256"] == "1f4f2c758fdc3b1f8f92e25dc1561dddbc4ffb11b335f86cdefab4a3e77b21e1",
      "vocabularies unchanged": [len(v["values"]) for v in sorted(m["vocabulary"], key=lambda v: v["axis"])] == [9, 9, 13],
    }
    return checks
LIVE_ASSUMPTION = "A recording of `relay <sid> - --json` replaces the assumption"
def no_assumption_in(texts):
    # the sentence every one of the four places carried while the assumption was live,
    # whitespace-folded (v2: v1 matched the bare identifier, which history mentions keep)
    return all(LIVE_ASSUMPTION not in re.sub(r"\s+", " ", t) for t in texts)
def run_twine(*argv, env=None):
    base = {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8", "TMPDIR": str(WORK)}
    if env: base.update(env)
    return subprocess.run([sys.executable, "-I", "-S", "-B", str(TWINE), *argv], capture_output=True, env=base, cwd=str(TREE), timeout=300)
def stub_root(version):
    root = WORK / f"root-{version}"; (root / "bin").mkdir(parents=True); (root / "bin" / "VERSION").write_text(version + "\n"); return root
def check_ok(proc, want):
    if not proc.stdout.strip(): return False
    obj = json.loads(proc.stdout); return obj.get("ok") is want and proc.returncode == (0 if want else 1)

# --- probes: the recordings ---
for p, exit_, n, h, en, eh in ROWS:
    probe(f"{p}: landed byte-exact ({n} B, {h[:12]})", file_is(p, n, h))
    probe(f"{stderr_path(p)}: stderr beside it byte-exact ({en} B, {eh[:12]})", file_is(stderr_path(p), en, eh))
probe(f"{CARRIED}: the paste-back landed CRLF-folded ({CARRIED_BYTES} B, {CARRIED_SHA[:12]})", file_is(CARRIED, CARRIED_BYTES, CARRIED_SHA))
expected = {p for p, *_ in ROWS} | {stderr_path(p) for p, *_ in ROWS} | {CARRIED}
found = {str(q.relative_to(TREE)) for q in (TREE / f"fixtures/bale-{VERSION}").rglob("*") if q.is_file()} if (TREE / f"fixtures/bale-{VERSION}").is_dir() else set()
probe(f"fixtures/bale-{VERSION}/ holds exactly the 24 recordings, their 24 .stderr siblings and the carried paste (49 files)", exact_file_set(found, expected))
probe("fixtures/bale-0.4.49/ untouched: the 23 recordings hash as recorded", all(file_is(p if p.startswith("fixtures/") else f"fixtures/{p}", size(p if p.startswith("fixtures/") else f"fixtures/{p}"), h) for p, h in OLD) and len(OLD) == 23)
old_found = {str(q.relative_to(TREE)) for q in (TREE / "fixtures/bale-0.4.49").rglob("*") if q.is_file()}
probe("fixtures/bale-0.4.49/ gained no file", old_found == {f"fixtures/{p}" for p, _ in OLD})

# --- probes: the README rows ---
readme = (TREE / "fixtures/README.md").read_text(encoding="utf-8")
rows = readme_rows(readme)
probe(f"fixtures/README.md has a `## bale {VERSION}` section", f"\n## bale {VERSION}\n" in readme)
for p, exit_, n, h, en, eh in ROWS:
    probe(f"README row for {p.split('/',2)[2]}: exit {exit_}, {n} B, sha256, {en} B stderr, stderr sha256", row_matches(rows, p, exit_, n, h, en, eh))
probe("README names the carried paste-back with its landed sha256", CARRIED.split("/",1)[1] in readme and CARRIED_SHA in readme)

# --- probes: the consumption manifest ---
m = tomllib.load(open(TREE / "share/bale-consumption.toml", "rb"))
for name, ok in manifest_facts(m).items():
    probe(f"consumption manifest: {name}", ok)

# --- probes: the assumption retired in its four places ---
probe("the live assumption sentence (a recording of relay <sid> - --json replaces the assumption) is gone from its four places",
      no_assumption_in([(TREE / p).read_text(encoding="utf-8") for p in FOUR_PLACES]))

# --- probes: the verbs ---
probe("twine bale check admits a 0.4.51 install", check_ok(run_twine("bale", "check", "--json", "--bale-root", str(stub_root("0.4.51"))), True))
probe("twine bale check refuses a 0.4.49 install", check_ok(run_twine("bale", "check", "--json", "--bale-root", str(stub_root("0.4.49"))), False))
probe("twine transitions --json is still total (ok)", check_ok(run_twine("transitions", "--json"), True))

# --- probes: the recorder and the lander ---
rec, land = TREE / "bin/twine-record-fixtures", TREE / "bin/twine-land-recordings"
probe("bin/twine-record-fixtures exists, is executable, parses as bash and emits a PROBE block",
      rec.is_file() and os.access(rec, os.X_OK) and subprocess.run(["bash", "-n", str(rec)], capture_output=True).returncode == 0
      and "PROBE BEGIN" in rec.read_text(encoding="utf-8"))
land_run = subprocess.run([sys.executable, "-I", "-S", "-B", str(land), "--check", CARRIED], capture_output=True, cwd=str(TREE), timeout=300) if land.is_file() else None
probe("bin/twine-land-recordings --check <the carried paste> exits 0 on this tree", land_run is not None and land_run.returncode == 0)

# --- controls ---
p0, e0, n0, h0, en0, eh0 = ROWS[0]
if file_is(p0, n0 + 1, h0) or file_is(p0, n0, "0" * 64) or file_is("fixtures/no/such/file", 0, hashlib.sha256(b"").hexdigest()): broken("file_is accepts a wrong size, hash or missing file")
good_row = f"| `{p0[9:]}` | `x` | `y` | {e0} | {n0} | `{h0}` | {en0} | `{eh0}` |\n"
if not row_matches(readme_rows(good_row), p0, e0, n0, h0, en0, eh0): broken("row_matches refuses its own good row")
if row_matches(readme_rows(good_row.replace(f"| {e0} |", f"| {1-e0} |")), p0, e0, n0, h0, en0, eh0): broken("row_matches accepts a wrong exit")
if row_matches(readme_rows(good_row.replace(f"`{eh0}`", "`" + "f" * 64 + "`")), p0, e0, n0, h0, en0, eh0): broken("row_matches accepts a wrong stderr sha")
if row_matches(readme_rows(good_row.replace(f"| {en0} |", f"| {en0 + 1} |")), p0, e0, n0, h0, en0, eh0): broken("row_matches accepts wrong stderr bytes")
if readme_rows(f"| `{p0[9:]}` | `x` | `y` | {e0} | {n0} | `{h0}` |\n"): broken("the row pattern accepts a six-column row")
if exact_file_set(expected | {"extra"}, expected) or exact_file_set(expected - {CARRIED}, expected): broken("exact_file_set accepts an extra or a missing file")
if not no_assumption_in(["clean text", "history: the assumption named _read_relay_input was retired"]): broken("no_assumption_in refuses history")
if no_assumption_in(["clean", "x A recording of `relay <sid>\n- --json` replaces the\nassumption y"]): broken("no_assumption_in misses the live sentence across line breaks")
class Fake:
    def __init__(self, rc, out): self.returncode, self.stdout = rc, out
if not check_ok(Fake(0, b'{"ok": true}'), True) or check_ok(Fake(0, b'{"ok": true}'), False) or check_ok(Fake(1, b'{"ok": true}'), True) or check_ok(Fake(0, b""), True): broken("check_ok is wrong")
bad = json.loads(json.dumps(m)); bad["bale"]["pin"] = "0.4.49"
if manifest_facts(bad)["pin"]: broken("manifest_facts accepts the old pin")
bad = json.loads(json.dumps(m)); [s for s in bad["surface"] if s.get("verb") == "relay"][0]["argv"] = ["relay", "<sid>", "<file>", "--json"]
if manifest_facts(bad)["relay argv"]: broken("manifest_facts accepts the file argv")
bad = json.loads(json.dumps(m)); [s for s in bad["surface"] if s.get("verb") == "relay"][0]["reasons"] = RELAY_REASONS[:-1]
if manifest_facts(bad)["relay reasons"]: broken("manifest_facts accepts a short reasons list")
bad = json.loads(json.dumps(m)); [s for s in bad["surface"] if s.get("verb") == "open"][0]["also_recorded"] = []
if manifest_facts(bad)["open also"]: broken("manifest_facts accepts open without its refusal")
bad = json.loads(json.dumps(m)); bad["bale"]["schemas"]["telemetry-record.schema.json"] = "0" * 64
if manifest_facts(bad)["schemas"]: broken("manifest_facts accepts a changed schema hash")
if len(ROWS) != 24 or len({r[0] for r in ROWS}) != 24 or len(SCHEMAS) != 8 or len(RELAY_REASONS) != 22: broken("the pinned facts are not what the probes assume")

print(f"[checkpoint] {len(failures)} failing probe(s)")
sys.exit(1 if failures else 0)
PY

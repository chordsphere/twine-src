#!/usr/bin/env bash
# Blind checkpoint — session twine-runtime-anthropic (Arc 2 R2, v1), authored
# at the desk of sitting 2026-10-08-open-arc2-003 from the request alone.
#
# What it grades (outcomes only): the `anthropic` adapter is registered and
# five capabilities are implemented; the fifteen recordings of 2026-10-13 and
# their carried paste are in place byte-exact and the lander's --check
# agrees; the pinned readers map every recording — and the synthetic
# refusals, truncations and shapes that could not be recorded — onto the
# stop axis as the brief's table says, with usage through from_anthropic;
# build_request places the three cache breakpoints and sends nothing twine
# never asks for; the key goes into x-api-key and nowhere else, and its
# absence refuses construction; the transition table is total with
# request-refused and provider-error, loop_keys and written_against at the
# floor; no module imports the anthropic SDK; the two stale usage sentences
# are gone; VERSION moved. The recordings it drives the readers with are
# carried here (gzip+base64) so nothing in the tree is trusted twice.
#
# Writes only under ./.checkpoint-r2.<pid>/ (removed at exit); reads nothing
# of its own. Exit 0 all probes passed; 1 a probe failed; 2 the oracle is
# broken.
set -u
WORK="$(pwd)/.checkpoint-r2.$$"
mkdir -p "$WORK" || exit 2
trap 'rm -rf "$WORK"' EXIT
echo "[checkpoint] writes only under $WORK (removed at exit)"
export TMPDIR="$WORK"
PYTHONDONTWRITEBYTECODE=1 python3 -I -B - "$WORK" <<'PY'
import base64, gzip, hashlib, json, os, re, subprocess, sys, tomllib
from pathlib import Path

def broken(msg):
    print(f"[checkpoint] ORACLE BROKEN: {msg}")
    sys.exit(2)
sys.excepthook = lambda t, v, tb: broken(f"unplanned {t.__name__}: {v}")

WORK = Path(sys.argv[1]); TREE = Path.cwd()
FIVE = {"tool-calling", "thinking", "usage-accounting", "prompt-caching", "streaming"}
PINS = json.loads("{\"rows\": [[\"models\", \"json\", null, 14233, \"d744304435f479b8350556098dbf9cc5c3a4d94814351dfdcc073623d4afce13\"], [\"text\", \"json\", \"f874bb9125f432e6a5aa5ebd4964125d6792872d100c919fc775e1c10828f1a1\", 527, \"b9330f4527da18c36006c76905134be6ead1bd61980a17d02dcf117c823c11a3\"], [\"text_stream\", \"sse\", \"7364a117e4583cff95db45733fc2a7ac9fec66e9b9355f66cfb8ec61a7b14467\", 1258, \"ff21be177393814ab673b742cb0ea22ad80d22f9ee6ac68d84c681a49fd141b5\"], [\"max_tokens\", \"json\", \"4a8c485ec97d5179a2a481ed4cdc4f3e1b5e3da0c7db11bdde1b6c8160c35029\", 536, \"258f687adf36abbd828b39bc886ab360f1677fbb957eb378f0ec3f28e7de25fd\"], [\"max_tokens_stream\", \"sse\", \"3b828585dec98edf6c557a8f72ca8f0736339de31aca71e6753ab5c6cd15e5e0\", 1266, \"5b74e39103d928b54390010db3f80b5643fc19326987d4861be9d1a213b659bc\"], [\"tool_use\", \"json\", \"e35be61c7d9347e59825ddb4267a5f4cd7bf213272ae4f48dd20d201cf0f1a36\", 631, \"712d0ac17cd9439f426b00300a68e8c8eef10834c7fecbc1607c09b8830e89ee\"], [\"tool_use_stream\", \"sse\", \"45665e3e977936e29f4e51e9e5a2a6efc7ee559eba3d757b1aa4939107b0a5bd\", 1795, \"9a0ee0617a853e634650710792baef74c067e0566ee666b1e1cf5cd945d396d7\"], [\"tool_result\", \"json\", \"d5d067e11a7eee68deb08a87242adbbdd59b9ba58e346a82fe1def0deff0d8a0\", 552, \"3090a163575dedb1158041ef1507946ee8777f8e9e141996bf2ddc4515905785\"], [\"tool_result_error\", \"json\", \"ebc86720085f5a219382d1a1c56d49c609376b8c1e0b6bc48488245433ae7e21\", 642, \"248e6b96cd39b32725d7de3dad99cd737ba120382b2901edbc0463efc0eb5137\"], [\"thinking_stream\", \"sse\", \"1b46a648951e2c91bdb2d3cde8f00e3c6381a2f647f56cdfeba9c31ed4a02606\", 2566, \"2c159fc05ba61367ab9c0f52346a7d75787783bc22f5c25d35e1af27bb831988\"], [\"cache_write\", \"json\", \"eef65b5ead7166b24c483142a365762133a3d5c551d7c1e4af355f73cbf1a6d0\", 530, \"b857ef93e7081d52231d0d7e2bd51b9d715d0aa25a35d3deb5d306a904469f51\"], [\"cache_read\", \"json\", \"9b0521f6aea591eb5436d770cfcf0329bc92807a74ac9167d60c5bb9b8fbe460\", 527, \"ad4dafd70c4656126f0d2416e880ecef05add216f508e718615e6d0e883b7ff0\"], [\"error_401\", \"json\", \"088074b66073201ecd0f9b33719bbe75d12a7e902cd4a7f63a5968ccae7ed15f\", 130, \"822bfc574d1a7489ef21c556d4dcd30c4aaa7ab4be7b00d275a1fbd74800b661\"], [\"error_404_model\", \"json\", \"cce91afb6514cbc46fcb0b44dcd346dd8f4422a951b331ae7d455835d2acf801\", 133, \"ed007a184db21677ff8ee6621308461008e960182b70f75313e48ef9cf3bf174\"], [\"error_400\", \"json\", \"2050f12e5179384323c5c6304369a047c9e4b9932002b706a3c89b7876f1a5c3\", 138, \"5c8bd802a47e72312fddd1dd662e8258e30edeb0dd3d7d630d07bfbf71313dc7\"]], \"carry\": {\"text\": \"H4sIAHaAzWoC/3WRQU/DMAyF/4vPm7RpTEg9shsHJI4IoSgkXpstdbrEYYyq/x1nrBod4pT4fc9O8tJDGyx6qMB4nS3OG+32eb6er2EGzoreplotlsvN9vTIm8NT2AW32u2OD9uvl2fx8KnD4sKUdI0ixOCLoFNyiTWxSCYQo+yq1370M34Wcl6kOjpCGN5+rFqKCBVl72eQOHQqok6BxIhkFedIcAEJDxnJ4MRtUUb4NGr5fLGqB0ddZsVhjyRwdS+nadOgMjKeXSA1NSxGLtj+x8beMh+7BluM2qt1+9d/pcvmlg4zCJl/S3c3yvVREmHjaO+onvQnjB/OoGJXsoMSvdXRll+kLcYSkqoxCKp9eNcepMc6XVNI7MwlrOEbf5A/sg8CAAA=\", \"max_tokens\": \"H4sIAHaAzWoC/3WRQUsDMRCF/0qZcxdaZCnuVbxoDyLoRSSMyXQ3bDZZMxNpKf3vJrVLbcVTwvvezCRv9jAEQw4a0A6ToapD26eqrmqYgzVZH7hVi+XybrN7kHVc3243Ty9mJY9jf/+aPbIbqbiIGVvKQgyuCMhsWdBLlnTwQvnWvO0nv9C2kOPRwHMYaWZ5NqAhOLz/VKD1FKHxybk5sIRRRUIOvkzDrZLQk2c4IabPRF7Thd9QbuJ40tLxhc0erB+TTA2am1Weh7ojpfMAscGrS8Ni4hmb/9hUW/rT2NFAEZ2qh7/+M1121/Qwh5Dkt1RfKedP5Sw763vr24t6pvhlNSmxJT0oOzAYTVmn31AsIamWQkatCx/oINcYi60PLFafwjp8A9FhFEMYAgAA\", \"tool_use\": \"H4sIAHaAzWoC/3WRX0/CMBTFv0ufwYC4aHhViNHwgAlqYkxT1rutobsd7S0RCd/d2+mCw/i2nd/pPffPQdROgxVTkVsVNQwrZTZxmA0zMRBGs16HUo7G49ti/0Ar97jDxaxZ3Ew+i+Wa2EP7BpILQlAlsOCdTYIKwQRSmDy5QwL+mr4dOj85Z2UM0KWk/8g586e63Orm1ayXxexlsrqfX949I7tQ1emdB6VlYWz7EJvIRQ+iUVQxQ0cQLuiDxJEzlbXgE/1J1MZDzuj4/t2QMpg4RmsHIpBrJNcODvvNtSDANgLm0HNr4BI2dFpsx+e4titJbgPI8GpynXrJK5A51yfjUPYdo463o/3DurcpAJoKavDKyqz+6z/RcXVOeS0u0m8pG59Jp7F4cZXBjcGyVyCA35kcJJm0PZFOrJXX7TkK8GlNsgTHqLRurWy6hTaqRBfI5D/rOn4BKySlcHcCAAA=\", \"error_401\": \"H4sIAHaAzWoC/6tWKqksSFWyUkotKsovUtKB0lbVMPHE0pKM1LySzOTEksz8vHiYstzU4uLEdJCCzLyyxJzMFIUK3cSCTN3s1EqlWh2lotTC0tTikvjMFKAKICfewNDQOa3Sq6TCydfJOcrDKM/UPCOiIqBMqRYAc7xCfYIAAAA=\", \"error_404_model\": \"H4sIAHaAzWoC/6tWKqksSFWyUkotKsovUtKB0lbVMPG8/JL4tPzSvJR4mIrc1OLixHSQXG5+SmqOlUJevm5xaXKGLpira2RgZKZUq6NUlFpYmlpcEp+ZAlQJ5MQbGBo6p1V6lVQal3tXWRa4unvkZwWlGWco1QIA/Rfzi4UAAAA=\", \"error_400\": \"H4sIAHaAzWoC/6tWKqksSFWyUkotKsovUtKB0lbVMPHMvLLEnMyU+KLUwtLU4pJ4mLrc1OLixHSQCiir2ErBLTM1J0UBpDKzKDVFqVZHCaYrMwWoEMiJNzA0dE6r9CqpMs0oyiwJKnUP9YnwtiwuUKoFAN8FPI+KAAAA\", \"text_stream\": \"H4sIAHaAzWoC/7VTwW7bMAy95ysMnhOgwRas8K0oCgzZDjv1MgwCa7G2EEXyJLprUfjfSyVxYyVuhx7qi+H3KPG9Z5IeyHFZbClGrElFxsAzjYxl8Qz81BKUkJEwH76hfIat12SlpLLYaVo0aDbdYrVYSZXR6Wis1cVyeX3/tObvVz8v8XZdr29/3JjlL5SavIEAwdsEYIxGurnUrfKORSOUv//sP9A4ClC6zto5RPatCoTRuwyK9LcjV1EGapLDNg5YN7gwru1Ysd+QE/LLN+mDVUOqkovZeKfygouBF1q/xQ1n0/3UNrSlgFattuf1R3bZnLL9HHzHY+ireKHwYCpSbFIOkILSGHTK3N1TSLZVTV6o2vo7tCC3aIO185FNdbDfF69PP5vRfgwOWas766vN9DBMlOwaa3rcux/zyfzhHNNjKty9SoB+ontrXH3SroAEwlsKZfgY31e4K8kU7pFc2WvZQR//kyEbiXwvJN/+LyPfjgQU2XO8dtiySU8ZCSMP2fwDOa24Cw4+sAUnK9V/2l6cD3KGHHWJ68a4jfz40SL0U1lNhT/mYBTzCyrZunXqBAAA\", \"thinking_stream\": \"H4sIAHaAzWoC/7VW246iShR9n6/o8OpMABVBk/OAiICiXLw1npwYhBJLLsWlQGDivx+cbrvbnp6ZTDJDYrD2WlV77U2xKFCACA8eQpBltgd2GbZT/Mm1sT14+ErgKgbEgLgDic+3MTH4SoTIBUFDcQI7d8GXow39/AvzhWlY0L1OzbwdRdPCoZrgE2eJgI2PdcRHQ28rNpz7BE0gRcE1YGcZbLJF12wOinCjkRj8+9/TwIYRSIlBlAfBZyLDKN6lwM5QdBfKQJKDyAF3QRc0k4PsFstvVcAozvEOIx9EDdjtN3ls5wh2TrMwhija3ROoG97A7o+w29zr+iA+ghCkdrBjwu/5ryh9fI9ePhMox29DXFMLSAvogB2G1z4Q10a5dupeex4dQHote+cB1EBegPZ2QDSruND2IpRh6DyXf3m4XpdPn8DTDnhu824fIMf/eB98QPmW0wXlU+Fv8Wvdz/PwEUY+jLzrA7/9HRDNKINeZOM8vZKI94LihvZOwQNxDRI/Et1sRWz/XPQ3yp3op8j3Yl+obyVfHv5q7pd+vHDfdkjgjQXrGVOR9xYSr3T5laK40jHeh7j5OYvRpKPQ+/PZNVN4OPXa0hDN8unKcSacgtu0hDhJU06jcU3OilrWantIe9k2zYJElIztTEs9vi15KT8pEaVpJ2tVhDpqlRuLzNCEaQmltxCM0yqB50X/nGmVzkr6UDZjG2zGnh0qzKZgyt5mVc8XbIjk4R7WG4ubrMKkwJZKqdBTfbQXhtbG7pALOB7qZwMJjthVD8VWLKR277DkWPk0HU1NmsV9EuWQnTomW6yWjlOxpACLiSCvfJalrMe46PGy6a4pKcbLjDwKyCDLjim2gnq5rxM+jzk0Dg8T1sReQlMnRVLkSlxbptgVTyeDGhXJUQzFfK1qPh5HigLq4exQ1k6WjYTNur1/bLfWkeKPGN6i5EZhr6osc5Gu5RlJdWfsaMr0MztZchZrxpAcnTWh1OEqVww1NnK3vVbchPQT27e6Vbmew0wcdiM2l7kjri2xqrm+VUzJjbCWNUwZ1JDh26qexoyZM3vMqUu1a89ZrpuUfuLP02E3TmzSrrx0Pl9LrMc63jib2Z2qTR56pdEiPZEd+nbeIUf9g7w5tizaHNJxf9qyTufM0NvUJF/KGqX33a20RhBq6/4j8oVkOZfb8bJVmNvEr8NxryWqUmUjYx+ERvbYOZyWG2GWB+psG2iP/jLX8aOuTuTVIdRaPdpVYn67HW+yPcM7us9wez6EeAmoPBLU8lEbiWIG+2XQaTl0Szcqq+Cw39nm2Khcj6kOGXOADjM3vWBOKR2tM071oJduIVw4m5VPlypYTfW+5x71uaWr7RXTXs/DuvaDou8kNY5Z3RMXJWiNgaNYXDBjGH4r+uvipAd7dVUV4wCpizD223KVl/M89iRe/OfZaX7ifSj+lfWh+M2L/PBy/Tk7pX9ip6C8Er/dXnzzFwJ+357oD6yxyfhqi0/pO32auPypTtLfVXE7enyo/w4k3ui9OxQQIHJ3jYVGxG8cDd6dMy5/7bDw7uve6bwLvQr7+vppemFTl8tH3fqo728x4uHdnvkfqp6j3gYKAAA=\", \"tool_use_stream\": \"H4sIAHaAzWoC/81UTW/bMAy951cYOidDsy0b4Nuww4Z0h30AK5qlEFSLsZXIkmvRRYvA/32UHSeW57S7rJhveo8U+Z5owj0YjKMcnBMpcIeixIkUKOJoz/CxABazgGTT7sziPcutBE0hiRaVhFkm1K6aLWYLilLSp7qUX8znHzePS1wtlj+ui6vU4J1Yuu8pxYQFCCit9oBwTlE146sl1iD1yOJfN+1BKAMli02l9ZQ5tAUvQThrAsjBXQUmgQCUQMnadVjVqVCmqJCj3YEh8u2b91RIJBnwhG5GZQ0PIy46nmh5jutyfQEoMsihFJov8j/jT+w8G7L1lNkK+9D8HamB8l4lwFF5J5i3SopSetfNBkovnKdgiUq1vRWa0TVSidRYhyo5GFBH9NWTCbQjcPCZ32qb7MYHYSSkKSnhoRXe573uQx5aq3nloJsKf65oLi6/ff25er1JPl27q3z3odquxJfPlxRlRO7zGns3SjeJ3he6s/b+au11H++XqoQEWd0oCkQVyqQDFRHzIDsnnOYZxdPCm5BAeIucGmofcUtDeQwuyCxFT7xtJpWx+rz3L9TCfk0IZuuml+ipYXihhuJozYxFOPbzPzTlXuEDrln9rEl+wzz3w9ii1000rrLbtqP6ApL19AR7sP/D/fU2HKzW+t/tx8FCW8wH0Kkz0p0ps6P/tbcRg+kYtW7sKfocC5J/A2DeycIDBwAA\", \"max_tokens_stream\": \"H4sIAHaAzWoC/7VTwW7bMAy95ysMnhOg2RAM9bXopbcNGDpsGARWYmwhsuRKcpGi8L+XSuLGcp0VPcwXw+89ie/RJD2RjWXRUAhYkQgRfVwojFgWLxCfW4ISMhKWwzeUL9A4RYYl0mCnaFWj3nWrzWrDKq3S0VCJq/X6Zvt8F78/1r9/be8b+cXf1j+v71mTF2DAO5MADEFzNZuqSWcje4Tyz9/jB2pLHkrbGbOEEF0rPGFwNoMCPXZkJWWgIj5swoB1Qwpt2y6K6HZkmfz6jeugrElIvjhqZ0UuuBp4ptUlbjib7qe2poY8GrFp3uvP7Lqesv0SXBfH0IazkH/SkkTUqQ+QGqXQq9RzuyWfYouKHFOVcQ9ogG9RGivrQtTyFL8vhqdfLOg4BadWiwfj5G5+FmYkh7qK9sfwYz5lP52LtE/Cw6sEOFefWGi1rSY1C0ggXLLJAxjx3zYPkszmEcntvclOJn+4lgodigYVseHLbXLtR11y7aj6bO5hx2bTZCSM3GfTDw3uhzH5xBZMVqr/b3vxfpAz5OyLc9fa7vinjxahv9CwufaPOZgO2iux7dXe8gQAAA==\"}, \"paste_sha\": \"4d1bfd63ef6746546c13962aad08f3ee726e4d81284b69cb21ea4a1bbd5da92d\"}")
ROWS, CARRY, PASTE_SHA = PINS["rows"], PINS["carry"], PINS["paste_sha"]
STOP13 = {"end-turn", "max-tokens", "model-refusal", "window-exhausted", "rate-limited", "overloaded", "network-failure",
          "timeout", "tool-error", "malformed-shape", "cap-reached", "killed", "cap-unchecked"}
SECRET = "sk-ant-ORACLE-SENTINEL-7f3a9c"
SSE = {"content-type": "text/event-stream; charset=utf-8", "request-id": "req_oracle"}
JSONH = {"content-type": "application/json", "request-id": "req_oracle"}

failures = []
def probe(label, ok):
    print(f"{'[PASS]' if ok else '[FAIL]'} {label}")
    if not ok: failures.append(label)

def rec(name): return gzip.decompress(base64.b64decode(CARRY[name]))
def env(): return {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C.UTF-8", "TMPDIR": str(WORK), "PYTHONDONTWRITEBYTECODE": "1"}
def twine(*argv):
    return subprocess.run([sys.executable, "-I", "-B", str(TREE / "bin" / "twine"), *argv, "--json"], capture_output=True, env=env(), cwd=str(WORK), timeout=120)
def twin(p):
    try: return json.loads(p.stdout) if p.stdout.strip() else None
    except ValueError: return None

# One isolated interpreter per probe group: a script that imports the adapter and prints JSON results.
PRE = ("import sys, json, traceback\n"
       "sys.path.insert(0, " + json.dumps(str(TREE)) + ")\n"
       "def J(x):\n    return json.loads(json.dumps(x, default=str))\n"
       "out = {}\n"
       "def step(name, fn):\n    try:\n        out[name] = {'ok': True, 'value': J(fn())}\n"
       "    except BaseException as e:\n        out[name] = {'ok': False, 'error': type(e).__name__ + ': ' + str(e)}\n")
def run_py(code):
    p = subprocess.run([sys.executable, "-I", "-B", "-c", PRE + code + "\nprint(json.dumps(out))\n"], capture_output=True, env=env(), cwd=str(WORK), timeout=300)
    err = p.stderr.decode(errors="replace")
    try: return json.loads(p.stdout.decode()), err
    except ValueError: return {"__crash__": err[-600:]}, err

# --- detectors ---
def value(res, name): return res.get(name, {}).get("value")
def okv(res, name): return res.get(name, {}).get("ok") is True
def tokens(v, want): return isinstance(v, dict) and v.get("usage") == want
def stopped(v, key): return isinstance(v, dict) and "stop" in v and v.get("stop") == key
def refused_with(v, *words):
    return (isinstance(v, dict) and v.get("stop") == "request-refused" and isinstance(v.get("reason"), str)
            and all(w in v["reason"] for w in words) and v.get("usage") is None)
def implements(a): return set((a.get("implements") or a.get("capabilities") or []))

# --- registry ---
p = twine("runtime", "list"); o = twin(p) or {}
caps = {c.get("name"): c for c in o.get("capabilities", []) if isinstance(c, dict)}
ads = {a.get("name"): a for a in o.get("adapters", []) if isinstance(a, dict)}
probe("runtime list: ok, adapter `anthropic` registered implementing the five, `fake` still registered",
      p.returncode == 0 and o.get("ok") is True and "anthropic" in ads and FIVE <= implements(ads["anthropic"]) and "fake" in ads)
probe("the five capabilities are `implemented` and name `anthropic` among their adapters",
      all(caps.get(n, {}).get("status") == "implemented" and "anthropic" in (caps.get(n, {}).get("adapters") or []) for n in FIVE))

# --- recordings ---
fx = TREE / "fixtures" / "anthropic"
all_ok = True
for name, ext, rq, nb, rs in ROWS:
    r = fx / f"{name}.response.{ext}"
    ok = r.is_file() and hashlib.sha256(r.read_bytes()).hexdigest() == rs and len(r.read_bytes()) == nb
    if rq:
        q = fx / f"{name}.request.json"; ok = ok and q.is_file() and hashlib.sha256(q.read_bytes()).hexdigest() == rq
    try:
        mo = json.loads((fx / f"{name}.meta.json").read_text(encoding="utf-8"))
        ok = ok and isinstance(mo.get("status"), int) and isinstance(mo.get("headers"), dict)
    except Exception: ok = False
    if not ok: all_ok = False; print(f"  [detail] recording {name} is not as recorded")
probe("the fifteen recordings (response, request, meta) are in place byte-exact", all_ok)
cp = fx / "carried" / "twine-anthropic-record-2026-10-13.txt"
probe("the carried paste is in place, LF, byte-exact", cp.is_file() and hashlib.sha256(cp.read_bytes()).hexdigest() == PASTE_SHA)
lander = TREE / "bin" / "twine-land-provider-recordings"
if lander.is_file() and cp.is_file():
    l = subprocess.run([sys.executable, "-I", "-B", str(lander), str(cp), "--check", "--tree", str(TREE)], capture_output=True, env=env(), cwd=str(WORK), timeout=120)
    probe("bin/twine-land-provider-recordings PASTE --check --tree agrees with the landed tree (exit 0)", l.returncode == 0)
else:
    probe("bin/twine-land-provider-recordings exists", False)

# --- the table ---
t = twin(twine("transitions")) or {}
axes = {a.get("name"): a for a in t.get("axes", []) if isinstance(a, dict)}
stop_keys = set(axes.get("stop", {}).get("keys") or [])
manifest = tomllib.load(open(TREE / "share" / "bale-consumption.toml", "rb"))
floor = manifest["bale"].get("floor")
toml = tomllib.load(open(TREE / "share" / "transitions.toml", "rb"))
probe("twine transitions: ok and total, the stop axis carrying the thirteen plus request-refused and provider-error",
      t.get("ok") is True and STOP13 | {"request-refused", "provider-error"} <= stop_keys)
probe(f"[table] written_against is the manifest's floor ({floor})", isinstance(floor, str) and t.get("written_against") == floor)
probe("[axis.stop] loop_keys names cap-reached, cap-unchecked and killed",
      set(toml.get("axis", {}).get("stop", {}).get("loop_keys") or []) == {"cap-reached", "cap-unchecked", "killed"})
rp, _ = run_py("import twine.transitions as T\nstep('loop', lambda: sorted(T.loop_keys()))\nstep('stop', lambda: sorted(T.stop_keys()))\n")
probe("twine.transitions.loop_keys() returns the three and stop_keys() the axis",
      value(rp, "loop") == ["cap-reached", "cap-unchecked", "killed"] and set(value(rp, "stop") or []) == stop_keys)

# --- the readers ---
code = ("from twine.runtime.adapters import anthropic as A\nimport base64, gzip\n"
        "CARRY = " + json.dumps(CARRY) + "\nJSONH = " + json.dumps(JSONH) + "\nSSE = " + json.dumps(SSE) + "\n" + '''
def rec(n): return gzip.decompress(base64.b64decode(CARRY[n]))
def rr(status, headers, body): return A.read_response(status, headers, body).as_json()
def rs(status, headers, chunks): return A.read_stream(status, headers, chunks).as_json()
step("text", lambda: rr(200, JSONH, rec("text")))
step("max_tokens", lambda: rr(200, JSONH, rec("max_tokens")))
step("tool_use", lambda: rr(200, JSONH, rec("tool_use")))
step("e401", lambda: rr(401, JSONH, rec("error_401")))
step("e404", lambda: rr(404, JSONH, rec("error_404_model")))
step("e400", lambda: rr(400, JSONH, rec("error_400")))
step("e429", lambda: rr(429, dict(JSONH, **{"retry-after": "7"}), b'{"type":"error","error":{"type":"rate_limit_error","message":"This request would exceed the rate limit"},"request_id":"req_x"}'))
step("e529", lambda: rr(529, JSONH, b'{"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}'))
step("e500", lambda: rr(500, JSONH, b'{"type":"error","error":{"type":"api_error","message":"Internal server error"}}'))
step("e504", lambda: rr(504, JSONH, b'{"type":"error","error":{"type":"timeout_error","message":"Request timed out"}}'))
step("pause", lambda: rr(200, JSONH, rec("text").replace(b'"stop_reason":"end_turn"', b'"stop_reason":"pause_turn"')))
step("notjson", lambda: rr(200, JSONH, b"<html>nope</html>"))
step("refusal", lambda: rr(200, JSONH, rec("text").replace(b'"stop_reason":"end_turn"', b'"stop_reason":"refusal"')))
step("window", lambda: rr(200, JSONH, rec("text").replace(b'"stop_reason":"end_turn"', b'"stop_reason":"model_context_window_exceeded"')))
step("stream_whole", lambda: rs(200, SSE, [rec("text_stream")]))
step("stream_bytes", lambda: rs(200, SSE, [bytes([b]) for b in rec("text_stream")]))
step("thinking", lambda: rs(200, SSE, [rec("thinking_stream")[i:i+7] for i in range(0, len(rec("thinking_stream")), 7)]))
step("tool_stream", lambda: rs(200, SSE, [rec("tool_use_stream")]))
step("max_stream", lambda: rs(200, SSE, [rec("max_tokens_stream")]))
step("truncated", lambda: rs(200, SSE, [rec("text_stream")[: int(len(rec("text_stream")) * 0.6)]]))
head = rec("text_stream").split(b"\\n\\n")[0] + b"\\n\\n"
step("sse_error", lambda: rs(200, SSE, [head + b'event: error\\ndata: {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}\\n\\n']))
step("stop_key", lambda: [A.stop_key(x) for x in ("end_turn", "tool_use", "max_tokens", "refusal", "model_context_window_exceeded", "stop_sequence", "pause_turn")])
step("error_key", lambda: [A.error_key(429, "rate_limit_error", None), A.error_key(529, "overloaded_error", None), A.error_key(500, "api_error", None),
                           A.error_key(504, "timeout_error", None), A.error_key(401, "authentication_error", None), A.error_key(None, None, TimeoutError("t")),
                           A.error_key(None, None, ConnectionError("c"))])
tools = [{"name": "a", "description": "first", "input_schema": {"type": "object", "properties": {}}},
         {"name": "b", "description": "last", "input_schema": {"type": "object", "properties": {}}}]
step("build", lambda: A.build_request(model="m", max_tokens=5, system="sys", messages=[{"role": "user", "content": "hi"}], tools=tools, thinking={"type": "adaptive"}))
step("build_unknown", lambda: A.build_request(model="m", max_tokens=5, system=None, messages=[{"role": "user", "content": "hi"}], tools=[], thinking=None, temperature=0.5))
''')
r, err = run_py(code)
if "__crash__" in r: print("  [detail] the reader interpreter crashed: " + r["__crash__"].replace("\n", " | ")[-400:])
v = value(r, "text")
probe("read_response(text): stop end-turn, text 'twine', usage 37/4/0/0/0, request_id from the header",
      stopped(v, "end-turn") and v.get("text") == "twine" and tokens(v, {"input": 37, "output": 4, "thinking": 0, "cache_read": 0, "cache_write": 0})
      and v.get("request_id") == "req_oracle" and v.get("tool_calls") == [])
probe("read_response(max_tokens): stop max-tokens", stopped(value(r, "max_tokens"), "max-tokens"))
v = value(r, "tool_use")
probe("read_response(tool_use): stop null, one tool call with the recorded id, name and parsed arguments, the tool_use block kept in content",
      stopped(v, None) and v.get("tool_calls") == [{"id": "toolu_01FRmgqdpXibQfEW3UHF2DVn", "name": "read_file", "arguments": {"path": "notes.txt"}}]
      and any(isinstance(b, dict) and b.get("type") == "tool_use" and b.get("input") == {"path": "notes.txt"} for b in (v.get("content") or [])))
probe("the 401 recording: request-refused, reason quoting authentication_error and its message, usage null",
      refused_with(value(r, "e401"), "authentication_error", "invalid x-api-key"))
probe("the 404 and 400 recordings: request-refused naming not_found_error / invalid_request_error",
      refused_with(value(r, "e404"), "not_found_error") and refused_with(value(r, "e400"), "invalid_request_error"))
v = value(r, "e429")
probe("a 429 with retry-after 7: rate-limited, retry_after 7", stopped(v, "rate-limited") and v.get("retry_after") == 7)
probe("529 → overloaded, 500 → provider-error, 504 → timeout",
      stopped(value(r, "e529"), "overloaded") and stopped(value(r, "e500"), "provider-error") and stopped(value(r, "e504"), "timeout"))
probe("refusal → model-refusal, model_context_window_exceeded → window-exhausted",
      stopped(value(r, "refusal"), "model-refusal") and stopped(value(r, "window"), "window-exhausted"))
probe("pause_turn and a non-JSON 200 → malformed-shape", stopped(value(r, "pause"), "malformed-shape") and stopped(value(r, "notjson"), "malformed-shape"))
want_text = {"input": 37, "output": 4, "thinking": 0, "cache_read": 0, "cache_write": 0}
probe("read_stream(text_stream) whole and byte by byte: end-turn, 'twine', usage from message_delta",
      all(stopped(value(r, k), "end-turn") and value(r, k).get("text") == "twine" and tokens(value(r, k), want_text) for k in ("stream_whole", "stream_bytes")))
v = value(r, "thinking")
probe("read_stream(thinking_stream): end-turn, text '391', usage 49/3/30/0/0, one thinking block with its signature kept in content",
      stopped(v, "end-turn") and v.get("text") == "391" and tokens(v, {"input": 49, "output": 3, "thinking": 30, "cache_read": 0, "cache_write": 0})
      and len(v.get("thinking") or []) == 1
      and any(isinstance(b, dict) and b.get("type") == "thinking" and isinstance(b.get("signature"), str) and len(b["signature"]) > 20 for b in (v.get("content") or [])))
v = value(r, "tool_stream")
probe("read_stream(tool_use_stream): stop null, arguments assembled from the input_json_delta pieces",
      stopped(v, None) and v.get("tool_calls") == [{"id": "toolu_01KQPVZ2fcGYsWmkAujZaLHK", "name": "read_file", "arguments": {"path": "notes.txt"}}])
probe("read_stream(max_tokens_stream): max-tokens", stopped(value(r, "max_stream"), "max-tokens"))
probe("a stream cut before message_stop → network-failure", stopped(value(r, "truncated"), "network-failure"))
probe("an SSE error event carrying overloaded_error → overloaded", stopped(value(r, "sse_error"), "overloaded"))
probe("stop_key: end_turn, tool_use, max_tokens, refusal, window, stop_sequence, pause_turn",
      value(r, "stop_key") == ["end-turn", None, "max-tokens", "model-refusal", "window-exhausted", "malformed-shape", "malformed-shape"])
probe("error_key: 429, 529, 500, 504, 401, a timeout, a connection error",
      value(r, "error_key") == ["rate-limited", "overloaded", "provider-error", "timeout", "request-refused", "timeout", "network-failure"])
b = value(r, "build") or {}
sysb = b.get("system"); tl = b.get("tools") or []; msgs = b.get("messages") or []
last = msgs[-1].get("content") if msgs and isinstance(msgs[-1], dict) else None
tools0 = {"type": "object", "properties": {}}
probe("build_request: system as one cached text block, cache_control on the last tool only and on the last message's last block, stream true, thinking passed, nothing twine never sends",
      isinstance(sysb, list) and len(sysb) == 1 and sysb[0].get("type") == "text" and sysb[0].get("text") == "sys" and sysb[0].get("cache_control") == {"type": "ephemeral"}
      and len(tl) == 2 and tl[1].get("cache_control") == {"type": "ephemeral"} and "cache_control" not in tl[0] and tl[0].get("input_schema") == tools0
      and isinstance(last, list) and bool(last) and last[-1].get("cache_control") == {"type": "ephemeral"} and last[-1].get("text") == "hi"
      and b.get("stream") is True and b.get("thinking") == {"type": "adaptive"} and b.get("model") == "m" and b.get("max_tokens") == 5
      and not ({"stop_sequences", "temperature", "top_p", "top_k", "metadata", "tool_choice"} & set(b)))
probe("build_request refuses an unknown keyword (temperature)", "build_unknown" in r and not okv(r, "build_unknown"))

# --- the key ---
code2 = ("from twine.runtime.adapters import anthropic as A\nimport base64, gzip\n"
         "CARRY = " + json.dumps(CARRY) + "\nSECRET = " + json.dumps(SECRET) + "\n" + '''
seen = {}
def transport(method, url, headers, body):
    seen.update({"method": method, "url": url, "headers": dict(headers), "body": body.decode() if body else None})
    return 401, {"content-type": "application/json", "request-id": "req_k"}, [gzip.decompress(base64.b64decode(CARRY["error_401"]))]
def go():
    a = A.AnthropicAdapter(env={"ANTHROPIC_API_KEY": SECRET}, transport=transport)
    o = a.call({"model": "claude-haiku-5-5", "max_tokens": 8, "messages": [{"role": "user", "content": "hi"}]}).as_json()
    return {"seen": seen, "outcome": o, "repr": repr(a)}
step("call", go)
step("nokey", lambda: A.AnthropicAdapter(env={}, transport=transport))
step("emptykey", lambda: A.AnthropicAdapter(env={"ANTHROPIC_API_KEY": ""}, transport=transport))
''')
k, kerr = run_py(code2)
v = value(k, "call") or {}
seen = v.get("seen") or {}; hdr = {str(h).lower(): val for h, val in (seen.get("headers") or {}).items()}
probe("AnthropicAdapter.call: POST to https://api.anthropic.com/v1/messages with x-api-key, anthropic-version 2023-06-01 and a JSON content-type",
      seen.get("method") == "POST" and str(seen.get("url", "")).startswith("https://api.anthropic.com/v1/messages") and hdr.get("x-api-key") == SECRET
      and hdr.get("anthropic-version") == "2023-06-01" and str(hdr.get("content-type", "")).startswith("application/json"))
probe("…and the 401 comes back as request-refused with the key nowhere in the outcome, the adapter's repr or stderr",
      refused_with(v.get("outcome") or {}, "authentication_error") and SECRET not in json.dumps(v.get("outcome")) and SECRET not in str(v.get("repr")) and SECRET not in kerr)
probe("construction without ANTHROPIC_API_KEY (absent, or empty) refuses, naming the variable",
      "nokey" in k and not okv(k, "nokey") and not okv(k, "emptykey") and "ANTHROPIC_API_KEY" in k.get("nokey", {}).get("error", "")
      and SECRET not in k.get("nokey", {}).get("error", ""))

# --- hygiene ---
hits = []
for pth in (TREE / "twine").rglob("*.py"):
    if re.search(r"^\s*(import|from)\s+anthropic(\s|$|\.)", pth.read_text(encoding="utf-8"), re.M): hits.append(str(pth.relative_to(TREE)))
probe("no module under twine/ imports the anthropic SDK" + (f" ({', '.join(hits)})" if hits else ""), not hits)
fold = lambda s: re.sub(r"\s+", " ", re.sub(r"(?m)^\s*#\s?", "", s))  # comment prefixes stripped: the sentences span comment lines
probe("twine/spend.py no longer says a provider recording does not exist",
      "none exists yet (the gated probe" not in fold((TREE / "twine/spend.py").read_text(encoding="utf-8")))
probe("tests/helpers.py no longer says no provider usage has ever been recorded",
      "No provider usage has ever been recorded" not in fold((TREE / "tests/helpers.py").read_text(encoding="utf-8")))
ver = (TREE / "VERSION").read_text(encoding="utf-8").strip()
try: tup = tuple(int(x) for x in ver.split("."))
except ValueError: tup = ()
probe(f"VERSION ({ver}) is at least 0.17.0", len(tup) == 3 and tup >= (0, 17, 0))
probe("no __pycache__ in the tree", not any(".checkpoint-r2" not in str(q) for q in TREE.rglob("__pycache__")))

# --- controls ---
for n, _, _, nb, rs_ in ROWS:
    if n in CARRY and (hashlib.sha256(rec(n)).hexdigest() != rs_ or len(rec(n)) != nb): broken(f"the carried recording {n} does not hash as the rows say")
if not re.fullmatch(r"[0-9a-f]{64}", PASTE_SHA) or len(ROWS) != 15 or len(CARRY) != 10: broken("the pins are malformed")
if not stopped({"stop": "end-turn"}, "end-turn") or stopped({"stop": "end-turn"}, None) or not stopped({"stop": None}, None) or stopped({}, None): broken("stopped is wrong")
if (not refused_with({"stop": "request-refused", "reason": "x authentication_error y", "usage": None}, "authentication_error")
        or refused_with({"stop": "request-refused", "reason": "x", "usage": None}, "authentication_error")
        or refused_with({"stop": "rate-limited", "reason": "authentication_error", "usage": None}, "authentication_error")
        or refused_with({"stop": "request-refused", "reason": "authentication_error", "usage": {"input": 1}}, "authentication_error")): broken("refused_with is wrong")
if not tokens({"usage": {"input": 1}}, {"input": 1}) or tokens({"usage": {"input": 2}}, {"input": 1}): broken("tokens is wrong")
if implements({"implements": ["a"]}) != {"a"} or implements({"capabilities": ["b"]}) != {"b"} or implements({}) != set(): broken("implements is wrong")
ctl, _ = run_py("step('x', lambda: 1)\nstep('y', lambda: 1/0)\n")
if not (okv(ctl, "x") and value(ctl, "x") == 1 and not okv(ctl, "y") and "ZeroDivisionError" in ctl["y"]["error"]): broken("run_py is wrong")
if fold("a  b\nc") != "a b c" or fold("# No provider usage has ever been\n# recorded") != "No provider usage has ever been recorded": broken("fold is wrong")
if rec("text")[:9] != b'{"model":' or b"event: message_start" not in rec("text_stream"): broken("the carried recordings are not the recordings")

print(f"[checkpoint] {len(failures)} failing probe(s)")
sys.exit(1 if failures else 0)
PY

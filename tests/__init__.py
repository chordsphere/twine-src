"""twine's test suite — stdlib unittest, run from the repo root with

    python3 -B -m unittest discover -s tests -t .

Hermetic by rule (twine-seed.md T8, and this session's brief): no
network, no bale install, no third-party module. `twine bale check` is
tested against temp roots the tests build — bin/VERSION at the pin, at
another version, and absent — never against a real install, and every
CLI subprocess runs with TWINE_BALE_ROOT pinned to a temp directory so
a bale on the developer's PATH can never leak into a verdict.

Layout (CODE.md §13): one file per subject —
  helpers.py                 the subprocess and temp-root helpers
  test_registry.py           the registry, and parser/registry parity
  test_json_discipline.py    the one-JSON-line contract on every verb
  test_bale_check.py         root resolution and the pin check
  test_status.py             `twine status`
  test_consumption_manifest.py  share/bale-consumption.toml as data
  test_fixtures.py           fixtures/ parse, and fixtures/README.md
  test_entrypoint.py         bin/twine under python3 -I -S; T9 and T10
  test_take.py               `twine take` and twine.shapes: the fixtures as
                             positives, negatives derived from their bytes
"""

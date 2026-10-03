"""twine's test suite — stdlib unittest, run from the repo root with

    python3 -B -m unittest discover -s tests -t .

Hermetic by rule (twine-seed.md T8, and this session's brief): no
network, no bale install, no third-party module. `twine bale check` is
tested against temp roots the tests build — bin/VERSION at the pin, at
another version, and absent — never against a real install, and every
CLI subprocess runs with TWINE_BALE_ROOT pinned to a temp directory so
a bale on the developer's PATH can never leak into a verdict. The two
verbs that run bale (`carry exchange`, `carry response`; session 2b-ii)
reach it only through the run seam: the fixture player, a run-seam
double, or a stub `bin/bale` the tests write into a temp root — each a
double named as one, never a bale.

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
  test_process.py            the run seam (Context.run) and its default runner
  test_carry.py              `twine carry probe`
  test_carry_bale.py         `twine carry exchange` and `twine carry response`
  test_transitions.py        `twine transitions` and the transition table
  test_spend.py              the cost spine: the usage record, the stream,
                             prices, totals, the pre-call check, `twine spend`
"""

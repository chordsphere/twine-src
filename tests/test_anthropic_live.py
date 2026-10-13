"""The one live smoke test of the Anthropic adapter (Arc 2 R2) — gated.

It runs only when the environment says both `TWINE_LIVE_SMOKE=1` and
`ANTHROPIC_API_KEY` is set; otherwise every test here is skipped, saying
which gate is closed. It never runs under bale: `bale apply` validates with
the network off (bale.toml leaves `[sandbox] network` unset), and T8 holds
twine's suite to never reaching a model API — this file is the architect's
to run by hand, from the repository root:

    TWINE_LIVE_SMOKE=1 ANTHROPIC_API_KEY=… python3 -B -m unittest discover -s tests -t . -p test_anthropic_live.py -v

It makes the `text` recording's call — `claude-haiku-5-5`, max_tokens 32,
one user turn asking for the word "twine" — twice through the real
transport (twine/runtime/transport.py, the only place twine opens a
socket): non-streamed and streamed, each through the boundary. Two calls,
a few dozen tokens. The key is handed to the adapter in the environment
mapping it is given, read here from the process environment and nowhere
else; nothing here prints, logs or stores it.
"""

from __future__ import annotations

import os
import unittest

from twine.runtime.adapters.anthropic import KEY_VARIABLE, AnthropicAdapter
from twine.runtime.boundary import Boundary, Request
from twine.spend import Tokens

GATE = "TWINE_LIVE_SMOKE"
MODEL = "claude-haiku-5-5"
SYSTEM = "You are a worker in a test harness. Answer tersely."
ASK = "Reply with the single word: twine"


def closed_gate() -> str | None:
    """Why the smoke test does not run, or None when both gates are open."""
    if os.environ.get(GATE) != "1":
        return f"{GATE} is not 1: the live smoke test is run by hand (T8)"
    if not os.environ.get(KEY_VARIABLE, "").strip():
        return f"{KEY_VARIABLE} is not set: the live smoke test needs the architect's key"
    return None


@unittest.skipIf(closed_gate() is not None, closed_gate() or "")
class LiveSmoke(unittest.TestCase):

    def call(self, *, stream: bool):
        env = {KEY_VARIABLE: os.environ[KEY_VARIABLE]}
        boundary = Boundary(AnthropicAdapter(env=env, model=MODEL, max_tokens=32,
                                             system=SYSTEM, thinking=None, stream=stream,
                                             timeout=60.0))
        return boundary.call(Request(({"role": "user", "content": ASK},)))

    def check(self, turn) -> None:
        self.assertEqual(turn.stop, "end-turn", turn.reason)
        self.assertIn("twine", turn.text.lower())
        self.assertIsInstance(turn.usage, Tokens)
        self.assertGreater(turn.usage.input, 0)
        self.assertGreater(turn.usage.output, 0)
        self.assertTrue(turn.request_id)
        self.assertEqual(turn.provider_stop, "end_turn")

    def test_text_not_streamed(self):
        self.check(self.call(stream=False))

    def test_text_streamed(self):
        self.check(self.call(stream=True))


if __name__ == "__main__":
    unittest.main()

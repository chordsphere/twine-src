"""twine's runtime — the face that hosts a session (twine-seed.md §4, T4).

Arc 2 builds it; R1 (session `2026-10-12-twine-runtime-registry-007`)
landed its two foundations, R2 (`2026-10-13-twine-runtime-anthropic-002`)
the Anthropic adapter, and R3–R4 fill it in:

  contract     the Contract a capability declares (TQ-2, ratified): its
               purpose, what an implementing adapter must do, what the
               runtime promises, where it lands and on what grounds
  capabilities.toml  the declaration: one [[capability]] per runtime
               capability — name, module, status, summary — so a parity
               test has something to walk (T7, §4.1)
  capabilities the capability modules, one per file, each exposing
               CONTRACT; `usage_accounting` also exports from_anthropic,
               the first provider usage mapping; reached only through the
               registry
  registry     loads the declaration, checks parity by name against the
               capabilities directory, loads each module's contract and
               every registered adapter, and reports every fault by name;
               `twine runtime list` and `twine runtime show` render it
  terms        the shapes the boundary, the adapters and the loop share —
               ToolSpec, ToolCall, the tool protocols, ThinkingSettings, the
               token check; not a capability module, because nothing
               outside capabilities/ may import one (the registry must be
               able to report one missing while every verb still loads)
  usage        the provider usage mappings' code (from_anthropic), moved
               out of the usage-accounting module at R2 for the same reason
               — the adapter calls it; that module re-exports it
  boundary     the adapter boundary (Q-3, ratified): the Adapter interface
               a model adapter implements, the Turn it answers with, and
               the Boundary that holds every turn to the contract — the
               stop set read from share/transitions.toml's `stop` axis
               (twine.transitions.stop_keys), usage as twine.spend.Tokens,
               model and thinking fixed at spawn (D12)
  adapters     the registered adapters, discovered by listing the package:
               `fake`, the scripted transport the tests drive (T8) and
               nothing else does, and since R2 `anthropic`, the Messages API
               (the key from the environment it is given, the stop and error
               words mapped through the table's [[mapping]] rows)
  transport    the transport seam an adapter is handed, and the real one —
               https_transport, the only place twine opens a socket

The contract for all of it is claude/context/runtime-contract.md.

Nothing under this package reaches a network except through transport.py,
nothing reads the process environment (the Anthropic adapter reads its key
from the mapping it is given), and nothing imports outside the standard
library and twine (T8, T9) — no provider SDK; a test walks the imports.
"""

from __future__ import annotations

from pathlib import Path

# The runtime's own files, located from this file — never from the
# working directory.
RUNTIME_DIR = Path(__file__).resolve().parent
CAPABILITIES_DECLARATION = RUNTIME_DIR / "capabilities.toml"
CAPABILITIES_DIR = RUNTIME_DIR / "capabilities"
CAPABILITIES_PACKAGE = "twine.runtime.capabilities"
ADAPTERS_DIR = RUNTIME_DIR / "adapters"
ADAPTERS_PACKAGE = "twine.runtime.adapters"

"""The runtime's capability modules — one per capability (T7, §4.1, TQ-2).

Each module here is listed by twine/runtime/capabilities.toml under its
dotted name and exposes a module-level `CONTRACT` (twine.runtime.contract.
Contract) naming the capability it is the contract for. A module the
declaration does not list, or a listed module that is absent, is a fault
`twine runtime list` names and tests/test_runtime.py fails on: there is no
list to edit but the declaration, and the declaration is checked against
this directory.

A capability module carries its contract; `usage_accounting` also carries
the provider usage mappings (`from_anthropic`). Nothing outside this
directory imports a capability module, and no capability module imports
another: the registry alone reaches them, by its guarded import, so a
missing one is a named `missing-module` problem rather than an import
failure that stops every verb from loading. The shapes the boundary and
the adapters share — the tool call, the thinking settings, the token
check — are in twine.runtime.terms.

Nothing here reaches a network or reads a key; stdlib and twine only.
"""

"""The registered model adapters — one module per adapter (or family).

Each module here exposes an `ADAPTERS` tuple of twine.runtime.boundary.
Adapter subclasses; twine.runtime.registry discovers the modules by
listing this package (sorted), as twine.registry discovers the verb
modules, so a new adapter is a new module and no shared list is edited.
Each adapter declares the capabilities it implements (`implements`); the
registry derives every capability's `adapters` from those sets.

At Arc 2 R1 the one adapter is `fake` (fake.py), the scripted transport
twine's tests drive (T8) and nothing else does. R2 adds `anthropic`, R6
the OpenAI-compatible adapter.
"""

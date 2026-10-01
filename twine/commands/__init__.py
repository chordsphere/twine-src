"""twine's verb modules, one per verb family.

Each module here exposes a `COMMANDS` tuple of twine.registry.Command
and nothing else the registry needs; twine.registry.load_registry()
discovers every module in this package by listing it (sorted) and
refuses a duplicate verb name. A new verb family is a new module — no
list to edit, which is what lets file-disjoint sessions add verbs
beside each other.

Handlers take (Context, Namespace) and return a Result (twine.registry);
they write informational text to ctx.stderr only and never print to
stdout — the dispatcher owns stdout and the --json discipline.
"""

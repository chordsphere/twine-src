"""The contract object a runtime capability declares (TQ-2, proposed at
Arc 2 R1; claude/context/runtime-contract.md §2).

Every module under twine/runtime/capabilities/ exposes one module-level
`CONTRACT`, a Contract naming the capability it is the contract for. The
declaration (twine/runtime/capabilities.toml) says which capabilities
exist and their status; the module says what each one means. The registry
holds the two to each other by name: a module whose CONTRACT names another
capability than the declaration entry that points at it is a fault.

A contract is data, not prose in a docstring, so `twine runtime show`
renders it, a test can check it is whole, and R2–R5 implement a
declaration rather than invent one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# A capability name: lowercase words joined by single hyphens.
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


class ContractError(ValueError):
    """A Contract that is not whole; the message names every fault."""


@dataclass(frozen=True)
class Contract:
    """One capability's declared contract.

    capability        the capability's name, as the declaration spells it
    purpose           what the capability is, one paragraph
    adapter_must      what an adapter that implements it must do — one
                      obligation per entry
    runtime_promises  what the runtime (the boundary, the loop) promises in
                      return — one promise per entry
    lands             which Arc 2 session implements it, and what exists now
    grounds           the seed entries the contract is derived from
    """

    capability: str
    purpose: str
    adapter_must: tuple[str, ...]
    runtime_promises: tuple[str, ...]
    lands: str
    grounds: tuple[str, ...]

    def faults(self) -> list[str]:
        """Every reason this contract is not whole; [] when it is."""
        found: list[str] = []
        if not isinstance(self.capability, str) or not NAME_PATTERN.match(self.capability):
            found.append(f"capability {self.capability!r} is not a lowercase "
                         "hyphenated name")
        for field_name in ("purpose", "lands"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                found.append(f"{field_name} is empty")
        for field_name in ("adapter_must", "runtime_promises", "grounds"):
            value = getattr(self, field_name)
            if not isinstance(value, tuple) or not value:
                found.append(f"{field_name} must be a non-empty tuple")
            elif not all(isinstance(v, str) and v.strip() for v in value):
                found.append(f"{field_name} holds an empty or non-string entry")
        return found

    def check(self) -> "Contract":
        """Self, or ContractError naming every fault."""
        found = self.faults()
        if found:
            raise ContractError(f"contract for {self.capability!r}: " + "; ".join(found))
        return self

    def as_json(self) -> dict[str, Any]:
        """The contract as `twine runtime show --json` renders it."""
        return {"purpose": self.purpose,
                "adapter_must": list(self.adapter_must),
                "runtime_promises": list(self.runtime_promises),
                "lands": self.lands,
                "grounds": list(self.grounds)}

    def as_lines(self) -> list[str]:
        """The same facts as readable lines."""
        lines = [f"purpose: {self.purpose}", "an adapter that implements it must:"]
        lines += [f"  - {item}" for item in self.adapter_must]
        lines.append("the runtime promises:")
        lines += [f"  - {item}" for item in self.runtime_promises]
        lines.append(f"lands: {self.lands}")
        lines.append(f"grounds: {'; '.join(self.grounds)}")
        return lines

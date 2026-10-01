"""The bale surface twine reads (twine-seed.md D2, D3, D4; T10).

Twine never imports bale. What it reads from an install is files bale
leaves on disk and the stdout of bale's non-interactive verbs; this
session reads one file, `<root>/bin/VERSION`, and compares it to the
pin in the consumption manifest (`share/bale-consumption.toml`).

Sections:
  1. Install-root resolution     (~line 30)
  2. The installed version       (~line 95)
  3. The consumption manifest    (~line 120)
  4. The pin check               (~line 175)
"""

from __future__ import annotations

import logging
import os
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from twine import CONSUMPTION_MANIFEST

log = logging.getLogger("twine.bale")

ENV_ROOT = "TWINE_BALE_ROOT"
VERSION_RELPATH = Path("bin") / "VERSION"

# ---------------------------------------------------------------------------
# 1. Install-root resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Root:
    """Where the bale install root was found, or that it was not.

    `path` is None when nothing resolved; `source` names which rule
    produced it ("--bale-root", "TWINE_BALE_ROOT", "PATH") or is None.
    """

    path: Path | None
    source: str | None
    detail: str

    @property
    def found(self) -> bool:
        return self.path is not None


def resolve_root(explicit: str | None = None,
                 env: Mapping[str, str] | None = None,
                 which: Callable[[str], str | None] = shutil.which) -> Root:
    """Resolve the install root, first rule that answers wins (D2):

    1. `--bale-root DIR` (the explicit argument);
    2. the environment variable TWINE_BALE_ROOT;
    3. `command -v bale`, followed to its real path and up to the
       directory holding bin/ (`~/.local/bin/bale` -> `~/bale/bin/bale`
       -> `~/bale` on the architect's machine).

    `env` and `which` are injectable so tests never touch the real
    environment or a real install.
    """
    env = os.environ if env is None else env
    if explicit:
        path = Path(explicit).expanduser()
        log.info("bale root from --bale-root: %s", path)
        return Root(path, "--bale-root", f"--bale-root {explicit}")
    from_env = env.get(ENV_ROOT)
    if from_env:
        path = Path(from_env).expanduser()
        log.info("bale root from %s: %s", ENV_ROOT, path)
        return Root(path, ENV_ROOT, f"{ENV_ROOT}={from_env}")
    exe = which("bale")
    if not exe:
        log.info("no bale on PATH, no %s, no --bale-root", ENV_ROOT)
        return Root(None, None,
                    f"no --bale-root, no {ENV_ROOT}, and no bale on PATH")
    real = Path(os.path.realpath(exe))
    path = real.parent.parent
    log.info("bale root from PATH: %s -> %s -> %s", exe, real, path)
    return Root(path, "PATH", f"command -v bale -> {real}")


# ---------------------------------------------------------------------------
# 2. The installed version
# ---------------------------------------------------------------------------


def read_installed_version(root: Path) -> tuple[str | None, str]:
    """`<root>/bin/VERSION` stripped, or None with the reason it was not
    readable. Never raises: an unreadable install is a reported fact."""
    path = root / VERSION_RELPATH
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        log.info("cannot read %s: %s", path, exc.strerror or exc)
        return None, f"{path} unreadable: {exc.strerror or exc}"
    version = text.strip()
    if not version:
        return None, f"{path} is empty"
    return version, f"{path} reads {version}"


# ---------------------------------------------------------------------------
# 3. The consumption manifest
# ---------------------------------------------------------------------------


class ManifestError(Exception):
    """share/bale-consumption.toml is missing, unparseable, or malformed."""


@dataclass(frozen=True)
class Manifest:
    """The parsed consumption manifest (D4): the pin, the installed
    schema hashes, and the surfaces twine reads, as data a test can
    walk. `data` is the whole TOML document."""

    path: Path
    pin: str
    schemas: dict[str, str]
    surfaces: list[dict[str, Any]]
    data: dict[str, Any]


def load_manifest(path: Path = CONSUMPTION_MANIFEST) -> Manifest:
    """Parse the manifest with tomllib and check the shape twine relies
    on. Raises ManifestError with the reason; callers report, never
    swallow."""
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except OSError as exc:
        raise ManifestError(f"{path}: {exc.strerror or exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"{path}: not valid TOML: {exc}") from exc
    bale = data.get("bale")
    if not isinstance(bale, dict):
        raise ManifestError(f"{path}: no [bale] table")
    pin = bale.get("pin")
    if not isinstance(pin, str) or not pin.strip():
        raise ManifestError(f"{path}: [bale] pin must be a non-empty string")
    schemas = bale.get("schemas")
    if not isinstance(schemas, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in schemas.items()):
        raise ManifestError(f"{path}: [bale.schemas] must map file names to sha256 strings")
    surfaces = data.get("surface", [])
    if not isinstance(surfaces, list) or not all(isinstance(s, dict) for s in surfaces):
        raise ManifestError(f"{path}: [[surface]] must be an array of tables")
    log.debug("manifest %s: pin %s, %d schemas, %d surfaces",
              path, pin, len(schemas), len(surfaces))
    return Manifest(path, pin.strip(), dict(schemas), list(surfaces), data)


# ---------------------------------------------------------------------------
# 4. The pin check
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckResult:
    """`twine bale check`'s facts: the pin, what is installed (None when
    unreadable), where, and whether they agree."""

    pin: str
    installed: str | None
    root: Path | None
    source: str | None
    ok: bool
    reason: str

    def as_json(self) -> dict[str, Any]:
        return {"pin": self.pin, "installed": self.installed,
                "root": None if self.root is None else str(self.root),
                "source": self.source, "ok": self.ok, "reason": self.reason}

    def as_lines(self) -> list[str]:
        where = "no install found" if self.root is None else str(self.root)
        return [f"pin:       {self.pin}",
                f"installed: {self.installed if self.installed else '(unreadable)'}",
                f"root:      {where}" + (f"  (from {self.source})" if self.source else ""),
                f"check:     {'ok' if self.ok else 'FAIL'} — {self.reason}"]


def check(manifest: Manifest, root: Root) -> CheckResult:
    """Compare the installed bin/VERSION to the manifest's pin (D2).

    ok only when an install was found, its VERSION read, and the two
    strings are equal. Every other outcome is reported, with the reason,
    and never raises — a wrong or absent install is a check result, not
    an internal error.
    """
    if root.path is None:
        return CheckResult(manifest.pin, None, None, None, False,
                           f"no bale install found ({root.detail})")
    installed, detail = read_installed_version(root.path)
    if installed is None:
        return CheckResult(manifest.pin, None, root.path, root.source, False,
                           detail)
    if installed != manifest.pin:
        return CheckResult(manifest.pin, installed, root.path, root.source, False,
                           f"installed {installed} differs from pin {manifest.pin}")
    return CheckResult(manifest.pin, installed, root.path, root.source, True,
                       f"installed {installed} matches the pin")

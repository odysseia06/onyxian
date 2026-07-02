"""Locate the module library and profiles that ship with the engine.

Three sources, in priority order, so the same engine works whether it was
``pipx install onyxian``-ed or run from a clone:

1. ``ONYXIAN_HOME`` — an explicit checkout/library root: a dev override and escape
   hatch. Must contain a ``modules/`` directory.
2. Installed package data — ``onyxian/_library/`` inside the wheel, the normal path
   for an installed package. Populated at build time by the hatchling
   ``force-include`` in pyproject.toml.
3. The source checkout — the repo root two levels above this package, per the
   §4.2 layout, for ``pip install -e .`` and running from a clone (here the
   wheel's ``_library`` is absent, so this branch carries dev and CI).
"""

from __future__ import annotations

import os
from pathlib import Path

from .errors import OnyxianError
from .manifests import load_manifest
from .model import Manifest

_PACKAGE_LIBRARY = Path(__file__).resolve().parent / "_library"
_CHECKOUT_ROOT = Path(__file__).resolve().parents[2]


def _onyxian_home() -> Path | None:
    env = os.environ.get("ONYXIAN_HOME")
    if not env:
        return None
    root = Path(env)
    if not (root / "modules").is_dir():
        raise OnyxianError(f"ONYXIAN_HOME={env} has no modules/ directory")
    return root


def default_modules_root() -> Path:
    """The bundled module library: ONYXIAN_HOME, else installed package data, else the checkout."""
    home = _onyxian_home()
    if home is not None:
        return home / "modules"
    if (_PACKAGE_LIBRARY / "modules").is_dir():
        return _PACKAGE_LIBRARY / "modules"
    if (_CHECKOUT_ROOT / "modules").is_dir():
        return _CHECKOUT_ROOT / "modules"
    raise OnyxianError(
        "cannot locate the Onyxian module library; install the onyxian package, "
        "run from a checkout, or set ONYXIAN_HOME to a checkout root"
    )


def bundled_profiles_root() -> Path | None:
    """Where shipped profiles live (so `--answers <name>` resolves a bundled profile), or None."""
    for base in (_onyxian_home(), _PACKAGE_LIBRARY, _CHECKOUT_ROOT):
        if base is not None and (base / "profiles").is_dir():
            return base / "profiles"
    return None


def discover_modules(modules_root: Path, vault_root: Path | None = None) -> dict[str, Manifest]:
    """Load every bundled module, plus a vault's externally-installed ones (M4).

    External modules live under ``<vault>/.vault/modules/<id>/`` — engine-owned
    state, installed by `add <git-url|path>` behind the trust warning (§12).
    An external module may not shadow a bundled id.
    """
    if not modules_root.is_dir():
        raise OnyxianError(f"module library not found at {modules_root}")
    library: dict[str, Manifest] = {}
    for entry in sorted(modules_root.iterdir(), key=lambda p: p.name):
        if entry.is_dir() and (entry / "module.yaml").is_file():
            manifest = load_manifest(entry)
            library[manifest.name] = manifest
    if not library:
        raise OnyxianError(f"module library at {modules_root} contains no modules")
    if vault_root is not None:
        external_root = vault_root / ".vault" / "modules"
        if external_root.is_dir():
            for entry in sorted(external_root.iterdir(), key=lambda p: p.name):
                if entry.is_dir() and (entry / "module.yaml").is_file():
                    manifest = load_manifest(entry)
                    if manifest.name in library:
                        raise OnyxianError(
                            f"external module {manifest.name!r} (at {entry}) shadows a bundled module; "
                            "remove it or rename it upstream"
                        )
                    library[manifest.name] = manifest
    return library

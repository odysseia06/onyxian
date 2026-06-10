"""Locate the module library that ships with the engine.

In a checkout (including an editable install) the library is the ``modules/``
directory two levels above this package, per the repository layout in
KICKSTART.md §4.2. ``ONYX_HOME`` overrides the repo root for installs where the
package does not sit inside a checkout; first-class wheel distribution of the
library is an M1+ concern and is deliberately not solved here.
"""

from __future__ import annotations

import os
from pathlib import Path

from .errors import OnyxError
from .manifests import load_manifest
from .model import Manifest


def find_repo_root() -> Path:
    env = os.environ.get("ONYX_HOME")
    if env:
        root = Path(env)
        if not (root / "modules").is_dir():
            raise OnyxError(f"ONYX_HOME={env} has no modules/ directory")
        return root
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "modules").is_dir():
        return candidate
    raise OnyxError(
        "cannot locate the Onyx module library; run from a checkout or set ONYX_HOME"
    )


def default_modules_root() -> Path:
    return find_repo_root() / "modules"


def discover_modules(modules_root: Path, vault_root: Path | None = None) -> dict[str, Manifest]:
    """Load every bundled module, plus a vault's externally-installed ones (M4).

    External modules live under ``<vault>/.vault/modules/<id>/`` — engine-owned
    state, installed by `add <git-url|path>` behind the trust warning (§12).
    An external module may not shadow a bundled id.
    """
    if not modules_root.is_dir():
        raise OnyxError(f"module library not found at {modules_root}")
    library: dict[str, Manifest] = {}
    for entry in sorted(modules_root.iterdir(), key=lambda p: p.name):
        if entry.is_dir() and (entry / "module.yaml").is_file():
            manifest = load_manifest(entry)
            library[manifest.name] = manifest
    if not library:
        raise OnyxError(f"module library at {modules_root} contains no modules")
    if vault_root is not None:
        external_root = vault_root / ".vault" / "modules"
        if external_root.is_dir():
            for entry in sorted(external_root.iterdir(), key=lambda p: p.name):
                if entry.is_dir() and (entry / "module.yaml").is_file():
                    manifest = load_manifest(entry)
                    if manifest.name in library:
                        raise OnyxError(
                            f"external module {manifest.name!r} (at {entry}) shadows a bundled module; "
                            "remove it or rename it upstream"
                        )
                    library[manifest.name] = manifest
    return library

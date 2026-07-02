"""External modules (KICKSTART.md §12, M4): fetched from a git URL or local path.

A module is data, but a malicious template is still a social-engineering
surface — and skills and agent definitions are *instructions your agents will
follow*. So external installs are gated behind an explicit trust warning, the
content is copied vault-locally under ``.vault/modules/<id>/`` (engine-owned
state, reviewable before and after), and git sources are pinned to the commit
that was reviewed. ``update`` advances the pin; ``remove`` deletes the copy.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from .errors import OnyxianError
from .fsio import read_text
from .manifests import load_manifest
from .model import Manifest
from .sources import _git

EXTERNAL_REL = ".vault/modules"


def looks_external(spec: str) -> bool:
    if "://" in spec or spec.startswith("git@"):
        return True
    path = Path(spec)
    return path.is_dir() and (path / "module.yaml").is_file()


def _peek_name(module_yaml: Path) -> str:
    try:
        data = yaml.safe_load(read_text(module_yaml))
    except Exception as exc:  # noqa: BLE001
        raise OnyxianError(f"cannot parse {module_yaml}: {exc}") from None
    name = (data or {}).get("name")
    if not isinstance(name, str) or not name:
        raise OnyxianError(f"{module_yaml} has no usable 'name'")
    return name


def fetch_external(spec: str, scratch: Path) -> tuple[Manifest, str, str | None]:
    """Fetch a module from a git URL / local repo / plain directory into scratch.

    Returns (validated manifest rooted in scratch, repo spec for the config,
    pin sha or None for unversioned directory sources).
    """
    if "://" in spec or spec.startswith("git@") or (Path(spec) / ".git").exists():
        checkout = scratch / "checkout"
        _git(["clone", "--quiet", "--depth", "1", spec, str(checkout)])
        pin = _git(["rev-parse", "HEAD"], cwd=checkout)
        module_yaml = checkout / "module.yaml"
        if not module_yaml.is_file():
            raise OnyxianError(f"{spec} has no module.yaml at its root; not an Onyxian module repository")
        name = _peek_name(module_yaml)
        staged = scratch / name
        shutil.copytree(checkout, staged, ignore=shutil.ignore_patterns(".git"))
        return load_manifest(staged), spec, pin
    source_dir = Path(spec)
    if (source_dir / "module.yaml").is_file():
        name = _peek_name(source_dir / "module.yaml")
        staged = scratch / name
        shutil.copytree(source_dir, staged, ignore=shutil.ignore_patterns(".git"))
        return load_manifest(staged), str(source_dir.resolve()), None
    raise OnyxianError(f"{spec!r} is neither an installed module id, a git URL, nor a module directory")


def install_external(vault_root: Path, manifest: Manifest) -> Path:
    """Place the staged module under `.vault/modules/<id>/` (replacing any prior copy)."""
    target = vault_root / ".vault" / "modules" / manifest.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(manifest.directory, target)
    return target


def trust_warning(manifest: Manifest, repo: str, pin: str | None) -> str:
    counts = (
        f"{len(manifest.folders)} folder(s), {len(manifest.templates)} template(s), "
        f"{len(manifest.bases)} base view(s), {len(manifest.seeds)} seed(s), "
        f"{len(manifest.skills)} skill(s), {len(manifest.agents)} agent(s)"
    )
    lines = [
        "=" * 72,
        f"TRUST WARNING — external module {manifest.name!r} v{manifest.version}",
        f"  from: {repo}" + (f" @ {pin[:12]}" if pin else " (unpinned directory source)"),
        f"  provides: {counts}",
        "",
        f"  {' '.join(manifest.summary.split())}",
        "",
        "  A module is data-only — the engine never executes anything in it. But:",
        "  - templates and seeds become notes you will read and trust,",
        "  - skills and agent definitions are INSTRUCTIONS YOUR AGENTS WILL FOLLOW.",
        "  Review the content before trusting it. After install it sits at",
        f"  .vault/modules/{manifest.name}/ for inspection; this exact commit is pinned.",
    ]
    if manifest.skills or manifest.agents:
        surface = [s.id for s in manifest.skills] + [a.name for a in manifest.agents]
        lines.append(f"  agent surface shipped: {', '.join(surface)}")
    lines.append("=" * 72)
    return "\n".join(lines)

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

from .errors import OnyxianError, VaultStateError
from .fsio import read_text, sha256_tree
from .manifests import load_manifest
from .model import Config, Lock, Manifest
from .sources import _git, _reject_symlinks

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
            raise OnyxianError(
                f"{spec} has no module.yaml at its root; not an Onyxian module repository"
            )
        name = _peek_name(module_yaml)
        _reject_symlinks(checkout)
        staged = scratch / name
        shutil.copytree(checkout, staged, ignore=shutil.ignore_patterns(".git"))
        return load_manifest(staged), spec, pin
    source_dir = Path(spec)
    if (source_dir / "module.yaml").is_file():
        name = _peek_name(source_dir / "module.yaml")
        _reject_symlinks(source_dir)
        staged = scratch / name
        shutil.copytree(source_dir, staged, ignore=shutil.ignore_patterns(".git"))
        return load_manifest(staged), str(source_dir.resolve()), None
    raise OnyxianError(
        f"{spec!r} is neither an installed module id, a git URL, nor a module directory"
    )


def install_external(vault_root: Path, manifest: Manifest) -> Path:
    """Place the staged module under `.vault/modules/<id>/` (replacing any prior copy)."""
    target = vault_root / ".vault" / "modules" / manifest.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(manifest.directory, target)
    return target


def _module_copy(vault_root: Path, mod_id: str) -> Path:
    return vault_root / ".vault" / "modules" / mod_id


def record_module_trust(vault_root: Path, lock: Lock, mod_id: str) -> None:
    """Baseline the reviewed copy of ``mod_id`` at trust time (#48). The caller saves the lock.

    ``plan``/``apply`` render from ``.vault/modules/<id>/``, so this hash is what later
    runs check the copy against — a mismatch means it was changed out of band since it
    was trusted.
    """
    lock.module_trust[mod_id] = sha256_tree(_module_copy(vault_root, mod_id))


def verify_module_trust(
    vault_root: Path, config: Config, lock: Lock
) -> tuple[list[str], list[str]]:
    """``(tampered, unverified)`` externally-sourced module ids (#48).

    ``tampered``: a baseline was recorded and the copy on disk no longer matches it.
    ``unverified``: the module is externally sourced but predates baselines (installed
    before #48), so there is no recorded hash to check — re-trusting records one.
    """
    tampered: list[str] = []
    unverified: list[str] = []
    for mod_id, mc in config.modules.items():
        if mc.source is None:
            continue
        baseline = lock.module_trust.get(mod_id)
        copy = _module_copy(vault_root, mod_id)
        if baseline is None:
            unverified.append(mod_id)
        elif not copy.is_dir() or sha256_tree(copy) != baseline:
            tampered.append(mod_id)
    return sorted(tampered), sorted(unverified)


def assert_module_trust(vault_root: Path, config: Config, lock: Lock) -> None:
    """Fail closed if any external module's reviewed copy was tampered with (#48)."""
    tampered, _ = verify_module_trust(vault_root, config, lock)
    if tampered:
        raise VaultStateError(
            "the reviewed copy of external module(s) "
            + ", ".join(repr(m) for m in tampered)
            + f" under {EXTERNAL_REL}/ changed since you trusted it; the engine renders "
            "plan/apply from that copy, so it will not proceed. Re-review with "
            "`onyxian update <id>` (or `onyxian remove <id>` then `onyxian add <repo>`), "
            "or restore the copy from version control if the change was accidental."
        )


def changed_instruction_files(installed: Path, staged: Path) -> list[str]:
    """Module-relative skill/agent paths whose bytes differ between the installed
    copy and a freshly fetched one (present on only one side counts). These files
    are instructions the vault's agents will follow, so `update` re-gates trust on
    them (issue #32); templates and seeds already change under the never-clobber
    rules and are reviewable in the plan."""
    changed: list[str] = []
    for sub in ("skills", "agents"):
        old_root, new_root = installed / sub, staged / sub
        rels: set[str] = set()
        for root in (old_root, new_root):
            if root.is_dir():
                rels.update(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        for rel in rels:
            old, new = old_root / rel, new_root / rel
            if not (old.is_file() and new.is_file() and old.read_bytes() == new.read_bytes()):
                changed.append(f"{sub}/{rel}")
    return sorted(changed)


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

"""Shared test plumbing.

Two ways to drive the engine in tests:

- through the real CLI in-process (``run_cli``) against the real module
  library that ships in this repository — the e2e-ish path;
- through the API against a synthetic module library built per-test
  (``synth_library``) — the path for exercising planner/render edge cases
  without coupling tests to real module content.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from onyxian.configio import parse_config
from onyxian.fsio import sha256_file
from onyxian.intent import build_desired_state
from onyxian.lockio import load_lock
from onyxian.manifests import load_manifest
from onyxian.model import Config, Manifest
from onyxian.planner import Plan, build_plan
from onyxian.repo import discover_modules
from onyxian.resolve import resolve_modules

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_MODULES = REPO_ROOT / "modules"
ANSWERS_DIR = Path(__file__).resolve().parent / "fixtures" / "answers"
GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures" / "golden"

NOW = "2026-01-01"


@pytest.fixture(autouse=True)
def pinned_now(monkeypatch):
    """Every test renders dates from a pinned clock; determinism is the default."""
    monkeypatch.setenv("ONYXIAN_NOW", NOW)


@pytest.fixture(autouse=True)
def no_obsidian(monkeypatch):
    """Doctor never probes a real Obsidian in tests; the suite must not depend
    on what the developer's machine has installed. Compat cases inject probes
    via run_doctor(..., obsidian_probe=...)."""
    monkeypatch.setattr("onyxian.compat.probe_obsidian_version", lambda: None)


def run_cli(*argv: str) -> int:
    from onyxian.cli import main

    return main([str(a) for a in argv])


def tree_hashes(root: Path) -> dict[str, str]:
    """Portable path -> sha256 for every file under root (dirs implied)."""
    return {
        p.relative_to(root).as_posix(): sha256_file(p)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def init_minimal_vault(tmp_path: Path, name: str = "vault") -> Path:
    vault = tmp_path / name
    code = run_cli("init", str(vault), "--answers", str(ANSWERS_DIR / "minimal.yaml"), "--yes")
    assert code == 0
    return vault


# ------------------------------------------------------------- synthetic modules


def write_module(
    modules_root: Path,
    name: str,
    *,
    version: str = "0.1.0",
    summary: str = "synthetic test module",
    depends: list[str] | None = None,
    conflicts: list[str] | None = None,
    variables: list[dict] | None = None,
    folders: list[str] | None = None,
    templates: dict[str, str] | None = None,
    bases: dict[str, str] | None = None,
    seeds: dict[str, str] | None = None,
    skills: dict[str, dict[str, str]] | None = None,
    agents: dict[str, dict] | None = None,
    post_install: str = "",
) -> Path:
    """Write a synthetic module to disk; file dicts map install path -> content."""
    module_dir = modules_root / name
    manifest: dict = {"name": name, "version": version, "summary": summary}
    if depends is None and name != "core":
        depends = ["core"]
    if depends:
        manifest["depends"] = depends
    if conflicts:
        manifest["conflicts"] = conflicts
    if variables:
        manifest["variables"] = variables
    provides: dict = {}
    if folders:
        provides["folders"] = folders
    for key, files in (("templates", templates), ("bases", bases)):
        if files:
            provides[key] = sorted(files)
    if skills:
        provides["skills"] = sorted(skills)
        for skill_id, skill_files in skills.items():
            for rel, content in skill_files.items():
                target = module_dir / "skills" / skill_id
                for segment in rel.split("/"):
                    target = target / segment
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
    if agents:
        provides["agents"] = sorted(agents)
        for agent_id, definition in agents.items():
            target = module_dir / "agents" / f"{agent_id}.yaml"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(yaml.safe_dump(definition, sort_keys=False), encoding="utf-8")
    if provides:
        manifest["provides"] = provides
    if seeds:
        manifest["seeds"] = sorted(seeds)
    if post_install:
        manifest["post_install"] = post_install
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "module.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )
    for files in (templates, bases, seeds):
        for install_path, content in (files or {}).items():
            asset = module_dir / "assets"
            for segment in install_path.split("/"):
                asset = asset / segment
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_text(content, encoding="utf-8", newline="\n")
    return module_dir


@pytest.fixture
def synth_root(tmp_path: Path) -> Path:
    root = tmp_path / "modules"
    write_module(root, "core")
    return root


def make_config(modules: dict[str, dict] | None = None, **overrides) -> Config:
    raw = {
        "framework": {"version": "0.1.0", "runtimes": ["claude-code"]},
        "vault": {"name": overrides.get("vault_name", "Test Vault")},
        "naming": {"folder_style": overrides.get("folder_style", "Title-Case-Hyphen")},
        "modules": {"core": {"version": "0.1.0"}, **(modules or {})},
    }
    return parse_config(raw, where="<test config>")


def plan_for(
    vault: Path, modules_root: Path, config: Config
) -> tuple[Plan, list[Manifest], "object"]:
    """Build (plan, manifests, lock) for a vault against a module root."""
    library = discover_modules(modules_root)
    manifests = resolve_modules(config, library)
    desired = build_desired_state(config, manifests)
    lock = load_lock(vault)
    return build_plan(vault, desired, lock, set(config.modules)), manifests, lock


def real_manifest(name: str) -> Manifest:
    return load_manifest(REAL_MODULES / name)

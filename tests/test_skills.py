"""Skill packages: structure, manifest binding, and the one-source-of-truth sync (§6.2)."""

import pytest
import yaml

from conftest import REAL_MODULES, REPO_ROOT, run_cli, write_module
from onyx.errors import ManifestError
from onyx.manifests import load_manifest

CORE_SKILLS = REAL_MODULES / "core" / "skills"


def skill_frontmatter(skill_dir):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{skill_dir.name}: SKILL.md must open with YAML frontmatter"
    block = text.split("---\n", 2)[1]
    return yaml.safe_load(block)


@pytest.mark.parametrize(
    "skill_id", ["vault-bootstrap", "vault-conventions", "obsidian-tasks", "obsidian-templater"]
)
def test_core_skill_frontmatter_is_spec_shaped(skill_id):
    meta = skill_frontmatter(CORE_SKILLS / skill_id)
    assert meta["name"] == skill_id
    assert isinstance(meta["description"], str) and len(meta["description"]) > 40


def test_core_manifest_binds_both_skills():
    manifest = load_manifest(REAL_MODULES / "core")
    assert sorted(s.id for s in manifest.skills) == [
        "obsidian-tasks",
        "obsidian-templater",
        "vault-bootstrap",
        "vault-conventions",
    ]
    assert all((s.directory / "SKILL.md").is_file() for s in manifest.skills)


def test_conventions_skill_mirrors_the_canonical_docs_byte_for_byte():
    """One source of truth, two audiences: change core/conventions/, re-copy, or this fails (§6.2)."""
    for name in ("frontmatter.md", "naming.md"):
        canonical = (REPO_ROOT / "core" / "conventions" / name).read_bytes()
        bundled = (CORE_SKILLS / "vault-conventions" / name).read_bytes()
        assert bundled == canonical, (
            f"{name} diverged between core/conventions/ and the vault-conventions skill; "
            "edit the canonical file and copy it over"
        )


def test_bootstrap_skill_keeps_the_parity_table_complete():
    """§9.2: every wizard question maps onto a config key; the skill must name them all."""
    body = (CORE_SKILLS / "vault-bootstrap" / "SKILL.md").read_text(encoding="utf-8")
    for key in ("vault.name", "naming.folder_style", "framework.runtimes", "modules.<id>", "sources.obsidian-skills"):
        assert key in body, f"parity table lost the {key} mapping"
    for rule in ("--dry-run", "--answers", "doctor", "verbatim"):
        assert rule in body


def test_listed_skill_without_package_is_rejected(tmp_path):
    module_dir = write_module(tmp_path, "demo")
    manifest_path = module_dir / "module.yaml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8") + "provides:\n  skills: [ghost-skill]\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="ghost-skill"):
        load_manifest(module_dir)


def test_unlisted_skill_package_is_rejected(tmp_path):
    module_dir = write_module(tmp_path, "demo")
    rogue = module_dir / "skills" / "rogue"
    rogue.mkdir(parents=True)
    (rogue / "SKILL.md").write_text("---\nname: rogue\ndescription: x\n---\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="rogue"):
        load_manifest(module_dir)


def test_modules_command_lists_the_library(capsys):
    assert run_cli("modules") == 0
    out = capsys.readouterr().out
    assert "core 0.1.0" in out
    assert "skills: vault-bootstrap, vault-conventions, obsidian-tasks, obsidian-templater" in out

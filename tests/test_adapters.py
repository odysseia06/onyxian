"""claude-code adapter and the generated Start-Here note (KICKSTART.md §7.4, §9.2)."""

import pytest

from conftest import make_config, plan_for, write_module
from onyx.applier import apply_plan
from onyx.errors import ResolveError
from onyx.intent import build_desired_state
from onyx.lockio import load_lock
from onyx.repo import discover_modules
from onyx.resolve import resolve_modules

SKILL_MD = "---\nname: demo-skill\ndescription: test skill\n---\n\nThis skill documents the {{root}} placeholder syntax itself.\n"


@pytest.fixture
def world_root(tmp_path):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(
        modules_root,
        "demo",
        variables=[{"key": "root", "prompt": "Root", "default": "Demo-Stuff"}],
        folders=["{{root}}"],
        skills={"demo-skill": {"SKILL.md": SKILL_MD, "reference.md": "see {{root}}\n", "logo.bin": "raw"}},
    )
    return modules_root


def desired_for(modules_root, config):
    library = discover_modules(modules_root)
    manifests = resolve_modules(config, library)
    return build_desired_state(config, manifests)


def test_skills_are_copied_byte_for_byte(world_root):
    """A skill is a static package; one documenting {{placeholder}} syntax must survive verbatim."""
    config = make_config({"demo": {"version": "0.1.0"}})
    files = desired_for(world_root, config).file_by_path()
    skill = files[".claude/skills/demo-skill/SKILL.md"]
    assert skill.kind == "managed" and skill.module == "demo"
    assert b"the {{root}} placeholder syntax itself" in skill.content
    assert files[".claude/skills/demo-skill/reference.md"].content == "see {{root}}\n".encode()
    assert files[".claude/skills/demo-skill/logo.bin"].content == b"raw"


def test_runtime_paths_are_not_style_transformed(world_root):
    config = make_config({"demo": {"version": "0.1.0"}}, folder_style="Spaces")
    files = desired_for(world_root, config).file_by_path()
    assert ".claude/skills/demo-skill/SKILL.md" in files  # not ".claude/skills/demo skill"


def test_non_claude_runtimes_get_skills_but_not_claude_agents(world_root, monkeypatch):
    """D9: every runtime gets the (runtime-agnostic) skill packages; only Claude gets rendered subagents."""
    config = make_config({"demo": {"version": "0.1.0"}})
    config.runtimes = ["generic"]
    files = desired_for(world_root, config).file_by_path()
    assert ".claude/skills/demo-skill/SKILL.md" in files
    assert not [p for p in files if p.startswith(".claude/agents/")]
    assert "AGENTS.md" in files


def test_skill_id_collisions_are_rejected(world_root, tmp_path):
    write_module(
        world_root,
        "other",
        skills={"demo-skill": {"SKILL.md": "---\nname: demo-skill\ndescription: dup\n---\n"}},
    )
    config = make_config({"demo": {"version": "0.1.0"}, "other": {"version": "0.1.0"}})
    with pytest.raises(ResolveError, match="skill id collision"):
        desired_for(world_root, config)


def test_skills_are_lock_tracked_and_module_attributed(world_root, tmp_path):
    config = make_config({"demo": {"version": "0.1.0"}})
    vault = tmp_path / "vault"
    vault.mkdir()
    plan, _, lock = plan_for(vault, world_root, config)
    assert apply_plan(vault, plan, lock).ok
    entry = load_lock(vault).get(".claude/skills/demo-skill/SKILL.md")
    assert entry is not None and entry.module == "demo" and entry.kind == "managed"


def test_start_here_summarizes_the_module_set(world_root):
    config = make_config({"demo": {"version": "0.1.0"}})
    files = desired_for(world_root, config).file_by_path()
    text = files["Start-Here.md"].content.decode("utf-8")
    assert files["Start-Here.md"].module == "core"
    assert "- **core** 0.1.0" in text and "- **demo** 0.1.0" in text
    assert "created:" not in text  # regeneration date would break P3; documented exception
    assert "onyx plan" in text


def test_start_here_reflects_post_install(world_root):
    write_module(world_root, "noisy", post_install="Fill in your Strategy note first.")
    config = make_config({"noisy": {"version": "0.1.0"}})
    text = desired_for(world_root, config).file_by_path()["Start-Here.md"].content.decode("utf-8")
    assert "## First actions" in text
    assert "- **noisy**: Fill in your Strategy note first." in text


from pathlib import Path

from onyx.adapters import _folders_from_scope, _frontmatter_description, _skill_one_liner
from onyx.model import ProvidedSkill


def test_frontmatter_description_extracts_field():
    md = "---\nname: x\ndescription: A short summary.\n---\n\nbody\n"
    assert _frontmatter_description(md) == "A short summary."


def test_frontmatter_description_missing_returns_none():
    assert _frontmatter_description("no frontmatter here\n") is None
    assert _frontmatter_description("---\nname: x\n---\nbody\n") is None


def test_folders_from_scope_strips_globs_dedupes_and_handles_empty():
    assert _folders_from_scope(["Projects/Software/**", "Projects/Software/**"]) == ["Projects/Software"]
    assert _folders_from_scope(["Daily/*"]) == ["Daily"]
    assert _folders_from_scope(["**"]) == ["the whole vault"]
    assert _folders_from_scope([]) == []


def test_skill_one_liner_reads_description(tmp_path):
    d = tmp_path / "demo-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Does a thing.\n---\nbody\n", encoding="utf-8"
    )
    assert _skill_one_liner(ProvidedSkill(id="demo-skill", directory=d)) == "**demo-skill** — Does a thing."


def test_skill_one_liner_fallback_without_description(tmp_path):
    d = tmp_path / "bare"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: bare\n---\nbody\n", encoding="utf-8")
    assert _skill_one_liner(ProvidedSkill(id="bare", directory=d)) == "**bare** — see its `SKILL.md`."

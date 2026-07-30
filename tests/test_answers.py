"""Answers-file validation and answers-to-Config parity (#131: the CLI asks no questions)."""

from pathlib import Path

import pytest
from conftest import write_module

from onyxian.answers import Answers, build_config, load_answers
from onyxian.errors import AnswersError
from onyxian.repo import discover_modules


def _core_library(tmp_path: Path):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    return discover_modules(modules_root)


def _answers_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "answers.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_answers_file_accepts_module_list_alongside_config_keys(tmp_path):
    answers = load_answers(
        _answers_file(
            tmp_path,
            "vault: { name: Journal }\nnaming: { folder_style: Spaces }\nmodules: [journal]\n",
        )
    )

    assert answers.vault_name == "Journal"
    assert answers.folder_style == "Spaces"
    assert answers.modules == {"journal": {}}


def test_profile_name_is_retained(tmp_path):
    answers = load_answers(_answers_file(tmp_path, "name: writer\nmodules: [core, writing]\n"))

    assert answers.profile_name == "writer"


def test_empty_answers_build_the_default_core_config(tmp_path):
    config = build_config(_core_library(tmp_path), Answers())

    assert config.vault_name == "My Vault"
    assert config.folder_style == "Title-Case-Hyphen"
    assert config.runtimes == ["claude-code"]
    assert list(config.modules) == ["core"]


def test_build_config_enables_dependencies_of_answered_modules(tmp_path):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(
        modules_root,
        "journal",
        variables=[{"key": "root", "prompt": "Journal folder", "default": "Journal"}],
        folders=["{{root}}"],
    )
    write_module(modules_root, "extra", depends=["core", "journal"])
    answers = Answers()
    answers.modules = {"extra": {}}

    config = build_config(discover_modules(modules_root), answers)

    assert set(config.modules) == {"core", "extra", "journal"}
    assert config.modules["journal"].vars == {"root": "Journal"}


def test_required_variable_without_an_answer_is_an_error(tmp_path):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(modules_root, "strict", variables=[{"key": "req", "prompt": "Required thing"}])
    answers = Answers()
    answers.modules = {"strict": {}}

    with pytest.raises(AnswersError, match="supply it in the answers file"):
        build_config(discover_modules(modules_root), answers)


def test_answers_file_reads_checkpoints_flag(tmp_path):
    answers = load_answers(_answers_file(tmp_path, "framework: { checkpoints: true }\n"))
    assert answers.checkpoints is True


def test_answers_file_rejects_non_bool_checkpoints(tmp_path):
    with pytest.raises(AnswersError, match="checkpoints"):
        load_answers(_answers_file(tmp_path, "framework: { checkpoints: yes-please }\n"))


def test_config_defaults_checkpoints_off(tmp_path):
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "vault: { name: V }\n"))
    assert build_config(library, answers).checkpoints is False


def test_config_carries_checkpoints_from_answers(tmp_path):
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "framework: { checkpoints: true }\n"))
    assert build_config(library, answers).checkpoints is True


def test_answers_file_reads_scope_hooks_flag(tmp_path):
    answers = load_answers(_answers_file(tmp_path, "framework: { scope_hooks: true }\n"))
    assert answers.scope_hooks is True


def test_answers_file_rejects_non_bool_scope_hooks(tmp_path):
    with pytest.raises(AnswersError, match="scope_hooks"):
        load_answers(_answers_file(tmp_path, "framework: { scope_hooks: sure }\n"))


def test_config_defaults_scope_hooks_off(tmp_path):
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "vault: { name: V }\n"))
    assert build_config(library, answers).scope_hooks is False


def test_config_carries_scope_hooks_from_answers(tmp_path):
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "framework: { scope_hooks: true }\n"))
    assert build_config(library, answers).scope_hooks is True


def test_answers_file_defaults_obsidian_skills_in(tmp_path):
    """Silence means the default (#65): obsidian-skills is declared unless opted out."""
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "vault: { name: V }\n"))
    assert "obsidian-skills" in build_config(library, answers).sources


def test_answers_file_opts_out_of_a_source_with_false(tmp_path):
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "sources: { obsidian-skills: false }\n"))
    assert build_config(library, answers).sources == {}


def test_source_default_needs_claude_code(tmp_path):
    """The skills land in .claude/skills/; no claude-code runtime, no default."""
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "framework: { runtimes: [generic] }\n"))
    assert build_config(library, answers).sources == {}

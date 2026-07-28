"""Interview prompt validation and interview-to-Config parity."""

import builtins
from pathlib import Path

import pytest
from conftest import write_module

from onyxian.errors import AnswersError
from onyxian.interview import (
    _prompt_bool,
    _prompt_choice,
    _prompt_variable,
    load_answers,
    run_interview,
)
from onyxian.model import Variable
from onyxian.repo import discover_modules


def _scripted_input(monkeypatch, answers):
    it = iter(answers)
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(it))


def _counting_input(monkeypatch, answers):
    """Record every consumed answer so a test can assert exactly how many prompts fired."""
    it = iter(answers)
    consumed: list[str] = []

    def fake_input(_prompt):
        value = next(it)
        consumed.append(value)
        return value

    monkeypatch.setattr(builtins, "input", fake_input)
    return consumed


def test_prompt_choice_reprompts_then_accepts(monkeypatch, capsys):
    _scripted_input(monkeypatch, ["bad", "bad", "2"])
    assert _prompt_choice("pick", ("a", "b"), "a") == "b"
    out = capsys.readouterr().out
    assert "not a valid choice" in out
    assert "using default" not in out  # accepted a valid answer, so no fallback note


def test_prompt_choice_empty_input_returns_default_on_first_attempt(monkeypatch, capsys):
    consumed = _counting_input(monkeypatch, ["", "unused"])
    assert _prompt_choice("pick", ("a", "b"), "b") == "b"
    assert consumed == [""]  # empty answer short-circuits; nothing else is read
    assert "using default" not in capsys.readouterr().out


def test_prompt_choice_falls_back_to_default_after_exactly_three_bad_inputs(monkeypatch, capsys):
    consumed = _counting_input(monkeypatch, ["x", "9", "?!", "unused"])
    assert _prompt_choice("pick", ("a", "b"), "a") == "a"
    assert consumed == ["x", "9", "?!"]  # bounded at three reads; the fourth is never consumed
    assert "unrecognized; using default 'a'" in capsys.readouterr().out


def test_prompt_bool_reprompts_then_accepts(monkeypatch, capsys):
    _scripted_input(monkeypatch, ["maybe", "y"])
    assert _prompt_bool("enable?", False) is True
    out = capsys.readouterr().out
    assert "enter y or n" in out
    assert "using default" not in out


def test_prompt_bool_empty_input_returns_default_on_first_attempt(monkeypatch):
    consumed = _counting_input(monkeypatch, ["", "unused"])
    assert _prompt_bool("enable?", True) is True
    assert consumed == [""]


def test_prompt_bool_falls_back_to_default_after_exactly_three_bad_inputs(monkeypatch, capsys):
    consumed = _counting_input(monkeypatch, ["huh", "wat", "??", "unused"])
    assert _prompt_bool("enable?", False) is False
    assert consumed == ["huh", "wat", "??"]
    assert "unrecognized; using default 'n'" in capsys.readouterr().out


def test_required_text_accepts_the_third_attempt(monkeypatch):
    variable = Variable(key="root", prompt="Root folder")
    consumed = _counting_input(monkeypatch, ["", "", "Reading"])
    assert _prompt_variable("reading", variable) == "Reading"
    assert consumed == ["", "", "Reading"]


def test_required_text_fails_after_exactly_three_empty_inputs(monkeypatch):
    variable = Variable(key="root", prompt="Root folder")
    consumed = _counting_input(monkeypatch, ["", "", "", "unused"])
    with pytest.raises(AnswersError, match="required"):
        _prompt_variable("reading", variable)
    assert consumed == ["", "", ""]


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


def test_interactive_init_selects_runtimes_and_modules_from_summaries(
    tmp_path, monkeypatch, capsys
):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core", summary="Shared vault foundation")
    write_module(
        modules_root,
        "journal",
        summary="A daily journal and reflection workflow",
        variables=[{"key": "root", "prompt": "Journal folder"}],
        folders=["{{root}}"],
    )
    library = discover_modules(modules_root)
    _scripted_input(
        monkeypatch,
        [
            "Journal Vault",
            "3",
            "codex, generic",
            "n",
            "journal",
            "My Journal",
        ],
    )

    config = run_interview(library, None, interactive=True)

    assert config.runtimes == ["codex", "generic"]
    assert list(config.modules) == ["core", "journal"]
    assert config.modules["journal"].vars == {"root": "My Journal"}
    assert "A daily journal and reflection workflow" in capsys.readouterr().out


def test_answers_file_reads_checkpoints_flag(tmp_path):
    answers = load_answers(_answers_file(tmp_path, "framework: { checkpoints: true }\n"))
    assert answers.checkpoints is True


def test_answers_file_rejects_non_bool_checkpoints(tmp_path):
    with pytest.raises(AnswersError, match="checkpoints"):
        load_answers(_answers_file(tmp_path, "framework: { checkpoints: yes-please }\n"))


def test_interview_defaults_checkpoints_off(tmp_path):
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "vault: { name: V }\n"))
    config = run_interview(library, answers, interactive=False)
    assert config.checkpoints is False


def test_interview_carries_checkpoints_from_answers(tmp_path):
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "framework: { checkpoints: true }\n"))
    config = run_interview(library, answers, interactive=False)
    assert config.checkpoints is True


def test_interview_reprompts_checkpoint_typos(tmp_path, monkeypatch, capsys):
    library = _core_library(tmp_path)
    # vault name, folder style, and a generic runtime are all pinned so the
    # checkpoint question is the only prompt that reads input.
    answers = load_answers(
        _answers_file(
            tmp_path,
            "vault: { name: V }\nnaming: { folder_style: kebab-case }\n"
            "framework: { runtimes: [generic] }\n",
        )
    )
    _scripted_input(monkeypatch, ["yes please", "y"])
    config = run_interview(library, answers, interactive=True)
    assert config.checkpoints is True
    assert "not a valid choice" in capsys.readouterr().out


def test_answers_file_reads_scope_hooks_flag(tmp_path):
    answers = load_answers(_answers_file(tmp_path, "framework: { scope_hooks: true }\n"))
    assert answers.scope_hooks is True


def test_answers_file_rejects_non_bool_scope_hooks(tmp_path):
    with pytest.raises(AnswersError, match="scope_hooks"):
        load_answers(_answers_file(tmp_path, "framework: { scope_hooks: sure }\n"))


def test_interview_defaults_scope_hooks_off(tmp_path):
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "vault: { name: V }\n"))
    assert run_interview(library, answers, interactive=False).scope_hooks is False


def test_interview_carries_scope_hooks_from_answers(tmp_path):
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "framework: { scope_hooks: true }\n"))
    assert run_interview(library, answers, interactive=False).scope_hooks is True


def test_answers_file_defaults_obsidian_skills_in_like_the_wizard(tmp_path):
    """Parity (#65): silence in an answers file means what silence means in the wizard."""
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "vault: { name: V }\n"))
    config = run_interview(library, answers, interactive=False)
    assert "obsidian-skills" in config.sources


def test_answers_file_opts_out_of_a_source_with_false(tmp_path):
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "sources: { obsidian-skills: false }\n"))
    assert run_interview(library, answers, interactive=False).sources == {}


def test_source_default_needs_claude_code(tmp_path):
    """The skills land in .claude/skills/; no claude-code runtime, no default."""
    library = _core_library(tmp_path)
    answers = load_answers(_answers_file(tmp_path, "framework: { runtimes: [generic] }\n"))
    assert run_interview(library, answers, interactive=False).sources == {}


def test_declared_source_is_not_re_asked_interactively(tmp_path, monkeypatch):
    """An answers file that already spoke is an answer, not a reason to prompt."""
    library = _core_library(tmp_path)
    answers = load_answers(
        _answers_file(
            tmp_path,
            "vault: { name: V }\nnaming: { folder_style: kebab-case }\n"
            "sources: { obsidian-skills: false }\n",
        )
    )
    # only the checkpoint and scope-hook questions remain; a fourth read would raise
    _scripted_input(monkeypatch, ["n", "n"])
    assert run_interview(library, answers, interactive=True).sources == {}


def test_interview_reprompts_scope_hook_typos(tmp_path, monkeypatch, capsys):
    library = _core_library(tmp_path)
    answers = load_answers(
        _answers_file(
            tmp_path,
            "vault: { name: V }\nnaming: { folder_style: kebab-case }\n"
            "framework: { checkpoints: false }\n"
            "sources: { obsidian-skills: false }\n",
        )
    )
    _scripted_input(monkeypatch, ["yes please", "y"])
    assert run_interview(library, answers, interactive=True).scope_hooks is True
    assert "not a valid choice" in capsys.readouterr().out


def test_interview_source_typo_then_empty_keeps_default_yes(tmp_path, monkeypatch, capsys):
    library = _core_library(tmp_path)
    answers = load_answers(
        _answers_file(
            tmp_path,
            "vault: { name: V }\nnaming: { folder_style: kebab-case }\n"
            "framework: { checkpoints: false, scope_hooks: false }\n",
        )
    )
    consumed = _counting_input(monkeypatch, ["yes please", ""])
    config = run_interview(library, answers, interactive=True)
    assert "obsidian-skills" in config.sources
    assert consumed == ["yes please", ""]
    assert "not a valid choice" in capsys.readouterr().out

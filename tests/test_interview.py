"""Interview prompts and the interview -> Config parity for the checkpoint and scope-hooks flags."""

import builtins
from pathlib import Path

import pytest
from conftest import write_module

from onyxian.errors import AnswersError
from onyxian.interview import _prompt_bool, _prompt_choice, load_answers, run_interview
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


def _core_library(tmp_path: Path):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    return discover_modules(modules_root)


def _answers_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "answers.yaml"
    path.write_text(text, encoding="utf-8")
    return path


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


def test_interview_offers_the_flag_interactively(tmp_path, monkeypatch):
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
    _scripted_input(monkeypatch, ["y"])
    config = run_interview(library, answers, interactive=True)
    assert config.checkpoints is True


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


def test_interview_offers_scope_hooks_interactively(tmp_path, monkeypatch):
    library = _core_library(tmp_path)
    answers = load_answers(
        _answers_file(tmp_path, "vault: { name: V }\nnaming: { folder_style: kebab-case }\n")
    )
    # claude-code default -> three prompts fire in order: checkpoint, scope-hooks, source-install.
    _scripted_input(monkeypatch, ["n", "y", "n"])
    assert run_interview(library, answers, interactive=True).scope_hooks is True

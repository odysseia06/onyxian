"""Interview prompts and the interview -> Config parity for the scope-hooks flag."""

import builtins
from pathlib import Path

import pytest
from conftest import write_module

from onyxian.errors import AnswersError
from onyxian.interview import _prompt_choice, load_answers, run_interview
from onyxian.repo import discover_modules


def _scripted_input(monkeypatch, answers):
    it = iter(answers)
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(it))


def test_prompt_choice_reprompts_then_accepts(monkeypatch, capsys):
    _scripted_input(monkeypatch, ["nope", "2"])
    assert _prompt_choice("pick", ("a", "b"), "a") == "b"
    assert "not a valid choice" in capsys.readouterr().out


def test_prompt_choice_falls_back_to_default_after_three_bad_inputs(monkeypatch, capsys):
    _scripted_input(monkeypatch, ["x", "9", "?!"])
    assert _prompt_choice("pick", ("a", "b"), "a") == "a"
    assert "unrecognized; using default 'a'" in capsys.readouterr().out


def _core_library(tmp_path: Path):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    return discover_modules(modules_root)


def _answers_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "answers.yaml"
    path.write_text(text, encoding="utf-8")
    return path


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
    # claude-code default runtime -> scope-hooks question, then the source-install prompt.
    _scripted_input(monkeypatch, ["y", "n"])
    assert run_interview(library, answers, interactive=True).scope_hooks is True

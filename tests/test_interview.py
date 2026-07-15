"""Interview prompts and the interview -> Config parity for the checkpoint flag."""

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

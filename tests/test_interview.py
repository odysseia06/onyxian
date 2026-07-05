"""Interview prompts: choice questions retry bad input, then fall back to the default."""

import builtins

from onyxian.interview import _prompt_choice


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

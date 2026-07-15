"""`onyxian add`: comment-preserving config insertion, dependency closure, plan/apply (§9.1)."""

from types import SimpleNamespace

import pytest

from conftest import run_cli, write_module
from onyxian.config_edit import insert_module_entries
from onyxian.errors import ConfigError
from onyxian.model import ModuleConfig


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A synthetic module library selected via ONYXIAN_HOME, plus an initialized core-only vault."""
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(
        modules_root,
        "demo",
        variables=[{"key": "root", "prompt": "Folder name", "default": "Demo-Stuff"}],
        folders=["{{root}}/Logs"],
        seeds={"{{root}}/Strategy.md": "fill me in\n"},
        post_install="Fill the Strategy note first.",
    )
    write_module(modules_root, "extra", depends=["core", "demo"], folders=["Extra-Things"])
    write_module(modules_root, "strict", variables=[{"key": "req", "prompt": "Required thing"}])
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    answers = tmp_path / "answers.yaml"
    answers.write_text("modules: {core: {}}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(answers), "--yes") == 0
    return SimpleNamespace(vault=vault, tmp=tmp_path)


def config_text(home) -> str:
    return (home.vault / ".vault" / "config.yaml").read_text(encoding="utf-8")


def test_add_enables_module_and_applies(home, capsys):
    assert run_cli("add", "demo", "--vault", str(home.vault), "--yes") == 0
    out = capsys.readouterr().out
    assert "Fill the Strategy note first." in out  # post_install relayed
    assert 'demo: { version: "0.1.0", vars: { root: "Demo-Stuff" } }' in config_text(home)
    assert (home.vault / "Demo-Stuff" / "Logs").is_dir()
    assert (home.vault / "Demo-Stuff" / "Strategy.md").read_text(encoding="utf-8") == "fill me in\n"
    start_here = (home.vault / "Start-Here.md").read_text(encoding="utf-8")
    assert "- **demo** 0.1.0" in start_here  # regenerated for the new module set


def test_add_preserves_user_comments_and_formatting(home):
    config_file = home.vault / ".vault" / "config.yaml"
    before = config_file.read_text(encoding="utf-8")
    marked = before.replace("vault:", "# my precious comment\nvault:")
    config_file.write_text(marked, encoding="utf-8")
    assert run_cli("add", "demo", "--vault", str(home.vault), "--yes") == 0
    after = config_text(home)
    assert "# my precious comment" in after
    # Every original line survives, in order; add only inserted.
    original_lines = [l for l in marked.split("\n")]
    it = iter(after.split("\n"))
    assert all(any(line == out_line for out_line in it) for line in original_lines)


def test_add_is_idempotent(home, capsys):
    assert run_cli("add", "demo", "--vault", str(home.vault), "--yes") == 0
    assert run_cli("add", "demo", "--vault", str(home.vault), "--yes") == 0
    assert "already enabled" in capsys.readouterr().out


def test_add_pulls_dependencies_and_says_so(home, capsys):
    assert run_cli("add", "extra", "--vault", str(home.vault), "--yes") == 0
    out = capsys.readouterr().out
    assert "plus dependencies: demo" in out
    text = config_text(home)
    assert "extra:" in text and "demo:" in text
    assert (home.vault / "Extra-Things").is_dir()


def test_add_unknown_module_lists_available(home, capsys):
    assert run_cli("add", "ghost", "--vault", str(home.vault), "--yes") == 1
    assert "'ghost'" in capsys.readouterr().err


def test_required_variable_needs_answers_when_non_interactive(home, tmp_path, capsys):
    assert run_cli("add", "strict", "--vault", str(home.vault), "--yes") == 1
    assert "supply it in the answers file" in capsys.readouterr().err
    answers = tmp_path / "strict.yaml"
    answers.write_text('modules: {strict: {req: "Value"}}\n', encoding="utf-8")
    assert (
        run_cli("add", "strict", "--vault", str(home.vault), "--answers", str(answers), "--yes")
        == 0
    )
    assert 'req: "Value"' in config_text(home)


def test_add_dry_run_changes_nothing(home):
    before = config_text(home)
    assert run_cli("add", "demo", "--vault", str(home.vault), "--dry-run") == 0
    assert config_text(home) == before
    assert not (home.vault / "Demo-Stuff").exists()


def test_insert_requires_a_block_style_modules_line():
    text = 'framework:\n  version: "0.1.0"\nvault:\n  name: "X"\nnaming:\n  folder_style: Title-Case-Hyphen\nmodules: {core: {version: "0.1.0"}}\n'
    with pytest.raises(ConfigError, match="by hand"):
        insert_module_entries(text, {"demo": ModuleConfig(version="0.1.0")})

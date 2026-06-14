"""CLI behavior: init guards, non-interactive discipline, honest stubs (KICKSTART.md §9.1)."""

import subprocess
import sys

from conftest import ANSWERS_DIR, REPO_ROOT, init_minimal_vault, run_cli, tree_hashes

MINIMAL_ANSWERS = str(ANSWERS_DIR / "minimal.yaml")


def test_version_via_real_entrypoint():
    out = subprocess.run(
        [sys.executable, "-m", "onyx.cli", "--version"], capture_output=True, text=True
    )
    assert out.returncode == 0
    assert out.stdout.strip() == "onyx 1.0.9"


def test_init_refuses_a_lived_in_folder(tmp_path, capsys):
    target = tmp_path / "lived-in"
    target.mkdir()
    (target / "My Notes.md").write_text("precious\n", encoding="utf-8")
    code = run_cli("init", str(target), "--answers", MINIMAL_ANSWERS, "--yes")
    captured = capsys.readouterr()
    assert code == 1
    assert "adopt" in captured.err
    assert (target / "My Notes.md").read_text(encoding="utf-8") == "precious\n"
    assert not (target / ".vault").exists()


def test_init_tolerates_vcs_obsidian_and_os_junk(tmp_path):
    target = tmp_path / "fresh"
    (target / ".git").mkdir(parents=True)
    (target / ".obsidian").mkdir()
    (target / ".DS_Store").write_text("", encoding="utf-8")
    assert run_cli("init", str(target), "--answers", MINIMAL_ANSWERS, "--yes") == 0
    assert (target / "Home.md").is_file()


def test_init_refuses_an_already_initialized_vault(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    code = run_cli("init", str(vault), "--answers", MINIMAL_ANSWERS, "--yes")
    assert code == 1
    assert "already an Onyx vault" in capsys.readouterr().err


def test_non_interactive_init_requires_answers(tmp_path, capsys):
    code = run_cli("init", str(tmp_path / "v"))
    assert code == 1
    assert "--answers" in capsys.readouterr().err


def test_non_interactive_confirmation_requires_yes(tmp_path, capsys):
    code = run_cli("init", str(tmp_path / "v"), "--answers", MINIMAL_ANSWERS)
    assert code == 1
    assert "--yes" in capsys.readouterr().err
    assert not (tmp_path / "v").exists()


def test_init_dry_run_writes_nothing(tmp_path, capsys):
    target = tmp_path / "v"
    code = run_cli("init", str(target), "--answers", MINIMAL_ANSWERS, "--dry-run")
    out = capsys.readouterr().out
    assert code == 0
    assert "dry run" in out
    assert "templates/Note.md" in out  # the plan itself was shown (kebab-case answers)
    assert not target.exists()


def test_profile_file_is_a_valid_answers_input(tmp_path):
    """profiles/minimal.yaml (§5.5) feeds --answers directly; defaults fill the rest."""
    target = tmp_path / "v"
    profile = REPO_ROOT / "profiles" / "minimal.yaml"
    assert run_cli("init", str(target), "--answers", str(profile), "--yes") == 0
    config_text = (target / ".vault" / "config.yaml").read_text(encoding="utf-8")
    assert 'name: "My Vault"' in config_text
    assert "folder_style: Title-Case-Hyphen" in config_text
    assert (target / "Templates" / "Note.md").is_file()


def test_apply_dry_run_changes_nothing(tmp_path):
    vault = init_minimal_vault(tmp_path)
    (vault / "templates" / "Note.md").unlink()  # forces a pending restore
    before = tree_hashes(vault)
    assert run_cli("apply", "--vault", str(vault), "--dry-run") == 0
    assert tree_hashes(vault) == before
    assert run_cli("apply", "--vault", str(vault), "--yes") == 0
    assert (vault / "templates" / "Note.md").is_file()


def test_commands_on_a_non_vault_fail_with_guidance(tmp_path, capsys):
    code = run_cli("plan", "--vault", str(tmp_path))
    assert code == 1
    assert "not an Onyx-managed vault" in capsys.readouterr().err


def test_every_charter_command_is_real():
    """§9.1's command table is fully implemented; no stubs remain."""
    from onyx.cli import build_parser

    parser = build_parser()
    subactions = next(a for a in parser._actions if getattr(a, "choices", None))
    for command in ("init", "adopt", "plan", "apply", "add", "remove", "update", "doctor", "module", "modules"):
        assert command in subactions.choices


def test_invalid_onyx_now_is_a_clean_error(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ONYX_NOW", "not-a-date")
    code = run_cli("init", str(tmp_path / "v"), "--answers", MINIMAL_ANSWERS, "--yes")
    assert code == 1
    assert "ONYX_NOW" in capsys.readouterr().err


def test_answers_resolves_a_bundled_profile_by_name(tmp_path):
    """An installed user types `--answers minimal`, not a path into site-packages."""
    target = tmp_path / "v"
    assert run_cli("init", str(target), "--answers", "minimal", "--yes") == 0
    assert (target / "Templates" / "Note.md").is_file()


def test_answers_unknown_profile_lists_what_is_available(tmp_path, capsys):
    code = run_cli("init", str(tmp_path / "v"), "--answers", "no-such-profile", "--yes")
    assert code == 1
    err = capsys.readouterr().err
    assert "Available profiles" in err and "minimal" in err

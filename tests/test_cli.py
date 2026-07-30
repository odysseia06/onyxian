"""CLI behavior: init guards, non-interactive discipline, honest stubs (KICKSTART.md §9.1)."""

import json
import subprocess
import sys

import pytest
from conftest import ANSWERS_DIR, REPO_ROOT, init_minimal_vault, run_cli, tree_hashes

from onyxian import ENGINE_VERSION
from onyxian.configio import load_config
from onyxian.sources import OBSIDIAN_SKILLS

MINIMAL_ANSWERS = str(ANSWERS_DIR / "minimal.yaml")


def test_version_via_real_entrypoint():
    out = subprocess.run(
        [sys.executable, "-m", "onyxian.cli", "--version"], capture_output=True, text=True
    )
    assert out.returncode == 0
    # ENGINE_VERSION is the single source (issue #5); with one place to edit there
    # is no hand-synced literal left to drift from it.
    assert out.stdout.strip() == f"onyxian {ENGINE_VERSION}"


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
    assert "already an Onyxian vault" in capsys.readouterr().err


def test_bare_init_builds_a_core_vault_with_zero_questions(tmp_path, capsys):
    """#129: `onyxian init <folder>` needs no TTY, no answers file, no confirmation."""
    target = tmp_path / "my-notes"
    code = run_cli("init", str(target))
    captured = capsys.readouterr()
    assert code == 0
    assert (target / "Home.md").is_file()
    config = load_config(target)
    assert config.vault_name == "my-notes"
    assert set(config.modules) == {"core"}
    # obsidian-skills stays declared but uninstalled: instruction consent is --trust's job.
    assert OBSIDIAN_SKILLS in config.sources
    assert "not installed" in captured.err
    assert "onyxian add" in captured.out  # the growth hint


def test_bare_init_asks_nothing_even_on_a_tty(tmp_path, monkeypatch):
    monkeypatch.setattr("onyxian.cli._is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("init asked a question"))
    assert run_cli("init", str(tmp_path / "v")) == 0


def test_bare_init_dry_run_shows_the_plan_and_writes_nothing(tmp_path, capsys):
    target = tmp_path / "v"
    assert run_cli("init", str(target), "--dry-run") == 0
    out = capsys.readouterr().out
    assert "dry run" in out
    assert "Templates/Note.md" in out  # the plan itself was shown (default styling)
    assert not target.exists()


def test_init_profile_is_a_zero_question_full_vault(tmp_path):
    """#129: --profile <name> is the one-shot path; no confirmation, no prompts."""
    target = tmp_path / "v"
    assert run_cli("init", str(target), "--profile", "minimal") == 0
    config = load_config(target)
    assert config.vault_name == "v"
    assert (target / "Templates" / "Note.md").is_file()


def test_init_profile_rejects_an_answers_file(tmp_path, capsys):
    code = run_cli("init", str(tmp_path / "v"), "--profile", MINIMAL_ANSWERS)
    assert code == 1
    assert "not a profile" in capsys.readouterr().err
    assert not (tmp_path / "v").exists()


def test_init_profile_unknown_lists_available(tmp_path, capsys):
    code = run_cli("init", str(tmp_path / "v"), "--profile", "no-such-profile")
    assert code == 1
    err = capsys.readouterr().err
    assert "--profile" in err and "Available profiles" in err


def test_non_interactive_confirmation_requires_yes(tmp_path, capsys):
    code = run_cli("init", str(tmp_path / "v"), "--answers", MINIMAL_ANSWERS)
    assert code == 1
    assert "--yes" in capsys.readouterr().err
    assert not (tmp_path / "v").exists()


def test_eof_at_a_prompt_exits_cleanly(tmp_path, capsys, monkeypatch):
    target = tmp_path / "v"
    monkeypatch.setattr("onyxian.cli._is_interactive", lambda: True)

    def raise_eof(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    assert run_cli("init", str(target), "--answers", MINIMAL_ANSWERS) == 130
    assert "interrupted; nothing partial was left unrecorded" in capsys.readouterr().err
    assert not target.exists()


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
    assert "not an Onyxian-managed vault" in capsys.readouterr().err


def test_non_vault_with_marker_warns_against_the_state_forking_reinit(tmp_path, capsys):
    """A vault marker without .vault/ means a sync service dropped the hidden state
    folder (issue #18) — every command's refusal must say so, not suggest init."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "onyxian.md").write_text("# Onyxian\n", encoding="utf-8")
    code = run_cli("plan", "--vault", str(tmp_path))
    assert code == 1
    err = capsys.readouterr().err
    assert "did not sync" in err
    assert "onyxian init" not in err


def test_every_charter_command_is_real():
    """§9.1's command table is fully implemented; no stubs remain."""
    from onyxian.cli import build_parser

    parser = build_parser()
    subactions = next(a for a in parser._actions if getattr(a, "choices", None))
    assert subactions.choices is not None
    for command in (
        "init",
        "adopt",
        "plan",
        "apply",
        "add",
        "remove",
        "update",
        "doctor",
        "lock",
        "module",
        "modules",
        "new",
    ):
        assert command in subactions.choices


def test_invalid_onyxian_now_is_a_clean_error(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ONYXIAN_NOW", "not-a-date")
    code = run_cli("init", str(tmp_path / "v"), "--answers", MINIMAL_ANSWERS, "--yes")
    assert code == 1
    assert "ONYXIAN_NOW" in capsys.readouterr().err


def test_answers_resolves_a_bundled_profile_by_name(tmp_path, capsys):
    """An installed user types `--answers minimal`, not a path into site-packages."""
    target = tmp_path / "v"
    assert run_cli("init", str(target), "--answers", "minimal", "--yes") == 0
    assert "profile: minimal" in capsys.readouterr().out
    assert (target / "Templates" / "Note.md").is_file()


def test_answers_unknown_profile_lists_what_is_available(tmp_path, capsys):
    code = run_cli("init", str(tmp_path / "v"), "--answers", "no-such-profile", "--yes")
    assert code == 1
    err = capsys.readouterr().err
    assert "Available profiles" in err and "minimal" in err


# ------------------------------------- exit codes and --json (issue #66)
#
# The contract a script branches on, documented in core/onyxian/errors.py:
# 0 = clean, 1 = the command could not do its job, 2 = it ran and has findings.


def test_plan_exit_code_separates_clean_from_pending(tmp_path):
    """The terraform-style drift check: `plan` says *whether* it planned anything."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("plan", "--vault", str(vault)) == 0
    (vault / "templates" / "Note.md").unlink()  # a pending restore
    assert run_cli("plan", "--vault", str(vault)) == 2


def test_plan_json_carries_the_actions_and_the_same_exit_code(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    (vault / "templates" / "Note.md").unlink()
    capsys.readouterr()  # drop init's own output
    code = run_cli("plan", "--vault", str(vault), "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["pending"] == 1
    assert payload["changes"][0]["type"] == "restore"
    assert payload["changes"][0]["path"] == "templates/Note.md"
    assert payload["checked"]  # the no-op counters `plan` prints as prose


def test_doctor_json_carries_the_verdict_and_the_same_exit_code(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    capsys.readouterr()  # drop init's own output
    code = run_cli("doctor", "--vault", str(vault), "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["exit_code"] == 0
    assert payload["verdict"].startswith("healthy")
    assert {f["level"] for f in payload["findings"]} <= {"ok", "info"}

    (vault / "templates" / "Note.md").unlink()  # a WARN, not a broken vault
    code = run_cli("doctor", "--vault", str(vault), "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == 2 and payload["exit_code"] == 2
    assert payload["level"] == "warn"
    assert any(f["level"] == "warn" and f["suggestion"] for f in payload["findings"])


def test_a_usage_error_is_an_error_not_a_finding(tmp_path, capsys):
    """argparse's own exit 2 would be indistinguishable from `doctor`'s findings."""
    with pytest.raises(SystemExit) as exc:
        run_cli("doctor", "--vault", str(tmp_path), "--no-such-flag")
    assert exc.value.code == 1
    assert "unrecognized arguments" in capsys.readouterr().err

"""onyxian project new: standalone scaffold, never-clobber, fresh date, untracked."""

import pytest
from conftest import REAL_MODULES, run_cli

from onyxian.errors import OnyxianError
from onyxian.lockio import load_lock
from onyxian.project_new import scaffold_project, validate_project


def _vault_with_projects(tmp_path):
    answers = tmp_path / "a.yaml"
    answers.write_text("modules: [core, projects-software]\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(answers), "--yes") == 0
    return vault


def _vault_core_only(tmp_path):
    answers = tmp_path / "a.yaml"
    answers.write_text("modules: [core]\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(answers), "--yes") == 0
    return vault


def test_scaffold_creates_overview_and_dirs(tmp_path):
    vault = _vault_with_projects(tmp_path)
    created = scaffold_project(vault, "Limbo", REAL_MODULES, today="2026-06-14")
    assert created == "Projects/Software/Limbo"
    assert (vault / "Projects/Software/Limbo/00 Overview.md").is_file()
    for d in ("Devlog", "Tasks", "Research", "Assets"):
        assert (vault / "Projects/Software/Limbo" / d).is_dir()
    overview = (vault / "Projects/Software/Limbo/00 Overview.md").read_text(encoding="utf-8")
    assert "2026-06-14" in overview  # fresh date, not the pinned-seed 2026-01-01
    assert "{{" not in overview  # placeholders resolved


def test_scaffold_refuses_existing(tmp_path):
    vault = _vault_with_projects(tmp_path)
    scaffold_project(vault, "Limbo", REAL_MODULES, today="2026-06-14")
    with pytest.raises(OnyxianError, match="already exists"):
        scaffold_project(vault, "Limbo", REAL_MODULES, today="2026-06-14")


def test_scaffold_rejects_unsafe_name(tmp_path):
    vault = _vault_with_projects(tmp_path)
    with pytest.raises(OnyxianError):
        scaffold_project(vault, "../escape", REAL_MODULES, today="2026-06-14")
    with pytest.raises(OnyxianError):
        scaffold_project(vault, "a/b", REAL_MODULES, today="2026-06-14")


def test_scaffold_does_not_lock_track_the_project(tmp_path):
    vault = _vault_with_projects(tmp_path)
    scaffold_project(vault, "Limbo", REAL_MODULES, today="2026-06-14")
    lock = load_lock(vault)
    assert lock.get("Projects/Software/Limbo/00 Overview.md") is None  # untracked


def test_cli_project_new_dry_run_writes_nothing(tmp_path, capsys):
    vault = _vault_with_projects(tmp_path)
    capsys.readouterr()
    assert run_cli("project", "new", "Limbo", "--vault", str(vault), "--dry-run") == 0
    assert "Limbo" in capsys.readouterr().out
    assert not (vault / "Projects/Software/Limbo").exists()


def test_cli_project_new_creates(tmp_path):
    vault = _vault_with_projects(tmp_path)
    assert run_cli("project", "new", "Limbo", "--vault", str(vault), "--yes") == 0
    assert (vault / "Projects/Software/Limbo/00 Overview.md").is_file()


def test_validate_project_checks_without_writing(tmp_path):
    vault = _vault_with_projects(tmp_path)
    assert validate_project(vault, "Limbo", REAL_MODULES) == "Projects/Software/Limbo"
    assert not (vault / "Projects/Software/Limbo").exists()


def test_cli_dry_run_fails_when_module_missing(tmp_path, capsys):
    vault = _vault_core_only(tmp_path)
    capsys.readouterr()
    assert run_cli("project", "new", "Limbo", "--vault", str(vault), "--dry-run") == 1
    captured = capsys.readouterr()
    assert "projects-software" in captured.err
    assert "would create" not in captured.out


def test_cli_dry_run_fails_on_path_name(tmp_path, capsys):
    vault = _vault_with_projects(tmp_path)
    capsys.readouterr()
    assert run_cli("project", "new", "a/b", "--vault", str(vault), "--dry-run") == 1
    captured = capsys.readouterr()
    assert "single folder name" in captured.err
    assert "would create" not in captured.out


def test_cli_dry_run_fails_when_project_exists(tmp_path, capsys):
    vault = _vault_with_projects(tmp_path)
    scaffold_project(vault, "Limbo", REAL_MODULES, today="2026-06-14")
    capsys.readouterr()
    assert run_cli("project", "new", "Limbo", "--vault", str(vault), "--dry-run") == 1
    captured = capsys.readouterr()
    assert "already exists" in captured.err
    assert "would create" not in captured.out


def test_cli_validation_precedes_confirm(tmp_path, capsys):
    # non-interactive stdin without --yes: the validation error must fire before the
    # confirm gate would raise its "pass --yes" error
    vault = _vault_core_only(tmp_path)
    capsys.readouterr()
    assert run_cli("project", "new", "Limbo", "--vault", str(vault)) == 1
    err = capsys.readouterr().err
    assert "projects-software" in err
    assert "--yes" not in err

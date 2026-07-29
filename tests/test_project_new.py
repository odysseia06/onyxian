"""onyxian new / project new: standalone scaffolds, never-clobber, fresh date, untracked."""

import pytest
from conftest import REAL_MODULES, make_config, run_cli, write_module

from onyxian.configio import render_config_text
from onyxian.errors import OnyxianError
from onyxian.lockio import load_lock
from onyxian.scaffold import run_scaffold, validate_scaffold


def _vault_with(tmp_path, *mods):
    answers = tmp_path / "a.yaml"
    answers.write_text(f"modules: [core{''.join(', ' + m for m in mods)}]\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(answers), "--yes") == 0
    return vault


def test_scaffold_creates_overview_and_dirs(tmp_path):
    vault = _vault_with(tmp_path, "projects-software")
    created = run_scaffold(vault, "project", "Limbo", REAL_MODULES, today="2026-06-14")
    assert created == "Projects/Software/Limbo"
    assert (vault / "Projects/Software/Limbo/00 Overview.md").is_file()
    for d in ("Devlog", "Tasks", "Research", "Assets"):
        assert (vault / "Projects/Software/Limbo" / d).is_dir()
    overview = (vault / "Projects/Software/Limbo/00 Overview.md").read_text(encoding="utf-8")
    assert "2026-06-14" in overview  # fresh date, not the pinned-seed 2026-01-01
    assert "{{" not in overview  # placeholders resolved


def test_new_course_repoints_the_exam_base(tmp_path):
    vault = _vault_with(tmp_path, "academic")
    created = run_scaffold(vault, "course", "CS-410", REAL_MODULES, today="2026-06-14")
    assert created == "Academic/Courses/CS-410"
    course = vault / "Academic/Courses/CS-410"
    for d in ("Lectures", "Assignments", "Exam-Prep", "Readings", "Notes", "Assets"):
        assert (course / d).is_dir()
    assert "2026-06-14" in (course / "00 Overview.md").read_text(encoding="utf-8")
    base = (course / "Exam-Prep/Exam-Study.base").read_text(encoding="utf-8")
    assert 'file.inFolder("Academic/Courses/CS-410/Exam-Prep")' in base
    assert "_Course-Template" not in base  # the engine repointed it; no manual edit left
    # the copy is the user's content, never ledgered
    assert load_lock(vault).get("Academic/Courses/CS-410/Exam-Prep/Exam-Study.base") is None


def test_new_piece_scaffolds_without_declared_subfolders(tmp_path):
    vault = _vault_with(tmp_path, "music")
    created = run_scaffold(vault, "piece", "Nocturne", REAL_MODULES, today="2026-06-14")
    assert created == "Music/Projects/Nocturne"
    assert (vault / "Music/Projects/Nocturne/00 Overview.md").is_file()
    assert (vault / "Music/Projects/Nocturne/04 Decisions.md").is_file()


def test_scaffold_refuses_existing(tmp_path):
    vault = _vault_with(tmp_path, "projects-software")
    run_scaffold(vault, "project", "Limbo", REAL_MODULES, today="2026-06-14")
    with pytest.raises(OnyxianError, match="already exists"):
        run_scaffold(vault, "project", "Limbo", REAL_MODULES, today="2026-06-14")


def test_scaffold_rejects_unsafe_name(tmp_path):
    vault = _vault_with(tmp_path, "projects-software")
    with pytest.raises(OnyxianError):
        run_scaffold(vault, "project", "../escape", REAL_MODULES, today="2026-06-14")
    with pytest.raises(OnyxianError):
        run_scaffold(vault, "project", "a/b", REAL_MODULES, today="2026-06-14")


def test_scaffold_does_not_lock_track_the_project(tmp_path):
    vault = _vault_with(tmp_path, "projects-software")
    run_scaffold(vault, "project", "Limbo", REAL_MODULES, today="2026-06-14")
    lock = load_lock(vault)
    assert lock.get("Projects/Software/Limbo/00 Overview.md") is None  # untracked


def test_cli_project_new_dry_run_writes_nothing(tmp_path, capsys):
    vault = _vault_with(tmp_path, "projects-software")
    capsys.readouterr()
    assert run_cli("project", "new", "Limbo", "--vault", str(vault), "--dry-run") == 0
    assert "Limbo" in capsys.readouterr().out
    assert not (vault / "Projects/Software/Limbo").exists()


def test_cli_project_new_creates(tmp_path):
    vault = _vault_with(tmp_path, "projects-software")
    assert run_cli("project", "new", "Limbo", "--vault", str(vault), "--yes") == 0
    assert (vault / "Projects/Software/Limbo/00 Overview.md").is_file()


def test_cli_new_game_creates(tmp_path):
    vault = _vault_with(tmp_path, "projects-gamedev")
    assert run_cli("new", "game", "Limbo", "--vault", str(vault), "--yes") == 0
    assert (vault / "Projects/Game-Dev/Limbo/01 Vision.md").is_file()
    assert (vault / "Projects/Game-Dev/Limbo/Mechanics").is_dir()


def test_validate_scaffold_checks_without_writing(tmp_path):
    vault = _vault_with(tmp_path, "projects-software")
    created = validate_scaffold(vault, "project", "Limbo", REAL_MODULES, today="2026-06-14")
    assert created == "Projects/Software/Limbo"
    assert not (vault / "Projects/Software/Limbo").exists()


def test_cli_dry_run_fails_when_module_missing(tmp_path, capsys):
    vault = _vault_with(tmp_path)
    capsys.readouterr()
    assert run_cli("project", "new", "Limbo", "--vault", str(vault), "--dry-run") == 1
    captured = capsys.readouterr()
    assert "projects-software" in captured.err
    assert "would create" not in captured.out


def test_cli_scaffold_from_disabled_module_names_it(tmp_path, capsys):
    vault = _vault_with(tmp_path)
    capsys.readouterr()
    assert run_cli("new", "course", "CS-410", "--vault", str(vault), "--dry-run") == 1
    err = capsys.readouterr().err
    assert "onyxian add academic" in err


def test_scaffold_provided_twice_is_an_error(tmp_path, synth_root):
    for mod, root in (("alpha", "Alpha"), ("beta", "Beta")):
        write_module(
            synth_root,
            mod,
            variables=[{"key": "root", "prompt": "Root", "default": root}],
            folders=["{{root}}/_T/Sub"],
            scaffolds=[{"name": "thing", "source": "{{root}}/_T"}],
        )
    vault = tmp_path / "vault"
    (vault / ".vault").mkdir(parents=True)
    config = make_config({"alpha": {"version": "0.1.0"}, "beta": {"version": "0.1.0"}})
    (vault / ".vault" / "config.yaml").write_text(render_config_text(config), encoding="utf-8")
    with pytest.raises(OnyxianError, match="more than one enabled module"):
        run_scaffold(vault, "thing", "X", synth_root, today="2026-06-14")


def test_cli_unknown_scaffold_lists_available(tmp_path, capsys):
    vault = _vault_with(tmp_path, "academic")
    capsys.readouterr()
    assert run_cli("new", "bogus", "X", "--vault", str(vault), "--dry-run") == 1
    err = capsys.readouterr().err
    assert "bogus" in err
    assert "course" in err  # the enabled scaffolds are listed


def test_cli_dry_run_fails_on_path_name(tmp_path, capsys):
    vault = _vault_with(tmp_path, "projects-software")
    capsys.readouterr()
    assert run_cli("project", "new", "a/b", "--vault", str(vault), "--dry-run") == 1
    captured = capsys.readouterr()
    assert "single folder name" in captured.err
    assert "would create" not in captured.out


def test_cli_dry_run_fails_when_project_exists(tmp_path, capsys):
    vault = _vault_with(tmp_path, "projects-software")
    run_scaffold(vault, "project", "Limbo", REAL_MODULES, today="2026-06-14")
    capsys.readouterr()
    assert run_cli("project", "new", "Limbo", "--vault", str(vault), "--dry-run") == 1
    captured = capsys.readouterr()
    assert "already exists" in captured.err
    assert "would create" not in captured.out


def test_cli_validation_precedes_confirm(tmp_path, capsys):
    # non-interactive stdin without --yes: the validation error must fire before the
    # confirm gate would raise its "pass --yes" error
    vault = _vault_with(tmp_path)
    capsys.readouterr()
    assert run_cli("project", "new", "Limbo", "--vault", str(vault)) == 1
    err = capsys.readouterr().err
    assert "projects-software" in err
    assert "--yes" not in err

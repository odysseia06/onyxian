"""The real M2 modules, end to end: install, render, style, idempotence (KICKSTART.md §14 M2)."""

import pytest

from conftest import REAL_MODULES, run_cli, tree_hashes
from onyx.manifests import load_manifest


@pytest.fixture
def full_vault(tmp_path):
    answers = tmp_path / "answers.yaml"
    answers.write_text(
        "modules:\n  daily-notes: {}\n  academic: {}\n  fitness: {}\n", encoding="utf-8"
    )
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(answers), "--yes") == 0
    return vault


def test_all_three_modules_load_with_their_surface():
    for name, skill, agent in (
        ("daily-notes", "daily-notes", "daily-planner"),
        ("academic", "exam-prep", "study-coach"),
        ("fitness", "fitness-review", "fitness-coach"),
    ):
        manifest = load_manifest(REAL_MODULES / name)
        assert [s.id for s in manifest.skills] == [skill]
        assert [a.name for a in manifest.agents] == [agent]
    fitness = load_manifest(REAL_MODULES / "fitness")
    assert len(fitness.templates) == 14
    assert len(fitness.seeds) == 4
    assert fitness.agents[0].disclaimer  # §17.4: the disclaimer is baked into the definition


def test_full_vault_is_healthy_and_converged(full_vault, capsys):
    assert run_cli("doctor", "--vault", str(full_vault)) == 0
    before = tree_hashes(full_vault)
    assert run_cli("apply", "--vault", str(full_vault), "--yes") == 0
    assert tree_hashes(full_vault) == before  # P3 holds across the whole M2 surface


def test_no_unrendered_placeholders_outside_static_skills(full_vault):
    offenders = []
    for path in full_vault.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(full_vault).as_posix()
        if rel.startswith(".claude/skills/"):
            continue  # skills are byte-copied and may document {{...}} on purpose
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "{{" in text:
            offenders.append(rel)
    assert not offenders, f"unrendered placeholders in: {offenders}"


def test_rendered_agents_carry_resolved_scopes(full_vault):
    study = (full_vault / ".claude" / "agents" / "study-coach.md").read_text(encoding="utf-8")
    assert "- `Academic/Courses/*/Exam-Prep/**`" in study
    assert "- `Daily-Notes/**`" in study  # requires: daily-notes, which is enabled
    coach = (full_vault / ".claude" / "agents" / "fitness-coach.md").read_text(encoding="utf-8")
    assert "Not medical advice" in coach
    assert "Fitness/Nutrition/Strategy.md" in coach


def test_fitness_without_daily_notes_drops_the_cross_scope(tmp_path):
    answers = tmp_path / "answers.yaml"
    answers.write_text("modules:\n  fitness: {}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(answers), "--yes") == 0
    coach = (vault / ".claude" / "agents" / "fitness-coach.md").read_text(encoding="utf-8")
    assert "Daily-Notes" not in coach


def test_kebab_style_yields_a_consistent_tree(tmp_path):
    answers = tmp_path / "answers.yaml"
    answers.write_text(
        "naming: { folder_style: kebab-case }\nmodules:\n  fitness: {}\n  daily-notes: {}\n",
        encoding="utf-8",
    )
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(answers), "--yes") == 0
    # Styled default root + styled literal segments: no mixed-case seams.
    # (Windows paths are case-insensitive, so compare real on-disk names.)
    top = {p.name for p in vault.iterdir() if p.is_dir()}
    assert {"fitness", "daily-notes", "templates"} <= top
    assert "Fitness" not in top
    inner = {p.name for p in (vault / "fitness").iterdir() if p.is_dir()}
    assert "training" in inner and "Training" not in inner
    assert (vault / "fitness" / "training" / "logs").is_dir()
    # Variable-derived content references follow: the base filter uses the styled root.
    base = (vault / "fitness" / "training" / "Training-Log.base").read_text(encoding="utf-8")
    assert 'file.hasTag("fitness/log")' in base


def test_exam_base_lands_inside_the_course_template(full_vault):
    base = (
        full_vault / "Academic" / "Courses" / "_Course-Template" / "Exam-Prep" / "Exam-Study.base"
    ).read_text(encoding="utf-8")
    assert 'file.inFolder("Academic/Courses/_Course-Template/Exam-Prep")' in base
    assert "point this filter at the new" in base  # the copy-per-course instruction survives

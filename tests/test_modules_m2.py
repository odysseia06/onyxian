"""The real M2 modules, end to end: install, render, style, idempotence (KICKSTART.md §14 M2)."""

import json

import pytest
import yaml

from conftest import REAL_MODULES, make_config, run_cli, tree_hashes
from onyx.intent import build_desired_state
from onyx.manifests import load_manifest
from onyx.repo import discover_modules
from onyx.resolve import resolve_modules


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
    for name, skills, agent in (
        ("daily-notes", ["daily-notes", "task-capture"], "daily-planner"),
        ("academic", ["exam-prep"], "study-coach"),
        ("fitness", ["fitness-review"], "fitness-coach"),
    ):
        manifest = load_manifest(REAL_MODULES / name)
        assert [s.id for s in manifest.skills] == skills
        assert [a.name for a in manifest.agents] == [agent]
    fitness = load_manifest(REAL_MODULES / "fitness")
    assert len(fitness.templates) == 14
    assert len(fitness.seeds) == 4
    assert fitness.agents[0].disclaimer  # §17.4: the disclaimer is baked into the definition


def test_task_capture_skill_is_provided_and_spec_shaped():
    manifest = load_manifest(REAL_MODULES / "daily-notes")
    assert "task-capture" in [s.id for s in manifest.skills]
    skill_md = (REAL_MODULES / "daily-notes" / "skills" / "task-capture" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert skill_md.startswith("---\n")
    meta = yaml.safe_load(skill_md.split("---\n", 2)[1])
    assert meta["name"] == "task-capture"
    assert isinstance(meta["description"], str) and len(meta["description"]) > 40


def test_full_vault_is_healthy_and_converged(full_vault, capsys):
    assert run_cli("doctor", "--vault", str(full_vault)) == 0
    before = tree_hashes(full_vault)
    assert run_cli("apply", "--vault", str(full_vault), "--yes") == 0
    assert tree_hashes(full_vault) == before  # P3 holds across the whole M2 surface


def _daily_notes_seed(granularity: str, folder_style: str) -> dict:
    config = make_config(
        {"daily-notes": {"version": "0.1.0", "vars": {"granularity": granularity}}},
        folder_style=folder_style,
    )
    manifests = resolve_modules(config, discover_modules(REAL_MODULES))
    files = build_desired_state(config, manifests).file_by_path()
    return json.loads(files[".obsidian/daily-notes.json"].content.decode("utf-8"))


@pytest.mark.parametrize(
    "granularity,fmt",
    [("YYYY/MM", "YYYY/MM/YYYY-MM-DD"), ("YYYY", "YYYY/YYYY-MM-DD"), ("flat", "YYYY-MM-DD")],
)
def test_daily_notes_seed_format_follows_granularity(granularity, fmt):
    """The seeded Daily Notes config encodes the granularity so daily:* aligns with Onyx's layout."""
    cfg = _daily_notes_seed(granularity, "Title-Case-Hyphen")
    assert cfg == {"folder": "Daily-Notes", "format": fmt, "template": "Templates/Daily/Daily Note"}


def test_daily_notes_seed_template_and_folder_follow_style():
    cfg = _daily_notes_seed("flat", "kebab-case")
    assert cfg["folder"] == "daily-notes"
    assert cfg["template"] == "templates/daily/Daily Note"


def test_daily_template_has_captured_query():
    config = make_config({"daily-notes": {"version": "0.1.0", "vars": {}}})
    manifests = resolve_modules(config, discover_modules(REAL_MODULES))
    files = build_desired_state(config, manifests).file_by_path()
    template = files["Templates/Daily/Daily Note.md"].content.decode("utf-8")
    assert "### Captured" in template
    assert "tags include #captured" in template


def test_daily_planner_agent_lists_task_capture():
    config = make_config({"daily-notes": {"version": "0.1.0", "vars": {}}})
    manifests = resolve_modules(config, discover_modules(REAL_MODULES))
    files = build_desired_state(config, manifests).file_by_path()
    agent = files[".claude/agents/daily-planner.md"].content.decode("utf-8")
    assert "- task-capture" in agent  # appears under "## Skills to consult"


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


def test_project_tasks_base_excludes_the_template():
    config = make_config({"projects-software": {"version": "0.2.0"}})
    manifests = resolve_modules(config, discover_modules(REAL_MODULES))
    files = build_desired_state(config, manifests).file_by_path()
    base = files["Projects/Software/Project-Tasks.base"].content.decode("utf-8")
    assert 'file.inFolder("Projects/Software")' in base


def test_project_steward_playbook_and_triggers():
    config = make_config({"projects-software": {"version": "0.2.0"}})
    manifests = resolve_modules(config, discover_modules(REAL_MODULES))
    files = build_desired_state(config, manifests).file_by_path()
    agent = files[".claude/agents/project-steward.md"].content.decode("utf-8")
    assert "## Operating playbook" in agent
    assert "Devlog/" in agent and "Key Decisions" in agent
    assert "property:set name=status" in agent
    assert "## Reach for this agent when you hear" in agent
    steward = next(m for m in manifests if m.name == "projects-software").agents[0]
    assert "task-capture" not in steward.skills
    assert "obsidian-cli" not in steward.skills
    assert "vault-operations" in steward.skills


def test_project_steward_has_preamble_once_and_confirm_line():
    config = make_config({"projects-software": {"version": "0.2.0"}})
    files = build_desired_state(config, resolve_modules(config, discover_modules(REAL_MODULES))).file_by_path()
    agent = files[".claude/agents/project-steward.md"].content.decode("utf-8")
    assert agent.count("## Operating the live vault") == 1
    assert "confirm in one line" in agent


def test_every_shipped_agent_declares_triggers():
    """Every agent in the bundled library is reachable by a natural phrase (routing parity)."""
    library = discover_modules(REAL_MODULES)
    missing = [f"{m.name}/{a.name}" for m in library.values() for a in m.agents if not a.triggers]
    assert not missing, f"agents without triggers: {missing}"

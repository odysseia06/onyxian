"""Applier gates: re-verify before every write; skip, never force (KICKSTART.md §8)."""

from types import SimpleNamespace

import pytest

from conftest import make_config, plan_for, write_module
from onyxian.applier import apply_plan
from onyxian.fsio import sha256_bytes
from onyxian.lockio import load_lock

PLAN_V1 = "# plan v1\n"
PLAN_V2 = "# plan v2\n"
TEMPLATE = "Templates/Demo/Plan.md"


@pytest.fixture
def world(tmp_path):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(
        modules_root,
        "demo",
        folders=["Demo-Area"],
        templates={TEMPLATE: PLAN_V1},
        seeds={"Start.md": "seed\n"},
    )
    vault = tmp_path / "vault"
    vault.mkdir()
    config = make_config({"demo": {"version": "0.1.0"}})
    return SimpleNamespace(vault=vault, modules_root=modules_root, config=config)


def plan(world):
    p, _, lock = plan_for(world.vault, world.modules_root, world.config)
    return p, lock


def template_path(world):
    return world.vault / "Templates" / "Demo" / "Plan.md"


def test_converge_writes_locks_and_persists(world):
    p, lock = plan(world)
    result = apply_plan(world.vault, p, lock)
    assert result.ok and result.lock_changed
    assert template_path(world).read_bytes() == PLAN_V1.encode()
    assert (world.vault / "Demo-Area").is_dir()
    persisted = load_lock(world.vault)
    assert persisted.get(TEMPLATE).sha256 == sha256_bytes(PLAN_V1.encode())
    assert persisted.get("Start.md").kind == "seeded"


def test_dry_run_touches_nothing(world):
    p, lock = plan(world)
    result = apply_plan(world.vault, p, lock, dry_run=True)
    assert not result.performed and not result.lock_changed
    assert list(world.vault.iterdir()) == []


def test_create_race_with_different_content_skips_and_preserves(world):
    p, lock = plan(world)
    squatter = template_path(world)
    squatter.parent.mkdir(parents=True)
    squatter.write_text("user got here first\n", encoding="utf-8")
    result = apply_plan(world.vault, p, lock)
    assert not result.ok
    assert any(a.path == TEMPLATE for a, _ in result.skipped)
    assert squatter.read_text(encoding="utf-8") == "user got here first\n"
    assert load_lock(world.vault).get(TEMPLATE) is None


def test_create_race_with_identical_content_heals_the_ledger(world):
    p, lock = plan(world)
    target = template_path(world)
    target.parent.mkdir(parents=True)
    target.write_bytes(PLAN_V1.encode())
    result = apply_plan(world.vault, p, lock)
    assert result.ok
    assert load_lock(world.vault).get(TEMPLATE).sha256 == sha256_bytes(PLAN_V1.encode())


def test_update_race_skips_when_user_edits_between_plan_and_apply(world):
    p, lock = plan(world)
    apply_plan(world.vault, p, lock)
    bump = world.modules_root / "demo" / "assets" / "Templates" / "Demo" / "Plan.md"
    bump.write_text(PLAN_V2, encoding="utf-8", newline="\n")
    p2, lock2 = plan(world)  # plans an UPDATE against a clean file
    template_path(world).write_text("edited right now\n", encoding="utf-8")
    result = apply_plan(world.vault, p2, lock2)
    assert not result.ok
    assert template_path(world).read_text(encoding="utf-8") == "edited right now\n"
    assert load_lock(world.vault).get(TEMPLATE).sha256 == sha256_bytes(PLAN_V1.encode())


def test_conflict_writes_sibling_and_leaves_original(world):
    p, lock = plan(world)
    apply_plan(world.vault, p, lock)
    template_path(world).write_text("customized\n", encoding="utf-8")
    bump = world.modules_root / "demo" / "assets" / "Templates" / "Demo" / "Plan.md"
    bump.write_text(PLAN_V2, encoding="utf-8", newline="\n")
    p2, lock2 = plan(world)
    result = apply_plan(world.vault, p2, lock2)
    assert result.ok
    assert template_path(world).read_text(encoding="utf-8") == "customized\n"
    sibling = template_path(world).with_name("Plan.md.new")
    assert sibling.read_bytes() == PLAN_V2.encode()
    persisted = load_lock(world.vault)
    assert persisted.get(TEMPLATE).sha256 == sha256_bytes(PLAN_V1.encode())  # original entry untouched
    assert persisted.get(TEMPLATE + ".new").sha256 == sha256_bytes(PLAN_V2.encode())


def test_report_actions_are_never_executed(world):
    user_file = world.vault / "Start.md"
    user_file.write_text("the user's file\n", encoding="utf-8")
    p, lock = plan(world)
    result = apply_plan(world.vault, p, lock)
    assert result.ok  # blocked items are reports, not failures of apply
    assert user_file.read_text(encoding="utf-8") == "the user's file\n"
    assert load_lock(world.vault).get("Start.md") is None

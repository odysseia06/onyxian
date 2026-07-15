"""The §8 write contract as a decision matrix — every branch pinned by a test."""

from types import SimpleNamespace

import pytest
from conftest import make_config, plan_for, write_module

from onyxian.applier import apply_plan
from onyxian.planner import (
    BLOCKED,
    CONFLICT_NEW,
    CREATE,
    CREATE_DIR,
    ORPHANED,
    RELOCK,
    RESTORE,
    STALE,
    UPDATE,
)

PLAN_V1 = "# plan v1\n"
PLAN_V2 = "# plan v2 (improved)\n"
SEED = "seed content\n"
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
        seeds={"Start.md": SEED},
    )
    vault = tmp_path / "vault"
    vault.mkdir()
    config = make_config({"demo": {"version": "0.1.0"}})
    return SimpleNamespace(vault=vault, modules_root=modules_root, config=config)


def plan(world):
    p, _, lock = plan_for(world.vault, world.modules_root, world.config)
    return p, lock


def converge(world):
    p, lock = plan(world)
    result = apply_plan(world.vault, p, lock)
    assert result.ok
    return result


def actions_by_type(p):
    out = {}
    for action in p.actions:
        out.setdefault(action.type, []).append(action)
    return out


def bump_asset(world, content=PLAN_V2):
    asset = world.modules_root / "demo" / "assets" / "Templates" / "Demo" / "Plan.md"
    asset.write_text(content, encoding="utf-8", newline="\n")


def test_fresh_vault_plans_creates_only(world):
    p, _ = plan(world)
    by_type = actions_by_type(p)
    assert [a.path for a in by_type[CREATE_DIR]] == ["Demo-Area"]
    assert sorted(a.path for a in by_type[CREATE]) == [
        ".claude/onyxian.md",
        "CLAUDE.md",
        "Onyxian Assistant.md",
        "Start-Here.md",
        "Start.md",
        TEMPLATE,
    ]
    assert set(by_type) == {CREATE_DIR, CREATE}


def test_converged_vault_plans_nothing(world):
    converge(world)
    p, _ = plan(world)
    assert p.is_empty and not p.reports
    assert p.noops.get("dir_exists") == 1
    assert p.noops.get("seed_done") == 2  # Start.md and the seeded CLAUDE.md wrapper
    assert (
        p.noops.get("up_to_date") == 4
    )  # demo template, Start-Here, Onyxian Assistant.md, and the .claude/onyxian.md digest


def test_untracked_identical_file_is_claimed_not_rewritten(world):
    target = world.vault / "Templates" / "Demo" / "Plan.md"
    target.parent.mkdir(parents=True)
    target.write_text(PLAN_V1, encoding="utf-8", newline="\n")
    p, _ = plan(world)
    assert [a.path for a in actions_by_type(p)[RELOCK]] == [TEMPLATE]


def test_untracked_different_file_is_blocked_forever(world):
    """User files: the engine must never write to them. There is no override flag (§8.2)."""
    target = world.vault / "Start.md"
    target.write_text("the user's own start note\n", encoding="utf-8")
    p, lock = plan(world)
    blocked = actions_by_type(p)[BLOCKED]
    assert [a.path for a in blocked] == ["Start.md"]
    apply_plan(world.vault, p, lock)
    assert target.read_text(encoding="utf-8") == "the user's own start note\n"


def test_deleted_seed_is_never_recreated(world):
    converge(world)
    (world.vault / "Start.md").unlink()
    p, _ = plan(world)
    assert p.is_empty
    assert p.noops.get("seed_done") == 2  # the deleted Start.md and the seeded CLAUDE.md, both done


def test_modified_seed_is_left_alone(world):
    converge(world)
    (world.vault / "Start.md").write_text("mine now\n", encoding="utf-8")
    p, _ = plan(world)
    assert p.is_empty


def test_deleted_managed_file_is_restored(world):
    converge(world)
    (world.vault / "Templates" / "Demo" / "Plan.md").unlink()
    p, _ = plan(world)
    assert [a.path for a in actions_by_type(p)[RESTORE]] == [TEMPLATE]


def test_user_modified_managed_with_unchanged_intent_is_a_noop(world):
    converge(world)
    (world.vault / "Templates" / "Demo" / "Plan.md").write_text("customized\n", encoding="utf-8")
    p, _ = plan(world)
    assert p.is_empty
    assert p.noops.get("user_modified_up_to_date") == 1


def test_clean_managed_with_new_intent_is_updated(world):
    converge(world)
    bump_asset(world)
    p, _ = plan(world)
    assert [a.path for a in actions_by_type(p)[UPDATE]] == [TEMPLATE]


def test_dirty_managed_with_new_intent_conflicts_to_new_sibling(world):
    converge(world)
    (world.vault / "Templates" / "Demo" / "Plan.md").write_text("customized\n", encoding="utf-8")
    bump_asset(world)
    p, _ = plan(world)
    conflicts = actions_by_type(p)[CONFLICT_NEW]
    assert [(a.path, a.write_path) for a in conflicts] == [(TEMPLATE, TEMPLATE + ".new")]


def test_user_edit_matching_new_intent_relocks_without_writing(world):
    converge(world)
    bump_asset(world)
    (world.vault / "Templates" / "Demo" / "Plan.md").write_text(
        PLAN_V2, encoding="utf-8", newline="\n"
    )
    p, _ = plan(world)
    assert [a.path for a in actions_by_type(p)[RELOCK]] == [TEMPLATE]


def test_file_squatting_on_a_planned_folder_is_blocked(world):
    (world.vault / "Demo-Area").write_text("not a folder\n", encoding="utf-8")
    p, _ = plan(world)
    blocked = actions_by_type(p)[BLOCKED]
    assert "Demo-Area" in [a.path for a in blocked]


def test_disabled_module_entries_are_reported_orphaned_never_deleted(world):
    converge(world)
    world.config = make_config({})  # demo disabled; only core remains
    p, _ = plan(world)
    orphaned = actions_by_type(p)[ORPHANED]
    assert sorted(a.path for a in orphaned) == ["Start.md", TEMPLATE]
    # The only write is the regenerated Start-Here reflecting the shrunken module set;
    # nothing belonging to the disabled module is ever deleted by plan/apply.
    assert [(a.type, a.path) for a in p.mutating] == [(UPDATE, "Start-Here.md")]
    assert (world.vault / "Templates" / "Demo" / "Plan.md").exists()


def test_dropped_asset_is_reported_stale(world):
    converge(world)
    write_module(world.modules_root, "demo", folders=["Demo-Area"], seeds={"Start.md": SEED})
    p, _ = plan(world)
    stale = actions_by_type(p)[STALE]
    assert [a.path for a in stale] == [TEMPLATE]
    assert p.is_empty


def test_conflict_cycle_reaches_steady_state(world):
    """conflict -> apply -> empty plan; the pending *.new never re-plans (P3)."""
    converge(world)
    (world.vault / "Templates" / "Demo" / "Plan.md").write_text("customized\n", encoding="utf-8")
    bump_asset(world)
    p, lock = plan(world)
    assert apply_plan(world.vault, p, lock).ok
    p2, _ = plan(world)
    assert p2.is_empty and not p2.reports
    # The delivered sibling is exempt from stale reporting.
    assert (world.vault / "Templates" / "Demo" / "Plan.md.new").read_text(
        encoding="utf-8"
    ) == PLAN_V2


def test_deleted_pending_sibling_is_redelivered(world):
    converge(world)
    (world.vault / "Templates" / "Demo" / "Plan.md").write_text("customized\n", encoding="utf-8")
    bump_asset(world)
    p, lock = plan(world)
    apply_plan(world.vault, p, lock)
    (world.vault / "Templates" / "Demo" / "Plan.md.new").unlink()
    p2, _ = plan(world)
    assert [a.write_path for a in actions_by_type(p2)[CONFLICT_NEW]] == [TEMPLATE + ".new"]


def test_user_edited_sibling_is_blocked(world):
    converge(world)
    (world.vault / "Templates" / "Demo" / "Plan.md").write_text("customized\n", encoding="utf-8")
    bump_asset(world)
    p, lock = plan(world)
    apply_plan(world.vault, p, lock)
    (world.vault / "Templates" / "Demo" / "Plan.md.new").write_text(
        "edited the offer\n", encoding="utf-8"
    )
    bump_asset(world, "# plan v3\n")
    p2, _ = plan(world)
    blocked = actions_by_type(p2)[BLOCKED]
    assert [a.write_path for a in blocked] == [TEMPLATE + ".new"]


def decline_current_offer(world):
    """The keep-mine ledger effect (issue #4): converge, customize, ship v2,
    then record the shipped sha as declined on the original's row."""
    from dataclasses import replace

    from onyxian.lockio import save_lock

    converge(world)
    (world.vault / "Templates" / "Demo" / "Plan.md").write_text("customized\n", encoding="utf-8")
    bump_asset(world)
    p, lock = plan(world)
    intent = actions_by_type(p)[CONFLICT_NEW][0].intent  # the offer exists before the decline
    lock.put(replace(lock.get(TEMPLATE), declined=intent.sha256))
    save_lock(world.vault, lock)


def test_declined_version_is_not_redelivered(world):
    """The inverse of test_deleted_pending_sibling_is_redelivered: after keep-mine
    (sibling gone, decline recorded) the offer must NOT come back."""
    decline_current_offer(world)
    p, _ = plan(world)
    assert p.is_empty and not p.reports
    assert p.noops.get("declined_current_version") == 1


def test_decline_expires_when_shipped_content_changes(world):
    """The decline is per-version: different shipped bytes resume the offer."""
    decline_current_offer(world)
    bump_asset(world, "# plan v3\n")
    p, _ = plan(world)
    assert [a.write_path for a in actions_by_type(p)[CONFLICT_NEW]] == [TEMPLATE + ".new"]


def test_preexisting_unmanaged_file_at_new_path_blocks_delivery(world):
    """A user file already sitting at `<path>.new` — never locked, never delivered —
    must block the sibling write outright (§8.3); no conflict copy is planned."""
    converge(world)
    (world.vault / "Templates" / "Demo" / "Plan.md").write_text("customized\n", encoding="utf-8")
    sibling = world.vault / "Templates" / "Demo" / "Plan.md.new"
    sibling.write_text("the user's own scratch file\n", encoding="utf-8")
    bump_asset(world)
    p, lock = plan(world)
    by_type = actions_by_type(p)
    assert [(a.path, a.write_path) for a in by_type[BLOCKED]] == [(TEMPLATE, TEMPLATE + ".new")]
    assert "unmanaged" in by_type[BLOCKED][0].detail
    assert CONFLICT_NEW not in by_type
    apply_plan(world.vault, p, lock)
    assert sibling.read_text(encoding="utf-8") == "the user's own scratch file\n"

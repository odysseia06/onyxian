"""The §8 write contract as a decision matrix — every branch pinned by a test."""

from types import SimpleNamespace

import pytest
from conftest import can_symlink, make_config, plan_for, write_module

from onyxian.applier import apply_plan
from onyxian.errors import PathError
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
    Action,
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
    out: dict[str, list[Action]] = {}
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


def test_disabled_module_managed_entries_are_orphaned_but_seed_ownership_is_retained(world):
    converge(world)
    world.config = make_config({})  # demo disabled; only core remains
    p, _ = plan(world)
    orphaned = actions_by_type(p)[ORPHANED]
    assert [a.path for a in orphaned] == [TEMPLATE]
    # The only write is the regenerated Start-Here reflecting the shrunken module set;
    # nothing belonging to the disabled module is ever deleted by plan/apply. The
    # seed row stays silent so a later re-enable remembers that the user owns it.
    assert [(a.type, a.path) for a in p.mutating] == [(UPDATE, "Start-Here.md")]
    assert (world.vault / "Templates" / "Demo" / "Plan.md").exists()


def test_retained_seed_ownership_blocks_a_different_module_at_the_same_path(world):
    converge(world)
    write_module(world.modules_root, "other", seeds={"Start.md": "other seed\n"})
    world.config = make_config({"other": {"version": "0.1.0"}})

    p, _ = plan(world)

    blocked = [a for a in actions_by_type(p)[BLOCKED] if a.path == "Start.md"]
    assert len(blocked) == 1
    assert "user-owned seed from module 'demo'" in blocked[0].detail


def test_dropped_asset_is_reported_stale(world):
    converge(world)
    write_module(world.modules_root, "demo", folders=["Demo-Area"], seeds={"Start.md": SEED})
    p, _ = plan(world)
    stale = actions_by_type(p)[STALE]
    assert [a.path for a in stale] == [TEMPLATE]
    assert p.is_empty


def release_renamed_asset(world, new_path="Templates/Demo/Renamed.md", content=PLAN_V2):
    write_module(
        world.modules_root,
        "demo",
        version="0.2.0",
        folders=["Demo-Area"],
        templates={new_path: content},
        seeds={"Start.md": SEED},
        renames={TEMPLATE: new_path},
    )
    world.config = make_config({"demo": {"version": "0.2.0"}})
    return new_path


def test_declared_rename_plans_destination_and_old_path_cleanup(world):
    converge(world)
    renamed = release_renamed_asset(world)

    p, _ = plan(world)
    by_type = actions_by_type(p)

    assert renamed in [a.path for a in by_type[CREATE]]
    assert [(a.path, a.write_path) for a in by_type["rename"]] == [(TEMPLATE, renamed)]
    assert TEMPLATE not in [a.path for a in by_type.get(STALE, [])]


def test_declared_rename_leaves_a_modified_old_file_stale(world):
    converge(world)
    (world.vault / "Templates" / "Demo" / "Plan.md").write_text("customized\n", encoding="utf-8")
    renamed = release_renamed_asset(world)

    p, _ = plan(world)
    by_type = actions_by_type(p)

    assert renamed in [a.path for a in by_type[CREATE]]
    assert "rename" not in by_type
    stale = [a for a in by_type[STALE] if a.path == TEMPLATE]
    assert len(stale) == 1
    assert renamed in stale[0].detail and "modified" in stale[0].detail


def test_declared_case_only_rename_blocks_when_old_file_is_modified(world):
    converge(world)
    old = world.vault / "Templates" / "Demo" / "Plan.md"
    old.write_text("customized\n", encoding="utf-8")
    renamed = release_renamed_asset(world, "Templates/Demo/plan.md")

    p, _ = plan(world)
    by_type = actions_by_type(p)

    assert "rename" not in by_type
    blocked = [a for a in by_type[BLOCKED] if a.path == renamed]
    assert len(blocked) == 1
    assert TEMPLATE in blocked[0].detail and "cannot coexist portably" in blocked[0].detail
    stale = [a for a in by_type[STALE] if a.path == TEMPLATE]
    assert len(stale) == 1 and "modified" in stale[0].detail
    assert old.read_text(encoding="utf-8") == "customized\n"


def test_declared_case_only_rename_stays_stale_when_user_edit_matches_new_bytes(world):
    converge(world)
    old = world.vault / "Templates" / "Demo" / "Plan.md"
    old.write_bytes(PLAN_V2.encode())
    renamed = release_renamed_asset(world, "Templates/Demo/plan.md")

    p, _ = plan(world)
    by_type = actions_by_type(p)

    assert "rename" not in by_type
    assert any(a.path == renamed for a in by_type[BLOCKED])
    assert any(a.path == TEMPLATE and "modified" in a.detail for a in by_type[STALE])


def test_declared_case_aliasing_rename_blocks_an_unmanaged_destination(world):
    converge(world)
    renamed = "templates/Demo/Renamed.md"
    destination = world.vault.joinpath(*renamed.split("/"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("user file\n", encoding="utf-8")
    release_renamed_asset(world, renamed)

    p, _ = plan(world)
    by_type = actions_by_type(p)

    assert "rename" not in by_type
    blocked = [a for a in by_type[BLOCKED] if a.path == renamed]
    assert len(blocked) == 1
    assert "unmanaged file" in blocked[0].detail
    stale = [a for a in by_type[STALE] if a.path == TEMPLATE]
    assert len(stale) == 1 and renamed in stale[0].detail
    assert destination.read_text(encoding="utf-8") == "user file\n"


def test_case_only_managed_path_rename_is_rejected(world):
    """#56: desired and ledger spellings cannot alias on two of the three CI OSes."""
    converge(world)
    renamed = "Templates/Demo/plan.md"
    write_module(
        world.modules_root,
        "demo",
        version="0.2.0",
        templates={renamed: PLAN_V1},
    )
    world.config = make_config({"demo": {"version": "0.2.0"}})

    with pytest.raises(PathError) as exc:
        plan(world)

    message = str(exc.value)
    assert TEMPLATE in message and renamed in message
    assert "case-insensitive filesystem" in message


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


def test_decline_expires_when_the_customization_is_reverted(world):
    """#70: a decline protects a customization, not a version pin. Revert the file to
    its ledgered bytes and the clean-update branch takes over — nothing left to keep."""
    decline_current_offer(world)
    (world.vault / "Templates" / "Demo" / "Plan.md").write_text(
        PLAN_V1, encoding="utf-8", newline="\n"
    )
    p, _ = plan(world)
    assert [a.path for a in actions_by_type(p)[UPDATE]] == [TEMPLATE]


def test_decline_expires_when_shipped_content_changes(world):
    """The decline is per-version: different shipped bytes resume the offer."""
    decline_current_offer(world)
    bump_asset(world, "# plan v3\n")
    p, _ = plan(world)
    assert [a.write_path for a in actions_by_type(p)[CONFLICT_NEW]] == [TEMPLATE + ".new"]


# Symlinks (issue #53): content hashes follow a link while os.replace swaps out
# the link itself, so a symlink anywhere on a target path is blocked, never written.


def _require_symlinks(world):
    if not can_symlink(world.vault):
        pytest.skip("filesystem does not permit symlink creation")


def test_symlink_to_identical_content_is_blocked_not_relocked(world):
    """Relocking a link would let the next update replace it with a regular
    file, silently cutting the real target off from updates."""
    _require_symlinks(world)
    elsewhere = world.vault.parent / "real-plan.md"
    elsewhere.write_text(PLAN_V1, encoding="utf-8", newline="\n")
    target = world.vault / "Templates" / "Demo" / "Plan.md"
    target.parent.mkdir(parents=True)
    target.symlink_to(elsewhere)
    p, _ = plan(world)
    by_type = actions_by_type(p)
    blocked = [a for a in by_type[BLOCKED] if a.path == TEMPLATE]
    assert blocked and "symlink" in blocked[0].detail
    assert RELOCK not in by_type


def test_managed_path_replaced_by_symlink_is_blocked_and_survives_apply(world):
    converge(world)
    _require_symlinks(world)
    elsewhere = world.vault.parent / "real-plan.md"
    elsewhere.write_text(PLAN_V1, encoding="utf-8", newline="\n")
    target = world.vault / "Templates" / "Demo" / "Plan.md"
    target.unlink()
    target.symlink_to(elsewhere)
    bump_asset(world)
    p, lock = plan(world)
    by_type = actions_by_type(p)
    assert [a.path for a in by_type[BLOCKED]] == [TEMPLATE]
    assert UPDATE not in by_type and CONFLICT_NEW not in by_type
    apply_plan(world.vault, p, lock)
    assert target.is_symlink()
    assert elsewhere.read_text(encoding="utf-8") == PLAN_V1


def test_dangling_symlink_at_create_target_is_blocked(world):
    """exists() follows a dangling link and reads absent; creating there would
    replace the user's link via os.replace."""
    _require_symlinks(world)
    target = world.vault / "Start.md"
    target.symlink_to(world.vault / "nowhere.md")
    p, lock = plan(world)
    by_type = actions_by_type(p)
    blocked = [a for a in by_type[BLOCKED] if a.path == "Start.md"]
    assert blocked and "symlink" in blocked[0].detail
    assert "Start.md" not in [a.path for a in by_type[CREATE]]
    apply_plan(world.vault, p, lock)
    assert target.is_symlink() and not target.exists()


def test_symlinked_folder_at_planned_dir_is_blocked(world):
    """A symlinked folder would redirect every engine write beneath it outside
    the vault root."""
    _require_symlinks(world)
    outside = world.vault.parent / "outside-area"
    outside.mkdir()
    (world.vault / "Demo-Area").symlink_to(outside, target_is_directory=True)
    p, _ = plan(world)
    by_type = actions_by_type(p)
    blocked = [a for a in by_type[BLOCKED] if a.path == "Demo-Area"]
    assert blocked and "symlink" in blocked[0].detail
    assert CREATE_DIR not in by_type
    assert p.noops.get("dir_exists") is None


def test_symlinked_parent_blocks_every_file_beneath_it(world):
    _require_symlinks(world)
    outside = world.vault.parent / "outside-templates"
    outside.mkdir()
    (world.vault / "Templates").symlink_to(outside, target_is_directory=True)
    p, lock = plan(world)
    by_type = actions_by_type(p)
    blocked = [a for a in by_type[BLOCKED] if a.path == TEMPLATE]
    assert blocked and "symlink" in blocked[0].detail and "Templates" in blocked[0].detail
    apply_plan(world.vault, p, lock)
    assert list(outside.iterdir()) == []  # nothing escaped through the link


def test_seeded_locked_path_replaced_by_symlink_stays_silent(world):
    """A seeded file is the user's outright; turning it into a link is their
    business — the engine has no write to gate and reports nothing."""
    converge(world)
    _require_symlinks(world)
    start = world.vault / "Start.md"
    elsewhere = world.vault.parent / "my-start.md"
    elsewhere.write_text("mine\n", encoding="utf-8")
    start.unlink()
    start.symlink_to(elsewhere)
    p, _ = plan(world)
    assert p.is_empty and not p.reports
    assert p.noops.get("seed_done") == 2


def test_symlinked_new_sibling_blocks_delivery(world):
    converge(world)
    _require_symlinks(world)
    (world.vault / "Templates" / "Demo" / "Plan.md").write_text("customized\n", encoding="utf-8")
    elsewhere = world.vault.parent / "scratch.md"
    elsewhere.write_text("scratch\n", encoding="utf-8")
    sibling = world.vault / "Templates" / "Demo" / "Plan.md.new"
    sibling.symlink_to(elsewhere)
    bump_asset(world)
    p, lock = plan(world)
    by_type = actions_by_type(p)
    assert [(a.path, a.write_path) for a in by_type[BLOCKED]] == [(TEMPLATE, TEMPLATE + ".new")]
    assert CONFLICT_NEW not in by_type
    apply_plan(world.vault, p, lock)
    assert sibling.is_symlink()
    assert elsewhere.read_text(encoding="utf-8") == "scratch\n"


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

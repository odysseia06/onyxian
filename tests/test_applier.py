"""Applier gates: re-verify before every write; skip, never force."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import can_symlink, make_config, plan_for, write_module

from onyxian.applier import apply_plan
from onyxian.fsio import move_file_atomic, sha256_bytes, write_bytes_atomic
from onyxian.lockio import load_lock
from onyxian.model import LockEntry

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
        # Weekly.md sorts after TEMPLATE, so it proves the run continued past a
        # failure there; actions are applied in sorted path order.
        seeds={"Start.md": "seed\n", "Weekly.md": "weekly\n"},
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
    template_entry = persisted.get(TEMPLATE)
    assert template_entry is not None
    assert template_entry.sha256 == sha256_bytes(PLAN_V1.encode())
    start_entry = persisted.get("Start.md")
    assert start_entry is not None
    assert start_entry.kind == "seeded"


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
    entry = load_lock(world.vault).get(TEMPLATE)
    assert entry is not None
    assert entry.sha256 == sha256_bytes(PLAN_V1.encode())


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
    entry = load_lock(world.vault).get(TEMPLATE)
    assert entry is not None
    assert entry.sha256 == sha256_bytes(PLAN_V1.encode())


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
    original_entry = persisted.get(TEMPLATE)
    assert original_entry is not None
    assert original_entry.sha256 == sha256_bytes(PLAN_V1.encode())  # original entry untouched
    new_entry = persisted.get(TEMPLATE + ".new")
    assert new_entry is not None
    assert new_entry.sha256 == sha256_bytes(PLAN_V2.encode())


def test_symlink_swapped_in_between_plan_and_apply_is_skipped(world):
    """The one race a sha recheck cannot catch: a symlink to the exact locked
    bytes hashes clean, but os.replace would destroy the link (issue #53)."""
    if not can_symlink(world.vault):
        pytest.skip("filesystem does not permit symlink creation")
    p, lock = plan(world)
    apply_plan(world.vault, p, lock)
    bump = world.modules_root / "demo" / "assets" / "Templates" / "Demo" / "Plan.md"
    bump.write_text(PLAN_V2, encoding="utf-8", newline="\n")
    p2, lock2 = plan(world)  # plans an UPDATE against a clean regular file
    elsewhere = world.vault.parent / "real-plan.md"
    elsewhere.write_text(PLAN_V1, encoding="utf-8", newline="\n")
    target = template_path(world)
    target.unlink()
    target.symlink_to(elsewhere)
    result = apply_plan(world.vault, p2, lock2)
    assert not result.ok
    assert [a.path for a, _ in result.skipped] == [TEMPLATE]
    assert "symlink" in result.skipped[0][1]
    assert target.is_symlink()
    assert elsewhere.read_text(encoding="utf-8") == PLAN_V1


def test_write_failure_skips_that_action_and_finishes_the_run(world):
    """A user *file* where a managed file needs a parent folder makes the write
    raise OSError; that must degrade to a skip, never abort the run (issue #57)."""
    (world.vault / "Templates").write_text("a user file, not a folder\n", encoding="utf-8")
    p, lock = plan(world)
    result = apply_plan(world.vault, p, lock)
    assert not result.ok
    assert [a.target for a, _ in result.skipped] == [TEMPLATE]
    assert "could not be written" in result.skipped[0][1]
    assert (world.vault / "Templates").read_text(encoding="utf-8") == "a user file, not a folder\n"
    assert load_lock(world.vault).get(TEMPLATE) is None
    # Everything the failing action stood in front of still ran and still ledgered.
    assert (world.vault / "Weekly.md").read_text(encoding="utf-8") == "weekly\n"
    assert load_lock(world.vault).get("Weekly.md") is not None


def test_ledger_save_failure_leaves_the_file_for_the_next_plan_to_relock(world, monkeypatch):
    """The applier docstring's crash claim, now that a failed save degrades: the
    bytes land, the ledger row does not, and the next plan heals it as a relock."""
    monkeypatch.setattr(
        "onyxian.applier.save_lock", lambda *a: (_ for _ in ()).throw(OSError("disk full"))
    )
    p, lock = plan(world)
    result = apply_plan(world.vault, p, lock)
    # Every file action needs the ledger, so every one of them degrades; the
    # folder actions need no save and still land.
    assert {a.target for a, _ in result.skipped} == {
        a.target for a in p.mutating if a.type != "create_dir"
    }
    assert template_path(world).read_bytes() == PLAN_V1.encode()  # bytes landed anyway
    assert not result.lock_changed
    assert load_lock(world.vault).entries == {}

    monkeypatch.undo()
    p2, lock2 = plan(world)
    assert {a.type for a in p2.mutating} == {"relock"}
    assert apply_plan(world.vault, p2, lock2).ok
    entry = load_lock(world.vault).get(TEMPLATE)
    assert entry is not None
    assert entry.sha256 == sha256_bytes(PLAN_V1.encode())


def test_create_dir_race_with_a_user_file_is_skipped(world):
    p, lock = plan(world)
    (world.vault / "Demo-Area").write_text("a user file landed here\n", encoding="utf-8")
    result = apply_plan(world.vault, p, lock)
    assert not result.ok
    assert [a.target for a, _ in result.skipped] == ["Demo-Area"]
    assert (world.vault / "Demo-Area").read_text(encoding="utf-8") == "a user file landed here\n"
    assert template_path(world).read_bytes() == PLAN_V1.encode()  # the rest still applied


def test_restore_rewrites_a_managed_file_the_user_deleted(world):
    p, lock = plan(world)
    apply_plan(world.vault, p, lock)
    template_path(world).unlink()
    p2, lock2 = plan(world)
    assert [a.type for a in p2.mutating] == ["restore"]
    assert apply_plan(world.vault, p2, lock2).ok
    assert template_path(world).read_bytes() == PLAN_V1.encode()


def release_renamed_demo(world, renamed="Templates/Demo/Renamed.md", content=PLAN_V2):
    write_module(
        world.modules_root,
        "demo",
        version="0.2.0",
        folders=["Demo-Area"],
        templates={renamed: content},
        seeds={"Start.md": "seed\n", "Weekly.md": "weekly\n"},
        renames={TEMPLATE: renamed},
    )
    world.config = make_config({"demo": {"version": "0.2.0"}})
    return renamed


def test_declared_rename_removes_clean_old_file_and_rekeys_the_lock(world):
    first, lock = plan(world)
    assert apply_plan(world.vault, first, lock).ok
    renamed = release_renamed_demo(world)

    rename_plan, rename_lock = plan(world)
    result = apply_plan(world.vault, rename_plan, rename_lock)

    assert result.ok
    assert not template_path(world).exists()
    assert (world.vault / "Templates" / "Demo" / "Renamed.md").read_bytes() == PLAN_V2.encode()
    persisted = load_lock(world.vault)
    assert persisted.get(TEMPLATE) is None
    new_entry = persisted.get(renamed)
    assert new_entry is not None and new_entry.module_version == "0.2.0"
    settled, _ = plan(world)
    assert settled.is_empty and not settled.reports


def test_declared_rename_rechecks_old_file_before_deleting(world):
    first, lock = plan(world)
    assert apply_plan(world.vault, first, lock).ok
    release_renamed_demo(world)
    rename_plan, rename_lock = plan(world)
    template_path(world).write_text("edited after review\n", encoding="utf-8")

    result = apply_plan(world.vault, rename_plan, rename_lock)

    assert not result.ok
    assert template_path(world).read_text(encoding="utf-8") == "edited after review\n"
    assert (world.vault / "Templates" / "Demo" / "Renamed.md").read_bytes() == PLAN_V2.encode()
    assert load_lock(world.vault).get(TEMPLATE) is not None
    assert any(a.type == "rename" and "modified" in reason for a, reason in result.skipped)


def test_declared_rename_retries_a_transient_delete_failure(world, monkeypatch):
    first, lock = plan(world)
    assert apply_plan(world.vault, first, lock).ok
    release_renamed_demo(world)
    rename_plan, rename_lock = plan(world)
    source = template_path(world)
    real_unlink = Path.unlink
    attempts = 0

    def transient_failure(path, *args, **kwargs):
        nonlocal attempts
        if path == source and attempts == 0:
            attempts += 1
            raise PermissionError("temporarily held")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", transient_failure)
    result = apply_plan(world.vault, rename_plan, rename_lock)

    assert result.ok
    assert attempts == 1
    assert load_lock(world.vault).get(TEMPLATE) is None


def test_declared_rename_keeps_old_file_when_destination_is_squatted_after_review(world):
    first, lock = plan(world)
    assert apply_plan(world.vault, first, lock).ok
    release_renamed_demo(world)
    rename_plan, rename_lock = plan(world)
    destination = world.vault / "Templates" / "Demo" / "Renamed.md"
    destination.write_text("user arrived first\n", encoding="utf-8")

    result = apply_plan(world.vault, rename_plan, rename_lock)

    assert not result.ok
    assert template_path(world).read_bytes() == PLAN_V1.encode()
    assert destination.read_text(encoding="utf-8") == "user arrived first\n"
    assert load_lock(world.vault).get(TEMPLATE) is not None
    assert any(
        a.type == "rename" and "destination is not ready" in reason for a, reason in result.skipped
    )


def test_declared_rename_retires_a_missing_old_lock_row_after_destination_lands(world):
    first, lock = plan(world)
    assert apply_plan(world.vault, first, lock).ok
    renamed = release_renamed_demo(world)
    rename_plan, rename_lock = plan(world)
    template_path(world).unlink()

    result = apply_plan(world.vault, rename_plan, rename_lock)

    assert result.ok
    assert load_lock(world.vault).get(TEMPLATE) is None
    assert load_lock(world.vault).get(renamed) is not None


def test_declared_case_only_rename_rekeys_without_a_colliding_lock(world):
    first, lock = plan(world)
    assert apply_plan(world.vault, first, lock).ok
    renamed = release_renamed_demo(world, "Templates/Demo/plan.md")

    rename_plan, rename_lock = plan(world)
    path_actions = [
        action
        for action in rename_plan.mutating
        if action.path == TEMPLATE or action.target == renamed
    ]
    assert [(a.type, a.path, a.write_path) for a in path_actions] == [("rename", TEMPLATE, renamed)]

    result = apply_plan(world.vault, rename_plan, rename_lock)

    assert result.ok
    destination = world.vault / "Templates" / "Demo" / "plan.md"
    assert destination.read_bytes() == PLAN_V2.encode()
    assert "plan.md" in {path.name for path in destination.parent.iterdir()}
    assert "Plan.md" not in {path.name for path in destination.parent.iterdir()}
    persisted = load_lock(world.vault)
    assert persisted.get(TEMPLATE) is None
    assert persisted.get(renamed) is not None
    settled, _ = plan(world)
    assert settled.is_empty and not settled.reports


def test_declared_case_only_rename_retries_a_transient_move_failure(world, monkeypatch):
    first, lock = plan(world)
    assert apply_plan(world.vault, first, lock).ok
    renamed = release_renamed_demo(world, "Templates/Demo/plan.md")
    rename_plan, rename_lock = plan(world)
    source = template_path(world)
    real_replace = os.replace
    attempts = 0

    def transient_failure(old, new):
        nonlocal attempts
        if old == source and attempts == 0:
            attempts += 1
            raise PermissionError("temporarily held")
        return real_replace(old, new)

    monkeypatch.setattr(os, "replace", transient_failure)
    result = apply_plan(world.vault, rename_plan, rename_lock)

    assert result.ok
    assert attempts == 1
    assert (world.vault / renamed).read_bytes() == PLAN_V2.encode()
    assert load_lock(world.vault).get(renamed) is not None


def test_declared_case_aliasing_rename_retires_a_hardlinked_old_name(world, monkeypatch):
    first, lock = plan(world)
    assert apply_plan(world.vault, first, lock).ok
    renamed = release_renamed_demo(world, "templates/Demo/Renamed.md")
    source = template_path(world)
    destination = world.vault / renamed
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError as exc:
        pytest.skip(f"filesystem does not permit hardlinks: {exc}")
    real_replace = os.replace

    def posix_same_inode_noop(old, new):
        if old == source and new == destination:
            return None
        return real_replace(old, new)

    # POSIX permits rename(old, new) to do nothing when both names identify the
    # same inode. Model that explicitly so this regression stays covered on
    # Windows, whose ReplaceFile behavior otherwise retires the source for us.
    monkeypatch.setattr(os, "replace", posix_same_inode_noop)

    rename_plan, rename_lock = plan(world)
    result = apply_plan(world.vault, rename_plan, rename_lock)

    assert result.ok
    assert not source.exists()
    assert destination.read_bytes() == PLAN_V2.encode()
    assert load_lock(world.vault).get(TEMPLATE) is None
    assert load_lock(world.vault).get(renamed) is not None


def test_declared_case_only_rename_rechecks_new_matching_bytes_as_a_user_edit(world):
    first, lock = plan(world)
    assert apply_plan(world.vault, first, lock).ok
    renamed = release_renamed_demo(world, "Templates/Demo/plan.md")
    rename_plan, rename_lock = plan(world)
    source = template_path(world)
    source.write_bytes(PLAN_V2.encode())

    result = apply_plan(world.vault, rename_plan, rename_lock)

    assert not result.ok
    assert source.read_bytes() == PLAN_V2.encode()
    assert load_lock(world.vault).get(TEMPLATE) is not None
    assert load_lock(world.vault).get(renamed) is None


def test_declared_case_only_rename_recovers_a_move_that_landed_before_the_lock_save(world):
    first, lock = plan(world)
    assert apply_plan(world.vault, first, lock).ok
    renamed = release_renamed_demo(world, "Templates/Demo/plan.md")
    source = template_path(world)
    destination = world.vault / renamed
    move_file_atomic(source, destination)
    write_bytes_atomic(destination, PLAN_V2.encode())

    recovery_plan, recovery_lock = plan(world)
    result = apply_plan(world.vault, recovery_plan, recovery_lock)

    assert result.ok
    persisted = load_lock(world.vault)
    assert persisted.get(TEMPLATE) is None
    assert persisted.get(renamed) is not None
    settled, _ = plan(world)
    assert settled.is_empty and not settled.reports


def test_declared_case_only_rename_rejects_an_unrelated_destination_row_after_review(world):
    first, lock = plan(world)
    assert apply_plan(world.vault, first, lock).ok
    renamed = release_renamed_demo(world, "Templates/Demo/plan.md")
    rename_plan, rename_lock = plan(world)
    rename_plan.actions = [action for action in rename_plan.actions if action.type == "rename"]
    del rename_lock.entries[TEMPLATE]
    rename_lock.put(
        LockEntry(
            path=renamed,
            sha256="different-state",
            module="demo",
            module_version="0.2.0",
            kind="managed",
        )
    )

    result = apply_plan(world.vault, rename_plan, rename_lock)

    assert not result.ok
    assert load_lock(world.vault).get(TEMPLATE) is not None


def test_case_aliasing_predecessor_runs_before_other_historical_sources(world):
    archive = "Templates/Demo/Archive.md"
    renamed = "Templates/Demo/plan.md"
    write_module(
        world.modules_root,
        "demo",
        folders=["Demo-Area"],
        templates={TEMPLATE: PLAN_V1, archive: "archived v1\n"},
        seeds={"Start.md": "seed\n", "Weekly.md": "weekly\n"},
    )
    first, lock = plan(world)
    assert apply_plan(world.vault, first, lock).ok
    write_module(
        world.modules_root,
        "demo",
        version="0.2.0",
        folders=["Demo-Area"],
        templates={renamed: PLAN_V2},
        seeds={"Start.md": "seed\n", "Weekly.md": "weekly\n"},
        renames={archive: renamed, TEMPLATE: renamed},
    )
    world.config = make_config({"demo": {"version": "0.2.0"}})

    rename_plan, rename_lock = plan(world)
    result = apply_plan(world.vault, rename_plan, rename_lock)

    assert result.ok
    assert not (world.vault / archive).exists()
    persisted = load_lock(world.vault)
    assert persisted.get(archive) is None
    assert persisted.get(TEMPLATE) is None
    assert persisted.get(renamed) is not None
    settled, _ = plan(world)
    assert settled.is_empty and not settled.reports


def bump_demo(world, text):
    asset = world.modules_root / "demo" / "assets" / "Templates" / "Demo" / "Plan.md"
    asset.write_text(text, encoding="utf-8", newline="\n")


def test_relock_records_a_user_edit_that_matches_the_new_version(world):
    p, lock = plan(world)
    apply_plan(world.vault, p, lock)
    bump_demo(world, PLAN_V2)
    template_path(world).write_text(PLAN_V2, encoding="utf-8", newline="\n")
    p2, lock2 = plan(world)
    assert [a.type for a in p2.mutating] == ["relock"]
    assert apply_plan(world.vault, p2, lock2).ok
    entry = load_lock(world.vault).get(TEMPLATE)
    assert entry is not None
    assert entry.sha256 == sha256_bytes(PLAN_V2.encode())


def test_relock_retires_the_new_sibling_the_user_deleted(world):
    """Conflict resolution: the user accepted the update by hand and threw the
    delivered sibling away — nothing but this branch retires its ledger row."""
    p, lock = plan(world)
    apply_plan(world.vault, p, lock)
    template_path(world).write_text("customized\n", encoding="utf-8")
    bump_demo(world, PLAN_V2)
    p2, lock2 = plan(world)
    apply_plan(world.vault, p2, lock2)  # delivers Plan.md.new
    assert load_lock(world.vault).get(TEMPLATE + ".new") is not None

    template_path(world).with_name("Plan.md.new").unlink()
    template_path(world).write_text(PLAN_V2, encoding="utf-8", newline="\n")
    p3, lock3 = plan(world)
    assert apply_plan(world.vault, p3, lock3).ok
    persisted = load_lock(world.vault)
    assert persisted.get(TEMPLATE + ".new") is None
    original = persisted.get(TEMPLATE)
    assert original is not None
    assert original.sha256 == sha256_bytes(PLAN_V2.encode())


def test_conflict_new_refreshes_the_pending_sibling_in_place(world):
    p, lock = plan(world)
    apply_plan(world.vault, p, lock)
    template_path(world).write_text("customized\n", encoding="utf-8")
    bump_demo(world, PLAN_V2)
    p2, lock2 = plan(world)
    apply_plan(world.vault, p2, lock2)

    plan_v3 = "# plan v3\n"
    bump_demo(world, plan_v3)
    p3, lock3 = plan(world)
    assert [a.type for a in p3.mutating] == ["conflict_new"]
    assert apply_plan(world.vault, p3, lock3).ok
    sibling = template_path(world).with_name("Plan.md.new")
    assert sibling.read_bytes() == plan_v3.encode()  # untouched sibling refreshed, not duplicated
    assert template_path(world).read_text(encoding="utf-8") == "customized\n"
    new_entry = load_lock(world.vault).get(TEMPLATE + ".new")
    assert new_entry is not None
    assert new_entry.sha256 == sha256_bytes(plan_v3.encode())


def test_report_actions_are_never_executed(world):
    user_file = world.vault / "Start.md"
    user_file.write_text("the user's file\n", encoding="utf-8")
    p, lock = plan(world)
    result = apply_plan(world.vault, p, lock)
    assert result.ok  # blocked items are reports, not failures of apply
    assert user_file.read_text(encoding="utf-8") == "the user's file\n"
    assert load_lock(world.vault).get("Start.md") is None

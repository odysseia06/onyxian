"""The planner: a pure diff of desired state vs lock vs disk (KICKSTART.md §8, §9.1).

This file is the §8 write contract in executable form. The decision matrix for
every desired file:

  no lock entry, nothing on disk            -> create
  no lock entry, disk bytes == desired      -> relock (claim it; identical bytes, no write)
  no lock entry, disk bytes differ          -> blocked (a user file is in the way; never write)
  seeded + same-module lock entry           -> done forever (even if the user deleted it)
  seeded + different-module lock entry      -> blocked (the original seed remains user-owned)
  managed + locked, disk missing            -> restore (framework-owned; intent says it exists)
  managed + locked, disk clean, desired same-> up to date
  managed + locked, disk clean, desired new -> update (safe overwrite; user never touched it)
  managed + locked, disk dirty, desired same-> up to date (the file is the user's until update)
  managed + locked, disk dirty, desired new -> conflict: write `<path>.new` beside it (§8.3)
  managed + locked, disk dirty, desired new,
    declined == desired sha                 -> no-op (user declined this version via
                                               `onyxian diff --keep-mine`; the offer resumes
                                               when the shipped content changes)
  managed + locked, disk dirty == desired   -> relock (user already made it match; just re-ledger)
  declared rename, old disk == old lock     -> land destination, then retire the old path
  declared rename, old disk dirty           -> leave the old path tracked and report it stale
  a symlink anywhere on the target path     -> blocked (hashes follow the link, but a write would
                                               replace the link itself; §8 checks cannot be
                                               trusted through one) — except seeded + locked,
                                               where the engine has no write left to gate

There is no flag that turns a `blocked` into a write.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .fsio import differs_only_in_line_endings_or_bom, sha256_file
from .intent import DesiredState, FileIntent
from .model import KIND_MANAGED, KIND_SEEDED, LOCATION_VAULT, Lock, LockEntry
from .paths import (
    check_casefold_unique,
    first_symlink_component,
    path_has_exact_spelling,
    paths_casefold_collide,
    to_native,
)

# Mutating action types (apply does something).
CREATE_DIR = "create_dir"
CREATE = "create"
RESTORE = "restore"
UPDATE = "update"
RELOCK = "relock"
CONFLICT_NEW = "conflict_new"
RENAME = "rename"

# Report-only action types (apply never touches these).
BLOCKED = "blocked"
ORPHANED = "orphaned"
STALE = "stale"

MUTATING_TYPES = (CREATE_DIR, CREATE, RESTORE, UPDATE, RELOCK, CONFLICT_NEW, RENAME)
REPORT_TYPES = (BLOCKED, ORPHANED, STALE)

# No-op counters (kept as numbers so `plan` can say what it checked).
NOOP_UPTODATE = "up_to_date"
NOOP_SEED_DONE = "seed_done"
NOOP_USER_MODIFIED = "user_modified_up_to_date"
NOOP_DIR_EXISTS = "dir_exists"
NOOP_DECLINED = "declined_current_version"


@dataclass(frozen=True)
class Action:
    type: str
    path: str
    module: str
    kind: str = ""
    detail: str = ""
    write_path: str = ""  # conflict sibling or declared rename destination
    intent: FileIntent | None = None
    source_entry: LockEntry | None = None  # immutable precondition for a declared rename

    @property
    def target(self) -> str:
        return self.write_path or self.path


@dataclass
class Plan:
    actions: list[Action] = field(default_factory=list)
    noops: dict[str, int] = field(default_factory=dict)

    def _count(self, key: str) -> None:
        self.noops[key] = self.noops.get(key, 0) + 1

    @property
    def mutating(self) -> list[Action]:
        return [a for a in self.actions if a.type in MUTATING_TYPES]

    @property
    def reports(self) -> list[Action]:
        return [a for a in self.actions if a.type in REPORT_TYPES]

    @property
    def is_empty(self) -> bool:
        return not self.mutating


def _symlink_detail(link: str) -> str:
    return f"a symlink sits at {link}; the engine never writes through or replaces links"


def _disk_sha(path: Path) -> str | None:
    """Hash of the file on disk, None if absent. A directory in a file's place
    is 'present but different'."""
    if path.is_file():
        return sha256_file(path)
    if path.exists():
        return "<not-a-file>"
    return None


def _same_file(first: Path, second: Path) -> bool:
    try:
        return first.is_file() and second.is_file() and os.path.samefile(first, second)
    except OSError:
        return False


def _plan_sibling_write(plan: Plan, intent: FileIntent, lock: Lock, vault_root: Path) -> None:
    """Plan the `<path>.new` write for a conflicted managed file (§8.3).

    The offer persists until the user resolves the original (accepts the new
    content, or the desired content changes again); while the delivered
    sibling matches the desired bytes, re-planning is a no-op.
    """
    new_path = intent.path + ".new"

    def make(action_type: str, detail: str = "") -> Action:
        return Action(
            action_type,
            path=intent.path,
            module=intent.module,
            kind=intent.kind,
            write_path=new_path,
            intent=intent,
            detail=detail,
        )

    # The sibling's parents were vetted via the original's path; only the final
    # segment can be a link here, and hashing through it would lie (issue #53).
    if to_native(vault_root, new_path).is_symlink():
        plan.actions.append(make(BLOCKED, _symlink_detail(new_path)))
        return

    entry = lock.get(new_path)
    disk = _disk_sha(to_native(vault_root, new_path))

    if entry is None:
        if disk is None:
            plan.actions.append(
                make(CONFLICT_NEW, "you modified the original; the new version lands beside it")
            )
        elif disk == intent.sha256:
            plan.actions.append(make(RELOCK, "*.new already present with the right content"))
        else:
            plan.actions.append(
                make(BLOCKED, f"cannot deliver update: an unmanaged file sits at {new_path}")
            )
        return
    # The sibling is already ours (locked).
    if disk == intent.sha256:
        if entry.sha256 == intent.sha256:
            plan._count(NOOP_UPTODATE)  # delivered and current; the ball is in the user's court
        else:
            plan.actions.append(make(RELOCK, "*.new already present with the right content"))
    elif disk is None or disk == entry.sha256:
        plan.actions.append(make(CONFLICT_NEW, "refreshing the pending *.new sibling"))
    else:
        plan.actions.append(
            make(BLOCKED, f"you edited {new_path} too; resolve it by hand, then re-plan")
        )


def _plan_file(plan: Plan, intent: FileIntent, lock: Lock, vault_root: Path) -> None:
    entry = lock.get(intent.path)

    def make(action_type: str, detail: str = "") -> Action:
        return Action(
            action_type,
            path=intent.path,
            module=intent.module,
            kind=intent.kind,
            intent=intent,
            detail=detail,
        )

    if entry is not None and entry.kind == KIND_SEEDED:
        if entry.module == intent.module:
            plan._count(NOOP_SEED_DONE)  # seeded once; the user owns it now, present or not
        else:
            plan.actions.append(
                make(
                    BLOCKED,
                    f"this path remains a user-owned seed from module {entry.module!r}; "
                    f"module {intent.module!r} cannot claim it",
                )
            )
        return

    # Before any content check: hashes follow a link while a write would replace
    # the link itself, so no byte comparison below can be trusted (issue #53).
    link = first_symlink_component(vault_root, intent.path)
    if link is not None:
        plan.actions.append(make(BLOCKED, _symlink_detail(link)))
        return

    disk = _disk_sha(to_native(vault_root, intent.path))

    if entry is None:
        if disk is None:
            plan.actions.append(make(CREATE))
        elif disk == intent.sha256:
            plan.actions.append(make(RELOCK, "identical content already on disk; recording it"))
        else:
            detail = "a file the engine does not own is already there; it will not be touched"
            native = to_native(vault_root, intent.path)
            try:
                cosmetic_difference = native.is_file() and differs_only_in_line_endings_or_bom(
                    native.read_bytes(), intent.content
                )
            except OSError:
                cosmetic_difference = False
            if cosmetic_difference:
                detail += (
                    "; it differs only in line endings or a byte-order mark — normalize to claim it"
                )
            plan.actions.append(
                make(
                    BLOCKED,
                    detail,
                )
            )
        return

    if disk is None:
        plan.actions.append(make(RESTORE, "managed file missing; restoring from intent"))
        return
    user_modified = disk != entry.sha256
    desired_changed = intent.sha256 != entry.sha256
    if not user_modified:
        if not desired_changed:
            plan._count(NOOP_UPTODATE)
        else:
            plan.actions.append(make(UPDATE, "unmodified since install; safe overwrite"))
    else:
        if disk == intent.sha256:
            plan.actions.append(make(RELOCK, "your edit already matches the new version"))
        elif not desired_changed:
            plan._count(NOOP_USER_MODIFIED)  # their customization stands until an update arrives
        elif entry.declined == intent.sha256:
            plan._count(NOOP_DECLINED)  # the user declined exactly this version (§8.3 exit ramp)
        else:
            _plan_sibling_write(plan, intent, lock, vault_root)


def build_plan(
    vault_root: Path, desired: DesiredState, lock: Lock, enabled_modules: set[str]
) -> Plan:
    active_rename_entries: dict[str, LockEntry] = {}
    aliasing_targets: set[str] = set()
    for rename in desired.renames:
        entry = lock.get(rename.old_path)
        if (
            entry is not None
            and entry.module == rename.module
            and entry.kind == KIND_MANAGED
            and entry.location == LOCATION_VAULT
        ):
            active_rename_entries[rename.old_path] = entry
            if paths_casefold_collide(rename.old_path, rename.new_path):
                aliasing_targets.add(rename.new_path)

    # A case-only module rename must not miss the old exact-keyed ledger row.
    # A declared rename owns that transition; every other desired-vs-ledger
    # alias still fails closed before touching the OS-specific disk view (#56).
    check_casefold_unique(
        [(intent.path, intent.module) for intent in desired.dirs]
        + [(intent.path, intent.module) for intent in desired.files]
        + [
            (entry.path, entry.module)
            for entry in lock.sorted_entries()
            if entry.path not in active_rename_entries
        ]
    )

    plan = Plan()

    for dir_intent in desired.dirs:
        native = to_native(vault_root, dir_intent.path)
        link = first_symlink_component(vault_root, dir_intent.path)
        if link is not None:
            # is_dir() follows the link, so a symlinked folder would silently
            # redirect every write beneath it outside the vault root (issue #53).
            plan.actions.append(
                Action(
                    BLOCKED,
                    path=dir_intent.path,
                    module=dir_intent.module,
                    detail=_symlink_detail(link),
                )
            )
        elif native.is_dir():
            plan._count(NOOP_DIR_EXISTS)
        elif native.exists():
            plan.actions.append(
                Action(
                    BLOCKED,
                    path=dir_intent.path,
                    module=dir_intent.module,
                    detail="a file sits where a folder should go; the engine will not touch it",
                )
            )
        else:
            plan.actions.append(Action(CREATE_DIR, path=dir_intent.path, module=dir_intent.module))

    for file_intent in desired.files:
        if file_intent.path not in aliasing_targets:
            _plan_file(plan, file_intent, lock, vault_root)

    desired_by_path = desired.file_by_path()
    rename_by_old = {rename.old_path: rename for rename in desired.renames}
    planned_renames: set[str] = set()
    rename_source_modified: set[str] = set()
    rename_destination_blocked: set[str] = set()
    for rename in desired.renames:
        entry = active_rename_entries.get(rename.old_path)
        if entry is None:
            continue
        aliases = paths_casefold_collide(rename.old_path, rename.new_path)
        source_link = first_symlink_component(vault_root, rename.old_path)
        source_sha = (
            None if source_link is not None else _disk_sha(to_native(vault_root, rename.old_path))
        )
        recovered_case_move = (
            aliases
            and source_sha == desired_by_path[rename.new_path].sha256
            and not path_has_exact_spelling(vault_root, rename.old_path)
            and path_has_exact_spelling(vault_root, rename.new_path)
        )
        acceptable_source_hashes: set[str | None] = {None, entry.sha256}
        if source_link is not None or (
            source_sha not in acceptable_source_hashes and not recovered_case_move
        ):
            rename_source_modified.add(rename.old_path)
            if aliases:
                plan.actions.append(
                    Action(
                        BLOCKED,
                        path=rename.new_path,
                        module=rename.module,
                        kind=entry.kind,
                        detail=(
                            f"declared rename source {rename.old_path!r} is modified; "
                            "a case-aliasing destination cannot coexist portably, "
                            "so it was not written"
                        ),
                    )
                )
            continue
        if aliases:
            source_native = to_native(vault_root, rename.old_path)
            destination_native = to_native(vault_root, rename.new_path)
            destination_link = first_symlink_component(vault_root, rename.new_path)
            destination_sha = (
                None if destination_link is not None else _disk_sha(destination_native)
            )
            allowed_destination_hashes = {desired_by_path[rename.new_path].sha256}
            if source_sha is None:
                allowed_destination_hashes.add(entry.sha256)
            if destination_link is not None or (
                destination_sha is not None
                and not _same_file(source_native, destination_native)
                and destination_sha not in allowed_destination_hashes
            ):
                rename_destination_blocked.add(rename.old_path)
                plan.actions.append(
                    Action(
                        BLOCKED,
                        path=rename.new_path,
                        module=rename.module,
                        kind=entry.kind,
                        detail=(
                            f"declared rename source {rename.old_path!r} is safe, but an "
                            "unmanaged file or unsafe path occupies the case-aliasing destination"
                        ),
                    )
                )
                continue
        if any(a.type == BLOCKED and a.target == rename.new_path for a in plan.actions):
            rename_destination_blocked.add(rename.old_path)
            continue
        plan.actions.append(
            Action(
                RENAME,
                path=rename.old_path,
                write_path=rename.new_path,
                module=rename.module,
                kind=entry.kind,
                detail="declared rename; remove the old path only after the destination is ready",
                intent=desired_by_path[rename.new_path],
                source_entry=entry,
            )
        )
        planned_renames.add(rename.old_path)

    desired_paths = {f.path for f in desired.files}
    for entry in lock.sorted_entries():
        # `remove` deliberately retains seeded rows as permanent ownership markers
        # (#52). Only disabled managed rows need the orphan cleanup ramp.
        if entry.module not in enabled_modules and entry.kind != KIND_SEEDED:
            plan.actions.append(
                Action(
                    ORPHANED,
                    path=entry.path,
                    module=entry.module,
                    kind=entry.kind,
                    detail=(
                        f"module {entry.module!r} is no longer enabled; "
                        f"`onyxian remove {entry.module}` cleans this up"
                    ),
                )
            )
        elif (
            entry.kind != KIND_SEEDED
            and not entry.module.startswith(
                "source:"
            )  # source content is update's (M3), not plan's
            and entry.path not in desired_paths
            and not (entry.path.endswith(".new") and entry.path[: -len(".new")] in desired_paths)
            and entry.path not in planned_renames
        ):
            stale_rename = rename_by_old.get(entry.path)
            if stale_rename is not None and entry.path in rename_source_modified:
                detail = (
                    f"declared rename to {stale_rename.new_path!r} was not applied because the "
                    "tracked old file is modified or unsafe; left in place"
                )
            elif stale_rename is not None and entry.path in rename_destination_blocked:
                detail = (
                    f"declared rename to {stale_rename.new_path!r} was not applied because the "
                    "destination is blocked; the tracked old file was left in place"
                )
            else:
                detail = (
                    "tracked but no longer provided by its module; "
                    "`onyxian update`/`onyxian remove` will handle it"
                )
            plan.actions.append(
                Action(
                    STALE,
                    path=entry.path,
                    module=entry.module,
                    kind=entry.kind,
                    detail=detail,
                )
            )

    order = {t: i for i, t in enumerate((*MUTATING_TYPES, *REPORT_TYPES))}
    plan.actions.sort(
        key=lambda a: (
            a.type != CREATE_DIR,
            order[a.type] if a.type != CREATE_DIR else 0,
            0 if a.type == RENAME and paths_casefold_collide(a.path, a.target) else 1,
            a.target,
            a.path,
        )
    )
    return plan


_BADGES = {
    CREATE_DIR: ("+ dir ", ""),
    CREATE: ("+", ""),
    RESTORE: ("+", "restore"),
    UPDATE: ("~", "update"),
    RELOCK: ("=", "relock"),
    CONFLICT_NEW: ("!", "conflict"),
    RENAME: ("~", "rename"),
    BLOCKED: ("x", "BLOCKED"),
    ORPHANED: ("*", "orphaned"),
    STALE: ("*", "stale"),
}


def describe(action: Action) -> str:
    badge, label = _BADGES[action.type]
    kind = f" ({action.kind})" if action.kind else ""
    label_part = f" {label}" if label else ""
    arrow = (
        f" -> {action.write_path}" if action.write_path and action.write_path != action.path else ""
    )
    detail = f"  [{action.detail}]" if action.detail else ""
    return f"  {badge}{label_part} {action.path}{arrow}{kind}  ({action.module}){detail}"


def render_plan(plan: Plan) -> str:
    lines: list[str] = []
    if plan.mutating:
        lines.append("planned changes:")
        lines.extend(describe(a) for a in plan.mutating)
    else:
        lines.append("no changes planned; the vault matches the declared intent.")
    if plan.reports:
        lines.append("needs your attention (the engine will not act on these):")
        lines.extend(describe(a) for a in plan.reports)
    checked = sum(plan.noops.values())
    if checked:
        parts = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(plan.noops.items()))
        lines.append(f"checked and already right: {parts}.")
    return "\n".join(lines)


def _action_json(action: Action) -> dict[str, str]:
    return {
        "type": action.type,
        "path": action.path,
        "target": action.target,  # conflict sibling / rename destination, else `path`
        "module": action.module,
        "kind": action.kind,
        "detail": action.detail,
    }


def plan_json(plan: Plan) -> dict[str, object]:
    """The same three sections `render_plan` prints, for scripts and the agent layer (#66)."""
    return {
        "pending": len(plan.mutating),
        "changes": [_action_json(a) for a in plan.mutating],
        "reports": [_action_json(a) for a in plan.reports],
        "checked": dict(sorted(plan.noops.items())),
    }

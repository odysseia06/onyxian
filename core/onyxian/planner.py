"""The planner: a pure diff of desired state vs lock vs disk (KICKSTART.md §8, §9.1).

This file is the §8 write contract in executable form. The decision matrix for
every desired file:

  no lock entry, nothing on disk            -> create
  no lock entry, disk bytes == desired      -> relock (claim it; identical bytes, no write)
  no lock entry, disk bytes differ          -> blocked (a user file is in the way; never write)
  seeded + lock entry                       -> done forever (even if the user deleted it)
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

There is no flag that turns a `blocked` into a write.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .fsio import sha256_file
from .intent import DesiredState, FileIntent
from .model import KIND_SEEDED, Lock
from .paths import to_native

# Mutating action types (apply does something).
CREATE_DIR = "create_dir"
CREATE = "create"
RESTORE = "restore"
UPDATE = "update"
RELOCK = "relock"
CONFLICT_NEW = "conflict_new"

# Report-only action types (apply never touches these).
BLOCKED = "blocked"
ORPHANED = "orphaned"
STALE = "stale"

MUTATING_TYPES = (CREATE_DIR, CREATE, RESTORE, UPDATE, RELOCK, CONFLICT_NEW)
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
    write_path: str = ""  # differs from `path` only for conflict_new (the *.new sibling)
    intent: FileIntent | None = None

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


def _disk_sha(path: Path) -> str | None:
    """Hash of the file on disk, None if absent. A directory in a file's place is 'present but different'."""
    if path.is_file():
        return sha256_file(path)
    if path.exists():
        return "<not-a-file>"
    return None


def _plan_sibling_write(plan: Plan, intent: FileIntent, lock: Lock, vault_root: Path) -> None:
    """Plan the `<path>.new` write for a conflicted managed file (§8.3).

    The offer persists until the user resolves the original (accepts the new
    content, or the desired content changes again); while the delivered
    sibling matches the desired bytes, re-planning is a no-op.
    """
    new_path = intent.path + ".new"
    entry = lock.get(new_path)
    disk = _disk_sha(to_native(vault_root, new_path))
    base = dict(path=intent.path, module=intent.module, kind=intent.kind, write_path=new_path, intent=intent)
    if entry is None:
        if disk is None:
            plan.actions.append(Action(CONFLICT_NEW, detail="you modified the original; the new version lands beside it", **base))
        elif disk == intent.sha256:
            plan.actions.append(Action(RELOCK, detail="*.new already present with the right content", **base))
        else:
            plan.actions.append(
                Action(BLOCKED, detail=f"cannot deliver update: an unmanaged file sits at {new_path}", **base)
            )
        return
    # The sibling is already ours (locked).
    if disk == intent.sha256:
        if entry.sha256 == intent.sha256:
            plan._count(NOOP_UPTODATE)  # delivered and current; the ball is in the user's court
        else:
            plan.actions.append(Action(RELOCK, detail="*.new already present with the right content", **base))
    elif disk is None or disk == entry.sha256:
        plan.actions.append(Action(CONFLICT_NEW, detail="refreshing the pending *.new sibling", **base))
    else:
        plan.actions.append(
            Action(BLOCKED, detail=f"you edited {new_path} too; resolve it by hand, then re-plan", **base)
        )


def _plan_file(plan: Plan, intent: FileIntent, lock: Lock, vault_root: Path) -> None:
    entry = lock.get(intent.path)
    disk = _disk_sha(to_native(vault_root, intent.path))
    base = dict(path=intent.path, module=intent.module, kind=intent.kind, intent=intent)

    if entry is None:
        if disk is None:
            plan.actions.append(Action(CREATE, **base))
        elif disk == intent.sha256:
            plan.actions.append(Action(RELOCK, detail="identical content already on disk; recording it", **base))
        else:
            plan.actions.append(
                Action(BLOCKED, detail="a file the engine does not own is already there; it will not be touched", **base)
            )
        return

    if entry.kind == KIND_SEEDED:
        plan._count(NOOP_SEED_DONE)  # seeded once; the user owns it now, present or not
        return

    if disk is None:
        plan.actions.append(Action(RESTORE, detail="managed file missing; restoring from intent", **base))
        return
    user_modified = disk != entry.sha256
    desired_changed = intent.sha256 != entry.sha256
    if not user_modified:
        if not desired_changed:
            plan._count(NOOP_UPTODATE)
        else:
            plan.actions.append(Action(UPDATE, detail="unmodified since install; safe overwrite", **base))
    else:
        if disk == intent.sha256:
            plan.actions.append(Action(RELOCK, detail="your edit already matches the new version", **base))
        elif not desired_changed:
            plan._count(NOOP_USER_MODIFIED)  # their customization stands until an update arrives
        elif entry.declined == intent.sha256:
            plan._count(NOOP_DECLINED)  # the user declined exactly this version (§8.3 exit ramp)
        else:
            _plan_sibling_write(plan, intent, lock, vault_root)


def build_plan(vault_root: Path, desired: DesiredState, lock: Lock, enabled_modules: set[str]) -> Plan:
    plan = Plan()

    for dir_intent in desired.dirs:
        native = to_native(vault_root, dir_intent.path)
        if native.is_dir():
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
        _plan_file(plan, file_intent, lock, vault_root)

    desired_paths = {f.path for f in desired.files}
    for entry in lock.sorted_entries():
        if entry.module not in enabled_modules:
            plan.actions.append(
                Action(
                    ORPHANED,
                    path=entry.path,
                    module=entry.module,
                    kind=entry.kind,
                    detail=f"module {entry.module!r} is no longer enabled; re-enable it in the config, then `onyxian remove {entry.module}` cleans this up",
                )
            )
        elif (
            entry.kind != KIND_SEEDED
            and not entry.module.startswith("source:")  # source content is update's (M3), not plan's
            and entry.path not in desired_paths
            and not (entry.path.endswith(".new") and entry.path[: -len(".new")] in desired_paths)
        ):
            plan.actions.append(
                Action(
                    STALE,
                    path=entry.path,
                    module=entry.module,
                    kind=entry.kind,
                    detail="tracked but no longer provided by its module; `onyxian update`/`onyxian remove` will handle it",
                )
            )

    order = {t: i for i, t in enumerate((*MUTATING_TYPES, *REPORT_TYPES))}
    plan.actions.sort(key=lambda a: (a.type != CREATE_DIR, order[a.type] if a.type != CREATE_DIR else 0, a.target))
    return plan


_BADGES = {
    CREATE_DIR: ("+ dir ", ""),
    CREATE: ("+", ""),
    RESTORE: ("+", "restore"),
    UPDATE: ("~", "update"),
    RELOCK: ("=", "relock"),
    CONFLICT_NEW: ("!", "conflict"),
    BLOCKED: ("x", "BLOCKED"),
    ORPHANED: ("*", "orphaned"),
    STALE: ("*", "stale"),
}


def describe(action: Action) -> str:
    badge, label = _BADGES[action.type]
    kind = f" ({action.kind})" if action.kind else ""
    label_part = f" {label}" if label else ""
    arrow = f" -> {action.write_path}" if action.write_path and action.write_path != action.path else ""
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

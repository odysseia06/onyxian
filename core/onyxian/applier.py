"""The applier: execute a reviewed plan under the §8 write contract.

Defense in depth: the planner already decided every action from a consistent
snapshot, but the world may have moved between plan and apply — so every
precondition is re-verified against the live disk immediately before each
write, and an action whose precondition no longer holds is skipped with a
reason, never forced. The lock is saved after every successful write, so a
crash leaves at most one already-written file pending its ledger entry — which
the next plan heals as a `relock` (identical bytes), never as data loss.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .fsio import sha256_file, write_bytes_atomic
from .lockio import save_lock
from .model import Lock, LockEntry
from .paths import first_symlink_component, to_native
from .planner import (
    CONFLICT_NEW,
    CREATE,
    CREATE_DIR,
    RELOCK,
    RESTORE,
    UPDATE,
    Action,
    Plan,
)

_RECHECK_FAILED = "state changed between plan and apply; run `onyxian plan` again"


@dataclass
class ApplyResult:
    performed: list[Action] = field(default_factory=list)
    skipped: list[tuple[Action, str]] = field(default_factory=list)
    lock_changed: bool = False

    @property
    def ok(self) -> bool:
        return not self.skipped


def _entry_for(action: Action) -> LockEntry:
    intent = action.intent
    assert intent is not None  # mutating file actions always carry their intent
    return LockEntry(
        path=action.target,
        sha256=intent.sha256,
        module=intent.module,
        module_version=intent.module_version,
        kind=intent.kind,
    )


def apply_plan(vault_root: Path, plan: Plan, lock: Lock, *, dry_run: bool = False) -> ApplyResult:
    result = ApplyResult()
    if dry_run:
        return result

    def record(action: Action) -> None:
        lock.put(_entry_for(action))
        save_lock(vault_root, lock)
        result.lock_changed = True
        result.performed.append(action)

    for action in plan.mutating:
        target = to_native(vault_root, action.target)

        # The sha rechecks below follow symlinks while a write would replace the
        # link itself, so a link to the exact expected bytes passes every byte
        # comparison — it must be gated directly (issue #53).
        link = first_symlink_component(vault_root, action.target)
        if link is not None:
            result.skipped.append(
                (
                    action,
                    f"a symlink appeared at {link}; the engine never writes through or "
                    "replaces links — run `onyxian plan` again",
                )
            )
            continue

        if action.type == CREATE_DIR:
            if target.is_dir():
                result.performed.append(action)  # already converged; still a success
            elif target.exists():
                result.skipped.append((action, _RECHECK_FAILED))
            else:
                target.mkdir(parents=True, exist_ok=True)
                result.performed.append(action)
            continue

        intent = action.intent
        assert intent is not None
        on_disk = sha256_file(target) if target.is_file() else None

        if action.type in (CREATE, RESTORE):
            if on_disk is None and not target.exists():
                write_bytes_atomic(target, intent.content)
                record(action)
            elif on_disk == intent.sha256:
                record(action)  # appeared with identical bytes; just ledger it
            else:
                result.skipped.append((action, _RECHECK_FAILED))

        elif action.type == UPDATE:
            entry = lock.get(action.path)
            if on_disk is not None and entry is not None and on_disk == entry.sha256:
                write_bytes_atomic(target, intent.content)
                record(action)
            elif on_disk == intent.sha256:
                record(action)
            else:
                result.skipped.append((action, _RECHECK_FAILED))

        elif action.type == RELOCK:
            if on_disk == intent.sha256:
                record(action)
                # §8.3 resolution: the original now matches desired content; if the
                # user also deleted the delivered *.new sibling, retire its entry —
                # nothing else ever would, and doctor would report it missing forever.
                sibling = action.path + ".new"
                if (
                    not action.write_path
                    and lock.get(sibling) is not None
                    and not to_native(vault_root, sibling).is_file()
                ):
                    del lock.entries[sibling]
                    save_lock(vault_root, lock)
            else:
                result.skipped.append((action, _RECHECK_FAILED))

        elif action.type == CONFLICT_NEW:
            entry = lock.get(action.target)
            overwrite_ok = entry is not None and on_disk is not None and on_disk == entry.sha256
            if on_disk is None and not target.exists():
                write_bytes_atomic(target, intent.content)
                record(action)
            elif on_disk == intent.sha256 or overwrite_ok:
                if on_disk != intent.sha256:
                    write_bytes_atomic(target, intent.content)
                record(action)
            else:
                result.skipped.append((action, _RECHECK_FAILED))

        else:  # pragma: no cover - planner only emits the types above as mutating
            result.skipped.append((action, f"unknown action type {action.type!r}"))

    return result

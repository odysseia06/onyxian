"""The applier: execute a reviewed plan under the write contract.

Defense in depth: the planner already decided every action from a consistent
snapshot, but the world may have moved between plan and apply — so every
precondition is re-verified against the live disk immediately before each
write, and an action whose precondition no longer holds is skipped with a
reason, never forced. The lock is saved after every successful file action, so
a crash leaves at most one landed action pending its ledger entry; the next
plan heals identical writes as a `relock` and recognizes a landed case-only
move by its exact destination spelling, never by overwriting user bytes.

The same holds for a write the OS refuses (issue #57): every action runs inside
one guard, so a file locked by Obsidian or a user file standing where a parent
folder must go costs that one action, never the rest of the run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ApplyError
from .fsio import move_file_atomic, remove_file_durable, sha256_file, write_bytes_atomic
from .lockio import save_lock
from .model import Lock, LockEntry
from .paths import (
    first_symlink_component,
    path_has_exact_spelling,
    paths_casefold_collide,
    to_native,
)
from .planner import (
    CONFLICT_NEW,
    CREATE,
    CREATE_DIR,
    RELOCK,
    RENAME,
    RESTORE,
    UPDATE,
    Action,
    Plan,
)

_RECHECK_FAILED = "state changed between plan and apply; run `onyxian plan` again"


def _write_failed(exc: Exception) -> str:
    """Skip reason for a write the OS refused — the ApplyError case, degraded."""
    return f"could not be written ({exc}); run `onyxian apply` again once that is fixed"


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


def _same_file(first: Path, second: Path) -> bool:
    try:
        return first.is_file() and second.is_file() and os.path.samefile(first, second)
    except OSError:
        return False


def _same_file_has_distinct_entries(first: Path, second: Path) -> bool:
    """Whether two names are separate directory entries for the same file.

    A case-insensitive filesystem can resolve differently-cased paths to one
    entry, while hardlinks are two entries that share an inode. Only the latter
    is safe to unlink after POSIX treats ``rename(first, second)`` as a no-op.
    """
    if not _same_file(first, second):
        return False
    try:
        if not os.path.samefile(first.parent, second.parent):
            return True
        names = {child.name for child in first.parent.iterdir()}
    except OSError:
        return False
    return first.name != second.name and first.name in names and second.name in names


def apply_plan(vault_root: Path, plan: Plan, lock: Lock, *, dry_run: bool = False) -> ApplyResult:
    result = ApplyResult()
    if dry_run:
        return result

    def record(action: Action) -> None:
        lock.put(_entry_for(action))
        save_lock(vault_root, lock)
        result.lock_changed = True
        result.performed.append(action)

    def perform(action: Action) -> None:
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
            return

        if action.type == CREATE_DIR:
            if target.is_dir():
                result.performed.append(action)  # already converged; still a success
            elif target.exists():
                result.skipped.append((action, _RECHECK_FAILED))
            else:
                target.mkdir(parents=True, exist_ok=True)
                result.performed.append(action)
            return

        if action.type == RENAME:
            expected = action.source_entry
            assert expected is not None
            intent = action.intent
            assert intent is not None

            if paths_casefold_collide(action.path, action.target):
                source_entry = lock.get(action.path)
                if source_entry is None:
                    destination_entry = lock.get(action.target)
                    if destination_entry == _entry_for(action) and target.is_file():
                        result.performed.append(action)
                    else:
                        result.skipped.append((action, _RECHECK_FAILED))
                    return
                if source_entry != expected:
                    result.skipped.append((action, _RECHECK_FAILED))
                    return

                source_link = first_symlink_component(vault_root, action.path)
                if source_link is not None:
                    result.skipped.append(
                        (
                            action,
                            f"a symlink appeared at {source_link}; the old file was kept",
                        )
                    )
                    return
                source = to_native(vault_root, action.path)
                source_sha = sha256_file(source) if source.is_file() else None
                destination_sha = sha256_file(target) if target.is_file() else None
                same_file = _same_file(source, target)
                recovered_case_move = (
                    source_sha == intent.sha256
                    and not path_has_exact_spelling(vault_root, action.path)
                    and path_has_exact_spelling(vault_root, action.target)
                )

                if source.is_file():
                    if source_sha != source_entry.sha256 and not recovered_case_move:
                        result.skipped.append(
                            (
                                action,
                                "the old file was modified after review; it was kept",
                            )
                        )
                        return
                    if not recovered_case_move:
                        if same_file or not target.exists():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            move_file_atomic(source, target)
                            # POSIX permits rename(old, new) to be a no-op when both
                            # names are hardlinks to the same inode. The reviewed old
                            # name still has to be retired in that case.
                            if _same_file_has_distinct_entries(source, target):
                                remove_file_durable(source)
                        elif target.is_file() and destination_sha == intent.sha256:
                            remove_file_durable(source)
                        else:
                            result.skipped.append(
                                (
                                    action,
                                    "rename destination is not safe to claim; "
                                    "the old file was kept",
                                )
                            )
                            return
                elif source.exists():
                    result.skipped.append(
                        (
                            action,
                            "the old path is no longer a regular file; it was kept",
                        )
                    )
                    return
                elif target.is_file():
                    if destination_sha not in (source_entry.sha256, intent.sha256):
                        result.skipped.append(
                            (
                                action,
                                "rename destination is not safe to claim; "
                                "the old lock row was kept",
                            )
                        )
                        return
                elif target.exists():
                    result.skipped.append(
                        (
                            action,
                            "rename destination is not a regular file; the old lock row was kept",
                        )
                    )
                    return
                else:
                    write_bytes_atomic(target, intent.content)

                if not target.is_file() or sha256_file(target) != intent.sha256:
                    write_bytes_atomic(target, intent.content)
                del lock.entries[action.path]
                lock.put(_entry_for(action))
                save_lock(vault_root, lock)
                result.lock_changed = True
                result.performed.append(action)
                return

            source_entry = lock.get(action.path)
            destination_entry = lock.get(action.target)
            if source_entry is None:
                if destination_entry == _entry_for(action) and target.is_file():
                    result.performed.append(action)  # another run completed the rename
                else:
                    result.skipped.append((action, _RECHECK_FAILED))
                return

            destination_ready = (
                destination_entry is not None
                and destination_entry.module == action.module
                and destination_entry.kind == action.kind
                and target.is_file()
            )
            if not destination_ready:
                result.skipped.append(
                    (
                        action,
                        "rename destination is not ready and ledgered; the old file was kept",
                    )
                )
                return

            if source_entry != expected:
                result.skipped.append((action, _RECHECK_FAILED))
                return

            source_link = first_symlink_component(vault_root, action.path)
            if source_link is not None:
                result.skipped.append(
                    (
                        action,
                        f"a symlink appeared at {source_link}; the old file was kept",
                    )
                )
                return
            source = to_native(vault_root, action.path)
            if source.is_file():
                if sha256_file(source) != source_entry.sha256:
                    result.skipped.append(
                        (
                            action,
                            "the old file was modified after review; it was kept",
                        )
                    )
                    return
                remove_file_durable(source)
            elif source.exists():
                result.skipped.append(
                    (
                        action,
                        "the old path is no longer a regular file; it was kept",
                    )
                )
                return

            del lock.entries[action.path]
            save_lock(vault_root, lock)
            result.lock_changed = True
            result.performed.append(action)
            return

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
                # Conflict resolution: the original now matches desired content; if the
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

    for action in plan.mutating:
        try:
            perform(action)
        except (OSError, ApplyError) as exc:
            # Only the relock sibling retirement can fail *after* the action itself
            # landed; that one stays a success (nothing was lost, and doctor reports
            # the stale row) rather than being reported both ways.
            if not (result.performed and result.performed[-1] is action):
                result.skipped.append((action, _write_failed(exc)))

    return result

"""`onyxian diff` — inspect and resolve `*.new` conflict siblings (KICKSTART.md §8.3).

The never-clobber model delivers updates to customized managed files beside
them as `*.new`; this module is the exit ramp for living with that. Pair
discovery mirrors the planner's conflict condition exactly; diffs compare the
original on disk against the rendered desired bytes (not the `*.new` file), so
pending, delivered, and stale-sibling states all render the same diff. Output
is plain deterministic text: stdlib difflib, no timestamps, LF.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, replace
from pathlib import Path

from .fsio import normalize_newlines, sha256_file, write_bytes_atomic
from .intent import DesiredState, FileIntent
from .lockio import save_lock
from .model import KIND_SEEDED, Lock, LockEntry
from .paths import split_portable, to_native

NEW_SUFFIX = ".new"

RECHECK_FAILED = "state changed since the diff was shown; run `onyxian diff` again"


@dataclass(frozen=True)
class ConflictPair:
    """One live §8.3 conflict: a user-modified managed file with newer shipped content."""

    intent: FileIntent
    delivered: bool  # the on-disk sibling already carries the shipped bytes

    @property
    def path(self) -> str:
        return self.intent.path

    @property
    def new_path(self) -> str:
        return self.intent.path + NEW_SUFFIX

    @property
    def shipped_by(self) -> str:
        return f"{self.intent.module} {self.intent.module_version}"


@dataclass(frozen=True)
class Leftover:
    """A `*.new` ledger row whose original is no longer conflicted — pure litter
    (the permanent doctor WARN the issue describes) plus, sometimes, its file."""

    entry: LockEntry


def _is_conflicted(vault_root: Path, intent: FileIntent, lock: Lock) -> bool:
    """The exact condition under which `_plan_file` enters `_plan_sibling_write`."""
    entry = lock.get(intent.path)
    if entry is None or entry.kind == KIND_SEEDED:
        return False
    native = to_native(vault_root, intent.path)
    if not native.is_file():
        return False
    disk = sha256_file(native)
    if disk == entry.sha256 or disk == intent.sha256 or intent.sha256 == entry.sha256:
        return False
    return entry.declined != intent.sha256


def find_conflicts(
    vault_root: Path, desired: DesiredState, lock: Lock
) -> tuple[list[ConflictPair], list[Leftover]]:
    """Every live conflict pair plus every resolved-leftover sibling row, path-sorted."""
    pairs: list[ConflictPair] = []
    for intent in desired.files:  # already sorted by portable path
        if not _is_conflicted(vault_root, intent, lock):
            continue
        sibling = to_native(vault_root, intent.path + NEW_SUFFIX)
        delivered = sibling.is_file() and sha256_file(sibling) == intent.sha256
        pairs.append(ConflictPair(intent=intent, delivered=delivered))

    active_siblings = {pair.new_path for pair in pairs}
    desired_paths = {f.path for f in desired.files}
    leftovers = [
        Leftover(entry)
        for entry in lock.sorted_entries()
        if entry.path.endswith(NEW_SUFFIX)
        and entry.kind != KIND_SEEDED
        and entry.path not in desired_paths  # a module may genuinely ship a *.new path
        and entry.path not in active_siblings
    ]
    return pairs, leftovers


def normalize_path_argument(raw: str) -> str:
    """Accept the original or the sibling path, pasted in either slash flavor."""
    portable = raw.replace("\\", "/")
    if portable.endswith(NEW_SUFFIX):
        portable = portable[: -len(NEW_SUFFIX)]
    split_portable(portable, origin="the onyxian diff path argument")
    return portable


def render_conflict_list(pairs: list[ConflictPair], leftovers: list[Leftover]) -> str:
    if not pairs and not leftovers:
        return "no conflict pairs; nothing pending resolution."
    lines: list[str] = []
    if pairs:
        lines.append(f"{len(pairs)} conflict pair(s):")
        for pair in pairs:
            state = "[delivered]" if pair.delivered else "[pending; run `onyxian apply` to deliver]"
            lines.append(f"  ! {pair.path} -> {pair.new_path}  ({pair.shipped_by}) {state}")
    if leftovers:
        lines.append(f"{len(leftovers)} resolved leftover(s):")
        for leftover in leftovers:
            lines.append(f"  * {leftover.entry.path}  [original already resolved; ledger row remains]")
    lines.append("see a diff with `onyxian diff <path>`; resolve with `onyxian diff --resolve`.")
    return "\n".join(lines)


def render_pair_diff(vault_root: Path, pair: ConflictPair) -> str:
    """Unified diff of yours-on-disk vs the shipped bytes. Deterministic: no
    timestamps, normalized newlines; degrades to a one-line notice for
    line-ending-only differences and for content that is not UTF-8 text."""
    raw = to_native(vault_root, pair.path).read_bytes()
    try:
        mine = raw.decode("utf-8-sig")  # tolerate a BOM, like every engine read
        shipped = pair.intent.content.decode("utf-8")
    except UnicodeDecodeError:
        return f"{pair.path}: binary or non-UTF-8 content differs; no text diff."
    mine_text, shipped_text = normalize_newlines(mine), normalize_newlines(shipped)
    if mine_text == shipped_text:
        return (
            f"{pair.path}: differs from the shipped version only in line endings or a byte-order"
            " mark; the text content is identical."
        )
    lines = difflib.unified_diff(
        mine_text.splitlines(),
        shipped_text.splitlines(),
        fromfile=f"{pair.path}  (yours)",
        tofile=f"{pair.new_path}  (shipped by {pair.shipped_by})",
        lineterm="",
    )
    return "\n".join(lines)


# ----------------------------------------------------------------- resolution
#
# Every operation below re-verifies its preconditions against the live disk
# immediately before writing (the applier discipline); a failed re-check skips
# with a reason, never forces. The lock is saved after every write.


def _retire_sibling(vault_root: Path, base_path: str, lock: Lock) -> str | None:
    """Remove the delivered sibling: delete the file only if it still hashes to
    its own ledger row (a user-edited `*.new` is never deleted), then pop the
    row. Returns a note when the file was left behind."""
    sibling = base_path + NEW_SUFFIX
    entry = lock.get(sibling)
    if entry is None:
        return None
    note = None
    native = to_native(vault_root, sibling)
    if native.is_file():
        if sha256_file(native) == entry.sha256:
            native.unlink()
        else:
            note = f"you edited {sibling}; it was left on disk, untracked from here on"
    lock.entries.pop(sibling, None)
    save_lock(vault_root, lock)
    return note


def take_new(vault_root: Path, pair: ConflictPair, lock: Lock) -> tuple[bool, str]:
    """Resolve by adopting the shipped bytes: overwrite the original at the
    user's explicit request, re-ledger it at the new sha, retire the sibling."""
    if not _is_conflicted(vault_root, pair.intent, lock):
        return False, RECHECK_FAILED
    write_bytes_atomic(to_native(vault_root, pair.path), pair.intent.content)
    lock.put(
        LockEntry(
            path=pair.path,
            sha256=pair.intent.sha256,
            module=pair.intent.module,
            module_version=pair.intent.module_version,
            kind=pair.intent.kind,
        )
    )
    save_lock(vault_root, lock)
    note = _retire_sibling(vault_root, pair.path, lock)
    message = f"took the shipped version: {pair.path} now carries {pair.shipped_by}'s content"
    return True, message + (f"\n  = {note}" if note else "")


def keep_mine(vault_root: Path, pair: ConflictPair, lock: Lock) -> tuple[bool, str]:
    """Resolve by declining the shipped version: record its sha on the
    original's row so the planner stops re-offering it, retire the sibling.
    The decline is per-version — a future release with different bytes
    resumes the offer."""
    if not _is_conflicted(vault_root, pair.intent, lock):
        return False, RECHECK_FAILED
    entry = lock.get(pair.path)
    lock.put(replace(entry, declined=pair.intent.sha256))
    save_lock(vault_root, lock)
    note = _retire_sibling(vault_root, pair.path, lock)
    message = (
        f"kept yours: {pair.path} (declined {pair.shipped_by}'s version; it will not be"
        " re-offered until the shipped content changes)"
    )
    return True, message + (f"\n  = {note}" if note else "")


def clean_leftover(vault_root: Path, leftover: Leftover, lock: Lock) -> tuple[bool, str]:
    """Retire a resolved-leftover `*.new` ledger row (the permanent doctor WARN),
    deleting its file only when it is byte-identical to the row."""
    entry = lock.get(leftover.entry.path)
    if entry is None or entry != leftover.entry:
        return False, RECHECK_FAILED
    note = ""
    native = to_native(vault_root, entry.path)
    if native.is_file():
        if sha256_file(native) == entry.sha256:
            native.unlink()
        else:
            note = "; the file differs from the ledger row and was left on disk"
    lock.entries.pop(entry.path, None)
    save_lock(vault_root, lock)
    return True, f"retired the leftover ledger row for {entry.path}{note}"

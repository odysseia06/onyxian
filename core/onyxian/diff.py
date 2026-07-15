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
from .model import KIND_MANAGED, KIND_SEEDED, Lock, LockEntry
from .paths import split_portable, to_native
from .planner import _disk_sha  # the one definition of "what is on disk at this path"

NEW_SUFFIX = ".new"

RECHECK_FAILED = "state changed since the diff was shown; run `onyxian diff` again"


@dataclass(frozen=True)
class ConflictPair:
    """One live §8.3 conflict: a user-modified managed file with newer shipped content.

    ``disk_sha256`` pins the original's bytes at discovery time (or the
    planner's not-a-file sentinel when a directory sits there); resolutions
    require exactly those bytes to still be on disk before writing.
    """

    intent: FileIntent
    disk_sha256: str
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
    """A conflict sibling's ledger row whose original is no longer conflicted —
    pure litter (the permanent doctor WARN the issue describes) plus,
    sometimes, its file."""

    entry: LockEntry


def _conflicted_disk_sha(vault_root: Path, intent: FileIntent, lock: Lock) -> str | None:
    """The original's on-disk hash when `_plan_file` would enter
    `_plan_sibling_write` for it, else None. Mirrors the planner exactly,
    including its treatment of a directory as present-but-different."""
    entry = lock.get(intent.path)
    if entry is None or entry.kind == KIND_SEEDED:
        return None
    disk = _disk_sha(to_native(vault_root, intent.path))
    if disk is None:
        return None
    if disk == entry.sha256 or disk == intent.sha256 or intent.sha256 == entry.sha256:
        return None
    if entry.declined == intent.sha256:
        return None
    return disk


def find_conflicts(
    vault_root: Path, desired: DesiredState, lock: Lock
) -> tuple[list[ConflictPair], list[Leftover]]:
    """Every live conflict pair plus every resolved-leftover sibling row, path-sorted."""
    pairs: list[ConflictPair] = []
    desired_by_path = desired.file_by_path()
    for intent in desired.files:  # already sorted by portable path
        disk = _conflicted_disk_sha(vault_root, intent, lock)
        if disk is None:
            continue
        sibling = to_native(vault_root, intent.path + NEW_SUFFIX)
        delivered = sibling.is_file() and sha256_file(sibling) == intent.sha256
        pairs.append(ConflictPair(intent=intent, disk_sha256=disk, delivered=delivered))

    # A leftover must be provably a conflict artifact: a managed row at
    # <base>.new that is not itself a desired file, whose base IS a desired
    # file of the same module and is no longer conflicted. Anything else that
    # merely ends in .new (a source-installed file, a module's own *.new
    # asset, a seeded row) is somebody's real file, not litter.
    active_siblings = {pair.new_path for pair in pairs}
    leftovers: list[Leftover] = []
    for entry in lock.sorted_entries():
        if not entry.path.endswith(NEW_SUFFIX) or entry.path in active_siblings:
            continue
        if entry.kind != KIND_MANAGED or entry.path in desired_by_path:
            continue
        base_intent = desired_by_path.get(entry.path[: -len(NEW_SUFFIX)])
        if base_intent is None or base_intent.module != entry.module:
            continue
        leftovers.append(Leftover(entry))
    return pairs, leftovers


def normalize_path_argument(raw: str) -> str:
    """Validate a pasted path in either slash flavor; no suffix guessing here."""
    portable = raw.replace("\\", "/")
    split_portable(portable, origin="the onyxian diff path argument")
    return portable


def match_pair(pairs: list[ConflictPair], portable: str) -> ConflictPair | None:
    """The original-or-sibling contract: an exact original-path match wins
    (a managed file may itself be named `*.new`); only then is the argument
    read as a sibling path and its base looked up."""
    exact = next((p for p in pairs if p.path == portable), None)
    if exact is not None or not portable.endswith(NEW_SUFFIX):
        return exact
    base = portable[: -len(NEW_SUFFIX)]
    return next((p for p in pairs if p.path == base), None)


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
            lines.append(
                f"  * {leftover.entry.path}  [original already resolved; ledger row remains]"
            )
    lines.append("see a diff with `onyxian diff <path>`; resolve with `onyxian diff --resolve`.")
    return "\n".join(lines)


def render_pair_diff(vault_root: Path, pair: ConflictPair) -> str:
    """Unified diff of yours-on-disk vs the shipped bytes. Deterministic: no
    timestamps, normalized newlines; degrades to a one-line notice for
    non-file originals, line-ending-only differences, trailing-newline-only
    differences, and content that is not UTF-8 text."""
    native = to_native(vault_root, pair.path)
    if not native.is_file():
        return f"{pair.path}: a directory (not a file) sits at this path; no text diff."
    raw = native.read_bytes()
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
    mine_lines, shipped_lines = mine_text.splitlines(), shipped_text.splitlines()
    if mine_lines == shipped_lines:
        # splitlines() hides exactly one difference: the presence of the final newline.
        which = (
            "your file lacks the trailing newline the shipped version ends with"
            if shipped_text.endswith("\n")
            else "your file ends with a trailing newline the shipped version lacks"
        )
        return f"{pair.path}: the text differs only at the very end — {which}."
    lines = difflib.unified_diff(
        mine_lines,
        shipped_lines,
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


def _retire_sibling(
    vault_root: Path, pair: ConflictPair, lock: Lock, desired_paths: set[str]
) -> str | None:
    """Remove the delivered sibling — but only when the row at `<path>.new` is
    provably this conflict's delivery artifact: managed, same module, and not
    a real desired file in its own right. A seeded or foreign row there is
    somebody's file and is never deleted or popped. The file itself is deleted
    only if it still hashes to its own ledger row (a user-edited `*.new` is
    never deleted). Returns a note when anything was left behind."""
    sibling = pair.new_path
    entry = lock.get(sibling)
    if entry is None:
        return None
    if entry.kind != KIND_MANAGED or entry.module != pair.intent.module or sibling in desired_paths:
        return f"{sibling} is not this conflict's delivery artifact; left alone"
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


def _reverify(vault_root: Path, pair: ConflictPair, lock: Lock) -> str | None:
    """The applier discipline, exact form: the original must still be
    conflicted AND still hold precisely the bytes whose diff was displayed."""
    current = _conflicted_disk_sha(vault_root, pair.intent, lock)
    if current is None or current != pair.disk_sha256:
        return RECHECK_FAILED
    return None


def take_new(
    vault_root: Path, pair: ConflictPair, lock: Lock, desired_paths: set[str]
) -> tuple[bool, str]:
    """Resolve by adopting the shipped bytes: overwrite the original at the
    user's explicit request, re-ledger it at the new sha, retire the sibling."""
    reason = _reverify(vault_root, pair, lock)
    if reason is not None:
        return False, reason
    native = to_native(vault_root, pair.path)
    if not native.is_file():
        return (
            False,
            f"a directory sits at {pair.path}; the engine will not replace it — resolve by hand",
        )
    write_bytes_atomic(native, pair.intent.content)
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
    note = _retire_sibling(vault_root, pair, lock, desired_paths)
    message = f"took the shipped version: {pair.path} now carries {pair.shipped_by}'s content"
    return True, message + (f"\n  = {note}" if note else "")


def keep_mine(
    vault_root: Path, pair: ConflictPair, lock: Lock, desired_paths: set[str]
) -> tuple[bool, str]:
    """Resolve by declining the shipped version: record its sha on the
    original's row so the planner stops re-offering it, retire the sibling.
    The decline is per-version — a future release with different bytes
    resumes the offer."""
    reason = _reverify(vault_root, pair, lock)
    if reason is not None:
        return False, reason
    entry = lock.get(pair.path)
    lock.put(replace(entry, declined=pair.intent.sha256))
    save_lock(vault_root, lock)
    note = _retire_sibling(vault_root, pair, lock, desired_paths)
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

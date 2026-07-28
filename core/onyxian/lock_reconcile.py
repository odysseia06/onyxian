"""Inspect and repair lockfiles forked by a file-sync service (issue #78).

Reconciliation deliberately chooses one complete ledger; it never merges rows or
changes their ownership hashes. Every selected row is checked against the live disk
and mismatches are reported, then retained. Dropping one would turn a customized
managed file into an unowned collision and weaken the never-clobber contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .configio import VAULT_DIR
from .errors import LockError, OnyxianError
from .fsio import sha256_bytes, sha256_file
from .lockio import lock_path, parse_lock_text, save_lock
from .model import LOCATION_RUNTIME, Lock
from .paths import first_symlink_component, to_native

SYNC_CONFLICT_MARKERS = ("conflicted copy", ".sync-conflict-")


@dataclass(frozen=True)
class LedgerVerification:
    matching: tuple[str, ...]
    changed: tuple[str, ...]
    missing: tuple[str, ...]
    unverified: tuple[str, ...]
    # Exact reviewed state for the post-confirmation race check. A category-only
    # comparison would miss one customized byte sequence changing into another.
    fingerprints: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class LockCandidate:
    name: str
    digest: str
    lock: Lock | None
    verification: LedgerVerification | None
    error: str = ""

    @property
    def valid(self) -> bool:
        return self.lock is not None and not self.error


@dataclass(frozen=True)
class LockReconcilePlan:
    candidates: tuple[LockCandidate, ...]
    selected_name: str
    snapshots: tuple[tuple[str, str], ...]
    conflict_names: tuple[str, ...]

    @property
    def selected(self) -> LockCandidate:
        return next(
            candidate for candidate in self.candidates if candidate.name == self.selected_name
        )


@dataclass(frozen=True)
class LockReconcileResult:
    generation: int
    machine_id: str
    retired: tuple[str, ...]


def sync_conflict_sibling_names(vault_root: Path) -> list[str]:
    """Every immediate sync-conflict sibling in ``.vault/`` (config or lock)."""
    state_dir = vault_root / VAULT_DIR
    if not state_dir.is_dir():
        return []
    return sorted(
        path.name
        for path in state_dir.iterdir()
        if path.is_file() and any(marker in path.name.lower() for marker in SYNC_CONFLICT_MARKERS)
    )


def lock_conflict_sibling_paths(vault_root: Path) -> tuple[Path, ...]:
    """Only conflicted JSON siblings that plausibly fork ``lock.json``."""
    state_dir = vault_root / VAULT_DIR
    if not state_dir.is_dir():
        return ()

    def is_lock_sibling(path: Path) -> bool:
        name = path.name.lower()
        dropbox_style = name.startswith("lock (") and "conflicted copy" in name
        syncthing_style = name.startswith("lock.sync-conflict-")
        return path.suffix.lower() == ".json" and (dropbox_style or syncthing_style)

    return tuple(
        sorted(
            (
                path
                for path in state_dir.iterdir()
                if path.is_file() and path.name != "lock.json" and is_lock_sibling(path)
            ),
            key=lambda path: path.name,
        )
    )


def verify_lock_rows(vault_root: Path, lock: Lock) -> LedgerVerification:
    matching: list[str] = []
    changed: list[str] = []
    missing: list[str] = []
    unverified: list[str] = []
    fingerprints: list[tuple[str, str]] = []

    for entry in lock.sorted_entries():
        if entry.location == LOCATION_RUNTIME:
            unverified.append(f"{entry.path} (runtime location)")
            fingerprints.append((entry.path, "runtime"))
            continue
        try:
            link = first_symlink_component(vault_root, entry.path)
            if link is not None:
                unverified.append(f"{entry.path} (via symlink {link})")
                fingerprints.append((entry.path, f"symlink:{link}"))
                continue
            native = to_native(vault_root, entry.path)
            if not native.is_file():
                missing.append(entry.path)
                state = "missing" if not native.exists() else "not-a-regular-file"
                fingerprints.append((entry.path, state))
                continue
            digest = sha256_file(native)
        except OSError as exc:
            reason = exc.strerror or str(exc)
            unverified.append(f"{entry.path} ({reason})")
            fingerprints.append((entry.path, f"unreadable:{exc.errno}:{reason}"))
            continue
        fingerprints.append((entry.path, digest))
        (matching if digest == entry.sha256 else changed).append(entry.path)

    return LedgerVerification(
        matching=tuple(matching),
        changed=tuple(changed),
        missing=tuple(missing),
        unverified=tuple(unverified),
        fingerprints=tuple(fingerprints),
    )


def _candidate_paths(vault_root: Path) -> tuple[Path, ...]:
    canonical = lock_path(vault_root)
    active = (canonical,) if canonical.is_file() else ()
    return active + lock_conflict_sibling_paths(vault_root)


def inspect_lock_candidates(
    vault_root: Path, *, verify_rows: bool = True
) -> tuple[LockCandidate, ...]:
    candidates: list[LockCandidate] = []
    for path in _candidate_paths(vault_root):
        try:
            raw = path.read_bytes()
        except OSError as exc:
            candidates.append(
                LockCandidate(path.name, "", None, None, f"cannot read {path}: {exc}")
            )
            continue
        digest = sha256_bytes(raw)
        if path.is_symlink():
            candidates.append(
                LockCandidate(path.name, digest, None, None, "candidate is a symlink")
            )
            continue
        try:
            text = raw.decode("utf-8-sig")
            lock = parse_lock_text(text, source=f"lock candidate {path}")
            verification = verify_lock_rows(vault_root, lock) if verify_rows else None
        except (UnicodeError, OSError, OnyxianError) as exc:
            candidates.append(LockCandidate(path.name, digest, None, None, str(exc)))
            continue
        candidates.append(LockCandidate(path.name, digest, lock, verification))
    return tuple(candidates)


def candidate_provenance(candidate: LockCandidate) -> str:
    if not candidate.valid:
        return f"{candidate.name}: invalid ({candidate.error})"
    assert candidate.lock is not None
    lock = candidate.lock
    if not lock.generation:
        return f"{candidate.name}: legacy unstamped ledger (generation 0)"
    return f"{candidate.name}: {lock.machine_id} at generation {lock.generation}"


def render_candidates(candidates: tuple[LockCandidate, ...]) -> list[str]:
    lines = ["lock candidates:"]
    for number, candidate in enumerate(candidates, start=1):
        detail = candidate_provenance(candidate)
        if candidate.valid:
            assert candidate.lock is not None
            detail += f", {len(candidate.lock.entries)} entries"
            if candidate.verification is not None:
                verification = candidate.verification
                detail += (
                    f" ({len(verification.matching)} match disk, "
                    f"{len(verification.changed)} changed, "
                    f"{len(verification.missing)} missing, "
                    f"{len(verification.unverified)} unverified)"
                )
        lines.append(f"  [{number}] {detail}")
    return lines


def build_reconcile_plan(
    vault_root: Path,
    candidates: tuple[LockCandidate, ...],
    selected_name: str,
) -> LockReconcilePlan:
    conflict_names = tuple(path.name for path in lock_conflict_sibling_paths(vault_root))
    if not conflict_names:
        raise LockError("no conflicted lock.json sibling was found; there is nothing to reconcile")
    if (
        not selected_name
        or Path(selected_name).name != selected_name
        or any(separator in selected_name for separator in ("/", "\\"))
    ):
        raise LockError("--keep must name one listed lock candidate, not a path")
    selected = next(
        (candidate for candidate in candidates if candidate.name == selected_name),
        None,
    )
    if selected is None:
        available = ", ".join(candidate.name for candidate in candidates)
        raise LockError(f"unknown lock candidate {selected_name!r}; choose one of: {available}")
    if not selected.valid:
        raise LockError(f"cannot keep invalid lock candidate {selected_name!r}: {selected.error}")
    unreadable = next((candidate for candidate in candidates if not candidate.digest), None)
    if unreadable is not None:
        detail = f"{unreadable.name!r}: {unreadable.error}"
        raise LockError(f"cannot safely retire unreadable lock candidate {detail}")
    return LockReconcilePlan(
        candidates=candidates,
        selected_name=selected_name,
        snapshots=tuple((candidate.name, candidate.digest) for candidate in candidates),
        conflict_names=conflict_names,
    )


def render_reconcile(plan: LockReconcilePlan, *, include_candidates: bool = True) -> list[str]:
    lines = render_candidates(plan.candidates) if include_candidates else []
    selected = plan.selected
    assert selected.lock is not None and selected.verification is not None
    verification = selected.verification
    lines.extend(
        [
            f"reconcile: keep {selected.name!r} and rewrite {VAULT_DIR}/lock.json",
            f"  retire sync-conflict sibling(s): {', '.join(plan.conflict_names)}",
        ]
    )
    if verification.changed:
        lines.append(f"  changed on disk (row kept): {', '.join(verification.changed)}")
    if verification.missing:
        lines.append(f"  missing from disk (row kept): {', '.join(verification.missing)}")
    if verification.unverified:
        lines.append(f"  not verifiable (row kept): {', '.join(verification.unverified)}")
    if not (verification.changed or verification.missing or verification.unverified):
        lines.append(f"  all {len(verification.matching)} ledger row(s) match disk")
    return lines


def apply_reconcile(vault_root: Path, plan: LockReconcilePlan) -> LockReconcileResult:
    """Apply a reviewed plan under the caller's vault mutex, reloading every candidate."""
    live = inspect_lock_candidates(vault_root)
    live_snapshots = tuple((candidate.name, candidate.digest) for candidate in live)
    if live_snapshots != plan.snapshots:
        raise LockError("lock candidates changed since review; run `onyxian lock reconcile` again")
    selected = next(
        (candidate for candidate in live if candidate.name == plan.selected_name),
        None,
    )
    if (
        selected is None
        or selected.lock is None
        or selected.verification is None
        or not selected.valid
    ):
        raise LockError("selected lock candidate is no longer valid; run reconciliation again")
    reviewed = plan.selected.verification
    assert reviewed is not None
    if selected.verification.fingerprints != reviewed.fingerprints:
        raise LockError("vault files changed since review; run `onyxian lock reconcile` again")

    # The repair write must order after every fork it just retired, even when the
    # user deliberately keeps an older ledger's rows.
    selected.lock.generation = max(
        candidate.lock.generation
        for candidate in live
        if candidate.valid and candidate.lock is not None
    )
    save_lock(vault_root, selected.lock)
    retired: list[str] = []
    for name in plan.conflict_names:
        path = vault_root / VAULT_DIR / name
        try:
            path.unlink()
        except OSError as exc:
            raise LockError(
                f"rewrote lock.json, but could not retire conflict sibling {name!r}: {exc}"
            ) from None
        retired.append(name)
    return LockReconcileResult(
        generation=selected.lock.generation,
        machine_id=selected.lock.machine_id,
        retired=tuple(retired),
    )

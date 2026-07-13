"""Read and write `.vault/lock.json` — the managed-file ledger (KICKSTART.md §8.1).

The lock records every file the engine has ever written, with the hash of the
exact bytes it wrote. It is machine-maintained, deterministic (sorted entries,
fixed key order, LF, trailing newline), and the single engine-written file that
cannot appear in its own ledger.
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import LockError
from .fsio import read_text, write_text_atomic
from .model import FILE_KINDS, LOCATIONS, Lock, LockEntry

LOCK_VERSION = 1

_ENTRY_KEYS = ("path", "sha256", "module", "module_version", "kind", "location")


def lock_path(vault_root: Path) -> Path:
    return vault_root / ".vault" / "lock.json"


def load_lock(vault_root: Path) -> Lock:
    path = lock_path(vault_root)
    if not path.is_file():
        return Lock()
    try:
        data = json.loads(read_text(path))
    except (OSError, ValueError) as exc:
        raise LockError(f"cannot read lockfile {path}: {exc}") from None
    if not isinstance(data, dict):
        raise LockError(f"lockfile {path} must be a JSON object")
    version = data.get("lock_version")
    if version != LOCK_VERSION:
        raise LockError(
            f"lockfile {path} has lock_version {version!r}; this engine speaks {LOCK_VERSION}"
        )
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        raise LockError(f"lockfile {path}: 'entries' must be a list")

    lock = Lock()
    for i, raw in enumerate(raw_entries):
        where = f"lockfile {path}: entries[{i}]"
        if not isinstance(raw, dict):
            raise LockError(f"{where} must be an object")
        if not set(_ENTRY_KEYS) <= set(raw) or not set(raw) <= {*_ENTRY_KEYS, "declined"}:
            raise LockError(
                f"{where} must have exactly the keys {list(_ENTRY_KEYS)} (plus optional 'declined')"
            )
        if not all(isinstance(raw[k], str) and raw[k] for k in _ENTRY_KEYS):
            raise LockError(f"{where}: all fields must be non-empty strings")
        if "declined" in raw and (not isinstance(raw["declined"], str) or not raw["declined"]):
            raise LockError(f"{where}: 'declined' must be a non-empty string when present")
        if raw["kind"] not in FILE_KINDS:
            raise LockError(f"{where}: kind must be one of {list(FILE_KINDS)}")
        if raw["location"] not in LOCATIONS:
            raise LockError(f"{where}: location must be one of {list(LOCATIONS)}")
        entry = LockEntry(**{k: raw[k] for k in _ENTRY_KEYS}, declined=raw.get("declined", ""))
        if lock.get(entry.path) is not None:
            raise LockError(f"{where}: duplicate path {entry.path!r}")
        lock.put(entry)
    return lock


def render_lock_text(lock: Lock) -> str:
    payload = {
        "lock_version": LOCK_VERSION,
        "entries": [
            {key: getattr(entry, key) for key in _ENTRY_KEYS}
            | ({"declined": entry.declined} if entry.declined else {})
            for entry in lock.sorted_entries()
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def save_lock(vault_root: Path, lock: Lock) -> None:
    write_text_atomic(lock_path(vault_root), render_lock_text(lock))

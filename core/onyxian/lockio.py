"""Read and write `.vault/lock.json` — the managed-file ledger (KICKSTART.md §8.1).

The lock records every file the engine has ever written, with the hash of the
exact bytes it wrote. It is machine-maintained, deterministic (sorted entries,
fixed key order, LF, trailing newline), and the single engine-written file that
cannot appear in its own ledger.
"""

from __future__ import annotations

import json
import os
import re
import socket
from dataclasses import replace
from pathlib import Path

from .errors import LockError, PathError
from .fsio import read_text, write_text_atomic
from .model import FILE_KINDS, LOCATIONS, Lock, LockEntry
from .paths import check_casefold_unique, split_portable

LOCK_VERSION = 1

_ENTRY_KEYS = ("path", "sha256", "module", "module_version", "kind", "location")


def lock_path(vault_root: Path) -> Path:
    return vault_root / ".vault" / "lock.json"


def load_lock(vault_root: Path, *, diagnose_casefold_collisions: bool = False) -> Lock:
    """Load and validate the ledger.

    ``diagnose_casefold_collisions`` is reserved for ``doctor``: the read-only
    diagnostic needs the ambiguous rows in hand to give specific repair advice.
    Every operational caller uses the strict default and fails closed (#56).
    """
    path = lock_path(vault_root)
    if not path.is_file():
        return Lock()
    try:
        text = read_text(path)
    except OSError as exc:
        raise LockError(f"cannot read lockfile {path}: {exc}") from None
    return parse_lock_text(
        text,
        source=f"lockfile {path}",
        diagnose_casefold_collisions=diagnose_casefold_collisions,
    )


def parse_lock_text(
    text: str,
    *,
    source: str,
    diagnose_casefold_collisions: bool = False,
) -> Lock:
    """Parse and validate lock JSON from disk or a checkpoint object."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise LockError(f"cannot read {source}: {exc}") from None
    if not isinstance(data, dict):
        raise LockError(f"{source} must be a JSON object")
    version = data.get("lock_version")
    if version != LOCK_VERSION:
        raise LockError(f"{source} has lock_version {version!r}; this engine speaks {LOCK_VERSION}")
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        raise LockError(f"{source}: 'entries' must be a list")

    has_generation = "generation" in data
    has_machine_id = "machine_id" in data
    if has_generation != has_machine_id:
        raise LockError(f"{source}: 'generation' and 'machine_id' must appear together")
    if has_generation:
        generation = data["generation"]
        machine_id = data["machine_id"]
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise LockError(f"{source}: 'generation' must be a positive integer")
        if not isinstance(machine_id, str) or not machine_id:
            raise LockError(f"{source}: 'machine_id' must be a non-empty string")
        if not machine_id.isprintable():
            raise LockError(f"{source}: 'machine_id' must contain only printable characters")
        if len(machine_id) > 128:
            raise LockError(f"{source}: 'machine_id' must be at most 128 characters")
    else:
        generation = 0
        machine_id = ""

    lock = Lock(generation=generation, machine_id=machine_id)
    for i, raw in enumerate(raw_entries):
        where = f"{source}: entries[{i}]"
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
        # The path's *domain*, like every other field's below. Without this a
        # hand-edited `"../x"` or `"con.md"` parsed fine and blew up later as a bare
        # PathError from whichever caller reached `to_native` first — doctor, remove,
        # or diff (#59). This is the trust boundary; downstream just reads rows.
        try:
            split_portable(raw["path"])
        except PathError as exc:
            raise LockError(f"{where}: {exc}") from None
        if raw["kind"] not in FILE_KINDS:
            raise LockError(f"{where}: kind must be one of {list(FILE_KINDS)}")
        if raw["location"] not in LOCATIONS:
            raise LockError(f"{where}: location must be one of {list(LOCATIONS)}")
        entry = LockEntry(**{k: raw[k] for k in _ENTRY_KEYS}, declined=raw.get("declined", ""))
        if lock.get(entry.path) is not None:
            raise LockError(f"{where}: duplicate path {entry.path!r}")
        lock.put(entry)

    if not diagnose_casefold_collisions:
        try:
            check_casefold_unique((entry.path, entry.module) for entry in lock.sorted_entries())
        except PathError as exc:
            raise LockError(f"{source}: {exc}") from None

    raw_trust = data.get("module_trust", {})
    if not isinstance(raw_trust, dict) or not all(
        isinstance(k, str) and k and isinstance(v, str) and v for k, v in raw_trust.items()
    ):
        raise LockError(f"{source}: 'module_trust' must map non-empty strings to non-empty strings")
    lock.module_trust = dict(raw_trust)
    return lock


def render_lock_text(lock: Lock) -> str:
    payload: dict[str, object] = {
        "lock_version": LOCK_VERSION,
    }
    if lock.generation:
        payload["generation"] = lock.generation
        payload["machine_id"] = lock.machine_id
    payload["entries"] = [
        {key: getattr(entry, key) for key in _ENTRY_KEYS}
        | ({"declined": entry.declined} if entry.declined else {})
        for entry in lock.sorted_entries()
    ]
    # Omitted when empty so every vault without external modules keeps its exact
    # pre-existing lock bytes (golden stability); sorted for determinism.
    if lock.module_trust:
        payload["module_trust"] = {k: lock.module_trust[k] for k in sorted(lock.module_trust)}
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def current_machine_id() -> str:
    """A stable, human-recognizable writer id, overridable for containers and CI."""
    raw = os.environ.get("ONYXIAN_MACHINE_ID") or socket.gethostname()
    normalized = re.sub(r"\s+", "-", raw.strip())
    return normalized[:128] or "unknown-machine"


def save_lock(vault_root: Path, lock: Lock) -> None:
    generation = lock.generation + 1
    machine_id = current_machine_id()
    stamped = replace(lock, generation=generation, machine_id=machine_id)
    write_text_atomic(lock_path(vault_root), render_lock_text(stamped))
    # The in-memory ledger advances only after the atomic write succeeds. A failed
    # save can therefore be retried without inventing a generation that never landed.
    lock.generation = generation
    lock.machine_id = machine_id

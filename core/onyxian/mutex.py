"""A coarse per-vault write mutex: one writer per vault at a time (issue #8).

Every command that mutates the ledger rewrites `.vault/lock.json` wholesale, and
the applier saves after every write. Two processes mutating the same vault at once
interleave those whole-file saves and the last writer clobbers the other's ledger.
This serializes them: a command about to write acquires an exclusive
`.vault/apply.lock`; a second process finds it and fails fast with `VaultBusyError`
naming the file, the holding pid, and when it started. The lock is transient —
created before the writes, removed before the command returns — so it never appears
in `lock.json` or any generated tree.

`O_EXCL` is the portable primitive here: atomic create-exclusive works on macOS,
Linux, and Windows alike, whereas `fcntl`/`flock` does not exist on Windows. The
stale-lock story is report-only, never auto-break (consistent with "no force
flags"): the message names the exact file to delete and the pid/time to check.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .errors import VaultBusyError

# Mirrors fsio._replace_with_retry: on Windows a scanner can briefly hold a
# freshly-touched file, turning the unlink into a transient sharing violation.
_UNLINK_ATTEMPTS = 10


@contextmanager
def vault_mutex(vault_root: Path) -> Iterator[None]:
    """Hold an exclusive write lock on ``vault_root`` for the duration of the block.

    Creates ``.vault/`` if it does not yet exist (init/adopt acquire before the
    vault dir is written), so the whole seed+apply sequence is guarded. Raises
    :class:`VaultBusyError` if another process already holds the lock; the lock
    file is removed on both normal and error exits.
    """
    lock_path = vault_root / ".vault" / "apply.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise VaultBusyError(_busy_message(lock_path)) from None
    try:
        os.write(fd, _stamp().encode("utf-8"))
    finally:
        os.close(fd)
    try:
        yield
    finally:
        _unlink_with_retry(lock_path)


def _stamp() -> str:
    """The holder's identity, written into the lock so a contender can report it."""
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{os.getpid()}\n{started}\n"


def _busy_message(lock_path: Path) -> str:
    pid, started = _read_stamp(lock_path)
    return (
        f"another onyxian process is working on this vault (started {started}, "
        f"pid {pid}); if that process is gone, delete .vault/apply.lock and re-run"
    )


def _read_stamp(lock_path: Path) -> tuple[str, str]:
    """(pid, started) from the lock, tolerating an empty/partial file (the holder
    may have created it but not yet written the stamp)."""
    try:
        lines = lock_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    pid = lines[0] if len(lines) >= 1 and lines[0] else "unknown"
    started = lines[1] if len(lines) >= 2 and lines[1] else "unknown"
    return pid, started


def _unlink_with_retry(lock_path: Path) -> None:
    delay = 0.02
    for attempt in range(_UNLINK_ATTEMPTS):
        try:
            lock_path.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt == _UNLINK_ATTEMPTS - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.4)

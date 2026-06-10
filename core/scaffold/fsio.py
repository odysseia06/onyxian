"""Deterministic file IO.

Everything the engine writes is UTF-8 without BOM, LF line endings, written
atomically (temp file + rename in the same directory). Determinism is what
makes idempotency (P3) and golden-file tests (§11) byte-exact across the
three-OS matrix.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

_REPLACE_ATTEMPTS = 10


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def encode_text(text: str) -> bytes:
    """Engine-canonical bytes for text content: LF, UTF-8, no BOM."""
    return normalize_newlines(text).encode("utf-8")


def read_text(path: Path) -> str:
    """Read text tolerating a BOM (some Windows editors add one); never write one back."""
    return path.read_text(encoding="utf-8-sig")


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` via a temp file + rename in the same directory.

    A crash mid-write leaves either the old file or a stray ``*.onyx-tmp`` to
    sweep by hand — never a torn target file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".onyx-tmp")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    _replace_with_retry(tmp, path)


def _replace_with_retry(tmp: Path, path: Path) -> None:
    """``os.replace`` with backoff: on Windows, virus scanners and indexers
    briefly hold freshly-written files, turning the rename into a transient
    sharing violation (KICKSTART.md §15, Windows breakage risk). Retrying a
    few times over ~1s absorbs that; a real permission problem still raises.
    """
    delay = 0.02
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.4)


def write_text_atomic(path: Path, text: str) -> bytes:
    """Atomically write canonical text; returns the exact bytes written."""
    data = encode_text(text)
    write_bytes_atomic(path, data)
    return data


def iter_files(root: Path) -> list[Path]:
    """All files under ``root``, sorted by their POSIX-style relative path."""
    files = [p for p in root.rglob("*") if p.is_file()]
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())

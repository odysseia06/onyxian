"""Vault-relative path discipline (KICKSTART.md §9.5).

Every path the engine plans or records is *portable form*: vault-relative,
forward-slash separated, and valid on macOS, Linux, and Windows alike. A path
that is legal on the current OS but would break on another is rejected here,
at plan time, not discovered by a user on the other OS.
"""

from __future__ import annotations

from pathlib import Path

from .errors import PathError

# Windows device names are reserved in every directory, with or without an
# extension ("CON", "con.md", "COM1.base" are all unusable).
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

_INVALID_CHARS = frozenset('<>:"|?*')


def split_portable(path: str, *, origin: str = "") -> tuple[str, ...]:
    """Validate ``path`` as portable form and return its segments.

    Raises :class:`PathError` with the precise reason and, when provided, the
    ``origin`` (which manifest or asset produced the path).
    """
    where = f" (from {origin})" if origin else ""
    if not isinstance(path, str) or not path:
        raise PathError(f"empty path{where}")
    if "\\" in path:
        raise PathError(f"backslash in path {path!r}{where}; portable form uses '/'")
    if path.startswith("/") or path.endswith("/"):
        raise PathError(f"path {path!r} must be relative with no trailing slash{where}")
    if len(path) >= 2 and path[1] == ":":
        raise PathError(f"path {path!r} looks absolute (drive letter){where}")

    segments = path.split("/")
    for seg in segments:
        if seg in ("", ".", ".."):
            raise PathError(f"segment {seg!r} not allowed in {path!r}{where}")
        if seg != seg.strip() or seg.endswith("."):
            raise PathError(
                f"segment {seg!r} in {path!r} has leading/trailing space or trailing dot"
                f" (breaks on Windows){where}"
            )
        for ch in seg:
            if ch in _INVALID_CHARS or ord(ch) < 0x20:
                raise PathError(
                    f"character {ch!r} in segment {seg!r} of {path!r} is invalid on Windows{where}"
                )
        stem = seg.split(".", 1)[0]
        if stem.upper() in _WINDOWS_RESERVED:
            raise PathError(
                f"segment {seg!r} in {path!r} is a reserved Windows device name{where}"
            )
    return tuple(segments)


def to_native(root: Path, portable: str) -> Path:
    """Resolve portable form against a vault root as a native path."""
    return root.joinpath(*split_portable(portable))


def parent_portable(portable: str) -> str | None:
    """Portable form of the parent, or None for a top-level entry."""
    if "/" not in portable:
        return None
    return portable.rsplit("/", 1)[0]

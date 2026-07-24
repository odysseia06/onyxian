"""Vault-relative path discipline (KICKSTART.md §9.5).

Every path the engine plans or records is *portable form*: vault-relative,
forward-slash separated, and valid on macOS, Linux, and Windows alike. A path
that is legal on the current OS but would break on another is rejected here,
at plan time, not discovered by a user on the other OS.
"""

from __future__ import annotations

from collections.abc import Iterable
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
            raise PathError(f"segment {seg!r} in {path!r} is a reserved Windows device name{where}")
    return tuple(segments)


def to_native(root: Path, portable: str) -> Path:
    """Resolve portable form against a vault root as a native path."""
    return root.joinpath(*split_portable(portable))


def first_symlink_component(root: Path, portable: str) -> str | None:
    """Portable prefix of the first component of ``portable`` that is a symlink
    under ``root``, or None when no component is a link.

    Content hashes follow a symlink while ``os.replace`` swaps out the link
    itself, so every byte-level safety check lies at a symlinked path (issue
    #53). The engine never creates symlinks (KICKSTART.md §9.5); one found on a
    target path is the user's, and every write path treats it as untouchable.
    """
    current = root
    prefix = ""
    for segment in split_portable(portable):
        current = current / segment
        prefix = f"{prefix}/{segment}" if prefix else segment
        if current.is_symlink():
            return prefix
    return None


def parent_portable(portable: str) -> str | None:
    """Portable form of the parent, or None for a top-level entry."""
    if "/" not in portable:
        return None
    return portable.rsplit("/", 1)[0]


def check_casefold_unique(paths: Iterable[tuple[str, str]]) -> None:
    """Raise :class:`PathError` when two portable paths (or their parent prefixes)
    differ only in case — they collide on case-insensitive filesystems (issue #8).

    ``paths`` is ``(portable_path, module)`` pairs. On Linux two paths differing
    only in case are distinct files; on the macOS and Windows defaults the second
    ``create`` lands on the first, so the same config yields divergent vaults
    across the 3-OS matrix. Rejecting it here, at plan time, keeps that from ever
    reaching a user on the other OS.

    Prefixes are walked (``a``, ``a/b``, ``a/b/c.md``) so a directory
    (``Templates``) and a file under a differently-cased sibling (``templates/x.md``)
    are caught, not only whole-path twins.
    """
    seen: dict[str, tuple[str, str, str]] = {}  # casefold(prefix) -> (spelling, path, module)
    for path, module in paths:
        prefix = ""
        for segment in path.split("/"):
            prefix = f"{prefix}/{segment}" if prefix else segment
            first = seen.get(prefix.casefold())
            if first is None:
                seen[prefix.casefold()] = (prefix, path, module)
            elif first[0] != prefix:
                raise PathError(
                    f"paths {first[1]!r} (module {first[2]!r}) and {path!r} (module {module!r}) "
                    f"differ only in case; they would collide on a case-insensitive filesystem "
                    f"(the macOS and Windows defaults)"
                )

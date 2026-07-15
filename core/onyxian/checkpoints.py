"""Opt-in vault checkpoints (issue #11, phase 1): a git-backed recovery net.

A checkpoint is a commit in a **separate** git repository whose git dir lives at
``.vault/checkpoints/`` and whose work tree is the vault root. Because the git dir
is passed explicitly, a user's own ``.git`` is never read or written, and a vault
with no git repository of its own gains none. ``git`` is a system tool, not a
runtime dependency (deps stay exactly PyYAML) — when it is absent the guard
degrades to a single warning and a clean exit (P2: tooling failures are never
fatal to the vault). This is a recovery net, not scope enforcement: it makes any
out-of-scope write cheap to see and undo, nothing more.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

CHECKPOINTS_REL = ".vault/checkpoints"

# Snapshot the whole vault except the checkpoint repo itself and Obsidian's
# volatile per-machine UI state. Patterns are work-tree-relative (vault root).
_EXCLUDES = ("/.vault/checkpoints/", ".obsidian/workspace*")

# Overrides applied to every invocation so a snapshot is identical regardless of
# the user's global git config: a fixed identity (works with no global identity,
# e.g. CI), no signing or hook surprises, verbatim bytes across platforms, and
# literal UTF-8 paths in status/diff output.
_CONFIG = (
    "-c", "user.name=Onyxian",
    "-c", "user.email=onyxian@localhost",
    "-c", "commit.gpgsign=false",
    "-c", "core.autocrlf=false",
    "-c", "core.safecrlf=false",
    "-c", "core.quotepath=false",
    "-c", "init.defaultBranch=main",
)

_DATE_FMT = "--date=format:%Y-%m-%d %H:%M"
_SEP = "\x1f"
_TIMEOUT = 180


class CheckpointUnavailable(Exception):
    """git is not on PATH; the caller degrades this to a warning and exits 0."""


@dataclass(frozen=True)
class Snapshot:
    """The outcome of a ``snapshot`` call. ``created`` is False for a no-op run."""

    created: bool
    checkpoint_id: str = ""
    when: str = ""
    files_changed: int = 0
    baseline: bool = False


@dataclass(frozen=True)
class CheckpointInfo:
    """One row for ``checkpoint list``: a past snapshot, newest first."""

    checkpoint_id: str
    when: str
    files_changed: int
    baseline: bool


_SHORTSTAT_RE = re.compile(r"(\d+) files? changed")


def _git_dir(vault_root: Path) -> Path:
    return vault_root / CHECKPOINTS_REL


def _git(
    vault_root: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git")
    if git is None:
        raise CheckpointUnavailable("git is not on PATH")
    return subprocess.run(
        [git, *_CONFIG, f"--git-dir={_git_dir(vault_root)}", f"--work-tree={vault_root}", *args],
        capture_output=True,
        text=True,
        check=check,
        timeout=_TIMEOUT,
    )


def _ensure_repo(vault_root: Path) -> None:
    gd = _git_dir(vault_root)
    if not (gd / "HEAD").is_file():
        gd.mkdir(parents=True, exist_ok=True)
        _git(vault_root, "init", "--quiet")
    info = gd / "info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "exclude").write_text("\n".join(_EXCLUDES) + "\n", encoding="utf-8", newline="\n")


def _has_head(vault_root: Path) -> bool:
    return _git(vault_root, "rev-parse", "--verify", "--quiet", "HEAD", check=False).returncode == 0


def snapshot(vault_root: Path) -> Snapshot:
    """Record the current vault state as one commit in the checkpoint repo."""
    _ensure_repo(vault_root)
    baseline = not _has_head(vault_root)
    _git(vault_root, "add", "-A")
    staged = _git(vault_root, "diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        # Nothing changed since the last snapshot; re-running is a no-op (P3).
        return Snapshot(created=False)
    files_changed = len(staged.splitlines())
    _git(vault_root, "commit", "--quiet", "--no-verify", "-m", "checkpoint")
    head = _git(vault_root, "log", "-1", _DATE_FMT, f"--format=%h{_SEP}%cd").stdout.strip()
    checkpoint_id, _, when = head.partition(_SEP)
    return Snapshot(
        created=True,
        checkpoint_id=checkpoint_id,
        when=when,
        files_changed=files_changed,
        baseline=baseline,
    )


def has_checkpoints(vault_root: Path) -> bool:
    """True once at least one snapshot exists (the checkpoint repo has a commit)."""
    return (_git_dir(vault_root) / "HEAD").is_file() and _has_head(vault_root)


def list_snapshots(vault_root: Path) -> list[CheckpointInfo]:
    """Every snapshot, newest first. Empty when no checkpoint has been taken yet."""
    if not has_checkpoints(vault_root):
        return []
    out = _git(
        vault_root, "log", _DATE_FMT, f"--format=%h{_SEP}%cd{_SEP}%p", "--shortstat"
    ).stdout
    infos: list[CheckpointInfo] = []
    for line in out.splitlines():
        if _SEP in line:
            cid, when, parents = line.split(_SEP)
            infos.append(
                CheckpointInfo(
                    checkpoint_id=cid, when=when, files_changed=0, baseline=parents.strip() == ""
                )
            )
        elif infos:
            m = _SHORTSTAT_RE.search(line)
            if m:
                infos[-1] = replace(infos[-1], files_changed=int(m.group(1)))
    return infos


def diff_since_last(vault_root: Path) -> list[tuple[str, str]]:
    """Working-tree changes since the last snapshot as (status_letter, path), path-sorted.

    Untracked files read as additions (``A``); the letters mirror git's porcelain
    XY codes collapsed to a single, human-facing verb.
    """
    out = _git(vault_root, "status", "--porcelain=v1", "--untracked-files=all").stdout
    changes: list[tuple[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        code, path = line[:2], line[3:]
        if "D" in code:
            letter = "D"
        elif code == "??" or "A" in code:
            letter = "A"
        else:
            letter = "M"
        changes.append((letter, path))
    return changes

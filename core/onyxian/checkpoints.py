"""Opt-in vault checkpoints (issues #11 and #73): a git-backed recovery net.

A checkpoint is a commit in a **separate** git repository whose git dir lives at
``.vault/checkpoints/`` and whose work tree is the vault root. Because the git dir
is passed explicitly, a user's own ``.git`` is never read or written, and a vault
with no git repository of its own gains none. ``git`` is a system tool, not a
runtime dependency (deps stay exactly PyYAML). Snapshot/list/diff are guard
operations, so an absent, failing, or hung git degrades to one warning and a clean
exit (P2: a SessionStart hook never breaks the session). Restore is an explicit
write request and therefore fails honestly when the same tooling is unavailable;
it never reports success without restoring. This is a recovery net, not scope
enforcement: it makes any out-of-scope write cheap to see and undo, nothing more.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from .errors import ApplyError, CheckpointError
from .fsio import sha256_bytes, sha256_file, write_bytes_atomic
from .lockio import parse_lock_text, save_lock
from .model import KIND_MANAGED, Lock, LockEntry
from .paths import check_casefold_unique, first_symlink_component, split_portable, to_native

CHECKPOINTS_REL = ".vault/checkpoints"

# Snapshot the whole vault except the checkpoint repo itself, Obsidian's volatile
# per-machine UI state, and the engine's own transients: a snapshot can be taken
# while another process holds the write mutex, and restoring a committed
# `apply.lock` would resurrect a stale lock and brick the vault (#60). A
# `*.onyxian-tmp` is half of an interrupted write — nobody wants it back either.
# Patterns are work-tree-relative (vault root) and forward-only: gitignore does not
# untrack, so a repo that already committed the lock keeps it until the first
# snapshot taken with no lock on disk stages the deletion.
_EXCLUDES = (
    "/.vault/checkpoints/",
    "/.vault/apply.lock",
    "*.onyxian-tmp",
    ".obsidian/workspace*",
)

# Recovery needs these two files even when a vault's own `.gitignore` hides
# `.vault/`: config keeps restore reachable, and lock makes path restores
# ledger-aware. `git add -A` still stages deletions once either path is tracked.
_RECOVERY_METADATA = (".vault/config.yaml", ".vault/lock.json")

# Overrides applied to every invocation so a snapshot is identical regardless of
# the user's global git config: a fixed identity (works with no global identity,
# e.g. CI), no signing or hook surprises, verbatim bytes across platforms, and
# literal UTF-8 paths in status/diff output.
_CONFIG = (
    "-c",
    "user.name=Onyxian",
    "-c",
    "user.email=onyxian@localhost",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "core.autocrlf=false",
    "-c",
    "core.safecrlf=false",
    "-c",
    "core.quotepath=false",
    "-c",
    "init.defaultBranch=main",
)

_DATE_FMT = "--date=format:%Y-%m-%d %H:%M"
_SEP = "\x1f"
_TIMEOUT = 180


class CheckpointUnavailable(Exception):
    """The guard could not run: git is absent, refused, or hung. The message is the
    reason, in one line — the caller prints it as a warning and exits 0 (#60)."""


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


@dataclass(frozen=True)
class RestoreChange:
    """One reviewed file replacement in a checkpoint restore."""

    path: str
    status: str
    before_sha256: str | None
    content: bytes | None
    before_ledger_entry: LockEntry | None = None
    ledger_entry: LockEntry | None = None
    restore_ledger: bool = False


@dataclass(frozen=True)
class RestorePlan:
    """The exact checkpoint bytes and live preconditions shown before confirmation."""

    checkpoint_id: str
    changes: tuple[RestoreChange, ...]
    ledger_paths: tuple[str, ...]
    verified_ledger_paths: tuple[str, ...]
    checkpoint_lock: Lock
    restore_lockfile: bool
    lockfile_before_sha256: str | None
    scopes: tuple[str, ...]
    reviewed_current_paths: tuple[str, ...]


@dataclass
class RestoreResult:
    """Applied and skipped restore paths, mirroring the applier's race-safe report."""

    restored: list[str]
    skipped: list[tuple[str, str]]


_SHORTSTAT_RE = re.compile(r"(\d+) files? changed")
_CHECKPOINT_ID_RE = re.compile(r"[0-9a-fA-F]{4,64}")


def _git_dir(vault_root: Path) -> Path:
    return vault_root / CHECKPOINTS_REL


def _git(
    vault_root: Path, *args: str, check: bool = True, timeout: int = _TIMEOUT
) -> subprocess.CompletedProcess[str]:
    """Run one checkpoint-repo git command.

    Every way git can fail the caller arrives as :class:`CheckpointUnavailable`, not
    just its absence: a git dir that is not a repo, a corrupted ref, a hang, and a
    binary that will not launch at all are tooling failures too — ``shutil.which``
    matches on name, never on whether the file actually execs. P2 says none of them
    may be fatal to the vault, least of all from the SessionStart hook (#60).

    ``timeout`` defaults to the snapshot-sized budget; read-only callers pass a short
    one so a hung git cannot stall them for minutes (#95).
    """
    git = shutil.which("git")
    if git is None:
        raise CheckpointUnavailable("git is not on PATH")
    try:
        return subprocess.run(
            [
                git,
                *_CONFIG,
                f"--git-dir={_git_dir(vault_root)}",
                f"--work-tree={vault_root}",
                *args,
            ],
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise CheckpointUnavailable(f"git {args[0]} timed out after {timeout}s") from None
    except subprocess.CalledProcessError as exc:
        raise CheckpointUnavailable(f"git {args[0]} failed: {_one_line(exc.stderr)}") from None
    except OSError as exc:
        raise CheckpointUnavailable(f"git {args[0]} could not run: {exc}") from None


def _git_bytes(
    vault_root: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[bytes]:
    """Binary-output twin of :func:`_git`, used for exact checkpoint file bytes."""
    git = shutil.which("git")
    if git is None:
        raise CheckpointUnavailable("git is not on PATH")
    try:
        return subprocess.run(
            [
                git,
                *_CONFIG,
                f"--git-dir={_git_dir(vault_root)}",
                f"--work-tree={vault_root}",
                *args,
            ],
            capture_output=True,
            check=check,
            timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise CheckpointUnavailable(f"git {args[0]} timed out after {_TIMEOUT}s") from None
    except subprocess.CalledProcessError as exc:
        raise CheckpointUnavailable(f"git {args[0]} failed: {_one_line(exc.stderr)}") from None
    except OSError as exc:
        raise CheckpointUnavailable(f"git {args[0]} could not run: {exc}") from None


def _one_line(stderr: str | bytes | None) -> str:
    """git's own reason, collapsed to its first line: the caller renders this as a
    single warning and must not spray a diagnostic into a session hook."""
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    for line in (stderr or "").splitlines():
        if line.strip():
            return line.strip()
    return "no error output"


def _ensure_repo(vault_root: Path) -> None:
    """Create the checkpoint repo if needed and refresh its exclude list.

    Its filesystem work degrades like git's own: a read-only or otherwise
    unwritable ``.vault/`` is a tooling failure, not a reason to kill a session (#60).
    """
    gd = _git_dir(vault_root)
    try:
        if not (gd / "HEAD").is_file():
            gd.mkdir(parents=True, exist_ok=True)
            _git(vault_root, "init", "--quiet")
        info = gd / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "exclude").write_text("\n".join(_EXCLUDES) + "\n", encoding="utf-8", newline="\n")
    except OSError as exc:
        raise CheckpointUnavailable(f"the checkpoint repo is unwritable: {exc}") from None


def _has_head(vault_root: Path, timeout: int = _TIMEOUT) -> bool:
    """True once the repo has a commit.

    ``--verify --quiet`` exits 1 for a ref that does not resolve and 128 for a
    fatal — a git dir that is not a repo, a missing object store, a git dir that is
    a regular file. Reading every non-zero as "no snapshots" made a repo git cannot
    read look like one that simply had not run yet (#93), so only 1 stays a soft
    "no". Note 1 is not exclusively the no-commits-yet case (a HEAD pointing at a
    missing branch also lands here); doctor tells those apart by the checkpoint
    directory existing, not by this return value.
    """
    proc = _git(
        vault_root, "rev-parse", "--verify", "--quiet", "HEAD", check=False, timeout=timeout
    )
    if proc.returncode not in (0, 1):
        raise CheckpointUnavailable(f"git rev-parse failed: {_one_line(proc.stderr)}")
    return proc.returncode == 0


def snapshot(vault_root: Path) -> Snapshot:
    """Record the current vault state as one commit in the checkpoint repo."""
    _ensure_repo(vault_root)
    baseline = not _has_head(vault_root)
    _git(vault_root, "add", "-A")
    force_paths = [
        path
        for path in _RECOVERY_METADATA
        if (vault_root / path).is_file() or (vault_root / path).is_symlink()
    ]
    if force_paths:
        _git(vault_root, "add", "-f", "--", *force_paths)
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


def has_checkpoints(vault_root: Path, timeout: int = _TIMEOUT) -> bool:
    """True once at least one snapshot exists (the checkpoint repo has a commit)."""
    return (_git_dir(vault_root) / "HEAD").is_file() and _has_head(vault_root, timeout=timeout)


def list_snapshots(vault_root: Path, timeout: int = _TIMEOUT) -> list[CheckpointInfo]:
    """Every snapshot, newest first. Empty when no checkpoint has been taken yet."""
    if not has_checkpoints(vault_root, timeout=timeout):
        return []
    out = _git(
        vault_root,
        "log",
        _DATE_FMT,
        f"--format=%h{_SEP}%cd{_SEP}%p",
        "--shortstat",
        timeout=timeout,
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


def _resolve_checkpoint(vault_root: Path, checkpoint_id: str) -> tuple[str, str]:
    """Return (full commit id, canonical short id), rejecting revision syntax."""
    if not _CHECKPOINT_ID_RE.fullmatch(checkpoint_id):
        raise CheckpointError(
            f"invalid checkpoint id {checkpoint_id!r}; use an id from `onyxian checkpoint list`"
        )
    proc = _git(
        vault_root,
        "rev-parse",
        "--verify",
        "--quiet",
        f"{checkpoint_id}^{{commit}}",
        check=False,
    )
    if proc.returncode == 1:
        raise CheckpointError(
            f"checkpoint {checkpoint_id!r} was not found; run `onyxian checkpoint list`"
        )
    if proc.returncode != 0:
        raise CheckpointUnavailable(f"git rev-parse failed: {_one_line(proc.stderr)}")
    commit = proc.stdout.strip()
    short = _git(vault_root, "rev-parse", "--short", commit).stdout.strip()
    return commit, short


def _checkpoint_blob(
    vault_root: Path,
    commit: str,
    path: str,
    *,
    required: bool = False,
) -> bytes | None:
    proc = _git_bytes(vault_root, "show", f"{commit}:{path}", check=False)
    if proc.returncode == 0:
        return proc.stdout
    if required:
        raise CheckpointUnavailable(f"git show failed: {_one_line(proc.stderr)}")
    return None


def _checkpoint_lock(
    vault_root: Path,
    commit: str,
    checkpoint_id: str,
    *,
    present: bool,
) -> Lock:
    raw = _checkpoint_blob(
        vault_root,
        commit,
        ".vault/lock.json",
        required=present,
    )
    if raw is None:
        return Lock()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CheckpointError(
            f"checkpoint {checkpoint_id} has a non-UTF-8 .vault/lock.json: {exc}"
        ) from None
    return parse_lock_text(
        text,
        source=f"checkpoint {checkpoint_id} .vault/lock.json",
    )


def _nul_paths(raw: bytes, *, source: str) -> set[str]:
    paths: set[str] = set()
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            path = item.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CheckpointError(f"{source} contains a non-UTF-8 path: {exc}") from None
        paths.add(path)
    return paths


def _checkpoint_tree(vault_root: Path, commit: str) -> dict[str, tuple[str, str, str]]:
    raw = _git_bytes(vault_root, "ls-tree", "-r", "-z", commit).stdout
    entries: dict[str, tuple[str, str, str]] = {}
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            metadata, raw_path = item.split(b"\t", 1)
            mode, object_type, object_id = metadata.split(b" ", 2)
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise CheckpointError(f"the checkpoint has an unreadable tree entry: {exc}") from None
        entries[path] = (
            mode.decode("ascii"),
            object_type.decode("ascii"),
            object_id.decode("ascii"),
        )
    return entries


def _file_fingerprints(path: Path, git_algorithm: str) -> tuple[str, str]:
    """Return (plain sha256, git blob id) in one streaming read."""
    size = path.stat().st_size
    plain = hashlib.sha256()
    git_blob = hashlib.sha1(usedforsecurity=False) if git_algorithm == "sha1" else hashlib.sha256()
    git_blob.update(f"blob {size}\0".encode("ascii"))
    bytes_read = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            bytes_read += len(chunk)
            plain.update(chunk)
            git_blob.update(chunk)
    if bytes_read != size:
        raise CheckpointError(f"{path} changed while its restore review was being built; run again")
    return plain.hexdigest(), git_blob.hexdigest()


def _current_paths(vault_root: Path) -> set[str]:
    raw = _git_bytes(
        vault_root,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
    ).stdout
    return _nul_paths(raw, source="the checkpoint work tree")


def _excluded_from_restore(path: str) -> bool:
    """The checkpoint repo and volatile/transient files are never restore targets."""
    return (
        path == ".git"
        or path.startswith(".git/")
        or path == CHECKPOINTS_REL
        or path.startswith(CHECKPOINTS_REL + "/")
        or path == ".vault/apply.lock"
        or path.endswith(".onyxian-tmp")
        or path.startswith(".obsidian/workspace")
    )


def _selected(path: str, scopes: tuple[str, ...]) -> bool:
    return not scopes or any(path == scope or path.startswith(scope + "/") for scope in scopes)


def plan_restore(
    vault_root: Path,
    checkpoint_id: str,
    paths: list[str],
    current_lock: Lock,
) -> RestorePlan:
    """Build the exact whole-vault or path-scoped plan shown at the gate."""
    commit, short = _resolve_checkpoint(vault_root, checkpoint_id)
    scopes: list[str] = []
    for raw_path in paths:
        path = raw_path.replace("\\", "/")
        split_portable(path, origin="the checkpoint restore path argument")
        if _excluded_from_restore(path):
            raise CheckpointError(f"{path!r} is excluded from checkpoints and cannot be restored")
        if path not in scopes:
            scopes.append(path)

    checkpoint_tree = _checkpoint_tree(vault_root, commit)
    all_checkpoint_paths = set(checkpoint_tree)
    checkpoint_lock = _checkpoint_lock(
        vault_root,
        commit,
        short,
        present=".vault/lock.json" in all_checkpoint_paths,
    )
    checkpoint_paths = {path for path in all_checkpoint_paths if not _excluded_from_restore(path)}
    current_paths = {
        path for path in _current_paths(vault_root) if not _excluded_from_restore(path)
    }
    scope_tuple = tuple(scopes)
    restore_lockfile = _selected(".vault/lock.json", scope_tuple)
    candidates = sorted(
        path for path in checkpoint_paths | current_paths if _selected(path, scope_tuple)
    )
    reviewed_current_paths = tuple(
        sorted(path for path in current_paths if _selected(path, scope_tuple))
    )
    if scopes:
        unmatched = [
            scope
            for scope in scopes
            if not any(path == scope or path.startswith(scope + "/") for path in candidates)
        ]
        if unmatched:
            raise CheckpointError(f"no checkpoint or current vault path matches {unmatched[0]!r}")
    check_casefold_unique((path, "checkpoint restore") for path in candidates)

    changes: list[RestoreChange] = []
    ledger_paths: list[str] = []
    verified_ledger_paths: list[str] = []
    lockfile_before_sha256: str | None = None
    git_algorithm = "sha1" if len(commit) == 40 else "sha256"
    for path in candidates:
        if path in checkpoint_tree:
            mode, object_type, source_object_id = checkpoint_tree[path]
        else:
            mode, object_type, source_object_id = "", "", ""
        if path in checkpoint_tree and (object_type != "blob" or mode not in ("100644", "100755")):
            kind = "a symlink" if mode == "120000" else "not a regular file"
            raise CheckpointError(f"checkpoint path {path!r} is {kind} and cannot be restored")
        try:
            link = first_symlink_component(vault_root, path)
            if link is not None:
                raise CheckpointError(
                    f"cannot restore {path!r}: {link!r} is a symlink, and Onyxian never "
                    "writes through or replaces links"
                )
            target = to_native(vault_root, path)
            if target.exists() and not target.is_file():
                raise CheckpointError(f"cannot restore {path!r}: it is not a regular file on disk")
            if target.is_file():
                before_sha256, current_object_id = _file_fingerprints(target, git_algorithm)
            else:
                before_sha256, current_object_id = None, None
        except (OSError, ApplyError) as exc:
            raise CheckpointError(f"cannot inspect {path!r} for restore: {exc}") from None
        if path == ".vault/lock.json":
            lockfile_before_sha256 = before_sha256
        if path not in checkpoint_paths and before_sha256 is not None:
            status = "D"
        elif path in checkpoint_paths and before_sha256 is None:
            status = "A"
        elif path in checkpoint_paths and current_object_id != source_object_id:
            status = "M"
        else:
            status = ""
        content = (
            _checkpoint_blob(vault_root, commit, path, required=True)
            if status in ("A", "M")
            else None
        )
        checkpoint_sha256: str | None
        if content is not None:
            checkpoint_sha256 = sha256_bytes(content)
        elif path in checkpoint_paths:
            checkpoint_sha256 = before_sha256
        else:
            checkpoint_sha256 = None
        historical_entry = checkpoint_lock.get(path)
        before_ledger_entry = current_lock.get(path)
        ledger_verified = (
            historical_entry is not None
            and historical_entry.kind == KIND_MANAGED
            and checkpoint_sha256 is not None
            and historical_entry.sha256 == checkpoint_sha256
        )
        restore_ledger = (
            bool(scopes) and not restore_lockfile and before_ledger_entry != historical_entry
        )
        if restore_ledger:
            ledger_paths.append(path)
            if ledger_verified:
                verified_ledger_paths.append(path)

        if status or path in ledger_paths:
            changes.append(
                RestoreChange(
                    path=path,
                    status=status,
                    before_sha256=before_sha256,
                    content=content,
                    before_ledger_entry=before_ledger_entry,
                    ledger_entry=historical_entry,
                    restore_ledger=restore_ledger,
                )
            )
    return RestorePlan(
        checkpoint_id=short,
        changes=tuple(changes),
        ledger_paths=tuple(ledger_paths),
        verified_ledger_paths=tuple(verified_ledger_paths),
        checkpoint_lock=checkpoint_lock,
        restore_lockfile=restore_lockfile,
        lockfile_before_sha256=lockfile_before_sha256,
        scopes=scope_tuple,
        reviewed_current_paths=reviewed_current_paths,
    )


def render_restore(plan: RestorePlan) -> list[str]:
    lines = [f"restore checkpoint {plan.checkpoint_id}:"]
    for change in plan.changes:
        if change.status:
            lines.append(f"  {change.status}  {change.path}")
        elif change.restore_ledger:
            lines.append(
                f"  =  {change.path}  [content unchanged; restoring checkpoint ledger row]"
            )
    if plan.ledger_paths:
        count = len(plan.ledger_paths)
        verified = len(plan.verified_ledger_paths)
        detail = f"restoring checkpoint ledger state for {count} path{'' if count == 1 else 's'}"
        if verified:
            detail += f"; re-verifying {verified} managed file{'' if verified == 1 else 's'}"
        lines.append(f"  ~  .vault/lock.json ({detail})")
    return lines


def _restore_recheck(vault_root: Path, path: str, before_sha256: str | None) -> str | None:
    """Return a skip reason when a reviewed path no longer has its reviewed state."""
    target = to_native(vault_root, path)
    try:
        link = first_symlink_component(vault_root, path)
        if link is not None:
            return "state changed since the restore review; run restore again"
        if before_sha256 is None:
            unchanged = not target.exists() and not target.is_symlink()
        else:
            unchanged = target.is_file() and sha256_file(target) == before_sha256
    except (OSError, ApplyError) as exc:
        return f"could not recheck: {exc}"
    if unchanged:
        return None
    return "state changed since the restore review; run restore again"


def apply_restore(vault_root: Path, plan: RestorePlan, lock: Lock) -> RestoreResult:
    """Apply reviewed file bytes, rechecking each path immediately before writing."""
    result = RestoreResult(restored=[], skipped=[])
    live_current_paths = {
        path
        for path in _current_paths(vault_root)
        if not _excluded_from_restore(path) and _selected(path, plan.scopes)
    }
    reviewed_current_paths = set(plan.reviewed_current_paths)
    if live_current_paths != reviewed_current_paths:
        changed_path = min(live_current_paths ^ reviewed_current_paths)
        result.skipped.append(
            (
                changed_path,
                "path set changed since the restore review; run restore again",
            )
        )
        return result
    if plan.restore_lockfile:
        reason = _restore_recheck(
            vault_root,
            ".vault/lock.json",
            plan.lockfile_before_sha256,
        )
        if reason is not None:
            result.skipped.append((".vault/lock.json", reason))
            return result

    changes = sorted(
        plan.changes,
        key=lambda change: (change.path != ".vault/lock.json", change.path),
    )
    for change in changes:
        if not plan.restore_lockfile and lock.get(change.path) != change.before_ledger_entry:
            result.skipped.append(
                (
                    change.path,
                    "ledger changed since the restore review; run restore again",
                )
            )
            continue
        target = to_native(vault_root, change.path)
        reason = _restore_recheck(vault_root, change.path, change.before_sha256)
        if reason is not None:
            result.skipped.append((change.path, reason))
            if plan.restore_lockfile and change.path == ".vault/lock.json":
                return result
            continue
        try:
            if change.status == "D":
                target.unlink()
            elif change.status in ("A", "M"):
                assert change.content is not None
                write_bytes_atomic(target, change.content)
            if change.restore_ledger:
                if change.ledger_entry is None:
                    lock.entries.pop(change.path, None)
                else:
                    lock.put(change.ledger_entry)
                save_lock(vault_root, lock)
            result.restored.append(change.path)
        except (OSError, ApplyError) as exc:
            result.skipped.append((change.path, f"could not restore: {exc}"))
            if plan.restore_lockfile and change.path == ".vault/lock.json":
                return result
    return result

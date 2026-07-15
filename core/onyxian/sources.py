"""Pinned third-party sources — `kepano/obsidian-skills` (KICKSTART.md §6.1, P6).

Depend, don't vendor: the skills are fetched from upstream at bootstrap, pinned
to the commit recorded in ``sources.obsidian-skills.pin``, and copied into the
vault's ``.claude/skills/`` under the full §8 write contract — every file
lock-tracked under the pseudo-module ``source:obsidian-skills``, no overwrites
of anything the engine does not own. Moving the pin forward is `update`'s job
(M3); `plan` deliberately does not reconcile source content (it is not a
function of config + module library).

A source install is an optional amplifier: any failure — no git, no network,
bad pin — degrades to a warning and the vault stays fully functional (P2).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import OnyxianError
from .fsio import sha256_bytes, sha256_file, write_bytes_atomic
from .lockio import save_lock
from .model import KIND_MANAGED, Config, Lock, LockEntry
from .paths import split_portable, to_native

OBSIDIAN_SKILLS = "obsidian-skills"
DEFAULT_REPOS = {OBSIDIAN_SKILLS: "https://github.com/kepano/obsidian-skills"}

# The kepano/obsidian-skills packages Onyxian agents reference but that no module
# provides. sources.py installs whatever the pinned upstream ships, so this is
# the curated subset the validator (skillcheck.py) treats as known-external.
# Note `obsidian-tasks`/`obsidian-templater` are NOT here — those are core's own
# module skills. `obsidian-cli` is intentionally absent: it is not a real
# upstream skill; its command vocabulary lives in the vault-operations skill,
# and agent references to it are dropped, not allowed.
EXTERNAL_SKILL_IDS = frozenset({"obsidian-markdown", "obsidian-bases", "defuddle"})

SOURCE_MODULE_PREFIX = "source:"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_GIT_TIMEOUT = 180


class SourceInstallError(OnyxianError):
    """A source could not be installed; callers degrade this to a warning (P2)."""


def source_module_id(name: str) -> str:
    return f"{SOURCE_MODULE_PREFIX}{name}"


def enabled_for_planner(config: Config) -> set[str]:
    """Modules plus declared-source pseudo-modules, so source files are never 'orphaned'."""
    return set(config.modules) | {source_module_id(name) for name in config.sources}


def _git(args: list[str], *, cwd: Path | None = None) -> str:
    git = shutil.which("git")
    if git is None:
        raise SourceInstallError("git is not available on PATH; source install skipped")
    try:
        proc = subprocess.run(
            [git, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise SourceInstallError(
            f"git {' '.join(args[:2])} timed out after {_GIT_TIMEOUT}s"
        ) from None
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        raise SourceInstallError(
            f"git {' '.join(args[:2])} failed: {detail[-1] if detail else 'unknown error'}"
        )
    return proc.stdout.strip()


@dataclass
class SourceInstallResult:
    name: str
    pin: str
    previous_pin: str | None
    installed: list[str]
    skipped: list[tuple[str, str]]  # (path, reason)


def install_obsidian_skills(
    vault_root: Path, config: Config, lock: Lock, *, advance_pin: bool = False
) -> SourceInstallResult | None:
    """Fetch the pinned upstream and place its skills under `.claude/skills/`, ledgered.

    With ``advance_pin`` (the `update` flow, §8.3) the recorded pin is ignored,
    upstream HEAD becomes the new pin, and the result carries the old one so
    the caller can report the commit delta. Returns None when nothing is
    declared or no runtime wants it. Raises :class:`SourceInstallError` on
    fetch problems — never half-installs without a ledger trail, because the
    lock is saved after every file.
    """
    declared = config.sources.get(OBSIDIAN_SKILLS)
    if declared is None:
        return None  # skills are runtime-agnostic; any declared source installs for every runtime
    repo = str(declared.get("repo") or DEFAULT_REPOS[OBSIDIAN_SKILLS])
    previous_pin = declared.get("pin")
    pin = None if advance_pin else previous_pin
    if pin is not None and not _SHA_RE.match(str(pin)):
        raise SourceInstallError(
            f"sources.{OBSIDIAN_SKILLS}.pin must be a full 40-hex commit sha, got {pin!r}"
        )

    module_id = source_module_id(OBSIDIAN_SKILLS)
    with tempfile.TemporaryDirectory(prefix="onyxian-src-") as tmp:
        checkout = Path(tmp) / "repo"
        _git(["clone", "--quiet", "--depth", "1" if pin is None else "50", repo, str(checkout)])
        if pin is not None:
            try:
                _git(["checkout", "--quiet", str(pin)], cwd=checkout)
            except SourceInstallError:
                _git(["fetch", "--quiet", "origin", str(pin)], cwd=checkout)
                _git(["checkout", "--quiet", str(pin)], cwd=checkout)
        resolved_pin = _git(["rev-parse", "HEAD"], cwd=checkout)

        skills_root = checkout / "skills"
        if not skills_root.is_dir():
            raise SourceInstallError(
                f"{repo} has no skills/ directory at {resolved_pin[:12]}; layout changed upstream?"
            )

        installed: list[str] = []
        skipped: list[tuple[str, str]] = []
        for source in sorted(skills_root.rglob("*"), key=lambda p: p.as_posix()):
            if not source.is_file() or ".git" in source.parts:
                continue
            rel = source.relative_to(skills_root).as_posix()
            path = f".claude/skills/{rel}"
            split_portable(path, origin=f"source {OBSIDIAN_SKILLS}: {rel}")
            content = source.read_bytes()
            digest = sha256_bytes(content)
            target = to_native(vault_root, path)
            entry = lock.get(path)
            on_disk = sha256_file(target) if target.is_file() else None

            if entry is None:
                if on_disk is not None and on_disk != digest:
                    skipped.append((path, "a file the engine does not own is already there"))
                    continue
            elif entry.module != module_id:
                skipped.append(
                    (
                        path,
                        f"owned by {entry.module!r}; a source never takes over another owner's file",
                    )
                )
                continue
            elif on_disk is not None and on_disk not in (entry.sha256, digest):
                skipped.append(
                    (
                        path,
                        "you customized it; the file stays untouched (updates to customized source files are not delivered)",
                    )
                )
                continue

            if on_disk != digest:
                write_bytes_atomic(target, content)
            lock.put(
                LockEntry(
                    path=path,
                    sha256=digest,
                    module=module_id,
                    module_version=resolved_pin[:12],
                    kind=KIND_MANAGED,
                )
            )
            save_lock(vault_root, lock)
            installed.append(path)

    return SourceInstallResult(
        name=OBSIDIAN_SKILLS,
        pin=resolved_pin,
        previous_pin=str(previous_pin) if previous_pin else None,
        installed=installed,
        skipped=skipped,
    )

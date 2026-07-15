"""Obsidian / obsidian-CLI compatibility surface (the "verified against" pin).

The module library's skills and agents encode empirically-verified prose about
how the official ``obsidian`` CLI behaves. Obsidian evolves on its own cadence,
so this module pins the version those claims were last verified against
(``VERIFIED_OBSIDIAN``) and gives doctor a read-only probe to compare the
user's installed Obsidian to it. Findings are warning-only; the fix channel is
the ordinary release flow (patch the prose, bump the touched module versions,
``onyxian update`` reconciles vaults — see RELEASING.md).

Re-verification inventory — the empirical claims and their anchors. To
re-verify a new Obsidian, walk this list, patch any prose that drifted, then
set ``VERIFIED_OBSIDIAN`` to the version you verified:

- ``obsidian daily:read`` CREATES a missing daily note — the load-bearing
  reason for the record-existence-first morning scaffold:
  ``modules/daily-notes/skills/daily-notes/SKILL.md`` (morning-scaffold steps).
- Command ids ``daily-notes`` and ``templater-obsidian:replace-in-file-templater``
  exist (same file; check with ``obsidian commands``).
- ``obsidian create ... template=`` inserts the template verbatim without
  running Templater: ``modules/core/skills/vault-operations/SKILL.md``.
- Community-plugin ids ``obsidian-tasks-plugin`` and ``templater-obsidian``:
  ``modules/core/skills/vault-operations/SKILL.md``.
- The per-OS redirector paths (``_redirector_candidates`` below): the same
  three are duplicated in prose by ``modules/core/skills/vault-operations/
  SKILL.md`` and by ``core/onyxian/adapters.py`` (agent preamble and the
  ``.claude/onyxian.md`` digest) — keep all of them in step.
- ``obsidian file`` reports the active note:
  ``modules/daily-notes/skills/task-capture/SKILL.md`` and
  ``modules/projects-software/agents/project-steward.yaml``.
- ``obsidian version`` prints ``X.Y.Z (installer X.Y.Z)`` and is a
  side-effect-free global info query (safe whether or not a vault is open).

Last verified: Obsidian 1.12.7 on 2026-07-04 — read-only subset live (version
query, both command ids via ``obsidian commands``, ``obsidian file`` active-note
reporting, the Windows redirector path); the two mutating claims
(``daily:read`` creation, ``create template=`` verbatim insertion) stand from
the 1.0.14 hardening pass.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
from pathlib import Path

VERIFIED_OBSIDIAN = "1.12.7"

_PROBE_TIMEOUT = 10  # seconds; the CLI proxies to the app and can hang with it

_VERSION_TOKEN = re.compile(r"\d+(\.\d+)*")


def _redirector_candidates() -> list[Path]:
    """The documented per-OS redirector locations, PATH-miss fallbacks."""
    candidates = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "Programs" / "Obsidian" / "Obsidian.com")
    candidates.append(Path("/usr/local/bin/obsidian"))
    # home unresolvable; the probe must degrade, never raise
    with contextlib.suppress(RuntimeError, OSError):
        candidates.append(Path.home() / ".local" / "bin" / "obsidian")
    return candidates


def find_obsidian() -> Path | None:
    """Locate the obsidian CLI: PATH first, then the documented redirectors."""
    on_path = shutil.which("obsidian")
    if on_path:
        return Path(on_path)
    for candidate in _redirector_candidates():
        if candidate.is_file():
            return candidate
    return None


def _parse_version(output: str) -> str:
    """First token of e.g. ``1.12.7 (installer 1.12.7)``; empty when the
    output is not a version (the CLI prints ``Error: ...`` lines instead)."""
    token = output.split()[0] if output.split() else ""
    return token if _VERSION_TOKEN.fullmatch(token) else ""


def probe_obsidian_version() -> str | None:
    """Installed Obsidian version — read-only, network-free, never raises.

    Returns the dotted version string; ``""`` when the CLI exists but the
    version could not be determined (Obsidian not running, timeout, unexpected
    output); ``None`` when no binary was found at all.
    """
    binary = find_obsidian()
    if binary is None:
        return None
    try:
        proc = subprocess.run(
            [str(binary), "version"],
            capture_output=True,
            # Explicit lenient decoding: text=True alone decodes with the
            # locale codec and strict errors, where one undecodable byte in
            # CLI output raises (POSIX) or yields stdout=None (Windows).
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    # The CLI's exit codes are unreliable (observed live: error text with
    # exit 0, valid output with exit 255), so the output alone decides.
    return _parse_version(proc.stdout or "")


def classify_drift(installed: str, verified: str = VERIFIED_OBSIDIAN) -> str:
    """``match`` | ``patch-newer`` | ``newer`` | ``older``.

    Hand-rolled dotted-integer compare (shorter versions pad with zeros);
    PyYAML stays the engine's only runtime dependency.
    """
    a = [int(part) for part in installed.split(".")]
    b = [int(part) for part in verified.split(".")]
    width = max(len(a), len(b))
    a += [0] * (width - len(a))
    b += [0] * (width - len(b))
    if a == b:
        return "match"
    if a < b:
        return "older"
    return "patch-newer" if a[:2] == b[:2] else "newer"

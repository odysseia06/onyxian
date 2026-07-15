"""Typed model for the three schemas the engine speaks (KICKSTART.md §4.4, §5.2, §8.1).

Pure data. Parsing and validation live in ``configio``, ``manifests``, and
``lockio``; planning logic lives in ``planner``. Keeping the model dumb keeps
every transition testable in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MODULE_ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

FOLDER_STYLES = ("Title-Case-Hyphen", "kebab-case", "Spaces")
RUNTIMES = ("claude-code", "codex", "opencode", "generic")

KIND_MANAGED = "managed"
KIND_SEEDED = "seeded"
FILE_KINDS = (KIND_MANAGED, KIND_SEEDED)

LOCATION_VAULT = "vault"
LOCATION_RUNTIME = "runtime"
LOCATIONS = (LOCATION_VAULT, LOCATION_RUNTIME)

VAR_TYPES = ("string", "choice", "bool")


# --------------------------------------------------------------------------- config


@dataclass
class ModuleConfig:
    """One entry under ``modules:`` in `.vault/config.yaml`.

    ``source`` is set for externally-installed modules (M4): the git repo (or
    local path) it came from and, for git sources, the pinned commit. The
    module's content lives vault-locally under ``.vault/modules/<id>/``.
    """

    version: str
    vars: dict[str, object] = field(default_factory=dict)
    source: dict[str, str] | None = None


@dataclass
class Config:
    """Parsed `.vault/config.yaml` — the user's declared intent (§4.4)."""

    framework_version: str
    runtimes: list[str]
    vault_name: str
    folder_style: str
    modules: dict[str, ModuleConfig]
    sources: dict[str, dict[str, str]] = field(default_factory=dict)
    scope_hooks: bool = False


# --------------------------------------------------------------------------- manifest


@dataclass(frozen=True)
class Variable:
    """One interview question declared by a module (§5.2)."""

    key: str
    prompt: str
    type: str = "string"
    options: tuple[str, ...] = ()
    default: object = None


@dataclass(frozen=True)
class ProvidedFile:
    """One file a module installs: where it lands and which asset it comes from.

    ``install_path`` is the raw, un-substituted portable path from the manifest
    (it may contain ``{{variable}}`` references); ``source`` is the asset file
    under the module's ``assets/`` directory, which mirrors the install tree
    verbatim — placeholder segments included — so a module stays reviewable by
    reading it (§5.1).
    """

    install_path: str
    source: Path


@dataclass(frozen=True)
class ProvidedSkill:
    """One Agent-Skills package a module ships: ``skills/<id>/`` with a SKILL.md (§6.2)."""

    id: str
    directory: Path


@dataclass(frozen=True)
class ScopeEntry:
    """One read/write glob in an agent's scope (§7.1, least privilege).

    ``requires`` names a module id; the entry is dropped at render time when
    that module is not enabled, so cross-module scopes (§7.3 reads the daily
    notes root) never break a vault that skipped the other module.
    """

    pattern: str
    requires: str | None = None


@dataclass(frozen=True)
class AgentDef:
    """A generalized agent definition (§7.3), rendered per-runtime by adapters."""

    name: str
    module: str
    description: str
    mission: str
    read: tuple[ScopeEntry, ...]
    write: tuple[ScopeEntry, ...]
    skills: tuple[str, ...] = ()
    escalate_when: tuple[str, ...] = ()
    disclaimer: str = ""
    playbook: str = ""
    triggers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Manifest:
    """Parsed and structurally validated ``module.yaml`` (§5.2)."""

    name: str
    version: str
    summary: str
    directory: Path
    depends: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    variables: tuple[Variable, ...] = ()
    folders: tuple[str, ...] = ()
    templates: tuple[ProvidedFile, ...] = ()
    bases: tuple[ProvidedFile, ...] = ()
    skills: tuple[ProvidedSkill, ...] = ()
    agents: tuple[AgentDef, ...] = ()
    seeds: tuple[ProvidedFile, ...] = ()
    post_install: str = ""

    @property
    def managed_files(self) -> tuple[ProvidedFile, ...]:
        return self.templates + self.bases

    @property
    def seeded_files(self) -> tuple[ProvidedFile, ...]:
        return self.seeds


# --------------------------------------------------------------------------- lock


@dataclass(frozen=True)
class LockEntry:
    """One ledger row: a file the engine wrote, and the exact bytes it wrote (§8.1).

    ``declined`` is the sha256 of a shipped version the user turned down via
    `onyxian diff --keep-mine`; while the desired content still hashes to it,
    the planner offers nothing for this path. Empty for the common case and
    omitted from the serialized lock, so undeclined ledgers keep their exact
    pre-existing byte form.
    """

    path: str
    sha256: str
    module: str
    module_version: str
    kind: str
    location: str = LOCATION_VAULT
    declined: str = ""


@dataclass
class Lock:
    """The managed-file ledger, keyed by portable path for lookups."""

    entries: dict[str, LockEntry] = field(default_factory=dict)

    def get(self, path: str) -> LockEntry | None:
        return self.entries.get(path)

    def put(self, entry: LockEntry) -> None:
        self.entries[entry.path] = entry

    def sorted_entries(self) -> list[LockEntry]:
        return [self.entries[k] for k in sorted(self.entries)]

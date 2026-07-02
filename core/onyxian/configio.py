"""Read, validate, and write `.vault/config.yaml` (KICKSTART.md §4.4).

The config is the user's file: hand-editing it and running ``plan`` is a fully
supported workflow, so validation errors must name the exact key and the
allowed values rather than dumping a stack trace.

Writing goes through a deterministic text emitter (not a YAML dumper) so the
emitted file is byte-stable across library versions and can carry comments.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import ENGINE_VERSION
from .errors import ConfigError
from .model import (
    FOLDER_STYLES,
    MODULE_ID_RE,
    RUNTIMES,
    SEMVER_RE,
    Config,
    ModuleConfig,
)
from .yamlio import load_yaml

VAULT_DIR = ".vault"
CONFIG_REL = ".vault/config.yaml"
LOCK_REL = ".vault/lock.json"

_SCALAR_TYPES = (str, int, float, bool)


def config_path(vault_root: Path) -> Path:
    return vault_root / VAULT_DIR / "config.yaml"


def is_managed_vault(vault_root: Path) -> bool:
    return config_path(vault_root).is_file()


def _require_keys(mapping: dict, allowed: set[str], required: set[str], *, where: str) -> None:
    unknown = set(mapping) - allowed
    if unknown:
        raise ConfigError(
            f"unknown key(s) {sorted(unknown)} in {where}; allowed: {sorted(allowed)}"
        )
    missing = required - set(mapping)
    if missing:
        raise ConfigError(f"missing required key(s) {sorted(missing)} in {where}")


def parse_config(data: object, *, where: str = CONFIG_REL) -> Config:
    if not isinstance(data, dict):
        raise ConfigError(f"{where} must be a YAML mapping")
    _require_keys(
        data,
        allowed={"framework", "vault", "naming", "modules", "sources"},
        required={"framework", "vault", "naming", "modules"},
        where=where,
    )

    framework = data["framework"]
    if not isinstance(framework, dict):
        raise ConfigError(f"'framework' must be a mapping in {where}")
    _require_keys(framework, allowed={"version", "runtimes"}, required={"version"}, where=f"{where}: framework")
    fw_version = framework["version"]
    if not isinstance(fw_version, str) or not SEMVER_RE.match(fw_version):
        raise ConfigError(f"framework.version must be a semver string, got {fw_version!r}")
    runtimes = framework.get("runtimes", ["claude-code"])
    if not isinstance(runtimes, list) or not runtimes or not all(isinstance(r, str) for r in runtimes):
        raise ConfigError("framework.runtimes must be a non-empty list of strings")
    for r in runtimes:
        if r not in RUNTIMES:
            raise ConfigError(f"unknown runtime {r!r}; allowed: {list(RUNTIMES)}")

    vault = data["vault"]
    if not isinstance(vault, dict):
        raise ConfigError(f"'vault' must be a mapping in {where}")
    _require_keys(vault, allowed={"name"}, required={"name"}, where=f"{where}: vault")
    vault_name = vault["name"]
    if not isinstance(vault_name, str) or not vault_name.strip():
        raise ConfigError("vault.name must be a non-empty string")

    naming = data["naming"]
    if not isinstance(naming, dict):
        raise ConfigError(f"'naming' must be a mapping in {where}")
    _require_keys(naming, allowed={"folder_style"}, required={"folder_style"}, where=f"{where}: naming")
    folder_style = naming["folder_style"]
    if folder_style not in FOLDER_STYLES:
        raise ConfigError(
            f"naming.folder_style must be one of {list(FOLDER_STYLES)}, got {folder_style!r}"
        )

    raw_modules = data["modules"]
    if not isinstance(raw_modules, dict) or not raw_modules:
        raise ConfigError("'modules' must be a non-empty mapping of module id -> settings")
    modules: dict[str, ModuleConfig] = {}
    for mod_id, entry in raw_modules.items():
        if not isinstance(mod_id, str) or not MODULE_ID_RE.match(mod_id):
            raise ConfigError(f"invalid module id {mod_id!r} (kebab-case required)")
        if not isinstance(entry, dict):
            raise ConfigError(f"modules.{mod_id} must be a mapping")
        _require_keys(
            entry, allowed={"version", "vars", "source"}, required={"version"}, where=f"{where}: modules.{mod_id}"
        )
        version = entry["version"]
        if not isinstance(version, str) or not SEMVER_RE.match(version):
            raise ConfigError(f"modules.{mod_id}.version must be a semver string, got {version!r}")
        raw_vars = entry.get("vars", {})
        if not isinstance(raw_vars, dict):
            raise ConfigError(f"modules.{mod_id}.vars must be a mapping")
        for key, value in raw_vars.items():
            if not isinstance(key, str):
                raise ConfigError(f"modules.{mod_id}.vars has a non-string key: {key!r}")
            if not isinstance(value, _SCALAR_TYPES):
                raise ConfigError(
                    f"modules.{mod_id}.vars.{key} must be a scalar, got {type(value).__name__}"
                )
        source = entry.get("source")
        if source is not None:
            if not isinstance(source, dict) or set(source) - {"repo", "pin"} or "repo" not in source:
                raise ConfigError(f"modules.{mod_id}.source must be a mapping with 'repo' (and optional 'pin')")
            if not all(isinstance(v, str) and v for v in source.values()):
                raise ConfigError(f"modules.{mod_id}.source values must be non-empty strings")
        modules[mod_id] = ModuleConfig(
            version=version, vars=dict(raw_vars), source=dict(source) if source else None
        )
    if "core" not in modules:
        raise ConfigError("the 'core' module is required by everything and must be enabled")

    sources = data.get("sources", {})
    if not isinstance(sources, dict):
        raise ConfigError("'sources' must be a mapping")
    for src_name, src in sources.items():
        if not isinstance(src, dict):
            raise ConfigError(f"sources.{src_name} must be a mapping")

    return Config(
        framework_version=fw_version,
        runtimes=list(runtimes),
        vault_name=vault_name,
        folder_style=folder_style,
        modules=modules,
        sources={k: dict(v) for k, v in sources.items()},
    )


def load_config(vault_root: Path) -> Config:
    path = config_path(vault_root)
    if not path.is_file():
        raise ConfigError(
            f"{vault_root} is not an Onyxian-managed vault ({CONFIG_REL} not found); "
            "run `onyxian init` on a new folder, or `onyxian adopt` on an existing one"
        )
    data = load_yaml(path, what="vault config")
    return parse_config(data)


def _yaml_scalar(value: object) -> str:
    """A YAML-safe scalar literal. JSON string/bool/number syntax is valid YAML."""
    return json.dumps(value, ensure_ascii=False)


def module_line(mod_id: str, mod: ModuleConfig) -> str:
    """The canonical one-line form of a `modules:` entry; shared by the emitter and `add`."""
    parts = [f"version: {_yaml_scalar(mod.version)}"]
    if mod.vars:
        vars_text = ", ".join(f"{k}: {_yaml_scalar(v)}" for k, v in mod.vars.items())
        parts.append(f"vars: {{ {vars_text} }}")
    if mod.source:
        src_text = ", ".join(f"{k}: {_yaml_scalar(mod.source[k])}" for k in sorted(mod.source))
        parts.append(f"source: {{ {src_text} }}")
    return f"  {mod_id}: {{ {', '.join(parts)} }}"


def render_config_text(config: Config) -> str:
    """Deterministic config emitter; the only writer of `.vault/config.yaml`."""
    lines: list[str] = []
    lines.append("# Onyxian instance config — declares intent: which modules, with which variables.")
    lines.append("# This file is yours to edit; run `onyxian plan` to preview the effect")
    lines.append("# and `onyxian apply` to reconcile the vault to it.")
    lines.append("framework:")
    lines.append(f"  version: {_yaml_scalar(config.framework_version)}")
    lines.append(f"  runtimes: [{', '.join(config.runtimes)}]")
    lines.append("vault:")
    lines.append(f"  name: {_yaml_scalar(config.vault_name)}")
    lines.append("naming:")
    lines.append(f"  folder_style: {config.folder_style}")
    lines.append("modules:")
    for mod_id, mod in config.modules.items():
        lines.append(module_line(mod_id, mod))
    if config.sources:
        lines.append("sources:")
        for src_name in sorted(config.sources):
            src = config.sources[src_name]
            lines.append(f"  {src_name}:")
            for key in sorted(src):
                lines.append(f"    {key}: {_yaml_scalar(src[key])}")
    return "\n".join(lines) + "\n"


def default_config(
    *,
    vault_name: str = "My Vault",
    folder_style: str = "Title-Case-Hyphen",
    runtimes: list[str] | None = None,
    modules: dict[str, ModuleConfig] | None = None,
    sources: dict[str, dict] | None = None,
) -> Config:
    return Config(
        framework_version=ENGINE_VERSION,
        runtimes=list(runtimes) if runtimes else ["claude-code"],
        vault_name=vault_name,
        folder_style=folder_style,
        modules=modules if modules is not None else {"core": ModuleConfig(version=ENGINE_VERSION)},
        sources={k: dict(v) for k, v in sources.items()} if sources else {},
    )

"""Load and validate module manifests — ``module.yaml`` (KICKSTART.md §5.2).

A module is data: a manifest plus an ``assets/`` tree that mirrors the install
tree verbatim, placeholder segments included (an asset that installs to
``{{root}}/Strategy.md`` lives at ``assets/{{root}}/Strategy.md``). Everything
a module can do is visible by reading its folder; validation here exists to
catch authoring mistakes at load time instead of plan time.
"""

from __future__ import annotations

import re
from pathlib import Path

from .errors import ManifestError, PathError
from .model import (
    MODULE_ID_RE,
    SEMVER_RE,
    VAR_TYPES,
    AgentDef,
    Manifest,
    ProvidedFile,
    ProvidedSkill,
    ScopeEntry,
    Variable,
)
from .paths import split_portable
from .yamlio import load_yaml


def _check_authored_path(path: str, *, origin: str) -> None:
    """Validate a raw manifest path; a violation here is the author's mistake, not the user's."""
    try:
        split_portable(path, origin=origin)
    except PathError as exc:
        raise ManifestError(str(exc)) from None


_VAR_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PLACEHOLDER_MARKER = "{{"

_ALLOWED_TOP = {
    "name",
    "version",
    "summary",
    "depends",
    "conflicts",
    "variables",
    "provides",
    "seeds",
    "post_install",
}
_ALLOWED_PROVIDES = {"folders", "templates", "bases", "skills", "agents"}
_ALLOWED_VARIABLE = {"key", "prompt", "type", "options", "default"}


def _str_list(value: object, *, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ManifestError(f"{where} must be a list of strings")
    return tuple(value)


def _parse_variable(raw: object, *, where: str) -> Variable:
    if not isinstance(raw, dict):
        raise ManifestError(f"{where} must be a mapping")
    unknown = set(raw) - _ALLOWED_VARIABLE
    if unknown:
        raise ManifestError(f"unknown key(s) {sorted(unknown)} in {where}")
    key = raw.get("key")
    if not isinstance(key, str) or not _VAR_KEY_RE.match(key):
        raise ManifestError(f"{where}: 'key' must be snake_case, got {key!r}")
    prompt = raw.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ManifestError(f"{where}: 'prompt' is required")
    var_type = raw.get("type", "string")
    if var_type not in VAR_TYPES:
        raise ManifestError(f"{where}: type must be one of {list(VAR_TYPES)}, got {var_type!r}")
    options = _str_list(raw.get("options"), where=f"{where}: options")
    default = raw.get("default")
    if var_type == "choice":
        if not options:
            raise ManifestError(f"{where}: choice variables need non-empty 'options'")
        if default is not None and default not in options:
            raise ManifestError(f"{where}: default {default!r} is not one of the options")
    elif options:
        raise ManifestError(f"{where}: 'options' only makes sense for type: choice")
    elif var_type == "bool":
        if default is not None and not isinstance(default, bool):
            raise ManifestError(f"{where}: bool default must be true/false")
    elif default is not None and not isinstance(default, str):
        raise ManifestError(f"{where}: string default must be a string")
    return Variable(key=key, prompt=prompt.strip(), type=var_type, options=options, default=default)


def _resolve_provided_files(
    patterns: tuple[str, ...], assets_dir: Path, *, module: str, what: str
) -> tuple[ProvidedFile, ...]:
    """Turn manifest file patterns into (install path, asset source) pairs.

    A pattern containing ``*`` is expanded against the assets tree (sorted, so
    expansion order is deterministic); wildcards and ``{{variables}}`` cannot
    be combined in one pattern because the expansion result must itself be the
    install path.
    """
    out: list[ProvidedFile] = []
    for pattern in patterns:
        where = f"module {module!r}: {what} entry {pattern!r}"
        if "*" in pattern:
            if _PLACEHOLDER_MARKER in pattern:
                raise ManifestError(f"{where}: wildcards and {{{{variables}}}} cannot be combined")
            _check_authored_path(pattern.replace("*", "x"), origin=where)
            matches = sorted(
                (p for p in assets_dir.glob(pattern) if p.is_file()),
                key=lambda p: p.relative_to(assets_dir).as_posix(),
            )
            if not matches:
                raise ManifestError(f"{where}: no assets match under {assets_dir}")
            for match in matches:
                rel = match.relative_to(assets_dir).as_posix()
                out.append(ProvidedFile(install_path=rel, source=match))
        else:
            _check_authored_path(pattern, origin=where)
            source = assets_dir.joinpath(*pattern.split("/"))
            if not source.is_file():
                raise ManifestError(f"{where}: asset file missing at {source}")
            out.append(ProvidedFile(install_path=pattern, source=source))
    return tuple(out)


_ALLOWED_AGENT = {
    "name",
    "module",
    "description",
    "mission",
    "scope",
    "skills",
    "escalate_when",
    "disclaimer",
    "playbook",
    "triggers",
}


def scope_glob_violation(pattern: str) -> str | None:
    """Why ``pattern`` is not a vault-relative scope glob, or None if it is valid.

    Shared by load-time manifest validation and render-time scope resolution
    (adapters) so the two stay in lockstep: a value substituted into a scope
    (``{{root}}`` -> ``/etc``) cannot slip past the render check that the load
    check would have caught (#11). Forward slashes, no upward escapes, no
    absolute paths; wildcards welcome.
    """
    if not isinstance(pattern, str) or not pattern:
        return "empty scope pattern"
    if "\\" in pattern:
        return f"scope pattern {pattern!r} uses backslashes; portable form is '/'"
    if pattern.startswith("/") or (len(pattern) >= 2 and pattern[1] == ":"):
        return f"scope pattern {pattern!r} must be vault-relative"
    if ".." in pattern.split("/"):
        return f"scope pattern {pattern!r} escapes the vault"
    return None


def _check_scope_glob(pattern: str, *, where: str) -> None:
    """Scope globs are vault-relative: forward slashes, no escapes upward, wildcards welcome."""
    violation = scope_glob_violation(pattern)
    if violation is not None:
        raise ManifestError(f"{where}: {violation}")


def _parse_scope_entries(raw: object, *, where: str) -> tuple[ScopeEntry, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ManifestError(f"{where} must be a list")
    entries: list[ScopeEntry] = []
    for i, item in enumerate(raw):
        item_where = f"{where}[{i}]"
        if isinstance(item, str):
            _check_scope_glob(item, where=item_where)
            entries.append(ScopeEntry(pattern=item))
        elif isinstance(item, dict):
            unknown = set(item) - {"path", "requires"}
            if unknown:
                raise ManifestError(f"{item_where}: unknown key(s) {sorted(unknown)}")
            pattern = item.get("path")
            requires = item.get("requires")
            if not isinstance(pattern, str):
                raise ManifestError(f"{item_where}: 'path' is required")
            if not isinstance(requires, str) or not MODULE_ID_RE.match(requires):
                raise ManifestError(f"{item_where}: 'requires' must be a module id")
            _check_scope_glob(pattern, where=item_where)
            entries.append(ScopeEntry(pattern=pattern, requires=requires))
        else:
            raise ManifestError(f"{item_where} must be a string or a {{path, requires}} mapping")
    return tuple(entries)


def _parse_agent(module_dir: Path, agent_id: str, module_name: str) -> AgentDef:
    agent_path = module_dir / "agents" / f"{agent_id}.yaml"
    if not agent_path.is_file():
        raise ManifestError(
            f"{module_dir / 'module.yaml'}: provides.agents lists {agent_id!r} "
            f"but {agent_path} is missing"
        )
    data = load_yaml(agent_path, what="agent definition")
    if not isinstance(data, dict):
        raise ManifestError(f"{agent_path} must be a YAML mapping")
    unknown = set(data) - _ALLOWED_AGENT
    if unknown:
        raise ManifestError(f"unknown key(s) {sorted(unknown)} in {agent_path}")
    if data.get("name") != agent_id:
        raise ManifestError(f"{agent_path}: 'name' must equal the file name {agent_id!r}")
    if data.get("module") != module_name:
        raise ManifestError(f"{agent_path}: 'module' must be {module_name!r}")
    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ManifestError(
            f"{agent_path}: 'description' is required (one line; runtimes use it for delegation)"
        )
    mission = data.get("mission")
    if not isinstance(mission, str) or not mission.strip():
        raise ManifestError(f"{agent_path}: 'mission' is required")
    scope = data.get("scope")
    if not isinstance(scope, dict) or set(scope) - {"read", "write"}:
        raise ManifestError(f"{agent_path}: 'scope' must be a mapping with only read/write (§7.1)")
    read = _parse_scope_entries(scope.get("read"), where=f"{agent_path}: scope.read")
    write = _parse_scope_entries(scope.get("write"), where=f"{agent_path}: scope.write")
    if not read:
        raise ManifestError(f"{agent_path}: scope.read must not be empty")
    skills = _str_list(data.get("skills"), where=f"{agent_path}: skills")
    escalate = _str_list(data.get("escalate_when"), where=f"{agent_path}: escalate_when")
    disclaimer = data.get("disclaimer", "")
    if not isinstance(disclaimer, str):
        raise ManifestError(f"{agent_path}: 'disclaimer' must be a string")
    playbook = data.get("playbook", "")
    if not isinstance(playbook, str):
        raise ManifestError(f"{agent_path}: 'playbook' must be a string")
    triggers = _str_list(data.get("triggers"), where=f"{agent_path}: triggers")
    return AgentDef(
        name=agent_id,
        module=module_name,
        description=" ".join(description.split()),
        mission=mission.strip(),
        read=read,
        write=write,
        skills=skills,
        escalate_when=escalate,
        disclaimer=disclaimer.strip(),
        playbook=playbook.strip(),
        triggers=triggers,
    )


def load_manifest(module_dir: Path) -> Manifest:
    manifest_path = module_dir / "module.yaml"
    data = load_yaml(manifest_path, what="module manifest")
    if not isinstance(data, dict):
        raise ManifestError(f"{manifest_path} must be a YAML mapping")
    unknown = set(data) - _ALLOWED_TOP
    if unknown:
        raise ManifestError(f"unknown key(s) {sorted(unknown)} in {manifest_path}")

    name = data.get("name")
    if not isinstance(name, str) or not MODULE_ID_RE.match(name):
        raise ManifestError(f"{manifest_path}: 'name' must be a kebab-case id, got {name!r}")
    if name != module_dir.name:
        raise ManifestError(
            f"{manifest_path}: name {name!r} does not match its directory {module_dir.name!r}"
        )
    version = data.get("version")
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        raise ManifestError(f"{manifest_path}: 'version' must be a semver string, got {version!r}")
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ManifestError(f"{manifest_path}: 'summary' is required")

    depends = _str_list(data.get("depends"), where=f"{manifest_path}: depends")
    conflicts = _str_list(data.get("conflicts"), where=f"{manifest_path}: conflicts")
    for dep in (*depends, *conflicts):
        if not MODULE_ID_RE.match(dep):
            raise ManifestError(f"{manifest_path}: invalid module id {dep!r} in depends/conflicts")
    if name != "core" and "core" not in depends:
        raise ManifestError(f"{manifest_path}: every module depends on 'core' (§5.1)")

    raw_variables = data.get("variables") or []
    if not isinstance(raw_variables, list):
        raise ManifestError(f"{manifest_path}: 'variables' must be a list")
    variables = tuple(
        _parse_variable(raw, where=f"{manifest_path}: variables[{i}]")
        for i, raw in enumerate(raw_variables)
    )
    seen_keys = set()
    for var in variables:
        if var.key in seen_keys:
            raise ManifestError(f"{manifest_path}: duplicate variable key {var.key!r}")
        seen_keys.add(var.key)

    provides = data.get("provides") or {}
    if not isinstance(provides, dict):
        raise ManifestError(f"{manifest_path}: 'provides' must be a mapping")
    unknown = set(provides) - _ALLOWED_PROVIDES
    if unknown:
        raise ManifestError(f"unknown key(s) {sorted(unknown)} in {manifest_path}: provides")

    folders = _str_list(provides.get("folders"), where=f"{manifest_path}: provides.folders")
    for folder in folders:
        _check_authored_path(folder, origin=f"{manifest_path}: provides.folders")

    assets_dir = module_dir / "assets"
    template_patterns = _str_list(
        provides.get("templates"), where=f"{manifest_path}: provides.templates"
    )
    base_patterns = _str_list(provides.get("bases"), where=f"{manifest_path}: provides.bases")
    seed_patterns = _str_list(data.get("seeds"), where=f"{manifest_path}: seeds")
    if (template_patterns or base_patterns or seed_patterns) and not assets_dir.is_dir():
        raise ManifestError(f"{manifest_path}: module provides files but has no assets/ directory")

    templates = _resolve_provided_files(
        template_patterns, assets_dir, module=name, what="provides.templates"
    )
    bases = _resolve_provided_files(base_patterns, assets_dir, module=name, what="provides.bases")
    seeds = _resolve_provided_files(seed_patterns, assets_dir, module=name, what="seeds")

    skill_ids = _str_list(provides.get("skills"), where=f"{manifest_path}: provides.skills")
    skills_dir = module_dir / "skills"
    skills: list[ProvidedSkill] = []
    for skill_id in skill_ids:
        if not MODULE_ID_RE.match(skill_id):
            raise ManifestError(
                f"{manifest_path}: invalid skill id {skill_id!r} (kebab-case required)"
            )
        skill_dir = skills_dir / skill_id
        if not (skill_dir / "SKILL.md").is_file():
            raise ManifestError(
                f"{manifest_path}: provides.skills lists {skill_id!r} "
                f"but {skill_dir / 'SKILL.md'} is missing"
            )
        skills.append(ProvidedSkill(id=skill_id, directory=skill_dir))
    if skills_dir.is_dir():
        on_disk = {
            p.name for p in skills_dir.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()
        }
        unlisted = on_disk - set(skill_ids)
        if unlisted:
            raise ManifestError(
                f"{manifest_path}: skill package(s) {sorted(unlisted)} exist on disk "
                "but are not listed under provides.skills"
            )

    agent_ids = _str_list(provides.get("agents"), where=f"{manifest_path}: provides.agents")
    for agent_id in agent_ids:
        if not MODULE_ID_RE.match(agent_id):
            raise ManifestError(
                f"{manifest_path}: invalid agent id {agent_id!r} (kebab-case required)"
            )
    agents = tuple(_parse_agent(module_dir, agent_id, name) for agent_id in agent_ids)
    agents_dir = module_dir / "agents"
    if agents_dir.is_dir():
        on_disk = {p.stem for p in agents_dir.glob("*.yaml")}
        unlisted = on_disk - set(agent_ids)
        if unlisted:
            raise ManifestError(
                f"{manifest_path}: agent definition(s) {sorted(unlisted)} exist on disk "
                "but are not listed under provides.agents"
            )

    post_install = data.get("post_install", "")
    if not isinstance(post_install, str):
        raise ManifestError(f"{manifest_path}: 'post_install' must be a string")

    install_paths = [f.install_path for f in (*templates, *bases, *seeds)]
    duplicates = {p for p in install_paths if install_paths.count(p) > 1}
    if duplicates:
        raise ManifestError(f"{manifest_path}: duplicate install path(s) {sorted(duplicates)}")

    return Manifest(
        name=name,
        version=version,
        summary=summary.strip(),
        directory=module_dir,
        depends=depends,
        conflicts=conflicts,
        variables=variables,
        folders=folders,
        templates=templates,
        bases=bases,
        skills=tuple(skills),
        agents=agents,
        seeds=seeds,
        post_install=post_install.strip(),
    )

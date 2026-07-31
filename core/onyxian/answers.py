"""Answers files, profiles, and flags into a Config — the CLI asks no questions (#131).

Hard parity rule: every input maps one-to-one onto a config key, so a composed
``init`` command, a hand-edited config, and an ``--answers`` file are three
doors into the same room. Two input shapes are accepted:

Answers file — a partial mirror of the config::

    vault:  { name: "Example" }
    naming: { folder_style: kebab-case }
    framework: { runtimes: [claude-code] }
    modules:
      core: {}            # module id -> variable values (flat)
    sources:
      obsidian-skills: false   # `false` opts out; omitted means the default, which is in

Profile — a named module set with presets (§5.5)::

    name: minimal
    modules: [core]
    presets:
      core: {}

Missing values fall back to declared defaults; a required variable with no
default and no answer is an error, never a silent guess.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .configio import default_config
from .errors import AnswersError
from .model import FOLDER_STYLES, MODULE_ID_RE, RUNTIMES, Config, Manifest, ModuleConfig
from .resolve import dependency_closure, resolve_variables
from .sources import OBSIDIAN_SKILLS
from .yamlio import load_yaml, require_mapping


class Answers:
    """Normalized form of an answers file or profile."""

    def __init__(self) -> None:
        self.profile_name: str | None = None
        self.vault_name: str | None = None
        self.folder_style: str | None = None
        self.runtimes: list[str] | None = None
        self.checkpoints: bool | None = None
        self.scope_hooks: bool | None = None
        self.modules: dict[str, dict[str, object]] = {}
        self.sources: dict[str, dict[str, str]] = {}
        self.sources_off: set[str] = set()  # named with `false`: opted out, not merely absent


def resolve_answers_spec(spec: str, flag: str = "--answers") -> Path:
    """An ``--answers``/``--profile`` value: an existing file path, or the bare name of a
    bundled profile.

    Lets an installed user write ``--answers minimal`` instead of hunting for the
    profile file inside site-packages.
    """
    path = Path(spec)
    if path.is_file():
        return path
    from .repo import bundled_profiles_root

    root = bundled_profiles_root()
    if root is not None:
        for candidate in (root / spec, root / f"{spec}.yaml"):
            if candidate.is_file():
                return candidate
        available = ", ".join(sorted(p.stem for p in root.glob("*.yaml")))
        raise AnswersError(
            f"{flag} {spec!r}: not a file, and not a bundled profile. "
            f"Available profiles: {available}"
        )
    raise AnswersError(f"{flag} {spec!r}: file not found")


def load_answers(path: Path) -> Answers:
    data = require_mapping(load_yaml(path, what="answers file"), what=f"answers file {path}")
    answers = Answers()

    modules_list = data.get("modules")
    if "name" in data or "presets" in data:  # profile shape (§5.5)
        allowed = {"name", "modules", "presets"}
        unknown = set(data) - allowed
        if unknown:
            raise AnswersError(f"profile {path}: unknown key(s) {sorted(unknown)}")
        profile_name = data.get("name")
        if not isinstance(profile_name, str) or not MODULE_ID_RE.match(profile_name):
            raise AnswersError(f"profile {path}: 'name' must be a kebab-case id")
        answers.profile_name = profile_name
        if not isinstance(modules_list, list):
            raise AnswersError(f"profile {path}: 'modules' must be a list")
        for mod_id in modules_list:
            if not isinstance(mod_id, str) or not MODULE_ID_RE.match(mod_id):
                raise AnswersError(f"profile {path}: invalid module id {mod_id!r}")
            answers.modules[mod_id] = {}
        presets = data.get("presets") or {}
        if not isinstance(presets, dict):
            raise AnswersError(f"profile {path}: 'presets' must be a mapping")
        for mod_id, preset in presets.items():
            if mod_id not in answers.modules:
                raise AnswersError(
                    f"profile {path}: preset for {mod_id!r} which is not in 'modules'"
                )
            if not isinstance(preset, dict):
                raise AnswersError(f"profile {path}: presets.{mod_id} must be a mapping")
            answers.modules[mod_id] = dict(preset)
        return answers

    allowed = {"vault", "naming", "framework", "modules", "sources"}
    unknown = set(data) - allowed
    if unknown:
        raise AnswersError(
            f"answers file {path}: unknown key(s) {sorted(unknown)}; allowed: {sorted(allowed)}"
        )
    raw_sources = data.get("sources") or {}
    if not isinstance(raw_sources, dict):
        raise AnswersError(f"answers file {path}: 'sources' must be a mapping")
    for src_name, src in raw_sources.items():
        if isinstance(src, bool):  # the explicit in/out; absent means the default (#65)
            if not src:
                answers.sources_off.add(str(src_name))
                continue
            src = {}
        if src is None:
            src = {}
        if not isinstance(src, dict) or set(src) - {"repo", "pin"}:
            raise AnswersError(f"answers file {path}: sources.{src_name} may only contain repo/pin")
        if not all(isinstance(v, str) and v for v in src.values()):
            raise AnswersError(
                f"answers file {path}: sources.{src_name} values must be non-empty strings"
            )
        answers.sources[str(src_name)] = {k: str(v) for k, v in src.items()}
    vault = data.get("vault") or {}
    if not isinstance(vault, dict) or set(vault) - {"name"}:
        raise AnswersError(f"answers file {path}: 'vault' may only contain 'name'")
    if "name" in vault:
        if not isinstance(vault["name"], str) or not vault["name"].strip():
            raise AnswersError(f"answers file {path}: vault.name must be a non-empty string")
        answers.vault_name = vault["name"]
    naming = data.get("naming") or {}
    if not isinstance(naming, dict) or set(naming) - {"folder_style"}:
        raise AnswersError(f"answers file {path}: 'naming' may only contain 'folder_style'")
    if "folder_style" in naming:
        if naming["folder_style"] not in FOLDER_STYLES:
            raise AnswersError(
                f"answers file {path}: folder_style must be one of {list(FOLDER_STYLES)}"
            )
        answers.folder_style = naming["folder_style"]
    framework = data.get("framework") or {}
    allowed_fw = {"runtimes", "checkpoints", "scope_hooks"}
    if not isinstance(framework, dict) or set(framework) - allowed_fw:
        raise AnswersError(
            f"answers file {path}: 'framework' may only contain "
            "'runtimes', 'checkpoints', and 'scope_hooks'"
        )
    if "checkpoints" in framework:
        if not isinstance(framework["checkpoints"], bool):
            raise AnswersError(f"answers file {path}: framework.checkpoints must be true or false")
        answers.checkpoints = framework["checkpoints"]
    if "scope_hooks" in framework:
        if not isinstance(framework["scope_hooks"], bool):
            raise AnswersError(f"answers file {path}: framework.scope_hooks must be true or false")
        answers.scope_hooks = framework["scope_hooks"]
    if "runtimes" in framework:
        runtimes = framework["runtimes"]
        if (
            not isinstance(runtimes, list)
            or not runtimes
            or any(r not in RUNTIMES for r in runtimes)
        ):
            raise AnswersError(
                f"answers file {path}: runtimes must be a non-empty subset of {list(RUNTIMES)}"
            )
        answers.runtimes = list(runtimes)
    raw_modules = data.get("modules") or {}
    if isinstance(raw_modules, list):
        normalized_modules: dict[str, dict[str, object]] = {}
        for mod_id in raw_modules:
            if not isinstance(mod_id, str) or not MODULE_ID_RE.match(mod_id):
                raise AnswersError(f"answers file {path}: invalid module id {mod_id!r}")
            normalized_modules[mod_id] = {}
        raw_modules = normalized_modules
    if not isinstance(raw_modules, dict):
        raise AnswersError(
            f"answers file {path}: 'modules' must be a list of ids or "
            "a mapping of id -> variable values"
        )
    for mod_id, mod_vars in raw_modules.items():
        if not isinstance(mod_id, str) or not MODULE_ID_RE.match(mod_id):
            raise AnswersError(f"answers file {path}: invalid module id {mod_id!r}")
        if mod_vars is None:
            mod_vars = {}
        if not isinstance(mod_vars, dict):
            raise AnswersError(
                f"answers file {path}: modules.{mod_id} must be a mapping of variable values"
            )
        answers.modules[mod_id] = dict(mod_vars)
    return answers


def collect_module_config(
    manifest: Manifest,
    provided: dict[str, object],
    *,
    folder_style: str = "Title-Case-Hyphen",
) -> ModuleConfig:
    """Resolve one module's variables from answers or defaults — shared by init, add, adopt.

    Untouched defaults are filled (and string defaults styled) by
    ``resolve_variables``; only explicit answers land here.
    """
    values: dict[str, object] = {}
    for var in manifest.variables:
        if var.key in provided:
            values[var.key] = provided[var.key]
        elif var.default is None:
            raise AnswersError(
                f"module {manifest.name!r} variable {var.key!r} has no default; "
                "supply it in the answers file"
            )
    extra = set(provided) - {var.key for var in manifest.variables}
    if extra:
        raise AnswersError(f"module {manifest.name!r} has no variable(s) {sorted(extra)}")
    return ModuleConfig(
        version=manifest.version,
        vars=resolve_variables(manifest, values, folder_style=folder_style),
    )


def build_config(library: dict[str, Manifest], answers: Answers) -> Config:
    """Produce a validated Config from answers; anything unanswered takes its default."""
    vault_name = answers.vault_name if answers.vault_name is not None else "My Vault"
    folder_style = answers.folder_style if answers.folder_style is not None else "Title-Case-Hyphen"
    runtimes = answers.runtimes if answers.runtimes is not None else ["claude-code"]

    enabled: dict[str, dict[str, object]] = {"core": {}}
    enabled.update(answers.modules)
    # Dependencies are auto-enabled and become visible in the plan and the config (§9.2).
    for mod_id in dependency_closure(enabled, library):
        enabled.setdefault(mod_id, {})

    modules: dict[str, ModuleConfig] = {}
    for mod_id in sorted(enabled, key=lambda m: (m != "core", m)):
        modules[mod_id] = collect_module_config(
            library[mod_id], enabled[mod_id], folder_style=folder_style
        )

    return default_config(
        vault_name=vault_name,
        folder_style=folder_style,
        runtimes=runtimes,
        modules=modules,
        sources=resolved_sources(answers, runtimes),
        checkpoints=bool(answers.checkpoints),
        scope_hooks=bool(answers.scope_hooks),
    )


def _default_repo(src_name: str) -> str:
    from .sources import DEFAULT_REPOS

    repo = DEFAULT_REPOS.get(src_name)
    if repo is None:
        raise AnswersError(
            f"source {src_name!r} has no default repo; supply 'repo' in the answers file"
        )
    return repo


def resolved_sources(
    answers: Answers | None, runtimes: Sequence[str] = ("claude-code",)
) -> dict[str, dict[str, str]]:
    """Declared sources from an answers file, default repos filled in — shared by init and adopt.

    obsidian-skills defaults *in* (#65); the opt-out is explicit:
    ``sources: {obsidian-skills: false}``. Only claude-code reads
    ``.claude/skills/``, so no claude-code runtime, no default.
    """
    declared = answers.sources if answers else {}
    sources = {
        src_name: {"repo": src.get("repo") or _default_repo(src_name), **src}
        for src_name, src in declared.items()
    }
    answered = OBSIDIAN_SKILLS in sources or OBSIDIAN_SKILLS in (
        answers.sources_off if answers else set()
    )
    if not answered and "claude-code" in runtimes:
        sources[OBSIDIAN_SKILLS] = {"repo": _default_repo(OBSIDIAN_SKILLS)}
    return sources

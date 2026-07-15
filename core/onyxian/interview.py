"""The interview: turn questions, answers files, and profiles into a Config (KICKSTART.md §9.2).

Hard parity rule: every question maps one-to-one onto a config key, so the
wizard, a hand-edited config, and an `--answers` file are three doors into the
same room. Two input shapes are accepted:

Answers file — a partial mirror of the config::

    vault:  { name: "Example" }
    naming: { folder_style: kebab-case }
    framework: { runtimes: [claude-code] }
    modules:
      core: {}            # module id -> variable values (flat)

Profile — a named module set with presets (§5.5)::

    name: minimal
    modules: [core]
    presets:
      core: {}

Missing values fall back to interactive prompts on a TTY, otherwise to declared
defaults; a required variable with no default and no answer is an error, never
a silent guess.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .configio import default_config
from .errors import AnswersError, ResolveError
from .model import FOLDER_STYLES, MODULE_ID_RE, RUNTIMES, Config, Manifest, ModuleConfig, Variable
from .resolve import resolve_variables
from .yamlio import load_yaml, require_mapping


def _is_interactive() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


class Answers:
    """Normalized form of an answers file or profile."""

    def __init__(self) -> None:
        self.vault_name: str | None = None
        self.folder_style: str | None = None
        self.runtimes: list[str] | None = None
        self.checkpoints: bool | None = None
        self.modules: dict[str, dict[str, object]] = {}
        self.sources: dict[str, dict[str, str]] = {}


def resolve_answers_spec(spec: str) -> Path:
    """An ``--answers`` value: an existing file path, or the bare name of a bundled profile.

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
            f"--answers {spec!r}: not a file, and not a bundled profile. "
            f"Available profiles: {available}"
        )
    raise AnswersError(f"--answers {spec!r}: file not found")


def load_answers(path: Path) -> Answers:
    data = require_mapping(load_yaml(path, what="answers file"), what=f"answers file {path}")
    answers = Answers()

    modules_list = data.get("modules")
    if isinstance(modules_list, list):  # profile shape (§5.5)
        allowed = {"name", "modules", "presets"}
        unknown = set(data) - allowed
        if unknown:
            raise AnswersError(f"profile {path}: unknown key(s) {sorted(unknown)}")
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
    if not isinstance(framework, dict) or set(framework) - {"runtimes", "checkpoints"}:
        raise AnswersError(
            f"answers file {path}: 'framework' may only contain 'runtimes' and 'checkpoints'"
        )
    if "checkpoints" in framework:
        if not isinstance(framework["checkpoints"], bool):
            raise AnswersError(f"answers file {path}: framework.checkpoints must be true or false")
        answers.checkpoints = framework["checkpoints"]
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
    if not isinstance(raw_modules, dict):
        raise AnswersError(
            f"answers file {path}: 'modules' must be a mapping of id -> variable values"
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


def _prompt_text(question: str, default: str) -> str:
    raw = input(f"{question} [{default}]: ").strip()
    return raw or default


def _prompt_choice(question: str, options: tuple[str, ...], default: str) -> str:
    print(question)
    for i, option in enumerate(options, start=1):
        marker = " (default)" if option == default else ""
        print(f"  {i}. {option}{marker}")
    for attempt in range(3):
        raw = input(f"choose 1-{len(options)} [{options.index(default) + 1}]: ").strip()
        if not raw:
            return default
        try:
            index = int(raw)
            if 1 <= index <= len(options):
                return options[index - 1]
        except ValueError:
            if raw in options:
                return raw
        if attempt < 2:
            print(f"  (not a valid choice; enter a number or one of: {', '.join(options)})")
    print(f"  (unrecognized; using default {default!r})")
    return default


def _prompt_variable(module: str, var: Variable, folder_style: str = "Title-Case-Hyphen") -> object:
    from .render import style_default

    label = f"[{module}] {var.prompt}"
    if var.type == "choice":
        default = var.default if var.default is not None else var.options[0]
        return _prompt_choice(label, var.options, str(default))
    if var.type == "bool":
        default = bool(var.default)
        raw = input(f"{label} (y/n) [{'y' if default else 'n'}]: ").strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        return default
    default = style_default(str(var.default), folder_style) if var.default is not None else ""
    if default:
        return _prompt_text(label, default)
    raw = input(f"{label}: ").strip()
    while not raw:
        raw = input(f"{label} (required): ").strip()
    return raw


def collect_module_config(
    manifest: Manifest,
    provided: dict[str, object],
    *,
    interactive: bool,
    folder_style: str = "Title-Case-Hyphen",
) -> ModuleConfig:
    """Resolve one module's variables from answers, prompts, or defaults —
    shared by init, add, adopt.

    Untouched defaults are filled (and string defaults styled) by
    ``resolve_variables``; only explicit answers and prompt replies land here.
    """
    values: dict[str, object] = {}
    for var in manifest.variables:
        if var.key in provided:
            values[var.key] = provided[var.key]
        elif interactive:
            values[var.key] = _prompt_variable(manifest.name, var, folder_style)
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


def run_interview(
    library: dict[str, Manifest],
    answers: Answers | None,
    *,
    interactive: bool | None = None,
) -> Config:
    """Produce a validated Config from answers and, where allowed, prompts."""
    if interactive is None:
        interactive = answers is None and _is_interactive()
    if answers is None:
        if not interactive:
            raise AnswersError(
                "stdin is not interactive; pass --answers <file.yaml> (or a profile) "
                "for a non-interactive run"
            )
        answers = Answers()

    vault_name = answers.vault_name
    if vault_name is None:
        vault_name = _prompt_text("Vault name", "My Vault") if interactive else "My Vault"
    folder_style = answers.folder_style
    if folder_style is None:
        folder_style = (
            _prompt_choice("Folder naming style", FOLDER_STYLES, "Title-Case-Hyphen")
            if interactive
            else "Title-Case-Hyphen"
        )
    runtimes = answers.runtimes or ["claude-code"]

    checkpoints = answers.checkpoints
    if checkpoints is None:
        if interactive:
            raw = (
                input(
                    "Enable vault checkpoints? A git-backed snapshot of the vault taken when a "
                    "Claude Code session starts, so any agent edit is easy to see and undo. "
                    "(y/n) [n]: "
                )
                .strip()
                .lower()
            )
            checkpoints = raw in ("y", "yes")
        else:
            checkpoints = False

    enabled: dict[str, dict[str, object]] = {"core": {}}
    enabled.update(answers.modules)
    for mod_id in list(enabled):
        if mod_id not in library:
            raise ResolveError(
                f"module {mod_id!r} is not in the module library (available: {sorted(library)})"
            )
    # Dependencies are auto-enabled and become visible in the plan and the config (§9.2).
    queue = list(enabled)
    while queue:
        mod_id = queue.pop()
        for dep in library[mod_id].depends:
            if dep not in enabled:
                if dep not in library:
                    raise ResolveError(f"module {mod_id!r} depends on unknown module {dep!r}")
                enabled[dep] = {}
                queue.append(dep)

    modules: dict[str, ModuleConfig] = {}
    for mod_id in sorted(enabled, key=lambda m: (m != "core", m)):
        modules[mod_id] = collect_module_config(
            library[mod_id], enabled[mod_id], interactive=interactive, folder_style=folder_style
        )

    sources = resolved_sources(answers)
    if not sources and interactive and "claude-code" in runtimes:
        raw = (
            input(
                "Install kepano/obsidian-skills (Obsidian-format literacy for agents, "
                "pinned to a commit)? (y/n) [y]: "
            )
            .strip()
            .lower()
        )
        if raw in ("", "y", "yes"):
            sources["obsidian-skills"] = {"repo": _default_repo("obsidian-skills")}

    return default_config(
        vault_name=vault_name,
        folder_style=folder_style,
        runtimes=runtimes,
        modules=modules,
        sources=sources,
        checkpoints=checkpoints,
    )


def _default_repo(src_name: str) -> str:
    from .sources import DEFAULT_REPOS

    repo = DEFAULT_REPOS.get(src_name)
    if repo is None:
        raise AnswersError(
            f"source {src_name!r} has no default repo; supply 'repo' in the answers file"
        )
    return repo


def resolved_sources(answers: Answers | None) -> dict[str, dict[str, str]]:
    """Declared sources from an answers file, default repos filled in — shared by init and adopt."""
    if answers is None:
        return {}
    return {
        src_name: {"repo": src.get("repo") or _default_repo(src_name), **src}
        for src_name, src in answers.sources.items()
    }

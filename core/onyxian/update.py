"""`onyxian update`: fetch, stage, re-plan, and move the pins forward.

Three things the CLI used to hold as habit are this module's contract:

1. **Scratch lifetime.** ``prepare_update`` fetches every externally-sourced module into
   a scratch tree the *caller* owns, and a staged manifest's ``directory`` points into
   it. The caller must keep it alive until it has installed the staged copies — and may
   drop it the moment it has, including on the decline path, where nothing is installed.
2. **Nothing here writes to the vault.** Deciding an update is pure but for the fetch, so
   a dry run shows the same plan and the same trust review a real run would (#32), and
   the trust gate happens between deciding and writing rather than inside either.
3. **Config edits are text transforms.** ``bump_pins`` and ``source_pin_edit`` return new
   config text rather than writing it, so the caller can collect every edit into the one
   write that must land *after* apply and never partway (cli.py invariant 4, #50).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .answers import Answers, collect_module_config
from .config_edit import (
    bump_module_versions,
    insert_module_variables,
    replace_module_pin,
    replace_source_pin,
)
from .configio import CONFIG_REL
from .errors import AnswersError, OnyxianError, ResolveError
from .external import EXTERNAL_REL, changed_instruction_files, fetch_external, trust_warning
from .intent import build_desired_state
from .lockio import load_lock
from .model import Config, Lock, Manifest, ModuleConfig
from .planner import CONFLICT_NEW, STALE, Plan, build_plan, render_plan
from .repo import default_modules_root, discover_modules
from .resolve import resolve_modules
from .sources import (
    SourceInstallError,
    SourceInstallResult,
    SourceTrustInfo,
    enabled_for_planner,
    install_obsidian_skills,
)


@dataclass
class UpdatePlan:
    """Everything an update decided, before a byte of it is written."""

    plan: Plan
    manifests: list[Manifest]
    new_config: Config
    module_targets: list[str]
    update_sources: bool
    staged: list[Manifest] = field(default_factory=list)
    changes: dict[str, tuple[str, str]] = field(default_factory=dict)  # id -> (old, new)
    held: dict[str, tuple[str, str]] = field(default_factory=dict)  # id -> (pinned, library)
    pin_changes: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    variable_additions: dict[str, dict[str, object]] = field(default_factory=dict)
    trust_blocks: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # stdout, ahead of the report
    warnings: list[str] = field(default_factory=list)  # stderr

    @property
    def nothing_to_do(self) -> bool:
        return (
            self.plan.is_empty
            and not self.changes
            and not self.pin_changes
            and not self.variable_additions
            and not self.update_sources
        )


def prepare_update(
    vault_root: Path,
    config: Config,
    target: str | None,
    scratch: Path,
    answers: Answers | None = None,
) -> UpdatePlan:
    """Decide the whole update — fetch, stage, re-plan — without touching the vault.

    ``scratch`` must outlive the caller's ``install_external`` calls (see module docstring).
    """
    if target is None:
        module_targets = list(config.modules)
        update_sources = bool(config.sources)
    elif target in config.modules:
        module_targets, update_sources = [target], False
    elif target in config.sources:
        module_targets, update_sources = [], True
    else:
        raise ResolveError(f"{target!r} is neither an enabled module nor a declared source")

    # Fetch externally-sourced modules first, so the plan reflects upstream.
    # The fetched content stays staged until the user confirms; declining leaves
    # both the vault and the installed library copy untouched.
    pin_changes: dict[str, tuple[str | None, str | None]] = {}
    staged: list[Manifest] = []
    trust_blocks: list[str] = []
    notes: list[str] = []
    warnings: list[str] = []
    for mod_id in module_targets:
        source = config.modules[mod_id].source
        if source is None:
            continue
        # Fetched on --dry-run too (into scratch only): the dry run must show the
        # same plan and trust review the real update would (#32).
        try:
            fetched, _, new_pin = fetch_external(source["repo"], scratch / mod_id)
            if fetched.name != mod_id:
                raise OnyxianError(
                    f"{source['repo']} now serves module {fetched.name!r}, not {mod_id!r}"
                )
            staged.append(fetched)
            old_pin = source.get("pin")
            if new_pin and new_pin != old_pin:
                pin_changes[mod_id] = (old_pin, new_pin)
                notes.append(f"external module {mod_id!r}: fetched {new_pin[:12]}")
            changed = changed_instruction_files(
                vault_root / ".vault" / "modules" / mod_id, Path(fetched.directory)
            )
            if changed:
                trust_blocks.append(
                    trust_warning(fetched, source["repo"], new_pin)
                    + "\n  changed instruction file(s) since the reviewed commit: "
                    + ", ".join(changed)
                    + f"\n  the reviewed copy stays at {EXTERNAL_REL}/{mod_id}/"
                    + " until you confirm."
                )
        except OnyxianError as exc:
            warnings.append(f"warning: external module {mod_id!r} not refreshed: {exc}")

    library = discover_modules(default_modules_root(), vault_root)
    library.update({m.name: m for m in staged})  # plan against the staged (new) content

    changes: dict[str, tuple[str, str]] = {}
    for mod_id in module_targets:
        if mod_id not in library:
            raise ResolveError(f"module {mod_id!r} is enabled but missing from the library")
        if config.modules[mod_id].version != library[mod_id].version:
            changes[mod_id] = (config.modules[mod_id].version, library[mod_id].version)

    # #51: a targeted run must not die on some *other* enabled module's version skew —
    # that is exactly the post-release state where a one-module update is wanted.
    # Resolution and rendering are whole-vault (the library ships only current content),
    # so resolve the skewed strangers at their library version and hold their files back.
    held = {
        mod_id: (config.modules[mod_id].version, library[mod_id].version)
        for mod_id in config.modules
        if mod_id not in module_targets
        and mod_id in library
        and config.modules[mod_id].version != library[mod_id].version
    }

    updated_modules: dict[str, ModuleConfig] = {}
    variable_additions: dict[str, dict[str, object]] = {}
    for mod_id, mod in config.modules.items():
        version = library[mod_id].version if mod_id in changes or mod_id in held else mod.version
        variables = dict(mod.vars)
        if mod_id in changes:
            supplied = answers.modules.get(mod_id, {}) if answers else {}
            changed_existing = {
                key
                for key, value in supplied.items()
                if key in variables and variables[key] != value
            }
            if changed_existing:
                raise AnswersError(
                    f"update answers cannot change existing variable(s) for module {mod_id!r}: "
                    f"{sorted(changed_existing)}; edit {CONFIG_REL} and rerun `onyxian update`"
                )
            variables.update(supplied)
            resolved = collect_module_config(
                library[mod_id], variables, folder_style=config.folder_style
            ).vars
            additions = {key: value for key, value in resolved.items() if key not in mod.vars}
            if additions:
                variable_additions[mod_id] = additions
            variables = resolved
        updated_modules[mod_id] = ModuleConfig(
            version=version,
            vars=variables,
            source=dict(mod.source) if mod.source else None,
        )

    # Intent at the bundled versions; existing choices stay untouched and newly
    # introduced variables come from --answers (or the manifest default).
    new_config = Config(
        framework_version=config.framework_version,
        runtimes=list(config.runtimes),
        vault_name=config.vault_name,
        folder_style=config.folder_style,
        modules=updated_modules,
        sources={k: dict(v) for k, v in config.sources.items()},
        checkpoints=config.checkpoints,
        scope_hooks=config.scope_hooks,
    )
    manifests = resolve_modules(new_config, library)
    desired = build_desired_state(new_config, manifests)
    plan = build_plan(vault_root, desired, load_lock(vault_root), enabled_for_planner(new_config))
    if held:
        # Only what the target owns. A held module's pin in config.yaml stays put, so
        # writing its new content would leave the ledger disagreeing with the config;
        # the generated aggregates (module "core") are held for the same reason.
        plan.actions = [a for a in plan.actions if a.module in module_targets]

    return UpdatePlan(
        plan=plan,
        manifests=manifests,
        new_config=new_config,
        module_targets=module_targets,
        update_sources=update_sources,
        staged=staged,
        changes=changes,
        held=held,
        pin_changes=pin_changes,
        variable_additions=variable_additions,
        trust_blocks=trust_blocks,
        notes=notes,
        warnings=warnings,
    )


def render_update_report(up: UpdatePlan) -> list[str]:
    """The version deltas, the plan, and the two never-overwritten reports."""
    lines = list(up.notes)
    if up.changes:
        lines.append("module updates:")
        lines += [f"  {mod}: {old} -> {new}" for mod, (old, new) in sorted(up.changes.items())]
    elif up.module_targets and not up.held:  # a source-only target has no versions to report on
        lines.append("all enabled modules are at their library versions.")
    if up.variable_additions:
        lines.append("new module variables:")
        lines += [
            f"  {mod_id}.{key} = {json.dumps(value, ensure_ascii=False)}"
            for mod_id in sorted(up.variable_additions)
            for key, value in sorted(up.variable_additions[mod_id].items())
        ]
    if up.held:
        lines.append("held at their pinned versions (not targeted by this run):")
        lines += [
            f"  {mod}: {pinned} (library {shipped})"
            for mod, (pinned, shipped) in sorted(up.held.items())
        ]
        lines.append("  `onyxian update` moves the whole vault forward.")
    lines.append(render_plan(up.plan))
    conflicts = [a for a in up.plan.mutating if a.type == CONFLICT_NEW]
    if conflicts:
        lines.append(
            "update report — new versions land BESIDE your customized files; no overwrites:"
        )
        lines += [f"  ! {a.path} -> {a.write_path}" for a in conflicts]
    stale = [a for a in up.plan.reports if a.type == STALE]
    if stale:
        lines.append("update report — tracked but no longer shipped; left in place:")
        lines += [f"  * {a.path}" for a in stale]
    return lines


def refresh_source(
    vault_root: Path, new_config: Config, lock: Lock, *, gate: Callable[[SourceTrustInfo], bool]
) -> tuple[SourceInstallResult | None, list[str]]:
    """Advance the declared source to upstream HEAD: (result or None, stderr notes).

    Never raises. This runs between the apply and the single config write, so a failure
    that escaped would strand the config behind files that already moved (#50).
    """
    try:
        src = install_obsidian_skills(vault_root, new_config, lock, advance_pin=True, gate=gate)
    except SourceInstallError as exc:
        return None, [f"warning: source update skipped: {exc}"]
    if src is not None and src.declined:
        # Fail closed like external instruction re-gates (#61), but a source is an
        # optional amplifier: decline just leaves it at the reviewed pin.
        return None, [
            f"source {src.name!r} left at its current pin: the changed skill "
            "instructions were not trusted (re-run `onyxian update` with --trust "
            "after reviewing)."
        ]
    return src, []


def bump_pins(
    config_text: str,
    changes: dict[str, tuple[str, str]],
    pin_changes: dict[str, tuple[str | None, str | None]],
    variable_additions: dict[str, dict[str, object]] | None = None,
) -> tuple[str, list[str], list[str]]:
    """Module version pins and external source pins: (config text, stdout, stderr)."""
    notes: list[str] = []
    warnings: list[str] = []
    if variable_additions:
        config_text, _ = insert_module_variables(config_text, variable_additions)
        notes += [
            f"config: variable answer(s) saved for {mod_id}"
            for mod_id in sorted(variable_additions)
        ]
    if changes:
        config_text, _ = bump_module_versions(config_text, changes)
        notes.append(f"config: version pin(s) bumped for {', '.join(sorted(changes))}")
    for mod_id, (old_pin, new_pin) in pin_changes.items():
        if old_pin and new_pin:
            config_text = replace_module_pin(config_text, mod_id, old_pin, new_pin)
            notes.append(f"config: {mod_id} source pin {old_pin[:12]} -> {new_pin[:12]}")
        elif new_pin:
            warnings.append(
                f"note: {mod_id} had no recorded pin; "
                f'add `pin: "{new_pin}"` to its source in {CONFIG_REL}'
            )
    return config_text, notes, warnings


def source_pin_edit(config_text: str, src: SourceInstallResult) -> tuple[str, list[str], list[str]]:
    """The source's commit delta report and its pin edit: (config text, stdout, stderr)."""
    if src.previous_pin and src.previous_pin != src.pin:
        delta = f"{src.previous_pin[:12]} -> {src.pin[:12]}"
    elif src.previous_pin:
        delta = f"already at {src.pin[:12]}"
    else:
        delta = f"now pinned at {src.pin[:12]}"
    notes = [f"source {src.name}: {delta} ({len(src.installed)} file(s) refreshed)"]
    warnings = [f"  - left alone {path}: {reason}" for path, reason in src.skipped]
    if src.previous_pin and src.previous_pin != src.pin:
        config_text = replace_source_pin(config_text, src.name, src.previous_pin, src.pin)
    elif not src.previous_pin:
        warnings.append(
            f'note: no pin was recorded before; add `pin: "{src.pin}"` under '
            f"sources.{src.name} in {CONFIG_REL} to pin it"
        )
    return config_text, notes, warnings

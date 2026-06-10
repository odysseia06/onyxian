"""The `onyx` command-line interface (KICKSTART.md §9.1).

Mental model: config declares intent, lock records state, `plan` is the diff,
`apply` reconciles. Everything else is ergonomics. Commands that arrive in
later milestones exist as honest stubs that say which milestone, instead of
pretending not to exist.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from . import ENGINE_VERSION
from .adopt import (
    acceptance_token,
    assert_additive,
    claim_existing_seeds,
    scan_vault,
)
from .applier import apply_plan
from .config_edit import (
    bump_module_versions,
    insert_module_entries,
    remove_module_entry,
    replace_pin,
)
from .configio import (
    CONFIG_REL,
    config_path,
    is_managed_vault,
    load_config,
    render_config_text,
)
from .doctor import exit_code as doctor_exit_code
from .doctor import render_findings, run_doctor
from .errors import AnswersError, ConfigError, OnyxError, ResolveError, VaultStateError
from .external import EXTERNAL_REL, fetch_external, install_external, looks_external, trust_warning
from .fsio import read_text, sha256_bytes, sha256_file, write_text_atomic
from .intent import build_desired_state
from .paths import to_native
from .planner import CONFLICT_NEW, STALE
from .interview import (
    _is_interactive,
    collect_module_config,
    load_answers,
    resolved_sources,
    run_interview,
)
from .lockio import load_lock, save_lock
from .model import KIND_SEEDED, Config, Lock, LockEntry, Manifest, ModuleConfig
from .planner import Plan, build_plan, render_plan
from .repo import default_modules_root, discover_modules
from .resolve import resolve_modules
from .sources import SourceInstallError, enabled_for_planner, install_obsidian_skills

# Things allowed to pre-exist in an `init` target: version control, Obsidian's
# own settings folder, and OS junk files. Anything else means the folder has a
# life already — that is `adopt`'s territory (M1), never `init`'s.
_ALLOWED_PREEXISTING = {".git", ".obsidian", ".DS_Store", "Thumbs.db", "desktop.ini"}


def _reconfigure_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def _confirm(question: str, *, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not _is_interactive():
        raise AnswersError("confirmation needed but stdin is not interactive; pass --yes")
    raw = input(f"{question} [y/N] ").strip().lower()
    return raw in ("y", "yes")


def _vault_root(args: argparse.Namespace) -> Path:
    root = Path(args.vault)
    if not is_managed_vault(root):
        raise ConfigError(
            f"{root} is not an Onyx-managed vault ({CONFIG_REL} not found); "
            "run `onyx init <folder>` to create one"
        )
    return root


def _load_context(vault_root: Path) -> tuple[Config, list[Manifest], Plan, Lock]:
    config = load_config(vault_root)
    library = discover_modules(default_modules_root(), vault_root)
    manifests = resolve_modules(config, library)
    desired = build_desired_state(config, manifests)
    lock = load_lock(vault_root)
    plan = build_plan(vault_root, desired, lock, enabled_for_planner(config))
    return config, manifests, plan, lock


def _install_sources_step(target: Path, config: Config, lock: Lock, library: dict[str, Manifest]) -> None:
    """Post-apply source install (§9.2 'runtime install'); failures degrade to warnings (P2)."""
    if not config.sources:
        return
    try:
        result = install_obsidian_skills(target, config, lock)
    except SourceInstallError as exc:
        print(f"warning: obsidian-skills install skipped: {exc}", file=sys.stderr)
        print(
            "         the vault works fully without it; `onyx update` (M3) will install declared sources later.",
            file=sys.stderr,
        )
        return
    if result is None:
        return
    print(f"installed source {result.name} at pin {result.pin[:12]} ({len(result.installed)} files).")
    for path, reason in result.skipped:
        print(f"  - skipped {path}: {reason}", file=sys.stderr)
    if config.sources[result.name].get("pin") != result.pin:
        config.sources[result.name]["pin"] = result.pin
        config_bytes = write_text_atomic(config_path(target), render_config_text(config))
        lock.put(
            LockEntry(
                path=CONFIG_REL,
                sha256=sha256_bytes(config_bytes),
                module="core",
                module_version=library["core"].version,
                kind=KIND_SEEDED,
            )
        )
        save_lock(target, lock)


def _print_apply_outcome(result, manifests: list[Manifest], newly_installed: set[str]) -> int:
    print(f"applied: {len(result.performed)} action(s).")
    if result.skipped:
        print("skipped (re-verify failed):", file=sys.stderr)
        for action, reason in result.skipped:
            print(f"  - {action.target}: {reason}", file=sys.stderr)
        return 1
    for manifest in manifests:
        if manifest.name in newly_installed and manifest.post_install:
            print(f"\n[{manifest.name}] next steps:")
            for line in manifest.post_install.splitlines():
                print(f"  {line}")
    return 0


# ----------------------------------------------------------------- commands


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.target)
    if target.exists():
        if not target.is_dir():
            raise VaultStateError(f"init target {target} exists and is not a directory")
        if (target / ".vault").exists():
            raise VaultStateError(
                f"{target} is already an Onyx vault; edit {CONFIG_REL} and run `onyx plan` / `onyx apply`"
            )
        offenders = sorted(e.name for e in target.iterdir() if e.name not in _ALLOWED_PREEXISTING)
        if offenders:
            shown = ", ".join(offenders[:5]) + (", ..." if len(offenders) > 5 else "")
            raise VaultStateError(
                f"init requires a new or empty folder, but {target} contains: {shown}. "
                "Bringing an existing vault under management is `adopt`'s job (M1)."
            )

    answers = load_answers(Path(args.answers)) if args.answers else None
    library = discover_modules(default_modules_root())
    config = run_interview(library, answers)
    manifests = resolve_modules(config, library)
    desired = build_desired_state(config, manifests)
    lock = Lock()
    plan = build_plan(target, desired, lock, enabled_for_planner(config))

    print(f"vault: {config.vault_name!r} at {target}")
    print(f"folder style: {config.folder_style}; modules: {', '.join(config.modules)}")
    print(render_plan(plan))
    print(f"  + {CONFIG_REL} (seeded; yours to edit)")
    print("  + .vault/lock.json (the engine's ledger)")

    if args.dry_run:
        print("dry run; nothing written.")
        return 0
    if not _confirm("create this vault?", assume_yes=args.yes):
        print("aborted; nothing written.")
        return 1

    target.mkdir(parents=True, exist_ok=True)
    config_bytes = write_text_atomic(config_path(target), render_config_text(config))
    lock.put(
        LockEntry(
            path=CONFIG_REL,
            sha256=sha256_bytes(config_bytes),
            module="core",
            module_version=library["core"].version,
            kind=KIND_SEEDED,
        )
    )
    save_lock(target, lock)
    result = apply_plan(target, plan, lock)
    code = _print_apply_outcome(result, manifests, newly_installed={m.name for m in manifests})
    _install_sources_step(target, config, lock, library)
    print(f"\nvault ready. open it in Obsidian, then try: onyx doctor --vault {target}")
    return code


def cmd_plan(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    _, _, plan, _ = _load_context(vault_root)
    print(render_plan(plan))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    config, manifests, plan, lock = _load_context(vault_root)
    print(render_plan(plan))
    if plan.is_empty:
        return 0
    if args.dry_run:
        print("dry run; nothing written.")
        return 0
    if not _confirm("apply these changes?", assume_yes=args.yes):
        print("aborted; nothing written.")
        return 1
    previously_installed = {entry.module for entry in lock.entries.values()}
    result = apply_plan(vault_root, plan, lock)
    newly_installed = {m.name for m in manifests} - previously_installed
    return _print_apply_outcome(result, manifests, newly_installed)


def cmd_doctor(args: argparse.Namespace) -> int:
    vault_root = Path(args.vault)
    findings = run_doctor(vault_root, default_modules_root())
    print(render_findings(findings))
    return doctor_exit_code(findings)


def cmd_adopt(args: argparse.Namespace) -> int:
    target = Path(args.target)
    if not target.is_dir():
        raise VaultStateError(f"adopt target {target} is not an existing directory")
    if (target / ".vault").exists():
        raise VaultStateError(
            f"{target} is already an Onyx vault; edit {CONFIG_REL} and run `onyx plan` / `onyx apply`"
        )

    library = discover_modules(default_modules_root())
    answers = load_answers(Path(args.answers)) if args.answers else None
    scan = scan_vault(target, library)

    # Assemble intent: answers win; scan results are defaults, never decisions (§9.3).
    folder_style = answers.folder_style if answers and answers.folder_style else scan.style
    vault_name = answers.vault_name if answers and answers.vault_name else target.resolve().name
    runtimes = answers.runtimes if answers and answers.runtimes else ["claude-code"]
    if answers and answers.modules:
        enabled: dict[str, dict[str, object]] = {m: dict(v) for m, v in answers.modules.items()}
    else:
        enabled = {}
        for claim in scan.claims:
            enabled.setdefault(claim.module, {})
    enabled.setdefault("core", {})
    for claim in scan.claims:  # claimed values fill gaps in whatever set is enabled
        if claim.module in enabled:
            enabled[claim.module].setdefault(claim.var, claim.value)
    for mod_id in list(enabled):
        if mod_id not in library:
            raise ResolveError(f"module {mod_id!r} is not in the module library (available: {sorted(library)})")
    queue = list(enabled)
    while queue:
        for dep in library[queue.pop()].depends:
            if dep not in enabled:
                enabled[dep] = {}
                queue.append(dep)

    modules: dict[str, ModuleConfig] = {}
    for mod_id in sorted(enabled, key=lambda m: (m != "core", m)):
        modules[mod_id] = collect_module_config(
            library[mod_id], enabled[mod_id], interactive=False, folder_style=folder_style
        )
    from .configio import default_config

    config = default_config(
        vault_name=vault_name,
        folder_style=folder_style,
        runtimes=runtimes,
        modules=modules,
        sources=resolved_sources(answers),
    )
    manifests = resolve_modules(config, library)
    desired = build_desired_state(config, manifests)
    lock = Lock()
    seed_claims = claim_existing_seeds(target, desired, lock)
    plan = build_plan(target, desired, lock, enabled_for_planner(config))
    assert_additive(plan)
    config_text = render_config_text(config)
    token = acceptance_token(config_text, plan, seed_claims)

    print(f"adopting: {target}  (vault {config.vault_name!r}, folder style {config.folder_style})")
    shown_claims = [c for c in scan.claims if c.module in config.modules]
    if shown_claims:
        print("claims (existing folders mapped to module variables; nothing moves):")
        for claim in shown_claims:
            print(f"  = {claim.value}/  ->  {claim.module}.{claim.var}  [{claim.reason}]")
    unused_claims = [c for c in scan.claims if c.module not in config.modules]
    if unused_claims:
        print("also matched, but those modules are not in your set (enable them to claim):")
        for claim in unused_claims:
            print(f"  ? {claim.value}/ looks like {claim.module}.{claim.var}")
    if seed_claims:
        print("existing files claimed as seeds (recorded as yours; never touched):")
        for sc in seed_claims:
            print(f"  = {sc.path}  ({sc.module})")
    print(render_plan(plan))
    print(f"  + {CONFIG_REL} (seeded; yours to edit)")
    print("  + .vault/lock.json (the engine's ledger)")
    if scan.ambiguities:
        print("checklist — decide these yourself; the engine will not (§9.3):")
        for note in scan.ambiguities:
            print(f"  ? {note}")
    print("guarantee: adopt is additive only; nothing existing is moved, renamed, deleted, or overwritten.")

    if args.dry_run:
        print("dry run; nothing written.")
        return 0
    if args.accept:
        if args.accept != token:
            print(
                "error: the vault or your answers changed since that plan was reviewed; "
                "re-run adopt and review again",
                file=sys.stderr,
            )
            return 1
    elif _is_interactive():
        typed = input('mandatory review (§9.3): type "adopt" to apply exactly this plan: ').strip()
        if typed != "adopt":
            print("aborted; nothing written.")
            return 1
    else:
        print(f"\nreview complete. to apply exactly this plan, re-run with: --accept {token}")
        return 0

    config_bytes = write_text_atomic(config_path(target), config_text)
    lock.put(
        LockEntry(
            path=CONFIG_REL,
            sha256=sha256_bytes(config_bytes),
            module="core",
            module_version=library["core"].version,
            kind=KIND_SEEDED,
        )
    )
    save_lock(target, lock)
    result = apply_plan(target, plan, lock)
    code = _print_apply_outcome(result, manifests, newly_installed={m.name for m in manifests})
    _install_sources_step(target, config, lock, library)
    print(f"\nvault adopted; nothing pre-existing was touched. next: onyx doctor --vault {target}")
    return code


def _collect_dependency_closure(
    target: str, config: Config, library: dict[str, Manifest]
) -> list[str]:
    to_add: list[str] = []
    queue = [target]
    while queue:
        mod_id = queue.pop()
        if mod_id in config.modules or mod_id in to_add:
            continue
        if mod_id not in library:
            raise ResolveError(f"module {target!r} depends on unknown module {mod_id!r}")
        to_add.append(mod_id)
        queue.extend(library[mod_id].depends)
    return to_add


def _enable_and_apply(
    args: argparse.Namespace,
    vault_root: Path,
    library: dict[str, Manifest],
    new_entries: dict[str, ModuleConfig],
    enabling_line: str,
) -> int:
    """Shared tail of `add` (bundled and external): config insert, plan, confirm, apply."""
    old_text = read_text(config_path(vault_root))
    new_text, new_config = insert_module_entries(old_text, new_entries)
    manifests = resolve_modules(new_config, library)
    desired = build_desired_state(new_config, manifests)
    lock = load_lock(vault_root)
    plan = build_plan(vault_root, desired, lock, enabled_for_planner(new_config))

    print(enabling_line)
    print(render_plan(plan))
    print(f"  ~ {CONFIG_REL} (adding: {', '.join(sorted(new_entries))})")
    if args.dry_run:
        print("dry run; nothing written.")
        return 0
    if not _confirm("enable and apply?", assume_yes=args.yes):
        print("aborted; nothing written.")
        return 1

    write_text_atomic(config_path(vault_root), new_text)
    previously_installed = {entry.module for entry in lock.entries.values()}
    result = apply_plan(vault_root, plan, lock)
    newly_installed = {m.name for m in manifests} - previously_installed
    return _print_apply_outcome(result, manifests, newly_installed)


def _add_external(args: argparse.Namespace, vault_root: Path, config: Config) -> int:
    spec = args.module
    with tempfile.TemporaryDirectory(prefix="onyx-ext-") as tmp:
        manifest, repo, pin = fetch_external(spec, Path(tmp))
        library = discover_modules(default_modules_root(), vault_root)
        already = config.modules.get(manifest.name)
        if already is not None and already.source is not None:
            print(f"module {manifest.name!r} is already installed; `onyx update {manifest.name}` refreshes it.")
            return 0
        if manifest.name in library or already is not None:
            raise ResolveError(
                f"module id {manifest.name!r} already exists in the library; external modules cannot shadow it"
            )
        for dep in manifest.depends:
            if dep not in library and dep not in config.modules:
                raise ResolveError(f"external module {manifest.name!r} depends on {dep!r}, which is not available")

        print(trust_warning(manifest, repo, pin))
        if not _confirm("trust and install this module?", assume_yes=args.yes):
            print("aborted; nothing installed.")
            return 1
        install_external(vault_root, manifest)

    library = discover_modules(default_modules_root(), vault_root)  # now includes the new module
    to_add = [manifest.name, *_collect_dependency_closure(manifest.name, config, library)]
    to_add = sorted(set(to_add))
    answers = load_answers(Path(args.answers)) if args.answers else None
    interactive = answers is None and _is_interactive()
    source_cfg = {"repo": repo, **({"pin": pin} if pin else {})}
    new_entries: dict[str, ModuleConfig] = {}
    for mod_id in to_add:
        provided = answers.modules.get(mod_id, {}) if answers else {}
        entry = collect_module_config(
            library[mod_id], provided, interactive=interactive, folder_style=config.folder_style
        )
        if mod_id == manifest.name:
            entry = ModuleConfig(version=entry.version, vars=entry.vars, source=source_cfg)
        new_entries[mod_id] = entry
    code = _enable_and_apply(
        args, vault_root, library, new_entries,
        f"installing external module: {manifest.name} (from {repo})",
    )
    if code != 0:
        shutil.rmtree(vault_root / ".vault" / "modules" / manifest.name, ignore_errors=True)
        print(f"rolled back the staged copy at {EXTERNAL_REL}/{manifest.name}.", file=sys.stderr)
    return code


def cmd_add(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    config = load_config(vault_root)
    if looks_external(args.module):
        return _add_external(args, vault_root, config)
    library = discover_modules(default_modules_root(), vault_root)
    target = args.module
    if target not in library:
        raise ResolveError(
            f"module {target!r} is not in the library (available: {sorted(library)}); "
            "`onyx modules` describes each one, and a git URL or module directory installs externally"
        )
    if target in config.modules:
        print(f"module {target!r} is already enabled; nothing to do.")
        return 0

    to_add = _collect_dependency_closure(target, config, library)
    answers = load_answers(Path(args.answers)) if args.answers else None
    interactive = answers is None and _is_interactive()
    new_entries: dict[str, ModuleConfig] = {}
    for mod_id in sorted(to_add):
        provided = answers.modules.get(mod_id, {}) if answers else {}
        new_entries[mod_id] = collect_module_config(
            library[mod_id], provided, interactive=interactive, folder_style=config.folder_style
        )
    deps = [m for m in to_add if m != target]
    enabling = f"enabling: {target}" + (f" (plus dependencies: {', '.join(sorted(deps))})" if deps else "")
    return _enable_and_apply(args, vault_root, library, new_entries, enabling)


def cmd_update(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    config = load_config(vault_root)
    target = args.module

    if target is None:
        module_targets = list(config.modules)
        update_sources = bool(config.sources)
    elif target in config.modules:
        module_targets, update_sources = [target], False
    elif target in config.sources:
        module_targets, update_sources = [], True
    else:
        raise ResolveError(f"{target!r} is neither an enabled module nor a declared source")

    # Refresh externally-sourced modules first, so the library reflects upstream (§12).
    pin_changes: dict[str, tuple[str | None, str | None]] = {}
    for mod_id in module_targets:
        mod = config.modules[mod_id]
        if mod.source is None:
            continue
        if args.dry_run:
            print(f"external module {mod_id!r}: would refresh from {mod.source['repo']}")
            continue
        try:
            with tempfile.TemporaryDirectory(prefix="onyx-ext-") as tmp:
                fetched, _, new_pin = fetch_external(mod.source["repo"], Path(tmp))
                if fetched.name != mod_id:
                    raise OnyxError(f"{mod.source['repo']} now serves module {fetched.name!r}, not {mod_id!r}")
                install_external(vault_root, fetched)
            old_pin = mod.source.get("pin")
            if new_pin and new_pin != old_pin:
                pin_changes[mod_id] = (old_pin, new_pin)
                print(f"external module {mod_id!r}: refreshed at {new_pin[:12]}")
        except OnyxError as exc:
            print(f"warning: external module {mod_id!r} not refreshed: {exc}", file=sys.stderr)

    library = discover_modules(default_modules_root(), vault_root)

    changes: dict[str, tuple[str, str]] = {}
    for mod_id in module_targets:
        if mod_id not in library:
            raise ResolveError(f"module {mod_id!r} is enabled but missing from the library")
        if config.modules[mod_id].version != library[mod_id].version:
            changes[mod_id] = (config.modules[mod_id].version, library[mod_id].version)

    # Intent at the bundled versions; the user's variables are untouched.
    new_config = Config(
        framework_version=config.framework_version,
        runtimes=list(config.runtimes),
        vault_name=config.vault_name,
        folder_style=config.folder_style,
        modules={
            mod_id: ModuleConfig(
                version=library[mod_id].version if mod_id in changes else mod.version,
                vars=dict(mod.vars),
            )
            for mod_id, mod in config.modules.items()
        },
        sources={k: dict(v) for k, v in config.sources.items()},
    )
    manifests = resolve_modules(new_config, library)
    desired = build_desired_state(new_config, manifests)
    lock = load_lock(vault_root)
    plan = build_plan(vault_root, desired, lock, enabled_for_planner(new_config))

    if changes:
        print("module updates:")
        for mod_id, (old, new) in sorted(changes.items()):
            print(f"  {mod_id}: {old} -> {new}")
    else:
        print("all enabled modules are at their library versions.")
    print(render_plan(plan))
    conflicts = [a for a in plan.mutating if a.type == CONFLICT_NEW]
    if conflicts:
        print("update report — new versions land BESIDE your customized files; no overwrites (§8.3):")
        for action in conflicts:
            print(f"  ! {action.path} -> {action.write_path}")
    stale = [a for a in plan.reports if a.type == STALE]
    if stale:
        print("update report — tracked but no longer shipped; left in place:")
        for action in stale:
            print(f"  * {action.path}")

    if plan.is_empty and not changes and not update_sources:
        print("nothing to update.")
        return 0
    if args.dry_run:
        if update_sources:
            print("sources: the pin would be advanced to upstream HEAD.")
        print("dry run; nothing written.")
        return 0
    if not _confirm("apply this update?", assume_yes=args.yes):
        print("aborted; nothing written.")
        return 1

    result = apply_plan(vault_root, plan, lock)
    code = _print_apply_outcome(result, manifests, newly_installed=set())

    config_text = read_text(config_path(vault_root))
    if changes:
        config_text, _ = bump_module_versions(config_text, changes)
        write_text_atomic(config_path(vault_root), config_text)
        print(f"config: version pin(s) bumped for {', '.join(sorted(changes))}")
    for mod_id, (old_pin, new_pin) in pin_changes.items():
        if old_pin and new_pin:
            config_text = replace_pin(config_text, old_pin, new_pin)
            write_text_atomic(config_path(vault_root), config_text)
            print(f"config: {mod_id} source pin {old_pin[:12]} -> {new_pin[:12]}")
        elif new_pin:
            print(
                f"note: {mod_id} had no recorded pin; add `pin: \"{new_pin}\"` to its source in {CONFIG_REL}",
                file=sys.stderr,
            )

    if update_sources:
        try:
            src = install_obsidian_skills(vault_root, new_config, lock, advance_pin=True)
        except SourceInstallError as exc:
            print(f"warning: source update skipped: {exc}", file=sys.stderr)
            src = None
        if src is not None:
            if src.previous_pin and src.previous_pin != src.pin:
                delta = f"{src.previous_pin[:12]} -> {src.pin[:12]}"
            elif src.previous_pin:
                delta = f"already at {src.pin[:12]}"
            else:
                delta = f"now pinned at {src.pin[:12]}"
            print(f"source {src.name}: {delta} ({len(src.installed)} file(s) refreshed)")
            for path, reason in src.skipped:
                print(f"  - left alone {path}: {reason}", file=sys.stderr)
            if src.previous_pin and src.previous_pin != src.pin:
                config_text = replace_pin(config_text, src.previous_pin, src.pin)
                write_text_atomic(config_path(vault_root), config_text)
            elif not src.previous_pin:
                print(
                    f"note: no pin was recorded before; add `pin: \"{src.pin}\"` under "
                    f"sources.{src.name} in {CONFIG_REL} to pin it",
                    file=sys.stderr,
                )
    return code


def cmd_remove(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    config = load_config(vault_root)
    mod_id = args.module
    if mod_id == "core":
        raise ResolveError("'core' is required by everything and cannot be removed (§5.1)")
    if mod_id not in config.modules:
        print(f"module {mod_id!r} is not enabled; nothing to do.")
        return 0
    library = discover_modules(default_modules_root(), vault_root)
    dependents = sorted(
        m for m in config.modules
        if m != mod_id and m in library and mod_id in library[m].depends
    )
    if dependents:
        raise ResolveError(
            f"cannot remove {mod_id!r}: {', '.join(dependents)} depend(s) on it; remove those first"
        )

    lock = load_lock(vault_root)
    entries = [e for e in lock.sorted_entries() if e.module == mod_id]
    to_delete, to_leave = [], []
    for entry in entries:
        native = to_native(vault_root, entry.path)
        if entry.kind == KIND_SEEDED:
            to_leave.append((entry, "seeded; yours from the day it was created"))
        elif not native.is_file():
            to_leave.append((entry, "already gone from disk"))
        elif sha256_file(native) == entry.sha256:
            to_delete.append(entry)
        else:
            to_leave.append((entry, "you modified it; it stays, untracked from here on"))

    manifests = resolve_modules(config, library)
    desired = build_desired_state(config, manifests)
    module_dirs = {d.path for d in desired.dirs if d.module == mod_id}

    print(f"removing module {mod_id!r} (§8.3: only unmodified framework-owned files are deleted):")
    if to_delete:
        print("  will delete:")
        for entry in to_delete:
            print(f"    - {entry.path}")
    if to_leave:
        print("  left behind:")
        for entry, reason in to_leave:
            print(f"    = {entry.path}  [{reason}]")
    print(f"  ~ {CONFIG_REL} (dropping the {mod_id!r} entry)")
    print("  folders the module created are pruned only if empty; anything holding your files stays.")
    if args.dry_run:
        print("dry run; nothing written.")
        return 0
    if not _confirm(f"remove {mod_id!r}?", assume_yes=args.yes):
        print("aborted; nothing written.")
        return 1

    deleted, raced = 0, []
    prune_candidates: set[str] = set(module_dirs)
    for entry in to_delete:
        native = to_native(vault_root, entry.path)
        # Re-verify at the moment of truth: a byte changed since review keeps the file.
        if native.is_file() and sha256_file(native) == entry.sha256:
            native.unlink()
            deleted += 1
            parent = entry.path.rsplit("/", 1)[0] if "/" in entry.path else ""
            if parent:
                prune_candidates.add(parent)
        else:
            raced.append(entry.path)
            to_leave.append((entry, "changed since review; left alone"))
    for entry in entries:
        lock.entries.pop(entry.path, None)  # the module is gone; every claim is relinquished
    save_lock(vault_root, lock)

    pruned = 0
    for dir_path in sorted(prune_candidates, key=lambda p: -p.count("/")):
        native = to_native(vault_root, dir_path)
        try:
            while native != vault_root and native.is_dir() and not any(native.iterdir()):
                native.rmdir()
                pruned += 1
                native = native.parent
        except OSError:
            continue  # this branch holds something; move on to the next candidate

    config_text, new_config = remove_module_entry(read_text(config_path(vault_root)), mod_id)
    write_text_atomic(config_path(vault_root), config_text)
    if config.modules[mod_id].source is not None:
        shutil.rmtree(vault_root / ".vault" / "modules" / mod_id, ignore_errors=True)
        print(f"  - removed the external copy at {EXTERNAL_REL}/{mod_id}")
    print(
        f"removed {mod_id!r}: {deleted} file(s) deleted, {len(to_leave)} left behind, "
        f"{pruned} empty folder(s) pruned."
    )

    # The module set changed, so core's generated content (Start-Here.md) is stale.
    # Converge it here only if that is ALL that is pending; anything else stays the
    # user's explicit `apply`.
    new_manifests = resolve_modules(new_config, library)
    new_desired = build_desired_state(new_config, new_manifests)
    follow_up = build_plan(vault_root, new_desired, lock, enabled_for_planner(new_config))
    if follow_up.mutating and all(
        a.type == "update" and a.module == "core" for a in follow_up.mutating
    ):
        apply_plan(vault_root, follow_up, lock)
        print("refreshed generated content for the new module set.")
    elif follow_up.mutating:
        print("the module set changed; review the rest with `onyx plan`, then `onyx apply`.")
    if raced:
        print("changed since review, left alone: " + ", ".join(raced), file=sys.stderr)
        return 1
    return 0


def cmd_module_new(args: argparse.Namespace) -> int:
    from .manifests import load_manifest
    from .model import MODULE_ID_RE

    mod_id = args.id
    if not MODULE_ID_RE.match(mod_id):
        raise ResolveError(f"module id {mod_id!r} must be kebab-case (e.g. my-domain)")
    target = Path(args.dir) / mod_id
    if target.exists():
        raise VaultStateError(f"{target} already exists; pick another id or directory")
    title = "-".join(part.capitalize() for part in mod_id.split("-"))

    manifest_text = f'''name: {mod_id}
version: 0.1.0
summary: >
  One paragraph on what this module gives a vault. Shown in the interview and
  in `onyx modules`; make it earn its place.
depends: [core]
variables:
  # Every folder the module roots should be a variable with a default (P4).
  - key: root
    prompt: "Folder name for this domain"
    default: "{title}"
provides:
  folders:
    - "{{{{root}}}}"
  templates:
    - "Templates/{title}/Example Note.md"
  # bases:   - "{{{{root}}}}/Overview.base"      # .base views over typed frontmatter (P5)
  # skills:  - my-skill                           # skills/<id>/SKILL.md
  # agents:  - my-agent                           # agents/<id>.yaml (see §7.3)
# seeds:     - "{{{{root}}}}/Start.md"            # written once, user-owned forever (§8.2)
post_install: |
  One short paragraph for the human: what to fill in or read first.
'''
    example_note = f'''---
type: {mod_id}-note
created: <% tp.date.now("YYYY-MM-DD") %>
status: active
tags:
  - {mod_id}
date: <% tp.date.now("YYYY-MM-DD") %>
---

# <% tp.file.title %>

## Notes

-
'''
    readme = f'''# {mod_id}

What this module provides and the conventions it carries. Document your note
types (their `type` values, status lifecycles, extra frontmatter fields) in a
table here — agents and humans both read this.

Authoring rules live in the Onyx repository at `core/conventions/authoring.md`:
assets mirror install paths verbatim (placeholder segments included), prose is
never hard-wrapped, `{{{{variable}}}}` belongs to the engine and `<% tp.* %>` to
Templater, and modules contain no executable code.
'''
    write_text_atomic(target / "module.yaml", manifest_text)
    write_text_atomic(target / "assets" / "Templates" / title / "Example Note.md", example_note)
    write_text_atomic(target / "docs" / "README.md", readme)

    manifest = load_manifest(target)  # the §9.1 guarantee: valid out of the box
    print(f"scaffolded module {manifest.name!r} v{manifest.version} at {target} (validates cleanly).")
    print("next: fill the summary, real assets, and docs; test-install with"
          f" `onyx add {target}` in a scratch vault; distribute by pushing this folder"
          " as a git repository (module.yaml at the root).")
    return 0


def cmd_modules(args: argparse.Namespace) -> int:
    library = discover_modules(default_modules_root())
    for name in sorted(library):
        manifest = library[name]
        print(f"{manifest.name} {manifest.version}")
        print(f"  {' '.join(manifest.summary.split())}")
        if manifest.depends:
            print(f"  depends: {', '.join(manifest.depends)}")
        for var in manifest.variables:
            options = f" (options: {', '.join(var.options)})" if var.options else ""
            default = f" [default: {var.default}]" if var.default is not None else " (required)"
            print(f"  var {var.key}: {var.prompt}{options}{default}")
        if manifest.skills:
            print(f"  skills: {', '.join(s.id for s in manifest.skills)}")
    return 0


# ----------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="onyx",
        description="Composable, agent-optional framework for Obsidian vaults.",
    )
    parser.add_argument("--version", action="version", version=f"onyx {ENGINE_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="interview -> config -> plan -> confirm -> apply on a new/empty folder")
    p.add_argument("target", help="folder to create the vault in (created if missing)")
    p.add_argument("--answers", help="answers file or profile YAML for a non-interactive run")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument("--dry-run", action="store_true", help="show the plan and write nothing")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("plan", help="show the diff between declared intent and the vault (read-only)")
    p.add_argument("--vault", default=".", help="vault root (default: current directory)")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("apply", help="execute the plan; every write is recorded in the lockfile")
    p.add_argument("--vault", default=".", help="vault root (default: current directory)")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument("--dry-run", action="store_true", help="show the plan and write nothing")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("doctor", help="validate vault state against intent (read-only)")
    p.add_argument("--vault", default=".", help="vault root (default: current directory)")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("modules", help="list available modules, their variables, and defaults (read-only)")
    p.set_defaults(func=cmd_modules)

    p = sub.add_parser("add", help="enable a module: config insert, module questions, plan, apply")
    p.add_argument("module", help="module id to enable (dependencies are added automatically)")
    p.add_argument("--vault", default=".", help="vault root (default: current directory)")
    p.add_argument("--answers", help="answers file supplying the module's variable values")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument("--dry-run", action="store_true", help="show the plan and write nothing")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser(
        "adopt",
        help="bring an existing vault under management — additive only, mandatory plan review, no fast path",
    )
    p.add_argument("target", help="the existing vault directory")
    p.add_argument("--answers", help="answers file or profile YAML; scan proposals fill whatever it leaves unset")
    p.add_argument("--dry-run", action="store_true", help="scan, map, and show the plan; write nothing")
    p.add_argument(
        "--accept",
        metavar="TOKEN",
        help="apply the exact plan a previous run displayed (the token it printed); rejected if anything changed",
    )
    p.set_defaults(func=cmd_adopt)

    p = sub.add_parser("update", help="upgrade module assets and pinned sources — §8.3: zero overwrites of modified files")
    p.add_argument("module", nargs="?", help="one module or source to update (default: everything)")
    p.add_argument("--vault", default=".", help="vault root (default: current directory)")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument("--dry-run", action="store_true", help="show the update plan and write nothing")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("remove", help="disable a module — deletes only unmodified framework-owned files (§8.3)")
    p.add_argument("module", help="module id to remove")
    p.add_argument("--vault", default=".", help="vault root (default: current directory)")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument("--dry-run", action="store_true", help="show what would happen and write nothing")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("module", help="module authoring tools")
    module_sub = p.add_subparsers(dest="module_command", required=True)
    p_new = module_sub.add_parser("new", help="scaffold a module skeleton that validates out of the box")
    p_new.add_argument("id", help="module id, kebab-case")
    p_new.add_argument("--dir", default=".", help="directory to scaffold into (default: current directory)")
    p_new.set_defaults(func=cmd_module_new)

    return parser


def main(argv: list[str] | None = None) -> int:
    _reconfigure_streams()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except OnyxError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted; nothing partial was left unrecorded (the ledger is saved per write).", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

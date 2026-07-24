"""The `onyxian` command-line interface (KICKSTART.md §9.1).

Mental model: config declares intent, lock records state, `plan` is the diff,
`apply` reconciles. Everything else is ergonomics. Commands that arrive in
later milestones exist as honest stubs that say which milestone, instead of
pretending not to exist.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from . import ENGINE_VERSION
from .adopt import (
    acceptance_token,
    assert_additive,
    claim_existing_seeds,
    scan_vault,
)
from .applier import ApplyResult, apply_plan
from .checkpoints import (
    CheckpointUnavailable,
    diff_since_last,
    has_checkpoints,
    list_snapshots,
    snapshot,
)
from .config_edit import (
    bump_module_versions,
    insert_module_entries,
    remove_module_entry,
    replace_module_pin,
    replace_source_pin,
)
from .configio import (
    CONFIG_REL,
    config_path,
    is_managed_vault,
    load_config,
    render_config_text,
    unmanaged_vault_message,
)
from .diff import (
    NEW_SUFFIX,
    ConflictPair,
    Leftover,
    clean_leftover,
    find_conflicts,
    keep_mine,
    match_pair,
    normalize_path_argument,
    render_conflict_list,
    render_pair_diff,
    take_new,
)
from .doctor import exit_code as doctor_exit_code
from .doctor import render_findings, run_doctor
from .errors import AnswersError, ConfigError, OnyxianError, ResolveError, VaultStateError
from .external import (
    EXTERNAL_REL,
    assert_module_trust,
    changed_instruction_files,
    fetch_external,
    install_external,
    looks_external,
    record_module_trust,
    trust_warning,
)
from .fsio import read_text, sha256_bytes, sha256_file, write_text_atomic
from .intent import DesiredState, build_desired_state, resolve_today
from .interview import (
    _is_interactive,
    collect_module_config,
    load_answers,
    resolve_answers_spec,
    resolved_sources,
    run_interview,
)
from .lockio import load_lock, save_lock
from .model import KIND_SEEDED, Config, Lock, LockEntry, Manifest, ModuleConfig
from .mutex import vault_mutex
from .paths import to_native
from .planner import CONFLICT_NEW, STALE, UPDATE, Plan, build_plan, render_plan
from .project_new import scaffold_project, validate_project
from .repo import default_modules_root, discover_modules
from .resolve import resolve_modules
from .scopecheck import ALLOW, evaluate
from .sources import (
    SourceInstallError,
    SourceTrustInfo,
    enabled_for_planner,
    install_obsidian_skills,
    source_trust_warning,
)

# Things allowed to pre-exist in an `init` target: version control, Obsidian's
# own settings folder, and OS junk files. Anything else means the folder has a
# life already — that is `adopt`'s territory (M1), never `init`'s.
_ALLOWED_PREEXISTING = {".git", ".obsidian", ".DS_Store", "Thumbs.db", "desktop.ini"}


def _reconfigure_streams() -> None:
    # Best-effort: let the console tolerate characters it can't encode. Only real
    # TextIOWrapper streams expose reconfigure(); a pytest capture or a pipe wrapper
    # has no such method and is left as-is (equivalent to the old "ignore
    # AttributeError"). A ValueError (e.g. a detached buffer) is swallowed too.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            with contextlib.suppress(ValueError):
                stream.reconfigure(errors="replace")


def _confirm(question: str, *, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not _is_interactive():
        raise AnswersError("confirmation needed but stdin is not interactive; pass --yes")
    raw = input(f"{question} [y/N] ").strip().lower()
    return raw in ("y", "yes")


def _confirm_trust(question: str, *, trusted: bool) -> bool:
    """Instruction content is a consent separate from the plan gate: --yes never
    covers it, and scripted runs fail closed until --trust is passed (#61)."""
    if trusted:
        return True
    if not _is_interactive():
        raise AnswersError(
            "new or changed agent/skill instructions need their own consent; "
            "review the trust warning and pass --trust (--yes covers only the plan)"
        )
    return _confirm(question, assume_yes=False)


def _vault_root(args: argparse.Namespace) -> Path:
    root = Path(args.vault)
    if not is_managed_vault(root):
        raise ConfigError(
            unmanaged_vault_message(root, "run `onyxian init <folder>` to create one")
        )
    return root


def _load_context(vault_root: Path) -> tuple[Config, list[Manifest], Plan, Lock]:
    config = load_config(vault_root)
    library = discover_modules(default_modules_root(), vault_root)
    manifests = resolve_modules(config, library)
    desired = build_desired_state(config, manifests)
    lock = load_lock(vault_root)
    assert_module_trust(vault_root, config, lock)  # #48: don't plan from a tampered copy
    plan = build_plan(vault_root, desired, lock, enabled_for_planner(config))
    return config, manifests, plan, lock


def _source_install_gate(trusted: bool) -> Callable[[SourceTrustInfo], bool]:
    """A trust gate for a source install: show the banner, then take the instruction
    consent separately from the plan (#48/#61). Non-interactive without --trust fails
    closed, but for an optional source that means 'skip it', so the caller degrades.

    The prompt may run under the vault mutex (source installs happen inside init/adopt/
    update): safe, because the mutex has no holder-side timeout and these commands are
    single-writer — a second process just fails fast. ponytail: pre-fetch to gate before
    the mutex if that ordering ever matters.
    """

    def gate(info: SourceTrustInfo) -> bool:
        print(source_trust_warning(info))
        try:
            return _confirm_trust(
                "trust and install these source skill instructions?", trusted=trusted
            )
        except AnswersError as exc:
            print(f"warning: {exc}", file=sys.stderr)
            return False

    return gate


def _install_sources_step(
    target: Path, config: Config, lock: Lock, library: dict[str, Manifest], *, trusted: bool
) -> None:
    """Post-apply source install (§9.2 'runtime install'); failures degrade to warnings (P2)."""
    if not config.sources:
        return
    try:
        result = install_obsidian_skills(target, config, lock, gate=_source_install_gate(trusted))
    except SourceInstallError as exc:
        print(f"warning: obsidian-skills install skipped: {exc}", file=sys.stderr)
        print(
            "         the vault works fully without it; `onyxian update` "
            "will install declared sources later.",
            file=sys.stderr,
        )
        return
    if result is None:
        return
    if result.declined:
        print(
            f"source {result.name!r} not installed: its skill instructions were not trusted. "
            "The vault works without them; `onyxian update --trust` installs them after review.",
            file=sys.stderr,
        )
        return
    print(
        f"installed source {result.name} at pin {result.pin[:12]} ({len(result.installed)} files)."
    )
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


def _print_apply_outcome(
    result: ApplyResult, manifests: list[Manifest], newly_installed: set[str]
) -> int:
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


# ------------------------------------------------------- plan / apply invariants
#
# The commands below are thin: build a plan, review it, gate, write. A contributor
# must preserve these invariants (CONTRIBUTING.md points here):
#
# 1. What you print is what you apply. The plan is built once, rendered, and that
#    same object goes to apply_plan; never re-plan between review and apply. Adopt
#    pins this down with acceptance_token (a fingerprint over the reviewed config
#    text, plan actions, and seed claims); everywhere else it is convention. The one
#    sanctioned exception is cmd_remove's follow-up plan, which auto-applies only
#    when every mutating action is a core UPDATE.
# 2. --dry-run returns before any write of any kind — config edits, lock saves,
#    external installs. _review_gate returns 0 on the dry-run branch, above the writes.
# 3. config.yaml is the user's file. After init/adopt seed it, every edit goes
#    through a config_edit function that re-parses before returning; the CLI writes
#    that text with write_text_atomic and never regenerates a user-edited config with
#    render_config_text (the only post-seed regeneration is in _install_sources_step,
#    immediately after the engine itself generated the file).
# 4. Write ordering: add writes config *before* apply (declared intent survives a
#    crash; re-running plan/apply converges); update bumps versions and pins only
#    *after* apply_plan has run — the config never gets ahead of an apply that never
#    happened.
# 5. Exit codes: 0 for clean runs, dry runs, and degraded-but-warned source installs;
#    1 for user abort, errors, skipped re-verifies, and remove's raced files; 130 for
#    interrupt. _print_apply_outcome is the only translator from an apply result to
#    text and code.
# 6. Any lock.put done in cli.py itself is followed by save_lock before the next
#    fallible operation.
# 7. The vault mutex brackets every ledger save, and the Lock object saved inside
#    it is (re)loaded inside it too — never a snapshot taken before the gate. The
#    confirm prompt can hang open while another onyxian process completes a whole
#    command; saving a lock loaded before the gate would erase that process's rows
#    wholesale (#47). Pre-gate loads exist only to build the plan and the review.
#    (init/adopt are exempt: they start from an empty ledger a fresh Lock() models
#    exactly, and both refuse to run on an already-managed vault.)


def _review_gate(
    review: Sequence[str],
    *,
    dry_run: bool,
    assume_yes: bool,
    question: str,
    dry_run_extra: Sequence[str] = (),
) -> int | None:
    """Print the review, then gate: 0 = dry-run exit, 1 = user abort, None = proceed."""
    for line in review:
        print(line)
    if dry_run:
        for line in dry_run_extra:
            print(line)
        print("dry run; nothing written.")
        return 0
    if not _confirm(question, assume_yes=assume_yes):
        print("aborted; nothing written.")
        return 1
    return None


def _apply_and_report(
    vault_root: Path,
    plan: Plan,
    lock: Lock,
    manifests: list[Manifest],
    *,
    newly_installed: set[str] | None = None,
) -> int:
    """Snapshot the lock delta (unless the caller supplies it), apply, and translate."""
    if newly_installed is None:
        previously_installed = {entry.module for entry in lock.entries.values()}
        newly_installed = {m.name for m in manifests} - previously_installed
    result = apply_plan(vault_root, plan, lock)
    return _print_apply_outcome(result, manifests, newly_installed)


def _seed_config_and_apply(
    target: Path,
    config_text: str,
    plan: Plan,
    lock: Lock,
    manifests: list[Manifest],
    config: Config,
    library: dict[str, Manifest],
    *,
    trusted: bool,
) -> int:
    """The shared init/adopt tail: seed config.yaml, ledger it, apply, install sources.

    The caller renders (init) or has already reviewed (adopt) ``config_text``.
    """
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
    code = _apply_and_report(
        target, plan, lock, manifests, newly_installed={m.name for m in manifests}
    )
    _install_sources_step(target, config, lock, library, trusted=trusted)
    return code


# ----------------------------------------------------------------- commands


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.target)
    if target.exists():
        if not target.is_dir():
            raise VaultStateError(f"init target {target} exists and is not a directory")
        if (target / ".vault").exists():
            raise VaultStateError(
                f"{target} is already an Onyxian vault; edit {CONFIG_REL} "
                "and run `onyxian plan` / `onyxian apply`"
            )
        offenders = sorted(e.name for e in target.iterdir() if e.name not in _ALLOWED_PREEXISTING)
        if offenders:
            shown = ", ".join(offenders[:5]) + (", ..." if len(offenders) > 5 else "")
            raise VaultStateError(
                f"init requires a new or empty folder, but {target} contains: {shown}. "
                "Bringing an existing vault under management is `adopt`'s job."
            )

    answers = load_answers(resolve_answers_spec(args.answers)) if args.answers else None
    library = discover_modules(default_modules_root())
    config = run_interview(library, answers)
    manifests = resolve_modules(config, library)
    desired = build_desired_state(config, manifests)
    lock = Lock()
    plan = build_plan(target, desired, lock, enabled_for_planner(config))

    review = [
        f"vault: {config.vault_name!r} at {target}",
        f"folder style: {config.folder_style}; modules: {', '.join(config.modules)}",
        render_plan(plan),
        f"  + {CONFIG_REL} (seeded; yours to edit)",
        "  + .vault/lock.json (the engine's ledger)",
    ]
    gate = _review_gate(
        review, dry_run=args.dry_run, assume_yes=args.yes, question="create this vault?"
    )
    if gate is not None:
        return gate

    with vault_mutex(target):
        target.mkdir(parents=True, exist_ok=True)
        code = _seed_config_and_apply(
            target,
            render_config_text(config),
            plan,
            lock,
            manifests,
            config,
            library,
            trusted=args.trust,
        )
        print(f"\nvault ready. open it in Obsidian, then try: onyxian doctor --vault {target}")
    return code


def cmd_plan(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    _, _, plan, _ = _load_context(vault_root)
    print(render_plan(plan))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    _config, manifests, plan, lock = _load_context(vault_root)
    print(render_plan(plan))
    if plan.is_empty:
        return 0
    gate = _review_gate(
        (), dry_run=args.dry_run, assume_yes=args.yes, question="apply these changes?"
    )
    if gate is not None:
        return gate
    with vault_mutex(vault_root):
        lock = load_lock(vault_root)  # invariant 7: never save the pre-gate snapshot
        return _apply_and_report(vault_root, plan, lock, manifests)


def cmd_doctor(args: argparse.Namespace) -> int:
    vault_root = Path(args.vault)
    findings = run_doctor(vault_root, default_modules_root())
    print(render_findings(findings))
    return doctor_exit_code(findings)


def _load_agent_scopes(vault_root: Path, agent: str) -> list[str] | None:
    """The agent's resolved write globs from `.claude/onyxian-scopes.json`, or None
    when the file or the agent is absent (in which case the hook must not block)."""
    try:
        data = json.loads((vault_root / ".claude" / "onyxian-scopes.json").read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entry = data.get(agent) if isinstance(data, dict) else None
    write = entry.get("write") if isinstance(entry, dict) else None
    return [str(g) for g in write] if isinstance(write, list) else None


def _resolve_daily_note(vault_root: Path) -> str | None:
    """Today's daily-note path from `.obsidian/daily-notes.json`, so `daily:append`
    becomes a provable target. None when daily notes aren't configured."""
    try:
        cfg = json.loads((vault_root / ".obsidian" / "daily-notes.json").read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    fmt = str(cfg.get("format", ""))
    if not fmt:
        return None
    year, month, day = resolve_today().split("-")
    stamp = fmt.replace("YYYY", year).replace("MM", month).replace("DD", day)
    folder = str(cfg.get("folder", "")).rstrip("/")
    return f"{folder}/{stamp}.md" if folder else f"{stamp}.md"


def cmd_hook_scope_check(args: argparse.Namespace) -> int:
    """PreToolUse gate (#11 phase 3): decide a Bash command against an agent's write
    scope. Emits `permissionDecision` deny/ask; stays silent to let a command through.
    It only ever narrows permissions — an in-scope, read-only, or non-obsidian command
    is passed to Claude Code's normal flow, never auto-approved."""
    vault_root = Path(args.vault)
    payload = sys.stdin.read()
    try:
        data = json.loads(payload) if payload.strip() else {}
    except json.JSONDecodeError:
        return 0
    command = (data.get("tool_input") or {}).get("command", "") if isinstance(data, dict) else ""
    if data.get("tool_name") not in (None, "Bash") or not command:
        return 0
    write_globs = _load_agent_scopes(vault_root, args.agent)
    if write_globs is None:
        return 0  # scopes unknown; never block on a missing/foreign agent
    decision = evaluate(command, write_globs, daily_note=_resolve_daily_note(vault_root))
    if decision.verdict == ALLOW:
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision.verdict,
                    "permissionDecisionReason": decision.reason,
                }
            }
        )
    )
    return 0


def _files(n: int) -> str:
    return f"{n} file{'' if n == 1 else 's'}"


def cmd_checkpoint(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    try:
        if args.action == "list":
            infos = list_snapshots(vault_root)
            if not infos:
                print("no checkpoints yet; run `onyxian checkpoint` to create a baseline.")
            for info in infos:
                tail = "(baseline)" if info.baseline else f"{_files(info.files_changed)} changed"
                print(f"{info.checkpoint_id}  {info.when}   {tail}")
        elif args.action == "diff":
            if not has_checkpoints(vault_root):
                print("no checkpoints yet; run `onyxian checkpoint` to create a baseline.")
            else:
                changes = diff_since_last(vault_root)
                if not changes:
                    print("no changes since the last checkpoint.")
                for letter, path in changes:
                    print(f"{letter}  {path}")
        else:
            result = snapshot(vault_root)
            if not args.quiet:
                if result.created:
                    tail = "(baseline)" if result.baseline else "since last"
                    print(
                        f"checkpoint {result.checkpoint_id} ({result.when}) — "
                        f"{_files(result.files_changed)} changed {tail}"
                    )
                else:
                    print("no changes since the last checkpoint.")
    except CheckpointUnavailable:
        # The guard is a net, not a dependency: a missing git must never break a
        # session or fail a command (P2). One honest line, then get out of the way.
        print(
            "warning: git not found; skipping checkpoint (the vault is unaffected).",
            file=sys.stderr,
        )
    return 0


def cmd_adopt(args: argparse.Namespace) -> int:
    target = Path(args.target)
    if not target.is_dir():
        raise VaultStateError(f"adopt target {target} is not an existing directory")
    if (target / ".vault").exists():
        raise VaultStateError(
            f"{target} is already an Onyxian vault; edit {CONFIG_REL} "
            "and run `onyxian plan` / `onyxian apply`"
        )

    library = discover_modules(default_modules_root())
    answers = load_answers(resolve_answers_spec(args.answers)) if args.answers else None
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
            raise ResolveError(
                f"module {mod_id!r} is not in the module library (available: {sorted(library)})"
            )
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
        print("checklist — decide these yourself; the engine will not:")
        for note in scan.ambiguities:
            print(f"  ? {note}")
    print(
        "guarantee: adopt is additive only; nothing existing is moved, "
        "renamed, deleted, or overwritten."
    )

    if args.dry_run:
        print("dry run; nothing written.")
        print(f"to apply exactly this plan, re-run with: --accept {token}")
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
        typed = input('mandatory review: type "adopt" to apply exactly this plan: ').strip()
        if typed != "adopt":
            print("aborted; nothing written.")
            return 1
    else:
        print(f"\nreview complete. to apply exactly this plan, re-run with: --accept {token}")
        return 0

    with vault_mutex(target):
        code = _seed_config_and_apply(
            target, config_text, plan, lock, manifests, config, library, trusted=args.trust
        )
        print(
            "\nvault adopted; nothing pre-existing was touched. "
            f"next: onyxian doctor --vault {target}"
        )
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
    *,
    record_trust_ids: Sequence[str] = (),
) -> int:
    """Shared tail of `add` (bundled and external): config insert, plan, confirm, apply.

    ``record_trust_ids`` names external modules whose freshly-installed copy under
    ``.vault/modules/<id>/`` should be baselined for integrity now that the user trusted
    it (#48); empty for bundled adds.
    """
    old_text = read_text(config_path(vault_root))
    new_text, new_config = insert_module_entries(old_text, new_entries)
    manifests = resolve_modules(new_config, library)
    desired = build_desired_state(new_config, manifests)
    lock = load_lock(vault_root)
    plan = build_plan(vault_root, desired, lock, enabled_for_planner(new_config))

    review = [
        enabling_line,
        render_plan(plan),
        f"  ~ {CONFIG_REL} (adding: {', '.join(sorted(new_entries))})",
    ]
    gate = _review_gate(
        review, dry_run=args.dry_run, assume_yes=args.yes, question="enable and apply?"
    )
    if gate is not None:
        return gate

    with vault_mutex(vault_root):
        write_text_atomic(config_path(vault_root), new_text)
        lock = load_lock(vault_root)  # invariant 7: never save the pre-gate snapshot
        for mod_id in record_trust_ids:
            record_module_trust(vault_root, lock, mod_id)
        if record_trust_ids:
            save_lock(vault_root, lock)  # persist the baseline even if apply writes nothing
        return _apply_and_report(vault_root, plan, lock, manifests)


def _add_external(args: argparse.Namespace, vault_root: Path, config: Config) -> int:
    spec = args.module
    with tempfile.TemporaryDirectory(prefix="onyxian-ext-") as tmp:
        manifest, repo, pin = fetch_external(spec, Path(tmp))
        library = discover_modules(default_modules_root(), vault_root)
        already = config.modules.get(manifest.name)
        if already is not None and already.source is not None:
            print(
                f"module {manifest.name!r} is already installed; "
                f"`onyxian update {manifest.name}` refreshes it."
            )
            return 0
        if manifest.name in library or already is not None:
            raise ResolveError(
                f"module id {manifest.name!r} already exists in the library; "
                "external modules cannot shadow it"
            )
        for dep in manifest.depends:
            if dep not in library and dep not in config.modules:
                raise ResolveError(
                    f"external module {manifest.name!r} depends on {dep!r}, which is not available"
                )

        print(trust_warning(manifest, repo, pin))
        if args.dry_run:
            # Dry run stages nothing and records no trust decision (invariant 2:
            # no write of any kind). Plan against the scratch checkout — it is the
            # byte-identical tree install_external would copy to .vault/modules/.
            library[manifest.name] = manifest
        else:
            if not _confirm_trust("trust and install this module?", trusted=args.trust):
                print("aborted; nothing installed.")
                return 1
            install_external(vault_root, manifest)
            # Re-discover so planning sees the staged copy, not the scratch one.
            library = discover_modules(default_modules_root(), vault_root)

        to_add = [manifest.name, *_collect_dependency_closure(manifest.name, config, library)]
        to_add = sorted(set(to_add))
        answers = load_answers(resolve_answers_spec(args.answers)) if args.answers else None
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
            args,
            vault_root,
            library,
            new_entries,
            f"installing external module: {manifest.name} (from {repo})",
            record_trust_ids=[manifest.name],
        )
    if code != 0:
        # Once the config enables the module, the library copy must stay: deleting
        # it would break every subsequent resolve. Applied files are ledgered, so
        # a plain re-run of `apply` converges.
        if manifest.name in load_config(vault_root).modules:
            print(
                f"apply did not finish; {manifest.name!r} stays installed and enabled — "
                "re-run `onyxian apply` to converge.",
                file=sys.stderr,
            )
        else:
            shutil.rmtree(vault_root / ".vault" / "modules" / manifest.name, ignore_errors=True)
            print(
                f"rolled back the staged copy at {EXTERNAL_REL}/{manifest.name}.", file=sys.stderr
            )
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
            "`onyxian modules` describes each one, and a git URL or module directory "
            "installs externally"
        )
    if target in config.modules:
        print(f"module {target!r} is already enabled; nothing to do.")
        return 0

    to_add = _collect_dependency_closure(target, config, library)
    answers = load_answers(resolve_answers_spec(args.answers)) if args.answers else None
    interactive = answers is None and _is_interactive()
    new_entries: dict[str, ModuleConfig] = {}
    for mod_id in sorted(to_add):
        provided = answers.modules.get(mod_id, {}) if answers else {}
        new_entries[mod_id] = collect_module_config(
            library[mod_id], provided, interactive=interactive, folder_style=config.folder_style
        )
    deps = [m for m in to_add if m != target]
    enabling = f"enabling: {target}" + (
        f" (plus dependencies: {', '.join(sorted(deps))})" if deps else ""
    )
    return _enable_and_apply(args, vault_root, library, new_entries, enabling)


def cmd_update(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    config = load_config(vault_root)
    # #48: refuse before we use any installed copy as the re-gate baseline — a tampered
    # copy would otherwise define what "changed" means for changed_instruction_files.
    assert_module_trust(vault_root, config, load_lock(vault_root))
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

    # Fetch externally-sourced modules first, so the plan reflects upstream (§12).
    # The fetched content stays staged until the user confirms; declining leaves
    # both the vault and the installed library copy untouched.
    pin_changes: dict[str, tuple[str | None, str | None]] = {}
    staged: list[Manifest] = []
    trust_blocks: list[str] = []
    scratch = tempfile.TemporaryDirectory(prefix="onyxian-ext-")
    for mod_id in module_targets:
        mod = config.modules[mod_id]
        if mod.source is None:
            continue
        # Fetched on --dry-run too (into scratch only): the dry run must show the
        # same plan and trust review the real update would (#32).
        try:
            fetched, _, new_pin = fetch_external(mod.source["repo"], Path(scratch.name) / mod_id)
            if fetched.name != mod_id:
                raise OnyxianError(
                    f"{mod.source['repo']} now serves module {fetched.name!r}, not {mod_id!r}"
                )
            staged.append(fetched)
            old_pin = mod.source.get("pin")
            if new_pin and new_pin != old_pin:
                pin_changes[mod_id] = (old_pin, new_pin)
                print(f"external module {mod_id!r}: fetched {new_pin[:12]}")
            changed = changed_instruction_files(
                vault_root / ".vault" / "modules" / mod_id, Path(fetched.directory)
            )
            if changed:
                trust_blocks.append(
                    trust_warning(fetched, mod.source["repo"], new_pin)
                    + "\n  changed instruction file(s) since the reviewed commit: "
                    + ", ".join(changed)
                    + f"\n  the reviewed copy stays at {EXTERNAL_REL}/{mod_id}/ until you confirm."
                )
        except OnyxianError as exc:
            print(f"warning: external module {mod_id!r} not refreshed: {exc}", file=sys.stderr)

    library = discover_modules(default_modules_root(), vault_root)
    library.update({m.name: m for m in staged})  # plan against the staged (new) content

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
        print("update report — new versions land BESIDE your customized files; no overwrites:")
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
    for block in trust_blocks:
        print(block)
    # Changed instructions get their own gate (#61): --yes below covers the plan
    # only. Dry runs skip it — invariant 2 already guarantees nothing is written.
    if (
        trust_blocks
        and not args.dry_run
        and not _confirm_trust("trust the changed instructions and continue?", trusted=args.trust)
    ):
        print("aborted; nothing written.")
        scratch.cleanup()
        return 1
    dry_run_extra = (
        ["sources: the pin would be advanced to upstream HEAD."] if update_sources else []
    )
    gate = _review_gate(
        (),
        dry_run=args.dry_run,
        assume_yes=args.yes,
        question="apply this update?",
        dry_run_extra=dry_run_extra,
    )
    if gate is not None:
        scratch.cleanup()
        return gate

    for fetched in staged:
        install_external(vault_root, fetched)
    scratch.cleanup()
    with vault_mutex(vault_root):
        lock = load_lock(vault_root)  # invariant 7: never save the pre-gate snapshot
        for fetched in staged:  # #48: re-baseline each freshly reviewed copy
            record_module_trust(vault_root, lock, fetched.name)
        if staged:
            save_lock(vault_root, lock)
        code = _apply_and_report(vault_root, plan, lock, manifests, newly_installed=set())

        # Config edits stay *after* apply (invariant 4) and are collected into one
        # write: config.yaml is touched at most once per run, never partway.
        config_text = read_text(config_path(vault_root))
        edited = False
        if changes:
            config_text, _ = bump_module_versions(config_text, changes)
            edited = True
            print(f"config: version pin(s) bumped for {', '.join(sorted(changes))}")
        for mod_id, (old_pin, new_pin) in pin_changes.items():
            if old_pin and new_pin:
                config_text = replace_module_pin(config_text, mod_id, old_pin, new_pin)
                edited = True
                print(f"config: {mod_id} source pin {old_pin[:12]} -> {new_pin[:12]}")
            elif new_pin:
                print(
                    f"note: {mod_id} had no recorded pin; "
                    f'add `pin: "{new_pin}"` to its source in {CONFIG_REL}',
                    file=sys.stderr,
                )

        if update_sources:
            try:
                src = install_obsidian_skills(
                    vault_root,
                    new_config,
                    lock,
                    advance_pin=True,
                    gate=_source_install_gate(args.trust),
                )
            except SourceInstallError as exc:
                print(f"warning: source update skipped: {exc}", file=sys.stderr)
                src = None
            if src is not None and src.declined:
                # Fail closed like external instruction re-gates (#61), but a source is an
                # optional amplifier (P2): decline just leaves it at the reviewed pin.
                print(
                    f"source {src.name!r} left at its current pin: the changed skill "
                    "instructions were not trusted (re-run `onyxian update` with --trust "
                    "after reviewing).",
                    file=sys.stderr,
                )
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
                    config_text = replace_source_pin(
                        config_text, src.name, src.previous_pin, src.pin
                    )
                    edited = True
                elif not src.previous_pin:
                    print(
                        f'note: no pin was recorded before; add `pin: "{src.pin}"` under '
                        f"sources.{src.name} in {CONFIG_REL} to pin it",
                        file=sys.stderr,
                    )

        if edited:
            write_text_atomic(config_path(vault_root), config_text)
    return code


def _diff_context(
    vault_root: Path,
) -> tuple[DesiredState, Lock, list[ConflictPair], list[Leftover]]:
    """(desired, lock, pairs, leftovers) for `diff` — the planner's inputs, no plan."""
    config = load_config(vault_root)
    library = discover_modules(default_modules_root(), vault_root)
    manifests = resolve_modules(config, library)
    desired = build_desired_state(config, manifests)
    lock = load_lock(vault_root)
    assert_module_trust(vault_root, config, lock)  # #48: --take-new writes module content
    pairs, leftovers = find_conflicts(vault_root, desired, lock)
    return desired, lock, pairs, leftovers


def cmd_diff(args: argparse.Namespace) -> int:
    if args.take_new and args.keep_mine:
        raise OnyxianError("--take-new and --keep-mine are mutually exclusive; pick one")
    if (args.take_new or args.keep_mine) and args.resolve:
        raise OnyxianError(
            "--resolve is the interactive flow; drop it to use --take-new/--keep-mine"
        )
    if (args.take_new or args.keep_mine) and args.path is None:
        raise OnyxianError(
            "--take-new/--keep-mine resolve one pair at a time; name the conflicted path"
        )

    vault_root = _vault_root(args)
    desired, _, pairs, leftovers = _diff_context(vault_root)  # the lock is reloaded before writes
    desired_paths = {f.path for f in desired.files}
    portable = normalize_path_argument(args.path) if args.path is not None else None
    pair = match_pair(pairs, portable) if portable is not None else None

    if args.take_new or args.keep_mine:
        if pair is None:
            print(
                f"no active conflict for {portable}; `onyxian diff` lists the current pairs.",
                file=sys.stderr,
            )
            return 1
        print(render_pair_diff(vault_root, pair))
        wording = (
            f"overwrite {pair.path} with the shipped version"
            if args.take_new
            else f"keep your {pair.path} and decline {pair.shipped_by}'s version"
        )
        gate = _review_gate(
            (),
            dry_run=args.dry_run,
            assume_yes=args.yes,
            question=f"{wording}?",
            dry_run_extra=[f"would {wording}."],
        )
        if gate is not None:
            return gate
        with vault_mutex(vault_root):
            lock = load_lock(vault_root)  # invariant 7: never save the pre-gate snapshot
            ok, message = (take_new if args.take_new else keep_mine)(
                vault_root, pair, lock, desired_paths
            )
        print(f"  = {message}" if ok else f"  x {pair.path}: {message}")
        return 0 if ok else 1

    if args.resolve:
        return _resolve_interactively(
            vault_root, pairs, leftovers, portable, desired_paths, dry_run=args.dry_run
        )

    if portable is None:
        print(render_conflict_list(pairs, leftovers))
        return 1 if pairs or leftovers else 0

    if pair is None:
        leftover_names = {portable, portable + NEW_SUFFIX}
        matched = next((lo.entry.path for lo in leftovers if lo.entry.path in leftover_names), None)
        if matched is not None:
            print(
                f"{matched[: -len(NEW_SUFFIX)]} is already resolved; a leftover ledger row remains"
                f" for {matched} — clean it up with `onyxian diff --resolve`."
            )
            return 1
        print(f"no active conflict for {portable}; `onyxian diff` lists the current pairs.")
        return 0
    print(render_pair_diff(vault_root, pair))
    return 1


def _resolve_interactively(
    vault_root: Path,
    pairs: list[ConflictPair],
    leftovers: list[Leftover],
    portable: str | None,
    desired_paths: set[str],
    *,
    dry_run: bool,
) -> int:
    """Per-pair diff + choice, defaulting to leave; then leftover cleanup offers."""
    if portable is not None:
        matched = match_pair(pairs, portable)
        pairs = [matched] if matched is not None else []
        leftover_names = {portable, portable + NEW_SUFFIX}
        leftovers = [lo for lo in leftovers if lo.entry.path in leftover_names]
        if not pairs and not leftovers:
            print(f"no active conflict for {portable}; `onyxian diff` lists the current pairs.")
            return 0
    if dry_run:
        # Only the dry-run exit shares the gate; the interactive path below prints
        # each pair's diff interleaved with its own prompt, so it can't review upfront.
        review: list[str] = []
        for pair in pairs:
            review.append(render_pair_diff(vault_root, pair))
            review.append(f"{pair.path}: would offer take-new / keep-mine / leave.")
        for leftover in leftovers:
            review.append(f"{leftover.entry.path}: would offer to retire the leftover ledger row.")
        _review_gate(review, dry_run=True, assume_yes=True, question="")
        return 0
    if not _is_interactive():
        raise AnswersError(
            "interactive resolve needs a terminal; non-interactively use "
            "`onyxian diff <path> --take-new|--keep-mine --yes` one pair at a time"
        )
    # Each accepted resolution takes the mutex for just its own write and works on
    # a lock loaded inside it (invariant 7): the prompts between writes can hang
    # open indefinitely, and every helper re-verifies against the live state anyway.
    failed = False
    for pair in pairs:
        print(render_pair_diff(vault_root, pair))
        choice = input(f"{pair.path}: [t]ake-new / [k]eep-mine / [l]eave  [l]: ").strip().lower()
        if choice in ("t", "take-new"):
            resolver = take_new
        elif choice in ("k", "keep-mine"):
            resolver = keep_mine
        else:
            print(f"  = left alone: {pair.path} (the offer stands)")
            continue
        with vault_mutex(vault_root):
            ok, message = resolver(vault_root, pair, load_lock(vault_root), desired_paths)
        print(f"  = {message}" if ok else f"  x {pair.path}: {message}")
        failed |= not ok
    for leftover in leftovers:
        raw = (
            input(f"clean up the leftover ledger row for {leftover.entry.path}? [y/N] ")
            .strip()
            .lower()
        )
        if raw in ("y", "yes"):
            with vault_mutex(vault_root):
                ok, message = clean_leftover(vault_root, leftover, load_lock(vault_root))
            print(f"  = {message}" if ok else f"  x {leftover.entry.path}: {message}")
            failed |= not ok
    return 1 if failed else 0


def cmd_remove(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    config = load_config(vault_root)
    mod_id = args.module
    if mod_id == "core":
        raise ResolveError("'core' is required by everything and cannot be removed")
    lock = load_lock(vault_root)
    entries = [e for e in lock.sorted_entries() if e.module == mod_id]
    if mod_id not in config.modules and not entries:
        print(f"module {mod_id!r} is not enabled; nothing to do.")
        return 0
    library = discover_modules(default_modules_root(), vault_root)
    dependents = sorted(
        m for m in config.modules if m != mod_id and m in library and mod_id in library[m].depends
    )
    if dependents:
        raise ResolveError(
            f"cannot remove {mod_id!r}: {', '.join(dependents)} depend(s) on it; remove those first"
        )

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

    if mod_id in config.modules:
        header = f"removing module {mod_id!r} (only unmodified framework-owned files are deleted):"
    else:
        header = (
            f"module {mod_id!r} is disabled but still tracked; cleaning up what it left behind "
            "(only unmodified framework-owned files are deleted):"
        )
    review = [header]
    if to_delete:
        review.append("  will delete:")
        review += [f"    - {entry.path}" for entry in to_delete]
    if to_leave:
        review.append("  left behind:")
        review += [f"    = {entry.path}  [{reason}]" for entry, reason in to_leave]
    if mod_id in config.modules:
        review.append(f"  ~ {CONFIG_REL} (dropping the {mod_id!r} entry)")
    review.append(
        "  folders the module created are pruned only if empty; anything holding your files stays."
    )
    gate = _review_gate(
        review, dry_run=args.dry_run, assume_yes=args.yes, question=f"remove {mod_id!r}?"
    )
    if gate is not None:
        return gate

    with vault_mutex(vault_root):
        # Invariant 7: reload before mutating; the reviewed `entries` snapshot still
        # names exactly the rows to relinquish and the files eligible for deletion.
        lock = load_lock(vault_root)
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

        if mod_id in config.modules:
            config_text, new_config = remove_module_entry(
                read_text(config_path(vault_root)), mod_id
            )
            write_text_atomic(config_path(vault_root), config_text)
        else:
            new_config = config  # orphan cleanup: the config never listed this module
        # An external module's vault-local copy is engine-owned state; drop it in either path.
        # Key off the directory, not config[mod_id].source, which KeyErrors once the entry is gone.
        external_copy = vault_root / ".vault" / "modules" / mod_id
        if external_copy.is_dir():
            shutil.rmtree(external_copy, ignore_errors=True)
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
            a.type == UPDATE and a.module == "core" for a in follow_up.mutating
        ):
            apply_plan(vault_root, follow_up, lock)
            print("refreshed generated content for the new module set.")
        elif follow_up.mutating:
            print(
                "the module set changed; review the rest with `onyxian plan`, then `onyxian apply`."
            )
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
  in `onyxian modules`; make it earn its place.
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
  # agents:  - my-agent                           # agents/<id>.yaml
# seeds:     - "{{{{root}}}}/Start.md"            # written once, user-owned forever
post_install: |
  One short paragraph for the human: what to fill in or read first.
'''
    example_note = f"""---
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
"""
    readme = f"""# {mod_id}

What this module provides and the conventions it carries. Document your note
types (their `type` values, status lifecycles, extra frontmatter fields) in a
table here — agents and humans both read this.

The module authoring guide — manifest anatomy, variables, Bases, skills and
agents, and the review checklist — is at
https://github.com/odysseia06/onyxian/blob/main/docs/module-authoring.md
In short: assets mirror install paths verbatim (placeholder segments included),
prose is never hard-wrapped, `{{{{variable}}}}` belongs to the engine and
`<% tp.* %>` to Templater, and modules contain no executable code.
"""
    write_text_atomic(target / "module.yaml", manifest_text)
    write_text_atomic(target / "assets" / "Templates" / title / "Example Note.md", example_note)
    write_text_atomic(target / "docs" / "README.md", readme)

    manifest = load_manifest(target)  # the §9.1 guarantee: valid out of the box
    print(
        f"scaffolded module {manifest.name!r} v{manifest.version} at {target} (validates cleanly)."
    )
    print(
        "next: fill the summary, real assets, and docs; test-install with"
        f" `onyxian add {target}` in a scratch vault; distribute by pushing this folder"
        " as a git repository (module.yaml at the root). Authoring guide and review"
        " checklist: https://github.com/odysseia06/onyxian/blob/main/docs/module-authoring.md"
    )
    return 0


def cmd_modules(args: argparse.Namespace) -> int:
    bundled = discover_modules(default_modules_root())
    # With --vault, merge in external modules installed under .vault/modules/; without it,
    # stay vault-less (the command is documented to need no vault). Shadowing a bundled id is
    # rejected at discovery, so provenance is a sound set difference against the bundled ids.
    library = discover_modules(default_modules_root(), _vault_root(args)) if args.vault else bundled
    for name in sorted(library):
        manifest = library[name]
        marker = "" if name in bundled else f"  (external, {EXTERNAL_REL}/{name})"
        print(f"{manifest.name} {manifest.version}{marker}")
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


def cmd_project_new(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    name = args.name
    # validate before the gate: a dry run must not report success for an operation
    # that would fail, and the confirm prompt must not fire before the error
    validate_project(vault_root, name, default_modules_root())
    gate = _review_gate(
        (),
        dry_run=args.dry_run,
        assume_yes=args.yes,
        question=f"create project {name!r}?",
        dry_run_extra=[f"would create project {name!r} under the projects-software root"],
    )
    if gate is not None:
        return gate
    created = scaffold_project(vault_root, name, default_modules_root(), today=resolve_today())
    print(f"created {created}/ — fill its 00 Overview.md (project-steward can do this for you)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="onyxian",
        description="Composable, agent-optional framework for Obsidian vaults.",
    )
    parser.add_argument("--version", action="version", version=f"onyxian {ENGINE_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "init", help="interview -> config -> plan -> confirm -> apply on a new/empty folder"
    )
    p.add_argument("target", help="folder to create the vault in (created if missing)")
    p.add_argument("--answers", help="answers file or profile YAML for a non-interactive run")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument(
        "--trust",
        action="store_true",
        help="accept declared sources' skill instructions without prompting "
        "(--yes never covers instruction content)",
    )
    p.add_argument("--dry-run", action="store_true", help="show the plan and write nothing")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser(
        "plan", help="show the diff between declared intent and the vault (read-only)"
    )
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

    p = sub.add_parser(
        "checkpoint",
        help=(
            "snapshot the vault into a private git history you can diff and restore from "
            "by hand — an opt-in recovery net, never scope enforcement"
        ),
    )
    p.add_argument(
        "action",
        nargs="?",
        choices=["list", "diff"],
        help="list snapshots, or diff the working tree against the last one; "
        "omit to take a snapshot",
    )
    p.add_argument("--vault", default=".", help="vault root (default: current directory)")
    p.add_argument(
        "--quiet", action="store_true", help="print nothing on success (for the SessionStart hook)"
    )
    p.set_defaults(func=cmd_checkpoint)

    p = sub.add_parser(
        "hook", help="internal hooks invoked by Claude Code (not for interactive use)"
    )
    hook_sub = p.add_subparsers(dest="hook_command", required=True)
    p_sc = hook_sub.add_parser(
        "scope-check",
        help="PreToolUse gate: allow/deny/ask a Bash command against an agent's write scope",
    )
    p_sc.add_argument("--agent", required=True, help="the agent whose write scope to enforce")
    p_sc.add_argument("--vault", default=".", help="vault root (default: current directory)")
    p_sc.set_defaults(func=cmd_hook_scope_check)

    p = sub.add_parser(
        "modules", help="list available modules, their variables, and defaults (read-only)"
    )
    p.add_argument(
        "--vault", help="also list external modules installed in this vault under .vault/modules/"
    )
    p.set_defaults(func=cmd_modules)

    p = sub.add_parser("add", help="enable a module: config insert, module questions, plan, apply")
    p.add_argument("module", help="module id to enable (dependencies are added automatically)")
    p.add_argument("--vault", default=".", help="vault root (default: current directory)")
    p.add_argument("--answers", help="answers file supplying the module's variable values")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument(
        "--trust",
        action="store_true",
        help="accept a third-party module's trust warning without prompting "
        "(--yes never covers instruction content)",
    )
    p.add_argument("--dry-run", action="store_true", help="show the plan and write nothing")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser(
        "adopt",
        help=(
            "bring an existing vault under management — additive only, "
            "mandatory plan review, no fast path"
        ),
    )
    p.add_argument("target", help="the existing vault directory")
    p.add_argument(
        "--answers",
        help="answers file or profile YAML; scan proposals fill whatever it leaves unset",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="scan, map, and show the plan; write nothing"
    )
    p.add_argument(
        "--accept",
        metavar="TOKEN",
        help=(
            "apply the exact plan a previous run displayed (the token it printed); "
            "rejected if anything changed"
        ),
    )
    p.add_argument(
        "--trust",
        action="store_true",
        help="accept declared sources' skill instructions without prompting "
        "(--yes never covers instruction content)",
    )
    p.set_defaults(func=cmd_adopt)

    p = sub.add_parser(
        "update",
        help="upgrade module assets and pinned sources — zero overwrites of modified files",
    )
    p.add_argument("module", nargs="?", help="one module or source to update (default: everything)")
    p.add_argument("--vault", default=".", help="vault root (default: current directory)")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument(
        "--trust",
        action="store_true",
        help="accept changed third-party agent/skill instructions without prompting "
        "(--yes never covers instruction content)",
    )
    p.add_argument("--dry-run", action="store_true", help="show the update plan and write nothing")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser(
        "diff",
        help="inspect and resolve *.new conflict siblings "
        "(read paths exit 1 when anything is listed or shown, 0 when clean)",
    )
    p.add_argument(
        "path",
        nargs="?",
        help="the conflicted file (original or its *.new sibling); omit to list all pairs",
    )
    p.add_argument("--vault", default=".", help="vault root (default: current directory)")
    p.add_argument(
        "--resolve",
        action="store_true",
        help="interactive: show each diff, then take-new / keep-mine / leave",
    )
    p.add_argument(
        "--take-new",
        action="store_true",
        help="resolve one pair by adopting the shipped version (needs the path)",
    )
    p.add_argument(
        "--keep-mine",
        action="store_true",
        help=(
            "resolve one pair by declining the shipped version until "
            "its content changes (needs the path)"
        ),
    )
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument(
        "--dry-run", action="store_true", help="show what a resolution would do and write nothing"
    )
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser(
        "remove", help="disable a module — deletes only unmodified framework-owned files"
    )
    p.add_argument("module", help="module id to remove")
    p.add_argument("--vault", default=".", help="vault root (default: current directory)")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument(
        "--dry-run", action="store_true", help="show what would happen and write nothing"
    )
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("module", help="module authoring tools")
    module_sub = p.add_subparsers(dest="module_command", required=True)
    p_new = module_sub.add_parser(
        "new", help="scaffold a module skeleton that validates out of the box"
    )
    p_new.add_argument("id", help="module id, kebab-case")
    p_new.add_argument(
        "--dir", default=".", help="directory to scaffold into (default: current directory)"
    )
    p_new.set_defaults(func=cmd_module_new)

    p = sub.add_parser("project", help="project-level scaffolding (projects-software)")
    project_sub = p.add_subparsers(dest="project_command", required=True)
    p_project_new = project_sub.add_parser(
        "new", help="scaffold a new software project from the template"
    )
    p_project_new.add_argument("name", help="the project folder name")
    p_project_new.add_argument(
        "--vault", default=".", help="vault root (default: current directory)"
    )
    p_project_new.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p_project_new.add_argument(
        "--dry-run", action="store_true", help="show what would be created; write nothing"
    )
    p_project_new.set_defaults(func=cmd_project_new)

    return parser


def main(argv: list[str] | None = None) -> int:
    _reconfigure_streams()
    args = build_parser().parse_args(argv)
    try:
        exit_code: int = args.func(args)
        return exit_code
    except OnyxianError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(
            "\ninterrupted; nothing partial was left unrecorded (the ledger is saved per write).",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

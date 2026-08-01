"""The `onyxian` command-line interface (KICKSTART.md §9.1).

Mental model: config declares intent, lock records state, `plan` is the diff,
`apply` reconciles. Everything else is ergonomics. Commands that arrive in
later milestones exist as honest stubs that say which milestone, instead of
pretending not to exist.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import io
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from string import Template
from typing import Any, NoReturn

from . import ENGINE_VERSION
from .adopt import (
    acceptance_token,
    assert_additive,
    build_adopt_config,
    claim_existing_seeds,
    render_adopt_review,
    scan_vault,
)
from .answers import (
    Answers,
    build_config,
    collect_module_config,
    load_answers,
    resolve_answers_spec,
)
from .applier import ApplyResult, apply_plan
from .checkpoints import (
    CHECKPOINTS_REL,
    CheckpointUnavailable,
    apply_restore,
    diff_since_last,
    guard_has_run,
    has_checkpoints,
    list_snapshots,
    plan_restore,
    render_restore,
    snapshot,
)
from .config_edit import (
    insert_module_entries,
    remove_module_entry,
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
    ConflictPair,
    Leftover,
    clean_leftover,
    conflicts_json,
    find_conflicts,
    keep_mine,
    match_pair,
    normalize_path_argument,
    render_conflict_list,
    render_pair_diff,
    take_new,
)
from .doctor import exit_code as doctor_exit_code
from .doctor import findings_json, render_findings, run_doctor
from .errors import (
    EXIT_ERROR,
    EXIT_FINDINGS,
    EXIT_OK,
    AnswersError,
    CheckpointError,
    ConfigError,
    LockError,
    OnyxianError,
    ResolveError,
    VaultStateError,
)
from .external import (
    EXTERNAL_REL,
    assert_module_trust,
    fetch_external,
    install_external,
    looks_external,
    record_module_trust,
    trust_warning,
)
from .fsio import iter_files, read_text, sha256_bytes, sha256_file, write_text_atomic
from .intent import DesiredState, build_desired_state, resolve_today
from .lock_reconcile import (
    LockCandidate,
    apply_reconcile,
    build_reconcile_plan,
    inspect_lock_candidates,
    lock_conflict_sibling_paths,
    render_candidates,
    render_reconcile,
)
from .lockio import load_lock, save_lock
from .model import KIND_SEEDED, Config, Lock, LockEntry, Manifest, ModuleConfig
from .mutex import vault_mutex
from .paths import NEW_SUFFIX, to_native
from .planner import UPDATE, Plan, build_plan, plan_json, render_plan
from .repo import default_modules_root, discover_modules, module_template_root
from .resolve import dependency_closure, resolve_modules
from .scaffold import run_scaffold, validate_scaffold
from .scopecheck import ALLOW, ASK, DENY, Decision, evaluate, evaluate_write
from .sources import (
    OBSIDIAN_SKILLS,
    SOURCE_MODULE_PREFIX,
    SourceInstallError,
    SourceTrustInfo,
    enabled_for_planner,
    install_obsidian_skills,
    source_trust_warning,
)
from .update import (
    UpdatePlan,
    bump_pins,
    prepare_update,
    refresh_source,
    render_update_report,
    source_pin_edit,
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


def _is_interactive() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


# ----------------------------------------------------------------- ANSI (issue #133)
#
# Hand-rolled color, stdlib only (KICKSTART.md D7). Styling happens at the print
# boundary and nowhere earlier: every render_* function stays plain text, because
# that text feeds the --json twins and adopt's acceptance_token, which must never
# see an escape code. Color is on only when stdout is a real terminal, NO_COLOR
# is unset (https://no-color.org), and — on Windows — the console accepts VT.

_RESET = "\x1b[0m"
_BOLD = "1"
_DIM = "2"
_RED = "31"
_GREEN = "32"
_YELLOW = "33"
_MAGENTA = "35"
_CYAN = "36"

_color_on = False  # set once in main(); tests patch _detect_color or this flag

# The single-char badge vocabulary shared by every renderer (planner._BADGES et al.).
_BADGE_COLORS = {
    "+": _GREEN,
    "~": _YELLOW,
    "=": _DIM,
    "!": _RED,
    "x": _RED,
    "*": _MAGENTA,
    "-": _RED,
}
_FINDING_COLORS = {"ok": _GREEN, "info": _CYAN, "warn": _YELLOW, "FAIL": f"{_BOLD};{_RED}"}
_VERDICT_COLORS = {"needs attention": _YELLOW, "broken": f"{_BOLD};{_RED}"}

_BADGE_RE = re.compile(r"^(\s+)([+~=!x*-])(\s.*)$")
_FINDING_RE = re.compile(r"^(\s*)(ok|info|warn|FAIL)(: .*)$")


def _enable_vt() -> bool:
    """Ask Windows' console for VT processing; other platforms need no switch.
    A piped or console-less stdout fails the mode calls and simply gets no color."""
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
    mode = ctypes.c_uint32()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))  # VT processing


def _detect_color() -> bool:
    if os.environ.get("NO_COLOR"):  # any non-empty value disables, per no-color.org
        return False
    try:
        if not sys.stdout.isatty():
            return False
    except (AttributeError, ValueError):
        return False
    return _enable_vt()


def _paint(code: str, text: str) -> str:
    return f"\x1b[{code}m{text}{_RESET}"


def _stylize_line(line: str) -> str:
    if badge := _BADGE_RE.match(line):
        indent, char, rest = badge.groups()
        return f"{indent}{_paint(_BADGE_COLORS[char], char)}{rest}"
    if finding := _FINDING_RE.match(line):
        indent, label, rest = finding.groups()
        return f"{indent}{_paint(_FINDING_COLORS[label], label)}{rest}"
    if line.lstrip().startswith("-> "):  # a finding's suggestion continuation
        return _paint(_DIM, line)
    if " verdict: " in line:
        head, sep, verdict = line.partition(" verdict: ")
        return f"{head}{sep}{_paint(_VERDICT_COLORS.get(verdict, _GREEN), verdict)}"
    if line.endswith(":") and not line[0].isspace():  # section header
        return _paint(_BOLD, line)
    return line


def _stylize(text: str) -> str:
    """Colorize a rendered block for terminal display; the identity when color is off,
    so piped output and every test capture stay byte-identical to the renderer."""
    if not _color_on:
        return text
    return "\n".join(_stylize_line(line) for line in text.split("\n"))


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
            "review the trust warning and pass --trust (no other flag grants it)"
        )
    return _confirm(question, assume_yes=False)


def _emit(notes: Sequence[str] = (), warnings: Sequence[str] = ()) -> None:
    """Print a library function's collected report: notes to stdout, warnings to stderr."""
    for line in notes:
        print(_stylize(line))
    for line in warnings:
        print(line, file=sys.stderr)


def _answers(args: argparse.Namespace) -> Answers | None:
    """The parsed ``--answers`` file or bundled profile; None when the flag is absent."""
    return load_answers(resolve_answers_spec(args.answers)) if args.answers else None


def _var_overrides(pairs: Sequence[str], manifest: Manifest) -> dict[str, object]:
    """Repeatable ``--var key=value`` flags for the module being added (#130).

    Values are typed against the manifest's declaration; an unknown key passes
    through so ``collect_module_config`` raises its error naming the declared
    variables, rather than a second copy of it here.
    """
    provided: dict[str, object] = {}
    declared = {var.key: var for var in manifest.variables}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise AnswersError(f"--var {pair!r}: expected key=value")
        var = declared.get(key)
        if var is not None and var.type == "bool":
            if value.lower() not in ("true", "false"):
                raise AnswersError(f"--var {key}: must be true or false, got {value!r}")
            provided[key] = value.lower() == "true"
        else:
            provided[key] = value
    return provided


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
    target: Path,
    config: Config,
    lock: Lock,
    library: dict[str, Manifest],
    *,
    trusted: bool,
    ask_consent: bool = True,
) -> None:
    """Post-apply source install (§9.2 'runtime install'); failures degrade to warnings (P2).

    ``ask_consent=False`` is the zero-question init path (#129): never prompt for
    instruction consent, decline instead — exactly what a scripted run without a TTY
    already does.
    """
    if not config.sources:
        return
    if (
        OBSIDIAN_SKILLS in config.sources
        and not trusted
        and not (ask_consent and _is_interactive())
    ):
        # _confirm_trust fails closed here (#61), so the fetch could only be thrown away.
        # Since obsidian-skills now defaults in (#65), that is every scripted init: decline
        # before the network, not after cloning a repo we were never going to install.
        print(
            f"source {OBSIDIAN_SKILLS!r} not installed: its skill instructions need their own "
            "consent, which only --trust gives. The vault works without them; "
            "`onyxian update --trust` installs them after review.",
            file=sys.stderr,
        )
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
        print("skipped:", file=sys.stderr)  # each line carries its own reason
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
# The commands below are thin: build a plan, review it, gate, write — except `add`,
# which prints the plan and applies ungated (#130: a wrong add is cheap to undo).
# A contributor must preserve these invariants (CONTRIBUTING.md points here):
#
# 1. What you print is what you apply. The plan is built once, rendered, and that
#    same object goes to apply_plan; never re-plan between review and apply. Adopt
#    pins this down with acceptance_token (a fingerprint over the reviewed config
#    text, plan actions, and seed claims); everywhere else it is convention. The one
#    sanctioned exception is cmd_remove's follow-up plan, which auto-applies only
#    when every mutating action is a core UPDATE.
# 2. --dry-run returns before any write of any kind — config edits, lock saves,
#    external installs. _review_gate returns 0 on the dry-run branch, above the writes;
#    ungated add hand-rolls the same branch above its config write and mutex.
# 3. config.yaml is the user's file. After init/adopt seed it, every edit goes
#    through a config_edit function that re-parses before returning; the CLI writes
#    that text with write_text_atomic and never regenerates a user-edited config with
#    render_config_text (the only post-seed regeneration is in _install_sources_step,
#    immediately after the engine itself generated the file).
# 4. Write ordering: add writes config *before* apply (declared intent survives a
#    crash; re-running plan/apply converges); update bumps versions and pins only
#    *after* apply_plan has run — the config never gets ahead of an apply that never
#    happened. A *partial* apply (re-verify skips) still bumps, deliberately: a pin
#    left behind the library makes resolve_modules hard-fail every later command,
#    including the `apply` that would converge. The un-applied files are carried by
#    the ledger, which still holds their old hashes, so `apply` re-plans them.
#    Anything fallible between apply_plan and that single config write must degrade
#    rather than raise, or the config is stranded behind files that already moved
#    (#50) — sources.install_obsidian_skills funnels every failure into
#    SourceInstallError for exactly this reason.
# 5. Exit codes follow the three-value convention documented in errors.py, which is the
#    contract scripts branch on: 0 for clean runs, dry runs, and degraded-but-warned
#    source installs; 1 for user abort, errors, usage errors, skipped re-verifies, and
#    remove's raced files; 2 only for the read-only reports (plan/doctor/diff/modules lint) that ran
#    fine and have something to report; 130 for interrupt. _print_apply_outcome is the
#    only translator from an apply result to text and code.
# 6. Any lock.put done in cli.py itself is followed by save_lock before the next
#    fallible operation.
# 7. The vault mutex brackets every ledger save and every write under .vault/
#    (including install_external's staging copy and its rollback), and the Lock
#    saved inside it is (re)loaded inside it too — never a snapshot taken before the gate. The
#    confirm prompt can hang open (and ungated add can lose the same race while planning)
#    while another onyxian process completes a whole command; saving a lock loaded
#    before the gate would erase that process's rows
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
        print(_stylize(line))
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
    ask_consent: bool = True,
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
    _install_sources_step(target, config, lock, library, trusted=trusted, ask_consent=ask_consent)
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

    # #129: bare init and --profile ask nothing — no questions, no confirmation gate.
    # --answers keeps its reviewed, gated flow for CI and agents.
    zero_question = not args.answers
    if args.profile:
        answers = load_answers(resolve_answers_spec(args.profile, flag="--profile"))
        if answers.profile_name is None:
            raise AnswersError(
                f"--profile {args.profile!r}: not a profile; answers files go to --answers"
            )
    else:
        answers = _answers(args) or Answers()
    if zero_question and answers.vault_name is None:
        answers.vault_name = target.resolve().name or "My Vault"

    library = discover_modules(default_modules_root())
    config = build_config(library, answers)
    manifests = resolve_modules(config, library)
    desired = build_desired_state(config, manifests)
    lock = Lock()
    plan = build_plan(target, desired, lock, enabled_for_planner(config))

    if args.dry_run or not zero_question:
        review = [f"vault: {config.vault_name!r} at {target}"]
        if answers.profile_name:
            review.append(f"profile: {answers.profile_name}")
        review += [
            f"runtimes: {', '.join(config.runtimes)}",
            f"folder style: {config.folder_style}; modules: {', '.join(config.modules)}",
            render_plan(plan),
            f"  + {CONFIG_REL} (seeded; yours to edit)",
            "  + .vault/lock.json (the engine's ledger)",
        ]
        # A zero-question run only gets here for --dry-run, which returns before
        # _confirm — so args.yes alone decides the gate.
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
            ask_consent=not zero_question,
        )
        if zero_question:
            print(
                f"\ncreated {config.vault_name!r} at {target} — modules: "
                f"{', '.join(config.modules)}."
            )
            print("grow it: `onyxian add <module>` (`onyxian modules` lists what's available).")
            print(f"open it in Obsidian, or check it any time: onyxian doctor --vault {target}")
        else:
            print(f"\nvault ready. open it in Obsidian, then try: onyxian doctor --vault {target}")
    return code


def cmd_plan(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    _, _, plan, _ = _load_context(vault_root)
    print(json.dumps(plan_json(plan), indent=2) if args.json else _stylize(render_plan(plan)))
    # The drift check CI can branch on: "would apply write anything?". Report-only
    # actions are deliberately not findings here — `doctor` is what judges those.
    return EXIT_OK if plan.is_empty else EXIT_FINDINGS


def cmd_apply(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    _config, manifests, plan, lock = _load_context(vault_root)
    print(_stylize(render_plan(plan)))
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
    print(
        json.dumps(findings_json(findings), indent=2)
        if args.json
        else _stylize(render_findings(findings))
    )
    return doctor_exit_code(findings)


def _choose_lock_candidate(candidates: tuple[LockCandidate, ...]) -> str:
    valid = [candidate for candidate in candidates if candidate.valid]
    if not valid:
        raise LockError("no valid lock candidate can survive reconciliation")
    while True:
        raw = input("keep which lock candidate (number or filename)? ").strip()
        selected: LockCandidate | None = None
        if raw.isdigit() and 1 <= int(raw) <= len(candidates):
            selected = candidates[int(raw) - 1]
        else:
            selected = next((candidate for candidate in candidates if candidate.name == raw), None)
        if selected is not None and selected.valid:
            return selected.name
        print("choose one of the valid candidates listed above.", file=sys.stderr)


def cmd_lock(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    if not lock_conflict_sibling_paths(vault_root):
        raise LockError("no conflicted lock.json sibling was found; there is nothing to reconcile")
    candidates = inspect_lock_candidates(vault_root)
    selected_name = args.keep
    candidates_already_shown = False
    if selected_name is None:
        for line in render_candidates(candidates):
            print(line)
        candidates_already_shown = True
        if not _is_interactive():
            raise AnswersError(
                "lock reconciliation needs an explicit survivor in non-interactive mode; "
                "pass --keep <filename>"
            )
        selected_name = _choose_lock_candidate(candidates)

    plan = build_reconcile_plan(vault_root, candidates, selected_name)
    gate = _review_gate(
        render_reconcile(plan, include_candidates=not candidates_already_shown),
        dry_run=args.dry_run,
        assume_yes=args.yes,
        question=f"keep {selected_name!r} and reconcile the lock?",
    )
    if gate is not None:
        return gate
    with vault_mutex(vault_root):
        result = apply_reconcile(vault_root, plan)
    retired = ", ".join(result.retired)
    print(
        f"reconciled lock.json at generation {result.generation} on "
        f"{result.machine_id}; retired {retired}"
    )
    return EXIT_OK


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


_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# A moment.js format is a run of repeated letters per token, plus [escaped literals].
_MOMENT_TOKEN = re.compile(r"\[([^\]]*)\]|([A-Za-z])\2*")


def _render_moment(fmt: str, today: datetime.date) -> str | None:
    """Render an Obsidian (moment.js) date format, or None if it uses a token outside the
    date set below. Guessing is worse than not knowing here: the result is a *proof* that
    an agent's write is in scope, so a wrong stamp denies a write that should have passed.

    ponytail: date tokens only, English names (moment's default locale) — a localized
    Obsidian or a time/week format falls back to None, i.e. `ask`. Widen the table if a
    real vault needs more.
    """
    values = {
        "YYYY": f"{today.year:04d}",
        "YY": f"{today.year % 100:02d}",
        "MMMM": _MONTHS[today.month - 1],
        "MMM": _MONTHS[today.month - 1][:3],
        "MM": f"{today.month:02d}",
        "M": str(today.month),
        "DD": f"{today.day:02d}",
        "D": str(today.day),
        "dddd": _WEEKDAYS[today.weekday()],
        "ddd": _WEEKDAYS[today.weekday()][:3],
    }
    out: list[str] = []
    pos = 0
    for match in _MOMENT_TOKEN.finditer(fmt):
        out.append(fmt[pos : match.start()])
        pos = match.end()
        if match.group(2) is None:  # [literal]
            out.append(match.group(1))
            continue
        rendered = values.get(match.group(0))
        if rendered is None:
            return None
        out.append(rendered)
    out.append(fmt[pos:])
    return "".join(out)


def _resolve_daily_note(vault_root: Path) -> str | None:
    """Today's daily-note path from `.obsidian/daily-notes.json`, so `daily:append`
    becomes a provable target. None when daily notes aren't configured, the file is
    malformed, or the format uses a token `_render_moment` won't resolve."""
    try:
        cfg = json.loads((vault_root / ".obsidian" / "daily-notes.json").read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    fmt = str(cfg.get("format", "")) if isinstance(cfg, dict) else ""
    if not fmt:
        return None
    stamp = _render_moment(fmt, datetime.date.fromisoformat(resolve_today()))
    if stamp is None:
        return None
    folder = str(cfg.get("folder", "")).rstrip("/")
    return f"{folder}/{stamp}.md" if folder else f"{stamp}.md"


def _decide_direct_write(
    tool_name: str, file_path: str, vault_root: Path, write_globs: list[str] | None
) -> Decision:
    """The Write/Edit arm of the gate. These tools are re-allowed on agents *because*
    the hook path-checks them, so unknown scopes degrade to `ask`, not silence (the
    Bash arm stays fail-open: it polices a channel that exists regardless). A target
    outside the vault can never match a vault-relative glob — provable, so deny."""
    if write_globs is None:
        return Decision(
            ASK, "this agent's write scope is unknown (`.claude/onyxian-scopes.json` unreadable)"
        )
    try:
        relative = Path(file_path).resolve().relative_to(vault_root.resolve())
    except (ValueError, OSError):
        return Decision(DENY, f"`{tool_name}` writes `{file_path}`, outside the vault")
    return evaluate_write(tool_name, relative.as_posix(), write_globs)


def cmd_hook_scope_check(args: argparse.Namespace) -> int:
    """PreToolUse gate (#11 phase 3): decide a Bash command or a direct-write tool
    call (Write/Edit) against an agent's write scope. Emits `permissionDecision`
    deny/ask; stays silent to let a call through. It only ever narrows permissions —
    an in-scope, read-only, or non-obsidian command is passed to Claude Code's
    normal flow, never auto-approved."""
    vault_root = Path(args.vault)
    payload = sys.stdin.read()
    try:
        data = json.loads(payload) if payload.strip() else {}
    except json.JSONDecodeError:
        return 0
    if not isinstance(data, dict):
        return 0  # valid JSON, but not a PreToolUse event; a hook never breaks the session
    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input")
    write_globs = _load_agent_scopes(vault_root, args.agent)
    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
        if not isinstance(file_path, str) or not file_path:
            return 0  # malformed input; the tool call itself will fail downstream
        decision = _decide_direct_write(tool_name, file_path, vault_root, write_globs)
    else:
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if tool_name not in (None, "Bash") or not isinstance(command, str) or not command:
            return 0
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


def _no_snapshots_message(vault_root: Path) -> str:
    """The empty-history line for `checkpoint list`/`diff` — doctor's #93 split (#96):
    "not readable", not "never taken", once the guard has run, because that also
    covers real history behind a corrupt ref where "no checkpoints yet" is a lie."""
    if guard_has_run(vault_root):
        return (
            "the checkpoint guard has run, but no snapshot is readable; "
            "`onyxian checkpoint` prints git's own reason."
        )
    return "no checkpoints yet; run `onyxian checkpoint` to create a baseline."


def cmd_checkpoint(args: argparse.Namespace) -> int:
    candidate = Path(args.vault)
    recovery_history = candidate / CHECKPOINTS_REL / "HEAD"
    if args.action in ("list", "diff", "restore") and recovery_history.is_file():
        # Recovery stays reachable when config.yaml itself is the file that was
        # deleted or corrupted. Taking a *new* snapshot still requires a managed
        # vault; existing history is sufficient authority only to inspect/restore.
        vault_root = candidate
    else:
        vault_root = _vault_root(args)
    if args.action != "restore":
        if args.dry_run:
            raise CheckpointError("--dry-run is only valid with `checkpoint restore`")
        if args.yes:
            raise CheckpointError("--yes is only valid with `checkpoint restore`")
        if args.checkpoint_id is not None or args.paths:
            action = args.action or "snapshot"
            raise CheckpointError(f"`checkpoint {action}` does not take a checkpoint id or paths")
    elif args.quiet:
        raise CheckpointError("--quiet is only valid when taking a checkpoint")
    try:
        if args.action == "restore":
            if args.checkpoint_id is None:
                raise CheckpointError(
                    "restore needs a checkpoint id from `onyxian checkpoint list`"
                )
            # A whole-vault restore replaces lock.json itself, so it must remain
            # usable when that live file is the damaged state being recovered.
            lock_path = ".vault/lock.json"
            normalized_paths = [path.replace("\\", "/") for path in args.paths]
            restores_lockfile = not normalized_paths or any(
                lock_path == path or lock_path.startswith(path + "/") for path in normalized_paths
            )
            current_lock = Lock() if restores_lockfile else load_lock(vault_root)
            plan = plan_restore(vault_root, args.checkpoint_id, args.paths, current_lock)
            if not plan.changes:
                print(f"vault already matches checkpoint {plan.checkpoint_id} for those paths.")
                return 0
            gate = _review_gate(
                render_restore(plan),
                dry_run=args.dry_run,
                assume_yes=args.yes,
                question=f"restore from checkpoint {plan.checkpoint_id}?",
            )
            if gate is not None:
                return gate
            with vault_mutex(vault_root):
                lock = plan.checkpoint_lock if plan.restore_lockfile else load_lock(vault_root)
                restore_result = apply_restore(vault_root, plan, lock)
            for path in restore_result.restored:
                print(f"  = restored {path}")
            if restore_result.skipped:
                print("skipped:", file=sys.stderr)
                for path, reason in restore_result.skipped:
                    print(f"  - {path}: {reason}", file=sys.stderr)
                return EXIT_ERROR
        elif args.action == "list":
            infos = list_snapshots(vault_root)
            if not infos:
                print(_no_snapshots_message(vault_root))
            for info in infos:
                tail = "(baseline)" if info.baseline else f"{_files(info.files_changed)} changed"
                print(f"{info.checkpoint_id}  {info.when}   {tail}")
        elif args.action == "diff":
            if not has_checkpoints(vault_root):
                print(_no_snapshots_message(vault_root))
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
    except CheckpointUnavailable as exc:
        if args.action == "restore":
            raise CheckpointError(f"checkpoint restore is unavailable: {exc}") from None
        # The guard is a net, not a dependency: no tooling failure may break a session
        # or fail a command (P2) — not a missing git, not a git that refuses or hangs,
        # not an unwritable `.vault/checkpoints/` (#60). Each of those reaches here as
        # CheckpointUnavailable, so this never fires once the snapshot is on disk: a
        # net that claims it skipped when it did not is worse than no net. One honest
        # line naming the reason, then get out of the way.
        # Not "skipping checkpoint": `list` and `diff` reach here too, and they were
        # never taking one. "Unavailable" is true for all three (#93).
        print(
            f"warning: {exc}; the checkpoint guard is unavailable (the vault is unaffected).",
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
    scan = scan_vault(target, library)
    config = build_adopt_config(target, library, _answers(args), scan)
    manifests = resolve_modules(config, library)
    desired = build_desired_state(config, manifests)
    lock = Lock()
    seed_claims = claim_existing_seeds(target, desired, lock)
    plan = build_plan(target, desired, lock, enabled_for_planner(config))
    assert_additive(plan)
    config_text = render_config_text(config)
    token = acceptance_token(config_text, plan, seed_claims)

    for line in render_adopt_review(target, config, scan, plan, seed_claims):
        print(_stylize(line))

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


def _enable_and_apply(
    args: argparse.Namespace,
    vault_root: Path,
    library: dict[str, Manifest],
    new_entries: dict[str, ModuleConfig],
    enabling_line: str,
    *,
    record_trust_ids: Sequence[str] = (),
) -> int:
    """Shared tail of `add` (bundled and external): config insert, plan, apply — no gate (#130).

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

    # #130: no confirm gate — the chosen values are printed instead, and a wrong
    # default is cheap to undo (`onyxian remove` is clean while the files are untouched).
    print(enabling_line)
    for mod_id, entry in sorted(new_entries.items()):
        if entry.vars:
            choices = ", ".join(
                f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in entry.vars.items()
            )
            print(f"  {mod_id}: {choices}")
    print(_stylize(render_plan(plan)))
    print(_stylize(f"  ~ {CONFIG_REL} (adding: {', '.join(sorted(new_entries))})"))
    if args.dry_run:
        print("dry run; nothing written.")
        return 0

    with vault_mutex(vault_root):
        write_text_atomic(config_path(vault_root), new_text)
        lock = load_lock(vault_root)  # invariant 7: never save the pre-gate snapshot
        for mod_id in record_trust_ids:
            record_module_trust(vault_root, lock, mod_id)
        if record_trust_ids:
            save_lock(vault_root, lock)  # persist the baseline even if apply writes nothing
        return _apply_and_report(
            vault_root, plan, lock, manifests, newly_installed=set(new_entries)
        )


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
        # #130: validate --var before the trust gate and staging — a typo raising later
        # would orphan the freshly staged copy under .vault/modules/.
        overrides = _var_overrides(args.var, manifest)

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
            with vault_mutex(vault_root):  # #50: staging into .vault/ is a vault write
                install_external(vault_root, manifest)
            # Re-discover so planning sees the staged copy, not the scratch one.
            library = discover_modules(default_modules_root(), vault_root)

        to_add = sorted(dependency_closure([manifest.name], library, have=config.modules))
        answers = _answers(args)
        source_cfg = {"repo": repo, **({"pin": pin} if pin else {})}
        new_entries: dict[str, ModuleConfig] = {}
        for mod_id in to_add:
            provided = dict(answers.modules.get(mod_id, {})) if answers else {}
            if mod_id == manifest.name:
                provided.update(overrides)
            entry = collect_module_config(
                library[mod_id], provided, folder_style=config.folder_style
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
            with vault_mutex(vault_root):  # #50: so does un-staging it
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
        if args.var:
            print(
                f"--var has no effect on an enabled module: edit modules.{target} in "
                ".vault/config.yaml and run `onyxian apply`, or remove and re-add."
            )
        return 0

    to_add = dependency_closure([target], library, have=config.modules)
    answers = _answers(args)
    overrides = _var_overrides(args.var, library[target])
    new_entries: dict[str, ModuleConfig] = {}
    for mod_id in sorted(to_add):
        provided = dict(answers.modules.get(mod_id, {})) if answers else {}
        if mod_id == target:
            provided.update(overrides)
        new_entries[mod_id] = collect_module_config(
            library[mod_id], provided, folder_style=config.folder_style
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

    # The scratch tree holds every fetched module and must outlive install_external
    # below: a staged manifest points into it until the copy under .vault/ is made.
    with tempfile.TemporaryDirectory(prefix="onyxian-ext-") as scratch:
        up = prepare_update(vault_root, config, args.module, Path(scratch), _answers(args))
        # Config is user-formatted text. Prove the surgical version/variable/pin edits
        # understand its current layout before the review gate and any vault write.
        bump_pins(
            read_text(config_path(vault_root)),
            up.changes,
            up.pin_changes,
            up.variable_additions,
        )
        _emit(render_update_report(up), up.warnings)
        if up.nothing_to_do:
            print("nothing to update.")
            return 0
        for block in up.trust_blocks:
            print(block)
        # Changed instructions get their own gate (#61): --yes below covers the plan
        # only. Dry runs skip it — invariant 2 already guarantees nothing is written.
        if (
            up.trust_blocks
            and not args.dry_run
            and not _confirm_trust(
                "trust the changed instructions and continue?", trusted=args.trust
            )
        ):
            print("aborted; nothing written.")
            return 1
        gate = _review_gate(
            (),
            dry_run=args.dry_run,
            assume_yes=args.yes,
            question="apply this update?",
            dry_run_extra=(
                ["sources: the pin would be advanced to upstream HEAD."]
                if up.update_sources
                else []
            ),
        )
        if gate is not None:
            return gate

        with vault_mutex(vault_root):
            for fetched in up.staged:  # #50: staging into .vault/ is a vault write
                install_external(vault_root, fetched)
            lock = load_lock(vault_root)  # invariant 7: never save the pre-gate snapshot
            for fetched in up.staged:  # #48: re-baseline each freshly reviewed copy
                record_module_trust(vault_root, lock, fetched.name)
            if up.staged:
                save_lock(vault_root, lock)
            code = _apply_and_report(vault_root, up.plan, lock, up.manifests, newly_installed=set())
            _write_config_edits(vault_root, up, lock, trusted=args.trust)
        return code


def _write_config_edits(vault_root: Path, up: UpdatePlan, lock: Lock, *, trusted: bool) -> None:
    """Update's tail: every config edit collected into the one write invariant 4 allows.

    Stays *after* apply, and touches config.yaml at most once per run — never partway.
    """
    before = read_text(config_path(vault_root))
    config_text, notes, warnings = bump_pins(
        before, up.changes, up.pin_changes, up.variable_additions
    )
    _emit(notes, warnings)
    if up.update_sources:
        src, src_warnings = refresh_source(
            vault_root, up.new_config, lock, gate=_source_install_gate(trusted)
        )
        _emit((), src_warnings)
        if src is not None:
            config_text, notes, warnings = source_pin_edit(config_text, src)
            _emit(notes, warnings)
    if config_text != before:
        write_text_atomic(config_path(vault_root), config_text)


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
    if args.json and (args.path or args.resolve or args.take_new or args.keep_mine):
        # A single pair's view is a unified diff — text, with no honest JSON shape.
        raise OnyxianError(
            "--json prints the whole conflict listing; it takes no path and no resolution "
            "flag (filter its `conflicts` array instead)"
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
            return EXIT_ERROR
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
        return EXIT_OK if ok else EXIT_ERROR

    if args.resolve:
        return _resolve_interactively(
            vault_root, pairs, leftovers, portable, desired_paths, dry_run=args.dry_run
        )

    if portable is None:
        if args.json:
            print(json.dumps(conflicts_json(pairs, leftovers), indent=2))
        else:
            print(_stylize(render_conflict_list(pairs, leftovers)))
        return EXIT_FINDINGS if pairs or leftovers else EXIT_OK

    if pair is None:
        leftover_names = {portable, portable + NEW_SUFFIX}
        matched = next((lo.entry.path for lo in leftovers if lo.entry.path in leftover_names), None)
        if matched is not None:
            print(
                f"{matched[: -len(NEW_SUFFIX)]} is already resolved; a leftover ledger row remains"
                f" for {matched} — clean it up with `onyxian diff --resolve`."
            )
            return EXIT_FINDINGS
        print(f"no active conflict for {portable}; `onyxian diff` lists the current pairs.")
        return EXIT_OK
    print(render_pair_diff(vault_root, pair))
    return EXIT_FINDINGS


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
    return EXIT_ERROR if failed else EXIT_OK


def cmd_remove(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    config = load_config(vault_root)
    mod_id = args.module
    if mod_id == "core":
        raise ResolveError("'core' is required by everything and cannot be removed")
    if mod_id.startswith(SOURCE_MODULE_PREFIX):
        # This path exists for sources the config no longer declares (the ORPHANED hint).
        # Deleting the files while `sources:` still names it only half-removes it: the
        # planner sees nothing wrong and the next `update` silently reinstalls (#54).
        src_name = mod_id.removeprefix(SOURCE_MODULE_PREFIX)
        if src_name in config.sources:
            raise ResolveError(
                f"source {src_name!r} is still declared in {CONFIG_REL}; delete its "
                f"`sources.{src_name}:` entry by hand first, then re-run this to clean up "
                "the files it installed"
            )
    lock = load_lock(vault_root)
    entries = [e for e in lock.sorted_entries() if e.module == mod_id]
    external_copy = vault_root / ".vault" / "modules" / mod_id
    removable_entries = [e for e in entries if e.kind != KIND_SEEDED]
    if mod_id not in config.modules and not removable_entries and not external_copy.is_dir():
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
        # names exactly the rows considered and the files eligible for deletion.
        lock = load_lock(vault_root)
        # The config edit is fallible (an unfamiliar layout raises), so compute it before
        # the first deletion: a config this command cannot edit costs nothing (#54).
        if mod_id in config.modules:
            config_text, new_config = remove_module_entry(
                read_text(config_path(vault_root)), mod_id
            )
        else:
            config_text, new_config = None, config  # orphan cleanup: the config never listed it
        deleted, raced, undeletable = 0, [], []
        prune_candidates: set[str] = set(module_dirs)
        for entry in to_delete:
            native = to_native(vault_root, entry.path)
            # Re-verify at the moment of truth: a byte changed since review keeps the file.
            if native.is_file() and sha256_file(native) == entry.sha256:
                try:
                    native.unlink()
                except OSError as exc:
                    # Obsidian holding the file open is routine on Windows; degrade to a
                    # skip-with-reason rather than abort a half-done removal (#54).
                    undeletable.append(entry.path)
                    to_leave.append((entry, f"could not be deleted ({exc.strerror or exc})"))
                    continue
                deleted += 1
                parent = entry.path.rsplit("/", 1)[0] if "/" in entry.path else ""
                if parent:
                    prune_candidates.add(parent)
            else:
                raced.append(entry.path)
                to_leave.append((entry, "changed since review; left alone"))
        for entry in removable_entries:
            # Seed rows remain as durable proof that these user-owned paths were
            # already seeded. Re-adding the module must never mistake their edited
            # bytes for an unmanaged collision (#52).
            live_entry = lock.get(entry.path)
            if (
                live_entry is not None
                and live_entry.module == mod_id
                and live_entry.kind != KIND_SEEDED
            ):
                lock.entries.pop(entry.path)
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

        if config_text is not None:
            write_text_atomic(config_path(vault_root), config_text)
        # An external module's vault-local copy is engine-owned state; drop it in either path.
        # Key off the directory, not config[mod_id].source, which KeyErrors once the entry is gone.
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
        if undeletable:
            print(
                "could not be deleted (open in another program?), left on disk: "
                + ", ".join(undeletable),
                file=sys.stderr,
            )
        if raced:
            print("changed since review, left alone: " + ", ".join(raced), file=sys.stderr)
        return 1 if raced or undeletable else 0


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

    # The skeleton is data (module-template/, next to the module library), not code.
    # `$id`/`$title` in a path or a body are the only substitutions, so `{{var}}` and
    # `<% tp.* %>` reach the new module verbatim — as a module's own assets must.
    template_root = module_template_root()
    for src in iter_files(template_root):
        rel = src.relative_to(template_root).as_posix()
        write_text_atomic(
            target.joinpath(*Template(rel).safe_substitute(id=mod_id, title=title).split("/")),
            Template(read_text(src)).safe_substitute(id=mod_id, title=title),
        )

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


def cmd_module_lint(args: argparse.Namespace) -> int:
    from .lint import lint_module

    findings = lint_module(Path(args.path))
    print(
        json.dumps(findings_json(findings), indent=2)
        if args.json
        else _stylize(render_findings(findings, subject="module"))
    )
    return doctor_exit_code(findings)


def cmd_modules(args: argparse.Namespace) -> int:
    # #132: `modules` is the one module-shaped name — bare lists, `new`/`lint` author.
    # Dispatch on the subcommand dest here instead of per-child set_defaults(func=...),
    # which argparse lets a parent default silently override (bpo-9351).
    if args.modules_command == "new":
        return cmd_module_new(args)
    if args.modules_command == "lint":
        return cmd_module_lint(args)
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


def cmd_new(args: argparse.Namespace) -> int:
    vault_root = _vault_root(args)
    scaffold, name = args.scaffold, args.name
    today = resolve_today()
    # validate before the gate: a dry run must not report success for an operation
    # that would fail, and the confirm prompt must not fire before the error
    target = validate_scaffold(vault_root, scaffold, name, default_modules_root(), today=today)
    gate = _review_gate(
        (),
        dry_run=args.dry_run,
        assume_yes=args.yes,
        question=f"create {scaffold} {name!r}?",
        dry_run_extra=[f"would create {scaffold} {name!r} at {target}/"],
    )
    if gate is not None:
        return gate
    created = run_scaffold(vault_root, scaffold, name, default_modules_root(), today=today)
    print(f"created {created}/ — the copied notes are dated today; fill them in")
    return 0


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error, which the convention in errors.py spends on
    *findings*. A misspelled flag is an error, so it exits 1 like every other one.
    Subparsers inherit this class: argparse defaults `parser_class` to `type(self)`.
    The raw formatter keeps the hand-written `examples:` epilogs line-per-line (#133)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_ERROR, f"{self.prog}: error: {message}\n")


_JSON_HELP = "print the report as JSON on stdout instead of prose (same exit codes)"


def _common(*, vault: bool = False, yes: bool = False, dry_run: str = "") -> _Parser:
    """A parent parser carrying the flags nearly every subcommand repeats.

    ``--vault`` and ``--yes`` mean the same thing everywhere, so their help lives here;
    ``dry_run`` takes its help text as an argument, because what a dry run *shows* is
    the one thing that genuinely differs per command.
    """
    parent = _Parser(add_help=False)
    if vault:
        parent.add_argument("--vault", default=".", help="vault root (default: current directory)")
    if yes:
        parent.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    if dry_run:
        parent.add_argument("--dry-run", action="store_true", help=dry_run)
    return parent


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="onyxian",
        description="Composable, agent-optional framework for Obsidian vaults.",
        epilog=(
            "examples:\n"
            '  onyxian init "My Vault"                  create a core-only vault, zero questions\n'
            '  onyxian init "My Vault" --profile writer one-shot full vault from a bundled preset\n'
            "  onyxian add fitness                      enable a module and apply it immediately\n"
            "  onyxian plan                             preview what apply would change\n"
            "  onyxian doctor                           check the vault against declared intent\n"
            "  onyxian update --dry-run                 preview module and source upgrades\n"
            "\n"
            "run `onyxian <command> --help` for that command's flags."
        ),
    )
    parser.add_argument("--version", action="version", version=f"onyxian {ENGINE_VERSION}")
    # The metavar keeps hidden commands (hook) out of the usage line; a subcommand
    # added without help= is likewise absent from the listing below it (#132).
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    p = sub.add_parser(
        "init",
        parents=[_common(yes=True, dry_run="show the plan and write nothing")],
        help="create a vault in a new/empty folder: core-only from defaults, "
        "or --profile <name> for a full preset — zero questions either way",
        epilog=(
            "examples:\n"
            '  onyxian init "My Vault"                    core-only vault, manifest defaults\n'
            '  onyxian init "My Vault" --profile writer   full vault from a bundled profile\n'
            '  onyxian init "My Vault" --answers my.yaml  full control, behind a reviewed plan'
        ),
    )
    p.add_argument("target", help="folder to create the vault in (created if missing)")
    excl = p.add_mutually_exclusive_group()
    excl.add_argument(
        "--answers", help="answers file or profile YAML: full control, behind a reviewed plan"
    )
    excl.add_argument(
        "--profile",
        help="bundled profile name (or profile YAML path): a one-shot full vault, no questions",
    )
    p.add_argument(
        "--trust",
        action="store_true",
        help="accept declared sources' skill instructions without prompting "
        "(--yes never covers instruction content)",
    )
    p.set_defaults(func=cmd_init)

    p = sub.add_parser(
        "plan",
        parents=[_common(vault=True)],
        help="show the diff between declared intent and the vault "
        "(read-only; exits 2 when anything is pending, 0 when clean)",
    )
    p.add_argument("--json", action="store_true", help=_JSON_HELP)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser(
        "apply",
        parents=[_common(vault=True, yes=True, dry_run="show the plan and write nothing")],
        help="execute the plan; every write is recorded in the lockfile",
    )
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser(
        "doctor",
        parents=[_common(vault=True)],
        help="validate vault state against intent "
        "(read-only; exits 2 on any warning or failure, 0 when healthy)",
    )
    p.add_argument("--json", action="store_true", help=_JSON_HELP)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser(
        "lock",
        parents=[
            _common(
                vault=True,
                yes=True,
                dry_run="review the selected ledger and disk verification; write nothing",
            )
        ],
        help="inspect or repair the managed-file ledger",
    )
    p.add_argument("action", choices=["reconcile"], help="repair a file-sync fork")
    p.add_argument(
        "--keep",
        metavar="FILENAME",
        help="exact lock candidate filename to keep (prompted when omitted interactively)",
    )
    p.set_defaults(func=cmd_lock)

    p = sub.add_parser(
        "checkpoint",
        parents=[_common(vault=True)],
        help=(
            "snapshot, inspect, or restore the vault through a private git history "
            "— an opt-in recovery net, never scope enforcement"
        ),
        epilog=(
            "examples:\n"
            "  onyxian checkpoint                        take a snapshot now\n"
            "  onyxian checkpoint list                   list snapshots\n"
            "  onyxian checkpoint restore <id>           restore the whole vault\n"
            "  onyxian checkpoint restore <id> Home.md   restore a single file"
        ),
    )
    p.add_argument(
        "action",
        nargs="?",
        choices=["list", "diff", "restore"],
        help="list snapshots, diff against the last one, or restore from one; "
        "omit to take a snapshot",
    )
    p.add_argument(
        "checkpoint_id",
        nargs="?",
        help="checkpoint id to restore (from `onyxian checkpoint list`)",
    )
    p.add_argument(
        "paths",
        nargs="*",
        help="vault-relative paths to restore; omit for the whole vault",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="skip restore's confirmation prompt",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="show what restore would change and write nothing",
    )
    p.add_argument(
        "--quiet", action="store_true", help="print nothing on success (for the SessionStart hook)"
    )
    p.set_defaults(func=cmd_checkpoint)

    p = sub.add_parser(
        "hook", description="internal hooks invoked by Claude Code (not for interactive use)"
    )
    hook_sub = p.add_subparsers(dest="hook_command", required=True)
    p_sc = hook_sub.add_parser(
        "scope-check",
        parents=[_common(vault=True)],
        help="PreToolUse gate: allow/deny/ask a Bash command against an agent's write scope",
    )
    p_sc.add_argument("--agent", required=True, help="the agent whose write scope to enforce")
    p_sc.set_defaults(func=cmd_hook_scope_check)

    p = sub.add_parser(
        "modules",
        help="list available modules, their variables, and defaults (read-only); "
        "`modules new` and `modules lint` are the authoring tools",
    )
    p.add_argument(
        "--vault", help="also list external modules installed in this vault under .vault/modules/"
    )
    p.set_defaults(func=cmd_modules)
    modules_sub = p.add_subparsers(dest="modules_command")
    p_mod_new = modules_sub.add_parser(
        "new", help="scaffold a module skeleton that validates out of the box"
    )
    p_mod_new.add_argument("id", help="module id, kebab-case")
    p_mod_new.add_argument(
        "--dir", default=".", help="directory to scaffold into (default: current directory)"
    )
    p_lint = modules_sub.add_parser(
        "lint",
        help="check a module against the authoring conventions "
        "(read-only; exits 2 on any warning or failure, 0 when clean)",
    )
    p_lint.add_argument(
        "path", nargs="?", default=".", help="the module directory (default: current directory)"
    )
    p_lint.add_argument("--json", action="store_true", help=_JSON_HELP)

    p = sub.add_parser(
        "add",
        parents=[_common(vault=True, dry_run="show the plan and write nothing")],
        help="enable a module and apply immediately: manifest defaults, --var overrides",
        epilog=(
            "examples:\n"
            "  onyxian add fitness                             manifest defaults, applied now\n"
            "  onyxian add fitness --var root=Health           override one variable\n"
            "  onyxian add https://github.com/me/mod --trust   third-party module, consented"
        ),
    )
    p.add_argument("module", help="module id to enable (dependencies are added automatically)")
    p.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="override one module variable (repeatable); manifest defaults fill the rest",
    )
    p.add_argument("--answers", help="answers file supplying the module's variable values")
    p.add_argument(
        "--trust",
        action="store_true",
        help="accept a third-party module's trust warning without prompting "
        "(required for scripted external installs; instruction content always needs this consent)",
    )
    p.set_defaults(func=cmd_add)

    p = sub.add_parser(
        "adopt",
        parents=[_common(dry_run="scan, map, and show the plan; write nothing")],
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
        parents=[_common(vault=True, yes=True, dry_run="show the update plan and write nothing")],
        help="upgrade module assets and pinned sources — zero overwrites of modified files",
        epilog=(
            "examples:\n"
            "  onyxian update --dry-run   preview everything that would change\n"
            "  onyxian update             upgrade all modules and pinned sources\n"
            "  onyxian update fitness     upgrade one module only"
        ),
    )
    p.add_argument("module", nargs="?", help="one module or source to update (default: everything)")
    p.add_argument(
        "--answers",
        help="answers file supplying variables newly required by an updated module",
    )
    p.add_argument(
        "--trust",
        action="store_true",
        help="accept changed third-party agent/skill instructions without prompting "
        "(--yes never covers instruction content)",
    )
    p.set_defaults(func=cmd_update)

    p = sub.add_parser(
        "diff",
        parents=[
            _common(
                vault=True, yes=True, dry_run="show what a resolution would do and write nothing"
            )
        ],
        help="inspect and resolve *.new conflict siblings "
        "(read paths exit 2 when anything is listed or shown, 0 when clean)",
        epilog=(
            "examples:\n"
            "  onyxian diff                       list every conflict pair\n"
            "  onyxian diff Guide.md              show one pair's diff\n"
            "  onyxian diff Guide.md --take-new   adopt the shipped version\n"
            "  onyxian diff --resolve             walk every pair interactively"
        ),
    )
    p.add_argument(
        "path",
        nargs="?",
        help="the conflicted file (original or its *.new sibling); omit to list all pairs",
    )
    p.add_argument("--json", action="store_true", help=f"{_JSON_HELP} — the listing only")
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
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser(
        "remove",
        parents=[_common(vault=True, yes=True, dry_run="show what would happen and write nothing")],
        help="disable a module — deletes only unmodified framework-owned files",
    )
    p.add_argument("module", help="module id to remove")
    p.set_defaults(func=cmd_remove)

    p_new = sub.add_parser(
        "new",
        parents=[
            _common(vault=True, yes=True, dry_run="show what would be created; write nothing")
        ],
        help="instantiate a module's scaffold (a course, game, piece, project, ...)",
    )
    p_new.add_argument(
        "scaffold",
        help="which scaffold, as declared by an enabled module (e.g. course, game, piece, project)",
    )
    p_new.add_argument("name", help="the new folder name")
    p_new.set_defaults(func=cmd_new)

    return parser


def main(argv: list[str] | None = None) -> int:
    global _color_on
    _reconfigure_streams()
    _color_on = _detect_color()
    args = build_parser().parse_args(argv)
    try:
        exit_code: int = args.func(args)
        return exit_code
    except OnyxianError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except (KeyboardInterrupt, EOFError):
        print(
            "\ninterrupted; nothing partial was left unrecorded (the ledger is saved per write).",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

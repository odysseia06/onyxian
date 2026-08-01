"""`onyxian doctor` — validate vault state against declared intent.

Read-only by construction: doctor builds the same plan `apply` would and turns
it into findings, then layers on ledger consistency checks. It never modifies
anything; every finding carries the command that would fix it. It shells out for
two checks, both side-effect-free reads: the Obsidian compat probe (a version
query, see compat.py) and — only when checkpoints are enabled — listing the
checkpoint repo's history. Neither can FAIL the vault, and neither creates
anything; no check anywhere in doctor makes a network call.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import compat
from .checkpoints import CheckpointUnavailable, guard_has_run, list_snapshots
from .configio import VAULT_DIR, load_config
from .diff import find_conflicts
from .errors import EXIT_FINDINGS, EXIT_OK, OnyxianError, PathError
from .external import EXTERNAL_REL, verify_module_trust
from .fsio import TMP_SUFFIX, sha256_file
from .intent import build_desired_state
from .lock_reconcile import (
    candidate_provenance,
    inspect_lock_candidates,
    lock_conflict_sibling_paths,
    sync_conflict_sibling_names,
)
from .lockio import load_lock
from .model import KIND_SEEDED, LOCATION_RUNTIME
from .mutex import read_stamp, write_lock_path
from .paths import check_casefold_unique, first_symlink_component, to_native
from .planner import BLOCKED, ORPHANED, STALE, build_plan
from .repo import discover_modules
from .resolve import resolve_modules
from .sources import SOURCE_MODULE_PREFIX, enabled_for_planner

_GIT_PROBE_TIMEOUT = 10  # seconds; doctor's git calls are read-only and must not
# inherit snapshot's 180s budget — a hung git stalled doctor ~6 min, silently (#95)

OK = 0
INFO = 1
WARN = 2
FAIL = 3

_LABEL = {OK: "ok", INFO: "info", WARN: "warn", FAIL: "FAIL"}


@dataclass(frozen=True)
class Finding:
    level: int
    message: str
    suggestion: str = ""


def run_doctor(
    vault_root: Path,
    modules_root: Path,
    *,
    obsidian_probe: Callable[[], str | None] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []

    # Before the config gate: a conflicted sibling is the likely explanation when
    # the config or lockfile itself turns out broken below.
    conflicts = sync_conflict_sibling_names(vault_root)
    if conflicts:
        lock_conflicts = lock_conflict_sibling_paths(vault_root)
        provenance = ""
        if lock_conflicts:
            candidates = inspect_lock_candidates(vault_root, verify_rows=False)
            provenance = "; lock candidates: " + "; ".join(
                candidate_provenance(candidate) for candidate in candidates
            )
            suggestion = (
                "review and repair with `onyxian lock reconcile`; then run Onyxian "
                f"commands from one machine only, or carry {VAULT_DIR}/ between machines "
                "via git"
            )
        else:
            suggestion = (
                "reconcile by hand (keep the correct file, delete the sibling), then run "
                f"Onyxian commands from one machine only, or carry {VAULT_DIR}/ between "
                "machines via git"
            )
        findings.append(
            Finding(
                WARN,
                f"sync-conflict sibling(s) in {VAULT_DIR}/: {', '.join(conflicts)} — "
                f"a file-sync service forked state another machine wrote{provenance}",
                suggestion,
            )
        )

    try:
        config = load_config(vault_root)
        findings.append(Finding(OK, "config parses and is schema-valid"))
    except OnyxianError as exc:
        findings.append(Finding(FAIL, f"config: {exc}"))
        return findings

    try:
        library = discover_modules(modules_root, vault_root)
        manifests = resolve_modules(config, library)
        findings.append(Finding(OK, f"module set resolves: {', '.join(m.name for m in manifests)}"))
    except OnyxianError as exc:
        findings.append(Finding(FAIL, f"modules: {exc}"))
        return findings

    try:
        desired = build_desired_state(config, manifests)
        findings.append(
            Finding(
                OK,
                f"intent renders cleanly ({len(desired.files)} files, {len(desired.dirs)} folders)",
            )
        )
    except OnyxianError as exc:
        findings.append(Finding(FAIL, f"intent: {exc}"))
        return findings

    try:
        # Unlike operational callers, doctor must inspect casefold-colliding rows
        # so it can name both spellings and give the existing manual repair ramp.
        lock = load_lock(vault_root, diagnose_casefold_collisions=True)
        findings.append(Finding(OK, f"lockfile parses ({len(lock.entries)} entries)"))
    except OnyxianError as exc:
        findings.append(Finding(FAIL, f"lockfile: {exc}"))
        return findings

    # The planner rejects case-twin *desired* paths at plan time (#8), but nothing
    # checked the ledger itself. Rows that are two files on Linux are one file on the
    # macOS/Windows defaults, so a vault carried across reads healthy on exactly one
    # of them — and no command retires an arbitrary row, hence the by-hand ramp (#59).
    ledger_casefold_unique = True
    try:
        check_casefold_unique([(e.path, e.module) for e in lock.sorted_entries()])
    except PathError as exc:
        ledger_casefold_unique = False
        findings.append(
            Finding(
                WARN,
                f"ledger rows collide: {exc}",
                "one spelling is a ghost here; keep the file you actually have and delete "
                f"the other row from {VAULT_DIR}/lock.json — the engine will not pick for you",
            )
        )

    # Integrity of each external module's reviewed copy under .vault/modules/<id>/, which
    # plan/apply render from. A recorded baseline that no longer matches means it was
    # changed out of band (#48); a missing baseline predates the check.
    tampered, unverified = verify_module_trust(vault_root, config, lock)
    for mod_id in tampered:
        findings.append(
            Finding(
                FAIL,
                f"external module {mod_id!r}: its reviewed copy under {EXTERNAL_REL}/ changed "
                "since you trusted it (integrity check failed)",
                f"re-review with `onyxian update {mod_id}` (or remove and re-add), or restore "
                "the copy from version control",
            )
        )
    for mod_id in unverified:
        findings.append(
            Finding(
                INFO,
                f"external module {mod_id!r}: no integrity baseline recorded (installed before "
                "baselines existed); its reviewed copy is not verified",
                f"`onyxian update {mod_id}` records one",
            )
        )

    # Conflict-delivery state that lives entirely in the ledger, which the plan cannot express: a
    # delivered sibling is a planner no-op, and a leftover row has no desired file to
    # plan from at all. Both are `onyxian diff`'s business, so ask it (#59).
    pairs, leftovers = find_conflicts(vault_root, desired, lock)
    leftover_paths = {lo.entry.path for lo in leftovers}
    desired_paths = {f.path for f in desired.files}

    missing: list[str] = []
    modified: list[str] = []
    missing_src: list[str] = []
    symlinked: list[str] = []
    for entry in lock.sorted_entries():
        if entry.path in leftover_paths:
            continue  # reported below, with the ramp that actually retires it
        # Reserved, not dead: no engine code writes outside the vault yet (see
        # `LockEntry`), so only a hand-edited lockfile reaches this. Kept
        # because the alternative for such a row is a permanent bogus "missing
        # from disk" WARN for a path that was never the vault's to hold (#70).
        if entry.location == LOCATION_RUNTIME:
            findings.append(
                Finding(
                    INFO,
                    f"runtime-installed entry {entry.path!r} lives outside the vault; not verified",
                )
            )
            continue
        native = to_native(vault_root, entry.path)
        if entry.kind == KIND_SEEDED:
            continue  # seeded files belong to the user, present or not
        # A link to identical bytes hashes clean, so the sha checks below would
        # call it healthy while any write would replace the link (issue #53).
        link = first_symlink_component(vault_root, entry.path)
        if link is not None:
            symlinked.append(entry.path if link == entry.path else f"{entry.path} (via {link})")
            continue
        if not native.is_file():
            if entry.module.startswith(SOURCE_MODULE_PREFIX):
                missing_src.append(entry.path)
            elif entry.path in desired_paths:
                missing.append(entry.path)
            # A row intent no longer asks for is not restorable: `_plan_file` walks
            # desired files only, so `onyxian apply` would plan nothing and the WARN
            # would stand forever (#59). The planner's own orphaned/stale report
            # below names such a row, with a ramp that can actually retire it.
        elif sha256_file(native) != entry.sha256:
            modified.append(entry.path)
    if missing:
        findings.append(
            Finding(
                WARN,
                f"managed file(s) missing from disk: {', '.join(missing)}",
                "run `onyxian apply` to restore",
            )
        )
    if missing_src:
        findings.append(
            Finding(
                WARN,
                f"source-installed file(s) missing from disk: {', '.join(missing_src)}",
                "`onyxian update` reinstalls declared sources",
            )
        )
    if modified:
        findings.append(
            Finding(
                INFO,
                f"managed file(s) customized by you: {', '.join(modified)}",
                "fine to keep; future updates will land beside them as *.new",
            )
        )
    if symlinked:
        findings.append(
            Finding(
                WARN,
                f"managed path(s) shadowed by a symlink: {', '.join(symlinked)}",
                "the engine never writes through or replaces links; replace the link "
                "with a regular file to let updates land again",
            )
        )
    if pairs:
        findings.append(
            Finding(
                WARN,
                "update(s) waiting beside your customized file(s): "
                f"{', '.join(p.new_path for p in pairs)}",
                "`onyxian diff` shows each one; `onyxian diff --resolve` takes or declines it",
            )
        )
    if leftovers:
        findings.append(
            Finding(
                WARN,
                "leftover ledger row(s) for already-resolved conflicts: "
                f"{', '.join(sorted(leftover_paths))}",
                "`onyxian diff --resolve` retires them; `onyxian apply` plans nothing here",
            )
        )

    # A broken ledger was diagnosed above; asking the planner to reinterpret its
    # case-aliasing rows would now fail closed (#56) and hide that repair advice.
    if ledger_casefold_unique:
        try:
            plan = build_plan(vault_root, desired, lock, enabled_for_planner(config))
        except PathError as exc:
            findings.append(
                Finding(
                    FAIL,
                    f"intent and ledger paths collide: {exc}",
                    "if this is a deliberate case-only managed-path move, declare it under "
                    "`renames:` in the module manifest; otherwise restore the prior spelling "
                    "or choose a genuinely different path, then re-run doctor",
                )
            )
        else:
            if plan.is_empty:
                findings.append(Finding(OK, "vault matches the declared intent; nothing pending"))
            else:
                findings.append(
                    Finding(
                        WARN,
                        f"{len(plan.mutating)} change(s) pending",
                        "review with `onyxian plan`, then `onyxian apply`",
                    )
                )
            for action in plan.reports:
                if action.type == BLOCKED:
                    findings.append(Finding(WARN, f"blocked: {action.detail} ({action.target})"))
                elif action.type == ORPHANED:
                    findings.append(
                        Finding(WARN, f"orphaned lock entry {action.path!r}: {action.detail}")
                    )
                elif action.type == STALE:
                    findings.append(
                        Finding(INFO, f"stale lock entry {action.path!r}: {action.detail}")
                    )

    findings.extend(_litter_findings(vault_root))

    extra_runtimes = [r for r in config.runtimes if r != "claude-code"]
    if extra_runtimes:
        findings.append(
            Finding(
                INFO,
                f"runtimes {extra_runtimes} declared: the vault-side AGENTS.md is generated and "
                "checked by the plan; home-directory skill installs (Codex/OpenCode) are a "
                "later consent-gated flow",
            )
        )
    if config.sources:
        findings.append(
            Finding(INFO, "sources declared; pin reachability is not checked (network-bound)")
        )
    if config.checkpoints:
        findings.append(_checkpoint_finding(vault_root))

    probe = obsidian_probe if obsidian_probe is not None else compat.probe_obsidian_version
    findings.append(_obsidian_compat_finding(probe()))

    return findings


def _litter_findings(vault_root: Path) -> list[Finding]:
    """What the engine itself leaves behind when a run dies mid-flight (#59).

    Neither state is unsafe and neither is ever cleaned up automatically ("no force
    flags"), but both are invisible everywhere else: a `*.onyxian-tmp` just sits in
    the vault looking like a note, and a stranded `apply.lock` makes every writing
    command refuse the vault — including the `onyxian apply` doctor keeps suggesting.
    """
    findings: list[Finding] = []
    strays = sorted(
        p.relative_to(vault_root).as_posix()
        for p in vault_root.rglob(f"*{TMP_SUFFIX}")
        if p.is_file()
    )
    if strays:
        findings.append(
            Finding(
                INFO,
                f"half-written temp file(s) from an interrupted run: {', '.join(strays)}",
                "the real files are intact (writes are atomic); delete these by hand",
            )
        )
    write_lock = write_lock_path(vault_root)
    if write_lock.is_file():
        pid, started = read_stamp(write_lock)
        findings.append(
            Finding(
                WARN,
                f"a write lock is held on this vault (pid {pid}, started {started}); "
                "every command that writes will refuse it while it is there",
                f"if no onyxian process is running, delete {VAULT_DIR}/apply.lock and re-run",
            )
        )
    return findings


def _checkpoint_finding(vault_root: Path) -> Finding:
    """The checkpoint guard's own health, for vaults that opted in (#93).

    Every way the guard can fail now degrades to one stderr line from a `--quiet`
    SessionStart hook (#60) — right, but quiet, and a runtime may never show it. So a
    vault whose git is missing or whose checkpoint repo is unreadable looks protected
    and is not, until the user reaches for a recovery net that was never there. This
    is the row that says so. Read-only like the rest of doctor: it lists, it never
    snapshots, and it never brings the checkpoint repo into existence.
    """
    try:
        snapshots = list_snapshots(vault_root, timeout=_GIT_PROBE_TIMEOUT)
    except CheckpointUnavailable as exc:
        return Finding(
            WARN,
            f"checkpoints are enabled but the guard cannot run: {exc}",
            "fix that, or set framework.checkpoints: false — until then no snapshot "
            "is being taken and there is nothing to restore from",
        )
    if not snapshots:
        # An empty history is ambiguous, and the ambiguity is the whole point: git
        # is never even invoked when the repo does not exist, so a guard that has
        # been failing since day one looks identical to one that has not run yet —
        # the permanently-broken case #93 is about. `guard_has_run` is the
        # discriminator (a vault too read-only to leave the dir behind fails
        # doctor's ledger checks anyway).
        if guard_has_run(vault_root):
            return Finding(
                WARN,
                # "not readable", not "never taken": this also fires on a repo whose
                # history exists but whose ref is corrupt, where "never" would be a lie.
                "checkpoints are enabled and the guard has run, but no snapshot is "
                "readable — it is failing silently",
                "`onyxian checkpoint` prints git's own reason; until it succeeds there is "
                "nothing to restore from",
            )
        return Finding(
            INFO,
            "checkpoints are enabled but none has been taken yet",
            "`onyxian checkpoint` creates a baseline (a Claude Code session start does it for you)",
        )
    return Finding(
        OK,
        f"checkpoints: {len(snapshots)} snapshot(s), newest {snapshots[0].when}",
    )


def _obsidian_compat_finding(installed: str | None) -> Finding:
    """Warning-only compat drift check against compat.VERIFIED_OBSIDIAN — never FAIL."""
    if installed is None:
        return Finding(
            INFO,
            "obsidian CLI not found; Obsidian compat not checked (the vault works as plain files)",
        )
    if not installed:
        return Finding(
            INFO,
            "obsidian CLI found but its version could not be determined (is Obsidian running?); "
            "compat not checked",
        )
    verified = compat.VERIFIED_OBSIDIAN
    drift = compat.classify_drift(installed, verified)
    if drift == "match":
        return Finding(
            OK,
            f"Obsidian {installed} matches the version this release's agent instructions were "
            "verified against",
        )
    if drift == "patch-newer":
        return Finding(
            INFO,
            f"Obsidian {installed} is a patch ahead of the verified {verified}; "
            "agent instructions are probably fine",
        )
    if drift == "newer":
        return Finding(
            WARN,
            f"Obsidian {installed} is newer than {verified}, the version this release's "
            "agent instructions were verified against",
            "agent CLI command ids/behaviors may have drifted; check for a newer onyxian release, "
            "then `onyxian update` delivers refreshed instructions",
        )
    return Finding(
        INFO,
        f"Obsidian {installed} is older than the verified {verified}; instructions may reference "
        "commands your version lacks — consider updating Obsidian",
    )


_VERDICT = {
    OK: "healthy",
    INFO: "healthy (notes above)",
    WARN: "needs attention",
    FAIL: "broken",
}


def _worst(findings: list[Finding]) -> int:
    return max((f.level for f in findings), default=OK)


def render_findings(findings: list[Finding], *, subject: str = "vault") -> str:
    """The prose report. ``subject`` names what was inspected — a vault for `doctor`,
    a module for `modules lint` (#75); the finding vocabulary is the same for both."""
    lines = []
    for f in findings:
        lines.append(f"{_LABEL[f.level]:>4}: {f.message}")
        if f.suggestion:
            lines.append(f"      -> {f.suggestion}")  # aligned under the message (#133)
    lines.append(f"{subject} verdict: {_VERDICT[_worst(findings)]}")
    return "\n".join(lines)


def findings_json(findings: list[Finding]) -> dict[str, object]:
    """The same report as `render_findings`, for scripts and the agent layer (#66)."""
    worst = _worst(findings)
    return {
        "level": _LABEL[worst].lower(),
        "verdict": _VERDICT[worst],
        "exit_code": exit_code(findings),
        "findings": [
            {"level": _LABEL[f.level].lower(), "message": f.message, "suggestion": f.suggestion}
            for f in findings
        ],
    }


def exit_code(findings: list[Finding]) -> int:
    """WARN and FAIL are both *findings*: `--json`'s `level` is what separates them,
    because exit 1 has to stay reserved for a doctor run that could not happen."""
    return EXIT_OK if _worst(findings) <= INFO else EXIT_FINDINGS

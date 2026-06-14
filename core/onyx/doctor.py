"""`onyx doctor` — validate vault state against declared intent (KICKSTART.md §9.4).

Read-only by construction: doctor builds the same plan `apply` would and turns
it into findings, then layers on ledger consistency checks. It never modifies
anything; every finding carries the command that would fix it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .configio import load_config
from .errors import OnyxError
from .fsio import sha256_file
from .intent import build_desired_state
from .lockio import load_lock
from .model import KIND_SEEDED, LOCATION_RUNTIME
from .paths import to_native
from .planner import BLOCKED, ORPHANED, STALE, build_plan
from .repo import discover_modules
from .resolve import resolve_modules
from .sources import SOURCE_MODULE_PREFIX, enabled_for_planner

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


def run_doctor(vault_root: Path, modules_root: Path) -> list[Finding]:
    findings: list[Finding] = []

    try:
        config = load_config(vault_root)
        findings.append(Finding(OK, "config parses and is schema-valid"))
    except OnyxError as exc:
        findings.append(Finding(FAIL, f"config: {exc}"))
        return findings

    try:
        library = discover_modules(modules_root, vault_root)
        manifests = resolve_modules(config, library)
        findings.append(
            Finding(OK, f"module set resolves: {', '.join(m.name for m in manifests)}")
        )
    except OnyxError as exc:
        findings.append(Finding(FAIL, f"modules: {exc}"))
        return findings

    try:
        desired = build_desired_state(config, manifests)
        findings.append(Finding(OK, f"intent renders cleanly ({len(desired.files)} files, {len(desired.dirs)} folders)"))
    except OnyxError as exc:
        findings.append(Finding(FAIL, f"intent: {exc}"))
        return findings

    try:
        lock = load_lock(vault_root)
        findings.append(Finding(OK, f"lockfile parses ({len(lock.entries)} entries)"))
    except OnyxError as exc:
        findings.append(Finding(FAIL, f"lockfile: {exc}"))
        return findings

    missing, modified, missing_src = [], [], []
    for entry in lock.sorted_entries():
        if entry.location == LOCATION_RUNTIME:
            findings.append(
                Finding(INFO, f"runtime-installed entry {entry.path!r} not verified (arrives in M3)")
            )
            continue
        native = to_native(vault_root, entry.path)
        if entry.kind == KIND_SEEDED:
            continue  # seeded files belong to the user, present or not
        if not native.is_file():
            (missing_src if entry.module.startswith(SOURCE_MODULE_PREFIX) else missing).append(entry.path)
        elif sha256_file(native) != entry.sha256:
            modified.append(entry.path)
    if missing:
        findings.append(
            Finding(WARN, f"managed file(s) missing from disk: {', '.join(missing)}", "run `onyx apply` to restore")
        )
    if missing_src:
        findings.append(
            Finding(
                WARN,
                f"source-installed file(s) missing from disk: {', '.join(missing_src)}",
                "`onyx update` (M3) reinstalls declared sources",
            )
        )
    if modified:
        findings.append(
            Finding(
                INFO,
                f"managed file(s) customized by you: {', '.join(modified)}",
                "fine to keep; future updates will land beside them as *.new (§8.3)",
            )
        )

    plan = build_plan(vault_root, desired, lock, enabled_for_planner(config))
    if plan.is_empty:
        findings.append(Finding(OK, "vault matches the declared intent; nothing pending"))
    else:
        findings.append(
            Finding(WARN, f"{len(plan.mutating)} change(s) pending", "review with `onyx plan`, then `onyx apply`")
        )
    for action in plan.reports:
        if action.type == BLOCKED:
            findings.append(Finding(WARN, f"blocked: {action.detail} ({action.target})"))
        elif action.type == ORPHANED:
            findings.append(Finding(WARN, f"orphaned lock entry {action.path!r}: {action.detail}"))
        elif action.type == STALE:
            findings.append(Finding(INFO, f"stale lock entry {action.path!r}: {action.detail}"))

    extra_runtimes = [r for r in config.runtimes if r != "claude-code"]
    if extra_runtimes:
        findings.append(
            Finding(
                INFO,
                f"runtimes {extra_runtimes} declared: the vault-side AGENTS.md is generated and checked "
                "by the plan; home-directory skill installs (Codex/OpenCode) are a later consent-gated flow",
            )
        )
    if config.sources:
        findings.append(Finding(INFO, "sources declared; pin reachability checks are network-bound and opt-in (M1)"))

    return findings


def render_findings(findings: list[Finding]) -> str:
    lines = []
    for f in findings:
        suffix = f"  -> {f.suggestion}" if f.suggestion else ""
        lines.append(f"{_LABEL[f.level]:>4}: {f.message}{suffix}")
    worst = max((f.level for f in findings), default=OK)
    verdict = {OK: "healthy", INFO: "healthy (notes above)", WARN: "needs attention", FAIL: "broken"}[worst]
    lines.append(f"vault verdict: {verdict}")
    return "\n".join(lines)


def exit_code(findings: list[Finding]) -> int:
    worst = max((f.level for f in findings), default=OK)
    return {OK: 0, INFO: 0, WARN: 1, FAIL: 2}[worst]

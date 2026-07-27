"""`onyxian adopt` machinery: scan, map, claim (KICKSTART.md §9.3).

Adopting is additive by construction, not by discipline: adopt starts from an
*empty* lock, so the planner can only ever produce creates, relocks (identical
bytes), and blocked reports — update/restore/conflict actions are impossible.
Claiming never moves or renames anything; a claim is just a proposed value for
a module variable, so the module's new assets land inside the user's existing
structure. Anything ambiguous goes to a human checklist, never to an action.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .configio import CONFIG_REL, default_config
from .fsio import sha256_file
from .intent import DesiredState
from .interview import Answers, collect_module_config, resolved_sources
from .model import KIND_SEEDED, Config, Lock, LockEntry, Manifest
from .paths import first_symlink_component, to_native
from .planner import CREATE, CREATE_DIR, RELOCK, Plan, describe, render_plan
from .render import _style_segment  # the one canonical segment transform
from .resolve import dependency_closure

_VAR_SEGMENT_RE = re.compile(r"^\{\{\s*([a-z][a-z0-9_]*)\s*\}\}$")
_STYLES = ("Title-Case-Hyphen", "kebab-case", "Spaces")


# ----------------------------------------------------------------- scanning


def infer_folder_style(names: list[str]) -> str:
    """Best guess at the vault's existing naming style; a default, never a verdict."""
    kebab = sum(1 for n in names if n == n.lower() and " " not in n)
    spaces = sum(1 for n in names if " " in n)
    title = len(names) - kebab - spaces
    best = max(
        ("Title-Case-Hyphen", title), ("kebab-case", kebab), ("Spaces", spaces), key=lambda t: t[1]
    )
    return best[0] if best[1] > 0 else "Title-Case-Hyphen"


def _style_variants(segment: str) -> set[str]:
    return {_style_segment(segment, style) for style in _STYLES}


def _root_shapes(manifest: Manifest) -> dict[str, set[str]]:
    """variable key -> the literal child segments its paths put directly under `{{var}}/`."""
    shapes: dict[str, set[str]] = {}
    declared = {v.key for v in manifest.variables if v.type == "string"}
    raw_paths = list(manifest.folders) + [
        f.install_path for f in (*manifest.templates, *manifest.bases, *manifest.seeds)
    ]
    for raw in raw_paths:
        segments = raw.split("/")
        match = _VAR_SEGMENT_RE.match(segments[0])
        if not match or match.group(1) not in declared:
            continue
        key = match.group(1)
        shapes.setdefault(key, set())
        if len(segments) > 1 and not _VAR_SEGMENT_RE.match(segments[1]):
            shapes[key].add(segments[1])
    return shapes


@dataclass(frozen=True)
class Claim:
    module: str
    var: str
    value: str
    reason: str


@dataclass
class ScanResult:
    style: str
    claims: list[Claim] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    top_dirs: list[str] = field(default_factory=list)


def scan_vault(target: Path, library: dict[str, Manifest]) -> ScanResult:
    """Classify the existing top-level tree against known module shapes (§9.3 steps 1-2)."""
    top_dirs = sorted(e.name for e in target.iterdir() if e.is_dir() and not e.name.startswith("."))
    result = ScanResult(style=infer_folder_style(top_dirs), top_dirs=top_dirs)

    # (module, var) -> {candidate dir -> reason}
    matches: dict[tuple[str, str], dict[str, str]] = {}
    for manifest in library.values():
        defaults = {v.key: v.default for v in manifest.variables}
        for var_key, children in _root_shapes(manifest).items():
            for dir_name in top_dirs:
                reasons = []
                default = defaults.get(var_key)
                if isinstance(default, str) and dir_name in _style_variants(default):
                    reasons.append(f"name matches the default {default!r}")
                if children:
                    hits = [
                        child
                        for child in sorted(children)
                        if any(
                            (target / dir_name / variant).exists()
                            for variant in _style_variants(child)
                        )
                    ]
                    if len(hits) * 2 >= len(children):
                        reasons.append(f"contains {', '.join(hits)}")
                if reasons:
                    matches.setdefault((manifest.name, var_key), {})[dir_name] = "; ".join(reasons)

    claimed_dirs: dict[str, tuple[str, str]] = {}
    for (module, var_key), candidates in sorted(matches.items()):
        if len(candidates) > 1:
            result.ambiguities.append(
                f"module {module!r}: folders {sorted(candidates)} all look "
                f"like its {var_key!r} root; "
                "claim one by setting the variable yourself, or leave the module disabled"
            )
            continue
        dir_name, reason = next(iter(candidates.items()))
        if dir_name in claimed_dirs:
            other_module, other_var = claimed_dirs[dir_name]
            result.ambiguities.append(
                f"folder {dir_name!r} matches both {other_module}.{other_var} "
                f"and {module}.{var_key}; "
                "claiming neither — set the variable on the module you mean"
            )
            result.claims = [
                c for c in result.claims if not (c.module == other_module and c.var == other_var)
            ]
            continue
        claimed_dirs[dir_name] = (module, var_key)
        result.claims.append(Claim(module=module, var=var_key, value=dir_name, reason=reason))

    return result


# ----------------------------------------------------------------- intent


def build_adopt_config(
    target: Path, library: dict[str, Manifest], answers: Answers | None, scan: ScanResult
) -> Config:
    """Adopt's intent: answers win; scan results are defaults, never decisions (§9.3).

    Everything here is computation over the scan and the answers file — no prompt, no
    write, no network — so the caller can render the review and the acceptance token
    from a Config it knows nothing was asked about.
    """
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
    for mod_id in dependency_closure(enabled, library):
        enabled.setdefault(mod_id, {})

    return default_config(
        vault_name=vault_name,
        folder_style=folder_style,
        runtimes=runtimes,
        modules={
            mod_id: collect_module_config(
                library[mod_id], enabled[mod_id], interactive=False, folder_style=folder_style
            )
            for mod_id in sorted(enabled, key=lambda m: (m != "core", m))
        },
        sources=resolved_sources(answers, runtimes),
    )


# ----------------------------------------------------------------- claiming & review


@dataclass(frozen=True)
class SeedClaim:
    path: str
    module: str


def claim_existing_seeds(vault_root: Path, desired: DesiredState, lock: Lock) -> list[SeedClaim]:
    """Existing files at seed paths become the seeds, at their current content (§8.2).

    Seeded files are user-owned from the moment they exist — and here they
    existed before we did. Claiming records them in the ledger so the engine
    never proposes them again; their bytes are never read into, compared
    against, or replaced by the asset.
    """
    claims: list[SeedClaim] = []
    for intent in desired.files:
        if intent.kind != KIND_SEEDED or lock.get(intent.path) is not None:
            continue
        native = to_native(vault_root, intent.path)
        # Never claim through a symlink: the recorded hash would be the link
        # target's — a file the module does not own (issue #53). The planner
        # reports the path blocked instead, onto the adopt checklist.
        if native.is_file() and first_symlink_component(vault_root, intent.path) is None:
            lock.put(
                LockEntry(
                    path=intent.path,
                    sha256=sha256_file(native),
                    module=intent.module,
                    module_version=intent.module_version,
                    kind=KIND_SEEDED,
                )
            )
            claims.append(SeedClaim(path=intent.path, module=intent.module))
    return claims


ADDITIVE_TYPES = frozenset({CREATE_DIR, CREATE, RELOCK})


def assert_additive(plan: Plan) -> None:
    """Adopt's invariant: with a fresh lock the plan can only add. A violation is an engine bug."""
    offenders = [a for a in plan.mutating if a.type not in ADDITIVE_TYPES]
    if offenders:  # pragma: no cover - reaching this means the planner broke its contract
        raise AssertionError(
            f"adopt produced non-additive actions: {[(a.type, a.path) for a in offenders]}"
        )


def render_adopt_review(
    target: Path,
    config: Config,
    scan: ScanResult,
    plan: Plan,
    seed_claims: list[SeedClaim],
) -> list[str]:
    """The mandatory review, exactly as the user must read it before accepting (§9.3 step 4)."""
    lines = [
        f"adopting: {target}  (vault {config.vault_name!r}, folder style {config.folder_style})"
    ]
    shown_claims = [c for c in scan.claims if c.module in config.modules]
    if shown_claims:
        lines.append("claims (existing folders mapped to module variables; nothing moves):")
        lines += [f"  = {c.value}/  ->  {c.module}.{c.var}  [{c.reason}]" for c in shown_claims]
    unused_claims = [c for c in scan.claims if c.module not in config.modules]
    if unused_claims:
        lines.append("also matched, but those modules are not in your set (enable them to claim):")
        lines += [f"  ? {c.value}/ looks like {c.module}.{c.var}" for c in unused_claims]
    if seed_claims:
        lines.append("existing files claimed as seeds (recorded as yours; never touched):")
        lines += [f"  = {sc.path}  ({sc.module})" for sc in seed_claims]
    lines.append(render_plan(plan))
    lines.append(f"  + {CONFIG_REL} (seeded; yours to edit)")
    lines.append("  + .vault/lock.json (the engine's ledger)")
    if scan.ambiguities:
        lines.append("checklist — decide these yourself; the engine will not:")
        lines += [f"  ? {note}" for note in scan.ambiguities]
    lines.append(
        "guarantee: adopt is additive only; nothing existing is moved, "
        "renamed, deleted, or overwritten."
    )
    return lines


def acceptance_token(config_text: str, plan: Plan, seed_claims: list[SeedClaim]) -> str:
    """Fingerprint of exactly what was reviewed; apply requires it back unchanged (§9.3 step 5)."""
    h = hashlib.sha256()
    h.update(config_text.encode("utf-8"))
    for action in plan.actions:
        h.update(describe(action).encode("utf-8"))
        # `describe` carries paths, types, and modules but no content, and module
        # versions can stay put while the bytes behind them move (an ONYXIAN_HOME
        # or dev-checkout swap between review and accept). Fold in the desired sha
        # so the token means the content that was reviewed, not just its shape (#70).
        if action.intent is not None:
            h.update(action.intent.sha256.encode("ascii"))
    for claim in seed_claims:
        h.update(f"seed-claim:{claim.path}:{claim.module}".encode())
    return h.hexdigest()[:12]

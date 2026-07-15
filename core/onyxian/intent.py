"""Build the desired state: what the vault should contain per the config (KICKSTART.md §4.1).

The desired state is a pure value — rendered bytes and portable paths, fully
deterministic for a given (config, module library, ONYXIAN_NOW). The planner
diffs it against the lock and the disk; nothing here touches the vault.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass

from .errors import ResolveError
from .fsio import encode_text, read_text, sha256_bytes
from .model import KIND_MANAGED, KIND_SEEDED, Config, Manifest
from .render import RenderContext, render_path, render_text
from .resolve import resolve_variables

ENV_NOW = "ONYXIAN_NOW"
START_HERE_PATH = "Start-Here.md"


def resolve_today() -> str:
    """Today's ISO date, overridable via ONYXIAN_NOW so tests and CI stay byte-exact."""
    override = os.environ.get(ENV_NOW)
    if override:
        try:
            return datetime.date.fromisoformat(override).isoformat()
        except ValueError:
            raise ResolveError(
                f"{ENV_NOW} must be an ISO date (YYYY-MM-DD), got {override!r}"
            ) from None
    return datetime.date.today().isoformat()


@dataclass(frozen=True)
class DirIntent:
    path: str
    module: str


@dataclass(frozen=True)
class FileIntent:
    path: str
    content: bytes
    sha256: str
    kind: str
    module: str
    module_version: str


@dataclass
class DesiredState:
    dirs: list[DirIntent]
    files: list[FileIntent]

    def file_by_path(self) -> dict[str, FileIntent]:
        return {f.path: f for f in self.files}


def _start_here_intent(
    manifests: list[Manifest], core_version: str, *, claude_runtime: bool
) -> FileIntent:
    """The §9.2 "Start here" note: a managed, regenerated summary of the enabled module set.

    Deliberately a pure function of the module set — no dates, no vault name —
    so an unchanged vault plans empty tomorrow too (P3). The one framework note
    without a `created` key; the exception is documented in the conventions.
    """
    lines = [
        "---",
        "type: start-here",
        "status: active",
        "tags: []",
        "---",
        "",
        "# Start here",
        "",
        "Onyxian manages this vault. The engine regenerates this note when your module set changes; the moment you edit it, it is yours, and future versions will arrive beside it as `Start-Here.md.new` instead of overwriting you.",
        "",
        "## Enabled modules",
        "",
    ]
    for manifest in manifests:
        summary = " ".join(manifest.summary.split())
        lines.append(f"- **{manifest.name}** {manifest.version} — {summary}")
    first_actions = [
        (m.name, " ".join(m.post_install.split())) for m in manifests if m.post_install
    ]
    if first_actions:
        lines += ["", "## First actions", ""]
        for name, text in first_actions:
            lines.append(f"- **{name}**: {text}")
    working = [
        "",
        "## Working the vault",
        "",
        "- `.vault/config.yaml` declares your intent. Edit it freely, then run `onyxian plan` to preview the effect and `onyxian apply` to reconcile.",
        "- `onyxian add <module>` enables more modules, `onyxian modules` lists what exists, and `onyxian doctor` checks vault health read-only.",
        "- Everything here works without any agent: templates are plain copies, views are plain files, and deleting `.claude/` costs convenience, never function.",
    ]
    if claude_runtime:
        working.append(
            "- See `Onyxian Assistant.md` for what your assistant can do and what to say."
        )
    working.append("")
    lines += working
    content = encode_text("\n".join(lines))
    return FileIntent(
        path=START_HERE_PATH,
        content=content,
        sha256=sha256_bytes(content),
        kind=KIND_MANAGED,
        module="core",
        module_version=core_version,
    )


_DAILY_NOTE_FORMATS = {
    "YYYY/MM": "YYYY/MM/YYYY-MM-DD",
    "YYYY": "YYYY/YYYY-MM-DD",
    "flat": "YYYY-MM-DD",
}


def build_desired_state(config: Config, manifests: list[Manifest]) -> DesiredState:
    resolved_vars = {
        m.name: resolve_variables(m, config.modules[m.name].vars, folder_style=config.folder_style)
        for m in manifests
    }
    from .render import _style_segment

    # First-party derived values for the daily-notes module: Obsidian's Daily
    # Notes plugin stores a date format (which also encodes the sub-folder
    # layout) and a template path, so that module's .obsidian/daily-notes.json
    # seed can follow the granularity choice and the vault's folder style.
    if "daily-notes" in resolved_vars:
        dn = resolved_vars["daily-notes"]
        dn["daily_format"] = _DAILY_NOTE_FORMATS.get(dn.get("granularity"), "YYYY-MM-DD")
        dn["daily_template"] = "/".join(
            (
                _style_segment("Templates", config.folder_style),
                _style_segment("Daily", config.folder_style),
                "Daily Note",
            )
        )

    globals_ = {
        "today": resolve_today(),
        "vault_name": config.vault_name,
        # The style-resolved name of the core Templates folder, for assets that
        # must reference it (e.g. task queries excluding template files).
        "templates_root": _style_segment("Templates", config.folder_style),
    }

    dirs: dict[str, DirIntent] = {}
    files: dict[str, FileIntent] = {}
    dir_owner: dict[str, str] = {}

    for manifest in manifests:
        ctx = RenderContext(resolved_vars[manifest.name], resolved_vars, globals_)

        for raw_folder in manifest.folders:
            origin = f"module {manifest.name!r}: provides.folders {raw_folder!r}"
            path = render_path(raw_folder, ctx, config.folder_style, is_file=False, origin=origin)
            if path not in dirs:
                dirs[path] = DirIntent(path=path, module=manifest.name)
                dir_owner[path] = manifest.name

        for provided, kind in (
            *((f, KIND_MANAGED) for f in manifest.managed_files),
            *((f, KIND_SEEDED) for f in manifest.seeded_files),
        ):
            origin = f"module {manifest.name!r}: {provided.install_path!r}"
            path = render_path(
                provided.install_path, ctx, config.folder_style, is_file=True, origin=origin
            )
            if path in files:
                other = files[path]
                raise ResolveError(
                    f"install path collision at {path!r}: modules "
                    f"{other.module!r} and {manifest.name!r} both provide it"
                )
            text = render_text(read_text(provided.source), ctx, origin=str(provided.source))
            content = encode_text(text)
            files[path] = FileIntent(
                path=path,
                content=content,
                sha256=sha256_bytes(content),
                kind=kind,
                module=manifest.name,
                module_version=manifest.version,
            )

    # Runtime artifacts and generated content ride the same pipeline (§7.4).
    from .adapters import (  # local import: adapters builds FileIntents from here
        agents_md_intent,
        assistant_guide_intent,
        claude_code_intents,
        claude_orientation_intents,
    )

    extras = claude_code_intents(config, manifests, resolved_vars, globals_)
    core_version = next(m.version for m in manifests if m.name == "core")
    extras.append(
        _start_here_intent(manifests, core_version, claude_runtime="claude-code" in config.runtimes)
    )
    extras.extend(
        claude_orientation_intents(config, manifests, resolved_vars, globals_, core_version)
    )
    assistant = assistant_guide_intent(config, manifests, resolved_vars, globals_, core_version)
    if assistant is not None:
        extras.append(assistant)
    agents_md = agents_md_intent(config, manifests, resolved_vars, globals_, core_version)
    if agents_md is not None:
        extras.append(agents_md)
    for extra in extras:
        if extra.path in files:
            raise ResolveError(
                f"install path collision at {extra.path!r}: modules "
                f"{files[extra.path].module!r} and {extra.module!r} both provide it"
            )
        files[extra.path] = extra

    for path in files:
        if path in dirs:
            raise ResolveError(f"{path!r} is provided both as a folder and as a file")

    return DesiredState(
        dirs=[dirs[k] for k in sorted(dirs)],
        files=[files[k] for k in sorted(files)],
    )

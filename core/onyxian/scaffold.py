"""`onyxian new` — instantiate a module's scaffold (a copy-per-instance template subtree).

Standalone scaffolding: NOT routed through plan/apply (that is the reconcile
model for declared intent). A created instance is the user's content, so it is
never recorded in lock.json — `onyxian update`/`remove` must never reconcile it.
The subtree is rendered from the module ASSETS (raw `{{onyxian.today}}`), so dates
are today, not the frozen literal a one-time seed would bake. References to the
subtree's own path (a Base's `file.inFolder(...)` filter cannot self-scope) are
repointed at the new instance, so no copy needs a manual edit.
"""

from __future__ import annotations

from pathlib import Path

from .configio import load_config
from .errors import OnyxianError, PathError
from .fsio import read_text, write_text_atomic
from .model import Config, Manifest
from .paths import split_portable, to_native
from .render import RenderContext, _style_segment, render_path, render_text
from .repo import discover_modules
from .resolve import resolve_variables


def _prepare(
    vault_root: Path, scaffold: str, name: str, modules_root: Path, *, today: str
) -> tuple[Config, Manifest, RenderContext, str, str, str, Path]:
    """Every scaffold precondition, no writes. Returns what the copy step needs."""
    config = load_config(vault_root)
    library = discover_modules(modules_root, vault_root)

    providers = [
        (mod_id, library[mod_id])
        for mod_id in sorted(config.modules)
        if mod_id in library and any(s.name == scaffold for s in library[mod_id].scaffolds)
    ]
    if not providers:
        offering = sorted(
            mod_id
            for mod_id, manifest in library.items()
            if any(s.name == scaffold for s in manifest.scaffolds)
        )
        if offering:
            hints = " or ".join(f"`onyxian add {mod_id}`" for mod_id in offering)
            raise OnyxianError(
                f"scaffold {scaffold!r} is provided by the {' / '.join(offering)} module, "
                f"which is not enabled in this vault; enable it with {hints} first"
            )
        available = sorted(
            s.name
            for mod_id in config.modules
            if mod_id in library
            for s in library[mod_id].scaffolds
        )
        raise OnyxianError(
            f"unknown scaffold {scaffold!r}; "
            f"scaffolds available in this vault: {', '.join(available) if available else 'none'}"
        )
    if len(providers) > 1:
        mods = ", ".join(mod_id for mod_id, _ in providers)
        raise OnyxianError(
            f"scaffold {scaffold!r} is provided by more than one enabled module ({mods}); "
            f"disable one of them first"
        )
    mod_id, manifest = providers[0]
    source = next(s.source for s in manifest.scaffolds if s.name == scaffold)

    try:
        segments = split_portable(name)
    except PathError as exc:
        raise OnyxianError(f"{name!r} is not a valid {scaffold} name: {exc}") from None
    if len(segments) != 1:
        raise OnyxianError(f"{name!r} must be a single folder name, not a path")

    resolved = {
        m_id: resolve_variables(library[m_id], cfg.vars, folder_style=config.folder_style)
        for m_id, cfg in config.modules.items()
        if m_id in library
    }
    globals_ = {
        "today": today,
        "vault_name": config.vault_name,
        "templates_root": _style_segment("Templates", config.folder_style),
    }
    ctx = RenderContext(resolved[mod_id], resolved, globals_)

    # the template root as it renders on disk (e.g. "Academic/Courses/_Course-Template")
    source_path = render_path(
        source, ctx, config.folder_style, is_file=False, origin=f"scaffold {scaffold!r}"
    )
    parent = source_path.rpartition("/")[0]
    target_portable = f"{parent}/{name}" if parent else name
    target_dir = to_native(vault_root, target_portable)
    if target_dir.exists():
        raise OnyxianError(
            f"{scaffold} {target_portable!r} already exists; "
            f"pick a different name or open the existing folder"
        )
    return config, manifest, ctx, source, source_path, target_portable, target_dir


def validate_scaffold(
    vault_root: Path, scaffold: str, name: str, modules_root: Path, *, today: str
) -> str:
    """Run run_scaffold's precondition checks without writing anything.

    The CLI calls this before its dry-run/confirm gate so a dry run cannot report
    success for an operation that would fail, and the confirm prompt cannot precede
    the error. Returns the portable target path.
    """
    return _prepare(vault_root, scaffold, name, modules_root, today=today)[5]


def run_scaffold(
    vault_root: Path, scaffold: str, name: str, modules_root: Path, *, today: str
) -> str:
    """Instantiate ``scaffold`` as a sibling of its template named ``name``.

    Replays the module's folders and files under the template subtree into the
    new instance, rendered fresh, with every reference to the subtree's own
    path repointed at the instance. Returns the portable target path.
    """
    config, manifest, ctx, source, source_path, target_portable, target_dir = _prepare(
        vault_root, scaffold, name, modules_root, today=today
    )
    prefix = source_path + "/"

    # the subtree's path as it appears in file CONTENT: `{{root}}` substituted but
    # literal segments unstyled — the convention Base filters are authored in
    source_text = render_text(source, ctx, origin=f"scaffold {scaffold!r}")
    target_text = f"{source_text.rpartition('/')[0]}/{name}".lstrip("/")

    def _rehome(rendered: str) -> Path:
        sub = rendered[len(prefix) :]  # path under the template root, e.g. "Exam-Prep"
        return target_dir.joinpath(*sub.split("/"))

    # the working dirs (declared as module folders under the template)
    for raw in manifest.folders:
        rendered = render_path(
            raw, ctx, config.folder_style, is_file=False, origin=f"folder {raw!r}"
        )
        if rendered.startswith(prefix):
            _rehome(rendered).mkdir(parents=True, exist_ok=True)

    # every file the module puts under the template — seeded notes and managed
    # Bases alike — rendered fresh so the date is today, then repointed
    for file in (*manifest.seeds, *manifest.templates, *manifest.bases):
        rendered = render_path(
            file.install_path,
            ctx,
            config.folder_style,
            is_file=True,
            origin=f"file {file.install_path!r}",
        )
        if rendered.startswith(prefix):
            text = render_text(read_text(file.source), ctx, origin=str(file.source))
            write_text_atomic(_rehome(rendered), text.replace(source_text, target_text))

    target_dir.mkdir(
        parents=True, exist_ok=True
    )  # ensure the dir exists even if the template had no files
    return target_portable

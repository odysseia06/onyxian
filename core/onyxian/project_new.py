"""`onyxian project new` — instantiate a projects-software project from its template.

Standalone scaffolding: NOT routed through plan/apply (that is the reconcile
model for declared intent). A created project is the user's content, so it is
never recorded in lock.json — `onyxian update`/`remove` must never reconcile it.
The subtree is rendered from the module ASSETS (raw `{{onyxian.today}}`), so dates
are today, not the frozen literal a one-time seed would bake.
"""
from __future__ import annotations

from pathlib import Path

from .configio import load_config
from .errors import OnyxianError, PathError
from .fsio import read_text, write_text_atomic
from .paths import split_portable, to_native
from .render import RenderContext, _style_segment, render_path, render_text
from .repo import discover_modules
from .resolve import resolve_variables

_PROJECT_MODULE = "projects-software"
_TEMPLATE_SEGMENT = "_Project-Template"


def scaffold_project(vault_root: Path, name: str, modules_root: Path, *, today: str) -> str:
    """Create `<root>/<name>/` from the project template. Returns the portable project path."""
    config = load_config(vault_root)
    if _PROJECT_MODULE not in config.modules:
        raise OnyxianError(
            f"the {_PROJECT_MODULE!r} module is not enabled in this vault; "
            f"enable it with `onyxian add {_PROJECT_MODULE}` first"
        )
    try:
        segments = split_portable(name)
    except PathError as exc:
        raise OnyxianError(f"{name!r} is not a valid project name: {exc}") from None
    if len(segments) != 1:
        raise OnyxianError(f"{name!r} must be a single folder name, not a path")

    library = discover_modules(modules_root)
    manifest = library[_PROJECT_MODULE]
    resolved = {
        mod_id: resolve_variables(library[mod_id], cfg.vars, folder_style=config.folder_style)
        for mod_id, cfg in config.modules.items()
        if mod_id in library
    }
    own = resolved[_PROJECT_MODULE]
    root = own["root"]
    project_portable = f"{root}/{name}"
    project_dir = to_native(vault_root, project_portable)
    if project_dir.exists():
        raise OnyxianError(
            f"project {project_portable!r} already exists; "
            f"pick a different name or open the existing project"
        )

    globals_ = {
        "today": today,
        "vault_name": config.vault_name,
        "templates_root": _style_segment("Templates", config.folder_style),
    }
    ctx = RenderContext(own, resolved, globals_)

    # the template root as it renders on disk (e.g. "Projects/Software/_Project-Template")
    template_root = render_path(
        f"{{{{root}}}}/{_TEMPLATE_SEGMENT}", ctx, config.folder_style,
        is_file=False, origin="onyxian project new",
    )
    prefix = template_root + "/"

    def _rehome(rendered: str) -> Path:
        sub = rendered[len(prefix):]  # path under the template root, e.g. "Devlog"
        return project_dir.joinpath(*sub.split("/"))

    # the four working dirs (declared as module folders under the template)
    for raw in manifest.folders:
        rendered = render_path(raw, ctx, config.folder_style, is_file=False, origin=f"folder {raw!r}")
        if rendered.startswith(prefix):
            _rehome(rendered).mkdir(parents=True, exist_ok=True)

    # the seeded files (the Overview), rendered fresh so the date is today
    for seed in manifest.seeds:
        rendered = render_path(
            seed.install_path, ctx, config.folder_style, is_file=True, origin=f"seed {seed.install_path!r}"
        )
        if rendered.startswith(prefix):
            text = render_text(read_text(seed.source), ctx, origin=str(seed.source))
            write_text_atomic(_rehome(rendered), text)

    project_dir.mkdir(parents=True, exist_ok=True)  # ensure the dir exists even if the template had no files
    return project_portable

"""Resolve the enabled module set and its variables (KICKSTART.md §5).

The config lists every enabled module explicitly; resolution validates rather
than infers. A missing dependency is an error telling the user what to add —
auto-enabling happens in the interview and `add` flows, never silently here.
"""

from __future__ import annotations

from .errors import ResolveError
from .model import Config, Manifest, Variable


def resolve_modules(config: Config, library: dict[str, Manifest]) -> list[Manifest]:
    """Validate the enabled set against the library; return manifests in dependency order."""
    enabled = list(config.modules)

    for mod_id in enabled:
        if mod_id not in library:
            raise ResolveError(
                f"module {mod_id!r} is enabled in config but not in the module library "
                f"(available: {sorted(library)})"
            )
        manifest = library[mod_id]
        pinned = config.modules[mod_id].version
        if pinned != manifest.version:
            raise ResolveError(
                f"module {mod_id!r} is pinned to {pinned} in config but the library ships "
                f"{manifest.version}; version drift is handled by `update` (M3) — for now, "
                f"align the config pin with the library"
            )

    for mod_id in enabled:
        for dep in library[mod_id].depends:
            if dep not in enabled:
                raise ResolveError(
                    f"module {mod_id!r} requires {dep!r}; add it to the modules section"
                )
        for foe in library[mod_id].conflicts:
            if foe in enabled:
                raise ResolveError(f"modules {mod_id!r} and {foe!r} cannot coexist")

    # Topological order, dependencies first, ties broken by name for determinism.
    ordered: list[str] = []
    state: dict[str, int] = {}  # 1 = visiting, 2 = done

    def visit(mod_id: str, chain: tuple[str, ...]) -> None:
        if state.get(mod_id) == 2:
            return
        if state.get(mod_id) == 1:
            cycle = " -> ".join((*chain, mod_id))
            raise ResolveError(f"dependency cycle: {cycle}")
        state[mod_id] = 1
        for dep in sorted(library[mod_id].depends):
            visit(dep, (*chain, mod_id))
        state[mod_id] = 2
        ordered.append(mod_id)

    for mod_id in sorted(enabled):
        visit(mod_id, ())
    return [library[mod_id] for mod_id in ordered]


def _check_type(var: Variable, value: object, *, where: str) -> object:
    if var.type == "string":
        if not isinstance(value, str) or not value.strip():
            raise ResolveError(f"{where} must be a non-empty string, got {value!r}")
        return value
    if var.type == "choice":
        if value not in var.options:
            raise ResolveError(f"{where} must be one of {list(var.options)}, got {value!r}")
        return value
    if var.type == "bool":
        if not isinstance(value, bool):
            raise ResolveError(f"{where} must be true or false, got {value!r}")
        return value
    raise ResolveError(f"{where}: unknown variable type {var.type!r}")  # unreachable


def resolve_variables(
    manifest: Manifest,
    configured: dict[str, object],
    *,
    folder_style: str = "Title-Case-Hyphen",
) -> dict[str, object]:
    """Final variable values for one module: configured value, else declared default.

    String defaults are authored in the canonical Title-Case-Hyphen style and
    follow the vault's folder style when used; configured values are the
    user's exact choice and pass through verbatim (P4).
    """
    from .render import style_default

    declared = {var.key: var for var in manifest.variables}
    unknown = set(configured) - set(declared)
    if unknown:
        raise ResolveError(
            f"module {manifest.name!r} has no variable(s) {sorted(unknown)} "
            f"(declared: {sorted(declared)})"
        )
    values: dict[str, object] = {}
    for key, var in declared.items():
        where = f"modules.{manifest.name}.vars.{key}"
        if key in configured:
            values[key] = _check_type(var, configured[key], where=where)
        elif var.default is not None:
            values[key] = (
                style_default(var.default, folder_style)
                if var.type == "string" and isinstance(var.default, str)
                else var.default
            )
        else:
            raise ResolveError(f"{where} is required and has no default")
    return values

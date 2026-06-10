"""Asset rendering: ``{{variable}}`` substitution and folder-name styling (KICKSTART.md §5.3, §10.2).

Substitution is deliberately primitive — plain string replacement, no
conditionals, no loops. Two placeholder languages coexist in assets and must
never be confused: ``{{...}}`` is the engine's, resolved exactly once here;
``<% tp.* %>`` is Templater's, owned by the user's Obsidian and passed through
byte-for-byte (P2: a template must work as a plain copy).
"""

from __future__ import annotations

import re

from .errors import RenderError
from .paths import split_portable

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*\}\}")


def _normalize_name(name: str) -> str:
    """Module ids are kebab-case but `_` is accepted in references (§7.3 uses both)."""
    return name.replace("-", "_")


class RenderContext:
    """Lookup table for one module's rendering pass.

    Own variables resolve unqualified (``{{root}}``); every enabled module's
    variables resolve qualified (``{{fitness.root}}``); engine globals live
    under ``onyx.`` (``{{onyx.today}}``, ``{{onyx.vault_name}}``).
    """

    def __init__(
        self,
        own: dict[str, object],
        qualified: dict[str, dict[str, object]],
        globals_: dict[str, object],
    ) -> None:
        self._values: dict[str, str] = {}
        for mod_name, values in qualified.items():
            for key, value in values.items():
                self._values[f"{_normalize_name(mod_name)}.{key}"] = _stringify(value)
        for key, value in globals_.items():
            self._values[f"onyx.{key}"] = _stringify(value)
        # Own variables last: an unqualified name always means "this module".
        for key, value in own.items():
            self._values[key] = _stringify(value)

    def lookup(self, name: str) -> str | None:
        return self._values.get(_normalize_name(name) if "." in name else name)


def _stringify(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_text(text: str, ctx: RenderContext, *, origin: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        value = ctx.lookup(name)
        if value is None:
            raise RenderError(f"undefined variable {{{{{name}}}}} in {origin}")
        return value

    return _PLACEHOLDER_RE.sub(replace, text)


def _style_segment(segment: str, style: str) -> str:
    if style == "kebab-case":
        return segment.lower()
    if style == "Spaces":
        return segment.replace("-", " ")
    return segment  # Title-Case-Hyphen is the canonical authored form


def style_default(value: str, style: str) -> str:
    """Folder style applied to a variable *default* (per '/' segment).

    Defaults are authored in the canonical style and are the engine's
    suggestion, so they follow the vault's style; a value the user actually
    chose is theirs verbatim and never goes through this (P4).
    """
    return "/".join(_style_segment(seg, style) for seg in value.split("/"))


def render_path(
    raw: str, ctx: RenderContext, style: str, *, is_file: bool, origin: str
) -> str:
    """Render an install path: substitute variables, then style literal folder segments.

    The folder style applies only to segments authored literally in a manifest;
    a segment that came from a variable is the user's exact chosen name and is
    never transformed. Filenames are never transformed either.
    """
    raw_segments = raw.split("/")
    rendered: list[str] = []
    for i, raw_seg in enumerate(raw_segments):
        is_last = i == len(raw_segments) - 1
        if _PLACEHOLDER_RE.search(raw_seg):
            value = render_text(raw_seg, ctx, origin=origin)
            rendered.extend(value.split("/"))
        elif is_file and is_last:
            rendered.append(raw_seg)
        else:
            rendered.append(_style_segment(raw_seg, style))
    final = "/".join(rendered)
    split_portable(final, origin=origin)
    return final

"""Surgical edits to `.vault/config.yaml` on the user's behalf.

The config is the user's file (§4.4): `add` must not regenerate it wholesale,
because that would destroy their comments and formatting. Instead, new module
entries are inserted textually right after the top-level ``modules:`` line —
every other byte of the file survives untouched — and the result is re-parsed
before anything is written, so a malformed outcome is impossible to commit.
"""

from __future__ import annotations

import json
import re

import yaml

from .configio import module_line, parse_config
from .errors import ConfigError
from .model import Config, ModuleConfig


def _module_block_span(lines: list[str], mod_id: str) -> tuple[int, int]:
    """(start, end) line indices of one module's entry under ``modules:``.

    The entry starts at the two-space-indented ``<id>:`` line and runs until
    the next line at two-space (or less) indentation — covering both the
    canonical one-line flow style and a user's hand-expanded block style.
    """
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^  {re.escape(mod_id)}\s*:", line):
            start = i
            break
    if start is None:
        raise ConfigError(
            f"could not find the `{mod_id}:` entry under `modules:`; your config uses a "
            "layout this command does not understand — edit it by hand and run `onyxian plan`"
        )
    end = start + 1
    while end < len(lines) and (lines[end].startswith("    ") or not lines[end].strip()):
        end += 1
    return start, end


def bump_module_versions(text: str, changes: dict[str, tuple[str, str]]) -> tuple[str, Config]:
    """Rewrite ``modules.<id>.version`` values in place; every other byte survives."""
    lines = text.split("\n")
    for mod_id, (old, new) in changes.items():
        start, end = _module_block_span(lines, mod_id)
        pattern = re.compile(rf"(version\s*:\s*[\"']?){re.escape(old)}([\"']?)")
        for i in range(start, end):
            replaced = pattern.sub(rf"\g<1>{new}\g<2>", lines[i], count=1)
            if replaced != lines[i]:
                lines[i] = replaced
                break
        else:
            raise ConfigError(
                f"could not find version {old!r} in the `{mod_id}:` entry; "
                "edit the config by hand and run `onyxian plan`"
            )
    new_text = "\n".join(lines)
    try:
        config = parse_config(yaml.safe_load(new_text))
    except Exception as exc:  # noqa: BLE001 - re-raised with context, nothing is written
        raise ConfigError(
            f"bumping versions produced an invalid config ({exc}); nothing written"
        ) from None
    for mod_id, (_, new) in changes.items():
        if config.modules[mod_id].version != new:
            raise ConfigError(f"version bump for {mod_id!r} did not take; edit the config by hand")
    return new_text, config


def _matching_brace(text: str, opening: int) -> int | None:
    """Find a flow mapping's closing brace without mistaking braces inside strings."""
    depth = 0
    quote: str | None = None
    escaped = False
    index = opening
    while index < len(text):
        char = text[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if quote == "'":
            if char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char in ('"', "'"):
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _insert_flow_values(line: str, opening: int, rendered: str) -> str:
    closing = _matching_brace(line, opening)
    if closing is None:
        raise ConfigError(
            "could not understand an inline module mapping while adding update answers; "
            "edit the config by hand and run `onyxian plan`"
        )
    body = line[opening + 1 : closing]
    content = body.rstrip()
    trailing = body[len(content) :]
    separator = ", " if content.strip() else ""
    return line[: opening + 1] + content + separator + rendered + trailing + line[closing:]


def insert_module_variables(
    text: str, additions: dict[str, dict[str, object]]
) -> tuple[str, Config]:
    """Add newly introduced module variables while preserving the user's surrounding text."""
    lines = text.split("\n")
    for mod_id in sorted(additions):
        values = additions[mod_id]
        if not values:
            continue
        rendered = ", ".join(
            f"{key}: {json.dumps(value, ensure_ascii=False)}"
            for key, value in sorted(values.items())
        )
        start, end = _module_block_span(lines, mod_id)
        entry = lines[start]
        entry_value = entry.split(":", 1)[1].lstrip()
        if entry_value.startswith("{"):
            vars_match = re.search(r"\bvars\s*:\s*\{", entry)
            if vars_match:
                opening = entry.find("{", vars_match.start())
                lines[start] = _insert_flow_values(entry, opening, rendered)
            else:
                opening = entry.find("{", entry.find(":") + 1)
                lines[start] = _insert_flow_values(entry, opening, f"vars: {{ {rendered} }}")
            continue

        vars_line = next(
            (index for index in range(start + 1, end) if re.match(r"^    vars\s*:", lines[index])),
            None,
        )
        if vars_line is not None:
            inline = lines[vars_line].split(":", 1)[1].lstrip()
            if inline.startswith("{"):
                opening = lines[vars_line].find("{", lines[vars_line].find(":") + 1)
                lines[vars_line] = _insert_flow_values(lines[vars_line], opening, rendered)
            else:
                insert_at = vars_line + 1
                while insert_at < end:
                    candidate = lines[insert_at]
                    if candidate.strip() and len(candidate) - len(candidate.lstrip()) <= 4:
                        break
                    insert_at += 1
                while insert_at > vars_line + 1 and not lines[insert_at - 1].strip():
                    insert_at -= 1
                lines[insert_at:insert_at] = [
                    f"      {key}: {json.dumps(value, ensure_ascii=False)}"
                    for key, value in sorted(values.items())
                ]
            continue

        version_line = next(
            (
                index
                for index in range(start + 1, end)
                if re.match(r"^    version\s*:", lines[index])
            ),
            start,
        )
        lines[version_line + 1 : version_line + 1] = [
            "    vars:",
            *[
                f"      {key}: {json.dumps(value, ensure_ascii=False)}"
                for key, value in sorted(values.items())
            ],
        ]

    new_text = "\n".join(lines)
    try:
        config = parse_config(yaml.safe_load(new_text))
    except Exception as exc:  # noqa: BLE001 - re-raised with context, nothing is written
        raise ConfigError(
            f"adding update answers produced an invalid config ({exc}); nothing written"
        ) from None
    for mod_id, values in additions.items():
        for key, value in values.items():
            if config.modules[mod_id].vars.get(key) != value:
                raise ConfigError(
                    f"variable insertion for {mod_id}.{key} did not take; edit the config by hand"
                )
    return new_text, config


def remove_module_entry(text: str, mod_id: str) -> tuple[str, Config]:
    """Delete one module's entry from the config text; every other byte survives."""
    lines = text.split("\n")
    start, end = _module_block_span(lines, mod_id)
    new_text = "\n".join(lines[:start] + lines[end:])
    try:
        config = parse_config(yaml.safe_load(new_text))
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(
            f"removing the module produced an invalid config ({exc}); nothing written"
        ) from None
    if mod_id in config.modules:
        raise ConfigError(f"removal of {mod_id!r} did not take; edit the config by hand")
    return new_text, config


def _source_block_span(lines: list[str], src_name: str) -> tuple[int, int]:
    """(start, end) line indices of one source's sub-block under top-level ``sources:``.

    Mirrors :func:`_module_block_span` but scoped to the ``sources:`` section:
    the entry starts at the two-space ``<name>:`` line (four-space keys below it,
    per ``render_config_text``'s canonical layout) and runs until the next line at
    two-space-or-less indentation.
    """
    in_sources = False
    start = None
    for i, line in enumerate(lines):
        if line.rstrip() == "sources:":
            in_sources = True
            continue
        if in_sources and line and not line.startswith(" "):
            break  # a new top-level key ended the sources section
        if in_sources and re.match(rf"^  {re.escape(src_name)}\s*:", line):
            start = i
            break
    if start is None:
        raise ConfigError(
            f"could not find the `{src_name}:` entry under `sources:`; your config uses a "
            "layout this command does not understand — edit it by hand and run `onyxian plan`"
        )
    end = start + 1
    while end < len(lines) and (lines[end].startswith("    ") or not lines[end].strip()):
        end += 1
    return start, end


def _replace_pin_in_span(
    lines: list[str], start: int, end: int, old_pin: str, new_pin: str, where: str
) -> str:
    """Replace ``old_pin`` with ``new_pin`` within ``lines[start:end]`` only.

    Requires exactly one occurrence in the span; zero or several raise
    :class:`ConfigError` (the ambiguous case the old whole-file replace corrupted),
    and nothing is written.
    """
    count = "\n".join(lines[start:end]).count(old_pin)
    if count != 1:
        raise ConfigError(
            f"expected exactly one occurrence of the recorded pin in the {where}, found {count}; "
            "edit the config by hand and run `onyxian plan`"
        )
    for i in range(start, end):
        if old_pin in lines[i]:
            lines[i] = lines[i].replace(old_pin, new_pin, 1)
            break
    return "\n".join(lines)


def _reparse_after_pin(new_text: str) -> Config:
    try:
        return parse_config(yaml.safe_load(new_text))
    except Exception as exc:  # noqa: BLE001 - re-raised with context, nothing is written
        raise ConfigError(
            f"the pin edit produced an invalid config ({exc}); nothing written"
        ) from None


def replace_module_pin(text: str, mod_id: str, old_pin: str, new_pin: str) -> str:
    """Advance ``modules.<mod_id>.source.pin`` in place, anchored to that entry only."""
    lines = text.split("\n")
    start, end = _module_block_span(lines, mod_id)
    new_text = _replace_pin_in_span(
        lines, start, end, old_pin, new_pin, f"`{mod_id}:` module entry"
    )
    source = _reparse_after_pin(new_text).modules[mod_id].source
    if source is None or source.get("pin") != new_pin:
        raise ConfigError(f"pin update for module {mod_id!r} did not take; edit the config by hand")
    return new_text


def replace_source_pin(text: str, src_name: str, old_pin: str, new_pin: str) -> str:
    """Advance ``sources.<src_name>.pin`` in place, anchored to that entry only."""
    lines = text.split("\n")
    start, end = _source_block_span(lines, src_name)
    new_text = _replace_pin_in_span(
        lines, start, end, old_pin, new_pin, f"`{src_name}:` source entry"
    )
    source = _reparse_after_pin(new_text).sources.get(src_name, {})
    if source.get("pin") != new_pin:
        raise ConfigError(
            f"pin update for source {src_name!r} did not take; edit the config by hand"
        )
    return new_text


def insert_module_entries(text: str, entries: dict[str, ModuleConfig]) -> tuple[str, Config]:
    """Insert canonical one-line entries after ``modules:``; returns (new text, parsed config)."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.rstrip() == "modules:":
            insert_at = i + 1
            break
    else:
        raise ConfigError(
            "could not find a top-level `modules:` block line in .vault/config.yaml; "
            "your config uses a layout `add` does not understand — add the module by hand "
            "and run `onyxian plan`"
        )
    new_lines = [module_line(mod_id, entries[mod_id]) for mod_id in sorted(entries)]
    new_text = "\n".join(lines[:insert_at] + new_lines + lines[insert_at:])
    try:
        config = parse_config(yaml.safe_load(new_text))
    except Exception as exc:  # noqa: BLE001 - re-raised with context, nothing is written
        raise ConfigError(
            f"inserting the module produced an invalid config ({exc}); nothing written"
        ) from None
    return new_text, config

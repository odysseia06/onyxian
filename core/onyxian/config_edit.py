"""Surgical edits to `.vault/config.yaml` on the user's behalf.

The config is the user's file (§4.4): `add` must not regenerate it wholesale,
because that would destroy their comments and formatting. Instead, new module
entries are inserted textually right after the top-level ``modules:`` line —
every other byte of the file survives untouched — and the result is re-parsed
before anything is written, so a malformed outcome is impossible to commit.
"""

from __future__ import annotations

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


def replace_pin(text: str, old_pin: str, new_pin: str) -> str:
    """Swap a 40-hex source pin in place (unique enough to be a safe literal replace)."""
    if old_pin not in text:
        raise ConfigError("could not find the recorded pin in the config; edit it by hand")
    return text.replace(old_pin, new_pin)


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

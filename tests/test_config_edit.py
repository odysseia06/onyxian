"""Anchored source-pin edits: a pin is replaced only within its owning block (issue #9).

The old ``replace_pin`` did a whole-file ``text.replace`` — when a module's
``source: { pin: X }`` and a ``sources:`` entry were pinned to the same commit,
advancing one silently advanced the other to a commit that was never installed.
``replace_module_pin`` / ``replace_source_pin`` anchor to the owning span, require
exactly one occurrence there, and semantically verify the parsed result.
"""

import pytest
import yaml

from onyxian.config_edit import replace_module_pin, replace_source_pin
from onyxian.configio import parse_config
from onyxian.errors import ConfigError

PIN_A = "a" * 40
PIN_B = "b" * 40
PIN_C = "c" * 40

_HEADER = (
    "framework:\n"
    '  version: "0.1.0"\n'
    "  runtimes: [claude-code]\n"
    "vault:\n"
    '  name: "V"\n'
    "naming:\n"
    "  folder_style: Title-Case-Hyphen\n"
)


def _config(modules: str, sources: str = "") -> str:
    text = _HEADER + "modules:\n" + modules
    if sources:
        text += "sources:\n" + sources
    return text


def _parsed(text: str):
    return parse_config(yaml.safe_load(text))


# A module and a source pinned to the SAME commit — the corruption case.
_SAME_PIN = _config(
    modules=(
        '  core: { version: "0.1.0" }\n'
        f'  ext: {{ version: "0.1.0", source: {{ repo: "r", pin: "{PIN_A}" }} }}\n'
    ),
    sources=(f'  obsidian-skills:\n    repo: "s"\n    pin: "{PIN_A}"\n'),
)


def test_replace_module_pin_leaves_a_same_pinned_source_untouched():
    out = replace_module_pin(_SAME_PIN, "ext", PIN_A, PIN_B)
    cfg = _parsed(out)
    assert cfg.modules["ext"].source["pin"] == PIN_B
    assert cfg.sources["obsidian-skills"]["pin"] == PIN_A  # the source's bytes are untouched


def test_replace_source_pin_leaves_a_same_pinned_module_untouched():
    out = replace_source_pin(_SAME_PIN, "obsidian-skills", PIN_A, PIN_B)
    cfg = _parsed(out)
    assert cfg.sources["obsidian-skills"]["pin"] == PIN_B
    assert cfg.modules["ext"].source["pin"] == PIN_A  # the module's bytes are untouched


def test_replace_module_pin_absent_pin_raises_and_writes_nothing():
    text = _config(
        modules=f'  ext: {{ version: "0.1.0", source: {{ repo: "r", pin: "{PIN_A}" }} }}\n'
    )
    with pytest.raises(ConfigError, match="edit the config by hand"):
        replace_module_pin(text, "ext", PIN_B, PIN_C)  # PIN_B is not in the ext block


def test_replace_module_pin_duplicate_in_block_raises():
    # The pin appears twice in the ext entry (in the repo URL and the pin field):
    # a whole-block replace would be ambiguous, so it must refuse.
    text = _config(
        modules=f'  ext: {{ version: "0.1.0", source: {{ repo: "x/{PIN_A}", pin: "{PIN_A}" }} }}\n'
    )
    with pytest.raises(ConfigError, match="edit the config by hand"):
        replace_module_pin(text, "ext", PIN_A, PIN_B)


def test_replace_module_pin_on_a_hand_expanded_block_style_entry():
    text = _config(
        modules=(
            '  core: { version: "0.1.0" }\n'
            "  ext:\n"
            '    version: "0.1.0"\n'
            "    source:\n"
            '      repo: "r"\n'
            f'      pin: "{PIN_A}"\n'
        )
    )
    out = replace_module_pin(text, "ext", PIN_A, PIN_B)
    assert _parsed(out).modules["ext"].source["pin"] == PIN_B

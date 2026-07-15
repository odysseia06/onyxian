"""Config schema and the deterministic emitter (KICKSTART.md §4.4)."""

import pytest
import yaml

from onyxian.configio import parse_config, render_config_text
from onyxian.errors import ConfigError
from onyxian.model import ModuleConfig


def charter_shaped_config() -> dict[str, object]:
    return {
        "framework": {"version": "0.1.0", "runtimes": ["claude-code"]},
        "vault": {"name": "My Vault"},
        "naming": {"folder_style": "Title-Case-Hyphen"},
        "modules": {
            "core": {"version": "0.1.0"},
            "fitness": {"version": "0.1.0", "vars": {"root": "Fitness", "review_cadence": "both"}},
        },
        "sources": {
            "obsidian-skills": {
                "repo": "https://github.com/kepano/obsidian-skills",
                "pin": "abc123",
            },
        },
    }


def _framework(data: dict[str, object]) -> dict[str, object]:
    """The framework sub-mapping, narrowed so mypy allows keyed mutation in tests."""
    fw = data["framework"]
    assert isinstance(fw, dict)
    return fw


def test_parses_the_charter_example_shape():
    config = parse_config(charter_shaped_config())
    assert config.vault_name == "My Vault"
    assert config.folder_style == "Title-Case-Hyphen"
    assert list(config.modules) == ["core", "fitness"]
    assert config.modules["fitness"].vars == {"root": "Fitness", "review_cadence": "both"}
    assert config.sources["obsidian-skills"]["pin"] == "abc123"


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda d: d.update(extra=1), "unknown key"),
        (lambda d: d.pop("vault"), "missing required"),
        (lambda d: d["naming"].update(folder_style="snake_case"), "folder_style"),
        (lambda d: d["framework"].update(runtimes=["vim"]), "unknown runtime"),
        (lambda d: d["framework"].update(version="one"), "semver"),
        (lambda d: d["modules"].pop("core"), "'core' module is required"),
        (lambda d: d["modules"].update({"Bad_Id": {"version": "0.1.0"}}), "kebab-case"),
        (lambda d: d["modules"]["fitness"].update(vars={"root": ["list"]}), "scalar"),
        (lambda d: d["modules"]["fitness"].pop("version"), "missing required"),
    ],
)
def test_schema_violations_fail_loudly(mutate, match):
    data = charter_shaped_config()
    mutate(data)
    with pytest.raises(ConfigError, match=match):
        parse_config(data)


def test_checkpoints_defaults_off():
    config = parse_config(charter_shaped_config())
    assert config.checkpoints is False


def test_checkpoints_flag_parses_and_roundtrips():
    data = charter_shaped_config()
    _framework(data)["checkpoints"] = True
    config = parse_config(data)
    assert config.checkpoints is True
    reparsed = parse_config(yaml.safe_load(render_config_text(config)))
    assert reparsed.checkpoints is True


def test_checkpoints_must_be_bool():
    data = charter_shaped_config()
    _framework(data)["checkpoints"] = "yes"
    with pytest.raises(ConfigError, match="checkpoints"):
        parse_config(data)


def test_emitter_omits_checkpoints_when_off():
    config = parse_config(charter_shaped_config())
    assert "checkpoints" not in render_config_text(config)


def test_emitter_emits_checkpoints_when_on():
    data = charter_shaped_config()
    _framework(data)["checkpoints"] = True
    config = parse_config(data)
    assert "checkpoints: true" in render_config_text(config)


def test_emitter_roundtrips_through_the_parser():
    config = parse_config(charter_shaped_config())
    text = render_config_text(config)
    reparsed = parse_config(yaml.safe_load(text))
    assert reparsed == config


def test_emitter_is_deterministic():
    config = parse_config(charter_shaped_config())
    assert render_config_text(config) == render_config_text(config)
    assert render_config_text(config).endswith("\n")
    assert "\r" not in render_config_text(config)


def test_emitter_quotes_awkward_strings():
    config = parse_config(charter_shaped_config())
    config.vault_name = 'He said "vault: yes"'
    config.modules["fitness"] = ModuleConfig(version="0.1.0", vars={"root": "Weird: Name"})
    reparsed = parse_config(yaml.safe_load(render_config_text(config)))
    assert reparsed.vault_name == 'He said "vault: yes"'
    assert reparsed.modules["fitness"].vars["root"] == "Weird: Name"

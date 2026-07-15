"""Manifest schema validation and asset binding (KICKSTART.md §5.2)."""

import pytest
from conftest import REAL_MODULES, write_module

from onyxian.errors import ManifestError
from onyxian.manifests import load_manifest


def test_real_core_module_loads():
    manifest = load_manifest(REAL_MODULES / "core")
    assert manifest.name == "core"
    assert manifest.depends == ()
    assert [f.install_path for f in manifest.templates] == ["Templates/Note.md"]
    assert [f.install_path for f in manifest.seeds] == [
        "Home.md",
        ".obsidian/community-plugins.json",
    ]
    assert [s.id for s in manifest.skills] == [
        "vault-bootstrap",
        "vault-conventions",
        "obsidian-tasks",
        "obsidian-templater",
        "vault-operations",
    ]
    assert all(f.source.is_file() for f in (*manifest.templates, *manifest.seeds))


def test_placeholder_segments_live_verbatim_in_assets(tmp_path):
    write_module(tmp_path, "demo", seeds={"{{root}}/Strategy.md": "fill me in\n"})
    manifest = load_manifest(tmp_path / "demo")
    seed = manifest.seeds[0]
    assert seed.install_path == "{{root}}/Strategy.md"
    assert seed.source.name == "Strategy.md"
    assert seed.source.parent.name == "{{root}}"


def test_wildcards_expand_sorted(tmp_path):
    module_dir = write_module(tmp_path, "demo")
    assets = module_dir / "assets" / "Templates" / "Demo"
    assets.mkdir(parents=True)
    for name in ("b.md", "a.md", "c.txt"):
        (assets / name).write_text("x", encoding="utf-8")
    manifest_path = module_dir / "module.yaml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8")
        + 'provides:\n  templates: ["Templates/Demo/*.md"]\n',
        encoding="utf-8",
    )
    manifest = load_manifest(module_dir)
    assert [f.install_path for f in manifest.templates] == [
        "Templates/Demo/a.md",
        "Templates/Demo/b.md",
    ]


def _break(tmp_path, **kwargs):
    write_module(tmp_path, "demo", **kwargs)
    return tmp_path / "demo"


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"version": "one.two"}, "semver"),
        ({"summary": "  "}, "summary"),
        ({"depends": []}, "every module depends on 'core'"),
        ({"variables": [{"key": "Bad-Key", "prompt": "x"}]}, "snake_case"),
        ({"variables": [{"key": "x", "prompt": "x", "type": "choice"}]}, "options"),
        (
            {
                "variables": [
                    {"key": "x", "prompt": "x", "type": "choice", "options": ["a"], "default": "z"}
                ]
            },
            "not one of",
        ),
        (
            {"variables": [{"key": "x", "prompt": "x"}, {"key": "x", "prompt": "y"}]},
            "duplicate variable",
        ),
        ({"folders": ["bad|name"]}, "invalid on Windows"),
        (
            {"templates": {"Templates/A.md": "x"}, "seeds": {"Templates/A.md": "x"}},
            "duplicate install path",
        ),
    ],
)
def test_authoring_mistakes_are_rejected(tmp_path, kwargs, match):
    module_dir = _break(tmp_path, **kwargs)
    with pytest.raises(ManifestError, match=match):
        load_manifest(module_dir)


def test_name_must_match_directory(tmp_path):
    module_dir = write_module(tmp_path, "demo")
    renamed = tmp_path / "other"
    module_dir.rename(renamed)
    with pytest.raises(ManifestError, match="does not match its directory"):
        load_manifest(renamed)


def test_missing_asset_is_an_error(tmp_path):
    module_dir = write_module(tmp_path, "demo", templates={"Templates/A.md": "x"})
    (module_dir / "assets" / "Templates" / "A.md").unlink()
    with pytest.raises(ManifestError, match="asset file missing"):
        load_manifest(module_dir)


def test_unknown_keys_are_rejected(tmp_path):
    module_dir = write_module(tmp_path, "demo")
    manifest_path = module_dir / "module.yaml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8") + "scripts: [evil.sh]\n", encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="unknown key"):
        load_manifest(module_dir)


def test_wildcard_plus_variable_is_rejected(tmp_path):
    module_dir = write_module(tmp_path, "demo", folders=["{{root}}"])
    manifest_path = module_dir / "module.yaml"
    (module_dir / "assets").mkdir(exist_ok=True)
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8") + 'seeds: ["{{root}}/*.md"]\n', encoding="utf-8"
    )
    with pytest.raises(ManifestError, match="cannot be combined"):
        load_manifest(module_dir)

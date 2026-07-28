"""Manifest schema validation and asset binding (KICKSTART.md §5.2)."""

import pytest
from conftest import REAL_MODULES, make_config, write_module

from onyxian.errors import ManifestError, PathError, ResolveError
from onyxian.intent import build_desired_state
from onyxian.manifests import load_manifest
from onyxian.repo import discover_modules
from onyxian.resolve import resolve_modules


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


def test_renames_parse_old_to_new_managed_paths(tmp_path):
    write_module(
        tmp_path,
        "demo",
        templates={"Templates/Demo/New.md": "new\n"},
        renames={"Templates/Demo/Old.md": "Templates/Demo/New.md"},
    )

    manifest = load_manifest(tmp_path / "demo")

    assert [(rename.old_path, rename.new_path) for rename in manifest.renames] == [
        ("Templates/Demo/Old.md", "Templates/Demo/New.md")
    ]


@pytest.mark.parametrize(
    "renames,match",
    [
        ({"bad|old.md": "Templates/Demo/New.md"}, "invalid on Windows"),
        ({"Templates/Demo/Same.md": "Templates/Demo/Same.md"}, "must differ"),
    ],
)
def test_renames_reject_unsafe_authored_paths(tmp_path, renames, match):
    module_dir = write_module(
        tmp_path,
        "demo",
        templates={"Templates/Demo/New.md": "new\n"},
        renames=renames,
    )

    with pytest.raises(ManifestError, match=match):
        load_manifest(module_dir)


def test_renames_must_be_a_mapping(tmp_path):
    module_dir = write_module(tmp_path, "demo")
    manifest_path = module_dir / "module.yaml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8") + "renames: []\n",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="'renames' must be a mapping"):
        load_manifest(module_dir)


def _desired_for(tmp_path, *, templates=None, seeds=None, renames=None):
    write_module(tmp_path, "core")
    write_module(
        tmp_path,
        "demo",
        variables=[{"key": "root", "prompt": "Root", "default": "Demo-Area"}],
        templates=templates,
        seeds=seeds,
        renames=renames,
    )
    config = make_config({"demo": {"version": "0.1.0"}}, folder_style="kebab-case")
    return build_desired_state(config, resolve_modules(config, discover_modules(tmp_path)))


def test_renames_render_variables_and_folder_style(tmp_path):
    desired = _desired_for(
        tmp_path,
        templates={"{{root}}/New.md": "new\n"},
        renames={"{{root}}/Old.md": "{{root}}/New.md"},
    )

    assert [(r.old_path, r.new_path, r.module) for r in desired.renames] == [
        ("demo-area/Old.md", "demo-area/New.md", "demo")
    ]


@pytest.mark.parametrize("destination_kind", ["missing", "seeded"])
def test_rename_destination_must_be_a_current_managed_file(tmp_path, destination_kind):
    templates = {"{{root}}/Current.md": "current\n"}
    seeds = {"{{root}}/New.md": "seed\n"} if destination_kind == "seeded" else None

    with pytest.raises(ResolveError, match=r"rename destination.*current managed file"):
        _desired_for(
            tmp_path,
            templates=templates,
            seeds=seeds,
            renames={"{{root}}/Old.md": "{{root}}/New.md"},
        )


def test_rename_source_cannot_still_be_provided(tmp_path):
    with pytest.raises(ResolveError, match=r"rename source.*still provided"):
        _desired_for(
            tmp_path,
            templates={
                "{{root}}/Old.md": "old\n",
                "{{root}}/New.md": "new\n",
            },
            renames={"{{root}}/Old.md": "{{root}}/New.md"},
        )


def test_rename_paths_must_still_differ_after_rendering(tmp_path):
    with pytest.raises(ResolveError, match="same rendered path"):
        _desired_for(
            tmp_path,
            templates={"Demo-Area/New.md": "new\n"},
            renames={"{{root}}/New.md": "Demo-Area/New.md"},
        )


def test_rename_source_cannot_use_the_conflict_delivery_suffix(tmp_path):
    with pytest.raises(PathError, match="reserved for conflict delivery"):
        _desired_for(
            tmp_path,
            templates={"{{root}}/New.md": "new\n"},
            renames={"{{root}}/Old.md.new": "{{root}}/New.md"},
        )


def test_rename_source_cannot_case_alias_an_unrelated_desired_path(tmp_path):
    with pytest.raises(ResolveError, match=r"rename source.*case-aliases.*not its destination"):
        _desired_for(
            tmp_path,
            templates={
                "{{root}}/New.md": "new\n",
                "{{root}}/plan.md": "other\n",
            },
            renames={"{{root}}/Plan.md": "{{root}}/New.md"},
        )


def test_rename_source_may_share_the_destinations_new_parent_spelling(tmp_path):
    write_module(tmp_path, "core")
    write_module(
        tmp_path,
        "demo",
        templates={
            "Templates/New.md": "new\n",
            "Templates/Other.md": "other\n",
        },
        renames={"templates/Old.md": "Templates/New.md"},
    )
    config = make_config({"demo": {"version": "0.1.0"}})

    desired = build_desired_state(config, resolve_modules(config, discover_modules(tmp_path)))

    assert [(r.old_path, r.new_path) for r in desired.renames] == [
        ("templates/Old.md", "Templates/New.md")
    ]


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

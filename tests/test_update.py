"""The M3 exit criterion (§14): update on a vault with user-modified managed files —
zero overwrites, correct *.new reporting. Plus version bumps, pin advance, idempotence."""

from types import SimpleNamespace

import pytest

from conftest import run_cli, tree_hashes, write_module
from onyxian.config_edit import bump_module_versions
from onyxian.errors import ConfigError
from onyxian.lockio import load_lock

V1 = "# guide v1\n"
V2 = "# guide v2 (improved)\n"
SEED_V1 = "seed v1\n"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A vault installed at demo v0.1.0, ready for the library to move to v0.2.0."""
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(
        modules_root,
        "demo",
        version="0.1.0",
        folders=["Demo-Area"],
        templates={"Templates/Demo/Guide.md": V1, "Templates/Demo/Old-Asset.md": "retired soon\n"},
        seeds={"Start.md": SEED_V1},
    )
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    answers = tmp_path / "a.yaml"
    answers.write_text("modules: {demo: {}}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(answers), "--yes") == 0
    return SimpleNamespace(vault=vault, modules_root=modules_root, tmp=tmp_path)


def release_v2(home, *, seed="seed v2 — never delivered to existing vaults\n"):
    """The library moves to demo 0.2.0: Guide changes, Old-Asset is dropped, seed changes."""
    write_module(
        home.modules_root,
        "demo",
        version="0.2.0",
        folders=["Demo-Area"],
        templates={"Templates/Demo/Guide.md": V2},
        seeds={"Start.md": seed},
    )


def test_exit_criterion_zero_overwrites_correct_new_report(home, capsys):
    guide = home.vault / "Templates" / "Demo" / "Guide.md"
    guide.write_text("MY customized guide\n", encoding="utf-8")  # the user touched it
    release_v2(home)
    before = tree_hashes(home.vault)

    assert run_cli("update", "--vault", str(home.vault), "--yes") == 0
    out = capsys.readouterr().out

    assert "demo: 0.1.0 -> 0.2.0" in out
    assert "no overwrites" in out and "Templates/Demo/Guide.md -> Templates/Demo/Guide.md.new" in out
    # Zero overwrites: the customized file is byte-identical; the new version sits beside it.
    after = tree_hashes(home.vault)
    assert after["Templates/Demo/Guide.md"] == before["Templates/Demo/Guide.md"]
    assert guide.with_name("Guide.md.new").read_text(encoding="utf-8") == V2
    # The seed was never updated (§8.2) and the dropped asset was left in place, reported.
    assert after["Start.md"] == before["Start.md"]
    assert "no longer shipped" in out and "Old-Asset.md" in out
    assert (home.vault / "Templates" / "Demo" / "Old-Asset.md").exists()
    # Config pin bumped.
    config_text = (home.vault / ".vault" / "config.yaml").read_text(encoding="utf-8")
    assert 'demo: { version: "0.2.0" }' in config_text


def test_clean_files_update_in_place(home):
    release_v2(home)
    assert run_cli("update", "--vault", str(home.vault), "--yes") == 0
    guide = home.vault / "Templates" / "Demo" / "Guide.md"
    assert guide.read_text(encoding="utf-8") == V2
    assert not guide.with_name("Guide.md.new").exists()
    entry = load_lock(home.vault).get("Templates/Demo/Guide.md")
    assert entry.module_version == "0.2.0"


def test_update_is_idempotent(home, capsys):
    release_v2(home)
    assert run_cli("update", "--vault", str(home.vault), "--yes") == 0
    capsys.readouterr()
    before = tree_hashes(home.vault)
    assert run_cli("update", "--vault", str(home.vault), "--yes") == 0
    assert "nothing to update." in capsys.readouterr().out
    assert tree_hashes(home.vault) == before


def test_update_dry_run_writes_nothing(home):
    release_v2(home)
    before = tree_hashes(home.vault)
    assert run_cli("update", "--vault", str(home.vault), "--dry-run") == 0
    assert tree_hashes(home.vault) == before


def test_single_module_update_targets_only_it(home, capsys):
    release_v2(home)
    assert run_cli("update", "demo", "--vault", str(home.vault), "--yes") == 0
    assert "demo: 0.1.0 -> 0.2.0" in capsys.readouterr().out


def test_unknown_target_is_an_error(home, capsys):
    assert run_cli("update", "ghost", "--vault", str(home.vault), "--yes") == 1
    assert "neither an enabled module nor a declared source" in capsys.readouterr().err


def test_resolved_new_sibling_settles_after_user_accepts(home, capsys):
    """User adopts the delivered version by making their file match: next update is a no-op."""
    guide = home.vault / "Templates" / "Demo" / "Guide.md"
    guide.write_text("customized\n", encoding="utf-8")
    release_v2(home)
    assert run_cli("update", "--vault", str(home.vault), "--yes") == 0
    guide.write_text(V2, encoding="utf-8", newline="\n")  # user accepts the new content
    capsys.readouterr()
    assert run_cli("update", "--vault", str(home.vault), "--yes") == 0
    out = capsys.readouterr().out
    assert "relock" in out  # the engine re-claims it without writing
    assert load_lock(home.vault).get("Templates/Demo/Guide.md").sha256 is not None


def test_bump_preserves_user_comments_and_layout():
    text = (
        "# my header comment\n"
        "framework:\n  version: \"0.1.0\"\n  runtimes: [claude-code]\n"
        "vault:\n  name: \"X\"\n"
        "naming:\n  folder_style: Title-Case-Hyphen\n"
        "modules:\n"
        "  core: { version: \"0.1.0\" }\n"
        "  # my module note\n"
        "  demo:\n"
        "    version: '0.1.0'\n"
        "    vars: { root: \"Demo\" }\n"
    )
    new_text, config = bump_module_versions(text, {"demo": ("0.1.0", "0.2.0")})
    assert "# my header comment" in new_text and "# my module note" in new_text
    assert config.modules["demo"].version == "0.2.0"
    assert config.modules["core"].version == "0.1.0"
    assert 'core: { version: "0.1.0" }' in new_text  # untouched


def test_bump_fails_loudly_on_unrecognized_layout():
    text = "modules: {demo: {version: \"0.1.0\"}}\n"
    with pytest.raises(ConfigError, match="by hand"):
        bump_module_versions(text, {"demo": ("0.1.0", "0.2.0")})

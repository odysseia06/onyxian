"""`onyxian remove` (§8.3): delete only unmodified managed files; report everything left behind."""

from types import SimpleNamespace

import pytest
from conftest import run_cli, write_module

from onyxian.lockio import load_lock


@pytest.fixture
def home(tmp_path, monkeypatch):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(
        modules_root,
        "demo",
        folders=["Demo-Area/Logs"],
        templates={"Templates/Demo/Guide.md": "guide\n", "Templates/Demo/Extra.md": "extra\n"},
        seeds={"Start.md": "seed\n"},
        skills={"demo-skill": {"SKILL.md": "---\nname: demo-skill\ndescription: x\n---\n"}},
    )
    write_module(modules_root, "extra", depends=["core", "demo"])
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    answers = tmp_path / "a.yaml"
    answers.write_text("modules: {demo: {}}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(answers), "--yes") == 0
    return SimpleNamespace(vault=vault, tmp=tmp_path)


def test_remove_deletes_unmodified_keeps_modified_and_seeded(home, capsys):
    guide = home.vault / "Templates" / "Demo" / "Guide.md"
    guide.write_text("MY guide now\n", encoding="utf-8")
    assert run_cli("remove", "demo", "--vault", str(home.vault), "--yes") == 0
    out = capsys.readouterr().out

    assert not (home.vault / "Templates" / "Demo" / "Extra.md").exists()  # unmodified: deleted
    assert not (
        home.vault / ".claude" / "skills" / "demo-skill"
    ).exists()  # runtime artifact: deleted
    assert guide.read_text(encoding="utf-8") == "MY guide now\n"  # modified: yours, kept
    assert (home.vault / "Start.md").exists()  # seeded: never touched
    assert "you modified it" in out and "seeded" in out

    lock = load_lock(home.vault)
    assert all(e.module != "demo" for e in lock.entries.values())  # every claim relinquished
    config_text = (home.vault / ".vault" / "config.yaml").read_text(encoding="utf-8")
    assert "demo" not in config_text

    # The vault is converged afterwards: nothing pending, nothing orphaned.
    capsys.readouterr()
    assert run_cli("plan", "--vault", str(home.vault)) == 0
    plan_out = capsys.readouterr().out
    assert "no changes planned" in plan_out and "orphaned" not in plan_out


def test_remove_prunes_only_empty_folders(home):
    keeper = home.vault / "Demo-Area" / "Logs" / "my-note.md"
    keeper.write_text("user content\n", encoding="utf-8")
    user_template = home.vault / "Templates" / "My-Template.md"
    user_template.write_text("mine\n", encoding="utf-8")
    assert run_cli("remove", "demo", "--vault", str(home.vault), "--yes") == 0
    assert keeper.exists()  # the folder held user files, so it stays
    # Templates/Demo emptied out and was pruned; the root survives because the user's file is in it.
    assert not (home.vault / "Templates" / "Demo").exists()
    assert user_template.exists()


def test_remove_prunes_empty_module_tree_entirely(home):
    assert run_cli("remove", "demo", "--vault", str(home.vault), "--yes") == 0
    assert not (home.vault / "Demo-Area").exists()


def test_remove_refuses_core_and_depended_on_modules(home, capsys):
    assert run_cli("remove", "core", "--vault", str(home.vault), "--yes") == 1
    assert "cannot be removed" in capsys.readouterr().err
    assert run_cli("add", "extra", "--vault", str(home.vault), "--yes") == 0
    capsys.readouterr()
    assert run_cli("remove", "demo", "--vault", str(home.vault), "--yes") == 1
    assert "depend(s) on it" in capsys.readouterr().err


def test_remove_dry_run_changes_nothing(home):
    from conftest import tree_hashes

    before = tree_hashes(home.vault)
    assert run_cli("remove", "demo", "--vault", str(home.vault), "--dry-run") == 0
    assert tree_hashes(home.vault) == before


def test_remove_is_idempotent(home, capsys):
    assert run_cli("remove", "demo", "--vault", str(home.vault), "--yes") == 0
    capsys.readouterr()
    assert run_cli("remove", "demo", "--vault", str(home.vault), "--yes") == 0
    assert "not enabled" in capsys.readouterr().out


def test_remove_cleans_orphaned_lock_entries(home, capsys):
    """A module hand-deleted from config but still in the lock is cleaned up in one step."""
    from onyxian.config_edit import remove_module_entry

    config_file = home.vault / ".vault" / "config.yaml"
    new_text, _ = remove_module_entry(config_file.read_text(encoding="utf-8"), "demo")
    config_file.write_text(new_text, encoding="utf-8")

    assert run_cli("remove", "demo", "--vault", str(home.vault), "--yes") == 0
    out = capsys.readouterr().out
    assert "disabled but still tracked" in out  # the orphan-path header, not the enabled one
    assert "removed 'demo'" in out
    assert not (home.vault / "Templates" / "Demo" / "Extra.md").exists()
    lock = load_lock(home.vault)
    assert all(e.module != "demo" for e in lock.entries.values())

    # A subsequent plan sees nothing orphaned — the cleanup was complete.
    capsys.readouterr()
    assert run_cli("plan", "--vault", str(home.vault)) == 0
    assert "orphaned" not in capsys.readouterr().out


def test_remove_orphan_dry_run_omits_config_line_and_writes_nothing(home, capsys):
    from conftest import tree_hashes

    from onyxian.config_edit import remove_module_entry

    config_file = home.vault / ".vault" / "config.yaml"
    new_text, _ = remove_module_entry(config_file.read_text(encoding="utf-8"), "demo")
    config_file.write_text(new_text, encoding="utf-8")

    before = tree_hashes(home.vault)
    assert run_cli("remove", "demo", "--vault", str(home.vault), "--dry-run") == 0
    out = capsys.readouterr().out
    assert "disabled but still tracked" in out
    assert "dropping the" not in out  # no config-entry line: the config never listed it
    assert tree_hashes(home.vault) == before  # dry run writes nothing


def test_remove_degrades_when_a_file_cannot_be_deleted(home, capsys, monkeypatch):
    """Obsidian holding a file open (routine on Windows) must not abort a half-done removal."""
    from pathlib import Path

    real_unlink = Path.unlink

    def refuse_one(self, *args, **kwargs):
        if self.parts[-3:] == ("Templates", "Demo", "Guide.md"):
            raise PermissionError(13, "The process cannot access the file")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", refuse_one)
    assert run_cli("remove", "demo", "--vault", str(home.vault), "--yes") == 1
    captured = capsys.readouterr()
    assert "could not be deleted" in captured.out + captured.err

    stuck = home.vault / "Templates" / "Demo" / "Guide.md"
    assert stuck.is_file()  # left on disk, reported — not a traceback mid-removal
    assert not (home.vault / "Templates" / "Demo" / "Extra.md").exists()  # the rest went through
    assert all(e.module != "demo" for e in load_lock(home.vault).entries.values())
    assert "demo" not in (home.vault / ".vault" / "config.yaml").read_text(encoding="utf-8")


def test_remove_validates_the_config_edit_before_deleting(home, capsys):
    """A layout the config editor cannot handle costs nothing: no file is deleted first."""
    import yaml
    from conftest import tree_hashes

    config_file = home.vault / ".vault" / "config.yaml"
    raw = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    # Valid YAML the user could have written by hand, but not a layout `remove` can edit textually.
    config_file.write_text(yaml.safe_dump(raw, default_flow_style=True), encoding="utf-8")

    before = tree_hashes(home.vault)
    assert run_cli("remove", "demo", "--vault", str(home.vault), "--yes") == 1
    assert "layout this command does not understand" in capsys.readouterr().err
    assert tree_hashes(home.vault) == before  # nothing deleted behind a config edit that failed


def test_remove_orphan_cleans_external_copy(home, capsys):
    """An external module disabled by hand-edit still has its .vault/modules/<id> copy removed."""
    from onyxian.config_edit import remove_module_entry

    ext_src = write_module(
        home.tmp / "ext-src", "ext-demo", templates={"Templates/Ext/Note.md": "n\n"}
    )
    assert run_cli("add", str(ext_src), "--vault", str(home.vault), "--yes", "--trust") == 0
    copy = home.vault / ".vault" / "modules" / "ext-demo"
    assert copy.is_dir()

    config_file = home.vault / ".vault" / "config.yaml"
    new_text, _ = remove_module_entry(config_file.read_text(encoding="utf-8"), "ext-demo")
    config_file.write_text(new_text, encoding="utf-8")

    capsys.readouterr()
    # No KeyError even though config no longer has the entry; the copy is gone afterwards.
    assert run_cli("remove", "ext-demo", "--vault", str(home.vault), "--yes") == 0
    out = capsys.readouterr().out
    assert "removed the external copy" in out
    assert not copy.exists()

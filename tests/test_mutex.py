"""The coarse per-vault write mutex: one writer per vault at a time (issue #8).

`vault_mutex` is a context manager that creates an exclusive `.vault/apply.lock`
for the duration of a command's write phase. A second process that finds the file
fails fast with `VaultBusyError` (never breaking the holder's lock), and the file
is always removed on the way out — success or error — so it never lands in the
ledger or a generated tree. The CLI wires it around every ledger-mutating command
(init, apply, adopt, add, update, remove, diff resolution) but never around
read-only paths — and the Lock object it saves inside the mutex is (re)loaded
inside it, so a command that sat at its confirm prompt while another process
finished never saves a stale snapshot over that process's rows (issue #47).
"""

import os
import re
from pathlib import Path

import pytest
from conftest import ANSWERS_DIR, init_minimal_vault, run_cli, tree_hashes, write_module

from onyxian import applier, cli
from onyxian.errors import OnyxianError, VaultBusyError
from onyxian.lockio import load_lock, save_lock
from onyxian.model import LockEntry
from onyxian.mutex import vault_mutex

MINIMAL = str(ANSWERS_DIR / "minimal.yaml")
# A planted lock impersonating another live process, for the "refuses while held" path.
PLANTED = "4242\n2026-07-02T09:15:03Z\n"


def _bare_vault(tmp_path: Path) -> Path:
    (tmp_path / ".vault").mkdir()
    return tmp_path


def _hold_lock(vault: Path) -> None:
    (vault / ".vault" / "apply.lock").write_text(PLANTED, encoding="utf-8")


# --------------------------------------------------------------- context manager


def test_acquire_creates_lockfile_and_release_removes_it(tmp_path):
    vault = _bare_vault(tmp_path)
    lockfile = vault / ".vault" / "apply.lock"
    assert not lockfile.exists()
    with vault_mutex(vault):
        assert lockfile.is_file()
    assert not lockfile.exists()


def test_lockfile_records_the_holding_pid(tmp_path):
    vault = _bare_vault(tmp_path)
    lockfile = vault / ".vault" / "apply.lock"
    with vault_mutex(vault):
        first_line = lockfile.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == str(os.getpid())


def test_contention_raises_vault_busy_naming_file_pid_and_start(tmp_path):
    vault = _bare_vault(tmp_path)
    _hold_lock(vault)
    with pytest.raises(VaultBusyError) as excinfo, vault_mutex(vault):
        pass  # pragma: no cover - never entered
    message = str(excinfo.value)
    assert "pid 4242" in message
    assert "2026-07-02T09:15:03Z" in message
    assert ".vault/apply.lock" in message
    # main() renders any OnyxianError as a one-line `error:` with exit 1.
    assert isinstance(excinfo.value, OnyxianError)


def test_contention_does_not_break_the_existing_lock(tmp_path):
    vault = _bare_vault(tmp_path)
    lockfile = vault / ".vault" / "apply.lock"
    _hold_lock(vault)
    with pytest.raises(VaultBusyError), vault_mutex(vault):
        pass  # pragma: no cover - never entered
    assert lockfile.read_text(encoding="utf-8") == PLANTED  # the holder's file is untouched


def test_lockfile_is_removed_even_when_body_raises(tmp_path):
    vault = _bare_vault(tmp_path)
    lockfile = vault / ".vault" / "apply.lock"
    with pytest.raises(RuntimeError), vault_mutex(vault):
        assert lockfile.is_file()
        raise RuntimeError("boom")
    assert not lockfile.exists()


def test_acquire_creates_the_vault_dir_when_missing(tmp_path):
    """init/adopt acquire before `.vault/` exists; the mutex makes the dir so the
    whole seed+apply sequence is guarded (issue #8 open question)."""
    vault = tmp_path / "brand-new"
    with vault_mutex(vault):
        assert (vault / ".vault" / "apply.lock").is_file()
    assert (vault / ".vault").is_dir()
    assert not (vault / ".vault" / "apply.lock").exists()


# --------------------------------------------------------------- CLI: refused while held


def test_apply_refuses_while_the_lock_is_held(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    (vault / "templates" / "Note.md").unlink()  # a real pending change apply would write
    _hold_lock(vault)
    before = tree_hashes(vault)
    code = run_cli("apply", "--vault", str(vault), "--yes")
    err = capsys.readouterr().err
    assert code == 1
    assert "another onyxian process is working on this vault" in err
    assert "apply.lock" in err and "pid 4242" in err
    assert tree_hashes(vault) == before  # nothing written
    assert (vault / ".vault" / "apply.lock").exists()  # the holder's lock is not broken


def test_update_refuses_while_the_lock_is_held(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    (vault / "templates" / "Note.md").unlink()  # gives update a non-empty plan
    _hold_lock(vault)
    before = tree_hashes(vault)
    code = run_cli("update", "--vault", str(vault), "--yes")
    err = capsys.readouterr().err
    assert code == 1
    assert "another onyxian process is working on this vault" in err
    assert tree_hashes(vault) == before


def test_add_refuses_while_the_lock_is_held(tmp_path, monkeypatch, capsys):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(modules_root, "demo", folders=["Demo-Area"])
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    (tmp_path / "answers.yaml").write_text("modules: {core: {}}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(tmp_path / "answers.yaml"), "--yes") == 0
    capsys.readouterr()
    _hold_lock(vault)
    code = run_cli("add", "demo", "--vault", str(vault), "--yes")
    assert code == 1
    assert "another onyxian process is working on this vault" in capsys.readouterr().err
    assert "demo" not in (vault / ".vault" / "config.yaml").read_text(encoding="utf-8")


def test_external_add_stages_nothing_while_the_lock_is_held(tmp_path, monkeypatch, capsys):
    """#50: `add <external>` copies the fetched module into `.vault/modules/` — a vault
    write like any other, so it waits for the mutex instead of racing another writer's
    rmtree+copytree over the same directory."""
    write_module(tmp_path / "modules", "core")
    external = write_module(tmp_path / "ext", "demo-ext", folders=["Ext-Area"])
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    (tmp_path / "answers.yaml").write_text("modules: {core: {}}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(tmp_path / "answers.yaml"), "--yes") == 0
    capsys.readouterr()
    _hold_lock(vault)
    code = run_cli("add", str(external), "--vault", str(vault), "--yes", "--trust")
    assert code == 1
    assert "another onyxian process is working on this vault" in capsys.readouterr().err
    assert not (vault / ".vault" / "modules" / "demo-ext").exists()


def test_remove_refuses_while_the_lock_is_held(tmp_path, monkeypatch, capsys):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(
        modules_root,
        "demo",
        folders=["Demo-Area"],
        templates={"Templates/Demo/Guide.md": "guide\n"},
    )
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    (tmp_path / "answers.yaml").write_text("modules: {demo: {}}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(tmp_path / "answers.yaml"), "--yes") == 0
    capsys.readouterr()
    _hold_lock(vault)
    code = run_cli("remove", "demo", "--vault", str(vault), "--yes")
    assert code == 1
    assert "another onyxian process is working on this vault" in capsys.readouterr().err
    assert "demo" in (vault / ".vault" / "config.yaml").read_text(encoding="utf-8")  # not removed
    assert (vault / "Templates" / "Demo" / "Guide.md").exists()  # nothing deleted


# --------------------------------------------------------------- CLI: diff resolution guarded

GUIDE = "Templates/Demo/Guide.md"


def _conflict_vault(tmp_path: Path, monkeypatch, capsys) -> Path:
    """A vault with one delivered conflict pair at GUIDE (test_diff's setup, condensed):
    the user customized the managed file, demo 0.2.0 shipped new content, and
    `update` delivered the `*.new` sibling."""
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(modules_root, "demo", version="0.1.0", templates={GUIDE: "# guide v1\n"})
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    (tmp_path / "a.yaml").write_text("modules: {demo: {}}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(tmp_path / "a.yaml"), "--yes") == 0
    guide = vault / "Templates" / "Demo" / "Guide.md"
    guide.write_text("MY customized guide\n", encoding="utf-8")
    write_module(modules_root, "demo", version="0.2.0", templates={GUIDE: "# guide v2\n"})
    assert run_cli("update", "--vault", str(vault), "--yes") == 0
    capsys.readouterr()
    return vault


def test_diff_take_new_refuses_while_the_lock_is_held(tmp_path, monkeypatch, capsys):
    vault = _conflict_vault(tmp_path, monkeypatch, capsys)
    _hold_lock(vault)
    before = tree_hashes(vault)
    code = run_cli("diff", GUIDE, "--take-new", "--yes", "--vault", str(vault))
    err = capsys.readouterr().err
    assert code == 1
    assert "another onyxian process is working on this vault" in err
    assert tree_hashes(vault) == before  # neither the original, the sibling, nor the ledger moved


def test_diff_keep_mine_refuses_while_the_lock_is_held(tmp_path, monkeypatch, capsys):
    vault = _conflict_vault(tmp_path, monkeypatch, capsys)
    _hold_lock(vault)
    before = tree_hashes(vault)
    code = run_cli("diff", GUIDE, "--keep-mine", "--yes", "--vault", str(vault))
    err = capsys.readouterr().err
    assert code == 1
    assert "another onyxian process is working on this vault" in err
    assert tree_hashes(vault) == before


def test_interactive_resolve_refuses_while_the_lock_is_held(tmp_path, monkeypatch, capsys):
    vault = _conflict_vault(tmp_path, monkeypatch, capsys)
    _hold_lock(vault)
    monkeypatch.setattr("onyxian.cli._is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "t")
    before = tree_hashes(vault)
    code = run_cli("diff", "--resolve", "--vault", str(vault))
    err = capsys.readouterr().err
    assert code == 1
    assert "another onyxian process is working on this vault" in err
    assert tree_hashes(vault) == before


def test_diff_read_paths_run_while_the_lock_is_held(tmp_path, monkeypatch, capsys):
    vault = _conflict_vault(tmp_path, monkeypatch, capsys)
    _hold_lock(vault)
    assert run_cli("diff", "--vault", str(vault)) == 1  # listing exits 1 while pairs exist
    assert run_cli("diff", GUIDE, "--vault", str(vault)) == 1
    assert run_cli("diff", GUIDE, "--take-new", "--dry-run", "--vault", str(vault)) == 0
    out = capsys.readouterr()
    assert "another onyxian process" not in out.out + out.err
    assert (vault / ".vault" / "apply.lock").exists()  # read paths never touched the lock


# --------------------------------------------------------------- CLI: reload under the mutex

FOREIGN = "From-Another-Process.md"


def _inject_row_at_confirm(monkeypatch, vault: Path) -> None:
    """Monkeypatch the confirm gate to mutate the on-disk ledger before answering
    yes — the moral equivalent of another process completing a whole command while
    this one sat at its y/N prompt (issue #47's failure scenario)."""

    def confirm_and_inject(question: str, *, assume_yes: bool) -> bool:
        lock = load_lock(vault)
        lock.put(
            LockEntry(
                path=FOREIGN,
                sha256="0" * 64,
                module="core",
                module_version="0.1.0",
                kind="seeded",
            )
        )
        save_lock(vault, lock)
        return True

    monkeypatch.setattr(cli, "_confirm", confirm_and_inject)


def test_apply_preserves_rows_written_while_the_prompt_was_open(tmp_path, monkeypatch):
    vault = init_minimal_vault(tmp_path)
    (vault / "templates" / "Note.md").unlink()  # a pending action, so apply reaches the gate
    _inject_row_at_confirm(monkeypatch, vault)
    assert run_cli("apply", "--vault", str(vault)) == 0
    lock = load_lock(vault)
    assert lock.get(FOREIGN) is not None  # the other process's row survived the save
    assert lock.get("templates/Note.md") is not None  # and this command's work is ledgered


def test_add_preserves_rows_written_while_the_prompt_was_open(tmp_path, monkeypatch, capsys):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(modules_root, "demo", templates={GUIDE: "guide\n"})
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    (tmp_path / "answers.yaml").write_text("modules: {core: {}}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(tmp_path / "answers.yaml"), "--yes") == 0
    _inject_row_at_confirm(monkeypatch, vault)
    assert run_cli("add", "demo", "--vault", str(vault)) == 0
    lock = load_lock(vault)
    assert lock.get(FOREIGN) is not None
    assert lock.get(GUIDE) is not None


def test_update_preserves_rows_written_while_the_prompt_was_open(tmp_path, monkeypatch):
    vault = init_minimal_vault(tmp_path)
    (vault / "templates" / "Note.md").unlink()  # a non-empty plan, so the gate fires
    _inject_row_at_confirm(monkeypatch, vault)
    assert run_cli("update", "--vault", str(vault)) == 0
    lock = load_lock(vault)
    assert lock.get(FOREIGN) is not None
    assert lock.get("templates/Note.md") is not None


def test_remove_preserves_rows_written_while_the_prompt_was_open(tmp_path, monkeypatch, capsys):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(modules_root, "demo", templates={GUIDE: "guide\n"})
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    (tmp_path / "answers.yaml").write_text("modules: {demo: {}}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(tmp_path / "answers.yaml"), "--yes") == 0
    _inject_row_at_confirm(monkeypatch, vault)
    assert run_cli("remove", "demo", "--vault", str(vault)) == 0
    lock = load_lock(vault)
    assert lock.get(FOREIGN) is not None  # survived remove's wholesale row relinquishment
    assert lock.get(GUIDE) is None  # while demo's own rows are gone


def test_diff_take_new_preserves_rows_written_while_the_prompt_was_open(
    tmp_path, monkeypatch, capsys
):
    vault = _conflict_vault(tmp_path, monkeypatch, capsys)
    _inject_row_at_confirm(monkeypatch, vault)
    assert run_cli("diff", GUIDE, "--take-new", "--vault", str(vault)) == 0
    lock = load_lock(vault)
    assert lock.get(FOREIGN) is not None
    entry = lock.get(GUIDE)
    assert entry is not None
    assert entry.module_version == "0.2.0"  # the resolution itself still happened


# --------------------------------------------------------------- CLI: read-only untouched


def test_read_only_commands_run_while_the_lock_is_held(tmp_path):
    vault = init_minimal_vault(tmp_path)
    _hold_lock(vault)
    assert run_cli("plan", "--vault", str(vault)) == 0
    assert run_cli("doctor", "--vault", str(vault)) == 0
    assert run_cli("apply", "--vault", str(vault), "--dry-run") == 0
    assert (vault / ".vault" / "apply.lock").exists()  # read-only never touched the lock


# --------------------------------------------------------------- CLI: acquired then released


def test_apply_releases_the_lock_on_success(tmp_path):
    vault = init_minimal_vault(tmp_path)
    (vault / "templates" / "Note.md").unlink()
    assert run_cli("apply", "--vault", str(vault), "--yes") == 0
    assert (vault / "templates" / "Note.md").is_file()  # the change was applied
    assert not (vault / ".vault" / "apply.lock").exists()  # lock cleaned up


def _held_during_apply_spy(monkeypatch, seen: dict[str, bool]):
    real = applier.apply_plan

    def spy(vault_root, plan, lock, **kwargs):
        seen["held"] = (vault_root / ".vault" / "apply.lock").is_file()
        return real(vault_root, plan, lock, **kwargs)

    monkeypatch.setattr(cli, "apply_plan", spy)


def test_init_holds_the_mutex_during_apply_then_releases_it(tmp_path, monkeypatch):
    seen: dict[str, bool] = {}
    _held_during_apply_spy(monkeypatch, seen)
    target = tmp_path / "v"
    assert run_cli("init", str(target), "--answers", MINIMAL, "--yes") == 0
    assert seen["held"] is True  # the write phase ran under the mutex
    assert not (target / ".vault" / "apply.lock").exists()


def test_adopt_holds_the_mutex_during_apply_then_releases_it(tmp_path, monkeypatch, capsys):
    write_module(tmp_path / "modules", "core", seeds={"Home.md": "home\n"})
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    target = tmp_path / "existing"
    target.mkdir()
    (target / "Random.md").write_text("mine\n", encoding="utf-8")
    assert run_cli("adopt", str(target), "--dry-run") == 0
    match = re.search(r"--accept ([0-9a-f]{12})", capsys.readouterr().out)
    assert match is not None
    token = match.group(1)
    seen: dict[str, bool] = {}
    _held_during_apply_spy(monkeypatch, seen)
    assert run_cli("adopt", str(target), "--accept", token) == 0
    assert seen["held"] is True
    assert not (target / ".vault" / "apply.lock").exists()

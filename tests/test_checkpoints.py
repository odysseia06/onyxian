"""The opt-in vault checkpoint guard — a recovery net, not scope enforcement (issue #11, phase 1).

The checkpoint CLI shells out to ``git`` with a **separate** git dir under
``.vault/checkpoints/`` so it never reads or writes a user's own ``.git``. Snapshot
timestamps are pinned here via ``GIT_AUTHOR_DATE``/``GIT_COMMITTER_DATE`` (``ONYXIAN_NOW``
is date-only and does not cover git's clock) so the displayed output is byte-stable.
"""

from __future__ import annotations

import builtins
import os
import re
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import init_minimal_vault, run_cli

from onyxian.fsio import sha256_bytes, sha256_file
from onyxian.lockio import load_lock, save_lock

CHECKPOINTS = ".vault/checkpoints"
PINNED_GIT = "2026-07-02T09:14:00+00:00"


@pytest.fixture
def pinned_git_dates(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_DATE", PINNED_GIT)
    monkeypatch.setenv("GIT_COMMITTER_DATE", PINNED_GIT)


def _cp_git(vault: Path, *args: str) -> str:
    """Query the checkpoint repo directly (test-side inspection)."""
    proc = subprocess.run(
        ["git", f"--git-dir={vault / CHECKPOINTS}", f"--work-tree={vault}", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def test_checkpoint_creates_a_snapshot(tmp_path, capsys, pinned_git_dates):
    vault = init_minimal_vault(tmp_path)
    capsys.readouterr()  # drop init chatter
    code = run_cli("checkpoint", "--vault", str(vault))
    assert code == 0
    out = capsys.readouterr().out
    assert (vault / CHECKPOINTS / "HEAD").is_file()
    assert re.search(r"checkpoint [0-9a-f]{7,} \(2026-07-02 09:14\) . \d+ files? changed", out), out
    assert _cp_git(vault, "rev-list", "--count", "HEAD") == "1"


def test_rerun_with_no_changes_is_a_noop(tmp_path, capsys, pinned_git_dates):
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    capsys.readouterr()
    code = run_cli("checkpoint", "--vault", str(vault))
    assert code == 0
    assert "no changes" in capsys.readouterr().out
    assert _cp_git(vault, "rev-list", "--count", "HEAD") == "1"  # still one snapshot


def test_a_change_produces_a_new_snapshot(tmp_path, capsys, pinned_git_dates):
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    (vault / "a-new-note.md").write_text("hello\n", encoding="utf-8")
    capsys.readouterr()
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    assert "1 file changed since last" in capsys.readouterr().out
    assert _cp_git(vault, "rev-list", "--count", "HEAD") == "2"


def test_a_preexisting_user_git_is_never_touched(tmp_path, pinned_git_dates):
    vault = init_minimal_vault(tmp_path)
    # A user's own git repo at the vault root, with a commit of their own.
    env = {**os.environ}

    def user_git(*a: str) -> None:
        subprocess.run(
            ["git", "-C", str(vault), "-c", "user.name=U", "-c", "user.email=u@e", *a],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    user_git("init", "-q")
    user_git("add", "-A")
    user_git("commit", "-q", "-m", "user baseline")

    dotgit = vault / ".git"

    def state() -> dict[str, object]:
        return {
            "HEAD": (dotgit / "HEAD").read_bytes(),
            "index": (dotgit / "index").read_bytes(),
            "commits": subprocess.run(
                ["git", "-C", str(vault), "rev-list", "--count", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout,
            "refs": {
                p.relative_to(dotgit).as_posix(): p.read_bytes()
                for p in sorted((dotgit / "refs").rglob("*"))
                if p.is_file()
            },
        }

    before = state()
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    assert state() == before  # no index/HEAD/ref changes in the user repo


def test_git_absent_warns_and_exits_zero(tmp_path, capsys, monkeypatch):
    vault = init_minimal_vault(tmp_path)
    monkeypatch.setattr("onyxian.checkpoints.shutil.which", lambda name: None)
    capsys.readouterr()
    code = run_cli("checkpoint", "--vault", str(vault))
    assert code == 0
    err = capsys.readouterr().err
    assert err.count("\n") == 1  # exactly one warning line
    assert "git" in err.lower()
    assert not (vault / CHECKPOINTS / "HEAD").exists()


def test_list_shows_snapshots_newest_first_with_baseline(tmp_path, capsys, pinned_git_dates):
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0  # baseline
    (vault / "note.md").write_text("hello\n", encoding="utf-8")
    assert run_cli("checkpoint", "--vault", str(vault)) == 0  # +1 file
    capsys.readouterr()
    assert run_cli("checkpoint", "list", "--vault", str(vault)) == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 2
    assert "1 file changed" in lines[0]  # newest first
    assert "(baseline)" in lines[1]
    assert "2026-07-02 09:14" in lines[0]


def test_diff_shows_working_tree_changes_since_last(tmp_path, capsys, pinned_git_dates):
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    (vault / "Start-Here.md").write_text("edited\n", encoding="utf-8")
    (vault / "Brand-New.md").write_text("new\n", encoding="utf-8")
    capsys.readouterr()
    assert run_cli("checkpoint", "diff", "--vault", str(vault)) == 0
    out = capsys.readouterr().out
    assert re.search(r"^M\s+Start-Here\.md$", out, re.M), out
    assert re.search(r"^A\s+Brand-New\.md$", out, re.M), out


def test_list_with_no_guard_at_all_says_no_checkpoints_yet(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    capsys.readouterr()
    assert run_cli("checkpoint", "list", "--vault", str(vault)) == 0
    assert "no checkpoints yet" in capsys.readouterr().out


def test_list_reports_a_broken_guard_instead_of_no_checkpoints_yet(tmp_path, capsys, monkeypatch):
    """#96: `.vault/checkpoints/` existing with no readable snapshot is a guard that
    ran and failed, not one that has not run yet — doctor's #93 discriminator, which
    `checkpoint list` conflated into "no checkpoints yet"."""
    vault = init_minimal_vault(tmp_path)
    monkeypatch.setattr("onyxian.checkpoints.shutil.which", lambda name: None)
    assert run_cli("checkpoint", "--quiet", "--vault", str(vault)) == 0  # dir made, repo never was
    monkeypatch.undo()
    capsys.readouterr()
    assert run_cli("checkpoint", "list", "--vault", str(vault)) == 0
    out = capsys.readouterr().out
    assert "no checkpoints yet" not in out
    assert "no snapshot is readable" in out
    assert "onyxian checkpoint" in out  # the command that prints git's own reason


def test_diff_reports_a_broken_ref_instead_of_no_checkpoints_yet(
    tmp_path, capsys, pinned_git_dates
):
    """#96's other face: real history behind a missing branch ref makes `rev-parse`
    exit 1, so `has_checkpoints` says no — while snapshots genuinely exist on disk."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    (vault / CHECKPOINTS / "refs" / "heads" / "main").unlink()
    capsys.readouterr()
    assert run_cli("checkpoint", "diff", "--vault", str(vault)) == 0
    out = capsys.readouterr().out
    assert "no checkpoints yet" not in out
    assert "no snapshot is readable" in out


def test_excludes_checkpoints_and_obsidian_workspace(tmp_path, pinned_git_dates):
    vault = init_minimal_vault(tmp_path)
    obsidian = vault / ".obsidian"
    obsidian.mkdir(exist_ok=True)
    (obsidian / "workspace.json").write_text("{}\n", encoding="utf-8")
    (obsidian / "app.json").write_text("{}\n", encoding="utf-8")
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    tracked = _cp_git(vault, "ls-files").splitlines()
    assert ".obsidian/app.json" in tracked  # ordinary obsidian config is snapshotted
    assert ".obsidian/workspace.json" not in tracked  # volatile per-machine UI state is not
    assert not any(p.startswith(".vault/checkpoints/") for p in tracked)  # never itself


def test_excludes_the_live_mutex_and_half_written_temp_files(tmp_path, pinned_git_dates):
    """#60: the SessionStart hook can snapshot while another process holds the write
    mutex. Committing `.vault/apply.lock` means a later restore resurrects a stale
    lock and bricks the vault; `*.onyxian-tmp` is a torn write nobody wants back."""
    vault = init_minimal_vault(tmp_path)
    (vault / ".vault" / "apply.lock").write_text("4242\n2026-07-02T09:15:03Z\n", encoding="utf-8")
    (vault / "Start-Here.md.onyxian-tmp").write_text("half\n", encoding="utf-8")
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    tracked = _cp_git(vault, "ls-files").splitlines()
    assert ".vault/apply.lock" not in tracked
    assert "Start-Here.md.onyxian-tmp" not in tracked


def test_snapshot_keeps_recovery_metadata_even_when_the_vault_gitignore_hides_it(
    tmp_path, pinned_git_dates
):
    """The historical ledger is required for a later ledger-aware path restore."""
    vault = init_minimal_vault(tmp_path)
    (vault / ".gitignore").write_text(".vault/\n", encoding="utf-8")

    assert run_cli("checkpoint", "--vault", str(vault)) == 0

    tracked = _cp_git(vault, "ls-files").splitlines()
    assert ".vault/config.yaml" in tracked
    assert ".vault/lock.json" in tracked


def test_a_git_that_runs_and_fails_warns_and_exits_zero(tmp_path, capsys, pinned_git_dates):
    """#60: only git's *absence* used to degrade. A git that runs and fails — a
    `safe.directory` refusal on a synced vault, a half-copied checkpoint repo —
    escaped `cmd_checkpoint` as a traceback out of the SessionStart hook."""
    vault = init_minimal_vault(tmp_path)
    gd = vault / CHECKPOINTS
    gd.mkdir(parents=True)
    (gd / "HEAD").write_text("not a git repository\n", encoding="utf-8")  # survives _ensure_repo
    capsys.readouterr()
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    err = capsys.readouterr().err
    assert err.count("\n") == 1  # exactly one warning line
    assert "git" in err.lower()


def test_a_git_that_hangs_warns_and_exits_zero(tmp_path, capsys, monkeypatch):
    """#60: the 180s timeout is a real ceiling (a network filesystem stalling git);
    `TimeoutExpired` must degrade like every other tooling failure, not traceback."""
    vault = init_minimal_vault(tmp_path)

    def hang(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 180)

    monkeypatch.setattr("onyxian.checkpoints.subprocess.run", hang)
    capsys.readouterr()
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "git" in err.lower()


def test_a_git_that_cannot_launch_warns_and_exits_zero(tmp_path, capsys, monkeypatch):
    """#60: `shutil.which` matches a name on PATH, never whether the file actually
    execs — a broken git shim raises OSError out of `subprocess.run` itself, and that
    is a tooling failure like any other."""
    vault = init_minimal_vault(tmp_path)

    def unlaunchable(cmd, **kwargs):
        raise OSError(8, "Exec format error")

    monkeypatch.setattr("onyxian.checkpoints.subprocess.run", unlaunchable)
    capsys.readouterr()
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "git" in err.lower()


def test_an_unwritable_checkpoint_repo_warns_and_exits_zero(tmp_path, capsys):
    """#60: the guard's own filesystem work degrades too. Here `.vault/checkpoints` is
    occupied by a file — the shape a sloppy sync tool leaves behind — so the repo
    cannot be created at all."""
    vault = init_minimal_vault(tmp_path)
    (vault / CHECKPOINTS).write_text("not a directory\n", encoding="utf-8")
    capsys.readouterr()
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "unwritable" in err  # _ensure_repo's own reason, not the CLI's static tail


def test_a_broken_stdout_never_claims_a_snapshot_was_skipped(
    tmp_path, monkeypatch, pinned_git_dates
):
    """#60: the degrade path covers the guard, not the printing. `onyxian checkpoint |
    head -1` closes the pipe *after* the commit lands; reporting that as "skipping
    checkpoint" would be a safety net lying about the one thing it exists to do."""
    vault = init_minimal_vault(tmp_path)
    real_print = builtins.print

    def closed_pipe(*args, **kwargs):
        if kwargs.get("file") is None:  # stdout only; the warning goes to stderr
            raise BrokenPipeError(32, "Broken pipe")
        real_print(*args, **kwargs)

    monkeypatch.setattr(builtins, "print", closed_pipe)
    with pytest.raises(BrokenPipeError):
        run_cli("checkpoint", "--vault", str(vault))
    monkeypatch.undo()
    assert _cp_git(vault, "rev-list", "--count", "HEAD") == "1"  # the snapshot is real


def test_quiet_prints_nothing_but_still_snapshots(tmp_path, capsys, pinned_git_dates):
    vault = init_minimal_vault(tmp_path)
    capsys.readouterr()
    code = run_cli("checkpoint", "--quiet", "--vault", str(vault))
    assert code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (vault / CHECKPOINTS / "HEAD").is_file()


def test_restore_single_managed_path_restores_its_verified_checkpoint_ledger_row(
    tmp_path, capsys, pinned_git_dates
):
    """A missing ledger update would make the restored bytes look user-modified."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")

    portable = "templates/Note.md"
    target = vault / "templates" / "Note.md"
    checkpoint_bytes = target.read_bytes()
    checkpoint_entry = load_lock(vault).get(portable)
    assert checkpoint_entry is not None

    later_bytes = b"# A later managed version\n"
    target.write_bytes(later_bytes)
    later_lock = load_lock(vault)
    later_lock.put(
        replace(
            checkpoint_entry,
            sha256=sha256_bytes(later_bytes),
            module_version="99.0.0",
        )
    )
    save_lock(vault, later_lock)

    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        portable,
        "--vault",
        str(vault),
        "--yes",
    )

    assert code == 0
    out = capsys.readouterr().out
    assert f"restore checkpoint {checkpoint_id}" in out
    assert f"M  {portable}" in out
    assert ".vault/lock.json" in out
    assert target.read_bytes() == checkpoint_bytes
    assert load_lock(vault).get(portable) == checkpoint_entry


def test_restore_without_paths_returns_the_whole_vault_to_the_checkpoint(
    tmp_path, capsys, pinned_git_dates
):
    """Missing restore-wide discovery would leave edits, deletions, or stray files behind."""
    vault = init_minimal_vault(tmp_path)
    workspace = vault / ".obsidian" / "workspace.json"
    workspace.write_text('{"before": true}\n', encoding="utf-8")
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")

    start = vault / "Start-Here.md"
    home = vault / "Home.md"
    start_at_checkpoint = start.read_bytes()
    home_at_checkpoint = home.read_bytes()
    start.write_text("agent edit\n", encoding="utf-8")
    home.unlink()
    stray = vault / "Stray Agent Note.md"
    stray.write_text("should disappear\n", encoding="utf-8")
    workspace.write_text('{"current": true}\n', encoding="utf-8")

    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        "--vault",
        str(vault),
        "--yes",
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "M  Start-Here.md" in out
    assert "A  Home.md" in out
    assert "D  Stray Agent Note.md" in out
    assert start.read_bytes() == start_at_checkpoint
    assert home.read_bytes() == home_at_checkpoint
    assert not stray.exists()
    assert workspace.read_text(encoding="utf-8") == '{"current": true}\n'


def test_whole_vault_restore_uses_the_checkpoint_ledger_as_its_final_base(
    tmp_path, capsys, pinned_git_dates
):
    """Re-saving a pre-restore Lock after restoring lock.json would resurrect later rows."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    checkpoint_lock = load_lock(vault)

    portable = "templates/Note.md"
    target = vault / "templates" / "Note.md"
    entry = checkpoint_lock.get(portable)
    assert entry is not None
    later_bytes = b"# later managed bytes\n"
    target.write_bytes(later_bytes)
    later_lock = load_lock(vault)
    later_lock.put(replace(entry, sha256=sha256_bytes(later_bytes), module_version="99.0.0"))
    ghost_bytes = b"not in the checkpoint\n"
    (vault / "Ghost.md").write_bytes(ghost_bytes)
    later_lock.put(
        replace(
            entry,
            path="Ghost.md",
            sha256=sha256_bytes(ghost_bytes),
            module_version="99.0.0",
        )
    )
    save_lock(vault, later_lock)

    capsys.readouterr()
    assert (
        run_cli(
            "checkpoint",
            "restore",
            checkpoint_id,
            "--vault",
            str(vault),
            "--yes",
        )
        == 0
    )

    assert load_lock(vault) == checkpoint_lock
    assert not (vault / "Ghost.md").exists()


def test_restore_never_mistakes_an_unreadable_checkpoint_blob_for_a_deletion(
    tmp_path, capsys, pinned_git_dates
):
    """A missing object is guard failure, not evidence that the path was absent."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    portable = "templates/Note.md"
    blob_id = _cp_git(vault, "rev-parse", f"{checkpoint_id}:{portable}")
    loose_object = vault / CHECKPOINTS / "objects" / blob_id[:2] / blob_id[2:]
    assert loose_object.is_file()
    loose_object.chmod(0o600)
    loose_object.unlink()

    target = vault / "templates" / "Note.md"
    current_bytes = b"# current bytes must survive\n"
    target.write_bytes(current_bytes)
    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        portable,
        "--vault",
        str(vault),
        "--yes",
    )

    assert code == 1
    assert target.read_bytes() == current_bytes
    assert "unavailable" in capsys.readouterr().err


def test_path_restore_preserves_a_checkpoint_customization_without_claiming_it(
    tmp_path, capsys, pinned_git_dates
):
    """Rehashing customized snapshot bytes would let a future update overwrite them."""
    vault = init_minimal_vault(tmp_path)
    portable = "templates/Note.md"
    target = vault / "templates" / "Note.md"
    checkpoint_entry = load_lock(vault).get(portable)
    assert checkpoint_entry is not None

    customized_bytes = b"# customized when snapshotted\n"
    target.write_bytes(customized_bytes)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")

    later_bytes = b"# later framework-owned version\n"
    target.write_bytes(later_bytes)
    later_lock = load_lock(vault)
    later_lock.put(
        replace(
            checkpoint_entry,
            sha256=sha256_bytes(later_bytes),
            module_version="99.0.0",
        )
    )
    save_lock(vault, later_lock)

    capsys.readouterr()
    assert (
        run_cli(
            "checkpoint",
            "restore",
            checkpoint_id,
            portable,
            "--vault",
            str(vault),
            "--yes",
        )
        == 0
    )

    restored_entry = load_lock(vault).get(portable)
    assert target.read_bytes() == customized_bytes
    assert restored_entry == checkpoint_entry
    assert restored_entry.sha256 != sha256_bytes(customized_bytes)


def test_path_restore_fails_closed_when_the_checkpoint_ledger_blob_is_unreadable(
    tmp_path, capsys, pinned_git_dates
):
    """A corrupt historical ledger must not be interpreted as an intentionally empty one."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    lock_blob = _cp_git(vault, "rev-parse", f"{checkpoint_id}:.vault/lock.json")
    loose_object = vault / CHECKPOINTS / "objects" / lock_blob[:2] / lock_blob[2:]
    assert loose_object.is_file()
    loose_object.chmod(0o600)
    loose_object.unlink()

    target = vault / "templates" / "Note.md"
    current_bytes = b"# current bytes must survive\n"
    target.write_bytes(current_bytes)
    current_lock = load_lock(vault)
    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        "templates/Note.md",
        "--vault",
        str(vault),
        "--yes",
    )

    assert code == 1
    assert target.read_bytes() == current_bytes
    assert load_lock(vault) == current_lock
    assert "unavailable" in capsys.readouterr().err


def test_restore_refuses_to_materialize_a_checkpoint_symlink(tmp_path, capsys, pinned_git_dates):
    """Restoring mode 120000 as a regular file would violate the no-symlink contract."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    git_base = [
        "git",
        "-c",
        "user.name=Onyxian",
        "-c",
        "user.email=onyxian@localhost",
        f"--git-dir={vault / CHECKPOINTS}",
        f"--work-tree={vault}",
    ]
    blob_id = subprocess.run(
        [*git_base, "hash-object", "-w", "--stdin"],
        input="Home.md",
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subprocess.run(
        [
            *git_base,
            "update-index",
            "--add",
            "--cacheinfo",
            f"120000,{blob_id},Linked.md",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        [*git_base, "commit", "--quiet", "--no-verify", "-m", "checkpoint"],
        capture_output=True,
        text=True,
        check=True,
    )
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")

    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        "Linked.md",
        "--vault",
        str(vault),
        "--yes",
    )

    assert code == 1
    assert not (vault / "Linked.md").exists()
    assert "symlink" in capsys.readouterr().err


def test_restore_dry_run_shows_the_review_without_writing(tmp_path, capsys, pinned_git_dates):
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    target = vault / "Start-Here.md"
    changed = b"agent edit\n"
    target.write_bytes(changed)

    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        "Start-Here.md",
        "--vault",
        str(vault),
        "--dry-run",
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "M  Start-Here.md" in out
    assert "dry run; nothing written." in out
    assert target.read_bytes() == changed


def test_restore_declined_at_the_review_gate_writes_nothing(
    tmp_path, capsys, monkeypatch, pinned_git_dates
):
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    target = vault / "Start-Here.md"
    changed = b"agent edit\n"
    target.write_bytes(changed)
    monkeypatch.setattr("onyxian.cli._is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        "Start-Here.md",
        "--vault",
        str(vault),
    )

    assert code == 1
    assert "aborted; nothing written." in capsys.readouterr().out
    assert target.read_bytes() == changed


def test_restore_rechecks_a_path_changed_during_review(
    tmp_path, capsys, monkeypatch, pinned_git_dates
):
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    target = vault / "Start-Here.md"
    target.write_bytes(b"first edit\n")
    raced = b"changed while the prompt was open\n"

    def mutate_then_confirm(_question: str, *, assume_yes: bool) -> bool:
        assert not assume_yes
        target.write_bytes(raced)
        return True

    monkeypatch.setattr("onyxian.cli._confirm", mutate_then_confirm)
    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        "Start-Here.md",
        "--vault",
        str(vault),
    )

    assert code == 1
    assert target.read_bytes() == raced
    assert "state changed since the restore review" in capsys.readouterr().err


def test_path_restore_rechecks_a_ledger_row_changed_during_review(
    tmp_path, capsys, monkeypatch, pinned_git_dates
):
    """A file-only recheck must not apply against an unreviewed live ledger row."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    portable = "templates/Note.md"
    target = vault / "templates" / "Note.md"
    changed = b"# agent edit\n"
    target.write_bytes(changed)
    checkpoint_entry = load_lock(vault).get(portable)
    assert checkpoint_entry is not None
    raced_entry = replace(checkpoint_entry, module_version="99.0.0")

    def mutate_ledger_then_confirm(_question: str, *, assume_yes: bool) -> bool:
        assert not assume_yes
        raced_lock = load_lock(vault)
        raced_lock.put(raced_entry)
        save_lock(vault, raced_lock)
        return True

    monkeypatch.setattr("onyxian.cli._confirm", mutate_ledger_then_confirm)
    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        portable,
        "--vault",
        str(vault),
    )

    assert code == 1
    assert target.read_bytes() == changed
    assert load_lock(vault).get(portable) == raced_entry
    assert "ledger changed since the restore review" in capsys.readouterr().err


def test_whole_restore_rechecks_lockfile_before_any_write(
    tmp_path, capsys, monkeypatch, pinned_git_dates
):
    """A raced global ledger must abort the dependent whole-vault restore."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    target = vault / "Start-Here.md"
    changed = b"agent edit\n"
    target.write_bytes(changed)
    portable = "templates/Note.md"
    checkpoint_entry = load_lock(vault).get(portable)
    assert checkpoint_entry is not None
    raced_entry = replace(checkpoint_entry, module_version="99.0.0")

    def mutate_lockfile_then_confirm(_question: str, *, assume_yes: bool) -> bool:
        assert not assume_yes
        raced_lock = load_lock(vault)
        raced_lock.put(raced_entry)
        save_lock(vault, raced_lock)
        return True

    monkeypatch.setattr("onyxian.cli._confirm", mutate_lockfile_then_confirm)
    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        "--vault",
        str(vault),
    )

    assert code == 1
    assert target.read_bytes() == changed
    assert load_lock(vault).get(portable) == raced_entry
    assert ".vault/lock.json" in capsys.readouterr().err


def test_whole_restore_rechecks_the_reviewed_path_set_before_any_write(
    tmp_path, capsys, monkeypatch, pinned_git_dates
):
    """A file created at the prompt must not survive an allegedly exact restore."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    target = vault / "Start-Here.md"
    changed = b"agent edit\n"
    target.write_bytes(changed)
    raced = vault / "appeared-during-review.md"

    def create_path_then_confirm(_question: str, *, assume_yes: bool) -> bool:
        assert not assume_yes
        raced.write_text("new and unreviewed\n", encoding="utf-8")
        return True

    monkeypatch.setattr("onyxian.cli._confirm", create_path_then_confirm)
    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        "--vault",
        str(vault),
    )

    assert code == 1
    assert target.read_bytes() == changed
    assert raced.is_file()
    assert "path set changed since the restore review" in capsys.readouterr().err


def test_restore_accepts_multiple_paths_and_leaves_unselected_changes_alone(
    tmp_path, capsys, pinned_git_dates
):
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    start = vault / "Start-Here.md"
    home = vault / "Home.md"
    assistant = vault / "Onyxian Assistant.md"
    checkpoint_start = start.read_bytes()
    checkpoint_home = home.read_bytes()
    start.write_bytes(b"changed start\n")
    home.write_bytes(b"changed home\n")
    assistant_bytes = b"leave this changed\n"
    assistant.write_bytes(assistant_bytes)

    capsys.readouterr()
    assert (
        run_cli(
            "checkpoint",
            "restore",
            checkpoint_id,
            "Start-Here.md",
            "Home.md",
            "--vault",
            str(vault),
            "--yes",
        )
        == 0
    )

    assert start.read_bytes() == checkpoint_start
    assert home.read_bytes() == checkpoint_home
    assert assistant.read_bytes() == assistant_bytes


def test_restore_git_unavailable_is_an_error_not_a_guard_noop(tmp_path, capsys, monkeypatch):
    vault = init_minimal_vault(tmp_path)
    target = vault / "Start-Here.md"
    changed = b"must survive\n"
    target.write_bytes(changed)
    monkeypatch.setattr("onyxian.checkpoints.shutil.which", lambda _name: None)

    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        "deadbeef",
        "Start-Here.md",
        "--vault",
        str(vault),
        "--yes",
    )

    assert code == 1
    assert target.read_bytes() == changed
    err = capsys.readouterr().err
    assert "restore is unavailable" in err
    assert "vault is unaffected" not in err


def test_path_restore_ignores_an_unselected_gitlink_in_the_checkpoint(
    tmp_path, capsys, pinned_git_dates
):
    """An unrelated unsupported tree entry must not block a safe single-file restore."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    parent = _cp_git(vault, "rev-parse", "HEAD")
    git_base = [
        "git",
        "-c",
        "user.name=Onyxian",
        "-c",
        "user.email=onyxian@localhost",
        f"--git-dir={vault / CHECKPOINTS}",
        f"--work-tree={vault}",
    ]
    subprocess.run(
        [
            *git_base,
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{parent},EmbeddedRepo",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        [*git_base, "commit", "--quiet", "--no-verify", "-m", "checkpoint"],
        capture_output=True,
        text=True,
        check=True,
    )
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    home = vault / "Home.md"
    checkpoint_bytes = home.read_bytes()
    home.write_bytes(b"later edit\n")

    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        "Home.md",
        "--vault",
        str(vault),
        "--yes",
    )

    assert code == 0
    assert home.read_bytes() == checkpoint_bytes


def test_restore_only_dry_run_flag_cannot_accidentally_take_a_snapshot(tmp_path, capsys):
    """A misplaced restore flag must not turn a promised dry run into a write."""
    vault = init_minimal_vault(tmp_path)
    capsys.readouterr()

    code = run_cli("checkpoint", "--dry-run", "--vault", str(vault))

    assert code == 1
    assert not (vault / CHECKPOINTS / "HEAD").exists()
    assert "--dry-run is only valid with `checkpoint restore`" in capsys.readouterr().err


def test_whole_vault_restore_can_recover_a_corrupted_live_ledger(
    tmp_path, capsys, pinned_git_dates
):
    """Recovery must not require successfully parsing the state it was asked to replace."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    checkpoint_lock = load_lock(vault)
    (vault / ".vault" / "lock.json").write_text("{not json\n", encoding="utf-8")

    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        "--vault",
        str(vault),
        "--yes",
    )

    assert code == 0
    assert load_lock(vault) == checkpoint_lock


def test_whole_vault_restore_can_recover_a_deleted_config(tmp_path, capsys, pinned_git_dates):
    """The recovery command must stay reachable when config.yaml is what was lost."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    config = vault / ".vault" / "config.yaml"
    checkpoint_bytes = config.read_bytes()
    config.unlink()

    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        "--vault",
        str(vault),
        "--yes",
    )

    assert code == 0
    assert config.read_bytes() == checkpoint_bytes


def test_path_restore_can_recover_lock_json_itself(tmp_path, capsys, pinned_git_dates):
    """Selecting the historical ledger must not require parsing the corrupt live one."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    checkpoint_lock = load_lock(vault)
    (vault / ".vault" / "lock.json").write_text("{not json\n", encoding="utf-8")

    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        ".vault/lock.json",
        "--vault",
        str(vault),
        "--yes",
    )

    assert code == 0
    assert load_lock(vault) == checkpoint_lock


def test_ledger_only_restore_names_the_path_in_the_review(tmp_path, capsys, pinned_git_dates):
    """A global lock count alone does not show the user which row will change."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    portable = "templates/Note.md"
    checkpoint_entry = load_lock(vault).get(portable)
    assert checkpoint_entry is not None
    changed_lock = load_lock(vault)
    changed_lock.put(replace(checkpoint_entry, module_version="99.0.0"))
    save_lock(vault, changed_lock)

    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        portable,
        "--vault",
        str(vault),
        "--dry-run",
    )

    assert code == 0
    out = capsys.readouterr().out
    assert f"=  {portable}  [content unchanged; restoring checkpoint ledger row]" in out
    assert "re-verifying 1 managed file" in out


def test_restore_rejects_a_known_symlink_before_reading_its_target(
    tmp_path, capsys, monkeypatch, pinned_git_dates
):
    """Once a link is known, even hashing through it crosses the vault boundary."""
    import onyxian.checkpoints as checkpoint_module

    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    portable = "Start-Here.md"
    target = vault / portable
    target.write_bytes(b"agent edit\n")

    monkeypatch.setattr(
        checkpoint_module,
        "first_symlink_component",
        lambda _root, path: path if path == portable else None,
    )

    def unexpected_read(_path: Path, _git_algorithm: str) -> tuple[str, str]:
        pytest.fail("restore followed a path after identifying it as a symlink")

    monkeypatch.setattr(checkpoint_module, "_file_fingerprints", unexpected_read)
    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        portable,
        "--vault",
        str(vault),
        "--yes",
    )

    assert code == 1
    assert target.read_bytes() == b"agent edit\n"
    assert "symlink" in capsys.readouterr().err


def test_restore_read_failure_during_final_recheck_is_reported_as_a_skip(
    tmp_path, capsys, monkeypatch, pinned_git_dates
):
    """A cross-platform simulated sharing denial must not escape as a traceback."""
    import onyxian.checkpoints as checkpoint_module

    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    target = vault / "Start-Here.md"
    changed = b"agent edit\n"
    target.write_bytes(changed)
    real_sha256_file = sha256_file

    def deny_target(path: Path) -> str:
        if path == target:
            raise PermissionError("simulated sharing denial")
        return real_sha256_file(path)

    def deny_after_review(_question: str, *, assume_yes: bool) -> bool:
        assert not assume_yes
        monkeypatch.setattr(checkpoint_module, "sha256_file", deny_target)
        return True

    monkeypatch.setattr("onyxian.cli._confirm", deny_after_review)
    capsys.readouterr()
    try:
        code = run_cli(
            "checkpoint",
            "restore",
            checkpoint_id,
            "Start-Here.md",
            "--vault",
            str(vault),
        )
    except PermissionError as exc:  # pragma: no cover - the regression fails here
        pytest.fail(f"restore leaked a file-read error: {exc}")

    assert code == 1
    assert target.read_bytes() == changed
    assert "could not recheck" in capsys.readouterr().err


def test_restore_read_failure_during_review_is_a_clean_error(
    tmp_path, capsys, monkeypatch, pinned_git_dates
):
    """The review phase must translate an unreadable live file at the CLI boundary."""
    import onyxian.checkpoints as checkpoint_module

    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    target = vault / "Start-Here.md"
    changed = b"agent edit\n"
    target.write_bytes(changed)
    real_fingerprints = checkpoint_module._file_fingerprints

    def deny_target(path: Path, git_algorithm: str) -> tuple[str, str]:
        if path == target:
            raise PermissionError("simulated sharing denial")
        return real_fingerprints(path, git_algorithm)

    monkeypatch.setattr(checkpoint_module, "_file_fingerprints", deny_target)
    capsys.readouterr()
    try:
        code = run_cli(
            "checkpoint",
            "restore",
            checkpoint_id,
            "Start-Here.md",
            "--vault",
            str(vault),
            "--yes",
        )
    except PermissionError as exc:  # pragma: no cover - the regression fails here
        pytest.fail(f"restore leaked a file-read error: {exc}")

    assert code == 1
    assert target.read_bytes() == changed
    assert "cannot inspect" in capsys.readouterr().err


def test_path_restore_ignores_an_unselected_nonportable_checkpoint_name(
    tmp_path, capsys, pinned_git_dates
):
    """One POSIX-only user filename must not block recovery of an unrelated note."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    git_base = [
        "git",
        "-c",
        "user.name=Onyxian",
        "-c",
        "user.email=onyxian@localhost",
        "-c",
        "core.protectNTFS=false",
        f"--git-dir={vault / CHECKPOINTS}",
        f"--work-tree={vault}",
    ]
    blob_id = subprocess.run(
        [*git_base, "hash-object", "-w", "--stdin"],
        input="portable only on POSIX\n",
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    subprocess.run(
        [
            *git_base,
            "update-index",
            "--add",
            "--cacheinfo",
            f"100644,{blob_id},Odd:Name.md",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        [*git_base, "commit", "--quiet", "--no-verify", "-m", "checkpoint"],
        capture_output=True,
        text=True,
        check=True,
    )
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    home = vault / "Home.md"
    checkpoint_bytes = home.read_bytes()
    home.write_bytes(b"later edit\n")

    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        "Home.md",
        "--vault",
        str(vault),
        "--yes",
    )

    assert code == 0
    assert home.read_bytes() == checkpoint_bytes


def test_whole_restore_rejects_case_colliding_checkpoint_paths_before_writing(
    tmp_path, capsys, pinned_git_dates
):
    """One checkpoint must not map two files onto one path on Windows or macOS."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("checkpoint", "--vault", str(vault)) == 0
    git_base = [
        "git",
        "-c",
        "user.name=Onyxian",
        "-c",
        "user.email=onyxian@localhost",
        "-c",
        "core.ignorecase=false",
        f"--git-dir={vault / CHECKPOINTS}",
        f"--work-tree={vault}",
    ]
    for name, content in (
        ("Collision.md", "first\n"),
        ("collision.md", "second\n"),
    ):
        blob_id = subprocess.run(
            [*git_base, "hash-object", "-w", "--stdin"],
            input=content,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(
            [
                *git_base,
                "update-index",
                "--add",
                "--cacheinfo",
                f"100644,{blob_id},{name}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    subprocess.run(
        [*git_base, "commit", "--quiet", "--no-verify", "-m", "checkpoint"],
        capture_output=True,
        text=True,
        check=True,
    )
    checkpoint_id = _cp_git(vault, "rev-parse", "--short", "HEAD")
    home = vault / "Home.md"
    changed = b"must remain unchanged\n"
    home.write_bytes(changed)

    capsys.readouterr()
    code = run_cli(
        "checkpoint",
        "restore",
        checkpoint_id,
        "--vault",
        str(vault),
        "--yes",
    )

    assert code == 1
    assert home.read_bytes() == changed
    assert not (vault / "Collision.md").exists()
    assert "differ only in case" in capsys.readouterr().err

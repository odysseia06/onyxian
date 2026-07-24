"""The opt-in vault checkpoint guard — a recovery net, not scope enforcement (issue #11, phase 1).

The checkpoint CLI shells out to ``git`` with a **separate** git dir under
``.vault/checkpoints/`` so it never reads or writes a user's own ``.git``. Snapshot
timestamps are pinned here via ``GIT_AUTHOR_DATE``/``GIT_COMMITTER_DATE`` (``ONYXIAN_NOW``
is date-only and does not cover git's clock) so the displayed output is byte-stable.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from conftest import init_minimal_vault, run_cli

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


def test_quiet_prints_nothing_but_still_snapshots(tmp_path, capsys, pinned_git_dates):
    vault = init_minimal_vault(tmp_path)
    capsys.readouterr()
    code = run_cli("checkpoint", "--quiet", "--vault", str(vault))
    assert code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (vault / CHECKPOINTS / "HEAD").is_file()

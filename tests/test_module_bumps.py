"""The module-version-bump guard (tools/check_module_bumps.py).

Each test builds a throwaway git repo in tmp_path, tags a baseline release, then
runs the guard as a subprocess against that repo — the same way CI invokes it.
The guard is stdlib-only, so these tests never import it; they exercise the real
entry point, its exit code, and its output.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "check_module_bumps.py"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def write_module(
    repo: Path, mod_id: str, version: str, files: dict[str, str] | None = None
) -> None:
    d = repo / "modules" / mod_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "module.yaml").write_text(
        f"name: {mod_id}\nversion: {version}\nsummary: a synthetic module\n",
        encoding="utf-8",
        newline="\n",
    )
    for rel, content in (files or {}).items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")


def commit(repo: Path, msg: str = "change") -> None:
    git(repo, "add", "-A")
    git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg)


def run_guard(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), str(repo)], capture_output=True, text=True)


def init_repo(tmp_path: Path) -> Path:
    """An empty git repo with a committer identity — no commits, no tags yet."""
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "config", "user.email", "test@example.com")
    git(r, "config", "user.name", "Test Harness")
    return r


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with one committed module at 0.2.2, tagged v1.1.0."""
    r = init_repo(tmp_path)
    write_module(r, "daily-notes", "0.2.2", {"assets/Note.md": "original\n"})
    commit(r, "baseline")
    git(r, "tag", "v1.1.0")
    return r


def test_content_change_without_bump_fails(repo: Path) -> None:
    write_module(repo, "daily-notes", "0.2.2", {"assets/Note.md": "edited\n"})
    commit(repo, "edit a managed file, no bump")

    result = run_guard(repo)

    assert result.returncode != 0
    assert "FAIL" in result.stdout
    assert "daily-notes" in result.stdout
    assert "v1.1.0" in result.stdout  # names the baseline tag
    assert "0.2.2" in result.stdout  # names the offending version
    assert "modules/daily-notes/assets/Note.md" in result.stdout  # names the changed file


def test_content_change_with_bump_passes(repo: Path) -> None:
    write_module(repo, "daily-notes", "0.2.3", {"assets/Note.md": "edited\n"})
    commit(repo, "edit a managed file and bump")

    result = run_guard(repo)

    assert result.returncode == 0
    assert "ok:" in result.stdout
    assert "1 module(s) changed" in result.stdout


def test_bump_without_content_change_passes(repo: Path) -> None:
    # Only module.yaml moves — no asset edits. Harmless, must not fail.
    write_module(repo, "daily-notes", "0.2.3", {"assets/Note.md": "original\n"})
    commit(repo, "bump the version, touch nothing else")

    result = run_guard(repo)

    assert result.returncode == 0
    assert "FAIL" not in result.stdout


def test_backwards_version_fails_with_distinct_message(repo: Path) -> None:
    write_module(repo, "daily-notes", "0.2.1", {"assets/Note.md": "edited\n"})
    commit(repo, "edit a managed file and lower the version")

    result = run_guard(repo)

    assert result.returncode != 0
    assert "backwards" in result.stdout  # distinct from the plain unbumped message
    assert "daily-notes" in result.stdout
    assert "0.2.2" in result.stdout  # the baseline version
    assert "0.2.1" in result.stdout  # the (lower) worktree version


def test_no_release_tag_is_bootstrap_noop(tmp_path: Path) -> None:
    r = init_repo(tmp_path)
    write_module(r, "daily-notes", "0.2.2", {"assets/Note.md": "original\n"})
    commit(r, "first ever commit, no tag")

    result = run_guard(r)

    assert result.returncode == 0
    assert "no release tag reachable" in result.stdout


def test_engine_only_change_exits_zero(repo: Path) -> None:
    (repo / "core").mkdir()
    (repo / "core" / "engine.py").write_text("print('hi')\n", encoding="utf-8", newline="\n")
    commit(repo, "engine-only change, nothing under modules/")

    result = run_guard(repo)

    assert result.returncode == 0
    assert "no module content changes" in result.stdout


def test_multiple_offending_modules_all_reported(tmp_path: Path) -> None:
    r = init_repo(tmp_path)
    write_module(r, "daily-notes", "0.2.2", {"assets/Note.md": "original\n"})
    write_module(r, "fitness", "0.2.1", {"assets/Log.md": "original\n"})
    commit(r, "baseline")
    git(r, "tag", "v1.1.0")

    write_module(r, "daily-notes", "0.2.2", {"assets/Note.md": "edited\n"})
    write_module(r, "fitness", "0.2.1", {"assets/Log.md": "edited\n"})
    commit(r, "edit both, bump neither")

    result = run_guard(r)

    assert result.returncode != 0
    assert "daily-notes" in result.stdout
    assert "fitness" in result.stdout
    assert result.stdout.count("FAIL") == 2


def test_new_module_absent_at_tag_passes(repo: Path) -> None:
    write_module(repo, "music", "0.1.0", {"assets/Playlist.md": "brand new\n"})
    commit(repo, "add a brand-new module")

    result = run_guard(repo)

    assert result.returncode == 0
    assert "FAIL" not in result.stdout


def test_module_deleted_from_worktree_is_skipped(repo: Path) -> None:
    import shutil

    shutil.rmtree(repo / "modules" / "daily-notes")
    commit(repo, "remove a module entirely")

    result = run_guard(repo)

    assert result.returncode == 0
    assert "FAIL" not in result.stdout

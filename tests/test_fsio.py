"""fsio's last line of defense: the atomic writer never replaces a symlink (issue #53),
and its rename is durable across a power loss (issue #60).

Plan and apply gate symlinks with better messages; this backstop covers every
other write path (sources update, diff resolution, config edits), turning
silent link destruction into a loud, safe error.
"""

import os

import pytest
from conftest import can_symlink

from onyxian.errors import ApplyError
from onyxian.fsio import remove_file_durable, write_bytes_atomic


def test_write_bytes_atomic_refuses_a_symlink_destination(tmp_path):
    if not can_symlink(tmp_path):
        pytest.skip("filesystem does not permit symlink creation")
    real = tmp_path / "real.md"
    real.write_bytes(b"theirs\n")
    link = tmp_path / "link.md"
    link.symlink_to(real)
    with pytest.raises(ApplyError, match="symlink"):
        write_bytes_atomic(link, b"new bytes\n")
    assert link.is_symlink()
    assert real.read_bytes() == b"theirs\n"


def test_write_bytes_atomic_refuses_a_dangling_symlink_destination(tmp_path):
    if not can_symlink(tmp_path):
        pytest.skip("filesystem does not permit symlink creation")
    link = tmp_path / "link.md"
    link.symlink_to(tmp_path / "nowhere.md")
    with pytest.raises(ApplyError, match="symlink"):
        write_bytes_atomic(link, b"new bytes\n")
    assert link.is_symlink()


def test_write_bytes_atomic_fsyncs_the_parent_directory(tmp_path, monkeypatch):
    """#60: fsyncing the temp file alone does not make the *rename* durable. After a
    power loss the ledger could hold the new sha while the disk kept the old bytes,
    and the planner would then read the engine's own file as user-modified forever."""
    if os.name == "nt":
        pytest.skip("a directory cannot be opened for fsync on Windows")
    real_fsync = os.fsync
    synced: list[tuple[int, int]] = []

    def spy(fd: int) -> None:
        st = os.fstat(fd)
        synced.append((st.st_dev, st.st_ino))
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", spy)
    write_bytes_atomic(tmp_path / "note.md", b"bytes\n")
    monkeypatch.undo()
    st = os.stat(tmp_path)
    assert (st.st_dev, st.st_ino) in synced


def test_remove_file_durable_fsyncs_the_parent_directory(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("a directory cannot be opened for fsync on Windows")
    path = tmp_path / "note.md"
    path.write_bytes(b"bytes\n")
    real_fsync = os.fsync
    synced: list[tuple[int, int]] = []

    def spy(fd: int) -> None:
        st = os.fstat(fd)
        synced.append((st.st_dev, st.st_ino))
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", spy)
    remove_file_durable(path)
    monkeypatch.undo()
    st = os.stat(tmp_path)
    assert (st.st_dev, st.st_ino) in synced


def test_write_bytes_atomic_survives_a_refused_directory_fsync(tmp_path, monkeypatch):
    """That fsync is best effort: Windows cannot open a directory for it at all and
    some filesystems refuse outright — neither may cost the caller a good write."""

    def refuse(*args, **kwargs):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(os, "open", refuse)
    write_bytes_atomic(tmp_path / "note.md", b"bytes\n")
    monkeypatch.undo()
    assert (tmp_path / "note.md").read_bytes() == b"bytes\n"

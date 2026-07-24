"""fsio's last line of defense: the atomic writer never replaces a symlink (issue #53).

Plan and apply gate symlinks with better messages; this backstop covers every
other write path (sources update, diff resolution, config edits), turning
silent link destruction into a loud, safe error.
"""

import pytest
from conftest import can_symlink

from onyxian.errors import ApplyError
from onyxian.fsio import write_bytes_atomic


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

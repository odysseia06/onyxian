"""Portable-path discipline (KICKSTART.md §9.5): strictest-OS rules enforced everywhere."""

import pytest

from onyxian.errors import PathError
from onyxian.paths import parent_portable, split_portable, to_native


@pytest.mark.parametrize(
    "path,expected",
    [
        ("Templates", ("Templates",)),
        ("Templates/Note.md", ("Templates", "Note.md")),
        ("Daily Notes/2026/06.md", ("Daily Notes", "2026", "06.md")),
        (".vault/config.yaml", (".vault", "config.yaml")),
        ("{{root}}/Strategy.md", ("{{root}}", "Strategy.md")),  # raw manifest form is checkable too
        ("Ünïcode/nötes.md", ("Ünïcode", "nötes.md")),
    ],
)
def test_valid_paths(path, expected):
    assert split_portable(path) == expected


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/absolute",
        "trailing/",
        "back\\slash",
        "C:/drive",
        "a//b",
        "a/./b",
        "a/../b",
        "..",
        "dot./end",
        "space /end",
        " lead/x",
        "ta*b",
        "qu?estion",
        'quo"te',
        "pi|pe",
        "less<than",
        "co:lon",
        "CON",
        "con.md",
        "Notes/COM7.base",
        "lpt1.txt/x",
        "ctrl\x01char",
    ],
)
def test_invalid_paths(path):
    with pytest.raises(PathError):
        split_portable(path)


def test_error_names_the_origin():
    with pytest.raises(PathError, match="module 'demo'"):
        split_portable("bad|name", origin="module 'demo'")


def test_to_native_joins_segments(tmp_path):
    assert to_native(tmp_path, "a/b/c.md") == tmp_path / "a" / "b" / "c.md"


def test_parent_portable():
    assert parent_portable("a/b/c.md") == "a/b"
    assert parent_portable("a") is None

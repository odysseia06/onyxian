"""Portable-path discipline (KICKSTART.md §9.5): strictest-OS rules enforced everywhere."""

import pytest
from conftest import can_symlink, make_config, write_module

from onyxian.errors import PathError
from onyxian.intent import build_desired_state
from onyxian.paths import (
    check_casefold_unique,
    first_symlink_component,
    parent_portable,
    split_portable,
    to_native,
)
from onyxian.repo import discover_modules
from onyxian.resolve import resolve_modules


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


# --------------------------------------------------------- symlink walk (issue #53)


def test_first_symlink_component_names_the_earliest_link(tmp_path):
    if not can_symlink(tmp_path):
        pytest.skip("filesystem does not permit symlink creation")
    real = tmp_path / "real"
    (real / "b").mkdir(parents=True)
    (tmp_path / "a").symlink_to(real, target_is_directory=True)
    assert first_symlink_component(tmp_path, "a/b/c.md") == "a"
    assert first_symlink_component(tmp_path, "real/b/c.md") is None


def test_first_symlink_component_sees_dangling_and_final_links(tmp_path):
    if not can_symlink(tmp_path):
        pytest.skip("filesystem does not permit symlink creation")
    (tmp_path / "gone.md").symlink_to(tmp_path / "nowhere.md")
    assert first_symlink_component(tmp_path, "gone.md") == "gone.md"
    assert first_symlink_component(tmp_path, "absent/child.md") is None


# --------------------------------------------------- case-fold collisions (issue #8)


def test_casefold_unique_accepts_distinct_and_legitimately_nested_paths():
    # Distinct names, plus a folder and a file nested under it with the SAME
    # spelling — the common, correct shape — must not trip the check.
    check_casefold_unique(
        [
            ("A.md", "x"),
            ("B.md", "y"),
            ("Templates", "core"),
            ("Templates/Note.md", "core"),
        ]
    )


def test_casefold_unique_rejects_whole_path_twins():
    with pytest.raises(PathError) as exc:
        check_casefold_unique([("A.md", "foo"), ("a.md", "bar")])
    msg = str(exc.value)
    assert "A.md" in msg and "a.md" in msg
    assert "'foo'" in msg and "'bar'" in msg
    assert "case-insensitive filesystem" in msg


def test_casefold_unique_rejects_prefix_collision_dir_vs_file():
    # A file under `Dir/` collides with a differently-cased folder `dir` on a
    # case-insensitive filesystem; walking prefixes catches it.
    with pytest.raises(PathError) as exc:
        check_casefold_unique([("Dir/x.md", "a"), ("dir", "b")])
    msg = str(exc.value)
    assert "Dir/x.md" in msg and "dir" in msg
    assert "'a'" in msg and "'b'" in msg


def test_casefold_collision_across_modules_fails_at_plan_time(tmp_path):
    """Two modules whose desired paths differ only in case fail when the desired
    state is built (plan time), naming both spellings and both owning modules."""
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(modules_root, "foo", seeds={"Notes/Inbox.md": "a\n"})
    write_module(modules_root, "bar", seeds={"notes/inbox.md": "b\n"})
    config = make_config({"foo": {"version": "0.1.0"}, "bar": {"version": "0.1.0"}})
    manifests = resolve_modules(config, discover_modules(modules_root))
    with pytest.raises(PathError) as exc:
        build_desired_state(config, manifests)
    msg = str(exc.value)
    assert "Notes/Inbox.md" in msg and "notes/inbox.md" in msg
    assert "'foo'" in msg and "'bar'" in msg
    assert "case-insensitive filesystem" in msg

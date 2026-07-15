"""Lockfile ledger: deterministic, validated, every transition explicit (KICKSTART.md §8.1)."""

import json

import pytest

from onyxian.errors import LockError
from onyxian.lockio import load_lock, lock_path, render_lock_text, save_lock
from onyxian.model import Lock, LockEntry


def entry(path: str, sha: str = "ab" * 32) -> LockEntry:
    return LockEntry(path=path, sha256=sha, module="core", module_version="0.1.0", kind="managed")


def test_missing_lockfile_is_an_empty_ledger(tmp_path):
    assert load_lock(tmp_path).entries == {}


def test_roundtrip_preserves_entries(tmp_path):
    lock = Lock()
    lock.put(entry("b/file.md"))
    lock.put(
        LockEntry(
            path="a.md", sha256="cd" * 32, module="core", module_version="0.1.0", kind="seeded"
        )
    )
    save_lock(tmp_path, lock)
    loaded = load_lock(tmp_path)
    assert loaded.entries == lock.entries


def test_serialization_is_sorted_and_stable(tmp_path):
    lock = Lock()
    lock.put(entry("z.md"))
    lock.put(entry("a.md"))
    text = render_lock_text(lock)
    assert text.index('"a.md"') < text.index('"z.md"')
    assert text == render_lock_text(lock)
    assert text.endswith("\n")
    parsed = json.loads(text)
    assert list(parsed["entries"][0]) == [
        "path",
        "sha256",
        "module",
        "module_version",
        "kind",
        "location",
    ]


def test_put_replaces_by_path():
    lock = Lock()
    lock.put(entry("a.md", "11" * 32))
    lock.put(entry("a.md", "22" * 32))
    assert lock.get("a.md").sha256 == "22" * 32
    assert len(lock.entries) == 1


@pytest.mark.parametrize(
    "payload,match",
    [
        ("[]", "JSON object"),
        ('{"lock_version": 99, "entries": []}', "lock_version"),
        ('{"lock_version": 1, "entries": 3}', "must be a list"),
        ('{"lock_version": 1, "entries": [{"path": "a"}]}', "exactly the keys"),
        (
            '{"lock_version": 1, "entries": ['
            '{"path": "a", "sha256": "x", "module": "m", "module_version": "1", "kind": "weird", "location": "vault"}]}',
            "kind",
        ),
    ],
)
def test_malformed_lockfiles_are_rejected(tmp_path, payload, match):
    lock_path(tmp_path).parent.mkdir(parents=True)
    lock_path(tmp_path).write_text(payload, encoding="utf-8")
    with pytest.raises(LockError, match=match):
        load_lock(tmp_path)


def test_declined_roundtrips(tmp_path):
    """A keep-mine decline (issue #4) survives save/load; the key is optional."""
    lock = Lock()
    lock.put(
        LockEntry(
            path="a.md",
            sha256="ab" * 32,
            module="core",
            module_version="0.1.0",
            kind="managed",
            declined="cd" * 32,
        )
    )
    save_lock(tmp_path, lock)
    assert load_lock(tmp_path).get("a.md").declined == "cd" * 32


def test_declined_is_emitted_only_when_set():
    """Undeclined rows must serialize byte-identically to the pre-#4 format
    (LOCK_VERSION stays 1; golden lock.json fixtures must not drift)."""
    lock = Lock()
    lock.put(entry("plain.md"))
    lock.put(
        LockEntry(
            path="kept.md",
            sha256="ab" * 32,
            module="core",
            module_version="0.1.0",
            kind="managed",
            declined="cd" * 32,
        )
    )
    parsed = json.loads(render_lock_text(lock))
    rows = {row["path"]: row for row in parsed["entries"]}
    assert list(rows["plain.md"]) == [
        "path",
        "sha256",
        "module",
        "module_version",
        "kind",
        "location",
    ]
    assert list(rows["kept.md"]) == [
        "path",
        "sha256",
        "module",
        "module_version",
        "kind",
        "location",
        "declined",
    ]
    assert rows["kept.md"]["declined"] == "cd" * 32


@pytest.mark.parametrize(
    "declined,match",
    [
        ('""', "non-empty string"),  # present but empty
        ("3", "non-empty string"),  # wrong type
    ],
)
def test_malformed_declined_is_rejected(tmp_path, declined, match):
    payload = (
        '{"lock_version": 1, "entries": ['
        '{"path": "a", "sha256": "x", "module": "m", "module_version": "1",'
        f' "kind": "managed", "location": "vault", "declined": {declined}}}]}}'
    )
    lock_path(tmp_path).parent.mkdir(parents=True)
    lock_path(tmp_path).write_text(payload, encoding="utf-8")
    with pytest.raises(LockError, match=match):
        load_lock(tmp_path)


def test_unknown_keys_are_still_rejected(tmp_path):
    payload = (
        '{"lock_version": 1, "entries": ['
        '{"path": "a", "sha256": "x", "module": "m", "module_version": "1",'
        ' "kind": "managed", "location": "vault", "surprise": "y"}]}'
    )
    lock_path(tmp_path).parent.mkdir(parents=True)
    lock_path(tmp_path).write_text(payload, encoding="utf-8")
    with pytest.raises(LockError, match="keys"):
        load_lock(tmp_path)


def test_duplicate_paths_are_rejected(tmp_path):
    raw = {
        "lock_version": 1,
        "entries": [
            {
                "path": "a.md",
                "sha256": "x1",
                "module": "m",
                "module_version": "1",
                "kind": "managed",
                "location": "vault",
            },
            {
                "path": "a.md",
                "sha256": "x2",
                "module": "m",
                "module_version": "1",
                "kind": "managed",
                "location": "vault",
            },
        ],
    }
    lock_path(tmp_path).parent.mkdir(parents=True)
    lock_path(tmp_path).write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(LockError, match="duplicate"):
        load_lock(tmp_path)

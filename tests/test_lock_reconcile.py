"""Guided repair for lockfiles forked by a file-sync service (issue #78)."""

import json

from conftest import init_minimal_vault, run_cli, tree_hashes

from onyxian import lock_reconcile
from onyxian.fsio import sha256_file


def _fork_lock(vault):
    canonical = vault / ".vault" / "lock.json"
    active = json.loads(canonical.read_text(encoding="utf-8"))
    active.update(generation=4, machine_id="laptop")
    canonical.write_text(json.dumps(active, indent=2) + "\n", encoding="utf-8", newline="\n")

    sibling = vault / ".vault" / "lock.sync-conflict-20260706-090923-DESKTOP.json"
    fork = json.loads(json.dumps(active))
    fork.update(generation=6, machine_id="desktop")
    sibling.write_text(json.dumps(fork, indent=2) + "\n", encoding="utf-8", newline="\n")
    return canonical, sibling


def test_reconcile_dry_run_reviews_provenance_and_disk_mismatches_without_writing(
    tmp_path, capsys, monkeypatch
):
    """Dropping either mismatched row would erase ownership history, so the review names
    both and dry-run leaves the complete fork untouched."""
    monkeypatch.setenv("ONYXIAN_MACHINE_ID", "repair-machine")
    vault = init_minimal_vault(tmp_path)
    _canonical, sibling = _fork_lock(vault)
    note = vault / "templates" / "Note.md"
    note.write_text(note.read_text(encoding="utf-8") + "customized\n", encoding="utf-8")
    (vault / "Onyxian Assistant.md").unlink()
    before = tree_hashes(vault)
    capsys.readouterr()

    code = run_cli(
        "lock",
        "reconcile",
        "--vault",
        str(vault),
        "--keep",
        sibling.name,
        "--dry-run",
    )
    out = capsys.readouterr().out

    assert code == 0
    assert sibling.name in out
    assert "desktop" in out and "generation 6" in out
    assert "templates/Note.md" in out and "changed on disk" in out
    assert "Onyxian Assistant.md" in out and "missing from disk" in out
    assert "dry run" in out.lower()
    assert tree_hashes(vault) == before


def test_reconcile_reports_an_unreadable_row_without_invalidating_its_ledger(
    tmp_path, capsys, monkeypatch
):
    """A transient Windows sharing denial is an unverifiable row, not grounds to reject
    an otherwise valid survivor; the row remains safe because reconciliation keeps it."""
    vault = init_minimal_vault(tmp_path)
    _canonical, sibling = _fork_lock(vault)
    target = vault / "templates" / "Note.md"

    def deny_target(path):
        if path == target:
            raise PermissionError("simulated sharing denial")
        return sha256_file(path)

    monkeypatch.setattr(lock_reconcile, "sha256_file", deny_target)
    capsys.readouterr()

    code = run_cli(
        "lock",
        "reconcile",
        "--vault",
        str(vault),
        "--keep",
        sibling.name,
        "--dry-run",
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "not verifiable (row kept)" in out
    assert "templates/Note.md" in out
    assert sibling.is_file()


def test_reconcile_promotes_selected_ledger_retires_siblings_and_preserves_rows(
    tmp_path, capsys, monkeypatch
):
    """The selected fork becomes canonical, while changed/missing rows stay in the ledger
    so a later apply cannot mistake customized content for an unowned file."""
    monkeypatch.setenv("ONYXIAN_MACHINE_ID", "repair-machine")
    vault = init_minimal_vault(tmp_path)
    canonical, sibling = _fork_lock(vault)
    note = vault / "templates" / "Note.md"
    note.write_text(note.read_text(encoding="utf-8") + "customized\n", encoding="utf-8")
    (vault / "Onyxian Assistant.md").unlink()
    capsys.readouterr()

    code = run_cli(
        "lock",
        "reconcile",
        "--vault",
        str(vault),
        "--keep",
        sibling.name,
        "--yes",
    )

    assert code == 0
    repaired = json.loads(canonical.read_text(encoding="utf-8"))
    assert repaired["generation"] == 7
    assert repaired["machine_id"] == "repair-machine"
    assert {row["path"] for row in repaired["entries"]} >= {
        "templates/Note.md",
        "Onyxian Assistant.md",
    }
    assert not sibling.exists()
    assert "reconciled lock.json" in capsys.readouterr().out


def test_reconcile_does_not_retire_a_conflicted_json_that_is_not_a_lock_sibling(
    tmp_path, monkeypatch
):
    """The repair deletes state candidates, so a broad `startswith("lock")` match would
    turn an unrelated .vault JSON file into collateral damage."""
    monkeypatch.setenv("ONYXIAN_MACHINE_ID", "repair-machine")
    vault = init_minimal_vault(tmp_path)
    _canonical, sibling = _fork_lock(vault)
    unrelated = vault / ".vault" / "lock-notes (conflicted copy).json"
    unrelated.write_text('{"notes": true}\n', encoding="utf-8")

    code = run_cli(
        "lock",
        "reconcile",
        "--vault",
        str(vault),
        "--keep",
        sibling.name,
        "--yes",
    )

    assert code == 0
    assert unrelated.is_file()


def test_reconcile_generation_advances_past_newest_fork_when_older_ledger_survives(
    tmp_path, monkeypatch
):
    """Choosing older content must not move the ordering counter backward; otherwise the
    discarded machine's next stale sync would appear newer than the repaired ledger."""
    monkeypatch.setenv("ONYXIAN_MACHINE_ID", "repair-machine")
    vault = init_minimal_vault(tmp_path)
    canonical, sibling = _fork_lock(vault)  # canonical gen 4, sibling gen 6

    code = run_cli(
        "lock",
        "reconcile",
        "--vault",
        str(vault),
        "--keep",
        canonical.name,
        "--yes",
    )

    assert code == 0
    repaired = json.loads(canonical.read_text(encoding="utf-8"))
    assert repaired["generation"] == 7
    assert not sibling.exists()


def test_interactive_reconcile_numbers_the_candidates_it_accepts(tmp_path, capsys, monkeypatch):
    """The prompt accepts numeric choices, so the review must expose those same numbers."""
    vault = init_minimal_vault(tmp_path)
    _canonical, sibling = _fork_lock(vault)
    monkeypatch.setattr("onyxian.cli._is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")
    capsys.readouterr()

    code = run_cli("lock", "reconcile", "--vault", str(vault), "--dry-run")
    out = capsys.readouterr().out

    assert code == 0
    assert "[1] lock.json" in out
    assert f"[2] {sibling.name}" in out
    assert sibling.is_file()


def test_reconcile_rechecks_candidate_bytes_after_confirmation(tmp_path, capsys, monkeypatch):
    """A sync service can deliver another fork while the review is open; the selected
    bytes shown to the user must be the bytes promoted."""
    vault = init_minimal_vault(tmp_path)
    canonical, sibling = _fork_lock(vault)
    canonical_before = canonical.read_bytes()

    def change_candidate(_question, *, assume_yes):
        assert not assume_yes
        fork = json.loads(sibling.read_text(encoding="utf-8"))
        fork["machine_id"] = "desktop-changed-during-review"
        sibling.write_text(json.dumps(fork, indent=2) + "\n", encoding="utf-8", newline="\n")
        return True

    monkeypatch.setattr("onyxian.cli._confirm", change_candidate)
    capsys.readouterr()

    code = run_cli(
        "lock",
        "reconcile",
        "--vault",
        str(vault),
        "--keep",
        sibling.name,
    )

    assert code == 1
    assert "lock candidates changed since review" in capsys.readouterr().err
    assert canonical.read_bytes() == canonical_before
    assert sibling.is_file()


def test_reconcile_rechecks_disk_rows_after_confirmation(tmp_path, capsys, monkeypatch):
    """A file changing while the review is open invalidates its hash classification."""
    vault = init_minimal_vault(tmp_path)
    canonical, sibling = _fork_lock(vault)
    canonical_before = canonical.read_bytes()
    note = vault / "templates" / "Note.md"

    def change_managed_file(_question, *, assume_yes):
        assert not assume_yes
        note.write_text(note.read_text(encoding="utf-8") + "late edit\n", encoding="utf-8")
        return True

    monkeypatch.setattr("onyxian.cli._confirm", change_managed_file)
    capsys.readouterr()

    code = run_cli(
        "lock",
        "reconcile",
        "--vault",
        str(vault),
        "--keep",
        sibling.name,
    )

    assert code == 1
    assert "vault files changed since review" in capsys.readouterr().err
    assert canonical.read_bytes() == canonical_before
    assert sibling.is_file()


def test_noninteractive_reconcile_requires_an_explicit_survivor(tmp_path, capsys, monkeypatch):
    """`--yes` may confirm a reviewed choice; it must never silently choose a fork."""
    monkeypatch.setattr("onyxian.cli._is_interactive", lambda: False)
    vault = init_minimal_vault(tmp_path)
    canonical, sibling = _fork_lock(vault)
    before = canonical.read_bytes()
    capsys.readouterr()

    code = run_cli("lock", "reconcile", "--vault", str(vault), "--yes")

    assert code == 1
    assert "--keep" in capsys.readouterr().err
    assert canonical.read_bytes() == before
    assert sibling.is_file()

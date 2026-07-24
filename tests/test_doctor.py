"""Doctor: read-only diagnosis with actionable findings (KICKSTART.md §9.4)."""

import pytest
from conftest import REAL_MODULES, can_symlink, init_minimal_vault

from onyxian import compat
from onyxian.compat import VERIFIED_OBSIDIAN
from onyxian.compat import probe_obsidian_version as real_probe  # pre-fixture binding
from onyxian.doctor import FAIL, INFO, OK, WARN, exit_code, run_doctor
from onyxian.lockio import load_lock, save_lock
from onyxian.model import LockEntry


def doctor(vault, probe=None):
    findings = run_doctor(vault, REAL_MODULES, obsidian_probe=probe)
    return findings, exit_code(findings)


def test_fresh_vault_is_healthy(tmp_path):
    vault = init_minimal_vault(tmp_path)
    findings, code = doctor(vault)
    assert code == 0
    # Obsidian-less machines (CI, and tests via the conftest fixture) get
    # exactly one INFO — compat not checked — and stay healthy.
    not_ok = [f for f in findings if f.level != OK]
    assert [f.level for f in not_ok] == [INFO]
    assert "Obsidian compat not checked" in not_ok[0].message


def test_missing_managed_file_warns_and_suggests_apply(tmp_path):
    vault = init_minimal_vault(tmp_path)
    (vault / "templates" / "Note.md").unlink()  # golden answers use kebab-case
    findings, code = doctor(vault)
    assert code == 1
    warns = [f for f in findings if f.level == WARN]
    assert any("missing from disk" in f.message for f in warns)
    assert any("onyxian apply" in f.suggestion for f in warns)


def test_user_customized_managed_file_is_informational_only(tmp_path):
    vault = init_minimal_vault(tmp_path)
    note = vault / "templates" / "Note.md"
    note.write_text(note.read_text(encoding="utf-8") + "my tweak\n", encoding="utf-8")
    findings, code = doctor(vault)
    assert code == 0
    infos = [f for f in findings if f.level == INFO]
    assert any("customized" in f.message for f in infos)


def test_symlinked_managed_path_warns(tmp_path):
    """A link to identical bytes hashes clean, so without an explicit check
    doctor would call this vault healthy while updates would destroy the link
    (issue #53)."""
    if not can_symlink(tmp_path):
        pytest.skip("filesystem does not permit symlink creation")
    vault = init_minimal_vault(tmp_path)
    note = vault / "templates" / "Note.md"
    real = tmp_path / "real-note.md"
    real.write_text(note.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    note.unlink()
    note.symlink_to(real)
    findings, code = doctor(vault)
    assert code == 1
    warns = [f for f in findings if f.level == WARN]
    assert any("symlink" in f.message for f in warns)


def test_orphaned_lock_entry_warns(tmp_path):
    vault = init_minimal_vault(tmp_path)
    lock = load_lock(vault)
    lock.put(
        LockEntry(
            path="Ghost.md", sha256="0" * 64, module="ghost", module_version="0.1.0", kind="managed"
        )
    )
    save_lock(vault, lock)
    findings, code = doctor(vault)
    assert code == 1
    assert any("orphaned" in f.message for f in findings if f.level == WARN)


def test_broken_config_fails_fast(tmp_path):
    vault = init_minimal_vault(tmp_path)
    (vault / ".vault" / "config.yaml").write_text("[unclosed", encoding="utf-8")
    findings, code = doctor(vault)
    assert code == 2
    assert findings[-1].level == FAIL


def test_unmanaged_directory_fails_with_guidance(tmp_path):
    findings, code = doctor(tmp_path)
    assert code == 2
    assert any("not an Onyxian-managed vault" in f.message for f in findings)


def test_sync_conflict_siblings_in_vault_dir_warn(tmp_path):
    """A sync service's conflicted copy of the ledger is the canonical forked-vault
    tell (KICKSTART.md §8.4, issue #18); doctor must surface it, not read past it."""
    vault = init_minimal_vault(tmp_path)
    (vault / ".vault" / "lock (conflicted copy).json").write_text("{}", encoding="utf-8")
    (vault / ".vault" / "lock.sync-conflict-20260706-090923-ABC1234.json").write_text(
        "{}", encoding="utf-8"
    )
    findings, code = doctor(vault)
    assert code == 1
    warns = [f for f in findings if f.level == WARN and "sync-conflict" in f.message]
    assert len(warns) == 1
    assert "lock (conflicted copy).json" in warns[0].message
    assert "lock.sync-conflict-20260706-090923-ABC1234.json" in warns[0].message
    assert "one machine" in warns[0].suggestion


def test_conflicted_config_sibling_is_flagged_even_when_config_is_broken(tmp_path):
    """The scan runs before the config gate: a conflicted sibling is the likely
    explanation for a broken config, so it must appear alongside the FAIL."""
    vault = init_minimal_vault(tmp_path)
    (vault / ".vault" / "config (conflicted copy).yaml").write_text("", encoding="utf-8")
    (vault / ".vault" / "config.yaml").write_text("[unclosed", encoding="utf-8")
    findings, code = doctor(vault)
    assert code == 2
    assert any("config (conflicted copy).yaml" in f.message for f in findings)


def test_unmanaged_dir_with_vault_marker_names_the_hidden_folder_case(tmp_path):
    """Obsidian Sync does not sync hidden folders, so machine B sees a managed vault
    as unmanaged. The refusal must warn against the state-forking init/adopt instead
    of suggesting it (issue #18)."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "onyxian.md").write_text("# Onyxian\n", encoding="utf-8")
    findings, code = doctor(tmp_path)
    assert code == 2
    fails = [f for f in findings if f.level == FAIL]
    assert any("did not sync" in f.message for f in fails)
    assert not any("run `onyxian init`" in f.message for f in fails)


# ---------------------------------------------------------- Obsidian compat


def _bumped(index: int) -> str:
    """VERIFIED_OBSIDIAN with component `index` bumped and the rest zeroed."""
    parts = [int(p) for p in VERIFIED_OBSIDIAN.split(".")]
    parts += [0] * (3 - len(parts))
    parts[index] += 1
    parts[index + 1 :] = [0] * len(parts[index + 1 :])
    return ".".join(str(p) for p in parts)


def _compat_findings(findings):
    return [f for f in findings if "bsidian" in f.message]


def test_obsidian_absent_is_info_only(tmp_path):
    vault = init_minimal_vault(tmp_path)
    findings, code = doctor(vault, probe=lambda: None)
    assert code == 0
    compat_findings = _compat_findings(findings)
    assert len(compat_findings) == 1
    assert compat_findings[0].level == INFO
    assert "obsidian CLI not found" in compat_findings[0].message


def test_obsidian_unknown_version_is_info(tmp_path):
    vault = init_minimal_vault(tmp_path)
    findings, code = doctor(vault, probe=lambda: "")
    assert code == 0
    compat_findings = _compat_findings(findings)
    assert len(compat_findings) == 1
    assert compat_findings[0].level == INFO
    assert "could not be determined" in compat_findings[0].message


def test_obsidian_match_is_ok(tmp_path):
    vault = init_minimal_vault(tmp_path)
    findings, code = doctor(vault, probe=lambda: VERIFIED_OBSIDIAN)
    assert code == 0
    compat_findings = _compat_findings(findings)
    assert len(compat_findings) == 1
    assert compat_findings[0].level == OK
    assert "matches" in compat_findings[0].message


def test_obsidian_patch_ahead_is_info(tmp_path):
    vault = init_minimal_vault(tmp_path)
    findings, code = doctor(vault, probe=lambda: _bumped(2))
    assert code == 0
    infos = [f for f in _compat_findings(findings) if f.level == INFO]
    assert any("patch ahead" in f.message for f in infos)


def test_obsidian_minor_ahead_warns_with_update_path(tmp_path):
    vault = init_minimal_vault(tmp_path)
    findings, code = doctor(vault, probe=lambda: _bumped(1))
    assert code == 1
    warns = [f for f in _compat_findings(findings) if f.level == WARN]
    assert len(warns) == 1
    assert "is newer than" in warns[0].message
    assert "onyxian update" in warns[0].suggestion


def test_obsidian_major_ahead_warns(tmp_path):
    vault = init_minimal_vault(tmp_path)
    findings, code = doctor(vault, probe=lambda: _bumped(0))
    assert code == 1
    assert any(f.level == WARN for f in _compat_findings(findings))


def test_obsidian_older_is_info(tmp_path):
    vault = init_minimal_vault(tmp_path)
    findings, code = doctor(vault, probe=lambda: "0.9.0")
    assert code == 0
    infos = [f for f in _compat_findings(findings) if f.level == INFO]
    assert any("older than" in f.message for f in infos)


def test_probe_version_output_parsing():
    assert compat._parse_version("1.12.7 (installer 1.12.7)") == "1.12.7"
    assert compat._parse_version('Error: Command "version" not found.') == ""
    assert compat._parse_version("") == ""


def test_drift_classification_pads_shorter_versions():
    assert compat.classify_drift("1.12", "1.12.0") == "match"
    assert compat.classify_drift("1.12.0.1", "1.12.0") == "patch-newer"


def _fake_obsidian(tmp_path, output: str, code: int = 0):
    """A stand-in obsidian binary so the real subprocess path runs on CI."""
    import os

    if os.name == "nt":
        script = tmp_path / "obsidian.bat"
        script.write_text(f"@echo {output}\n@exit /b {code}\n", encoding="utf-8")
    else:
        script = tmp_path / "obsidian"
        script.write_text(f"#!/bin/sh\necho '{output}'\nexit {code}\n", encoding="utf-8")
        script.chmod(0o755)
    return script


def test_real_probe_runs_the_binary_and_parses_stdout(tmp_path, monkeypatch):
    script = _fake_obsidian(tmp_path, "1.12.7 (installer 1.12.7)")
    monkeypatch.setattr(compat, "find_obsidian", lambda: script)
    assert real_probe() == "1.12.7"


def test_real_probe_trusts_output_over_exit_code(tmp_path, monkeypatch):
    # Observed live: the CLI can exit nonzero on valid output and zero on errors.
    script = _fake_obsidian(tmp_path, "1.12.7 (installer 1.12.7)", code=255)
    monkeypatch.setattr(compat, "find_obsidian", lambda: script)
    assert real_probe() == "1.12.7"


def test_real_probe_degrades_error_text_to_unknown(tmp_path, monkeypatch):
    script = _fake_obsidian(tmp_path, "Error: The CLI is unable to find Obsidian.")
    monkeypatch.setattr(compat, "find_obsidian", lambda: script)
    assert real_probe() == ""


def test_find_obsidian_prefers_path_then_redirectors(tmp_path, monkeypatch):
    import shutil

    script = _fake_obsidian(tmp_path, "1.12.7")
    monkeypatch.setattr(shutil, "which", lambda _: str(script))
    assert compat.find_obsidian() == script
    monkeypatch.setattr(shutil, "which", lambda _: None)
    monkeypatch.setattr(compat, "_redirector_candidates", lambda: [script])
    assert compat.find_obsidian() == script
    monkeypatch.setattr(compat, "_redirector_candidates", lambda: [tmp_path / "nope"])
    assert compat.find_obsidian() is None


def test_redirector_candidates_survive_unresolvable_home(monkeypatch):
    from pathlib import Path

    def no_home():
        raise RuntimeError("home is unresolvable")

    monkeypatch.setattr(Path, "home", staticmethod(no_home))
    assert all("obsidian" in str(c).lower() for c in compat._redirector_candidates())

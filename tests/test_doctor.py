"""Doctor: read-only diagnosis with actionable findings (KICKSTART.md §9.4)."""

from conftest import REAL_MODULES, init_minimal_vault
from onyx.doctor import FAIL, INFO, OK, WARN, exit_code, run_doctor
from onyx.lockio import load_lock, save_lock
from onyx.model import LockEntry


def doctor(vault):
    findings = run_doctor(vault, REAL_MODULES)
    return findings, exit_code(findings)


def test_fresh_vault_is_healthy(tmp_path):
    vault = init_minimal_vault(tmp_path)
    findings, code = doctor(vault)
    assert code == 0
    assert all(f.level == OK for f in findings)


def test_missing_managed_file_warns_and_suggests_apply(tmp_path):
    vault = init_minimal_vault(tmp_path)
    (vault / "templates" / "Note.md").unlink()  # golden answers use kebab-case
    findings, code = doctor(vault)
    assert code == 1
    warns = [f for f in findings if f.level == WARN]
    assert any("missing from disk" in f.message for f in warns)
    assert any("onyx apply" in f.suggestion for f in warns)


def test_user_customized_managed_file_is_informational_only(tmp_path):
    vault = init_minimal_vault(tmp_path)
    note = vault / "templates" / "Note.md"
    note.write_text(note.read_text(encoding="utf-8") + "my tweak\n", encoding="utf-8")
    findings, code = doctor(vault)
    assert code == 0
    infos = [f for f in findings if f.level == INFO]
    assert any("customized" in f.message for f in infos)


def test_orphaned_lock_entry_warns(tmp_path):
    vault = init_minimal_vault(tmp_path)
    lock = load_lock(vault)
    lock.put(
        LockEntry(path="Ghost.md", sha256="0" * 64, module="ghost", module_version="0.1.0", kind="managed")
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
    assert any("not an Onyx-managed vault" in f.message for f in findings)

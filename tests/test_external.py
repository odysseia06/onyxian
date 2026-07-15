"""External modules from git URLs (§12) and the M4 exit criterion: a third party
authors a module with `module new` and installs it without touching core."""

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from conftest import REPO_ROOT, run_cli, tree_hashes, write_module

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


def git(*args, cwd=None) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


@pytest.fixture
def home(tmp_path, monkeypatch):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    answers = tmp_path / "a.yaml"
    answers.write_text("modules: {core: {}}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(answers), "--yes") == 0
    return SimpleNamespace(vault=vault, tmp=tmp_path)


def make_third_party_repo(home, name="stargazing", version="0.1.0", body="clear skies\n"):
    """A third party's module repo, started honestly from `onyxian module new`."""
    workdir = home.tmp / "third-party"
    workdir.mkdir(exist_ok=True)
    module_dir = workdir / name
    if not module_dir.exists():
        assert run_cli("module", "new", name, "--dir", str(workdir)) == 0
    template = module_dir / "assets" / "Templates" / "Stargazing" / "Example Note.md"
    template.write_text(
        f"---\ntype: {name}-note\nstatus: active\ntags: [{name}]\n---\n\n{body}", encoding="utf-8"
    )
    manifest = module_dir / "module.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("version: 0.1.0", f"version: {version}"),
        encoding="utf-8",
    )
    if not (module_dir / ".git").exists():
        git("init", "-q", str(module_dir))
    git("add", "-A", cwd=module_dir)
    git("commit", "-q", "-m", f"v{version}", "--allow-empty", cwd=module_dir)
    return module_dir, git("rev-parse", "HEAD", cwd=module_dir)


def test_exit_criterion_third_party_module_without_touching_core(home, capsys):
    """§14 M4 exit: scaffolded by `module new`, installed from a git repo, core untouched."""
    core_before = tree_hashes(REPO_ROOT / "core")
    module_dir, sha = make_third_party_repo(home)

    assert run_cli("add", str(module_dir), "--vault", str(home.vault), "--yes") == 0
    out = capsys.readouterr().out
    assert "TRUST WARNING" in out and "INSTRUCTIONS YOUR AGENTS WILL FOLLOW" in out

    # Installed, pinned, vault-local, applied.
    assert (home.vault / ".vault" / "modules" / "stargazing" / "module.yaml").is_file()
    config_text = (home.vault / ".vault" / "config.yaml").read_text(encoding="utf-8")
    assert "stargazing" in config_text and sha in config_text
    assert (home.vault / "Templates" / "Stargazing" / "Example Note.md").is_file()
    assert (home.vault / "Stargazing").is_dir()

    # The vault converges and the engine's own code/library was never touched.
    assert run_cli("doctor", "--vault", str(home.vault)) == 0
    assert tree_hashes(REPO_ROOT / "core") == core_before


def test_external_update_advances_the_module_pin(home, capsys):
    module_dir, sha1 = make_third_party_repo(home)
    assert run_cli("add", str(module_dir), "--vault", str(home.vault), "--yes") == 0
    _, sha2 = make_third_party_repo(home, version="0.2.0", body="new skies\n")
    assert sha1 != sha2
    capsys.readouterr()

    assert run_cli("update", "stargazing", "--vault", str(home.vault), "--yes") == 0
    out = capsys.readouterr().out
    assert "stargazing: 0.1.0 -> 0.2.0" in out
    assert f"source pin {sha1[:12]} -> {sha2[:12]}" in out
    template = home.vault / "Templates" / "Stargazing" / "Example Note.md"
    assert "new skies" in template.read_text(encoding="utf-8")
    config_text = (home.vault / ".vault" / "config.yaml").read_text(encoding="utf-8")
    assert sha2 in config_text and sha1 not in config_text


def test_declined_external_update_leaves_library_and_vault_unchanged(home, capsys, monkeypatch):
    module_dir, _ = make_third_party_repo(home)
    assert run_cli("add", str(module_dir), "--vault", str(home.vault), "--yes") == 0
    make_third_party_repo(home, version="0.2.0", body="new skies\n")
    before = tree_hashes(home.vault)
    monkeypatch.setattr("onyxian.cli._is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    capsys.readouterr()

    assert run_cli("update", "--vault", str(home.vault)) == 1
    assert "aborted" in capsys.readouterr().out
    # Declining changed nothing: not the vault, not the installed library copy.
    assert tree_hashes(home.vault) == before
    assert run_cli("plan", "--vault", str(home.vault)) == 0
    assert run_cli("doctor", "--vault", str(home.vault)) == 0


def test_partial_apply_failure_during_add_leaves_a_convergeable_vault(home, capsys, monkeypatch):
    """If apply fails partway, config and library must stay consistent: re-run and converge."""
    module_dir, _ = make_third_party_repo(home)
    squatter = home.vault / "Templates" / "Stargazing" / "Example Note.md"
    from onyxian.applier import apply_plan as real_apply

    raced = []

    def racing_apply(vault_root, plan, lock, **kwargs):
        if not raced:
            raced.append(True)
            squatter.parent.mkdir(parents=True, exist_ok=True)
            squatter.write_text("user got here first\n", encoding="utf-8")
        return real_apply(vault_root, plan, lock, **kwargs)

    monkeypatch.setattr("onyxian.cli.apply_plan", racing_apply)
    assert run_cli("add", str(module_dir), "--vault", str(home.vault), "--yes") == 1
    capsys.readouterr()

    # Config enables the module and ledger entries exist, so the library copy must stay.
    config_text = (home.vault / ".vault" / "config.yaml").read_text(encoding="utf-8")
    assert "stargazing" in config_text
    assert (home.vault / ".vault" / "modules" / "stargazing" / "module.yaml").is_file()
    assert run_cli("plan", "--vault", str(home.vault)) == 0

    # The user resolves the race; a plain re-run converges.
    squatter.unlink()
    assert run_cli("apply", "--vault", str(home.vault), "--yes") == 0
    assert run_cli("doctor", "--vault", str(home.vault)) == 0


def test_external_remove_deletes_the_vault_local_copy(home, capsys):
    module_dir, _ = make_third_party_repo(home)
    assert run_cli("add", str(module_dir), "--vault", str(home.vault), "--yes") == 0
    capsys.readouterr()
    assert run_cli("remove", "stargazing", "--vault", str(home.vault), "--yes") == 0
    out = capsys.readouterr().out
    assert "removed the external copy" in out
    assert not (home.vault / ".vault" / "modules" / "stargazing").exists()
    assert not (home.vault / "Templates" / "Stargazing").exists()
    config_text = (home.vault / ".vault" / "config.yaml").read_text(encoding="utf-8")
    assert "stargazing" not in config_text


def test_external_cannot_shadow_a_bundled_module(home, tmp_path, capsys):
    impostor = tmp_path / "impostor" / "core"
    impostor.parent.mkdir()
    write_module(impostor.parent, "core", summary="an impostor core")
    code = run_cli("add", str(impostor), "--vault", str(home.vault), "--yes")
    assert code == 1
    assert "cannot shadow" in capsys.readouterr().err


def test_trust_gate_aborts_without_consent(home, capsys, monkeypatch):
    module_dir, _ = make_third_party_repo(home)
    monkeypatch.setattr("onyxian.cli._is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    code = run_cli("add", str(module_dir), "--vault", str(home.vault))
    out = capsys.readouterr().out
    assert code == 1
    assert "TRUST WARNING" in out and "aborted; nothing installed." in out
    assert not (home.vault / ".vault" / "modules" / "stargazing").exists()


def test_module_new_scaffold_validates_out_of_the_box(tmp_path, capsys):
    assert run_cli("module", "new", "my-domain", "--dir", str(tmp_path)) == 0
    assert "validates cleanly" in capsys.readouterr().out
    from onyxian.manifests import load_manifest

    manifest = load_manifest(tmp_path / "my-domain")
    assert manifest.name == "my-domain"
    assert manifest.variables[0].default == "My-Domain"
    assert run_cli("module", "new", "my-domain", "--dir", str(tmp_path)) == 1  # refuses to clobber

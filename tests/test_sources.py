"""Pinned source installs, exercised against a local git upstream — no network (§6.1, P6)."""

import shutil
import subprocess
from types import SimpleNamespace

import pytest
import yaml

from conftest import run_cli, write_module
from onyxian.lockio import load_lock

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


def make_upstream(tmp_path):
    """A stand-in for kepano/obsidian-skills: a git repo with a skills/ tree."""
    up = tmp_path / "upstream"
    for skill in ("obsidian-markdown", "defuddle"):
        (up / "skills" / skill).mkdir(parents=True)
        (up / "skills" / skill / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: upstream skill\n---\nv1\n", encoding="utf-8"
        )
    git("init", "-q", str(up))
    git("add", "-A", cwd=up)
    git("commit", "-q", "-m", "v1", cwd=up)
    return up, git("rev-parse", "HEAD", cwd=up)


@pytest.fixture
def home(tmp_path, monkeypatch):
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    upstream, sha = make_upstream(tmp_path)
    return SimpleNamespace(tmp=tmp_path, upstream=upstream, sha=sha)


def write_answers(home, sources: dict) -> str:
    path = home.tmp / "answers.yaml"
    path.write_text(
        yaml.safe_dump({"modules": {"core": {}}, "sources": sources}), encoding="utf-8"
    )
    return str(path)


def test_init_installs_pins_and_ledgers_the_source(home, capsys):
    answers = write_answers(home, {"obsidian-skills": {"repo": str(home.upstream)}})
    vault = home.tmp / "vault"
    assert run_cli("init", str(vault), "--answers", answers, "--yes") == 0
    out = capsys.readouterr().out
    assert f"at pin {home.sha[:12]}" in out

    skill = vault / ".claude" / "skills" / "obsidian-markdown" / "SKILL.md"
    assert skill.read_text(encoding="utf-8").endswith("v1\n")
    entry = load_lock(vault).get(".claude/skills/obsidian-markdown/SKILL.md")
    assert entry.module == "source:obsidian-skills"
    assert entry.module_version == home.sha[:12]
    config_text = (vault / ".vault" / "config.yaml").read_text(encoding="utf-8")
    assert f'pin: "{home.sha}"' in config_text

    # Source content is not plan's to reconcile: the vault is converged and healthy.
    assert run_cli("plan", "--vault", str(vault)) == 0
    assert "no changes planned" in capsys.readouterr().out
    assert run_cli("doctor", "--vault", str(vault)) == 0


def test_a_recorded_pin_beats_upstream_head(home):
    pinned_sha = home.sha
    (home.upstream / "skills" / "obsidian-markdown" / "SKILL.md").write_text("v2\n", encoding="utf-8")
    git("add", "-A", cwd=home.upstream)
    git("commit", "-q", "-m", "v2", cwd=home.upstream)

    answers = write_answers(home, {"obsidian-skills": {"repo": str(home.upstream), "pin": pinned_sha}})
    vault = home.tmp / "vault"
    assert run_cli("init", str(vault), "--answers", answers, "--yes") == 0
    skill = vault / ".claude" / "skills" / "obsidian-markdown" / "SKILL.md"
    assert skill.read_text(encoding="utf-8").endswith("v1\n")  # the pin, not HEAD
    config_text = (vault / ".vault" / "config.yaml").read_text(encoding="utf-8")
    assert f'pin: "{pinned_sha}"' in config_text


def test_unreachable_upstream_degrades_to_a_warning(home, capsys):
    answers = write_answers(home, {"obsidian-skills": {"repo": str(home.tmp / "no-such-repo")}})
    vault = home.tmp / "vault"
    assert run_cli("init", str(vault), "--answers", answers, "--yes") == 0  # P2: vault still works
    err = capsys.readouterr().err
    assert "install skipped" in err and "works fully without it" in err
    assert (vault / "Start-Here.md").is_file()
    assert not (vault / ".claude" / "skills").exists()
    assert run_cli("doctor", "--vault", str(vault)) == 0


def test_adopt_never_overwrites_user_files_with_source_content(home, capsys):
    vault = home.tmp / "lived-in"
    (vault / ".claude" / "skills" / "obsidian-markdown").mkdir(parents=True)
    (vault / ".claude" / "skills" / "obsidian-markdown" / "SKILL.md").write_text(
        "the user's own version\n", encoding="utf-8"
    )
    answers = write_answers(home, {"obsidian-skills": {"repo": str(home.upstream)}})
    code = run_cli("adopt", str(vault), "--answers", answers)
    out = capsys.readouterr()
    assert code == 0
    token = [w for w in out.out.split() if len(w) == 12 and all(c in "0123456789abcdef" for c in w)]
    assert run_cli("adopt", str(vault), "--answers", answers, "--accept", token[-1]) == 0
    captured = capsys.readouterr()
    assert "skipped .claude/skills/obsidian-markdown/SKILL.md" in captured.err
    user_file = vault / ".claude" / "skills" / "obsidian-markdown" / "SKILL.md"
    assert user_file.read_text(encoding="utf-8") == "the user's own version\n"
    assert load_lock(vault).get(".claude/skills/obsidian-markdown/SKILL.md") is None
    # The sibling skill installed fine.
    assert (vault / ".claude" / "skills" / "defuddle" / "SKILL.md").is_file()


def test_source_never_steals_a_module_owned_skill(home, capsys):
    """Core-style modules ship skill ids the upstream also ships; the module keeps ownership."""
    module_skill = "---\nname: obsidian-markdown\ndescription: module-owned\n---\nmodule version\n"
    write_module(
        home.tmp / "modules",
        "demo",
        skills={"obsidian-markdown": {"SKILL.md": module_skill}},
    )
    answers = home.tmp / "answers.yaml"
    answers.write_text(
        yaml.safe_dump(
            {
                "modules": {"core": {}, "demo": {}},
                "sources": {"obsidian-skills": {"repo": str(home.upstream)}},
            }
        ),
        encoding="utf-8",
    )
    vault = home.tmp / "vault"
    assert run_cli("init", str(vault), "--answers", str(answers), "--yes") == 0
    err = capsys.readouterr().err
    assert "skipped .claude/skills/obsidian-markdown/SKILL.md" in err

    skill = vault / ".claude" / "skills" / "obsidian-markdown" / "SKILL.md"
    assert skill.read_text(encoding="utf-8") == module_skill
    entry = load_lock(vault).get(".claude/skills/obsidian-markdown/SKILL.md")
    assert entry.module == "demo"
    # The sibling skill the module does not ship installed normally.
    assert load_lock(vault).get(".claude/skills/defuddle/SKILL.md").module == "source:obsidian-skills"
    # Convergence: apply and the source install no longer fight over the file.
    assert run_cli("plan", "--vault", str(vault)) == 0
    assert "no changes planned" in capsys.readouterr().out
    assert run_cli("doctor", "--vault", str(vault)) == 0


def test_missing_source_file_is_a_doctor_warning_pointing_at_update(home, capsys):
    answers = write_answers(home, {"obsidian-skills": {"repo": str(home.upstream)}})
    vault = home.tmp / "vault"
    assert run_cli("init", str(vault), "--answers", answers, "--yes") == 0
    (vault / ".claude" / "skills" / "defuddle" / "SKILL.md").unlink()
    capsys.readouterr()
    assert run_cli("doctor", "--vault", str(vault)) == 1
    out = capsys.readouterr().out
    assert "source-installed file(s) missing" in out and "update" in out


def test_update_advances_the_pin_and_reports_the_delta(home, capsys):
    """§8.3: update moves the pin forward, re-runs the install path, reports the delta."""
    answers = write_answers(home, {"obsidian-skills": {"repo": str(home.upstream)}})
    vault = home.tmp / "vault"
    assert run_cli("init", str(vault), "--answers", answers, "--yes") == 0
    old_sha = home.sha
    (home.upstream / "skills" / "obsidian-markdown" / "SKILL.md").write_text("v2 upstream\n", encoding="utf-8")
    git("add", "-A", cwd=home.upstream)
    git("commit", "-q", "-m", "v2", cwd=home.upstream)
    new_sha = git("rev-parse", "HEAD", cwd=home.upstream)
    capsys.readouterr()

    assert run_cli("update", "--vault", str(vault), "--yes") == 0
    out = capsys.readouterr().out
    assert f"{old_sha[:12]} -> {new_sha[:12]}" in out
    skill = vault / ".claude" / "skills" / "obsidian-markdown" / "SKILL.md"
    assert skill.read_text(encoding="utf-8") == "v2 upstream\n"
    config_text = (vault / ".vault" / "config.yaml").read_text(encoding="utf-8")
    assert new_sha in config_text and old_sha not in config_text


def test_update_never_overwrites_a_customized_source_file(home, capsys):
    answers = write_answers(home, {"obsidian-skills": {"repo": str(home.upstream)}})
    vault = home.tmp / "vault"
    assert run_cli("init", str(vault), "--answers", answers, "--yes") == 0
    skill = vault / ".claude" / "skills" / "obsidian-markdown" / "SKILL.md"
    skill.write_text("MY customized copy\n", encoding="utf-8")
    (home.upstream / "skills" / "obsidian-markdown" / "SKILL.md").write_text("v2 upstream\n", encoding="utf-8")
    git("add", "-A", cwd=home.upstream)
    git("commit", "-q", "-m", "v2", cwd=home.upstream)
    capsys.readouterr()

    assert run_cli("update", "--vault", str(vault), "--yes") == 0
    err = capsys.readouterr().err
    assert skill.read_text(encoding="utf-8") == "MY customized copy\n"
    assert "left alone .claude/skills/obsidian-markdown/SKILL.md" in err


def test_bad_pin_format_is_rejected_loudly(home, capsys):
    answers = write_answers(home, {"obsidian-skills": {"repo": str(home.upstream), "pin": "main"}})
    vault = home.tmp / "vault"
    assert run_cli("init", str(vault), "--answers", answers, "--yes") == 0  # degraded, not fatal
    assert "40-hex commit sha" in capsys.readouterr().err


def test_answers_sources_shape_is_validated(home, capsys):
    path = home.tmp / "bad.yaml"
    path.write_text("sources: {obsidian-skills: {branch: main}}\n", encoding="utf-8")
    assert run_cli("init", str(home.tmp / "v"), "--answers", str(path), "--yes") == 1
    assert "repo/pin" in capsys.readouterr().err

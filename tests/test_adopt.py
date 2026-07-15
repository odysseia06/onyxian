"""`onyxian adopt` (§9.3): scan, claim, gap-fill additively, checklist the ambiguous.

The fixture vault is shaped like the charter's canonical persona (Appendix C):
lived-in domain folders, a pre-existing home note, a customized template where
the engine wants to install one, junk that matches nothing, and a planted
ambiguity — adopted with zero destructive operations.
"""

import re
from types import SimpleNamespace

import pytest

from conftest import run_cli, tree_hashes, write_module
from onyxian.adopt import infer_folder_style
from onyxian.lockio import load_lock


@pytest.fixture
def home(tmp_path, monkeypatch):
    modules_root = tmp_path / "modules"
    write_module(
        modules_root,
        "core",
        templates={"Templates/Note.md": "# canonical template\n"},
        seeds={"Home.md": "home seed\n"},
        folders=["Templates"],
    )
    write_module(
        modules_root,
        "fitness",
        variables=[{"key": "root", "prompt": "Fitness folder", "default": "Fitness"}],
        folders=["{{root}}/Training/Logs", "{{root}}/Reviews", "{{root}}/Tracking"],
        seeds={"{{root}}/Strategy.md": "strategy stub\n"},
    )
    write_module(
        modules_root,
        "academic",
        variables=[{"key": "root", "prompt": "Academic folder", "default": "Academic"}],
        folders=["{{root}}/Courses", "{{root}}/Exam-Prep"],
    )
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))

    vault = tmp_path / "lived-in-vault"
    # The lived-in structure: fitness under a CUSTOM name, with content.
    (vault / "My-Fitness" / "Training" / "Logs").mkdir(parents=True)
    (vault / "My-Fitness" / "Reviews").mkdir()
    (vault / "My-Fitness" / "Strategy.md").write_text(
        "five years of my strategy\n", encoding="utf-8"
    )
    (vault / "My-Fitness" / "Training" / "Logs" / "2026-01-02.md").write_text(
        "squats\n", encoding="utf-8"
    )
    # Planted ambiguity: two folders that both look like the academic root.
    (vault / "Academic" / "Courses").mkdir(parents=True)
    (vault / "University" / "Courses").mkdir(parents=True)
    # Pre-existing user files at engine paths.
    (vault / "Home.md").write_text("my own home page\n", encoding="utf-8")
    (vault / "Templates").mkdir()
    (vault / "Templates" / "Note.md").write_text("my customized template\n", encoding="utf-8")
    # Junk that matches nothing.
    (vault / "Random-Stuff").mkdir()
    return SimpleNamespace(vault=vault, tmp=tmp_path)


def adopt_review(home, capsys, *extra):
    code = run_cli("adopt", str(home.vault), *extra)
    out = capsys.readouterr()
    return code, out.out + out.err


def extract_token(output: str) -> str:
    match = re.search(r"--accept ([0-9a-f]{12})", output)
    assert match, f"no acceptance token in output:\n{output}"
    return match.group(1)


def test_scan_claims_shape_matched_folder_under_custom_name(home, capsys):
    code, out = adopt_review(home, capsys, "--dry-run")
    assert code == 0
    assert "My-Fitness/  ->  fitness.root" in out
    claim_line = next(line for line in out.splitlines() if "fitness.root" in line)
    assert "contains" in claim_line and "Training" in claim_line and "Reviews" in claim_line


def test_planted_ambiguity_lands_on_the_checklist_not_in_actions(home, capsys):
    code, out = adopt_review(home, capsys, "--dry-run")
    assert code == 0
    assert "checklist" in out
    assert "'Academic'" in out and "'University'" in out
    assert "academic" not in [
        line.split()[-1] for line in out.splitlines() if "->" in line
    ]  # no academic claim
    assert "Exam-Prep" not in out  # nothing of academic's gets planned


def test_existing_seed_files_are_claimed_never_replaced(home, capsys):
    code, out = adopt_review(home, capsys, "--dry-run")
    assert code == 0
    assert "= Home.md  (core)" in out
    assert "= My-Fitness/Strategy.md  (fitness)" in out


def test_customized_template_is_blocked_onto_the_checklist(home, capsys):
    code, out = adopt_review(home, capsys, "--dry-run")
    assert code == 0
    assert "Templates/Note.md" in out and "BLOCKED" in out


def test_dry_run_and_review_write_nothing(home, capsys):
    before = tree_hashes(home.vault)
    code, _ = adopt_review(home, capsys, "--dry-run")
    assert code == 0
    code, out = adopt_review(home, capsys)  # non-interactive review run
    assert code == 0
    assert "--accept" in out
    assert tree_hashes(home.vault) == before


def test_accept_token_applies_exactly_the_reviewed_plan(home, capsys):
    before = tree_hashes(home.vault)
    _, review = adopt_review(home, capsys)
    token = extract_token(review)
    code, out = adopt_review(home, capsys, "--accept", token)
    assert code == 0
    assert "nothing pre-existing was touched" in out

    after = tree_hashes(home.vault)
    # Every pre-existing byte survived.
    assert all(after[path] == digest for path, digest in before.items())
    # Gap-fill landed additively.
    assert (home.vault / "My-Fitness" / "Tracking").is_dir()
    assert (home.vault / "Start-Here.md").is_file()
    # Claims are in the ledger: the user's own files, at their current content, as seeds.
    lock = load_lock(home.vault)
    assert lock.get("Home.md").kind == "seeded"
    assert lock.get("My-Fitness/Strategy.md").kind == "seeded"
    assert before["Home.md"] == after["Home.md"]
    # The customized template stayed untracked and untouched.
    assert lock.get("Templates/Note.md") is None
    # Idempotence: adopting produced a converged vault.
    assert run_cli("plan", "--vault", str(home.vault)) == 0


def test_stale_token_is_rejected(home, capsys):
    _, review = adopt_review(home, capsys)
    token = extract_token(review)
    (home.vault / "My-Fitness" / "Reviews" / "new-note.md").write_text("x\n", encoding="utf-8")
    # A new file does not change the plan; change something that does: the claimed strategy seed disappears.
    (home.vault / "My-Fitness" / "Strategy.md").unlink()
    code, out = adopt_review(home, capsys, "--accept", token)
    assert code == 1
    assert "changed since" in out


def test_adopt_refuses_managed_vaults(home, capsys):
    _, review = adopt_review(home, capsys)
    token = extract_token(review)
    adopt_review(home, capsys, "--accept", token)
    code, out = adopt_review(home, capsys)
    assert code == 1
    assert "already an Onyxian vault" in out


def test_answers_override_scan_proposals(home, capsys, tmp_path):
    answers = tmp_path / "a.yaml"
    answers.write_text(
        'vault: { name: "Chosen Name" }\nmodules:\n  fitness: { root: "My-Fitness" }\n',
        encoding="utf-8",
    )
    code, out = adopt_review(home, capsys, "--answers", str(answers), "--dry-run")
    assert code == 0
    assert "'Chosen Name'" in out
    assert "academic" not in out.split("checklist")[0]  # explicit module set: only fitness + core


@pytest.mark.parametrize(
    "names,expected",
    [
        (["Daily-Notes", "Fitness", "Templates"], "Title-Case-Hyphen"),
        (["daily-notes", "fitness", "templates"], "kebab-case"),
        (["Daily Notes", "My Stuff", "Templates"], "Spaces"),
        ([], "Title-Case-Hyphen"),
    ],
)
def test_folder_style_inference(names, expected):
    assert infer_folder_style(names) == expected


def test_dry_run_prints_the_same_acceptance_token_the_review_prints(home, capsys):
    """The wizard's documented flow: iterate with --dry-run, then apply with --accept."""
    before = tree_hashes(home.vault)
    _, dry = adopt_review(home, capsys, "--dry-run")
    token = extract_token(dry)
    assert tree_hashes(home.vault) == before  # dry run wrote nothing
    code, out = adopt_review(home, capsys, "--accept", token)
    assert code == 0
    assert "nothing pre-existing was touched" in out

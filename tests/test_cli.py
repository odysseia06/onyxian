"""CLI behavior: init guards, non-interactive discipline, honest stubs (KICKSTART.md §9.1)."""

import json
import re
import subprocess
import sys
import types

import pytest
from conftest import ANSWERS_DIR, REPO_ROOT, init_minimal_vault, run_cli, tree_hashes

from onyxian import ENGINE_VERSION
from onyxian.configio import load_config
from onyxian.sources import OBSIDIAN_SKILLS

MINIMAL_ANSWERS = str(ANSWERS_DIR / "minimal.yaml")


def test_version_via_real_entrypoint():
    out = subprocess.run(
        [sys.executable, "-m", "onyxian.cli", "--version"], capture_output=True, text=True
    )
    assert out.returncode == 0
    # ENGINE_VERSION is the single source (issue #5); with one place to edit there
    # is no hand-synced literal left to drift from it.
    assert out.stdout.strip() == f"onyxian {ENGINE_VERSION}"


def test_init_refuses_a_lived_in_folder(tmp_path, capsys):
    target = tmp_path / "lived-in"
    target.mkdir()
    (target / "My Notes.md").write_text("precious\n", encoding="utf-8")
    code = run_cli("init", str(target), "--answers", MINIMAL_ANSWERS, "--yes")
    captured = capsys.readouterr()
    assert code == 1
    assert "adopt" in captured.err
    assert (target / "My Notes.md").read_text(encoding="utf-8") == "precious\n"
    assert not (target / ".vault").exists()


def test_init_tolerates_vcs_obsidian_and_os_junk(tmp_path):
    target = tmp_path / "fresh"
    (target / ".git").mkdir(parents=True)
    (target / ".obsidian").mkdir()
    (target / ".DS_Store").write_text("", encoding="utf-8")
    assert run_cli("init", str(target), "--answers", MINIMAL_ANSWERS, "--yes") == 0
    assert (target / "Home.md").is_file()


def test_init_refuses_an_already_initialized_vault(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    code = run_cli("init", str(vault), "--answers", MINIMAL_ANSWERS, "--yes")
    assert code == 1
    assert "already an Onyxian vault" in capsys.readouterr().err


def test_bare_init_builds_a_core_vault_with_zero_questions(tmp_path, capsys):
    """#129: `onyxian init <folder>` needs no TTY, no answers file, no confirmation."""
    target = tmp_path / "my-notes"
    code = run_cli("init", str(target))
    captured = capsys.readouterr()
    assert code == 0
    assert (target / "Home.md").is_file()
    config = load_config(target)
    assert config.vault_name == "my-notes"
    assert set(config.modules) == {"core"}
    # obsidian-skills stays declared but uninstalled: instruction consent is --trust's job.
    assert OBSIDIAN_SKILLS in config.sources
    assert "not installed" in captured.err
    assert "onyxian add" in captured.out  # the growth hint


def test_bare_init_asks_nothing_even_on_a_tty(tmp_path, monkeypatch):
    monkeypatch.setattr("onyxian.cli._is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("init asked a question"))
    assert run_cli("init", str(tmp_path / "v")) == 0


def test_bare_init_dry_run_shows_the_plan_and_writes_nothing(tmp_path, capsys):
    target = tmp_path / "v"
    assert run_cli("init", str(target), "--dry-run") == 0
    out = capsys.readouterr().out
    assert "dry run" in out
    assert "Templates/Note.md" in out  # the plan itself was shown (default styling)
    assert not target.exists()


def test_init_profile_is_a_zero_question_full_vault(tmp_path):
    """#129: --profile <name> is the one-shot path; no confirmation, no prompts."""
    target = tmp_path / "v"
    assert run_cli("init", str(target), "--profile", "minimal") == 0
    config = load_config(target)
    assert config.vault_name == "v"
    assert (target / "Templates" / "Note.md").is_file()


def test_init_profile_rejects_an_answers_file(tmp_path, capsys):
    code = run_cli("init", str(tmp_path / "v"), "--profile", MINIMAL_ANSWERS)
    assert code == 1
    assert "not a profile" in capsys.readouterr().err
    assert not (tmp_path / "v").exists()


def test_init_profile_unknown_lists_available(tmp_path, capsys):
    code = run_cli("init", str(tmp_path / "v"), "--profile", "no-such-profile")
    assert code == 1
    err = capsys.readouterr().err
    assert "--profile" in err and "Available profiles" in err


def test_non_interactive_confirmation_requires_yes(tmp_path, capsys):
    code = run_cli("init", str(tmp_path / "v"), "--answers", MINIMAL_ANSWERS)
    assert code == 1
    assert "--yes" in capsys.readouterr().err
    assert not (tmp_path / "v").exists()


def test_eof_at_a_prompt_exits_cleanly(tmp_path, capsys, monkeypatch):
    target = tmp_path / "v"
    monkeypatch.setattr("onyxian.cli._is_interactive", lambda: True)

    def raise_eof(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    assert run_cli("init", str(target), "--answers", MINIMAL_ANSWERS) == 130
    assert "interrupted; nothing partial was left unrecorded" in capsys.readouterr().err
    assert not target.exists()


def test_init_dry_run_writes_nothing(tmp_path, capsys):
    target = tmp_path / "v"
    code = run_cli("init", str(target), "--answers", MINIMAL_ANSWERS, "--dry-run")
    out = capsys.readouterr().out
    assert code == 0
    assert "dry run" in out
    assert "templates/Note.md" in out  # the plan itself was shown (kebab-case answers)
    assert not target.exists()


def test_profile_file_is_a_valid_answers_input(tmp_path):
    """profiles/minimal.yaml (§5.5) feeds --answers directly; defaults fill the rest."""
    target = tmp_path / "v"
    profile = REPO_ROOT / "profiles" / "minimal.yaml"
    assert run_cli("init", str(target), "--answers", str(profile), "--yes") == 0
    config_text = (target / ".vault" / "config.yaml").read_text(encoding="utf-8")
    assert 'name: "My Vault"' in config_text
    assert "folder_style: Title-Case-Hyphen" in config_text
    assert (target / "Templates" / "Note.md").is_file()


def test_apply_dry_run_changes_nothing(tmp_path):
    vault = init_minimal_vault(tmp_path)
    (vault / "templates" / "Note.md").unlink()  # forces a pending restore
    before = tree_hashes(vault)
    assert run_cli("apply", "--vault", str(vault), "--dry-run") == 0
    assert tree_hashes(vault) == before
    assert run_cli("apply", "--vault", str(vault), "--yes") == 0
    assert (vault / "templates" / "Note.md").is_file()


def test_commands_on_a_non_vault_fail_with_guidance(tmp_path, capsys):
    code = run_cli("plan", "--vault", str(tmp_path))
    assert code == 1
    assert "not an Onyxian-managed vault" in capsys.readouterr().err


def test_non_vault_with_marker_warns_against_the_state_forking_reinit(tmp_path, capsys):
    """A vault marker without .vault/ means a sync service dropped the hidden state
    folder (issue #18) — every command's refusal must say so, not suggest init."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "onyxian.md").write_text("# Onyxian\n", encoding="utf-8")
    code = run_cli("plan", "--vault", str(tmp_path))
    assert code == 1
    err = capsys.readouterr().err
    assert "did not sync" in err
    assert "onyxian init" not in err


def test_command_tree_is_trimmed_and_regrouped():
    """#132: core verbs keep their names; authoring folds under `modules`; the
    one-letter-apart `module` and the `project` alias are gone; `hook` still parses."""
    from onyxian.cli import build_parser

    parser = build_parser()
    subactions = next(a for a in parser._actions if getattr(a, "choices", None))
    assert isinstance(subactions.choices, dict)  # subparsers map name -> parser
    for command in (
        "init",
        "adopt",
        "plan",
        "apply",
        "add",
        "remove",
        "update",
        "doctor",
        "diff",
        "lock",
        "checkpoint",
        "hook",
        "modules",
        "new",
    ):
        assert command in subactions.choices
    assert "module" not in subactions.choices  # listing vs authoring, one letter apart
    assert "project" not in subactions.choices  # folded into `new project`
    modules_sub = next(
        a for a in subactions.choices["modules"]._actions if getattr(a, "choices", None)
    )
    assert set(modules_sub.choices) == {"new", "lint"}


def test_top_level_help_hides_the_hook_command():
    """#132: `hook` is Claude Code plumbing — it works, but never advertises itself."""
    from onyxian.cli import build_parser

    help_text = build_parser().format_help()
    assert "hook" not in help_text
    assert "adopt" in help_text  # the visible commands are still listed


def test_modules_new_dispatches_to_authoring_not_listing(tmp_path):
    """#132: bare `modules` lists; `modules new` must scaffold, not fall through to the list."""
    assert run_cli("modules", "new", "my-domain", "--dir", str(tmp_path)) == 0
    assert (tmp_path / "my-domain" / "module.yaml").is_file()


def test_invalid_onyxian_now_is_a_clean_error(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ONYXIAN_NOW", "not-a-date")
    code = run_cli("init", str(tmp_path / "v"), "--answers", MINIMAL_ANSWERS, "--yes")
    assert code == 1
    assert "ONYXIAN_NOW" in capsys.readouterr().err


def test_answers_resolves_a_bundled_profile_by_name(tmp_path, capsys):
    """An installed user types `--answers minimal`, not a path into site-packages."""
    target = tmp_path / "v"
    assert run_cli("init", str(target), "--answers", "minimal", "--yes") == 0
    assert "profile: minimal" in capsys.readouterr().out
    assert (target / "Templates" / "Note.md").is_file()


def test_answers_unknown_profile_lists_what_is_available(tmp_path, capsys):
    code = run_cli("init", str(tmp_path / "v"), "--answers", "no-such-profile", "--yes")
    assert code == 1
    err = capsys.readouterr().err
    assert "Available profiles" in err and "minimal" in err


# ------------------------------------- exit codes and --json (issue #66)
#
# The contract a script branches on, documented in core/onyxian/errors.py:
# 0 = clean, 1 = the command could not do its job, 2 = it ran and has findings.


def test_plan_exit_code_separates_clean_from_pending(tmp_path):
    """The terraform-style drift check: `plan` says *whether* it planned anything."""
    vault = init_minimal_vault(tmp_path)
    assert run_cli("plan", "--vault", str(vault)) == 0
    (vault / "templates" / "Note.md").unlink()  # a pending restore
    assert run_cli("plan", "--vault", str(vault)) == 2


def test_plan_json_carries_the_actions_and_the_same_exit_code(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    (vault / "templates" / "Note.md").unlink()
    capsys.readouterr()  # drop init's own output
    code = run_cli("plan", "--vault", str(vault), "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["pending"] == 1
    assert payload["changes"][0]["type"] == "restore"
    assert payload["changes"][0]["path"] == "templates/Note.md"
    assert payload["checked"]  # the no-op counters `plan` prints as prose


def test_doctor_json_carries_the_verdict_and_the_same_exit_code(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    capsys.readouterr()  # drop init's own output
    code = run_cli("doctor", "--vault", str(vault), "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["exit_code"] == 0
    assert payload["verdict"].startswith("healthy")
    assert {f["level"] for f in payload["findings"]} <= {"ok", "info"}

    (vault / "templates" / "Note.md").unlink()  # a WARN, not a broken vault
    code = run_cli("doctor", "--vault", str(vault), "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == 2 and payload["exit_code"] == 2
    assert payload["level"] == "warn"
    assert any(f["level"] == "warn" and f["suggestion"] for f in payload["findings"])


def test_a_usage_error_is_an_error_not_a_finding(tmp_path, capsys):
    """argparse's own exit 2 would be indistinguishable from `doctor`'s findings."""
    with pytest.raises(SystemExit) as exc:
        run_cli("doctor", "--vault", str(tmp_path), "--no-such-flag")
    assert exc.value.code == 1
    assert "unrecognized arguments" in capsys.readouterr().err


# ------------------------------------- --json everywhere (issue #134)
#
# The contract: with --json, stdout carries exactly one JSON document —
# {"command", "exit_code", ...payload} — and every prose line, prompt, and
# warning goes to stderr instead. Exit codes are identical to the prose runs.


def test_every_visible_command_takes_json():
    """#134: every user-facing (sub)command accepts --json; `hook` stays out —
    its stdout already is a JSON protocol Claude Code parses."""
    from onyxian.cli import build_parser

    parser = build_parser()
    subactions = next(a for a in parser._actions if getattr(a, "choices", None))
    for name, sub in subactions.choices.items():
        if name == "hook":
            continue
        assert any("--json" in a.option_strings for a in sub._actions), name
    modules_sub = next(
        a for a in subactions.choices["modules"]._actions if getattr(a, "choices", None)
    )
    for name, sub in modules_sub.choices.items():
        assert any("--json" in a.option_strings for a in sub._actions), f"modules {name}"


def test_plan_and_doctor_json_carry_the_envelope(tmp_path, capsys):
    """The #66 payloads stay put; #134 adds "command" and "exit_code" around them."""
    vault = init_minimal_vault(tmp_path)
    capsys.readouterr()
    assert run_cli("plan", "--vault", str(vault), "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "plan" and payload["exit_code"] == 0
    assert payload["pending"] == 0
    assert run_cli("doctor", "--vault", str(vault), "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "doctor" and payload["exit_code"] == 0


def test_init_json_is_one_document_with_prose_on_stderr(tmp_path, capsys):
    target = tmp_path / "v"
    code = run_cli("init", str(target), "--json")
    captured = capsys.readouterr()
    payload = json.loads(captured.out)  # the whole of stdout parses as one document
    assert code == 0
    assert payload["command"] == "init" and payload["exit_code"] == 0
    assert payload["modules"] == ["core"]
    assert "Home.md" in payload["applied"]
    assert payload["skipped"] == []
    assert "onyxian add" in captured.err  # the growth hint moved to stderr


def test_apply_json_reports_planned_and_applied(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    (vault / "templates" / "Note.md").unlink()
    capsys.readouterr()
    code = run_cli("apply", "--vault", str(vault), "--yes", "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["command"] == "apply"
    assert payload["pending"] == 1
    assert payload["changes"][0]["path"] == "templates/Note.md"
    assert payload["applied"] == ["templates/Note.md"]
    assert payload["skipped"] == []


def test_add_json_dry_run_marks_the_document_and_writes_nothing(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    before = tree_hashes(vault)
    capsys.readouterr()
    code = run_cli("add", "fitness", "--vault", str(vault), "--dry-run", "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["command"] == "add"
    assert payload["dry_run"] is True
    assert "fitness" in payload["enabling"]
    assert payload["pending"] >= 1
    assert "applied" not in payload  # nothing ran, so the document says nothing ran
    assert tree_hashes(vault) == before


def test_remove_json_lists_what_was_deleted(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    assert run_cli("add", "fitness", "--vault", str(vault)) == 0
    capsys.readouterr()
    code = run_cli("remove", "fitness", "--vault", str(vault), "--yes", "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["command"] == "remove"
    assert payload["module"] == "fitness"
    assert payload["deleted"]  # fitness shipped managed files; they were deleted
    assert isinstance(payload["pruned"], int)


def test_update_json_when_nothing_to_do(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    capsys.readouterr()
    code = run_cli("update", "core", "--vault", str(vault), "--yes", "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["command"] == "update"
    assert payload["pending"] == 0
    assert payload["updates"] == {}


def test_adopt_json_carries_the_acceptance_token(tmp_path, capsys):
    target = tmp_path / "existing"
    target.mkdir()
    (target / "Notes.md").write_text("mine\n", encoding="utf-8")
    assert run_cli("adopt", str(target), "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "adopt"
    assert payload["accept_token"]
    assert "applied" not in payload  # review complete, nothing written
    assert not (target / ".vault").exists()
    # the token round-trips: a script can review, then re-run with --accept
    code = run_cli("adopt", str(target), "--accept", payload["accept_token"], "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["applied"]
    assert (target / ".vault").is_dir()


def test_modules_json_lists_the_library(capsys):
    assert run_cli("modules", "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    names = {m["name"] for m in payload["modules"]}
    assert {"core", "fitness"} <= names
    fitness = next(m for m in payload["modules"] if m["name"] == "fitness")
    assert fitness["version"]
    assert isinstance(fitness["variables"], list)


def test_checkpoint_list_json(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    capsys.readouterr()
    code = run_cli("checkpoint", "list", "--vault", str(vault), "--json")
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["command"] == "checkpoint list"
    assert payload["checkpoints"] == []


def test_json_error_still_yields_one_document(tmp_path, capsys):
    code = run_cli("plan", "--vault", str(tmp_path), "--json")
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 1
    assert payload["command"] == "plan" and payload["exit_code"] == 1
    assert "not an Onyxian-managed vault" in payload["error"]
    assert "not an Onyxian-managed vault" in captured.err  # prose error stays too


# ------------------------------------- no prompts without a TTY (issue #134)


def test_remove_without_a_tty_fails_instead_of_prompting(tmp_path, capsys):
    vault = init_minimal_vault(tmp_path)
    assert run_cli("add", "fitness", "--vault", str(vault)) == 0
    capsys.readouterr()
    code = run_cli("remove", "fitness", "--vault", str(vault))  # no --yes, no TTY
    assert code == 1
    assert "--yes" in capsys.readouterr().err
    assert "fitness" in load_config(vault).modules  # nothing was removed


def test_json_confirmation_error_is_a_document_too(tmp_path, capsys):
    """Both halves of #134 together: no TTY + no --yes fails clearly, and the
    failure itself is still one JSON document on stdout."""
    vault = init_minimal_vault(tmp_path)
    (vault / "templates" / "Note.md").unlink()
    capsys.readouterr()
    code = run_cli("apply", "--vault", str(vault), "--json")  # no --yes, no TTY
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert "--yes" in payload["error"]
    assert "applied" not in payload


# ------------------------------------- ANSI presentation layer (issue #133)
#
# Styling happens at the print boundary only: render_* output stays plain text
# because it feeds the --json twins and adopt's acceptance_token. Color is off
# whenever stdout is not a TTY, so the whole suite exercises the plain branch
# by construction — these tests flip the switches explicitly.


def test_color_stays_off_when_stdout_is_not_a_tty(monkeypatch):
    from onyxian import cli

    monkeypatch.delenv("NO_COLOR", raising=False)
    assert cli._detect_color() is False  # pytest's capture is not a TTY


def test_no_color_beats_a_real_tty(monkeypatch):
    """https://no-color.org: any non-empty NO_COLOR wins over TTY detection."""
    from onyxian import cli

    monkeypatch.setattr(sys, "stdout", types.SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli, "_enable_vt", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert cli._detect_color() is True
    monkeypatch.setenv("NO_COLOR", "1")
    assert cli._detect_color() is False


def test_windows_vt_probe_returns_a_bool_without_crashing():
    """Piped stdout on Windows has no console mode; the probe must degrade, not raise."""
    from onyxian import cli

    assert cli._enable_vt() in (True, False)


def test_stylize_is_the_identity_when_color_is_off(monkeypatch):
    from onyxian import cli

    monkeypatch.setattr(cli, "_color_on", False)
    block = "planned changes:\n  + Home.md  (core)\nvault verdict: healthy"
    assert cli._stylize(block) == block


def test_stylize_colors_badges_labels_and_verdicts(monkeypatch):
    """Escapes wrap only the badge/label/verdict token; stripping them restores the text."""
    from onyxian import cli

    monkeypatch.setattr(cli, "_color_on", True)
    block = "\n".join(
        [
            "planned changes:",
            "  + Home.md  (core)",
            "  ~ update Start-Here.md  (core)",
            "  x BLOCKED Templates/Note.md  (core)",
            "  ok: ledger verified",
            "warn: 1 change(s) pending",
            "      -> run `onyxian apply`",
            "vault verdict: needs attention",
        ]
    )
    styled = cli._stylize(block)
    assert "\x1b[32m+\x1b[0m" in styled  # create badge: green
    assert "\x1b[33m~\x1b[0m" in styled  # update badge: yellow
    assert "\x1b[31mx\x1b[0m" in styled  # blocked badge: red
    assert "\x1b[32mok\x1b[0m" in styled
    assert "\x1b[33mwarn\x1b[0m" in styled
    assert "\x1b[33mneeds attention\x1b[0m" in styled
    assert styled.splitlines()[0].startswith("\x1b[1m")  # section header: bold
    assert re.sub("\x1b\\[[0-9;]*m", "", styled) == block


def test_help_teaches_by_example():
    """#133: the top-level help and the busiest commands carry usage examples."""
    from onyxian.cli import build_parser

    parser = build_parser()
    top = parser.format_help()
    assert "examples:" in top
    assert "onyxian add fitness" in top
    subactions = next(a for a in parser._actions if getattr(a, "choices", None))
    assert isinstance(subactions.choices, dict)  # subparsers map name -> parser
    assert "examples:" in subactions.choices["init"].format_help()

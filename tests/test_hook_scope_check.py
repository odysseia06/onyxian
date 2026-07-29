"""`onyxian hook scope-check` — the PreToolUse gate (issue #11, phase 3).

Reads the PreToolUse JSON from stdin, looks the agent's write globs up in
`.claude/onyxian-scopes.json`, and emits a `permissionDecision` (deny/ask) — or
stays silent (exit 0) to let a command through. It never emits `allow`: the hook
only ever *narrows* permissions, never broadens them.
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from conftest import run_cli


def _vault(
    tmp_path: Path, scopes: Mapping[str, object], *, daily: Mapping[str, object] | None = None
) -> Path:
    vault = tmp_path / "vault"
    (vault / ".claude").mkdir(parents=True)
    (vault / ".claude" / "onyxian-scopes.json").write_text(json.dumps(scopes), encoding="utf-8")
    if daily is not None:
        (vault / ".obsidian").mkdir(parents=True, exist_ok=True)
        (vault / ".obsidian" / "daily-notes.json").write_text(json.dumps(daily), encoding="utf-8")
    return vault


def _run(monkeypatch, capsys, vault: Path, agent: str, command: str, tool: str = "Bash"):
    payload = {"tool_name": tool, "tool_input": {"command": command}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    code = run_cli("hook", "scope-check", "--agent", agent, "--vault", str(vault))
    out = capsys.readouterr().out
    decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out.strip() else None
    return code, decision, out


DP = {"daily-planner": {"write": ["Daily-Notes/**"]}}


def test_out_of_scope_write_is_denied(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    code, decision, out = _run(
        monkeypatch,
        capsys,
        vault,
        "daily-planner",
        'obsidian create path="Secret/x.md" content="hi"',
    )
    assert code == 0 and decision == "deny"
    assert "Secret/x.md" in out


def test_unprovable_target_asks(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    code, decision, _ = _run(
        monkeypatch, capsys, vault, "daily-planner", 'obsidian append file="Some Note" content="x"'
    )
    assert code == 0 and decision == "ask"


def test_in_scope_write_is_allowed_through_silently(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    code, decision, out = _run(
        monkeypatch,
        capsys,
        vault,
        "daily-planner",
        'obsidian create path="Daily-Notes/2026/x.md" content="x"',
    )
    assert code == 0 and decision is None and out.strip() == ""


def test_read_only_command_is_allowed_through_silently(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    code, _, out = _run(
        monkeypatch, capsys, vault, "daily-planner", 'obsidian read path="Secret/anything.md"'
    )
    assert code == 0 and out.strip() == ""


def test_daily_append_resolves_from_config_and_allows(monkeypatch, capsys, tmp_path):
    vault = _vault(
        tmp_path,
        DP,
        daily={
            "format": "YYYY/MM/YYYY-MM-DD",
            "folder": "Daily-Notes",
            "template": "Templates/Daily/Daily Note",
        },
    )
    code, _, out = _run(
        monkeypatch, capsys, vault, "daily-planner", 'obsidian daily:append content="- [ ] t"'
    )
    assert code == 0 and out.strip() == ""  # today's daily note is under Daily-Notes/** -> allowed


def test_daily_append_asks_when_no_daily_config(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)  # no .obsidian/daily-notes.json
    code, decision, _ = _run(
        monkeypatch, capsys, vault, "daily-planner", 'obsidian daily:append content="x"'
    )
    assert code == 0 and decision == "ask"


def test_missing_scopes_file_never_blocks(monkeypatch, capsys, tmp_path):
    vault = tmp_path / "bare"
    vault.mkdir()
    code, _, out = _run(
        monkeypatch, capsys, vault, "daily-planner", 'obsidian create path="Secret/x.md"'
    )
    assert code == 0 and out.strip() == ""


def test_unknown_agent_never_blocks(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    code, _, out = _run(
        monkeypatch, capsys, vault, "ghost-agent", 'obsidian create path="Secret/x.md"'
    )
    assert code == 0 and out.strip() == ""


def test_non_bash_tool_is_ignored(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    payload = {"tool_name": "Read", "tool_input": {"file_path": "Secret/x.md"}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    code = run_cli("hook", "scope-check", "--agent", "daily-planner", "--vault", str(vault))
    assert code == 0 and capsys.readouterr().out.strip() == ""


def _run_write(monkeypatch, capsys, vault: Path, agent: str, tool: str, file_path: str):
    payload = {"tool_name": tool, "tool_input": {"file_path": file_path}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    code = run_cli("hook", "scope-check", "--agent", agent, "--vault", str(vault))
    out = capsys.readouterr().out
    decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out.strip() else None
    return code, decision, out


@pytest.mark.parametrize("tool", ["Write", "Edit"])
def test_direct_write_in_scope_is_allowed_through_silently(monkeypatch, capsys, tmp_path, tool):
    vault = _vault(tmp_path, DP)
    code, decision, out = _run_write(
        monkeypatch, capsys, vault, "daily-planner", tool, str(vault / "Daily-Notes" / "x.md")
    )
    assert code == 0 and decision is None and out.strip() == ""


@pytest.mark.parametrize("tool", ["Write", "Edit"])
def test_direct_write_out_of_scope_is_denied(monkeypatch, capsys, tmp_path, tool):
    vault = _vault(tmp_path, DP)
    code, decision, out = _run_write(
        monkeypatch, capsys, vault, "daily-planner", tool, str(vault / "Secret" / "x.md")
    )
    assert code == 0 and decision == "deny"
    assert "Secret/x.md" in out


def test_direct_write_outside_the_vault_is_denied(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    outside = tmp_path / "elsewhere" / "x.md"
    code, decision, out = _run_write(
        monkeypatch, capsys, vault, "daily-planner", "Write", str(outside)
    )
    assert code == 0 and decision == "deny"
    assert "outside the vault" in out


def test_direct_write_with_missing_scopes_asks_instead_of_allowing(monkeypatch, capsys, tmp_path):
    """Write/Edit are re-allowed on hooked agents *because* the hook path-checks them,
    so an unreadable scopes file degrades to ask — unlike the Bash arm, which polices
    a channel that exists regardless and stays fail-open."""
    vault = tmp_path / "bare"
    vault.mkdir()
    code, decision, _ = _run_write(
        monkeypatch, capsys, vault, "daily-planner", "Write", str(vault / "Daily-Notes" / "x.md")
    )
    assert code == 0 and decision == "ask"


def test_direct_write_with_malformed_file_path_stays_silent(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    payload = {"tool_name": "Write", "tool_input": {"file_path": 5}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    code = run_cli("hook", "scope-check", "--agent", "daily-planner", "--vault", str(vault))
    assert code == 0 and capsys.readouterr().out.strip() == ""


@pytest.mark.parametrize(
    "payload",
    [
        "[1]",  # issue #49: valid JSON, not an object
        '"x"',
        "3",
        "null",
        '{"tool_name": "Bash", "tool_input": [1]}',  # object, but tool_input is not one
        '{"tool_name": "Bash", "tool_input": {"command": 5}}',  # command is not a string
        '{"tool_name": ["Bash"], "tool_input": {"command": "obsidian create path=\\"x.md\\""}}',
    ],
)
def test_malformed_payload_never_breaks_the_session(monkeypatch, capsys, tmp_path, payload):
    """A PreToolUse hook must exit 0 and stay silent on any garbage stdin — a traceback
    here breaks the user's session over input the hook does not even own."""
    vault = _vault(tmp_path, DP)
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    code = run_cli("hook", "scope-check", "--agent", "daily-planner", "--vault", str(vault))
    assert code == 0 and capsys.readouterr().out.strip() == ""


def test_malformed_daily_notes_config_never_breaks_the_session(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".obsidian" / "daily-notes.json").write_text("[1]", encoding="utf-8")
    code, decision, _ = _run(
        monkeypatch, capsys, vault, "daily-planner", 'obsidian daily:append content="x"'
    )
    assert code == 0 and decision == "ask"  # unresolvable target stays unprovable


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        ("YYYY-MM-DD", "2026-01-01"),
        ("YYYY/MM MMMM/YYYY-MM-DD", "2026/01 January/2026-01-01"),  # MMMM ate MM's replacement
        ("MMM D, YYYY", "Jan 1, 2026"),
        ("YYYY-MM-DD dddd", "2026-01-01 Thursday"),
        ("[Daily] YYYY-MM-DD", "Daily 2026-01-01"),  # [...] is a moment.js literal escape
        ("YY-MM-DD", "26-01-01"),
    ],
)
def test_daily_note_format_tokens_resolve(monkeypatch, capsys, tmp_path, fmt, expected):
    """A wrong stamp is a wrong proof: it denies or asks on an in-scope write. The write
    glob pins the exact path, so any mis-rendered token shows up as a deny."""
    vault = _vault(
        tmp_path,
        {"daily-planner": {"write": [f"Daily-Notes/{expected}.md"]}},
        daily={"format": fmt, "folder": "Daily-Notes"},
    )
    code, decision, out = _run(
        monkeypatch, capsys, vault, "daily-planner", 'obsidian daily:append content="x"'
    )
    assert code == 0 and decision is None, out


def test_unresolvable_daily_note_format_asks_instead_of_guessing(monkeypatch, capsys, tmp_path):
    """`Do`/`w`/`Q` and friends are not resolved; the hook must say so, not invent a path."""
    vault = _vault(tmp_path, DP, daily={"format": "YYYY-[W]ww", "folder": "Daily-Notes"})
    code, decision, _ = _run(
        monkeypatch, capsys, vault, "daily-planner", 'obsidian daily:append content="x"'
    )
    assert code == 0 and decision == "ask"

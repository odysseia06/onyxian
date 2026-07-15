"""`onyxian hook scope-check` — the PreToolUse gate (issue #11, phase 3).

Reads the PreToolUse JSON from stdin, looks the agent's write globs up in
`.claude/onyxian-scopes.json`, and emits a `permissionDecision` (deny/ask) — or
stays silent (exit 0) to let a command through. It never emits `allow`: the hook
only ever *narrows* permissions, never broadens them.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from conftest import run_cli


def _vault(tmp_path: Path, scopes: dict, *, daily: dict | None = None) -> Path:
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
    code, decision, out = _run(monkeypatch, capsys, vault, "daily-planner",
                               'obsidian create path="Secret/x.md" content="hi"')
    assert code == 0 and decision == "deny"
    assert "Secret/x.md" in out


def test_unprovable_target_asks(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    code, decision, _ = _run(monkeypatch, capsys, vault, "daily-planner",
                             'obsidian append file="Some Note" content="x"')
    assert code == 0 and decision == "ask"


def test_in_scope_write_is_allowed_through_silently(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    code, decision, out = _run(monkeypatch, capsys, vault, "daily-planner",
                               'obsidian create path="Daily-Notes/2026/x.md" content="x"')
    assert code == 0 and decision is None and out.strip() == ""


def test_read_only_command_is_allowed_through_silently(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    code, _, out = _run(monkeypatch, capsys, vault, "daily-planner",
                               'obsidian read path="Secret/anything.md"')
    assert code == 0 and out.strip() == ""


def test_daily_append_resolves_from_config_and_allows(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP, daily={"format": "YYYY/MM/YYYY-MM-DD", "folder": "Daily-Notes",
                                        "template": "Templates/Daily/Daily Note"})
    code, _, out = _run(monkeypatch, capsys, vault, "daily-planner",
                               'obsidian daily:append content="- [ ] t"')
    assert code == 0 and out.strip() == ""  # today's daily note is under Daily-Notes/** -> allowed


def test_daily_append_asks_when_no_daily_config(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)  # no .obsidian/daily-notes.json
    code, decision, _ = _run(monkeypatch, capsys, vault, "daily-planner",
                             'obsidian daily:append content="x"')
    assert code == 0 and decision == "ask"


def test_missing_scopes_file_never_blocks(monkeypatch, capsys, tmp_path):
    vault = tmp_path / "bare"
    vault.mkdir()
    code, _, out = _run(monkeypatch, capsys, vault, "daily-planner",
                               'obsidian create path="Secret/x.md"')
    assert code == 0 and out.strip() == ""


def test_unknown_agent_never_blocks(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    code, _, out = _run(monkeypatch, capsys, vault, "ghost-agent",
                               'obsidian create path="Secret/x.md"')
    assert code == 0 and out.strip() == ""


def test_non_bash_tool_is_ignored(monkeypatch, capsys, tmp_path):
    vault = _vault(tmp_path, DP)
    payload = {"tool_name": "Read", "tool_input": {"file_path": "Secret/x.md"}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    code = run_cli("hook", "scope-check", "--agent", "daily-planner", "--vault", str(vault))
    assert code == 0 and capsys.readouterr().out.strip() == ""

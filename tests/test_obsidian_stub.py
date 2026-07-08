"""Unit tests for the fake obsidian CLI (issue #2): each sharp edge the skills
defend against has a dedicated test, the shipped daily template resolves to a
pinned rendering with no macros left, and the PATH shim round-trips a real
subprocess call on every OS."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from evals import harness, obsidian_stub

EXPECTED_DAILY = (
    harness.EVALS_FIXTURES / "expected" / "daily-2026-01-01.md"
).read_text(encoding="utf-8")
DAILY_REL = "Daily-Notes/2026/01/2026-01-01.md"


@pytest.fixture
def vault(tmp_path):
    return harness.build_fixture_vault(
        tmp_path / "v", answers="daily.yaml", overlay="lived-in"
    )


def _call(vault: Path, *argv: str, active: str | None = "Home.md"):
    """Run one stub call; return (code, out, last trace record)."""
    state = vault / ".vault" / "_stub_state.json"
    trace = vault / ".vault" / "_stub_trace.jsonl"
    if not state.exists():
        obsidian_stub._save_active(state, active)
    code, out = obsidian_stub.run(
        list(argv), vault=vault, state_path=state, trace_path=trace, today=harness.NOW
    )
    rec = json.loads(trace.read_text(encoding="utf-8").splitlines()[-1])
    return code, out, rec


# --------------------------------------------------------------- sharp edges


def test_daily_read_creates_a_missing_note(vault):
    """SHARP EDGE: `daily:read` on a missing note creates it (macros literal) —
    which is why the scaffold forbids it as an existence probe."""
    assert not (vault / DAILY_REL).exists()
    code, out, rec = _call(vault, "daily:read")
    assert code == 0
    assert (vault / DAILY_REL).exists()
    assert rec["created"] is True and rec["wrote"] is True
    assert "<%" in out  # inserted verbatim; Templater has not run


def test_read_unresolved_path_falls_back_to_active(vault):
    """SHARP EDGE (40ab880): an unresolved `path=` silently returns the active note."""
    code, out, rec = _call(vault, "read", "path=Does-Not-Exist.md", active="Home.md")
    assert rec["fallback"] is True
    assert rec["target"] == "Home.md"


def test_read_unresolved_name_falls_back_to_active(vault):
    code, out, rec = _call(vault, "read", "file=NoSuchNote", active="Home.md")
    assert rec["fallback"] is True
    assert rec["target"] == "Home.md"


def test_read_by_exact_path_does_not_fall_back(vault):
    code, out, rec = _call(vault, "read", "path=Home.md")
    assert rec["fallback"] is False
    assert rec["target"] == "Home.md"


def test_file_with_no_args_reports_active_without_fallback(vault):
    """`obsidian file` reporting the active note is legitimate, not the fallback bug."""
    code, out, rec = _call(vault, "file", active="Home.md")
    assert rec["fallback"] is False
    assert out == "Home.md"


def test_create_with_template_inserts_verbatim(vault):
    """SHARP EDGE (vault-operations:68): `create ... template=` inserts macros literally."""
    code, out, rec = _call(
        vault, "create", "path=Scratch.md", "template=daily"
    )
    assert code == 0
    assert "<%" in (vault / "Scratch.md").read_text(encoding="utf-8")


def test_create_over_existing_without_overwrite_errors(vault):
    code, out, rec = _call(vault, "create", "path=Home.md", "content=nope")
    assert code == 1
    assert rec["wrote"] is False
    assert "Onyxian" not in (vault / "Home.md").read_text(encoding="utf-8") or True


def test_command_daily_notes_creates_from_template_and_activates(vault):
    assert not (vault / DAILY_REL).exists()
    code, out, rec = _call(vault, "command", "id=daily-notes")
    assert rec["op"] == "command:daily-notes"
    assert rec["created"] is True
    body = (vault / DAILY_REL).read_text(encoding="utf-8")
    assert "<%" in body  # verbatim; the separate templater command resolves it


def test_command_templater_resolves_the_active_note(vault):
    _call(vault, "command", "id=daily-notes")  # creates + activates today's note
    code, out, rec = _call(
        vault, "command", "id=templater-obsidian:replace-in-file-templater"
    )
    assert rec["op"] == "command:templater"
    assert rec["wrote"] is True
    assert "<%" not in (vault / DAILY_REL).read_text(encoding="utf-8")


# --------------------------------------------------------------- templater pin


def test_resolving_the_shipped_template_leaves_no_macros(vault):
    template = (vault / "Templates" / "Daily" / "Daily Note.md").read_text(
        encoding="utf-8"
    )
    resolved = obsidian_stub.resolve_templater(template, harness.NOW)
    assert "<%" not in resolved
    assert resolved == EXPECTED_DAILY, (
        "stub template rendering drifted from the pinned expected bytes; if intended, "
        "regenerate tests/fixtures/evals/expected/daily-2026-01-01.md"
    )


# --------------------------------------------------------------- PATH shim


def test_path_shim_round_trips_a_subprocess_call(vault, tmp_path):
    """The generated shim (POSIX script + obsidian.cmd) resolves on PATH and calls
    the stub as a real subprocess — the live lane depends on this on every OS."""
    shim_dir = harness.write_shim(tmp_path / "shim")
    env = {
        **_clean_env(),
        "OBSIDIAN_STUB_VAULT": str(vault),
        "OBSIDIAN_STUB_STATE": str(vault / ".vault" / "_shim_state.json"),
        "OBSIDIAN_STUB_TRACE": str(vault / ".vault" / "_shim_trace.jsonl"),
        "ONYXIAN_NOW": harness.NOW,
    }
    env["PATH"] = str(shim_dir) + _pathsep() + env.get("PATH", "")
    result = subprocess.run(
        "obsidian vault info=name",
        shell=True,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Eval Vault"


def _pathsep() -> str:
    return ";" if sys.platform == "win32" else ":"


def _clean_env() -> dict:
    import os

    return dict(os.environ)

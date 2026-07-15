"""Shared eval plumbing reused by the scripted lane (``tests/test_agent_evals.py``)
and the live lane (``tools/eval_live.py``): build a fixture vault, replay a
transcript's steps through the stub, snapshot the vault, run the contracts, and
generate the PATH shim for the live/subprocess lane.

Keeping this in one place is a hard requirement (issue #2 acceptance criteria):
the live runner must build the *same* vault and run the *same* checkers as CI.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

from onyxian.cli import main as onyxian_main

from evals import contracts, obsidian_stub

REPO_ROOT = Path(__file__).resolve().parents[2]
ANSWERS_DIR = REPO_ROOT / "tests" / "fixtures" / "answers"
EVALS_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "evals"
OVERLAY_DIR = EVALS_FIXTURES / "overlay"
TRANSCRIPTS_DIR = EVALS_FIXTURES / "transcripts"
MODULES_DIR = REPO_ROOT / "modules"
NOW = "2026-01-01"


# --------------------------------------------------------------- fixture vault


def build_fixture_vault(
    dest: Path,
    *,
    answers: str,
    overlay: str | None = None,
    daily_state: str = "absent",
    pre: dict[str, str] | None = None,
    today: str = NOW,
) -> Path:
    """Init a vault from an answers fixture, apply an overlay, and set the daily
    note's pre-state (``absent`` | ``clean`` | ``macros``) plus any ``pre`` files."""
    os.environ["ONYXIAN_NOW"] = today
    with contextlib.redirect_stdout(io.StringIO()):  # the init banner is noise here
        code = onyxian_main(["init", str(dest), "--answers", str(ANSWERS_DIR / answers), "--yes"])
    if code != 0:
        raise RuntimeError(f"onyxian init failed for {answers} (exit {code})")

    if overlay:
        src = OVERLAY_DIR / overlay
        for f in sorted(src.rglob("*")):
            if f.is_file():
                out = dest / f.relative_to(src)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(f.read_bytes())

    if daily_state != "absent":
        daily_rel = obsidian_stub._daily_rel(dest, today)
        template = (dest / obsidian_stub._template_rel(dest)).read_text(encoding="utf-8")
        content = (
            obsidian_stub.resolve_templater(template, today) if daily_state == "clean" else template
        )
        out = dest / daily_rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8", newline="\n")

    for rel, content in (pre or {}).items():
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8", newline="\n")

    return dest


def snapshot(vault: Path) -> dict[str, str]:
    """Portable relpath -> text content for every file under the vault."""
    return {
        p.relative_to(vault).as_posix(): p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(vault.rglob("*"))
        if p.is_file()
    }


# --------------------------------------------------------------- replay


def replay(
    vault: Path, steps: list[list[str]], *, active: str | None = None, today: str = NOW
) -> list[dict]:
    """Run each ``[op, k=v, ...]`` step through the stub in-process; return the trace."""
    state_path = vault / ".vault" / "_stub_state.json"
    trace_path = vault / ".vault" / "_stub_trace.jsonl"
    if trace_path.exists():
        trace_path.unlink()
    obsidian_stub._save_active(state_path, active)

    for step in steps:
        argv = [str(tok) for tok in step]
        obsidian_stub.run(
            argv, vault=vault, state_path=state_path, trace_path=trace_path, today=today
        )

    trace: list[dict] = []
    for i, line in enumerate(trace_path.read_text(encoding="utf-8").splitlines(), 1):
        rec = json.loads(line)
        rec["i"] = i
        trace.append(rec)
    return trace


def run_contracts(
    trace: list[dict],
    vault_before: dict[str, str],
    vault_after: dict[str, str],
    report: dict | None,
    *,
    daily_rel: str,
    capture: dict | None = None,
    today: str = NOW,
) -> list[contracts.Violation]:
    return contracts.check_all(
        trace,
        vault_before,
        vault_after,
        report,
        daily_rel=daily_rel,
        capture=capture,
        today=today,
    )


# --------------------------------------------------------------- positive checks


def failed_calls(trace: list[dict]) -> list[dict]:
    """Trace events whose stub call exited nonzero — a misspelled command or an
    unexpected CLI error. No transcript expects a CLI error, so any nonzero exit is
    a harness failure (a broken transcript that silently stops doing its work)."""
    return [e for e in trace if e.get("code", 0) != 0]


def postcondition_failures(
    transcript: dict,
    trace: list[dict],
    vault_before: dict[str, str],
    vault_after: dict[str, str],
    daily_rel: str,
) -> list[str]:
    """Check that the intended behavior actually *happened* — not merely that
    nothing bad did. The contracts reject bad traces; these positive checks reject
    a passing transcript that no-ops (never creates the note, never files the task).
    Returns human-readable failures; empty means clean."""
    fails: list[str] = []
    report = transcript.get("report") or {}
    existence = report.get("existence")
    if existence == "created":
        if daily_rel in vault_before:
            fails.append(f"report says existence=created but {daily_rel} existed before the run")
        if daily_rel not in vault_after:
            fails.append(f"report says existence=created but {daily_rel} was not created")
    elif existence == "already-present":
        if daily_rel not in vault_before:
            fails.append(
                f"report says existence=already-present but {daily_rel} was absent before the run"
            )

    if transcript.get("capture") and not transcript.get("assert_no_writes"):
        appends = [e for e in trace if e["op"] in ("append", "daily:append") and e["wrote"]]
        if not appends:
            fails.append("capture scenario filed nothing — no append/daily:append write occurred")
        for e in appends:
            payload = (e["payload"] or "").strip()
            if payload and payload not in vault_after.get(e["target"], ""):
                fails.append(
                    f"append to {e['target']} did not persist: {payload!r} missing after the run"
                )
    return fails


# --------------------------------------------------------------- PATH shim


def write_shim(shim_dir: Path) -> Path:
    """Write an ``obsidian`` PATH shim (POSIX script + Windows ``.cmd``) that calls
    the stub as a subprocess. Returns ``shim_dir`` (prepend it to ``PATH``)."""
    shim_dir.mkdir(parents=True, exist_ok=True)
    stub = obsidian_stub.__file__
    py = sys.executable

    posix = shim_dir / "obsidian"
    posix.write_text(f'#!/bin/sh\nexec "{py}" "{stub}" "$@"\n', encoding="utf-8", newline="\n")
    posix.chmod(0o755)

    cmd = shim_dir / "obsidian.cmd"
    cmd.write_text(f'@echo off\r\n"{py}" "{stub}" %*\r\n', encoding="utf-8", newline="\r\n")
    return shim_dir

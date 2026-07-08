"""Behavioral eval driver (issue #2): replay each scripted transcript through the
fake obsidian CLI and grade the trace with the contract checkers.

- Passing transcripts must raise zero violations (and, where declared, write nothing).
- Expected-violation transcripts must raise *exactly* their declared rule ids.
- Every rule has at least one passing and one failing transcript in the suite.
- Each transcript pins its module version; a bump without re-deriving fails a test.

What this cannot assert is stated plainly in tests/evals/README.md.
"""

from __future__ import annotations

import importlib.util

import yaml
import pytest

from evals import contracts, harness, obsidian_stub

TRANSCRIPTS = sorted(harness.TRANSCRIPTS_DIR.glob("*.yaml"))
EXPECTED_DAILY = (
    harness.EVALS_FIXTURES / "expected" / "daily-2026-01-01.md"
).read_text(encoding="utf-8")


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _expand(steps: list[list]) -> list[list[str]]:
    """Expand the `content=@resolved-daily` sentinel to the pinned resolved bytes."""
    out = []
    for step in steps:
        out.append(
            [
                "content=" + EXPECTED_DAILY if tok == "content=@resolved-daily" else str(tok)
                for tok in step
            ]
        )
    return out


def _fmt(path, violations, expect) -> str:
    lines = [
        f"{path.name}: fired {sorted({v.rule for v in violations})}, expected {sorted(expect)}"
    ]
    for v in violations:
        lines.append(f"  [{v.rule}] step {v.step}: {v.message}")
    return "\n".join(lines)


@pytest.mark.parametrize("path", TRANSCRIPTS, ids=lambda p: p.stem)
def test_transcript(path, tmp_path):
    t = _load(path)
    vault = harness.build_fixture_vault(
        tmp_path / "v",
        answers=t["vault"]["answers"],
        overlay=t["vault"].get("overlay"),
        daily_state=t.get("daily_state", "absent"),
        pre=t.get("pre"),
    )
    daily_rel = obsidian_stub._daily_rel(vault, harness.NOW)
    before = harness.snapshot(vault)
    trace = harness.replay(
        vault, _expand(t["steps"]), active=t.get("state", {}).get("active")
    )
    after = harness.snapshot(vault)

    # Universal: every stub call must succeed. A misspelled command or an
    # unexpected CLI error means the transcript silently stopped doing its work.
    bad = harness.failed_calls(trace)
    assert not bad, f"{path.name}: stub calls exited nonzero: " + "; ".join(
        f"step {e['i']} {e['argv']} -> {e['code']}" for e in bad
    )

    violations = harness.run_contracts(
        trace, before, after, t.get("report"), daily_rel=daily_rel, capture=t.get("capture")
    )
    fired = {v.rule for v in violations}
    expect = set(t.get("expect_violations", []))

    if expect:
        assert fired == expect, _fmt(path, violations, expect)
    else:
        assert not violations, _fmt(path, violations, expect)
        # Positive postconditions: the intended creation/append actually happened.
        pc = harness.postcondition_failures(t, trace, before, after, daily_rel)
        assert not pc, f"{path.name}: postcondition(s) failed:\n  " + "\n  ".join(pc)
        if t.get("assert_no_writes"):
            wrote = [e["op"] for e in trace if e["wrote"]]
            assert not wrote, f"{path.name}: expected zero writes, got {wrote}"


@pytest.mark.parametrize("path", TRANSCRIPTS, ids=lambda p: p.stem)
def test_transcript_module_version_is_pinned(path):
    """A transcript encodes one reading of a skill's prose; the pin must track the
    module that *provides* that skill, so a bump there forces the transcript to be
    re-derived and re-pinned (the RELEASING.md discipline, extended to behavior)."""
    t = _load(path)
    manifest = yaml.safe_load(
        (harness.MODULES_DIR / t["module"] / "module.yaml").read_text(encoding="utf-8")
    )
    actual = str(manifest["version"])
    assert str(t["module_version"]) == actual, (
        f"{path.name} pins {t['module']} v{t['module_version']} but its module.yaml is "
        f"v{actual}. Re-derive the transcript from the new prose and re-pin `module_version`."
    )
    provided = manifest.get("provides", {}).get("skills", [])
    assert t["skill"] in provided, (
        f"{path.name} encodes skill '{t['skill']}' but module '{t['module']}' provides "
        f"{provided}; pin the module that actually ships the skill's prose."
    )


def test_every_rule_has_a_failing_transcript():
    covered = set()
    for path in TRANSCRIPTS:
        covered |= set(_load(path).get("expect_violations", []))
    missing = contracts.RULE_IDS - covered
    assert not missing, f"rules with no expected-violation transcript: {sorted(missing)}"


def test_suite_is_not_empty():
    assert TRANSCRIPTS, "no transcripts discovered under tests/fixtures/evals/transcripts/"


# ------------------------------------------------- positive-check regressions
# These prove the harness catches a transcript that silently stops doing its work
# (a no-op or a misspelled command), not just one that misbehaves.


def test_a_misspelled_command_is_flagged(tmp_path):
    vault = harness.build_fixture_vault(
        tmp_path / "v", answers="daily.yaml", overlay="lived-in", daily_state="clean"
    )
    trace = harness.replay(
        vault,
        [["vault", "info=name"], ["daily:apend", "content=- [ ] x ➕ 2026-01-01"]],
        active="Home.md",
    )
    assert harness.failed_calls(trace), "a misspelled command must exit nonzero and be flagged"


def test_a_capture_that_never_appends_is_flagged():
    t = {"capture": {"kind": "none"}}
    trace = [
        {"i": 1, "op": "vault", "target": None, "wrote": False, "payload": None, "code": 0},
        {"i": 2, "op": "daily:read", "target": "D.md", "wrote": False, "payload": None, "code": 0},
    ]
    fails = harness.postcondition_failures(t, trace, {}, {}, "D.md")
    assert any("filed nothing" in f for f in fails)


def test_a_created_report_without_creation_is_flagged():
    t = {"report": {"existence": "created"}}
    fails = harness.postcondition_failures(t, [], {}, {}, "D.md")  # after lacks the note
    assert any("was not created" in f for f in fails)


def test_an_append_that_did_not_persist_is_flagged():
    t = {"capture": {"kind": "none"}}
    trace = [
        {"i": 1, "op": "daily:append", "target": "D.md", "wrote": True, "payload": "- [ ] x", "code": 0}
    ]
    fails = harness.postcondition_failures(t, trace, {}, {"D.md": "(nothing here)"}, "D.md")
    assert any("did not persist" in f for f in fails)


# --------------------------------------------------------------- live lane (seam)

_EVAL_LIVE = harness.REPO_ROOT / "tools" / "eval_live.py"


def _load_eval_live():
    spec = importlib.util.spec_from_file_location("eval_live", _EVAL_LIVE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_eval_live_is_inert_without_the_env_flag(monkeypatch, capsys):
    monkeypatch.delenv("ONYXIAN_EVAL_LIVE", raising=False)
    rc = _load_eval_live().main([])
    assert rc == 0
    assert "inert" in capsys.readouterr().out.lower()


def test_eval_live_reuses_the_shared_fixture_builder_shim_and_checkers():
    src = _EVAL_LIVE.read_text(encoding="utf-8")
    assert "harness.build_fixture_vault" in src
    assert "harness.write_shim" in src
    assert "contracts.check_all" in src


def test_eval_live_is_not_wired_into_any_workflow():
    wf = harness.REPO_ROOT / ".github" / "workflows"
    if not wf.is_dir():
        pytest.skip("no .github/workflows in this checkout")
    hits = [
        p.name for p in wf.rglob("*.y*ml") if "eval_live" in p.read_text(encoding="utf-8")
    ]
    assert not hits, f"the live lane must never gate CI; referenced in: {hits}"

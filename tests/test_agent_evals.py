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


def _module_version(module: str) -> str:
    data = yaml.safe_load((harness.MODULES_DIR / module / "module.yaml").read_text(encoding="utf-8"))
    return str(data["version"])


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

    violations = harness.run_contracts(
        trace, before, after, t.get("report"), daily_rel=daily_rel, capture=t.get("capture")
    )
    fired = {v.rule for v in violations}
    expect = set(t.get("expect_violations", []))

    if expect:
        assert fired == expect, _fmt(path, violations, expect)
    else:
        assert not violations, _fmt(path, violations, expect)
        if t.get("assert_no_writes"):
            wrote = [e["op"] for e in trace if e["wrote"]]
            assert not wrote, f"{path.name}: expected zero writes, got {wrote}"


@pytest.mark.parametrize("path", TRANSCRIPTS, ids=lambda p: p.stem)
def test_transcript_module_version_is_pinned(path):
    """A transcript encodes one reading of a skill's prose; when the providing
    module version moves, the transcript must be re-derived from the new prose and
    re-pinned (the RELEASING.md pinned-version discipline, extended to behavior)."""
    t = _load(path)
    actual = _module_version(t["module"])
    assert str(t["module_version"]) == actual, (
        f"{path.name} pins {t['module']} v{t['module_version']} but its module.yaml is "
        f"v{actual}. Re-derive the transcript from the new prose and re-pin `module_version`."
    )


def test_every_rule_has_a_failing_transcript():
    covered = set()
    for path in TRANSCRIPTS:
        covered |= set(_load(path).get("expect_violations", []))
    missing = contracts.RULE_IDS - covered
    assert not missing, f"rules with no expected-violation transcript: {sorted(missing)}"


def test_suite_is_not_empty():
    assert TRANSCRIPTS, "no transcripts discovered under tests/fixtures/evals/transcripts/"


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

"""Live-LLM eval lane (issue #2) — the seam, not the gate.

The scripted lane in ``tests/test_agent_evals.py`` grades the *maintainer's*
reading of a skill's prose. It cannot tell whether a real model, handed the
skill and a scenario's opening prompt, follows the procedure. This runner closes
that gap without ever gating CI:

1. build the **same** fixture vault the scripted lane builds
   (``evals.harness.build_fixture_vault``),
2. prepend the stub **PATH shim** so the agent's ``obsidian`` calls are recorded
   (``evals.harness.write_shim``),
3. launch a headless agent from ``ONYXIAN_EVAL_AGENT_CMD`` against the vault with
   a scenario's opening prompt, and
4. run the **same** contract checkers over the recorded trace
   (``evals.contracts.check_all``).

Inert unless ``ONYXIAN_EVAL_LIVE=1`` (an env var, matching the ``ONYXIAN_NOW``
idiom — this repo configures no pytest markers). Never wired into ``ci.yml``;
the result is an advisory pass-rate over N runs, not a pass/fail gate. v1 ships
this seam, not a running lane — plugging in an actual agent command is left to
whoever wants to spend the tokens.

Usage (from the repo root)::

    ONYXIAN_EVAL_LIVE=1 \
    ONYXIAN_EVAL_AGENT_CMD='claude -p "Scaffold today's daily note." --dangerously-...' \
    python tools/eval_live.py [scenario ...]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# tools/ is not a package; make tests/evals importable so the live lane reuses
# the exact fixture builder, shim, and checkers the scripted lane uses.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

import yaml  # noqa: E402

from evals import contracts, harness, obsidian_stub  # noqa: E402


def run_scenario(transcript_path: Path, agent_cmd: str, vault_dir: Path, *, today: str = harness.NOW):
    """Build the fixture, run the agent against it through the shim, grade the trace.

    Returns human-readable failures: contract violations, nonzero stub calls, and
    unmet postconditions (the note was never created, the task was never filed)."""
    t = yaml.safe_load(Path(transcript_path).read_text(encoding="utf-8"))
    vault = harness.build_fixture_vault(
        vault_dir,
        answers=t["vault"]["answers"],
        overlay=t["vault"].get("overlay"),
        daily_state=t.get("daily_state", "absent"),
        pre=t.get("pre"),
        today=today,
    )
    shim = harness.write_shim(vault_dir.parent / "shim")
    state = vault / ".vault" / "_live_state.json"
    trace_path = vault / ".vault" / "_live_trace.jsonl"
    obsidian_stub._save_active(state, t.get("state", {}).get("active"))
    if trace_path.exists():
        trace_path.unlink()

    env = {
        **os.environ,
        "PATH": str(shim) + os.pathsep + os.environ.get("PATH", ""),
        "OBSIDIAN_STUB_VAULT": str(vault),
        "OBSIDIAN_STUB_STATE": str(state),
        "OBSIDIAN_STUB_TRACE": str(trace_path),
        "ONYXIAN_NOW": today,
    }
    before = harness.snapshot(vault)
    subprocess.run(agent_cmd, shell=True, env=env, cwd=str(vault))
    after = harness.snapshot(vault)

    trace = []
    if trace_path.exists():
        for i, line in enumerate(trace_path.read_text(encoding="utf-8").splitlines(), 1):
            rec = json.loads(line)
            rec["i"] = i
            trace.append(rec)

    daily_rel = obsidian_stub._daily_rel(vault, today)
    violations = contracts.check_all(
        trace, before, after, t.get("report"), daily_rel=daily_rel, capture=t.get("capture"), today=today
    )
    failures = [f"[{v.rule}] step {v.step}: {v.message}" for v in violations]
    failures += [
        f"[nonzero-exit] step {e['i']} {' '.join(e['argv'])} -> {e['code']}"
        for e in harness.failed_calls(trace)
    ]
    failures += [
        f"[postcondition] {m}"
        for m in harness.postcondition_failures(t, trace, before, after, daily_rel)
    ]
    return failures


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if os.environ.get("ONYXIAN_EVAL_LIVE") != "1":
        print("eval_live: inert. Set ONYXIAN_EVAL_LIVE=1 to run the live lane.")
        return 0
    agent_cmd = os.environ.get("ONYXIAN_EVAL_AGENT_CMD")
    if not agent_cmd:
        print("eval_live: set ONYXIAN_EVAL_AGENT_CMD to the headless agent invocation.")
        return 2

    wanted = set(argv)
    scenarios = [
        p
        for p in sorted(harness.TRANSCRIPTS_DIR.glob("*.yaml"))
        if not yaml.safe_load(p.read_text(encoding="utf-8")).get("expect_violations")
        and (not wanted or p.stem in wanted)
    ]
    passed = 0
    for path in scenarios:
        with tempfile.TemporaryDirectory() as td:
            failures = run_scenario(path, agent_cmd, Path(td) / "v")
        ok = not failures
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {path.stem}")
        for f in failures:
            print(f"        {f}")
    print(f"\neval_live: {passed}/{len(scenarios)} scenarios clean (advisory, not a gate).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

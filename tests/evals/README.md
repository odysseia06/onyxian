# Behavioral eval harness (issue #2)

Everything else in the suite pins **bytes** (`test_examples.py`, `test_golden.py`),
**structure** (`test_skills.py`), or **prose↔asset drift** (`test_modules_m2.py`).
Nothing executed a skill's *procedure*. The three most recent behavior fixes
(06dc093, 3f4cdb2, 40ab880) were all found by manual dogfooding, days after they
shipped. This harness executes the deterministic procedures — the morning
scaffold and task capture — against a fake `obsidian` CLI and grades the trace,
so that class of regression is caught in CI.

It runs inside plain `python -m pytest tests -q` on the existing 3-OS × 2-Python
matrix. No new runtime dependency (stdlib + pytest + the PyYAML already used), no
`ci.yml` change, no change under `modules/`.

## The pieces

| File | Role |
|---|---|
| `obsidian_stub.py` | a fake `obsidian` CLI over a vault root; reproduces the sharp edges the skills defend against; appends a JSONL trace |
| `contracts.py` | eight pure-function checkers over `(trace, vault_before, vault_after, report)` |
| `harness.py` | shared plumbing: build a fixture vault, replay a transcript, snapshot, run the contracts, write the PATH shim |
| `../fixtures/evals/transcripts/*.yaml` | scripted procedures (8 passing + 6 expected-violation) |
| `../fixtures/evals/overlay/lived-in/` | a small lived-in overlay applied on top of a fresh `init` |
| `../fixtures/evals/expected/` | the pinned resolved daily rendering |
| `CLI_SEMANTICS.md` | provenance for each sharp edge (verified vs. assumed) |
| `../../tools/eval_live.py` | the live-LLM seam — inert unless `ONYXIAN_EVAL_LIVE=1`, never in CI |

Driver: `tests/test_agent_evals.py` (transcripts) and `tests/test_obsidian_stub.py`
(the stub itself). Each transcript pins its providing `module_version`; a bump
without re-deriving the transcript fails a test — the RELEASING.md pinned-version
discipline, extended to behavior.

## The eight contracts

Each rule has at least one passing **and** one failing transcript, so the checkers
and transcripts audit each other:

- **no-mutation-before-existence-recorded** — a scaffold records existence
  read-only before anything can create the note (3f4cdb2 / 321d965).
- **report-backed-by-reads** — an existence claim matches ground truth and a
  read-only check that preceded any mutation (3f4cdb2).
- **read-by-exact-path** — no trace event hit the silent active-note fallback
  (40ab880).
- **no-macros-written** — no written payload carries `<%` or a macro-bearing
  checkbox (06dc093).
- **create-only-when-absent** — a native create runs only when the note is
  absent; `create ... overwrite` never.
- **additive-only** — no `delete`/`move`/`rename`/`property:remove`/overwrite.
- **look-before-append** — every append target was read first, and the line was
  not already there.
- **task-line-format** — appended tasks carry `➕ <today>`; due→`📅`,
  scheduled→`⏳`, undated→`#captured` and no invented date.

## What this harness cannot assert

The scripted lane encodes the *maintainer's* reading of a skill's prose, replayed
through a fake CLI. Four things stay out of reach without a live model — the
`tools/eval_live.py` seam exists to close them, but is advisory, never a gate:

1. **Skill selection** — that a trigger phrase reaches the right skill/agent at all.
2. **Prose → procedure fidelity** — a wording change that keeps the enumerated
   steps but confuses a model passes CI. This is exactly the failure mode of the
   three shipped patches; CI v1 catches only its downstream half (a changed
   *procedure* that violates a contract), not the upstream half (unchanged
   procedure, worse prose).
3. **Natural-language parsing** in task capture ("by Friday" → the right `📅`
   date, routing inference, priority) — transcripts start *after* the parse; the
   `capture:` block states the intended parse as data.
4. **Free-text truthfulness** — v1 replaces the agent's prose reply with a
   structured `report` block and checks that instead.

## Running the live seam (optional, off by default)

```
ONYXIAN_EVAL_LIVE=1 \
ONYXIAN_EVAL_AGENT_CMD='<headless agent invocation>' \
python tools/eval_live.py [scenario ...]
```

Without `ONYXIAN_EVAL_LIVE=1` it prints one line and exits 0.

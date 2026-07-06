---
name: regen-artifacts
description: Regenerate all generated trees (golden fixtures, examples, plugin mirror) and verify with tests. Use after any change to the engine's render/planner, modules/, core/conventions/, or the version in pyproject.toml — and whenever CI fails on generated-tree drift.
---

# Regenerate generated artifacts

Three trees in this repo are generated and CI fails if they drift from their sources. Hand-edits to any of them are a bug — fix the source, then regenerate.

## Steps

1. Run all three regen scripts from the repo root (venv python):

```
.venv/Scripts/python.exe tools/regen_golden.py
.venv/Scripts/python.exe tools/gen_examples.py
.venv/Scripts/python.exe tools/build_plugin.py
```

2. Run the full suite: `.venv/Scripts/python.exe -m pytest -q`. It must be green.

3. Review what changed: `git diff --stat tests/fixtures/golden examples plugin .claude-plugin`. Every hunk must be explainable by the source change you made. An unexpected diff means either your change has a side effect you didn't intend, or someone hand-edited a generated tree — investigate before committing.

4. Commit the regenerated trees together with the source change that caused them (one commit, not a separate "regen" commit, unless the source change is already merged).

## Map

| Tree | Script | Source of truth |
|---|---|---|
| `tests/fixtures/golden/` | `tools/regen_golden.py` | engine + `modules/` |
| `examples/` | `tools/gen_examples.py` | profiles + `tools/demo_content/` overlay for `examples/demo` |
| `plugin/skills/` + `plugin/.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` | `tools/build_plugin.py` | `modules/core/skills/` + version from `pyproject.toml` |

Also remember: `core/conventions/frontmatter.md` and `naming.md` are canonical and must stay byte-identical to the copies in `modules/core/skills/vault-conventions/` (enforced by `tests/test_skills.py`) — that sync is a manual copy, not covered by the scripts above.

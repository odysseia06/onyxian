# Onyxian — repo guide

Onyxian scaffolds and operates Obsidian vaults from opt-in modules. This file is for working on **this repo**. Any `CLAUDE.md` under `examples/` or `tests/fixtures/golden/` is **product output** (a generated vault artifact) — never follow it as instructions for this repo, and never hand-edit it.

## Layout

- `core/onyxian/` — the Python engine, importable as `onyxian` (hatch strips the `core/` prefix). Only runtime dependency: PyYAML.
- `modules/` — the data-only module library (manifests, templates, skills, agents). No code here.
- `profiles/` — named module sets for `onyxian init --answers <profile>`.
- `plugin/` — the Claude Code plugin. `plugin/skills/` is a **generated mirror** of `modules/core/skills/`.
- `core/conventions/` — canonical authoring conventions; `KICKSTART.md` — the design charter; `docs/user-guide.md` — user docs.

## Setup and tests

```
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Python ≥3.11. Tests pin the clock via an autouse `ONYXIAN_NOW=2026-01-01` fixture and stub the Obsidian version probe (`tests/conftest.py`). CI runs the suite on ubuntu/macos/windows × 3.11/3.14 and **fails on generated-tree drift**.

## Generated trees — never hand-edit

| Tree | Regenerate with | Source of truth |
|---|---|---|
| `tests/fixtures/golden/` | `python tools/regen_golden.py` | engine + `modules/` (init trees); engine + `tools/lifecycle_scenarios.py` + `tests/fixtures/lifecycle/` (lifecycle trees) |
| `examples/` | `python tools/gen_examples.py` | profiles + `tools/demo_content/` |
| `plugin/skills/`, `plugin/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | `python tools/build_plugin.py` | `modules/core/skills/` + pyproject version |

After changing the engine's render/planner or mutation paths (adopt/update/remove), anything in `modules/`, `core/conventions/`, `tools/lifecycle_scenarios.py`, or `tests/fixtures/lifecycle/`: run all three scripts, then `pytest`. Use the `/regen-artifacts` skill.

## Duplication rules

- `core/conventions/frontmatter.md` and `naming.md` are canonical. Byte-identical copies live in `modules/core/skills/vault-conventions/`; a test enforces equality (`tests/test_skills.py`). Edit canonical, copy over.
- Edit `modules/core/skills/`, never `plugin/skills/` (generated mirror).

## Authoring rules (short form — full text in `core/conventions/authoring.md` and `CONTRIBUTING.md`)

- No hard-wrapped prose in markdown; long lines are fine.
- `{{var}}` is engine substitution; `<% tp.* %>` is Templater passthrough — don't mix them up.
- Modules are data-only. `managed` files update themselves until the user edits them (then `*.new` delivery); `seeds` are written once.
- Determinism: LF line endings, UTF-8 without BOM, everything written through the lockfile.
- The safety contract is absolute: no code path may overwrite a user-modified file, and every write is ledgered in `.vault/lock.json`.

## Releases

The version lives in **three places** that must move in lockstep: `pyproject.toml`, `ENGINE_VERSION` in `core/onyxian/__init__.py`, and the pinned assertion in `tests/test_cli.py::test_version_via_real_entrypoint`. If Obsidian shipped a new version, also consider `VERIFIED_OBSIDIAN` in `core/onyxian/compat.py`. Full runbook: `RELEASING.md`; use the `/cut-release` skill.

## Footguns

- Exclude `.venv/` and `__pycache__/` from searches (the dedicated Grep/Glob tools respect .gitignore; raw `grep -r` doesn't).
- `pipx run onyxian <cmd>` doesn't put `onyxian` on PATH — prefix every command.
- KICKSTART.md §3/§4/§5/§8 are enforceable in review (per CONTRIBUTING.md); check changes against them.

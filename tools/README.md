# tools

Dev and CI scripts. Nothing here runs in a user's vault.

- `regen_golden.py` — regenerate the golden vault fixtures under `tests/fixtures/golden/` from their answers files, with `ONYXIAN_NOW` pinned. The only legitimate way to change a golden tree; hand-edits to fixtures are a review-time rejection (CONTRIBUTING.md).
- `gen_examples.py` — regenerate the reference vaults under `examples/` from every profile in `profiles/`, with `ONYXIAN_NOW` pinned so the trees are byte-identical everywhere. CI reruns it and fails on drift, so every example doubles as an integration test. `examples/demo` is the one exception to "fresh init": it's the researcher-developer profile plus a deterministic overlay of lived-in content from `tools/demo_content/`.
- `build_plugin.py` — regenerate the Claude Code plugin: copies the five core skills from `modules/core/skills/` into `plugin/skills/` and stamps the plugin + marketplace manifests with the version from `pyproject.toml`, so the plugin always ships the same version as the engine. `plugin/skills/` is a generated mirror — never hand-edit it; edit the canonical skill under `modules/core/skills/` and rerun. CI fails on drift.
- `demo_content/` — the hand-authored lived-in notes that `gen_examples.py` overlays onto `examples/demo`. This is the only place demo content is edited by hand; the copy under `examples/` is generated.

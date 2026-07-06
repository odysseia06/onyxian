---
name: cut-release
description: Cut an onyxian release — bump the version in all three lockstep locations, regenerate artifacts, tag, and push. Use when the user asks to release, publish, or bump the version.
---

# Cut a release

Full runbook lives in `RELEASING.md`; this is the executable checklist. Versioning is semver; module content changes need their own `modules/<id>/module.yaml` bump (separate concern, see RELEASING.md).

## Preconditions

1. On `main`, clean tree, up to date with origin: `git status`, `git pull`.
2. CI green on main: `gh run list --branch main --limit 3`.

## Steps

1. **Bump the version in all three places, in lockstep** (missing one fails tests or ships a lying `--version`):
   - `pyproject.toml` → `version = "X.Y.Z"`
   - `core/onyxian/__init__.py` → `ENGINE_VERSION`
   - `tests/test_cli.py::test_version_via_real_entrypoint` → the pinned assertion
2. **Ask the user** whether Obsidian shipped a new verified version; if so update `VERIFIED_OBSIDIAN` in `core/onyxian/compat.py`.
3. Regenerate everything and test: invoke the `/regen-artifacts` skill (the plugin manifests embed the version, so this step is mandatory).
4. Commit: `release: onyxian X.Y.Z` — plus a short body listing what shipped. No attribution footers.
5. Tag and push: `git tag vX.Y.Z && git push origin main vX.Y.Z`.
6. Publishing is automatic: the tag triggers `.github/workflows/publish.yml` (PyPI trusted publishing). Point the user at the Actions run; confirm the new version appears on https://pypi.org/project/onyxian/.
7. Smoke-test per RELEASING.md (pipx run against a temp vault) if the release touched the engine.

## Never

- Never tag with a dirty tree or red CI.
- Never bump only some of the three version locations.
- Never hand-edit `plugin/.claude-plugin/plugin.json` or `.claude-plugin/marketplace.json` to fix a version — rerun `tools/build_plugin.py`.

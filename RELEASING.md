# Releasing Onyxian

Onyxian ships two artifacts: the Python package `onyxian` (the CLI + bundled
module library) on PyPI, and the Claude Code plugin (the skills + the
`/vault-bootstrap` command) from this repository. This doc is the owner's
release runbook.

## What ships where

- **PyPI `onyxian`** — `pip install onyxian` / `pipx install onyxian` /
  `uvx onyxian`. The wheel bundles the whole module library under
  `onyxian/_library/` (see `pyproject.toml` `[tool.hatch.build.targets.wheel]`),
  so an installed CLI finds its modules with no checkout. The import package and
  the `onyxian` command keep their names; only the distribution name is `onyxian`
  (`onyxian` was taken on PyPI).
- **Claude Code plugin** — installed straight from this repo with
  `/plugin marketplace add odysseia06/onyxian` then `/plugin install onyxian`. No PyPI
  step; the plugin's `vault-bootstrap` skill installs the CLI itself on first use.

## One-time PyPI setup (Trusted Publishing — no tokens)

Do this once, then every tagged release publishes itself.

1. Log in to <https://pypi.org> as the project owner.
2. Go to **Your projects → Publishing → Add a pending publisher** (this works
   before the project exists, so the very first release can create it):
   - **PyPI Project Name:** `onyxian`
   - **Owner:** `odysseia06`
   - **Repository name:** `onyxian`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
3. On GitHub, create the environment: **Settings → Environments → New
   environment → `pypi`** (add reviewers/branch protection if you want a manual
   gate before each publish).

That's it. No API token is stored anywhere; PyPI verifies the GitHub OIDC token
from the `publish.yml` workflow running in the `pypi` environment.

## Cutting a release

1. Make sure `main` is green (the `ci` workflow) and the working tree is clean.
2. Bump the version in `pyproject.toml` and `core/onyxian/__init__.py`
   `ENGINE_VERSION` (so `onyxian --version` matches), and update the pinned
   assertion in `tests/test_cli.py::test_version_via_real_entrypoint` (it
   asserts the exact `onyxian <version>` string). PyPI versions are immutable, so
   always go forward — e.g. `1.0.1 → 1.0.2`. (The plugin + marketplace manifests
   are stamped by `build_plugin.py` in step 3 — don't hand-edit them.)
3. Regenerate the derived artifacts and run the suite:
   ```
   python tools/regen_golden.py && python tools/gen_examples.py && python tools/build_plugin.py
   pytest
   ```
   `build_plugin.py` stamps the new version into the plugin + marketplace
   manifests, so the Claude Code plugin ships the same version as the engine.
4. Commit, then tag and push (use the new version):
   ```
   git commit -am "release: onyxian 1.0.2"
   git tag -a v1.0.2 -m "onyxian 1.0.2"
   git push origin main v1.0.2
   ```
5. The `publish.yml` workflow builds, sanity-checks that the wheel carries the
   module library, and publishes to PyPI. Watch it under the Actions tab.
6. Verify: `pipx install --force onyxian && onyxian --version`.

## Module version bumps reach existing vaults

When a release bumps a *module's* version (in `modules/<id>/module.yaml`) — not just the engine — existing vaults pick the change up with `onyxian update <id>` (or `onyxian update` for all of them). Managed files (templates, Bases, the rendered agent) reconcile in place while the user has left them alone; a file they customized is delivered as a `*.new` sibling instead, never overwritten. Tell users to preview with `onyxian update <id> --dry-run` first. Example: the `projects-software` 0.2.0 bump ships the project-steward operating playbook, so `onyxian update projects-software --dry-run` previews the refreshed `.claude/agents/project-steward.md` (or a `.new` beside a copy they edited).

## Verifying a release actually works end to end

The build job already asserts the wheel bundles the library. For a real smoke
test, install the published package into a throwaway environment with **no
checkout and no `ONYXIAN_HOME`** and create a vault:

```
pipx run onyxian init /tmp/release-smoke --answers <(printf 'modules:\n  fitness: {}\n') --yes
onyxian doctor --vault /tmp/release-smoke
```

If that produces a healthy vault, the release is good. If it errors with "cannot
locate the Onyxian module library," the wheel didn't bundle `_library/` — stop and
fix packaging before announcing.

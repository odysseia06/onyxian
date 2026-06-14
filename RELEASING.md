# Releasing Onyx

Onyx ships two artifacts: the Python package `onyx-vault` (the CLI + bundled
module library) on PyPI, and the Claude Code plugin (the skills + the
`/vault-bootstrap` command) from this repository. This doc is the owner's
release runbook.

## What ships where

- **PyPI `onyx-vault`** — `pip install onyx-vault` / `pipx install onyx-vault` /
  `uvx onyx-vault`. The wheel bundles the whole module library under
  `onyx/_library/` (see `pyproject.toml` `[tool.hatch.build.targets.wheel]`),
  so an installed CLI finds its modules with no checkout. The import package and
  the `onyx` command keep their names; only the distribution name is `onyx-vault`
  (`onyx` was taken on PyPI).
- **Claude Code plugin** — installed straight from this repo with
  `/plugin marketplace add odysseia06/onyx` then `/plugin install onyx`. No PyPI
  step; the plugin's `vault-bootstrap` skill installs the CLI itself on first use.

## One-time PyPI setup (Trusted Publishing — no tokens)

Do this once, then every tagged release publishes itself.

1. Log in to <https://pypi.org> as the project owner.
2. Go to **Your projects → Publishing → Add a pending publisher** (this works
   before the project exists, so the very first release can create it):
   - **PyPI Project Name:** `onyx-vault`
   - **Owner:** `odysseia06`
   - **Repository name:** `onyx`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
3. On GitHub, create the environment: **Settings → Environments → New
   environment → `pypi`** (add reviewers/branch protection if you want a manual
   gate before each publish).

That's it. No API token is stored anywhere; PyPI verifies the GitHub OIDC token
from the `publish.yml` workflow running in the `pypi` environment.

## Cutting a release

1. Make sure `main` is green (the `ci` workflow) and the working tree is clean.
2. Bump the version in `pyproject.toml` and `core/onyx/__init__.py`
   `ENGINE_VERSION` (so `onyx --version` matches). PyPI versions are immutable,
   so always go forward — e.g. `1.0.1 → 1.0.2`.
3. Regenerate the derived artifacts and run the suite:
   ```
   python tools/regen_golden.py && python tools/gen_examples.py && python tools/build_plugin.py
   pytest
   ```
   `build_plugin.py` stamps the new version into the plugin + marketplace
   manifests, so the Claude Code plugin ships the same version as the engine.
4. Commit, then tag and push (use the new version):
   ```
   git commit -am "release: onyx-vault 1.0.2"
   git tag -a v1.0.2 -m "onyx-vault 1.0.2"
   git push origin main v1.0.2
   ```
5. The `publish.yml` workflow builds, sanity-checks that the wheel carries the
   module library, and publishes to PyPI. Watch it under the Actions tab.
6. Verify: `pipx install --force onyx-vault && onyx --version`.

## Verifying a release actually works end to end

The build job already asserts the wheel bundles the library. For a real smoke
test, install the published package into a throwaway environment with **no
checkout and no `ONYX_HOME`** and create a vault:

```
pipx run onyx-vault init /tmp/release-smoke --answers <(printf 'modules:\n  fitness: {}\n') --yes
onyx doctor --vault /tmp/release-smoke
```

If that produces a healthy vault, the release is good. If it errors with "cannot
locate the Onyx module library," the wheel didn't bundle `_library/` — stop and
fix packaging before announcing.

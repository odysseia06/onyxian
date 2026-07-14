# Releasing Onyxian

Onyxian ships two artifacts: the Python package `onyxian` (the CLI + bundled
module library) on PyPI, and the Claude Code plugin (the skills + the
`/vault-bootstrap` command) from this repository. This doc is the owner's
release runbook.

## What ships where

- **PyPI `onyxian`** — `pip install onyxian` / `pipx install onyxian` /
  `uvx onyxian`. The wheel bundles the whole module library under
  `onyxian/_library/` (see `pyproject.toml` `[tool.hatch.build.targets.wheel]`),
  so an installed CLI finds its modules with no checkout. Distribution name,
  command, and import package are all `onyxian`. (Releases up to 1.0.14 shipped
  as `onyx-vault` with an `onyx` command; 1.1.0 renamed everything.)
- **Claude Code plugin** — installed straight from this repo with
  `/plugin marketplace add odysseia06/onyxian` then `/plugin install onyxian@onyxian`. No PyPI
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
   (`publish.yml` re-checks this: it refuses to publish a tag whose commit
   didn't pass `ci` — but starting from green is still how you avoid burning a
   version number, since PyPI releases are immutable.)
2. Bump the version in **one place**: `ENGINE_VERSION` in
   `core/onyxian/__init__.py`. Hatchling reads it at build time (`pyproject.toml`
   declares `dynamic = ["version"]`), the CLI reads it for `--version`, and
   `build_plugin.py` stamps it into the manifests — so the wheel, the CLI, the
   plugin, and the `framework.version` in generated vaults are all this one
   string. PyPI versions are immutable, so always go forward — e.g. `1.0.1 → 1.0.2`.
3. Update `CHANGELOG.md`: move everything under `## [Unreleased]` down into a new
   `## [X.Y.Z] - YYYY-MM-DD` heading (leave an empty `## [Unreleased]` above it).
   `publish.yml` greps for the `## [X.Y.Z]` heading and blocks the release if it
   is missing, so this is not optional.
5. If Obsidian shipped a new version since the last release, re-verify the
   empirical-claims inventory in `core/onyxian/compat.py` (its module docstring
   is the checklist) against the installed Obsidian, patch any skill/agent
   prose that drifted (bumping each touched `module.yaml` version), then set
   `VERIFIED_OBSIDIAN` in `compat.py` to the version you just verified —
   `onyxian doctor` compares users' installed Obsidian against it.
6. Regenerate the derived artifacts and run the suite:
   ```
   python tools/regen_golden.py && python tools/gen_examples.py && python tools/build_plugin.py
   pytest
   ```
   `build_plugin.py` stamps the new version into the plugin + marketplace
   manifests, so the Claude Code plugin ships the same version as the engine.
7. Commit, then tag and push (use the new version):
   ```
   git commit -am "release: onyxian 1.0.2"
   git tag -a v1.0.2 -m "onyxian 1.0.2"
   git push origin main v1.0.2
   ```
8. The `publish.yml` workflow first waits for this commit's `ci` run to pass,
   then builds, checks the tag matches the built version and that `CHANGELOG.md`
   has an entry for it, sanity-checks that the wheel carries the module library,
   and publishes to PyPI. Watch it under the Actions tab.
9. Verify: `pipx install --force onyxian && onyxian --version`.

## Module version bumps reach existing vaults

When a release bumps a *module's* version (in `modules/<id>/module.yaml`) — not just the engine — existing vaults pick the change up with `onyxian update <id>` (or `onyxian update` for all of them). Managed files (templates, Bases, the rendered agent) reconcile in place while the user has left them alone; a file they customized is delivered as a `*.new` sibling instead, never overwritten. Tell users to preview with `onyxian update <id> --dry-run` first. Example: the `projects-software` 0.2.0 bump ships the project-steward operating playbook, so `onyxian update projects-software --dry-run` previews the refreshed `.claude/agents/project-steward.md` (or a `.new` beside a copy they edited).

## Verifying a release actually works end to end

The build job already asserts the wheel bundles the library. For a real smoke
test, install the published package into a throwaway environment with **no
checkout and no `ONYXIAN_HOME`** and create a vault:

```
tmp=$(mktemp -d)
printf 'modules:\n  fitness: {}\n' > "$tmp/smoke-answers.yaml"
pipx run onyxian init "$tmp/release-smoke" --answers "$tmp/smoke-answers.yaml" --yes
pipx run onyxian doctor --vault "$tmp/release-smoke"
```

(Two portability notes baked into that snippet: `--answers` must be a real file on disk — the engine checks the path, so a process substitution like `<(printf ...)` won't do — and `pipx run` doesn't put `onyxian` on your PATH, so the doctor invocation goes through `pipx run` too.)

If that produces a healthy vault, the release is good. If it errors with "cannot
locate the Onyxian module library," the wheel didn't bundle `_library/` — stop and
fix packaging before announcing.

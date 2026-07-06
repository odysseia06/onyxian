---
name: add-module
description: Author a new onyxian module (or bump an existing one) following the repo's authoring conventions, test it in a scratch vault, and regenerate artifacts. Use when adding a module, adding templates/skills/agents to one, or bumping a module version.
---

# Add or update a module

Modules are **data-only** (manifest + templates + Bases + skills + agents). Read `core/conventions/authoring.md` before writing content — it is enforceable in review.

## New module

1. Scaffold: `.venv/Scripts/python.exe -m onyxian.cli module new <id>` (or `onyxian module new <id>`), which creates `modules/<id>/` with a starter `module.yaml`.
2. Fill the manifest, honoring the checklist:
   - `depends: [core]` at minimum; declare a root variable for the module's folder so users can rename it.
   - Classify every file: `managed` (framework-updated, `*.new` on user edit) vs `seeds` (written once, then the user's). When unsure, seed it — reclassifying seed→managed later is a breaking change for users.
   - `{{var}}` placeholders are engine substitution; `<% tp.* %>` is Templater passthrough. Never hard-wrap prose.
   - Frontmatter and naming must follow `core/conventions/frontmatter.md` and `naming.md`.
   - Start the version at `0.1.0`.
3. If the module ships an agent layer, give the agent a documented read/write scope and route all writes through the `vault-operations` contract (see existing modules like `daily-notes` or `research` for the pattern).
4. Test-install in a scratch vault:
   ```
   .venv/Scripts/python.exe -m onyxian.cli init <scratch-dir> --answers minimal
   cd <scratch-dir> && onyxian add <id> && onyxian doctor && onyxian plan   # plan must be empty
   ```
   Open it in Obsidian if the module ships Bases (`.base` files render only in-app).
5. Decide whether any profile in `profiles/` should include it.
6. Invoke `/regen-artifacts` and commit module + regenerated trees together.

## Content change to an existing module

1. Edit under `modules/<id>/`.
2. Bump `modules/<id>/module.yaml` version (semver: content tweak = patch, new files = minor, seed/managed reclassification or renames = major and needs a design conversation first — renamed managed paths leave STALE litter in user vaults).
3. Invoke `/regen-artifacts`.
4. Release note line: existing vaults pick this up with `onyxian update` — user-modified files arrive as `*.new` siblings.

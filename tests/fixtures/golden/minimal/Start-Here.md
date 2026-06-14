---
type: start-here
status: active
tags: []
---

# Start here

Onyx manages this vault. The engine regenerates this note when your module set changes; the moment you edit it, it is yours, and future versions will arrive beside it as `Start-Here.md.new` instead of overwriting you.

## Enabled modules

- **core** 0.1.0 — The conventions every other module builds on: the Templates root, the vault home note, and the frontmatter and naming rules that humans and agents share.

## First actions

- **core**: Open Home.md in Obsidian; it explains what was installed and how the safety contract works. The note is seeded: it is yours now, replace it freely. Onyx's templates use the Tasks and Templater community plugins, and the vault enables both. Onyx can enable plugins but cannot install them, so add them once from Obsidian: Settings > Community plugins > Browse > "Tasks" and "Templater", then point Templater's template folder at Templates/.

## Working the vault

- `.vault/config.yaml` declares your intent. Edit it freely, then run `onyx plan` to preview the effect and `onyx apply` to reconcile.
- `onyx add <module>` enables more modules, `onyx modules` lists what exists, and `onyx doctor` checks vault health read-only.
- Everything here works without any agent: templates are plain copies, views are plain files, and deleting `.claude/` costs convenience, never function.

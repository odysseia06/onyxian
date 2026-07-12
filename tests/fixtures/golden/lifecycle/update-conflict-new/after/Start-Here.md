---
type: start-here
status: active
tags: []
---

# Start here

Onyxian manages this vault. The engine regenerates this note when your module set changes; the moment you edit it, it is yours, and future versions will arrive beside it as `Start-Here.md.new` instead of overwriting you.

## Enabled modules

- **core** 0.1.0 — Synthetic core for the lifecycle goldens: one managed template and one seeded home note — enough surface to exercise the planner's mutation rows without coupling these fixtures to the real module library.
- **demo** 0.2.0 — Synthetic demo module for the lifecycle goldens: a folder, two managed templates (one retired in v2), and one seed (changed in v2 but never redelivered to existing vaults).

## Working the vault

- `.vault/config.yaml` declares your intent. Edit it freely, then run `onyxian plan` to preview the effect and `onyxian apply` to reconcile.
- `onyxian add <module>` enables more modules, `onyxian modules` lists what exists, and `onyxian doctor` checks vault health read-only.
- Everything here works without any agent: templates are plain copies, views are plain files, and deleting `.claude/` costs convenience, never function.
- See `Onyxian Assistant.md` for what your assistant can do and what to say.

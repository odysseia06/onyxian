---
type: start-here
status: active
tags: []
---

# Start here

Onyx manages this vault. The engine regenerates this note when your module set changes; the moment you edit it, it is yours, and future versions will arrive beside it as `Start-Here.md.new` instead of overwriting you.

## Enabled modules

- **core** 0.1.0 — The conventions every other module builds on: the Templates root, the vault home note, and the frontmatter and naming rules that humans and agents share.
- **daily-notes** 0.1.0 — Daily planning notes under a date hierarchy: task queries that bake in the day (due, scheduled, overdue, carry-over), a notes/journal skeleton, and an end-of-day close-out — the hub the other domains hang their day off.
- **fitness** 0.1.0 — A complete personal fitness system: training plans and logs, nutrition driven by a user-owned Strategy note (never hardcoded targets), bodyweight and measurement tracking with Base views, health and knowledge notes, and weekly/monthly reviews.

## First actions

- **core**: Open Home.md in Obsidian; it explains what was installed and how the safety contract works. The note is seeded: it is yours now, replace it freely.
- **daily-notes**: Create today's note from Templates/Daily/Daily Note.md; the daily-notes skill documents the folder layout. The task-query blocks need the community Tasks plugin to render and degrade to plain code blocks without it.
- **fitness**: Fill in Goals.md and Nutrition/Strategy.md before the first review cycle: the fitness-coach agent reads targets from the Strategy note and only from it, and will ask rather than invent numbers while it is empty.

## Working the vault

- `.vault/config.yaml` declares your intent. Edit it freely, then run `onyx plan` to preview the effect and `onyx apply` to reconcile.
- `onyx add <module>` enables more modules, `onyx modules` lists what exists, and `onyx doctor` checks vault health read-only.
- Everything here works without any agent: templates are plain copies, views are plain files, and deleting `.claude/` costs convenience, never function.

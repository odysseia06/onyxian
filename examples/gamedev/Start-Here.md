---
type: start-here
status: active
tags: []
---

# Start here

Onyxian manages this vault. The engine regenerates this note when your module set changes; the moment you edit it, it is yours, and future versions will arrive beside it as `Start-Here.md.new` instead of overwriting you.

## Enabled modules

- **core** 0.1.3 — The conventions every other module builds on: the Templates root, the vault home note, and the frontmatter and naming rules that humans and agents share.
- **daily-notes** 0.2.3 — Daily planning notes under a date hierarchy: task queries that bake in the day (due, scheduled, overdue, carry-over), a notes/journal skeleton, and an end-of-day close-out — the hub the other domains hang their day off.
- **projects-gamedev** 0.2.0 — Game projects as living wikis: a copy-per-game template subtree (overview, vision, roadmap, tech design, decision log, plus design/mechanics/world/ content/art/UI areas), with idea and mechanic templates for the incubation stage. Engine code stays a software project; this is the game.
- **projects-software** 0.2.4 — Per-project software engineering notes: a copy-per-project template subtree (overview, devlog, tasks, research), dated devlog entries, typed task and feature notes with a status-driven Base, and subsystem notes that grow with the architecture.

## First actions

- **core**: Open Home.md in Obsidian; it explains what was installed and how the safety contract works. The note is seeded: it is yours now, replace it freely. Onyxian's templates use the Tasks and Templater community plugins, and the vault enables both. With Obsidian open you can install them from the keyboard — `obsidian plugin:install id=obsidian-tasks-plugin enable` and `id=templater-obsidian` (run `obsidian plugins:restrict off` first on a fresh vault) — or add them from Settings > Community plugins > Browse. Then point Templater's template folder at Templates/. Your Claude Code agents will offer to do this for you, asking first.
- **daily-notes**: Create today's note from Templates/Daily/Daily Note.md; the daily-notes skill documents the folder layout. The task-query blocks need the community Tasks plugin to render and degrade to plain code blocks without it.
- **projects-gamedev**: Start a game by copying _Game-Template to a sibling named after it, then fill the numbered notes (the Overview links everything). Game ideas incubate as Game Idea notes before they earn a folder; mechanics get one Mechanic Note each. The Design-Board Base shows your games, incubating ideas, and mechanics; the game-steward agent operates all of it and never touches the _Game-Template master copies.
- **projects-software**: Start a project with `onyxian project new "<Name>"`: it scaffolds a sibling of _Project-Template with the Devlog/Tasks/Research/Assets folders and a dated Overview to fill in. Subsystem folders (renderer, runtime, api, ...) are yours to add per project as the architecture demands; the devlogs skill documents the rhythm.

## Working the vault

- `.vault/config.yaml` declares your intent. Edit it freely, then run `onyxian plan` to preview the effect and `onyxian apply` to reconcile.
- `onyxian add <module>` enables more modules, `onyxian modules` lists what exists, and `onyxian doctor` checks vault health read-only.
- Everything here works without any agent: templates are plain copies, views are plain files, and deleting `.claude/` costs convenience, never function.
- See `Onyxian Assistant.md` for what your assistant can do and what to say.

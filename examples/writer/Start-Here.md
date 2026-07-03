---
type: start-here
status: active
tags: []
---

# Start here

Onyxian manages this vault. The engine regenerates this note when your module set changes; the moment you edit it, it is yours, and future versions will arrive beside it as `Start-Here.md.new` instead of overwriting you.

## Enabled modules

- **core** 0.1.3 — The conventions every other module builds on: the Templates root, the vault home note, and the frontmatter and naming rules that humans and agents share.
- **daily-notes** 0.2.2 — Daily planning notes under a date hierarchy: task queries that bake in the day (due, scheduled, overdue, carry-over), a notes/journal skeleton, and an end-of-day close-out — the hub the other domains hang their day off.
- **reading** 0.2.1 — An Inbox -> Articles -> Evergreen reading pipeline: quick captures land in the inbox, kept pieces become article notes, and ideas worth keeping forever get distilled into evergreen notes — with web clipping via the defuddle skill and a status-driven Base view over the whole flow.
- **writing** 0.2.0 — Editorial blog workflow: ideas mature into drafts and published posts, series tie posts together, research notes feed them — with a status-driven pipeline Base and an editorial calendar. Site implementation stays a software project; this module is the words.

## First actions

- **core**: Open Home.md in Obsidian; it explains what was installed and how the safety contract works. The note is seeded: it is yours now, replace it freely. Onyxian's templates use the Tasks and Templater community plugins, and the vault enables both. With Obsidian open you can install them from the keyboard — `obsidian plugin:install id=obsidian-tasks-plugin enable` and `id=templater-obsidian` (run `obsidian plugins:restrict off` first on a fresh vault) — or add them from Settings > Community plugins > Browse. Then point Templater's template folder at Templates/. Your Claude Code agents will offer to do this for you, asking first.
- **daily-notes**: Create today's note from Templates/Daily/Daily Note.md; the daily-notes skill documents the folder layout. The task-query blocks need the community Tasks plugin to render and degrade to plain code blocks without it.
- **reading**: Capture into Inbox with the Quick Capture template (the defuddle skill clips web pages cleanly); triage on your own rhythm — keep into Articles, distill into Evergreen. The reading-triage skill documents the flow.
- **writing**: Capture post ideas with the Blog Idea template; promote to Drafts when the thesis is real, to Published when it ships (record the URL). The pipeline Base and the Content-Backlog note show the flow end to end.

## Working the vault

- `.vault/config.yaml` declares your intent. Edit it freely, then run `onyxian plan` to preview the effect and `onyxian apply` to reconcile.
- `onyxian add <module>` enables more modules, `onyxian modules` lists what exists, and `onyxian doctor` checks vault health read-only.
- Everything here works without any agent: templates are plain copies, views are plain files, and deleting `.claude/` costs convenience, never function.
- See `Onyxian Assistant.md` for what your assistant can do and what to say.

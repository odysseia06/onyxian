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
- **reading** 0.1.0 — An Inbox -> Articles -> Evergreen reading pipeline: quick captures land in the inbox, kept pieces become article notes, and ideas worth keeping forever get distilled into evergreen notes — with web clipping via the defuddle skill and a status-driven Base view over the whole flow.
- **writing** 0.1.0 — Editorial blog workflow: ideas mature into drafts and published posts, series tie posts together, research notes feed them — with a status-driven pipeline Base and an editorial calendar. Site implementation stays a software project; this module is the words.

## First actions

- **core**: Open Home.md in Obsidian; it explains what was installed and how the safety contract works. The note is seeded: it is yours now, replace it freely. Onyx's templates use the Tasks and Templater community plugins, and the vault enables both. Onyx can enable plugins but cannot install them, so add them once from Obsidian: Settings > Community plugins > Browse > "Tasks" and "Templater", then point Templater's template folder at Templates/.
- **daily-notes**: Create today's note from Templates/Daily/Daily Note.md; the daily-notes skill documents the folder layout. The task-query blocks need the community Tasks plugin to render and degrade to plain code blocks without it.
- **reading**: Capture into Inbox with the Quick Capture template (the defuddle skill clips web pages cleanly); triage on your own rhythm — keep into Articles, distill into Evergreen. The reading-triage skill documents the flow.
- **writing**: Capture post ideas with the Blog Idea template; promote to Drafts when the thesis is real, to Published when it ships (record the URL). The pipeline Base and the Content-Backlog note show the flow end to end.

## Working the vault

- `.vault/config.yaml` declares your intent. Edit it freely, then run `onyx plan` to preview the effect and `onyx apply` to reconcile.
- `onyx add <module>` enables more modules, `onyx modules` lists what exists, and `onyx doctor` checks vault health read-only.
- Everything here works without any agent: templates are plain copies, views are plain files, and deleting `.claude/` costs convenience, never function.

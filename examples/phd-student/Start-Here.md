---
type: start-here
status: active
tags: []
---

# Start here

Onyx manages this vault. The engine regenerates this note when your module set changes; the moment you edit it, it is yours, and future versions will arrive beside it as `Start-Here.md.new` instead of overwriting you.

## Enabled modules

- **core** 0.1.0 — The conventions every other module builds on: the Templates root, the vault home note, and the frontmatter and naming rules that humans and agents share.
- **academic** 0.2.0 — Course and exam management: a copy-per-course template subtree (overview, syllabus, schedule, lectures, assignments, exam prep with a study Base), plus a free-form additional-notes area for concepts and definitions.
- **daily-notes** 0.2.0 — Daily planning notes under a date hierarchy: task queries that bake in the day (due, scheduled, overdue, carry-over), a notes/journal skeleton, and an end-of-day close-out — the hub the other domains hang their day off.
- **reading** 0.2.0 — An Inbox -> Articles -> Evergreen reading pipeline: quick captures land in the inbox, kept pieces become article notes, and ideas worth keeping forever get distilled into evergreen notes — with web clipping via the defuddle skill and a status-driven Base view over the whole flow.
- **research** 0.2.0 — A typed research-paper pipeline: PDFs and summaries named by citation key, seven paper-type templates with type-specific analysis sections, a multi-view Paper Library Base over rich frontmatter, plus topic notes, literature maps, open questions, and reading lists.

## First actions

- **core**: Open Home.md in Obsidian; it explains what was installed and how the safety contract works. The note is seeded: it is yours now, replace it freely. Onyx's templates use the Tasks and Templater community plugins, and the vault enables both. With Obsidian open you can install them from the keyboard — `obsidian plugin:install id=obsidian-tasks-plugin enable` and `id=templater-obsidian` (run `obsidian plugins:restrict off` first on a fresh vault) — or add them from Settings > Community plugins > Browse. Then point Templater's template folder at Templates/. Your Claude Code agents will offer to do this for you, asking first.
- **academic**: Start a course by copying the whole _Course-Template folder to "<CODE> <Course Name>" beside it, then fill the Overview/Syllabus/Schedule notes and point the Exam-Study.base folder filter at the new course (the exam-prep skill walks through it).
- **daily-notes**: Create today's note from Templates/Daily/Daily Note.md; the daily-notes skill documents the folder layout. The task-query blocks need the community Tasks plugin to render and degrade to plain code blocks without it.
- **reading**: Capture into Inbox with the Quick Capture template (the defuddle skill clips web pages cleanly); triage on your own rhythm — keep into Articles, distill into Evergreen. The reading-triage skill documents the flow.
- **research**: Drop a PDF into Paper-PDFs named "CitationKey - Short Title.pdf", then create its summary from the matching typed template (or the interactive Paper Summary template, which asks and renames for you). The paper-pipeline skill documents the whole flow.

## Working the vault

- `.vault/config.yaml` declares your intent. Edit it freely, then run `onyx plan` to preview the effect and `onyx apply` to reconcile.
- `onyx add <module>` enables more modules, `onyx modules` lists what exists, and `onyx doctor` checks vault health read-only.
- Everything here works without any agent: templates are plain copies, views are plain files, and deleting `.claude/` costs convenience, never function.

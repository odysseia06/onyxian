---
name: editorial-pipeline
description: The writing module's editorial conventions - idea capture, draft and published status truth, backlog and calendar upkeep, and the boundary between words and website code.
---

# editorial-pipeline

Read the resolved root from `.vault/config.yaml` under `modules.writing.vars.root` (called `<root>` below). The pipeline stages are folders and statuses: `<root>/Ideas` (`status: idea`), `<root>/Drafts` (`status: draft`), and `<root>/Published` (`status: published`). The Blog-Pipeline Base reads frontmatter, so accurate status, topic, series, slug, and published_url fields are the source of truth.

## Capture

- Use the Blog Idea template for new ideas: one thesis or angle per note, `type: blog-idea`, `status: idea`, `topic` filled when known, and `date` set to the capture date.
- Put source material in `<root>/Research` with the Blog Research Note template, then wikilink it from the idea or draft. Research supports posts; it is not the post itself.
- Keep `Content-Backlog.md` as a coarse queue of wikilinks. Do not duplicate the full note content there.

## Promotion

- Idea to draft: promote only when the thesis is real enough to write. Change `type` to `blog-draft`, `status` to `draft`, add `series` and `slug` when known, and move the note from `Ideas/` to `Drafts/` only after the user confirms the move.
- Draft to published: promote only after the post ships. Change `type` to `blog-published`, `status` to `published`, set `published_url`, and move the note from `Drafts/` to `Published/` only after the user confirms the move.
- Never move, delete, or rename posts silently. A promotion is a proposed batch: explain the destination and metadata edits, then wait for confirmation.

## Calendar and backlog

- Publishing rhythm and target dates live only in `<root>/Editorial-Calendar.md`. If it is empty, ask the user to fill it or give the next target; never invent dates.
- "What should I write next?" means read Ideas, Drafts, Content-Backlog.md, and Editorial-Calendar.md, then suggest the smallest useful next action.
- Stale drafts are surfaced by the Blog-Pipeline Base's Drafting view, which sorts oldest first. Recommend attention; do not change status just because a draft is old.

## Boundary

Editorial work lives in this module. The website implementation is a software project: link to it by wikilink when relevant, but keep code tasks, deployment notes, and implementation decisions in the projects-software module.

---
name: reading-triage
description: The reading pipeline's conventions — clipping web content with defuddle, inbox capture, triage into article notes, evergreen distillation, and linking into other domains. Use for any task touching captures, articles, or evergreen notes.
---

# reading-triage

Read the resolved root from `.vault/config.yaml` under `modules.reading.vars.root` (called `<root>` below). The stages are folders AND statuses: `<root>/Inbox` (`status: inbox`), `<root>/Articles` (`status: kept`), `<root>/Evergreen` (tag `reading/evergreen`). The Reading-Pipeline Base reads the frontmatter, so accurate statuses are the pipeline.

## Capturing

- Web content: clip with the defuddle skill (clean markdown, no nav junk), then wrap it in a Quick Capture note in `<root>/Inbox` — `source`, `url`, and "What Caught My Attention" filled. The clip body goes under Rough Notes, trimmed to what matters.
- One idea per capture. A capture is a bookmark with a pulse, not an archive.

## Triage

- **Keep:** the piece earns a real Article Note in `<root>/Articles` — thesis, key points, your take. Mark the capture's status `kept` (or fold the capture into the article note and propose retiring it).
- **Distill:** an idea that should outlive its source becomes an Evergreen Note in `<root>/Evergreen` — written in your own words, titled as a claim, linking the supporting articles/captures. Evergreen notes are about ideas, not sources.
- **Let die:** stale inbox items are the user's to prune; never delete them yourself, and never move files between stage folders without the user confirming the batch.

## Linking outward

A reading note that serves a project, course, or training plan gets wikilinked from that domain's notes — link, don't duplicate. When a capture is clearly domain work in disguise (a paper → research pipeline; a repo → projects), say so and propose the right pipeline instead of processing it here.

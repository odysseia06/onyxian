---
name: paper-pipeline
description: The research module's paper conventions — citation-key naming, the seven paper types, the status lifecycle, rich frontmatter, and how summaries, topic notes, and reading lists connect. Use for any task touching papers, summaries, or the research pipeline.
---

# paper-pipeline

Read the resolved domain root from `.vault/config.yaml` under `modules.research.vars.root` (called `<root>` below).

## Naming — exact, no exceptions

Paper summaries and PDFs share one name: `CitationKey - Short Title` (e.g. `Komlo2024 - FROST.md` beside `Komlo2024 - FROST.pdf`). The citation key is FirstAuthorYear. Never organize papers into subfolders — they live flat in `<root>/Paper-Summaries` and `<root>/Paper-PDFs`; metadata and the Paper Library Base do the organizing.

## Types — exactly these seven

`attack`, `construction`, `engineering`, `foundations`, `framework`, `protocol`, `survey`. Each has a typed template (Templates folder, under `Research/`) whose middle sections ask the questions that matter for that kind of paper; the interactive `Paper Summary` template prompts for everything and renames the note itself (needs Templater). If a paper genuinely fits none, ask the user — do not invent a type.

## Statuses — exactly these four

`to-read` → `reading` → `summarized` → `revisiting` (when returning to a summarized paper). Set `date_summarized` when the summary is filled; the Base's views (To Read, Reading Now, Summarized, Revisiting, By Type, High Priority) are driven entirely by this frontmatter, so keeping it accurate IS maintaining the library.

## Frontmatter

Papers carry the pipeline's own rich schema (title, aliases, authors, year, venue, type, topics, tags incl. `paper`, status, priority, rating, citation_key, pdf, doi, url, date_added, date_summarized, compares_to, improves_on, related_work, summary_template, personal_take). Preserve it exactly — for paper notes this schema outranks the vault's generic core keys, and the `type` field means paper type, with `tags: paper` marking the note class. `personal_take` is a one-liner that surfaces in Base views; `compares_to` / `improves_on` / `related_work` hold citation-key wikilinks. When venue or year is not stated in the PDF itself, check the paper's landing page (its DOI, ePrint, or arXiv URL) before recording a caveat — preprint landing pages usually list where a paper was published.

## Beyond summaries

- Topic notes (`<root>/Topic-Notes`) braid threads across papers — one note per research thread, linking the relevant summaries.
- Reading lists (`<root>/Reading-Lists`) are ordered wikilink runs assembled for a purpose (a deep dive, a course, a review); annotate why each paper is on the list.
- Open questions (`<root>/Open-Questions`) get one note each, linking the papers that raise or partially answer them.
- Literature maps (`<root>/Literature-Maps`) are canvases or notes mapping an area; build them from summaries, not from scratch.

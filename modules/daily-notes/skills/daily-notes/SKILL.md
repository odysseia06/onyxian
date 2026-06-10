---
name: daily-notes
description: How daily notes work in this vault — where today's note lives, how to create it, how task carry-over and the end-of-day close-out work. Use whenever creating, finding, or updating a daily note.
---

# Daily notes

The vault's daily-notes module follows one convention with one configurable choice. Read the resolved values from `.vault/config.yaml` under `modules.daily-notes.vars` (`root` and `granularity`) before creating anything.

## Where today's note lives

- The filename is **always** `YYYY-MM-DD.md` — never drop the year just because a folder already carries it.
- The folder depends on `granularity`: `YYYY/MM` → `<root>/2026/06/2026-06-10.md` (zero-padded month); `YYYY` → `<root>/2026/2026-06-10.md`; `flat` → `<root>/2026-06-10.md`.
- Create missing year/month folders as needed; the engine scaffolds only the root.

## Creating the note

- Instantiate `Daily Note.md` from the vault's Templates folder (under `Daily/`). With Templater installed the date placeholders and the task-query macro fill themselves; without it, replace each `<% ... %>` with today's date by hand and the `tasks` blocks render once the Tasks plugin is installed.
- The baked-in queries give the day its structure: Due Today, Scheduled Today, Overdue, Carry-over (everything unfinished in the daily-notes tree), Completed Today.

## Working the day

- New tasks land under `## Tasks` with Tasks-plugin metadata (due `📅`, scheduled `⏳`, created `➕`) so the queries pick them up.
- Carry-over is query-driven, not copy-driven: unfinished tasks from previous days surface automatically — do not duplicate task lines forward by hand. Complete them where they live.
- Frontmatter `status` is `open` for the current day; flip it to `closed` during the end-of-day review.

## End of day

- Check off what got done, reschedule what must move (edit the task's own date), write the `## Journal` entry, set `status: closed`.

## Integrations

- When the fitness module is enabled, its fitness-review skill defines an `## Intake` section and an optional `weight:` frontmatter key for daily notes; that convention is owned there, not here.
- Other modules link into the day with wikilinks; the daily note is the hub, not the archive — substance belongs in domain notes.

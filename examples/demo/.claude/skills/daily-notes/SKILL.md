---
name: daily-notes
description: How daily notes work in this vault — where today's note lives, the safe morning-scaffold procedure for setting up today's note, how task carry-over works, and the end-of-day close-out. Use whenever setting up, creating, finding, or updating today's daily note.
---

# Daily notes

The vault's daily-notes module follows one convention with one configurable choice. Read the resolved values from `.vault/config.yaml` under `modules.daily-notes.vars` (`root` and `granularity`) before creating anything.

## Where today's note lives

- The filename is **always** `YYYY-MM-DD.md` — never drop the year just because a folder already carries it.
- The folder depends on `granularity`: `YYYY/MM` → `<root>/2026/06/2026-06-10.md` (zero-padded month); `YYYY` → `<root>/2026/2026-06-10.md`; `flat` → `<root>/2026-06-10.md`.
- Create missing year/month folders as needed; the engine scaffolds only the root.

## Creating the note (the morning scaffold)

This is the deterministic morning procedure. It is additive and idempotent, and it records whether today's note already existed *before* it touches anything — so it can never confuse "I just created it" with "it was already here." Run it with Obsidian open.

1. Reach the live vault: `obsidian vault info=name`. If it returns nothing, Obsidian is not running or the CLI is not enabled — say so and stop. Never fall back to editing files on disk.
2. Compute the path: `obsidian daily:path`, and use what it returns; never hand-compute the date folder. `daily:path` must only compute a path — if you cannot confirm it neither creates nor opens the note, derive the path yourself from the convention above (`<root>` + the granularity folders + `YYYY-MM-DD.md`) so that nothing before the existence check can create the note.
3. Establish existence read-only, before anything can mutate: check whether a file already exists at that path with a listing (`obsidian files`, or `obsidian file` against the path) — never with `obsidian daily:read`, because opening the daily note can create it. Record now whether it existed; because nothing so far creates the note, that record is the true pre-run state.
4. If it did not exist, create it natively so Obsidian and Templater render the template: `obsidian command id=daily-notes` (creates and opens today's note from the configured Daily Note template), then `obsidian command id=templater-obsidian:replace-in-file-templater` (Templater fills the `<% ... %>` and `<%* ... %>` macros).
5. If it did exist, read it now with `obsidian daily:read` — safe, because the note is known present. If no `<% ... %>` remain, it is already set up and you are done. If raw macros linger, resolve them with `obsidian command id=templater-obsidian:replace-in-file-templater` only.
6. Verify and report the truth: `obsidian daily:read` and confirm no `<% ... %>` remain. Report only what step 3 recorded — "created today's note" or "today's note was already set up." Never claim a note already existed, or that you did or did not overwrite it, unless step 3's read-only check established it.

The baked-in queries give the day its structure: Due Today, Scheduled Today, Overdue, Carry-over (everything unfinished in the daily-notes tree), Captured, Completed Today.

If Templater is unavailable and macros stay literal, resolve the note from the template you already have rather than re-authoring its queries: read the installed `Daily Note.md` under the Templates `Daily/` folder, drop the `<%* ... %>` wrapper, and write out exactly what its string-building produces — substituting today's date for the `today` value and emitting each `### ` task-query block as the template assembles it. The installed template already carries real folder names (Onyx resolved every `{{ ... }}` at apply time), so no placeholder substitution is needed. Write the result with `obsidian create path="<the path from step 2>" content="..."`, and only when the note is missing; never overwrite an existing day.

## Working the day

- New tasks land under `## Tasks` with Tasks-plugin metadata (due `📅`, scheduled `⏳`, created `➕`) so the queries pick them up.
- Carry-over is query-driven, not copy-driven: unfinished tasks from previous days surface automatically — do not duplicate task lines forward by hand, and do not read a past daily note directly to take stock of carry-over. The Carry-over query already surfaces every unfinished task in the tree, and `daily:read` only ever reads today's note anyway. Complete tasks where they live.
- Frontmatter `status` is `open` for the current day; flip it to `closed` during the end-of-day review.

## End of day

- Check off what got done, reschedule what must move (edit the task's own date), write the `## Journal` entry, set `status: closed`.

## Integrations

- When the fitness module is enabled, its fitness-review skill defines an `## Intake` section and an optional `weight:` frontmatter key for daily notes; that convention is owned there, not here.
- Other modules link into the day with wikilinks; the daily note is the hub, not the archive — substance belongs in domain notes.

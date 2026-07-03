---
name: practice-loop
description: The music module's working conventions: Goals-note-driven practice targets, truthful session logs, composition capture before projects, and proposal-only routine changes.
---

# practice-loop

The music module is Goals-note-driven: practice priorities, target cadence, repertoire focus, constraints, and creative direction live in the user's own `<root>/Goals.md`, never in instructions. Read the resolved folder root from `.vault/config.yaml` under `modules.music.vars.root` (called `<root>` below).

## The one iron rule

Practice targets and priorities come from `<root>/Goals.md` and only from there. If Goals.md is empty, stale, or contradictory, ask the user to fill or clarify it; never invent session counts, practice durations, repertoire priorities, or creative deadlines.

## Session logging

- Log each practice session as one Practice Log note under `<root>/Practice/Logs` using the Practice Log template.
- Keep frontmatter truthful: `type: practice-log`, `status: logged`, `tags` includes `music/log`, `date` is the session date, `duration` is the actual duration, and `focus` is the session's main focus.
- `Practice/Practice-Log.base` is the overview. It reads `music/log` notes and shows `date`, `duration`, and `focus`, so do not leave those fields vague when the user supplied them.
- Corrections are append-only. If a previous log was wrong, add a correction note or a dated correction section rather than rewriting history silently.

## Routine proposals

- A practice routine is a proposal over the user's goals and constraints, not a hidden plan rewrite.
- When drafting a routine, cite the Goals.md priorities it responds to, list assumptions explicitly, and put suggested changes in a proposed-next-session or routine note for the user to accept.
- If Goals.md does not say what matters most right now, ask before ranking technique, repertoire, theory, ear training, production, or composition work.

## Composition capture

- Loose ideas live in `<root>/Composition/**` first. Use the Composition Idea template for song sketches, melodic fragments, lyric starts, chord-progression ideas, and arrangement concepts.
- A piece earns a folder under `<root>/Projects/` only when the user decides it has become serious. Treat that as a promotion: propose the new project folder and template copy, then wait for confirmation.
- Keep project promotion separate from practice logging. A session can link to a composition idea or project note, but it should not silently restructure the composition shelf.

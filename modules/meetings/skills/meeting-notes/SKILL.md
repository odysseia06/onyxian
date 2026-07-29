---
name: meeting-notes
description: The meetings conventions — dated meeting notes from the typed templates, the scheduled/held/closed lifecycle behind the Meeting-Board views, person notes with next-time agendas, decision capture, and follow-up discipline. Use for any task touching meetings, people notes, or 1:1 preparation.
---

# meeting-notes

Read the resolved root from `.vault/config.yaml` under `modules.meetings.vars.root` (called `<root>` below).

## Structure

- Meeting notes live directly in `<root>`, named `YYYY-MM-DD <topic>` (for a 1:1: `YYYY-MM-DD <name> 1-1`), created from the Meeting Note, One-on-One, or Decision Meeting template.
- Person notes live in `<root>/People`, one per person, named after the person, from the Person template.
- `00 Dashboard.md` at the root is the user's home for the week; `Meeting-Board.base` and `People-Directory.base` are the live views.

## Meetings

- Frontmatter is the record: `date` is the meeting date, `attendees` holds wikilinks to person notes, `project` optionally links the relevant project note.
- Status lifecycle: `scheduled` → `held` → `closed`. A meeting is `held` once it happened but action items remain open; `closed` when every action item is resolved. The Meeting-Board views read these statuses: Upcoming is `scheduled`, Open Follow-Ups is `held`, Recent is `closed`.
- Action items are Tasks-plugin checkboxes under `## Action Items`, one owner each; carry unfinished ones forward explicitly (to the owner's person note or a daily note), never silently.
- Meeting notes are the record of what happened — corrections are new dated bullets, never rewrites.

## People

- One note per person: `role` and `org` in frontmatter, working context under `## About`. Status lifecycle: `active` → `former` — people are never deleted, only marked former.
- `## Next Time` is the running 1:1 agenda: topics land there between meetings and move into the next One-on-One note's agenda when it is created.

## Decision capture

- A decision-heavy meeting gets the Decision Meeting template: the question, the options considered, the decision, and the why. A decision without its why is a future archaeology dig.
- Small decisions inside an ordinary meeting get a dated bullet under `## Decisions`.

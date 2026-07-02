---
name: task-capture
description: Capture a task from natural language into this Obsidian vault — parse the text, date, and priority; route it to the right note; format it for the Tasks plugin; and append it. Use whenever the user wants to add, capture, jot, or remember a task ("add a task to…", "remind me to…", "I need to fix X by Friday", "check this later").
---

# Task capture

Turn a spoken or typed intent into a correctly formatted Tasks-plugin line in the right note, additively. Read the `vault-operations` skill first — every write here obeys that contract — and `obsidian-tasks` for the exact Tasks-plugin syntax.

## The flow

1. **Parse** the request into: the task text, an optional date and its kind (due vs scheduled), an optional priority, and any destination the user named.
2. **Route** — decide the home note (see Routing).
3. **Format** the Tasks line (see The line).
4. **Look, then append** — read the home note's `## Tasks` section first; if an equivalent task is already there, stop (do not duplicate). Otherwise append the line with `obsidian daily:append` (the daily note) or `obsidian append file="<note>"` (a routed note), creating a `## Tasks` heading if the note has none.
5. **Confirm** in one line: what you filed, where, and where it will show — e.g. "→ `Fix the auth bug 📅 2026-06-20` in Projects/Software/Onyx; shows on Friday's daily note."

## The line

Build `- [ ] <text>` plus metadata, using the Tasks-plugin emoji (see `obsidian-tasks`):

- Always stamp the created date: `➕ <today>` (today = the system date).
- Dates, by the user's words:
  - "by / due / deadline / before <date>" → `📅 <date>` (due)
  - "on / work on / start / look at <date>" → `⏳ <date>` (scheduled)
  - no date given → add the tag `#captured` (this surfaces it on the daily note until handled)
- Resolve natural-language dates to `YYYY-MM-DD`, anchored on today ("Friday" → the next Friday's date).
- Priority only if the user signalled it (`🔺` highest, `⏫` high, `🔼` medium, `🔽` low). Extra `#tags` only if stated.
- Never invent a date the user did not give — an undated request stays undated, plus `#captured`.

## Routing

Pick the home note in this order:

1. **Explicit** — the user named a place ("the Onyx task", "in my fitness notes"). Use it.
2. **Active note** — the note open in Obsidian (`obsidian file` reports the active file) is a strong default home when the task plainly belongs to it.
3. **Inferred** — match the task's subject to an enabled domain or a known project.
4. **Standalone / unclear / "just remind me"** → today's daily note (`obsidian daily:append`).

Confirm the destination in your one-line reply. **Ask only when the home is genuinely ambiguous** — never guess between two plausible projects; that is an escalation (vault-operations), not initiative.

## Why this is enough

You rarely need to copy a task onto the daily note. A dated task already appears there through the daily note's Due / Scheduled / Overdue queries (they scan the whole vault). An undated capture appears through the daily note's `### Captured` query because of its `#captured` tag. So: file it once, in the right place; the daily note surfaces it.

## Out of scope

Recurring tasks (`🔁`), rescheduling or completing existing tasks (that is the daily-planner's job), and capturing several tasks in one breath. Do one clean capture; escalate anything beyond it.

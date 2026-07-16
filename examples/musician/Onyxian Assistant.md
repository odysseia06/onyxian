---
type: assistant-guide
status: active
tags: []
---

# What your assistant can do

This vault works as plain files — none of this is required. With Claude Code open, the agents below operate the vault for you: say what you want and the right one does the work, additively and within its lane. Onyxian regenerates this note as you enable or remove modules.

## Agents

### daily-planner
Plans and maintains the day — runs the morning scaffold, gives a triage briefing that proposes (never silently makes) changes to your open and overdue tasks across the vault, and walks the end-of-day close-out.
Say e.g.: "plan my day" · "what's on today / triage my tasks" · "close out the day"
Where its work lands: `Daily-Notes`

### practice-coach
Logs practice sessions, captures composition ideas, and reviews practice trends against the user's own Music Goals note. Goals-note-driven; it never invents priorities or targets.
Say e.g.: "log today's practice session" · "how's my practice trending" · "capture this song idea" · "draft me a practice routine"
Where its work lands: `Music/Practice`, `Music/Composition`

## Skills under the hood

Instruction packages in `.claude/skills/` the agents lean on. You never invoke these by name — they are listed so you know what is there.

- **vault-bootstrap** — Interview wizard that sets up a new Onyxian vault (init) or brings an existing vault under management (adopt) — asks the questions, builds an answers file, shows the engine's plan verbatim, and applies only after the user confirms. Use when the user wants to create an Onyxian vault, adopt an existing Obsidian vault, or enable modules through a guided flow.
- **vault-conventions** — The frontmatter, naming, and writing rules any agent must follow when creating or editing notes in an Onyxian-managed vault. Read this before writing any note, template, or generated text into the vault.
- **obsidian-tasks** — Create and query tasks using the Tasks plugin syntax including due dates, recurrence, priorities, and task queries. Use when the user mentions Tasks plugin, recurring tasks, task queries, or advanced task management in Obsidian.
- **obsidian-templater** — Create dynamic templates using Templater's template syntax and tp.* functions. Use when the user mentions Templater, dynamic templates, tp.date, tp.file, template commands, or automated note creation.
- **vault-operations** — How an agent safely operates a live Obsidian vault through the obsidian CLI — additive writes, least privilege, look-before-you-write, and when to escalate. Read this before running any obsidian command that changes the vault.
- **daily-notes** — How daily notes work in this vault — where today's note lives, the safe morning-scaffold procedure for setting up today's note, how task carry-over works, and the end-of-day close-out. Use whenever setting up, creating, finding, or updating today's daily note.
- **task-capture** — Capture a task from natural language into this Obsidian vault — parse the text, date, and priority; route it to the right note; format it for the Tasks plugin; and append it. Use whenever the user wants to add, capture, jot, or remember a task ("add a task to…", "remind me to…", "I need to fix X by Friday", "check this later").
- **practice-loop** — The music module's working conventions — Goals-note-driven practice targets, truthful session logs, composition capture before projects, and proposal-only routine changes. Use for any task touching practice logs, routines, or composition ideas.

## If you'd rather not use AI

Delete `.claude/` and everything here still works — templates are plain copies, views are plain files. See `Start-Here.md` for the no-AI tour.

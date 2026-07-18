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

### game-steward
Captures game ideas and mechanic notes, appends dated devlog entries, records decisions with their why, and starts new games as additive copies of the template subtree — the master copies stay untouched.
Say e.g.: "capture this game idea" · "log today's devlog for <game>" · "we decided … (record it)" · "start a new game project"
Where its work lands: `Projects/Game-Dev`

### project-steward
Captures devlogs and decisions, maintains task and feature notes, and keeps subsystem notes current across software projects — append-only history, wikilink-first structure.
Say e.g.: "log this session / devlog" · "we decided … (record a decision)" · "mark … done / shipped / blocked" · "start a new project"
Where its work lands: `Projects/Software`

## Skills under the hood

Instruction packages in `.claude/skills/` the agents lean on. You never invoke these by name — they are listed so you know what is there.

- **vault-bootstrap** — Interview wizard that sets up a new Onyxian vault (init) or brings an existing vault under management (adopt) — asks the questions, builds an answers file, shows the engine's plan verbatim, and applies only after the user confirms. Use when the user wants to create an Onyxian vault, adopt an existing Obsidian vault, or enable modules through a guided flow.
- **vault-conventions** — The frontmatter, naming, and writing rules any agent must follow when creating or editing notes in an Onyxian-managed vault. Read this before writing any note, template, or generated text into the vault.
- **obsidian-tasks** — Create and query tasks using the Tasks plugin syntax including due dates, recurrence, priorities, and task queries. Use when the user mentions Tasks plugin, recurring tasks, task queries, or advanced task management in Obsidian.
- **obsidian-templater** — Create dynamic templates using Templater's template syntax and tp.* functions. Use when the user mentions Templater, dynamic templates, tp.date, tp.file, template commands, or automated note creation.
- **vault-operations** — How an agent safely operates a live Obsidian vault through the obsidian CLI — additive writes, least privilege, look-before-you-write, and when to escalate. Read this before running any obsidian command that changes the vault.
- **daily-notes** — How daily notes work in this vault — where today's note lives, the safe morning-scaffold procedure for setting up today's note, how task carry-over works, and the end-of-day close-out. Use whenever setting up, creating, finding, or updating today's daily note.
- **task-capture** — Capture a task from natural language into this Obsidian vault — parse the text, date, and priority; route it to the right note; format it for the Tasks plugin; and append it. Use whenever the user wants to add, capture, jot, or remember a task ("add a task to…", "remind me to…", "I need to fix X by Friday", "check this later").
- **game-wiki** — The gamedev module's working conventions — idea incubation before folders, copy-per-game structure from untouchable master copies, one truthful-status note per mechanic, append-only devlogs, decisions with their why, and the engine-code boundary. Use for any task touching game ideas, mechanics, devlogs, or game project notes.
- **devlogs** — The software-projects conventions — per-project folders from the template subtree, dated devlog entries, typed task and feature notes, decision capture, and subsystem notes. Use for any task touching project notes, devlogs, or project task tracking.

## If you'd rather not use AI

Delete `.claude/` and everything here still works — templates are plain copies, views are plain files. See `Start-Here.md` for the no-AI tour.

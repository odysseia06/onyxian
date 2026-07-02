---
type: assistant-guide
status: active
tags: []
---

# What your assistant can do

This vault works as plain files — none of this is required. With Claude Code open, the agents below operate the vault for you: say what you want and the right one does the work, additively and within its lane. Onyxian regenerates this note as you enable or remove modules.

## Agents

### study-coach
Builds and maintains study plans and exam-prep material from syllabi, schedules, lecture notes, and deadlines — including spaced-repetition review scheduling into each course's Exam-Prep folder.
Say e.g.: "build a study plan from this syllabus" · "what's due this week" · "schedule exam review" · "track my progress through this chapter"
Where its work lands: `Academic/Courses/*/Exam-Prep`, `Academic/Courses/*/Notes`

### daily-planner
Plans and maintains the day — runs the morning scaffold, gives a triage briefing that proposes (never silently makes) changes to your open and overdue tasks across the vault, and walks the end-of-day close-out.
Say e.g.: "plan my day" · "what's on today / triage my tasks" · "close out the day"
Where its work lands: `Daily-Notes`

### fitness-coach
Analyzes training logs, intake, and tracking data against the user's own Strategy and Goals notes, and produces the periodic fitness reviews. Strategy-note-driven — it never invents targets.
Say e.g.: "run my fitness review" · "how's my training trending" · "check my adherence this week" · "review my progress against my goals"
Where its work lands: `Fitness/Reviews`, `Fitness/Tracking`

### oss-scout
Tends the OSS watchlist and contribution notes — staleness sweeps, contribution-candidate shortlists, promote/demote proposals under the one-copy rule.
Say e.g.: "track this repo" · "sweep my watchlist for staleness" · "what could I contribute to" · "log a contribution"
Where its work lands: `Projects/Software/OSS-Watchlist`, `Projects/Software/OSS-Contributing`

### project-steward
Captures devlogs and decisions, maintains task and feature notes, and keeps subsystem notes current across software projects — append-only history, wikilink-first structure.
Say e.g.: "log this session / devlog" · "we decided … (record a decision)" · "mark … done / shipped / blocked" · "start a new project"
Where its work lands: `Projects/Software`

### reading-triager
Clips web content into clean inbox captures, triages the inbox into article notes, drafts evergreen distillations, and keeps pipeline statuses truthful. Proposes promotions; never moves or deletes the user's notes on its own.
Say e.g.: "clip this page / save this article" · "triage my reading inbox" · "distill this into an evergreen note" · "what should I read next"
Where its work lands: `Reading`

### research-librarian
Runs paper intake and library upkeep — typed summaries from PDFs, citation-key naming, status and frontmatter hygiene, topic-note and reading-list linking. Never reorganizes the library into folders.
Say e.g.: "summarize this paper" · "I dropped a PDF in the papers folder" · "tidy the paper library" · "link this paper to related work"
Where its work lands: `Academic/Research/Paper-Summaries`, `Academic/Research/Topic-Notes`, `Academic/Research/Reading-Lists`, `Academic/Research/Literature-Maps`, `Academic/Research/Open-Questions`

## Skills under the hood

Instruction packages in `.claude/skills/` the agents lean on. You never invoke these by name — they are listed so you know what is there.

- **vault-bootstrap** — Interview wizard that sets up a new Onyxian vault (init) or brings an existing vault under management (adopt) — asks the questions, builds an answers file, shows the engine's plan verbatim, and applies only after the user confirms. Use when the user wants to create an Onyxian vault, adopt an existing Obsidian vault, or enable modules through a guided flow.
- **vault-conventions** — The frontmatter, naming, and writing rules any agent must follow when creating or editing notes in an Onyxian-managed vault. Read this before writing any note, template, or generated text into the vault.
- **obsidian-tasks** — Create and query tasks using the Tasks plugin syntax including due dates, recurrence, priorities, and task queries. Use when the user mentions Tasks plugin, recurring tasks, task queries, or advanced task management in Obsidian.
- **obsidian-templater** — Create dynamic templates using Templater's template syntax and tp.* functions. Use when the user mentions Templater, dynamic templates, tp.date, tp.file, template commands, or automated note creation.
- **vault-operations** — How an agent safely operates a live Obsidian vault through the obsidian CLI — additive writes, least privilege, look-before-you-write, and when to escalate. Read this before running any obsidian command that changes the vault.
- **exam-prep** — The academic module's working conventions — starting a course from the template subtree, chapter-note study tracking with the Exam-Study Base, and building study/spaced-repetition schedules from the syllabus and schedule notes. Use for any coursework, exam prep, or study-planning task.
- **daily-notes** — How daily notes work in this vault — where today's note lives, the safe morning-scaffold procedure for setting up today's note, how task carry-over works, and the end-of-day close-out. Use whenever setting up, creating, finding, or updating today's daily note.
- **task-capture** — Capture a task from natural language into this Obsidian vault — parse the text, date, and priority; route it to the right note; format it for the Tasks plugin; and append it. Use whenever the user wants to add, capture, jot, or remember a task ("add a task to…", "remind me to…", "I need to fix X by Friday", "check this later").
- **fitness-review** — The fitness system's working conventions — strategy-note-driven targets, the daily Intake tally, bodyweight tracking, and how weekly/monthly reviews are produced. Use when logging food or training, tracking weight, or writing a fitness review.
- **oss-tracking** — The OSS tracking conventions — one note per project, the watching/contributing status lifecycles, the one-copy promote/demote rule, and last-checked staleness discipline. Use for any task touching the OSS watchlist or contributions.
- **devlogs** — The software-projects conventions — per-project folders from the template subtree, dated devlog entries, typed task and feature notes, decision capture, and subsystem notes. Use for any task touching project notes, devlogs, or project task tracking.
- **reading-triage** — The reading pipeline's conventions — clipping web content with defuddle, inbox capture, triage into article notes, evergreen distillation, and linking into other domains. Use for any task touching captures, articles, or evergreen notes.
- **paper-pipeline** — The research module's paper conventions — citation-key naming, the seven paper types, the status lifecycle, rich frontmatter, and how summaries, topic notes, and reading lists connect. Use for any task touching papers, summaries, or the research pipeline.

## If you'd rather not use AI

Delete `.claude/` and everything here still works — templates are plain copies, views are plain files. See `Start-Here.md` for the no-AI tour.

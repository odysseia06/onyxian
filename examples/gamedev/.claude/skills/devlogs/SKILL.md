---
name: devlogs
description: The software-projects conventions — per-project folders from the template subtree, dated devlog entries, typed task and feature notes, decision capture, and subsystem notes. Use for any task touching project notes, devlogs, or project task tracking.
---

# devlogs

Read the resolved root from `.vault/config.yaml` under `modules.projects-software.vars.root` (called `<root>` below).

## Per-project structure

- One folder per project under `<root>`, started by copying `<root>/_Project-Template/` (Devlog, Tasks, Research, Assets + the Overview note). Never work inside the template itself.
- Subsystem folders are added per project as the architecture demands (runtime, renderer, ecs, api, ...), each with a subsystem note; the Overview's Subsystems section indexes them. Prefer wikilinks between architecture, subsystem, task, and devlog notes over duplicating design detail.

## Devlogs

- One dated entry per working session in the project's `Devlog/`, named `YYYY-MM-DD <topic>`, from the Devlog Entry template: what I did, what changed, problems, decisions/insights, next step.
- Devlogs are append-only history — never rewritten, never backfilled silently. Corrections go in a new entry.

## Tasks and features

- Task notes (template: Task Note) live in the project's `Tasks/`: scope, dependencies, done-when, plus a Tasks-plugin checklist line so daily-note queries surface it. Status lifecycle: `open` → `done` (set `blocked` while stuck). The `Project-Tasks.base` views read these statuses.
- Feature notes (template: Feature Note) capture design intent before implementation: `planned` → `building` → `shipped`.

## Decision capture

- Small decisions: a dated bullet under the Overview's Key Decisions. Big ones: a note in the project's `Research/` with the options considered and why the winner won, linked from the Overview. A decision without its why is a future archaeology dig.

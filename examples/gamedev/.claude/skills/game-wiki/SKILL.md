---
name: game-wiki
description: The gamedev module's working conventions — idea incubation before folders, copy-per-game structure from untouchable master copies, one truthful-status note per mechanic, append-only devlogs, decisions with their why, and the engine-code boundary. Use for any task touching game ideas, mechanics, devlogs, or game project notes.
---

# game-wiki

Read the resolved root from `.vault/config.yaml` under `modules.projects-gamedev.vars.root` (called `<root>` below). Each game is a folder under `<root>` copied from `<root>/_Game-Template/`; `Design-Board.base` is the overview — a Games roster (every real `00 Overview` note), incubating Ideas with their age, and Mechanics grouped by status. The Base reads frontmatter, so truthful `type`, `status`, and `date` fields are the source of truth.

## Master copies

`<root>/_Game-Template/**` is the user's set of master copies: seeded once, owned by the user, excluded from every Design-Board view. Never modify, move, or add to it. Starting a game copies it — read the template notes, create the new game's siblings — and that copy is additive and confirmed with the user first.

## Idea incubation

- One Game Idea note per idea (type `game-idea`, status `incubating`), created in `<root>` from the Game Idea template. Ideas have no folder — the Design-Board's Ideas view is what surfaces them, oldest first.
- An idea earns a game folder only when the user decides it is serious. That threshold is always the user's call: propose starting the game, never start it unprompted.

## Mechanics

- One Mechanic Note per mechanic (type `game-mechanic`), in the game's `Mechanics/` folder. `status` starts `planned`; move it as the mechanic becomes real — e.g. `prototyping`, `shipped`, or `cut` — and keep the vocabulary consistent across mechanics, because the Design-Board's Mechanics view groups by it.
- A mechanic that touches other systems names them under its Interactions section; keep those wikilinks alive as notes change.

## Devlogs and decisions

- Devlogs are dated and append-only: today's entry lives at `<game>/Devlog/<today>.md`, and a second session the same day appends a heading to that same file. Corrections are new entries, never rewrites of history.
- Decisions land in the game's `04 Decisions.md` as dated entries under `## Accepted` (or `## Rejected`), always with the why. A decision without its recorded rationale is not a decision entry yet — ask for the why first.

## Boundary

The game lives here; a custom engine or any substantial code is a software project (projects-software module). Link the game and its engine by wikilink, never mix their notes.

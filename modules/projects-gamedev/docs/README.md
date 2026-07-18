# projects-gamedev

Game projects as wikis, generalized from the maintainer's setup (KICKSTART.md §5.4): the copy-per-game `_Game-Template/` carries the five numbered notes (Overview with a live task query, Vision, Roadmap, Tech Design, Decisions) and the area folders (Game-Design, Mechanics, Worldbuilding, Content, Art-Audio, UI-UX, Research, Tasks, Devlog, Assets). The numbered notes are seeds — the user's master copies.

| `type` | `status` | Template |
|---|---|---|
| `game-idea` | `incubating` | Game Idea (pre-folder incubation) |
| `game-mechanic` | `planned` | Mechanic Note |
| `game-overview` / `game-vision` / `game-roadmap` / `game-tech` / `game-decisions` | `active` | seeded subtree |

`Design-Board.base` is the overview: a Games roster (one row per real `00 Overview`), incubating Ideas with an age column, and Mechanics grouped by status — with `_Game-Template/**` excluded from every view so the master copies never pollute the board.

Agent layer: `game-steward` uses the `game-wiki` skill to capture idea and mechanic notes, append dated devlog entries, and record decisions in `04 Decisions.md` always with their why. New games start as an additive, user-confirmed copy of `_Game-Template/`; modifying the masters themselves is an explicit escalation, and the idea-to-folder threshold stays the user's call.

The source vault's separation is kept: a custom engine is a *software* project (projects-software module); the game built on it lives here, and the two link by wikilink. Variables: `root` (default `Projects/Game-Dev`).

# projects-gamedev

Game projects as wikis, generalized from the maintainer's setup (KICKSTART.md §5.4): the copy-per-game `_Game-Template/` carries the five numbered notes (Overview with a live task query, Vision, Roadmap, Tech Design, Decisions) and the area folders (Game-Design, Mechanics, Worldbuilding, Content, Art-Audio, UI-UX, Research, Tasks, Devlog, Assets). The numbered notes are seeds — the user's master copies.

| `type` | `status` | Template |
|---|---|---|
| `game-idea` | `incubating` | Game Idea (pre-folder incubation) |
| `game-mechanic` | `planned` | Mechanic Note |
| `game-overview` / `game-vision` / `game-roadmap` / `game-tech` / `game-decisions` | `active` | seeded subtree |

The source vault's separation is kept: a custom engine is a *software* project (projects-software module); the game built on it lives here, and the two link by wikilink. Variables: `root` (default `Projects/Game-Dev`).

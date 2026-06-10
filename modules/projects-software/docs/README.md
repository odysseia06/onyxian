# projects-software

Per-project engineering notes, generalized from the maintainer's working setup (KICKSTART.md §5.4) — the engine-project shape (subsystem folders + Devlog + Tasks + Research) with the subsystems left to grow per project instead of being imposed.

## Note types

| `type` | `status` | Template |
|---|---|---|
| `project-overview` | `active` | seeded in `_Project-Template` |
| `devlog` | `logged` (append-only history) | Devlog Entry |
| `task` | `open` → `done` (`blocked` while stuck) | Task Note (carries a Tasks-plugin checklist line) |
| `feature` | `planned` → `building` → `shipped` | Feature Note |

`Project-Tasks.base` renders Open / All-By-Status over `task`+`project` tagged notes — tag-driven, style-independent.

## Variables

- `root` (default `Projects/Software`) — a nested default on purpose: software projects usually live inside a broader projects area. Game-dev projects and the OSS watchlist/contributing workflow are their own modules (M4).

Seeded: `_Project-Template/00 Overview.md` — the user's master copy.

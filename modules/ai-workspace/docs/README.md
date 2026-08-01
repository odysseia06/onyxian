# ai-workspace

The smallest module in the roster: two shelves and a dashboard, generalized from the maintainer's `General/Prompts` + `General/Agent-Skills` shelves. Still deliberately light on schema — prompt notes and skill drafts vary too much for typed frontmatter to help, so the module adds no keys of its own and documents values of the core keys instead. Prompt notes are `type: prompt`, living notes edited in place — an improvement replaces the old text, never a dated copy. Skill drafts are `type: skill-draft` with the lifecycle `status: draft → testing → graduated`.

Agent layer: `skill-smith` uses the `prompt-library` skill to capture prompts, keep draft statuses truthful, and answer "which drafts are still in testing" from the status keys alone. The lifecycle is the user's: statuses advance only on their say-so, graduation records where the skill shipped, and retiring a graduated draft into `Agent-Skills/Archive` is propose-only. The dashboard stays the user's own note.

Variables: `root` (default `AI-Workspace`; the canonical-example vault keeps these shelves under `General/`, claimable via the variable on adopt — the `researcher-developer` profile presets exactly that). Seeded: `00 Dashboard.md`.

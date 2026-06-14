# core

The module every other module depends on (KICKSTART.md §5.4). It installs the shared surface a vault needs before any domain content exists:

- `Templates/` — the vault-wide template root (managed). Other modules install their templates beneath it.
- `Templates/Note.md` — the generic typed-note template (managed): the four core frontmatter keys, Templater-compatible, functional as a plain copy.
- `Home.md` — the vault home note (seeded): explains what was installed and the safety contract, then becomes the user's page entirely.
- `.obsidian/community-plugins.json` — (seeded) enables the **Tasks** and **Templater** community plugins, which the templates rely on. Onyx enables them; the user installs them once from Obsidian's plugin browser. Seeded, so `adopt` claims an existing plugin list rather than overwriting it.
- four skills, installed into the vault's `.claude/skills/` and shipped in the Claude Code plugin: `vault-bootstrap` (the interview wizard), `vault-conventions` (the rules agents follow), and `obsidian-tasks` / `obsidian-templater` (how to drive the two plugins the templates use).

The conventions themselves — frontmatter schema, naming rules — live at `core/conventions/` in this repository and bind framework-created notes only; user notes are never validated against them. `core` declares no variables in M0: it has nothing worth tailoring yet, and a variable without a real choice behind it is noise in the interview.

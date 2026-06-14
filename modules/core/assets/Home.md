---
type: home
created: {{onyx.today}}
status: active
tags: []
---

# {{onyx.vault_name}}

This vault was scaffolded by Onyx on {{onyx.today}}. Everything here is plain files: the framework never needs to run for the vault to work, and no agent is load-bearing for your notes.

What you have right now:

- [[Note]] — the core note template. Copy it by hand, or point Obsidian's template hotkey (or Templater) at the Templates folder; the `<% ... %>` placeholder fills itself only if Templater is installed, and is simply text to replace if not.
- `.vault/config.yaml` — your declared intent: which modules are enabled, under which names. It is yours to edit; run `onyx plan` afterwards to preview exactly what would change, and `onyx apply` to make it so.
- `.vault/lock.json` — the engine's ledger of every file it has ever written. Machine-maintained; you never need to touch it.

Plugins this vault expects:

- **Templater** fills the `<% ... %>` placeholders in templates (today's date, the note title), and **Tasks** powers the task queries (due, scheduled, overdue) the domain modules use. This vault enables both in `.obsidian/community-plugins.json`, but Onyx can only enable them, not install them: open Settings, then Community plugins, then Browse, and add **Tasks** and **Templater** once. Then set Templater's template folder to `Templates`. Without the plugins the templates still open as plain notes; only the dynamic parts stay literal text.

How the safety contract works:

- A file the engine wrote gets updated only while you have left it untouched. The moment you customize it, it is yours: newer versions arrive beside it as `*.new` files instead of overwriting your work.
- This note was seeded — written once as a starting point and owned by you from that moment. The engine will never change it or recreate it. Replace all of this text with your own home page.
- Anything you create yourself is invisible to the engine. It will never write to, move, rename, or delete a file it does not own. There is no flag that overrides this.

Where to go next:

- Domain modules (daily notes, academic, fitness, research, and more) ship in upcoming milestones and are enabled per-vault, with your folder names, via `onyx add <module>`.
- `onyx doctor` checks the vault against its declared intent at any time, read-only.

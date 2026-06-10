---
name: vault-conventions
description: The frontmatter, naming, and writing rules any agent must follow when creating or editing notes in an Onyx-managed vault. Read this before writing any note, template, or generated text into the vault.
---

# Vault conventions

This skill mirrors `core/conventions/` from the Onyx repository — one source of truth, two audiences (KICKSTART.md §6.2). The bundled reference files carry the full rules:

- `frontmatter.md` — the typed-frontmatter schema every framework-created note follows.
- `naming.md` — folder styles, what gets transformed when, and the portable-path rules.

## The short version

- Every note you create carries the four core keys: `type` (kebab-case class), `created` (ISO date, set once), `status` (per-type lifecycle), `tags` (list, user-owned). Modules add typed fields on top; check the module's docs before inventing a key.
- These rules bind notes that **you or the framework create**. The user's own notes are never validated, corrected, or reformatted against them. Preserve unknown frontmatter keys byte-for-byte.
- Wikilinks for internal references; attachments go in the domain's `Assets/` folder.

## Writing rules (these bite)

- **Do not hard-wrap prose.** One logical line per paragraph and per bullet; Obsidian's Live Preview renders a hard-wrapped bullet with a gap mid-sentence, which reads as broken. Long lines are correct here.
- **Two placeholder languages.** `{{...}}` belongs to the Onyx engine and is already resolved by the time files reach the vault; `<% tp.* %>` belongs to Templater and must be left exactly as written — when you instantiate a template by hand, replace `<% ... %>` placeholders with real values and leave everything else.
- **Respect ownership.** Files tracked as managed by the engine (`.vault/lock.json`) update themselves; editing one hands ownership to the user and future updates will arrive as `*.new` siblings. Never move, rename, or delete files you did not create; never touch `.vault/` by hand.
- `status` changes are value edits, not file moves, unless the module's documented workflow says otherwise.

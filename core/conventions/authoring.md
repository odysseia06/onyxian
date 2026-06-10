# Module authoring rules

What it takes for a module to be accepted into the library — or shipped on your own. The module system is specified in KICKSTART.md §5; these are the working rules that keep modules reviewable, portable, and safe.

## Starting a module

`onyx module new <id>` scaffolds a skeleton (manifest with guidance comments, an example template, a docs README) that validates out of the box. Fill the summary, replace the example asset with real material, document your note types in `docs/README.md`, and test-install with `onyx add <path-to-your-module>` in a scratch vault — the full plan/lock machinery treats your module exactly like a bundled one.

## Distributing a module

Push the module folder as a git repository with `module.yaml` at the root. Anyone installs it with `onyx add <git-url>`: the engine shows a trust warning (§12), pins the reviewed commit into their config, and keeps the content vault-locally under `.vault/modules/<id>/` where it stays inspectable. `onyx update <id>` advances their pin; `onyx remove <id>` deletes the copy. Be worthy of the trust gate: your skills and agent definitions are instructions other people's agents will follow — write them with the same least-privilege discipline the bundled roster uses (§7.1).

## Structure

- A module is **data only**: `module.yaml` plus an `assets/` tree, optionally `skills/`, `agents/`, `docs/`. No executable code anywhere (§5.1) — a module must be fully reviewable by reading it.
- `assets/` mirrors the install tree **verbatim, placeholder segments included**: the asset that installs to `{{root}}/Strategy.md` lives at `assets/{{root}}/Strategy.md`. What you see in the module folder is exactly what lands in the vault.
- Wildcards (`*`) in `provides` lists expand against `assets/` in sorted order; a wildcard pattern cannot also contain `{{variables}}`.

## Two placeholder languages — never confuse them

| Syntax | Owner | Resolved | Use for |
|---|---|---|---|
| `{{variable}}` | the Onyx engine | once, at `apply` time | user tailoring: folder names, cadences; plus globals `{{onyx.today}}`, `{{onyx.vault_name}}` |
| `<% tp.* %>` | Templater (user's Obsidian) | every time the user instantiates a template | per-note values: today's date in a new note |

The engine substitutes `{{...}}` and passes `<% ... %>` through byte-for-byte. Every template must remain functional as a plain copy with no Templater installed (P2): a `<% ... %>` left unresolved must read as an obvious fill-me-in, never break the note.

## Prose in assets must not be hard-wrapped

One logical line per paragraph and per bullet; let editors soft-wrap. A bullet hard-wrapped at ~100 columns puts its continuation on an indented line, which Obsidian's Live Preview renders as a gap partway through the sentence — valid Markdown that reads as broken. Paragraphs fare little better: under "Strict line breaks" the wrap becomes a visible `<br>`. This rule covers module assets and any text the engine generates into a vault.

## Choosing `managed` vs `seeds`

- `provides.templates` / `provides.bases` → **managed**: framework-owned, silently updatable while the user has not customized their copy (§8.2). Use for anything you expect to improve over time.
- `seeds` → written **once**, user-owned from that moment, never updated or recreated. Use for starting points the user is meant to make their own (a Strategy note, example notes, a home page).
- When in doubt: if a future version of the module should be able to improve the file, it is managed; if the user's edits are the point of the file, it is a seed.

## Manifest hygiene

- `name` matches the directory name; `version` is plain semver; every module except `core` declares `depends: [core]`.
- Variables are the tailoring surface (P4): give every folder the module roots a `root` variable with a sensible default rather than hardcoding a name. Defaults are authored in `Title-Case-Hyphen` (the canonical style).
- `post_install` is for the human: what to fill in, what to read first. One short paragraph.
- Bases-first (P5): if your module's overview is a hand-maintained list note, redesign it as a `.base` over typed frontmatter.

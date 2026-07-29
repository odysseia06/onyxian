---
name: vault-operations
description: How an agent safely operates a live Obsidian vault through the obsidian CLI — additive writes, least privilege, look-before-you-write, and when to escalate. Read this before running any obsidian command that changes the vault.
---

# Vault operations

`vault-conventions` governs what a note looks like; this skill governs how you change a *live* vault. When Obsidian is running with its command-line interface enabled, the `obsidian` CLI drives the open vault directly — create notes, append to the daily note, set frontmatter, query tasks and Bases. That is real power over the user's data, so it comes with a contract. This skill is that contract, and its command quick reference (below) covers the syntax you need.

## Finding the CLI

If `obsidian` is not on PATH, it may still be installed — a terminal opened before the CLI was enabled won't have it yet. Before concluding the CLI is unavailable, look for the binary at the platform's standard location and call it by full path: Windows `%LOCALAPPDATA%\Programs\Obsidian\Obsidian.com`, macOS `/usr/local/bin/obsidian`, Linux `~/.local/bin/obsidian`. Only treat the CLI as genuinely unavailable if it is not there either.

## The CLI in brief

- It drives a **running** Obsidian instance over its open vault. If `obsidian vault info=name` returns nothing, the app is not running or the CLI is not enabled — say so and stop. Do not silently fall back to editing files on disk; that bypasses Obsidian's own indexing and file history.
- Commands target the active vault. When more than one vault may be open, name yours explicitly: `obsidian <command> vault="<name>"`.
- The CLI is an amplifier, never a dependency. Anything it does must also be doable by hand; if it is unavailable, degrade to telling the user what you would have done.

## The live write contract

This is the engine's write contract, restated for commands that mutate a running vault:

- **Additive by default.** Reach for `create` (a new file), `append`, `daily:append`, and `property:set`. Do not use `create ... overwrite`, `move`, `rename`, or `delete` on anything you did not create this run — the lone exception is the heading insert below, on a note in your own scope.
- **The user's notes are theirs.** Never reword, reformat, restructure, move, or delete a note the user wrote. You add to the vault; you do not edit the user's existing content out from under them.
- **The engine owns structure; you own content.** Folders, modules, templates, and Bases come from `onyxian apply`, not from an agent. Fill notes inside the structure that is already there; never invent folders or move the furniture.
- **Respect managed files.** Files Onyxian tracks in `.vault/lock.json` update themselves — do not hand-edit them through the CLI. Never touch `.vault/` at all.
- **Look before you write, and read the *right* target.** Read the target first to stay idempotent — and read it by exact `path=` (e.g. `read path="<folder>/<note>.md"`). `file=` resolves by name like a wikilink, and an unresolved name or an omitted `path=`/`file=` silently returns the **active** note rather than erroring — so a careless read can hand you a different note than you meant. `daily:read`/`daily:path` only ever address *today's* daily note (they take no date argument); to reach a past or specific day use `read path="<exact path>"`. If what you would add is already there, stop — running a workflow twice must not double-write it.
- **Report only state you checked — of the note you actually asked for.** When you report that a file already existed, or that you did or did not overwrite it, that claim must come from a read you performed this run (never relayed from a sub-step's narration) and from a read of the note you requested: confirm the returned note's identity — its `date`/title matches the path you asked for — because a silent active-file fallback can hand you a different note.

## Two edits beyond plain additions

**A typed property.** Setting a note's own typed property is allowed: `obsidian property:set name=status value=<v> file="<note>"`. Where a status has two representations — a frontmatter `status` a Base reads, and a Tasks-plugin checkbox — the frontmatter is canonical: set it first, then update the checkbox, and if the second write fails, stop and report the split rather than leaving them inconsistent.

**A line under a heading.** There is no insert-under-heading command (`append`/`prepend` only reach a file's tail and head). To add a line under a specific heading — a decision under a project Overview's `## Key Decisions`, say — read the note, splice the line in after that heading, and write the whole note back with `create ... overwrite`. Only do this to a note in your own write scope that you maintain, keep every other line exactly as it was, and lean on Obsidian's file history if you get it wrong.

## Stay in your scope

Your agent definition lists the globs you may read and write. Those bind your CLI calls too: a `create` or `append` outside your write scope is a defect, not initiative. When a task needs a file outside your scope, escalate instead of reaching for it.

## Escalate instead of acting when

- a workflow would overwrite, move, rename, or delete an existing file;
- a write would land outside your declared write scope;
- the right destination for a note is ambiguous;
- a managed or user-owned file would have to change to finish the task.

Stop and hand it back to the user with what you found and what you propose.

## The reversibility net

Obsidian keeps file history: `obsidian history` lists versions and `obsidian history:restore` / `obsidian sync:restore` recover them. That is a backstop for genuine accidents, not a license to overwrite and "undo later." Operate as if there were no undo; the net is there for the case where you were careful and still wrong.

## Ensuring a required plugin is present

Some workflows need a community plugin — **Tasks** (`obsidian-tasks-plugin`) for the task queries, **Templater** (`templater-obsidian`) for the template macros. The vault enables both in `.obsidian/community-plugins.json`, but a fresh vault may not have the plugin code installed yet, and a brand-new vault opens in Restricted Mode with community plugins off.

The CLI can install them — but never silently. Check first with `obsidian plugins:enabled filter=community`; if a plugin your workflow needs is missing, stop and ask the user, naming the plugin and why you need it. Only on an explicit yes:

- If the vault is in Restricted Mode, turn it off first — `obsidian plugins:restrict off`. This is a trust decision (it lets community plugins run); fold it into the same ask.
- Install and enable in one step — `obsidian plugin:install id=obsidian-tasks-plugin enable` (and/or `id=templater-obsidian`).
- Templater also needs its template folder pointed at the Templates root, which `plugin:install` does not configure — tell the user to set it in Templater's settings.

If the user declines, continue without the plugin and say plainly what degrades: task queries render as plain code blocks, template macros stay literal.

## Templates do not auto-resolve

`obsidian create ... template=` and `obsidian template:read ... resolve` insert a template **verbatim** — they do not run Templater, so any `<% ... %>` / `<%* ... %>` macros land literally (verified against the live CLI). When a template is Templater-driven, do not create from it through the CLI and expect a finished note: either let Obsidian and Templater create the note, or resolve the content yourself before writing it. Never write a note that still contains `<% ... %>`.

## Command quick reference

Safe to run on your own, within scope:

- **Read** — `read`, `daily:read`, `file`, `files`, `search`, `search:context`, `tasks`, `properties`, `backlinks`, `base:query`.
- **Add** — `create` (new file only), `append`, `daily:append`, `daily:prepend`, `property:set` (a key you own).

Escalate first — these change or remove what already exists:

- `delete`, `move`, `rename`, `create ... overwrite`, `property:remove`, `plugin:*`, `reload`, `restart`, and anything under `dev:` / `eval`.

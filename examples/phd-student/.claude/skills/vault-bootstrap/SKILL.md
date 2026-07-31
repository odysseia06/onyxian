---
name: vault-bootstrap
description: Conversational setup for an Onyxian vault — turns what the user wants into `onyxian` CLI flags and answers files, shows the engine's plan verbatim where a review is due, and applies only with the user's consent. Use when the user wants to create an Onyxian vault, adopt an existing Obsidian vault, or enable modules through a guided flow.
---

# vault-bootstrap — the conversational flag-composer

You are the conversational front end of a deterministic engine. The division of labor is absolute: **you turn the conversation into `onyxian` commands; the engine does every write.** The CLI asks no questions, and neither do you beyond what the conversation actually needs — there is no script of questions to run. You never create, edit, move, or delete vault files yourself during bootstrap, and you never reach into `.vault/`. If something looks wrong, you show the engine's output and ask — you do not work around it.

## Preconditions

1. **The engine must be installed.** Run `onyxian --version`. If it prints a version, continue. If the command is not found, the `onyxian` CLI is not on PATH — offer to install it, and on the user's OK run the first of these that is available (each installs the published `onyxian` package, whose command is `onyxian`), in order:
   - `uv tool install onyxian`
   - `pipx install onyxian`
   - `python -m pip install --user onyxian`  (on Windows, `py -m pip install --user onyxian` if `python` is not found)

   `uv` and `pipx` give an isolated install; `pip --user` is the fallback. Re-run `onyxian --version` to confirm before continuing. If none of `uv`, `pipx`, or `pip` exist, tell the user to install one (uv is the lightest) and stop — never work around a missing engine by editing vault files yourself. A development checkout is the other valid source: `pip install -e .` from a clone, or set `ONYXIAN_HOME` to one.
2. `onyxian modules` lists every available module with its variables and defaults — use it instead of guessing what exists.
3. For **adopt**, tell the user to commit the vault to version control (or copy it) first. The engine is additive by contract, but the recommendation is part of the flow.

## The parity rule

Every decision maps one-to-one onto a config key; a composed command, a hand-edited `.vault/config.yaml`, and an `--answers` file are three doors into the same room. Never invent a decision without a key, and never set a key the user didn't decide — anything undecided keeps its declared default, named, not asked about.

| Decision | Config key | How to supply it |
|---|---|---|
| Vault name | `vault.name` | `vault.name` in an answers file; bare `init` names the vault after its folder |
| Folder naming style (`Title-Case-Hyphen` / `kebab-case` / `Spaces`) | `naming.folder_style` | `naming.folder_style` in an answers file (default `Title-Case-Hyphen`) |
| Agent runtime(s) | `framework.runtimes` | `framework.runtimes` in an answers file (default `[claude-code]`) |
| Module set | `modules.<id>` | `--profile <name>`, `modules.<id>: {}` in an answers file, or `onyxian add <id>` after init |
| Module variables | `modules.<id>.vars.<key>` | `modules.<id>.<key>` in an answers file; manifest defaults fill the rest |
| Vault checkpoints (git-backed session snapshots; default off) | `framework.checkpoints` | `framework.checkpoints: true` in an answers file |
| Agent scope hooks (Claude Code PreToolUse gate; default off) | `framework.scope_hooks` | `framework.scope_hooks: true` in an answers file |
| Pinned `kepano/obsidian-skills` (defaults in, claude-code only) | `sources.obsidian-skills` | omit for the default; `sources.obsidian-skills: false` opts out; installing needs `--trust` |

## Flow A — new vault (`init`)

The target folder must be new or empty — anything else is adopt's job (the engine refuses and says so). Fit the command to what the user said; don't interrogate. Three shapes, cheapest first:

1. **They just want a vault** → `onyxian init <target>`. Core-only, zero questions, applied immediately; the growth path is `onyxian add <module>` any time. Skip to the doctor step.
2. **A bundled profile fits what they described** → `onyxian init <target> --profile <name>`. One shot, full preset, also applied immediately. `onyxian init x --profile no-such` prints the available names; the profile files live at `profiles/*.yaml`.
3. **They have specific wants** — particular modules, folder names, naming style, runtimes, sources — → write exactly those decisions to a temporary YAML answers file in the parity shape above. Then:
   - `onyxian init <target> --answers <file> --dry-run` and show the **full plan output verbatim** — counts, paths, and anything under "needs your attention". Do not summarize it away.
   - On an explicit yes: `onyxian init <target> --answers <file> --yes`. On no: change the answers file and loop.

Add `--trust` **only** if the user said yes to installing obsidian-skills — that answer is the consent for its skill instructions, and `--yes` deliberately does not carry it. Without `--trust` the source stays declared but uninstalled until `onyxian update --trust`; bare `init` likewise declines it and says so.

Finish every shape the same way: run `onyxian doctor --vault <target>`, relay the verdict and any post-install steps, and point the user at `Start-Here.md` and `Home.md` in the new vault.

## Flow B — existing vault (`adopt`)

1. Remind about the VCS commit, then run `onyxian adopt <target> --dry-run`. The scan proposes claims (existing folders mapped to module roots via variables), a purely additive gap-fill plan, and a **checklist** of ambiguities the engine refuses to decide.
2. Show claims, plan, and checklist verbatim. Walk the user through each claim (accept, or change the variable value) and each checklist item (these stay manual by design — never resolve one by acting on files).
3. Adjusted claims are just module variable answers: rebuild the answers file and re-run the dry run until the user is satisfied. A required variable the scan couldn't claim is an engine error naming the module and key — it goes in the answers file too, never into a guess.
4. Adopt has **no `--yes`** — mandatory review, no fast path. The dry run prints an acceptance token derived from the exact plan shown; apply with `onyxian adopt <target> --answers <file> --accept <token>`. If the vault changed in between, the token is rejected and you re-review — that is the feature working, not a bug.
5. Finish with `onyxian doctor`, relay post-install notes, and summarize exactly what was added and what was left untouched.

## Hard rules

- Don't interrogate. Defaults are answers; discuss only the decisions the user has signaled they care about, and never run a staged question sequence.
- Where a review gates an apply (`--answers` init, adopt), the user sees the plan from **this** run first; `--yes` / `--accept` are never used on a plan the user has not just seen.
- Blocked items ("needs your attention") are the user's decisions. Present each one; never resolve one by deleting, renaming, or overwriting anything.
- Relay engine errors verbatim, then help interpret them. Never hand-edit files to force a flow through.
- Bare `init` and `--profile` write immediately into a new/empty folder by design; if the user changes their mind afterwards, growth and removal go through `onyxian add` / `onyxian remove`, never manual deletion of engine files. In the `--answers` and adopt flows, nothing is written before the gated apply — abandoning is free, and say so.

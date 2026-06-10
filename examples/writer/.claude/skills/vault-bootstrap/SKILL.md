---
name: vault-bootstrap
description: Interview wizard that sets up a new Onyx vault (init) or brings an existing vault under management (adopt) — asks the questions, builds an answers file, shows the engine's plan verbatim, and applies only after the user confirms. Use when the user wants to create an Onyx vault, adopt an existing Obsidian vault, or enable modules through a guided flow.
---

# vault-bootstrap — the interview wizard

You are the conversational front end of a deterministic engine (KICKSTART.md §9.2). The division of labor is absolute: **you ask questions and drive the `onyx` CLI; the engine does every write.** You never create, edit, move, or delete vault files yourself during bootstrap, and you never reach into `.vault/`. If something looks wrong, you show the engine's output and ask — you do not work around it.

## Preconditions

1. `onyx --version` must succeed. If it does not, the engine is not installed: from a checkout of the Onyx repository run `pip install -e .`, or ask the user where their checkout lives and set `ONYX_HOME` to it.
2. `onyx modules` lists every available module with its variables and defaults — use it instead of guessing what exists.
3. For **adopt**, tell the user to commit the vault to version control (or copy it) first. The engine is additive by contract, but the recommendation is part of the flow (§9.3).

## The parity rule

Every question maps one-to-one onto a config key; the wizard, a hand-edited `.vault/config.yaml`, and an `--answers` file are three doors into the same room. Never invent a question without a key, never set a key without asking or stating the default.

| Question | Config key | Answers-file key |
|---|---|---|
| Vault name | `vault.name` | `vault.name` |
| Folder naming style (`Title-Case-Hyphen` / `kebab-case` / `Spaces`) | `naming.folder_style` | `naming.folder_style` |
| Agent runtime(s) | `framework.runtimes` | `framework.runtimes` |
| Profile pick or custom module set | `modules.<id>` | `modules.<id>: {}` (or a profile file as the whole answers file) |
| Each module variable, defaults visible | `modules.<id>.vars.<key>` | `modules.<id>.<key>` |
| Install pinned `kepano/obsidian-skills`? | `sources.obsidian-skills` | `sources.obsidian-skills: {}` |

## Flow A — new vault (`init`)

1. Ask where the vault should live; confirm the folder is new or empty (the engine refuses anything else and points to adopt).
2. Offer profiles first (`profiles/*.yaml`, e.g. `minimal`), then custom selection from `onyx modules`. Show what each module brings (its summary) and note dependencies are added automatically and will be visible in the plan.
3. Ask the per-module variable questions with defaults visible, then naming style, vault name, runtimes, and the obsidian-skills question.
4. Write the collected answers to a temporary YAML file in the answers shape above.
5. Run `onyx init <target> --answers <file> --dry-run` and show the user the **full plan output verbatim** — counts, paths, and anything under "needs your attention". Do not summarize it away.
6. Ask for explicit confirmation. On yes: `onyx init <target> --answers <file> --yes`. On no: ask what to change and loop.
7. Run `onyx doctor --vault <target>`, relay the verdict and any post-install steps, and point the user at `Start-Here.md` and `Home.md` in the new vault.

## Flow B — existing vault (`adopt`)

1. Remind about the VCS commit, then run `onyx adopt <target> --dry-run`. The scan proposes claims (existing folders mapped to module roots via variables), a purely additive gap-fill plan, and a **checklist** of ambiguities the engine refuses to decide.
2. Show claims, plan, and checklist verbatim. Walk the user through each claim (accept, or change the variable value) and each checklist item (these stay manual by design — never resolve one by acting on files).
3. Adjusted claims are just module variable answers: rebuild the answers file and re-run the dry run until the user is satisfied.
4. Adopt has **no `--yes`** (§9.3: mandatory review, no fast path). The dry run prints an acceptance token derived from the exact plan shown; apply with `onyx adopt <target> --answers <file> --accept <token>`. If the vault changed in between, the token is rejected and you re-review — that is the feature working, not a bug.
5. Finish with `onyx doctor`, relay post-install notes, and summarize exactly what was added and what was left untouched.

## Hard rules

- The user sees the plan from **this** run before anything is applied; `--yes` / `--accept` are never used on a plan the user has not just seen.
- Blocked items ("needs your attention") are the user's decisions. Present each one; never resolve one by deleting, renaming, or overwriting anything.
- Relay engine errors verbatim, then help interpret them. Never hand-edit files to force a flow through.
- If the user changes their mind mid-flow, nothing has been written until step 6 (init) / the `--accept` run (adopt) — say so; abandoning is free.

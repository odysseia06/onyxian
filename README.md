# Onyx

[![PyPI](https://img.shields.io/pypi/v/onyx-vault.svg)](https://pypi.org/project/onyx-vault/)
[![CI](https://github.com/odysseia06/onyx/actions/workflows/ci.yml/badge.svg)](https://github.com/odysseia06/onyx/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/onyx-vault.svg)](https://pypi.org/project/onyx-vault/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Onyx scaffolds and operates a tailored [Obsidian](https://obsidian.md) vault, composed from **opt-in modules**. Pick the domains you care about and Onyx wires up the folders, typed frontmatter, [Bases](https://help.obsidian.md/bases) views, and templates for each. The same framework serves a researcher, a PhD student, a musician, and a product manager, with different module sets and different folder names.

Three things hold true everywhere:

- **It works without any AI.** Templates are plain copies, views are plain files. Optional Claude Code skills and agents amplify the vault, but nothing depends on them.
- **It never clobbers your files.** Every file Onyx writes is tracked. A file you edited is yours: updates that would overwrite it arrive as a `*.new` sibling instead, never a silent overwrite. There is no flag that overrides this.
- **It's tailored to you.** Folder names, cadences, and structures are per-vault variables, not baked-in opinions.

## Install

### In Claude Code (nothing to set up)

```
/plugin marketplace add odysseia06/onyx
/plugin install onyx@onyx
/vault-bootstrap
```

The plugin ships the interview wizard. On first run it installs the CLI for you and walks you from an empty folder, or an existing vault, to a working setup.

### As a command-line tool

```
uv tool install onyx-vault      # or:  pipx install onyx-vault
```

Then create a vault:

```
onyx init my-vault                                  # interactive interview
onyx init my-vault --answers researcher-developer   # or start from a profile
```

Open the folder in Obsidian and you're done.

### From source

```
git clone https://github.com/odysseia06/onyx && cd onyx
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Using it

| Command | What it does |
|---|---|
| `onyx init <folder>` | Create a new vault from the interview or a profile. Refuses a non-empty folder. |
| `onyx adopt <vault>` | Bring an **existing** vault under management. Additive only, behind a reviewed plan. |
| `onyx add <module>` | Enable a module (its dependencies come with it). |
| `onyx remove <module>` | Disable a module. Deletes only unmodified framework files; your edits stay. |
| `onyx update` | Pull newer module and skill versions. Files you changed are never overwritten. |
| `onyx plan` / `onyx apply` | Preview the diff, then reconcile. Every mutating command takes `--dry-run`. |
| `onyx doctor` | Check the vault against its declared intent. Read-only. |
| `onyx modules` | List available modules with their variables and defaults. |
| `onyx module new <id>` | Scaffold your own module. |

**Adopting an existing vault is the safe path.** `onyx adopt <vault> --dry-run` is read-only: it maps your existing folders onto module variables, proposes a purely additive plan, and parks anything ambiguous on a checklist instead of touching it. Nothing is moved, renamed, deleted, or overwritten. There is no `--yes` on `adopt` — you review the plan and confirm it, by passing back the token the review prints. (Commit your vault to git first; Onyx will remind you.)

## How it works

The engine is a small CLI built on a declarative reconciliation loop:

- `.vault/config.yaml` declares **intent** — which modules, with which variables. Yours to edit.
- `.vault/lock.json` records **state** — every file Onyx has written, with its hash. Machine-maintained.
- `onyx plan` computes the difference; `onyx apply` reconciles it.

Every file Onyx writes is one of two kinds. **Managed** files (templates, views, skills) update themselves while you leave them alone, and turn into `*.new` deliveries the moment you customize them. **Seeded** files (your home note, a strategy note) are written once and yours from then on. Everything else in the vault is invisible to Onyx, and it will never write there.

## Modules

| Module | What it gives you |
|---|---|
| `core` | The shared conventions, the `Templates/` root, and the home note every module builds on. |
| `daily-notes` | One note per day with task-rollover queries: due, scheduled, overdue, carry-over. |
| `academic` | Courses from a copy-per-course template; exam prep tracked through a Base. |
| `fitness` | Training, nutrition, and body tracking, driven by a Strategy note you own. |
| `research` | A typed paper pipeline: PDF to summary to topic links, over a multi-view Paper Library Base. |
| `reading` | An Inbox to Articles to Evergreen pipeline, with web clipping. |
| `projects-software` | Per-project devlogs, decision logs, subsystem notes, and a task Base. |
| `projects-gamedev` | Game projects as living wikis: design, mechanics, worldbuilding, devlog. |
| `oss` | Open-source tracking from watchlist to contribution, with staleness-aware Bases. |
| `music` | Theory, practice, composition, production, listening, and copy-per-piece projects. |
| `writing` | An editorial blog pipeline: ideas to drafts to published, with series and a calendar. |
| `ai-workspace` | A prompts library and an agent-skills workbench. |

Enable any combination with `onyx add`, or start from a **profile** (a named module set): `minimal`, `fitness-focused`, `student`, `phd-student`, `writer`, or `researcher-developer`.

## The agent layer (optional)

When you use Claude Code, each enabled module installs scoped skills and a per-domain agent into `.claude/` — a `research-librarian`, a `study-coach`, a `fitness-coach`, and so on, each with explicit read/write boundaries. Other runtimes get a generated `AGENTS.md`. Delete `.claude/` entirely and the vault still works as plain files; the agents only ever amplify.

## Documentation

- **[KICKSTART.md](KICKSTART.md)** — the full design document: vision, architecture, the module system, and the write/lock/update contract.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — how to work on Onyx and author modules.
- **[RELEASING.md](RELEASING.md)** — how releases are cut and published.

## License

MIT.

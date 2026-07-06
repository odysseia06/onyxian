# Onyxian

[![PyPI](https://img.shields.io/pypi/v/onyxian.svg)](https://pypi.org/project/onyxian/)
[![CI](https://github.com/odysseia06/onyxian/actions/workflows/ci.yml/badge.svg)](https://github.com/odysseia06/onyxian/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://pypi.org/project/onyxian/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Onyxian scaffolds and operates a tailored [Obsidian](https://obsidian.md) vault, composed from **opt-in modules**. Pick the domains you care about and Onyxian wires up the folders, typed frontmatter, [Bases](https://help.obsidian.md/bases) views, and templates for each. The same framework serves a researcher, a PhD student, a musician, and a product manager, with different module sets and different folder names.

Three things hold true everywhere:

- **It works without any AI.** Templates are plain copies, views are plain files. Optional Claude Code skills and agents amplify the vault, but nothing depends on them.
- **It never clobbers your files.** Every file Onyxian writes is tracked. A file you edited is yours: updates that would overwrite it arrive as a `*.new` sibling instead, never a silent overwrite. There is no flag that overrides this.
- **It's tailored to you.** Folder names, cadences, and structures are per-vault variables, not baked-in opinions.

<p align="center">
  <img src="https://raw.githubusercontent.com/odysseia06/onyxian/main/docs/assets/onyxian-init.svg" alt="onyxian init planning and creating a complete PhD-student vault — folders, templates, Bases views, and agents — from one command" width="780">
</p>

## Install

### In Claude Code (nothing to set up)

```
/plugin marketplace add odysseia06/onyxian
/plugin install onyxian@onyxian
/vault-bootstrap
```

The plugin ships the interview wizard. On first run it installs the CLI for you and walks you from an empty folder, or an existing vault, to a working setup.

### As a command-line tool

```
uv tool install onyxian      # or:  pipx install onyxian
```

Then create a vault:

```
onyxian init my-vault                                  # interactive interview
onyxian init my-vault --answers researcher-developer   # or start from a profile
```

Open the folder in Obsidian and you're done.

### From source

```
git clone https://github.com/odysseia06/onyxian && cd onyxian
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Using it

| Command | What it does |
|---|---|
| `onyxian init <folder>` | Create a new vault from the interview or a profile. Refuses a non-empty folder. |
| `onyxian adopt <vault>` | Bring an **existing** vault under management. Additive only, behind a reviewed plan. |
| `onyxian add <module>` | Enable a module (its dependencies come with it). Also takes a git URL or local directory to install a third-party module, behind a trust warning. |
| `onyxian remove <module>` | Disable a module. Deletes only unmodified framework files; your edits stay. |
| `onyxian update` | Pull newer module and skill versions. Files you changed are never overwritten. |
| `onyxian plan` / `onyxian apply` | Preview the diff, then reconcile. Every mutating command takes `--dry-run`. |
| `onyxian doctor` | Check the vault against its declared intent. Read-only. |
| `onyxian modules` | List available modules with their variables and defaults. |
| `onyxian module new <id>` | Scaffold your own module. |
| `onyxian project new <name>` | Scaffold a software project from the project template (needs the `projects-software` module). |

**Adopting an existing vault is the safe path.** `onyxian adopt <vault> --dry-run` is read-only: it maps your existing folders onto module variables, proposes a purely additive plan, and parks anything ambiguous on a checklist instead of touching it. Nothing is moved, renamed, deleted, or overwritten. There is no `--yes` on `adopt` — in a terminal you review the plan and type `adopt` to confirm; non-interactively (scripts, agents), the review prints an acceptance token derived from the exact plan shown, and you apply with `--accept <token>`. (Commit your vault to git first; Onyxian will remind you.)

## How it works

The engine is a small CLI built on a declarative reconciliation loop:

- `.vault/config.yaml` declares **intent** — which modules, with which variables. Yours to edit.
- `.vault/lock.json` records **state** — every file Onyxian has written, with its hash. Machine-maintained.
- `onyxian plan` computes the difference; `onyxian apply` reconciles it.

Every file Onyxian writes is one of two kinds. **Managed** files (templates, views, skills) update themselves while you leave them alone, and turn into `*.new` deliveries the moment you customize them. **Seeded** files (your home note, a strategy note) are written once and yours from then on. Everything else in the vault is invisible to Onyxian, and it will never write there.

## Modules

| Module | What it gives you |
|---|---|
| `core` | The shared conventions, the `Templates/` root, and the home note every module builds on. |
| `daily-notes` | One note per day with task-rollover queries (due, scheduled, overdue, carry-over, captured) and natural-language task capture. |
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

Enable any combination with `onyxian add`, or start from a **profile** (a named module set): `minimal`, `fitness-focused`, `student`, `phd-student`, `writer`, or `researcher-developer`.

Modules are data, not code, so the roster isn't closed: scaffold your own with `onyxian module new <id>`, publish it as a git repository, and anyone can install it with `onyxian add <url>` (they'll see a trust warning first — a module can't execute anything, but a malicious template is still a social-engineering surface).

## The agent layer (optional)

When you use Claude Code, each enabled module installs scoped skills and a per-domain agent into `.claude/` — `daily-planner`, `research-librarian`, `study-coach`, `fitness-coach`, and so on, each with a documented read/write scope it operates within. A generated `CLAUDE.md` orients Claude the moment you open the vault, pointing at the agents and the operating rules so a plain request reaches the right one; other runtimes get a generated `AGENTS.md`.

These agents don't only suggest — they **operate the live vault** through Obsidian's official command-line interface: scaffold and triage the day, capture a task from a sentence (*"add a task to fix this by Friday"*), log a coding session or record a decision (*"we decided X because Y"*), file a typed paper summary, and so on — you reach the right agent just by saying what you want. Every write follows one contract (the `vault-operations` skill): additive by default, inside the agent's scope, escalating rather than guessing. These scopes are conventions the agents are instructed to honor, not a filesystem sandbox — the [user guide](docs/user-guide.md#the-agent-layer-optional) says exactly what kind of guarantee that is. Delete `.claude/` entirely and the vault still works as plain files; the agent layer is power, never a dependency.

## Documentation

- **[docs/user-guide.md](docs/user-guide.md)** — the user guide: install, quickstart, adopting an existing vault, everyday operations, `*.new` files, the agent layer, a full module reference, and troubleshooting. Start here.
- **[KICKSTART.md](KICKSTART.md)** — the design charter: vision, architecture, the module system, and the write/lock/update contract. Internal, but the deep read on why the engine works the way it does.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — how to work on Onyxian and author modules.
- **[RELEASING.md](RELEASING.md)** — how releases are cut and published.

## License

MIT.

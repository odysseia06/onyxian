# Onyxian user guide

Onyxian scaffolds and operates a tailored [Obsidian](https://obsidian.md) vault, composed from opt-in modules: pick the domains you care about and it wires up the folders, typed frontmatter, [Bases](https://help.obsidian.md/bases) views, and templates for each. The same framework serves a PhD student, a musician, a developer, and a product manager, with different module sets and different folder names. It can also adopt a vault you already have — additively, behind a plan you review — and keep everything updated for years without ever touching a file you wrote.

Three things hold true everywhere:

- **It works without any AI.** Templates are plain copies, views are plain files. Optional Claude Code skills and agents amplify the vault, but nothing depends on them.
- **It never clobbers your files.** Every file Onyxian writes is tracked. A file you edited is yours: updates that would overwrite it arrive as a `*.new` sibling instead, never a silent overwrite. There is no flag that overrides this.
- **It's tailored to you.** Folder names, cadences, and structures are per-vault variables, not baked-in opinions.

Contents: [install](#install) · [quickstart](#quickstart-your-first-vault) · [how Onyxian thinks](#how-onyxian-thinks) · [adopting an existing vault](#adopting-an-existing-vault) · [everyday operations](#everyday-operations) · [`*.new` files](#when-an-update-meets-your-edits-new-files) · [the agent layer](#the-agent-layer-optional) · [module reference](#module-reference) · [two day-zero stories](#two-day-zero-stories) · [troubleshooting and FAQ](#troubleshooting-and-faq)

## Install

There are three doors. If you use Claude Code, take the first one — it needs no Python setup at all.

### In Claude Code (recommended, nothing to set up)

```
/plugin marketplace add odysseia06/onyxian
/plugin install onyxian@onyxian
/vault-bootstrap
```

The plugin ships the interview wizard. On first run it checks for the `onyxian` engine and, if it's missing, offers to install it for you (via `uv`, `pipx`, or `pip --user`, whichever you have) — so a Claude Code user never touches Python directly. The wizard then walks you through creating a new vault or adopting an existing one: it asks the questions, shows you the engine's plan verbatim, and applies only after you confirm. Nothing is written until you say yes.

### As a command-line tool

```
uv tool install onyxian      # or:  pipx install onyxian
```

`uv` and `pipx` are installers for Python command-line tools; each gives the tool its own isolated environment so it can't interfere with anything else on your machine. You don't need to know Python to use either. If you have neither, `python -m pip install --user onyxian` works too (on Windows, `py -m pip install --user onyxian` if `python` isn't found). Onyxian requires Python 3.11 or newer.

The package is called `onyxian`; the command it installs is `onyxian`. Check it worked:

```
onyxian --version
```

### From source

```
git clone https://github.com/odysseia06/onyxian && cd onyxian
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Quickstart: your first vault

The fastest start is a **profile** — a named module set with sensible presets:

```
onyxian init my-vault --answers student
```

Available profiles: `minimal` (core only), `student` (daily notes + academic), `phd-student` (adds the research-paper pipeline and reading), `fitness-focused`, `gamedev` (game wikis plus software projects), `musician`, `writer`, and `researcher-developer` (the full canonical example: daily notes, academic, research, reading, software projects, OSS tracking, and fitness).

Onyxian prints the full plan — every folder, template, Base view, and agent file it intends to create — and asks for confirmation before writing anything:

```
vault: 'My Vault' at my-vault
folder style: Title-Case-Hyphen; modules: core, academic, daily-notes
planned changes:
  + dir  Academic/Courses  (academic)
  + dir  Daily-Notes  (daily-notes)
  ...
  + Home.md (seeded)  (core)
  + Templates/Daily/Daily Note.md (managed)  (daily-notes)
  ...
  + .vault/config.yaml (seeded; yours to edit)
  + .vault/lock.json (the engine's ledger)
create this vault? [y/N]
```

(Abridged — the real plan lists every path.) `onyxian init` only works on a new or empty folder; if the folder already has notes in it, that's [adopt](#adopting-an-existing-vault)'s job, and `init` will refuse and say so. A pre-existing `.git` or `.obsidian` folder is fine.

Running `onyxian init my-vault` with no `--answers` also works: it asks for a vault name and folder-naming style and creates a core-only vault, which you grow afterwards with `onyxian add <module>` — each module asks its own questions (folder name, cadence) as you add it. The full guided experience with profile selection lives in the `/vault-bootstrap` wizard in Claude Code. You can also write your own answers file for a fully non-interactive run — see the [first day-zero story](#two-day-zero-stories) for an example.

### What you get

- One folder per enabled module, named per your answers (e.g. `Academic/`, `Daily-Notes/`).
- `Templates/` with per-domain templates that work as plain copies.
- `Home.md` — your home note. Seeded once, yours to rewrite.
- `Start-Here.md` — the no-AI tour: what's installed and what to do first.
- `Onyxian Assistant.md` — what the agent layer can do and what to say (if you use Claude Code).
- `.vault/config.yaml` and `.vault/lock.json` — Onyxian's intent and ledger (next section).
- `.claude/` — skills and agents for Claude Code (optional; the vault works without it).

### Open it in Obsidian

Open the folder as a vault (Obsidian: "Open folder as vault"). Then install the two community plugins Onyxian's templates use:

- **Tasks** powers the task queries (due, scheduled, overdue, carry-over) the domain modules use.
- **Templater** fills the `<% ... %>` placeholders in templates (today's date, the note title).

The vault already enables both in `.obsidian/community-plugins.json`, but the plugin code itself has to be downloaded once. With [Obsidian's command-line interface](https://obsidian.md/cli) you can do it without leaving the keyboard:

```
obsidian plugins:restrict off
obsidian plugin:install id=obsidian-tasks-plugin enable
obsidian plugin:install id=templater-obsidian enable
```

(`plugins:restrict off` is needed once on a fresh vault, because Obsidian starts in restricted mode.) Or do it in the app: Settings → Community plugins → Browse. Either way, then point Templater's template folder at `Templates`.

**Until the Tasks plugin is installed, the task-query blocks in daily notes and dashboards render as plain code blocks.** That's expected — they're queries waiting for their engine, not broken notes. Without Templater, the `<% ... %>` placeholders stay as literal text you can fill by hand. Nothing else degrades.

Finally, a health check never hurts:

```
onyxian doctor --vault my-vault
```

## How Onyxian thinks

The engine is a declarative reconciliation loop with four moving parts:

- **`.vault/config.yaml` — what you asked for.** Which modules, with which variables (folder names, cadences). Yours to edit by hand; hand-editing it and running `plan` is a fully supported workflow, equivalent to using the wizard.
- **`.vault/lock.json` — what Onyxian wrote.** Every file the engine has ever written, with its hash. Machine-maintained; you never touch it.
- **`onyxian plan` — the preview.** A read-only diff between intent and reality. Always safe to run.
- **`onyxian apply` — do it.** Executes exactly what plan showed, recording every write in the lockfile.

Every other command (`add`, `remove`, `update`) is ergonomics over this loop, and every mutating command takes `--dry-run`.

### Two kinds of Onyxian-written file — and everything else

- **Managed** files (templates, Base views, skills, agent files) are framework-owned. They update themselves as long as you leave them alone. The moment you customize one, it becomes yours: newer versions arrive beside it as a `*.new` file instead of overwriting your work.
- **Seeded** files (your home note, a fitness Strategy note, a course template's Overview) are written **once** as a starting point and never updated or removed by the engine. You own them from the moment they exist — even deleting one won't make Onyxian recreate it.
- **Everything else is invisible to Onyxian.** A file the engine didn't write is never written to, moved, renamed, or deleted. If a plan calls for a path where one of your files already sits, the action is reported as **blocked** and skipped — the engine tells you, and does nothing.

"Never clobbers" therefore means, concretely: re-running any command against an unchanged vault is a no-op; updates to files you edited become `*.new` deliveries; your own files block the engine rather than the other way around; and there is no `--force` flag anywhere that changes any of this.

## Adopting an existing vault

You don't need to start over. `onyxian adopt` brings a lived-in vault under management, and it is designed to be the safe path:

- **The dry run is read-only.** `onyxian adopt <vault> --dry-run` scans, maps, and prints — it writes nothing.
- **The plan is additive only.** The scan proposes *claims*: an existing `Fitness/` folder can be claimed as the fitness module's root by setting a variable — nothing is moved or renamed; the module's *new* assets simply land inside your existing structure. Only missing folders, templates, and views are planned. Existing files at seed paths (your own `Home.md`, an existing Strategy note) are recorded as yours and never replaced.
- **Ambiguity goes to a checklist, not to action.** A folder that half-matches two modules, or a file where a folder is expected, lands on a printed checklist for you to decide — the engine refuses to guess.
- **There is no fast path.** `adopt` has no `--yes`. In a terminal, you read the plan and type `adopt` to confirm. Non-interactively (scripts, agents), any review run — `--dry-run` included — prints an acceptance token derived from the exact plan shown; you apply with `onyxian adopt <vault> --accept <token>`. If the vault or your answers changed since that review, the token is rejected and you review again — that's the feature working.

Before adopting, **commit your vault to git** (or copy it somewhere). The engine is additive by contract, but a backup costs nothing and the docs will keep telling you this.

A typical session:

```
cd ~/notes && git add -A && git commit -m "before onyxian adopt"
onyxian adopt ~/notes --dry-run     # read-only: claims, plan, checklist
onyxian adopt ~/notes               # same review, then type "adopt" to apply
onyxian doctor --vault ~/notes
```

By default adopt enables the modules its scan recognized in your folders. To choose the set yourself, pass a profile or answers file — `onyxian adopt ~/notes --answers researcher-developer --dry-run` — and the scan's claims fill in whatever the answers leave unset.

## Everyday operations

`onyxian modules` needs no vault at all; the rest default to the current directory as the vault and take `--vault <path>` to run from elsewhere. Every mutating command takes `--dry-run` and `--yes`.

**See what exists:**

```
onyxian modules
```

Lists every available module with its summary, variables, and defaults.

**Enable a module:**

```
onyxian add fitness
```

Asks the module's questions (folder name, review cadence — defaults visible), pulls in dependencies automatically, shows the plan, and applies on your confirmation. Adding a module that's already enabled is a no-op. `onyxian add` also accepts a git URL or local directory to install a third-party module — you'll get a trust warning first, because a module is data, but a malicious template is still a social-engineering surface.

**Disable a module:**

```
onyxian remove fitness --dry-run    # see exactly what would happen first
onyxian remove fitness
```

Removal deletes **only** unmodified framework-owned files. Everything else is left behind and reported with a reason: seeded files ("yours from the day it was created"), files you modified ("it stays, untracked from here on"), files already gone. Folders the module created are pruned only if empty — anything holding your files stays. `core` cannot be removed, and a module that others depend on must wait until they're removed first.

**Pull newer module versions:**

```
onyxian update --dry-run            # what would change?
onyxian update                      # everything
onyxian update research             # just one module
```

Files you never touched are updated in place. Files you customized get the new version delivered as a `*.new` sibling and listed in an update report — zero overwrites, ever. `onyxian update` also refreshes any declared sources (like the pinned `obsidian-skills` package) and moves their pins forward.

**Check vault health:**

```
onyxian doctor
```

Read-only. Validates the config and the module dependency closure, renders the declared intent, and checks the lockfile against the disk — missing managed files, files you've customized, orphaned entries, and anything still pending — then suggests a command for whatever is off.

**Reshape by hand:** edit `.vault/config.yaml` directly (rename a root folder variable, add a module entry), then:

```
onyxian plan
onyxian apply
```

**Scaffold a software project** (if the `projects-software` module is enabled):

```
onyxian project new "My-Engine"
```

Creates a sibling of `_Project-Template` with the Devlog/Tasks/Research/Assets folders and a dated Overview to fill in.

For module authors there is also `onyxian module new <id>`, which scaffolds a module skeleton that validates out of the box — the [module authoring guide](module-authoring.md) walks through the whole thing.

## When an update meets your edits: `*.new` files

Say you rewrote `Templates/Daily/Daily Note.md` to your taste, and a later `onyxian update` ships an improved version. Onyxian will not overwrite your file. Instead you get:

```
Templates/Daily/Daily Note.md        <- yours, untouched
Templates/Daily/Daily Note.md.new    <- the new shipped version
```

and the update report says so explicitly. `onyxian diff` is the tool for living with these:

```
onyxian diff                                 # list every conflict pair in the vault
onyxian diff "Templates/Daily/Daily Note.md" # show what changed, as a unified diff
onyxian diff --resolve                       # walk each pair: see the diff, then choose
```

For every pair the menu is the same three choices — deliberately not a merge tool, because a merge that guesses is worse than a report that doesn't:

- **take-new** — adopt the shipped version wholesale. Your file is overwritten at your explicit request, the ledger records the new content, and the `.new` is cleaned up (unless you edited the `.new` itself, in which case it is left for you). Non-interactively: `onyxian diff <path> --take-new --yes`.
- **keep-mine** — decline this shipped version. The engine records exactly which version you turned down and stops re-offering it; the `.new` is cleaned up. The decline is per-version: when a future release ships *different* content for that file, the offer resumes — declining one update never means missing all of them. Non-interactively: `onyxian diff <path> --keep-mine --yes`.
- **leave** — decide later. The pair keeps showing up in `onyxian diff`, and the delivered `.new` sits quietly without being re-written while its content is current.

Hand-merging (pulling some hunks of the new version into your file) is still yours to do: `onyxian diff <path>` shows exactly what changed, you edit your file in Obsidian, then resolve the pair with **keep-mine** — your merged file is your version. If instead you edit your file to match the shipped content exactly, the next `onyxian apply` records it and the file updates normally again from then on.

## The agent layer (optional)

Everything above works with no AI anywhere. If you use Claude Code, each enabled module additionally installs skills and a per-domain agent under `.claude/`:

- `.claude/skills/` — instruction packages the agents lean on: the vault's conventions (`vault-conventions`), the safe-operations contract (`vault-operations`), and one skill per workflow (`exam-prep`, `paper-pipeline`, `fitness-review`, `reading-triage`, `daily-notes`, `task-capture`, `devlogs`, `oss-tracking`, `editorial-pipeline`, `practice-loop`, `game-wiki`). You never invoke these by name; the agents read them.
- `.claude/agents/` — one scoped agent per domain module. `daily-planner` (say "plan my day", "close out the day"), `study-coach` ("build a study plan from this syllabus"), `research-librarian` (files a typed paper summary from a PDF), `reading-triager`, `fitness-coach`, `project-steward` ("we decided X because Y" becomes a decision-log entry), `oss-scout`, `blog-editor` ("capture this post idea"), `practice-coach` ("log today's practice session"), `game-steward` ("capture this game idea"). Task capture works from a plain sentence: "add a task to fix this by Friday".
- `CLAUDE.md` — written once, then yours — imports a generated `.claude/onyxian.md` that Onyxian keeps current as your module set changes, so a plain request reaches the right agent the moment you open the vault.
- `Onyxian Assistant.md` in the vault lists your installed agents, what each does, and example phrases.

These agents don't only suggest — they operate the live vault through Obsidian's official command-line interface, following one write contract (the `vault-operations` skill): additive by default, look before you write, escalate rather than guess.

**An honest word about scoping.** Each agent's definition declares what it may read and where it may write (for example, daily-planner: "You may write only within: `Daily-Notes/**`"), and instructs the agent to propose-and-ask for anything outside that lane. These boundaries are documented conventions the agents are built to follow — they are *instructions*, not a mechanical sandbox. Nothing at the filesystem level physically prevents an agent runtime from writing elsewhere. In practice the contract holds well, and it's reinforced at every layer of the instructions, but you should know what kind of guarantee it is. (The engine's own never-clobber guarantee — locks, `*.new`, blocked writes — *is* mechanical.) Closing that gap where it can be closed is tracked in [issue #11](https://github.com/odysseia06/onyxian/issues/11).

**A recovery net: vault checkpoints.** Because scope is advisory, Onyxian offers an opt-in safety net that makes any stray write cheap to see and undo. Run `onyxian checkpoint` to snapshot the whole vault into a private git history kept under `.vault/checkpoints/` — a *separate* git repository, so it never touches a `.git` of your own, and needs no git repo to exist. `onyxian checkpoint list` shows past snapshots and `onyxian checkpoint diff` shows what changed since the last one. Enable it during setup (or set `framework.checkpoints: true` in `.vault/config.yaml`) and, with Claude Code, Onyxian wires a `SessionStart` hook so a checkpoint is taken automatically whenever a session starts — nothing to remember. It's a net, not a sandbox: if `git` isn't installed the command simply warns and moves on, and the vault is never affected.

**Optional scope hooks (Claude Code).** You can turn a chunk of that convention into machinery. Enable it during setup (or set `framework.scope_hooks: true` in `.vault/config.yaml`) and, under Claude Code, Onyxian installs a `PreToolUse` hook on each agent plus a `.claude/onyxian-scopes.json` listing every agent's write globs. Before a command runs, the hook reads the `obsidian` CLI target and answers three ways: a write it can **prove** lands inside the agent's scope passes through untouched; one it can **prove** lands outside is **denied**; anything it **can't** prove is turned into an **ask** — the escalation you'd want anyway, made automatic. It only ever tightens: a read-only or non-`obsidian` command is never auto-approved by the hook.

The honest limits, stated plainly: the hook can prove the target of `obsidian create path="…"` or `append path="…"`, but not of `file="Note Name"` (that wikilink-style name is resolved *inside* Obsidian, where a client-side hook can't see it) or of a command that names no target (Obsidian's silent active-note fallback) — both of those become **ask**, not a false allow. And because the write happens in the Obsidian process, nothing at the shell level can police a process that writes vault files without going through the CLI. Closing those fully needs a per-invocation path restriction in the obsidian CLI itself — an upstream ask, not something a hook can fake. So scope hooks are a strong nudge with a known ceiling, not a sandbox; the recovery net for what slips through is version control of your own.

During setup you'll also be offered `kepano/obsidian-skills`, the official Obsidian-format skills (markdown, Bases, web clipping via defuddle). Onyxian installs it from upstream into `.claude/skills/`, pinned to a commit recorded in your config; `onyxian update` moves the pin forward. It's optional, and an install failure degrades to a warning, never a broken vault.

Other agent runtimes (Codex, OpenCode, or anything generic) get skills-level support: declare the runtime in `.vault/config.yaml` under `framework.runtimes` and Onyxian generates an `AGENTS.md` in the vault embedding the conventions, the agent roster, and skill references. Claude Code is the first-class experience; the rest is honest but thinner.

And the exit is always open: delete `.claude/` entirely and the vault still works as plain files. The agent layer is power, never a dependency.

## Module reference

Twelve modules ship today. Dependencies are automatic (everything depends on `core`), and every folder root is a variable — the defaults below are just defaults.

| Module | What it gives you | Variables (default) | Agent |
|---|---|---|---|
| `core` | The shared conventions, the `Templates/` root, the home note, and the base skills every module builds on. | — | — |
| `daily-notes` | One note per day with task-rollover queries (due, scheduled, overdue, carry-over, captured) and natural-language task capture. | `root` (`Daily-Notes`), `granularity` (`YYYY/MM`, `YYYY`, or `flat`) | `daily-planner` |
| `academic` | Courses from a copy-per-course template subtree (lectures, assignments, readings); exam prep tracked through a study Base. | `root` (`Academic`) | `study-coach` |
| `fitness` | Training plans and logs, nutrition driven by a Strategy note you own, bodyweight and measurement tracking, weekly/monthly reviews. | `root` (`Fitness`), `review_cadence` (default `both`; or `weekly` / `monthly`) | `fitness-coach` |
| `research` | A typed paper pipeline: PDF to summary to topic links, named by citation key, over a multi-view Paper Library Base. | `root` (`Research`; nested roots like `Academic/Research` work) | `research-librarian` |
| `reading` | An Inbox → Articles → Evergreen pipeline, with web clipping and a status-driven Base over the whole flow. | `root` (`Reading`) | `reading-triager` |
| `projects-software` | Per-project devlogs, decision logs, typed task notes with a status Base, and subsystem notes. | `root` (`Projects/Software`) | `project-steward` |
| `projects-gamedev` | Game projects as living wikis: design, mechanics, worldbuilding, content, devlog — from a copy-per-game template, with a design-board Base. | `root` (`Projects/Game-Dev`) | `game-steward` |
| `oss` | Open-source tracking from watchlist to contribution, with staleness-aware Bases and a one-copy promote/demote rule. | `root` (`Projects/Software`) | `oss-scout` |
| `music` | Theory, practice logs with a Base, composition, production, listening notes, and copy-per-piece projects. | `root` (`Music`) | `practice-coach` |
| `writing` | An editorial blog pipeline: ideas to drafts to published, with series, a pipeline Base, and an editorial calendar. | `root` (`Writing/Blog`) | `blog-editor` |
| `ai-workspace` | A prompts library and an agent-skills workbench — plain notes, no special schema. | `root` (`AI-Workspace`) | — |

Honesty notes: `ai-workspace` currently ships structure only — folders and a dashboard note, **no skills or agents yet**. `writing`, `music`, and `projects-gamedev` now ship their agent layers (`blog-editor`, `practice-coach`, and `game-steward` with their skills). `oss` deliberately defaults its root to the same folder as `projects-software`, so OSS tracking nests inside your software-projects area; change either variable if you want them apart.

## Two day-zero stories

### A PhD student, empty folder

She installs the CLI and starts from the profile closest to her life:

```
uv tool install onyxian
onyxian init Thesis-Vault --answers phd-student --dry-run
```

The plan scrolls past — course folders, a paper pipeline, a reading inbox, daily notes, templates, Bases, four agents — and nothing is written yet. She wants one change: `Academic` should be called `University`. A profile can't rename folders, so she writes a short answers file instead and runs it for real:

```yaml
# answers.yaml
vault: { name: "Thesis Vault" }
modules:
  core: {}
  daily-notes: { granularity: "YYYY/MM" }
  academic: { root: "University" }
  research: { root: "University/Research" }
  reading: {}
```

```
onyxian init Thesis-Vault --answers answers.yaml
```

Two minutes later her vault has a copy-per-course template subtree, a paper pipeline, a reading inbox, and a `Start-Here.md` telling her what to do first. She opens it in Obsidian, installs Tasks and Templater (three `obsidian` commands, above), copies `_Course-Template` to `MATH-501 Measure Theory`, and starts today's note from `Templates/Daily/Daily Note.md`. She never opens the repository.

### The developer with five years of notes

He has a lived-in vault: `Fitness/`, `Academic/`, `Daily-Notes/`, and years of project notes. He commits it to git, then runs a read-only scan:

```
cd ~/vault && git add -A && git commit -m "before onyxian"
onyxian adopt ~/vault --dry-run
```

The scan claims his existing `Fitness/`, `Academic/`, and `Daily-Notes/` folders for the matching modules — via variables, nothing moved or renamed. The plan is purely additive: a few missing Bases, some templates, agents for the modules he enabled. His own `Home.md` is claimed as a seed, recorded as his, never replaced. Two ambiguous folders land on the checklist instead of being touched. He reads the plan, reruns without `--dry-run`, types `adopt` at the prompt, and finishes with:

```
onyxian doctor --vault ~/vault
```

His vault is under management the same day, and `git status` confirms what the plan promised: new files only.

## Troubleshooting and FAQ

**`onyxian: command not found` right after installing.** The install directory isn't on your PATH yet. With uv, run `uv tool update-shell`; with pipx, `pipx ensurepath`; with `pip --user`, add your user scripts directory to PATH (on Linux/macOS usually `~/.local/bin`). Then open a new terminal and try `onyxian --version` again.

**Task queries show as code blocks.** The Tasks community plugin isn't installed (being *enabled* in the vault config isn't enough — the plugin code must be downloaded once). Install it: `obsidian plugin:install id=obsidian-tasks-plugin enable`, or Settings → Community plugins → Browse → Tasks. On a fresh vault run `obsidian plugins:restrict off` first.

**Templates come out with raw `<% ... %>` placeholders.** Templater isn't installed, or its template folder isn't set. Install it (`obsidian plugin:install id=templater-obsidian enable`) and point Templater's template-folder setting at `Templates`. Without Templater the placeholders are simply text to replace by hand — the templates still work as plain copies.

**A `SomeFile.md.new` appeared next to my note.** You customized that managed file, and an update shipped a newer version — this is the never-clobber guarantee doing its job. Run `onyxian diff SomeFile.md` to see what changed, then `onyxian diff --resolve` (or `--take-new` / `--keep-mine` non-interactively) to settle it. See [`*.new` files](#when-an-update-meets-your-edits-new-files).

**The plan says `BLOCKED`.** A file Onyxian doesn't own sits where the plan wants to write. The engine will not touch it — move or rename your file if you want the framework asset there, or just leave it; blocked items are reports, not errors.

**`init` refuses my folder.** `init` only works on new or empty folders (a pre-existing `.git` or `.obsidian` is tolerated). If the folder has notes in it, use `onyxian adopt` — that's exactly what it's for.

**How do I uninstall or back out?** Three levels, from mild to total:

1. *Drop a module:* `onyxian remove <module>` — deletes only unmodified framework files, keeps everything of yours, and reports what it left behind.
2. *Drop the AI layer:* delete `.claude/` (and `AGENTS.md` if you declared other runtimes). The vault keeps working; that's a design guarantee, not an accident.
3. *Drop Onyxian entirely:* delete `.vault/` (the config and ledger — plus any third-party modules staged under `.vault/modules/`) along with `.claude/`. Everything Onyxian manages lives inside the vault, so what remains is a plain Obsidian vault of plain Markdown files, fully yours. You lose the ability to update or cleanly remove modules later, nothing else. Then `uv tool uninstall onyxian` or `pipx uninstall onyxian` removes the CLI itself.

**Can I sync my vault between two machines (Obsidian Sync, iCloud, Syncthing)?** The notes, absolutely. Onyxian commands, from **one machine only** — or commit `.vault/` to git and move it that way. `.vault/lock.json` is a single-writer ledger: if two machines both run `apply` or `update` and a sync service carries the results, the ledger can fork (the tell-tale is a "conflicted copy" of `lock.json` — `onyxian doctor` flags these; if you see one, stop and reconcile before running anything else). Obsidian Sync has an extra wrinkle: it doesn't sync hidden folders, so a second machine won't see `.vault/` at all and will treat the vault as unmanaged. Git handles both problems, which is one more reason the docs keep telling you to commit your vault.

**Windows notes.** Windows is a first-class platform and is tested in CI. Paths and line endings are normalized, and Onyxian never creates symlinks in your vault (Windows and sync tools both punish them). If `python` isn't on your PATH, use `py -m pip install --user onyxian`. If the `obsidian` CLI isn't found, Obsidian may still ship it — look for `%LOCALAPPDATA%\Programs\Obsidian\Obsidian.com`.

**Where do I report a bug or ask for a module?** [github.com/odysseia06/onyxian](https://github.com/odysseia06/onyxian) — and if you want to build a module yourself, `onyxian module new <id>` plus the [module authoring guide](module-authoring.md) is the whole on-ramp.

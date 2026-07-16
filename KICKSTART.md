# `Onyxian` — Project Charter & Master Blueprint

> **What this file is.** The single source of truth for building `Onyxian`. It is handed to Claude Code — and to specialized subagents — as the steering document. It defines the vision, the invariants, the system architecture, the module system, the skills and agent roster, the install and update experience, the quality bar, and the build order. An implementing agent reading only this file should be able to build the right thing, in the right order, without inventing policy.
>
> **Terminology guard.** In this repository, **bootstrap** always means the _product feature_ that scaffolds an end-user's vault (`init`, `adopt`). This document is the _kickstart_ — the blueprint for the people and agents building the product. Do not conflate the two.
>
> **Status (v1.1.0, 2026-07).** Shipped through M4. The charter is kept honest against the shipped engine: where the build diverged from the original plan, the text says so in place — divergences are labeled, not papered over. User-facing documentation lives in README.md and docs/user-guide.md; this file is the deep read on intent and invariants.

---

## 0. TL;DR for an implementing agent

You are building an **open-source, AI-native framework for Obsidian vaults**. It turns a vault into a long-lived personal knowledge system — life, research, and engineering in one place — composed from **opt-in modules**. The defining property is **tailorability**: a cryptography researcher, a biology PhD student, a musician, and a product manager are all served by the same framework with different module sets, different folder names, and different agents. It is _not_ a "here is my vault, init on it" template, and _not_ another monolithic productivity starter.

Three rules tower over everything else:

1. The vault must be fully usable **without any LLM**. Agents amplify; they are never load-bearing.
2. The framework must be **additive and idempotent**: it never deletes or overwrites a user's files, and every file it writes is tracked so it can be safely updated or removed later.
3. **Tailoring is the product.** Nothing about the maintainer's personal setup is hardcoded; it is the canonical _example_, never the default.

Obsidian-format literacy comes from **depending on** `kepano/obsidian-skills` — never vendoring it. On that substrate the project ships its own module assets (folders, templates, `.base` views), first-party skills, a roster of scoped subagents, and a bootstrap-and-update engine built on a declarative reconciliation loop.

Read §3 (Principles), §4 (Architecture), §5 (Modules), and §8 (Write & update contract) before writing code. Build in the order of §14.

---

## 1. Vision & Positioning

### 1.1 What it is

A composable framework that scaffolds and then _operates_ a personal Obsidian vault. The user picks the domains they care about; the framework wires up folders, frontmatter conventions, Bases views, templates, skills, and per-domain agents for each — and can later add, update, or remove modules without damaging anything the user wrote or customized. The vault is a permanent personal repository with endless expansion surface, not a one-time scaffold.

### 1.2 The person it serves

The canonical example persona — _example_, not default — is a cryptography researcher who is also a working developer. They want a typed research-paper pipeline, course and exam management, an OSS watchlist-to-contributing workflow, per-project engineering notes and devlogs, fitness tracking driven by a strategy note, and daily planning. They want to _skip_ everything they don't use. The framework must serve this person completely while serving a musician or a product manager equally well through a different module set. If a design choice only makes sense for the example persona, the design choice is wrong.

### 1.3 The niche

_Tailoring is the product._ Most comparable projects ship a fixed structure and ask the user to adapt to it. `Onyxian` inverts this: structure is composed per user, named per user, and grows with the user. The second-order consequence is that **safe evolution** — adopting an existing vault, updating modules years later, removing what stopped being useful — matters as much as day-one scaffolding, and is designed in from the start rather than bolted on.

### 1.4 Honest read on the field

The "Obsidian + AI agent" space is crowded: multiple community starter repos exist, including wizard-based bootstraps; `kepano/obsidian-skills` is official, popular, and excellent at what it covers; tutorials abound. _(Field surveyed early June 2026 — re-verify before writing positioning copy; this landscape moves monthly.)_ The project does not win on novelty of category. It wins on:

1. **Modularity** — opt-in domains with declared dependencies and per-module variables, not a fixed tree.
2. **Bases-first data layer** — `.base` views over typed frontmatter instead of hand-maintained MOC/index lists.
3. **A per-domain agent roster** — scoped subagents installed only for enabled modules, each with explicit read/write boundaries.
4. **Safe adoption of existing vaults** — `adopt` works additively on a real, lived-in vault, behind a mandatory reviewed plan.
5. **An update story** — installed modules upgrade without overwriting user-modified files. Most projects in this niche have no update semantics at all.

---

## 2. Non-goals

These are enforceable in review. A pull request that drifts into any of them is rejected by citing this section.

- **Not a hosted service.** No SaaS, no accounts, no sync, no backup product.
- **Not an Obsidian plugin.** No `.obsidian` plugin code. The framework operates through plain files, a small CLI, and agent runtimes. (Driving the official Obsidian CLI via the `obsidian-cli` skill is in scope.)
- **Not an LLM application.** No chat UI, no model wrapper, no API keys handled by this project.
- **Not a PKM methodology.** No Zettelkasten or PARA dogma. Conventions here are structural (frontmatter, naming, file placement), never ideological.
- **Not a redistribution vehicle.** Third-party skills are installed from upstream, never copied into this repo.
- **No telemetry.** No analytics, no phone-home, no network calls beyond what the user's config declares or the user explicitly asks for by name (installing a module from a git URL with `add`, `update` refreshing a pinned upstream).
- **Not "the maintainer's vault as a product."** The maintainer's setup informs the example vault and the default presets; it is never the mandatory shape.

---

## 3. Design principles

Numbered invariants. Violating one is a bug, not a tradeoff.

- **P1 — Files are the product.** Everything lives as plain text in the user's vault: Markdown, YAML, `.base`, `.canvas`. No databases, no opaque state. The user can read, edit, move, or delete anything by hand at any time, and the framework must tolerate that.
- **P2 — Agent-optional.** Every workflow has a manual path. Templates work as plain copies. Bases views work without any agent. Deleting `.claude/` must cost the user convenience, never function.
- **P3 — Additive and idempotent.** The framework never deletes or overwrites user files. Re-running any command against an unchanged vault is a byte-identical no-op. Every framework write is recorded in the lockfile (§8).
- **P4 — Tailoring over defaults.** Folder names, cadences, granularities, and structures are module variables with sensible defaults. Persona assumptions never appear in code or assets — only in profiles, which are data.
- **P5 — Bases-first.** Each module answers its "what do I have, what's in flight" questions with `.base` views over typed frontmatter. A hand-maintained index list in a framework asset is an anti-pattern.
- **P6 — Depend, don't vendor.** `kepano/obsidian-skills` is installed from upstream at bootstrap, pinned to a commit recorded in config. Nothing of it is copied into this repository.
- **P7 — Runtime-portable, Claude Code first-class.** Module instructions ship as Agent-Skills-spec skills usable by any compatible runtime. Claude Code additionally gets subagents and slash commands. Other runtimes get skills plus a generated `AGENTS.md` through adapters.
- **P8 — Verifiable.** A lockfile accounts for every managed file. Every mutating command supports `--dry-run`. A `doctor` command validates vault state against declared intent.
- **P9 — Honest documentation.** Externally observable facts in docs carry a verified-on date. Uncertain claims are flagged as uncertain. This charter follows its own rule (Appendix A).

---

## 4. System architecture

### 4.1 The three layers

The system is three layers, and **each layer is useful without the layer above it**:

1. **Engine** (deterministic, no AI). A small CLI implementing a declarative reconciliation loop: `vault.config` declares _intent_, `lock.json` records _state_, `plan` computes the difference, `apply` reconciles it. Every other command is sugar over this loop. The engine handles scaffolding, locking, updating, removal, and validation.
2. **Modules** (declarative content, no code). Self-describing folders of assets — folder trees, templates, `.base` views — plus a manifest declaring variables, dependencies, skills, and agents. Modules contain no executable logic.
3. **Agent surface** (optional amplifier). First-party and third-party skills, the subagent roster, and per-runtime adapters. Everything in this layer can be absent and the vault still works (P2).

### 4.2 Repository layout (monorepo)

```
<repo>/
├─ KICKSTART.md                  # this charter
├─ README.md   LICENSE (MIT)   CONTRIBUTING.md   RELEASING.md
├─ core/
│  ├─ onyxian/                   # the engine: plan / apply / lock / doctor (importable package)
│  │                             # — adapter code lives here too (adapters.py), not under adapters/
│  └─ conventions/               # core frontmatter schema, naming rules, core templates
├─ modules/
│  └─ <module-name>/
│     ├─ module.yaml             # manifest (§5.2)
│     ├─ assets/                 # folders, templates, .base files ({{variable}} substitution)
│     ├─ skills/                 # module-specific Agent Skills
│     ├─ agents/                 # generalized agent definitions (§7)
│     └─ docs/
├─ profiles/                     # named module sets + preset answers — YAML, data not code
├─ adapters/
│  └─ claude-code/               # runtime notes only; the per-runtime rendering is core/onyxian/adapters.py
├─ plugin/                       # Claude Code plugin — GENERATED by tools/build_plugin.py, never hand-edited
├─ docs/                         # user guide + assets
├─ examples/                     # reference vaults — GENERATED by the engine in CI, never hand-edited
├─ tests/                        # engine unit tests, golden-file tests, e2e fixtures
└─ tools/                        # dev and CI scripts
```

### 4.3 What lands in the user's vault

```
<vault>/
├─ .vault/
│  ├─ config.yaml                # instance intent (§4.4) — user-editable
│  └─ lock.json                  # managed-file ledger (§8) — machine-maintained
├─ .claude/                      # claude-code runtime only: skills/ agents/ commands/
├─ AGENTS.md                     # generated for non-Claude runtimes (adapter output)
├─ Templates/                    # core + per-module templates
└─ <module folders>              # per enabled module, named per user variables
```

Runtime installs that live _outside_ the vault (e.g. Codex's `~/.codex/skills`) were designed to be written only with explicit consent during bootstrap and recorded in the lockfile with `location: runtime` so they can be audited and removed (§8.1). **As shipped, the engine never writes outside the vault** — every runtime gets its skills inside `.claude/skills/` (§6.1, §7.4) — so `location: runtime` is reserved in the model and unused today.

### 4.4 Instance config — `.vault/config.yaml`

```yaml
framework:
  version: "0.1.0"
  runtimes: [claude-code]            # claude-code | codex | opencode | generic
vault:
  name: "My Vault"
naming:
  folder_style: Title-Case-Hyphen    # Title-Case-Hyphen | kebab-case | Spaces
modules:
  core:        { version: "0.1.0" }
  daily-notes: { version: "0.1.0", vars: { root: "Daily-Notes", granularity: "YYYY/MM" } }
  academic:    { version: "0.1.0", vars: { root: "Academic" } }
  fitness:     { version: "0.1.0", vars: { root: "Fitness", review_cadence: both } }
sources:
  obsidian-skills:
    repo: "https://github.com/kepano/obsidian-skills"
    pin: "<commit-sha>"              # set at install; changed only by `update`
```

The config is the user's to edit. Hand-editing it and running `plan` is a fully supported workflow, equivalent to using the wizard.

---

## 5. The module system

### 5.1 What a module is

A **module** is a self-describing folder that provides some subset of: vault folders, templates, `.base` views, skills, and agent definitions for one domain. Modules declare dependencies (`core` is required by everything), expose **variables** answered during the interview (or supplied in an answers file), and are installed, updated, and removed only through the engine so that every file is accounted for. Modules contain no executable code: a module is reviewable by reading it.

### 5.2 Manifest schema — `module.yaml`

|Field|Type|Meaning|
|---|---|---|
|`name`|string|unique module id, kebab-case|
|`version`|semver|module version; drives update planning|
|`summary`|string|one-paragraph description shown in the interview|
|`depends`|list|module ids that must be enabled first|
|`conflicts`|list|module ids that cannot coexist (rare; justify in docs)|
|`variables`|list|interview questions: `key`, `prompt`, `type` (string/choice/bool), `options`, `default`|
|`provides.folders`|list|folder paths to create, `{{variable}}`-substituted|
|`provides.templates`|list|template files installed under `Templates/`|
|`provides.bases`|list|`.base` views installed into module folders|
|`provides.skills`|list|skill ids shipped by this module|
|`provides.agents`|list|agent ids shipped by this module|
|`seeds`|list|files created once as starting points, never updated (§8.2)|
|`post_install`|string|human instructions surfaced after apply|

**Schematic example** — a deliberately simplified illustration of the manifest shape, not a copy of the shipped module. The real fitness manifest (`modules/fitness/module.yaml`, v0.2.1 at this writing) has grown well past this: more folders (Nutrition and Health subtrees, progress photos), different seeds (a Dashboard, Goals, and the Strategy note under Nutrition), and different Base paths. The schema is what this example teaches; the shipped file is the reference.

```yaml
name: fitness
version: 0.1.0
summary: Training logs, health and nutrition tracking, periodic reviews —
  driven by a user-owned Strategy note rather than hardcoded targets.
depends: [core]
variables:
  - key: root
    prompt: "Folder name for the fitness domain"
    default: "Fitness"
  - key: review_cadence
    prompt: "Review cadence"
    type: choice
    options: [weekly, monthly, both]
    default: both
provides:
  folders:
    - "{{root}}/Training/Logs"
    - "{{root}}/Training/Plans"
    - "{{root}}/Training/Exercises"
    - "{{root}}/Health"
    - "{{root}}/Nutrition"
    - "{{root}}/Reviews"
    - "{{root}}/Tracking"
    - "{{root}}/Assets"
  templates: ["Templates/Fitness/*.md"]
  bases:
    - "{{root}}/Tracking/Training-Log.base"
    - "{{root}}/Tracking/Reviews.base"
  skills: [fitness-review]
  agents: [fitness-coach]
seeds:
  - "{{root}}/Strategy.md"
post_install: |
  Fill in your Strategy note before the first review cycle; the fitness-coach
  agent reads targets from it and only from it.
```

### 5.3 Variables & templating

Substitution is deliberately primitive: `{{module.key}}` string replacement in paths and asset contents, resolved once at apply time from config. No conditionals, no loops, no logic in assets — if an asset needs logic, it is two assets and a variable choosing between them. This keeps modules reviewable and diffs predictable.

### 5.4 Module roster

|Module|Provides (essence)|Ships in|
|---|---|---|
|`core`|conventions, `Templates/` root, home note, config + lock|M0|
|`daily-notes`|`Daily-Notes/<granularity>`, daily template, task-rollover conventions|M2|
|`academic`|Courses with a course-template subtree (Lectures, Assignments, Exam-Prep, Readings, Notes, Assets), additional-notes area|M2|
|`fitness`|Training / Health / Nutrition / Reviews / Tracking, strategy-note-driven|M2|
|`research`|Paper-PDFs, Paper-Summaries, Topic-Notes, Literature-Maps, Open-Questions, Reading-Lists; typed paper pipeline|M3|
|`reading`|Inbox → Articles → Evergreen pipeline; web clipping via `defuddle`|M3|
|`projects-software`|per-project subsystem notes, devlogs, decision logs|M3|
|`projects-gamedev`|project wiki + Logs / Research / Thoughts|M4|
|`oss`|Watchlist → Contributing workflow|M4|
|`music`|Composition / Production / Theory / Practice / Listening|M4|
|`writing`|Blog Drafts → Published, Ideas, Series, Research|M4|
|`ai-workspace`|prompts library, agent-skills workbench|M4|

> [!warning] Asset reality check
> Real module content must be generalized from the maintainer's actual templates, `.base` files, and skills. At charter time the build has the vault _tree_ and `CLAUDE.md` only. M2 cannot start from generic stand-ins — sanitized source assets are a blocking owner input (§17).

### 5.5 Profiles

A profile is a named module set with preset answers — pure data:

```yaml
# profiles/phd-student.yaml
name: phd-student
modules: [core, daily-notes, academic, research, reading]
presets:
  daily-notes: { granularity: "YYYY/MM" }
```

Shipping a new profile must never require code. Initial roster: `phd-student`, `researcher-developer` (the canonical example), `student`, `fitness-focused`, `writer`, `minimal`.

---

## 6. Skills layer

### 6.1 Third-party substrate

`kepano/obsidian-skills` supplies Obsidian-format literacy: `obsidian-markdown`, `obsidian-bases`, `json-canvas`, `obsidian-cli`, `defuddle`. Verified 2026-06-10: the repository is MIT-licensed (~35k stars), follows the **Agent Skills specification** (agentskills.io) so the skills are usable by any compatible agent — Claude Code, Codex, and OpenCode are named explicitly — and its README documents these install paths:

|Runtime|Documented path|
|---|---|
|Claude Code|`/plugin marketplace add kepano/obsidian-skills` → `/plugin install obsidian@obsidian-skills`|
|Any (npx)|`npx skills add https://github.com/kepano/obsidian-skills`|
|Codex|copy `skills/` into `~/.codex/skills`|
|OpenCode|clone the full repo into `~/.opencode/skills/obsidian-skills`|

As shipped, bootstrap does not execute those per-runtime paths: the engine installs the pinned skills into the vault's own `.claude/skills/`, under the full §8 write contract, **for every runtime** — the skills travel with the vault, stay in the lockfile, and one install path serves all runtimes. Runtime-side installs (copying into `~/.codex/skills`, cloning into `~/.opencode/skills`) are **future work, never built**; the table above records upstream's documented paths as facts about the world for when that work happens, and `location: runtime` (§8.1) is the reserved lockfile mechanism for it. The pin still lives in `sources.obsidian-skills.pin`; re-verify upstream's paths at build time (P9).

### 6.2 First-party skills

- `vault-bootstrap` — the interview wizard itself, implemented _as a skill_ plus a slash command. The wizard being a skill keeps the bootstrap runtime-portable and dogfoods the system from day one.
- `vault-conventions` (core) — the frontmatter, naming, and linking rules any agent must follow when writing into the vault. Humans read the same document in `core/conventions/`; one source of truth, two audiences.
- Module skills, one per workflow: `exam-prep` (academic), `paper-pipeline` (research), `fitness-review` (fitness), `reading-triage` (reading), and so on per the roster.

---

## 7. Agent roster

### 7.1 Design rules

- Agents are **generalized definitions** in module folders, rendered per-runtime by adapters. Claude Code: `.claude/agents/*.md` subagents and slash commands. Other runtimes: sections of the generated `AGENTS.md`.
- **Least privilege.** Every agent declares `scope.read` and `scope.write` as path globs over _resolved_ module variables. Writing outside declared scope is a defect.
- **Escalate, don't improvise.** Each definition lists conditions that end autonomous action and surface a question to the user.
- Agents are installed only when their module is enabled, and removed with it.

### 7.2 Roster

|Agent|Module|Mission (one line)|
|---|---|---|
|`vault-curator`|core|**not built — future work.** conventions enforcement, link hygiene, frontmatter validation, periodic vault health report. The deterministic slice of this mission shipped as `onyxian doctor` instead; the eight agents below are the shipped roster (see the user guide)|
|`daily-planner`|daily-notes|morning scaffold, task rollover, end-of-day review|
|`study-coach`|academic|study and exam plans from syllabus, notes, and deadlines; spaced-repetition scheduling into Exam-Prep|
|`fitness-coach`|fitness|log analysis against the user's Strategy note; periodic reviews; outputs carry a not-medical-advice disclaimer baked into the definition|
|`research-librarian`|research|paper intake: PDF → summary → topic links → reading-list and Bases updates|
|`reading-triager`|reading|inbox triage, clipping via defuddle, evergreen promotion|
|`project-steward`|projects-software|devlog and decision-log capture, subsystem note upkeep|
|`oss-scout`|oss|watchlist monitoring → contribution candidates|
|`blog-editor`|writing|idea capture and pipeline upkeep; propose-and-confirm promotions along Ideas → Drafts → Published|

### 7.3 Example definition — `modules/academic/agents/study-coach.yaml`

```yaml
name: study-coach
module: academic
scope:
  read:  ["{{academic.root}}/**", "{{daily_notes.root}}/**"]
  write: ["{{academic.root}}/Courses/*/Exam-Prep/**",
          "{{academic.root}}/Courses/*/Notes/**"]
skills: [obsidian-markdown, obsidian-bases, exam-prep]
mission: >
  Build and maintain study plans from syllabi, lecture notes, and assignment
  deadlines. Generate spaced-repetition schedules into Exam-Prep. Never modify
  the user's lecture notes; produce derived notes alongside them.
escalate_when:
  - deadline information conflicts across notes
  - any operation would delete or restructure existing files
```

### 7.4 Adapter contract

An adapter is a pure function: **(resolved module set, config) → runtime artifacts.**

|Adapter|Output|
|---|---|
|`claude-code`|skills → `.claude/skills/`, agents → `.claude/agents/`, commands → `.claude/commands/`|
|`codex`|skills → `.claude/skills/` (in-vault, same §8 contract), generated `AGENTS.md` in vault|
|`opencode`|skills → `.claude/skills/` (in-vault, same §8 contract), generated `AGENTS.md` in vault|
|`generic-agentsmd`|`AGENTS.md` in vault embedding conventions, roster, and skill references|

As shipped, every adapter writes inside the vault: non-Claude runtimes read the same `.claude/skills/` tree (Agent-Skills-spec skills are runtime-portable) plus the generated `AGENTS.md`. Runtime-side installs — copies into `~/.codex/skills`, clones into `~/.opencode/skills/`, recorded with `location: runtime` — are explicitly future work (§6.1); no engine code writes outside the vault today. Runtime conventions churn quickly; adapters exist precisely to quarantine that churn. Pre-1.0, only Claude Code carries a first-class promise — the rest are skills-level support (D9).

---

## 8. Write, lock & update contract

This section is load-bearing. Treat it with the seriousness of look-ahead-bias prevention in a backtester: get it wrong and everything downstream is quietly poisoned.

### 8.1 The lockfile — `.vault/lock.json`

Every file the engine writes gets an entry:

```json
{ "path": "Fitness/Tracking/Training-Log.base",
  "sha256": "…",
  "module": "fitness",
  "module_version": "0.1.0",
  "kind": "managed",
  "location": "vault" }
```

`location` is `vault` or `runtime` (files installed outside the vault, e.g. Codex skill copies), so external writes are auditable and reversible. As shipped, `runtime` is reserved and unused — no engine code writes outside the vault (§6.1, §7.4); every entry today says `vault`.

### 8.2 Three classes of file

- **`managed`** — framework-owned: templates, `.base` views, skills, agent files, generated `AGENTS.md`. Updatable under the rule below.
- **`seeded`** — created once as a starting point (example notes, the fitness Strategy stub, the home note). Never updated, never removed by the engine. The user owns them from the moment they exist.
- **user files** — everything not in the lockfile. The engine must never write to, move, rename, or delete them. There is no flag that overrides this.

### 8.3 Update and removal semantics

- `update` replaces a `managed` file **only if** its on-disk hash still matches the lockfile — i.e. the user never touched it. If the user modified it, the new version is written as a `*.new` sibling and listed in the update report. No silent overwrites; no three-way merges (a merge that guesses is worse than a report that doesn't).
- `update` also moves the `sources.obsidian-skills.pin` forward, re-running the upstream install path, and reports the commit delta.
- `remove <module>` deletes only unmodified `managed` files belonging to that module, reports every file it left behind and why, and never touches `seeded` or user files.
- **Renames.** When a module version renames or moves a managed path, the new file is written at the new path and the old file is left in place, reported as a stale lock entry (`plan` and `doctor` both surface it). Litter-plus-report is the accepted design for now — deleting on the engine's own initiative is exactly what §8 forbids. Cleanup semantics (a `renames:` manifest field that lets a module declare the move so the unmodified old file can be removed) are future work.

This contract is what makes "endless expansion" a safe promise instead of a slow-motion data-loss bug.

### 8.4 Synced vaults and the lockfile

`.vault/lock.json` is a single-writer ledger. Two machines running `apply` or `update` against the same vault through a file-sync service (Obsidian Sync, iCloud, Syncthing) can fork it — a sync tool's "conflicted copy" of `lock.json` is the canonical failure — after which both machines hold ledgers that disagree with the disk and with each other. Obsidian Sync adds a sharper edge: it does not sync hidden folders, so a second machine may see no `.vault/` at all and treat a managed vault as unmanaged. The supported stance: **one writing machine** — sync the notes freely, but run Onyxian commands from a single machine — or commit `.vault/` to git and let git, which understands conflicts, carry it between machines. A `doctor` check for cross-machine ledger skew is tracked as future work.

---

## 9. The bootstrap experience

### 9.1 Command reference

The engine's mental model is declarative reconciliation: _config declares intent, lock records state, `plan` is the diff, `apply` reconciles._ Everything else is ergonomics.

|Command|Purpose|Guarantee|
|---|---|---|
|`init`|interview → config → plan → confirm → apply on a new/empty target|refuses non-empty targets (points to `adopt`)|
|`adopt`|bring an existing vault under management|additive only; mandatory reviewed plan; nothing moved, renamed, or deleted|
|`plan`|show the full diff between config and vault state|read-only, always safe|
|`apply`|execute the reviewed plan|writes only what plan showed; locks every write|
|`add <module>`|enable a module: append to config, resolve deps, run module questions, plan/apply|idempotent|
|`remove <module>`|disable a module|per §8.3; prints what it left behind|
|`update [module]`|upgrade module assets and pinned sources|per §8.3; zero overwrites of modified files|
|`doctor`|validate vault state against intent|read-only; never touches the network|
|`module new`|scaffold a module skeleton for authors (M4)|generated module passes validation out of the box|

Every mutating command supports `--dry-run`. `init` and `adopt` accept `--answers <file.yaml>` for a fully non-interactive run — this is also exactly how CI generates `examples/`, so the non-interactive path can never rot.

### 9.2 The interview

Runs as the `vault-bootstrap` skill inside Claude Code, or as plain CLI prompts elsewhere — with a hard parity rule: **every wizard question maps one-to-one to a config key**, so wizard, hand-edited config, and answers file are three doors into the same room.

Stages: runtime selection → profile pick _or_ custom module selection (dependencies resolved and shown) → per-module variables with defaults visible → naming style → summary screen → plan → explicit confirmation → apply → runtime install → `doctor` → a "Start here" note written into the vault with the user's enabled modules and next actions.

### 9.3 Adopting an existing vault

The maintainer's own lived-in vault is the acceptance test for this flow.

1. **Scan** — classify the existing tree against known module shapes.
2. **Map** — propose claims: an existing `Fitness/` can be claimed as the fitness module's root via the `root` variable. Claiming never moves or renames anything; it sets variables so the module's _new_ assets land inside the existing structure.
3. **Gap-fill** — only missing folders, templates, and Bases are planned, additively.
4. **Checklist, not action** — anything ambiguous (a folder that half-matches two modules, files where a folder is expected) goes to a human checklist in the report, never to an automatic operation.
5. **Mandatory plan review** — `adopt` has no fast path; the user reads the plan or it doesn't run.

Docs recommend a git commit of the vault before adopting; the tool itself stays VCS-agnostic.

### 9.4 `doctor` checks

Config schema validity · module dependency closure · lockfile↔disk consistency (missing, modified, orphaned managed files) · template presence for enabled modules · frontmatter conformance of framework-created notes · runtime install presence for declared runtimes · Obsidian compat drift (a local, side-effect-free `obsidian version` probe compared against the `VERIFIED_OBSIDIAN` pin in `core/onyxian/compat.py` — the version this release's agent instructions were empirically verified against; warning-only, the fix channel is the release flow). Pin *reachability* is deliberately not checked — that would be a network call, and `doctor` makes none; it says so in its report instead. `doctor` never modifies anything; it emits a report with suggested commands.

### 9.5 Cross-platform requirements

macOS, Linux, and Windows are first-class from M0 — Windows is in CI from the first commit, not retrofitted. Path handling and line endings are normalized; no symlinks are ever created in user vaults (Windows and sync tools both punish them).

---

## 10. Vault conventions (core)

### 10.1 Frontmatter core schema

Every framework-created note carries:

|Key|Type|Notes|
|---|---|---|
|`type`|string|note class, e.g. `daily`, `paper-summary`, `training-log`, `course-lecture`|
|`created`|ISO date|set at creation|
|`status`|enum|per-type lifecycle, e.g. paper: `inbox → reading → summarized`|
|`tags`|list|freeform, user-owned|

Modules add typed fields (papers: `authors`, `year`, `venue`, `read_status`; training logs: `date`, `session_type`, `duration`). The schema lives in `core/conventions/` and is mirrored by the `vault-conventions` skill — one source of truth read by both humans and agents.

### 10.2 The rest of the rules

**Bases-first:** each module's overview questions are answered by `.base` views over the frontmatter above (P5). **Naming:** folder style is the `naming.folder_style` config variable, defaulting to `Title-Case-Hyphen` to match the canonical example vault; per-module file naming is specified in each module's docs (daily notes: `YYYY-MM-DD.md`). **Links:** wikilinks within the vault; every domain keeps an `Assets/` folder for attachments. **Templates:** all under `Templates/<Domain>/`, Templater-compatible but functional as plain copies (P2).

---

## 11. Quality: testing & CI

- **Engine unit tests** (pytest): planner, lockfile transitions, variable substitution, path normalization.
- **Golden-file tests:** known config + answers → byte-exact expected vault tree; any diff fails CI.
- **Idempotency tests:** every command applied twice; the second run must produce an empty plan.
- **Update-contract tests:** fixtures with user-modified managed files; assert zero overwrites and correct `*.new` reporting.
- **Adopt tests:** a fixture vault modeled on the maintainer's sanitized tree; assert the plan is purely additive and the checklist catches planted ambiguities.
- **`examples/` as integration test:** CI regenerates every example vault from profiles via `--answers` and fails on drift. Examples are never hand-edited.
- **Matrix:** all of the above on macOS, Linux, Windows.

---

## 12. Distribution & licensing

- **License:** MIT for everything in this repository.
- **Third-party:** `kepano/obsidian-skills` is installed from upstream at bootstrap (P6); the project redistributes none of it, so no notice obligations attach. MIT terms would permit vendoring with their LICENSE intact if the dependency ever had to be frozen — that is a documented fallback, not the plan.
- **Channels:** GitHub repository (primary); a Claude Code plugin-marketplace listing for the bootstrap skill; an `npx skills add`-compatible layout for first-party skills. External module installation from arbitrary git URLs arrives in M4 behind a documented manifest-trust warning (a module is data, but a malicious template is still a social-engineering surface — say so plainly in docs).

The Claude Code plugin channel grew past "a listing for the bootstrap skill": as shipped it carries five skills — a generated mirror of `modules/core/skills/` built by `tools/build_plugin.py`, stamped with the engine version, never hand-edited — plus the `/vault-bootstrap` wizard. That creates a real version-skew surface: a managed vault can hold the same skill twice, once from the plugin (updated by the marketplace) and once in `.claude/skills/` (updated by `onyxian update`), and the two can be at different versions between releases. For a managed vault, **the vault copy is canonical** — it is lock-tracked, reconciled by `update`, and travels with the vault; the plugin copy exists to bootstrap and to serve users outside any managed vault (see `plugin/README.md`).

---

## 13. Decisions log

Proposed defaults become **Confirmed** only by owner sign-off; record the date when flipping.

| #   | Decision                  | Status   | Resolution                                                                                                                                                                                                                       |
| --- | ------------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | Bootstrap mechanism       | Confirmed (2026-06-10) | Two-stage: deterministic engine (reconciliation loop) + agent-led interview as the `vault-bootstrap` skill. Claude Code wizard first-class; CLI prompts and `--answers` as equal-parity paths.                                   |
| D2  | Opinionatedness           | Confirmed (2026-06-10) | Thin core; every domain opt-in; profiles are data.                                                                                                                                                                               |
| D3  | `kepano/obsidian-skills`  | Confirmed (2026-06-10) | Depend + pin, never vendor; install via upstream-documented per-runtime paths (verified 2026-06-10).                                                                                                                             |
| D4  | License                   | Confirmed (2026-06-10) | MIT.                                                                                                                                                                                                                             |
| D5  | Repo shape                | Confirmed (2026-06-10) | Monorepo per §4.2.                                                                                                                                                                                                               |
| D6  | Reference vaults          | Confirmed (2026-06-10) | `examples/` generated by the engine in CI from profiles; doubles as the integration test; zero personal content.                                                                                                                 |
| D7  | Engine language           | Confirmed (2026-06-10) | Python 3.11+, dependency-light, pytest-tested. Rationale: maintainer's primary language, cross-platform, agent-readable. Logged alternative: Node (aligns with `npx skills`); revisit only if distribution friction proves real. |
| D8  | Non-Obsidian scope        | Confirmed (2026-06-10) | Obsidian-first, plain-markdown-safe. Folders, frontmatter, and templates degrade gracefully to any Markdown tool; `.base` and wikilinks are the Obsidian layer. Other apps are degradation targets, not design centers.          |
| D9  | Runtime targets at launch | Confirmed (2026-06-10) | Claude Code full experience; Codex, OpenCode, and generic `AGENTS.md` at skills level via the Agent Skills spec. Re-verify each runtime's conventions at build time.                                                             |
| D10 | The name                  | Confirmed (2026-07-02) | `onyxian` — distribution, command, and import package all match. Shipped as `onyx-vault` (command `onyx`) through 1.0.14; 1.1.0 renamed everything (see RELEASING.md's historical note). PyPI names are forever, hence the log entry. |

---

## 14. Roadmap

|Milestone|Builds|Exit criteria|
|---|---|---|
|**M0 — Foundation**|repo scaffold; config / manifest / lockfile schemas final; engine skeleton with the reconciliation loop and idempotent write layer; CI matrix live|`init` produces a core-only vault on all three OSes; an immediate re-run is a byte-identical no-op|
|**M1 — Bootstrap experience**|`vault-bootstrap` interview skill + slash command; profiles; `adopt` scan/map/plan; pinned kepano install per runtime|end-to-end wizard `init` inside Claude Code; `adopt --dry-run` produces a correct, purely additive plan against a copy of the maintainer's real vault|
|**M2 — First real modules**|`daily-notes`, `academic`, `fitness`, with assets generalized from real vault material, plus their skills and agents|`examples/` regenerate cleanly in CI; the maintainer dogfoods `adopt` on the live vault|
|**M3 — Breadth + updates**|`research`, `reading`, `projects-software`; `update` per §8; `generic-agentsmd` adapter; Codex/OpenCode paths verified|`update` proven on a vault with user-modified managed files: zero overwrites, correct `*.new` report|
|**M4 — Community**|remaining roster; external module install from git URL; `module new` + authoring guide|a third party authors and installs a module without touching core; tag v1.0|

---

## 15. Risk register

|Risk|L|I|Mitigation|
|---|---|---|---|
|Destructive write into a lived-in vault|low|severe|§8 contract; mandatory reviewed plan on `adopt`; lockfile-gated writes; e2e tests on vault fixtures|
|Upstream drift — kepano repo, runtime install paths|med|med|commit pinning; dated facts in docs (P9); CI smoke-test of install paths|
|Obsidian Bases syntax evolution|med|med|`doctor`'s Obsidian compat-drift check (installed version vs. the `VERIFIED_OBSIDIAN` pin, §9.4) flags unverified Obsidian versions; the release runbook's re-verification checklist (`compat.py` docstring, RELEASING.md) patches drifted prose; golden examples pinned|
|Agent-runtime convention churn (Codex / OpenCode / AGENTS.md)|high|med|adapters quarantine runtime specifics; only Claude Code is a first-class promise pre-1.0|
|Crowded niche, weak demand|med|med|differentiate on `adopt` + update semantics, which competitors lack; read traction honestly as a demand signal, not a vanity metric|
|Scope creep toward plugin/app territory|med|med|§2 is enforceable in review; the charter is the referee|
|Malicious or sloppy third-party modules (M4)|med|med|modules are data-only by design; manifest validation; explicit trust warning at install|
|Windows path/encoding breakage|med|med|Windows in CI from M0|

---

## 16. Success criteria

Definitions of "working," chosen to be checkable rather than flattering:

- **S1** — A stranger goes from empty folder to a tailored, working vault in under ten minutes without reading source code.
- **S2** — The maintainer's real vault is adopted with zero destructive operations and is more useful the same day.
- **S3** — Deleting every agent and skill from a vault leaves it fully functional (P2 proven, not asserted).
- **S4** — A third party authors and installs a module without modifying core.
- **S5** — `update` on a customized vault overwrites nothing the user modified.
- **S6** — `examples/` regenerate byte-stable in CI on all three OSes.

Stars and adoption are signals worth watching honestly; pre-1.0 they are not success criteria.

---

## 17. Open items for the owner

1. ~~Confirm or veto D1–D9; resolve D10 (the name).~~ Done — D1–D9 confirmed 2026-06-10; D10 resolved 2026-07-02 as `onyxian` (§13).
2. Provide sanitized module raw material: `Templates/` (root and domain sets), two or three representative `.base` files, and the contents of `General/Agent-Skills` plus any non-kepano `.claude/` skills.
3. Decide whether the shipped default presets mirror your folder naming (recommended — it is proven by daily use) or use neutral names.
4. Approve the disclaimer language for `fitness-coach` outputs.

---

## Appendix A — Verified external facts (re-verify at build time)

|Fact|Verified|
|---|---|
|`kepano/obsidian-skills`: MIT license; ~35k stars; five skills (markdown, bases, json-canvas, cli, defuddle); follows the Agent Skills spec (agentskills.io); names Claude Code, Codex, OpenCode as compatible|2026-06-10|
|Upstream install paths: Claude Code plugin marketplace; `npx skills add`; Codex `~/.codex/skills`; OpenCode full-repo clone into `~/.opencode/skills/`|2026-06-10|
|Competitive field: multiple starter repos exist, including wizard-based bootstraps|surveyed early June 2026|

Anything about the outside world _not_ in this table is an assumption until checked.

## Appendix B — Glossary

**Module** — a data-only folder of vault assets plus a manifest, installable per user. **Profile** — a named module set with preset answers; pure data. **Managed file** — engine-written, lock-tracked, updatable while unmodified. **Seeded file** — engine-written once as a starting point; user-owned thereafter. **Lockfile** — the ledger of every framework write (`.vault/lock.json`). **Reconciliation loop** — config declares intent, lock records state, `plan` diffs, `apply` reconciles. **Adapter** — pure function from resolved modules to runtime-specific artifacts. **Runtime** — an agent environment (Claude Code, Codex, OpenCode). **Skill** — an Agent-Skills-spec instruction package. **Subagent** — a scoped, mission-specific agent definition. **Bases** — Obsidian's `.base` views over note frontmatter; this project's data layer. **Bootstrap** — the product feature (`init`/`adopt`). **Kickstart** — this charter.

## Appendix C — Day-zero walkthroughs

**A PhD student, empty folder.** She runs `init`, picks the `phd-student` profile, keeps every default except renaming `Academic` to `University`. The plan shows 31 folders, 12 templates, 4 Bases, 3 agents; she confirms. Two minutes later her vault has a course-template subtree, a paper pipeline, a reading inbox, and a "Start here" note. She never opens the repository.

**The cryptographer-developer, five years of notes.** He runs `adopt` on a git-committed copy. The scan claims his existing `Fitness/`, `Academic/`, and `Daily-Notes/` for the matching modules via variables; the plan is purely additive — a few missing Bases, the conventions doc, agents for the modules he enabled. Two ambiguous folders land on the checklist instead of being touched. He reads the plan, applies, runs `doctor`, and his vault is under management without a single file moved.

_End of charter._

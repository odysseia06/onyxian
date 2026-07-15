# Onyxian module authoring guide

A module is how you teach Onyxian a domain: a set of folders, typed templates, [Bases](https://help.obsidian.md/bases) views, and optional Claude Code skills and agents that together encode a workflow you actually run. This guide is for anyone building one — a bundled module for the library or a private module you distribute yourself. You do not need the repository, the charter (`KICKSTART.md`), or any internal document to act on anything here; every rule stands on its own, and every rule the engine enforces names the exact check so you can trust this guide matches the code.

If you have only used Onyxian as a vault owner, read the [user guide](user-guide.md) first — this guide assumes you know what `apply`, `*.new` files, and the trust warning are.

Contents: [what a module is](#1-what-a-module-is) · [the edit–install loop](#2-start-here-the-editinstall-loop) · [manifest anatomy](#3-manifest-anatomy) · [variables](#4-variables) · [templates and frontmatter](#5-templates-and-frontmatter) · [Bases patterns](#6-bases-patterns) · [skills and agents](#7-skills-and-agents-least-privilege) · [the quality bar](#8-the-quality-bar) · [the review checklist](#9-the-review-checklist) · [testing your module](#10-testing-your-module) · [distributing](#11-distributing)

## 1. What a module is

A module is **data, not code**. It is a `module.yaml` manifest plus an `assets/` tree, and optionally `skills/`, `agents/`, and `docs/` folders. There is no executable code anywhere in a module — the engine never runs anything a module ships. That is the whole security model: a reviewer can trust a module by *reading its folder*, and the folder is the entire review surface.

The `assets/` tree **mirrors the install tree**, placeholder segments included. An asset that installs to `{{root}}/Strategy.md` lives at `assets/{{root}}/Strategy.md`; the file at `assets/Templates/Daily/Daily Note.md` installs to `Templates/Daily/Daily Note.md`. What you see in the module folder is what lands in the vault, transformed only by two mechanical steps at apply: variable substitution (`{{...}}`), and folder-style restyling of the *literal* path segments (a `kebab-case` vault installs `Templates/Daily/Daily Note.md` as `templates/daily/Daily Note.md`; the file name itself is left alone). There is no build step and no indirection — and a module is plain files, so ship plain files: a symlink under `assets/` is copied by dereferencing its target, which is both surprising and unsafe.

Here is a real, complete manifest — `modules/daily-notes/module.yaml`, quoted verbatim:

```yaml
name: daily-notes
version: 0.2.2
summary: >
  Daily planning notes under a date hierarchy: task queries that bake in the
  day (due, scheduled, overdue, carry-over), a notes/journal skeleton, and an
  end-of-day close-out — the hub the other domains hang their day off.
depends: [core]
variables:
  - key: root
    prompt: "Folder name for daily notes"
    default: "Daily-Notes"
  - key: granularity
    prompt: "Folder layout beneath the root (the filename is always YYYY-MM-DD.md)"
    type: choice
    options: ["YYYY/MM", "YYYY", "flat"]
    default: "YYYY/MM"
provides:
  folders:
    - "{{root}}"
  templates:
    - "Templates/Daily/Daily Note.md"
  skills:
    - daily-notes
    - task-capture
  agents:
    - daily-planner
seeds:
  - ".obsidian/daily-notes.json"
post_install: |
  Create today's note from Templates/Daily/Daily Note.md; the daily-notes skill
  documents the folder layout. The task-query blocks need the community Tasks
  plugin to render and degrade to plain code blocks without it.
```

That manifest and the `assets/`, `skills/`, and `agents/` folders beside it *are* the daily-notes module. Nothing else.

## 2. Start here: the edit–install loop

Scaffold a module:

```
onyxian module new my-domain
```

This creates `./my-domain/` with a `module.yaml` (annotated with guidance comments), one example template under `assets/`, and a `docs/README.md` — a skeleton that already validates. Replace the example asset with real material, fill the summary, and document your note types in `docs/README.md`.

Then work the loop against a **scratch vault** — a throwaway vault you keep only for testing. Create one, install your module into it as a local directory, and inspect the result:

```
onyxian init ./scratch-vault
onyxian add ./my-domain --vault ./scratch-vault
```

`onyxian add` accepts a bundled module id, a git URL, *or* a local module directory — a directory (or URL) installs your module exactly the way a stranger's `onyxian add` will, through the full plan/lock machinery, so nothing about a bundled module is special.

One thing to know before you iterate: `add` **snapshots** your module into the vault's `.vault/modules/<id>/` and works from that copy thereafter (that snapshot is what keeps an external module inspectable and pinned). Editing your source folder does *not* change the snapshot, so a plain `onyxian apply` will not see your edits. To pull a fresh copy of your source into the vault, run `onyxian update`, which re-reads the source, re-stages it, and shows the plan for what changed:

```
onyxian update my-domain --vault ./scratch-vault
```

So the real loop is: edit your source, `onyxian update my-domain`, inspect the vault, repeat. Two health checks close it:

- **Convergence.** Right after an `update` has re-staged your latest edits, run `onyxian apply --vault ./scratch-vault` once more. It must be a no-op — no writes, nothing to do. If it wants to change files, your assets are not deterministic (a stray timestamp, a non-`{{...}}` value the engine cannot reproduce) and you have a bug.
- **Health.** Run `onyxian doctor --vault ./scratch-vault`. It validates the vault state against intent, read-only, and reports drift.

When the module looks right in the scratch vault, it is ready to review or distribute.

## 3. Manifest anatomy

`module.yaml` is loaded and validated by `load_manifest` in `core/onyxian/manifests.py`. Validation happens at *load* time, not plan time, so authoring mistakes surface immediately. Unknown top-level keys are rejected outright (`unknown key(s) [...] in module.yaml`); the allowed keys are exactly the ones below.

**`name`** (required) — a kebab-case id that **must equal the module's directory name**. If they differ you get `name 'x' does not match its directory 'y'`. This is why `onyxian module new` creates `./<id>/` and puts `name: <id>` inside it.

**`version`** (required) — a plain semver string like `0.2.2`. Not a range, not a prefix. A non-semver value fails with `'version' must be a semver string, got '...'`. The version is the update contract's tripwire: bumping it is how existing vaults learn an update exists (see [§10](#10-testing-your-module)).

**`summary`** (required) — one paragraph, shown by `onyxian modules` and in the external-module trust warning (`trust_warning` in `core/onyxian/external.py`). Make it earn the module's place; a hollow summary reads as a hollow module.

**`depends`** (required for everything except `core`) — the modules yours needs. Every module must list `core`; omitting it fails with `every module depends on 'core'`. Dependencies are pulled in automatically when a user enables your module, and they define the closure your agents may reference skills from ([§7](#7-skills-and-agents-least-privilege)).

**`conflicts`** (optional) — module ids that cannot be enabled alongside yours. Coexistence is enforced at resolve time by `resolve_modules` in `core/onyxian/resolve.py` (`modules 'x' and 'y' cannot coexist`), not by `load_manifest`.

**`variables`** (optional) — the tailoring surface. Covered in full in [§4](#4-variables).

**`provides`** (optional) — what the module installs, a mapping with only these keys (`folders`, `templates`, `bases`, `skills`, `agents`); anything else is rejected:

- `folders` — folder paths to create (usually a `{{variable}}` root).
- `templates` — managed template files. Each pattern resolves against `assets/`; a missing asset fails with `asset file missing at ...`.
- `bases` — managed `.base` view files, same resolution.
- `skills` — skill ids, each backed by `skills/<id>/SKILL.md`. A listed skill with no `SKILL.md` fails; and every skill package **on disk** must be listed — an unlisted one fails with `skill package(s) [...] exist on disk but are not listed under provides.skills`. There is no way to smuggle in an unlisted skill.
- `agents` — agent ids, each backed by `agents/<id>.yaml`, with the same on-disk/listed parity (`agent definition(s) [...] exist on disk but are not listed under provides.agents`).

A `templates`/`bases` pattern may contain a wildcard (`*`, expanded against `assets/` in sorted order) **or** a `{{variable}}`, but not both — the expansion result must itself be the install path, so the two cannot mix (`wildcards and {{variables}} cannot be combined`).

**`seeds`** (optional) — files written **once**, then owned by the user forever (see [§5](#5-templates-and-frontmatter)). Same asset resolution as templates.

Across `templates`, `bases`, and `seeds`, no two entries may resolve to the same install path (`duplicate install path(s) [...]`).

**`post_install`** (optional) — a short paragraph for the human: what to fill in or read first.

## 4. Variables

Variables are how a module is tailored per vault — folder names, cadences, layout choices — instead of baking in one person's opinions. A variable has a `key` (snake_case), a `prompt`, a `type`, an optional `default`, and — for choices — `options`. Three types:

- **`string`** (the default) — free text, e.g. a folder name.
- **`choice`** — one of a fixed `options` list; a `choice` with no options, or a `default` outside the options, is rejected.
- **`bool`** — true/false.

**The `root` convention.** Give every folder the module roots a variable — by convention named `root` — with a sensible default, rather than hardcoding a folder name. Author defaults in **`Title-Case-Hyphen`** (`Daily-Notes`, `My-Domain`); this is the canonical style, and the engine restyles it to match the user's chosen folder convention (a `kebab-case` vault gets `daily-notes`). The scaffold from `onyxian module new` starts you with exactly this: a `root` variable whose default is the `Title-Case-Hyphen` form of the module id.

**Globals.** `{{onyxian.today}}` and `{{onyxian.vault_name}}` are always available — you do not declare them. `{{onyxian.today}}` is recomputed every time the desired state is built (`resolve_today` in `core/onyxian/intent.py`), so reach for it only in a **seed**, which is rendered once at install and then frozen. In a *managed* file it re-renders on every `onyxian apply` and will silently rewrite the file each new day — a footgun, not a stamp. For a date that belongs to an individual note, use Templater (`<% tp.date.now() %>`), resolved when the user creates the note.

**No logic.** A variable supplies a value; it never runs logic, and it cannot select *which* assets exist — every file listed under `provides` and `seeds` is always installed. A `choice` variable changes the *value substituted into* an asset (an asset containing `{{layout}}` renders differently per choice), never the set of files. There are no conditionals, loops, or expressions anywhere in a manifest or an asset. (The daily-notes `granularity` choice looks like branching but is not a pattern you can reuse: the engine special-cases it into a derived value baked into one seed — see `_DAILY_NOTE_FORMATS` in `core/onyxian/intent.py` — a first-party shortcut a third-party module cannot reach for.)

## 5. Templates and frontmatter

**Typed frontmatter is the contract.** The `type`, `status`, and `tags` frontmatter your templates emit is what Bases filter on and what agents reason about. A template that emits `type: session` and `tags: [fitness/log]` is what lets a Base say "show me every training log" and an agent say "I operate on sessions." (Agent *scopes* are path globs, not frontmatter filters — see [§7](#7-skills-and-agents-least-privilege); the note types are the vocabulary an agent's mission and playbook are written against, not a mechanism it filters on.) Decide these fields deliberately — they are the module's public interface, not decoration.

**Two placeholder languages — never mix them.** This is the single most common authoring mistake.

| Syntax | Owner | Resolved | Use for |
|---|---|---|---|
| `{{variable}}` | the Onyxian engine | **once, at `apply` time** | user tailoring: folder names, cadences; plus the globals `{{onyxian.today}}`, `{{onyxian.vault_name}}` |
| `<% tp.* %>` | Templater (the user's Obsidian) | **every time the user instantiates the template** | per-note values: today's date in a note the user creates tomorrow |

The engine substitutes `{{...}}` and passes `<% ... %>` through byte-for-byte. Never write `<% ... %>` for something the engine should resolve, or `{{...}}` for a per-note value.

**Templates must degrade.** Every template has to remain a functional plain copy with **no Templater installed**. An unresolved `<% ... %>` must read as an obvious fill-me-in, never break the note.

**No literal checkbox carrying a raw Templater macro.** This one has teeth. A line like `- [ ] <% tp.date.now(...) %>` shipped literally is scanned by the community Tasks plugin as a *phantom open task* — a task that exists in every fresh copy of the template and never gets done. Let Templater *emit* such checkboxes; never ship one literally. This is enforced across all bundled assets by the test `test_no_template_checkbox_carries_a_raw_macro` (`tests/test_modules_m2.py`), which scans for `[ ]`/`[x]` lines containing `<%`.

**No hard-wrapped prose.** One logical line per paragraph and per bullet; let editors soft-wrap. A bullet hard-wrapped at ~100 columns renders in Obsidian's Live Preview with a gap partway through the sentence — valid Markdown that reads as broken. This applies to every template, seed, and anything else the module puts into a vault.

**`managed` vs `seeds` — the decision rule.** Anything in `provides.templates` or `provides.bases` is **managed**: framework-owned, silently improved by later versions *until the user edits their copy*, at which point an update arrives as a `*.new` sibling rather than an overwrite. Anything in `seeds` is written **once** and is the user's from that moment — never updated, never recreated. The rule: if a future version of the module should be able to improve the file, it is managed; if the user's edits *are the point* of the file (a Strategy note, a home page, a starter example), it is a seed.

## 6. Bases patterns

A [Base](https://help.obsidian.md/bases) is a `.base` file — a live, filtered view over your notes' frontmatter. Bases are how a module answers a question ("what did I train this month?") without a hand-maintained list note that rots. A few patterns the bundled modules use:

**Filter on frontmatter your templates actually emit.** A Base is only as good as the typed data behind it. The fitness module's `Training-Log.base` filters on a tag its session template emits:

```yaml
filters:
  and:
    - 'file.hasTag("fitness/log")'
```

If your template does not emit `fitness/log`, that filter shows nothing. Design the frontmatter ([§5](#5-templates-and-frontmatter)) and the Base together.

**Variable-derived filters must follow the user's folder style.** When a filter references a folder that came from a variable, it has to use the *styled* form the user actually gets. A `kebab-case` vault whose fitness root became `fitness` needs the Base filter to say `fitness/log`, not `Fitness/log` — the test `test_kebab_style_yields_a_consistent_tree` (`tests/test_modules_m2.py`) exists precisely to catch a Base that renders a mixed-case seam.

**`file.inFolder` for scoped views.** To scope a view to one folder, filter on it:

```yaml
filters:
  and:
    - file.inFolder("Projects/Software")
```

**The copy-per-instance pattern for template subtrees.** Bases cannot self-scope to the folder they live in, so a Base that ships inside a *template* subtree (meant to be copied per course, per project) hardcodes the template folder and tells the user to repoint it. The academic module's `Exam-Study.base` does exactly this:

```yaml
# When copying _Course-Template to a real course, point this filter at the new
# course's Exam-Prep folder (one line) — Bases cannot self-scope to their folder.
filters:
  and:
    - file.inFolder("{{root}}/Courses/_Course-Template/Exam-Prep")
    - chapter > 0
```

The "point this filter at the new course" instruction is part of the shipped file, and `test_exam_base_lands_inside_the_course_template` asserts it survives rendering.

**Bases-first.** If your module's overview would be a hand-maintained list note that a human has to keep current, it should be a `.base` over typed frontmatter instead. A list note that drifts out of date is a bug the framework can design away.

## 7. Skills and agents, least-privilege

**Division of labor.** A **skill** is a procedure any agent (or human) can follow — `skills/<id>/SKILL.md`, a self-contained document. An **agent** is a mission plus a scope plus a playbook — `agents/<id>.yaml`, a bounded operator you can hand a job. A skill teaches *how*; an agent is *who* does it, and *where* it is allowed to act.

**The scope model, as `manifests.py` enforces it.** An agent's `scope` is a mapping with only `read` and `write` keys. Each is a list of vault-relative globs over the module's resolved variables. The rules `_parse_agent` and `_check_scope_glob` enforce:

- **`scope.read` must not be empty** (`scope.read must not be empty`). An agent that can read nothing is a mistake.
- Globs are **vault-relative**: at load time `_check_scope_glob` rejects a leading `/` or drive letter (`must be vault-relative`), backslashes (`portable form is '/'`), and `..` (`escapes the vault`). After variable substitution the render step re-checks for `..` and backslashes only (`core/onyxian/adapters.py`), so keep your variable *defaults* vault-relative yourself — a rendered value like `/etc` is not caught there. And remember what a scope is: advisory text in the agent's prompt, not a mechanical sandbox — the user guide's "honest word about scoping" is explicit that nothing at the filesystem level enforces it.

**Cross-module reads use `requires:`.** To read a folder that belongs to *another* module, write the scope entry as a `{path, requires}` mapping instead of a bare string:

```yaml
scope:
  read:
    - "{{root}}/**"
    - { path: "Daily-Notes/**", requires: daily-notes }
```

The `requires` entry names the module that must be enabled for that path to apply. If the user has not enabled `daily-notes`, the entry **drops out** of the rendered agent's instructions entirely — the fitness coach in a vault without daily-notes is never *told* it may read `Daily-Notes/`, so it does not go looking there. (Scopes are instructions, not enforced permissions, so this shapes what the agent is directed to do, not a filesystem barrier.) The drop is enforced by `test_fitness_without_daily_notes_drops_the_cross_scope`.

**`escalate_when`** — the conditions that end the agent's autonomy and hand control back to the human. List the known failure modes of the agent's job here.

**`triggers`** — natural phrases that route a user to this agent ("plan my day", "log a workout"). Every bundled agent declares triggers, enforced by `test_every_shipped_agent_declares_triggers`; without them the agent is unreachable by phrase.

**`skills:` must resolve in the dependency closure.** Every skill an agent lists must be provided by a module in *your module's transitive dependency closure*, or be one of the curated external (kepano) skill ids. A reference to a skill that no dependency provides fails at resolve time via `check_agent_skills` in `core/onyxian/skillcheck.py`: `agent .../... references skill '...', which no module in its dependency closure provides and which is not a known external skill`. If your agent needs a skill from another module, add that module to `depends`.

**What every agent gets for free.** You do not hand-write the safety floor — the renderer (`core/onyxian/adapters.py`) supplies it:

- The **standing escalations** in `_STANDING_ESCALATIONS` (deleting/moving/renaming/restructuring files, or needing to write outside the write scope) are appended to whatever `escalate_when` you wrote — unconditionally, for every agent.
- The **least-privilege sentence** ("Least privilege governs you: writing outside your write scope is a defect, not initiative.") is added to the operating rules of every agent.
- The **operating-the-live-vault preamble** (`_OPERATING_PREAMBLE`) — drive the vault through the `obsidian` CLI, be additive, look before you write, escalate before anything destructive — is added to any agent that declares a `playbook`. An operating agent should have one; give it a playbook and it carries the preamble.

Write your `scope`, `escalate_when`, `triggers`, and `playbook` to be *minimal and specific*; the framework guarantees the floor.

## 8. The quality bar

Validation passing is not the bar — it is the floor. A manifest with two folders and a seed dashboard validates cleanly and is still not a module worth shipping.

The strong bundled modules earned their place by being **generalized from a system the maintainer actually runs**. Everything that makes them strong — typed-frontmatter lifecycles a Base can query, agent scopes with real `requires:` cross-module entries, skills that enumerate the exact sections a template emits — is there because it answers a question someone actually asks their vault.

A module earns its place by encoding a workflow someone actually runs: a status lifecycle a note moves through, a Base that answers a real question, a procedure a stranger's agent can follow start to finish. Folders plus a dashboard seed is a skeleton, not a module. The checklist below is how you tell the difference before you ship.

## 9. The review checklist

Every module PR — and every private module worth trusting — should pass all seven. This is the one canonical copy; `CONTRIBUTING.md` links here rather than restating it.

1. **Validates and converges.** `load_manifest` passes, the module installs into a scratch vault, and a second `onyxian apply` is a no-op.
2. **Reviewable by reading.** Data only, no executable code; `assets/` mirrors install paths verbatim; nothing on disk is unlisted in the manifest.
3. **Substance over scaffolding.** At least one workflow is encoded — a typed-note lifecycle, a Base that answers a question the templates' frontmatter can answer, or a skill with a real procedure. Not just folders and a dashboard seed.
4. **Tailoring surface.** Every folder the module roots sits behind a variable with a `Title-Case-Hyphen` default; `managed` vs `seeds` is chosen deliberately per file.
5. **Templates degrade.** The two placeholder languages are used correctly; templates are functional with no Templater; no literal checkbox carries a raw Templater macro; no hard-wrapped prose.
6. **Least-privilege agents and skills.** Minimal read/write globs; cross-module reads use `requires:`; `escalate_when` covers the known failure modes; `triggers` are present; every `skills:` entry resolves in the dependency closure or the curated external list.
7. **Versioned and tested.** Semver is bumped for any content change; test pins, golden fixtures, and examples are regenerated via the tools only; there is one content-invariant test per new surface.

## 10. Testing your module

**Distributing your own module?** The [edit–install loop](#2-start-here-the-editinstall-loop) is your whole test suite: install into a scratch vault, inspect, confirm the second `onyxian apply` is a no-op, and run `onyxian doctor`. That proves the module validates, renders, and converges.

**Contributing to the bundled library?** Three extra rules apply, because a bundled module ships inside the engine's test and fixture machinery:

- **Bump the semver for any content change.** Any edit under `modules/<id>/` requires bumping `version:` in that module's `module.yaml`. The version pin is the update contract's tripwire, and the resolver *fails loudly* if the config pin and the shipped version drift apart — `resolve_modules` raises `module '...' is pinned to X in config but the library ships Y; run onyxian update ...`, exercised by `test_version_drift_is_loud` (`tests/test_resolve.py`).
- **Regenerate fixtures with the tools, never by hand.** Golden fixtures and examples are generated trees; regenerate them with `python tools/regen_golden.py` and `python tools/gen_examples.py`. A hand-edited fixture will drift and fail CI.
- **Add one content-invariant test per new surface.** Every content invariant in the bundled modules is pinned by a test in `tests/test_modules_m2.py` — section parity, the phantom-checkbox rule, resolved scopes, triggers. When you add a surface (a new Base filter, a new agent scope, a new template section a skill must name), add at least one test that pins its invariant. `tests/test_modules_m2.py` is the model to copy.

## 11. Distributing

An external module is a **git repository with `module.yaml` at its root**. Anyone installs it with `onyxian add <git-url>`.

**What your users see.** Before installing, the engine prints a trust warning (`trust_warning` in `core/onyxian/external.py` is the verbatim text). In summary, it names your module and version, its source and commit, a count of what it provides, and your `summary` — then it reminds the reader that while a module is data-only and never executed, your **templates and seeds become notes they will trust** and your **skills and agent definitions are instructions their agents will follow**, so they should review the content first. On install, the engine pins the reviewed commit into their config and keeps your module vault-locally under `.vault/modules/<id>/`, where it stays inspectable.

**The lifecycle.** `onyxian update <id>` fetches upstream `HEAD`, shows a path-level plan, and — on the user's confirmation — advances the pin and re-stages the new content; `onyxian remove <id>` deletes the copy (keeping anything of theirs). Note what that confirmation is and is not: it is a gate over the *file plan*, not a re-display of the changed skill and agent text. The content trust review happens once, at first `add`. Tell your users that, and treat every commit you publish as one they will run without re-reading it.

**Be worthy of the trust gate.** Your skills and agent definitions are instructions other people's agents will follow. Write them with the same least-privilege discipline ([§7](#7-skills-and-agents-least-privilege)) the bundled roster uses, and hold your module to [the checklist](#9-the-review-checklist) before you ask anyone to trust it.

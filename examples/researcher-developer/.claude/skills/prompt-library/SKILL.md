---
name: prompt-library
description: The ai-workspace module's shelf conventions — living prompt notes edited in place, skill drafts with a user-driven draft → testing → graduated lifecycle, graduation links to where the skill shipped, and propose-only archival. Use for any task touching prompt notes or skill drafts.
---

# prompt-library

Read the resolved root from `.vault/config.yaml` under `modules.ai-workspace.vars.root` (called `<root>` below). Two shelves, plain notes on the core frontmatter keys — the module defines no keys of its own, only the `type` and `status` values documented here.

## The one iron rule

The lifecycle is the user's. A skill draft moves `draft → testing → graduated` only when the user says so: record transitions, never advance one because a draft "looks done", and never mark a draft `graduated` without recording where it shipped.

## Prompt shelf

- One note per prompt in `<root>/Prompts`, named by what it is for. Frontmatter: `type: prompt`, `status: active`, tags include `ai`.
- Prompts are living notes, edited in place: an improvement replaces the old text. No version copies, no dated duplicates — if the user wants history, that is their own version control's job, not the shelf's.
- Per-project agent-instruction drafts (CLAUDE.md / AGENTS.md templates for a project type, review master prompts, and the like) live here too, one note per use.

## Skill workbench

- One note per skill draft in `<root>/Agent-Skills`, `type: skill-draft`, `status: draft` at capture; organize by target runtime if that helps. When a draft outgrows one file, a folder beside the note is fine — the note stays the tracked surface.
- `status` is the lifecycle: `draft → testing → graduated`. Keep it truthful; "which drafts are still in testing" is answered from these keys alone.
- Graduation: when the user says a skill shipped, set `status: graduated` and record where it shipped in the note — the repo, marketplace, or vault path that now owns it.
- Archival: propose moving graduated drafts into `<root>/Agent-Skills/Archive`, and move only after the user confirms. The workbench shows work in flight; Archive keeps the paper trail.

## Boundary

The workbench is the scratchpad; a graduated skill lives where it shipped. Link out to the shipped location and never mirror shipped content back into the draft — two copies of a live skill always diverge. The dashboard (`<root>/00 Dashboard.md`) is the user's own overview note: read it for orientation, leave writing it to them.

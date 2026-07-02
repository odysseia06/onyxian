# Core frontmatter schema

This is the one source of truth for the typed-frontmatter conventions. Humans read it here; the `vault-conventions` skill mirrors it for agents. The two must never diverge — change this file, regenerate the skill.

## Scope

These rules bind **framework-created notes** — anything a module installs or an Onyxian agent writes. The engine never validates or rewrites the user's own notes against this schema; adopting the conventions in your own notes is what makes module `.base` views light up, and is always optional.

## Every framework-created note carries

| Key | Type | Notes |
|---|---|---|
| `type` | string | note class, kebab-case, e.g. `note`, `home`, `daily`, `paper-summary`, `training-log` |
| `created` | ISO date (`YYYY-MM-DD`) | set once at creation, never edited by tooling |
| `status` | string | per-type lifecycle; each module documents its enum (e.g. paper: `inbox → reading → summarized`) |
| `tags` | list of strings | freeform, user-owned; tooling may suggest, never prune |

## Module extensions

Modules add typed fields on top of the core four and document them in their own `docs/`. Examples from the roster: papers add `authors`, `year`, `venue`, `read_status`; training logs add `date`, `session_type`, `duration`. A module's `.base` views filter on these fields — that is the Bases-first principle (P5): views over typed frontmatter, never hand-maintained index lists.

## Types defined by `core`

| `type` | `status` lifecycle | Written by |
|---|---|---|
| `note` | `active` (free-form thereafter; the template does not police it) | the user, from `Templates/Note.md` |
| `home` | `active` | seeded once at init; user-owned from then on |
| `start-here` | `active` | engine-generated summary of the enabled module set, regenerated as modules change. The one framework note without `created`: a regeneration date would make an unchanged vault plan dirty tomorrow (P3 outranks schema completeness) |

## Rules for tooling and agents

- Set all four core keys on every note you create; never delete a key the user added.
- Dates are plain ISO dates, no timestamps, no timezones — vault portability beats precision here.
- `status` transitions are append-only edits to the value, never accompanied by file moves unless the module's docs say the workflow moves files.
- Unknown frontmatter keys in any note are the user's business: preserve them byte-for-byte.

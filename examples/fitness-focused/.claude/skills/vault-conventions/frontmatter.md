# Core frontmatter schema

This is the one source of truth for the typed-frontmatter conventions. Humans read it here; the `vault-conventions` skill mirrors it for agents. The two must never diverge — change this file, regenerate the skill.

## Scope

These rules bind **framework-created notes** — anything a module installs or an Onyxian agent writes. The engine never validates or rewrites the user's own notes against this schema; adopting the conventions in your own notes is what makes module `.base` views light up, and is always optional.

## Core default schema

Unless an explicit exception below applies, every framework-created note carries:

| Key | Type | Notes |
|---|---|---|
| `type` | string | note class, kebab-case, e.g. `note`, `home`, `daily`, `training-log` |
| `created` | ISO date (`YYYY-MM-DD`) | set once at creation, never edited by tooling |
| `status` | string | per-type lifecycle; each module documents its enum (e.g. daily: `open → closed`) |
| `tags` | list of strings | freeform, user-owned; tooling may suggest, never prune |

## Module extensions

Modules normally add typed fields on top of the core four and document them in their own `docs/`. For example, training logs add `date`, `session_type`, and `duration`. A module's `.base` views filter on these fields — that is the Bases-first principle (P5): views over typed frontmatter, never hand-maintained index lists.

## Explicit exceptions

### Research paper notes

The research paper pipeline has a documented module-specific schema, preserved from the source workflow, that replaces rather than extends the core default:

- `type` is the paper genre: `attack`, `construction`, `engineering`, `foundations`, `framework`, `protocol`, or `survey`.
- `tags` includes `paper`, which marks the note class.
- `date_added` replaces `created`, and `date_summarized` records completion; paper notes do not carry a `created` key.
- `status` follows `to-read → reading → summarized → revisiting`.

For paper notes, preserve the complete schema documented by the `paper-pipeline` skill and the shipped paper templates exactly. It outranks the core default above.

### Generated `start-here` note

The engine-generated `start-here` note omits `created`: a regeneration date would make an unchanged vault plan dirty tomorrow, so P3 outranks schema completeness. It otherwise uses the core keys.

## Types defined by `core`

| `type` | `status` lifecycle | Written by |
|---|---|---|
| `note` | `active` (free-form thereafter; the template does not police it) | the user, from `Templates/Note.md` |
| `home` | `active` | seeded once at init; user-owned from then on |
| `start-here` | `active` | engine-generated summary of the enabled module set, regenerated as modules change |

## Rules for tooling and agents

- Apply the core default unless the note belongs to an explicit exception above; for an exception, preserve its documented schema exactly. Never delete a key the user added.
- Dates are plain ISO dates, no timestamps, no timezones — vault portability beats precision here.
- `status` transitions are append-only edits to the value, never accompanied by file moves unless the module's docs say the workflow moves files.
- Unknown frontmatter keys in any note are the user's business: preserve them byte-for-byte.

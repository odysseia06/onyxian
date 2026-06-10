# research

The typed paper pipeline, generalized from the maintainer's working library (KICKSTART.md §5.4): flat folders + rich frontmatter + an eight-view Base, with seven paper-type templates whose middle sections ask type-appropriate questions (an attack paper needs a threat model; a survey needs a taxonomy).

## The one sanctioned schema deviation

Paper notes keep their proven frontmatter exactly (the source vault's own rule: "preserve the canonical paper frontmatter"). For papers, `type` means *paper type* (`attack` … `survey`) and `tags: paper` marks the note class; `date_added`/`date_summarized` play the role of `created`. Documented here so the §10.1 core schema and this module never fight.

## Lifecycle

`to-read` → `reading` → `summarized` → `revisiting`. The Base (`Paper Library.base`, tag-driven, style-independent) renders All Papers / To Read / Reading Now / Summarized / Revisiting / By Type / High Priority / Recent Additions.

## Variables

- `root` (default `Research`). Nested roots work: the canonical-example vault keeps it at `Academic/Research`, which the `phd-student` profile presets (persona lives in profiles, not defaults — P4).

Seeded: `00 Paper Dashboard.md`. Templates: the interactive `Paper Summary` (Templater-driven prompts + auto-rename) and seven static typed variants for manual or agent use.

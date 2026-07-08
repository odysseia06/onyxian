# obsidian CLI semantics — verified vs. assumed

The fake `obsidian` CLI (`obsidian_stub.py`) reproduces the *sharp edges* the
daily-notes / task-capture / vault-operations skills defend against, so a
procedure change is executed against them rather than a forgiving fake. Each edge
is one of two kinds:

- **verified** — confirmed against the real Obsidian CLI (the skill prose says so,
  or a maintainer checked).
- **assumed** — inferred from skill prose or from the bug the skill fixed, and
  **not yet** re-confirmed against a live CLI. Assumed edges are safe to encode —
  they make the checkers stricter, not looser — but should be re-verified
  opportunistically. If one turns out wrong, the fix is a stub change plus a
  transcript re-derive, never a silent loosening.

| # | Stub behavior | Kind | Provenance |
|---|---|---|---|
| 1 | `create ... template=` inserts the template **verbatim** (`<% %>` literal) | **verified** | `vault-operations/SKILL.md:68` — "verified against the live CLI" |
| 2 | `daily:read` on a **missing** daily note **creates it** (macros literal) before returning | assumed | `daily-notes/SKILL.md:22` — "opening the daily note can create it"; the 3f4cdb2 / 321d965 false-existence bug |
| 3 | `read`/`file` with an **omitted or unresolved** `path=`/`file=` silently returns the **active** note (flagged `fallback` in the trace) | assumed | `vault-operations/SKILL.md:28`; 40ab880 |
| 4 | `create path=` on an **existing** file without `overwrite` **errors** | assumed | the additive write contract (`vault-operations/SKILL.md:24`); no destructive default |
| 5 | `command id=daily-notes` creates today's note from `Templates/Daily/Daily Note.md` (verbatim) when missing and makes it active | assumed | scaffold step 4 (`daily-notes/SKILL.md:23`) |
| 6 | `command id=templater-obsidian:replace-in-file-templater` resolves `<% %>` / `<%* %>` in the **active** note | assumed | scaffold steps 4–5 (`daily-notes/SKILL.md:23-24`) |
| 7 | `append file=<name>` with an **unresolved** name shares the read active-note fallback | assumed | inferred from #3; see open question below |

Dot-folders (`.obsidian/`, `.claude/`, `.vault/`) are not vault-indexed notes, so
wikilink-style `file=<name>` resolution ignores them — matching Obsidian's own
link resolver.

## Templater emulation

`resolve_templater()` handles exactly two constructs, enough for the shipped
daily template and nothing else:

- inline `<% tp.date.now("YYYY-MM-DD") %>` → today (`ONYXIAN_NOW`),
- the `<%* ... %>` block's `const today = ...` + `tR += "..." + today + "...";`
  string concatenation.

It is **not** a Templater clone and does not emulate whitespace-control (`-%>`).
The result is deterministic and pinned by
`tests/fixtures/evals/expected/daily-2026-01-01.md`; it is not byte-for-byte real
Templater output, and does not need to be (issue #2 out-of-scope). A stub unit
test asserts that resolving the shipped template leaves no `<%`.

## Open questions (from issue #2), pending live re-verification

- Edges #2 and #3 are only *assumed* from skill prose. Re-verify against a live
  Obsidian CLI, or keep them documented here and verify opportunistically. They
  are encoded here because they make the harness stricter, not weaker.
- Edge #7: does `append file=` actually share the active-note fallback that reads
  have? Encoded **yes** (conservative — a bad append is then caught, not hidden).
  One check against the live CLI should confirm or correct this before it is
  relied on beyond the harness.

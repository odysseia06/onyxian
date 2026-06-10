# Contributing to Onyx

## Before anything else

Read [KICKSTART.md](KICKSTART.md) — at minimum §3 (Principles), §4 (Architecture), §5 (Modules), and §8 (Write & update contract). The charter is the referee: §2 non-goals and §3 principles are enforceable in review, and a PR that violates a numbered principle is a bug report against the PR, not a tradeoff discussion.

## Development setup

```
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -e .[dev]
pytest
```

Python 3.11+ is required. Runtime dependencies are deliberately minimal (PyYAML only); think hard before proposing another.

## The rules that bite

- **Every engine write goes through the lockfile.** If you add a code path that writes into a vault without recording a lock entry, that is a defect, not a style issue (§8).
- **Never touch user files.** Anything not in the lockfile is the user's. The planner must emit a blocked/report action for collisions, never a write (§8.2).
- **Determinism.** Engine output is byte-identical across OSes and across runs: UTF-8 without BOM, LF line endings, sorted lock entries, no timestamps in the lock. Date-bearing content renders from the `ONYX_NOW` override in tests and CI so golden trees stay byte-exact.
- **Re-running anything against an unchanged vault is a no-op** (P3). The idempotency tests enforce this; keep them passing.

## Authoring module assets and generated prose

- **Do not hard-wrap prose** in module assets, fragments, or anything the engine emits into a vault. One logical line per paragraph and per bullet; let editors soft-wrap. Hard-wrapped bullets render in Obsidian Live Preview with a gap partway through the sentence, which reads as broken. See `core/conventions/authoring.md`.
- **Two placeholder languages, two moments.** `{{variable}}` is the *engine's* substitution, resolved once at apply time. `<% tp.* %>` is *Templater's*, resolved when the user instantiates a template — the engine passes it through untouched. A template must remain functional as a plain copy with no Templater installed (P2).
- Modules contain **no executable code**. A module is reviewable by reading it (§5.1).
- The `vault-conventions` skill bundles copies of `core/conventions/frontmatter.md` and `naming.md`; a test enforces byte-equality. Edit the canonical file under `core/conventions/`, then copy it into `modules/core/skills/vault-conventions/` — never edit the bundled copy directly.

## Tests

`pytest` runs everything. Per KICKSTART.md §11, changes touching the engine or module assets need:

- unit coverage for new planner/lock/render behavior,
- the idempotency suite still green,
- golden fixtures regenerated *only* via `python tools/regen_golden.py` (never hand-edited), with the diff reviewed in the PR.

CI runs the matrix on Ubuntu, macOS, and Windows. Windows is first-class; "passes on my Linux box" is not done.

## Commit and PR hygiene

- Small, reviewable PRs; one concern each.
- Cite the charter section your change implements or amends.
- Changes to charter decisions (§13) require owner sign-off — flip Proposed→Confirmed only with a date and a reviewer.

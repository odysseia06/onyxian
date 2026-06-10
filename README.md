# Onyx

An open-source, AI-native framework for Obsidian vaults. Onyx turns a vault into a long-lived personal knowledge system — life, research, and engineering in one place — composed from **opt-in modules**. A cryptography researcher, a biology PhD student, a musician, and a product manager are all served by the same framework with different module sets, different folder names, and different agents.

Three rules tower over everything else:

1. The vault is fully usable **without any LLM**. Agents amplify; they are never load-bearing.
2. The framework is **additive and idempotent**: it never deletes or overwrites your files, and every file it writes is tracked in a lockfile so it can be safely updated or removed later.
3. **Tailoring is the product.** Folder names, cadences, and structures are per-user variables, not hardcoded opinions.

The full blueprint — vision, invariants, architecture, module system, write/lock/update contract, roadmap — lives in [KICKSTART.md](KICKSTART.md). Read that before contributing; its §2 non-goals and §3 principles are enforceable in review.

## Status

**v1.0.0 — the KICKSTART.md §14 roadmap is complete (M0–M4).** The deterministic reconciliation engine with the §8 lockfile write contract; the `vault-bootstrap` interview skill; `adopt` (scan → claims → additive gap-fill → checklist → mandatory review), `add`, `update` (§8.3: clean files update in place, customized files get the new version beside them as `*.new` — zero overwrites, ever), and `remove` (deletes only unmodified framework-owned files); the **full twelve-module roster** generalized from the maintainer's lived-in vault (`daily-notes`, `academic`, `fitness`, `research`, `reading`, `projects-software`, `projects-gamedev`, `oss`, `music`, `writing`, `ai-workspace` on the `core` substrate); the claude-code adapter plus generated `AGENTS.md` for generic/Codex/OpenCode runtimes; the pinned `kepano/obsidian-skills` install; **external modules from any git URL** behind a trust warning, pinned and vault-local; and `onyx module new` for authors. Six profiles, six engine-generated reference vaults under `examples/`, CI-enforced byte-stable on the 3-OS matrix.

## How it works

The engine is a small CLI implementing declarative reconciliation:

- `.vault/config.yaml` declares **intent** (which modules, with which variables) — yours to edit.
- `.vault/lock.json` records **state** (every file the engine ever wrote, with its hash) — machine-maintained.
- `onyx plan` computes the difference. `onyx apply` reconciles it.

Files the engine writes are either **managed** (framework-owned, updated only while your copy is untouched — if you edited it, updates land as a `*.new` sibling instead) or **seeded** (written once as a starting point, yours from that moment on). Everything else in the vault is yours, and the engine will never write to it. There is no flag that overrides this.

## Try it (developers)

```
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -e .[dev]

onyx init path/to/new-vault              # interactive
onyx init path/to/new-vault --answers profiles/minimal.yaml --yes
onyx adopt path/to/existing-vault        # scan, claims, additive plan, mandatory review
onyx add <module> --vault path/to/vault  # enable a module (dependencies auto-added)
onyx modules                             # what exists, with variables and defaults
onyx plan   --vault path/to/new-vault    # always read-only
onyx doctor --vault path/to/new-vault

pytest
```

`init` refuses non-empty targets — that is `adopt`'s territory, and `adopt` is additive only: claims map your existing folders onto module variables, nothing is ever moved, renamed, deleted, or overwritten, ambiguities land on a checklist instead of in actions, and there is no `--yes` — you review the plan and confirm it (interactively, or by passing back the acceptance token the review printed). In Claude Code, `/vault-bootstrap` runs the whole interview conversationally.

## Repository layout

```
core/scaffold/      the engine (importable as the `onyx` package)
core/conventions/   frontmatter schema, naming rules, authoring rules
modules/            self-describing data-only modules (M0 ships `core`)
profiles/           named module sets with preset answers — pure data
adapters/           per-runtime artifact generators (M1+)
examples/           reference vaults, generated in CI — never hand-edited
tests/              unit, golden-file, idempotency, and contract tests
tools/              dev and CI scripts
```

## License

MIT. Third-party skills (e.g. `kepano/obsidian-skills`) are installed from upstream at bootstrap and never redistributed here.

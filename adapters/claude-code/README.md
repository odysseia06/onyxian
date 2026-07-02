# claude-code adapter

The first-class runtime. Implemented in the engine at `core/onyxian/adapters.py`; this directory documents the contract.

**Output for a vault whose `framework.runtimes` includes `claude-code`:**

- `provides.skills` of every enabled module → `.claude/skills/<skill-id>/**`, copied byte-for-byte (a skill is a static instruction package; one that documents `{{placeholder}}` syntax must survive verbatim). Managed, lock-tracked, attributed to the providing module — so disabling the module orphans them visibly and `onyxian remove` can clean them up.
- Declared sources (`sources.obsidian-skills`) → `.claude/skills/<name>/**` at the recorded pin, lock-tracked under the pseudo-module `source:obsidian-skills`.
- Module agents → `.claude/agents/*.md`, rendered over resolved variables.
- Orientation surfaces from the same resolved agent set → a seeded `CLAUDE.md` (written once, user-owned) importing the managed `.claude/onyxian.md` roster digest, plus the human-facing `Onyxian Assistant.md`.

Everything is ordinary desired state flowing through plan/apply/lock: no copytree side channels, no unledgered writes. Runtime paths are never folder-style transformed. Deleting the whole `.claude/` tree costs convenience, never function (P2).

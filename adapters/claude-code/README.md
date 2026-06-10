# claude-code adapter

The first-class runtime (D9). Implemented in the engine at `core/scaffold/adapters.py`; this directory documents the contract and will hold rendering templates as they appear (agent definitions arrive with M2 modules).

**Output for a vault whose `framework.runtimes` includes `claude-code`:**

- `provides.skills` of every enabled module → `.claude/skills/<skill-id>/**`, copied byte-for-byte (a skill is a static instruction package; one that documents `{{placeholder}}` syntax must survive verbatim). Managed, lock-tracked, attributed to the providing module — so disabling the module orphans them visibly and `remove` (M3) can clean them up.
- Declared sources (`sources.obsidian-skills`) → `.claude/skills/<name>/**` at the recorded pin, lock-tracked under the pseudo-module `source:obsidian-skills` (§6.1).
- Module agents → `.claude/agents/*.md`, rendered over resolved variables (§7.3) — lands with M2, when modules first ship agents.

Everything is ordinary desired state flowing through plan/apply/lock: no copytree side channels, no unledgered writes. Runtime paths are never folder-style transformed. Deleting the whole `.claude/` tree costs convenience, never function (P2).

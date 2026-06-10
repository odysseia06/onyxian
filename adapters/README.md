# Adapters

An adapter is a pure function: **(resolved module set, config) → runtime artifacts** (KICKSTART.md §7.4). They quarantine agent-runtime churn away from modules and the engine.

| Adapter | Output | Ships in |
|---|---|---|
| `claude-code` | skills → `.claude/skills/`, agents → `.claude/agents/`, commands → `.claude/commands/` | M1 |
| `codex` | skills copied to `~/.codex/skills` (consent required, `location: runtime` in the lock), generated `AGENTS.md` | M3 |
| `opencode` | repo-shaped skills under `~/.opencode/skills/` (consent required), generated `AGENTS.md` | M3 |
| `generic-agentsmd` | `AGENTS.md` in the vault embedding conventions, roster, and skill references | M3 |

Nothing here yet by design — M0 is the deterministic engine only, and the vault is fully functional without any of this (P2).

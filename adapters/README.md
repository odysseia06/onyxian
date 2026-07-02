# Adapters

An adapter is a pure function: **(resolved module set, config) → runtime artifacts**. They quarantine agent-runtime churn away from modules and the engine. The code lives in the engine at `core/onyxian/adapters.py`; this directory documents the contracts.

| Adapter | Output |
|---|---|
| `claude-code` | skills → `.claude/skills/`, agents → `.claude/agents/`, a managed `.claude/onyxian.md` digest behind a seeded `CLAUDE.md`, and a human-facing `Onyxian Assistant.md` |
| `generic-agentsmd` | `AGENTS.md` in the vault embedding conventions, roster, and skill references |
| `codex` | `AGENTS.md` today; runtime-installed skills under `~/.codex/skills` are planned |
| `opencode` | `AGENTS.md` today; repo-shaped skills under `~/.opencode/skills/` are planned |

Everything an adapter writes is ordinary desired state flowing through plan/apply/lock. The vault is fully functional without any of it (P2).

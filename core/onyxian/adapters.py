"""Runtime adapters: (resolved module set, config) -> runtime artifacts (KICKSTART.md §7.4).

An adapter's output is ordinary desired state — managed, module-attributed
``FileIntent``s that flow through the same plan/apply/lock pipeline as vault
content, so runtime artifacts are updatable, conflict-protected, and removable
exactly like everything else the engine writes. Deleting the whole ``.claude/``
tree costs the user convenience, never function (P2).

Skill packages are copied **byte-for-byte**: a skill is a static instruction
package, and one that documents the engine's own ``{{variable}}`` syntax must
survive verbatim. Vault-tailored artifacts (agent definitions whose scopes and
text render over resolved variables, §7.3) arrive with M2 modules.

M1 ships the ``claude-code`` adapter (skills into ``.claude/skills/``);
``generic-agentsmd``, ``codex``, and ``opencode`` land in M3. Runtime paths are
never folder-style transformed: ``.claude`` is a tooling directory, not vault
content.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping

import yaml

from .errors import ResolveError
from .fsio import encode_text, read_text, sha256_bytes
from .intent import FileIntent
from .model import KIND_MANAGED, KIND_SEEDED, AgentDef, Config, Manifest, ProvidedSkill, ScopeEntry
from .paths import split_portable
from .render import RenderContext, render_text

CLAUDE_SKILLS_PREFIX = ".claude/skills"
CLAUDE_AGENTS_PREFIX = ".claude/agents"
CLAUDE_MD_PATH = "CLAUDE.md"
CLAUDE_SETTINGS_PATH = ".claude/settings.json"
ONYXIAN_ORIENTATION_PATH = ".claude/onyxian.md"
ONYXIAN_ASSISTANT_PATH = "Onyxian Assistant.md"

# The least-privilege floor every rendered agent carries, beyond its own list (§7.1).
_STANDING_ESCALATIONS = (
    "any operation would delete, move, rename, or restructure existing files",
    "completing the task would require writing outside your write scope",
)


_OPERATING_PREAMBLE = [
    "## Operating the live vault",
    "",
    "- Drive the vault through the `obsidian` CLI. If `obsidian` is not on your PATH, "
    "find the redirector before concluding it is unavailable "
    "(on Windows, `%LOCALAPPDATA%\\Programs\\Obsidian\\Obsidian.com`).",
    "- Additive by default; look before you write; escalate before anything that would "
    "overwrite, move, delete, or restructure. The `vault-operations` skill is the full contract.",
]


def _frontmatter_description(text: str) -> str | None:
    """The `description:` from a SKILL.md YAML frontmatter block, or None if absent/malformed."""
    if not text.startswith("---"):
        return None
    body = text[3:]
    end = body.find("\n---")
    if end == -1:
        return None
    try:
        data = yaml.safe_load(body[:end])
    except yaml.YAMLError:
        return None
    if isinstance(data, dict):
        desc = data.get("description")
        if isinstance(desc, str) and desc.strip():
            return desc
    return None


def _skill_one_liner(skill: ProvidedSkill) -> str:
    """One appendix bullet for a shipped skill: its own SKILL.md description, or a fallback."""
    try:
        text = read_text(skill.directory / "SKILL.md")
    except OSError:
        return f"**{skill.id}** — see its `SKILL.md`."
    desc = _frontmatter_description(text)
    if not desc:
        return f"**{skill.id}** — see its `SKILL.md`."
    return f"**{skill.id}** — {' '.join(desc.split())}"


def _folders_from_scope(write_patterns: list[str]) -> list[str]:
    """Human-readable folders from an agent's resolved write scope (drop trailing globs, dedupe)."""
    folders: list[str] = []
    for pattern in write_patterns:
        folder = pattern
        for suffix in ("/**", "/*"):
            if folder.endswith(suffix):
                folder = folder[: -len(suffix)]
                break
        if folder in ("**", "*", ""):
            folder = "the whole vault"
        if folder not in folders:
            folders.append(folder)
    return folders


class ResolvedAgent:
    """An agent definition with every text field rendered and scopes resolved."""

    def __init__(
        self, agent: AgentDef, ctx: RenderContext, enabled_modules: set[str], *, origin: str
    ) -> None:
        def resolve_scope(entries: tuple[ScopeEntry, ...]) -> list[str]:
            resolved = []
            for entry in entries:
                if entry.requires is not None and entry.requires not in enabled_modules:
                    continue
                pattern = render_text(entry.pattern, ctx, origin=origin)
                if ".." in pattern.split("/") or "\\" in pattern:
                    raise ResolveError(
                        f"{origin}: scope pattern {pattern!r} escapes the vault after substitution"
                    )
                resolved.append(pattern)
            return resolved

        rt: Callable[[str], str] = lambda text: render_text(text, ctx, origin=origin)  # noqa: E731
        self.name = agent.name
        self.module = agent.module
        self.description = rt(agent.description)
        self.mission = rt(agent.mission)
        self.read = resolve_scope(agent.read)
        self.write = resolve_scope(agent.write)
        self.skills = list(agent.skills)
        self.escalations = [rt(item) for item in (*agent.escalate_when, *_STANDING_ESCALATIONS)]
        self.disclaimer = rt(agent.disclaimer) if agent.disclaimer else ""
        self.playbook = rt(agent.playbook) if agent.playbook else ""
        self.triggers = [rt(t) for t in agent.triggers]

    def body_lines(self) -> list[str]:
        lines = [self.mission, ""]
        if self.triggers:
            lines += ["## Reach for this agent when you hear", ""]
            lines += [f'- "{t}"' for t in self.triggers]
            lines += [""]
        lines += [
            "## Operating rules",
            "",
            "Follow the vault-conventions skill for every note you create or edit. "
            "Least privilege governs you: writing outside your write scope is a defect, "
            "not initiative.",
            "",
            "You may read:",
            "",
        ]
        lines += [f"- `{p}`" for p in self.read]
        lines += ["", "You may write only within:", ""]
        lines += (
            [f"- `{p}`" for p in self.write]
            if self.write
            else ["- (nowhere — this agent is read-only)"]
        )
        if self.playbook:
            lines += ["", *_OPERATING_PREAMBLE, "", "## Operating playbook", "", self.playbook]
        lines += ["", "## Escalate instead of acting when", ""]
        lines += [f"- {item}" for item in self.escalations]
        if self.skills:
            lines += ["", "## Skills to consult", ""]
            lines += [f"- {s}" for s in self.skills]
        if self.disclaimer:
            lines += [
                "",
                "## Mandatory disclaimer",
                "",
                f"End every substantive response with this exact line: {self.disclaimer}",
            ]
        return lines


def render_agent_markdown(
    agent: AgentDef, ctx: RenderContext, enabled_modules: set[str], *, origin: str
) -> str:
    """A Claude Code subagent definition: frontmatter + a scoped system prompt."""
    resolved = ResolvedAgent(agent, ctx, enabled_modules, origin=origin)
    lines = [
        "---",
        f"name: {resolved.name}",
        f"description: {json.dumps(resolved.description, ensure_ascii=False)}",
        "---",
        "",
        f"# {resolved.name}",
        "",
        *resolved.body_lines(),
        "",
    ]
    return "\n".join(lines)


AGENTS_MD_RUNTIMES = ("generic", "codex", "opencode")


def agents_md_intent(
    config: Config,
    manifests: list[Manifest],
    resolved_vars: dict[str, dict[str, object]],
    globals_: Mapping[str, object],
    core_version: str,
) -> FileIntent | None:
    """Generated `AGENTS.md` for non-Claude runtimes (§7.4): conventions digest,
    the agent roster with resolved scopes, and pointers to the skill packages.

    Vault-internal only; home-directory installs for Codex/OpenCode are a later
    consent-gated flow. Deterministic, managed, core-attributed — same pipeline
    as everything else the engine writes.
    """
    if not any(r in config.runtimes for r in AGENTS_MD_RUNTIMES):
        return None
    enabled_modules = {m.name for m in manifests}
    lines = [
        "# AGENTS.md — generated by Onyxian",
        "",
        "Instructions for agent runtimes operating this Obsidian vault. "
        "Generated from the enabled module set; regenerated when it changes — if you edit "
        "this file it becomes yours and updates will land beside it as `AGENTS.md.new`.",
        "",
        "## Vault conventions (the short version)",
        "",
        "- Framework-created notes carry `type`, `created` (ISO date, set once), `status` "
        "(per-type lifecycle), and `tags` (user-owned). Preserve unknown frontmatter keys "
        "byte-for-byte; never validate or reformat the user's own notes.",
        "- Wikilinks for internal references; plain markdown links only for external URLs. "
        "Do not hard-wrap prose — one logical line per paragraph or bullet.",
        "- `{{...}}` placeholders were the engine's and are already resolved; `<% tp.* %>` "
        "belongs to Templater — leave it exactly as written, or substitute real values "
        "when instantiating a template by hand.",
        "- Files tracked in `.vault/lock.json` are framework-managed: editing one hands it "
        "to the user and future updates arrive as `*.new` siblings. Never move, rename, or "
        "delete files you did not create; never touch `.vault/`.",
        "- The full rules ship as skill packages under `.claude/skills/` "
        "(`vault-conventions` first); read them, they are plain markdown.",
        "",
        "## Enabled modules",
        "",
    ]
    for manifest in manifests:
        summary = " ".join(manifest.summary.split())
        lines.append(f"- **{manifest.name}** {manifest.version} — {summary}")
    skill_ids = [skill.id for manifest in manifests for skill in manifest.skills]
    if skill_ids:
        lines += [
            "",
            "## Skill packages",
            "",
            "Workflow instructions, one folder per skill under `.claude/skills/` "
            "(plain markdown, runtime-agnostic):",
            "",
        ]
        lines += [f"- `.claude/skills/{skill_id}/SKILL.md`" for skill_id in skill_ids]
    for manifest in manifests:
        ctx = RenderContext(resolved_vars[manifest.name], resolved_vars, globals_)
        for agent in manifest.agents:
            origin = f"module {manifest.name!r}: agent {agent.name!r} (AGENTS.md)"
            resolved = ResolvedAgent(agent, ctx, enabled_modules, origin=origin)
            lines += [
                "",
                "---",
                "",
                f"# Agent: {resolved.name}",
                "",
                f"_{resolved.description}_",
                "",
            ]
            lines += resolved.body_lines()
    lines.append("")
    content = encode_text("\n".join(lines))
    return FileIntent(
        path="AGENTS.md",
        content=content,
        sha256=sha256_bytes(content),
        kind=KIND_MANAGED,
        module="core",
        module_version=core_version,
    )


def claude_orientation_intents(
    config: Config,
    manifests: list[Manifest],
    resolved_vars: dict[str, dict[str, object]],
    globals_: Mapping[str, object],
    core_version: str,
) -> list[FileIntent]:
    """The Claude Code front door (§7.4): a seeded ``CLAUDE.md`` wrapper plus the
    managed ``.claude/onyxian.md`` digest it imports.

    ``CLAUDE.md`` is loaded automatically every session, so it is where an agent
    learns it is in an Onyxian vault, how to drive it through the ``obsidian`` CLI,
    and which agents to reach for. The wrapper is *seeded* — written once and
    never reconciled, so the user owns it and ``adopt`` never clobbers an
    existing CLAUDE.md. The roster and operating contract live in the *managed*
    digest, regenerated as the module set changes. Both are absent unless the
    claude-code runtime is enabled (parity with AGENTS.md for other runtimes).
    """
    if "claude-code" not in config.runtimes:
        return []

    roster: list[str] = []
    for manifest in manifests:
        ctx = RenderContext(resolved_vars[manifest.name], resolved_vars, globals_)
        for agent in manifest.agents:
            origin = f"module {manifest.name!r}: agent {agent.name!r} (CLAUDE.md)"
            line = f"- **{agent.name}** — {render_text(agent.description, ctx, origin=origin)}"
            if agent.triggers:
                line += f' Say e.g. "{render_text(agent.triggers[0], ctx, origin=origin)}".'
            roster.append(line)
    skill_ids = [skill.id for manifest in manifests for skill in manifest.skills]

    digest = [
        "# Onyxian — how to work in this vault",
        "",
        "Generated by Onyxian from the enabled modules and regenerated as they change — "
        "do not edit it; put your own instructions in `CLAUDE.md`, which imports this. "
        "The vault works as plain files; none of this is required for it to function.",
        "",
        "## Operate the live vault through the obsidian CLI",
        "",
        "- Use the official `obsidian` CLI for anything live. If `obsidian` is not on PATH "
        "it may still be installed — find the redirector first "
        "(Windows `%LOCALAPPDATA%\\Programs\\Obsidian\\Obsidian.com`, "
        "macOS `/usr/local/bin/obsidian`, Linux `~/.local/bin/obsidian`).",
        "- Read the `vault-operations` skill before any command that changes the vault: "
        "additive by default, within scope, look before you write, "
        "escalate before overwrite / move / delete.",
        "- Read the `vault-conventions` skill before creating or editing a note: typed "
        "frontmatter (`type`, `created`, `status`, `tags`), wikilinks, never hard-wrap "
        "prose, never reformat a note the user wrote.",
    ]
    if roster:
        digest += [
            "",
            "## Agents — reach for one when the task fits",
            "",
            *roster,
            "",
            "Invoke an agent by name; each carries its own read/write scope and a "
            "step-by-step playbook in `.claude/agents/<name>.md`.",
        ]
    if skill_ids:
        joined = ", ".join(f"`{s}`" for s in skill_ids)
        digest += [
            "",
            "## Skills",
            "",
            f"Installed in `.claude/skills/`: {joined} — read the relevant "
            "`SKILL.md` when it applies.",
        ]
    digest.append("")
    digest_bytes = encode_text("\n".join(digest))

    vault_name = str(globals_.get("vault_name", "Vault"))
    wrapper = [
        f"# {vault_name}",
        "",
        "An Obsidian vault scaffolded and operated by "
        "[Onyxian](https://github.com/odysseia06/onyxian) — it works as plain files; "
        "the agent layer only amplifies.",
        "",
        "The agent orientation for this vault lives in `.claude/onyxian.md` (imported "
        "below); Onyxian keeps it current as you enable modules. This `CLAUDE.md` is "
        "yours — add anything you like; Onyxian writes it once and never touches it again.",
        "",
        "@.claude/onyxian.md",
        "",
    ]
    wrapper_bytes = encode_text("\n".join(wrapper))

    return [
        FileIntent(
            path=ONYXIAN_ORIENTATION_PATH,
            content=digest_bytes,
            sha256=sha256_bytes(digest_bytes),
            kind=KIND_MANAGED,
            module="core",
            module_version=core_version,
        ),
        FileIntent(
            path=CLAUDE_MD_PATH,
            content=wrapper_bytes,
            sha256=sha256_bytes(wrapper_bytes),
            kind=KIND_SEEDED,
            module="core",
            module_version=core_version,
        ),
    ]


def assistant_guide_intent(
    config: Config,
    manifests: list[Manifest],
    resolved_vars: dict[str, dict[str, object]],
    globals_: Mapping[str, object],
    core_version: str,
) -> FileIntent | None:
    """A human-facing `Onyxian Assistant.md` (§7.4): what each agent does, what to say,
    and where its work lands, plus a skills appendix.

    Reuses `ResolvedAgent` so the prose matches the generated agent files and
    `onyxian.md`. Managed, core-attributed, claude-code-gated; no dates so golden
    trees stay byte-exact. Rendered even for a core-only vault (no agents).
    """
    if "claude-code" not in config.runtimes:
        return None
    enabled_modules = {m.name for m in manifests}

    lines = [
        "---",
        "type: assistant-guide",
        "status: active",
        "tags: []",
        "---",
        "",
        "# What your assistant can do",
        "",
        "This vault works as plain files — none of this is required. With Claude Code "
        "open, the agents below operate the vault for you: say what you want and the "
        "right one does the work, additively and within its lane. Onyxian regenerates "
        "this note as you enable or remove modules.",
        "",
        "## Agents",
        "",
    ]

    blocks: list[list[str]] = []
    for manifest in manifests:
        ctx = RenderContext(resolved_vars[manifest.name], resolved_vars, globals_)
        for agent in manifest.agents:
            origin = f"module {manifest.name!r}: agent {agent.name!r} (Onyxian Assistant.md)"
            resolved = ResolvedAgent(agent, ctx, enabled_modules, origin=origin)
            block = [f"### {resolved.name}", resolved.description]
            if resolved.triggers:
                says = " · ".join(f'"{t}"' for t in resolved.triggers)
                block.append(f"Say e.g.: {says}")
            folders = _folders_from_scope(resolved.write)
            if folders:
                block.append("Where its work lands: " + ", ".join(f"`{f}`" for f in folders))
            else:
                block.append("Reads only; never writes on its own.")
            blocks.append(block)

    if blocks:
        for block in blocks:
            lines += block
            lines.append("")
    else:
        lines += ["Domain agents arrive as you enable modules (try `onyxian add <module>`).", ""]

    skills = [skill for manifest in manifests for skill in manifest.skills]
    if skills:
        lines += [
            "## Skills under the hood",
            "",
            "Instruction packages in `.claude/skills/` the agents lean on. You never invoke "
            "these by name — they are listed so you know what is there.",
            "",
        ]
        lines += [f"- {_skill_one_liner(skill)}" for skill in skills]
        lines.append("")

    lines += [
        "## If you'd rather not use AI",
        "",
        "Delete `.claude/` and everything here still works — templates are plain copies, "
        "views are plain files. See `Start-Here.md` for the no-AI tour.",
        "",
    ]

    content = encode_text("\n".join(lines))
    return FileIntent(
        path=ONYXIAN_ASSISTANT_PATH,
        content=content,
        sha256=sha256_bytes(content),
        kind=KIND_MANAGED,
        module="core",
        module_version=core_version,
    )


def claude_settings_intent(config: Config, core_version: str) -> FileIntent | None:
    """A seeded ``.claude/settings.json`` wiring the checkpoint guard to session start.

    Emitted only when the user opted into checkpoints (``framework.checkpoints``)
    **and** the claude-code runtime is enabled. Seeded — written once and never
    reconciled: the hook's *behavior* updates through the ``onyxian`` CLI it
    invokes, so the file itself never needs to change, and settings files are a
    merge magnet both Claude Code and users edit, so the engine claims it once and
    then leaves it alone. If an unmanaged one already exists the planner reports it
    ``blocked`` and never overwrites it. The command is a bare console-script call
    with no shell metacharacters, so it runs identically under sh and cmd.
    """
    if not config.checkpoints or "claude-code" not in config.runtimes:
        return None
    settings = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume|clear",
                    "hooks": [{"type": "command", "command": "onyxian checkpoint --quiet"}],
                }
            ]
        }
    }
    content = encode_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    return FileIntent(
        path=CLAUDE_SETTINGS_PATH,
        content=content,
        sha256=sha256_bytes(content),
        kind=KIND_SEEDED,
        module="core",
        module_version=core_version,
    )


def claude_code_intents(
    config: Config,
    manifests: list[Manifest],
    resolved_vars: dict[str, dict[str, object]],
    globals_: Mapping[str, object],
) -> list[FileIntent]:
    """Skill packages and rendered agents of every enabled module, under `.claude/`.

    Skill packages are Agent-Skills-spec markdown and install for *every*
    runtime (D9: non-Claude runtimes get skills-level support; the generated
    AGENTS.md points at them). Only the rendered subagent files are
    Claude-Code-specific.
    """
    render_claude_agents = "claude-code" in config.runtimes
    enabled_modules = {m.name for m in manifests}
    intents: list[FileIntent] = []
    seen_ids: dict[str, str] = {}
    for manifest in manifests:
        ctx = RenderContext(resolved_vars[manifest.name], resolved_vars, globals_)
        for agent in manifest.agents if render_claude_agents else ():
            path = f"{CLAUDE_AGENTS_PREFIX}/{agent.name}.md"
            origin = f"module {manifest.name!r}: agent {agent.name!r}"
            if path in {i.path for i in intents}:
                raise ResolveError(f"agent name collision at {path}")
            split_portable(path, origin=origin)
            content = encode_text(render_agent_markdown(agent, ctx, enabled_modules, origin=origin))
            intents.append(
                FileIntent(
                    path=path,
                    content=content,
                    sha256=sha256_bytes(content),
                    kind=KIND_MANAGED,
                    module=manifest.name,
                    module_version=manifest.version,
                )
            )
        for skill in manifest.skills:
            if skill.id in seen_ids:
                raise ResolveError(
                    f"skill id collision: modules {seen_ids[skill.id]!r} and "
                    f"{manifest.name!r} both ship a skill called {skill.id!r}"
                )
            seen_ids[skill.id] = manifest.name
            for source in sorted(skill.directory.rglob("*"), key=lambda p: p.as_posix()):
                if not source.is_file():
                    continue
                rel = source.relative_to(skill.directory).as_posix()
                path = f"{CLAUDE_SKILLS_PREFIX}/{skill.id}/{rel}"
                origin = f"module {manifest.name!r}: skill {skill.id!r}: {rel}"
                split_portable(path, origin=origin)
                content = source.read_bytes()
                intents.append(
                    FileIntent(
                        path=path,
                        content=content,
                        sha256=sha256_bytes(content),
                        kind=KIND_MANAGED,
                        module=manifest.name,
                        module_version=manifest.version,
                    )
                )
    return intents

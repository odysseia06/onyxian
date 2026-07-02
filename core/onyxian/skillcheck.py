"""Validate that agent `skills:` lists resolve to a real, installable skill.

An agent in module M may name a skill provided by a module in M's transitive
dependency closure, or a curated external (kepano) skill id. Anything else is a
broken reference that would mislead the agent in a vault that does not enable
the other module (the projects-software -> task-capture bug) or that names a
non-existent external skill (the obsidian-cli phantom).
"""
from __future__ import annotations

from .errors import ResolveError
from .model import Manifest
from .sources import EXTERNAL_SKILL_IDS


def _closure(name: str, library: dict[str, Manifest]) -> set[str]:
    seen: set[str] = set()
    stack = [name]
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in library:
            continue
        seen.add(cur)
        stack.extend(library[cur].depends)
    return seen


def available_skills(name: str, library: dict[str, Manifest]) -> set[str]:
    """Skill ids an agent in `name` may reference: closure module skills + external."""
    skills = set(EXTERNAL_SKILL_IDS)
    for mod in _closure(name, library):
        skills.update(s.id for s in library[mod].skills)
    return skills


def check_agent_skills(library: dict[str, Manifest]) -> None:
    for manifest in library.values():
        avail = available_skills(manifest.name, library)
        for agent in manifest.agents:
            for skill in agent.skills:
                if skill not in avail:
                    raise ResolveError(
                        f"agent {manifest.name}/{agent.name} references skill {skill!r}, "
                        f"which no module in its dependency closure provides and which is "
                        f"not a known external skill. Add a depends on the providing module, "
                        f"or drop the reference."
                    )

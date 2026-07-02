"""Every agent's skills: must resolve to an installed/known skill (no broken refs)."""
import pytest

from conftest import REAL_MODULES, write_module
from onyxian.errors import ResolveError
from onyxian.repo import discover_modules
from onyxian.skillcheck import available_skills, check_agent_skills

def _agent(agent_id: str, module: str = "demo", **extra) -> dict:
    return {
        "name": agent_id,
        "module": module,
        "description": "x.",
        "mission": "Tend {{root}}.",
        "scope": {"read": ["{{root}}/**"], "write": ["{{root}}/**"]},
        **extra,
    }


def test_every_real_agent_skill_resolves():
    library = discover_modules(REAL_MODULES)
    for manifest in library.values():
        avail = available_skills(manifest.name, library)
        for agent in manifest.agents:
            unresolved = [s for s in agent.skills if s not in avail]
            assert not unresolved, f"{manifest.name}/{agent.name} references {unresolved}"


def test_unresolved_skill_is_rejected(tmp_path):
    write_module(tmp_path, "core")
    write_module(
        tmp_path, "demo",
        variables=[{"key": "root", "prompt": "r", "default": "Demo"}],
        folders=["{{root}}"],
        agents={"demo-agent": _agent("demo-agent", skills=["no-such-skill"])},
    )
    library = discover_modules(tmp_path)
    with pytest.raises(ResolveError, match="no-such-skill"):
        check_agent_skills(library)

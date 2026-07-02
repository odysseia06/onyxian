"""Agent definitions: schema, rendering, least-privilege floor (KICKSTART.md §7)."""

import pytest
import yaml

from conftest import make_config, plan_for, write_module
from onyxian.applier import apply_plan
from onyxian.errors import ManifestError
from onyxian.intent import build_desired_state
from onyxian.lockio import load_lock
from onyxian.manifests import load_manifest
from onyxian.repo import discover_modules
from onyxian.resolve import resolve_modules


def agent_def(**overrides) -> dict:
    base = {
        "name": "demo-agent",
        "module": "demo",
        "description": "Test agent: keeps the demo domain tidy.",
        "mission": "Tend {{root}} and nothing else. Cadence: {{cadence}}.",
        "scope": {
            "read": ["{{root}}/**", {"path": "{{journal.root}}/**", "requires": "journal"}],
            "write": ["{{root}}/Output/**"],
        },
        "skills": ["obsidian-markdown"],
        "escalate_when": ["the {{root}} dashboard is missing"],
        "disclaimer": "Not advice.",
    }
    base.update(overrides)
    return base


@pytest.fixture
def library_root(tmp_path):
    root = tmp_path / "modules"
    write_module(root, "core")
    write_module(
        root,
        "demo",
        variables=[
            {"key": "root", "prompt": "Root", "default": "Demo-Stuff"},
            {"key": "cadence", "prompt": "Cadence", "type": "choice", "options": ["weekly", "monthly"], "default": "weekly"},
        ],
        folders=["{{root}}/Output"],
        agents={"demo-agent": agent_def()},
    )
    write_module(root, "journal", variables=[{"key": "root", "prompt": "Root", "default": "Journal"}], folders=["{{root}}"])
    return root


def rendered_agent(library_root, config) -> str:
    library = discover_modules(library_root)
    manifests = resolve_modules(config, library)
    files = build_desired_state(config, manifests).file_by_path()
    return files[".claude/agents/demo-agent.md"].content.decode("utf-8")


def test_agent_renders_with_resolved_variables(library_root):
    config = make_config({"demo": {"version": "0.1.0"}})
    text = rendered_agent(library_root, config)
    assert "Tend Demo-Stuff and nothing else. Cadence: weekly." in text
    assert "- `Demo-Stuff/**`" in text
    assert "- `Demo-Stuff/Output/**`" in text
    assert "- the Demo-Stuff dashboard is missing" in text
    assert "End every substantive response with this exact line: Not advice." in text
    assert "## Operating playbook" not in text  # agent_def() declares no playbook


def test_playbook_renders_as_its_own_section(tmp_path):
    """An agent with a `playbook` gets a concrete '## Operating playbook' section (live-vault pilot)."""
    root = tmp_path / "modules"
    write_module(root, "core")
    write_module(
        root,
        "demo",
        variables=[
            {"key": "root", "prompt": "Root", "default": "Demo-Stuff"},
            {"key": "cadence", "prompt": "Cadence", "type": "choice", "options": ["weekly", "monthly"], "default": "weekly"},
        ],
        folders=["{{root}}/Output"],
        agents={"demo-agent": agent_def(playbook="Run `obsidian daily:read` over {{root}} before writing.")},
    )
    config = make_config({"demo": {"version": "0.1.0"}})
    manifests = resolve_modules(config, discover_modules(root))
    text = build_desired_state(config, manifests).file_by_path()[".claude/agents/demo-agent.md"].content.decode("utf-8")
    assert "## Operating playbook" in text
    assert "Run `obsidian daily:read` over Demo-Stuff before writing." in text


def test_triggers_render_as_a_section(tmp_path):
    """An agent with `triggers` lists them under '## Reach for this agent when you hear'."""
    root = tmp_path / "modules"
    write_module(root, "core")
    write_module(
        root,
        "demo",
        variables=[
            {"key": "root", "prompt": "Root", "default": "Demo-Stuff"},
            {"key": "cadence", "prompt": "Cadence", "type": "choice", "options": ["weekly", "monthly"], "default": "weekly"},
        ],
        folders=["{{root}}/Output"],
        agents={"demo-agent": agent_def(triggers=["log this", "we decided"])},
    )
    config = make_config({"demo": {"version": "0.1.0"}})
    manifests = resolve_modules(config, discover_modules(root))
    text = build_desired_state(config, manifests).file_by_path()[".claude/agents/demo-agent.md"].content.decode("utf-8")
    assert "## Reach for this agent when you hear" in text
    assert '- "log this"' in text


def test_playbook_agents_get_the_operating_preamble(tmp_path):
    """A playbook agent inherits the shared operating preamble before its own steps."""
    root = tmp_path / "modules"
    write_module(root, "core")
    write_module(
        root,
        "demo",
        variables=[
            {"key": "root", "prompt": "Root", "default": "Demo-Stuff"},
            {"key": "cadence", "prompt": "Cadence", "type": "choice", "options": ["weekly", "monthly"], "default": "weekly"},
        ],
        folders=["{{root}}/Output"],
        agents={"demo-agent": agent_def(playbook="1. do the thing.")},
    )
    config = make_config({"demo": {"version": "0.1.0"}})
    manifests = resolve_modules(config, discover_modules(root))
    text = build_desired_state(config, manifests).file_by_path()[".claude/agents/demo-agent.md"].content.decode("utf-8")
    assert "## Operating the live vault" in text  # the shared preamble heading
    assert "1. do the thing." in text             # the agent's own steps


def test_cross_module_scope_drops_when_module_disabled(library_root):
    config = make_config({"demo": {"version": "0.1.0"}})
    text = rendered_agent(library_root, config)
    assert "Journal" not in text  # requires: journal, and journal is not enabled


def test_cross_module_scope_resolves_when_enabled(library_root):
    config = make_config({"demo": {"version": "0.1.0"}, "journal": {"version": "0.1.0"}})
    text = rendered_agent(library_root, config)
    assert "- `Journal/**`" in text


def test_least_privilege_floor_is_always_present(library_root):
    config = make_config({"demo": {"version": "0.1.0"}})
    text = rendered_agent(library_root, config)
    assert "delete, move, rename, or restructure" in text
    assert "outside your write scope" in text


def test_frontmatter_description_is_yaml_safe(library_root):
    config = make_config({"demo": {"version": "0.1.0"}})
    text = rendered_agent(library_root, config)
    frontmatter = yaml.safe_load(text.split("---\n")[1])
    assert frontmatter["name"] == "demo-agent"
    assert frontmatter["description"].startswith("Test agent")


def test_agents_are_lock_tracked_and_module_attributed(library_root, tmp_path):
    config = make_config({"demo": {"version": "0.1.0"}})
    vault = tmp_path / "vault"
    vault.mkdir()
    plan, _, lock = plan_for(vault, library_root, config)
    assert apply_plan(vault, plan, lock).ok
    entry = load_lock(vault).get(".claude/agents/demo-agent.md")
    assert entry is not None and entry.module == "demo" and entry.kind == "managed"


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda d: d.pop("description"), "description"),
        (lambda d: d.pop("mission"), "mission"),
        (lambda d: d.update(module="other"), "'module' must be"),
        (lambda d: d.update(name="wrong-name"), "'name' must equal"),
        (lambda d: d.update(extra_key=1), "unknown key"),
        (lambda d: d["scope"].update(execute=["x"]), "only read/write"),
        (lambda d: d["scope"].update(read=[]), "must not be empty"),
        (lambda d: d["scope"].update(read=["C:/absolute"]), "vault-relative"),
        (lambda d: d["scope"].update(read=["a/../b"]), "escapes the vault"),
        (lambda d: d["scope"].update(read=[{"path": "x/**", "requires": "Bad Id"}]), "module id"),
    ],
)
def test_agent_schema_violations(tmp_path, mutate, match):
    definition = agent_def()
    mutate(definition)
    write_module(tmp_path, "demo", agents={"demo-agent": definition})
    with pytest.raises(ManifestError, match=match):
        load_manifest(tmp_path / "demo")


def test_unlisted_agent_definition_is_rejected(tmp_path):
    module_dir = write_module(tmp_path, "demo", agents={"demo-agent": agent_def()})
    rogue = module_dir / "agents" / "rogue.yaml"
    rogue.write_text(yaml.safe_dump(agent_def(name="rogue")), encoding="utf-8")
    with pytest.raises(ManifestError, match="rogue"):
        load_manifest(module_dir)

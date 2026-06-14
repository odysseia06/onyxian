"""The Claude Code plugin mirrors the canonical skills and has valid manifests.

The plugin is the Claude Code front door (`/plugin install onyx@onyx`); its
skills are generated from modules/core/skills/ by tools/build_plugin.py and must
not drift. The manifests are hand-maintained but must stay valid and leak no
personal contact info (we publish them).
"""

import json

from conftest import REPO_ROOT

PLUGIN = REPO_ROOT / "plugin"


def test_plugin_skills_mirror_canonical_sources():
    for skill in ("vault-bootstrap", "vault-conventions"):
        src = REPO_ROOT / "modules" / "core" / "skills" / skill
        dst = PLUGIN / "skills" / skill
        assert dst.is_dir(), f"plugin skill {skill!r} missing; run `python tools/build_plugin.py`"
        src_files = {p.relative_to(src).as_posix(): p.read_bytes() for p in src.rglob("*") if p.is_file()}
        dst_files = {p.relative_to(dst).as_posix(): p.read_bytes() for p in dst.rglob("*") if p.is_file()}
        assert dst_files == src_files, (
            f"plugin/skills/{skill} drifted from modules/core/skills/{skill}; "
            "run `python tools/build_plugin.py`"
        )


def test_plugin_manifest_is_valid_and_clean():
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "onyx"
    assert manifest["version"]
    assert "email" not in json.dumps(manifest), "no personal email in a published manifest"


def test_marketplace_manifest_points_at_the_plugin():
    mkt = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert mkt["name"] == "onyx"
    entry = next(p for p in mkt["plugins"] if p["name"] == "onyx")
    assert entry["source"] == "./plugin"
    assert (REPO_ROOT / "plugin" / ".claude-plugin" / "plugin.json").is_file()  # source resolves
    assert "email" not in json.dumps(mkt), "no personal email in a published manifest"


def test_bootstrap_skill_self_installs_the_cli():
    """The plugin's whole point: the wizard installs the engine, the user does nothing."""
    body = (PLUGIN / "skills" / "vault-bootstrap" / "SKILL.md").read_text(encoding="utf-8")
    assert "onyx-vault" in body
    for installer in ("uv tool install", "pipx install", "pip install --user"):
        assert installer in body

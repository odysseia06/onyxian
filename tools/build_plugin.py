#!/usr/bin/env python
"""Regenerate the Claude Code plugin from the canonical sources + the pyproject version.

The plugin (``plugin/``) is the Claude Code front door: ``/plugin marketplace
add odysseia06/onyxian`` then ``/plugin install onyxian@onyxian``. This is its single
generator, and CI fails on drift:

- ``plugin/skills/`` mirrors ``modules/core/skills/{vault-bootstrap,
  vault-conventions}`` (one source of truth for the skill content).
- ``plugin/.claude-plugin/plugin.json`` and the repo-root
  ``.claude-plugin/marketplace.json`` are written here with the version read
  from ``ENGINE_VERSION`` (core/onyxian/__init__.py) — the single source the
  wheel, the CLI, and generated vaults all read (issue #5). The plugin therefore
  always carries the SAME version as the onyxian engine — no drift, no forgotten bump.

Claude Code uses the plugin's ``version`` as its update cache key, so bumping the
engine version in pyproject and re-running this is what makes existing plugin
users pick up skill changes. To release: bump pyproject, run this, commit.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "modules" / "core" / "skills"
DST = REPO / "plugin" / "skills"
SKILLS = [
    "vault-bootstrap",
    "vault-conventions",
    "obsidian-tasks",
    "obsidian-templater",
    "vault-operations",
]


def _project_version() -> str:
    # ENGINE_VERSION is the single version source (issue #5); import it the same
    # way tools/regen_golden.py imports the onyxian package. The sys.path insert
    # makes `core/onyxian` importable when running from a bare checkout.
    if str(REPO / "core") not in sys.path:
        sys.path.insert(0, str(REPO / "core"))
    from onyxian import ENGINE_VERSION

    return ENGINE_VERSION


def _write_json(path: Path, data: dict) -> None:
    # newline="\n" forces LF on every OS; without it Windows writes CRLF and the
    # repo (.gitattributes eol=lf) sees the generated file as drifted on the
    # Windows CI leg.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> int:
    for skill in SKILLS:
        src = SRC / skill
        if not (src / "SKILL.md").is_file():
            print(f"error: canonical skill missing at {src}", file=sys.stderr)
            return 1
        dst = DST / skill
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"synced {skill} -> {dst.relative_to(REPO).as_posix()}")

    version = _project_version()

    _write_json(
        REPO / "plugin" / ".claude-plugin" / "plugin.json",
        {
            "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
            "name": "onyxian",
            "version": version,
            "description": (
                "Bootstrap and operate a tailored Obsidian vault. Ships the vault-bootstrap "
                "wizard and the shared vault conventions; the wizard installs the onyxian "
                "CLI on first use."
            ),
            "author": {"name": "odysseia06", "url": "https://github.com/odysseia06"},
            "homepage": "https://github.com/odysseia06/onyxian",
            "keywords": ["obsidian", "knowledge-management", "agent-skills", "pkm", "claude-code"],
        },
    )

    _write_json(
        REPO / ".claude-plugin" / "marketplace.json",
        {
            "name": "onyxian",
            "owner": {"name": "odysseia06"},
            "plugins": [
                {
                    "name": "onyxian",
                    "source": "./plugin",
                    "description": (
                        "Bootstrap and operate a tailored Obsidian vault with Onyxian — the "
                        "vault-bootstrap wizard plus the shared vault conventions. Pairs with "
                        "the onyxian CLI on PyPI."
                    ),
                    "version": version,
                    "author": {"name": "odysseia06"},
                }
            ],
        },
    )
    print(f"wrote manifests at version {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

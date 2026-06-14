#!/usr/bin/env python
"""Regenerate the Claude Code plugin's skill copies from the canonical sources.

The plugin (``plugin/``) is the Claude Code front door: ``/plugin marketplace
add odysseia06/onyx`` then ``/plugin install onyx@onyx`` installs the
``vault-bootstrap`` and ``vault-conventions`` skills (the skill's frontmatter
``name`` becomes the ``/vault-bootstrap`` shortcut). Those skills have one
source of truth under ``modules/core/skills/``; this mirrors them into
``plugin/skills/`` so the two cannot drift. CI reruns it and fails on any diff.

The manifests (``plugin/.claude-plugin/plugin.json`` and the repo-root
``.claude-plugin/marketplace.json``) are hand-maintained, not generated.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "modules" / "core" / "skills"
DST = REPO / "plugin" / "skills"
SKILLS = ["vault-bootstrap", "vault-conventions"]


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

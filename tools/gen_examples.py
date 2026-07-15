#!/usr/bin/env python
"""Regenerate the reference vaults under examples/ from the profiles (KICKSTART.md D6).

Examples are engine-generated, never hand-edited; CI reruns this script and
fails on any drift, which makes every example a standing integration test.
ONYXIAN_NOW is pinned so the trees are byte-identical on every machine and OS.

examples/demo is the one exception to "fresh init": it is the
researcher-developer profile plus a deterministic overlay of lived-in demo
content from tools/demo_content/ (hand-authored there, never in examples/),
so Bases views render populated for newcomers. Same regeneration rule: this
script is the only writer, CI fails on drift.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PINNED_NOW = "2026-01-01"  # must match tests/conftest.py::NOW


def main() -> int:
    try:
        from onyxian.cli import main as onyxian_main
    except ImportError:
        print(
            "error: the onyxian package is not importable; run `pip install -e .[dev]` first",
            file=sys.stderr,
        )
        return 1

    os.environ["ONYXIAN_NOW"] = PINNED_NOW
    profiles = sorted((REPO / "profiles").glob("*.yaml"))
    if not profiles:
        print("error: no profiles found", file=sys.stderr)
        return 1
    for profile in profiles:
        target = REPO / "examples" / profile.stem
        if target.exists():
            shutil.rmtree(target)
        code = onyxian_main(["init", str(target), "--answers", str(profile), "--yes"])
        if code != 0:
            print(f"error: example {profile.stem!r} failed with exit code {code}", file=sys.stderr)
            return code
        print(f"regenerated {target}")

    demo_content = REPO / "tools" / "demo_content"
    if demo_content.is_dir():
        target = REPO / "examples" / "demo"
        if target.exists():
            shutil.rmtree(target)
        code = onyxian_main(
            [
                "init",
                str(target),
                "--answers",
                str(REPO / "profiles" / "researcher-developer.yaml"),
                "--yes",
            ]
        )
        if code != 0:
            print(f"error: demo vault init failed with exit code {code}", file=sys.stderr)
            return code
        for src in sorted(demo_content.rglob("*")):
            if src.is_file():
                dst = target / src.relative_to(demo_content)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
        print(f"regenerated {target} (researcher-developer + tools/demo_content overlay)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

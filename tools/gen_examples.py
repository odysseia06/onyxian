#!/usr/bin/env python
"""Regenerate the reference vaults under examples/ from the profiles (KICKSTART.md D6).

Examples are engine-generated, never hand-edited; CI reruns this script and
fails on any drift, which makes every example a standing integration test.
ONYX_NOW is pinned so the trees are byte-identical on every machine and OS.
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
        from onyx.cli import main as onyx_main
    except ImportError:
        print("error: the onyx package is not importable; run `pip install -e .[dev]` first", file=sys.stderr)
        return 1

    os.environ["ONYX_NOW"] = PINNED_NOW
    profiles = sorted((REPO / "profiles").glob("*.yaml"))
    if not profiles:
        print("error: no profiles found", file=sys.stderr)
        return 1
    for profile in profiles:
        target = REPO / "examples" / profile.stem
        if target.exists():
            shutil.rmtree(target)
        code = onyx_main(["init", str(target), "--answers", str(profile), "--yes"])
        if code != 0:
            print(f"error: example {profile.stem!r} failed with exit code {code}", file=sys.stderr)
            return code
        print(f"regenerated {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

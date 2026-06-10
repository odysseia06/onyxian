#!/usr/bin/env python
"""Regenerate the golden vault fixtures under tests/fixtures/golden/.

The only legitimate way to change a golden tree (CONTRIBUTING.md). Pins
ONYX_NOW so the result is byte-identical on every machine and OS; review the
resulting diff like any other code change.

Requires the package to be installed (`pip install -e .[dev]`).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PINNED_NOW = "2026-01-01"  # must match tests/conftest.py::NOW

GOLDENS = {
    "minimal": REPO / "tests" / "fixtures" / "answers" / "minimal.yaml",
}


def main() -> int:
    try:
        from onyx.cli import main as onyx_main
    except ImportError:
        print("error: the onyx package is not importable; run `pip install -e .[dev]` first", file=sys.stderr)
        return 1

    os.environ["ONYX_NOW"] = PINNED_NOW
    for name, answers in GOLDENS.items():
        target = REPO / "tests" / "fixtures" / "golden" / name
        if target.exists():
            shutil.rmtree(target)
        code = onyx_main(["init", str(target), "--answers", str(answers), "--yes"])
        if code != 0:
            print(f"error: regeneration of {name!r} failed with exit code {code}", file=sys.stderr)
            return code
        print(f"regenerated {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

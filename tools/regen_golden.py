#!/usr/bin/env python
"""Regenerate the golden vault fixtures under tests/fixtures/golden/.

The only legitimate way to change a golden tree (CONTRIBUTING.md). Pins
ONYXIAN_NOW so the result is byte-identical on every machine and OS; review the
resulting diff like any other code change.

Requires the package to be installed (`pip install -e .[dev]`).
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PINNED_NOW = "2026-01-01"  # must match tests/conftest.py::NOW

GOLDENS = {
    "minimal": REPO / "tests" / "fixtures" / "answers" / "minimal.yaml",
}


def regen_lifecycle() -> None:
    """Snapshot every mutation-lifecycle scenario (tools/lifecycle_scenarios.py)
    into tests/fixtures/golden/lifecycle/<name>/{before,after}. The scenarios
    point ONYXIAN_HOME at the synthetic libraries under tests/fixtures/lifecycle/,
    so restore the caller's value afterwards."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import lifecycle_scenarios as scenarios

    saved_home = os.environ.get("ONYXIAN_HOME")
    try:
        for scenario in scenarios.SCENARIOS:
            target = REPO / "tests" / "fixtures" / "golden" / "lifecycle" / scenario.name
            if target.exists():
                shutil.rmtree(target)
            with tempfile.TemporaryDirectory(prefix="onyxian-lifecycle-") as tmp:
                vault = Path(tmp) / "vault"
                scenarios.run_scenario(
                    scenario,
                    vault,
                    after_build=lambda r: shutil.copytree(vault, target / "before"),
                )
                shutil.copytree(vault, target / "after")
            print(f"regenerated {target}")
    finally:
        if saved_home is None:
            os.environ.pop("ONYXIAN_HOME", None)
        else:
            os.environ["ONYXIAN_HOME"] = saved_home


def main() -> int:
    try:
        from onyxian.cli import main as onyxian_main
    except ImportError:
        print("error: the onyxian package is not importable; run `pip install -e .[dev]` first", file=sys.stderr)
        return 1

    os.environ["ONYXIAN_NOW"] = PINNED_NOW
    for name, answers in GOLDENS.items():
        target = REPO / "tests" / "fixtures" / "golden" / name
        if target.exists():
            shutil.rmtree(target)
        code = onyxian_main(["init", str(target), "--answers", str(answers), "--yes"])
        if code != 0:
            print(f"error: regeneration of {name!r} failed with exit code {code}", file=sys.stderr)
            return code
        print(f"regenerated {target}")
    regen_lifecycle()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Regenerate every generated tree — the single entrypoint (issue #80).

The three generators below are what CI diffs for drift, and the sequence used to
live only in prose (CLAUDE.md, RELEASING.md, the `/regen-artifacts` skill), which
made "run all three" a convention rather than a command. Adding a fourth generated
tree means adding its script here; nothing else has to learn the new name.

Each script runs as a subprocess rather than an import: they pin `ONYXIAN_NOW` by
mutating `os.environ` and drive the CLI in-process, so a shared interpreter would
leak one script's pinned clock into the next. This also runs them exactly the way
the docs tell a human to.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SCRIPTS = ("regen_golden.py", "gen_examples.py", "build_plugin.py")


def main() -> int:
    for name in SCRIPTS:
        print(f"--- {name}", flush=True)  # unbuffered, or it lands after the child's output
        code = subprocess.run([sys.executable, str(TOOLS / name)]).returncode
        if code != 0:
            print(f"error: {name} failed with exit code {code}", file=sys.stderr)
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

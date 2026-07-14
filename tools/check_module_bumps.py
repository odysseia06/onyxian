#!/usr/bin/env python
"""Fail when a module's content changed since the last release but its version didn't.

The product's update contract is version-driven: `resolve_modules` treats a
config-pin/library-version mismatch as "an update is available", and `cmd_update`
only reaches existing vaults when the library version moved. A content edit that
forgets to bump `module.yaml` slips outside that contract — the bytes change but
the tripwire never fires (see issue #6). This guard enforces the rule that CI and
CONTRIBUTING.md now name: any change under `modules/<id>/` requires a version bump
in that module's `module.yaml`.

Stdlib-only (subprocess + re + pathlib) so it needs no install step and runs the
same on Windows. Takes an optional repo-root argument (default: cwd) so tests can
point it at a throwaway repo.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

VERSION_RE = re.compile(r"^version:\s*(\d+\.\d+\.\d+)\s*$", re.MULTILINE)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True
    )


def parse_version(text: str) -> str | None:
    m = VERSION_RE.search(text)
    return m.group(1) if m else None


def next_patch(version: str) -> str:
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def print_changed_files(files: list[str]) -> None:
    print("  changed files:")
    for f in files:
        print(f"    {f}")


def main(argv: list[str]) -> int:
    repo = Path(argv[0]) if argv else Path.cwd()

    described = git(repo, "describe", "--tags", "--match", "v*", "--abbrev=0", "HEAD")
    baseline = described.stdout.strip()
    if described.returncode != 0 or not baseline:
        print("no release tag reachable; nothing to guard against.")
        return 0

    changed = [p for p in git(repo, "diff", "--name-only", baseline, "--", "modules/").stdout.splitlines() if p]
    by_module: dict[str, list[str]] = {}
    for path in changed:
        by_module.setdefault(path.split("/")[1], []).append(path)

    considered = 0
    unbumped: list[tuple[str, str, list[str]]] = []
    backwards: list[tuple[str, str, str, list[str]]] = []
    for mod, files in sorted(by_module.items()):
        worktree_manifest = repo / "modules" / mod / "module.yaml"
        if not worktree_manifest.exists():
            continue  # removed from the worktree — deletion is a separate contract (out of scope)
        tag_result = git(repo, "show", f"{baseline}:modules/{mod}/module.yaml")
        tag_version = parse_version(tag_result.stdout) if tag_result.returncode == 0 else None
        considered += 1
        if tag_version is None:
            continue  # new module (absent at the tag) — nothing to compare against
        worktree_version = parse_version(worktree_manifest.read_text(encoding="utf-8"))
        if worktree_version == tag_version:
            unbumped.append((mod, worktree_version, sorted(files)))
        elif version_tuple(worktree_version) < version_tuple(tag_version):
            backwards.append((mod, tag_version, worktree_version, sorted(files)))
        # strictly greater → a real bump → pass

    if unbumped or backwards:
        for mod, version, files in unbumped:
            print(f"FAIL: module '{mod}' changed since {baseline} but module.yaml still says {version}")
            print_changed_files(files)
            print(f"  fix: bump the version in modules/{mod}/module.yaml (e.g. {version} -> {next_patch(version)})")
        for mod, tag_version, worktree_version, files in backwards:
            print(f"FAIL: module '{mod}' version went backwards since {baseline}: {tag_version} -> {worktree_version}")
            print_changed_files(files)
            print(f"  fix: set the version in modules/{mod}/module.yaml above {tag_version} (e.g. {next_patch(tag_version)})")
        return 1

    if considered == 0:
        print(f"ok: no module content changes since {baseline}.")
    else:
        print(f"ok: {considered} module(s) changed since {baseline}, all with version bumps.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

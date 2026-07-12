"""Scenario definitions for the mutation-lifecycle goldens (issue #3).

One definition, two consumers: tools/regen_golden.py snapshots each scenario's
tree after ``build`` into before/ and after ``mutate`` into after/ under
tests/fixtures/golden/lifecycle/, and tests/test_golden_lifecycle.py replays
the same steps in a temp dir and compares. Keeping the steps here means the
regen tool and the test cannot drift apart.

Scenarios drive the real CLI in-process against the committed synthetic
libraries under tests/fixtures/lifecycle/ (selected per phase via
ONYXIAN_HOME), never the real modules/ library — so these goldens do not churn
when a real module ships a content change.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[1]
LIFECYCLE_FIXTURES = REPO / "tests" / "fixtures" / "lifecycle"
ANSWERS = LIFECYCLE_FIXTURES / "answers" / "lifecycle.yaml"

_TOKEN_RE = re.compile(r"--accept ([0-9a-f]{12})")


class Runner:
    """Drives the real CLI in-process against one vault; scripted user edits write LF bytes."""

    def __init__(self, vault: Path) -> None:
        self.vault = vault

    def cli(self, *argv: object) -> tuple[int, str]:
        from onyxian.cli import main

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = main([str(a) for a in argv])
        return code, buffer.getvalue()

    def check(self, *argv: object) -> str:
        code, out = self.cli(*argv)
        if code != 0:
            pretty = " ".join(str(a) for a in argv)
            raise RuntimeError(f"`onyxian {pretty}` exited {code}:\n{out}")
        return out

    def write(self, rel: str, text: str) -> None:
        target = self.vault.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")

    def delete(self, rel: str) -> None:
        self.vault.joinpath(*rel.split("/")).unlink()

    def adopt_accept(self, *argv: object) -> None:
        """The documented non-interactive adopt flow: --dry-run prints the token, --accept applies it."""
        review = self.check("adopt", self.vault, *argv, "--dry-run")
        match = _TOKEN_RE.search(review)
        if match is None:
            raise RuntimeError(f"no acceptance token in adopt output:\n{review}")
        self.check("adopt", self.vault, *argv, "--accept", match.group(1))


@dataclass(frozen=True)
class Scenario:
    name: str
    library_before: str  # dir under tests/fixtures/lifecycle/: ONYXIAN_HOME during build
    library_after: str | None  # ONYXIAN_HOME switch before mutate, if any
    build: Callable[[Runner], None]
    mutate: Callable[[Runner], None]


def _build_adopt_lived_in(r: Runner) -> None:
    """A plain, lived-in vault: user files at seed paths, a customized template
    at a managed path (report-only BLOCKED), and a user note where demo wants
    its folder. No engine involvement; the before tree is all the user's."""
    r.write("Home.md", "My own home page, written long before Onyxian.\n")
    r.write("Templates/Note.md", "My customized note template; the engine must never touch it.\n")
    r.write("Demo-Area/reading-notes.md", "A user note already living in the folder demo provides.\n")
    r.write("Start.md", "My own start page, sitting exactly at demo's seed path.\n")


def _mutate_adopt_lived_in(r: Runner) -> None:
    r.adopt_accept("--answers", ANSWERS)


def _build_update_conflict(r: Runner) -> None:
    r.check("init", r.vault, "--answers", ANSWERS, "--yes")
    r.write("Templates/Demo/Guide.md", "Guide, customized by the user; updates must land beside it.\n")
    r.delete("Templates/Note.md")


def _mutate_update_conflict(r: Runner) -> None:
    r.check("update", "--vault", r.vault, "--yes")


def _build_remove_user_files(r: Runner) -> None:
    r.check("init", r.vault, "--answers", ANSWERS, "--yes")
    r.write("Templates/Demo/Guide.md", "Guide, customized by the user; remove must leave it alone.\n")
    r.write("Demo-Area/keep-me.md", "A user note that keeps the module folder alive.\n")


def _mutate_remove_user_files(r: Runner) -> None:
    r.check("remove", "demo", "--vault", r.vault, "--yes")


SCENARIOS: list[Scenario] = [
    Scenario(
        name="adopt-lived-in",
        library_before="library-v1",
        library_after=None,
        build=_build_adopt_lived_in,
        mutate=_mutate_adopt_lived_in,
    ),
    Scenario(
        name="update-conflict-new",
        library_before="library-v1",
        library_after="library-v2",
        build=_build_update_conflict,
        mutate=_mutate_update_conflict,
    ),
    Scenario(
        name="remove-user-files-stay",
        library_before="library-v1",
        library_after=None,
        build=_build_remove_user_files,
        mutate=_mutate_remove_user_files,
    ),
]


def run_scenario(
    scenario: Scenario,
    vault: Path,
    *,
    setenv: Callable[[str, str], None] | None = None,
    after_build: Callable[[Runner], None] | None = None,
) -> Runner:
    """Run both phases against ``vault``. ``setenv`` lets pytest pass
    monkeypatch.setenv so the ONYXIAN_HOME switches do not leak; the regen tool
    uses plain os.environ. ``after_build`` is the before-tree hook (snapshot or
    compare) between the phases."""
    if setenv is None:
        setenv = os.environ.__setitem__
    setenv("ONYXIAN_HOME", str(LIFECYCLE_FIXTURES / scenario.library_before))
    runner = Runner(vault)
    scenario.build(runner)
    if after_build is not None:
        after_build(runner)
    if scenario.library_after is not None:
        setenv("ONYXIAN_HOME", str(LIFECYCLE_FIXTURES / scenario.library_after))
    scenario.mutate(runner)
    return runner

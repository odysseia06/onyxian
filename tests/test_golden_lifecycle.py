"""Golden lifecycle tests (KICKSTART.md §11, issue #3): the mutation paths —
adopt, update with *.new delivery, remove — replayed byte-exact against
committed before/after trees.

The trees under tests/fixtures/golden/lifecycle/ are generated only by
tools/regen_golden.py from the scenarios in tools/lifecycle_scenarios.py (the
single definition both this test and the regen tool consume). If a test here
fails after an intended engine or fixture-library change, regenerate and
review the diff — never hand-edit a golden tree.
"""

import json
import sys

import pytest

from conftest import GOLDEN_DIR, REPO_ROOT, tree_hashes
from onyxian.fsio import sha256_file

sys.path.insert(0, str(REPO_ROOT / "tools"))

from lifecycle_scenarios import LIFECYCLE_FIXTURES, SCENARIOS, run_scenario

LIFECYCLE_GOLDEN = GOLDEN_DIR / "lifecycle"
REGEN_HINT = "run `python tools/regen_golden.py` and review the fixture diff"


def golden_trees(name: str) -> tuple[dict[str, str], dict[str, str]]:
    golden = LIFECYCLE_GOLDEN / name
    assert (golden / "before").is_dir() and (golden / "after").is_dir(), (
        f"lifecycle golden missing at {golden}; {REGEN_HINT}"
    )
    return tree_hashes(golden / "before"), tree_hashes(golden / "after")


def golden_lock_entries(name: str) -> dict[str, dict]:
    lock = json.loads(
        (LIFECYCLE_GOLDEN / name / "after" / ".vault" / "lock.json").read_text(encoding="utf-8")
    )
    return {entry["path"]: entry for entry in lock["entries"]}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_scenario_replay_matches_golden_trees(scenario, tmp_path, monkeypatch):
    """Replay build + mutate in a temp dir; both phases must match the committed trees."""
    before_golden, after_golden = golden_trees(scenario.name)
    vault = tmp_path / "vault"

    def check_before(runner):
        assert tree_hashes(vault) == before_golden, (
            f"replayed 'before' tree diverges from the {scenario.name} golden; "
            f"if the change is intended, {REGEN_HINT}"
        )

    run_scenario(scenario, vault, setenv=monkeypatch.setenv, after_build=check_before)
    assert tree_hashes(vault) == after_golden, (
        f"replayed 'after' tree diverges from the {scenario.name} golden; "
        f"if the change is intended, {REGEN_HINT}"
    )


def test_adopt_after_tree_preserves_every_before_byte():
    """The adopt guarantee, encoded in fixtures: additive only, nothing pre-existing touched."""
    before, after = golden_trees("adopt-lived-in")
    assert before, "the adopt 'before' tree must not be empty"
    clobbered = {p for p, digest in before.items() if after.get(p) != digest}
    assert not clobbered, f"adopt changed or removed pre-existing files: {sorted(clobbered)}"
    assert set(after) - set(before), "adopt gap-fill added nothing; the scenario lost its point"
    # The user's files at seed paths are claimed as seeds; the customized
    # template at a managed path stays blocked and out of the ledger.
    entries = golden_lock_entries("adopt-lived-in")
    assert entries["Home.md"]["kind"] == "seeded"
    assert entries["Start.md"]["kind"] == "seeded"
    assert "Templates/Note.md" not in entries


def test_update_after_tree_delivers_new_sibling_without_touching_original():
    """The §8.3 conflict row, encoded in fixtures: *.new beside the file, zero overwrites."""
    before, after = golden_trees("update-conflict-new")
    assert after["Templates/Demo/Guide.md"] == before["Templates/Demo/Guide.md"]
    v2_guide = sha256_file(
        LIFECYCLE_FIXTURES
        / "library-v2"
        / "modules"
        / "demo"
        / "assets"
        / "Templates"
        / "Demo"
        / "Guide.md"
    )
    assert after.get("Templates/Demo/Guide.md.new") == v2_guide
    assert (
        golden_lock_entries("update-conflict-new")["Templates/Demo/Guide.md.new"]["sha256"]
        == v2_guide
    )
    # Seeds are never redelivered; dropped assets are stale (report-only), left at v1 bytes.
    assert after["Start.md"] == before["Start.md"]
    v1_old_asset = sha256_file(
        LIFECYCLE_FIXTURES
        / "library-v1"
        / "modules"
        / "demo"
        / "assets"
        / "Templates"
        / "Demo"
        / "Old-Asset.md"
    )
    assert after.get("Templates/Demo/Old-Asset.md") == v1_old_asset
    # The managed template the user deleted comes back; the version pin advances.
    assert "Templates/Note.md" not in before and "Templates/Note.md" in after
    config_text = (
        LIFECYCLE_GOLDEN / "update-conflict-new" / "after" / ".vault" / "config.yaml"
    ).read_text(encoding="utf-8")
    assert 'demo: { version: "0.2.0" }' in config_text


def test_remove_after_tree_keeps_user_files_and_seeds():
    """The §8.3 remove contract, encoded in fixtures: only unmodified managed files go."""
    before, after = golden_trees("remove-user-files-stay")
    assert (
        after["Templates/Demo/Guide.md"] == before["Templates/Demo/Guide.md"]
    )  # user-modified: stays
    assert "Demo-Area/keep-me.md" in after  # user file keeps its folder alive
    assert "Templates/Demo/Old-Asset.md" not in after  # unmodified managed file: deleted
    assert after["Start.md"] == before["Start.md"]  # seeded: never touched
    entries = golden_lock_entries("remove-user-files-stay")
    assert all(entry["module"] != "demo" for entry in entries.values())
    config_text = (
        LIFECYCLE_GOLDEN / "remove-user-files-stay" / "after" / ".vault" / "config.yaml"
    ).read_text(encoding="utf-8")
    assert "demo" not in config_text
    # The module set changed, so core's generated summary was refreshed.
    assert after["Start-Here.md"] != before["Start-Here.md"]

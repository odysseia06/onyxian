"""examples/ as integration test (KICKSTART.md D6, §11): profile in, byte-exact vault out."""

import pytest
from conftest import REPO_ROOT, run_cli, tree_hashes

PROFILES = sorted((REPO_ROOT / "profiles").glob("*.yaml"), key=lambda p: p.stem)


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.stem)
def test_example_vault_matches_its_profile(profile, tmp_path):
    example = REPO_ROOT / "examples" / profile.stem
    assert example.is_dir(), (
        f"example missing for {profile.stem}; run `python tools/gen_examples.py`"
    )
    vault = tmp_path / profile.stem
    assert run_cli("init", str(vault), "--answers", str(profile), "--yes") == 0
    assert tree_hashes(vault) == tree_hashes(example), (
        f"examples/{profile.stem} drifted from what the engine generates; if the change is "
        "intended, run `python tools/gen_examples.py` and review the diff"
    )


def test_demo_vault_is_researcher_developer_plus_overlay(tmp_path):
    """examples/demo = fresh researcher-developer init + tools/demo_content, byte-exact and doctor-clean."""
    demo = REPO_ROOT / "examples" / "demo"
    assert demo.is_dir(), "demo vault missing; run `python tools/gen_examples.py`"
    vault = tmp_path / "demo"
    profile = REPO_ROOT / "profiles" / "researcher-developer.yaml"
    assert run_cli("init", str(vault), "--answers", str(profile), "--yes") == 0
    overlay = REPO_ROOT / "tools" / "demo_content"
    for src in sorted(overlay.rglob("*")):
        if src.is_file():
            dst = vault / src.relative_to(overlay)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
    assert tree_hashes(vault) == tree_hashes(demo), (
        "examples/demo drifted from researcher-developer + tools/demo_content; if the change is "
        "intended, run `python tools/gen_examples.py` and review the diff"
    )
    # doctor runs on the freshly built copy: a git checkout of examples/demo lacks
    # the engine-created EMPTY folders (git cannot store them), so doctor on the
    # checkout reports pending dir-creates. The tree_hashes assertion above already
    # proves the checkout's files are byte-identical to this copy's.
    assert run_cli("doctor", "--vault", str(vault)) == 0

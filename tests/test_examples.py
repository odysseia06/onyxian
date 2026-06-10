"""examples/ as integration test (KICKSTART.md D6, §11): profile in, byte-exact vault out."""

import pytest

from conftest import REPO_ROOT, run_cli, tree_hashes

PROFILES = sorted((REPO_ROOT / "profiles").glob("*.yaml"), key=lambda p: p.stem)


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.stem)
def test_example_vault_matches_its_profile(profile, tmp_path):
    example = REPO_ROOT / "examples" / profile.stem
    assert example.is_dir(), f"example missing for {profile.stem}; run `python tools/gen_examples.py`"
    vault = tmp_path / profile.stem
    assert run_cli("init", str(vault), "--answers", str(profile), "--yes") == 0
    assert tree_hashes(vault) == tree_hashes(example), (
        f"examples/{profile.stem} drifted from what the engine generates; if the change is "
        "intended, run `python tools/gen_examples.py` and review the diff"
    )

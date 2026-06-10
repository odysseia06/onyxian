"""Golden-file test (KICKSTART.md §11): answers in, byte-exact vault tree out.

The fixture under tests/fixtures/golden/minimal is generated only by
tools/regen_golden.py and reviewed as a diff in PRs; if this test fails after
an intended asset change, regenerate — never hand-edit.
"""

from conftest import GOLDEN_DIR, init_minimal_vault, tree_hashes


def test_minimal_vault_matches_golden_tree(tmp_path):
    golden = GOLDEN_DIR / "minimal"
    assert golden.is_dir(), (
        f"golden fixture missing at {golden}; run `python tools/regen_golden.py`"
    )
    vault = init_minimal_vault(tmp_path)
    generated = tree_hashes(vault)
    expected = tree_hashes(golden)
    assert generated == expected, (
        "generated vault diverges from the golden tree; if the change is intended, "
        "run `python tools/regen_golden.py` and review the fixture diff"
    )
    # Belt and braces: hashes match implies bytes match, but check one file raw.
    assert (vault / "Home.md").read_bytes() == (golden / "Home.md").read_bytes()

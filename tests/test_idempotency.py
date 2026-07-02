"""P3, the exit criterion of M0: re-running against an unchanged vault is a byte-identical no-op."""

from conftest import init_minimal_vault, run_cli, tree_hashes
from onyxian.configio import load_config
from onyxian.lockio import load_lock
from onyxian.repo import default_modules_root, discover_modules
from onyxian.intent import build_desired_state
from onyxian.planner import build_plan
from onyxian.resolve import resolve_modules


def empty_plan_for(vault):
    config = load_config(vault)
    library = discover_modules(default_modules_root())
    manifests = resolve_modules(config, library)
    desired = build_desired_state(config, manifests)
    return build_plan(vault, desired, load_lock(vault), set(config.modules))


def test_apply_twice_is_a_byte_identical_noop(tmp_path):
    vault = init_minimal_vault(tmp_path)
    before = tree_hashes(vault)
    assert before  # the vault is not empty

    plan = empty_plan_for(vault)
    assert plan.is_empty and not plan.reports

    assert run_cli("apply", "--vault", str(vault), "--yes") == 0
    assert tree_hashes(vault) == before

    assert run_cli("apply", "--vault", str(vault), "--yes") == 0
    assert tree_hashes(vault) == before


def test_plan_and_doctor_are_read_only(tmp_path):
    vault = init_minimal_vault(tmp_path)
    before = tree_hashes(vault)
    assert run_cli("plan", "--vault", str(vault)) == 0
    assert run_cli("doctor", "--vault", str(vault)) == 0
    assert tree_hashes(vault) == before


def test_hand_editing_config_is_a_supported_door(tmp_path):
    """§4.4: hand-editing config and running plan is equivalent to the wizard."""
    vault = init_minimal_vault(tmp_path)
    config_path = vault / ".vault" / "config.yaml"
    text = config_path.read_text(encoding="utf-8").replace('"Golden Minimal"', '"Renamed By Hand"')
    config_path.write_text(text, encoding="utf-8")
    # vault_name feeds only seeded content, which is written once; nothing to reconcile.
    plan = empty_plan_for(vault)
    assert plan.is_empty
    assert run_cli("doctor", "--vault", str(vault)) == 0

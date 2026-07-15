"""`onyxian diff` (issue #4): inspect and resolve *.new conflict siblings.

Read paths: pair listing (exit 1 when anything is listed, 0 when clean) and
deterministic stdlib unified diffs of the original on disk against the
rendered desired bytes. Write paths: --take-new / --keep-mine / --resolve,
every one re-verified against the live disk, never forced.
"""

from types import SimpleNamespace

import pytest
from conftest import run_cli, tree_hashes, write_module

from onyxian.lockio import load_lock

V1 = "# guide v1\n"
V2 = "# guide v2 (improved)\n"
MINE = "MY customized guide\n"
GUIDE = "Templates/Demo/Guide.md"
SEED = "seed v1\n"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A vault at demo 0.1.0, one managed template and one seed, ready for v2."""
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(
        modules_root,
        "demo",
        version="0.1.0",
        folders=["Demo-Area"],
        templates={GUIDE: V1},
        seeds={"Start.md": SEED},
    )
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    answers = tmp_path / "a.yaml"
    answers.write_text("modules: {demo: {}}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(answers), "--yes") == 0
    return SimpleNamespace(
        vault=vault,
        modules_root=modules_root,
        guide=vault / "Templates" / "Demo" / "Guide.md",
    )


def release_v2(home):
    write_module(
        home.modules_root,
        "demo",
        version="0.2.0",
        folders=["Demo-Area"],
        templates={GUIDE: V2},
        seeds={"Start.md": SEED},
    )


def align_pin(home):
    """Advance the config pin to the shipped 0.2.0 by hand (the documented
    alternative to `onyxian update`), leaving delivery to a future apply."""
    from onyxian.config_edit import bump_module_versions

    cfg = home.vault / ".vault" / "config.yaml"
    text, _ = bump_module_versions(cfg.read_text(encoding="utf-8"), {"demo": ("0.1.0", "0.2.0")})
    cfg.write_text(text, encoding="utf-8")


def make_pending(home):
    """Customized original + shipped v2 + pin advanced, before any apply:
    the conflict exists but the sibling has not been delivered yet."""
    home.guide.write_text(MINE, encoding="utf-8")
    release_v2(home)
    align_pin(home)


def make_delivered(home, capsys):
    make_pending(home)
    assert run_cli("update", "--vault", str(home.vault), "--yes") == 0
    capsys.readouterr()


def make_leftover(home, capsys):
    """The permanent-doctor-WARN state: original resolved, sibling row orphaned."""
    make_delivered(home, capsys)
    home.guide.write_text(V2, encoding="utf-8", newline="\n")  # user accepts the content
    assert (
        run_cli("apply", "--vault", str(home.vault), "--yes") == 0
    )  # original relocks; row for the sibling stays
    home.guide.with_name("Guide.md.new").unlink()  # file deleted only afterwards
    capsys.readouterr()


def diff_cli(home, capsys, *argv):
    code = run_cli("diff", *argv, "--vault", str(home.vault))
    out = capsys.readouterr()
    return code, out.out + out.err


# ----------------------------------------------------------------- listing


def test_clean_vault_lists_nothing_and_exits_zero(home, capsys):
    code, out = diff_cli(home, capsys)
    assert code == 0
    assert "no conflict pairs" in out


def test_pending_pair_is_listed_with_exit_one(home, capsys):
    make_pending(home)
    code, out = diff_cli(home, capsys)
    assert code == 1
    assert "1 conflict pair(s):" in out
    assert f"! {GUIDE} -> {GUIDE}.new  (demo 0.2.0)" in out
    assert "[pending; run `onyxian apply` to deliver]" in out


def test_delivered_pair_is_listed_as_delivered(home, capsys):
    make_delivered(home, capsys)
    code, out = diff_cli(home, capsys)
    assert code == 1
    assert "[delivered]" in out


def test_resolved_leftover_is_listed(home, capsys):
    make_leftover(home, capsys)
    code, out = diff_cli(home, capsys)
    assert code == 1
    assert "1 resolved leftover(s):" in out
    assert f"* {GUIDE}.new  [original already resolved; ledger row remains]" in out
    assert "conflict pair" not in out.split("resolved leftover")[0] or "0 conflict" not in out


def test_listing_and_single_diff_perform_no_writes(home, capsys):
    make_delivered(home, capsys)
    before = tree_hashes(home.vault)
    assert diff_cli(home, capsys)[0] == 1
    assert diff_cli(home, capsys, GUIDE)[0] == 1
    assert tree_hashes(home.vault) == before


# ----------------------------------------------------------------- rendering


def test_single_path_renders_deterministic_unified_diff(home, capsys):
    make_delivered(home, capsys)
    code, out = diff_cli(home, capsys, GUIDE)
    assert code == 1
    assert f"--- {GUIDE}  (yours)" in out
    assert f"+++ {GUIDE}.new  (shipped by demo 0.2.0)" in out
    assert "-MY customized guide" in out
    assert "+# guide v2 (improved)" in out
    _code2, out2 = diff_cli(home, capsys, GUIDE)
    assert out2 == out  # no timestamps, byte-identical across runs


def test_path_argument_accepts_new_suffix_and_backslashes(home, capsys):
    make_delivered(home, capsys)
    _, via_original = diff_cli(home, capsys, GUIDE)
    _, via_new = diff_cli(home, capsys, GUIDE + ".new")
    _, via_backslash = diff_cli(home, capsys, "Templates\\Demo\\Guide.md.new")
    assert via_new == via_original
    assert via_backslash == via_original


def test_unconflicted_path_reports_and_exits_zero(home, capsys):
    code, out = diff_cli(home, capsys, "Start.md")
    assert code == 0
    assert "no active conflict for Start.md" in out


def test_line_ending_only_difference_is_one_summary_line(home, capsys):
    home.guide.write_bytes(V2.replace("\n", "\r\n").encode("utf-8"))  # CRLF flavor of v2
    release_v2(home)
    align_pin(home)
    code, out = diff_cli(home, capsys, GUIDE)
    assert code == 1
    assert "only in line endings" in out
    assert "---" not in out and "+++" not in out  # no full-file diff


def test_non_utf8_content_yields_notice_not_a_crash(home, capsys):
    make_pending(home)
    home.guide.write_bytes(b"\xff\xfe\x00 not text")
    code, out = diff_cli(home, capsys, GUIDE)
    assert code == 1
    assert "binary or non-UTF-8" in out
    assert "Traceback" not in out


# ----------------------------------------------------------------- take-new


def test_take_new_updates_original_and_retires_sibling(home, capsys):
    make_delivered(home, capsys)
    code, _out = diff_cli(home, capsys, GUIDE, "--take-new", "--yes")
    assert code == 0
    assert home.guide.read_text(encoding="utf-8") == V2
    assert not home.guide.with_name("Guide.md.new").exists()
    lock = load_lock(home.vault)
    guide_entry = lock.get(GUIDE)
    assert guide_entry is not None
    assert guide_entry.module_version == "0.2.0"
    assert lock.get(GUIDE + ".new") is None
    # The vault is fully converged: nothing pending, nothing orphaned.
    assert run_cli("plan", "--vault", str(home.vault)) == 0
    assert "no changes planned" in capsys.readouterr().out


def test_take_new_without_yes_errors_on_non_interactive_stdin(home, capsys):
    make_delivered(home, capsys)
    before = tree_hashes(home.vault)
    code, out = diff_cli(home, capsys, GUIDE, "--take-new")
    assert code == 1
    assert "not interactive" in out and "--yes" in out
    assert tree_hashes(home.vault) == before


def test_take_new_never_deletes_a_user_edited_sibling(home, capsys):
    make_delivered(home, capsys)
    sibling = home.guide.with_name("Guide.md.new")
    sibling.write_text("I scribbled my merge notes in here\n", encoding="utf-8")
    code, out = diff_cli(home, capsys, GUIDE, "--take-new", "--yes")
    assert code == 0
    assert home.guide.read_text(encoding="utf-8") == V2  # the resolution itself happened
    assert sibling.read_text(encoding="utf-8") == "I scribbled my merge notes in here\n"
    assert "left on disk" in out
    assert load_lock(home.vault).get(GUIDE + ".new") is None  # row retired either way


def test_resolving_an_unconflicted_path_is_a_reported_failure(home, capsys):
    code, out = diff_cli(home, capsys, "Start.md", "--take-new", "--yes")
    assert code == 1
    assert "no active conflict" in out


def discover(home):
    """(desired, lock, pairs, leftovers) — the diff command's own discovery, for
    helper-level tests."""
    from onyxian.configio import load_config
    from onyxian.diff import find_conflicts
    from onyxian.intent import build_desired_state
    from onyxian.repo import default_modules_root, discover_modules
    from onyxian.resolve import resolve_modules

    config = load_config(home.vault)
    library = discover_modules(default_modules_root(), home.vault)
    desired = build_desired_state(config, resolve_modules(config, library))
    lock = load_lock(home.vault)
    pairs, leftovers = find_conflicts(home.vault, desired, lock)
    return desired, lock, pairs, leftovers


def test_take_new_skips_when_the_world_moved(home, capsys):
    """The applier-style re-verify: the pair dissolves between discovery and write."""
    from onyxian.diff import take_new

    make_delivered(home, capsys)
    desired, lock, pairs, _ = discover(home)
    home.guide.write_text(V2, encoding="utf-8", newline="\n")  # user resolves by hand meanwhile
    before = tree_hashes(home.vault)
    ok, reason = take_new(home.vault, pairs[0], lock, {f.path for f in desired.files})
    assert not ok and "run `onyxian diff` again" in reason
    assert tree_hashes(home.vault) == before


def test_take_new_requires_exactly_the_displayed_bytes(home, capsys):
    """P1 regression: an edit made after the diff was shown — still broadly
    conflicted — must not be silently overwritten. Preconditions are the exact
    bytes the user reviewed, applier-style."""
    from onyxian.diff import take_new

    make_delivered(home, capsys)
    desired, lock, pairs, _ = discover(home)
    home.guide.write_text("second thoughts, rewritten again\n", encoding="utf-8")
    ok, reason = take_new(home.vault, pairs[0], lock, {f.path for f in desired.files})
    assert not ok and "run `onyxian diff` again" in reason
    assert home.guide.read_text(encoding="utf-8") == "second thoughts, rewritten again\n"


def test_resolution_never_touches_an_unrelated_seeded_sibling_row(home, capsys):
    """P1 regression: a seeded ledger row that happens to sit at <path>.new is
    the user's file, not this conflict's delivery artifact — never deleted,
    never popped."""
    from onyxian.fsio import sha256_file
    from onyxian.lockio import save_lock
    from onyxian.model import LockEntry

    make_delivered(home, capsys)
    sibling = home.guide.with_name("Guide.md.new")
    sibling.write_text("an unrelated seed the user owns\n", encoding="utf-8")
    lock = load_lock(home.vault)
    lock.put(
        LockEntry(
            path=GUIDE + ".new",
            sha256=sha256_file(sibling),
            module="demo",
            module_version="0.1.0",
            kind="seeded",
        )
    )
    save_lock(home.vault, lock)

    code, _ = diff_cli(home, capsys, GUIDE, "--keep-mine", "--yes")
    assert code == 0  # the decline itself succeeds
    assert sibling.read_text(encoding="utf-8") == "an unrelated seed the user owns\n"
    row = load_lock(home.vault).get(GUIDE + ".new")
    assert row is not None
    assert row.kind == "seeded"  # row untouched


def test_source_installed_new_suffixed_file_is_not_litter(home, capsys, monkeypatch):
    """P1 regression: a legitimately installed file whose name merely ends in
    .new (e.g. source-installed) must not be classified as a resolved leftover
    — and must survive an interactive cleanup run."""
    from onyxian.fsio import sha256_file
    from onyxian.lockio import save_lock
    from onyxian.model import LockEntry

    handy = home.vault / "skills" / "handy.new"
    handy.parent.mkdir()
    handy.write_text("source-installed content\n", encoding="utf-8")
    lock = load_lock(home.vault)
    lock.put(
        LockEntry(
            path="skills/handy.new",
            sha256=sha256_file(handy),
            module="source:obsidian-skills",
            module_version="abc123",
            kind="managed",
        )
    )
    save_lock(home.vault, lock)

    code, out = diff_cli(home, capsys)
    assert code == 0 and "no conflict pairs" in out  # not listed at all
    monkeypatch.setattr("onyxian.cli._is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    diff_cli(home, capsys, "--resolve")
    assert handy.read_text(encoding="utf-8") == "source-installed content\n"
    assert load_lock(home.vault).get("skills/handy.new") is not None


def test_trailing_newline_only_difference_is_reported_not_empty(home, capsys):
    """P2 regression: b"same" vs b"same\\n" must render a notice, not an empty diff."""
    home.guide.write_bytes(V2.rstrip("\n").encode("utf-8"))
    release_v2(home)
    align_pin(home)
    code, out = diff_cli(home, capsys, GUIDE)
    assert code == 1
    assert "trailing newline" in out
    assert out.strip()  # never a blank screen


def test_directory_at_managed_path_is_a_conflict_like_the_planner_says(home, capsys):
    """P2 regression: the planner treats a directory at a managed path as
    'present but different' and plans the sibling; diff must agree, render a
    notice, and refuse take-new."""
    make_delivered(home, capsys)
    home.guide.unlink()
    home.guide.mkdir()
    code, out = diff_cli(home, capsys)
    assert code == 1 and GUIDE in out  # listed, like the planner plans it
    code, out = diff_cli(home, capsys, GUIDE)
    assert code == 1 and "directory" in out and "Traceback" not in out
    code, out = diff_cli(home, capsys, GUIDE, "--take-new", "--yes")
    assert code == 1
    assert home.guide.is_dir()  # never replaced


def test_managed_original_literally_named_dot_new_is_selectable(tmp_path, monkeypatch, capsys):
    """P2 regression: a managed file whose own name ends in .new must be
    addressable by its original path — exact match wins over suffix-stripping."""
    snip = "Templates/Demo/Snippet.new"
    modules_root = tmp_path / "modules"
    write_module(modules_root, "core")
    write_module(modules_root, "demo", version="0.1.0", templates={snip: "snip v1\n"})
    monkeypatch.setenv("ONYXIAN_HOME", str(tmp_path))
    answers = tmp_path / "a.yaml"
    answers.write_text("modules: {demo: {}}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    assert run_cli("init", str(vault), "--answers", str(answers), "--yes") == 0
    (vault / "Templates" / "Demo" / "Snippet.new").write_text("customized snip\n", encoding="utf-8")
    write_module(modules_root, "demo", version="0.2.0", templates={snip: "snip v2\n"})
    assert run_cli("update", "--vault", str(vault), "--yes") == 0
    capsys.readouterr()

    code = run_cli("diff", snip, "--vault", str(vault))
    out = capsys.readouterr().out
    assert code == 1
    assert f"--- {snip}  (yours)" in out
    assert "+snip v2" in out


def test_take_new_dry_run_writes_nothing(home, capsys):
    """KICKSTART P8: every mutating command supports --dry-run."""
    make_delivered(home, capsys)
    before = tree_hashes(home.vault)
    code, out = diff_cli(home, capsys, GUIDE, "--take-new", "--dry-run")
    assert code == 0
    assert "dry run; nothing written." in out
    assert tree_hashes(home.vault) == before


def test_resolve_dry_run_previews_without_prompts_or_writes(home, capsys):
    make_delivered(home, capsys)
    before = tree_hashes(home.vault)
    code, out = diff_cli(home, capsys, "--resolve", "--dry-run")  # non-interactive stdin: fine
    assert code == 0
    assert f"--- {GUIDE}  (yours)" in out
    assert "dry run; nothing written." in out
    assert tree_hashes(home.vault) == before


# ----------------------------------------------------------------- keep-mine


def test_keep_mine_declines_and_stops_redelivery(home, capsys):
    make_delivered(home, capsys)
    code, out = diff_cli(home, capsys, GUIDE, "--keep-mine", "--yes")
    assert code == 0
    assert "kept yours" in out and "0.2.0" in out
    assert home.guide.read_text(encoding="utf-8") == MINE  # untouched
    assert not home.guide.with_name("Guide.md.new").exists()
    lock = load_lock(home.vault)
    guide_entry = lock.get(GUIDE)
    assert guide_entry is not None
    assert guide_entry.declined  # the shipped sha is recorded
    assert lock.get(GUIDE + ".new") is None
    # The inverse of the re-delivery honesty note: plan/apply/update stay quiet.
    assert run_cli("plan", "--vault", str(home.vault)) == 0
    plan_out = capsys.readouterr().out
    assert "no changes planned" in plan_out and "declined current version" in plan_out
    assert run_cli("update", "--vault", str(home.vault), "--yes") == 0
    assert "nothing to update." in capsys.readouterr().out
    assert not home.guide.with_name("Guide.md.new").exists()


def test_keep_mine_decline_expires_on_a_new_shipped_version(home, capsys):
    make_delivered(home, capsys)
    assert diff_cli(home, capsys, GUIDE, "--keep-mine", "--yes")[0] == 0
    write_module(
        home.modules_root,
        "demo",
        version="0.3.0",
        folders=["Demo-Area"],
        templates={GUIDE: "# guide v3 (rethought)\n"},
        seeds={"Start.md": SEED},
    )
    assert run_cli("update", "--vault", str(home.vault), "--yes") == 0
    out = capsys.readouterr().out
    assert "demo: 0.2.0 -> 0.3.0" in out
    assert home.guide.read_text(encoding="utf-8") == MINE  # still never clobbered
    assert (
        home.guide.with_name("Guide.md.new").read_text(encoding="utf-8")
        == "# guide v3 (rethought)\n"
    )


# ----------------------------------------------------------------- resolve + leftovers


def test_resolve_errors_on_non_interactive_stdin(home, capsys):
    make_delivered(home, capsys)
    code, out = diff_cli(home, capsys, "--resolve")
    assert code == 1
    assert "terminal" in out and "--take-new" in out


def test_interactive_resolve_keep_mine_and_leftover_cleanup(home, capsys, monkeypatch):
    make_delivered(home, capsys)
    monkeypatch.setattr("onyxian.cli._is_interactive", lambda: True)
    answers = iter(["k"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    code, out = diff_cli(home, capsys, "--resolve")
    assert code == 0
    assert "kept yours" in out
    entry = load_lock(home.vault).get(GUIDE)
    assert entry is not None
    assert entry.declined


def test_leftover_cleanup_retires_the_doctor_warn(home, capsys, monkeypatch):
    make_leftover(home, capsys)
    assert run_cli("doctor", "--vault", str(home.vault)) == 1  # missing managed file: WARN forever
    assert "missing from disk" in capsys.readouterr().out
    monkeypatch.setattr("onyxian.cli._is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    code, out = diff_cli(home, capsys, "--resolve")
    assert code == 0
    assert "retired the leftover ledger row" in out
    assert load_lock(home.vault).get(GUIDE + ".new") is None
    assert run_cli("doctor", "--vault", str(home.vault)) == 0


def test_conflicting_resolution_flags_are_rejected(home, capsys):
    make_delivered(home, capsys)
    code, out = diff_cli(home, capsys, GUIDE, "--take-new", "--keep-mine", "--yes")
    assert code == 1
    assert "mutually exclusive" in out
    code, out = diff_cli(home, capsys, "--take-new", "--yes")
    assert code == 1
    assert "path" in out

"""`onyxian modules lint` — the authoring conventions, mechanically (issue #75).

The bundled library and the `modules new` scaffold are held to the same bar third-party
authors get, which is the point of the command: nothing here is a repo-only rule.
"""

import json

import pytest
from conftest import REAL_MODULES, run_cli

from onyxian.doctor import FAIL, WARN
from onyxian.errors import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK
from onyxian.lint import frontmatter_block, hardwrap_lines, lint_module

BUNDLED = sorted(p for p in REAL_MODULES.iterdir() if (p / "module.yaml").is_file())


@pytest.mark.parametrize("module_dir", BUNDLED, ids=lambda p: p.name)
def test_every_bundled_module_lints_clean(module_dir):
    findings = lint_module(module_dir)
    offenders = [f.message for f in findings if f.level >= WARN]
    assert not offenders, f"{module_dir.name} violates the authoring conventions: {offenders}"


def test_the_scaffold_lints_clean_out_of_the_box(tmp_path):
    """`modules new` validates out of the box; it must also *lint* clean,
    or the first thing a new author sees is a scaffold that fails the repo's own check."""
    assert run_cli("modules", "new", "my-domain", "--dir", str(tmp_path)) == EXIT_OK
    assert run_cli("modules", "lint", str(tmp_path / "my-domain")) == EXIT_OK


def test_lint_reports_findings_with_exit_2_and_json(tmp_path, capsys):
    """The #66 convention: a violation is a *report* (exit 2), never an error (exit 1)."""
    module = tmp_path / "my-domain"
    assert run_cli("modules", "new", "my-domain", "--dir", str(tmp_path)) == EXIT_OK
    template = next((module / "assets").rglob("*.md"))
    template.write_text(
        "---\ntype: note\n---\n\nA sentence that someone\nhard-wrapped at a column.\n",
        encoding="utf-8",
    )
    capsys.readouterr()
    assert run_cli("modules", "lint", str(module), "--json") == EXIT_FINDINGS
    report = json.loads(capsys.readouterr().out)
    assert report["level"] == "warn" and report["exit_code"] == EXIT_FINDINGS
    messages = [f["message"] for f in report["findings"]]
    assert any("continues the line above" in m for m in messages), messages
    assert any("missing created, status, tags" in m for m in messages), messages


def test_lint_defaults_to_the_module_you_are_standing_in(tmp_path, monkeypatch):
    """`Path('.').name` is the empty string, which would fail the name-matches-directory
    check on the command's own default."""
    assert run_cli("modules", "new", "my-domain", "--dir", str(tmp_path)) == EXIT_OK
    monkeypatch.chdir(tmp_path / "my-domain")
    assert run_cli("modules", "lint") == EXIT_OK


def test_a_broken_manifest_is_a_finding_not_a_crash(tmp_path, capsys):
    """One malformed module must not stop a sweep, so lint reports it instead of raising."""
    (tmp_path / "module.yaml").write_text("name: nope\nversion: 1\n", encoding="utf-8")
    findings = lint_module(tmp_path)
    assert [f.level for f in findings] == [FAIL]
    assert "manifest does not validate" in findings[0].message


def test_a_directory_that_is_not_a_module_is_an_error(tmp_path):
    assert run_cli("modules", "lint", str(tmp_path)) == EXIT_ERROR


def test_undeclared_and_confused_placeholders_are_findings(tmp_path):
    module = tmp_path / "my-domain"
    assert run_cli("modules", "new", "my-domain", "--dir", str(tmp_path)) == EXIT_OK
    template = next((module / "assets").rglob("*.md"))
    template.write_text(
        "---\ntype: note\ncreated: x\nstatus: active\ntags: []\n---\n\n"
        "{{cadence}} and {{onyxian.yesterday}} and {{tp.date.now}} and <% root %>.\n",
        encoding="utf-8",
    )
    messages = [f.message for f in lint_module(module) if f.level >= WARN]
    assert any("{{cadence}} is not a variable this module declares" in m for m in messages)
    assert any("{{onyxian.yesterday}} is not an engine global" in m for m in messages)
    assert any("{{tp.date.now}} is a Templater macro in engine delimiters" in m for m in messages)
    assert any("<% root %> is an engine variable in Templater delimiters" in m for m in messages)


def test_an_unlisted_asset_is_a_finding(tmp_path):
    module = tmp_path / "my-domain"
    assert run_cli("modules", "new", "my-domain", "--dir", str(tmp_path)) == EXIT_OK
    (module / "assets" / "stray.md").write_text("Orphan.\n", encoding="utf-8")
    messages = [f.message for f in lint_module(module) if f.level >= FAIL]
    assert any("stray.md" in m for m in messages), messages


def _write_module(root, *, provides, seeds=(), assets=()):
    root.mkdir(parents=True, exist_ok=True)
    (root / "module.yaml").write_text(
        "name: my-domain\nversion: 0.1.0\nsummary: A module.\ndepends: [core]\n"
        f"provides:\n  templates: {list(provides)}\nseeds: {list(seeds)}\n",
        encoding="utf-8",
    )
    for rel in (*provides, *seeds, *assets):
        path = root / "assets" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\ntype: note\ncreated: x\nstatus: active\ntags: []\n---\n", "utf-8")
    return root


def test_paths_that_break_on_another_os_are_findings(tmp_path):
    """Both checks already guard the assembled plan; running them per module means an
    author hears about it before install, on whichever OS they happen to author from."""
    module = _write_module(
        tmp_path / "my-domain",
        provides=["Notes/A.md", "notes/B.md"],
        seeds=["Seed.md.new"],
    )
    messages = [f.message for f in lint_module(module) if f.level >= FAIL]
    assert any("differ only in case" in m for m in messages), messages
    assert any("reserved for conflict delivery" in m for m in messages), messages


def test_rename_paths_are_checked_for_authoring_mistakes(tmp_path):
    module = _write_module(tmp_path / "my-domain", provides=["New.md"])
    with (module / "module.yaml").open("a", encoding="utf-8") as manifest:
        manifest.write('renames:\n  "{{missing}}/Old.md": "New.md"\n  "Old.md.new": "New.md"\n')

    messages = [f.message for f in lint_module(module) if f.level >= FAIL]

    assert any(
        "{{missing}} is not a variable this module declares" in message for message in messages
    ), messages
    assert any(
        "Old.md.new" in message and "reserved for conflict delivery" in message
        for message in messages
    ), messages


def test_reading_a_module_that_is_not_a_dependency_is_a_finding(tmp_path):
    module = _write_module(tmp_path / "my-domain", provides=["A.md"])
    (module / "assets" / "A.md").write_text("Link to {{daily-notes.root}}.\n", encoding="utf-8")
    messages = [f.message for f in lint_module(module) if f.level >= FAIL]
    assert any("reads module 'daily-notes', which is not available here" in m for m in messages)


@pytest.mark.parametrize(
    "text",
    [
        "Heading follows prose:\n\n# Title\nProse under a heading is its own block.\n",
        "- a bullet\n- another bullet\n\n| a | b |\n| - | - |\n| 1 | 2 |\n",
        "Fenced code is not prose:\n\n````markdown\n```tasks\nnot done\ndue today\n```\n````\n",
        '<%*\nconst a = 1;\nconst b = 2;\n-%>\n---\ntype: paper\ntitle: "<% a %>"\n---\n',
    ],
    ids=["heading", "table", "nested-fence", "templater-block"],
)
def test_hardwrap_detector_does_not_fire_on_valid_markdown(text):
    assert hardwrap_lines(text) == []


def test_hardwrap_detector_fires_on_a_wrapped_bullet_and_paragraph():
    text = "- a bullet that someone\n  wrapped\n\nprose that someone\nwrapped\n"
    assert hardwrap_lines(text) == [2, 5]


def test_frontmatter_is_found_beneath_a_leading_templater_block():
    """The paper templates prompt for values above the frontmatter they then fill;
    a schema check that only looks at byte 0 would silently skip all seven of them."""
    assert frontmatter_block("---\ntype: note\n---\nbody\n") == "type: note"
    assert frontmatter_block("<%*\nconst a = 1;\n-%>\n---\ntype: paper\n---\n") == "type: paper"
    assert frontmatter_block("no frontmatter here\n") is None

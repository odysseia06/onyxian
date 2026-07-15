"""Variable substitution and folder styling (KICKSTART.md §5.3, §10.2)."""

import pytest

from onyxian.errors import PathError, RenderError
from onyxian.render import RenderContext, render_path, render_text


def ctx(own=None, qualified=None, globals_=None) -> RenderContext:
    return RenderContext(own or {}, qualified or {}, globals_ or {})


def test_own_qualified_and_global_lookups():
    c = ctx(
        own={"root": "Fitness"},
        qualified={"daily-notes": {"root": "Journal"}, "fitness": {"root": "Fitness"}},
        globals_={"today": "2026-01-01", "vault_name": "My Vault"},
    )
    text = "{{root}} | {{fitness.root}} | {{daily-notes.root}} | {{onyxian.today}} | {{onyxian.vault_name}}"
    assert render_text(text, c, origin="t") == "Fitness | Fitness | Journal | 2026-01-01 | My Vault"


def test_underscore_alias_for_kebab_module_ids():
    """§7.3 writes {{daily_notes.root}}; both spellings must resolve."""
    c = ctx(qualified={"daily-notes": {"root": "Journal"}})
    assert render_text("{{daily_notes.root}}", c, origin="t") == "Journal"


def test_unknown_variable_is_a_hard_error_naming_the_origin():
    with pytest.raises(RenderError, match=r"\{\{missing\}\} in modules/demo/assets/x.md"):
        render_text("{{missing}}", ctx(), origin="modules/demo/assets/x.md")


def test_templater_placeholders_pass_through_untouched():
    text = 'created: <% tp.date.now("YYYY-MM-DD") %>\n{{root}}\n'
    out = render_text(text, ctx(own={"root": "X"}), origin="t")
    assert out == 'created: <% tp.date.now("YYYY-MM-DD") %>\nX\n'


def test_bool_variables_render_as_yaml_booleans():
    assert render_text("{{flag}}", ctx(own={"flag": True}), origin="t") == "true"
    assert render_text("{{flag}}", ctx(own={"flag": False}), origin="t") == "false"


@pytest.mark.parametrize(
    "style,expected",
    [
        ("Title-Case-Hyphen", "Daily-Notes/Weekly-Reviews"),
        ("kebab-case", "daily-notes/weekly-reviews"),
        ("Spaces", "Daily Notes/Weekly Reviews"),
    ],
)
def test_folder_style_transforms_literal_segments(style, expected):
    out = render_path("Daily-Notes/Weekly-Reviews", ctx(), style, is_file=False, origin="t")
    assert out == expected


def test_variable_segments_are_never_styled():
    """The user's exact chosen folder name wins over the style (P4)."""
    c = ctx(own={"root": "My-CHOSEN-Name"})
    out = render_path("{{root}}/Training-Logs", c, "kebab-case", is_file=False, origin="t")
    assert out == "My-CHOSEN-Name/training-logs"


def test_filenames_are_never_styled():
    out = render_path(
        "Templates/Demo-Stuff/Plan-Template.md", ctx(), "kebab-case", is_file=True, origin="t"
    )
    assert out == "templates/demo-stuff/Plan-Template.md"


def test_variable_value_may_contain_slash():
    c = ctx(own={"root": "Research/Papers"})
    out = render_path("{{root}}/Inbox", c, "Title-Case-Hyphen", is_file=False, origin="t")
    assert out == "Research/Papers/Inbox"


def test_hostile_variable_values_fail_path_validation():
    for bad in ("..", "a/../b", "x|y", "CON"):
        with pytest.raises(PathError):
            render_path(
                "{{root}}/Inbox", ctx(own={"root": bad}), "Spaces", is_file=False, origin="t"
            )

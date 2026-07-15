"""Module-set and variable resolution (KICKSTART.md §5)."""

import pytest

from conftest import make_config, write_module
from onyxian.errors import ResolveError
from onyxian.repo import discover_modules
from onyxian.resolve import resolve_modules, resolve_variables


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "modules"
    write_module(root, "core")
    write_module(
        root,
        "demo",
        variables=[
            {"key": "root", "prompt": "Folder name", "default": "Demo-Stuff"},
            {
                "key": "cadence",
                "prompt": "Cadence",
                "type": "choice",
                "options": ["weekly", "monthly"],
                "default": "weekly",
            },
            {"key": "strict", "prompt": "Strict?", "type": "bool", "default": False},
            {"key": "required_thing", "prompt": "No default here"},
        ],
    )
    write_module(root, "extra", depends=["core", "demo"])
    write_module(root, "foe", conflicts=["demo"])
    return discover_modules(root)


def test_dependency_order_is_topological_and_stable(library):
    config = make_config(
        {
            "extra": {"version": "0.1.0"},
            "demo": {"version": "0.1.0", "vars": {"required_thing": "x"}},
        }
    )
    ordered = [m.name for m in resolve_modules(config, library)]
    assert ordered.index("core") < ordered.index("demo") < ordered.index("extra")


def test_unknown_module_is_an_error(library):
    config = make_config({"ghost": {"version": "0.1.0"}})
    with pytest.raises(ResolveError, match="'ghost'"):
        resolve_modules(config, library)


def test_missing_dependency_names_what_to_add(library):
    config = make_config({"extra": {"version": "0.1.0"}})
    with pytest.raises(ResolveError, match="requires 'demo'"):
        resolve_modules(config, library)


def test_conflicts_are_rejected(library):
    config = make_config(
        {"demo": {"version": "0.1.0", "vars": {"required_thing": "x"}}, "foe": {"version": "0.1.0"}}
    )
    with pytest.raises(ResolveError, match="cannot coexist"):
        resolve_modules(config, library)


def test_version_drift_is_loud(library):
    config = make_config({"demo": {"version": "0.0.9", "vars": {"required_thing": "x"}}})
    with pytest.raises(ResolveError, match="run `onyxian update` to move the pin forward"):
        resolve_modules(config, library)


def test_dependency_cycles_are_detected(tmp_path):
    root = tmp_path / "modules"
    write_module(root, "core")
    write_module(root, "a", depends=["core", "b"])
    write_module(root, "b", depends=["core", "a"])
    library = discover_modules(root)
    config = make_config({"a": {"version": "0.1.0"}, "b": {"version": "0.1.0"}})
    with pytest.raises(ResolveError, match="cycle"):
        resolve_modules(config, library)


def test_variables_fall_back_to_defaults(library):
    values = resolve_variables(library["demo"], {"required_thing": "x"})
    assert values == {
        "root": "Demo-Stuff",
        "cadence": "weekly",
        "strict": False,
        "required_thing": "x",
    }


def test_required_variable_without_value_is_an_error(library):
    with pytest.raises(ResolveError, match="required_thing.*required"):
        resolve_variables(library["demo"], {})


@pytest.mark.parametrize(
    "vars_,match",
    [
        ({"required_thing": "x", "cadence": "yearly"}, "must be one of"),
        ({"required_thing": "x", "strict": "yes"}, "true or false"),
        ({"required_thing": ""}, "non-empty string"),
        ({"required_thing": "x", "typo": "v"}, "no variable"),
    ],
)
def test_variable_type_violations(library, vars_, match):
    with pytest.raises(ResolveError, match=match):
        resolve_variables(library["demo"], vars_)

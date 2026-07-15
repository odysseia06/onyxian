"""Release-pipeline hardening (issue #5): one version source, a gated publish,
a wheel smoke job, and a changelog.

These are contract tests over the packaging config and the CI/publish
workflows — the pieces that only ever run at release time and so have no other
regression net. They assert the safety properties the acceptance criteria name
(the publish gate exists and `build` depends on it, the wheel smoke job runs
off-checkout on all three OSes, the version lives in exactly one hand-edited
place), not the incidental wording of a step.
"""

from __future__ import annotations

import re
import tomllib

import yaml

from conftest import REPO_ROOT
from onyxian import ENGINE_VERSION

PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PUBLISH = REPO_ROOT / ".github" / "workflows" / "publish.yml"


def _pyproject() -> dict:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def _workflow(path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _all_run_scripts(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job.get("steps", []))


# ---------------------------------------------------------- part 2: one version source


def test_pyproject_version_is_dynamic_from_engine_version():
    data = _pyproject()
    project = data["project"]
    assert "version" not in project, "version must not be a static [project] key any more"
    assert "version" in project.get("dynamic", []), "version must be declared dynamic"
    hatch_version = data["tool"]["hatch"]["version"]
    assert hatch_version["path"] == "core/onyxian/__init__.py"


def test_hatch_version_source_resolves_to_engine_version():
    """The configured regex applied to __init__.py must yield exactly ENGINE_VERSION,
    so the built wheel's metadata version cannot diverge from what `--version` reports."""
    hatch_version = _pyproject()["tool"]["hatch"]["version"]
    pattern = hatch_version["pattern"]
    source = (REPO_ROOT / hatch_version["path"]).read_text(encoding="utf-8")
    match = re.search(pattern, source)
    assert match is not None, f"pattern {pattern!r} matched nothing in {hatch_version['path']}"
    assert match.group("version") == ENGINE_VERSION


# ---------------------------------------------------------- part 4: changelog


def test_changelog_has_unreleased_and_current_version():
    assert CHANGELOG.is_file(), "CHANGELOG.md must exist"
    text = CHANGELOG.read_text(encoding="utf-8")
    assert re.search(r"^## \[Unreleased\]", text, re.MULTILINE), (
        "an [Unreleased] section is required"
    )
    assert re.search(rf"^## \[{re.escape(ENGINE_VERSION)}\]", text, re.MULTILINE), (
        f"CHANGELOG.md needs a '## [{ENGINE_VERSION}]' heading for the current version"
    )


# ---------------------------------------------------------- part 1: gated publish


def test_publish_build_is_gated_on_ci_verification():
    jobs = _workflow(PUBLISH)["jobs"]
    assert "verify-release" in jobs, "a verify-release gate job is required"
    verify = jobs["verify-release"]
    # No checkout needed; it queries the ci workflow via gh with actions:read.
    assert verify.get("permissions", {}).get("actions") == "read"
    script = _all_run_scripts(verify)
    assert "gh run list" in script and "ci.yml" in script
    assert "GITHUB_SHA" in script, "the gate must check the tagged commit's own ci run"
    build_needs = jobs["build"].get("needs")
    build_needs = [build_needs] if isinstance(build_needs, str) else (build_needs or [])
    assert "verify-release" in build_needs, "build (and thus publish) must depend on the gate"


def test_publish_build_checks_tag_matches_wheel_and_changelog():
    build = _workflow(PUBLISH)["jobs"]["build"]
    script = _all_run_scripts(build)
    assert "onyxian --version" in script, "build must assert the tag matches the built version"
    assert "CHANGELOG.md" in script, "build must assert the changelog has an entry for the tag"


# ---------------------------------------------------------- part 3: wheel smoke


def test_ci_has_wheel_smoke_job_running_off_checkout():
    jobs = _workflow(CI)["jobs"]
    assert "wheel-smoke" in jobs, "a wheel-smoke job is required in ci"
    smoke = jobs["wheel-smoke"]
    oses = smoke["strategy"]["matrix"]["os"]
    assert set(oses) == {"ubuntu-latest", "macos-latest", "windows-latest"}
    script = _all_run_scripts(smoke)
    # A real wheel is built and installed, then driven through init + doctor.
    assert "build --wheel" in script and "install dist/*.whl" in script
    assert "init smoke-vault" in script and "doctor --vault smoke-vault" in script
    # The clean-venv lookup must not be rescued by ONYXIAN_HOME, nor use the pinned clock.
    assert "unset ONYXIAN_HOME ONYXIAN_NOW" in script, (
        "the smoke job must unset both so the wheel's own real-clock lookup is tested"
    )

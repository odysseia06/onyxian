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
from typing import Any

import yaml
from conftest import REPO_ROOT

from onyxian import ENGINE_VERSION

PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PUBLISH = REPO_ROOT / ".github" / "workflows" / "publish.yml"
PRE_COMMIT = REPO_ROOT / ".pre-commit-config.yaml"
REGEN_ALL = REPO_ROOT / "tools" / "regen_all.py"
GENERATORS = ("regen_golden.py", "gen_examples.py", "build_plugin.py")


def _pyproject() -> dict[str, Any]:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)


def _workflow(path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _all_run_scripts(job: dict[str, Any]) -> str:
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


def test_bundled_content_dirs_ship_in_the_wheel():
    """Every root directory repo.py resolves under `_library/` must be force-included.

    Miss one and it still resolves from a checkout — so tests and CI stay green — while
    every `pip install`ed copy loses it (issue #67 added module-template/ this way).
    """
    repo_src = (REPO_ROOT / "core" / "onyxian" / "repo.py").read_text(encoding="utf-8")
    resolved = {"modules", *re.findall(r'_bundled\("([^"]+)"\)', repo_src)}
    force_include = _pyproject()["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    for name in sorted(resolved):
        assert (REPO_ROOT / name).is_dir(), f"repo.py resolves {name}/, which is not in the repo"
        assert force_include.get(name) == f"onyxian/_library/{name}", (
            f"{name}/ is resolved by repo.py but not force-included into the wheel"
        )


# ------------------------------------------------- issue #80: coverage, pins, entrypoint


def _test_job() -> dict[str, Any]:
    job = _workflow(CI)["jobs"]["test"]
    assert isinstance(job, dict)
    return job


def test_ci_enforces_a_coverage_floor():
    """`--cov` without a threshold prints a number nobody has to act on."""
    match = re.search(r"--cov-fail-under=(\d+)", _all_run_scripts(_test_job()))
    assert match, "the test job computes coverage but nothing fails under a threshold"
    assert int(match.group(1)) >= 90, (
        "the floor is a ratchet — raise it when the real number moves up for good, "
        "never lower it to turn a red build green"
    )


def test_every_claimed_python_runs_the_test_suite():
    """A classifier is a support claim; an untested version is an unverified one.

    Both directions matter: dropping support means dropping the job *and* the
    classifier, and adding a job for a version we don't advertise is dead CI time.
    """
    declared = {
        c.rsplit(" :: ", 1)[1]
        for c in _pyproject()["project"]["classifiers"]
        if c.startswith("Programming Language :: Python :: 3.")
    }
    matrix = _test_job()["strategy"]["matrix"]
    tested = {str(v) for v in matrix["python"]}
    # An include entry without a `python` key merges into existing combinations
    # rather than adding a job, so it adds no version.
    tested |= {str(e["python"]) for e in matrix.get("include", []) if "python" in e}
    assert declared == tested, (
        f"pyproject claims {sorted(declared)} but ci's test matrix runs {sorted(tested)} — "
        "add the missing job or drop the classifier"
    )


def test_pre_commit_ruff_matches_the_dev_extra_pin():
    """A local hook on a different ruff than CI installs reports different findings,
    which is worse than no hook: it certifies a diff that CI then rejects."""
    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    pinned = next(d.split("==", 1)[1] for d in dev if d.startswith("ruff=="))
    repos = yaml.safe_load(PRE_COMMIT.read_text(encoding="utf-8"))["repos"]
    rev = next(r["rev"] for r in repos if r["repo"].rstrip("/").endswith("ruff-pre-commit"))
    assert rev == f"v{pinned}", (
        f".pre-commit-config.yaml pins ruff {rev} but the dev extra installs {pinned} — "
        "bump both together"
    )


def test_generated_trees_regenerate_through_one_entrypoint():
    """One command regenerates every generated tree, so the ordering-by-convention
    documented in three places can't go stale against what CI actually runs."""
    assert REGEN_ALL.is_file(), "tools/regen_all.py is the single regen entrypoint"
    entrypoint = REGEN_ALL.read_text(encoding="utf-8")
    script = _all_run_scripts(_test_job())
    assert "tools/regen_all.py" in script, "ci's drift check must call the entrypoint"
    for generator in GENERATORS:
        assert generator in entrypoint, f"{generator} is missing from the regen entrypoint"
        assert generator not in script, (
            f"ci calls {generator} directly — route it through tools/regen_all.py so the "
            "entrypoint stays the one place the set of generators is listed"
        )

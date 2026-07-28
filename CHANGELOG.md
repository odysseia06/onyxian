# Changelog

All notable changes to Onyxian are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
version is [ENGINE_VERSION](core/onyxian/__init__.py) — the single source the
wheel, the CLI, and generated vaults all read.

At release time the accumulated `## [Unreleased]` notes move under a new
`## [X.Y.Z] - YYYY-MM-DD` heading; `publish.yml` refuses to ship a tag whose
version has no heading here.

## [Unreleased]

### Added

- Lockfiles now carry a machine id and monotonically increasing generation, so
  `doctor` identifies each side of a file-sync fork. `onyxian lock reconcile`
  provides a dry-run/confirmation-gated repair that explicitly selects a survivor,
  re-verifies every row against disk, preserves mismatched ownership rows, and
  retires only canonical lock-conflict siblings (#78).
- `onyxian checkpoint restore <id> [path...]` restores one or more paths, or the
  whole vault, from the private checkpoint history after an `A` / `M` / `D`
  review and confirmation. Path restores also recover historical ledger state,
  re-verifying genuinely managed bytes without falsely claiming prior
  customizations (#73).
- `--json` on the three read-only reports — `onyxian plan`, `onyxian doctor`, and
  `onyxian diff` — printing the same report as a machine-readable object on stdout
  under the same exit code, so CI and the agent layer stop parsing human prose (#66).

### Changed

- **Exit codes are now three-valued and consistent across commands** (#66), documented
  in `core/onyxian/errors.py`: `0` clean, `1` the command could not do its job, `2` it
  ran fine and has findings. Three behaviors changed: `onyxian plan` exits `2` when
  anything is pending (it always exited `0`, so a terraform-style drift check had to
  scrape text), `onyxian diff`'s read paths exit `2` rather than `1` when they list or
  show a conflict (`1` could not be told apart from a hard error), and `onyxian doctor`
  exits `2` for a warning as well as a failure, with `--json`'s `level` now carrying
  the severity. Usage errors moved off argparse's default `2` onto `1`, where they no
  longer collide with findings.

### Fixed

- `onyxian adopt` on a module whose `depends` names something the library does not have
  now fails with the same error every other command gives, instead of a `KeyError`
  traceback — auto-enabling had been written out three times, and only two of the copies
  checked (#67).

### Changed

- `kepano/obsidian-skills` now defaults **in** under the `claude-code` runtime for an
  `--answers` file or profile, matching the wizard's default-yes prompt — the two were
  building different vaults (#65). Opt out with `sources: { obsidian-skills: false }`.
  A scripted run declares the source and says it left it uninstalled; `--trust` (or a
  later `onyxian update --trust`) installs it, and the refusal is now decided before the
  fetch instead of after.

## [1.1.0] - 2026-01-01

### Changed

- Renamed the project from `onyx-vault` to `onyxian`: the PyPI distribution, the
  CLI command, the import package, the GitHub repository, the Claude Code plugin,
  and the vault artifacts are now one token everywhere. Releases up to 1.0.14
  shipped as `onyx-vault` with an `onyx` command.

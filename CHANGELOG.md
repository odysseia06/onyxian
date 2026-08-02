# Changelog

All notable changes to Onyxian are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
version is [ENGINE_VERSION](core/onyxian/__init__.py) — the single source the
wheel, the CLI, and generated vaults all read.

At release time the accumulated `## [Unreleased]` notes move under a new
`## [X.Y.Z] - YYYY-MM-DD` heading; `publish.yml` refuses to ship a tag whose
version has no heading here.

## [Unreleased]

## [0.2.0] - 2026-08-02

### Added

- Added zero-question, core-only `onyxian init`, with `--profile` for one-shot
  tailored setup.
- Added machine-readable `--json` output across the CLI and `--var` overrides
  for module installation.

### Changed

- Reworked the CLI command layout and presentation, including ANSI summaries
  and non-interactive behavior that never prompts without a TTY.
- Simplified module installation to accept manifest defaults silently;
  vault-bootstrap now composes explicit CLI flags instead of running an
  interview.
- Replaced the internal KICKSTART design document with an expanded user guide.

### Fixed

- Linked each module dashboard to its main vault areas.
- Generated Claude orientations now pass user wording and identifiers to agents
  verbatim and forbid guessed citation identifiers.

## [0.1.0] - 2026-07-30

Fresh start. The version numbering and this changelog were reset — the project
is pre-1.0 and now says so. Engine and every bundled module restart at 0.1.0.
Everything before this point (the `onyx-vault` `1.0.x` releases and `onyxian`
`1.1.0`) lives in git history; those PyPI version numbers are burned once
uploaded and stay permanently skipped.

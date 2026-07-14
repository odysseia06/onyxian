# Changelog

All notable changes to Onyxian are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
version is [ENGINE_VERSION](core/onyxian/__init__.py) — the single source the
wheel, the CLI, and generated vaults all read.

At release time the accumulated `## [Unreleased]` notes move under a new
`## [X.Y.Z] - YYYY-MM-DD` heading; `publish.yml` refuses to ship a tag whose
version has no heading here.

## [Unreleased]

## [1.1.0] - 2026-01-01

### Changed

- Renamed the project from `onyx-vault` to `onyxian`: the PyPI distribution, the
  CLI command, the import package, the GitHub repository, the Claude Code plugin,
  and the vault artifacts are now one token everywhere. Releases up to 1.0.14
  shipped as `onyx-vault` with an `onyx` command.

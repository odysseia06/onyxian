# Changelog

All notable changes to Onyxian are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
version is [ENGINE_VERSION](core/onyxian/__init__.py) — the single source the
wheel, the CLI, and generated vaults all read.

At release time the accumulated `## [Unreleased]` notes move under a new
`## [X.Y.Z] - YYYY-MM-DD` heading; `publish.yml` refuses to ship a tag whose
version has no heading here.

## [Unreleased]

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

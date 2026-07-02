---
type: oss-contributing
created: 2025-12-30
tags:
  - oss
  - oss/contributing
date: 2025-12-30
repo: https://github.com/quietbus/dbus-secrets-mock
fork: https://github.com/fkayrak/dbus-secrets-mock
language: Rust
upstream-relationship: fork
status: contributing
last-checked: 2025-12-31
---

# dbus-secrets-mock

## What It Is

- An in-memory Secret Service test double: it spins up a throwaway `org.freedesktop.secrets` implementation on a private session bus so client code can be exercised against collections, items, and prompt behavior without touching a real keyring.

## Why I'm Contributing

- keyring-audit's core promise is "zero prompts, even on locked collections", and proving that needs a test session whose collection *starts* locked. The fixture builder here could only create unlocked collections — that gap sits directly between me and the integration test in [[Handle locked collections without prompting]].

## My Fork / Branches

- `pre-locked-collections` — lets a fixture declare collections locked at startup, and adds an assertion helper that fails the test if any `Unlock` or prompt call ever reaches the mock service.

## Open PRs

- [ ] Land the pre-locked-collections PR (fixture flag + no-prompt assertion helper) ➕ 2025-12-31

## Issues I'm Tracking

- [ ] Watch the bus-teardown flakiness issue — it would bite keyring-audit's CI the same way ➕ 2025-12-31

## Local Dev Notes

- `dbus-run-session -- cargo test` for everything; same zbus tokio/async-std feature trap as in keyring-audit itself ([[2025-12-27 Project scaffold and CLI skeleton]]).

## Upstream Maintainer Notes

- Responsiveness: single-maintainer project, replies within a few days; small and friendly.
- Contribution guidelines: rustfmt clean, tests required, PRs opened as drafts until CI passes.

## Related Notes

- [[Handle locked collections without prompting]] — the downstream task this unblocks.
- [[secret-service-rs]] — the real client library the mock gets exercised against.

## Log

- 2025-12-30 — started contributing: forked after the fixture gap surfaced during [[2025-12-30 Secret Service enumeration and locked collections]].
- 2025-12-31 — pushed `pre-locked-collections` and opened the PR as a draft pending CI.

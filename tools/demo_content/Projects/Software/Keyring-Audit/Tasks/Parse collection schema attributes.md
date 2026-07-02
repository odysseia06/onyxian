---
type: task
created: 2025-12-30
status: open
tags:
  - project
  - task
date: 2025-12-30
priority: high
---

# Parse collection schema attributes

## Summary

- Turn raw item attribute maps into a typed schema model (freedesktop generic secrets, NetworkManager connections, browser profiles, chrome/libsecret schemas) so findings can say *what kind* of secret is exposed instead of dumping key-value noise.

## Why This Matters

- "Attribute `password` contains a plausible secret" is a very different severity on a Wi-Fi entry than on a test fixture; classification is what makes the report readable and the severities defensible.

## Scope

- Map the schemas seen in the captured fixtures; unknown schemas fall back to `generic` with a warning finding. No network lookups, no heuristics beyond the attribute names.

## Implementation Notes

- Match on the `xdg:schema` attribute first, then well-known key shapes; keep the table data-driven (a static map, not a match tree) so adding schemas is a one-line diff.

## Dependencies

- Fixture dumps from [[2025-12-30 Secret Service enumeration and locked collections]] are already in the repo; no upstream dependency.

## Done When

- Known schemas classify correctly in unit tests over the fixtures, unknown schemas produce the fallback warning, and the JSON report carries the schema name per finding.

## Checklist

- [ ] Parse collection schema attributes into the typed model ➕ 2025-12-30 📅 2026-01-02

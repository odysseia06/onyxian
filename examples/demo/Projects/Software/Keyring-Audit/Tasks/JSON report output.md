---
type: task
created: 2025-12-28
status: done
tags:
  - project
  - task
date: 2025-12-28
priority: medium
---

# JSON report output

## Summary

- Emit the findings report as stable, versioned JSON behind `--format json`, alongside the default human-readable text output.

## Why This Matters

- The whole point of an audit tool is feeding other tooling (CI checks, dashboards); a stable schema from day one avoids the "v0 output everyone scraped" trap.

## Scope

- serde models for report, finding, and severity; `report_version: 0` field; text renderer consumes the same model so the two outputs can never drift.

## Implementation Notes

- Snapshot test pins the JSON shape; bumping `report_version` is the documented escape hatch for breaking changes.

## Dependencies

- None — landed on top of the enumeration work from [[2025-12-30 Secret Service enumeration and locked collections]].

## Done When

- `scan --format json` round-trips through `serde_json` in tests and the snapshot test passes.

## Checklist

- [x] Emit the findings report as stable versioned JSON ➕ 2025-12-28 📅 2025-12-30 ✅ 2025-12-30

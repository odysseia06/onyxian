---
type: task
created: 2025-12-30
status: blocked
tags:
  - project
  - task
date: 2025-12-30
priority: medium
---

# Handle locked collections without prompting

## Summary

- Report locked collections honestly — label and lock state as a finding — while *proving* the scan never triggers the org.freedesktop.Secret unlock prompt.

## Why This Matters

- The read-only, zero-prompt contract is the project's core promise ([[Projects/Software/Keyring-Audit/00 Overview|Overview]]). Detection landed on 2025-12-30 via `Collection::is_locked()`; what is missing is the proof that no code path prompts, which is the only thing that makes the contract trustworthy rather than merely intended.

## Scope

- Probe stage gates all item access on lock state (done); "locked, not audited" finding with the collection label (done); an integration test that scans a session containing a pre-locked collection and asserts zero prompt traffic (open). An explicit `--unlock` opt-in stays deliberately out of scope for v0.

## Implementation Notes

- `Collection::is_locked()` is a plain `Locked` property read — no prompt on any path; wired in on 2025-12-30 ([[2025-12-30 Secret Service enumeration and locked collections]], crate evaluation in [[secret-service-rs]]). The test needs a collection that *starts* locked, which is what my [[dbus-secrets-mock]] patch adds.

## Dependencies

- **Blocked on** the pre-locked-collections patch landing upstream in [[dbus-secrets-mock]] — running the test against my own fork works locally, but pinning CI to a fork is a habit worth not starting.

## Done When

- An integration test under `dbus-run-session` scans a session with one locked and one unlocked collection, produces the locked-collection finding, and the mock records zero `Unlock`/prompt calls.

## Checklist

- [ ] Prove the zero-prompt guarantee with a locked-collection integration test ➕ 2025-12-30

---
type: devlog
created: 2025-12-30
status: logged
tags:
  - project
  - devlog
date: 2025-12-30
---

# 2025-12-30 Secret Service enumeration and locked collections

## What I Did

- End-to-end enumeration: collections → items → attribute maps, into the internal model.
- First real findings rule: flag items whose attribute *keys or values* look like they carry the secret itself (`password=...`, tokens in `xdg:comment` fields — attributes are stored unencrypted, which most users do not know).
- Landed JSON output for the report ([[JSON report output]] closed today).

## What Changed

- `scan` now walks every *unlocked* collection and produces findings; `--format json` emits the versioned report (`report_version: 0`).
- Test fixtures: two captured attribute dumps (sanitized) checked in for the parser tests.

## Problems / Friction

- Locked collections: their items cannot be read, and the only way to change that is `Unlock` — which raises a user-facing prompt, and an audit tool that prompts has already failed. Detection is the easy half: `Collection::is_locked()` is a plain `Locked` property read, no prompt on any path (verified in the crate source; evaluation notes in [[secret-service-rs]]).
- The hard half is *proving* the zero-prompt guarantee: that needs a test session whose collection starts locked, and [[dbus-secrets-mock]]'s fixtures can only create unlocked ones — forked it to add exactly that.

## Decisions / Insights

- Decision: locked collections are skipped by default and *recorded as findings* ("collection X is locked; not audited") — visible, honest, prompt-free. An explicit `--unlock` opt-in can come later, if ever. Recorded in [[Projects/Software/Keyring-Audit/00 Overview|the Overview]].
- Insight: the zero-prompt promise has to hold by construction, not by care — the probe stage gates *all* item access on lock state, so no future collector can reintroduce a prompt path. The remaining proof work is tracked in [[Handle locked collections without prompting]].

## Next Step

- Schema-attribute parsing so findings can say *what kind* of secret is exposed → [[Parse collection schema attributes]].

---
name: oss-tracking
description: The OSS tracking conventions — one note per project, the watching/contributing status lifecycles, the one-copy promote/demote rule, and last-checked staleness discipline. Use for any task touching the OSS watchlist or contributions.
---

# oss-tracking

Read the resolved root from `.vault/config.yaml` under `modules.oss.vars.root` (called `<root>` below). Two folders, one note per project, frontmatter-driven (`repo`, `fork`, `language`, `status`, `last-checked`, plus `upstream-relationship` for contributions).

## Statuses — two disjoint lifecycles

- `<root>/OSS-Watchlist` (template: OSS-Watch): `watching` → `evaluating` → (`dropped`). Spotted projects being sized up; "Possible Contribution Angles" is the section that earns promotion.
- `<root>/OSS-Contributing` (template: OSS-Contributing): `contributing` → `merged` / `maintainer` / `paused`. Projects actually being shipped to; track open PRs and issues as task lines in the note.
- The Base views split on these status sets (not folders), so they stay correct under any folder-naming style.

## The one-copy rule

**Promote** = move the note from Watchlist to Contributing (and switch its status + add `fork`/`upstream-relationship`) once changes actually ship; **demote** = move it back when contribution stops. One note, one location — never duplicate a project across both folders. Moving the user's note is a file move: propose it and let the user confirm (the escalation floor applies).

## Staleness

`last-checked` is the heartbeat: update it whenever the note is meaningfully reviewed. The Bases flag watchlist entries stale after 60 days and contributions after 30; a stale sweep means re-checking the project's pulse and either refreshing the note, proposing promotion, or proposing `dropped`/`paused` — with reasons appended to the note's `## Log`.

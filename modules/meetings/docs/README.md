# meetings

The meetings and people domain for anyone whose work runs on conversations — the product-manager archetype, though nothing in it is PM-specific: typed meeting and person notes, a status-driven Meeting-Board, a people directory, and a steward agent.

## The flow

Meeting notes are dated files at the domain root (`YYYY-MM-DD <topic>`), created from three templates: Meeting Note (the general case), One-on-One (running 1:1s fed by each person's `## Next Time` agenda), and Decision Meeting (question, options considered, decision, why). People get one note each under `People/`, with `role` and `org` in frontmatter. The Meeting-Board Base turns meeting statuses into Upcoming / Open Follow-Ups / Recent views; the People-Directory Base is the roster. The meeting-notes skill documents the conventions; the meeting-steward agent operates them.

Templates and both Bases are **managed** (improvable by updates while you leave them unedited); the seeded `00 Dashboard.md` at the domain root is the user's from day one.

## Note types

| `type` | `status` lifecycle | Extra fields | Source |
|---|---|---|---|
| `meetings-dashboard` | `active` | — | seeded `00 Dashboard.md` |
| `meeting` | `scheduled` → `held` → `closed` | `date`, `attendees`, `project` | Meeting Note, One-on-One, and Decision Meeting templates; drives the Meeting-Board |
| `person` | `active` → `former` | `role`, `org` | Person template; drives the People-Directory |

One-on-ones and decision meetings are ordinary `meeting` notes with a nested tag (`meeting/one-on-one`, `meeting/decision`), so the Meeting-Board sees every meeting and tag search narrows by kind.

## What this module deliberately does not cover

Project tracking is the `projects-software` (or `projects-gamedev`) module — a meeting's `project` field is a wikilink into whichever is enabled. Task scheduling beyond a meeting's own action items belongs to `daily-notes`.

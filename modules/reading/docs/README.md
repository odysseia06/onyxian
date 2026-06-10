# reading

The Inbox → Articles → Evergreen pipeline, generalized from the maintainer's reading system (KICKSTART.md §5.4). Stages are folders and statuses together; the tag-driven `Reading-Pipeline.base` renders Inbox / Articles / Evergreen / Everything views.

## Note types

| `type` | `status` | Extra fields | Template |
|---|---|---|---|
| `reading-capture` | `inbox` → `kept` (or left to die — a feature) | `source`, `url` | Quick Capture |
| `reading-article` | `kept` | `source`, `author`, `url` | Article Note |
| `evergreen` | `evergreen` | — | Evergreen Note |

## Design notes

- Web clipping rides the third-party `defuddle` skill (P6) — referenced, never bundled.
- Source-specific folders (the canonical vault keeps a `Hacker-News/` capture stream) are user territory: adopt leaves them, the module doesn't impose them.
- Variables: `root` (default `Reading`).

Seeded: `00 Dashboard.md`.

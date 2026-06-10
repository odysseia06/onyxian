# daily-notes

Generalized from the maintainer's daily system (KICKSTART.md §5.4): one note per day under a date hierarchy, structured by Tasks-plugin queries that bake the day's date in at creation time, so due/scheduled/overdue/carry-over views are correct forever, not relative to whoever opens the note later.

## Note type

| `type` | `status` lifecycle | Extra fields | Template |
|---|---|---|---|
| `daily` | `open` → `closed` (end-of-day review) | `date`; optionally `weight` when fitness tracking uses daily notes | Daily Note |

## Variables

- `root` (default `Daily-Notes`).
- `granularity` (`YYYY/MM` | `YYYY` | `flat`, default `YYYY/MM`) — folder layout only; the filename is always `YYYY-MM-DD.md`. Date folders are created on use (by you or the daily-planner agent), not scaffolded: empty year folders for years that have not happened would be noise.

## Design notes

- The template's query macro needs Templater to expand and the Tasks plugin to render; as a plain copy it degrades to visible placeholders (P2) and the note still works as paper.
- Carry-over is query-driven, not copy-driven — unfinished tasks surface automatically; nothing is duplicated forward.
- The `## Intake` nutrition tally seen in the source vault is deliberately *not* in the shipped template: it is the fitness module's convention (see its fitness-review skill), and daily notes must stand alone (P4).

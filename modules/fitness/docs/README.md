# fitness

Generalized from the maintainer's lived-in fitness system (KICKSTART.md §5.4): the structure, templates, and views are the proven daily-use shapes with every personal number stripped — targets live in the user's own seeded Strategy and Goals notes, never in module content.

## Note types

| `type` | `status` lifecycle | Extra fields | Template |
|---|---|---|---|
| `training-log` | `logged` | `energy`, `session_type` | Workout Log |
| `training-plan` | `active` → retired by the user | — | Workout Plan |
| `exercise` | `active` | — | Exercise Note |
| `bodyweight-log` | `logged` | `weight` | Bodyweight Log |
| `measurement` | `logged` | — | Measurement Check-In |
| `meal-plan` | `active` | — | Meal Plan |
| `recipe` / `food` | `active` | — | Recipe Note / Food Note |
| `health` / `recovery` / `supplement` | `active` | — | Health / Recovery / Supplement Note |
| `knowledge` | `active` | `source` | Knowledge Note |
| `fitness-review` | `logged` | `cadence: weekly\|monthly` | Weekly / Monthly Review |

Seeded (yours from day one): `00 Dashboard.md`, `Goals.md`, `Recurring Tasks.md`, `Nutrition/Strategy.md`.

## Views (P5)

- `Tracking/Bodyweight.base` — weight over time; reads `weight > 0` from `daily`- or `bodyweight`-tagged notes, so both tracking styles work.
- `Training/Training-Log.base` — session overview driven by the `fitness/log` tag. Tag-driven on purpose: tags survive any folder-naming style.

## Variables

- `root` (default `Fitness`) — the domain folder.
- `review_cadence` (`weekly` | `monthly` | `both`, default `both`) — consumed by the fitness-review skill and the fitness-coach agent; both review folders exist regardless so switching cadence later needs no migration.

The fitness-coach agent's disclaimer line (§17.4) is in `agents/fitness-coach.yaml` — owner-approved wording lives there and nowhere else.

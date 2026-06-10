---
name: fitness-review
description: The fitness system's working conventions — strategy-note-driven targets, the daily Intake tally, bodyweight tracking, and how weekly/monthly reviews are produced. Use when logging food or training, tracking weight, or writing a fitness review.
---

# fitness-review

The fitness module is strategy-note-driven: every target lives in the user's notes, never in instructions. Read the resolved folder root from `.vault/config.yaml` under `modules.fitness.vars.root` (called `<root>` below) and the review cadence from `modules.fitness.vars.review_cadence`.

## The one iron rule

Numeric targets (calories, macros, target weight, session counts) come from `<root>/Nutrition/Strategy.md` and `<root>/Goals.md` — and only from there. Reference the source (`see [[Strategy|Nutrition Strategy]]`) rather than copying numbers into other notes, so they stay current. If the Strategy note is empty, ask the user to fill it; never invent targets.

## Daily intake tally (when the daily-notes module is enabled)

- Track what is **actually eaten** (not planned meals) in an `## Intake` section of that day's daily note.
- Format: a Markdown table `Item | kcal | Protein | Carbs | Fat`, one row per consumed item, then bold **Total** and **Remaining** rows computed against the Strategy targets.
- Wikilink the meal/food note when one exists; estimate macros for one-off items (restaurant, café) and say they are estimates.
- When logging food: append the row, recompute **Total** and **Remaining**, check off the matching meal task if one exists, and flag anything on the Strategy "limit/avoid" list.

## Tracking

- Bodyweight: either a `weight:` frontmatter value in the daily note, or a Bodyweight Log note in `<root>/Tracking/Bodyweight` — the `Bodyweight.base` view reads both (it filters on `weight > 0` over `daily`/`bodyweight`-tagged notes).
- Measurements: Measurement Check-In notes in `<root>/Tracking/Measurements`, same cadence as reviews.
- Training: one Workout Log per session in `<root>/Training/Logs`; `Training-Log.base` is the overview, driven by the `fitness/log` tag — keep tags accurate.

## Reviews

- Cadence per config: `weekly`, `monthly`, or `both`. Weekly reviews land in `<root>/Reviews/Weekly` from the Weekly Review template; monthly in `<root>/Reviews/Monthly` from the Monthly Review template. Name them by date (`YYYY-MM-DD Weekly Review`).
- A weekly review reads the week's workout logs, the bodyweight trend (the base's Last 7 Days view), and intake adherence from daily notes; it fills the template's sections with observations, not pasted raw data.
- A monthly review works at trend level: goal progress against `Goals.md`, training and nutrition trajectories, body/health trends, and concrete changes for next month.
- Reviews describe and propose; they do not silently rewrite plans. Proposed plan changes go under the review's "Next" section for the user to act on.

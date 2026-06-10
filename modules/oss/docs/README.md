# oss

Watchlist → Contributing, generalized from the maintainer's OSS tracking (KICKSTART.md §5.4). One frontmatter-driven note per project; the two Bases split on the disjoint status sets (`watching`/`evaluating`/`dropped` vs `contributing`/`merged`/`maintainer`/`paused`) rather than folders, so they survive any naming style. Staleness formulas flag watchlist entries after 60 days and contributions after 30.

| `type` | statuses | Template |
|---|---|---|
| `oss-watch` | `watching` → `evaluating` → `dropped` | OSS-Watch |
| `oss-contributing` | `contributing` → `merged` / `maintainer` / `paused` | OSS-Contributing |

Variables: `root` (default `Projects/Software`, beside the projects-software module's tree; the modules are independent — enable either without the other).

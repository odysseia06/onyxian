# Profiles

A profile is a named module set with preset answers — pure data (KICKSTART.md §5.5). Shipping a new one must never require code. A profile file works directly as `--answers` input to `init` and `adopt`.

| Profile | Modules |
|---|---|
| `minimal` | core |
| `fitness-focused` | core, daily-notes, fitness |
| `musician` | core, daily-notes, music |
| `student` | core, daily-notes, academic |
| `phd-student` | core, daily-notes, academic, research, reading |
| `researcher-developer` (the canonical example) | core, daily-notes, academic, research, reading, projects-software, oss, fitness |
| `writer` | core, daily-notes, writing, reading |

The full §5.5 roster ships. Every profile has a matching engine-generated reference vault under `examples/`.

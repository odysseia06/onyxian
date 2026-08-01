# Profiles

A profile is a named module set with preset answers — pure data. Shipping a new one must never require code. A profile file works directly as `--answers` input to `init` and `adopt`.

| Profile | Modules |
|---|---|
| `minimal` | core |
| `creator` | core, daily-notes, writing, reading, ai-workspace |
| `developer` | core, daily-notes, projects-software, oss |
| `fitness-focused` | core, daily-notes, fitness |
| `gamedev` | core, daily-notes, projects-software, projects-gamedev |
| `musician` | core, daily-notes, music |
| `student` | core, daily-notes, academic |
| `phd-student` | core, daily-notes, academic, research, reading |
| `product-manager` | core, daily-notes, meetings, reading |
| `researcher-developer` (the canonical example) | core, daily-notes, academic, research, reading, projects-software, oss, fitness, ai-workspace |
| `writer` | core, daily-notes, writing, reading |

The full roster ships. Every profile has a matching engine-generated reference vault under `examples/`.

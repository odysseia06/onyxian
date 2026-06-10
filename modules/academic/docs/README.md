# academic

Generalized from the maintainer's real course system (KICKSTART.md §5.4): a copy-per-course template subtree under `Courses/_Course-Template/`, exam prep tracked through typed chapter notes and a Base, and a free-form `Additional-Notes/` area for concepts, definitions, and topic notes.

## The copy-per-course flow

`_Course-Template/` ships with `Lectures/ Assignments/ Exam-Prep/ Readings/ Notes/ Assets/` folders, three numbered starting notes, and `Exam-Prep/Exam-Study.base`. Starting a course = copy the whole folder, fill the numbered notes, repoint the Base's folder filter (one line — Bases cannot self-scope to their containing folder, so the proven pattern from the source vault is kept). The exam-prep skill walks agents and humans through it.

The numbered notes are **seeds**: the master copies belong to the user from day one (tune the grading table, add your own sections — updates will never touch them). The Base is **managed**: improvable by updates while you leave it unedited.

## Note types

| `type` | `status` lifecycle | Extra fields | Source |
|---|---|---|---|
| `course-overview` / `course-syllabus` / `course-schedule` | `active` | — | seeded template subtree |
| `course-note` | `active` | — | Course Note template |
| exam-prep chapter notes | `to-study` → `studying` → `studied` | `chapter`, `chapter-title`, `pages` | created per chapter; drive the Exam-Study Base |

## What this module deliberately does not cover

The research pipeline (paper PDFs, summaries, reading lists — `Academic/Research/` in the source vault) is the M3 `research` module; nesting it under the same root works via that module's own `root` variable. Per-topic subfolders under `Additional-Notes/` are the user's to grow.

# academic

Generalized from the maintainer's real course system: a copy-per-course template subtree under `Courses/_Course-Template/`, exam prep tracked through typed chapter notes and a Base, and a free-form `Additional-Notes/` area for concepts, definitions, and topic notes.

## The copy-per-course flow

`_Course-Template/` ships with `Lectures/ Assignments/ Exam-Prep/ Readings/ Notes/ Assets/` folders, three numbered starting notes, and `Exam-Prep/Exam-Study.base`. Starting a course = `onyxian new course "<CODE> <Course Name>"`: the engine copies the whole folder and repoints the Base's folder filter at the new course (Bases cannot self-scope to their containing folder), leaving the numbered notes to fill. The exam-prep skill walks agents and humans through it.

Note templates (Course Note, Chapter Note, Lecture Note, Assignment) install under `Templates/Academic/`; the seeded `00 Dashboard.md` at the domain root is the user's home for current courses and deadlines.

The numbered notes are **seeds**: the master copies belong to the user from day one (tune the grading table, add your own sections — updates will never touch them). The Base is **managed**: improvable by updates while you leave it unedited.

## Note types

| `type` | `status` lifecycle | Extra fields | Source |
|---|---|---|---|
| `academic-dashboard` | `active` | — | seeded `00 Dashboard.md` |
| `course-overview` / `course-syllabus` / `course-schedule` | `active` | — | seeded template subtree |
| `course-note` | `active` | — | Course Note template |
| `lecture-note` | `active` | — | Lecture Note template |
| `assignment` | `todo` → `in-progress` → `submitted` → `graded` | `due` | Assignment template |
| `chapter-note` | `to-study` → `studying` → `studied` | `chapter`, `chapter-title`, `pages` | Chapter Note template; drives the Exam-Study Base |

## What this module deliberately does not cover

The research pipeline (paper PDFs, summaries, reading lists — `Academic/Research/` in the source vault) is the `research` module; nesting it under the same root works via that module's own `root` variable. Per-topic subfolders under `Additional-Notes/` are the user's to grow.

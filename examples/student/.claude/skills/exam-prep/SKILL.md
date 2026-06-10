---
name: exam-prep
description: The academic module's working conventions — starting a course from the template subtree, chapter-note study tracking with the Exam-Study Base, and building study/spaced-repetition schedules from the syllabus and schedule notes. Use for any coursework, exam prep, or study-planning task.
---

# exam-prep

Read the resolved domain root from `.vault/config.yaml` under `modules.academic.vars.root` (called `<root>` below).

## Starting a course

1. Copy the whole `<root>/Courses/_Course-Template/` folder to a sibling named `<CODE> <Course Name>` (e.g. `IAM-504 Public Key Cryptography`). The numbered notes keep their names; one copyable folder is the whole point.
2. Fill `00 Overview.md` (instructor, grading table), `01 Syllabus.md`, and `02 Schedule.md` (week-by-week topics, readings, assignment dates).
3. Open the copied `Exam-Prep/Exam-Study.base` and update its `file.inFolder(...)` filter to the new course's `Exam-Prep` path — one line; Bases cannot self-scope.
4. Never work inside `_Course-Template` itself; it is the pristine master.

## Chapter study tracking

- One note per chapter/topic in the course's `Exam-Prep/`, with frontmatter fields `chapter` (number), `chapter-title`, `pages`, and `status`.
- `status` lifecycle: `to-study` → `studying` → `studied`. The Exam-Study Base turns these into the All Chapters / Still To Study / Board views — keep frontmatter accurate and the views stay truthful.

## Study plans and spaced repetition

- Build study plans from `01 Syllabus.md`, `02 Schedule.md`, and assignment deadlines in the course folder — cite which note each date came from. If deadline information conflicts across notes, stop and ask; never pick silently.
- Spaced repetition: when a chapter reaches `studied`, schedule reviews as Tasks-plugin tasks (`- [ ] Review <chapter note> 📅 <date>`) at roughly +3, +10, and +30 days, inside the chapter note or the course's exam-plan note. With the daily-notes module enabled, the daily note's queries surface them automatically on the right day.
- Lecture notes are the user's (`Lectures/`); produce derived notes (summaries, question banks) in `Exam-Prep/` or `Notes/` alongside them, never by editing the originals.

## Course notes

- General course notes use the Course Note template (Templates folder, under `Academic/`): key concepts, notes, questions, references. Keep tags lowercase; `course` plus course-specific tags as the user prefers.

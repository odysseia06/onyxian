---
name: exam-prep
description: The academic module's working conventions — starting a course from the template subtree, chapter-note study tracking with the Exam-Study Base, and building study/spaced-repetition schedules from the syllabus and schedule notes. Use for any coursework, exam prep, or study-planning task.
---

# exam-prep

Read the resolved domain root from `.vault/config.yaml` under `modules.academic.vars.root` (called `<root>` below).

## Starting a course

1. Run `onyxian new course "<CODE> <Course Name>"` (e.g. `CS-410 Applied Cryptography`): it copies the whole `<root>/Courses/_Course-Template/` folder to a sibling, dates the notes today, and repoints the Exam-Study Base's `file.inFolder(...)` filter at the new course's `Exam-Prep` — no manual Base edit needed.
2. Fill `00 Overview.md` (instructor, grading table), `01 Syllabus.md`, and `02 Schedule.md` (week-by-week topics, readings, assignment dates).
3. Never work inside `_Course-Template` itself; it is the pristine master.

## Chapter study tracking

- One note per chapter/topic in the course's `Exam-Prep/`, created from the Chapter Note template (Templates folder, under `Academic/`), with frontmatter fields `chapter` (number), `chapter-title`, `pages`, and `status`.
- `status` lifecycle: `to-study` → `studying` → `studied`. The Exam-Study Base turns these into the All Chapters / Still To Study / Board views — keep frontmatter accurate and the views stay truthful.

## Study plans and spaced repetition

- Build study plans from `01 Syllabus.md`, `02 Schedule.md`, and assignment deadlines in the course folder — cite which note each date came from. If deadline information conflicts across notes, stop and ask; never pick silently.
- Spaced repetition: when a chapter reaches `studied`, schedule reviews as Tasks-plugin tasks (`- [ ] Review <chapter note> 📅 <date>`) at roughly +3, +10, and +30 days, inside the chapter note or the course's exam-plan note. With the daily-notes module enabled, the daily note's queries surface them automatically on the right day.
- Lecture notes are the user's (`Lectures/`); produce derived notes (summaries, question banks) in `Exam-Prep/` or `Notes/` alongside them, never by editing the originals.

## Course notes

- General course notes use the Course Note template (Templates folder, under `Academic/`): key concepts, notes, questions, references. Keep tags lowercase; `course` plus course-specific tags as the user prefers.
- Lecture Note and Assignment templates live beside it for notes in `Lectures/` and `Assignments/`; an Assignment note's `due` date feeds study plans and deadline answers.

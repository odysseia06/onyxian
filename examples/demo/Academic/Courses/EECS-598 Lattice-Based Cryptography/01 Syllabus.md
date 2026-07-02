---
type: course-syllabus
created: 2025-12-26
status: active
tags:
  - course
  - syllabus
date: 2025-12-26
---

# Syllabus

## Course Description

- Graduate introduction to lattices in cryptography: geometric and computational foundations (Minkowski, SVP/CVP, LLL), the average-case problems SIS and LWE with their worst-case hardness evidence, the trapdoor and Gaussian-sampling toolbox, ring variants for efficiency, and a tour of constructions from encryption through signatures and IBE to the edge of FHE.

## Learning Objectives

- State the standard worst-case → average-case reductions precisely and know which direction each one runs.
- Work fluently with discrete Gaussians and the smoothing parameter — the technical core of the whole course.
- Implement toy Regev encryption and break under-parameterized instances, to make the parameter constraints felt rather than memorized.
- Read [[Gentry2008 - Trapdoors for Hard Lattices]]-era primary sources without survey support.

## Prerequisites

- Linear algebra (comfortable with dual bases and Gram–Schmidt), discrete probability, and an intro cryptography course (reductions, IND-CPA, ROM).

## Textbooks / References

- Primary: the course lecture notes (linked from [[Academic/Courses/EECS-598 Lattice-Based Cryptography/00 Overview|the Overview]]), cited below as "LN n".
- Companion survey: [[Peikert2016 - A Decade of Lattice Cryptography]] — the same arc with full proofs.
- Reference: Micciancio & Goldwasser, *Complexity of Lattice Problems* — for the complexity-theoretic background only.

## Policies

- Audit pacing: two lectures per week; slipping a week is fine, silently skipping exercises is not.
- A chapter note in Exam-Prep may only move to `studied` once the lecture's exercises have been attempted and written up.
- Spaced reviews (+3 / +10 / +30 days) are scheduled as tasks inside each chapter note when it reaches `studied`, so the daily note surfaces them.

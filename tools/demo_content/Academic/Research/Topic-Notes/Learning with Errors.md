---
type: topic-note
created: 2025-12-23
status: active
tags:
  - research
  - lattices
---

# Learning with Errors

The thread I am actually following this winter: LWE as a problem, the trapdoor machinery that makes it constructive, and the survey-level map of everything built on top. One note per thread, links to the summaries — the library itself stays flat.

## The Thread

- [[Regev2005 - Learning with Errors]] defines the problem and supplies the worst-case hardness evidence; everything below consumes it.
- [[Gentry2008 - Trapdoors for Hard Lattices]] turns a short basis into an oblivious Gaussian sampler — the step from "LWE is hard" to "LWE does things" (signatures, IBE).
- [[Peikert2016 - A Decade of Lattice Cryptography]] is the map: reductions, tools, constructions, and the ring-variant fine print.

## Where This Is Going

- Next intake per [[Lattice Crypto On-Ramp]]: Micciancio–Peikert 2012 (gadget trapdoors), then Ring-LWE (LPR 2010) when the course reaches week 9.
- The course track runs in parallel — chapter notes live under [[Academic/Courses/EECS-598 Lattice-Based Cryptography/00 Overview|EECS-598 Lattice-Based Cryptography]].

## Open Threads

- The classical-vs-quantum reduction gap for narrow-error LWE keeps coming up; if it grows into a real question it gets its own note in Open-Questions.
- How much of the GPV sampler survives in deployed schemes (Falcon) versus being replaced by gadget tricks — check after the MP12 read.

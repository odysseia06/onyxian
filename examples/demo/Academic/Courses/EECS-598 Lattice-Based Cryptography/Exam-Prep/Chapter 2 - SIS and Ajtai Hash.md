---
type: chapter-note
created: 2025-12-31
status: studying
tags:
  - course
  - exam-prep
chapter: 2
chapter-title: Short Integer Solution and Ajtai's hash function
pages: LN 3-4
---

# Chapter 2 - SIS and Ajtai Hash

In progress since 2025-12-31; PS2 half done. Moves to `studied` only after the collision-resistance reduction is written up without the notes open.

## Key Concepts

- SIS(n, q, β, m): given uniform A ∈ Z_q^{n×m}, find nonzero z ∈ Zᵐ with Az = 0 mod q and ‖z‖ ≤ β. Needs β ≥ √m (else no solution guaranteed) and β « q (else trivial q-vectors qualify).
- Ajtai's hash f_A(x) = Ax mod q on x ∈ {0,1}ᵐ compresses for m > n log q; a collision pair gives z = x − x' with ‖z‖ ≤ √m — collision resistance *is* SIS, no slack lost.
- The worst-case connection: solving SIS on average solves approximate SIVP in the worst case; the reduction's Gaussian machinery is previewed here and developed properly in week 5.

## Open Questions for This Chapter

- Where exactly the m > n log q compression threshold interacts with the β constraint when setting concrete parameters — the lecture waves at it; PS2 problem 3 seems designed to force it.
- How the SIS normal form (identity block in A) changes the reduction, if at all.

## Exercise Notes (PS2, in progress)

- Problem 1 (collision ⇒ SIS solution) done — the ±1 coordinate bound is the whole trick.
- Problems 2–3 remaining; blocked on nothing, just time.

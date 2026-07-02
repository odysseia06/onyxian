---
title: "On Lattices, Learning with Errors, Random Linear Codes, and Cryptography"
aliases:
  - LWE
authors:
  - Oded Regev
year: 2005
venue: "STOC 2005"
type: "foundations"
topics:
  - lattices
  - lwe
  - worst-case-hardness
tags:
  - paper

status: "summarized"
priority: "high"
rating: 5

citation_key: "Regev2005"
pdf: ""
doi: "10.1145/1060590.1060603"
url: "https://cims.nyu.edu/~regev/papers/qcrypto.pdf"

date_added: "2025-12-20"
date_summarized: "2025-12-23"

compares_to: []
improves_on: []
related_work:
  - "[[Gentry2008 - Trapdoors for Hard Lattices]]"
  - "[[Peikert2016 - A Decade of Lattice Cryptography]]"

summary_template: "foundations"
personal_take: "The problem definition the whole post-quantum program stands on; read before anything else in the area."
---

## One-Sentence Summary
- Defines the Learning with Errors (LWE) problem, shows that solving it on average is at least as hard as quantumly approximating worst-case lattice problems, and builds a public-key encryption scheme from it.

## Why This Paper Matters
- LWE became *the* average-case problem of lattice cryptography: Kyber, Dilithium, FHE, and most of the trapdoor literature are downstream of this definition.
- The worst-case to average-case reduction means random keys are as hard to break as the hardest instances of GapSVP/SIVP — a security guarantee number-theoretic assumptions never offered.

## Problem Statement
- Ajtai's SIS gives one-way and collision-resistant functions from worst-case lattice assumptions, but (at the time) no satisfying public-key encryption; Ajtai–Dwork had poor parameters. Is there a learning-style average-case problem with worst-case lattice hardness that supports PKE?

## Main Contribution
- The LWE definition (search and decision), a quantum worst-case to average-case reduction, search-to-decision equivalence for prime moduli, and an LWE-based PKE scheme with security from decision-LWE.

## Foundational Question
- Can public-key cryptography rest on the worst-case hardness of lattice problems?

## Core Definitions
-
- Definition 1: the LWE distribution A_{s,χ} — samples (a, ⟨a, s⟩ + e mod q) with a uniform in Z_q^n and e drawn from a discretized Gaussian of width αq.
- Definition 2: search-LWE — recover s from polynomially many samples; decision-LWE — distinguish A_{s,χ} from uniform on Z_q^n × Z_q.
- Definition 3: the noise condition αq > 2√n, needed for the reduction to go through.

## Model / Formal Setting
-
- Objects studied: n-dimensional lattices; worst-case problems GapSVP_γ and SIVP_γ with γ = Õ(n/α).
- Adversary / environment: any algorithm solving LWE with non-negligible advantage over random instances.
- Assumptions: none beyond worst-case lattice hardness; the reduction itself is quantum.

## Main Theorems / Statements
-
- Theorem 1: an efficient (even average-case) algorithm for search-LWE_{n,q,χ} yields an efficient *quantum* algorithm for worst-case SIVP_γ and GapSVP_γ, γ = Õ(n/α).
- Theorem 2: there is a PKE scheme, semantically secure under decision-LWE, with public keys of Õ(n²) bits and encryption blowup Õ(n) per bit.

## Proof Ideas
-
- Intuition: an LWE solver lets you turn discrete Gaussian samples over a lattice into *narrower* Gaussian samples; iterate until the samples are short enough to solve the worst-case problem.
- Key lemmas: solving CVP-with-a-hint from LWE samples (classical part); converting a CVP solver into narrower Gaussian samples via a quantum Fourier transform over the dual lattice (the quantum step).
- Main techniques: search-to-decision by guessing coordinates of s one residue at a time; smoothing-parameter arguments for the Gaussian machinery.

## Conceptual Contribution
- Recasts lattice hardness as noisy linear algebra — a learning problem — which is exactly the shape cryptographic constructions want to consume. "LWE as the new DDH" starts here.

## Comparison to Related Work
- Strictly stronger starting point than Ajtai–Dwork for PKE (better parameters, cleaner problem); complements SIS, which remains the natural home for hashing and signatures. Peikert 2009 later removed the quantum step for GapSVP at the cost of larger moduli.

## Strengths
- The problem definition is minimal and versatile; twenty years of constructions have consumed it unchanged.
- The reduction gives real evidence, not just heuristics, for average-case hardness.

## Weaknesses
- The reduction is inherently quantum for the standard parameter regime; a fully classical reduction for small moduli is still open.
- The original decision-LWE equivalence needs q prime and poly-bounded; later work generalizes but the paper's own statement is narrow.

## My Take
- The rare foundations paper that is also readable. The Gaussian-narrowing loop is the part worth internalizing — GPV's sampler ([[Gentry2008 - Trapdoors for Hard Lattices]]) makes much more sense after it.

## Open Questions
- Classical worst-case hardness for the standard narrow-error regime?
- How far can the error distribution be weakened (deterministic or small-support errors) before hardness collapses?

## Research Relevance
- Anchor node of my [[Learning with Errors]] thread and week 4 of [[Academic/Courses/EECS-598 Lattice-Based Cryptography/00 Overview|EECS-598]]; everything else in the library cites it.

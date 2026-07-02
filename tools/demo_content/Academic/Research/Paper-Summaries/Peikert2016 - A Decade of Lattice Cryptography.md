---
title: "A Decade of Lattice Cryptography"
aliases: []
authors:
  - Chris Peikert
year: 2016
venue: "Foundations and Trends in Theoretical Computer Science"
type: "survey"
topics:
  - lattices
  - sis
  - lwe
  - ring-lwe
tags:
  - paper

status: "summarized"
priority: "medium"
rating: 5

citation_key: "Peikert2016"
pdf: ""
doi: "10.1561/0400000074"
url: "https://eprint.iacr.org/2015/939"

date_added: "2025-12-20"
date_summarized: "2025-12-31"

compares_to: []
improves_on: []
related_work:
  - "[[Regev2005 - Learning with Errors]]"
  - "[[Gentry2008 - Trapdoors for Hard Lattices]]"

summary_template: "survey"
personal_take: "Still the best single map of the SIS/LWE landscape; I use its notation as my house style."
---

## One-Sentence Summary
- A self-contained survey of the 2005–2015 lattice-cryptography program: the SIS/LWE problems and their ring variants, the worst-case hardness evidence behind them, and the main constructions built on top.

## Why This Paper Matters
- It is the standard on-ramp to the field — the place where the scattered notation and folklore of a decade of papers got consolidated into one coherent account.

## Problem Statement
- By 2015 the lattice literature had grown too large and too internally cross-referenced to enter through primary sources; the survey's job is to give the working definitions, the hardness picture, and the construction patterns in one pass.

## Main Contribution
- A unified treatment of SIS, LWE, Ring-SIS, and Ring-LWE with their reductions, plus a guided tour of the canonical constructions (Regev and dual-Regev encryption, trapdoors and GPV signatures, and the road toward FHE).

## Scope of the Survey
-
- Topic covered: average-case lattice problems, worst-case/average-case reductions, and the cryptographic constructions consuming them.
- Time span: roughly Ajtai 1996 as prehistory, then 2005–2015 in earnest.
- Exclusions: concrete cryptanalysis and parameter selection are sketched, not developed; implementation and side channels are out of scope; it predates the NIST PQC process outcomes.

## Main Taxonomy
-
- Category 1: foundations — lattice background, Gaussians, SIS/LWE definitions and reductions.
- Category 2: essential tools — trapdoors, discrete Gaussian sampling, gadget matrices.
- Category 3: constructions — encryption, signatures, IBE and beyond, with ring variants for efficiency.

## Key Themes
-
- Theme 1: worst-case to average-case reductions as the field's distinguishing security story.
- Theme 2: the trapdoor toolbox as the bridge from hardness to functionality.
- Theme 3: rings (Ring-SIS/Ring-LWE) as the price-of-efficiency axis, with their own hardness fine print.

## Important Papers Mentioned
-
- Paper A: [[Regev2005 - Learning with Errors]] — the LWE definition and quantum reduction.
- Paper B: [[Gentry2008 - Trapdoors for Hard Lattices]] — preimage sampling, GPV signatures, LWE-based IBE.
- Paper C: Lyubashevsky–Peikert–Regev 2010 (Ring-LWE) and Micciancio–Peikert 2012 (gadget trapdoors) — both queued on [[Lattice Crypto On-Ramp]].

## Comparison Dimensions
-
- Security model: worst-case-hard problem backing each construction, and whether the reduction is quantum or classical.
- Efficiency: key/ciphertext sizes and the plain-vs-ring gap.
- Assumptions: error width, modulus size, and how parameter choices trade against the reductions.
- Practicality: which constructions were, by 2015, plausibly deployable.
- Application domain: encryption vs signatures vs "advanced" (IBE, FHE-adjacent).

## Survey Strengths
-
- What it organizes well: notation and parameter conventions — reading primary sources is dramatically easier after adopting its conventions.
- What is especially useful: the reduction diagrams connecting GapSVP/SIVP to SIS/LWE to constructions; Chapter 4's honest fine print on Ring-LWE hardness.

## Survey Weaknesses
-
- Missing areas: concrete security estimation (lattice estimators moved fast after 2016) and everything NIST-era.
- Biases: leans toward the author's own reduction-first view of the field; cryptanalysis gets a supporting role.
- Outdated parts: the FHE chapter stops before the modern bootstrapping era; no isogeny or code-based context.

## Comparison to Related Work
- Complements rather than replaces Micciancio–Goldwasser's complexity-theoretic book; it is the constructions-facing map, and newer lecture notes largely follow its structure.

## Strengths
- Self-contained: the Gaussian and smoothing-parameter background is developed rather than cited.
- Precise about what is and is not proven — rare for a survey.

## Weaknesses
- A decade old now; it needs to be paired with post-2016 cryptanalysis to set parameters responsibly.
- Dense as a first read; Chapters 1–4 before 5+ is the only order that works.

## My Take
- Read it as the companion text to [[Academic/Courses/EECS-598 Lattice-Based Cryptography/00 Overview|EECS-598]] — the course follows almost the same arc, and the survey fills in every proof the lectures wave at.

## Open Questions
- What would the same survey look like written after Kyber/Dilithium standardization — which of the 2015-era open problems actually closed?
- Where does the ring-hardness fine print stand today against the best structured-lattice attacks?

## Research Relevance
- The map for my [[Learning with Errors]] thread and the source of the ordering in [[Lattice Crypto On-Ramp]].

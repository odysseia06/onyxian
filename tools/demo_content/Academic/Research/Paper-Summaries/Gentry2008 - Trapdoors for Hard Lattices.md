---
title: "Trapdoors for Hard Lattices and New Cryptographic Constructions"
aliases:
  - GPV08
authors:
  - Craig Gentry
  - Chris Peikert
  - Vinod Vaikuntanathan
year: 2008
venue: "STOC 2008"
type: "construction"
topics:
  - lattices
  - trapdoors
  - gaussian-sampling
  - signatures
  - ibe
tags:
  - paper

status: "reading"
priority: "high"
rating:

citation_key: "Gentry2008"
pdf: ""
doi: "10.1145/1374376.1374407"
url: "https://eprint.iacr.org/2007/432"

date_added: "2025-12-27"
date_summarized: ""

compares_to: []
improves_on: []
related_work:
  - "[[Regev2005 - Learning with Errors]]"
  - "[[Peikert2016 - A Decade of Lattice Cryptography]]"

summary_template: "construction"
personal_take: "The trapdoor toolbox — preimage sampling is the move that turned SIS/LWE into signatures and IBE."
---

## One-Sentence Summary
- Shows how to use a short lattice basis as a trapdoor for *sampling* short preimages under the SIS function without leaking the basis, and builds hash-and-sign signatures and the first LWE-based IBE from it.

## Why This Paper Matters
- Before GPV, a short basis was only known to help with decoding; making it drive an oblivious Gaussian sampler is what unlocked the whole "advanced constructions" line (IBE, HIBE, ABE) surveyed in [[Peikert2016 - A Decade of Lattice Cryptography]].

## Problem Statement
- NTRUSign-style signatures leaked their trapdoor through the signature transcript (each signature is biased toward the secret basis, and Nguyen–Regev's attack recovers it). How do you use a lattice trapdoor so that outputs are distributed independently of which trapdoor you hold?

## Main Contribution
- Preimage sampleable trapdoor functions (PSFs) from SIS, a discrete Gaussian sampler over arbitrary lattice cosets, full-domain-hash signatures secure in the ROM, and identity-based encryption from LWE via the "dual" Regev scheme.

## Construction Goal
-
- What object is being constructed: a trapdoor function family f_A(e) = Ae mod q that anyone can evaluate but only the trapdoor holder can invert — by *sampling* a preimage from the right distribution, not by finding a canonical one.
- What properties are required: preimage samples must be statistically independent of the particular trapdoor basis; one-wayness/collision resistance from SIS.

## Main Construction Idea
-
- High-level intuition: replace Babai's deterministic nearest-plane rounding with randomized rounding — at each level, choose the plane with probability proportional to a Gaussian weight — so the output is a discrete Gaussian over the coset, the same distribution any short basis would produce.
- Design strategy: hash the message to a syndrome u, Gaussian-sample a short e with Ae = u; verification is just re-evaluating f_A and checking the norm.

## Building Blocks
-
- Primitive 1: SIS/LWE as in [[Regev2005 - Learning with Errors]] (dual Regev encryption for the IBE half).
- Primitive 2: Ajtai-style generation of a uniform A together with a short basis of Λ⊥(A).
- Assumption dependencies: smoothing-parameter machinery (Micciancio–Regev) to argue the sampled distribution is basis-independent.

## Construction Walkthrough
-
- Key generation: (A, T) with A statistically close to uniform and T a short basis for Λ⊥(A).
- Core algorithm(s): SampleD — randomized nearest-plane over T, producing e ~ D_{Λ⊥_u(A), s} for s ≥ ‖T̃‖·ω(√log n).
- Output / verification / recovery: signature is e with Ae = H(m) and ‖e‖ ≤ s√m; IBE secret key for identity id is a preimage of H(id), used to decrypt dual-Regev ciphertexts.

## Security Model and Proof Idea
-
- Security notion: EUF-CMA for signatures, IND-CPA (anonymous) IBE — both in the random-oracle model.
- Proof approach: FDH-style — the reduction programs H by sampling e first and setting H(m) = Ae, which is distributed correctly precisely because preimage samples do not depend on the trapdoor.
- Reduction intuition: a forger either collides with a programmed preimage (breaking SIS collision resistance) or produces a fresh short preimage (breaking SIS inversion).

## Efficiency / Tradeoffs
-
- Computation: Gaussian sampling per signature is the expensive step; keys and signatures are Õ(n²)-ish — practical descendants (Falcon) needed NTRU lattices to compress this.
- (still reading — want the exact parameter table from Section 5 before filling the rest of this in)

## Comparison to Related Work
- Fixes exactly the leakage that broke GGH/NTRUSign (Nguyen–Regev 2006). Micciancio–Peikert 2012 later replaced the short-basis trapdoor with gadget trapdoors — simpler and tighter; queued next on [[Lattice Crypto On-Ramp]].

## Strengths
- One clean primitive (the sampler) powers signatures and IBE at once.
- The "sample first, program the oracle" proof pattern is reusable and shows up all over the later literature.

## Weaknesses
- ROM proofs only; standard-model lattice signatures came later and cost more.
- Trapdoor generation and sampling as described are painful to implement well — floating-point Gaussian sampling is its own research area.

## My Take
- Reading this alongside week 6 of [[Academic/Courses/EECS-598 Lattice-Based Cryptography/00 Overview|EECS-598]]; the sampler finally made sense once I stopped thinking of it as decoding and started thinking of it as *deliberately bad* decoding with calibrated randomness.

## Open Questions
- (still reading — collect these on the second pass through Sections 6–8)

## Research Relevance
- Central node of the [[Learning with Errors]] thread: it consumes Regev's problem and produces the tools every later construction borrows.

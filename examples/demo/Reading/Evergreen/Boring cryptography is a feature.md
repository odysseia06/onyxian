---
type: evergreen
created: 2025-12-26
status: evergreen
tags:
  - reading
  - reading/evergreen
date: 2025-12-26
---

# Evergreen Note

## Core Idea

- In deployed cryptography, the absence of choices is a security property. Every knob an API exposes (cipher suites, curves, padding modes) is a place where a non-specialist will eventually stand; systems that hardcode one good answer fail less often than systems that let experts pick the best one.

## Why It Matters

- It inverts the instinct researchers bring to engineering. In research, generality and parameterization are virtues; in deployment they are attack surface. Holding both stances at once — parametrize in papers, hardcode in products — is the actual skill.

## Key Insights

- The historical failures that motivated this (padding oracles, downgrade attacks, JWT `alg:none`) were all *negotiation and configuration* failures, not primitive failures.
- "Boring" is a design budget: age spends its entire novelty budget on the spec being small, and none on cryptographic innovation.
- The claim has a limit: post-quantum migration shows that sometimes a new knob (hybrid key agreement) is the conservative move — boring is about minimizing *user-facing* choice, not freezing the primitive set.

## Supporting Notes

- [[Cryptographic Right Answers]] — the prescriptive-defaults table and its shrinking-options revision history.
- [[age]] — a tool whose whole identity is this claim.
- [[Post-quantum key agreement rollout in TLS]] — the boundary case: new primitives arriving as invisible plumbing.

## Related Areas

- keyring-audit's read-only/zero-prompt contract is the same principle applied to tool design ([[Projects/Software/Keyring-Audit/00 Overview|Overview]]).

## My Take

- Titling this as a claim keeps me honest: when I catch myself adding a config flag to a security tool, this note is the argument I have to beat first.

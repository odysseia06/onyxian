---
type: reading-article
created: 2025-12-24
status: kept
tags:
  - reading
  - reading/article
date: 2025-12-24
source: latacora.com
author: Latacora (Thomas Ptacek et al.)
url: https://www.latacora.com/blog/2018/04/03/cryptographic-right-answers/
---

# Article Note

## Title / Topic

- "Cryptographic Right Answers" — a table of default answers ("encrypting: use KMS or a library like libsodium; symmetric primitive: AES-GCM or ChaCha20-Poly1305; passwords: scrypt/argon2 ...") tracked across the 2008/2015/2018 editions.

## Why I Saved This

- It is the canonical statement of prescriptive-over-configurable crypto guidance, and I keep citing it from memory in code review; I want the actual claims, with their revision history, on hand.

## Main Thesis

- Practitioners should not be choosing cryptographic primitives; they should take opinionated defaults from people who track attacks for a living, and the *changes between editions* are themselves the argument — the answers converge toward fewer choices, not better-informed choosers.

## Key Points

- Every edition removes options: the 2018 answers are shorter and more prescriptive than 2008's.
- The recurring failure mode is the joint between primitives (IVs, padding, KDF misuse), not the primitives themselves.
- "Avoid" entries (JWT's algorithm agility, ad-hoc RSA) are as valuable as the recommendations.

## What Seems Useful

- Directly applicable to keyring-audit's findings rules: severity should track *misuse likelihood*, not theoretical strength — an unencrypted attribute beside strong crypto is exactly the kind of joint failure the article describes.

## My Take

- The format ages better than any individual recommendation. Post-2018 the table needs a PQ row — which is what the capture [[Post-quantum key agreement rollout in TLS]] is about — but the philosophy transfers unchanged.

## Related Notes

- Distilled into [[Boring cryptography is a feature]].
- [[age]] on the watchlist is this article's philosophy shipped as a tool.

## Actionable Follow-Up

- Encode two or three "right answers" checks as findings rules in [[Projects/Software/Keyring-Audit/00 Overview|keyring-audit]] once schema parsing lands.

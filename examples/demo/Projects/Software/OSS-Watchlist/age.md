---
type: oss-watch
created: 2025-12-21
tags:
  - oss
  - oss/watching
date: 2025-12-21
repo: https://github.com/FiloSottile/age
language: Go
stars: 19000
license: BSD-3-Clause
status: watching
last-checked: 2025-12-29
---

# age

## What It Is

- Small file-encryption tool and format: X25519 recipients, scrypt passphrases, ChaCha20-Poly1305 payloads, and a deliberately tiny spec. The spec being small *is* the product.

## Why It Caught My Eye

- It is the cleanest living example of [[Boring cryptography is a feature]] — no cipher negotiation, no config, one right answer per job. Also personally useful for encrypting vault backups.

## How I Found It

- Re-read of [[Cryptographic Right Answers]] over the holidays; age is what that article's philosophy looks like as a shipped tool.

## Tech / Stack

- Go, filippo.io/edwards25519, a plugin protocol (`age-plugin-*`) for hardware and custom recipient types — the plugin boundary is the extensibility escape valve that keeps the core boring.

## Possible Contribution Angles

- An `age-plugin-` identity backend over the freedesktop Secret Service, so keys can live in the desktop keyring — directly adjacent to the [[Projects/Software/Keyring-Audit/00 Overview|keyring-audit]] work; needs a real design pass before proposing upstream.
- Docs: the plugin protocol is specified but example-poor; a minimal annotated plugin walkthrough would land well.

## Related Notes

- [[Boring cryptography is a feature]], [[Cryptographic Right Answers]].

## Log

- 2025-12-21 — added to watchlist
- 2025-12-29 — checked releases and issue tracker; quiet since 1.2, no contribution opening yet. Staying `watching` until the plugin idea survives a design sketch.

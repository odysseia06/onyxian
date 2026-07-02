---
type: reading-capture
created: 2026-01-01
status: inbox
tags:
  - reading
  - reading/inbox
date: 2026-01-01
source: blog.cloudflare.com
url: https://blog.cloudflare.com/pq-2024/
---

# Quick Capture

## What Caught My Attention

- Cloudflare's numbers on hybrid post-quantum key agreement (X25519 + ML-KEM) already carrying a double-digit share of their TLS 1.3 handshakes — the migration is happening quietly, as protocol plumbing, not as a cryptographic event.

## Key Idea

- Deploy hybrids first: classical + lattice KEM composed so the handshake is safe unless *both* break. Signatures are the hard part left over, because certificate chains multiply the size cost.

## Why It Seems Interesting

- It is the deployed face of exactly the hardness assumptions I am studying — ML-KEM is Module-LWE, i.e. the [[Regev2005 - Learning with Errors]] lineage shipping at internet scale.

## Rough Notes

- Client share driven almost entirely by browser defaults; server-side support is the long tail.
- "Harvest now, decrypt later" is the stated threat model justifying key agreement before signatures.
- Worth checking what fraction of *my* daily traffic negotiates a hybrid group — `ssldump` afternoon sometime.

## Possible Links

- [[Learning with Errors]] — the deployment endpoint of the thread.
- [[Boring cryptography is a feature]] — hybrids as the boring, conservative move.

## Next Step

- Triage: probably keep → article note focused on the deployment-sequencing argument (key agreement before signatures).

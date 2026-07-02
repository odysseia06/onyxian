---
type: oss-watch
created: 2025-12-30
tags:
  - oss
  - oss/watching
date: 2025-12-30
repo: https://github.com/hwchen/secret-service-rs
language: Rust
stars: 100
license: MIT OR Apache-2.0
status: evaluating
last-checked: 2025-12-31
---

# secret-service-rs

## What It Is

- The Rust library for the freedesktop Secret Service API over DBus (zbus) — sessions (plain and DH-encrypted), collections, items, search. It is the layer [[Projects/Software/Keyring-Audit/00 Overview|keyring-audit]] stands on.

## Why It Caught My Eye

- It is not just a dependency, it is the load-bearing wall under keyring-audit's zero-prompt contract — so before trusting the contract to it, I read the parts of the source the contract depends on.

## How I Found It

- crates.io search while scaffolding keyring-audit ([[2025-12-27 Project scaffold and CLI skeleton]]).

## Tech / Stack

- Rust over zbus, with the tokio/async-std runtime feature split — pin the tokio feature explicitly; this bit once already.
- `Collection::is_locked()` reads the DBus `Locked` property directly — no `Unlock` call, no prompt — which is exactly the non-interactive probe the audit contract needs. Verified by reading `src/collection.rs`, not just the docs.

## Possible Contribution Angles

- A cookbook-style docs example for read-only consumers (check lock state first, never call `unlock()`), distilled from keyring-audit's probe stage — drafting nothing yet, nothing filed.
- No functional gap found for my use case so far; if the rest of the API read-through turns one up, this note is the place it gets recorded before anything goes upstream.

## Related Notes

- [[Handle locked collections without prompting]] — where the lock-state probe gets used.
- [[dbus-secrets-mock]] — the test double the client code gets exercised against.

## Log

- 2025-12-30 — added while wiring lock detection into keyring-audit; confirmed from the source that `is_locked()` is a plain property read with no prompt path.
- 2025-12-31 — finished the API-surface read-through; nothing worth a patch, so staying `evaluating` with the docs example as the only live angle.

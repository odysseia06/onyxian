---
type: note
created: 2025-12-27
status: active
tags:
  - project
  - decision
---

# Decision - Rust for keyring-audit

Language choice for the tool, decided 2025-12-27 before writing any code. Linked from the [[Projects/Software/Keyring-Audit/00 Overview|Overview]]'s Key Decisions.

## Options Considered

- **Rust** — mature `secret-service` crate over zbus; `zeroize` for scrubbing secret buffers; ships as a single binary.
- **Go** — fastest iteration and easiest distribution, but Secret Service support means hand-rolling DBus calls over `godbus`, and the GC makes "secret material never lingers in memory" a promise I cannot actually keep.
- **Python script** — fine for a personal one-off via `secretstorage`, but this is meant to be handed to other people, and a tool that audits keyrings should not arrive with a pip dependency tree.

## Why Rust Won

- The one domain-specific requirement is memory hygiene around secret values, and Rust is the only option of the three where `zeroize`-style scrubbing is both idiomatic and enforceable.
- The `secret-service` crate already speaks the protocol correctly — sessions, encrypted transport, and a non-prompting `Collection::is_locked()` probe — so the DBus layer is inherited rather than owned; the dependency evaluation notes live in [[secret-service-rs]].

## Costs Accepted

- Slower iteration than Go, and async DBus in Rust has real ceremony (runtime feature flags bit on day one — see [[2025-12-27 Project scaffold and CLI skeleton]]).

## Revisit If

- The `secret-service` crate stops being maintained, or the tool grows a GUI — either would reopen the question.

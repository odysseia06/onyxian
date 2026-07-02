---
type: devlog
created: 2025-12-27
status: logged
tags:
  - project
  - devlog
date: 2025-12-27
---

# 2025-12-27 Project scaffold and CLI skeleton

## What I Did

- `cargo new keyring-audit`; clap-derive CLI with `scan` and `report` subcommands and a global `--format` flag.
- Sketched the `Collector` trait (`probe() -> bool`, `collect() -> Vec<Collection>`) so backends beyond Secret Service can slot in later.
- Wired up the `secret-service` crate (zbus backend) far enough to open a session against the running gnome-keyring.

## What Changed

- Repo initialized with CI stub (fmt + clippy + test), MIT license, README sketch stating the read-only contract up front.
- `scan` connects and lists collection labels — nothing more yet, but the plumbing is real.

## Problems / Friction

- zbus runtime features: the crate offers tokio and async-std flavors and the defaults pulled the wrong one; had to pin the tokio feature explicitly or two executors end up in the binary.

## Decisions / Insights

- Language decision written down properly in [[Decision - Rust for keyring-audit]] — future me should not have to re-litigate it from memory.
- Insight: the findings engine should consume a dumb data model rather than judging during collection; keeps collectors trivially testable with fixture data.

## Next Step

- Enumerate items and attributes on a real session, then decide what the findings model looks like → [[2025-12-30 Secret Service enumeration and locked collections]].

---
type: project-overview
created: 2025-12-27
status: active
tags:
  - project
date: 2025-12-27
---

# Project Overview

## What This Is

- `keyring-audit` — a small Rust CLI that audits what is actually sitting in a desktop keyring via the freedesktop Secret Service API (GNOME Keyring, KWallet): stale entries, secrets whose *attribute metadata* leaks the secret's meaning in plaintext, and collections in surprising lock states. Read-only by design; it reports, it never fixes.

## Goals

- Zero interactive prompts, ever — an audit tool that pops an unlock dialog has already failed.
- Read-only by default; anything that would mutate the keyring is out of scope for v0.
- Machine-readable findings (JSON) so the report can feed other tooling; human text output as the default.

## Architecture

- probe (DBus session discovery) → collectors (one per backend, Secret Service first) → findings engine (rules over the collected model) → report (text / JSON).
- The collected model is deliberately dumb: collections → items → attribute maps; all judgement lives in the findings rules.

## Subsystems

Add a folder per subsystem beside this note as the architecture demands (runtime, renderer, api, storage, ...) and keep one subsystem note in each; link them here.

- None split out yet — collectors will be the first subsystem folder once the KWallet backend lands.

## Key Decisions

One bullet per decision, dated, with the why; deeper rationale gets its own note in Research.

- 2025-12-27 — Rust over Go: bindings maturity plus memory hygiene for secret material; full rationale in [[Decision - Rust for keyring-audit]].
- 2025-12-27 — tokio-backed zbus rather than async-std, to match the rest of my tooling.
- 2025-12-30 — locked collections are skipped by default and *reported as findings*; implicit unlocking is never acceptable (see [[2025-12-30 Secret Service enumeration and locked collections]]).

## Links

- Repository: local `~/dev/keyring-audit` for now — pushing once the report format survives a week of use.
- Issues / board: [[Projects/Software/Project-Tasks.base|Project Tasks]] board.
- Docs: README sketch in the repo; dependency evaluation notes in [[secret-service-rs]]; test-double contribution tracked in [[dbus-secrets-mock]].

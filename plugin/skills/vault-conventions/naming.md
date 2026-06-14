# Naming rules

How names are formed in an Onyx vault (KICKSTART.md §10.2), and exactly when the engine transforms them.

## Folder style

`naming.folder_style` in `.vault/config.yaml` is a vault-wide preference with three values:

| Style | `Daily-Notes` becomes | Notes |
|---|---|---|
| `Title-Case-Hyphen` | `Daily-Notes` | the default; canonical authored form in module manifests |
| `kebab-case` | `daily-notes` | lowercased segments |
| `Spaces` | `Daily Notes` | hyphens become spaces |

## Exactly what gets transformed

The style applies to **literal folder segments authored in module manifests** — and nothing else:

- A segment that came from a **variable** (`{{root}}`) is the user's exact chosen name and is installed verbatim. Tailoring beats styling (P4).
- **Filenames** are never transformed; a template called `Note.md` stays `Note.md` under every style.
- Files and folders the **user** creates are never renamed, restyled, or judged. The style only shapes what the engine itself creates.

## Portable-path rules (§9.5)

Every path the engine plans must work on macOS, Linux, and Windows alike, so manifests and variable values are validated against the strictest rules:

- forward slashes only; relative to the vault root; no `.` / `..` segments
- no `< > : " | ? *`, control characters, or backslashes in names
- no segment ending in a dot or space; no leading/trailing whitespace in a segment
- no Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`), with or without an extension
- the engine never creates symlinks in a vault — Windows and sync tools both punish them

A violation is rejected at plan time with the offending manifest named, not discovered later by a user on another OS.

## File naming inside modules

Per-module file naming is each module's own documented convention (daily notes: `YYYY-MM-DD.md`); `core` imposes nothing beyond the portable-path rules above.

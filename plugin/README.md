# Onyx — Claude Code plugin

The Claude Code front door to Onyx. It ships two skills:

- **`vault-bootstrap`** — the interview wizard. Invokes as `/vault-bootstrap`. On first run it installs the `onyx-vault` CLI (the deterministic engine) if it isn't already present, then drives `init` or `adopt`.
- **`vault-conventions`** — the frontmatter, naming, and writing rules any agent follows when working in an Onyx vault.

## Install

```
/plugin marketplace add odysseia06/onyx
/plugin install onyx@onyx
/vault-bootstrap
```

The engine itself is the `onyx-vault` package on PyPI; the wizard installs it for you (`uv tool` / `pipx` / `pip --user`), so a Claude Code user needs no manual Python setup.

## Don't edit `skills/` here by hand

`plugin/skills/` is generated from the canonical sources at `modules/core/skills/` by `tools/build_plugin.py`, and CI fails on drift. Edit the canonical skill, then run `python tools/build_plugin.py`.

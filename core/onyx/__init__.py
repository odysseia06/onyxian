"""Onyx engine — the deterministic layer of the framework (KICKSTART.md §4.1).

This package implements the declarative reconciliation loop: ``.vault/config.yaml``
declares intent, ``.vault/lock.json`` records state, ``plan`` computes the
difference, ``apply`` reconciles it. No AI anywhere in here; agents sit above
this layer and are never load-bearing (P2).

It lives at ``core/onyx/`` in the repository (§4.2) and is importable as
the ``onyx`` package via the mapping in ``pyproject.toml``.
"""

ENGINE_VERSION = "1.0.8"

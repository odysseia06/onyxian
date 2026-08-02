"""Onyxian engine — the deterministic layer of the framework.

This package implements the declarative reconciliation loop: ``.vault/config.yaml``
declares intent, ``.vault/lock.json`` records state, ``plan`` computes the
difference, ``apply`` reconciles it. No AI anywhere in here; agents sit above
this layer and are never load-bearing.

It lives at ``core/onyxian/`` in the repository and is importable as
the ``onyxian`` package via the mapping in ``pyproject.toml``.
"""

ENGINE_VERSION = "0.2.0"

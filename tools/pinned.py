"""The single source of the repository's pinned wall-clock date.

Golden fixtures and example vaults are regenerated with ``ONYXIAN_NOW`` pinned to
this date so their rendered trees are byte-identical on every machine and OS, and
the test suite pins the same clock (``tests/conftest.py``) so assertions line up
with what those fixtures were generated against. Defined here exactly once: the two
regen scripts import it (they run as ``python tools/<script>.py``, so ``tools/`` is
``sys.path[0]``) and ``conftest.py`` loads it by file path.

This is a repo fixture pin, not engine behavior — the engine's clock contract is
the ``ONYXIAN_NOW`` env var (``core/onyxian/intent.py``), so the constant lives in
``tools/`` rather than in the shipped ``onyxian`` package.
"""

PINNED_NOW = "2026-01-01"

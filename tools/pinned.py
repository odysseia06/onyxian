"""The single source of the repository's generated-artifact pins.

Golden fixtures and example vaults are regenerated with ``ONYXIAN_NOW`` and
``ONYXIAN_MACHINE_ID`` pinned so their trees are byte-identical on every machine
and OS, and the test suite pins the same values (``tests/conftest.py``). Defined
here exactly once: the two regen scripts import it (they run as
``python tools/<script>.py``, so ``tools/`` is ``sys.path[0]``) and ``conftest.py``
loads it by file path.

These are repository fixture values, not engine defaults, so they live in
``tools/`` rather than in the shipped ``onyxian`` package.
"""

PINNED_NOW = "2026-01-01"
PINNED_MACHINE_ID = "generated-fixture"

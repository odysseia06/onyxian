# tools

Dev and CI scripts. Nothing here runs in a user's vault.

- `regen_golden.py` — regenerate the golden vault fixtures under `tests/fixtures/golden/` from their answers files, with `ONYX_NOW` pinned. The only legitimate way to change a golden tree; hand-edits to fixtures are a review-time rejection (CONTRIBUTING.md).

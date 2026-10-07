# Adversarial: corpus write refusal

## Setup
Attempt `resolve_bounded_path("references/patterns/x.json", for_write=True)`.

## Expect
`PathSafetyError`: references/patterns remains read-only.

## Covered by
`scripts/test_io_safety.py::test_blocks_protected_skill_write`

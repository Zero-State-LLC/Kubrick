# Spec: finite spend inputs

## Goal

A spend estimate accepts numeric inputs only when they can be represented as finite floats, and it must verify that per-shot charges and the running total remain finite. NaN, infinity, unrepresentable integers, or arithmetic overflow must not cause a crash or let a configured budget cap pass.

## Behavior

1. `spend_estimate(provider, rows)` returns the existing `NOT_COMPUTABLE` shape if provider pricing is missing, the rate is boolean/non-numeric/non-finite/not float-representable, or any supplied numeric `generated_seconds` value is non-finite/not float-representable.
2. `budget_error(estimate, cap)` returns `BUDGET_CAP_UNVERIFIABLE` for a numeric cap that is non-finite/not float-representable, or when a purportedly inferred estimate has a non-numeric, non-finite, or not float-representable total.
3. Float-representable finite estimates and finite calculated charges retain current boundary behavior: equality with the cap passes; totals above it fail with `BUDGET_CAP_EXCEEDED`.
4. Arithmetic overflow makes the estimate `NOT_COMPUTABLE` and must not emit a non-finite per-shot charge or total.
5. Existing semantics for no cap, boolean caps, and non-numeric caps remain unchanged.

## Acceptance criteria

- Regression coverage exercises `NaN`, positive infinity, negative infinity, float-unrepresentable integers, and arithmetic overflow for durations, charges, estimated totals, and numeric caps.
- Each invalid duration produces `NOT_COMPUTABLE` with `total_credits: null`.
- Invalid estimate totals and caps fail with `BUDGET_CAP_UNVERIFIABLE` rather than passing or raising during formatting.
- Existing spend-estimate and budget-boundary tests pass.
- Production source and the test file pass the repository's style/validation checks.

## Verification

- Targeted: `uv run --with PyYAML --with jsonschema --with pytest python -m pytest scripts/test_spend_plan_numeric_guard.py -q`
- Regression: `uv run --with PyYAML --with jsonschema --with pytest python -m pytest scripts/test_phase_b.py -q`
- Repository gates: `python scripts/kubrick.py do check --action smoke`, `python scripts/check_hub_sync.py`, and `git diff --check`.

## Review Focus

- A finite negative duration remains outside this change and must not be accidentally treated as the NaN/infinity regression case.
- An absent or boolean budget cap retains its current no-cap behavior.
- A non-finite estimate total with a finite cap must not pass the comparison.

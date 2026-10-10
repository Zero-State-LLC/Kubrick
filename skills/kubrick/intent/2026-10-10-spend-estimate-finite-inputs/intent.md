# Intent

## Problem

The spend estimate accepts `NaN` and infinite generated durations as numeric values. These can produce a non-finite total, and comparisons against a budget cap do not reliably detect that total. Unrepresentable integers can raise during float conversion, while finite inputs can overflow calculated charges. Invalid pricing, estimates, and caps must fail closed instead of bypassing the gate or crashing.

## Proposed outcome

Treat non-finite generated durations, provider rates, estimate totals, and numeric budget caps as unverifiable. Estimates with non-finite input return `NOT_COMPUTABLE`; a numeric non-finite cap or estimate total produces `BUDGET_CAP_UNVERIFIABLE`. Preserve behavior for finite values, absent caps, and boolean/non-numeric caps. Out of scope: negative finite values, pricing model changes, and provider execution.

## Affected users / systems

Operators using spend estimates or the Keyframe adapter's budget gate; plan-level spend estimate tests.

## Constraints / non-goals

Preserve the existing output shape and fail-closed authority. Do not edit the Hermes skill contract, packaging mirror, provider rates, or external-service behavior in this change.

## Open questions

None for this bounded fix.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| A `NaN` duration currently produces an `INFERRED` estimate and can evade the cap comparison. | `OBSERVED` | Reproduced during the repository audit; regression test in `scripts/test_spend_plan_numeric_guard.py`. |
| Rejecting non-finite values should preserve finite-input behavior. | `INFERRED` | Existing spend boundary tests plus explicit regression coverage. |

## Author / date

- Author: Hermes Agent
- Date: 2026-10-10

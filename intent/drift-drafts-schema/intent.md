# Intent

## Problem

Issue #92 (folded into #104): when a board or clip fails QC, the retake router
labels the cause and drafts a known-drift entry for review. #104 shipped the
router and an `AMBIGUOUS_ROUTE` draft, but the draft is only a flag: it is not
a drift entry, nothing checks it against the drift schema, and the approval
step only refuses. The remaining acceptance: a classifier output schema, drafts
that validate against the drift schema, and an approval before merge.

## Proposed outcome

- `schemas/retake-route-report.schema.json` describes `route()` output.
- Each ambiguous draft carries `drift_entry` (validates against
  `schemas/drift-registry.schema.json`) or `missing_fields`. Inputs come from
  the defect, with `model` and `observed_on` also read from the document.
  `trigger_kind` must be explicit and in the drift schema enum; it is never
  guessed from the QC label. Evidence defaults to the shot and both labels.
- `validate_drafts` returns schema errors per draft.
- `apply_drafts(..., approved_by=...)`: no approver, no write (unchanged
  behavior). With an approver and valid drafts, it returns a registry patch
  and writes it to `out` when given. It refuses to write
  `assets/drift/known_drift.yaml`; the corpus changes through a reviewed PR.

Out of scope: live Jev calls, drafts for unambiguous routes, writing the
registry, new trigger kinds.

## Affected users / systems

Retake router callers, QC reviewers, `schemas/`, hub mirror.

## Constraints / non-goals

Kubrick stays generic; fixtures use generic names. Drafts stay `PROPOSED` and
`applied: false`. No corpus write without a reviewed PR.

## Open questions

- May an agent be the `approved_by`, or only a human? The code records any
  non-blank approver; policy is the owner's call.
- Should unambiguous routes also draft drift entries? Not in this change.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| #104 already drafts `AMBIGUOUS_ROUTE` entries and refuses corpus writes | `OBSERVED` | `src/kubrick/qc/edit_route.py` at 0.27.7 |
| A complete draft entry validates against the drift schema | `OBSERVED` | `scripts/test_drift_drafts.py` |
| Existing router tests are unchanged and pass | `OBSERVED` | `scripts/test_edit_route.py` |
| Recorded Jev labels are enough to exercise the ambiguity path | `INFERRED` | fixtures use `jev_label`; no live call |

## Author / date

- Author: Errnerner Shernerner (agent assisted)
- Date: 2026-10-07

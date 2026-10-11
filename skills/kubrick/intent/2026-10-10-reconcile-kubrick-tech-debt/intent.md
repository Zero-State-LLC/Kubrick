# Intent

## Problem

The 2026-10-10 Kubrick debt audit found four bounded issues on the `origin/main` tree at `130df12`: malformed or missing `generated_seconds` rows can be silently omitted from spend estimates; `src/kubrick/corpus/propose_pattern_evolution.py` has nine mypy errors; three source files contain invalid `# noqa` directives; and Ruff reports 563 existing findings across 41 files. A passing lint ratchet only proves the baseline was not exceeded. Silently dropping invalid spend rows can produce a plausible but understated estimate.

## Proposed outcome

Make spend estimation return `NOT_COMPUTABLE` when any supplied row has a missing, boolean, non-numeric, non-finite, or unrepresentable duration. Preserve current empty-row and finite-negative behavior. Remove the nine mypy errors in the named module without changing proposal output. Remove the three invalid `# noqa` warnings. Apply only the seven verified safe Ruff fixes, tighten the lint baseline to the resulting observed counts, and reconcile the audit ledger. Carry the remaining Ruff findings with their measured count. Do not attempt a broad cleanup.

## Affected users / systems

- Kubrick maintainers and CI.
- Operators relying on Keyframe spend estimates and budget-cap checks.
- Maintainers of pattern-evolution proposals.
- The generated `skills/kubrick` packaging mirror.

## Constraints / non-goals

- Root files remain the source of truth. Generate the `skills/kubrick` mirror with `bash scripts/sync_hub_skill.sh`; do not hand-edit it.
- Keep pattern evolution proposal-only. Do not automatically apply corpus changes.
- Preserve existing spend-estimate output shape and behavior for empty rows, finite negative durations, pricing, and rounding.
- Do not use `--unsafe-fixes`, mass-reformat the repository, weaken tests, or silence mypy errors with `type: ignore` or broad `Any` casts.
- The Ruff finding is not resolved by this bounded pass. Carry the remaining measured findings for a separate plan.
- No edits to `SKILL.md`, `references/`, provider rates, workflows, or external-service behavior.
- No spend, official hub publish, Forge promotion, deploy, push, or merge.

## Open questions

- None block the bounded implementation. Human acceptance of this intent is required before code changes.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| The audited checkout and fetched `origin/main` have the same tree, `3807452e96764db88ab40d75590b0c567b8e572b`. | `OBSERVED` | `git rev-parse 'HEAD^{tree}'` and `git rev-parse 'origin/main^{tree}'` after fetching on 2026-10-10. |
| The working tree was clean before this intent draft. | `OBSERVED` | `git status --short --branch` before creating the feature branch. |
| The audit observed nine mypy errors in `src/kubrick/corpus/propose_pattern_evolution.py` and 563 Ruff findings across 41 files. | `OBSERVED` | The 2026-10-10 audit on the same tree; verify again during implementation. |
| Seven Ruff fixes are safe and two `F841` fixes require unsafe mode. | `OBSERVED` | No-cache Ruff JSON inspection on the same tree; do not apply the two unsafe fixes. |
| Rejecting malformed rows at the estimate boundary is the narrowest correction that prevents partial, understated totals. | `INFERRED` | Existing `_is_finite_number` / `_not_computable_estimate` helpers and reproduction of malformed-row undercount. |

## Author / date

- Author: Hermes Agent
- Date: 2026-10-10

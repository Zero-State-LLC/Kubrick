# Intent

Status: accepted. Danny approved this change on 2026-10-10 1:16 AM PT (fix the review threads on #148 and merge).

## Problem

A request for empty end-card space rendered a literal blank panel. A request for a plain marker with no brand text still printed barrel text. A confirmation card floated outside the phone. An action without a completed verb left hands idle. Generated handwriting came back garbled.

## Proposed outcome

Five deterministic checks live in src/kubrick/prompts/prompt_guardrails.py and run from lint_text. END_CARD_SPACE and UI_OUTSIDE_SCREEN block only with explicit evidence. Evidence means an overlay purpose is named, or the UI is presented on a device screen. The other three checks are warnings. The warnings surface on the gate result as lint_warnings and they never block. The rules are written up in docs/PROMPT-GUARDRAILS.md.

## Affected users / systems

Prompt authors, reviewers who read gate results, the pre-spend gate path, and the CI jobs that record verdicts.

## Constraints / non-goals

Fail closed only on the two blocking codes. No paid generation inside the checks. Verdicts stay recorded in CI. Out of scope: model calls and automatic prompt rewriting.

## Open questions

Should the warnings become blocking when a brief asks for it?

## Verified / assumed claims

| Claim | Label | Basis |
| --- | --- | --- |
| Empty end-card space rendered a literal blank panel | OBSERVED | Flagged output samples |
| Generated handwriting came back garbled | OBSERVED | Flagged output samples |
| The three warning codes fire on the sample prompt texts | INFERRED | Local test run |

## Author / date

Grok Bot for Danny. 2026-10-10.

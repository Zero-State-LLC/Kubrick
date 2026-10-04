# Intent

Status: accepted. Danny approved the continuity upgrade plan (written against
`9ee7723`) and told the agent to handle the whole sequence in Cursor. Merge
still needs Danny's yes. Do not spend Keyframe, ElevenLabs, or any other paid API.

## Problem

Continuity checks read prompt text. Seedance follows the start board, the
reference images, and the finished take. Provider limits, frame action,
scoped holds, and image checks are missing, so EP-01 spent credits on
failures the gates could not see.

## Proposed outcome

Ship the plan's PR order, one reviewable PR per item, each closing its
issues. Include the cinematography addendum: grammar 1.1.0 with PR 2 or 2b,
board checks with the board gate, framing fields with the framing PR, and
the 12 EP-01 cases with take-QC core.

Out of scope: merging, paid generation, official Hermes hub submit,
Continuity Forge promotion, and issue #91 (deferred).

## Affected users / systems

Hermes operators running adapt, runbook, and cues. The hub mirror, CI, and
the one SKILL.md sentence that names the Keyframe duration range.

## Constraints / non-goals

- Fail closed. Local outputs stay PROPOSED.
- Do not write into `references/` during ordinary work.
- Do not weaken an assertion to force green. Update assertions only when the
  approved plan changes the contract they pin.
- Pattern evolution stays proposal-only.
- The duration sentence in SKILL.md changes because the plan changes that
  contract. No other SKILL.md rewrite.

## Open questions

- Keyframe's Seedance node may not expose an end image. The framing PR
  records that limit instead of inventing a call. Confirm with free docs.
- Heavy detectors stay optional. CI uses fixture measurements.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| The owner approved the upgrade plan and the cinematography addendum and asked for the full PR sequence without merging. | `OBSERVED` | Task instruction |
| `carrier_for` treats a start frame as carrying every lock, durations allow 3–60 including fractions, and capabilities.yaml has no reference aspect. | `OBSERVED` | `scripts/lock_carriers.py`, `scripts/adapt_keyframe.py`, `assets/models/capabilities.yaml` at `9ee7723` |
| Seedance bills integer 4–30 second shots at 62/77/93 for 4/5/6 seconds, and rejects reference aspect outside 0.40–2.50. | `INFERRED` | Upgrade plan, EP-01 notes. Not re-measured with a live call. |

## Author / date

- Author: Daniel Meyer (approval); implementation follows that approval
- Date: 2026-10-04

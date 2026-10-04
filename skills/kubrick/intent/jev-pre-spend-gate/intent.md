# Intent

Status: implementation requested by issue #90. Merge still needs Danny's yes.

Scope: GitHub issue #90. Issues #91, #92, and #93 stay out of this change.

## Problem

`video runbook` and `video cues` can emit a credit figure and a paid operation
without asking whether the compiled prompt violates a continuity hold. The
MYSLEF v0.23 prompts omit the red-chest lock. Nothing in the spend path
blocks that before the estimate.

## Proposed outcome

- Before `runbook` or `cues` record a credit figure or a paid operation, every
  compiled prompt is judged against the plan hold list.
- A hold hit blocks the spend and reports why. The result is `NOT_COMPUTABLE`.
- If Jev is unreachable, the command fails closed. `--jev-override` (or
  `KUBRICK_JEV_OVERRIDE`) allows that case only, and the override is logged.
  The override does not bypass a hold hit.
- CI uses recorded verdicts. The MYSLEF v0.23 prompts fail. The hand-fixed
  prompts pass. The gate result is on the payload and can be appended to a
  run ledger.
- Product version stays 0.23.0.

Out of scope: calling Keyframe, ElevenLabs, or an image provider; retrieval
dramatic fit (#91); retake drift classification (#92); hold-list QC on
finished frames (#93); rewriting `references/`; publishing the skill.

## Affected users / systems

Hermes operators running `video runbook` and `video cues`. The hub mirror,
the skill contract sentence that names `--jev-override`, and CI.

## Constraints / non-goals

- Root is the source of truth. `skills/kubrick/` is the packaging mirror.
- Do not weaken an existing assertion to force a green run.
- Do not write into `references/` during this work.
- Do not bump the product version.
- Kubrick still does not call a provider. The gate judges prompts; it does
  not spend.
- Danny's yes is still required to merge.

## Open questions

- No in-repo Jev endpoint exists. The live contract is the POST shape this
  change sends (`prompt`, `holds`) and the object it accepts (`verdict`,
  `findings`). Production `KUBRICK_JEV_URL` is an operator setting.
- Image-only stills outside `runbook` are not a spend command in this repo.
  They stay ungated here.
- Prop-state holds are `in_scope_only`. A live judge decides whether a prompt
  leaks them. Recorded tests do not re-derive that judgment.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| Issue #90 asks for a pre-spend hold check, fail-closed when Jev is down, a logged override, recorded MYSLEF verdicts, and a ledger entry. | `OBSERVED` | GitHub issue #90 |
| The repo has no separate hold-list file and no Jev client. Plan locks, location locks, and prop states are the hold texts. | `OBSERVED` | `examples/myslef-minder/storyboard-plan.yaml`, scripts search |
| `runbook` and `cues` are the commands that emit paid operations and credit figures. Adapt and image generate compile prompts and do not spend. | `OBSERVED` | `scripts/video_runbook.py`, `scripts/video_cues.py` |
| A live Jev service answers `POST {prompt, holds}` with `{verdict, findings}`. | `INFERRED` | no service is named in this repo or the org search |

## Author / date

- Author: Daniel Meyer
- Date: 2026-10-04

# Intent

Status: accepted. Danny approved the build, the PR, and merge on green at
01:49 PT on 2026-10-04.

Scope: recommendation 1 of `Research 2026-10-04 Identity and Start Frames`
(live board check before video spend), plus the cheap cut-type rules from
recommendation 2.

## Problem

The board gate scores fixture measurements and never looks at a board. The
video model copies the start image, so a wrong board becomes a wrong take.
EP-01 lost 124 cr to a board with human hands on a silicon-hand lock and
140 cr fixing head drift by hand.

## Proposed outcome

- Before `video runbook` writes a credit figure or a paid operation, every
  paid shot's local board image is checked against the approved `ref_pack`
  identity views (DINOv2 similarity, configurable threshold, default 0.70)
  and the character lock list (yes-or-no questions through a pluggable,
  local judge).
- On by default. A failure or a check that cannot run blocks spend with a
  clear code and points to regenerating the board. `--board-image-opt-out
  REASON` skips the checks and logs the reason.
- Hard cuts may not reuse an earlier board. A board that hides the identity
  may not open a shot that reveals it.
- Product version 0.25.0.

Out of scope: segmentation models (SAM2), calibration on EP-01 frames, live
take QC, `lock_carriers` changes, and any provider or paid API call.

## Affected users / systems

Hermes operators running `video runbook`, the hub mirror, CI, and the skill
contract sentence for `runbook`.

## Constraints / non-goals

- Free and local only. No paid API calls, including in tests.
- Heavy model packages are an optional extra and are never imported at
  module load. CI uses fixture PNGs and a mocked model.
- Fail closed, like `JEV_UNREACHABLE`.
- Root is the source of truth. `skills/kubrick/` is regenerated.

## Open questions

- The real DINOv2 threshold that separates kept from rejected MYSLEF takes.
- Accuracy of a small local vision-language model on MYSLEF lock questions.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| The video model copies the start board | `OBSERVED` | EP-01 tracker, 124 cr human-hands copy |
| 0.70 separates good and bad boards | `NOT_COMPUTABLE` | Uncalibrated; needs EP-01 kept and rejected takes |
| DINOv2 suits a non-human head better than face ID | `INFERRED` | Research note, VBench and Phantom use DINO features |

## Author / date

- Author: Grok Bot for Errnerner Shernerner, approved by Danny
- Date: 2026-10-04

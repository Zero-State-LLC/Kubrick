# Intent: hold-list QC on generated frames (#93)

## Problem

Checking boards and takes against the hold list is manual. The prompt gate
cannot see model drift: EP-01 takes 07 (back lights) and 12 (lens glow) failed
holds that their prompts satisfied.

## Proposed outcome

`kubrick.qc.hold_vision` asks a vision judge each hold (one yes-or-no question
with an expected answer) on each sampled frame and writes a PROPOSED per-hold
table: `pass`, `fail`, `borderline` (frames disagree) or `unverified` (no
usable answer, fail closed). Its `vlm` block is a `take_qc` verdict: a failed
hold is a `VLM_HOLD_FAIL` defect, an unverified hold makes the take
`not_computable`.

A hold may name a `judge`. `--judge NAME=answers:PATH` or
`--judge NAME=vlm:URL[@MODEL]` sends those holds to another judge, so a cheap
model answers easy holds and a stronger one answers the hard ones. A hold
whose judge is not routed is unverified.

## Affected users / systems

Take and board QC, `take_qc` (consumes the `vlm` block), the board calibration
tools (`tools/board_calibration/hold_vision_eval.py`), and the EP-01 fixtures.

## Constraints / non-goals

- Kubrick holds no key and calls no remote host. Judges are loopback only; a
  paid model is reached through a loopback adapter that enforces its own budget.
- Generic: holds, questions and routes are data. MYSLEF is test data only.
- The judge sees pixels (vision model), not a text description, so the
  text-only caveat in #93 does not apply.

## Acceptance

On the EP-01 restart takes (shots 01 07 09 10 11 12, mid and end frames), the
judged hold verdicts match the labelled verdicts within one item per shot.
CI replays recorded answers offline (no credits).

## Evidence

Live calibration on 2026-10-07 PT (276 calls per model, 77 images, 5 holds).
Hold acceptance, worst shot mismatches (sum over takes):

| Judge | Worst shot | Accept |
|---|---|---|
| qwen3.7-flash | 4 | no |
| qwen3.5-flash | 2 | no |
| gemini-2.5-flash | 3 | no |
| nova-lite | 6 | no |
| qwen3.5-flash, with light, glow and hands holds routed to gemini-2.5-flash | 1 | yes |

The routing was chosen after seeing this set, so the result is optimistic;
a held-out episode should confirm it.

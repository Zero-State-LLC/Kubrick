# Intent

Status: accepted by Danny (repo owner) on 2026-10-02.

Scope: GitHub issues #25, #26, #27, #28, #29, #30, and #31.

## Problem

Keyframe multi-shot clips absorb beats at or under two seconds, and a chained
shot cannot carry both a start image and reference images. A chained start
frame also needs a hold before the cut, or the join reads as a jump. Prop
state, wardrobe, and character-lock text can contradict the frames around
them, including brief residue that leaks onto shots from before it is
introduced. Nothing in the prep path names those conflicts before spend, and
there is no versioned technique library an author can opt into.

## Proposed outcome

- Product version 0.19.0 is the same on every surface the release audit
  checks. The production envelope schema id stays `0.16.0`. The installer
  receipt schema id stays `1.0.0`.
- Short beats, joins, start-frame holds, prop locks, reference-lock lint,
  wardrobe locks, and technique suggestions are computed before a provider
  call. New storyboard and brief fields are optional.
- Warnings share `{code, shot, message, recommendation}` and are stored on
  the compile receipt and the adapter output.
- A technique match is a suggestion. The prompt changes only when the frame
  lists that technique in `apply_techniques`.
- The MYSLEF shots 03–06 fixture shows the warnings, the cut list, and the
  dropped references. Keyframe still refuses a shot outside 3–60 seconds.

Out of scope: calling Keyframe, ElevenLabs, or OpenRouter; rewriting
`references/`; publishing the skill; changing the envelope schema id.

## Affected users / systems

Hermes operators running `compile` and `video adapt`. The Keyframe and
generic adapters, storyboard propagation, provider capability data, the
release audit, and the hub mirror.

## Constraints / non-goals

- Root is the source of truth. `skills/kubrick/` is the packaging mirror.
- Do not weaken an existing assertion or test to force a green run.
- Do not write into `references/` during this work.
- Do not commit or push.
- Do not clamp or drop a shot to satisfy a provider limit.
- Danny accepted this intent on 2026-10-02.

## Open questions

None. The short-beat threshold, the Keyframe hold, the exclusivity rule, and
the proposal-only technique rule are decided in the issue texts.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| Keyframe shots must be 3–60 seconds inclusive. A multi-shot movie is one clip. | `OBSERVED` | `scripts/provider_capabilities.py`, `scripts/adapt_keyframe.py` |
| Issues #25–#31 name the prep gaps above. Danny accepted the work on 2026-10-02. | `OBSERVED` | issue notes and this intent |
| MYSLEF script shots 03–06 are 2s, 1s, 2s, and 1s, with chains and a chair state path. | `OBSERVED` | MYSLEF shot map and the derived fixture |

## Author / date

- Author: implementation on branch `fix/issues-25-31`
- Date: 2026-10-02

# Intent

Status: accepted by Danny (repo owner) on 2026-10-02.

Scope: GitHub issues #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, and #44.

Phase A is #33–#38. Phase B (#39–#44) is implemented on the same branch in this release. Version stays 0.20.0.

## Problem

A character reference on a two-person shot can bleed onto the other person, and nothing in the prompt says which subject the image defines. Location references can contradict a room lock or a count, and an empty shot still inherits wardrobe and identity lines. Critical locks that exist only as negatives do not hold on Keyframe, which has no negative field. The cut list does not choose separate generations versus one multi-shot clip, does not reuse takes, and does not ask the operator to accept a script-clock gap. A retake can move a prop while an older downstream take still starts from the previous state. A chained Keyframe shot can be billed from a start image that was never grabbed or checked.

## Proposed outcome

- Product version 0.20.0 is the same on every surface the release audit checks. The production envelope schema id stays `0.16.0`. The installer receipt schema id stays `1.0.0`.
- Phase A warnings use `{code, shot, character, message, recommendation}`. New brief and storyboard fields are optional. Existing inputs stay valid.
- #33: `applies_to` scopes a character reference. An unscoped reference on a two-person frame warns `REFERENCE_BLEED_RISK`. A reference scoped to exactly one on-screen id adds one binding line.
- #34: `location` references are linted against location locks and `counts`. Counts compile to `exactly N name` lines. `cast: []` compiles to `nobody is in frame` and drops wardrobe and identity lines for that frame.
- #35: Each identity, wardrobe, prop, and light lock gets a carrier: `start_frame`, `reference`, `prompt_positive`, or `prompt_negative_only`. A critical lock whose carrier is `prompt_negative_only` warns `NEGATIVE_ONLY_LOCK`. Provider data gains `negative_prompt_effective` (false for keyframe).
- #36: `video --action retime` emits a PROPOSED generation plan, edit plan, and script-versus-final clock. It does not call a provider. A non-zero delta without `accept_clock_delta` is `CLOCK_DELTA_UNACCEPTED`.
- #37: `storyboard --action impact` reads `takes.yaml` as OBSERVATION. It replays declared prop states and warns `STALE_TAKE`. It does not write observations back onto the storyboard.
- #38: A chained Keyframe shot without `start_frame.asset` warns `START_FRAME_MISSING` and includes an ffmpeg handoff string. Kubrick does not run ffmpeg. `verified: false` with an asset warns `START_FRAME_UNVERIFIED`.
- `--strict` exits non-zero for `REFERENCE_LOCK_CONTRADICTION`, `LOCATION_REFERENCE_CONTRADICTION`, and `START_FRAME_MISSING` after the artifact is written. The other new codes stay warnings.
- #39: Drift entries live in `assets/drift/known_drift.yaml`. An entry applies only when `model` equals the document `model` or the provider default. `plain_top_motion` delegates to the #30 warning. Other triggers use character count, attached references, location references, `chain_from`, and the short-beat threshold. Age is `(as_of - observed_on).days > max_age` (default 180). One `DRIFT_ENTRY_STALE` warning is emitted per stale entry. Tests inject `as_of`.
- #40: The estimate is labelled INFERRED and uses generated seconds. A retime `clip_id` counts once. `image_rate` is not added. The cap fails closed only when a computable total is strictly greater than `budget_cap_credits`. Missing pricing is `NOT_COMPUTABLE` with a null total, never 0.
- #41: `multi_shot_prompt` is emitted only for `is_multi_shot_single_clip`. Continuity repeats planner wardrobe, prop, and asymmetry lines once, then identity clauses that are not already there. `SHOT_COUNT_HIGH` fires above 5 shots.
- #42: The overlay writes only keys that already exist on the provider. Vendor claims apply first, then observed values. An `input_mode` block applies only when that mode is requested. `max_references` and `native_audio` stay on the block. `negative_prompt_effective` is the #35 field. `CAPABILITY_STALE` uses the same age rule as drift, with `capability_max_age_days`.
- #43: A speech line belongs to a character when it starts with `{id}:` or is a `{character, line}` mapping. Words are the tokens after that prefix. `DIALOGUE_TOO_LONG` fires above 2.5 words per planned second. `speaks: false` plus an attributed line, and a `library_id` or `name` that casefold-matches `never_clone_of`, fail closed.
- #44: Figure-right is viewer-left. The asymmetry line is added once per on-screen feature. Empty cast drops it. `SCREEN_DIRECTION_FLIP` compares adjacent left/right sides and is silent when the later frame has boolean `axis_change: true`. `mirrored` counts only as boolean true.

Out of scope: calling Keyframe, ElevenLabs, or OpenRouter; running ffmpeg or a frame grab; rewriting `references/`; publishing the skill; changing the envelope schema id or the installer receipt schema id.

## Affected users / systems

Hermes operators running `compile`, `video adapt`, `video retime`, and `storyboard impact`. The Keyframe and generic adapters, storyboard propagation, provider capability data, the release audit, and the hub mirror.

## Constraints / non-goals

- Root is the source of truth. `skills/kubrick/` is the packaging mirror.
- Do not weaken an existing assertion or test to force a green run.
- Do not write into `references/` during this work.
- Do not commit or push.
- Do not grow `scripts/shot_plan.py` or `scripts/continuity_locks.py` past 499 lines. New prep logic lives in new modules.
- `scope` without `applies_to` does not count as scoped. `applies_to` must name exactly one id who is on screen.
- A count line uses the words zero through ten, otherwise digits. Names gain a trailing `s` when the count is not 1, unless the name already ends in `s`.
- A per-frame `counts` entry replaces the document count for that key only.
- Carrier precedence is start frame (a chain or a `start_frame` object), then a scoped reference that does not declare the negated feature, then a positive line, then negative only. A reference carries a light or prop lock only when a declare equals the lock id or the lock's positive text.
- Character locks keep the #16 positive restatement, so they are not `prompt_negative_only`.
- `cast` is consulted only when the frame has that key. `characters: []` alone does not drop identity lines.
- People on screen are `cast` when that key is present, otherwise `characters`.
- A character reference is attached when its path or media id is listed in `reference_images`, or when the frame lists no reference images and the owning character is on screen.
- Retime: a shot is its own generation when it is chained, reused, the provider is not `multi_shot`, or the provider is a multi-shot single clip and the beat is at or below the short-beat threshold. Two or more remaining contiguous beats share one clip. Reuse requires trim out minus in to cover the planned duration. `final_clock` sums new generations and counts each shared clip once. Reused shots add 0. Missing duration uses 4.0 seconds.
- Impact compares a downstream take's `observed_start_state` (else the declared storyboard start) to the retake's `observed_end_state`. Equal text, or the same resolved state id, is a match. A token that starts with a state id plus a space resolves to that id. `prop_assignments` errors fail closed and do not guess.
- Start-frame grab time is `start_frame.at_seconds`, else the join `at_seconds`, else 0. The ffmpeg `-ss` value is not the join `atSeconds` already stored on `startImage`. `verified` counts only when it is boolean true. A missing asset does not also warn `START_FRAME_UNVERIFIED`.
- `accept_clock_delta` is read from the plan file or the retime flag. It is not copied onto the propagated storyboard.
- Danny accepted this intent on 2026-10-02. Phase A and phase B are both in v0.20.0.

## Open questions

None. The rules above are the deterministic choices where an issue left a detail open.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| Issues #33–#38 name the prep gaps above. Danny accepted #33–#44 on 2026-10-02. | `OBSERVED` | issue notes and this intent |
| Keyframe has no negative prompt field. Flux, SD3, Midjourney, generic, and Grok Imagine do. | `OBSERVED` | `scripts/adapt_keyframe.py`, `scripts/adapt_provider.py` |
| Envelope schema id `0.16.0` and installer receipt schema id `1.0.0` do not track the product version. | `OBSERVED` | `scripts/version_surfaces.py` |
| MYSLEF script shots 03–06 are the example under `examples/myslef-minder/`. | `OBSERVED` | v0.19 release notes and the derived fixture |

## Author / date

- Author: implementation on branch `feat/upgrades-33-44`
- Date: 2026-10-02

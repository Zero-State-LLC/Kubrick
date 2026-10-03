# Intent

Status: accepted by Danny (repo owner) on 2026-10-02.

Scope: GitHub issues #39, #40, #41, #42, #43, and #44. Product version 0.21.0.

Phase A (#33–#38) already shipped as v0.20.0. This release is phase B only.

## Problem

Known model drift from the MYSLEF run lived in notes, except one inline wardrobe warning. Prep said nothing about credit cost. A multi-shot clip had no labelled shot structure. Capability numbers were provider-wide, with no source or check date. Voice and audio locks lived only in the continuity bible. Asymmetric features and screen direction could flip with no warning.

## Proposed outcome

- Product version 0.21.0 is the same on every surface the release audit checks. The production envelope schema id stays `0.16.0`. The installer receipt schema id stays `1.0.0`.
- #39: Drift entries live in `assets/drift/known_drift.yaml`. An entry applies only when `model` equals the document `model` or the provider default. `plain_top_motion` delegates to the #30 warning. Other triggers use character count, attached references, location references, `chain_from`, and the short-beat threshold. Age is `(as_of - observed_on).days > max_age` (default 180). One `DRIFT_ENTRY_STALE` warning is emitted per stale entry. Tests inject `as_of`.
- #40: The estimate is labelled INFERRED and uses generated seconds. A retime `clip_id` counts once. `image_rate` is not added. The cap fails closed only when a computable total is strictly greater than `budget_cap_credits`. Missing pricing is `NOT_COMPUTABLE` with a null total, never 0. The checklist is the two retry-guard strings. No provider is called.
- #41: `multi_shot_prompt` is emitted only for `is_multi_shot_single_clip`. Continuity repeats planner wardrobe, prop, and asymmetry lines once, then identity clauses that are not already there. `SHOT_COUNT_HIGH` fires above 5 shots.
- #42: The overlay writes only keys that already exist on the provider. Vendor claims apply first, then observed values. An `input_mode` block applies only when that mode is requested. `max_references` and `native_audio` stay on the block. `negative_prompt_effective` is the #35 field. `CAPABILITY_STALE` uses the same age rule as drift, with `capability_max_age_days`. Keyframe with no model argument returns the phase A values, including the 1.6s hold.
- #43: A speech line belongs to a character when it starts with `{id}:` or is a `{character, line}` mapping. Words are the tokens after that prefix. `DIALOGUE_TOO_LONG` fires above 2.5 words per planned second. `speaks: false` plus an attributed line, and a `library_id` or `name` that casefold-matches `never_clone_of`, fail closed.
- #44: Figure-right is viewer-left. The asymmetry line is added once per on-screen feature. Empty cast drops it. `SCREEN_DIRECTION_FLIP` compares adjacent left/right sides and is silent when the later frame has boolean `axis_change: true`. `mirrored` counts only as boolean true.

Out of scope: calling Keyframe, ElevenLabs, or OpenRouter; running ffmpeg or a frame grab; rewriting `references/`; publishing the skill; changing the envelope schema id or the installer receipt schema id; editing `scripts/retime_plan.py` or `scripts/test_retime_plan.py`.

## Affected users / systems

Hermes operators running `compile` and `video adapt`. The Keyframe and generic adapters, provider capability data, the release audit, and the hub mirror.

## Constraints / non-goals

- Root is the source of truth. `skills/kubrick/` is the packaging mirror.
- Do not weaken an existing assertion or test to force a green run.
- Do not write into `references/` during this work.
- Do not commit or push.
- Do not grow a touched Python module past 499 lines. New prep logic stays in the phase B modules.
- v0.20 docs describe only #33–#38 as shipped. Phase B release text lives in the v0.21 changelog, release notes, roadmap, and checklist.
- Danny accepted this intent on 2026-10-02. The release version is 0.21.0.

## Open questions

None. The rules above are the deterministic choices where an issue left a detail open.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| Issues #39–#44 name the prep gaps above. Danny accepted them on 2026-10-02. | `OBSERVED` | issue notes and this intent |
| #33–#38 shipped as v0.20.0 on main `79567bc`. | `OBSERVED` | git history and the v0.20 release docs |
| Envelope schema id `0.16.0` and installer receipt schema id `1.0.0` do not track the product version. | `OBSERVED` | `scripts/version_surfaces.py` |
| MYSLEF script shots 03–06 are the example under `examples/myslef-minder/`. | `OBSERVED` | v0.20 release notes and the derived fixture |

## Author / date

- Author: implementation on branch `feat/upgrades-39-44`
- Date: 2026-10-02

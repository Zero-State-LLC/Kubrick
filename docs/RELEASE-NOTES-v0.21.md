# Kubrick v0.21.0 Release Notes

v0.21.0 adds a dated drift registry, an inferred spend estimate, multi-shot
prompt blocks, model capability overlays, voice locks, and screen-direction
locks. The production envelope schema id stays `0.16.0`. Issues #33–#38
shipped in v0.20.0.

## Added

- #39: Known drift is `assets/drift/known_drift.yaml`, checked against
  `schemas/drift-registry.schema.json`. An invalid file fails closed. The #30
  plain-top motion warning is unchanged. Each seeded entry matches from shot
  facts. An `observed_on` older than 180 days warns `DRIFT_ENTRY_STALE`. The
  age comparison uses an injected date in tests.
- #40: Keyframe pricing is INFERRED provider data: 15.5 credits per second at
  480p, observed 2026-10-02. The estimate uses generated seconds. A shared
  retime `clip_id` is counted once. `image_rate` (7) is stored and is not
  added. `budget_cap_credits` fails closed with `BUDGET_CAP_EXCEEDED` when the
  estimate is above the cap. A provider with no pricing returns
  `NOT_COMPUTABLE`, not 0. The checklist is string-only. No API call.
- #41: `is_multi_shot_single_clip` output includes `multi_shot_prompt`: shot
  count, generated seconds, aspect, lighting, labelled shot blocks, one
  continuity block, and `Ending state:`. More than 5 shots warns
  `SHOT_COUNT_HIGH`. Generic output omits the field. Preservation is unchanged.
- #42: `provider_capabilities(provider, model=None)` merges `models[model]`
  over the provider defaults. `source` is `observed` or `vendor_claim`.
  Observed wins. A stale `verified_on` warns `CAPABILITY_STALE`. Missing
  `source` fails validation. Keyframe with no model argument returns the phase
  A values, including hold 1.6. `negative_prompt_effective` is the #35 field.
- #43: `audio_strategy: external` or `muted_native` appends "native audio is a
  guide track only" to Keyframe `audio.sound`. `speaks: false` plus a line for
  that character, or a `library_id` / voice `name` that casefold-matches
  `never_clone_of`, fails closed with `VOICE_LOCK_VIOLATION`. A line is that
  character's when it starts with `{id}:` or is `{character, line}`. Above 2.5
  words per planned second warns `DIALOGUE_TOO_LONG`.
- #44: `asymmetry` compiles "feature on the figure's side (viewer's side);
  never swap sides". Figure-right is viewer-left. The line is added once for
  each on-screen character. Empty cast drops it. A left/right change on the
  next frame warns `SCREEN_DIRECTION_FLIP` unless that frame has
  `axis_change: true`. `mirrored: true` warns that sides in the image are
  inverted. The string `"true"` does not.

## Example

Generic compile of `examples/myslef-minder/` shows the asymmetry line once on
every prompt where myslef is on screen (shots 03, 04, and 05): `cracked optic
on the figure's right (viewer's left); never swap sides`. Shot 06 says
`nobody is in frame` and does not carry the line. The run exits 0.

```bash
python3 scripts/kubrick.py compile \
  --brief examples/myslef-minder/brief.yaml \
  --mode storyboard \
  --storyboard-plan examples/myslef-minder/storyboard-plan.yaml \
  --provider generic \
  --out /tmp/myslef-minder-generic
```

Keyframe adapt of the same plan exits 0. Status stays `PROPOSED`. The plan
sets `audio_strategy: muted_native` and `budget_cap_credits: 400`.

The spend estimate is labelled INFERRED: four shots at 3 generated seconds,
46.5 credits each, 186 total, at 15.5 credits per second and 480p.
`execution_checklist` is:

- `on -32602 or 'Job not found', check get_movie includeCredits before any retry`
- `wait on processingJobId, not generationJobIds`

`multi_shot_prompt` starts `4 shots, 12s generated, aspect 9:16` and has
`Shot 1 (3s):` through `Shot 4 (3s):`. Continuity is one block. Lock lines in
that block are not repeated. The ending state begins `Ending state: the minder
walks out of frame right`.

`KNOWN_DRIFT` on this plan:

- `plain-top-motion-logo` on frame-002, with the #30 text (plain top + motion)
- `no-ref-head-red-light` on frame-002 and frame-003
- `char-ref-bleed-two-person` on frame-001
- `location-ref-overrides-prompt` on frame-001
- `start-frame-hold` on frame-002 and frame-004
- `multi-shot-merges-short-beats` on frame-001 through frame-004

Voice locks pass. myslef has `speaks: false` and no speech line. The minder's
line is `minder: Wha—` on the 1.0s beat, with `library_id`
`ibrahim-talkative-friend` and `never_clone_of: [danny]`. Every shot's
`audio.sound` says native audio is a guide track. A cap below 186 exits
non-zero with `BUDGET_CAP_EXCEEDED`.

```bash
python3 scripts/kubrick.py video --action adapt \
  --provider keyframe \
  --input examples/myslef-minder/storyboard-plan.yaml \
  --output /tmp/myslef-minder-keyframe.yaml
```

## Notes

- The installer receipt schema id stays `1.0.0`.
- No Keyframe, ElevenLabs, or OpenRouter call is required for this prep.

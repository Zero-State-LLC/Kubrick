# Kubrick v0.19.0 Release Notes

v0.19.0 adds shot prep before a provider call: short beats, joins, start-frame
holds, prop and wardrobe locks, reference-lock lint, and a proposal-only
technique library. The production envelope schema id stays `0.16.0`.

## Added

- #25: Keyframe is flagged `is_multi_shot_single_clip`. Each shot at or below
  the short-beat threshold (default 2.0 seconds, overridable with
  `short_beat_threshold_seconds`) warns with the shot id, the duration, and a
  recommendation to generate that shot as its own clip at the provider minimum,
  then trim. Shots under that minimum are generated at the minimum and trimmed.
  The warning is on the compile receipt and the adapter output.
- #26: A frame may set `join` to `cut` or `{chain_from, at_seconds}`. On
  Keyframe a chained shot gets `startImage` and drops `referenceImages`,
  because Seedance 2.5 treats those inputs as mutually exclusive. The rule
  lives in provider capabilities (`exclusive_inputs`). Non-adjacent chains are
  allowed. An unknown, same-frame, or later `chain_from` fails closed.
- #27: Generated duration is the planned duration plus any start-frame hold,
  raised to the provider minimum. Keyframe `start_frame_hold_seconds` is 1.6
  on a chained shot that does not open on an exit, so a #26 chain has a
  readable start frame. The cut list trims the excess (after the hold for a
  padded chain, otherwise from the tail) so used runtime stays the planned
  sum. `targetDurationSeconds` is what Keyframe renders. `plannedDurationSeconds`
  is the planned sum. An exit (`opens_with: exit`, or a leading "walks out" /
  "exits" / "leaves frame") is not held. Only a generated duration past the
  provider maximum fails closed.
- #28: A storyboard may register `props` with ordered states. Frames declare
  `prop_states`. Each shot prompt gets a positive prop lock, and that lock
  replaces carried-over prior-state lines for the same prop. A start state
  must continue the previous end state, and an unreachable jump fails closed.
  Brief end-state residue applies only from the frame whose `residue_add`
  introduces it.
- #29: An author-supplied character `references` list can declare visible
  features. A character-lock negative that names a declared feature warns
  before spend. That warning sets `shot` to null and records the character id
  in `character`. `--strict` exits non-zero after the adapter output is written.
- #30: Per-character `wardrobe`, overridable on the frame, compiles to
  `WARDROBE LOCK` lines. Keyframe warns when a plain top with no logo is paired
  with a significant motion verb.
- #31: `assets/techniques/techniques.yaml` is a versioned, schema-checked
  library. Matches are suggestions. A prompt changes only when the frame sets
  `apply_techniques`.

## Example

Generic compile shows the locks and the reference warning. It exits 0 without
`--strict` and non-zero with `--strict`.

```bash
python3 scripts/kubrick.py compile \
  --brief examples/myslef-minder/brief.yaml \
  --mode storyboard \
  --storyboard-plan examples/myslef-minder/storyboard-plan.yaml \
  --provider generic \
  --out /tmp/myslef-minder-generic
```

Keyframe adapt of the same plan exits 0. The brief and the storyboard are
9:16, and both the generic `generation_parameters.aspect_ratio` and the
Keyframe `aspectRatio` say 9:16. Script shots 03–06 are 2.0, 1.0, 2.0, and
1.0 seconds. Each generated shot is at least 3 seconds. The cut list trims
back to the planned 6 seconds: a chained 1.0 second shot is generated for 3.0
seconds and used from 1.6 to 2.6, and the exit shot is generated for 3.0
seconds and used from 0.0 to 1.0. `targetDurationSeconds` is the rendered
total. `plannedDurationSeconds` is the planned total. The artifact carries
`prep_warnings`, `technique_suggestions`, `cut_list`, and `dropped_references`
under `result.adapted_packet`. Chained shots carry `startImage` and omit
`referenceImages`. A frame that declares the chair drops the carried-over
prior chair line, so the chair lock is the only chair state in that prompt.

```bash
python3 scripts/kubrick.py video --action adapt \
  --provider keyframe \
  --input examples/myslef-minder/storyboard-plan.yaml \
  --output /tmp/myslef-minder-keyframe.yaml
```

## Notes

- The installer receipt schema id stays `1.0.0`.
- No Keyframe, ElevenLabs, or OpenRouter call is required for this prep.

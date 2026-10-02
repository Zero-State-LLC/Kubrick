# Intent

Status: accepted by Danny (repo owner) on 2026-10-02.

Scope: GitHub issues #16, #17, #18, #19, #20, #21, #22, and #23.

## Problem

The 2026-10-02 MYSLEF Kubrick-to-Keyframe run showed provider prompts that
were not shot-specific, pasted negatives into positive text, repeated clauses,
and rendered `motif ownershi` plus raw `observed_N` ids and `None`. Brief
validation rejected the noun `chair` when it appeared in two layers. `compile`
imports `jsonschema` without declaring it. An installed 0.17.0 skill failed
smoke because `kubrick.manifest.yaml` was still `0.16.0` while `VERSION` was
`0.17.0`. There is no Keyframe `create_movie` adapter, and character-lock
negatives such as `no nose` are not restated as positive identity constraints.

## Proposed outcome

- Product version 0.18.0 is the same on every surface that tracks the release.
  One audit covers those surfaces, including the `skills/kubrick` mirror when
  it is present, and both installers run that audit before activation.
- The production-envelope schema id stays `0.16.0`. It does not track the
  product version. The installer receipt schema id stays `1.0.0`.
- `PyYAML` and `jsonschema` are runtime dependencies. `compile` exits 3 with
  an install command when `jsonschema` cannot be imported.
- The same noun may appear in more than one brief layer. A verbatim multi-word
  phrase copied across layers still fails, and the error names the phrase and
  both layers.
- Per-shot prompts come from each storyboard frame's state. Observed ids render
  as evidence text. Blank and `None` values are omitted. Clauses are
  de-duplicated in order. General negatives stay in the negative field.
  Character-lock negatives are also restated as positive constraints.
- `motif ownership` is the ownership label. The truncated form `ownershi ` is
  not emitted.
- A `keyframe` provider emits the Keyframe `create_movie` shape. Each shot is
  3–60 seconds inclusive. 10 seconds is valid. Shorter than 3 or longer than
  60 fails closed. `targetDurationSeconds` is the sum of the shot durations.
  Speech is omitted when the shot has no dialogue. Grok Imagine stays capped
  at 8 seconds.

Out of scope: rewriting `references/`, changing golden envelope fixtures,
raising the Grok Imagine duration cap, and publishing the skill.

## Affected users / systems

Hermes operators running `compile`, `video shot`, and `video adapt`. Provider
adapters, the manifest, installers, release audit, hub mirror, and CI.

## Constraints / non-goals

- Root is the source of truth. `skills/kubrick/` is the packaging mirror.
- Do not weaken an existing assertion or test to force a green run.
- Do not write into `references/` during this work.
- Do not commit or push.
- Fail closed on Keyframe durations outside 3–60 seconds. Do not clamp or drop
  the shot.
- Character-lock rephrasing is only for the fixed feature lexicon. General
  negatives, including `geometry reset` and `no named esoterica`, stay out of
  positive prompt text.
- Danny accepted this intent on 2026-10-02, including the `SKILL.md` provider
  list and the compile dependency lines these issues require.

## Open questions

None. The duration floor, the envelope schema id, and the noun-versus-phrase
rule are decided in the constraints above.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| Smoke can fail with `manifest version '0.16.0' does not match VERSION '0.17.0'`. `validate_manifest.py` emits that string. Repo HEAD is 0.17.1 and internally consistent. | `OBSERVED` | `scripts/validate_manifest.py`; user report of the installed 0.17.0 skill |
| `audit_release_version.py` checks the root tree only. `install.sh` does not run it. Hub sync byte-compares trees and does not invent a version equality the source itself lacked. | `OBSERVED` | `scripts/audit_release_version.py`, `install.sh`, `scripts/check_hub_sync.py` |
| Production envelopes use schema_version `0.16.0`. Goldens and tests pin that id. | `OBSERVED` | `scripts/production_engine.py`, `evals/golden/v016/` |
| `pyproject.toml` `dependencies` is empty. `compile` aborts when PyYAML is missing and `validate_artifact.py` raises `SystemExit` when jsonschema is missing. | `OBSERVED` | `pyproject.toml`, `scripts/kubrick_compile.py`, `scripts/validate_artifact.py` |
| Layer checks tokenize each layer and reject any shared token other than a small stop list. That rejects `chair` in two layers. | `OBSERVED` | `scripts/build_motif_graph.py` |
| Adapter prompts label fields with `field[:-1]`, so `motif_ownership` becomes `motif ownershi`. The same strip is in `compare_visual_observation.py`. | `OBSERVED` | both scripts |
| `video_shot` builds one brief-level shot. `base_frame` appends `negative_constraints` onto the positive prompt. The MYSLEF generic shots were identical and contained those negatives and a repeated clause. | `OBSERVED` | `scripts/surface_compilers.py`, `scripts/adapt_provider.py`, MYSLEF `kubrick-out/` |
| No provider id `keyframe` is registered. Grok Imagine `max_duration_seconds` is 8. | `OBSERVED` | `scripts/provider_capabilities.py`, `kubrick.manifest.yaml` |
| Keyframe `create_movie` uses `title`, `brief`, `aspectRatio`, `targetDurationSeconds`, `qualityPreset`, `style`, `shots[]` with `scene`, `title`, `imagePrompt`, `videoPrompt`, `durationSeconds`, and `audio.sound`. Speech is absent when the character does not speak. | `OBSERVED` | `keyframe-create_movie.json` in the MYSLEF deliverable |
| A 2 second shot in that sample is below the 3 second floor this issue now requires. | `OBSERVED` | issue #22 and the sample payload |

## Author / date

- Author: Grok, implementing the work Danny accepted
- Date: 2026-10-02

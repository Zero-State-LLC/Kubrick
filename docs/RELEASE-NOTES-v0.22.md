# Kubrick v0.22.0 Release Notes

v0.22.0 delivers the ranked audit upgrades #61–#72. The platform half hardens
CI, artifacts, dependencies, the MCP surface, capability caps, and lint debt.
The production half adds sequence adapt, take selection, and retake, cut, and
audio prep. The production envelope schema id stays `0.16.0`. The installer
receipt schema id stays `1.0.0`. No provider is called.

## Platform (#61, #62, #65, #66, #67, #68, #72)

- #61: CI runs `pytest -q scripts tests tests_audit`, every script test, and
  the evals under subprocess-aware coverage with a 75% floor over `scripts/`.
  A step fails when the tree is dirty afterwards. `Pygments` is pinned at the
  2.20+ floor and `coverage` is in `requirements-ci.txt`.
- #62: Retrieval cache and receipts go to
  `$KUBRICK_PROJECT_DIR/out/kubrick/retrieval/` (default `./out/kubrick/`).
  An unwritable target fails closed with `ARTIFACT_DIR_UNWRITABLE`.
  NOT_COMPUTABLE exits 4 in retrieve, operate, and govern.
- #65: The manifest `action_requirements` table names the actions that import
  PyYAML or jsonschema at module level. Dispatch stops with
  `DEPENDENCY_MISSING` (exit 4) before spawning. `do check --action deps`
  reports readiness. A test keeps the table equal to the imports.
- #66: The MCP server caps request size, resolves the action from the
  manifest and checks its dependencies before spawning, and times out each
  call with `MCP_TIMEOUT`. A protocol harness covers these paths.
- #67: Keyframe adapt fails closed with `REFERENCE_CAP_EXCEEDED` above the
  model `max_references`, warns `NATIVE_AUDIO_UNSUPPORTED` for speech on a
  model without native audio, and drift warnings carry `evidence` and
  `observed_on`. Retime overlay limits are deferred.
- #68: Removed `typed_models.py`, the unrouted `adapt_flux/sd3/midjourney`
  wrappers, and dead helpers. Receipt identity hashes the routed adapter.
  `compare_frame_state` is NOT_COMPUTABLE without frame ids and INVALID when
  convergence is lost. The runtime contract and SKILL.md match dispatch.
- #72: `scripts/check_lint_ratchet.py` and `scripts/lint_baseline.json` hold
  per-file ruff and mypy counts that may only fall. The `skills/` mirror is
  excluded from lint. Shared `structured_io` and `value_coerce` helpers
  replace copied loaders and scalar helpers. `surface_compilers.py` is split
  into modules under 500 lines behind the same names.

## Production (#63, #64, #69, #70, #71)

- #63: `sequence_adapt.py` builds one Keyframe packet for a multi-shot
  sequence, covering every shot. Video adapt no longer fails closed on it.
- #64: `--take SHOT=TAKE_ID` on `storyboard impact` and `video retime`
  picks a take. Unknown and ambiguous ids fail closed with `TAKE_NOT_FOUND`
  and `TAKE_AMBIGUOUS`.
- #69: `video --action runbook [--retake SHOT]` lists PROPOSED Keyframe ops.
  A shot in a shared clip regenerates the whole clip. Unchanged shots are
  reused and the rejoin costs 0 credits. Spend is INFERRED and refused above
  `budget_cap_credits`.
- #70: `video --action cut-qa` lists ffmpeg frame-grab, scene-detect, and
  start-frame luma-MAE commands at the expected cuts. Nothing is executed.
- #71: `video --action cues` builds a cue sheet with voice locks, ducked and
  muted mixes at -14 LUFS / -1 dBTP, and an INFERRED ElevenLabs estimate that
  respects a cap. A non-speaking character with a line fails closed.

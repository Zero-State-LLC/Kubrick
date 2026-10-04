# Changelog — Kubrick

## [Unreleased]

### Added
- #98: `video runbook` keeps one node per call. A `-32001` provider result is `reconcile_later` (poll `objectKey` for about 6 minutes, no second submit). `estimateAvailable: false` quotes the billed-rate table (4/5/6 seconds → 62/77/93), not zero and not `seconds * 15.5`. The run ledger reconciles the late bill. `KUBRICK_JEV_TIMEOUT` sets the Jev client timeout (default 10s) and a dead endpoint fails closed after bounded retries. `tools/jev_adapter/` is a local fixture adapter with a health check. See `docs/runbook-spend-safety.md`.
- #99: Holds can name `scope` (locations, shots, characters), `anchor`, `views`, and `salience`. The pre-spend gate sends only the holds that match the prompt. A prop lock does not carry across a location change. A rear view gets the explicit rear negation. A POV frame omits wardrobe and asymmetry lines. A recorded Jev payload can pass or fail each hold (`present`, `located`, `strong`). A sample with `p` in 0.4–0.6 is re-sampled up to three times and is not a pass. See `docs/scoped-holds.md`.
- #100: Full take QC in `src/kubrick/qc/take_qc.py` keeps the fixture scorer and adds a VLM fixture verdict, an identity similarity threshold, and timestamps that must cover the sample clock. A live VLM flag is `NOT_COMPUTABLE`. ffmpeg runs only when the document opts in and the caller passes a runner. The module does not import `subprocess`. `video_cut_qa` still only prints commands.
- #103: A character `ref_pack` in `src/kubrick/plan/ref_pack.py` carries `views`, `head_lock`, `material_inserts`, and an `asset_hash`. Entry roles are `identity`, `material`, `costume_prop`, `location`, and `layout`. The resolver picks `start_frame`, `refs_only`, or `first_last`. Seedance `startImage` and `referenceImages` stay mutually exclusive, and a chain that drops references warns `REFS_DROPPED_BY_CHAIN`. A layout ref on a new-angle shot warns `LAYOUT_REF_ON_NEW_ANGLE`. The same pack hash is shared across movies. A disagreeing hash is `NOT_COMPUTABLE`. No image is generated.
- #102, #110: Numeric framing in `src/kubrick/prompts/framing.py`. A start frame plus one action and one camera move writes a motion-only video line (`action as move`) and leaves the still on the image prompt. Two primary moves warn `MOVE_CHAIN_CONFLICT`. A tight crop on a wide plate without `location_ref.precrop_to` warns `WIDE_PLATE_OVERRIDES_CROP` and `CROP_UNREACHABLE_FROM_PLATE`. An adjective proportion without a head-ratio band warns `ADJECTIVE_PROPORTION`. A push or pull without `end_framing` warns `MOVE_WITHOUT_END_ANCHOR`. An end framing with no head ratio or crop warns `MOVE_TARGET_MISSING`. An unbridged axis change warns `AXIS_CROSS_UNBRIDGED`. A video prompt that restates shot size or head ratio warns `VIDEO_REFRAME_IGNORED`. When the end framing is an anchor, prep records `END_IMAGE_UNSUPPORTED`: the Keyframe create_movie schema has `startImage` and no end-image field. The safe box scales the 1080×1920 rectangle (140, 940, 220, 1436). `delivery.platform` does not change those ratios.
- #101, #106, #110: The board gate in `src/kubrick/gates/board_qc.py` scores fixture measurements before video spend. A start frame with no image evidence is `unverified`, not `start_frame`. Silicon hands on the board can verify the lock. Human hands contradict it (`BOARD_LOCK_CONTRADICTED`, `HUMAN_HAND_ON_SILICON_LOCK`) and block the packet. A knees-up ask on a full-body plate is `crop_line` before spend. A `join: cut` does not inherit the previous shot's start frame. A chained shot still can when the board is verified. Warning codes include `EDGE_CUT`, `SAFE_ZONE_VIOLATION`, `PREV_BOARD_REF_COPY`, and `ASYMMETRY_TURN_RISK`.
- #100, #107, #110: Take QC core in `src/kubrick/qc/vision_observe.py` scores fixture measurements for the EP-01 restart cases (hands, glows, head-ratio drift, knees-up crop, and the rest of the twelve). A non-human head with no pose landmarks uses the head-dome measurement. `open_copy` warns `REF_OPEN_COPY`. A start that never releases warns `START_HOLD`. A clean fixture has an empty defect list. A picture prompt that drops a critical lock line, including the chest LED, is `MISSING_LOCK` even when a recorded Jev verdict says pass. CI does not call a detector or a paid API.
- #105: Production modules live in `src/kubrick/{plan,prompts,adapters,gates,qc,providers,corpus,surfaces,runtime}`. `scripts/<name>.py` remains the entry point and loads that module. `python scripts/kubrick.py` is unchanged. `kubrick.main` is split into per-command handlers in `src/kubrick/cli.py`, each under the complexity gate of 22. Tests stay in `scripts/` because the skill contract and Hermes evals invoke them by that path. Coverage measures `src/kubrick` as well as `scripts/`. The lint ratchet follows the moved modules.
- #105: The hub mirror is checked by regenerating it. CI runs pytest once, on checkout v4 and setup-python v5, with the coverage job on Python 3.12. The Hermes eval matrix remains 3.10–3.14. `scripts/check_workflows.py` rejects a deploy, pin, or Noema workflow. Duplicate PR and issue templates are removed. New issues and pull requests are added to org project 13 as Backlog when `PROJECT_TOKEN` is set. A board miss is a warning, and the partner-agents comment still posts. See `docs/CONTINUITY.md`.
- #90: `video runbook` and `video cues` run a Jev pre-spend gate before any credit figure or paid operation. The hold list is the plan `hold_list` when that field is set. Otherwise it is the plan `locks`, `location.locks`, and prop-state texts. A hold hit blocks spend (`JEV_HOLD`). If Jev is unreachable the command fails closed (`JEV_UNREACHABLE`) unless `--jev-override` or `KUBRICK_JEV_OVERRIDE` is set. The override is logged and does not bypass a hold hit. Recorded verdicts (`--jev-verdicts` or `KUBRICK_JEV_VERDICTS`) keep CI off the network. The gate result is written on the payload and, with `--run-ledger`, appended to the run ledger.

### Changed
- #90: A recorded verdict is keyed by the judged prompt and the hold list, so a changed hold, shot, channel, surface, or location does not reuse an old pass. A `hold_list` that is not a list is `HOLD_LIST_INVALID`. A local block matches `frame_id` and `shot_id`. A transport failure after an earlier pass is `JEV_UNREACHABLE`.

## [0.23.0] — 2026-10-03

### Added
- #78: `assets/grammar/film_grammar.yaml` with 66 hand-written entries (shot size, angle, lens band, move, lighting, edit, 9:16 composition), its schema, and `scripts/film_grammar.py`. Known terms expand to their prompt phrase and `lens_mm` maps to a lens band. New warnings `UNKNOWN_GRAMMAR_TERM`, `LENS_BAND_UNMAPPED`, and `MOVE_CHAIN_CONFLICT`. Negated terms ("no push-in") never resolve, and `camera.focus` only resolves focus entries.
- #77: Storyboard frames carry optional `camera` {`size`, `angle`, `lens_mm`, `move`, `focus`} and `cut` into generic per-shot prompts and Keyframe `videoPrompt` / `multi_shot_prompt`. An unknown frame key warns `UNKNOWN_FIELD`. The MYSLEF example plan carries the EP-01 camera blocks.
- #79: Seedance 2.5 drift entries from MYSLEF EP-01: `framing-wider-than-asked`, `brightness-over-directed` (dim and practical), `weak-action-intensity`, `chained-start-suppresses-move` (camera-context snap or whip only), and `flicker-clears-all-figures` (explicit flicker only). Techniques `scoped-flicker`, `cut-on-sound-peak`, `new-angle-after-cut` (≥ 30°), and `offscreen-event`. Matchers live in `scripts/plan_cues.py`.
- #79: Schema-backed `keep` list on storyboard frames, the storyboard root, and the adapter packet. A flicker that would clear a kept name warns `FLICKER_CLEARS_KEEP`.
- #81: Six targeted sidecars in a `wave3` manifest: withheld cause, dormant background watcher, uncanny near-human double, anempathetic playback, power-failure response, and the domestic trap. The MYSLEF example brief now describes the actual EP-01 scene and is a retrieval regression.

### Changed
- #76: Both retrievers share one stop-word set for token overlap and route matching. `SELECTED` needs `dramatic_fit >= 0.15`; weaker evidence is `NOT_COMPUTABLE` with `LOW_DRAMATIC_FIT`. Function-word-only briefs no longer select. The receipt lists the selected primary and supporting grammars first. Cache keys carry the selection policy, so older SELECTED receipts are not replayed.
- #80: Every sidecar is indexed, registered, and manifested. Duplicates are merged, directories match domains, dead lexicon links are repaired, and thin sidecars (missing fields or empty lists) are filled. Fixture models moved to `evals/fixtures/models/`. `audit_corpus_coverage.py` fails closed and runs in CI. The unused `schemas/cinematic-pattern.schema.json` is removed.
- #82: `kubrick do ledger --action init` routes like `do ledger init`; `operate` takes `--action` too. Relative path flags resolve against `KUBRICK_CALLER_CWD`; an inline `--brief` stays prose. `production_engine.py` is split under 500 lines (`production_artifacts.py`). The failing CodeQL and Pages workflows are removed (see `docs/ci/README.md`).

### Notes
- Product version is 0.23.0. The production envelope schema id stays `0.16.0`. `corpus_version` stays 0.11.5; `corpus_digest` changes with the corpus bytes (#80, #81). `schema_bundle_version` changes separately because the manifest-listed schemas changed: the new film-grammar schema and the `keep`, `camera`, and `cut` properties on the storyboard and adapter-packet schemas. No provider is called.


## [0.22.0] — 2026-10-03

### Added
- #61: CI runs `pytest -q scripts tests tests_audit`, every script test, and the evals under subprocess-aware coverage with a 75% floor, then fails on a dirty tree. `Pygments` and `coverage` are pinned in `requirements-ci.txt`.
- #65: Manifest `action_requirements` gates dispatch with `DEPENDENCY_MISSING` (exit 4). `do check --action deps` reports readiness.
- #66: MCP request byte cap, manifest action resolution and dependency check before spawn, and a per-call `MCP_TIMEOUT`.
- #67: `REFERENCE_CAP_EXCEEDED` above the model `max_references`, `NATIVE_AUDIO_UNSUPPORTED` warnings, and `evidence` on drift warnings.
- #63: Video adapt of a multi-shot sequence builds one Keyframe packet covering every shot. Shots whose shared constraints differ still fail closed and are named.
- #64: `--take SHOT=TAKE_ID` selects a take in `storyboard impact` and `video retime`. An unknown shot or take, an ambiguous take, or a selected take whose trim is too short fails closed with `TAKE_NOT_FOUND`, `TAKE_AMBIGUOUS`, or `TAKE_UNUSABLE`.
- #69: `video --action runbook` emits PROPOSED Keyframe retake ops: regenerate, wait up to 45s on `processingJobId`, check credits, reuse, and a 0-credit rejoin. Spend is INFERRED and stops at `budget_cap_credits`.
- #70: `video --action cut-qa` emits ffmpeg frame-grab, scene-detect, and start-frame luma-MAE commands for the expected cuts. `executes` is false.
- #71: `video --action cues` emits a cue sheet, voice locks, ducked and muted mix variants at -14 LUFS / -1 dBTP, and a capped INFERRED ElevenLabs estimate.
- #72: Per-file ruff/mypy lint ratchet (`scripts/check_lint_ratchet.py`) in CI. Shared `structured_io` and `value_coerce` helpers. `surface_compilers.py` split into modules under 500 lines.

### Changed
- #62: Retrieval cache and receipts write to `<project>/out/kubrick/retrieval/`. NOT_COMPUTABLE exits 4 in retrieve, operate, and govern.
- #68: Removed `typed_models.py`, the unrouted adapter wrappers, and dead helpers. `compare_frame_state` fails closed. Docs match dispatch.

### Notes
- Product version is 0.22.0. The production envelope schema id stays `0.16.0`. Retime overlay limits are deferred.


## [0.21.1] — 2026-10-03

### Fixed
- #48: A sequence packet with more than one shot fails closed on video adapt and names the dropped shots. A single-shot sequence still adapts. Storyboard adapt is unchanged.
- #49: CI installs `requirements-ci.txt`, runs `python -m pytest -q scripts`, then every `scripts/test_*.py`. `check_hub_sync.py` also runs after Hermes evals.
- #50: Removed `scripts/evolve_from_use.py`. `learn evolve` stays proposal-only.
- #51: Corpus coverage is written to `out/kubrick/corpus-coverage.json` (or `--output`). `references/reports/` is gitignored.
- #52: Legacy `design-build` renders `templates/design-specification.yaml`. Design markdown names the current product version.
- #53: The MCP server answers malformed JSON-RPC with -32700, -32600, and -32602 and keeps serving.
- #54: Video adapt, video retime, and storyboard impact return `DEPENDENCY_MISSING` (exit 4) when PyYAML or jsonschema is missing, with the install command.
- #55: `do wizard --action plan` is accepted. Any other wizard action is refused.
- #56: Storyboard impact emits `OBSERVATION_MISSING` or `TAKE_AMBIGUOUS` instead of a clean `PROPOSED` when a compared take has no observation or several takes and none is selected.
- #57: A numeric `budget_cap_credits` with a non-computable spend estimate fails closed as `BUDGET_CAP_UNVERIFIABLE`.
- #58: Shot prep, drift, and retime share `planned_duration` (default 8.0). A missing duration warns `DURATION_MISSING`.
- #59: `--takes` and `--answers` are bounded MCP paths. Routed writers use the bounded writer and refuse protected skill paths.
- #60: Removed the Noema pin and deploy workflows.

### Notes
- Product version is 0.21.1. The production envelope schema id stays `0.16.0`. The installer receipt schema id stays `1.0.0`.
- MYSLEF retime stays script 6.0, final 6.0, generated 12.0, delta 0.0.


## [0.21.0] — 2026-10-02

### Added
- #39: `known_drift` lives in `assets/drift/known_drift.yaml`, validated by `schemas/drift-registry.schema.json`. Entries are model-keyed and dated. A plain top plus motion on Keyframe still warns with the #30 text. An entry older than 180 days warns `DRIFT_ENTRY_STALE`. Tests inject the reference date.
- #40: Keyframe pricing is provider data labelled INFERRED (15.5 credits per second at 480p). The adapt output carries a per-shot and total `spend_estimate` from generated seconds, plus an `execution_checklist`. `budget_cap_credits` fails closed with `BUDGET_CAP_EXCEEDED` when the estimate is over the cap. A provider without pricing gets `NOT_COMPUTABLE`, not 0. No provider is called. `image_rate` is recorded and is not added to the video estimate.
- #41: Multi-shot single-clip providers get `multi_shot_prompt`: a header, `Shot N (Xs):` blocks, one continuity block, and an ending state. More than 5 shots warns `SHOT_COUNT_HIGH`. Generic output has no `multi_shot_prompt`. The preservation report is unchanged.
- #42: `provider_capabilities(provider, model=None)` merges a model overlay. Observed values win over vendor claims. Each block has `source` and `verified_on`. A stale `verified_on` warns `CAPABILITY_STALE`. A missing `source` fails schema validation. The Keyframe default remains the phase A values, including the 1.6s hold. `negative_prompt_effective` is the same field as #35.
- #43: `audio_strategy` is `native`, `external`, or `muted_native`. The last two mark Keyframe `audio.sound` as a guide track. A character `voice` with `speaks: false` plus a speech line, or a voice id matching `never_clone_of`, fails closed with `VOICE_LOCK_VIOLATION`. More than 2.5 words per planned second warns `DIALOGUE_TOO_LONG`.
- #44: Character `asymmetry` compiles one positive line with figure and viewer sides. A left/right swap between consecutive frames warns `SCREEN_DIRECTION_FLIP` unless the later frame sets `axis_change: true`. A reference with `mirrored: true` warns that sides in the image are inverted.

### Notes
- The production envelope schema id stays `0.16.0`. The installer receipt schema id stays `1.0.0`.
- MYSLEF shots 03–06 are the example under `examples/myslef-minder/`. Generic compile shows the asymmetry line once on each prompt where myslef is on screen. Keyframe adapt is `PROPOSED` and exits 0. The spend estimate is 4 × 3s at 15.5 credits per second, 186 credits total, labelled INFERRED. The exact commands are in `docs/RELEASE-NOTES-v0.21.md`.

## [0.20.1] — 2026-10-02

### Fixed
- #36: `video retime` `final_clock` is the edited runtime, the sum of edit-plan `out` minus `in`. `delta` is `final_clock` minus `script_clock`. `generated_clock` is generated seconds, counting each shared clip once. The MYSLEF example no longer sets `accept_clock_delta`. Its script clock, final clock, and delta are 6, 6, and 0, and its generated clock is 12. An edit window longer than the script beat is still `CLOCK_DELTA_UNACCEPTED` unless accepted.

## [0.20.0] — 2026-10-02

### Added
- #33: Optional `applies_to` scopes a character reference. An attached reference on a two-person frame that is not scoped to exactly one on-screen id warns `REFERENCE_BLEED_RISK`. A scoped reference adds one binding line. `scope` without `applies_to` does not scope the reference.
- #34: Storyboard `location` references are linted against location locks and `counts`. A contradiction warns `LOCATION_REFERENCE_CONTRADICTION`. `--strict` exits non-zero. Counts compile to `exactly N name` lines, and a frame count overrides that key. `cast: []` compiles to `nobody is in frame` and drops wardrobe and identity lines.
- #35: Adapter output carries `lock_carriers` (`start_frame`, `reference`, `prompt_positive`, `prompt_negative_only`). A critical lock carried only by a negative warns `NEGATIVE_ONLY_LOCK`. Provider capabilities add `negative_prompt_effective` (false for Keyframe).
- #36: `video --action retime` proposes a generation plan, an edit plan, and script versus final clock. Short, chained, or reused shots are separate generations. Contiguous long beats can share one clip. A non-zero delta without `accept_clock_delta` is `CLOCK_DELTA_UNACCEPTED`. No provider call.
- #37: `storyboard --action impact` reads `takes.yaml` as OBSERVATION and warns `STALE_TAKE` when a downstream take does not continue the retake's observed end. Observations are not written back.
- #38: A chained Keyframe shot without `start_frame.asset` warns `START_FRAME_MISSING` and includes an ffmpeg handoff string. `--strict` exits non-zero. An unverified asset warns `START_FRAME_UNVERIFIED`. Kubrick does not run ffmpeg.

### Notes
- The production envelope schema id stays `0.16.0`. The installer receipt schema id stays `1.0.0`.
- Issues #39–#44 shipped in v0.21.0.
- MYSLEF shots 03–06 are the example under `examples/myslef-minder/`. Generic compile:

```bash
python3 scripts/kubrick.py compile \
  --brief examples/myslef-minder/brief.yaml \
  --mode storyboard \
  --storyboard-plan examples/myslef-minder/storyboard-plan.yaml \
  --provider generic \
  --out /tmp/myslef-minder-generic
```

- Keyframe adapt, retime, and take impact of that plan:

```bash
python3 scripts/kubrick.py video --action adapt \
  --provider keyframe \
  --input examples/myslef-minder/storyboard-plan.yaml \
  --output /tmp/myslef-minder-keyframe.yaml
python3 scripts/kubrick.py video --action retime \
  --provider keyframe \
  --input examples/myslef-minder/storyboard-plan.yaml \
  --output /tmp/myslef-minder-retime.yaml
python3 scripts/kubrick.py storyboard --action impact \
  --storyboard examples/myslef-minder/storyboard-plan.yaml \
  --takes examples/myslef-minder/takes.yaml \
  --retake 04 \
  --output /tmp/myslef-minder-impact.yaml
```

## [0.19.0] — 2026-10-02

### Added
- #25: Keyframe short-beat warnings for shots at or below `short_beat_threshold_seconds` (default 2.0). The warning names the shot, the duration, and the recommendation to generate that shot as its own clip at the provider minimum, then trim. Shots under that minimum are generated at the minimum and trimmed. The warning is stored on the compile receipt and the adapter output.
- #26: Optional per-frame `join` (`cut` or `{chain_from, at_seconds}`). A Keyframe chained shot receives `startImage` and drops `referenceImages`. The exclusivity rule is provider data. Unknown, same-frame, and later chains fail closed. Non-adjacent chains are kept.
- #27: Generated duration is `max(planned + hold, provider minimum)`. A chained shot that does not open on an exit adds `start_frame_hold_seconds` (1.6) before that floor. See #26. The cut list trims the excess so used runtime stays the planned sum. `targetDurationSeconds` is the rendered sum and `plannedDurationSeconds` is the planned sum. Fail closed only above the provider maximum.
- #28: Storyboard `props` and per-frame `prop_states` compile a positive prop lock. A declared prop drops carried-over prior-state lines for that prop; the lock is the authority. Unreachable state jumps fail closed. Brief residue applies only from the `residue_add` that introduces it.
- #29: Author-supplied character reference manifests are linted against character-lock negatives. Character-level warnings set `shot` to null and name the character in `character`. `--strict` exits non-zero after the adapter writes the warning.
- #30: Per-character `wardrobe`, overridable per frame, compiles `WARDROBE LOCK` lines. Keyframe warns on a plain top plus a significant motion verb.
- #31: `assets/techniques/techniques.yaml` is checked against `schemas/techniques.schema.json` (registered in the manifest). Matches are suggestions unless the frame sets `apply_techniques`.

### Notes
- The production envelope schema id stays `0.16.0`. The installer receipt schema id stays `1.0.0`.
- MYSLEF shots 03–06 are the example under `examples/myslef-minder/`. Generic compile:

```bash
python3 scripts/kubrick.py compile \
  --brief examples/myslef-minder/brief.yaml \
  --mode storyboard \
  --storyboard-plan examples/myslef-minder/storyboard-plan.yaml \
  --provider generic \
  --out /tmp/myslef-minder-generic
```

- Keyframe adapt of that plan exits 0. Each shot is generated at least 3 seconds, and the cut list trims back to the planned beats. The artifact under `result.adapted_packet` includes `prep_warnings`, `technique_suggestions`, `cut_list`, and `dropped_references`. Chained shots carry `startImage` and omit `referenceImages`:

```bash
python3 scripts/kubrick.py video --action adapt \
  --provider keyframe \
  --input examples/myslef-minder/storyboard-plan.yaml \
  --output /tmp/myslef-minder-keyframe.yaml
```

## [0.18.0] — 2026-10-02

### Fixed
- #23: VERSION, `kubrick.manifest.yaml`, `pyproject.toml`, `SKILL.md`, README, CHANGELOG, and the v0.18 release notes are audited together, including the `skills/kubrick` mirror. Both installers run `audit_release_version.py --strict` before activation. The 0.17.0 smoke failure was a VERSION bump while the manifest stayed at 0.16.0; the installer did not run the release audit, and hub sync only byte-compares trees.
- #19: PyYAML and jsonschema are runtime dependencies. `compile` exits 3 with `python3 -m pip install -r requirements.txt` when jsonschema cannot be imported.
- #20: the same noun may appear in more than one brief layer. A verbatim multi-word phrase copied across layers still fails, and the error names the phrase and both layers.
- #18: ownership labels render as `motif ownership`.
- #17: per-shot prompts are built from each storyboard frame's state. Observed ids render as evidence text. Blank and `None` values are omitted.
- #21: general negatives stay in the negative field. Repeated clauses collapse in order.
- #16: character-lock negatives are restated as positive identity constraints and kept in the negative field when the provider has one. A brief may supply them with `character_locks` or with `character-lock:` / `identity-lock:` production constraints, and `compile` carries them into every provider prompt.
- #22: the `keyframe` provider emits a `create_movie` payload. Each shot is 3–60 seconds inclusive. Speech is omitted when a shot has no dialogue. Grok Imagine remains capped at 8 seconds. `aspectRatio` comes from an `N:M` token in the brief, and optional storyboard `duration_seconds`, `title`, `scene`, `sound`, and `speech_lines` pass through to the shot.

### Notes
- The production envelope schema id stays `0.16.0`. It does not track the product version. The installer receipt schema id stays `1.0.0`.

## [0.17.1] — 2026-09-01

### Changed
- Hermes Agent v0.21.0 `SKILL.md` contract: required frontmatter, body order,
  `${HERMES_SKILL_DIR}` substitution, Hermes `terminal` framing, and
  `[[as_document]]` for frame and storyboard images.
- Author line is now `Daniel Meyer (scrimshawlife-ctrl), Hermes Agent`.
- Description `Builds continuity-safe cinematic stories and visuals.` is
  unchanged (52 characters, one sentence, period).

### Notes
- Creative CLI, router, and production-surface behavior are unchanged.
- OpenClaw edition remains on the `openclaw` branch.

## [0.17.0] — 2026-08-08

### Added
- Hermes **wizard** (`do wizard`): presets, `--answers`, print-only default, `--run`, `--json`.
- Desktop-safe chat protocol and `schemas/wizard-answers.v1.schema.json`.
- Recipe `wizard-verify`.

### Notes
- Shipped on top of org **0.16.0** (version **0.17.0**, not 0.15.0).


Kubrick is the primary symbolic cinematic narrative engineering skill. It replaces the earlier scriptwriting skill as the recommended system for premise-to-production development with deep motif, geometric, cinematic, storyboard, and visual-fidelity encoding.

## [Unreleased]

## [0.16.0] - 2026-08-04

### Added — Canonical production engine

- `scripts/cinematic_project_state.py` shared state helper + `evals/golden/v016/` fixtures.

- Shared `ProductionSurface` / `ProductionRequest` / `ProductionResult` / `ProductionArtifact` / `ProductionContext` / `ProductionValidator` / `ProductionReceipt` in `scripts/production_engine.py`.
- All design/script/image/video actions execute through one validate→compile→receipt lifecycle.
- Expanded surface actions (design expand/summarize/qa; script rewrite/expand/compress/scene/beat/character/dialog/genre/qa; image generate/improve/analysis/batch; video blocking/transition/animation/timeline/continuity).
- Shared QA on every surface; `kubrick qa <surface>` sugar; `kubrick receipts`.
- Canonical artifact tree writer (`receipts/`, `artifacts/`, `validation/`, `qa/`, `timeline/`, `metadata/`).
- Docs: `docs/ARCHITECTURE-v0.16.md`.

### Changed

- Skill version advanced to `0.16.0`.
- Production envelopes use `schema_version: 0.16.0`.

## [0.15.0] - 2026-08-04

### Added — First-class production surfaces (foundation)

- Domain compilers for design.md lifecycle, script packets, image prompts, and video shot/sequence contracts (`scripts/surface_compilers.py`).
- `design improve` preserves valid sections and emits bounded diffs; video sequences fail closed on incompatible transitions.
- Example workflow: `examples/production-surfaces/`.
- Cross-surface acceptance tests and prohibited-pattern rejection receipts.
- Image/video `adapt` routes through provider adapters with preservation reports; script/image/video carry `source_design_revision` when design.md is supplied.
- Schemas for design-document, design-revision-receipt, shot-contract, and image-prompt-packet receipts.
- YAML brief intake enriches design create/improve (geometry, residue, production constraints, cinematic channel); placeholders are replaceable without wiping LOCKED sections.
- `--design` flag plus project `design.md` auto-discovery for revision linkage; shot YAML embeds `source_design_revision`.
- Fountain/beat-sheet script formats; authority-tagged `claims` on script/image/video packets.
- `design drift` project-wide reconciliation over artifact files or directories; `examples/production-surfaces/run_demo.sh`.
- `schemas/media-reconciliation-report.schema.json`.
- Provider capability declarations (`scripts/provider_capabilities.py`); video adapt fail-closed on image-only providers.
- Neutral `video prompt` packet + richer video QA dimensions; `schemas/video-prompt-packet.schema.json`.

- Registered peer intents `design`, `script`, `image`, and `video` with lifecycle actions.
- Added `scripts/production_surface.py` foundation runtime and surface entrypoints.
- Documented the v0.15 contract in `docs/FIRST-CLASS-PRODUCTION-SURFACES.md`.

### Added — Hardening

- Path containment and bounded YAML/JSON intake (`scripts/io_safety.py`).
- MCP `kubrick_do` intent/action allowlisting, flag validation, and path policy.
- Complete on-disk schema registry enforcement in the canonical manifest.
- Hub mirror drift gate (`scripts/check_hub_sync.py` / `check hub-sync`).
- Claim-level provenance helpers and expanded collision taxonomy (`scripts/provenance.py`).
- Frozen TypedDict contracts for high-risk artifacts (`scripts/typed_models.py`).
- `SECURITY.md` threat model; Windows `install.ps1` installer parity.
- Task aliases: `create`, `revise`, `inspect`, `validate`.
- Adversarial governance eval fixtures under `evals/adversarial/`.
- CI pins + ruff/mypy/pytest/hub-sync jobs.

### Changed

- Skill version advanced to `0.15.0`.
- Provider adapters and compile path use bounded IO helpers.
- OpenClaw alignment checklist published for v0.15 parity work.

## [0.14.0] - 2026-07-30

### Added — Deterministic contract consolidation

- Added `kubrick.manifest.yaml` as the stdlib-readable canonical Hermes registry for runtime profiles, intents, actions, aliases, recipes, schemas, providers, artifacts, authority classes, and exit codes.
- Added `pyproject.toml` to declare Python compatibility and optional `validation` / `dev` tooling without turning Kubrick into a required Python package.
- Added manifest validation, router parity tests, release-version alignment, and a cross-platform stdlib CI matrix.
- Added deterministic compile-receipt identities for the Kubrick release, corpus, schema bundle, provider adapter, command options, and normalized semantic input.
- Added mutation-sensitive identity tests and compile-receipt repeatability coverage.
- Added a canonical structured diagnostic schema and failure matrix for router errors, unavailable validation dependencies, and compiler `NOT_COMPUTABLE` paths.
- Added provider semantic-preservation reports covering graph identity, required observable content, ownership, geometry, state change, residue, continuity, and negative constraints.
- Added isolated lifecycle tests for dry-run, staged validation, fresh install, upgrade backup, rollback, receipts, and validation-failure safety.

### Changed

- The unified Hermes intent router now derives its registry, aliases, and recipes from the canonical manifest.
- The smoke gate now validates the manifest before the skill and corpus.
- The unified router now supports `KUBRICK_DIAGNOSTICS=json`; compiler `NOT_COMPUTABLE` consistently exits with manifest code `4`, while missing required optional tooling exits `3`.
- Grok Imagine now uses the shared provider adaptation path; all adapters fail closed when a critical semantic invariant is lost.
- The Hermes installer now validates before activation, atomically swaps installations, writes receipts, restores on activation failure, and supports `--dry-run`, `--rollback`, and `--version`.

### Changed — Operator intent router

- Primary CLI surface is `kubrick do <intent> [--action …]` (12 intents) for Hermes and humans.
- Soft aliases preserve all prior top-level command names (`adapt-flux`, `closed-loop-qa`, `validate-skill`, …).
- Help lists intents only; sugar includes `help`, `recipe`, and `aliases`.
- Recipes: `recipe storyboard-example`, `recipe verify`.
- MCP: single tool `kubrick_do` over the same router (never authoritative).
- Implementation: `scripts/intent_router.py`; design/plan under `docs/archive/superpowers/`.

### Documentation — OpenClaw edition pointer

- Added `docs/OPENCLAW.md` documenting the permanent **`openclaw`** branch Agent Skill packaging contributed by **Prabu** ([@prabu-openclaw](https://github.com/prabu-openclaw); [PR #1](https://github.com/scrimshawlife-ctrl/Kubrick/pull/1), commits `77fa721`, `15defae`).
- Cross-links from README, QUICKSTART, SKILL, and docs index so Hermes `main` and OpenClaw users can find the correct edition.

## [0.13.0] - 2026-07-30

### Added — Wave 2: Forge Feedback, Multi-Signal Evolution, Project Ledgers

- `scripts/extract_forge_signals.py` extracts multi-signal observation bundles from ledger diffs, revision records, saturation trends, collisions, ingestion results, and payoff realization.
- `schemas/forge-signal-bundle.schema.yaml` and `schemas/multi-signal-evolution-receipt.schema.yaml`.
- Multi-signal evolution proposals covering mutation success, production feasibility, anti-slop compliance, cultural-boundary respect, and payoff realization.
- Human review gates for large confidence deltas and structural or lifecycle mutations.
- Retirement/deprecation proposals for patterns that repeatedly create debt, collisions, or failed payoffs.
- First-class project symbolic ledgers with pattern history (evidence-of-use, source projects, outcome confidence), forge rehydrate/apply, and retrieval snapshots.
- Example Forge signal fixture under `references/examples/forge-signals/`.

### Added — Wave 3: Model Adapters, Closed-Loop QA, MCP Operators

- Shared latent-graph adapters for Flux, SD3, and Midjourney (plus existing Grok Imagine) via `adapt_provider.py`.
- Compiler provider support for `flux`, `sd3`, and `midjourney`.
- `closed_loop_visual_qa.py` orchestration with separate geometry, state, residue, and convergence fidelity reporting.
- CLI operators: saturation scoring, counterpoint, convergence-site locking, surface-occult audit, motif mutation, symbolic-architecture export.
- Optional stdio MCP server (`mcp_kubrick_server.py`) wrapping the same CLI without becoming authoritative.
- Time-sensitive contemporary cultural-signal packs with explicit provenance and validity windows.

### Governance

- Forge remains canonical authority; Kubrick emits observations and proposals only.
- No structural change applies automatically.
- Adapters never alter canonical symbolic intent.
- Operators fail closed on weak evidence and emit auditable receipts.
- Audience-facing prompts remain free of named esoterica unless explicitly requested.

### Added — Design Specification Compiler

- `design-build` compiles heterogeneous creative and technical evidence into a schema-valid design specification.
- Schema `schemas/design-specification.schema.yaml`, template `templates/design-specification.yaml`, and contract `references/design-specification-compiler.md`.

### Changed

- Skill version advanced from `0.12.0` to `0.13.0`.
- Unified CLI exposes forge-signals, multi-provider adapt, closed-loop-qa, operator, mcp-server, and design-build commands.
- README, QUICKSTART, SKILL, and `docs/` fully document the Wave 2/3 operator surface and shipped issue status.

## [0.12.0] - 2026-07-29

### Added — Unified Symbolic Storyboard Compiler

- Unified `scripts/kubrick.py` operator CLI.
- Compiler `0.3.0` orchestration from brief through retrieval, private graph, structured audit, audience translation, storyboard propagation, provider adaptation, and compile receipt.
- Draft 2020-12 artifact validation with exact failing paths.
- Canonical authority-transfer storyboard example and CI compilation.
- Storyboard state propagation for ownership, node, object, light, material, residue, and convergence continuity.
- Frame-transition comparison and prohibited-reset enforcement.
- Provider-neutral model-adapter packet contract.
- First Grok Imagine prompt adapter without mandatory credentials, network access, or model invocation.

### Added — Closed-Loop Visual QA

- Structured visual-observation schema and normalization for human, generic JSON, and optional Grok Vision outputs.
- Dimension-specific visual-fidelity reports for geometry, state, ownership, object, light, material, residue, convergence, and continuity.
- Targeted correction packets that preserve passing dimensions and change only observed mismatches.
- Bounded correction-loop governance with progress, regression, iteration-limit, and human-review decisions.
- Complete Grok generation/review bundle manifests and observation templates.

### Added — Governed Outcome Learning

- Pattern-use receipts recording retrieval confidence, compile validity, production feasibility, visual fidelity, correction count, payoff realization, cultural-boundary compliance, and operator outcome.
- Proposal-only pattern-evolution packets with bounded confidence deltas, misuse-risk additions, mutation-variable additions, and lifecycle review actions.
- Explicit prohibition on automatic corpus mutation or autonomous authority promotion.

### Added — Release and Runtime Hardening

- Deterministic repeatability check across two clean canonical compiles.
- Stable hashes for private graph, structured packet, storyboard state, transition report, neutral adapter packet, and Grok Imagine packet.
- Release checklist, release notes, current roadmap, authoritative `VERSION` manifest, and strict release-version audit.
- CI coverage for Hermes evals, outcome governance, canonical storyboard compilation, schema validation, and repeatability.
- Legacy sidecar normalization, qualitative production-cost support, structured ledger motif support, timestamp-safe deterministic hashing, and underscore-delimited route matching.

### Changed

- Skill version advanced from `0.11.0` to `0.12.0`.
- README and SKILL contract now describe the unified storyboard, adapter, visual-QA, and outcome-governance workflow.
- Outcome learning is observation- and proposal-based; ordinary execution never rewrites corpus confidence or lifecycle state.
- Continuity Forge, MCP, model APIs, and vision APIs remain optional extensions.

### Governance

- Local creative output remains `PROPOSED`.
- Production-use evidence remains `OBSERVATION`.
- Weak or invalid evidence returns `NOT_COMPUTABLE`.
- Pattern evolution cannot be applied automatically.
- Private pattern and lexicon semantics remain excluded from audience-facing packets.

## Earlier

Releases through 0.10.0 are archived in `docs/archive/releases/CHANGELOG-through-0.10.md`.

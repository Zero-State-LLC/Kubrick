# Changelog — Kubrick

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

## [0.10.0] - 2026-07-29

### Added — Neuro-Symbolic & Compositional Upgrades

- **Internal Motif/Structure Graph Layer**: Lightweight neuro-symbolic graph (nodes = motifs + observed states; edges = relational pressures and state transformations) used internally by the Dynamic Selection Engine. Translated exclusively into observable constraints.
- **Explicit Disentanglement of Cinematic Systems**: Layout/Geometry, Semantics/Function, and Attributes/States factored (SL-VAE style) to reduce leakage and enable cleaner interlocking.
- **Compositional Layered Encoding**: Analogs to Compositional Masked Attention (CMA) and Multi-Layered Sampler (MLS) — convergence masking, independent layers with controlled interaction, prioritized constraints.
- **Conditioning-Style Prompt Engineering**: Prompt sections act as precise control signals (geometry, state differentials, dual light, object participation).
- **Neuro-Symbolic Predicate Validation**: Internal combinatorial coherence checks treating lexicon entries as observable predicates.
- **Enhanced Single-Frame State Modeling**: Stronger before/after differentials, persistent residue as charge, layered time within one frame.

- Added section 17 "Neuro-Symbolic Motif Graph Layer" to references/symbolic-dramaturgy.md.
- Added "Neuro-Symbolic Conditioning Patterns (0.10.0+)" major section to references/cinematic-symbolism-corpus.md.
- SKILL.md bumped to 0.10.0 with full upgrade description.
- Goal: Higher relational precision, convergence strength, and controllable symbolic density for narrative + single-frame work while preserving full latency and anti-slop rules.

## [0.9.0] - 2026-07-29

### Added — Dynamic Latent Esoteric–Alchemical Encoding

- Full **Kubrick Esoteric–Alchemical Encoding Lexicon** (200+ entries across Hermetic Principles, Classical Alchemical Operations, Magnum Opus stages, Substances, Vessels, Polarity, Geometry, Elements, Planetary Forces, Initiatory Structures, Mythic Archetypes, Magical Operations, Chaos Magic, Theurgy, Kabbalah, Gnosticism, Neoplatonism, Time/Recursion, Shadow work, Dream/Astral, Divination, Ritual, Color, Sound, and Kubrick-native hidden structures).
- **Dynamic Esoteric–Alchemical Selection Engine**:
  - Analyzes prompt content or resulting image description.
  - Dynamically selects and interlocks multiple lexicon concepts.
  - Applies exclusively as observable structural constraints (state differentials, convergence points, relational pressure, recurrence-with-mutation, etc.).
  - **Latent operation**: No automatic disclosure or naming. Outputs are significantly more symbolically dense by default.
  - Explicit user query only ("what esoteric concepts were used?") triggers private report.
- New reference file: `references/esoteric-alchemical-lexicon.md`.
- Updated cinematic-symbolism-corpus.md with full Dynamic Selection rules, triggers, density mandates, and feedback loop for image analysis.
- SKILL.md updated with 0.9.0 capabilities and latent encoding behavior.
- Goal: Produce much higher symbolic density through content-driven, interlocking esoteric grammar without wasting tokens on explanation.

See `examples/beach-threshold.md` for baseline; 0.9.0+ runs will be denser.

## [0.8.0] - 2026-07-29

### Added — Profound Esoteric & Single-Frame Integration

- **Esoteric Structural Translation** in `references/cinematic-symbolism-corpus.md`
  - Formal translation layer for ancient magical and esoteric concepts (liminal/threshold, trace as binding/erasure, witness objects, erasure as active operation, inversion as crossing, dual preservation/dissolution, residue/charge).
  - All concepts enter exclusively via enforceable structural rules and constraint — never naming, iconography, or occult collage.
  - New "Core Translation Principles", "Rules for Profound Esoteric Work", and "Single-Frame Esoteric Mappings".

- Expanded **Cinematic Systems** in corpus: Light Systems, Geometry & Negative Space, Material & Trace, Inversion & Reflection, Perceptual Layering & Residue (with profound interlocking requirements).
- **Single-Frame & Generative Image Translation** section with concrete mappings, test criteria, and enforcement via Corpus Integration Rules.
- Integration points added across symbolic-dramaturgy.md, SKILL.md, and templates/production-handoff.md for esoteric and profound single-frame work.
- Stronger requirement for image prompts: interlocking from Light + Geometry + Material/Trace + Inversion at convergence point with state differentials.

## [0.7.1] - 2026-07-29
### Added — Autonomous Evolution from Use
- `scripts/evolve_from_use.py` — self-improvement engine
  - Aggregates retrieval receipts (auto-logged by retrieve script)
  - Incorporates project outcomes (success/failure signals)
  - Adjusts `confidence` in sidecars
  - Appends `usage_history` with performance data
  - Re-orders suggestions in `corpus-index.yaml` based on observed results
  - Emits auditable `evolution-*.json` receipts
- Auto-logging added to retrieval script (`references/usage/receipts/`)
- Seeded example usage data (receipts + outcomes)
- New procedures documented in SKILL.md under "Evolution from Use"
- Sidecars now carry usage-driven metadata

The corpus now improves from real application in projects and Forge workflows without manual curation for every pattern.

> **Superseded in 0.12.0:** automatic corpus changes are no longer part of the supported workflow. Outcome evidence now produces human-reviewed proposals only.

## [0.7.0] - 2026-07-29
### Added — Executable Retrieval (P0 of next campaign)
- `scripts/retrieve_symbolic_patterns.py` — deterministic retrieval helper
  - Loads index + sidecars
  - Scores with decomposition
  - Applies exclusions/prohibited
  - Emits structured retrieval_receipt
  - Fails closed below threshold
- Initial sidecar patterns in `references/patterns/` (9 high-value: alchemical nigredo, Kubrick monolith, Tarkovsky reflection, Bresson hands, Propp, Peirce, liminal, acousmatic, Denis marching)
- `evals/retrieval/` structure with inputs/ and expected/ golden fixtures
- 3 new formal tradition packs: Soviet montage, Japanese cinema, Animation
- SKILL.md documentation for the retrieval script

This begins the shift from reference skill to operational symbolic compiler.

## [0.6.2] - 2026-07-28 (further continuation)
### Added
- Additional genre packs: melodrama, comedy, low-budget/TV/short-form
- More populated schema examples (symbolic counterpoint, project ledger)
- Forge round-trip validation example and test
- Deeper film-pattern provenance depth for key examples (Kubrick Monolith, Tarkovsky, Bresson)
- Production feasibility test
- Expanded validation for round-trip and feasibility
- Updated SKILL.md with Forge round-trip procedure

### Expanded
- Genre and constrained-production guidance
- Transferable structure documentation in cinematic corpus

## [0.6.1] - 2026-07-28 (continuation after merge of #42)
### Added
- Populated schema examples (alchemical-nigredo, kubrick-monolith)
- Dedicated genre packs: horror, noir-thriller, science-fiction (under references/corpus/genre/)
- Concrete revision diff example (scene deletion)
- Additional validation tests for sequence/character arc and cultural review gates
- Concrete "How to Use" procedures in SKILL.md for scoring, ledger, sequence, character arc, revision, and handoff

### Expanded
- Film-pattern provenance depth examples integrated
- Cultural review trigger documentation and test
- Production feasibility notes in genre packs

This continues the P1/P2 hardening after the P0 merge.

## [0.6.0] - 2026-07-28
### Added — Symbolic Retrieval and Continuity Hardening (P0)
- Machine-readable schemas/ (symbolic-narrative-pattern, cinematic-pattern, transformation-grammar, narrative-affordance, symbolic-architecture, continuity-forge-symbolic-export)
- Retrieval scoring model with composite formula and NOT_COMPUTABLE threshold
- Negative retrieval / exclusion_profiles
- Project symbolic ledger (governing/supporting grammars, active/retired/prohibited motifs, symbolic_debt, saturation_score)
- Symbolic saturation control + SYMBOLIC_OVERLOAD
- Motif collision detection (REDUNDANT, CONTRADICTORY, etc.)
- Symbolic counterpoint rules
- Sequence-level symbolic_architecture and symbolic_character_arc compilation
- Symbolic revision diff engine
- Production feasibility weights
- Cultural review gates
- Corpus versioning and source_status (DRAFT → VALIDATED → DEPRECATED)
- Expanded cinematic corpus (genre packs, production scales, formal traditions: Soviet montage, Neorealism, Japanese, Hong Kong action, etc.)
- Film-pattern provenance depth (transferable_structure vs non_transferable_surface)
- references/retrieval-and-continuity.md
- Updated corpus-index.yaml with scoring, exclusions, ledger templates
- New validation cases for scoring, exclusion+collision, ledger+saturation+revision
- Forge round-trip validation expectations

### Changed
- SKILL.md now documents deterministic retrieval procedures as first-class
- All pattern work now expected to be schema-normalized + scored + collision-checked + ledger-tracked
- Cinematic examples now include production_cost and transferable vs surface distinction

This sprint converts the rich corpus into a reliable, auditable retrieval-and-continuity system.

## [0.5.0] - 2026-07-28
### Added
- Full provenance-linked Symbolic Narrative Pattern System
- `SymbolicNarrativePattern` core YAML schema with observed_structure, cinematic_affordances, mutation_rules, misuse_risks, and full source_records provenance
- Narrative Affordance Registry (BIND, DIVIDE, INITIATE, CONCEAL/REVEAL, INVERT, REPEAT, CONTAMINATE, MIRROR, SACRIFICE, CROSS, ENCLOSE, DESCEND, RETURN, HAUNT, ERASE, RESTORE + full mappings)
- Transformation Grammar Registry (alchemical processes, initiation, contamination, fragmentation, descent/return mapped to narrative + cinematic forms)
- Dedicated Cinematic Symbolism Corpus (techniques tracked as patterns with no fixed meanings)
- 10 corpus domains with starter PRIMARY/SCHOLARLY-anchored patterns (alchemical, ritual-liminal, cinematic)
- Source Hierarchy (PRIMARY / EARLY_COMMENTARY / SCHOLARLY / PRACTITIONER / COMPARATIVE / POPULAR / INTERNET)
- Cross-Tradition Relationship Types (HISTORICALLY_DERIVED, SHARED_FUNCTION, FORMAL_RESEMBLANCE, MODERN_SYNTHESIS, CONTESTED, UNSUPPORTED, etc.)
- Skill Retrieval Rules, Quality Gates, and 10 Validation Tests
- `corpus-usage.md`, `source-hierarchy.md`, `source-registry.md`, `cross-tradition-relationships.md`

### Changed
- kubrick positioned and documented as the primary/replacement symbolic cinematic skill
- Enhanced documentation across README, hermes docs, and internal references
- Updated retrieval discipline to prioritize dramatic problem → one primary grammar → at most two secondary → cinematic form → provenance

Kubrick now provides a rigorous, auditable bridge from historically grounded symbolic systems to subtle scene, character, blocking, composition, editing, and sound structures.

## [0.4.0] - 2026-07-28

### Added — Public-Ready Improvements

- Fixed frontmatter to Hermes standards.
- Added symbolic-specific eval rubric and regression cases.
- Strengthened observed-form-first, mutation, relational geometry, and anti-slop enforcement.
- Restructured SKILL.md closer to canonical Hermes skill format.
- Added concrete YAML examples of symbolic intent, motif lifecycle, and cinematic encoding.

## [0.3.0] - 2026-07-28

Initial public packaging of symbolic upgrade, Module 5B, Gates M–W, and Forge integration.

## Earlier

See scriptwriting history for base narrative engineering foundations. Kubrick supersedes that base for projects requiring cinematic symbolic precision.

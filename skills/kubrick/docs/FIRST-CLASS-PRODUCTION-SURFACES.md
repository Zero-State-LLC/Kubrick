# Kubrick First-Class Production Surfaces

Status: **IMPLEMENTED (v0.16.0 production engine)**  
Target: **v0.16**  
Scope: Hermes `main` (tracks [#33](https://github.com/Zero-State-LLC/Kubrick/issues/33); OpenClaw edition parity tracks [#32](https://github.com/Zero-State-LLC/Kubrick/issues/32))

## Decision

Kubrick must treat the following as peer, first-class production functions rather than secondary helpers attached to symbolic compilation:

1. `design` — create, improve, audit, and reconcile `design.md`
2. `script` — develop, rewrite, diagnose, and package scripts and screenplays
3. `image` — construct provider-ready still-image prompts and continuity packets
4. `video` — construct shot-aware video prompts, motion contracts, and sequence packets

All four surfaces operate over one shared cinematic state model. They may produce different artifacts, but they must not silently diverge in character identity, world rules, visual grammar, motif state, object ownership, chronology, material residue, camera logic, or production constraints.

## Problem

Kubrick already contains strong symbolic compilation, storyboard state, provider adaptation, visual QA, and a governed design-specification compiler. However, the current operator model makes the production capabilities appear uneven:

- `design` exposes only a single `build` action.
- scriptwriting is described in `SKILL.md` but lacks a dedicated first-class CLI intent and artifact contract.
- image prompting is split between compile and provider adaptation.
- video prompting is not represented as an explicit production surface.
- `design.md` is treated primarily as a compiled candidate rather than a living project contract that can be created, improved, audited, reconciled, and updated.
- downstream media prompts can become disconnected from the design specification and script state.

The result is a capable engine with an incomplete product surface.

## Product Model

```text
project evidence
  + existing design.md
  + script / treatment / scene material
  + visual references
  + production constraints
  + continuity ledger
        |
        v
shared cinematic state
  - locked facts
  - dramatic pressure
  - character and object identity
  - visual grammar
  - motif lifecycle
  - environment and material rules
  - camera and motion rules
  - audio and dialogue rules
  - provider-independent negative constraints
        |
        +--> design.md
        +--> script artifacts
        +--> image prompt packets
        +--> video prompt packets
        +--> QA / reconciliation receipts
```

## First-Class Intent Contract

### `design`

Purpose: own the project-level cinematic design contract.

Required actions:

| Action | Function |
|---|---|
| `create` | Generate a new `design.md` from available project evidence |
| `improve` | Strengthen an existing `design.md` without erasing valid decisions |
| `audit` | Diagnose omissions, contradictions, ambiguity, weak enforceability, and production risk |
| `reconcile` | Compare `design.md` against scripts, prompts, ledgers, references, and generated outputs |
| `update` | Produce a bounded revision and explicit change receipt |
| `validate` | Validate structure, required sections, invariants, provenance, and authority |
| `build` | Compatibility alias for `create` until deprecation |

`design.md` must be a readable production document, not a schema dump. It should remain useful to directors, writers, designers, artists, editors, sound teams, and generative agents.

### `script`

Purpose: make screenplay and scene work directly executable through Kubrick.

Required actions:

| Action | Function |
|---|---|
| `create` | Generate treatment, beat sheet, scene, sequence, short, episode, or screenplay material |
| `improve` | Rewrite for causality, pressure, character behavior, pacing, subtext, and cinematic legibility |
| `diagnose` | Identify weak stakes, false turns, exposition, continuity drift, dead motifs, and production ambiguity |
| `adapt` | Convert between treatment, beat sheet, screenplay, shot script, voiceover script, or production script |
| `continuity` | Check identity, chronology, object state, location state, knowledge state, and residue |
| `handoff` | Emit script-linked production packets for image, video, audio, storyboard, or Continuity Forge |

### `image`

Purpose: construct still-image prompts as governed cinematic artifacts.

Required actions:

| Action | Function |
|---|---|
| `prompt` | Generate a neutral image prompt packet from project state |
| `adapt` | Translate neutral packets to supported providers without semantic mutation |
| `sequence` | Generate continuity-safe prompts for a multi-image sequence |
| `reference` | Build character, environment, prop, costume, lighting, or style reference prompts |
| `negative` | Produce explicit negative constraints tied to known failure modes |
| `qa` | Compare generated imagery against expected state and emit corrective prompts |

### `video`

Purpose: construct temporally explicit generative-video instructions.

Required actions:

| Action | Function |
|---|---|
| `prompt` | Generate a provider-neutral video prompt packet |
| `shot` | Define one shot with start state, action, camera, timing, end state, and invariants |
| `sequence` | Build a multi-shot sequence with transitions and state propagation |
| `motion` | Define blocking, object motion, camera motion, physical behavior, rhythm, and forbidden motion |
| `adapt` | Translate the neutral packet to a named video provider while preserving invariants |
| `qa` | Compare observed video behavior against expected temporal and visual state |

## `design.md` Required Structure

A Kubrick-governed `design.md` should contain the sections below when applicable. Missing evidence must be marked `NOT_COMPUTABLE`; sections must not be filled with invented specificity.

1. **Document status and authority**
2. **Project identity and format**
3. **Creative objective**
4. **Audience experience**
5. **Dramatic engine**
6. **World rules and boundaries**
7. **Character identity and pressure architecture**
8. **Visual grammar**
9. **Composition and camera language**
10. **Lighting and color logic**
11. **Environment and production design**
12. **Character, costume, prop, and material continuity**
13. **Motif lifecycle and convergence limits**
14. **Motion and physical behavior**
15. **Editing, rhythm, and transition logic**
16. **Dialogue, voice, sound, and music logic**
17. **Image-generation rules**
18. **Video-generation rules**
19. **Provider-independent negative constraints**
20. **Accessibility, cultural, legal, and safety constraints when evidenced**
21. **Continuity invariants and locked facts**
22. **Production handoff requirements**
23. **Open questions and `NOT_COMPUTABLE` fields**
24. **Provenance map**
25. **Revision history and decision log**

Each normative statement should be one of:

- `LOCKED` — explicitly approved and authoritative
- `PROPOSED` — generated or suggested for approval
- `OBSERVED` — directly present in evidence
- `INFERRED` — supported interpretation
- `SPECULATIVE` — low-confidence creative possibility
- `NOT_COMPUTABLE` — insufficient or contradictory evidence

## Shared Artifact Contracts

Add the following artifact types and schemas:

- `cinematic-project-state`
- `design-document`
- `design-audit-report`
- `design-revision-receipt`
- `script-development-packet`
- `script-diagnostic-report`
- `script-continuity-report`
- `image-prompt-packet`
- `image-sequence-packet`
- `visual-reference-packet`
- `video-prompt-packet`
- `shot-contract`
- `video-sequence-packet`
- `motion-contract`
- `media-reconciliation-report`

Every media artifact must carry:

- `project_id`
- `artifact_id`
- `artifact_type`
- `authority`
- `source_state_id`
- `source_design_revision`
- `source_script_revision` when applicable
- `locked_invariants`
- `required_elements`
- `forbidden_changes`
- `provenance`
- `not_computable`

## Design Improvement Algorithm

`design improve` must not regenerate the document from scratch by default.

1. Parse the existing document into stable sections.
2. Extract normative claims and classify authority.
3. Load project evidence and continuity state.
4. Detect:
   - missing production-critical sections
   - vague or non-enforceable language
   - conflicting rules
   - accidental provider coupling
   - script/design mismatch
   - prompt/design mismatch
   - unsupported specificity
   - motif saturation
   - identity or continuity drift
5. Preserve valid decisions verbatim where possible.
6. Propose bounded edits with reasons and provenance.
7. Emit:
   - improved `design.md`
   - section-level diff
   - unresolved questions
   - invariant impact report
   - revision receipt
8. Never promote `PROPOSED` content to `LOCKED` without explicit authority.

## Prompt Construction Law

Image and video prompts are not free-form prose. They are compiled views of project state.

A prompt packet must separate:

- immutable identity
- current scene state
- desired transformation
- composition and camera
- lighting and material behavior
- motion and timing for video
- dialogue or audio cues when supported
- required continuity residue
- negative constraints
- provider syntax

Provider adaptation may alter formatting, weighting, token order, parameter syntax, and supported vocabulary. It may not alter story facts, identity, ownership, geometry, chronology, material state, start/end state, or required residue.

## Video-Specific Temporal Contract

Every shot must define:

```yaml
shot_id: stable-id
source_state_id: stable-id
duration_seconds: number
start_state: {}
action:
  subject: string
  verb: string
  path_or_change: string
camera:
  framing: string
  position: string
  movement: string
  lens_behavior: string
physics:
  required: []
  forbidden: []
end_state: {}
continuity_invariants: []
negative_constraints: []
```

A sequence compiler must prove that each shot's `end_state` is compatible with the next shot's `start_state`. Unresolved incompatibility returns `NOT_COMPUTABLE`.

## Script-Specific Contract

Kubrick script output must distinguish:

- dramatic intent
- observable action
- dialogue
- subtext
- knowledge state
- emotional force
- object and environment state
- continuity requirements
- production implications
- motif mutation
- residue

Script diagnosis must reject symbolic explanation as a substitute for dramatic causality.

## Router Target

The preferred v0.15 surface:

```bash
kubrick do design create --evidence project/ --output design.md
kubrick do design improve --input design.md --evidence project/ --out out/design-improvement
kubrick do design audit --input design.md --against scripts/ prompts/

kubrick do script create --brief brief.yaml --format screenplay --output screenplay.fountain
kubrick do script improve --input screenplay.fountain --design design.md --out out/script-revision
kubrick do script continuity --input screenplay.fountain --ledger project/ledger.yaml

kubrick do image prompt --scene scene.yaml --design design.md --provider generic
kubrick do image sequence --storyboard storyboard.yaml --design design.md --out out/images
kubrick do image qa --expected packet.yaml --observation observation.json

kubrick do video shot --scene scene.yaml --design design.md --duration 8 --output shot.yaml
kubrick do video sequence --script screenplay.fountain --design design.md --out out/video
kubrick do video adapt --packet shot.yaml --provider <provider>
```

## Compatibility

- Existing `compile`, `adapt`, `storyboard`, and `visual` commands remain functional.
- `design build` remains a soft alias for `design create` for at least one release.
- Existing provider adapters should become internal dependencies of `image adapt` and `video adapt`, not be removed.
- Existing visual QA should serve both still and temporal media through shared normalization plus media-specific dimensions.
- Existing symbolic graph, project ledger, and Forge authority rules remain authoritative within their current scope.

## Implementation Workstreams

### P0 — Contract and routing

- expand the manifest with `script`, `image`, and `video` intents
- expand `design` actions
- add compatibility aliases
- update top-level and intent help
- update `SKILL.md` trigger and procedure language
- add router tests for every action and default

### P0 — `design.md` lifecycle

- create parser and normalized internal model
- implement create/improve/audit/reconcile/update/validate
- add section-aware diff and revision receipt
- add schema and fixtures
- preserve Markdown readability and stable section IDs

### P1 — Script surface

- add screenplay/treatment/beat-sheet artifact models
- implement diagnostic and continuity passes
- support Fountain and Markdown initially
- emit production handoff packets linked to design revision

### P1 — Image surface

- wrap neutral adapter construction as `image prompt`
- add reference-prompt and sequence modes
- unify negative constraints and visual QA
- retain provider preservation reports

### P1 — Video surface

- add shot and motion schemas
- implement temporal state propagation
- add neutral video prompt packet (`video prompt`)
- add provider capability declarations and fail-closed adaptation
- extend QA to motion, timing, camera, physics, identity persistence, and end state

### P2 — Cross-surface reconciliation

- `design drift` (directory or multi-artifact evidence)
- design ↔ script
- design ↔ image
- design ↔ video
- script ↔ storyboard
- prompt ↔ generated observation
- project-wide drift report

### P2 — Documentation and examples

Add end-to-end examples for:

- existing project → improve `design.md`
- premise → design → screenplay scene → image sequence
- screenplay scene → shot contracts → video prompts
- generated output → QA → correction → design reconciliation

## Acceptance Criteria

1. `kubrick help` presents design, script, image, and video as first-class intents.
2. `design improve` preserves valid existing decisions and emits a bounded diff.
3. A `design.md` can be audited against a script and prompt packet.
4. Script output carries continuity and design revision IDs.
5. Image packets derive from shared project state and preserve provider-independent invariants.
6. Video shots define explicit start state, action, camera, physics, end state, and continuity constraints.
7. Multi-shot sequences fail closed on incompatible state transitions.
8. Provider adapters produce preservation reports for image and video.
9. All generated artifacts distinguish observed, inferred, speculative, proposed, locked, and not-computable claims.
10. Existing v0.14 commands remain operational through compatibility aliases.
11. Deterministic tests cover routing, schema validation, repeatability, and cross-surface drift.
12. No creative command silently promotes authority or overwrites canonical Forge state.

## Non-Goals

- direct dependency on any image or video provider API
- automatic canonical promotion
- replacing Continuity Forge as committed continuity authority
- hiding unresolved production questions behind generated detail
- provider-specific design documents
- a generic prose-writing or generic software-design skill

## Recommended Release Boundary

Ship this as **v0.15 — First-Class Production Surfaces**. Do not combine it with unrelated corpus expansion. The release should be considered complete only when the four peer surfaces are visible in the skill contract, router, schemas, examples, and regression suite.
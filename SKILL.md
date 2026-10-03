---
name: kubrick
description: Builds continuity-safe cinematic stories and visuals.
version: 0.22.0
author: Daniel Meyer (scrimshawlife-ctrl), Hermes Agent
license: LicenseRef-Zero-State-Proprietary-1.0
platforms: [linux, macos, windows]
metadata:
  author: Daniel Meyer (@scrimshawlife-ctrl) / Applied Alchemy Labs <scrimshawlife-ctrl@example.com>
  hermes:
    tags:
      - Creative
      - Cinematography
      - Screenplay
      - Storyboard
      - Continuity
      - ImagePrompt
      - SymbolicDesign
      - ProductionHandoff
    category: creative
    related_skills: []
---

# Kubrick Skill

Kubrick is a standalone Hermes skill that develops and revises screenplays,
cinematic systems, storyboards, and provider-ready visual prompts while
preserving dramatic causality and continuity. It does not answer film trivia,
write unrelated prose, or perform general software engineering. Hermes loads
this directory directly and uses `SKILL.md` as the behavior contract.

## When to Use

Use Kubrick when the user wants to:

- develop a premise, character pressure map, beat sheet, scene, or screenplay
- diagnose weak causality, motif drift, symbolic overload, or continuity conflict
- revise material while preserving locked facts, ownership, chronology, and residue
- build a visual design system, scene contract, shot recurrence, or production packet
- construct a single frame or storyboard with state continuity across images
- translate a neutral cinematic packet for Flux, SD3, Midjourney, Grok Imagine, or Keyframe
- compare an expected frame with a human or model observation
- compile creative evidence into a design specification

Do not use Kubrick for film trivia, reviews, general cinema questions, generic
prose, software engineering, packaging, DevOps, or visual tasks with no dramatic
system.

### When Not to Use

Choose a narrower writing, research, coding, or image skill when the request
does not need cinematic causality, motif state, visual continuity, or production
handoff.

## Prerequisites

- Python 3.10 or newer runs the bundled deterministic helpers.
- Core creative and routing behavior uses the Python standard library.
- `compile`, `video adapt`, `video retime`, and `storyboard impact` require PyYAML and jsonschema. Install them with `python3 -m pip install -r requirements.txt`.
- Model APIs, vision APIs, Continuity Forge, and the bundled MCP server are optional.
- No API key is required for local creative work.

Hermes substitutes `${HERMES_SKILL_DIR}` with the installed skill directory.
Write generated artifacts to a user-selected project directory or `out/`. Never
write into `references/` during ordinary work.

The OpenClaw edition is maintained separately on the `openclaw` branch. This
file is the Hermes contract.

## How to Run

Most creative requests can be completed from this contract and the relevant
files in `references/`. Use the bundled router when deterministic retrieval,
compilation, validation, adaptation, storyboard propagation, or QA adds value.

Call the Hermes `terminal` tool with the substituted skill path:

```text
terminal(command="python3 ${HERMES_SKILL_DIR}/scripts/kubrick.py do <intent> [--action <action>] [flags]", timeout=120)
```

Common invocations:

```text
terminal(command="python3 ${HERMES_SKILL_DIR}/scripts/kubrick.py recipe storyboard-example", timeout=120)
terminal(command="python3 ${HERMES_SKILL_DIR}/scripts/kubrick.py do retrieve --brief path/to/brief.yaml", timeout=120)
terminal(command="python3 ${HERMES_SKILL_DIR}/scripts/kubrick.py do adapt --action provider --provider flux --packet packet.yaml --output adapted.yaml", timeout=120)
terminal(command="python3 ${HERMES_SKILL_DIR}/scripts/kubrick.py do visual --action closed-loop --expected expected.yaml --observation-input observed.yaml --out out/qa", timeout=180)
terminal(command="python3 ${HERMES_SKILL_DIR}/scripts/kubrick.py do check --action smoke", timeout=120)
```

Use `help <intent>`, `recipe <name>`, and `aliases` on the same entrypoint for
discovery. Legacy command names remain soft aliases. The optional MCP server
exposes one proposal-only tool, `kubrick_do`, through the same intent router.

When you produce a frame still, storyboard image, or other high-resolution
visual, include the literal directive `[[as_document]]` in the same response so
Hermes attaches the original file instead of a crushed preview.

### Guided wizard

When the operator is unsure which `do` intent to run, wants a guided production
path, or you would freestyle flags:

1. Collect missing fields in chat, one at a time. Do not use interactive stdin
   from the agent `terminal` path.
2. Write `kubrick-wizard-answers.v1` JSON with `write_file`.
3. Preview: `terminal(command="python3 ${HERMES_SKILL_DIR}/scripts/kubrick.py do wizard --answers FILE --print-only", timeout=60)`
4. On approval: add `--run`, or run the printed argv through `terminal`.
5. Never set `allow_mutate: true` unless the user explicitly approved
   ledger, evolution, or operate writes.

Prefer the wizard when unsure; use `do <intent>` when flags are already known.

## Quick Reference

- `compile` — Turn a brief and optional ledger into cinematic artifacts
- `retrieve` — Rank executable patterns with exclusions and provenance
- `ledger` — Initialize, audit, mutate, or rehydrate project continuity
- `design` — design.md lifecycle (create/improve/audit/reconcile/update/validate)
- `script` — Script development, diagnosis, and continuity handoff
- `image` — Still-image prompt engineering and QA
- `video` — Temporal shot, motion, and sequence prompting and QA. `retime` proposes a generation and edit plan and does not call a provider. `runbook` (`--retake SHOT`), `cut-qa`, and `cues` emit PROPOSED retake ops, ffmpeg QA commands, and a cue sheet with mix targets. They never run a tool or spend credits. `retime` and `storyboard impact` accept `--take SHOT=TAKE_ID`.
- `storyboard` — Propagate or compare state across frames. `impact` reports stale takes from an observation ledger.
- `adapt` — Build neutral packets and provider-specific syntax
- `visual` — Normalize, compare, correct, and govern visual QA
- `learn` — Record outcomes and produce proposal-only evolution
- `check` — Validate the skill, corpus, artifacts, hub sync, and repeatability
- `operate` — Run graph and ledger operators
- `mcp` — Serve the optional MCP adapter
- `bundle` — Build a Grok review bundle
- `wizard` — Guided plan/execute via answers JSON or interactive TTY

Task aliases: `create` → compile, `revise` → design improve, `inspect` → operate,
`validate` → check smoke.

Adapter providers: `generic`, `grok-imagine`, `flux`, `sd3`, `midjourney`, and `keyframe`. `compile --provider none` (the default) skips adaptation.

CLI sugar: `kubrick qa <surface>` runs `do <surface> --action qa`; `kubrick validate design|script|image|video` runs design validate, script diagnose, or image/video qa; `kubrick receipts` lists receipts under `out/`.

Brief fields follow `examples/authority-transfer-storyboard/brief.yaml`: dramatic problem, desired state change, character pressure, observable evidence, layers, and production constraints. Optional `character_locks` is a list of identity constraints (`no nose`, `hairless scalp`). A `production_constraints` item prefixed `character-lock:` or `identity-lock:` is the same lock. `aspect_ratio`, or the first `N:M` token in `production_constraints`, sets Keyframe `aspectRatio`. The fallback is `16:9`.

Storyboard plan frames may carry optional `duration_seconds`, `title`, `scene`, `sound`, and `speech_lines`. Keyframe allows 3–60 seconds per shot. When `sound` is omitted, the shot uses `no scored music; evidenced room presence only`. Optional `props` registers ordered states, and a frame `prop_states` value is a state id or `start->end`. Optional `join` is `cut` or `{chain_from, at_seconds}`. `opens_with: exit` skips the Keyframe start-frame hold from #26. Optional `characters` carry `wardrobe` and an author-supplied `references` list (`path` or `mediaObjectId`, `role`, `declares`, `scope`, `applies_to`). `scope` without `applies_to` does not scope the reference. A frame `wardrobe` overrides that character. `apply_techniques` opts a frame into a technique template. `short_beat_threshold_seconds` overrides the provider short-beat threshold. Optional `location` (`locks`, `references`), `counts`, and `locks` live on the storyboard plan. A frame `counts` entry overrides one key. A frame `cast` limits wardrobe and identity lines; `cast: []` means nobody is in frame. `characters: []` alone does not. Optional `start_frame` is `{source_take, at_seconds, asset, verified}` for a chained Keyframe shot. Optional `shot_id` labels a frame in retime and impact output. `video retime` sets `final_clock` to the sum of edit-plan out minus in and `generated_clock` to generated seconds, counting a shared clip once. `accept_clock_delta: true` on the plan accepts a non-zero script-versus-final gap. `storyboard impact` reads `takes.yaml` (`shot`, `take_id`, `source_clip`, `trim`, `observed_end_state`, optional `observed_start_state`) as OBSERVATION and does not write it back. All of these fields are optional.

Authority classes:

- `PROPOSED` for creative outputs and change suggestions
- `OBSERVATION` for recorded evidence
- `NOT_COMPUTABLE` when evidence or continuity is insufficient
- authoritative promotion only by an explicitly authorized human or canonical system

Core law:

> A symbol should alter how a scene is interpreted without requiring the audience
> to consciously identify it.

Preferred sequence:

`observed form → association → recurrence under pressure → mutation → convergence with choice → residue`

Reject:

`named concept → decorative iconography → explanation → fixed meaning`

The three channels are diegetic form, dramaturgical choice, and cinematic
technique. A motif gains force by crossing channels without explanation.

## Procedure

1. **Classify the request.** Determine intent, scope, format, audience, production
   constraints, cultural context, canon status, and desired transformation.
   Done when the request is one cinematic job, not film trivia or general writing.
2. **Record observed facts.** Separate materially present evidence from inference.
   Done when every material claim is labeled observed, inferred, or speculative.
3. **Define dramatic pressure.** State what must change, who resists it, and why
   the change matters. Hidden architecture never replaces causality.
   Done when the scene has a pressure statement the audience can feel.
4. **Read local continuity first.** Use `read_file` on project ledgers and locked
   facts before corpus retrieval. Preserve identity, chronology, ownership,
   material memory, and residue.
   Done when locked facts are listed before any new invention.
5. **Retrieve only when useful.** Rank patterns by dramatic problem, state change,
   exclusions, collisions, feasibility, mutation potential, provenance, and stable
   ID. Default to one governing grammar, zero to two supporting patterns, and one
   to two convergence sites.
   Done when retrieval is skipped or the receipt names a stable pattern ID.
6. **Build the private graph.** Use observed forms as nodes and pressure or
   transformation as edges. Keep geometry, function, and attributes disentangled
   until a declared convergence site.
   Done when the graph has observable nodes and no unexplained named esoterica.
7. **Translate to observable cinema.** Express the private graph through behavior,
   blocking, objects, material, rhythm, sound, framing, movement, and light. Do
   not expose pattern IDs, lexicon links, or named esoterica to the audience.
   Done when audience-facing text contains only observable constraints.
8. **Propagate storyboard state.** Carry object, owner, light, material,
   convergence, and residue state frame to frame. Reject unexplained
   disappearance or reset. When you emit frame or storyboard images, include
   `[[as_document]]` in that response.
   Done when each frame transition is evidenced and image files are attached.
9. **Adapt downstream.** Provider adapters may change syntax, not graph identity,
   ownership, required objects, geometry, state change, residue, continuity, or
   negative constraints. Fail closed when a critical invariant cannot be
   represented.
   Done when the preservation report has no critical semantic loss.
10. **Run visual QA.** Normalize observations, compare expected and observed state
    by dimension, preserve passing dimensions, and correct only mismatches. Stop
    bounded loops when progress stalls or a critical dimension regresses.
    Done when every compared dimension is pass, corrected, or `NOT_COMPUTABLE`.
11. **Emit the minimum useful artifacts.** Common artifacts include a motif
    registry, motif lifecycle, graph, cinematic encoding, project ledger,
    retrieval receipt, storyboard state, provider packet, visual differential,
    correction receipt, revision delta, or production handoff.
    Done when each artifact has a path and a stated purpose.
12. **Label evidence and authority.** Use `OBSERVED`, `INFERRED`, or `SPECULATIVE`
    at the claim level where useful. Ordinary execution never promotes canon,
    increases corpus confidence, or overwrites authoritative Forge state.
    Done when outputs remain `PROPOSED` unless explicit authority was provided.
13. **Return safe failure.** Weak evidence, schema drift, unresolved collisions,
    missing boundaries, or contradictory continuity produce `NOT_COMPUTABLE` with
    a structured reason and the smallest next action that could resolve it.
    Done when failure names the blocker instead of inventing evidence.

For deeper rules, load only the reference needed for the task with `read_file` or
`skill_view`:

- `references/hermes-runtime-contract.md` for execution and authority
- `references/anti-slop-patterns.md` for diagnostic gates
- `references/continuity.md` for screenplay and project continuity
- `references/hermes-storyboard-state.md` for multi-frame state
- `references/hermes-model-adapters.md` for provider translation
- `references/hermes-visual-qa.md` for differential correction
- `references/corpus-usage.md` for retrieval and cultural boundaries
- `references/design-specification-compiler.md` for design compilation
- `references/continuity-forge-integration.md` for optional handoff

## Pitfalls

- Do not force symbolic machinery onto an unrelated or purely informational request.
- Do not use named symbolism, occult collage, decorative archetypes, or one-to-one
  correspondences as a substitute for action and consequence.
- Do not let every object carry equal symbolic weight. Preserve negative space.
- Do not retrieve patterns merely because the corpus exists.
- Do not allow more than two high-density convergence sites without explicit need.
- Do not silently change locked facts, graph identity, ownership, chronology, or
  residue during revision or provider adaptation.
- Do not reset motif state between storyboard frames without an evidenced transition.
- Do not treat MCP, Forge, or provider APIs as prerequisites. `compile` requires PyYAML and jsonschema.
- Do not mutate references, confidence, or canonical authority from creative commands.
- Do not invent evidence to avoid `NOT_COMPUTABLE`.
- Do not preview frame or storyboard images as crushed inline bubbles. Attach them
  with `[[as_document]]`.
- Platform note: the creative CLI is stdlib Python on linux, macos, and windows.
  POSIX install uses `install.sh`; Windows install uses `install.ps1`.

## Verification

Before returning work, verify the requirements that apply:

- Dramatic causality remains legible without explaining the symbolic system.
- Every important motif changes under pressure and leaves observable residue.
- Locked facts, ownership, chronology, and continuity are preserved or explicitly
  changed in a revision delta.
- Storyboard frames pass declared transition rules with no unexplained reset.
- Provider preservation reports contain no critical semantic loss.
- Audience-facing output contains observable constraints, not private graph labels.
- Claims distinguish observed evidence from inference and speculation.
- Outputs are proposal-only unless explicit authority was provided.
- Failure states use stable diagnostics and `NOT_COMPUTABLE` instead of invention.
- Frame and storyboard image responses include `[[as_document]]`.

Run deterministic checks through `terminal` when scripts or artifacts were used:

```text
terminal(command="python3 ${HERMES_SKILL_DIR}/scripts/kubrick.py do check --action smoke", timeout=120)
terminal(command="python3 ${HERMES_SKILL_DIR}/scripts/kubrick.py do check --action repeatability", timeout=180)
terminal(command="python3 ${HERMES_SKILL_DIR}/scripts/kubrick.py do check --action eval", timeout=300)
```

A valid delivery states what was produced, what was preserved, what was not
computable, and which optional integration or human authority is required next.

Current release context: `docs/ROADMAP-v0.22.md` and
`docs/RELEASE-NOTES-v0.22.md`.

Source, profile, and migration rules: `references/source-and-upgrades.md`.

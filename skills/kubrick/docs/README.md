# Kubrick Documentation

Current release: **0.16.0** (see root `VERSION`).

## Start here

| Doc | Audience | Purpose |
|---|---|---|
| [`../README.md`](../README.md) | Everyone | Public overview, install, architecture |
| [`../QUICKSTART.md`](../QUICKSTART.md) | Operators | Intent-first command workflows + recipes |
| [`../SKILL.md`](../SKILL.md) | Hermes runtime | Canonical skill operating contract |
| [`../AGENTS.md`](../AGENTS.md) | Agents | Multi-agent SDLC contract (`CLAUDE.md` is a thin pointer here) |
| [`CONTINUITY.md`](CONTINUITY.md) | Operators | Carrier order: start image, references, end image, prompt |
| [`../intent/README.md`](../intent/README.md) | Agents | Intent template for non-trivial work; then spec.md / plan |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Contributors | Dev setup, hub sync, invariants |
| [`HERMES-OFFICIAL-SUBMISSION.md`](HERMES-OFFICIAL-SUBMISSION.md) | Maintainers | Official optional-skills PR + community publish checklist |
| [`OPENCLAW.md`](OPENCLAW.md) | OpenClaw users | OpenClaw Agent Skill edition (Prabu; branch `openclaw`) |
| [`ISSUE-TRIAGE.md`](ISSUE-TRIAGE.md) | Maintainers | Open-issue close/keep recommendations |
| [`archive/`](archive/) | Everyone | Historical roadmaps and shipped plans |

## Runtime editions

| Edition | Branch | Notes |
|---|---|---|
| **Hermes** | [`main`](https://github.com/scrimshawlife-ctrl/Kubrick/tree/main) | Canonical Hermes skill; deterministic v0.16 contract |
| **OpenClaw** | [`openclaw`](https://github.com/scrimshawlife-ctrl/Kubrick/tree/openclaw) | Agent Skill packaging by **Prabu** ([PR #1](https://github.com/scrimshawlife-ctrl/Kubrick/pull/1)); external state dir; doctor / portability tests |

See [`OPENCLAW.md`](OPENCLAW.md) for install commands, credit, and what differs between editions.

## Operator surface (intent router)

Primary CLI (Hermes + humans):

```bash
python scripts/kubrick.py do <intent> [--action <action>] [flags]
```

**15 intents:** `adapt` · `bundle` · `check` · `compile` · `design` · `image` · `learn` · `ledger` · `mcp` · `operate` · `retrieve` · `script` · `storyboard` · `video` · `visual`

| Doc | Purpose |
|---|---|
| [`FIRST-CLASS-PRODUCTION-SURFACES.md`](FIRST-CLASS-PRODUCTION-SURFACES.md) | Design / script / image / video surface contracts |
| [`JEV-PRE-SPEND-GATE.md`](JEV-PRE-SPEND-GATE.md) | Hold-list check before `video runbook` and `video cues` spend |
| [`runbook-spend-safety.md`](runbook-spend-safety.md) | One node per call, `-32001` reconcile, billed-rate quotes, Jev timeout |
| [`scoped-holds.md`](scoped-holds.md) | Location, shot, and view scope, rear wording, and per-hold verdicts |
| [`archive/superpowers/specs/2026-07-30-operator-intent-router-design.md`](archive/superpowers/specs/2026-07-30-operator-intent-router-design.md) | Design: intents, aliases, UX, MCP (archived) |
| [`archive/superpowers/plans/2026-07-30-operator-intent-router.md`](archive/superpowers/plans/2026-07-30-operator-intent-router.md) | Implementation plan (archived) |
| [`../scripts/intent_router.py`](../scripts/intent_router.py) | Registry + resolve + help |
| [`../QUICKSTART.md`](../QUICKSTART.md) | Human recipes and examples |

Legacy flat command names remain soft aliases. MCP exposes a single tool: `kubrick_do`.

## Current release (v0.16)

| Doc | Purpose |
|---|---|
| [`ROADMAP-v0.16.md`](ROADMAP-v0.16.md) | Shipped scope + next priorities |
| [`RELEASE-NOTES-v0.16.md`](RELEASE-NOTES-v0.16.md) | What landed in 0.16.0 |
| [`RELEASE-CHECKLIST-v0.16.md`](RELEASE-CHECKLIST-v0.16.md) | Release gates and tag procedure |
| [`ARCHITECTURE-v0.16.md`](ARCHITECTURE-v0.16.md) | Production engine + surface architecture |
| [`DELIVERABLES-v0.16.md`](DELIVERABLES-v0.16.md) | Deliverable inventory for 0.16 |

## Historical release docs

Archived under [`archive/`](archive/) (see [`archive/README.md`](archive/README.md)):

| Doc | Notes |
|---|---|
| [`archive/releases/ROADMAP-v0.15.md`](archive/releases/ROADMAP-v0.15.md) (+ notes/checklist) | v0.15 hardening + surfaces prelude |
| [`archive/releases/ROADMAP-v0.14.md`](archive/releases/ROADMAP-v0.14.md) (+ notes/checklist) | v0.14 shipped scope |
| [`archive/releases/ROADMAP-v0.13.md`](archive/releases/ROADMAP-v0.13.md) (+ notes/checklist) | v0.13 Wave 2/3 and router context |
| [`archive/releases/ROADMAP-v0.12.md`](archive/releases/ROADMAP-v0.12.md) (+ notes/checklist) | v0.12 compiler / storyboard / outcome learning |
| [`archive/releases/ROADMAP-v0.11.md`](archive/releases/ROADMAP-v0.11.md) | Original Wave 1–3 production-hardening plan |

## Reference contracts

| Doc | Purpose |
|---|---|
| [`../references/hermes-runtime-contract.md`](../references/hermes-runtime-contract.md) | Runtime, artifacts, dependencies, canon |
| [`../references/hermes-model-adapters.md`](../references/hermes-model-adapters.md) | Neutral packet + provider adapters |
| [`../references/hermes-visual-qa.md`](../references/hermes-visual-qa.md) | Observation, fidelity, correction loop |
| [`../references/hermes-storyboard-state.md`](../references/hermes-storyboard-state.md) | Multi-frame state propagation |
| [`../references/hermes-graph-operators.md`](../references/hermes-graph-operators.md) | Graph construction operators |
| [`../references/continuity-forge-integration.md`](../references/continuity-forge-integration.md) | Forge handoff + multi-signal feedback |
| [`../references/design-specification-compiler.md`](../references/design-specification-compiler.md) | Design-spec compiler |
| [`../references/retrieval-and-continuity.md`](../references/retrieval-and-continuity.md) | Retrieval discipline |
| [`../references/anti-slop-patterns.md`](../references/anti-slop-patterns.md) | Anti-slop gates |

## Schemas

| Schema | Purpose |
|---|---|
| `schemas/forge-signal-bundle.schema.yaml` | Multi-signal Forge observation bundle |
| `schemas/multi-signal-evolution-receipt.schema.yaml` | Deterministic evolution receipt |
| `schemas/design-specification.schema.yaml` | Governed design specification |
| `schemas/project-symbolic-ledger.schema.yaml` | Project ledger (+ pattern history) |
| `schemas/pattern-evolution-proposal.schema.yaml` | Proposal-only evolution (+ review gates) |

Full schema set: [`../schemas/`](../schemas/).

## Examples and fixtures

| Path | Purpose |
|---|---|
| `examples/authority-transfer-storyboard/` | Canonical three-frame storyboard |
| `examples/production-surfaces/` | First-class design/script/image/video examples |
| `references/examples/forge-signals/` | Forge multi-signal extraction fixture |
| `references/patterns/contemporary/cultural-signal-packs/` | Time-sensitive cultural packs |
| `templates/design-specification.yaml` | Design-spec template |

## Verification commands

```bash
python scripts/kubrick.py do check --action smoke
python scripts/kubrick.py do check --action skill
python scripts/check_hub_sync.py
python scripts/test_surface_compilers.py
python scripts/test_cross_surface.py
python scripts/audit_release_version.py --strict
```

# Kubrick documentation

Current product version: **0.27.0** (`VERSION`). The production envelope schema
id stays `0.16.0`.

## Start here

| Doc | Audience | Purpose |
|---|---|---|
| [`../README.md`](../README.md) | Everyone | Hero, tags, tokens, atlas, roadmap |
| [`../src/kubrick/`](../src/kubrick/) | Contributors | Production packages; `scripts/` entries load them |
| [`../QUICKSTART.md`](../QUICKSTART.md) | Operators | Intent-first workflows |
| [`../SKILL.md`](../SKILL.md) | Hermes runtime | Skill operating contract |
| [`../AGENTS.md`](../AGENTS.md) | Agents | Agent contract (`CLAUDE.md` points here) |
| [`../CHANGELOG.md`](../CHANGELOG.md) | Everyone | Release notes |
| [`ROADMAP.md`](ROADMAP.md) | Everyone | Current roadmap and project board |
| [`RELEASE-CHECKLIST.md`](RELEASE-CHECKLIST.md) | Maintainers | Standing release gate |
| [`CONTINUITY.md`](CONTINUITY.md) | Operators | Carrier order |
| [`TAKE-QC.md`](TAKE-QC.md) | Operators | Fixture take QC and full checks |
| [`BOARD-GATE.md`](BOARD-GATE.md) | Operators | Board checks before video spend |
| [`BOARD-VISION-SETUP.md`](BOARD-VISION-SETUP.md) | Operators | Board image judge setup and the vision adapter contract |
| [`BOARD-IMAGE-CALIBRATION.md`](BOARD-IMAGE-CALIBRATION.md) | Maintainers | EP-01 calibration and how to rerun it |
| [`FRAMING.md`](FRAMING.md) | Operators | Numeric framing and the end-image limit |
| [`REF-PACK.md`](REF-PACK.md) | Operators | Shared character reference packs |
| [`RETAKE.md`](RETAKE.md) | Operators | Retake recommendations and fixture SFX |
| [`FILM-GRAMMAR.md`](FILM-GRAMMAR.md) | Operators | Film-grammar registry 1.1.0 |
| [`CORPUS.md`](CORPUS.md) | Operators | Symbolic corpus and retrieval floor |
| [`../intent/README.md`](../intent/README.md) | Agents | Intent, then spec or plan |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Contributors | Dev setup and hub sync |
| [`HERMES-OFFICIAL-SUBMISSION.md`](HERMES-OFFICIAL-SUBMISSION.md) | Maintainers | Official catalog checklist (owner-gated) |
| [`OPENCLAW.md`](OPENCLAW.md) | OpenClaw users | `openclaw` branch |
| [`ISSUE-TRIAGE.md`](ISSUE-TRIAGE.md) | Maintainers | Open-issue close/keep recommendations |
| [`archive/`](archive/) | Everyone | v0.11–v0.23 release sets |

## Runtime editions

| Edition | Branch | Notes |
|---|---|---|
| **Hermes** | [`main`](https://github.com/Zero-State-LLC/Kubrick/tree/main) | Canonical skill, product version 0.27.0 |
| **OpenClaw** | [`openclaw`](https://github.com/Zero-State-LLC/Kubrick/tree/openclaw) | Packaging by **Prabu**; external state dir |

## Operator surface

```bash
python scripts/kubrick.py do <intent> [--action <action>] [flags]
```

**16 intents:** `adapt` · `bundle` · `check` · `compile` · `design` · `image` · `learn` · `ledger` · `mcp` · `operate` · `retrieve` · `script` · `storyboard` · `video` · `visual` · `wizard`

| Doc | Purpose |
|---|---|
| [`FIRST-CLASS-PRODUCTION-SURFACES.md`](FIRST-CLASS-PRODUCTION-SURFACES.md) | Design, script, image, and video contracts |
| [`JEV-PRE-SPEND-GATE.md`](JEV-PRE-SPEND-GATE.md) | Hold-list check before video spend |
| [`runbook-spend-safety.md`](runbook-spend-safety.md) | One node per call, `-32001` reconcile, billed-rate quotes, Jev timeout |
| [`scoped-holds.md`](scoped-holds.md) | Location, shot, and view scope, rear wording, and per-hold verdicts |
| [`ARCHITECTURE-v0.16.md`](ARCHITECTURE-v0.16.md) | Historical production-engine note (envelope id 0.16.0) |
| [`../scripts/intent_router.py`](../scripts/intent_router.py) | Registry, resolve, and help |
| [`../QUICKSTART.md`](../QUICKSTART.md) | Recipes |

## Reference contracts

| Doc | Purpose |
|---|---|
| [`../references/hermes-runtime-contract.md`](../references/hermes-runtime-contract.md) | Runtime, artifacts, dependencies |
| [`../references/hermes-model-adapters.md`](../references/hermes-model-adapters.md) | Neutral packet and adapters |
| [`../references/hermes-visual-qa.md`](../references/hermes-visual-qa.md) | Observation and correction |
| [`../references/hermes-storyboard-state.md`](../references/hermes-storyboard-state.md) | Multi-frame state |
| [`../references/continuity-forge-integration.md`](../references/continuity-forge-integration.md) | Forge handoff |
| [`../references/design-specification-compiler.md`](../references/design-specification-compiler.md) | Design-spec compiler |
| [`../references/retrieval-and-continuity.md`](../references/retrieval-and-continuity.md) | Retrieval discipline |
| [`../references/corpus-usage.md`](../references/corpus-usage.md) | Corpus retrieval rules |
| [`../references/anti-slop-patterns.md`](../references/anti-slop-patterns.md) | Anti-slop gates |

Schemas: [`../schemas/`](../schemas/). Examples: [`../examples/`](../examples/).

## Verification

```bash
python scripts/kubrick.py do check --action smoke
python scripts/validate_hermes_skill.py
python scripts/check_hub_sync.py
python scripts/check_doc_links.py
python scripts/audit_release_version.py --strict
```

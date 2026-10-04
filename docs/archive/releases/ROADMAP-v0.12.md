# Kubrick v0.12 Status and Continuation Roadmap

## Current state

> **Superseded for planning:** current status lives in [`ROADMAP-v0.13.md`](ROADMAP-v0.13.md). This document is retained as historical v0.12 context.

Kubrick v0.12 is a CI-verified standalone Hermes symbolic compiler. The complete local pipeline now covers deterministic retrieval, private graph construction, structured audit, storyboard continuity, provider adaptation, visual QA, correction governance, outcome receipts, proposal-only evolution, and repeatability verification.

## Completed

- Unified `kubrick` CLI and compiler.
- Schema validation for graph, storyboard, adapter, observation, fidelity, correction, outcome, evolution, and iteration artifacts.
- Canonical three-frame storyboard example.
- Storyboard state propagation and transition diagnostics.
- Neutral model-adapter contract and Grok Imagine adapter.
- Structured visual observations and targeted correction packets.
- Bounded correction-loop governance.
- Pattern-use observations and human-reviewed evolution proposals.
- Stable-output repeatability checks in CI.

## Release reconciliation still required

- Align `SKILL.md`, README, changelog, compiler metadata, and corpus metadata to the authoritative `VERSION` file.
- Verify README and QUICKSTART commands directly in CI.
- Validate installation from a clean copied Hermes skill directory.
- Complete `docs/archive/releases/RELEASE-CHECKLIST-v0.12.md`.
- Create and publish the `v0.12.0` tag only after those gates pass.

## Post-v0.12 priorities

**Completed in v0.13:** Flux/SD3/Midjourney adapters, MCP/CLI operators, Forge multi-signal feedback, multi-signal evolution, first-class ledgers, closed-loop differential QA, contemporary cultural-signal packs. See `docs/archive/releases/ROADMAP-v0.13.md`.

Remaining:
1. Add video adapters as syntax-only translations over the neutral packet.
2. Add optional vision-provider normalizers while retaining manual and generic JSON observation paths.
3. Add privacy-preserving cross-project analytics from approved outcome receipts.
4. Expand the executable corpus only with provenance, misuse risks, mutation requirements, production-cost analysis, and regression coverage.

## Invariants

- Weak evidence returns `NOT_COMPUTABLE`.
- Audience output exposes observables, not private symbolic semantics.
- Local artifacts remain `PROPOSED`.
- Outcome receipts remain observations.
- Evolution proposals never apply automatically.
- External providers, MCP, and Continuity Forge remain optional.

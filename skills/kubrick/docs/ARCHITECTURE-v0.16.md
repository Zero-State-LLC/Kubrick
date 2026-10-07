# Kubrick v0.16: First-Class Production Surfaces

Status: **IMPLEMENTED**  
Target: **v0.16.0**  
Scope: Hermes `main` (OpenClaw parity tracked separately)

## Implementation order (done)

1. Shared production engine (`scripts/production_engine.py`)
2. Design surface first (create/improve/audit/validate/expand/summarize/…)
3. Script promoted to first-class surface (create/rewrite/continuity/handoff/…)
4. Image + video on the same engine (prompt/adapt/shot/sequence/…)
5. Unified QA + receipt system (`qa` on every surface, `kubrick receipts`)
6. CLI sugar, docs, and phased regression (`scripts/test_v016_phased_acceptance.py`)

## Architecture summary

Four peer surfaces (**design**, **script**, **image**, **video**) share one
canonical execution lifecycle:

```text
ProductionRequest
    → ProductionValidator
    → surface compiler (domain)
    → ProductionArtifact + ProductionReceipt
    → ProductionResult
```

Implementation:

| Component | Module |
|---|---|
| Engine types + lifecycle | `scripts/production_engine.py` |
| CLI/runtime adapter | `scripts/production_surface.py` |
| Domain compilers | `scripts/surface_compilers.py` |
| Provider capabilities | `scripts/provider_capabilities.py` |
| Receipt listing | `scripts/list_receipts.py` |

No parallel orchestration systems. Existing `compile` / `adapt` / `storyboard` /
`visual` workflows remain available through compatibility aliases.

## CLI

```bash
# Intent form (canonical)
kubrick do design --action create --brief brief.yaml --output design.md
kubrick do script --action create --brief brief.yaml --format fountain
kubrick do image --action prompt --brief brief.yaml --provider generic
kubrick do video --action shot --brief brief.yaml --output shot.yaml

# Sugar (v0.16)
kubrick design create --brief brief.yaml --output design.md
kubrick script qa --input script.md
kubrick qa image --input packet.json --evidence "observation text"
kubrick receipts --root out/surfaces

# Artifact tree
kubrick do design --action create --brief brief.yaml \
  --artifact-root out/prod --output out/prod/design.md
```

## Shared QA

Every surface exposes `qa`:

- `design qa`: missing sections, provider coupling, reconcile signals
- `script qa`: diagnosis + continuity
- `image qa`: observation overlap
- `video qa`: motion/timing/camera/physics/identity/end-state dimensions

## Artifact layout

When `--artifact-root` is set, the engine writes:

```text
receipts/   artifacts/   reports/   validation/
qa/         timeline/    references/  metadata/
```

Each receipt includes timestamp, surface, version, inputs, outputs, warnings,
validation, and `receipt_hash`.

## Migration from v0.15 foundation

1. Foundation stubs (`implementation_state: FOUNDATION`) are replaced by domain compilers.
2. `design build` remains an alias of `design create`.
3. Provider adapters remain internal dependencies of `image adapt` / `video adapt`.
4. Schema version on new envelopes is `0.16.0`.

See also: `docs/FIRST-CLASS-PRODUCTION-SURFACES.md`, `examples/production-surfaces/`.

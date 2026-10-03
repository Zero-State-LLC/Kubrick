# Kubrick v0.22 Status and Continuation Roadmap

## In progress (#80)

Corpus hygiene: every sidecar is indexed, registered, and manifested. Duplicate sidecars are merged, dead lexicon links are repaired, fixture models stay out of production capabilities, and the coverage audit fails closed in CI.

## Shipped

- Full CI with coverage floor and clean-tree check (#61)
- Project-local retrieval artifacts (#62)
- Manifest dependency gate and `check deps` (#65)
- MCP size cap, pre-spawn allow-list, and timeout (#66)
- Reference cap and native-audio checks (#67)
- Dead-code cleanup and fail-closed frame comparison (#68)
- Lint ratchet, shared helpers, and the surface compiler split (#72)
- Multi-shot sequence adapt (#63)
- Take selection by id (#64)
- Retake runbook, cut QA, and cue sheet prep (#69, #70, #71)

## Next

1. Retime model-overlay limits (needs its own intent).
2. Remove the `skills/kubrick` mirror once hub packaging allows it (owner-gated).
3. Land the official Hermes optional-skills submission against the current release.

## In progress (#76)

Retrieval ignores stop-words in token overlap and registry route matching. `SELECTED` requires dramatic fit of at least 0.15. Weaker evidence stays `NOT_COMPUTABLE` with `LOW_DRAMATIC_FIT`.

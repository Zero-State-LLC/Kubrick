# Kubrick v0.22 Status and Continuation Roadmap

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

## Superseded

Issues #76–#82 shipped in v0.23.0. See `docs/ROADMAP-v0.23.md`.

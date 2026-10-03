# Kubrick v0.20 Status and Continuation Roadmap

## Shipped

- Reference scope and the binding line (#33)
- Location-reference lint, count locks, and explicit empty cast (#34)
- Lock carriers and the negative-only warning (#35)
- Proposed retime plan and clock-delta sign-off (#36)
- Take ledger impact, observations never written back (#37)
- Start-frame asset gate and the ffmpeg handoff string (#38)

## Next

Phase B is the same branch, not this release:

1. #39: known-drift registry, model-keyed and dated.
2. #40: audio lock, per-character voice, and speech lint.
3. #41: screen direction and handedness.
4. #42: model-keyed capabilities with source and verified-on dates.
5. #43: structured multi-shot prompt blocks.
6. #44: spend plan, pre-spend credit estimate, budget cap, and retry-guard handoff.

Still open from v0.19.0:

1. Apply CI workflow hardening once a token with `workflow` scope is available (`docs/ci/`).
2. Land official Hermes optional-skills submission against the current release.
3. Keep the OpenClaw edition aligned with the Hermes edition after v0.20.0.

# Kubrick v0.17 Status and Continuation Roadmap

## Shipped

- Shared production engine and first-class surface lifecycle
- Expanded design/script/image/video actions + shared QA/receipts
- Cinematic project state helper and expanded v0.17 golden fixtures
- Architecture and deliverables docs for v0.17
- OpenClaw remote parity verified (`origin/openclaw` @ `db695bc`)

## Next

1. Apply CI workflow hardening once a token with `workflow` scope is available (`docs/ci/`).
2. Land official Hermes optional-skills submission against v0.17.0.
3. Port expanded goldens to the OpenClaw edition and keep editions aligned.
4. Raise pytest-cov toward release gates; add adversarial surface goldens as needed.

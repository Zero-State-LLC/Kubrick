# Kubrick v0.16 Status and Continuation Roadmap

## Shipped

- Shared production engine and first-class surface lifecycle
- Expanded design/script/image/video actions + shared QA/receipts
- Cinematic project state helper and expanded v0.16 golden fixtures
- Architecture and deliverables docs for v0.16
- OpenClaw remote parity verified (`origin/openclaw` @ `db695bc`)

## Next

1. Apply CI workflow hardening once a token with `workflow` scope is available (`docs/ci/`).
2. Land official Hermes optional-skills submission against v0.16.0.
3. Port expanded goldens to the OpenClaw edition and keep editions aligned.
4. Raise pytest-cov toward release gates; add adversarial surface goldens as needed.

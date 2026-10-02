# Kubrick v0.18 Status and Continuation Roadmap

## Shipped

- Prompt fidelity: per-shot state, de-duplicated clauses, character-lock positives
- Keyframe `create_movie` adapter (3–60 seconds per shot)
- Runtime dependencies for `compile` (PyYAML, jsonschema)
- Release-version audit across product surfaces, including the hub mirror
- Brief-layer check that names a repeated multi-word phrase and both layers

## Next

1. Apply CI workflow hardening once a token with `workflow` scope is available (`docs/ci/`).
2. Land official Hermes optional-skills submission against the current release.
3. Keep the OpenClaw edition aligned with the Hermes edition after v0.18.0.

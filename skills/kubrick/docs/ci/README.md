# CI

Active workflow: [`.github/workflows/hermes-evals.yml`](../../.github/workflows/hermes-evals.yml).

`hermes-evals.hardened.yml` in this directory is the same hardened definition kept as a
docs-side reference copy (useful if a future edit must land without the `workflow`
OAuth scope). Prefer editing the live workflow under `.github/workflows/` and keeping
this file in sync.

Hardening includes:

- stdlib surface / io / cross-surface tests on ubuntu (Python 3.10–3.14; no hosted macOS/Windows)
- `requirements-ci.txt` installs for validation-eval
- hub-sync gate (`scripts/check_hub_sync.py`)
- `dev-static` job: ruff + mypy + pytest on core modules

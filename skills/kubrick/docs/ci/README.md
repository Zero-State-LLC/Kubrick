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

## Removed workflows (#82)

`codeql.yml` and `pages.yml` were removed. Neither can go green without a repository setting change, and this change does not turn those settings on.

CodeQL uploads its results to the code-scanning API. That call returns 403 while Code Security is disabled. The runs from 2026-08-15 through 2026-08-21 failed that way. Scanning stays on [`.github/workflows/free-security-scan.yml`](../../.github/workflows/free-security-scan.yml), which runs `scripts/security-scan.sh` and does not use the code-scanning API.

Pages publishes a `site/` directory through the `github-pages` environment. This repo has no `site/` tree, so the artifact upload fails, and turning Pages on is a repository setting. The run on 2026-09-04 failed. Nothing replaced that workflow.

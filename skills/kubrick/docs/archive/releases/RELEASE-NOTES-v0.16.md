# Kubrick v0.16.0 Release Notes

v0.16.0 promotes first-class production surfaces onto a shared production engine
with validate→compile→receipt lifecycle, expanded surface actions, and golden
fixtures.

## Highlights

- Canonical `scripts/production_engine.py` shared types and lifecycle
- Expanded design / script / image / video actions through one engine
- Shared QA sugar (`kubrick qa`), receipts listing, artifact tree writer
- `scripts/cinematic_project_state.py` + `evals/golden/v016/` fixtures
- Docs: `docs/ARCHITECTURE-v0.16.md`, `docs/DELIVERABLES-v0.16.md`

## Upgrade notes

- Prefer surface CLIs (`kubrick design|script|image|video|qa|receipts`) over
  ad-hoc compiler calls; envelopes now declare `schema_version: 0.16.0`.
- Re-run `bash scripts/sync_hub_skill.sh` after local edits before committing.
- OpenClaw edition tracks separately on branch `openclaw`; see
  `docs/OPENCLAW-ALIGNMENT.md`.

# Kubrick v0.17.1 Release Notes

v0.17.1 aligns the Hermes skill contract with Hermes Agent v0.21.0
(tag v2026.8.31, Pantheon). The 0.17.0 production-surface CLI is unchanged.

## Patch notes

- `SKILL.md` frontmatter includes name, description, version, author, license,
  platforms, `metadata.hermes.tags`, and `metadata.hermes.related_skills: []`.
- Body order is intro, When to Use, Prerequisites, How to Run, Quick Reference,
  Procedure, Pitfalls, Verification.
- Invoke `scripts/kubrick.py` through the Hermes `terminal` tool and
  `${HERMES_SKILL_DIR}`.
- Frame and storyboard images use the `[[as_document]]` attachment directive.
- Author is `Daniel Meyer (scrimshawlife-ctrl), Hermes Agent`. License stays MIT.

# Kubrick v0.17.0 Release Notes

v0.17.0 promotes first-class production surfaces onto a shared production engine
with validate→compile→receipt lifecycle, expanded surface actions, and golden
fixtures.

## Highlights

- Canonical `scripts/production_engine.py` shared types and lifecycle
- Expanded design / script / image / video actions through one engine
- Shared QA sugar (`kubrick qa`), receipts listing, artifact tree writer
- `scripts/cinematic_project_state.py` + `evals/golden/v016/` fixtures
- Docs: `docs/ARCHITECTURE-v0.17.md`, `docs/DELIVERABLES-v0.17.md`

## Upgrade notes

- Prefer surface CLIs (`kubrick design|script|image|video|qa|receipts`) over
  ad-hoc compiler calls; envelopes now declare `schema_version: 0.17.0`.
- Re-run `bash scripts/sync_hub_skill.sh` after local edits before committing.
- OpenClaw edition tracks separately on branch `openclaw`; see
  `docs/OPENCLAW-ALIGNMENT.md`.

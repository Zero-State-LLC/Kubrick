# Release checklist: v0.17.1

- [x] VERSION / manifest / SKILL / pyproject / README / CHANGELOG aligned to v0.17.1
- [x] Hermes Agent v0.21.0 SKILL.md contract (frontmatter, body order, terminal, as_document)
- [x] Release notes, roadmap, and checklist present for v0.17
- [x] Production engine + surface acceptance tests present
- [x] Golden fixtures under `evals/golden/v016/` (expanded surface coverage)
- [x] Hub sync gate path (`bash scripts/sync_hub_skill.sh`)
- [x] OpenClaw branch parity confirmed on remote `openclaw` (`db695bc`; smoke/doctor/phased/golden PASS)
- [ ] Official Hermes PR refreshed against v0.17.1
- [ ] CI workflow hardening applied (requires `gh auth refresh -s workflow`; see `docs/ci/`)

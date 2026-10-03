# Release checklist — v0.19.0

- [x] VERSION / manifest / SKILL / pyproject / README / CHANGELOG aligned to v0.19.0
- [x] Release notes, roadmap, and checklist present for v0.19.0
- [x] `audit_release_version.py --strict` covers the hub mirror and envelope schema id `0.16.0`
- [x] Shot prep for issues #25–#31 is covered by `scripts/test_shot_plan.py` and `scripts/test_continuity_locks.py`
- [x] Hub sync gate path (`bash scripts/sync_hub_skill.sh`)
- [ ] Official Hermes PR refreshed against v0.19.0
- [ ] CI workflow hardening applied (requires `gh auth refresh -s workflow`; see `docs/ci/`)

# Release checklist: v0.22.0

- [x] VERSION / manifest / SKILL / pyproject / README / CHANGELOG aligned to v0.22.0
- [x] Release notes, roadmap, and checklist present for v0.22.0
- [x] `audit_release_version.py --strict` covers the hub mirror and envelope schema id `0.16.0`
- [x] Audit upgrades #61–#72 covered by `scripts/test_audit_u*.py`
- [x] MYSLEF regression exit 0 with retime script 6.0 / final 6.0 / generated 12.0
- [x] Hub sync gate path (`bash scripts/sync_hub_skill.sh`)
- [ ] Official Hermes PR refreshed against v0.22.0

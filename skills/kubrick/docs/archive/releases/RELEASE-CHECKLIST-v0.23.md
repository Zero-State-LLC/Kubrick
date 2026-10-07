# Release checklist: v0.23.0

- [x] VERSION / manifest / SKILL / pyproject / README / CHANGELOG aligned to v0.23.0
- [x] Release notes, roadmap, and checklist present for v0.23.0
- [x] `audit_release_version.py --strict` covers the hub mirror and envelope schema id `0.16.0`
- [x] Issues #76–#82 merged as #83, #87, #88, #84, #85, #86 and closed
- [x] Full suite on merged main: pytest, every script test, evals, corpus coverage audit
- [x] MYSLEF generic and Keyframe compile exit 0; `cats and dogs` retrieve is NOT_COMPUTABLE
- [x] Hub sync gate path (`bash scripts/sync_hub_skill.sh`)
- [ ] Official Hermes PR refreshed against v0.23.0

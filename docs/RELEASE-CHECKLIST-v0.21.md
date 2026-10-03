# Release checklist — v0.21.0

- [x] VERSION / manifest / SKILL / pyproject / README / CHANGELOG aligned to v0.21.0
- [x] Release notes, roadmap, and checklist present for v0.21.0
- [x] `audit_release_version.py --strict` covers the hub mirror and envelope schema id `0.16.0`
- [x] Phase B (#39–#44) is covered by `scripts/test_phase_b.py` and `scripts/test_phase_b_locks.py`
- [x] MYSLEF example under `examples/myslef-minder/` shows drift warnings, the 186-credit estimate, `multi_shot_prompt`, the muted-native guide line, the minder syllable, and the myslef asymmetry line
- [x] Hub sync gate path (`bash scripts/sync_hub_skill.sh`)
- [ ] Official Hermes PR refreshed against v0.21.0
- [ ] CI workflow hardening applied (requires `gh auth refresh -s workflow`; see `docs/ci/`)

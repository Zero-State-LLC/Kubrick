# Release checklist — v0.20.1

- [x] VERSION / manifest / SKILL / pyproject / README / CHANGELOG aligned to v0.20.1
- [x] Release notes, roadmap, and checklist present for v0.20
- [x] Retime `final_clock` is edited runtime and `generated_clock` is reported (v0.20.1)
- [x] `audit_release_version.py --strict` covers the hub mirror and envelope schema id `0.16.0`
- [x] Phase A (#33–#38) is covered by `scripts/test_phase_a_scope.py`, `scripts/test_phase_a_locks.py`, `scripts/test_retime_plan.py`, and `scripts/test_take_ledger.py`
- [x] MYSLEF example under `examples/myslef-minder/` shows scope, location lint, carriers, retime, take impact, and the start-frame gate
- [x] Hub sync gate path (`bash scripts/sync_hub_skill.sh`)
- [ ] Official Hermes PR refreshed against v0.20.1
- [ ] CI workflow hardening applied (requires `gh auth refresh -s workflow`; see `docs/ci/`)
- [ ] Phase B issues #39–#44

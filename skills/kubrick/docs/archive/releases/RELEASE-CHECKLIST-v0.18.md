# Release checklist — v0.18.0

- [x] VERSION / manifest / SKILL / pyproject / README / CHANGELOG aligned to v0.18.0
- [x] Release notes, roadmap, and checklist present for v0.18
- [x] `audit_release_version.py --strict` covers the hub mirror and envelope schema id `0.16.0`
- [x] Installers install `requirements.txt` when PyYAML or jsonschema is missing and run the strict audit before activation
- [x] Keyframe `create_movie` schema registered in `kubrick.manifest.yaml`
- [x] Hub sync gate path (`bash scripts/sync_hub_skill.sh`)
- [ ] Official Hermes PR refreshed against v0.18.0
- [ ] CI workflow hardening applied (requires `gh auth refresh -s workflow`; see `docs/ci/`)

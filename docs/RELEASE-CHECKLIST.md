# Release checklist

Current product version: **v0.24.0**.

Release notes live in [`CHANGELOG.md`](../CHANGELOG.md). The current plan is
[`ROADMAP.md`](ROADMAP.md). Older checklists, notes, and roadmaps are under
[`archive/releases/`](archive/releases/).

- [x] `VERSION`, `kubrick.manifest.yaml`, `SKILL.md`, `pyproject.toml`, `README.md`, and `CHANGELOG.md` name v0.24.0
- [x] `docs/ROADMAP.md` and this checklist name v0.24.0
- [x] `python scripts/audit_release_version.py --strict` covers the hub mirror
- [x] Envelope schema id stays `0.16.0` and does not track the product version
- [x] `python scripts/check_doc_links.py` passes
- [ ] Official Hermes catalog submission (owner-gated; see [`HERMES-OFFICIAL-SUBMISSION.md`](HERMES-OFFICIAL-SUBMISSION.md))

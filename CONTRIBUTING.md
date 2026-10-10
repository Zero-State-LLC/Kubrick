# Contributing to Kubrick

Kubrick is a self-contained Hermes skill (with an OpenClaw edition on branch
`openclaw`). Root is the source of truth; `skills/kubrick/` is a packaging
mirror kept in sync by CI.

## Development setup

```bash
python -m pip install -r requirements-ci.txt   # optional validation + lint
python scripts/kubrick.py do check --action smoke
```

Python **3.10+**. Runtime helpers are stdlib-first; PyYAML / jsonschema are
optional for the validation profile.

Coding agents follow [`AGENTS.md`](AGENTS.md) (`CLAUDE.md` is a thin pointer
there). Non-trivial work starts with [`intent/`](intent/README.md).

## Workflow

1. Branch from `main` (Hermes) or `openclaw` (OpenClaw edition only).
2. Edit root files: not only the hub mirror.
3. Refresh the hub copy before committing skill payload changes:

   ```bash
   bash scripts/sync_hub_skill.sh
   python scripts/check_hub_sync.py
   ```

4. Run the gates that match your change:

   ```bash
   python scripts/validate_hermes_skill.py
   python scripts/audit_release_version.py --strict
   python scripts/check_doc_links.py
   python scripts/test_intent_router.py
   python scripts/test_io_safety.py
   # Surface / production work:
   python scripts/test_surface_compilers.py
   python scripts/test_cross_surface.py
   ```

5. Open a PR against the correct base (`main` or `openclaw`).

## What belongs where

| Path | Role |
|---|---|
| Root skill tree | Canonical development payload |
| `skills/kubrick/` | Hermes hub/tap mirror (must match root) |
| `docs/` | Current operator + release docs |
| `docs/archive/` | Historical roadmaps / shipped plans |
| `evals/` | Golden and adversarial fixtures |
| `.github/workflows/` | CI (see also `docs/ci/`) |

Do **not** commit ephemeral agent scratch (`PR_BODY*.md`, `PUSH_INSTRUCTIONS.md`,
local patches under `/tmp`, caches, or `out/`).

## Learnings to repo

Lessons from runs become code, tests, docs, or harness in the repo, not box-only
scripts or notes. See the rule in [`AGENTS.md`](AGENTS.md#learnings-to-repo).

## Design invariants

- Fail closed: weak or contradictory evidence → `NOT_COMPUTABLE`
- Local outputs stay **PROPOSED** until explicitly promoted
- Pattern evolution is proposal-only (never auto-apply corpus mutations)
- Audience-facing packets must not dump named esoterica by default
- Provider adapters preserve identity / facts / ownership / chronology / geometry / residue

## Docs and version bumps

When cutting a release, keep `VERSION`, `kubrick.manifest.yaml`, `SKILL.md`,
`pyproject.toml`, `CHANGELOG.md`, `docs/ROADMAP.md`, and
`docs/RELEASE-CHECKLIST.md` aligned, then run
`python scripts/audit_release_version.py --strict` and
`python scripts/check_doc_links.py`. Older release sets stay in
`docs/archive/releases/`.

## Security

See [`SECURITY.md`](SECURITY.md). Do not open issues that include secrets;
rotate first, then report.


## Licensing and contributions

This repository is licensed under the MIT License. See [`LICENSE`](LICENSE) and [`LICENSE_POLICY.md`](LICENSE_POLICY.md).

By submitting a contribution, you agree that it is licensed under the MIT License. Do not add third-party code or assets without documenting their license and preserving required notices.

# OpenClaw alignment checklist (v0.16)

Track issue: https://github.com/Zero-State-LLC/Kubrick/issues/32

Bring the permanent `openclaw` branch to Hermes `main` / v0.16 contracts without
erasing OpenClaw packaging, external state (`KUBRICK_STATE_DIR`), doctor, or overlays.

Remote tip: `origin/openclaw` (see `git log origin/openclaw -1`).

## Port these from Hermes main (v0.16)

1. `kubrick.manifest.yaml` intents (15) + recipes + schema registry (`host: openclaw`)
2. `scripts/intent_router.py` + `scripts/kubrick.py` surface sugar (`qa`, `validate`, `receipts`)
3. `scripts/io_safety.py`, MCP allowlist, diagnostics, receipt identities
4. Canonical engine: `scripts/production_engine.py`
5. Domain compilers + surfaces (`surface_compilers.py`, `*_surface.py`, `production_surface.py`)
6. Provider capabilities, cinematic project state helper, golden fixtures
7. Atomic installer invariants (validate → swap → receipt → rollback)
8. Hub packaging story (or OpenClaw-equivalent export without nested drift)

## Keep OpenClaw-specific

- Install under `~/.openclaw/skills/kubrick`
- Mutable state outside the skill package (`kubrick_paths` / `KUBRICK_STATE_DIR`)
- Native `scripts/retrieve_symbolic_patterns.py` (prohibited-pattern doctor checks)
- `doctor` / portability tests
- Agent Skill packaging frontmatter required by OpenClaw
- `.clawhubignore` / ClawHub packaging

## Acceptance

- [x] `do check --action smoke` passes on OpenClaw edition (`origin/openclaw` @ `db695bc`)
- [x] `python scripts/doctor.py`: prohibited patterns excluded
- [x] `python scripts/test_v016_phased_acceptance.py` PASS
- [x] `python scripts/test_golden_v016.py` PASS (baseline six fixtures; Hermes main may be ahead on expanded goldens)
- [ ] `pytest evals/test_openclaw_portability.py` PASS (run when pytest env available)
- [x] No silent authority promotion; `NOT_COMPUTABLE` preserved
- [x] Retrieve/state paths remain outside the skill package

## Follow-up

- Port expanded `evals/golden/v016/` fixtures from Hermes `main` when they land.
- Keep doctor-native retrieve script when merging future Hermes changes.

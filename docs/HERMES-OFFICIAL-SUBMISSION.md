# Hermes Official Submission — Kubrick

This document is the operator checklist for getting Kubrick into Nous Research’s
**official optional skills catalog** while also publishing the community path.

**Target package version:** `0.16.0` (first-class production surfaces + shared engine).

## Two publication lanes

| Lane | Command / path | Trust |
|---|---|---|
| **Official** (PR) | Merge into `NousResearch/hermes-agent` as `optional-skills/creative/kubrick` | `official` |
| **Community** (now) | GitHub repo / tap `scrimshawlife-ctrl/Kubrick` | `community` |

Pursue both: community installability first, official PR for catalog trust.

## Acceptance criteria (official optional skill)

- [x] Bounded purpose: cinematic creative production + continuity + production handoff
- [x] Explicit activation conditions in `description` + **When to Use / When Not to Use**
- [x] No private filesystem paths, API keys, or user-specific assumptions
- [x] Deterministic CLI + fail-closed `NOT_COMPUTABLE` behavior
- [x] Dependencies documented; platforms declared
- [x] Supporting scripts via `${HERMES_SKILL_DIR}`
- [x] Proprietary LicenseRef-Zero-State-Proprietary-1.0 license (not OSI-approved) + real author attribution
- [x] Provenance notes in `SKILL.md`
- [x] In-repo validators green on v0.16.0 (`skill` / `smoke` / `validate_hermes_skill` / release audit)
- [x] Package dry-run path documented (`scripts/package_optional_skill.sh`)
- [ ] Local Hermes activation test (positive) — requires local `hermes` CLI
- [ ] Local Hermes negative activation test — requires local `hermes` CLI
- [ ] Upstream PR opened against `NousResearch/hermes-agent`

## Frontmatter contract (current)

```yaml
name: kubrick
author: Daniel Meyer / Applied Alchemy Labs
license: LicenseRef-Zero-State-Proprietary-1.0
platforms: [linux, macos, windows]
metadata.hermes.category: creative
```

Stable slug: **`kubrick`** — do not rename between releases.

## v0.16 packaging highlights

Ship these in the upstream optional-skill tree:

- Shared production engine (`scripts/production_engine.py`) and domain compilers
- Surface CLI sugar: `kubrick design|script|image|video|qa|receipts|validate`
- Schemas for design/script/image/video packets + cinematic project state
- Golden fixtures under `evals/golden/v016/`
- Architecture notes: `docs/ARCHITECTURE-v0.16.md` (optional in thin first merge)

## 1. Validate in-repo

```bash
cd /path/to/Kubrick
python3 scripts/kubrick.py do check --action skill
python3 scripts/kubrick.py do check --action smoke
python3 scripts/validate_hermes_skill.py
python3 scripts/audit_release_version.py --strict
python3 scripts/test_v016_phased_acceptance.py
python3 scripts/test_golden_v016.py
bash scripts/sync_hub_skill.sh && python3 scripts/check_hub_sync.py
```

## 2. Install / sync local Hermes skill

Preferred install location for local trust:

```bash
./install.sh
# or:
rsync -a --delete \
  --exclude '.git/' --exclude '.github/' --exclude 'out/' --exclude '__pycache__/' \
  ./ ~/.hermes/skills/kubrick/
```

Avoid nested paths like `~/.hermes/skills/creative/kubrick/kubrick`.

```bash
hermes skills list | grep -i kubrick
python3 ~/.hermes/skills/kubrick/scripts/kubrick.py do check --action smoke
```

## 3. Activation tests

Positive (should load Kubrick):

```bash
hermes chat --toolsets skills -q \
  "Use the Kubrick skill to create a visual design system for a psychological science-fiction film."
```

Negative (must **not** load Kubrick):

```bash
hermes chat --toolsets skills -q \
  "Calculate the SHA-256 checksum of README.md."
```

Record activation outcomes in the upstream PR body (see template below) before opening the PR.

## Community layout note

Hermes GitHub taps default to listing skill directories under `skills/`.
This repository ships a hub-discoverable copy at:

```text
skills/kubrick/SKILL.md
```

Root-level files remain the development workspace. After editing root, refresh:

```bash
./scripts/sync_hub_skill.sh
```

## 4. Community publish (no upstream wait)

```bash
# Hub groupings (already in repo root)
# skills.sh.json → grouping title "Cinematic Design"

hermes skills publish . --to github --repo scrimshawlife-ctrl/Kubrick

# Or as a tap:
hermes skills tap add scrimshawlife-ctrl/Kubrick
hermes skills search kubrick --source github
```

## 5. Official PR packaging

```bash
gh repo fork NousResearch/hermes-agent --clone
cd hermes-agent
git checkout -b feat/add-kubrick-skill-v016

# From the Kubrick repo:
/path/to/Kubrick/scripts/package_optional_skill.sh /path/to/hermes-agent

# Verify payload
find optional-skills/creative/kubrick -maxdepth 3 -type f | sort
git diff --check
git status --short

git add optional-skills/creative/kubrick
git commit -m "feat(skills): add Kubrick cinematic design skill v0.16"
git push -u origin feat/add-kubrick-skill-v016

# Draft the PR body from the template below, then:
gh pr create \
  --repo NousResearch/hermes-agent \
  --title "feat(skills): add Kubrick cinematic design skill (v0.16)" \
  --body-file /tmp/kubrick-hermes-pr-body.md
```

### Upstream PR body template

Draft locally (do **not** commit scratch PR bodies into this repo):

```markdown
## Summary

Adds `kubrick` **v0.16.0** under `optional-skills/creative/kubrick/`.

## Why optional-skills

Specialized cinematic continuity / production handoff — useful, not default-bundled.

## Validation

- [ ] Local Hermes detection (`~/.hermes/skills/kubrick`)
- [ ] `python3 scripts/kubrick.py do check --action skill`
- [ ] `python3 scripts/kubrick.py do check --action smoke`
- [ ] `python3 scripts/audit_release_version.py --strict`
- [ ] Positive activation (cinematic / screenplay prompt)
- [ ] Negative activation (unrelated checksum prompt)

## Notes

Stdlib-first helpers; optional `pyyaml` / `jsonschema` with degraded paths.
```

### Package dry-run (no fork / no PR)

```bash
mkdir -p /tmp/hermes-agent-dry
/path/to/Kubrick/scripts/package_optional_skill.sh /tmp/hermes-agent-dry
find /tmp/hermes-agent-dry/optional-skills/creative/kubrick -maxdepth 2 -type f | head
```

After merge:

```bash
hermes skills search kubrick --source official
hermes skills install official/creative/kubrick
hermes skills inspect official/creative/kubrick
```

## Size note

Kubrick is larger than many creative optional skills (corpus + schemas + evals).
That bulk is intentional: deterministic retrieval and continuity need the corpus.
The packaging script strips git/CI/historical planning docs before the PR copy.

If review asks for a thinner first merge, keep:

- `SKILL.md`, `LICENSE`, `README.md`, `QUICKSTART.md`
- `scripts/` (or a documented core subset)
- `schemas/`, `references/` (corpus + patterns), `templates/`, `examples/`
- a reduced `evals/` smoke set (`evals/golden/v016/` + skill validators)

and leave extended historical docs in the standalone GitHub repo.

## Do not ship in the upstream tree

- `.git/`, `.github/`
- local `out/`, caches, secrets
- machine-specific install notes
- ephemeral agent scratch (`PR_BODY*.md`, `PUSH_INSTRUCTIONS.md`)
- OpenClaw-only packaging (lives on branch `openclaw` in the standalone repo)

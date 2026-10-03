# Intent

Status: accepted by Danny (repo owner) on 2026-10-03 at 00:36 PT ("First fix the bugs then run the upgrades").

Scope: GitHub issues #48–#60, the bugs B1–B13 from the read-only audit of main c027520. Product version 0.21.1.

## Problem

The audit of v0.21.0 found:
- a sequence adapt that silently drops shots;
- CI that runs a third of the test scripts behind a green no-op job;
- a script that mutates `references/`;
- an eval artifact that breaks hub sync;
- a broken `design-build` route;
- a crashable MCP server;
- a wrong dependency contract;
- a broken wizard flag;
- impact and budget checks that pass on missing evidence;
- inconsistent duration defaults;
- gaps in the MCP path guard;
- two Noema workflows that fail on every run.

## Proposed outcome

- #48 (B1): a sequence with more than one shot fails closed (`NOT_COMPUTABLE`) in `video adapt` and names the dropped shots. A single-shot sequence still adapts.
- #49 (B2): CI runs `pytest -q scripts` and every `scripts/test_*.py` script. `ci.yml` `build` does real work. A guard test fails when a `scripts/test_*.py` file is not referenced by a workflow.
- #50 (B3): `scripts/evolve_from_use.py` is removed from the skill (root and mirror) and from `REQUIRED_PATHS`. `learn evolve` stays the proposal-only path.
- #51 (B4): the corpus coverage report goes to `out/kubrick/corpus-coverage.json` (or `--output`). `references/reports/` is gitignored. Evals leave hub sync green.
- #52 (B5): `design-build` routes to `generate_design_spec.py` and renders the design-specification template. Design output names the current `VERSION`, not v0.16.
- #53 (B6): the MCP server answers malformed requests with JSON-RPC errors (-32700, -32600, -32602) and keeps serving.
- #54 (B7): routed actions that need PyYAML or jsonschema return `DEPENDENCY_MISSING` (exit 4) with the package and install command. SKILL.md prerequisites name those actions. This intent explicitly accepts that SKILL.md prerequisites edit.
- #55 (B8): `do wizard --action plan` works. Other actions are refused clearly.
- #56 (B9): impact emits `OBSERVATION_MISSING` when a compared take has no observed state, and `TAKE_AMBIGUOUS` when one shot has several takes and none is selected. Neither is a clean PROPOSED.
- #57 (B10): with `budget_cap_credits` set and a non-computable estimate, Keyframe prep fails closed with `BUDGET_CAP_UNVERIFIABLE`. Without a cap, behaviour is unchanged.
- #58 (B11): one duration helper and one default (8.0 s) are shared by shot prep, drift and retime. A missing duration emits `DURATION_MISSING`. MYSLEF output is unchanged, because every MYSLEF frame has a duration.
- #59 (B12): `--takes` and `--answers` are MCP path flags. Routed writers use the bounded writer and refuse writes into the protected skill tree.
- #60 (B13): `.github/workflows/pin-currency.yml` and `deploy-worker-pin-pr.yml` are deleted. A guard test fails if a Noema pin or deploy workflow returns.

Out of scope: the 12 audit upgrades (phase 2 PR); retime model-overlay limits (that needs its own intent); calling Keyframe, ElevenLabs or OpenRouter; writing `references/` during ordinary work; publishing the skill.

## Affected users / systems

Hermes operators (compile, video adapt and retime, storyboard impact, wizard, design-build, MCP), CI, the release audit and the hub mirror.

## Constraints / non-goals

- Root is the source of truth. Run `bash scripts/sync_hub_skill.sh`, then `python3 scripts/check_hub_sync.py`.
- Do not weaken an existing assertion to force green. A test that locked in buggy behaviour (B9) is updated to the corrected contract, and the PR says so.
- Touched Python modules stay under 500 lines with cyclomatic complexity under 22, and new code is ruff and mypy clean.
- The MYSLEF regression stays exit 0 with an unchanged retime clock.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| Each bug reproduces on c027520 | `OBSERVED` | [[Kubrick Main Audit 2026-10-03]] and issue bodies #48–#60 |
| MYSLEF frames all carry durations | `OBSERVED` | `examples/myslef-minder/storyboard-plan.yaml` |

## Author / date

- Author: Grok Bot for Danny
- Date: 2026-10-03

# Intent

Status: accepted by Danny (repo owner) on 2026-10-03 at 00:36 PT ("then run the upgrades"; implement all 12 ranked audit upgrades).

Scope: GitHub issues #61–#72, the ranked upgrades U1–U12 from [[Kubrick Main Audit 2026-10-03]]. Built on main 9372d6b (phase 1, #48–#60, merged as PR #73). Product version 0.22.0.

## Problem

Phase 1 fixed the audit bugs. The upgrades close the remaining gaps:
- CI still skips `tests/`, has no coverage floor, and never checks for a clean tree.
- Retrieval writes inside the skill tree.
- Sequence adapt fails closed instead of adapting every shot.
- Takes cannot be selected.
- Dependency checks are piecemeal.
- The MCP server has no size cap, allow-list or timeout.
- Reference caps are unenforced.
- Dead code remains.
- MYSLEF's retake planning, cut verification and audio cueing were done by hand.
- Lint debt has no ratchet.

## Proposed outcome

Delivered in two stacked PRs.

**PR A: platform (#61, #62, #65, #66, #67, #68, #72)**
- #61 CI-FULL: CI runs `pytest -q scripts tests tests_audit`, with a subprocess-aware coverage floor of 75% over `scripts/`. A step fails when `git status --porcelain` is non-empty after the suite and evals. `pygments>=2.20` is pinned and coverage added to requirements-ci.
- #62 ARTIFACT-HYGIENE: retrieval cache and receipts go to `$KUBRICK_PROJECT_DIR/out/kubrick/` (default `./out/kubrick/` under the cwd), never the skill tree. An unwritable target gives a structured diagnostic. Domain NOT_COMPUTABLE exits 4 in retrieve, operate and govern.
- #65 DEPS-GATE: manifest `requires` per intent/action is checked before dispatch (DEPENDENCY_MISSING, exit 4). `do check --action deps` reports readiness. A test checks manifest vs imports.
- #66 MCP-HARDEN: request byte cap, manifest allow-list before spawning, a per-call timeout with a structured error, and a protocol test harness.
- #67 CAPS-ENFORCE: `REFERENCE_CAP_EXCEEDED` (fail closed) above `max_references`, `NATIVE_AUDIO_UNSUPPORTED` warning, drift warnings carry `evidence`. Retime overlay limits are deferred to their own intent.
- #68 CLEANUP: remove `typed_models.py`, the unrouted adapt wrappers (receipt identity hashes routed scripts) and dead helpers. compare_frame_state is fail-closed. Runtime-contract doc and SKILL.md quick reference match dispatch.
- #72 LINT-RATCHET: per-file ruff/mypy baselines with a check script and CI job (counts may only fall; new files clean). The `skills/` mirror is excluded from lint. Shared helpers replace the copies. `surface_compilers.py` is split into modules under 500 lines behind the same public API.

**PR B: production features (#63, #64, #69, #70, #71)**
- #63 SEQ-ADAPT: `video adapt` on a sequence adapts every shot in order. Any unadaptable shot makes the result NOT_COMPUTABLE, naming it.
- #64 TAKE-SELECT: `take_id` and `selected: true` in takes.yaml, plus a `--take <shot>=<take_id>` override in impact and retime. Two selected takes for one shot is TAKE_AMBIGUOUS.
- #69 RETAKE-RUNBOOK: `video --action runbook` emits an ordered Keyframe op list (regenerate, reuse with trims, 0-credit re-join, waits of 45 s or less on processingJobId, `get_movie includeCredits` after each paid step), with INFERRED credits.
- #70 CUT-QA: `video --action cut-qa` emits ffmpeg frame-grab, scene-detect and start-frame MAE commands from the final clock. Kubrick never runs them.
- #71 AUDIO-CUES: `video --action cues` emits a cue sheet on the final clock, ducked/muted mix variants with -14 LUFS / -1 dBTP targets, voice-lock-respecting speakers, and an INFERRED ElevenLabs estimate with a cap check.

The new actions are named in SKILL.md and the manifest. This intent accepts those SKILL.md additions. Every output is PROPOSED, prep only.

Out of scope: calling Keyframe, ElevenLabs, OpenRouter or ffmpeg; vision; retime model-overlay limits; removing the `skills/kubrick` mirror (hub packaging is owner-gated); publishing.

## Constraints / non-goals

- Root is the source of truth; sync the hub mirror.
- No weakened assertions. Modules stay under 500 lines with CC under 22, and new code is ruff and mypy clean.
- The stdlib contract holds.
- The MYSLEF regression stays exit 0 with an unchanged retime clock.

## Author / date

- Author: Grok Bot for Danny
- Date: 2026-10-03

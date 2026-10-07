# Intent

Status: accepted. Danny approved the #133 follow-up (audit items 1 and 2) on
2026-10-07 12:52 AM PT. It records the gate change that shipped in 0.27.2
(#107, PR #133) and the review fixes in 0.27.4. Merge still needs Danny's yes.

Scope: GitHub issue #107 and the three Codex P1 review threads on PR #133.
Issues #91, #92, and #93 stay out of this change.

## Problem

- A critical lock can define a `positive` line and a `negative` line. Before
  0.27.2 the pre-spend phrase check enforced only the first non-empty one, so
  a prompt that dropped the positive detail still cleared with a recorded pass.
- Test tenant fixtures (MYSLEF) stated the opposite of their own canon lock
  file, and the gate treated them as the passing example.
- After 0.27.2, review found two follow-on gaps. (a) The lock carrier table
  reported `prompt_positive` whenever a lock defined a positive line, even when
  the compiled shot prompt never says it. (b) A character-scoped lock was
  required on shots where that character is not cast (`cast: []`).

## Proposed outcome

- The phrase check (`kubrick.gates.lock_phrases`) requires every non-empty
  `negative` and `positive` line of a critical present lock (0.27.2).
- A lock with a `character` skips a prompt whose `characters` list leaves that
  character out. Prompts with no cast list keep the old behavior (0.27.4).
- The lock carrier table (`kubrick.plan.lock_carriers`) compares a lock's
  positive line against the compiled prompt for that frame. When the prompt
  omits it, the carrier is `unverified` with code
  `LOCK_POSITIVE_NOT_IN_PROMPT`. A caller without a compiled prompt keeps the
  old behavior (0.27.4).
- Tenant fixtures are test data. They are corrected to match their canon. No
  tenant canon is hardcoded in Kubrick code.

Out of scope: checking fixture lock text against a canon lock file (the 0.27.5
follow-up), live Jev or provider calls, rewriting `references/`, publishing.

## Affected users / systems

Pre-spend Jev gate (`video runbook`, `video cues`), provider adapters that
emit `lock_carriers` (generic, Keyframe), the Keyframe movie schema
(`lock_carriers[].code`), tenant fixtures under `evals/` and `examples/`, the
hub mirror.

## Constraints / non-goals

Fail closed. Recorded verdicts only in CI. Generic code: no project names or
canon in `src/`. `SKILL.md` changes only for the product version line. No paid
generation.

## Open questions

- Should the prompt compiler emit lock positive lines itself, so omitted
  positives stop happening at the source? Not decided here. Danny decides.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| Pre-0.27.2 phrase check enforced only the first lock line | `OBSERVED` | `_lock_phrase` on main `c1fcf2a` |
| Compiled MYSLEF example prompts omit the canon chest LED positive | `OBSERVED` | `compiled_prompts` on `examples/myslef-minder/storyboard-plan.yaml` |
| Frame-004 (shot 06) has an empty cast | `OBSERVED` | `cast: []` in the example plan |
| No other tenant relies on a positive being reported as carried without prompt text | `INFERRED` | full suite green; no other fixture asserts it |

## Author / date

- Author: Grok Bot for Errnerner Shernerner (scrimshawlife-ctrl)
- Date: 2026-10-07

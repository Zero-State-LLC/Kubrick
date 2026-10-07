# Intent

## Problem

0.27.6 writes every applicable character lock positive into each compiled
prompt. On a first-person (POV) shot the camera is the character, so lines
about how that character looks (wardrobe, face, a light on the body) describe
something the shot cannot show and push the model to put the character in
frame. Lines about what the character holds or does still matter.

## Proposed outcome

- POV marker: the existing `view: pov` field (frame `view`, or `camera.view`,
  read by `kubrick.gates.hold_scope.frame_view`). No new shot field.
- Appearance vs action: a new optional lock field `aspect: appearance | action`
  (`kubrick.plan.lock_aspect.lock_aspect`). When absent, `kind: identity` and
  `kind: wardrobe` default to appearance; every other kind defaults to action,
  so existing plans keep their lines. Lock text is never parsed. A body light
  that is appearance sets `aspect: appearance` explicitly.
- `pov_skips(lock, view)` is true for a POV shot, a lock with a `character`,
  and appearance aspect. It is applied in the prompt compiler
  (`lock_positive_lines`), the lock carrier table, the critical phrase check
  (`lock_phrases`), and Jev hold scope (`scoped_out`), so all four agree.

Out of scope: plain-string `character_locks` (they are not written into the
compiled prompt text), wardrobe lines (already skipped on POV), live Jev or
provider calls.

## Affected users / systems

Prompt compiler, lock carrier table, pre-spend phrase check and Jev holds,
plan authors (new optional `aspect` field), hub mirror.

## Constraints / non-goals

Kubrick stays generic; no tenant names in code. MYSLEF fixtures are unchanged.
A lock without a `character` is never skipped by this rule.

## Open questions

- Should the canon drift check also compare `aspect`? Not in this change.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| `view: pov` already exists and is read by `frame_view` | `OBSERVED` | `src/kubrick/gates/hold_scope.py` |
| Wardrobe and asymmetry lines are already skipped on POV in `prompt_lines` | `OBSERVED` | `src/kubrick/prompts/reference_lint.py` |
| Defaults keep non-POV output unchanged | `OBSERVED` | full test suite passes unchanged |
| No current tenant plan marks a POV shot with appearance locks | `INFERRED` | `git grep "view: pov"` over fixtures |

## Author / date

- Author: Errnerner Shernerner (agent assisted)
- Date: 2026-10-07

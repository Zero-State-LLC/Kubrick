# Intent

Status: accepted. Danny approved this change on 2026-10-07 7:30 PM PT. Merge still
needs Danny's yes.

## Problem

0.27.6 (#137) made the prompt compiler write each lock's `positive` line into the
frame prompt. It did not write the `negative` line. The pre-spend phrase check
(0.27.2, #107) requires both lines of a critical lock, so the live example plan
reported the critical negative line as `MISSING_LOCK` on every shot that casts
the lock's character (shots 03 to 05). Only hand-fixed fixture prompts passed.

Writing the negative inline exposes a second gap. The gate lint reports a
blocking `POSITIVE_NEGATIVE_CONFLICT` whenever a prompt says "no X" and also
uses the word X. A lock whose negative and positive share a word (for example a
light lock: "no light on the head" next to "the only light on the body is ...")
would trade `MISSING_LOCK` for a lint block.

## Proposed outcome

- `lock_negative_lines(document, frame)` mirrors `lock_positive_lines`: plan
  order, whitespace normalized, case-insensitive dedupe, blank lines skipped,
  every lock (critical or not), character locks only where cast (`cast` first,
  `cast: []` means nobody), POV frames skip appearance locks. `prompt_lines`
  appends the negatives right after the positives.
- The lines go inline in the prompt for every provider. Keyframe (Seedance 2.5,
  nano-banana-2) declares `negative_prompt_effective: false` and has no separate
  field, and the gate checks the picture prompt. Flux and SD3 `negative_prompt`
  and Midjourney `--no` take terms to avoid, so a "no ..." sentence there would
  be a double negative. They keep only the general negatives, as before.
- `lint_text` takes `declared` lines. A declared negative line (case and spacing
  ignored) is masked before the conflict scan. The gate passes every plan lock
  negative. Undeclared negations still block.

Out of scope: rewording lock lines, compiling `location.locks` or explicit
`hold_list` texts into prompts, live Jev or provider calls.

## Affected users / systems

Prompt compiler (`storyboard_prompts`, adapter packets, spend plan clause
counts), pre-spend Jev gate and its lint, tenant fixtures (test data only), hub
mirror.

## Constraints / non-goals

Kubrick stays generic: no tenant canon in code; MYSLEF is a fixture. Fail closed.
Recorded verdicts only in CI. No paid generation.

## Open questions

- Image and video models can read "no X" as a cue for X. The positive line still
  states the wanted state first. Should a lock be able to opt out of the inline
  negative per provider? Not decided here.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| On main 0.27.13 the example plan fails the phrase check on shots 03 to 05 for the critical negative | `OBSERVED` | `missing_lock_phrases` on `compiled_prompts` |
| Inline negatives without the lint mask block with `POSITIVE_NEGATIVE_CONFLICT` | `OBSERVED` | `_lint_block` on the patched prompts before the mask |
| With the change the example gate is `CLEAR` on recorded passes | `OBSERVED` | `scripts/test_lock_negative_gate.py` |
| Keyframe models do not honor a negative prompt | `OBSERVED` | `assets/models/capabilities.yaml` blocks |
| No other tenant relies on a compiled prompt without lock negatives | `INFERRED` | full suite green after one fixture change |

## Author / date

- Author: Grok Bot for Errnerner Shernerner (scrimshawlife-ctrl)
- Date: 2026-10-07

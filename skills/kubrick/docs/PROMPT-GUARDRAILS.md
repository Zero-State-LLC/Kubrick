# Prompt guardrails (0.27.15)

Five deterministic checks run before any spend.
They live in `src/kubrick/prompts/prompt_guardrails.py` and are called from `lint_text` before Jev.
Two are blocking. Three are warnings. A warning never stops the run.

## END_CARD_SPACE (blocking)

What fires: the prompt asks for empty space, a blank panel, or room for an end card.
Why: the generator took the request literally. It painted a flat pale panel over half the frame.
That panel is baked into the pixels, so no overlay can sit there cleanly.
Fix: do not ask for blank space. Describe the full scene as you want it. Add the end card in post.

## UI_OUTSIDE_SCREEN (blocking)

What fires: the prompt names a screen element (a card, a badge, a banner) without tying it to the device.
Why: a confirmation card was rendered floating beside a phone, with no surface under it.
Fix: anchor every screen element to its device. Say it stays inside the device screen edges (for example "the card stays inside the tablet screen").

## PROP_LETTERING_UNLOCKED (warning)

What fires: a prompt asks for a plain or unbranded prop, and the prop has a surface that can carry text.
Why: a "plain marker, no brand text" still came back with printed barrel text in a close-up.
The wording only steers the model. It does not lock the surface.
Fix: say the prop surface is bare, or keep the prop out of close-up. Check the frame before you rely on it.

## ACTION_NOT_COMPLETED (warning)

What fires: the prompt names an action but no completed verb, and no end state.
Why: the hands stayed idle and the shot ended before its beat.
Fix: give the action a completion. Say the hand sets the mug down and releases it.

## HANDWRITTEN_TEXT_IN_PROMPT (warning)

What fires: the prompt asks the generator to render words, a note, or a label as visible text.
Why: generated handwriting comes back garbled. Letters merge and drift.
Fix: generate the surface only, then place the text in post. See the next section.

## Handwritten codes and on-screen text

Overlay the exact text in post with ffmpeg drawtext.
Pick a handwriting font that has lowercase glyphs.
Some marker fonts are caps-only, and they change your text without warning.
For generated writing that must stay in frame, keep it small or soft, so the garble reads as texture.

## Keyframe multi-shot clips

Adjacent shots with the same scene label compile into one generation.
The same label on non-adjacent shots becomes separate clips.
A retake of one shot inside a multi-shot clip regenerates the whole clip, at the whole clip's cost.
For a critical shot, split it into its own short node.
Duplicate the clip node, set it to about 5 s, wire the location reference, and leave it out of the final concat.
Then splice it locally with ffmpeg.
The auto location reference bills a few credits. 4 were observed, not 7.

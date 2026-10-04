# Kubrick v0.23.0 Release Notes

v0.23.0 delivers issues #76–#82 from the continuation and corpus audit of
2026-10-03. Retrieval fails closed on weak evidence, the corpus is fully
indexed and audited, storyboard frames carry checked film grammar, and the
MYSLEF EP-01 drift and techniques are on record. The production envelope
schema id stays `0.16.0`. `corpus_version` stays 0.11.5. No provider is
called.

## Retrieval and corpus (#76, #80, #81)

- #76: One stop-word set drives token overlap and registry route matching in
  both retrievers. `SELECTED` requires `dramatic_fit >= 0.15`. Below that the
  receipt is `NOT_COMPUTABLE` with `LOW_DRAMATIC_FIT`; `cats and dogs` and
  function-word-only briefs no longer select. Scoring weights are unchanged.
  `ranked_patterns` lists the selected primary and supporting grammars first.
  Cache keys carry `SELECTION_POLICY`.
- #80: Every sidecar is indexed, registered, and manifested (`wave2`).
  Duplicates are merged, directories match domains, dead lexicon links are
  repaired, optional `grammar_family` is set where the registry is clear, and
  fixture models live under `evals/fixtures/models/`.
  `audit_corpus_coverage.py` fails closed on unindexed, unmanifested,
  unregistered, mismatched, or thin sidecars (an empty list counts as thin)
  and runs in the validation-eval job.
- #81: Six targeted sidecars (`wave3`), written in our own words with
  confidence at most 0.8: withheld cause, dormant background watcher,
  uncanny near-human double, anempathetic playback, power-failure response,
  and the domestic trap. The MYSLEF example brief states the real EP-01 scene
  and is a retrieval regression.

## Film grammar and storyboard carriers (#77, #78)

- #77: Frames take optional `camera` {`size`, `angle`, `lens_mm`, `move`,
  `focus`} and `cut`. Known terms reach generic per-shot prompts and Keyframe
  `videoPrompt` / `multi_shot_prompt`. Frames without `camera` keep the old
  `evidenced framing` / `static unless evidenced` output. Unknown frame keys
  warn `UNKNOWN_FIELD`.
- #78: `assets/grammar/film_grammar.yaml` holds 66 entries with definition,
  prompt phrase, aliases, and evidence. Unknown terms warn
  `UNKNOWN_GRAMMAR_TERM`, unmapped focal lengths warn `LENS_BAND_UNMAPPED`,
  and a snap or whip on a chained start frame warns `MOVE_CHAIN_CONFLICT`.
  Negated terms never resolve to the positive move, and `camera.focus` only
  resolves focus entries.

## MYSLEF drift and techniques (#79)

- Drift entries for Seedance 2.5, observed 2026-10-02:
  `framing-wider-than-asked`, `brightness-over-directed` (needs both a dim
  and a practical cue), `weak-action-intensity`,
  `chained-start-suppresses-move` (snap or whip with camera context), and
  `flicker-clears-all-figures` (explicit flicker evidence only).
- Techniques `scoped-flicker`, `cut-on-sound-peak`, `new-angle-after-cut`
  (at least 30°), and `offscreen-event`.
- `keep` is a schema-backed list on frames, the storyboard root, and the
  adapter packet. A flicker that would clear a kept name warns
  `FLICKER_CLEARS_KEEP`.

## Continuation cleanup (#82)

- `do ledger --action init` and `operate --action` route like the positional
  form.
- Relative path flags on routed commands resolve against the caller cwd. An
  inline `--brief` such as `day/night transition` stays prose.
- `production_engine.py` is under 500 lines; the artifact writer is
  `production_artifacts.py`, re-exported.
- The failing CodeQL and Pages workflows are removed. Scanning stays on
  `free-security-scan.yml`.

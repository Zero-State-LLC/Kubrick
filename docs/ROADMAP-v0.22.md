# Kubrick v0.22 Status and Continuation Roadmap

## In progress (#80)

Corpus hygiene: every sidecar is indexed, registered, and manifested. Duplicate sidecars are merged, dead lexicon links are repaired, fixture models stay out of production capabilities, and the coverage audit fails closed in CI.

## Shipped

- Full CI with coverage floor and clean-tree check (#61)
- Project-local retrieval artifacts (#62)
- Manifest dependency gate and `check deps` (#65)
- MCP size cap, pre-spawn allow-list, and timeout (#66)
- Reference cap and native-audio checks (#67)
- Dead-code cleanup and fail-closed frame comparison (#68)
- Lint ratchet, shared helpers, and the surface compiler split (#72)
- Multi-shot sequence adapt (#63)
- Take selection by id (#64)
- Retake runbook, cut QA, and cue sheet prep (#69, #70, #71)

## In progress (#77)

- Storyboard frames can carry optional `camera` and `cut`. Known terms reach generic prompts and Keyframe `videoPrompt` / `multi_shot_prompt`. An unknown frame key warns `UNKNOWN_FIELD`.

## In progress (#78)

- `assets/grammar/film_grammar.yaml` holds the working film grammar. Camera and cut terms are checked and expanded through it. A snap or whip on a chained start frame warns.

## In progress (#82)

Ledger `--action` matches the positional subcommand. Relative path flags on routed commands resolve against the caller cwd. `production_engine.py` is split under 500 lines. CodeQL and Pages workflows are removed (see `docs/ci/README.md`). QUICKSTART points at this roadmap.

## Next

1. Retime model-overlay limits (needs its own intent).
2. Remove the `skills/kubrick` mirror once hub packaging allows it (owner-gated).
3. Land the official Hermes optional-skills submission against the current release.

## In progress (#76)

Retrieval ignores stop-words in token overlap and registry route matching. `SELECTED` requires dramatic fit of at least 0.15. Weaker evidence stays `NOT_COMPUTABLE` with `LOW_DRAMATIC_FIT`.

## In progress (#81)

Six sidecars cover a withheld cause, a dormant background watcher, an uncanny near-human double, indifferent playback, a power-failure reply, and the domestic trap. The MYSLEF example brief now states that scene, and retrieval on it selects a fitting pattern.

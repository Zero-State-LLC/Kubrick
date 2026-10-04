# Film grammar

The film-grammar registry on `main` is schema **1.0.0**.

| Piece | Path |
|---|---|
| Entries | [`assets/grammar/film_grammar.yaml`](../assets/grammar/film_grammar.yaml) |
| Schema | [`schemas/film-grammar.schema.json`](../schemas/film-grammar.schema.json) |
| Loader | [`scripts/film_grammar.py`](../scripts/film_grammar.py) |

v0.23.0 records 66 entries. Categories are `shot_size`, `angle`, `lens_band`,
`move`, `lighting`, `edit`, and `composition_9_16`. A known term expands to
its prompt phrase. `lens_mm` maps to a lens band. Unknown terms warn
`UNKNOWN_GRAMMAR_TERM`. An unmapped focal length warns `LENS_BAND_UNMAPPED`.
A snap or whip on a frame that chains from a start frame warns
`MOVE_CHAIN_CONFLICT`. Negated terms do not resolve to the positive move.
`camera.focus` only resolves focus entries.

Storyboard frames may carry optional `camera` (`size`, `angle`, `lens_mm`,
`move`, `focus`) and `cut`. An unknown frame key warns `UNKNOWN_FIELD`.
That behavior is the skill contract in [`SKILL.md`](../SKILL.md).

Schema 1.1.0 (composition, blocking, camera height, continuity, and `targets`)
is proposed in [#109](https://github.com/Zero-State-LLC/Kubrick/issues/109)
and is not the registry on `main`. [#110](https://github.com/Zero-State-LLC/Kubrick/issues/110)
still covers the extra warning codes, motion-only video prompts, and the
head-dome fallback.

This registry is the shot vocabulary. The symbolic transformation grammar is
a different document: [`references/transformation-grammar-registry.md`](../references/transformation-grammar-registry.md).

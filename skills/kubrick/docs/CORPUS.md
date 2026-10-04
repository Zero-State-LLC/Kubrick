# Corpus

The symbolic corpus is the pattern sidecars and the retrieval rules. It is
not the film-grammar registry. Film grammar is [`FILM-GRAMMAR.md`](FILM-GRAMMAR.md).

| Contract | Path |
|---|---|
| Retrieval rules and quality gates | [`references/corpus-usage.md`](../references/corpus-usage.md) |
| Transformation grammar | [`references/transformation-grammar-registry.md`](../references/transformation-grammar-registry.md) |
| Pattern sidecars | [`references/patterns/`](../references/patterns/) |
| Coverage audit | [`scripts/audit_corpus_coverage.py`](../scripts/audit_corpus_coverage.py) |

On v0.23.0, `corpus_version` stays **0.11.5**. `SELECTED` requires
`dramatic_fit >= 0.15`. Weaker evidence is `NOT_COMPUTABLE` with
`LOW_DRAMATIC_FIT`. The coverage audit fails closed on an unindexed,
unmanifested, unregistered, mismatched, or thin sidecar, and CI runs it.

Ordinary work does not write into `references/`. Pattern evolution stays a
proposal until a human applies it. Retrieval details are in
[`references/retrieval-and-continuity.md`](../references/retrieval-and-continuity.md).

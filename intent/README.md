# Intent files

Non-trivial work starts here. Copy [`_TEMPLATE.md`](_TEMPLATE.md) to a dated,
scoped file (for example `intent/2026-09-04-short-slug.md`) and fill every
section before writing a spec, plan, or code.

Do not invent a parallel process. After the intent is written, continue with
the flow this repo already uses:

1. `intent.md` — problem, proposed outcome, constraints, verified vs assumed
2. `spec.md` / plan — existing `docs/` specs, `references/` contracts, and
   `CONTRIBUTING.md` gates. Revise `SKILL.md` only when the accepted intent
   is the Hermes contract itself.
3. Implementation in the allowed trees (root skill payload; then hub sync)
4. PR with honest `OBSERVED` / `INFERRED` / `NOT_COMPUTABLE` evidence

Trivial docs, chore, and single-line fixes do not need an intent file.
`_TEMPLATE.md` is the blank form; do not fill it in place.

An intent is not a spec, not a plan, and not implementation authority. It
does not authorize a `SKILL.md` rewrite, official Hermes hub publish,
Continuity Forge promotion, extra bots, or deploy/pin workflows.

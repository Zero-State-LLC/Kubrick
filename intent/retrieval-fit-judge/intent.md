# Intent

## Problem

Issue #91. Retrieval selects on shared words. On current main, a plain-language
MYSLEF brief and a plain authority-transfer brief are both `NOT_COMPUTABLE`
(every pattern scores 0.43 to 0.50, dramatic fit near 0), while a brief made of
pattern vocabulary ("consequence authority transfer withheld cause...") or an
unrelated brief that borrows it (a failed sourdough loaf) is `SELECTED`. Real
briefs had to be reworded into pattern vocabulary to pass.

## Proposed outcome

- A judge (Jev) gives each pattern `fit`, `weak` or `none` for a brief.
- Selection requires both signals: `fit` plus a lexical total at least
  `STRUCTURAL_FLOOR` (0.40), or `weak` plus full lexical eligibility. `none` or
  no verdict is never selected. The floor keeps hard collisions (score 0) and
  heavy cost, ledger or collision penalties out; on plain briefs the lexical
  dramatic score carries no signal, so it is not required for `fit`.
- Opt-in: `build_receipt(..., fit_recordings)` and `--fit-verdicts PATH`.
  Without verdicts, retrieval is unchanged.
- Recorded verdicts keyed by the brief's SHA-256 are used in tests. A brief
  with no recording fails closed (`JEV_FIT_UNAVAILABLE`).

Out of scope: a live Jev fit client and its prompt, changing lexical weights,
making the judge the default.

## Affected users / systems

Registry retrieval (`retrieve_symbolic_patterns_registry`), its CLI, receipts,
eval fixtures, hub mirror.

## Constraints / non-goals

Kubrick stays generic; MYSLEF and authority briefs are test data. No live or
paid calls in CI. The recorded verdicts in this change are hand-labelled
stand-ins, not live Jev output.

## Open questions

- Replace the hand-labelled verdicts with real recorded Jev verdicts (one live
  text call per fixture brief)? Owner decides; live calls are recording only.
- Is 0.40 the right structural floor? It admits one soft collision penalty.
- Should the judge become the default once a live client exists?

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| Plain briefs fail and vocabulary soup passes on lexical scoring alone | `OBSERVED` | `test_lexical_alone_shows_the_bug` |
| With recorded verdicts, plain briefs select a fitting pattern and nonsense is refused | `OBSERVED` | `scripts/test_retrieval_fit_judge.py` |
| Existing retrieval tests are unchanged and pass | `OBSERVED` | full suite |
| Live Jev labels these briefs as the hand labels did | `OBSERVED` false (0.27.10) | live recordings give `fit` to all three nonsense briefs; two acceptance tests fail |

## 0.27.10 finding

Live Jev recordings (seven calls) replaced the hand labels. Jev is permissive:
the vocabulary-soup brief gets ten `fit` verdicts (top p=0.97), sourdough one
(p=0.47), cats and dogs one (p=0.42). All three are `SELECTED`. A fit
probability floor of 0.8 would refuse two of them but not the vocabulary soup.
The acceptance tests are left failing until the owner picks a fix (question
wording, a probability floor, a fit-count cap, or a different judge).

## Author / date

- Author: Errnerner Shernerner (agent assisted)
- Date: 2026-10-07

# Intent

Status: accepted. Danny approved this cleanup (0.27.13) on 2026-10-07 7:01 PM PT.
Merge still needs Danny's yes.

Scope: two follow-ups. (a) Issue #91 retrieval fit screening, from the
2026-10-07 tracker entry on the permissive first recordings. (b) The three
Codex P1 review threads on PR #133 (item 1 of the 2026-10-07 main audit).
Issue #93 stays out of this change.

## Problem

- (a) The 0.27.10 screen was checked against the first, permissive live
  recordings. `weak` plus lexical eligibility had let the sourdough brief
  through; 0.27.10 already stopped `weak` from selecting. The vocabulary-soup
  brief still selects on those recordings: seven fits survive screening and
  its lexical leader, `withheld_cause_consequence_only`, is a `fit` at
  probability 0.68. Lexical overlap makes a lukewarm verdict the primary.
- (b) PR #135 (0.27.4) fixed the three threads: carriers compare the compiled
  prompt, character locks follow the cast, and
  `intent/critical-lock-lines/intent.md` records the gate change. One gap is
  left in (b2): the gate builds its per-shot rows in `compiled_prompts` from
  `characters` only, while the prompt compiler and the carrier table use
  `cast` first (`screen_mode`). A shot with only `cast: []` is still asked to
  state a character lock that the compiler correctly left out.

## Proposed outcome

- (a) `fit_select` takes `primary_floor`. When the primary (lexical leader
  among eligible `fit` patterns) has a recorded fit probability under
  `PRIMARY_FIT_PROBABILITY` (0.75), the brief is refused with
  `JEV_FIT_PRIMARY_MARGINAL`. It does not fall through to another pattern,
  because then the two signals disagree. No recorded probability: no check,
  as in screening.
- (a) The first recordings are kept as
  `evals/fixtures/retrieval/jev-fit-verdicts-permissive.yaml` and replayed in
  tests as a permissive judge.
- (b2) `compiled_prompts` fills each row's `characters` from `screen_mode`
  (`cast`, else `characters`, else unset).
- (b1) and (b3) need no code change; see the claims table.

Out of scope: live Jev calls, a new fit request, changing lexical weights, the
negative-line handling of the compiler.

## Affected users / systems

Registry retrieval with fit verdicts (receipts gain
`fit_judge.primary_fit_probability`), the pre-spend Jev gate (`video runbook`,
`video cues`), eval fixtures, hub mirror.

## Constraints / non-goals

Kubrick stays generic: MYSLEF and the authority briefs are test data only.
Recorded verdicts only in CI. Fail closed. No paid generation.

## Open questions

- Is 0.75 the right primary floor? On the recorded sets the lowest legitimate
  primary is 0.84 (authority example) and the vocabulary-soup leader is 0.68.
  The value was chosen after seeing these recordings, so it is optimistic.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| On main 0.27.12 the sourdough brief is refused on both recording sets | `OBSERVED` | `weak` never selects since 0.27.10 |
| On main 0.27.12 vocabulary soup is `SELECTED` on the permissive recordings | `OBSERVED` | primary `withheld_cause_consequence_only`, fit p 0.68 |
| With the floor, all briefs on the active recordings keep their result | `OBSERVED` | `scripts/test_retrieval_fit_judge.py` |
| (b1) carriers report `prompt_positive` only when the compiled prompt says the positive | `OBSERVED` | `positive_omitted` in `lock_carriers`; the compiler writes positives since 0.27.6 |
| (b2) a `cast: []` only shot was blocked with `MISSING_LOCK` on main | `OBSERVED` | `scripts/test_lock_line_scope.py` fails without the fix |
| (b3) an accepted intent for the #107 gate change exists | `OBSERVED` | `intent/critical-lock-lines/intent.md` (PR #135) |

## Author / date

- Author: Grok Bot for Errnerner Shernerner (scrimshawlife-ctrl)
- Date: 2026-10-07

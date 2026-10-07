# Intent: rewrite the legacy em dashes and check the whole repo

## Problem

`intent/no-new-em-dash` added a ratchet that only checks added lines, and left
about 390 legacy em dashes (U+2014) in docs, references, code comments, and
output strings out of scope. They keep being copied into new text, and the
ratchet cannot stop an em dash added to a file type it does not read.

## Proposed outcome

Every legacy em dash is rewritten by context: a colon for headings, term lists,
and `NOT_COMPUTABLE` reasons; a comma or semicolon mid-sentence; parentheses for
a paired aside; a hyphen before a changelog date; a sentence split where two
clauses meet. After that, `check_no_new_em_dash.py --all` fails on any em dash
in any tracked text file, and CI runs it on every build.

## Affected users / systems

Docs and references, surface output strings (`# Design: <project>`,
`NOT_COMPUTABLE: <reason>`), the v0.16 goldens (regenerated), CI, and the hub
mirror.

## Constraints / non-goals

- `SKILL.md`: punctuation only, in the command list (`compile: ...` instead of
  `compile` plus an em dash). No contract meaning changes. The owner approved
  rewriting every legacy em dash, which includes these 16 lines.
- Kept on purpose, marked `em-dash: allow`: the interrupted dialogue line
  `minder: Wha` plus an em dash in test data and the release note that quotes it.
- `LICENSE` is legal text and is exempt from `--all`.
- Artifacts written before this change keep working: `dialog-validate` accepts
  the old em dash sentinel as well as the new colon.
- No change to cinematic or CLI behavior beyond the output punctuation.

## Open questions

None.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| About 390 em dashes outside the hub mirror on main 313ba65 | `OBSERVED` | `git grep -n` count, 391 lines |
| Goldens change only in punctuation, content hashes, and the generator version string | `OBSERVED` | word diff after `test_golden_v016.py --write` |
| No parser other than `dialog-validate` matched the old separator | `OBSERVED` | grep of `src/` for separator-dependent checks |

## Author / date

- Author: Grok Bot for Daniel Meyer (operator approval 2026-10-07 03:31 PT: "replace the ~387 legacy em dashes ... make the em dash check repo-wide")
- Date: 2026-10-07

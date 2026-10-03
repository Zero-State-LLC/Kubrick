# Intent

Status: accepted by Danny (repo owner) on 2026-10-03 at 11:27 PT ("File all 7 as issues and start building in order").

Scope: GitHub issues #76–#82, the ranked next steps from the Kubrick Continuation and Corpus Audit 2026-10-03. Built on main 1453995 (v0.22.0).

## Problem

The pattern corpus is broad, but retrieval doesn't fail closed: any brief containing "and" clears the threshold. Kubrick also has no film grammar. Storyboard frames can't carry camera direction, and a `camera` block is dropped silently. Several MYSLEF failures have no drift entry or technique. The corpus has drifted: unindexed sidecars, duplicates, dead lexicon links, and fixture models in the production capabilities file. The MYSLEF example brief is borrowed from another fixture. Small routing and path bugs remain.

## Proposed outcome

- #76 RETRIEVAL-FLOOR: stop-words are ignored in token overlap and route matching. SELECTED requires a minimum dramatic fit; otherwise NOT_COMPUTABLE with LOW_DRAMATIC_FIT.
- #77 CAMERA-CARRIER: optional `camera` {size, angle, lens_mm, move, focus} and `cut` on storyboard frames, carried into generic and Keyframe prompts. An unknown frame key warns (UNKNOWN_FIELD) instead of being dropped silently.
- #78 FILM-GRAMMAR: `assets/grammar/film_grammar.yaml` plus schema, about 65 hand-written entries in our own words. Camera and cut terms are validated and expanded through it. A snap or whip move on a chained start frame warns.
- #79 MYSLEF drift and techniques: 5 drift entries and 4 techniques with MYSLEF evidence. Trigger enums are extended.
- #80 CORPUS-HYGIENE: every sidecar is indexed, in the registry and in a manifest. Duplicates are merged and thin sidecars filled. Directories match domains. Dead lexicon links are fixed. Sidecars get an optional `grammar_family`. Fixture models move to tests. The dead schema is fixed or removed. The coverage audit fails on drift and runs in CI.
- #81 TARGETED SYMBOLIC: 6–8 new sidecars and the real MYSLEF brief as a retrieval regression. Depends on #76.
- #82 CLEANUP: `do ledger --action` routing, relative paths resolved against the caller's cwd, a `production_engine.py` split under 500 lines, stale codeql/pages workflows, and the QUICKSTART roadmap pointer.

Each step lands as its own PR (#77 and #78 bundled). New SKILL.md lines that name the camera/cut fields and the film-grammar registry are accepted by this intent. Every output stays PROPOSED.

Out of scope: provider calls, vision, publishing, removing the skills mirror, retime overlay limits, version bumps (one release PR after the merges).

## Constraints / non-goals

- Root is the source of truth; sync the hub mirror with `bash scripts/sync_hub_skill.sh`.
- No weakened assertions. Modules stay under 500 lines with CC under 22. The lint ratchet may only fall, and new files are ruff and mypy clean.
- The stdlib contract holds.
- The MYSLEF regression stays exit 0.
- No copyrighted text is copied. Definitions are written in our own words.

## Author / date

- Author: Grok Bot for Danny
- Date: 2026-10-03

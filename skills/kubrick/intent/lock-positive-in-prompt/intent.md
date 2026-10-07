# Intent

## Problem

0.27.4 (#135) made the lock carrier table report `LOCK_POSITIVE_NOT_IN_PROMPT`
when a lock's `positive` line is missing from the compiled shot prompt. The
prompt compiler did not write those lines itself, so the code fired on every
plan that relied on the lock definition alone. On provider payloads (generic,
Keyframe) the table compared against an empty prompt map, so every shot was
flagged even when the payload prompt said the line. The code was noise, not a
drift signal.

0.27.5 (#136) compares plan lock text with the plan's canon lock file, but a
plan could mark a canon critical lock as non-critical (or the reverse) and pass.

## Proposed outcome

- `kubrick.plan.lock_positive_lines.lock_positive_lines` returns the `positive`
  line of each plan lock that applies to a frame. `prompt_lines` appends them,
  so every compiled frame prompt carries them. A lock with a `character` is
  written only where that character is cast, the same rule as the carrier
  table and the 0.27.4 phrase check.
- The carrier table checks an adapter frame's own `prompt` when it has one,
  else the plan's compiled prompts. `LOCK_POSITIVE_NOT_IN_PROMPT` then fires
  only when a prompt drops the line after compile.
- `kubrick.gates.canon_locks` compares `critical` (true only when the value is
  `true`) and reports `LOCK_CANON_DRIFT` with `field: critical`. `kind` is not
  compared.

Out of scope: rewriting the recorded v0.23 Jev fixture, live Jev or provider
calls, changing which statuses block spend.

## Affected users / systems

Prompt compiler (`storyboard_prompts`, adapter packets), lock carrier table,
canon drift gate in video prep (`runbook`, `cues`, `cut-qa`), tenant fixtures
under `evals/` and `examples/` (test data only), hub mirror.

## Constraints / non-goals

Kubrick stays generic. No tenant canon in code; MYSLEF is a fixture. A
`critical` mismatch is a new fail-closed `LOCK_CANON_DRIFT` in video prep for
plans that name a canon file. `LOCK_POSITIVE_NOT_IN_PROMPT` stays a report
entry and does not block.

## Open questions

- Should a POV frame skip character lock positives? Kept as-is (applies when
  cast), owner decides.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| `LOCK_POSITIVE_NOT_IN_PROMPT` is only a `lock_carriers` row code; no gate or exit code reads it | `OBSERVED` | `git grep` over `src/` at 0.27.5 |
| Provider payload prompts already carried lock positives for the MYSLEF example; the table flagged them anyway | `OBSERVED` | adapter run before the `_frame_prompt` change |
| The MYSLEF example plan and canon agree on `critical` | `OBSERVED` | full test suite passes with the new comparison |
| No other tenant plan relies on a critical mismatch | `INFERRED` | only plans with `canon_locks` are checked |

## Author / date

- Author: Errnerner Shernerner (agent assisted)
- Date: 2026-10-07

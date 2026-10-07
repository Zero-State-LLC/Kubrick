# Intent

Status: accepted. Danny approved audit item 2 on 2026-10-07 12:52 AM PT.
Merge still needs Danny's yes.

Scope: a generic check that plan lock text matches the canon lock file the
plan names. Follow-up to issue #107 and PR #135.

## Problem

Tenant plans and fixtures copy lock text from a canon lock file by hand. In
#107 the copy drifted ("chest LED stays dark" against a canon of one red chest
LED), and nothing caught it before a gate treated the drifted fixture as the
passing example.

## Proposed outcome

- A plan may set `canon_locks: <path>`. Each plan lock matches the canon lock
  with the same id, or with its `canon_id`.
- A different `positive` or `negative` line is `LOCK_CANON_DRIFT`. A named
  `canon_id` that is not in the canon is `LOCK_CANON_MISSING`. A bad path or
  file is `LOCK_CANON_UNREADABLE`.
- The check runs in the shared video prep step, so `runbook`, `cues`, and
  `cut-qa` fail closed before any estimate.
- Plans without `canon_locks` behave as before.

Out of scope: choosing a canon for any project, rewriting canon files,
comparing fields other than `positive` and `negative`, live calls.

## Affected users / systems

Video prep commands, tenant plans and fixtures under `examples/` and `evals/`,
the hub mirror.

## Constraints / non-goals

Generic code with no tenant names or canon text. Fail closed. Offline tests.

## Open questions

- Should `kind` and `critical` also be compared? Left out for now. Danny decides.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| MYSLEF example and fixture locks match `locks-v0.27.yaml` `red-chest-led` | `OBSERVED` | `canon_block` returns None in `scripts/test_canon_lock_drift.py` |
| A drifted positive blocks `video cues` | `OBSERVED` | same test, CLI run |
| No other plan in the repo sets `canon_locks` | `OBSERVED` | repo search |

## Author / date

- Author: Grok Bot for Errnerner Shernerner (scrimshawlife-ctrl)
- Date: 2026-10-07

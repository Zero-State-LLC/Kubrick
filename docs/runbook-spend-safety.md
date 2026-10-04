# Runbook spend safety

`video runbook` stays prep-only. It does not submit a generation and it does
not call Keyframe or ElevenLabs.

## One node per call

Each regenerate operation is one node (`nodes: 1`). A shared clip is one
operation for the whole clip.

## Timeout `-32001`

A provider result whose code is `-32001` is recorded as `reconcile_later`.

- Do not submit that node again.
- Poll `objectKey` for 360 seconds (about 6 minutes).
- When the late bill arrives, reconcile it on the run ledger. The new entry
  is `late_bill` and `submit` is false.

## Unavailable estimates

When `estimateAvailable` is false, quote the observed billed-rate table:

| Seconds | Credits |
| --- | --- |
| 4 | 62 |
| 5 | 77 |
| 6 | 93 |

A duration that is not in the table is `NOT_COMPUTABLE`. It is not `0` and
not `seconds * 15.5`.

## Jev timeout

`KUBRICK_JEV_TIMEOUT` is a positive number of seconds. The default is 10.
A request that never answers fails closed after bounded retries with
backoff. The reference adapter in `tools/jev_adapter/` replays
`tools/jev_adapter/fixtures/health.json`. Its health check does not open a
network connection.

# Jev pre-spend gate

`video runbook` and `video cues` check every prompt that would be spent
before they record a credit figure or a paid operation. Kubrick does not call
Keyframe, ElevenLabs, or an image provider. The gate only decides whether
those proposed operations may be written.

## Hold list

If the plan sets `hold_list`, that list is the whole check. It must be a list.
A string, mapping, or other non-list is `HOLD_LIST_INVALID` and blocks the
spend. The gate does not fall back to locks when that field is present. Each
entry is a string or an object with `text`, `negative`, or `positive`. An
entry with `blocked: true` and `shot` is a local block. The shot is matched
against the prompt shot and its aliases (`frame_id` and `shot_id`). It does
not need a Jev verdict, and an override does not clear it.

When `hold_list` is absent, the gate builds the list from:

- plan `locks` (presence checks; critical unless the lock says otherwise)
- `location.locks` (presence checks for that location)
- prop `states` (`in_scope_only`, so a state must not leak onto a shot that
  is outside its scope)

An empty hold list passes with code `NO_HOLDS` and does not call Jev. A step
with no prompts to spend passes with `NO_SPEND`.

Keyframe prompts are the compiled shot text. That text is what Keyframe would
copy into both the image prompt and the video prompt. Cue prompts are the
spoken lines that would be sent to ElevenLabs.

## Jev

Resolution order:

1. `--jev-verdicts FILE`, or `KUBRICK_JEV_VERDICTS`, a JSON object
   `{"verdicts": {"<sha256>": {"verdict": "pass"|"fail", "findings": [...]}}}`.
   The key is the sha256 of the canonical JSON for the judged prompt
   (`shot`, `channel`, `surfaces`, `location`, `prompt`) and the hold list.
   A change to either does not reuse the recorded verdict.
2. `KUBRICK_JEV_URL`, an `http` or `https` endpoint

The live call is `POST {"prompt": {...}, "holds": [...]}`. A usable response
is `{"verdict": "pass"|"fail", "findings": [{"code", "message", "hold_id"?}]}`.
A pass with findings, a missing verdict, or a transport error is unreachable.
A transport failure on a later prompt is unreachable too. If an earlier prompt
already failed a hold, that hold still blocks and the override does not clear it.

If Jev is not configured or cannot be reached, the command exits 4 with
`JEV_UNREACHABLE` and writes no paid operations and no credit estimate.

## Override

`--jev-override`, or `KUBRICK_JEV_OVERRIDE` set to `1`, `true`, or `yes`,
allows the spend only when Jev is unreachable. The command prints one stderr
line, `JEV_OVERRIDE` plus a JSON record. A hold hit still blocks, including
when the override flag is set. The message says the override does not bypass
a hold hit.

## Ledger

The payload always carries `jev_gate` (`checked_before_spend: true`) and
`run_ledger` with one `kind: jev_gate` entry. `--run-ledger PATH` appends
that entry to a file. A corrupt ledger is `LEDGER_INVALID` and is not
replaced. A successful judgment that cannot be written is
`LEDGER_WRITE_FAILED` and includes no paid operations.

## MYSLEF

`evals/fixtures/jev/myslef-v023.json` stores the v0.23 compiled prompts for
shots 03–06 and recorded fail verdicts for the missing red-chest lock.
`evals/fixtures/jev/myslef-hand-fixed.json` stores the same prompts with the
lock restored, plus an alley shot that does not carry the chair lock. Those
recorded verdicts pass. `scripts/test_jev_gate.py` checks the live compiler
against the v0.23 snapshot, so a prompt change does not inherit an old
verdict.

## Codes

| Code | Meaning |
|---|---|
| `JEV_HOLD` | A prompt hit a hold. Spend is blocked. |
| `JEV_UNREACHABLE` | Jev is down, unconfigured, or returned a verdict the gate cannot trust. |
| `JEV_OVERRIDE` | Jev was unreachable and the operator override was logged. |
| `JEV_PROMPT_MISSING` | A paid shot has no compiled prompt. |
| `HOLD_LIST_INVALID` | `hold_list` is not a list, or an entry has no text. |
| `NO_HOLDS` | The plan has nothing to check. |
| `NO_SPEND` | This step has no prompt that would be spent. |
| `CLEAR` | Jev passed every prompt. |
| `BLOCKED_SHOT` | The shot is marked blocked on the hold list. |
| `MISSING_LOCK` | A recorded or live finding: required lock text is absent. |
| `OUT_OF_SCOPE_LOCK` | A finding a judge may return when an in-scope-only hold leaks. |
| `BRAND_PRONE` | A finding a judge may return for brand-prone wording. |

# Kubrick roadmap

Product version **0.27.9**. Local output stays **PROPOSED**. Weak evidence
stays `NOT_COMPUTABLE`. No provider is called from this plan.

Project board: [Zero-State-LLC project 13](https://github.com/orgs/Zero-State-LLC/projects/13).

Shipped history is [`CHANGELOG.md`](../CHANGELOG.md). The standing release
gate is [`RELEASE-CHECKLIST.md`](RELEASE-CHECKLIST.md). Versioned notes from
v0.11 through v0.23 are in [`archive/releases/`](archive/releases/).

## Shipped in 0.27.9

- #91: optional Jev fit judge for retrieval (`--fit-verdicts`); selection needs a fit/weak verdict plus lexical eligibility; recorded verdicts in CI.

## Shipped in 0.27.8

- #92: retake router report schema; ambiguous drift drafts carry a drift-schema-valid entry or name the missing inputs; `apply_drafts` needs an approver and writes only a patch file.

## Shipped in 0.27.7

- POV shots (`view: pov`) skip character lock lines with `aspect: appearance`; action locks (what the character holds or does) stay.

## Shipped in 0.27.6

- The prompt compiler writes each applicable lock `positive` line (cast-scoped for character locks); `LOCK_POSITIVE_NOT_IN_PROMPT` now means real drift. Canon drift also compares `critical`.

## Shipped in 0.27.5

- Generic canon lock drift check (`LOCK_CANON_DRIFT`) in video prep; plans name their own `canon_locks` file.

## Shipped in 0.27.4

- #133 review follow-up: lock carriers checked against compiled prompt text (`LOCK_POSITIVE_NOT_IN_PROMPT`); character locks skip shots without that character; intent doc for the #107 gate change.

## Shipped in 0.27.3

- Issue #108: video cues SFX estimate computed from frame fixtures for any project; `SFX_ESTIMATE_MISSING` fails closed.

## Shipped in 0.27.2

- Issue #107: `kubrick.gates.lock_phrases` enforces every positive and negative line of a critical lock. MYSLEF fixtures realigned to chest LED canon.

## Shipped in 0.23.0

Issues [#76](https://github.com/Zero-State-LLC/Kubrick/issues/76) through
[#82](https://github.com/Zero-State-LLC/Kubrick/issues/82): retrieval floor,
storyboard camera and cut, film grammar 1.0.0, MYSLEF drift, corpus hygiene,
six sidecars, and the continuation cleanup. See the `0.23.0` section of
[`CHANGELOG.md`](../CHANGELOG.md).

## Shipped in 0.24.0

| Work | Issue | Pull request |
|---|---|---|
| Provider preflight | [#95](https://github.com/Zero-State-LLC/Kubrick/issues/95) | [#111](https://github.com/Zero-State-LLC/Kubrick/pull/111) |
| Prompt action and deterministic lint | [#96](https://github.com/Zero-State-LLC/Kubrick/issues/96), [#97](https://github.com/Zero-State-LLC/Kubrick/issues/97) | [#112](https://github.com/Zero-State-LLC/Kubrick/pull/112) |
| Film grammar 1.1.0 | [#109](https://github.com/Zero-State-LLC/Kubrick/issues/109) | [#113](https://github.com/Zero-State-LLC/Kubrick/pull/113) |
| Spend safety | [#98](https://github.com/Zero-State-LLC/Kubrick/issues/98) | [#114](https://github.com/Zero-State-LLC/Kubrick/pull/114) |
| Scoped holds | [#99](https://github.com/Zero-State-LLC/Kubrick/issues/99) | [#115](https://github.com/Zero-State-LLC/Kubrick/pull/115) |
| Restructure into `src/kubrick` | [#105](https://github.com/Zero-State-LLC/Kubrick/issues/105) | [#116](https://github.com/Zero-State-LLC/Kubrick/pull/116) |
| This docs pass | [#117](https://github.com/Zero-State-LLC/Kubrick/issues/117) | [#118](https://github.com/Zero-State-LLC/Kubrick/pull/118) |
| Take QC core and full take QC | [#100](https://github.com/Zero-State-LLC/Kubrick/issues/100), [#107](https://github.com/Zero-State-LLC/Kubrick/issues/107) | [#119](https://github.com/Zero-State-LLC/Kubrick/pull/119), [#123](https://github.com/Zero-State-LLC/Kubrick/pull/123) |
| Board gate | [#101](https://github.com/Zero-State-LLC/Kubrick/issues/101), [#106](https://github.com/Zero-State-LLC/Kubrick/issues/106) | [#120](https://github.com/Zero-State-LLC/Kubrick/pull/120) |
| Numeric framing | [#102](https://github.com/Zero-State-LLC/Kubrick/issues/102), [#110](https://github.com/Zero-State-LLC/Kubrick/issues/110) | [#121](https://github.com/Zero-State-LLC/Kubrick/pull/121) |
| Reference pack | [#103](https://github.com/Zero-State-LLC/Kubrick/issues/103) | [#122](https://github.com/Zero-State-LLC/Kubrick/pull/122) |
| Retake router | [#104](https://github.com/Zero-State-LLC/Kubrick/issues/104), [#92](https://github.com/Zero-State-LLC/Kubrick/issues/92), [#108](https://github.com/Zero-State-LLC/Kubrick/issues/108) | [#124](https://github.com/Zero-State-LLC/Kubrick/pull/124) |

[#91](https://github.com/Zero-State-LLC/Kubrick/issues/91) stays deferred.

A scoped lock missing from the prompt blocks before spend (`LOCK_MISSING_IN_BOARD`). A blank or whitespace prompt location on a location-scoped hold blocks (`LOCATION_UNSPECIFIED`) instead of dropping the hold. See [#125](https://github.com/Zero-State-LLC/Kubrick/pull/125).

## Carrier order

Start image, then references, then end image, then prompt. See
[`CONTINUITY.md`](CONTINUITY.md). That note does not add a provider call.

## Shipped in 0.25.0

Board image checks in the pre-spend gate, on by default in `video runbook`:
DINOv2 identity similarity to the approved `ref_pack` views (default 0.50
since 0.25.1, calibrated on EP-01 in
[`BOARD-IMAGE-CALIBRATION.md`](BOARD-IMAGE-CALIBRATION.md)), yes-or-no lock checks through
a local judge, and the hard-cut board rules. A check that cannot run blocks.
See [`JEV-PRE-SPEND-GATE.md`](JEV-PRE-SPEND-GATE.md#board-image-checks) and
[#126](https://github.com/Zero-State-LLC/Kubrick/pull/126).

## Shipped in 0.26.0

The board gate asks each lock clause as its own direct yes-or-no question
with an expected answer and combines the answers per lock. Checks carry a
severity (`block` or `warn`); a left-or-right side question defaults to
`warn`. On EP-01 through the Spark judge, clean boards blocked fell from 36
to 19 of 60 and defective ones blocked from 7 to 5 of 7. See
[`BOARD-IMAGE-CALIBRATION.md`](BOARD-IMAGE-CALIBRATION.md#atomic-lock-questions-0260-2026-10-04).

## Shipped in 0.27.1

- Dedicated offline regression for issue #106 (cut must not inherit a previous start_frame lock carrier; chain still can).

## Shipped in 0.27.0

The board judge setup and the calibration harness live in the repo
(`tools/board_vision/`, `tools/board_calibration/`,
`evals/calibration/board-image-ep01/`). The judge adapter takes any
OpenAI-compatible vision endpoint from a profile and fails closed. The MYSLEF
lock text names the mouth grille and the lens lock asks the longer lens glow
question: on EP-01 through the Spark judge, 11 of 60 clean boards and 7 of 7
defective ones block. Editable installs no longer break the `scripts/` entry
points. See [`BOARD-VISION-SETUP.md`](BOARD-VISION-SETUP.md) and
[`BOARD-IMAGE-CALIBRATION.md`](BOARD-IMAGE-CALIBRATION.md#lock-wording-fixes-0270-2026-10-04).

Next: a head detector so wide boards get a head crop without a plan box,
better automatic wording for "S never V" clauses (the hand-written lens
question beat the split one), a second labeled set so lock wording is not
tuned on the set that scores it, let `lock_carriers` count a start frame as
a carrier only when this gate passed, and reuse the same crop and embedding
in live take QC.

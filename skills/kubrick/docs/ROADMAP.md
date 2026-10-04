# Kubrick roadmap

Product version **0.25.1**. Local output stays **PROPOSED**. Weak evidence
stays `NOT_COMPUTABLE`. No provider is called from this plan.

Project board: [Zero-State-LLC project 13](https://github.com/orgs/Zero-State-LLC/projects/13).

Shipped history is [`CHANGELOG.md`](../CHANGELOG.md). The standing release
gate is [`RELEASE-CHECKLIST.md`](RELEASE-CHECKLIST.md). Versioned notes from
v0.11 through v0.23 are in [`archive/releases/`](archive/releases/).

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

Next: a head detector so wide boards get a head crop without a plan box, a
stronger local judge for lens glow and body lights (the 3B model is unreliable on them;
the Spark Qwen3.5 judge is better on direct questions, but still caught only 1 of 2 lens-glow
and 4 of 5 body-light defects and blocks most clean boards on the compound plan-lock wording,
see the calibration note), let `lock_carriers` count a
start frame as a carrier only when this gate passed, and reuse the same crop
and embedding in live take QC.

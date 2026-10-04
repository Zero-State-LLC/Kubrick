# Spec: board image gate

Intent: [`intent.md`](intent.md). Status: accepted with the intent.

## Where it runs

`video runbook`, after the Jev gate passes and before the spend estimate.
The gate selects the paid shots by `frame_id` and `shot_id`. `video cues` is
audio spend and does not run it.

## Modules

| Module | Role |
|---|---|
| `src/kubrick/gates/board_image_gate.py` | Checks, result, CLI (`scripts/board_image_gate.py`) |
| `src/kubrick/gates/board_image_plan.py` | Plan reading: board source, views, locks, threshold |
| `src/kubrick/gates/board_image_ledger.py` | Opt-out and run-ledger helpers |
| `src/kubrick/qc/board_pixels.py` | Standard-library PNG decode, Pillow fallback, crop |
| `src/kubrick/qc/board_vision.py` | `Embedder` and `LockJudge` interfaces and local backends |

## Inputs

- Board: frame `board_image` or `start_frame.board_image` (always checked),
  else a `start_frame.asset` that is a local image file. Paths resolve
  against the plan folder.
- Characters: `cast` when present (`cast: []` is nobody), else a non-empty
  `characters`, else every plan character.
- Identity views: `characters.<id>.ref_pack.views` and `head_lock` with role
  `identity`.
- Locks: `character_locks`, character `locks`, plan `locks` with
  `character: <id>`, and `board_checks` (`question`, `expect`).
- Crop: `board_subject_boxes.<id>` or `board_subject_box`, else the
  border-contrast box, else the full frame.

## Checks and codes

| Check | Fail | Cannot run |
|---|---|---|
| Image | `BOARD_IMAGE_MISSING`, `BOARD_IMAGE_UNREADABLE` | n/a |
| Identity, max cosine over views vs threshold | `BOARD_IDENTITY_MISMATCH` | `BOARD_IDENTITY_UNVERIFIED` |
| Lock detail, yes-or-no judge | `BOARD_LOCK_DETAIL_FAIL` | `BOARD_LOCK_DETAIL_UNVERIFIED` |
| Hard cut reuses a board | `BOARD_REUSED_ON_CUT` | n/a |
| Hidden identity on a revealing shot | `START_FRAME_HIDES_IDENTITY` | n/a |
| Threshold config | `BOARD_GATE_CONFIG_INVALID` | n/a |

Every fail and every cannot-run blocks spend (fail closed). The result names
the most specific code and recommends regenerating the board.

## Threshold

Default 0.70, max cosine of DINOv2-small CLS features. Precedence: CLI
`--board-identity-threshold`, then `ref_pack.identity_threshold`, then plan
`board_image_gate.identity_threshold`. Calibration on EP-01 is open.

## Judge policy

Recorded answers first (`--board-judge-answers`), else a loopback-only local
vision-language model (`KUBRICK_BOARD_VLM_URL`). A remote URL is refused. No
answer, no model, or a non yes-or-no reply is UNVERIFIED and blocks.

## Opt-out

`--board-image-opt-out REASON` or `KUBRICK_BOARD_IMAGE_OPT_OUT`. A blank
reason is `BOARD_OPT_OUT_REASON_MISSING`. The opt-out prints one
`BOARD_IMAGE_OPT_OUT` stderr line and is kept in the run ledger.

## Dependencies and tests

The optional `board-vision` extra holds `torch`, `transformers`, and
`Pillow`. They are imported on first use. Tests use fixture PNGs in
`evals/fixtures/board_images/`, a mocked embedder, recorded or fake judges,
and a throwaway loopback HTTP server. No paid API is called.

# Board gate

`src/kubrick/gates/board_qc.py` checks a start board before a video packet.
Measurements are fixtures. The command is `python scripts/board_qc.py --input
PATH`. It does not call a detector or a paid API.

`carrier_for` returns `{lock_id, carrier, evidence, status}`. Status is
`verified`, `unverified`, or `contradicted`. A start frame or a chain with no
image evidence is `unverified`, not `start_frame`. A board that shows silicon
hands can verify that lock. Human hands on that lock are
`BOARD_LOCK_CONTRADICTED` / `HUMAN_HAND_ON_SILICON_LOCK` and the packet is
refused. The recommendation is refs-only with a material insert plus an
identity ref.

A knees-up ask on a plate that still shows the ankles is `crop_line` and
blocks the packet. A shot with `join: cut` does not keep a start frame
inherited from the previous shot. A chained shot still can when the board
evidence is `verified`.

The board checks are `aspect`, `head_ratio`, `headroom_frac`, `crop_line`,
`subject_centroid`, `edge_cut`, `safe_zone`, `horizon_tilt`, `lead_room`,
`lens_side`, `screen_dir_180`, `eyeline_y`, `light_emitter`, `brightness`,
`ref_copy`, `text_render`, and `char_count`, plus `ASYMMETRY_TURN_RISK`.
`edge_cut` warns `EDGE_CUT`. A face outside the 9:16 safe box warns
`SAFE_ZONE_VIOLATION`. A copied previous board warns `PREV_BOARD_REF_COPY`.
A three-quarter turn on a locked asymmetry warns `ASYMMETRY_TURN_RISK`.

Fixtures: `evals/fixtures/ep01/board_gate_cases.yaml`.

## Board image checks

The fixture gate above never opens an image. The board image gate in
`src/kubrick/gates/board_image_gate.py` does: `video runbook` runs it on
every paid shot's local board image before any credit figure. It is on by
default and fails closed. See
[`JEV-PRE-SPEND-GATE.md`](JEV-PRE-SPEND-GATE.md#board-image-checks) for the
checks, the threshold, the judge policy, and the opt-out. Run it alone with
`python scripts/board_image_gate.py --input PLAN [--shot ID]`.

# Numeric framing

`src/kubrick/prompts/framing.py` reads plan fields. It does not call a provider
and it does not add a last-frame field to a Keyframe shot.

When a shot uses a start frame (`start_frame.asset`, `sourceFrame`, or
`source_shot`, or `join.chain_from`) and names one action and one camera move,
the video prompt is `{action} as {move}`. The image prompt keeps the still.
Two or more moves in `camera.move` produce no motion line. A list of two
primary moves warns `MOVE_CHAIN_CONFLICT`. One move does not.

`board_prompt` orders the start board as size and lens, angle and height,
placement, crop, head-ratio band (`head ratio 0.55 to 0.60`), facing, emitters
that must stay off as positive dark wording (an emitter `desk lamp` becomes
`the desk lamp stays dark`), and key side. An end band is included when
`end_framing` has one.

An end anchor is required when size or crop changes, or the head-ratio
midpoint moves by more than 0.05. Shot 09 (0.55–0.60 to 0.40–0.45) is an
anchor. The Keyframe `create_movie` schema has `startImage` and no end-image
field, so prep records `END_IMAGE_UNSUPPORTED` with that target. The shot
object does not gain `lastFrame`.

`safe_box(width, height)` scales the 1080×1920 rectangle (140, 940, 220, 1436).
`delivery.platform` names the target. The ratios stay the same. 478×856 and
768×1376 are the checked sizes.

A tight crop (`knees_up`, `ecu`, `cu`) on a wide `location_ref.plate` warns
`WIDE_PLATE_OVERRIDES_CROP` and `CROP_UNREACHABLE_FROM_PLATE` unless
`location_ref.precrop_to` is that crop. Other codes: `ADJECTIVE_PROPORTION`,
`MOVE_WITHOUT_END_ANCHOR`, `MOVE_TARGET_MISSING`, `AXIS_CROSS_UNBRIDGED`,
`VIDEO_REFRAME_IGNORED`.

Plans that do not carry `framing`, `end_framing`, `continuity`, `location_ref`,
or an explicit video prompt stay on the previous video text, except the
motion line above when a start frame and one move are already present.

Fixtures: `evals/fixtures/ep01/framing_cases.yaml`.

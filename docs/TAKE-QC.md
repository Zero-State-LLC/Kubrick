# Take QC core

`src/kubrick/qc/vision_observe.py` scores a take from fixture measurements.
The command is `python scripts/vision_observe.py --input PATH`. It does not
call MediaPipe, a VLM, Keyframe, or any other paid API.

Samples are the first frame, the middle, the last frame, each cut, and the
end of the 1.6 second hold. A defect is `{hold_id, score, t_start, t_end,
defect_code}`. Score 2 is a defect. Score 1 is marginal and stays off the
defect list. A clean take has an empty defect list. The report is
**PROPOSED**. A missing measurement the check needs is `NOT_COMPUTABLE`.

A non-human head with no pose landmarks uses `head_source: dome`. A pose
ratio without landmarks is not invented.

EP-01 cases live in `evals/fixtures/ep01/take_qc_cases.yaml`. The twelve
restart rows cover knees-up crop, push-in head drift, edge paste, back LEDs,
lens glow, grille light, debris that is too small to shoot, an open that
copies the reference, landscape aspect, human hands on a silicon lock,
a flipped lens side, and a copied board. `open_copy` also warns
`REF_OPEN_COPY`. A start that never releases warns `START_HOLD`.

Optional detector packages are listed, commented out, in
`requirements-qc.txt`. CI does not install that file.

`src/kubrick/qc/take_qc.py` is the full check on that core. A VLM verdict is
a fixture (`status: pass|fail`). `live: true` or a provider name is
`NOT_COMPUTABLE` and no model is called. Identity is a fixture similarity
against a threshold (default 0.85). Timestamps must cover the sample clock
and stay inside the duration. ffmpeg is off unless the document sets
`ffmpeg: true` and the caller passes a runner. The module does not import
`subprocess`. `video_cut_qa` still only prints commands.
